"""Instrumented demo API service with real fault injection.

This service simulates a small orders API backed by PostgreSQL. It emits
structured JSON logs and real Prometheus metrics, and supports three isolated,
reproducible fault-injection scenarios for runtime incident investigations:

1. pool-exhaustion  — holds all pooled DB connections (real pool exhaustion)
2. elevated-latency — adds real processing delay to DB-backed requests
3. config-failure  — points the service at an unreachable dependency

Faults are disabled by default and protected by a shared secret.
"""

from __future__ import annotations

import logging
import os
import random
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from demo_api import faults
from demo_api.logging_config import LOG_PATH, configure_logging
from demo_api.metrics import (
    db_operation_duration_seconds,
    db_pool_checkedout,
    db_pool_size,
    dependency_up,
    error_logs_total,
    http_request_duration_seconds,
    http_requests_total,
)

logger = configure_logging()

DEMO_DATABASE_URL = os.environ.get(
    "DEMO_DATABASE_URL", "postgresql+asyncpg://opensre:opensre@localhost:5432/opensre_demo"
)
DEMO_API_PORT = int(os.environ.get("DEMO_API_PORT", "8001"))
FAULT_SECRET = os.environ.get("DEMO_FAULT_SECRET", "change-me-fault-secret")

# Small pool so exhaustion is observable quickly: 2 connections, no overflow.
engine = create_async_engine(
    DEMO_DATABASE_URL,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=2,
    max_overflow=0,
    pool_timeout=3.0,
    pool_pre_ping=False,
    echo=False,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure schema exists for the demo (kept minimal; the backend owns its own DB).
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS orders ("
                "id SERIAL PRIMARY KEY, item TEXT NOT NULL, quantity INTEGER NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'created')"
            )
        )
        # Seed a few rows when empty.
        count = await conn.scalar(text("SELECT count(*) FROM orders"))
        if count == 0:
            await conn.execute(
                text(
                    "INSERT INTO orders (item, quantity, status) VALUES "
                    "('widget', 3, 'created'), ('gadget', 1, 'shipped'), ('gizmo', 7, 'created')"
                )
            )
    db_pool_size.set(engine.pool.size())
    dependency_up.labels(name="postgresql").set(1)
    logger.info("demo-api starting", extra={"fault": "none"})
    yield
    await engine.dispose()


