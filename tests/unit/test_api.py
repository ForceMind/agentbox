from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import agentbox_api.main as api_main
import httpx
import pytest
import uvicorn
from agentbox_api.main import create_app
from agentbox_api.waw_application import WAWAPIApplication, WAWMode
from agentbox_api.waw_deployment_profile import WAWDeploymentProfileObservation
from agentbox_core import __version__
from agentbox_core.configuration import Environment, Settings
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClaudeRuntime, FakeCodexRuntime, FakeProjectRuntime
from fastapi import APIRouter, FastAPI
from sqlalchemy.engine import make_url


class FakeWAWBindCoordinator:
    def __init__(self) -> None:
        self.calls = 0

    async def bind(self) -> dict[str, object]:
        self.calls += 1
        return {"status": "BOUND"}


def test_installed_module_app_and_run_settings_are_singletons() -> None:
    assert api_main.app.state.settings is api_main._installed_settings


def test_run_uses_the_installed_app_without_rebuilding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def unexpected_factory(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("run must not rebuild the API")

    def unexpected_profile() -> object:
        raise AssertionError("run must not reread the deployment profile")

    def captured_run(application: object, **kwargs: object) -> None:
        captured["application"] = application
        captured.update(kwargs)

    monkeypatch.setattr(api_main, "create_app", unexpected_factory)
    monkeypatch.setattr(api_main, "load_waw_deployment_profile", unexpected_profile)
    monkeypatch.setattr(uvicorn, "run", captured_run)
    api_main.run()

    assert captured["application"] is api_main.app
    assert captured["host"] == api_main._installed_settings.bind_host
    assert captured["port"] == api_main._installed_settings.bind_port


def _profile(mode: WAWMode) -> WAWDeploymentProfileObservation:
    return WAWDeploymentProfileObservation(
        mode=mode,
        source="missing_default" if mode is WAWMode.DISABLED else "installed_profile",
        raw_sha256=None if mode is WAWMode.DISABLED else "a" * 64,
        parent_identity=(1,),
        file_identity=None if mode is WAWMode.DISABLED else (2,),
    )


def test_factory_failure_closes_only_services_created_by_this_factory(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = 0

    def close() -> None:
        nonlocal closed
        closed += 1

    static_root = tmp_path / "static"
    static_root.mkdir()
    broken = settings.model_copy(update={"static_dir": static_root})
    monkeypatch.setattr(services.database, "close", close)
    monkeypatch.setattr(api_main, "build_services", lambda _settings: services)

    with pytest.raises(RuntimeError, match="frontend artifact"):
        create_app(broken)
    assert closed == 1


def test_factory_failure_preserves_caller_owned_services(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = 0

    def close() -> None:
        nonlocal closed
        closed += 1

    static_root = tmp_path / "static"
    static_root.mkdir()
    broken = settings.model_copy(update={"static_dir": static_root})
    monkeypatch.setattr(services.database, "close", close)

    with pytest.raises(RuntimeError, match="frontend artifact"):
        create_app(broken, services)
    assert closed == 0


def test_middleware_registration_failure_uses_the_owned_services_cleanup_boundary(
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = 0

    def close() -> None:
        nonlocal closed
        closed += 1

    def failed_middleware(self: FastAPI, *_args: object, **_kwargs: object) -> None:
        del self
        raise RuntimeError("synthetic middleware registration failure")

    monkeypatch.setattr(services.database, "close", close)
    monkeypatch.setattr(api_main, "build_services", lambda _settings: services)
    monkeypatch.setattr(FastAPI, "add_middleware", failed_middleware)

    with pytest.raises(RuntimeError, match="synthetic middleware registration failure"):
        create_app(settings)
    assert closed == 1


@pytest.mark.parametrize("caller_owns_services", [False, True])
@pytest.mark.parametrize(
    ("registration_method", "failed_path"),
    [
        ("add_api_route", "/healthz"),
        ("add_api_websocket_route", "/api/v1/workspaces/{workspace_id}/stream"),
    ],
)
def test_decorated_route_registration_failure_respects_service_ownership(
    caller_owns_services: bool,
    registration_method: str,
    failed_path: str,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = 0
    original_registration = getattr(APIRouter, registration_method)

    def close() -> None:
        nonlocal closed
        closed += 1

    def register(router: APIRouter, path: str, *args: object, **kwargs: object) -> None:
        if path == failed_path:
            raise RuntimeError("synthetic decorated route registration failure")
        original_registration(router, path, *args, **kwargs)

    monkeypatch.setattr(services.database, "close", close)
    monkeypatch.setattr(api_main, "build_services", lambda _settings: services)
    monkeypatch.setattr(APIRouter, registration_method, register)

    with pytest.raises(RuntimeError, match="synthetic decorated route registration failure"):
        create_app(settings, services if caller_owns_services else None)
    assert closed == (0 if caller_owns_services else 1)


@pytest.mark.parametrize("caller_owns_services", [False, True])
def test_production_waw_factory_failure_respects_service_ownership(
    caller_owns_services: bool,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = 0

    def close() -> None:
        nonlocal closed
        closed += 1

    production = settings.model_copy(update={"env": Environment.PRODUCTION})
    monkeypatch.setattr(services.database, "close", close)
    monkeypatch.setattr(
        api_main, "load_waw_deployment_profile", lambda: _profile(WAWMode.FILESYSTEM_V2)
    )
    monkeypatch.setattr(
        WAWAPIApplication,
        "production",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("synthetic WAW factory failure")),
    )
    if not caller_owns_services:
        monkeypatch.setattr(api_main, "build_services", lambda _settings: services)

    with pytest.raises(RuntimeError, match="synthetic WAW factory failure"):
        create_app(production, services if caller_owns_services else None)
    assert closed == (0 if caller_owns_services else 1)


@pytest.mark.parametrize("caller_owns_services", [False, True])
def test_factory_and_owned_database_cleanup_failure_preserve_both_failures(
    caller_owns_services: bool,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = settings.model_copy(update={"env": Environment.PRODUCTION})
    close_calls = 0

    def failing_close() -> None:
        nonlocal close_calls
        close_calls += 1
        raise RuntimeError("synthetic database cleanup failure")

    monkeypatch.setattr(services.database, "close", failing_close)
    monkeypatch.setattr(
        api_main, "load_waw_deployment_profile", lambda: _profile(WAWMode.FILESYSTEM_V2)
    )
    monkeypatch.setattr(
        WAWAPIApplication,
        "production",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("synthetic WAW factory failure")),
    )
    if not caller_owns_services:
        monkeypatch.setattr(api_main, "build_services", lambda _settings: services)

    if caller_owns_services:
        with pytest.raises(RuntimeError, match="synthetic WAW factory failure"):
            create_app(production, services)
        assert close_calls == 0
    else:
        with pytest.raises(BaseExceptionGroup) as raised:
            create_app(production)
        assert (
            str(raised.value)
            == "API factory failed and owned database cleanup failed (2 sub-exceptions)"
        )
        assert [str(error) for error in raised.value.exceptions] == [
            "synthetic WAW factory failure",
            "synthetic database cleanup failure",
        ]
        assert close_calls == 1


@pytest.mark.anyio
async def test_optional_waw_bind_runs_before_api_serving(settings: Settings) -> None:
    coordinator = FakeWAWBindCoordinator()
    application = create_app(settings, waw_bind_coordinator=coordinator)  # type: ignore[arg-type]
    async with application.router.lifespan_context(application):
        assert coordinator.calls == 1
    application.state.services.database.close()


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
