"""Prometheus investigation tool with predefined, parameterized queries.

The model never sends raw PromQL. It selects a query key and a time range;
the server builds the query from an allowlist, bounding lookback and step.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from tools.registry import ToolExecutionError, tool

# Predefined query allowlist. Keys are exposed to the model.
QUERY_CATALOG: dict[str, dict] = {
    "http_requests_per_second": {
        "query": "sum by (route) (rate(demo_http_requests_total[1m]))",
        "description": "HTTP request rate per route over the last minute",
    },
    "http_5xx_ratio": {
        "query": "sum(rate(demo_http_requests_total{status=~\"5..\"}[5m])) / clamp_min(sum(rate(demo_http_requests_total[5m])), 0.000001)",
        "description": "Ratio of HTTP 5xx responses over the last 5 minutes",
    },
    "http_request_duration_p95": {
        "query": "histogram_quantile(0.95, sum by (le, route) (rate(demo_http_request_duration_seconds_bucket[5m])))",
        "description": "P95 HTTP request duration in seconds per route",
    },
    "http_request_duration_avg": {
        "query": "sum by (route) (rate(demo_http_request_duration_seconds_sum[5m])) / clamp_min(sum by (route) (rate(demo_http_request_duration_seconds_count[5m])), 0.000001)",
        "description": "Average HTTP request duration in seconds per route",
    },
    "db_operation_duration_avg": {
        "query": "sum by (operation) (rate(demo_db_operation_duration_seconds_sum[5m])) / clamp_min(sum by (operation) (rate(demo_db_operation_duration_seconds_count[5m])), 0.000001)",
        "description": "Average database operation duration in seconds",
    },
    "db_pool_checked_out": {
        "query": "demo_db_pool_checkedout",
        "description": "Current number of checked-out (in-use) database connections (real pool measurement)",
    },
    "db_pool_utilization_ratio": {
        "query": "demo_db_pool_checkedout / clamp_min(demo_db_pool_size, 1)",
        "description": "Ratio of checked-out connections to configured pool size (derived from real pool metrics)",
    },
    "error_log_rate": {
        "query": "sum(rate(demo_error_logs_total[5m]))",
        "description": "Application error log lines per second over the last 5 minutes",
    },
    "dependency_health": {
        "query": "demo_dependency_up",
        "description": "Dependency health probes (1 = up, 0 = down)",
    },
}

MAX_RANGE_MINUTES = 120


class QueryPrometheusInput(BaseModel):
    query_key: str = Field(description="One of: " + ", ".join(sorted(QUERY_CATALOG)))
    time_range_minutes: int = Field(default=30, ge=1, le=MAX_RANGE_MINUTES)
    step_seconds: int = Field(default=15, ge=1, le=300)


def set_prometheus_client(client) -> None:
    from tools import prometheus_tools

    prometheus_tools._client = client


async def _execute_query(payload: dict) -> str:
    from tools import prometheus_tools

    client = prometheus_tools._client
    if client is None:
        raise ToolExecutionError("Prometheus client is not configured")
    key = payload["query_key"]
    entry = QUERY_CATALOG.get(key)
    if entry is None:
        raise ToolExecutionError(
            f"Unknown query_key '{key}'. Allowed: {', '.join(sorted(QUERY_CATALOG))}"
        )
    end = datetime.now(UTC)
    start = end - timedelta(minutes=payload["time_range_minutes"])
    try:
        data = await client.query_range(
            entry["query"], start, end, step_seconds=payload["step_seconds"]
        )
    except Exception as exc:  # noqa: BLE001 - structured error, no fabricated data
        raise ToolExecutionError(f"Prometheus query failed: {exc}") from exc
    results = data.get("data", {}).get("result", [])
    return json.dumps(
        {
            "query_key": key,
            "description": entry["description"],
            "time_range_minutes": payload["time_range_minutes"],
            "result_count": len(results),
            "results": results[:50],  # bound result count
        },
        default=str,
    )


tool(
    name="query_prometheus",
    description=(
        "Query Prometheus metrics for the demo service. Select a query_key from the "
        "allowed catalog and a time range. Returns actual metric values."
    ),
    input_model=QueryPrometheusInput,
    timeout_seconds=20.0,
)(_execute_query)
