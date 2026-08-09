import httpx
import pytest
from agentbox_api.main import app
from agentbox_core import __version__


@pytest.mark.anyio
async def test_health_endpoint() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_meta_endpoint() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/meta")

    assert response.status_code == 200
    assert response.json() == {
        "name": "AgentBox",
        "version": __version__,
        "api_version": "v1",
    }
