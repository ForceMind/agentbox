from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from agentbox_core.models import AuditEvent
from agentbox_core.services import ControlPlaneServices
from agentbox_runtime import RuntimeOperationError
from conftest import FakeClaudeRuntime
from sqlalchemy import select
from sqlalchemy.engine import make_url

PASSWORD = "a sufficiently long passphrase"


async def login(client: httpx.AsyncClient, origin_headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "maintainer", "password": PASSWORD},
        headers=origin_headers,
    )
    assert response.status_code == 200
    return str(response.json()["data"]["csrf_token"])


@pytest.mark.anyio
async def test_claude_status_and_sessions_require_auth_and_are_no_store(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    assert (await client.get("/api/v1/claude")).status_code == 401
    assert (await client.get("/api/v1/claude/sessions")).status_code == 401
    await login(client, origin_headers)

    status = await client.get("/api/v1/claude")
    sessions = await client.get("/api/v1/claude/sessions")
    assert status.status_code == sessions.status_code == 200
    assert status.headers["cache-control"] == sessions.headers["cache-control"] == "no-store"
    assert status.json()["data"]["authentication"] == "unknown"
    assert status.json()["data"]["capabilities"]["remote_control"] == "supported"
    listed = sessions.json()["data"]["sessions"]
    assert [session["project_id"] for session in listed] == ["project-a", "trust-project"]
    assert listed[1]["state"] == "needs_interaction"
    assert all("path" not in session for session in listed)


@pytest.mark.anyio
async def test_claude_start_stop_require_origin_and_csrf_and_audit_metadata_only(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    claude_runtime: FakeClaudeRuntime,
    initialized_services: ControlPlaneServices,
) -> None:
    assert (await client.post("/api/v1/claude/sessions/project-a/start")).status_code == 403
    csrf = await login(client, origin_headers)
    missing = await client.post("/api/v1/claude/sessions/project-a/start", headers=origin_headers)
    assert missing.status_code == 403
    assert "start:project-a" not in claude_runtime.calls

    started = await client.post(
        "/api/v1/claude/sessions/project-a/start",
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    stopped = await client.post(
        "/api/v1/claude/sessions/project-a/stop",
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert started.status_code == stopped.status_code == 200
    assert started.headers["cache-control"] == stopped.headers["cache-control"] == "no-store"
    assert started.json()["data"]["outcome"] == "started"
    assert stopped.json()["data"]["outcome"] == "stopped"

    with initialized_services.database.transaction() as session:
        events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action.like("claude_session_%")))
        )
    assert [event.action for event in events] == [
        "claude_session_start_requested",
        "claude_session_start_succeeded",
        "claude_session_stop_requested",
        "claude_session_stop_succeeded",
    ]
    assert all(event.metadata_json.get("project_id") == "project-a" for event in events)


@pytest.mark.anyio
async def test_claude_output_is_sensitive_ephemeral_no_store_and_never_audited_or_logged(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    claude_runtime: FakeClaudeRuntime,
    initialized_services: ControlPlaneServices,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await login(client, origin_headers)
    with caplog.at_level(logging.DEBUG):
        response = await client.get("/api/v1/claude/sessions/project-a/output")

    canary = claude_runtime.output_canary
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["data"]["output"] == canary
    assert response.json()["data"]["sensitive"] is True
    assert canary not in caplog.text

    with initialized_services.database.transaction() as session:
        events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "claude_output_viewed"))
        )
        serialized_audit = "\n".join(str(event.metadata_json) for event in events)
    assert len(events) == 1
    assert canary not in serialized_audit

    database = Path(make_url(initialized_services.database.engine.url).database or "")
    for candidate in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        if candidate.exists():
            assert canary.encode() not in candidate.read_bytes()


@pytest.mark.anyio
async def test_runtime_socket_failure_is_normalized_without_output_or_private_state(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    claude_runtime: FakeClaudeRuntime,
) -> None:
    async def fail(_request_id: str) -> tuple[object, ...]:
        raise RuntimeOperationError(
            "CLAUDE_RUNTIME_UNAVAILABLE",
            "Claude Runtime Executor is unavailable",
            category="unavailable",
            retryable=True,
        )

    claude_runtime.list_sessions = fail  # type: ignore[method-assign,assignment]
    await login(client, origin_headers)
    response = await client.get("/api/v1/claude/sessions")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "CLAUDE_RUNTIME_UNAVAILABLE"
    assert "CLAUDE-OUTPUT-CANARY" not in response.text


@pytest.mark.anyio
async def test_api_never_accepts_a_project_path_or_tmux_arguments(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    csrf = await login(client, origin_headers)
    response = await client.post(
        "/api/v1/claude/sessions/..%2Fetc/start",
        headers={**origin_headers, "X-CSRF-Token": csrf},
        json={"path": "/etc", "argv": ["kill-server"]},
    )
    assert response.status_code in {404, 405, 422}
