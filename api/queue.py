"""PostgreSQL-backed background job queue and worker.

Jobs are persisted in the `jobs` table so investigations survive restarts.
The worker polls for pending jobs inside the API process — no Redis or extra
infrastructure required for the local development stack.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from api.db import get_engine
from database.models import (
    IncidentStatus,
    Investigation,
    InvestigationStatus,
    Job,
    JobKind,
    JobStatus,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 2.0
LEADER_LOCK_MINUTES = 5


async def enqueue_job(kind: JobKind, payload: dict, max_attempts: int = 3) -> str:
    from database.models import Job as JobModel

    job = JobModel(kind=kind, payload=payload, max_attempts=max_attempts)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


class JobWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="opensre-job-worker")
            logger.info("Job worker started")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except TimeoutError:
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
        while not self._stopping.is_set():
            try:
                async with factory() as session:
                    job = await _claim_next_job(session)
                    if job is None:
                        await _sleep_or_stop(self._stopping, POLL_INTERVAL_SECONDS)
                        continue
                    await _dispatch(session, job)
            except Exception as exc:  # noqa: BLE001 - worker must not die
                logger.exception("Job worker iteration failed: %s", exc)
                await _sleep_or_stop(self._stopping, POLL_INTERVAL_SECONDS)


async def _claim_next_job(session) -> Job | None:
    now = datetime.now(UTC)
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.pending, Job.available_at <= now)
        .order_by(Job.available_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = (await session.execute(stmt)).scalars().first()
    if job is None:
        await session.rollback()
        return None
    job.status = JobStatus.running
    job.attempts += 1
    await session.commit()
    return job


async def _dispatch(session, job: Job) -> None:
    try:
        if job.kind == JobKind.investigation:
            await _run_investigation(session, job)
        elif job.kind == JobKind.github_webhook:
            await _run_github_webhook(session, job)
        else:
            raise ValueError(f"Unknown job kind: {job.kind}")
        job.status = JobStatus.done
        job.error = ""
        await session.commit()
        logger.info("Job %s (%s) completed", job.id, job.kind)
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        job.error = str(exc)[:2000]
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.failed
            await session.commit()
            logger.error("Job %s failed permanently: %s", job.id, exc)
        else:
            job.status = JobStatus.pending
            job.available_at = datetime.now(UTC) + timedelta(seconds=10 * job.attempts)
            await session.commit()
            logger.warning("Job %s attempt %d failed (%s); retrying", job.id, job.attempts, exc)


async def _run_investigation(session, job: Job) -> None:

    from agent.engine import InvestigationEngine
    from agent.schemas import EngineLimits
    from api.config import get_settings
    from api.providers import build_provider
    from api.store import SqlAlchemyInvestigationStore
    from database.models import Incident

    settings = get_settings()
    payload = job.payload or {}
    investigation_id = payload.get("investigation_id")
    if not investigation_id:
        raise ValueError("investigation job missing investigation_id")

    investigation = await session.get(Investigation, investigation_id)
    if investigation is None:
        raise ValueError(f"Investigation {investigation_id} not found")
    incident = await session.get(Incident, investigation.incident_id)
    if incident is None:
        raise ValueError(f"Incident {investigation.incident_id} not found")

    investigation.status = InvestigationStatus.running
    investigation.started_at = datetime.now(UTC)
    investigation.provider = settings.llm_provider
    investigation.model = settings.llm_model
    await session.commit()

    incident.status = IncidentStatus.investigating
    await session.commit()

    provider = build_provider()
    if provider is None:
        raise RuntimeError(
            "No LLM provider configured. Set LLM_PROVIDER/LLM_BASE_URL/LLM_MODEL."
        )

    engine = InvestigationEngine(
        provider=provider,
        store=SqlAlchemyInvestigationStore(session),
        limits=EngineLimits(
            max_iterations=settings.investigation_max_iterations,
            max_tool_calls=settings.investigation_max_tool_calls,
            max_wall_time_seconds=settings.investigation_max_wall_time_seconds,
            max_context_bytes=settings.investigation_max_context_bytes,
            max_tool_output_bytes=settings.investigation_max_tool_output_bytes,
            tool_timeout_seconds=settings.investigation_tool_timeout_seconds,
        ),
    )
    report = await engine.run(
        investigation_id=investigation.id,
        incident={
            "id": incident.id,
            "title": incident.title,
            "summary": incident.summary,
            "service": incident.service,
            "repository": incident.repository,
            "external_run_id": incident.external_run_id,
        },
        source=incident.source.value,
    )
    if report is None:
        investigation = await session.get(Investigation, investigation.id)
        incident = await session.get(Incident, investigation.incident_id)
        incident.status = IncidentStatus.failed
        await session.commit()
    else:
        incident = await session.get(Incident, investigation.incident_id)
        incident.status = IncidentStatus.completed
        await session.commit()


async def _run_github_webhook(session, job: Job) -> None:
    """Create an incident + investigation from a failed workflow_run event."""
    from sqlalchemy import select

    from database.models import Incident, IncidentSource, Investigation, InvestigationStatus

    payload = job.payload or {}
    run = payload.get("workflow_run", {}) or {}
    repo_full = payload.get("repository", "") or ""
    conclusion = (run.get("conclusion") or "").lower()
    action = payload.get("action", "")

    if action != "completed":
        return
    from api.config import get_settings

    settings = get_settings()
    investigate_success = conclusion == "success" and settings.github_investigate_success
    if conclusion == "success" and not investigate_success:
        return
    if conclusion not in ("failure", "cancelled", "timed_out") and not investigate_success:
        return

    # Idempotency: one incident per workflow run.
    existing = (
        await session.execute(
            select(Incident).where(Incident.external_run_id == str(run.get("id", "")))
        )
    ).scalars().first()
    if existing is not None:
        logger.info("Incident already exists for run %s", run.get("id"))
        return

    title = f"Workflow '{run.get('name', 'unknown')}' {conclusion} on {repo_full}"
    incident = Incident(
        source=IncidentSource.github_actions,
        title=title,
        summary=(
            f"GitHub Actions workflow run {run.get('id')} concluded with '{conclusion}'. "
            f"Head SHA: {run.get('head_sha', '')}."
        ),
        service=repo_full,
        repository=repo_full,
        external_run_id=str(run.get("id", "")),
        severity="high" if conclusion == "failure" else "medium",
        status=IncidentStatus.open,
        metadata_json={
            "head_sha": run.get("head_sha", ""),
            "head_branch": run.get("head_branch", ""),
            "event": run.get("event", ""),
            "html_url": run.get("html_url", ""),
            "run_attempt": run.get("run_attempt", 1),
        },
    )
    session.add(incident)
    await session.commit()
    await session.refresh(incident)

    investigation = Investigation(
        incident_id=incident.id,
        provider="",
        model="",
        status=InvestigationStatus.queued,
    )
    session.add(investigation)
    await session.commit()
    await session.refresh(investigation)

    incident.status = IncidentStatus.investigating
    await session.commit()

    await enqueue_job(JobKind.investigation, {"investigation_id": investigation.id})


async def _sleep_or_stop(stopping: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stopping.wait(), timeout=seconds)
    except TimeoutError:
        pass
