from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_core import __version__
from agentbox_core.configuration import Environment, Settings
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClaudeRuntime, FakeCodexRuntime, FakeProjectRuntime
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
async def test_doctor_requires_authentication(
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    application = create_app(settings, services)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/doctor")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_SESSION_INVALID"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_doctor_returns_only_safe_control_plane_data(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "maintainer",
            "password": "a sufficiently long passphrase",
        },
        headers=origin_headers,
    )
    assert login.status_code == 200

    response = await client.get("/api/v1/doctor")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["data"]["status"] == "ready"
    assert body["data"]["checks"] == {
        "configuration_valid": True,
        "database_reachable": True,
        "migrations_current": True,
        "admin_initialized": True,
        "control_plane_ready": True,
    }
    assert body["data"]["policy"] == {
        "environment": "test",
        "bind_host": "127.0.0.1",
        "bind_port": 8787,
        "session_ttl_seconds": 3600,
        "session_idle_ttl_seconds": 600,
        "login_rate_limit": 5,
        "login_rate_window_seconds": 300,
        "login_lock_duration_seconds": 300,
    }
    assert body["data"]["codex"] == {
        "installed": True,
        "version": "0.test.fixture",
        "installation_type": "standalone",
        "remote_control": "supported",
        "remote_state": "stopped",
        "findings": [],
    }
    serialized = response.text.lower()
    assert "secret" not in serialized
    assert "database_url" not in serialized
    assert "data_dir" not in serialized
    assert "sqlite+pysqlite" not in serialized


@pytest.mark.anyio
async def test_doctor_runs_independent_runtime_probes_concurrently(
    settings: Settings,
    initialized_services: ControlPlaneServices,
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
    origin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: set[str] = set()
    all_started = asyncio.Event()

    def concurrent_probe(
        name: str, original: Callable[[str], Awaitable[Any]]
    ) -> Callable[[str], Awaitable[Any]]:
        async def wrapped(request_id: str) -> Any:
            started.add(name)
            if len(started) == 5:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=1)
            return await original(request_id)

        return wrapped

    monkeypatch.setattr(codex_runtime, "status", concurrent_probe("codex", codex_runtime.status))
    monkeypatch.setattr(claude_runtime, "status", concurrent_probe("claude", claude_runtime.status))
    monkeypatch.setattr(
        project_runtime,
        "git_global_status",
        concurrent_probe("git", project_runtime.git_global_status),
    )
    monkeypatch.setattr(
        project_runtime,
        "github_status",
        concurrent_probe("github", project_runtime.github_status),
    )
    monkeypatch.setattr(
        project_runtime,
        "list_workspaces",
        concurrent_probe("workspaces", project_runtime.list_workspaces),
    )
    application = create_app(
        settings,
        initialized_services,
        codex_runtime,
        claude_runtime,
        project_runtime,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as test_client:
        login = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "maintainer", "password": "a sufficiently long passphrase"},
            headers=origin_headers,
        )
        assert login.status_code == 200
        response = await test_client.get("/api/v1/doctor")

    assert response.status_code == 200
    assert started == {"codex", "claude", "git", "github", "workspaces"}


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
