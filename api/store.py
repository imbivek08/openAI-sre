"""SQLAlchemy-backed implementation of the investigation store."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agent.engine import content_hash
from agent.schemas import InvestigationReport
from database.models import Evidence, Finding, Investigation, InvestigationEvent


class SqlAlchemyInvestigationStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_event(self, investigation_id: str, kind: str, payload: dict) -> None:
        event = InvestigationEvent(
            investigation_id=investigation_id,
            kind=kind,
            payload=_jsonable(payload),
        )
        self.session.add(event)
        await self.session.commit()

    async def add_evidence(
        self,
        investigation_id: str,
        source_type: str,
        source_id: str,
        excerpt: str,
        tool: str,
        metadata: dict,
    ) -> str:
        evidence = Evidence(
            investigation_id=investigation_id,
            source_type=source_type,
            source_id=source_id,
            excerpt=excerpt[:200_000],  # bounded storage
            tool=tool,
            metadata_json=_jsonable(metadata),
            retrieved_at=datetime.now(UTC),
            content_hash=content_hash(excerpt),
            sensitivity="unclassified",
        )
        self.session.add(evidence)
        await self.session.commit()
        await self.session.refresh(evidence)
        return evidence.id

    async def add_findings(self, investigation_id: str, report: InvestigationReport) -> None:
        self.session.add(
            Finding(
                investigation_id=investigation_id,
                hypothesis=report.most_likely_root_cause,
                confidence=report.confidence,
                confidence_rationale=report.confidence_rationale,
                supporting_evidence=report.supporting_evidence,
                contradicting_evidence=report.contradicting_evidence,
                explanation=report.incident_summary,
                next_diagnostics=report.recommended_diagnostics,
                remediation=report.recommended_remediation,
                human_approval_required=report.human_intervention_required,
                is_primary=True,
            )
        )
        for alt in report.alternative_hypotheses:
            self.session.add(
                Finding(
                    investigation_id=investigation_id,
                    hypothesis=alt.hypothesis,
                    confidence=alt.confidence,
                    confidence_rationale="",
                    supporting_evidence=alt.supporting_evidence,
                    contradicting_evidence=[],
                    explanation="",
                    next_diagnostics=[],
                    remediation=[],
                    human_approval_required=True,
                    is_primary=False,
                )
            )
        await self.session.commit()

    async def complete_investigation(
        self,
        investigation_id: str,
        status: str,
        report: InvestigationReport | None,
        tool_calls: int,
        iterations: int,
        error: str,
        limits_reached: bool,
    ) -> None:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            return
        investigation.status = status  # type: ignore[assignment]
        investigation.report_json = report.model_dump(mode="json") if report else None
        investigation.tool_calls = tool_calls
        investigation.iterations = iterations
        investigation.error = error[:2000]
        investigation.limits_reached = limits_reached
        investigation.completed_at = datetime.now(UTC)
        await self.session.commit()


def _jsonable(payload: dict) -> dict:
    try:
        json.dumps(payload, default=str)
        return payload
    except (TypeError, ValueError):
        return {"unserializable": str(payload)[:500]}
