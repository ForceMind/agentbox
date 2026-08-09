from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from agentbox_core.models import AuditEvent
from agentbox_core.services import ControlPlaneServices
from agentbox_runtime import PairCodeResult, RuntimeOperationError
from conftest import FakeClock, FakeCodexRuntime
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
async def test_codex_status_requires_auth_and_returns_fixture_truth(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
) -> None:
    assert (await client.get("/api/v1/codex/status")).status_code == 401
    await login(client, origin_headers)
    response = await client.get("/api/v1/codex/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert data["installed"] is True
    assert data["version"] == "0.test.fixture"
    assert data["capabilities"]["status"] == "unsupported"
    assert data["remote_state"] == "stopped"


@pytest.mark.anyio
async def test_remote_mutations_require_origin_session_and_csrf(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
) -> None:
    assert (await client.post("/api/v1/codex/remote/start")).status_code == 403
    csrf = await login(client, origin_headers)
    missing = await client.post("/api/v1/codex/remote/start", headers=origin_headers)
    wrong = await client.post(
        "/api/v1/codex/remote/start",
        headers={**origin_headers, "X-CSRF-Token": "wrong-session-token"},
    )
    assert missing.status_code == wrong.status_code == 403
    assert "start" not in codex_runtime.calls

    started = await client.post(
        "/api/v1/codex/remote/start",
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    stopped = await client.post(
        "/api/v1/codex/remote/stop",
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert started.status_code == stopped.status_code == 200
    assert started.json()["data"]["outcome"] == "started"
    assert stopped.json()["data"]["outcome"] == "stopped"


@pytest.mark.anyio
async def test_pair_is_ephemeral_no_store_and_metadata_only_audit(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
    initialized_services: ControlPlaneServices,
    caplog: pytest.LogCaptureFixture,
) -> None:
    csrf = await login(client, origin_headers)
    with caplog.at_level(logging.DEBUG):
        response = await client.post(
            "/api/v1/codex/pair-codes",
            headers={**origin_headers, "X-CSRF-Token": csrf},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["data"] == {
        "pair_code": codex_runtime.pair_code,
        "expires_at": None,
        "display_once": True,
    }
    assert codex_runtime.pair_code not in caplog.text

    with initialized_services.database.transaction() as session:
        pair_events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action.like("codex_pair_%")))
        )
        serialized = "\n".join(str(event.metadata_json) for event in pair_events)
    assert [event.action for event in pair_events] == [
        "codex_pair_requested",
        "codex_pair_succeeded",
    ]
    assert codex_runtime.pair_code not in serialized

    database = Path(make_url(initialized_services.database.engine.url).database or "")
    for candidate in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        if candidate.exists():
            assert codex_runtime.pair_code.encode() not in candidate.read_bytes()


@pytest.mark.anyio
async def test_pair_requires_recent_authentication(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
    clock: FakeClock,
) -> None:
    csrf = await login(client, origin_headers)
    clock.advance(seconds=61)
    response = await client.post(
        "/api/v1/codex/pair-codes",
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_RECENT_REQUIRED"
    assert "pair" not in codex_runtime.calls


@pytest.mark.anyio
async def test_pair_missing_and_wrong_csrf_never_reaches_runtime(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
) -> None:
    await login(client, origin_headers)
    missing = await client.post("/api/v1/codex/pair-codes", headers=origin_headers)
    wrong = await client.post(
        "/api/v1/codex/pair-codes",
        headers={**origin_headers, "X-CSRF-Token": "incorrect"},
    )
    assert missing.status_code == wrong.status_code == 403
    assert "pair" not in codex_runtime.calls


@pytest.mark.anyio
async def test_pair_runtime_failure_returns_only_normalized_error(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
    initialized_services: ControlPlaneServices,
) -> None:
    raw_canary = "PAIR-SECRET-CANARY-RAW-FAILURE-8F4N"

    async def fail_pair(_request_id: str) -> PairCodeResult:
        codex_runtime.calls.append("pair")
        raise RuntimeOperationError(
            "CODEX_PAIR_OUTPUT_UNRECOGNIZED",
            "Codex did not return a recognizable pairing code",
            category="broken",
        )

    codex_runtime.generate_pair_code = fail_pair  # type: ignore[method-assign,assignment]
    csrf = await login(client, origin_headers)
    response = await client.post(
        "/api/v1/codex/pair-codes",
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    serialized_response = response.text
    assert raw_canary not in serialized_response
    assert response.json()["error"]["code"] == "CODEX_PAIR_OUTPUT_UNRECOGNIZED"
    with initialized_services.database.transaction() as session:
        events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action.like("codex_pair_%")))
        )
    serialized_audit = "\n".join(str(event.metadata_json) for event in events)
    assert raw_canary not in serialized_audit
    assert events[-1].metadata_json == {
        "runtime": "codex",
        "error_code": "CODEX_PAIR_OUTPUT_UNRECOGNIZED",
    }


@pytest.mark.anyio
async def test_pair_rate_limit_preserves_retry_after_without_secret_data(
    client: httpx.AsyncClient,
    origin_headers: dict[str, str],
    codex_runtime: FakeCodexRuntime,
) -> None:
    async def rate_limited(_request_id: str) -> PairCodeResult:
        raise RuntimeOperationError(
            "CODEX_PAIR_RATE_LIMITED",
            "A new pairing code was requested too recently",
            category="rate_limited",
            retryable=True,
            retry_after=7,
        )

    codex_runtime.generate_pair_code = rate_limited  # type: ignore[method-assign,assignment]
    csrf = await login(client, origin_headers)
    response = await client.post(
        "/api/v1/codex/pair-codes",
        headers={**origin_headers, "X-CSRF-Token": csrf},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert response.json()["error"]["retryable"] is True
