"""Integration tests for the HTTP API using an in-memory SQLite database."""


import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from database.models import Investigation


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_endpoint(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "dependencies" in data
    assert "llm" in data


async def test_create_and_get_incident(client):
    created = await client.post(
        "/api/v1/incidents",
        json={"source": "runtime", "title": "API 5xx errors", "summary": "elevated error rate"},
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    fetched = await client.get(f"/api/v1/incidents/{incident_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "API 5xx errors"


async def test_list_incidents_pagination(client):
    for i in range(5):
        await client.post("/api/v1/incidents", json={"source": "runtime", "title": f"inc {i}"})
    resp = await client.get("/api/v1/incidents?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 5


async def test_list_incidents_filter_by_status(client):
    created = await client.post("/api/v1/incidents", json={"source": "runtime", "title": "x"})
    incident_id = created.json()["id"]
    resp = await client.get("/api/v1/incidents?status=open")
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["items"]]
    assert incident_id in ids


async def test_get_nonexistent_incident_returns_404(client):
    resp = await client.get("/api/v1/incidents/nonexistent-id")
    assert resp.status_code == 404


async def test_get_nonexistent_investigation_returns_404(client):
    resp = await client.get("/api/v1/investigations/nonexistent-id")
    assert resp.status_code == 404


async def test_investigation_events_empty(client):
    created = await client.post("/api/v1/incidents", json={"source": "runtime", "title": "x"})
    incident_id = created.json()["id"]
    # Create an investigation directly in the DB
    from api.db import get_session_factory
    from database.models import InvestigationStatus

    factory = get_session_factory()
    async with factory() as session:
        inv = Investigation(
            incident_id=incident_id,
            status=InvestigationStatus.queued,
        )
        session.add(inv)
        await session.commit()
        inv_id = inv.id

    resp = await client.get(f"/api/v1/investigations/{inv_id}/events")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_demo_status_endpoint(client):
    resp = await client.get("/api/v1/demo/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "scenarios" in data
    assert "pool-exhaustion" in data["scenarios"]
