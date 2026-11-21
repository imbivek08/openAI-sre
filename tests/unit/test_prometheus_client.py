"""Tests for Prometheus client query validation."""

from datetime import UTC, datetime, timedelta

import pytest

from integrations.prometheus.client import PrometheusClient


def test_range_limit_enforced():
    client = PrometheusClient("http://localhost:9090")
    start = datetime.now(UTC) - timedelta(minutes=180)
    end = datetime.now(UTC)
    with pytest.raises(Exception, match="exceeds maximum"):
        # query_range is async; call the validation path directly
        import asyncio

        asyncio.run(client.query_range("up", start, end))


def test_end_before_start_rejected():
    client = PrometheusClient("http://localhost:9090")
    now = datetime.now(UTC)
    import asyncio

    with pytest.raises(Exception, match="after start"):
        asyncio.run(client.query_range("up", now, now - timedelta(minutes=5)))


def test_step_bounds():
    client = PrometheusClient("http://localhost:9090")
    now = datetime.now(UTC)
    import asyncio

    with pytest.raises(Exception, match="step_seconds"):
        asyncio.run(client.query_range("up", now - timedelta(minutes=5), now, step_seconds=0))
