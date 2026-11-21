"""OpenSRE AI FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.v1 import demo, health, incidents, investigations, webhooks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("opensre.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Create schema if missing (Alembic migrations are the source of truth for
    # evolving schemas; this bootstrap keeps first-run friction low).

    from sqlalchemy import text

    from api.db import get_engine, get_session_factory

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: None)
    # Ensure demo database exists (separate DB on the same server).
    await _ensure_demo_database(settings)

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text("SELECT 1"))

    # Wire integrations into tool modules.
    from integrations.logs.json_logs import JsonLogStore
    from integrations.prometheus.client import PrometheusClient
    from tools import deployment_tools, github_tools, log_tools, prometheus_tools

    prometheus_tools.set_prometheus_client(
        PrometheusClient(settings.prometheus_url, timeout=15.0)
    )
    log_tools.set_log_store(JsonLogStore(settings.demo_log_path))
    deployment_tools.set_demo_api_url(settings.demo_api_url)

    if settings.github_token:
        from integrations.github.client import GitHubClient

        github_tools.set_github_client(
            GitHubClient(settings.github_token), settings.allowed_repos
        )

    # Seed deployment records so get_recent_deployments has real data.
    from sqlalchemy import func, select

    from database.models import Deployment

    async with factory() as session:
        count = await session.scalar(select(func.count(Deployment.id)))
        if not count:
            from datetime import datetime, timedelta

            now = datetime.now(UTC)
            session.add_all(
                [
                    Deployment(
                        service="demo-api",
                        version="1.4.2",
                        change_type="deploy",
                        description="Routine deployment: order endpoints refactor",
                        created_at=now - timedelta(hours=30),
                    ),
                    Deployment(
                        service="demo-api",
                        version="1.4.3",
                        change_type="config",
                        description="Config change: increased connection pool size",
                        created_at=now - timedelta(hours=5),
                    ),
                ]
            )
            await session.commit()

    # Start the background job worker.
    from api.queue import JobWorker

    worker = JobWorker()
    worker.start()
    app.state.worker = worker

    logger.info("OpenSRE AI API ready (provider=%s model=%s)", settings.llm_provider, settings.llm_model)
    yield
    await worker.stop()
    await engine.dispose()


async def _ensure_demo_database(settings) -> None:
    """Create the demo database if it does not exist yet."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    demo_url = settings.demo_database_url
    if "postgresql+asyncpg" not in demo_url:
        return
    base_url = demo_url.rsplit("/", 1)[0] + "/postgres"
    db_name = demo_url.rsplit("/", 1)[-1]
    engine = create_async_engine(base_url)
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :db"), {"db": db_name}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except Exception as exc:  # noqa: BLE001 - non-fatal at startup
        logger.warning("Could not ensure demo database: %s", exc)
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="OpenSRE AI",
        description="Open-source AI Site Reliability Engineering agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(incidents.router, prefix="/api/v1", tags=["incidents"])
    app.include_router(investigations.router, prefix="/api/v1", tags=["investigations"])
    app.include_router(demo.router, prefix="/api/v1", tags=["demo"])
    app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
    return app


app = create_app()
