"""JSONL file-backed log store for the demo environment.

The demo API writes structured JSON lines to a shared volume. This store reads
that file with bounded result counts and simple filtering. It is intentionally
small; a Loki implementation can be added behind the same interface later.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

from integrations.logs.base import LogEntry, LogQuery, LogStore

logger = logging.getLogger(__name__)

MAX_LIMIT = 500


class JsonLogStore(LogStore):
    def __init__(self, path: str) -> None:
        self.path = path

    async def search(self, query: LogQuery) -> list[LogEntry]:
        limit = min(max(query.limit, 1), MAX_LIMIT)
        if not os.path.exists(self.path):
            return []
        entries: list[LogEntry] = []
        # Read the tail of the file only, to stay bounded on large logs.
        lines = _tail_lines(self.path, n=20_000)
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry = _to_entry(record)
            if _matches(entry, query):
                entries.append(entry)
                if len(entries) >= limit:
                    break
        return entries


def _tail_lines(path: str, n: int) -> list[str]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = 64 * 1024
            data = b""
            pos = size
            while pos > 0 and data.count(b"\n") <= n:
                read = min(block, pos)
                pos -= read
                fh.seek(pos)
                data = fh.read(read) + data
            return data.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _to_entry(record: dict) -> LogEntry:
    ts_raw = record.get("timestamp") or record.get("time") or record.get("ts")
    ts = _parse_ts(ts_raw)
    return LogEntry(
        timestamp=ts,
        level=str(record.get("level", "INFO")).upper(),
        service=str(record.get("service", "")),
        message=str(record.get("message", "")),
        request_id=str(record.get("request_id", "")),
        status=_maybe_int(record.get("status")),
        error_type=str(record.get("error_type", "")),
        extra={k: v for k, v in record.items() if k not in _KNOWN_KEYS},
    )


_KNOWN_KEYS = {
    "timestamp",
    "time",
    "ts",
    "level",
    "service",
    "message",
    "request_id",
    "status",
    "error_type",
}


def _parse_ts(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=UTC)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _maybe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _matches(entry: LogEntry, query: LogQuery) -> bool:
    if query.service and entry.service != query.service:
        return False
    if query.level and entry.level.upper() != query.level.upper():
        return False
    if query.request_id and entry.request_id != query.request_id:
        return False
    if query.search and query.search.lower() not in entry.message.lower():
        return False
    if query.start and entry.timestamp and entry.timestamp < query.start:
        return False
    if query.end and entry.timestamp and entry.timestamp > query.end:
        return False
    return True
