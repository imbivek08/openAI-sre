"""Incident endpoints."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from api.config import get_settings
from api.db import get_session
from database.models import (
    Incident,
    IncidentSource,
    IncidentStatus,
    Investigation,
    InvestigationStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter()

PAGE_MAX = 100


class IncidentCreate(BaseModel):
    source: str = "runtime"
    title: str = Field(min_length=1, max_length=500)
    summary: str = ""
    service: str = ""
    repository: str = ""
    severity: str = "medium"


class IncidentResponse(BaseModel):
    id: str
    source: str
    title: str
    summary: str
    service: str
    repository: str
    external_run_id: str
    severity: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None


def _to_response(incident: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=incident.id,
        source=incident.source.value,
        title=incident.title,
        summary=incident.summary,
        service=incident.service,
        repository=incident.repository,
        external_run_id=incident.external_run_id,
        severity=incident.severity,
        status=incident.status.value,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


@router.get("/incidents", response_model=dict)
async def list_incidents(
    source: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=PAGE_MAX),
    session=Depends(get_session),
):
    stmt = select(Incident)
    if source:
        stmt = stmt.where(Incident.source == source)
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(Incident.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [_to_response(i) for i in rows],
        "page": page,
        "page_size": page_size,
        "total": total or 0,
    }


@router.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: IncidentCreate,
    session=Depends(get_session),
):
    try:
        source = IncidentSource(body.source)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid source: {body.source}")
    incident = Incident(
        source=source,
        title=body.title,
        summary=body.summary,
        service=body.service,
        repository=body.repository,
        severity=body.severity,
        status=IncidentStatus.open,
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)
    return _to_response(incident)


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, session=Depends(get_session)):
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _to_response(incident)


@router.post("/incidents/{incident_id}/investigate", response_model=dict)
async def start_investigation(
    incident_id: str,
    session=Depends(get_session),
):
    """Enqueue an AI investigation for an incident.

    Returns immediately with the investigation id; the worker picks the job up
    and the frontend can poll the investigation status.
    """
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status == IncidentStatus.investigating:
        raise HTTPException(status_code=409, detail="Incident is already under investigation")

    from api.providers import build_provider

    settings = get_settings()
    if not settings.llm_configured or build_provider() is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM provider configured. Set LLM_PROVIDER, LLM_BASE_URL and "
                "LLM_MODEL (see .env.example). Infrastructure and webhook features "
                "remain available without a model."
            ),
        )

    incident.status = IncidentStatus.investigating
    investigation = Investigation(
        incident_id=incident.id,
        provider=settings.llm_provider,
        model=settings.llm_model,
        status=InvestigationStatus.queued,
    )
    session.add(investigation)
    await session.commit()
    await session.refresh(investigation)

    from api.queue import enqueue_job
    from database.models import JobKind

    await enqueue_job(JobKind.investigation, {"investigation_id": investigation.id})
    return {
        "investigation_id": investigation.id,
        "incident_id": incident.id,
        "status": "queued",
    }
