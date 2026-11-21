"""Tests for the bounded investigation loop using scripted providers.

These tests exercise the full engine (tool validation, evidence persistence,
report parsing, evidence-reference validation, limits) without any model.
"""

import json
import os
import tempfile
from datetime import UTC, datetime

import tools  # noqa: F401  (registers all built-in tools)
from agent.engine import InvestigationEngine
from agent.providers.base import ModelProvider
from agent.schemas import EngineLimits, ProviderResponse, ToolCallRequest
from integrations.logs.json_logs import JsonLogStore


class FakePrometheusClient:
    """Returns real-shaped Prometheus API responses for tests."""

    def __init__(self):
        self.base_url = "http://fake:9090"
        self.timeout = 5.0

    async def query_range(self, query, start, end, step_seconds=15):
        return {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"route": "/api/orders"},
                        "values": [[start.timestamp(), "0.9"], [end.timestamp(), "1.0"]],
                    }
                ]
            },
        }


def _configure_tools():
    """Wire test doubles into the tool modules."""
    from tools import log_tools, prometheus_tools

    prometheus_tools.set_prometheus_client(FakePrometheusClient())

    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "ERROR",
                    "service": "demo-api",
                    "message": "PoolTimeoutError: connection timed out",
                    "error_type": "PoolTimeoutError",
                }
            )
            + "\n"
        )
    log_tools.set_log_store(JsonLogStore(path))


class MemoryStore:
    def __init__(self):
        self.events = []
        self.evidence = []
        self.findings = []
        self.completed = []

    async def add_event(self, investigation_id, kind, payload):
        self.events.append({"kind": kind, "payload": payload})

    async def add_evidence(self, investigation_id, source_type, source_id, excerpt, tool, metadata):
        eid = f"ev-{len(self.evidence) + 1}"
        self.evidence.append(
            {"id": eid, "source_type": source_type, "source_id": source_id, "excerpt": excerpt, "tool": tool}
        )
        return eid

    async def add_findings(self, investigation_id, report):
        self.findings.append(report)

    async def complete_investigation(
        self, investigation_id, status, report, tool_calls, iterations, error, limits_reached
    ):
        self.completed.append(
            {
                "status": status,
                "report": report,
                "tool_calls": tool_calls,
                "iterations": iterations,
                "error": error,
                "limits_reached": limits_reached,
            }
        )


def _report(evidence_ids):
    return {
        "incident_summary": "Demo service failed",
        "most_likely_root_cause": "Database connection-pool exhaustion held all connections",
        "confidence": 0.8,
        "confidence_label": "high",
        "confidence_rationale": "Corroborated by logs and metrics",
        "observed_facts": ["Pool timeout errors in logs", "Pool utilization at 100%"],
        "hypotheses": ["pool exhaustion"],
        "supporting_evidence": evidence_ids,
        "contradicting_evidence": [],
        "alternative_hypotheses": [],
        "timeline": [],
        "contributing_factors": ["small pool size"],
        "recommended_diagnostics": ["Check pool metrics"],
        "recommended_remediation": ["Reset the lab fault"],
        "risks": ["Data loss"],
        "uncertainty": "Low uncertainty; multiple evidence sources agree",
        "human_intervention_required": True,
    }


def _tool_response(name, args):
    return ProviderResponse(content=None, tool_calls=[ToolCallRequest(tool_name=name, arguments=args)])


class EvidenceAwareProvider(ModelProvider):
    """Calls two tools, then reports with the evidence IDs it observed."""

    name = "evidence-aware"
    supports_tool_calling = True

    def __init__(self):
        self.seen_evidence_ids = []
        self._tool_calls_made = 0

    async def complete(self, messages, tools=None, response_schema=None, temperature=0.1, max_tokens=4096):
        if self._tool_calls_made < 2:
            self._tool_calls_made += 1
            if self._tool_calls_made == 1:
                return _tool_response(
                    "query_prometheus",
                    {"query_key": "db_pool_utilization_ratio", "time_range_minutes": 30},
                )
            return _tool_response("search_application_logs", {"level": "ERROR", "time_range_minutes": 30})
        for m in messages:
            content = m.get("content", "")
            if '"evidence_id"' in content:
                try:
                    start = content.index("{")
                    end = content.rindex("}") + 1
                    data = json.loads(content[start:end])
                    if "evidence_id" in data:
                        self.seen_evidence_ids.append(data["evidence_id"])
                except (json.JSONDecodeError, ValueError):
                    pass
        return ProviderResponse(content=json.dumps(_report(self.seen_evidence_ids)))


