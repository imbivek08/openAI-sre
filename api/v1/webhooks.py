"""GitHub webhook receiver.

Verifies HMAC-SHA256 signatures, deduplicates by GitHub delivery ID, validates
repository allowlists, and enqueues investigation jobs. Returns promptly —
no LLM work happens in the request path.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from api.db import get_session
from api.rate_limit import rate_limit
from database.models import JobKind, WebhookDelivery
from integrations.github.webhooks import summarize_delivery, verify_signature

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(request: Request):
    rate_limit(request, per_minute=60.0)
    settings = _settings()
    event_type = request.headers.get("x-github-event", "")
    delivery_id = request.headers.get("x-github-delivery", "")
    signature = request.headers.get("x-hub-signature-256")

    body = await request.body()

    # 1. Signature verification (constant-time). Reject early on failure.
    signature_valid = verify_signature(body, signature, settings.github_webhook_secret)
    if not signature_valid:
        logger.warning(
            "Rejected webhook with invalid signature (event=%s delivery=%s)",
            event_type,
            delivery_id or "?",
        )
        raise HTTPException(status_code=401, detail="Invalid signature")

    if not delivery_id:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Delivery header")

    # 2. Parse payload.
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = payload.get("action", "")
    meta = summarize_delivery(event_type, action, payload)

    # 3. Persist delivery metadata (never the body) + deduplicate.
    delivery: WebhookDelivery | None = None
    async for session in _session_iter():
        existing = (
            await session.execute(
                select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
            )
        ).scalars().first()
        if existing is not None:
            # Duplicate delivery: acknowledge but do not reprocess.
            return {"status": "duplicate", "delivery_id": delivery_id}

        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            repository=meta["repository"],
            run_id=meta["run_id"],
            signature_valid=True,
        )
        session.add(delivery)
        await session.commit()
        break

    # 4. Event filtering.
    if event_type != "workflow_run":
        _mark_processed(delivery)
        return {"status": "ignored", "reason": f"unsupported event {event_type}"}

    repo_full = meta["repository"]
    if not repo_full:
        raise HTTPException(status_code=400, detail="Payload missing repository.full_name")

    if not settings.github_repo_allowed(repo_full):
        _mark_processed(delivery)
        logger.info("Ignoring webhook for non-allowlisted repository %s", repo_full)
        return {"status": "ignored", "reason": "repository not in allowlist"}

    run = payload.get("workflow_run", {}) or {}
    conclusion = (run.get("conclusion") or "").lower()
    investigate_success = conclusion == "success" and settings.github_investigate_success
    if conclusion == "success" and not investigate_success:
        _mark_processed(delivery)
        return {"status": "ignored", "reason": "successful run (default policy)"}
    if conclusion not in ("failure", "cancelled", "timed_out") and not investigate_success:
        _mark_processed(delivery)
        return {"status": "ignored", "reason": f"conclusion '{conclusion or 'none'}' not actionable"}

    # 5. Enqueue the investigation job (async, outside the request path).
    from api.queue import enqueue_job

    await enqueue_job(
        JobKind.github_webhook,
        {
            "workflow_run": run,
            "repository": repo_full,
            "head_sha": run.get("head_sha", ""),
            "action": action,
            "delivery_id": delivery_id,
        },
    )
    _mark_processed(delivery)
    logger.info(
        "Accepted %s workflow_run delivery=%s run=%s repo=%s",
        action,
        delivery_id,
        meta["run_id"],
        repo_full,
    )
    return {"status": "accepted", "delivery_id": delivery_id, "run_id": meta["run_id"]}


def _settings():
    from api.config import get_settings

    return get_settings()


def _session_iter():
    # get_session is an async generator; routers can't use it directly because
    # it yields a session per request. For the webhook we iterate manually.
    from api.db import get_session as _gs

    return _gs()


def _mark_processed(delivery: WebhookDelivery | None) -> None:
    """Best-effort marking of the delivery as processed (fire-and-forget)."""
    if delivery is None:
        return
    delivery.processed = True
    # The owning session may be closed by now; enqueue a tiny follow-up task.
    import asyncio

    async def _commit() -> None:

        async for session in get_session():
            fresh = await session.get(WebhookDelivery, delivery.id)
            if fresh is not None:
                fresh.processed = True
                await session.commit()
            break

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_commit())
    except RuntimeError:
        pass
