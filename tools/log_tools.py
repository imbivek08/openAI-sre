"""Application log search tool over the structured JSON log store."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from integrations.logs.base import LogQuery
from tools.registry import ToolExecutionError, tool

MAX_LIMIT = 200


class SearchLogsInput(BaseModel):
    level: str | None = Field(default=None, description="Log level, e.g. ERROR")
    request_id: str | None = Field(default=None, description="Exact request ID")
    search: str | None = Field(default=None, description="Case-insensitive term in message")
    time_range_minutes: int = Field(default=30, ge=1, le=120)
    limit: int = Field(default=50, ge=1, le=MAX_LIMIT)


def set_log_store(store) -> None:
    from tools import log_tools

    log_tools._store = store


async def _search_logs(payload: dict) -> str:
    from tools import log_tools

    store = log_tools._store
    if store is None:
        raise ToolExecutionError("Log store is not configured")
    end = datetime.now(UTC)
    start = end - timedelta(minutes=payload["time_range_minutes"])
    log_query = LogQuery(
        service="demo-api",
        level=payload.get("level"),
        request_id=payload.get("request_id"),
        search=payload.get("search"),
        start=start,
        end=end,
        limit=payload["limit"],
    )
    try:
        entries = await store.search(log_query)
    except Exception as exc:  # noqa: BLE001
        raise ToolExecutionError(f"Log search failed: {exc}") from exc
    return json.dumps(
        {
            "count": len(entries),
            "time_range_minutes": payload["time_range_minutes"],
            "entries": [
                {
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "level": e.level,
                    "service": e.service,
                    "request_id": e.request_id,
                    "status": e.status,
                    "error_type": e.error_type,
                    "message": e.message[:2000],
                }
                for e in entries
            ],
        },
        default=str,
    )


tool(
    name="search_application_logs",
    description=(
        "Search structured application logs from the demo service. Filter by level, "
        "request ID, search term, and time range. Returns real log entries."
    ),
    input_model=SearchLogsInput,
    timeout_seconds=15.0,
)(_search_logs)