class AlwaysToolProvider(ModelProvider):
    name = "always-tool"
    supports_tool_calling = True

    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools=None, response_schema=None, temperature=0.1, max_tokens=4096):
        self.calls += 1
        return _tool_response(
            "query_prometheus",
            {"query_key": "http_requests_per_second", "time_range_minutes": 5},
        )


class BadToolProvider(ModelProvider):
    """Requests a tool outside the runtime allowlist, then reports."""

    name = "bad-tool"
    supports_tool_calling = True

    def __init__(self):
        self._first = True

    async def complete(self, messages, tools=None, response_schema=None, temperature=0.1, max_tokens=4096):
        if self._first:
            self._first = False
            return _tool_response(
                "get_workflow_run", {"owner": "a", "repo": "b", "run_id": 1}
            )
        return ProviderResponse(content=json.dumps(_report([])))


class ImmediateReportProvider(ModelProvider):
    name = "immediate-report"
    supports_tool_calling = True

    def __init__(self):
        self._first = True

    async def complete(self, messages, tools=None, response_schema=None, temperature=0.1, max_tokens=4096):
        if self._first:
            self._first = False
            return ProviderResponse(content=json.dumps(_report(["ev-nonexistent"])))
        return ProviderResponse(content=json.dumps(_report([])))


async def test_engine_gathers_evidence_then_reports():
    _configure_tools()
    store = MemoryStore()
    provider = EvidenceAwareProvider()
    engine = InvestigationEngine(
        provider=provider, store=store, limits=EngineLimits(max_iterations=6, max_tool_calls=10)
    )
    report = await engine.run(
        investigation_id="inv-1",
        incident={"id": "inc-1", "title": "Test incident", "summary": "something failed", "service": "demo-api"},
        source="runtime",
    )
    assert report is not None
    assert len(store.evidence) == 2
    assert store.completed[0]["status"] == "completed"
    assert len(report.supporting_evidence) == 2
    assert all(r in {e["id"] for e in store.evidence} for r in report.supporting_evidence)


async def test_engine_stops_at_tool_call_limit():
    store = MemoryStore()
    provider = AlwaysToolProvider()
    engine = InvestigationEngine(
        provider=provider, store=store, limits=EngineLimits(max_iterations=10, max_tool_calls=3)
    )
    await engine.run(
        investigation_id="inv-2",
        incident={"id": "inc-2", "title": "Loop", "summary": "x"},
        source="runtime",
    )
    assert store.completed[0]["tool_calls"] == 3
    assert store.completed[0]["limits_reached"] is True


async def test_engine_rejects_disallowed_tool():
    store = MemoryStore()
    engine = InvestigationEngine(provider=BadToolProvider(), store=store)
    report = await engine.run(
        investigation_id="inv-3",
        incident={"id": "inc-3", "title": "X", "summary": "y"},
        source="runtime",
    )
    rejected = [
        e
        for e in store.events
        if e["kind"] == "tool_call"
        and e["payload"].get("status") in ("rejected_unknown", "rejected_not_in_allowlist")
    ]
    assert len(rejected) == 1
    assert rejected[0]["payload"]["status"] == "rejected_not_in_allowlist"
    assert report is not None


async def test_report_with_invalid_evidence_refs_is_sanitized():
    store = MemoryStore()
    engine = InvestigationEngine(provider=ImmediateReportProvider(), store=store)
    report = await engine.run(
        investigation_id="inv-4",
        incident={"id": "inc-4", "title": "X", "summary": "y"},
        source="runtime",
    )
    assert report is not None
    assert report.supporting_evidence == []
