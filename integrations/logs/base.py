"""Log retrieval interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LogQuery:
    service: str | None = None
    level: str | None = None
    request_id: str | None = None
    search: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    limit: int = 100


@dataclass
class LogEntry:
    timestamp: datetime | None
    level: str
    service: str
    message: str
    request_id: str = ""
    status: int | None = None
    error_type: str = ""
    extra: dict = field(default_factory=dict)


class LogStore(ABC):
    @abstractmethod
    async def search(self, query: LogQuery) -> list[LogEntry]:
        """Return matching log entries, newest first, bounded by query.limit."""
