"""Authorization helpers (API-key based admin access for demo/eval endpoints)."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from api.config import get_settings
from database.models import AuditEvent


async def require_admin(x_api_key: str | None = Header(default=None)) -> str:
    settings = get_settings()
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.demo_admin_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid X-API-Key header required",
        )
    return x_api_key


async def audit(session, action: str, actor: str, detail: dict) -> None:
    session.add(AuditEvent(action=action, actor=actor, detail=detail))
    await session.commit()
