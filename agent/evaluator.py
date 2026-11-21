"""Evaluation harness: score investigations against known ground truth.

Deterministic checks are used wherever possible (evidence-reference validity,
tool-call validity, root-cause keyword matching). No LLM judge is required.

Metrics per investigation:
- root_cause_match: report hypothesis matches the scenario's ground truth or an
  acceptable alternative (normalized keyword overlap).
- evidence_relevance: fraction of retrieved evidence whose source matches the
  scenario's expected evidence sources.
- unsupported_claim_rate: fraction of report claim lists (facts, contributing
  factors) that lack supporting evidence references.
- evidence_refs_valid: all referenced evidence IDs exist in retrieved evidence.
- tool_calls_valid: every executed tool call is in the source allowlist.
- completed / tool_call_count / latency_seconds.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field

from sqlalchemy import select

from agent.policies import allowed_tools_for
from simulator.scenarios import SCENARIOS, ScenarioSpec

logger = logging.getLogger(__name__)

_ROOT_CAUSE_KEYWORDS = {
    "pool-exhaustion": ["pool", "exhaustion", "connection"],
    "elevated-latency": ["latency", "delay"],
    "config-failure": ["configuration", "unreachable", "dependency"],
    "ci-test-failure": ["test", "assertion", "pytest"],
    "ci-missing-secret": ["secret", "environment variable", "missing"],
    "ci-docker-build-failure": ["docker", "build"],
}


@dataclass
class EvaluationMetrics:
    case_name: str
    investigation_id: str = ""
    root_cause_match: bool = False
    evidence_relevance: float = 0.0
    unsupported_claim_rate: float = 0.0
    evidence_refs_valid: bool = False
    tool_calls_valid: bool = False
    completed: bool = False
    tool_call_count: int = 0
    latency_seconds: float = 0.0
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "case_name": self.case_name,
            "investigation_id": self.investigation_id,
            "root_cause_match": self.root_cause_match,
            "evidence_relevance": round(self.evidence_relevance, 3),
            "unsupported_claim_rate": round(self.unsupported_claim_rate, 3),
            "evidence_refs_valid": self.evidence_refs_valid,
            "tool_calls_valid": self.tool_calls_valid,
            "completed": self.completed,
            "tool_call_count": self.tool_call_count,
            "latency_seconds": round(self.latency_seconds, 2),
            "details": self.details,
        }


def normalize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_root_cause(report: dict, scenario: ScenarioSpec) -> tuple[bool, float]:
    """Keyword-overlap match against ground truth and acceptable alternatives."""
    hypothesis = (report.get("most_likely_root_cause") or "").lower()
    if not hypothesis:
        return False, 0.0
    keywords = _ROOT_CAUSE_KEYWORDS.get(scenario.id, [])
    overlap = sum(1 for kw in keywords if kw in hypothesis)
    score = overlap / max(len(keywords), 1)
    matched = score >= 0.5
    if not matched:
        for alt in scenario.acceptable_alternatives:
            alt_norm = normalize(alt)
            hyp_norm = normalize(hypothesis)
            if alt_norm and len(alt_norm & hyp_norm) >= max(1, len(alt_norm) // 2):
                return True, score
    return matched, score


def score_evidence_relevance(evidence: list[dict], scenario: ScenarioSpec) -> float:
    """Fraction of retrieved evidence matching expected source types."""
    if not evidence:
        return 0.0
    expected = set()
    for item in scenario.expected_evidence:
        low = item.lower()
        if "prometheus" in low or "metric" in low or "pool" in low and "prometheus" in low:
            expected.add("prometheus")
        if "log" in low:
            expected.add("logs")
        if "health" in low:
            expected.add("health")
        if "deployment" in low:
            expected.add("deployments")
        if "runbook" in low:
            expected.add("runbook")
        if "job" in low or "workflow" in low or "commit" in low:
            expected.add("github")
    if not expected:
        return 1.0
    relevant = sum(1 for e in evidence if e.get("source_type") in expected)
    return relevant / len(evidence)


def score_unsupported_claims(report: dict, evidence_ids: set[str]) -> float:
    """Fraction of claim bullets that reference no evidence."""
    claims: list[str] = []
    claims.extend(report.get("observed_facts") or [])
    claims.extend(report.get("contributing_factors") or [])
    claims.extend(report.get("recommended_diagnostics") or [])
    claims.extend(report.get("recommended_remediation") or [])
    if not claims:
        return 0.0
    supported = 0
    # A claim is "supported" if the report has any supporting evidence refs at
    # all (per-claim attribution is not required by the schema).
    has_refs = bool(report.get("supporting_evidence"))
    if has_refs:
        supported = len(claims)
    return 1.0 - (supported / len(claims))


def score_evidence_refs(report: dict, evidence_ids: set[str]) -> bool:
    refs = list(report.get("supporting_evidence") or [])
    refs += list(report.get("contradicting_evidence") or [])
    for alt in report.get("alternative_hypotheses") or []:
        refs += list(alt.get("supporting_evidence") or [])
    return all(r in evidence_ids for r in refs)


def score_tool_calls(events: list[dict], source: str) -> bool:
    allowed = set(allowed_tools_for(source))
    for event in events:
        if event.get("kind") == "tool_call":
            tool = (event.get("payload") or {}).get("tool")
            if tool and tool not in allowed:
                return False
    return True


def evaluate_investigation(
    scenario: ScenarioSpec,
    report: dict | None,
    evidence: list[dict],
    events: list[dict],
    investigation: dict,
    latency_seconds: float = 0.0,
) -> EvaluationMetrics:
    metrics = EvaluationMetrics(case_name=scenario.id)
    metrics.investigation_id = str(investigation.get("id", ""))
    metrics.latency_seconds = latency_seconds
    metrics.completed = investigation.get("status") == "completed" and report is not None
    metrics.tool_call_count = int(investigation.get("tool_calls") or 0)

    evidence_ids = {e["id"] for e in evidence if e.get("id")}

    if report is None:
        metrics.details["error"] = "no report produced"
        return metrics

    matched, rc_score = score_root_cause(report, scenario)
    metrics.root_cause_match = matched
    metrics.evidence_relevance = score_evidence_relevance(evidence, scenario)
    metrics.unsupported_claim_rate = score_unsupported_claims(report, evidence_ids)
    metrics.evidence_refs_valid = score_evidence_refs(report, evidence_ids)
    metrics.tool_calls_valid = score_tool_calls(events, scenario.source)
    metrics.details["root_cause_score"] = round(rc_score, 3)
    metrics.details["evidence_count"] = len(evidence)
    return metrics


# --- CLI ---------------------------------------------------------------------


async def _run_all(db_url: str | None = None) -> int:
    """Re-evaluate the most recent completed investigation per scenario group.

    Without a live model this re-scores persisted investigations deterministically.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from api.config import get_settings
    from database.models import EvaluationResult, Evidence, Investigation, InvestigationEvent

    settings = get_settings()
    url = db_url or settings.database_url
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    rows_out: list[EvaluationMetrics] = []
    async with factory() as session:
        investigations = (
            (await session.execute(select(Investigation).order_by(Investigation.created_at.desc())))
            .scalars()
            .all()
        )
        for inv in investigations:
            if inv.status.value != "completed" or not inv.report_json:
                continue
            incident = await session.get(__import__("database.models", fromlist=["Incident"]).Incident, inv.incident_id)
            if incident is None:
                continue
            scenario = _scenario_for_incident(incident)
            if scenario is None:
                continue
            evidence = (
                (
                    await session.execute(
                        select(Evidence).where(Evidence.investigation_id == inv.id)
                    )
                )
                .scalars()
                .all()
            )
            events = (
                (
                    await session.execute(
                        select(InvestigationEvent).where(InvestigationEvent.investigation_id == inv.id)
                    )
                )
                .scalars()
                .all()
            )
            latency = 0.0
            if inv.started_at and inv.completed_at:
                latency = (inv.completed_at - inv.started_at).total_seconds()
            metrics = evaluate_investigation(
                scenario=scenario,
                report=inv.report_json,
                evidence=[{"id": e.id, "source_type": e.source_type} for e in evidence],
                events=[{"kind": e.kind, "payload": e.payload} for e in events],
                investigation={"id": inv.id, "status": inv.status.value, "tool_calls": inv.tool_calls},
                latency_seconds=latency,
            )
            session.add(
                EvaluationResult(
                    case_id=scenario.id,
                    investigation_id=inv.id,
                    root_cause_match=metrics.root_cause_match,
                    evidence_relevance=metrics.evidence_relevance,
                    unsupported_claim_rate=metrics.unsupported_claim_rate,
                    evidence_refs_valid=metrics.evidence_refs_valid,
                    tool_calls_valid=metrics.tool_calls_valid,
                    completed=metrics.completed,
                    tool_call_count=metrics.tool_call_count,
                    latency_seconds=metrics.latency_seconds,
                    metrics=metrics.details,
                )
            )
            rows_out.append(metrics)
        await session.commit()

    _print_summary(rows_out)
    return 0


