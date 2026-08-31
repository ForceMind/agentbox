"""Fake Runtime/API composition tests for metadata-only WAW behavior."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_api.waw_control_client import WAWControlClientError
from agentbox_core.models import Project
from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw import AgentType, workspace_id
from agentbox_core.waw_models import RuntimeHostInstallation
from conftest import FakeClaudeRuntime, FakeCodexRuntime, FakeProjectRuntime

PASSWORD = "a sufficiently long passphrase"
HOST_ID = "wri_" + "a" * 32
PROJECT_ID = "prj_" + "b" * 32
WORKSPACE_ID = workspace_id(PROJECT_ID, AgentType.CLAUDE)
DIGEST = "d" * 64
FINGERPRINT = "e" * 64


class FakeMetadataCoordinator:
    def __init__(self, *, epoch: str = "7", error: Exception | None = None) -> None:
        self.attestation = {"runtime_epoch": epoch}
        self.epoch = epoch
        self.error = error
        self.actions: list[str] = []

    async def request_lifecycle(self, action: str, request: dict[str, object]) -> dict[str, object]:
        self.actions.append(action)
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
            "runtime_epoch": self.epoch,
            "process_state": "RUNNING",
            "exit_code": None,
            "attachment_capacity": {"admitted": "0", "pending": "0", "limit": "32"},
        }


def _project() -> Project:
    now = datetime(2026, 8, 30)
    return Project(
        id=PROJECT_ID,
        slug="fake-runtime-project",
        display_name="Fake Runtime Project",
        relative_path="fake-runtime-project",
        source_type="local",
        repository_url=None,
        default_branch="main",
        state="ready",
        archived_at=None,
        created_at=now,
        updated_at=now,
    )


def _seed(services: ControlPlaneServices) -> None:
    now = datetime(2026, 8, 30)
    with services.database.transaction() as session:
        session.add(
            RuntimeHostInstallation(
                id=HOST_ID,
                revision=1,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(_project())
    services.workspaces.create(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest=DIGEST,
        executable_fingerprint=FINGERPRINT,
    )


async def _login(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD},
        headers=headers,
    )
    assert response.status_code == 200


def _app(
    settings: Any,
    services: ControlPlaneServices,
    coordinator: FakeMetadataCoordinator | None = None,
    *,
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
) -> Any:
    return create_app(
        settings,
        services,
        codex_runtime,
        claude_runtime,
        project_runtime,
        waw_bind_coordinator=coordinator,
    )


@pytest.mark.anyio
async def test_fake_runtime_metadata_flow_is_authenticated_and_no_store(
    settings: Any,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
) -> None:
    _seed(initialized_services)
    coordinator = FakeMetadataCoordinator()
    app = _app(
        settings,
        initialized_services,
        coordinator,
        codex_runtime=codex_runtime,
        claude_runtime=claude_runtime,
        project_runtime=project_runtime,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/api/v1/workspaces")).status_code == 401
        await _login(client, origin_headers)
        listing = await client.get("/api/v1/workspaces")
        status = await client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/status")
    assert listing.status_code == status.status_code == 200
    assert listing.headers["cache-control"] == status.headers["cache-control"] == "no-store"
    assert status.json()["data"]["runtime_epoch"] == "7"
    assert coordinator.actions == ["workspace.workspace.status"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("coordinator", "expected_status"),
    [
        (
            FakeMetadataCoordinator(
                error=WAWControlClientError(
                    "RUNTIME_UNAVAILABLE", "synthetic unavailable", retryable=True
                )
            ),
            503,
        ),
        (
            FakeMetadataCoordinator(
                error=WAWControlClientError("PROJECT_IDENTITY_CHANGED", "synthetic mismatch")
            ),
            502,
        ),
    ],
)
async def test_fake_runtime_errors_are_normalized_without_payload(
    settings: Any,
    initialized_services: ControlPlaneServices,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
    project_runtime: FakeProjectRuntime,
    coordinator: FakeMetadataCoordinator,
    expected_status: int,
) -> None:
    _seed(initialized_services)
    app = _app(
        settings,
        initialized_services,
        coordinator,
        codex_runtime=codex_runtime,
        claude_runtime=claude_runtime,
        project_runtime=project_runtime,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await _login(client, origin_headers)
        response = await client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/status")
    assert response.status_code == expected_status
    assert response.headers["cache-control"] == "no-store"
    assert "terminal" not in response.text
    assert "ticket" not in response.text
