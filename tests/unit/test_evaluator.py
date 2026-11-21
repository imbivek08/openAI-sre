"""Tests for the evaluation harness scoring functions."""

from agent.evaluator import (
    evaluate_investigation,
    score_evidence_refs,
    score_root_cause,
    score_tool_calls,
    score_unsupported_claims,
)
from simulator.scenarios import SCENARIOS


def test_root_cause_match_on_keywords():
    scenario = SCENARIOS["pool-exhaustion"]
    report = {"most_likely_root_cause": "Database connection-pool exhaustion due to held connections"}
    matched, score = score_root_cause(report, scenario)
    assert matched is True
    assert score >= 0.5


def test_root_cause_mismatch():
    scenario = SCENARIOS["pool-exhaustion"]
    report = {"most_likely_root_cause": "The UI button was the wrong color"}
    matched, _ = score_root_cause(report, scenario)
    assert matched is False


def test_evidence_refs_valid():
    report = {"supporting_evidence": ["ev-1", "ev-2"], "contradicting_evidence": [], "alternative_hypotheses": []}
    assert score_evidence_refs(report, {"ev-1", "ev-2", "ev-3"}) is True


def test_evidence_refs_invalid():
    report = {"supporting_evidence": ["ev-1", "ev-999"], "contradicting_evidence": [], "alternative_hypotheses": []}
    assert score_evidence_refs(report, {"ev-1"}) is False


def test_tool_calls_valid():
    events = [
        {"kind": "tool_call", "payload": {"tool": "query_prometheus"}},
        {"kind": "tool_call", "payload": {"tool": "search_application_logs"}},
    ]
    assert score_tool_calls(events, "runtime") is True


def test_tool_calls_invalid():
    events = [{"kind": "tool_call", "payload": {"tool": "get_workflow_run"}}]
    assert score_tool_calls(events, "runtime") is False


def test_unsupported_claims_zero_when_refs_present():
    report = {
        "observed_facts": ["fact one", "fact two"],
        "contributing_factors": [],
        "recommended_diagnostics": [],
        "recommended_remediation": [],
        "supporting_evidence": ["ev-1"],
    }
    assert score_unsupported_claims(report, {"ev-1"}) == 0.0


def test_unsupported_claims_one_when_no_refs():
    report = {
        "observed_facts": ["fact one"],
        "contributing_factors": [],
        "recommended_diagnostics": [],
        "recommended_remediation": [],
        "supporting_evidence": [],
    }
    assert score_unsupported_claims(report, set()) == 1.0


def test_evaluate_investigation_full():
    scenario = SCENARIOS["pool-exhaustion"]
    report = {
        "most_likely_root_cause": "Database connection-pool exhaustion",
        "observed_facts": ["pool timeout"],
        "contributing_factors": [],
        "recommended_diagnostics": [],
        "recommended_remediation": [],
        "supporting_evidence": ["ev-1"],
        "contradicting_evidence": [],
        "alternative_hypotheses": [],
    }
    evidence = [{"id": "ev-1", "source_type": "prometheus"}]
    events = [{"kind": "tool_call", "payload": {"tool": "query_prometheus"}}]
    metrics = evaluate_investigation(
        scenario=scenario,
        report=report,
        evidence=evidence,
        events=events,
        investigation={"id": "inv-1", "status": "completed", "tool_calls": 1},
        latency_seconds=12.3,
    )
    assert metrics.root_cause_match is True
    assert metrics.evidence_refs_valid is True
    assert metrics.tool_calls_valid is True
    assert metrics.completed is True
    assert metrics.latency_seconds == 12.3
