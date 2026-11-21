"""Bounded investigation loop — the core of OpenSRE AI.

The engine orchestrates a model provider and a validated tool registry to
gather real evidence, then produces a structured, evidence-referenced report.
It enforces configurable limits on iterations, tool calls, wall-clock time,
context size, tool output size, and per-tool timeouts.

The engine never fabricates evidence: every fact in a report must reference
evidence actually retrieved during the investigation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Protocol

from agent.policies import allowed_tools_for
from agent.prompts import (
    CONTINUE_INSTRUCTION,
    FINAL_REPORT_INSTRUCTION,
    SYSTEM_PROMPT,
    UNTRUSTED_DATA_FOOTER,
    UNTRUSTED_DATA_HEADER,
    policy_for_source,
)
from agent.providers.base import ModelProvider, ProviderError, parse_structured
from agent.schemas import EngineLimits, InvestigationReport, ProviderResponse, ToolCallRequest
from tools.registry import (
    ToolExecutionError,
    ToolOutputTooLargeError,
    ToolTimeoutError,
    ToolValidationError,
    get_registry,
)

logger = logging.getLogger(__name__)


class InvestigationStore(Protocol):
    async def add_event(self, investigation_id: str, kind: str, payload: dict) -> None: ...

    async def add_evidence(
        self,
        investigation_id: str,
        source_type: str,
        source_id: str,
        excerpt: str,
        tool: str,
        metadata: dict,
    ) -> str: ...

    async def add_findings(self, investigation_id: str, report: InvestigationReport) -> None: ...

    async def complete_investigation(
        self,
        investigation_id: str,
        status: str,
        report: InvestigationReport | None,
        tool_calls: int,
        iterations: int,
        error: str,
        limits_reached: bool,
    ) -> None: ...


# Map tool names to evidence source types.
TOOL_SOURCE_TYPES = {
    "query_prometheus": "prometheus",
    "search_application_logs": "logs",
    "get_service_health": "health",
    "get_recent_deployments": "deployments",
    "search_runbook": "runbook",
    "get_workflow_run": "github",
    "get_workflow_jobs": "github",
    "get_failed_job_logs": "github",
    "get_commit_details": "github",
    "get_changed_files": "github",
}


class InvestigationEngine:
    def __init__(
        self,
        provider: ModelProvider,
        store: InvestigationStore,
        limits: EngineLimits | None = None,
    ) -> None:
        self.provider = provider
        self.store = store
        self.limits = limits or EngineLimits()
        self.registry = get_registry()
        self._allowed: set[str] = set()

    async def run(
        self,
        investigation_id: str,
        incident: dict,
        source: str,
    ) -> InvestigationReport | None:
        """Run the bounded investigation loop. Returns the report or None on failure."""
        allowlist = allowed_tools_for(source)
        policy = policy_for_source(source)
        incident_block = json.dumps(incident, default=str)
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": policy},
            {
                "role": "user",
                "content": (
                    "INCIDENT UNDER INVESTIGATION:\n"
                    f"{incident_block}\n\n"
                    "Gather evidence with the approved tools, then produce the final report."
                ),
            },
        ]

        deadline = time.monotonic() + self.limits.max_wall_time_seconds
        tool_call_count = 0
        context_bytes = 0
        evidence_ids: set[str] = set()
        limits_reached = False
        iterations = 0
        last_error = ""
        allowed = set(allowlist)
        self._allowed = allowed

        await self.store.add_event(investigation_id, "started", {"source": source, "policy": policy[:200]})

        for iteration in range(1, self.limits.max_iterations + 1):
            iterations = iteration
            if time.monotonic() >= deadline:
                limits_reached = True
                last_error = "Wall-clock limit reached"
                await self.store.add_event(investigation_id, "limit", {"limit": "wall_time"})
                break
            if tool_call_count >= self.limits.max_tool_calls:
                limits_reached = True
                last_error = "Tool-call limit reached"
                await self.store.add_event(investigation_id, "limit", {"limit": "tool_calls"})
                break
            if context_bytes >= self.limits.max_context_bytes:
                limits_reached = True
                last_error = "Context size limit reached"
                await self.store.add_event(investigation_id, "limit", {"limit": "context_size"})
                break

            await self.store.add_event(
                investigation_id, "iteration", {"iteration": iteration, "tool_calls_so_far": tool_call_count}
            )
            response = await self._call_provider(messages, allowlist, finalize=False)

            if response.tool_calls:
                messages.append(_assistant_message(response))
                for call in response.tool_calls:
                    if tool_call_count >= self.limits.max_tool_calls:
                        limits_reached = True
                        last_error = "Tool-call limit reached during batch"
                        break
                    tool_call_count += 1
                    evidence_id_or_error = await self._execute_tool(
                        investigation_id, call, messages, evidence_ids
                    )
                    if evidence_id_or_error:
                        context_bytes += 2000  # approximate context growth tracking
                if limits_reached:
                    break
                continue

            # No tool calls: treat content as a final report attempt.
            report = self._try_parse_report(response.content)
            if report is not None:
                report, refs_valid = self._validate_evidence_refs(report, evidence_ids)
                await self.store.add_event(
                    investigation_id,
                    "finalized",
                    {"evidence_refs_valid": refs_valid, "tool_calls": tool_call_count},
                )
                await self.store.add_findings(investigation_id, report)
                await self.store.complete_investigation(
                    investigation_id,
                    "completed",
                    report,
                    tool_call_count,
                    iterations,
                    error="",
                    limits_reached=limits_reached,
                )
                return report

            # Unparsable final answer — nudge once, then move on.
            messages.append({"role": "assistant", "content": response.content or ""})
            messages.append({"role": "user", "content": CONTINUE_INSTRUCTION})
            await self.store.add_event(
                investigation_id, "unparsed_response", {"content_preview": (response.content or "")[:200]}
            )

        # Loop ended without a valid report — make one final attempt with
        # whatever evidence we have, or fail gracefully.
        return await self._finalize_or_fail(
            investigation_id,
            messages,
            allowlist,
            evidence_ids,
            tool_call_count,
            iterations,
            limits_reached,
            last_error,
        )

    # ------------------------------------------------------------------

    async def _call_provider(
        self, messages: list[dict], allowlist: list[str], finalize: bool
    ) -> ProviderResponse:
        tools = None
        if self.provider.supports_tool_calling and not finalize:
            tools = self.registry.tool_dicts(allowlist)
        try:
            return await self.provider.complete(
                messages=messages,
                tools=tools,
                response_schema=InvestigationReport if finalize or not self.provider.supports_tool_calling else None,
                temperature=0.1,
                max_tokens=4096,
            )
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Provider call failed: {type(exc).__name__}: {exc}") from exc

    async def _execute_tool(
        self,
        investigation_id: str,
        call: ToolCallRequest,
        messages: list[dict],
        evidence_ids: set[str],
    ) -> str | None:
        spec = self.registry.get(call.tool_name)
        if spec is None:
            await self.store.add_event(
                investigation_id, "tool_call", {"tool": call.tool_name, "status": "rejected_unknown"}
            )
            messages.append(_tool_message(call.tool_name, json.dumps({"error": f"Unknown tool: {call.tool_name}"})))
            return None
        if call.tool_name not in self._allowed:
            await self.store.add_event(
                investigation_id,
                "tool_call",
                {"tool": call.tool_name, "status": "rejected_not_in_allowlist"},
            )
            messages.append(
                _tool_message(
                    call.tool_name,
                    json.dumps({"error": f"Tool {call.tool_name} is not allowed for this incident source"}),
                )
            )
            return None

        started = time.monotonic()
        try:
            result = await self.registry.execute(call.tool_name, call.arguments)
        except ToolValidationError as exc:
            await self.store.add_event(
                investigation_id, "tool_call", {"tool": call.tool_name, "status": "invalid_args", "error": str(exc)[:300]}
            )
            messages.append(_tool_message(call.tool_name, json.dumps({"error": str(exc)[:500]})))
            return None
        except ToolTimeoutError as exc:
            await self.store.add_event(investigation_id, "tool_call", {"tool": call.tool_name, "status": "timeout"})
            messages.append(_tool_message(call.tool_name, json.dumps({"error": str(exc)[:500]})))
            return None
        except (ToolExecutionError, ToolOutputTooLargeError) as exc:
            await self.store.add_event(
                investigation_id, "tool_call", {"tool": call.tool_name, "status": "error", "error": str(exc)[:300]}
            )
            messages.append(_tool_message(call.tool_name, json.dumps({"error": str(exc)[:500]})))
            return None
        elapsed = time.monotonic() - started

        excerpt = result[: self.limits.max_tool_output_bytes]
        evidence_id = await self.store.add_evidence(
            investigation_id=investigation_id,
            source_type=TOOL_SOURCE_TYPES.get(call.tool_name, "unknown"),
            source_id=call.tool_name,
            excerpt=excerpt,
            tool=call.tool_name,
            metadata={"arguments": _safe_args(call.arguments), "duration_seconds": round(elapsed, 3)},
        )
        evidence_ids.add(evidence_id)
        await self.store.add_event(
            investigation_id,
            "tool_call",
            {"tool": call.tool_name, "status": "ok", "evidence_id": evidence_id, "duration_seconds": round(elapsed, 3)},
        )
        messages.append(
            _tool_message(
                call.tool_name,
                json.dumps(
                    {
                        "evidence_id": evidence_id,
                        "tool": call.tool_name,
                        "result": excerpt,
                    }
                ),
            )
        )
        return evidence_id

    def _try_parse_report(self, content: str | None) -> InvestigationReport | None:
        if not content:
            return None
        try:
            return parse_structured(content, InvestigationReport)
        except ProviderError:
            return None

    def _validate_evidence_refs(
        self, report: InvestigationReport, evidence_ids: set[str]
    ) -> tuple[InvestigationReport, bool]:
        """Ensure every evidence reference points at evidence actually retrieved."""
        refs_valid = True
        for field in ("supporting_evidence", "contradicting_evidence"):
            refs = getattr(report, field)
            valid = [r for r in refs if r in evidence_ids]
            if len(valid) != len(refs):
                refs_valid = False
                dropped = [r for r in refs if r not in evidence_ids]
                logger.warning("Dropping %d invalid evidence refs from %s", len(dropped), field)
            setattr(report, field, valid)
        for alt in report.alternative_hypotheses:
            alt.supporting_evidence = [r for r in alt.supporting_evidence if r in evidence_ids]
        if not refs_valid:
            report.uncertainty = (
                (report.uncertainty + " ").strip()
                + "Note: some evidence references could not be verified against retrieved evidence and were removed."
            ).strip()
        # A report with zero supporting evidence is not acceptable.
        if not report.supporting_evidence and not report.contradicting_evidence:
            refs_valid = False
        return report, refs_valid

    async def _finalize_or_fail(
        self,
        investigation_id: str,
        messages: list[dict],
        allowlist: list[str],
        evidence_ids: set[str],
        tool_call_count: int,
        iterations: int,
        limits_reached: bool,
        last_error: str,
    ) -> InvestigationReport | None:
        messages.append({"role": "user", "content": FINAL_REPORT_INSTRUCTION})
        try:
            response = await self._call_provider(messages, allowlist, finalize=True)
        except ProviderError as exc:
            await self.store.add_event(investigation_id, "error", {"stage": "finalize", "error": str(exc)[:300]})
            await self.store.complete_investigation(
                investigation_id, "failed", None, tool_call_count, iterations,
                error=f"Provider failed during finalization: {exc}", limits_reached=limits_reached,
            )
            return None

        report = self._try_parse_report(response.content)
        if report is None:
            await self.store.complete_investigation(
                investigation_id, "failed", None, tool_call_count, iterations,
                error="Model did not produce a valid structured report", limits_reached=limits_reached,
            )
            return None

        report, refs_valid = self._validate_evidence_refs(report, evidence_ids)
        report.limits_reached = True
        await self.store.add_event(
            investigation_id, "finalized", {"evidence_refs_valid": refs_valid, "tool_calls": tool_call_count}
        )
        await self.store.add_findings(investigation_id, report)
        await self.store.complete_investigation(
            investigation_id,
            "completed",
            report,
            tool_call_count,
            iterations,
            error=last_error,
            limits_reached=True,
        )
        return report


def _assistant_message(response: ProviderResponse) -> dict:
    msg: dict = {"role": "assistant", "content": response.content or ""}
    if response.tool_calls:
        msg["tool_calls"] = [
            {"function": {"name": c.tool_name, "arguments": json.dumps(c.arguments)}} for c in response.tool_calls
        ]
    return msg


def _tool_message(tool_name: str, content: str) -> dict:
    bounded = content[:60_000]
    return {"role": "user", "content": f"Tool result from {tool_name}:\n{UNTRUSTED_DATA_HEADER}\n{bounded}\n{UNTRUSTED_DATA_FOOTER}"}


def _safe_args(arguments: dict) -> dict:
    """Strip obvious secrets from tool arguments before audit persistence."""
    safe = {}
    for key, value in arguments.items():
        lower = str(key).lower()
        if any(marker in lower for marker in ("token", "secret", "password", "key")):
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
