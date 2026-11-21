"""Tests for the JSONL log store."""

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from integrations.logs.base import LogQuery
from integrations.logs.json_logs import JsonLogStore


def _write_log(path: str, entries: list[dict]):
    with open(path, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


@pytest.fixture
def log_file():
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    yield path
    os.unlink(path)


async def test_search_by_level(log_file):
    _write_log(
        log_file,
        [
            {"timestamp": datetime.now(UTC).isoformat(), "level": "INFO", "service": "demo-api", "message": "ok"},
            {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR", "service": "demo-api", "message": "boom"},
        ],
    )
    store = JsonLogStore(log_file)
    entries = await store.search(LogQuery(level="ERROR"))
    assert len(entries) == 1
    assert entries[0].message == "boom"


async def test_search_by_term(log_file):
    _write_log(
        log_file,
        [
            {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR", "service": "demo-api", "message": "PoolTimeoutError: connection timed out"},
            {"timestamp": datetime.now(UTC).isoformat(), "level": "ERROR", "service": "demo-api", "message": "ValueError: bad input"},
        ],
    )
    store = JsonLogStore(log_file)
    entries = await store.search(LogQuery(search="pool"))
    assert len(entries) == 1
    assert "PoolTimeoutError" in entries[0].message


async def test_limit_bounds_results(log_file):
    _write_log(
        log_file,
        [
            {"timestamp": datetime.now(UTC).isoformat(), "level": "INFO", "service": "demo-api", "message": f"line {i}"}
            for i in range(50)
        ],
    )
    store = JsonLogStore(log_file)
    entries = await store.search(LogQuery(limit=10))
    assert len(entries) == 10


async def test_missing_file_returns_empty():
    store = JsonLogStore("/nonexistent/path/app.log")
    assert await store.search(LogQuery()) == []


async def test_time_range_filter(log_file):
    now = datetime.now(UTC)
    _write_log(
        log_file,
        [
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "level": "ERROR", "service": "demo-api", "message": "old error"},
            {"timestamp": now.isoformat(), "level": "ERROR", "service": "demo-api", "message": "new error"},
        ],
    )
    store = JsonLogStore(log_file)
    entries = await store.search(LogQuery(level="ERROR", start=now - timedelta(minutes=30)))
    assert len(entries) == 1
    assert entries[0].message == "new error"
