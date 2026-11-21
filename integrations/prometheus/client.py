"""Prometheus HTTP API client with bounded, validated queries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

MAX_RANGE_MINUTES = 120
DEFAULT_STEP_SECONDS = 15


class PrometheusError(Exception):
    pass


class PrometheusClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step_seconds: int = DEFAULT_STEP_SECONDS,
    ) -> dict:
        """Execute an instant/range query against the Prometheus HTTP API.

        Enforces a maximum lookback window to bound resource use.
        """
        now = datetime.now(UTC)
        start = start.astimezone(UTC) if start.tzinfo else start.replace(tzinfo=UTC)
        end = end.astimezone(UTC) if end.tzinfo else end.replace(tzinfo=UTC)
        if end > now:
            end = now
        if end <= start:
            raise PrometheusError("end must be after start")
        if (end - start) > timedelta(minutes=MAX_RANGE_MINUTES):
            raise PrometheusError(f"Time range exceeds maximum of {MAX_RANGE_MINUTES} minutes")
        if not 1 <= step_seconds <= 300:
            raise PrometheusError("step_seconds must be between 1 and 300")

        params = {"query": query, "start": start.timestamp(), "end": end.timestamp(), "step": step_seconds}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/v1/query_range", params=params)
        except httpx.TimeoutException as exc:
            raise PrometheusError(f"Prometheus timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise PrometheusError(f"Prometheus connection error: {exc}") from exc
        if resp.status_code >= 400:
            raise PrometheusError(f"Prometheus HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if data.get("status") != "success":
            raise PrometheusError(f"Prometheus query failed: {data.get('error', 'unknown error')}")
        return data

    async def query_instant(self, query: str, time: datetime | None = None) -> dict:
        params: dict = {"query": query}
        if time is not None:
            params["time"] = time.timestamp()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/v1/query", params=params)
        except httpx.TimeoutException as exc:
            raise PrometheusError(f"Prometheus timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise PrometheusError(f"Prometheus connection error: {exc}") from exc
        if resp.status_code >= 400:
            raise PrometheusError(f"Prometheus HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if data.get("status") != "success":
            raise PrometheusError(f"Prometheus query failed: {data.get('error', 'unknown error')}")
        return data
