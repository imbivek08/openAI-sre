"""Prometheus metrics for the demo service.

All metrics reflect real measurements. Pool utilization is derived from the
actual SQLAlchemy pool checked-out count — no synthetic values.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "demo_http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status"],
)
http_request_duration_seconds = Histogram(
    "demo_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
db_operation_duration_seconds = Histogram(
    "demo_db_operation_duration_seconds",
    "Database operation duration in seconds",
    ["operation"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)
error_logs_total = Counter(
    "demo_error_logs_total",
    "Application error log lines",
    ["error_type"],
)
dependency_up = Gauge(
    "demo_dependency_up",
    "Dependency health (1 = up, 0 = down)",
    ["name"],
)
db_pool_checkedout = Gauge(
    "demo_db_pool_checkedout",
    "Current number of checked-out (in-use) database connections (real pool measurement)",
)
db_pool_size = Gauge(
    "demo_db_pool_size",
    "Configured database connection pool size",
)
