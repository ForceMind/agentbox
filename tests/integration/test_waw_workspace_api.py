"""ASGI integration coverage for the read-only WAW workspace API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, cast

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_api.waw_binding import WAWRuntimeBindCoordinator
from agentbox_core.models import Project
from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw import AgentType, workspace_id
from agentbox_core.waw_models import RuntimeHostInstallation
from agentbox_core.waw_tickets import AttachmentAuthority
from conftest import FakeClaudeRuntime, FakeCodexRuntime, FakeProjectRuntime

PASSWORD = "a sufficiently long passphrase"
HOST_ID = "wri_" + "a" * 32
PROJECT_ID = "prj_" + "b" * 32
WORKSPACE_ID = workspace_id(PROJECT_ID, AgentType.CLAUDE)
DIGEST = "d" * 64
FINGERPRINT = "e" * 64


class FakeStatusCoordinator:
    def __init__(
        self, *, epoch: str = "7", observed_epoch: str | None = None, error: Exception | None = None
    ) -> None:
        self.attestation = {"runtime_epoch": epoch}
        self.observed_epoch = observed_epoch or epoch
        self.error = error
        self.calls: list[str] = []

    async def request_lifecycle(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(action)
        if self.error is not None:
            raise self.error
        return {
            "workspace_id": request["workspace_id"],
            "project_id": request["project_id"],
            "agent_type": request["agent_type"],
            "generation": request["generation"],
            "binding_revision": request["binding_revision"],
            "binding_digest": request["binding_digest"],
            "state": "RUNNING",
            "reconciliation_state": "authoritative",
            "runtime_epoch": self.observed_epoch,
            "process_state": "RUNNING",
            "exit_code": None,
            "attachment_capacity": {"admitted": "0", "pending": "0", "limit": "32"},
        }


class FakeLifecycleCoordinator:
    def __init__(self) -> None:
        self.attestation = {
            "runtime_epoch": "7",
            "runtime_host_installation_id": HOST_ID,
            "runtime_host_installation_revision": "1",
        }
        self.actions: list[str] = []

    async def request_lifecycle(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.actions.append(action)
        if action == "workspace.workspace.start":
            return {
                "status": "STARTED",
                "state": "RUNNING",
                "workspace_id": request["workspace_id"],
                "project_id": request["project_id"],
                "agent_type": "claude",
                "generation": request["generation"],
            }
        if action == "workspace.workspace.stop":
            return {
                "status": "STOPPED",
                "state": "STOPPED",
                "workspace_id": request["workspace_id"],
                "project_id": request["project_id"],
                "agent_type": "claude",
                "generation": request["generation"],
            }
        raise AssertionError(action)


def _project(project_id: str, index: int = 0) -> Project:
    now = datetime(2026, 8, 30, 0, 0, 0)
    return Project(
        id=project_id,
        slug=f"fixture-{index}",
        display_name=f"Fixture {index}",
        relative_path=f"fixture-{index}",
        source_type="local",
        repository_url=None,
        default_branch="main",
        state="ready",
        archived_at=None,
        created_at=now,
        updated_at=now,
    )


def _host() -> RuntimeHostInstallation:
    now = datetime(2026, 8, 30, 0, 0, 0)
    return RuntimeHostInstallation(
        id=HOST_ID,
        revision=1,
        runtime_type="agentbox-runtime-linux-v1",
        created_at=now,
        updated_at=now,
    )


def _seed_workspace(services: ControlPlaneServices, *, scope: str = "admin") -> None:
    with services.database.transaction() as session:
        session.add(_project(PROJECT_ID))
        session.add(_host())
    services.workspaces.create(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope=scope,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest=DIGEST,
        executable_fingerprint=FINGERPRINT,
    )


def _seed_many(services: ControlPlaneServices, count: int = 33) -> None:
    with services.database.transaction() as session:
        session.add(_host())
        for index in range(count):
            project_id = f"prj_{index + 1:032x}"
            session.add(_project(project_id, index))
    for index in range(count):
        services.workspaces.create(
            project_id=f"prj_{index + 1:032x}",
            agent_type=AgentType.CLAUDE,
            authorization_scope="other" if index < 32 else "admin",
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision=1,
            binding_revision=1,
            binding_digest=f"{index + 1:064x}",
            executable_fingerprint=FINGERPRINT,
        )


async def _login(client: httpx.AsyncClient, origin_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD},
        headers=origin_headers,
    )
    assert response.status_code == 200


@pytest.fixture
async def waw_client(
    settings: Any,
    initialized_services: ControlPlaneServices,
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        settings,
        initialized_services,
        codex_runtime,
        claude_runtime,
        project_runtime,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.mark.anyio
async def test_list_and_get_workspace_metadata_are_authenticated_and_no_store(
    waw_client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    _seed_workspace(initialized_services)
    assert (await waw_client.get("/api/v1/workspaces")).status_code == 401
    await _login(waw_client, origin_headers)

    listing = await waw_client.get("/api/v1/workspaces")
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    assert listing.json()["data"]["workspaces"][0]["id"] == WORKSPACE_ID

    detail = await waw_client.get(f"/api/v1/workspaces/{WORKSPACE_ID}")
    assert detail.status_code == 200
    assert detail.headers["cache-control"] == "no-store"
    assert set(detail.json()["data"]) == {
        "id",
        "project_id",
        "agent_type",
        "state",
        "reconciliation_state",
        "generation",
        "revision",
        "created_at",
        "updated_at",
        "last_seen_at",
        "exit_code",
        "failure_code",
    }


@pytest.mark.anyio
async def test_unknown_and_unauthorized_workspace_collapse_to_404(
    waw_client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    _seed_workspace(initialized_services, scope="other")
    await _login(waw_client, origin_headers)
    unauthorized = await waw_client.get(f"/api/v1/workspaces/{WORKSPACE_ID}")
    unknown = await waw_client.get("/api/v1/workspaces/aws_" + "f" * 32)
    malformed = await waw_client.get("/api/v1/workspaces/not-an-id")
    assert unauthorized.status_code == unknown.status_code == malformed.status_code == 404


@pytest.mark.anyio
async def test_list_authorizes_before_32_row_cap(
    waw_client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
) -> None:
    _seed_many(initialized_services)
    await _login(waw_client, origin_headers)
    response = await waw_client.get("/api/v1/workspaces")
    assert response.status_code == 200
    rows = response.json()["data"]["workspaces"]
    assert len(rows) == 1
    assert rows[0]["project_id"] == "prj_" + f"{33:032x}"


@pytest.mark.anyio
async def test_runtime_status_maps_unavailable_and_epoch_mismatch(
    waw_client: httpx.AsyncClient,
    initialized_services: ControlPlaneServices,
    settings: Any,
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
    origin_headers: dict[str, str],
) -> None:
    _seed_workspace(initialized_services)
    await _login(waw_client, origin_headers)
    unavailable = await waw_client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/status")
    assert unavailable.status_code == 503
    assert unavailable.headers["cache-control"] == "no-store"

    mismatch = FakeStatusCoordinator(epoch="7", observed_epoch="wrong")
    app = create_app(
        settings,
        initialized_services,
        codex_runtime,
        claude_runtime,
        project_runtime,
        waw_bind_coordinator=cast(WAWRuntimeBindCoordinator, mismatch),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies=waw_client.cookies,
    ) as second:
        response = await second.get(f"/api/v1/workspaces/{WORKSPACE_ID}/status")
    assert response.status_code == 502
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_waw_start_stop_routes_are_csrf_and_generation_fenced(
    settings: Any,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
) -> None:
    _seed_workspace(initialized_services)
    coordinator = FakeLifecycleCoordinator()
    app = create_app(
        settings,
        initialized_services,
        codex_runtime,
        claude_runtime,
        project_runtime,
        waw_bind_coordinator=cast(WAWRuntimeBindCoordinator, coordinator),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "maintainer", "password": PASSWORD},
            headers=origin_headers,
        )
        csrf = login.json()["data"]["csrf_token"]
        started = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/workspaces/claude/start",
            json={},
            headers={**origin_headers, "x-csrf-token": csrf},
        )
        assert started.status_code == 200
        assert started.json()["state"] == "RUNNING"
        stale = await client.post(
            f"/api/v1/workspaces/{WORKSPACE_ID}/stop",
            json={"generation": "2"},
            headers={**origin_headers, "x-csrf-token": csrf},
        )
        assert stale.status_code == 409
        stopped = await client.post(
            f"/api/v1/workspaces/{WORKSPACE_ID}/stop",
            json={"generation": "1"},
            headers={**origin_headers, "x-csrf-token": csrf},
        )
        assert stopped.status_code == 200
        assert stopped.json()["state"] == "STOPPED"
    assert coordinator.actions == ["workspace.workspace.start", "workspace.workspace.stop"]


@pytest.mark.anyio
async def test_waw_attachment_ticket_is_transient_and_no_store(
    settings: Any,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
) -> None:
    _seed_workspace(initialized_services)
    initialized_services.workspaces.transition(
        WORKSPACE_ID, expected_revision=1, state="RUNNING"
    )
    coordinator = FakeLifecycleCoordinator()
    app = create_app(
        settings,
        initialized_services,
        codex_runtime,
        claude_runtime,
        project_runtime,
        waw_bind_coordinator=cast(WAWRuntimeBindCoordinator, coordinator),
        waw_attachment_authority=AttachmentAuthority(
            clock=lambda: 100.0, authority_epoch=7, lease_seed=9
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "maintainer", "password": PASSWORD},
            headers=origin_headers,
        )
        csrf = login.json()["data"]["csrf_token"]
        ticket = await client.post(
            f"/api/v1/workspaces/{WORKSPACE_ID}/attachments",
            json={"mode": "writer"},
            headers={**origin_headers, "x-csrf-token": csrf},
        )
    assert ticket.status_code == 200
    assert ticket.headers["cache-control"] == "no-store"
    assert ticket.json()["ticket"].startswith("wat_")
    assert "terminal" not in ticket.text
