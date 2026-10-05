"""Actual selector route + native Git/admission/opaque bridge regression evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from a3_changes_fixture import KEY, PROJECT_ID, A3ChangesFixture
from agentbox_api.main import create_app
from agentbox_core.configuration import Environment
from agentbox_core.models import Project
from agentbox_protocol.a3_content import (
    context_digest,
    encode_message,
    selector_commitment,
    validate_context,
)
from agentbox_protocol.a3_crypto import A3Browser
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


@pytest.fixture
async def fixture(tmp_path: Path) -> AsyncIterator[A3ChangesFixture]:
    value = await A3ChangesFixture.create(tmp_path)
    try:
        yield value
    finally:
        await value.close()


def client(fixture: A3ChangesFixture, **kwargs: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fixture.app),
        base_url="http://testserver",
        cookies={"agentbox_session": fixture.issued.token},
        headers={"Origin": "http://testserver", "X-CSRF-Token": fixture.issued.csrf_token},
        **kwargs,
    )


@pytest.mark.anyio
async def test_route_projects_only_bounded_noncredential_metadata(
    fixture: A3ChangesFixture,
) -> None:
    result = await fixture.bootstrap()
    assert result["schema_version"] == "a3-staged-observation/v1"
    assert set(result) == {"schema_version", "binding", "entries", "snapshot_sha256"}
    assert set(result["binding"]) == {
        "project_id",
        "project_revision",
        "binding_revision",
        "binding_digest",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_epoch",
        "session_scope",
        "auth_epoch",
    }
    assert result["binding"]["project_id"] == PROJECT_ID
    assert result["binding"]["auth_epoch"] == "1"
    assert all(type(value) is str for value in result["binding"].values())
    denied = next(e for e in result["entries"] if e["path"] == ".env")
    assert denied["selection_id"] is None
    assert denied["unavailable_code"] == "PATCH_UNAVAILABLE_SENSITIVE_PATH"
    serialized = json.dumps(result)
    for secret in (
        fixture.issued.token,
        fixture.issued.csrf_token,
        fixture.authenticated.session_id,
        str(fixture.project),
        KEY.hex(),
        "onerror",
        "unstaged-exclusion-canary",
    ):
        assert secret not in serialized
    assert fixture.runner.diff_count == 0
    assert fixture.owner.selectors._active == 0


@pytest.mark.anyio
@pytest.mark.parametrize("variation", ["origin", "csrf", "cookie", "body", "query", "project"])
async def test_boundary_rejects_before_observation(
    fixture: A3ChangesFixture, variation: str
) -> None:
    path = f"/api/v1/projects/{PROJECT_ID}/git/staged-observation"
    kwargs: dict[str, Any] = {}
    async with client(fixture) as api:
        if variation == "origin":
            kwargs["headers"] = {"Origin": "http://other.invalid"}
        elif variation == "csrf":
            kwargs["headers"] = {"X-CSRF-Token": "invalid"}
        elif variation == "cookie":
            api.cookies.clear()
        elif variation == "body":
            kwargs["content"] = b"{}"
        elif variation == "query":
            path += "?path=success.txt"
        else:
            path = "/api/v1/projects/not-formal/git/staged-observation"
        response = await api.post(path, **kwargs)
    assert response.status_code >= 400
    assert response.headers["cache-control"] == "no-store"
    assert fixture.observations == fixture.runner.diff_count == 0


@pytest.mark.anyio
async def test_default_source_off_and_non_test_injection_refused(fixture: A3ChangesFixture) -> None:
    fixture.app = create_app(fixture.settings, fixture.services)
    async with client(fixture) as api:
        response = await api.post(f"/api/v1/projects/{PROJECT_ID}/git/staged-observation")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PATCH_UNAVAILABLE_CONFIG"
    for env in (Environment.PRODUCTION, Environment.DEVELOPMENT):
        with pytest.raises(ValueError, match="TEST-only"):
            create_app(
                fixture.settings.model_copy(update={"env": env}),
                fixture.services,
                a3_observation_source=fixture,
            )
    assert fixture.observations == 0


@pytest.mark.anyio
async def test_post_await_currentness_is_not_bootstrap_authority(fixture: A3ChangesFixture) -> None:
    original = fixture.observe

    async def drifting(facts: Any) -> Any:
        value = await original(facts)
        with fixture.services.database.transaction() as session:
            row = session.get(Project, PROJECT_ID)
            assert row is not None
            row.revision += 1
        return value

    fixture.observe = drifting  # type: ignore[method-assign]
    async with client(fixture) as api:
        response = await api.post(f"/api/v1/projects/{PROJECT_ID}/git/staged-observation")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PATCH_REVOKED"
    assert "selection_id" not in response.text


async def prepare(fixture: A3ChangesFixture, path: str = "success.txt") -> tuple[A3Browser, str]:
    observation = await fixture.bootstrap()
    selection = next(e["selection_id"] for e in observation["entries"] if e["path"] == path)
    binding = dict(observation["binding"])
    binding.pop("auth_epoch")
    context = validate_context(
        {
            "protocol_id": "agentbox-a3-content/v1",
            "protocol_version": 1,
            **binding,
            "selector_commitment": selector_commitment(selection),
            "side": "staged",
            "request_nonce": (b"n" * 32).hex(),
        }
    )

    def now() -> int:
        return time.monotonic_ns() // 1_000_000 + 100000

    pin = hashlib.sha256(
        X25519PrivateKey.from_private_bytes(KEY).public_key().public_bytes_raw()
    ).hexdigest()
    browser = A3Browser(
        context,
        expected_pin=lambda: pin,
        clock_ms=now,
        current=lambda: context,
        deadline_ms=now() + 30000,
    )
    await fixture.command(
        "open",
        {
            "projectId": PROJECT_ID,
            "selectionId": selection,
            "requestNonce": context["request_nonce"],
        },
    )
    await fixture.command("send", {"wire": browser.start().hex(), "handle": fixture.handle})
    raw = await fixture.command("receive", {"handle": fixture.handle})
    await fixture.command(
        "send",
        {
            "wire": browser.receive_attest(bytes.fromhex(raw["wire"])).hex(),
            "handle": fixture.handle,
        },
    )
    browser.receive_ack(
        bytes.fromhex((await fixture.command("receive", {"handle": fixture.handle}))["wire"])
    )
    read = encode_message(
        {
            "protocol_id": "agentbox-a3-content/v1",
            "protocol_version": 1,
            "context_digest": context_digest(context),
            "request_nonce": context["request_nonce"],
            "kind": "PATCH_READ",
            "selection_id": selection,
        }
    )
    await fixture.command(
        "send", {"wire": browser.encrypt_read(read).hex(), "handle": fixture.handle}
    )
    return browser, selection


@pytest.mark.anyio
async def test_native_git_route_admission_opaque_full_end(fixture: A3ChangesFixture) -> None:
    browser, _ = await prepare(fixture)
    completed = None
    while completed is None:
        raw = bytes.fromhex((await fixture.command("receive", {"handle": fixture.handle}))["wire"])
        assert len(raw) <= 24576
        assert b"onerror" not in raw and b"A3 synthetic complete diff" not in raw
        completed = browser.receive_record(raw)
    assert b"A3 synthetic complete diff" in completed
    assert b"onerror" in completed
    assert b"unstaged-exclusion-canary" not in completed
    assert fixture.task is not None
    await fixture.task
    assert fixture.runner.diff_count == 2
    assert fixture.owner.selectors._active == 0
    assert len(fixture.owner.selectors._burned_nonces) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path,code", [("binary.bin", "PATCH_UNAVAILABLE_BINARY"), ("large.txt", "PATCH_TOO_LARGE")]
)
async def test_preflight_failure_never_sends_prefix(
    fixture: A3ChangesFixture, path: str, code: str
) -> None:
    with pytest.raises(ValueError):
        await prepare(fixture, path)
    assert fixture.task is not None
    await fixture.task
    assert fixture.failure == code
    assert fixture.owner.selectors._active == 0


@pytest.mark.anyio
async def test_cancel_held_end_has_no_resource_or_nonce_reset(fixture: A3ChangesFixture) -> None:
    fixture.mode = "hold-end"
    browser, _ = await prepare(fixture)
    while True:
        pending = asyncio.create_task(fixture.command("receive", {"handle": fixture.handle}))
        async with asyncio.timeout(5):
            while not fixture.held and not pending.done():
                await asyncio.sleep(0.001)
        if fixture.held:
            break
        browser.receive_record(bytes.fromhex((await pending)["wire"]))
    browser.close()
    await fixture.command("close", {})
    await fixture.command("release", {})
    late = bytes.fromhex((await pending)["wire"])
    with pytest.raises(ValueError):
        browser.receive_record(late)
    assert fixture.owner.selectors._active == 0
    assert len(fixture.owner.selectors._burned_nonces) == 1


@pytest.mark.anyio
async def test_late_old_adapter_close_cannot_clear_new_slot(fixture: A3ChangesFixture) -> None:
    observation = await fixture.bootstrap()
    selection = next(
        e["selection_id"] for e in observation["entries"] if e["path"] == "success.txt"
    )
    first = await fixture.command(
        "open",
        {"projectId": PROJECT_ID, "selectionId": selection, "requestNonce": (b"1" * 32).hex()},
    )
    await fixture.command("close", first)
    second = await fixture.command(
        "open",
        {"projectId": PROJECT_ID, "selectionId": selection, "requestNonce": (b"2" * 32).hex()},
    )
    relay = fixture.relay
    await fixture.command("close", first)
    assert fixture.relay is relay and first != second
    with pytest.raises(ValueError, match="PATCH_REVOKED"):
        await fixture.command("send", {**first, "wire": "00"})
    await fixture.command("close", second)


@pytest.mark.anyio
async def test_real_session_revocation_is_permission_failure(fixture: A3ChangesFixture) -> None:
    await fixture.command("mode", {"value": "permission"})
    with pytest.raises(ValueError, match="AUTH_SESSION_INVALID"):
        await fixture.bootstrap()
    assert fixture.observations == fixture.runner.diff_count == 0
