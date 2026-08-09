from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_core import __version__
from agentbox_core.configuration import Environment, Settings
from agentbox_core.services import ControlPlaneServices
from sqlalchemy.engine import make_url


@pytest.mark.anyio
async def test_health_endpoint_without_database_readiness(settings: Settings) -> None:
    application = create_app(settings)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/healthz")
            readiness = await client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert readiness.status_code == 503
        assert readiness.json() == {
            "status": "not_ready",
            "checks": {"database": False, "migrations": False},
        }
        assert not Path(make_url(settings.database_url).database or "").exists()
    finally:
        application.state.services.database.close()


@pytest.mark.anyio
async def test_readiness_reports_database_and_migrations(
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    application = create_app(settings, services)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": True, "migrations": True},
    }


@pytest.mark.anyio
async def test_meta_endpoint(settings: Settings, services: ControlPlaneServices) -> None:
    application = create_app(settings, services)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/meta")

    assert response.status_code == 200
    assert response.json() == {
        "name": "AgentBox",
        "version": __version__,
        "api_version": "v1",
        "environment": Environment.TEST.value,
    }


@pytest.mark.anyio
async def test_security_and_request_id_headers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "req_client-123"})

    assert response.headers["x-request-id"] == "req_client-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.anyio
async def test_malformed_request_id_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "bad request id\t"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REQUEST_ID_INVALID"
