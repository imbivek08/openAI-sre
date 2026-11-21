"""Service health and deployment/configuration-change tools."""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, Field

from tools.registry import ToolExecutionError, tool


class GetServiceHealthInput(BaseModel):
    pass


class GetRecentDeploymentsInput(BaseModel):
    service: str = Field(default="demo-api")
    limit: int = Field(default=10, ge=1, le=50)


def set_demo_api_url(url: str) -> None:
    from tools import deployment_tools

    deployment_tools._demo_api_url = url


async def _get_service_health(payload: dict) -> str:
    from tools import deployment_tools

    url = deployment_tools._demo_api_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{url}/health/dependencies")
            deps = resp.json()
            basic = await client.get(f"{url}/health")
            basic_status = basic.json()
    except httpx.TimeoutException as exc:
        raise ToolExecutionError(f"Demo API health check timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ToolExecutionError(f"Demo API unreachable: {exc}") from exc
    return json.dumps(
        {
            "status": basic_status.get("status"),
            "dependencies": deps,
        },
        default=str,
    )


async def _get_recent_deployments(payload: dict) -> str:
    """Read deployment/config-change records from the backend database."""
    from api.db import get_session_factory
    from database.models import Deployment

    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select

        stmt = (
            select(Deployment)
            .where(Deployment.service == payload["service"])
            .order_by(Deployment.created_at.desc())
            .limit(payload["limit"])
        )
        rows = (await session.execute(stmt)).scalars().all()
        return json.dumps(
            {
                "count": len(rows),
                "deployments": [
                    {
                        "id": r.id,
                        "service": r.service,
                        "version": r.version,
                        "change_type": r.change_type,
                        "description": r.description,
                        "status": r.status,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in rows
                ],
            },
            default=str,
        )


tool(
    name="get_service_health",
    description=(
        "Get current health of the demo service and its dependencies (database, "
        "external dependency). Returns real health probe results."
    ),
    input_model=GetServiceHealthInput,
    timeout_seconds=15.0,
)(_get_service_health)

tool(
    name="get_recent_deployments",
    description=(
        "List recent deployments and configuration changes for a service, most "
        "recent first. Useful for correlating incidents with changes."
    ),
    input_model=GetRecentDeploymentsInput,
    timeout_seconds=15.0,
)(_get_recent_deployments)