app = FastAPI(title="OpenSRE Demo API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:12])
    start = time.monotonic()
    status_code = 500
    error_type = ""
    response = None
    skip_logging = request.url.path.startswith("/metrics") or request.url.path.startswith("/__demo__")
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:  # noqa: BLE001
        error_type = type(exc).__name__
        raise
    finally:
        if not skip_logging and response is not None:
            duration = time.monotonic() - start
            route = request.url.path
            log_extra = {
                "request_id": request_id,
                "route": route,
                "status": status_code,
                "duration_ms": round(duration * 1000, 1),
            }
            if status_code >= 500:
                error_type = error_type or "InternalServerError"
                log_extra["error_type"] = error_type
                error_logs_total.labels(error_type=error_type).inc()
                logger.error("Request failed: %s %s -> %d", request.method, route, status_code, extra=log_extra)
            elif status_code >= 400:
                logger.warning("Client error: %s %s -> %d", request.method, route, status_code, extra=log_extra)
            else:
                logger.info(
                    "Request: %s %s -> %d (%.1fms)",
                    request.method,
                    route,
                    status_code,
                    duration * 1000,
                    extra=log_extra,
                )
            http_requests_total.labels(
                method=request.method, route=route, status=str(status_code)
            ).inc()
            http_request_duration_seconds.labels(method=request.method, route=route).observe(duration)


def _fault_secret_valid(request: Request) -> bool:
    import hmac

    provided = request.headers.get("x-fault-secret", "")
    return hmac.compare_digest(provided, FAULT_SECRET)


# --- Application routes ------------------------------------------------------


@app.get("/api/orders")
async def list_orders(request: Request):
    _apply_latency_fault()
    with db_operation_duration_seconds.labels(operation="select").time():
        _update_pool_gauge()
        async with SessionFactory() as session:
            result = await session.execute(text("SELECT id, item, quantity, status FROM orders ORDER BY id"))
            rows = [dict(r._mapping) for r in result]
    _update_pool_gauge()
    return {"orders": rows}


@app.get("/api/orders/{order_id}")
async def get_order(order_id: int):
    _apply_latency_fault()
    with db_operation_duration_seconds.labels(operation="select").time():
        _update_pool_gauge()
        async with SessionFactory() as session:
            result = await session.execute(
                text("SELECT id, item, quantity, status FROM orders WHERE id = :id"),
                {"id": order_id},
            )
            row = result.mappings().first()
    _update_pool_gauge()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return dict(row)


@app.post("/api/orders", status_code=201)
async def create_order(request: Request):
    body = await request.json()
    item = str(body.get("item", "unknown"))
    quantity = int(body.get("quantity", 1))
    _apply_latency_fault()
    with db_operation_duration_seconds.labels(operation="insert").time():
        _update_pool_gauge()
        async with SessionFactory() as session:
            result = await session.execute(
                text(
                    "INSERT INTO orders (item, quantity, status) VALUES (:item, :qty, 'created') "
                    "RETURNING id"
                ),
                {"item": item, "qty": quantity},
            )
            order_id = result.scalar()
            await session.commit()
    _update_pool_gauge()
    logger.info("Created order %s", order_id, extra={"operation": "insert", "order_id": order_id})
    return {"id": order_id, "item": item, "quantity": quantity, "status": "created"}


def _apply_latency_fault() -> None:
    """Elevated-latency fault: real processing delay on DB-backed requests."""
    if "elevated-latency" in faults.active_faults:
        time.sleep(faults._latency_seconds)


def _update_pool_gauge() -> None:
    """Reflect the real pool checked-out count in the gauge."""
    db_pool_checkedout.set(engine.pool.checkedout())


# --- Health endpoints ---------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "service": "demo-api"}


@app.get("/health/dependencies")
async def dependency_health():
    result = {}

    # Real database check
    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        result["postgresql"] = {"status": "up"}
        dependency_up.labels(name="postgresql").set(1)
    except Exception as exc:  # noqa: BLE001
        result["postgresql"] = {"status": "down", "error": type(exc).__name__}
        dependency_up.labels(name="postgresql").set(0)
        error_logs_total.labels(error_type="DatabaseConnectionError").inc()
        logger.error("Dependency check failed: postgresql down", extra={"error_type": "DatabaseConnectionError"})

    # External dependency check (affected by config-failure fault)
    url = faults._dependency_url
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
        result["external-dependency"] = {"status": "up" if resp.status_code < 500 else "down"}
        dependency_up.labels(name="external-dependency").set(1 if resp.status_code < 500 else 0)
    except Exception as exc:  # noqa: BLE001
        result["external-dependency"] = {"status": "down", "error": type(exc).__name__, "url": url}
        dependency_up.labels(name="external-dependency").set(0)
        error_logs_total.labels(error_type="DependencyConnectionError").inc()
        logger.error(
            "Dependency check failed: external-dependency down (%s)",
            type(exc).__name__,
            extra={"error_type": "DependencyConnectionError", "url": url},
        )

    return result


@app.get("/metrics")
async def metrics():
    _update_pool_gauge()
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")


# --- Protected fault-injection endpoints ---------------------------------------


@app.post("/__demo__/faults/pool-exhaustion/trigger")
async def trigger_pool_exhaustion(request: Request):
    if not _fault_secret_valid(request):
        raise HTTPException(status_code=401, detail="Invalid fault secret")
    return await faults.trigger_pool_exhaustion(SessionFactory)


@app.post("/__demo__/faults/elevated-latency/trigger")
async def trigger_elevated_latency(request: Request):
    if not _fault_secret_valid(request):
        raise HTTPException(status_code=401, detail="Invalid fault secret")
    seconds = 2.5
    return await faults.trigger_elevated_latency(seconds)


@app.post("/__demo__/faults/config-failure/trigger")
async def trigger_config_failure(request: Request):
    if not _fault_secret_valid(request):
        raise HTTPException(status_code=401, detail="Invalid fault secret")
    return await faults.trigger_config_failure()


@app.post("/__demo__/reset")
async def reset_faults(request: Request):
    if not _fault_secret_valid(request):
        raise HTTPException(status_code=401, detail="Invalid fault secret")
    faults.release_pool_connections()
    return faults.reset()


@app.get("/__demo__/status")
async def demo_status():
    return {
        "reachable": True,
        **faults.status(),
        "health": {"status": "ok"},
        "log_path": LOG_PATH,
    }
