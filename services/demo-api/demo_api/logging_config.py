"""Structured JSON logging for the demo service.

Logs are written as JSON lines to stdout AND to a shared log file so the
backend's log-search tool can retrieve them. No credentials, tokens, or
connection strings are ever logged.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.environ.get("DEMO_LOG_PATH", "./var/log/demo-api/app.log")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "demo-api",
            "message": record.getMessage(),
        }
        for key in ("request_id", "route", "status", "error_type", "operation", "duration_ms", "fault"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("demo_api")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(JsonFormatter())
    logger.addHandler(stdout)

    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        file_handler = logging.FileHandler(LOG_PATH)
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    except OSError:
        pass  # stdout logging still works

    return logger
