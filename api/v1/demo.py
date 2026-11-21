"""Demo lab controls and status.

All mutating endpoints require the admin API key (X-API-Key) and are audited.
Fault injection is disabled by default and only exists in the demo service.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.db import get_session
from api.rate_limit import rate_limit
from api.security import audit, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

SCENARIOS = {
    "pool-exhaustion": {
        "title": "Database connection-pool exhaustion",
        "description": "Holds all pooled database connections so new requests time out.",
    },
    "elevated-latency": {
        "title": "Artificially elevated request latency",
        "description": "Adds real processing delay to database-backed requests.",
    },
    "config-failure": {
        "title": "Configuration / dependency failure",
        "description": "Points the demo service at an unreachable dependency endpoint.",
    },
}


def _demo_url() -> str:
    from api.config import get_settings

    return get_settings().demo_api_url.rstrip("/")


def _fault_headers() -> dict:
    from api.config import get_settings

    return {"X-Fault-Secret": get_settings().demo_fault_secret}


async def _proxy_fault(path: str, json_body: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_demo_url()}/__demo__/{path}",
                json=json_body or {},
                headers=_fault_headers(),
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"Demo API timeout: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Demo API unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"Demo API fault endpoint returned HTTP {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()


@router.get("/demo/status")
async def demo_status():
    """Current fault-injection status and scenario metadata."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_demo_url()}/__demo__/status")
            demo = resp.json()
    except Exception as exc:  # noqa: BLE001
        demo = {"reachable": False, "error": str(exc)[:200], "active_faults": []}
    return {
        "reachable": demo.get("reachable", True),
        "scenarios": SCENARIOS,
        "active_faults": demo.get("active_faults", []),
        "health": demo.get("health"),
        "error": demo.get("error", ""),
    }


@router.post("/demo/scenarios/{scenario}/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scenario(
    scenario: str,
    request: Request,
    admin: str = Depends(require_admin),
):
    if scenario not in SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. Allowed: {', '.join(SCENARIOS)}",
        )
    rate_limit(request, per_minute=10.0)
    result = await _proxy_fault(f"faults/{scenario}/trigger")
    async for session in get_session():
        await audit(session, "demo.scenario.trigger", f"admin:{admin}", {"scenario": scenario})
        break
    return {"scenario": scenario, "status": "triggered", "detail": result}


@router.post("/demo/reset", status_code=status.HTTP_202_ACCEPTED)
async def reset_demo(
    request: Request,
    admin: str = Depends(require_admin),
):
    rate_limit(request, per_minute=10.0)
    result = await _proxy_fault("reset")
    async for session in get_session():
        await audit(session, "demo.reset", f"admin:{admin}", {})
        break
    return {"status": "reset", "detail": result}
