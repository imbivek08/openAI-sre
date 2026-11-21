"""Fault-injection state for the demo lab.

All faults are DISABLED by default. They can only be enabled through the
protected /__demo__ endpoints (shared secret required) and are automatically
cleared by reset. Faults change real application behavior — no synthetic
metrics are reported.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger("demo_api.faults")

# Active fault names, e.g. {"pool-exhaustion"}
active_faults: set[str] = set()

# Held database connections for the pool-exhaustion scenario (real connections).
_held_connections: list = []

# Artificial latency in seconds for the elevated-latency scenario.
_latency_seconds: float = 0.0

# Unreachable dependency URL for the config-failure scenario.
_dependency_url: str = "http://dependency.internal:9090/health"


def status() -> dict:
    return {
        "active_faults": sorted(active_faults),
        "latency_seconds": _latency_seconds,
        "dependency_url": _dependency_url,
        "held_connections": len(_held_connections),
    }


def reset() -> dict:
    global _latency_seconds, _dependency_url
    active_faults.clear()
    _held_connections.clear()
    _latency_seconds = 0.0
    _dependency_url = "http://dependency.internal:9090/health"
    logger.info("All demo faults reset")
    return status()


async def trigger_pool_exhaustion(session_factory) -> dict:
    """Hold every pooled connection so new requests time out.

    This is a REAL exhaustion: connections are checked out of the pool and not
    released, so subsequent pool acquisitions block until pool timeout.
    """
    from sqlalchemy import text

    from demo_api.metrics import db_pool_checkedout, db_pool_size

    engine = session_factory.kw["bind"]
    db_pool_size.set(engine.pool.size())
    held = []
    # Acquire exactly pool.size() connections and hold them.
    for _ in range(engine.pool.size()):
        conn = await engine.raw_connection()
        held.append(conn)
    _held_connections.extend(held)
    active_faults.add("pool-exhaustion")
    db_pool_checkedout.set(len(held))
    logger.error(
        "FAULT TRIGGERED: database connection-pool exhaustion — holding %d connections",
        len(held),
        extra={"fault": "pool-exhaustion"},
    )
    return status()


async def trigger_elevated_latency(seconds: float = 2.5) -> dict:
    global _latency_seconds
    _latency_seconds = seconds
    active_faults.add("elevated-latency")
    logger.error(
        "FAULT TRIGGERED: elevated request latency — adding %.1fs to DB-backed requests",
        seconds,
        extra={"fault": "elevated-latency"},
    )
    return status()


async def trigger_config_failure() -> dict:
    """Point the demo service at an unreachable dependency endpoint.

    The application will fail health checks and dependency-backed requests
    with real connection errors.
    """
    global _dependency_url
    _dependency_url = "http://127.0.0.1:9/dead-dependency"  # port 9 = discard, unreachable
    active_faults.add("config-failure")
    logger.error(
        "FAULT TRIGGERED: configuration failure — dependency URL set to unreachable %s",
        _dependency_url,
        extra={"fault": "config-failure"},
    )
    return status()


def release_pool_connections() -> None:
    """Release held connections (used by reset)."""
    for conn in list(_held_connections):
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    _held_connections.clear()
