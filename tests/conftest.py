"""Shared test fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the repository root is importable without installation.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./var/test.db")
os.environ.setdefault("DEMO_DATABASE_URL", "sqlite+aiosqlite:///./var/test_demo.db")
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("DEMO_ADMIN_KEY", "test-admin-key")
os.environ.setdefault("DEMO_FAULT_SECRET", "test-fault-secret")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True, scope="session")
async def create_tables():
    """Create all tables in the test database once per test session."""
    from api.db import get_engine
    from database.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
