"""Health and status endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from api.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class DependencyStatus(BaseModel):
    name: str
    status: str  # up | down | unknown | not_configured
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    dependencies: list[DependencyStatus]
    llm: dict


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()
    deps: list[DependencyStatus] = []

    # PostgreSQL — lightweight check via the API's own DB engine
    db_status = "unknown"
    db_detail = ""
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from api.db import get_engine

        factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        db_status = "up"
    except Exception as exc:  # noqa: BLE001
        db_status = "down"
        db_detail = str(exc)[:200]
    deps.append(DependencyStatus(name="postgres", status=db_status, detail=db_detail))

    # Demo API
    demo_status = "unknown"
    demo_detail = ""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.demo_api_url}/health")
            demo_status = "up" if resp.status_code == 200 else "down"
            demo_detail = f"HTTP {resp.status_code}" if resp.status_code != 200 else ""
    except Exception as exc:  # noqa: BLE001
        demo_status = "down"
        demo_detail = str(exc)[:200]
    deps.append(DependencyStatus(name="demo-api", status=demo_status, detail=demo_detail))

    # LLM provider
    if settings.llm_configured:
        llm_status = "configured"
        llm_detail = f"provider={settings.llm_provider} model={settings.llm_model}"
    else:
        llm_status = "not_configured"
        llm_detail = "Set LLM_PROVIDER, LLM_BASE_URL and LLM_MODEL to enable investigations"
    deps.append(DependencyStatus(name="llm-provider", status=llm_status, detail=llm_detail))

    # GitHub integration
    if settings.github_token:
        gh_status = "configured"
        repos = settings.allowed_repos
        gh_detail = f"allowed_repos={len(repos)}" + (f" ({', '.join(sorted(repos))})" if repos else " (none)")
    else:
        gh_status = "not_configured"
        gh_detail = "Set GITHUB_TOKEN and GITHUB_ALLOWED_REPOS to enable webhook investigations"
    deps.append(DependencyStatus(name="github", status=gh_status, detail=gh_detail))

    overall = "ok" if db_status == "up" else "degraded"
    return HealthResponse(
        status=overall,
        timestamp=datetime.now(UTC).isoformat(),
        dependencies=deps,
        llm={
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "tool_calling": settings.llm_tool_calling,
            "configured": settings.llm_configured,
            "base_url": settings.llm_base_url,
        },
    )


@router.get("/health/ready")
async def ready():
    return {"ready": True}