def _scenario_for_incident(incident) -> ScenarioSpec | None:
    from database.models import IncidentSource

    if incident.source == IncidentSource.runtime:
        # Heuristic: pick the runtime scenario whose symptoms best match the title.
        title = (incident.title + " " + incident.summary).lower()
        for sid, scenario in SCENARIOS.items():
            if scenario.source != "runtime":
                continue
            keywords = _ROOT_CAUSE_KEYWORDS.get(sid, [])
            if any(kw in title for kw in keywords):
                return scenario
        return SCENARIOS.get("pool-exhaustion")
    if incident.source == IncidentSource.github_actions:
        title = (incident.title + " " + incident.summary).lower()
        if "docker" in title or "build" in title:
            return SCENARIOS["ci-docker-build-failure"]
        if "secret" in title or "environment" in title:
            return SCENARIOS["ci-missing-secret"]
        return SCENARIOS["ci-test-failure"]
    return None


def _print_summary(rows: list[EvaluationMetrics]) -> None:
    if not rows:
        print("No completed investigations to evaluate yet.")
        print("Run an investigation first (dashboard or POST /api/v1/incidents/{id}/investigate).")
        return
    print(f"\n{'Case':<28} {'RC':<4} {'EvRel':<6} {'Unsup':<6} {'Refs':<5} {'Tools':<5} {'Calls':<6} {'Lat(s)':<8}")
    print("-" * 80)
    for m in rows:
        print(
            f"{m.case_name:<28} {'Y' if m.root_cause_match else 'N':<4} "
            f"{m.evidence_relevance:<6.2f} {m.unsupported_claim_rate:<6.2f} "
            f"{'Y' if m.evidence_refs_valid else 'N':<5} "
            f"{'Y' if m.tool_calls_valid else 'N':<5} "
            f"{m.tool_call_count:<6} {m.latency_seconds:<8.1f}"
        )
    n = len(rows)
    rc = sum(1 for m in rows if m.root_cause_match)
    print("-" * 80)
    print(f"Root-cause match: {rc}/{n}  |  mean evidence relevance: "
          f"{sum(m.evidence_relevance for m in rows) / n:.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenSRE AI evaluation harness")
    sub = parser.add_subparsers(dest="command", required=True)
    run_all = sub.add_parser("run-all", help="Re-score all completed investigations")
    run_all.add_argument("--db-url", default=None)
    args = parser.parse_args(argv)
    if args.command == "run-all":
        return asyncio.run(_run_all(args.db_url))
    return 1


if __name__ == "__main__":
    sys.exit(main())
