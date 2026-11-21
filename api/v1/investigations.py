"""Investigation detail endpoints."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.db import get_session
from database.models import Evidence, Finding, Investigation, InvestigationEvent

logger = logging.getLogger(__name__)
router = APIRouter()


class FindingResponse(BaseModel):
    id: str
    hypothesis: str
    confidence: float
    confidence_rationale: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    explanation: str
    next_diagnostics: list[str]
    remediation: list[str]
    human_approval_required: bool
    is_primary: bool


class InvestigationResponse(BaseModel):
    id: str
    incident_id: str
    provider: str
    model: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    iterations: int
    tool_calls: int
    error: str
    limits_reached: bool
    report: dict | None
    findings: list[FindingResponse]


class EventResponse(BaseModel):
    id: str
    kind: str
    payload: dict
    created_at: datetime | None


class EvidenceResponse(BaseModel):
    id: str
    source_type: str
    source_id: str
    excerpt: str
    retrieved_at: datetime | None
    tool: str
    metadata: dict
    content_hash: str
    sensitivity: str


@router.get("/investigations/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(investigation_id: str, session=Depends(get_session)):
    investigation = await session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    findings = (
        await session.execute(
            select(Finding)
            .where(Finding.investigation_id == investigation_id)
            .order_by(Finding.is_primary.desc())
        )
    ).scalars().all()
    return InvestigationResponse(
        id=investigation.id,
        incident_id=investigation.incident_id,
        provider=investigation.provider,
        model=investigation.model,
        status=investigation.status.value,
        started_at=investigation.started_at,
        completed_at=investigation.completed_at,
        iterations=investigation.iterations,
        tool_calls=investigation.tool_calls,
        error=investigation.error,
        limits_reached=investigation.limits_reached,
        report=investigation.report_json,
        findings=[
            FindingResponse(
                id=f.id,
                hypothesis=f.hypothesis,
                confidence=f.confidence,
                confidence_rationale=f.confidence_rationale,
                supporting_evidence=f.supporting_evidence,
                contradicting_evidence=f.contradicting_evidence,
                explanation=f.explanation,
                next_diagnostics=f.next_diagnostics,
                remediation=f.remediation,
                human_approval_required=f.human_approval_required,
                is_primary=f.is_primary,
            )
            for f in findings
        ],
    )


@router.get("/investigations/{investigation_id}/events", response_model=dict)
async def get_investigation_events(
    investigation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session=Depends(get_session),
):
    investigation = await session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    stmt = (
        select(InvestigationEvent)
        .where(InvestigationEvent.investigation_id == investigation_id)
        .order_by(InvestigationEvent.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [
            EventResponse(id=e.id, kind=e.kind, payload=e.payload, created_at=e.created_at) for e in rows
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/investigations/{investigation_id}/evidence", response_model=dict)
async def get_investigation_evidence(
    investigation_id: str,
    source_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session=Depends(get_session),
):
    investigation = await session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    stmt = select(Evidence).where(Evidence.investigation_id == investigation_id)
    if source_type:
        stmt = stmt.where(Evidence.source_type == source_type)
    stmt = stmt.order_by(Evidence.retrieved_at.asc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [
            EvidenceResponse(
                id=e.id,
                source_type=e.source_type,
                source_id=e.source_id,
                excerpt=e.excerpt,
                retrieved_at=e.retrieved_at,
                tool=e.tool,
                metadata=e.metadata_json,
                content_hash=e.content_hash,
                sensitivity=e.sensitivity,
            )
            for e in rows
        ],
        "page": page,
        "page_size": page_size,
    }
