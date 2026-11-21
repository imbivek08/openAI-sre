"""Structured schemas for the investigation engine and model outputs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    timestamp: datetime | None = None
    description: str
    source: str = ""


class AlternativeHypothesis(BaseModel):
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    """Final structured report produced by the investigation engine."""

    incident_summary: str
    most_likely_root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: str = "low"  # low | medium | high
    confidence_rationale: str
    observed_facts: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)  # evidence IDs
    contradicting_evidence: list[str] = Field(default_factory=list)  # evidence IDs
    alternative_hypotheses: list[AlternativeHypothesis] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    recommended_diagnostics: list[str] = Field(default_factory=list)
    recommended_remediation: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    uncertainty: str
    human_intervention_required: bool = True
    limits_reached: bool = False


class FindingModel(BaseModel):
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_rationale: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    explanation: str
    next_diagnostics: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)
    human_approval_required: bool = True


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    usage: dict = Field(default_factory=dict)
    raw_finish_reason: str | None = None


class EngineLimits(BaseModel):
    max_iterations: int = 6
    max_tool_calls: int = 20
    max_wall_time_seconds: float = 300.0
    max_context_bytes: int = 200_000
    max_tool_output_bytes: int = 262_144
    tool_timeout_seconds: float = 20.0
