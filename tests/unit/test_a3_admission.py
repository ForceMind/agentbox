"""Real existing API DB/session and Runtime inventory adapters; synthetic keys only."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from agentbox_api.a3_admission import A3SessionCurrentness
from agentbox_api.a3_relay import A3OpaqueTestRelay
from agentbox_core.models import AdminUser, ControlPlaneSession, Project
from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw_models import ProjectBindingRecord, RuntimeHostInstallation
from agentbox_protocol.a3_content import context_digest, encode_message
from agentbox_protocol.a3_crypto import A3Browser
from agentbox_runtime.a3_admission import A3SyntheticTestKey, A3TestReadOwner
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_encrypted_stream import RuntimePeer
from agentbox_runtime.waw_lifecycle import WAWLifecycleRegistry, WAWProjectBinding
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from test_git_staged_reader import LocalGitRunner
from test_git_staged_selectors import setup
from test_waw_api_application import HOST_ID, PROJECT_ID, _seed_current_binding

KEY = bytes(range(32))
PIN = hashlib.sha256(
    X25519PrivateKey.from_private_bytes(KEY).public_key().public_bytes_raw()
).hexdigest()


def api(services: ControlPlaneServices) -> tuple[A3SessionCurrentness, Any, list[str]]:
    issued = services.auth.login(
        username="maintainer",
        password="a sufficiently long passphrase",
        source_identifier="a3-test",
        request_id=None,
    )
    authenticated = services.sessions.authenticate(issued.token)
    _seed_current_binding(services)
    with services.database.transaction() as session:
        host = session.get(RuntimeHostInstallation, HOST_ID)
        assert host is not None
        host.last_runtime_epoch = "9"
    epoch = ["9"]
    adapter = A3SessionCurrentness(services, authenticated, runtime_epoch=lambda: epoch[0])
    assert not any(value is authenticated for value in vars(adapter).values())
    assert issued.csrf_token not in repr(vars(adapter)) and issued.token not in repr(vars(adapter))
    return adapter, authenticated, epoch


@pytest.mark.parametrize(
    "change",
    [
        "revoke",
        "auth_epoch",
        "inactive",
        "idle",
        "absolute",
        "user",
        "project",
        "archive",
        "binding",
        "host",
        "epoch",
        "clock",
    ],
)
def test_current_db_adapters_fail_closed_without_refresh(
    initialized_services: ControlPlaneServices, clock: Any, change: str
) -> None:
    services = initialized_services
    adapter, authenticated, epoch = api(services)
    before = adapter.current(PROJECT_ID, adapter.session_scope)
    assert before is not None
    assert set(dataclasses.asdict(before)) == {
        "project_id",
        "relative_key",
        "project_revision",
        "binding_revision",
        "binding_digest",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_epoch",
        "session_scope",
        "auth_epoch",
    }
    with services.database.transaction() as session:
        row = session.get(ControlPlaneSession, authenticated.session_id)
        user = session.get(AdminUser, authenticated.user_id)
        project = session.get(Project, PROJECT_ID)
        binding = session.get(ProjectBindingRecord, (PROJECT_ID, 1))
        host = session.get(RuntimeHostInstallation, HOST_ID)
        assert row and user and project and binding and host
        seen = row.last_seen_at
        if change == "revoke":
            row.revoked_at = seen
        elif change == "auth_epoch":
            row.auth_epoch += 1
        elif change == "inactive":
            user.is_active = False
        elif change == "idle":
            row.idle_expires_at = seen
        elif change == "absolute":
            row.expires_at = seen
        elif change == "user":
            adapter._user_id = "missing"
        elif change == "project":
            project.revision += 1
        elif change == "archive":
            project.archived_at = seen
        elif change == "binding":
            binding.status = "RECONCILIATION_REQUIRED"
        elif change == "host":
            host.last_runtime_epoch = "10"
        elif change == "epoch":
            epoch[0] = "10"
        elif change == "clock":
            adapter._last = seen + timedelta(seconds=1)
    assert adapter.current(PROJECT_ID, adapter.session_scope) is None
    with services.database.transaction() as session:
        row = session.get(ControlPlaneSession, authenticated.session_id)
        assert row is not None and row.last_seen_at == seen


async def runtime(tmp_path: Path, services: ControlPlaneServices) -> tuple[Any, ...]:
    adapter, authenticated, epoch = api(services)
    _, project, runner, _, reader = setup(tmp_path, LocalGitRunner(native=True))
    destination = project.with_name("replay-project")
    project.rename(destination)
    project = destination
    facts = adapter.current(PROJECT_ID, adapter.session_scope)
    assert facts is not None
    binding = WAWProjectBinding(
        facts.project_id,
        facts.relative_key,
        facts.project_revision,
        facts.binding_revision,
        facts.binding_digest,
        facts.runtime_host_installation_id,
        facts.runtime_host_installation_revision,
    )
    executor = WAWSupervisorExecutor(
        runtime_epoch="9",
        project_registry=ProjectRegistry(project.parent),
        command_factory=lambda *_: (_ for _ in ()).throw(AssertionError("no host start")),
        transport_factory=lambda *_: (_ for _ in ()).throw(AssertionError("no host transport")),
        geometry=PtyGeometry(80, 24),
        clock=time.monotonic,
        attachment_validator=lambda _: False,
    )
    await executor.register_project_binding(binding)
    lifecycle = WAWLifecycleRegistry(
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="3",
        host_manifest_digest="a" * 64,
        project_root_manifest_digest="b" * 64,
        runtime_epoch="9",
        executor=executor,
    )
    lifecycle.configure_application_gate()
    lifecycle.open_application_gate()
    # Synthetic process authority fixture, never a production pidfd proof.
    identity = object()
    live = [True]
    peer = RuntimePeer(identity, "1", lambda: live[0])
    lifecycle._authority = ("1", "test")
    lifecycle._peer_authority_identity = identity
    lifecycle._bindings[PROJECT_ID] = binding
    owner = A3TestReadOwner(
        reader,
        lifecycle,
        executor,
        peer,
        adapter.current,
        A3SyntheticTestKey(KEY),
        enabled_for_tests=True,
    )
    return owner, adapter, authenticated, lifecycle, executor, peer, live, runner, reader


@pytest.mark.anyio
async def test_actual_api_to_existing_owner_to_opaque_native_git_pipeline(
    tmp_path: Path, initialized_services: ControlPlaneServices
) -> None:
    owner, adapter, _, _, _, _, _, runner, _ = await runtime(tmp_path, initialized_services)
    scope = adapter.session_scope
    result = await owner.selectors.observe(PROJECT_ID, scope)
    selection = next(entry.selection_id for entry in result.entries if entry.path == "modified.txt")
    assert selection
    relay = A3OpaqueTestRelay(enabled_for_tests=True)
    async with owner.selectors.admit(PROJECT_ID, scope, selection, b"n" * 32) as admitted:
        context = admitted.context

        # Independent browser origin, never copy Runtime expires_ns into browser.
        def browser_now() -> int:
            return time.monotonic_ns() // 1_000_000 + 987654321

        browser = A3Browser(
            context,
            expected_pin=lambda: PIN,
            clock_ms=browser_now,
            current=lambda: context,
            deadline_ms=browser_now() + 30000,
        )
        from agentbox_runtime.a3_content_session import serve_admitted_staged_read

        task = asyncio.create_task(serve_admitted_staged_read(admitted, KEY, relay))
        await relay.browser_send(browser.start(), browser.check)
        await relay.browser_send(
            browser.receive_attest(await relay.browser_receive()), browser.check
        )
        browser.receive_ack(await relay.browser_receive())
        request = encode_message(
            {
                "protocol_id": "agentbox-a3-content/v1",
                "protocol_version": 1,
                "context_digest": context_digest(context),
                "request_nonce": context["request_nonce"],
                "kind": "PATCH_READ",
                "selection_id": selection,
            }
        )
        await relay.browser_send(browser.encrypt_read(request), browser.check)
        complete = None
        while complete is None:
            complete = browser.receive_record(await relay.browser_receive())
        await task
        assert b"staged secret-canary content" in complete and runner.diff_count == 2
    assert owner.selectors._active == 0 and len(owner.selectors._burned_nonces) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    ["reserved", "inflight", "duplicate", "gate", "quarantine", "epoch", "peer", "replace"],
)
async def test_real_inventory_and_owner_replacement_fence_handles(
    tmp_path: Path, initialized_services: ControlPlaneServices, change: str
) -> None:
    owner, adapter, _, lifecycle, executor, peer, live, _, reader = await runtime(
        tmp_path, initialized_services
    )
    scope = adapter.session_scope
    observation = await owner.selectors.observe(PROJECT_ID, scope)
    selection = next(
        entry.selection_id for entry in observation.entries if entry.path == "modified.txt"
    )
    assert selection
    async with owner.selectors.admit(PROJECT_ID, scope, selection, b"n" * 32) as admitted:
        if change == "reserved":
            executor._binding_reserved.add(PROJECT_ID)
        elif change == "inflight":
            executor._inflight_project_ids["fixture"] = PROJECT_ID
        elif change == "duplicate":
            executor._bindings["prj_" + "d" * 32] = executor._bindings[PROJECT_ID]
        elif change == "gate":
            lifecycle.close_application_gate()
        elif change == "quarantine":
            lifecycle._authority_quarantined = True
        elif change == "epoch":
            lifecycle._runtime_epoch = "10"
        elif change == "peer":
            live[0] = False
        elif change == "replace":
            replacement = A3TestReadOwner(
                reader,
                lifecycle,
                executor,
                peer,
                adapter.current,
                A3SyntheticTestKey(KEY),
                enabled_for_tests=True,
            )
            with pytest.raises(RuntimeOperationError):
                async with replacement.selectors.admit(PROJECT_ID, scope, selection, b"m" * 32):
                    pass
        with pytest.raises(RuntimeOperationError):
            admitted.check()
        with pytest.raises(RuntimeOperationError):
            await admitted.read()
    assert len(owner.selectors._burned_nonces) == 1


@pytest.mark.anyio
async def test_opaque_close_cancels_blocked_receive_and_default_off() -> None:
    with pytest.raises(ValueError):
        A3OpaqueTestRelay()
    relay = A3OpaqueTestRelay(enabled_for_tests=True)
    task = asyncio.create_task(relay.receive())
    await asyncio.sleep(0)
    relay.close()
    with pytest.raises(ValueError):
        await task
    with pytest.raises(ValueError):
        await relay.browser_send(b"x" * 24577, lambda: None)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change", ["revoke", "auth_epoch", "idle", "absolute", "binding", "peer", "replace"]
)
async def test_idle_pending_owner_closes_on_real_authority_loss(
    tmp_path: Path, initialized_services: ControlPlaneServices, change: str
) -> None:
    services = initialized_services
    owner, adapter, authenticated, lifecycle, executor, peer, live, runner, reader = await runtime(
        tmp_path, services
    )
    scope = adapter.session_scope
    observation = await owner.selectors.observe(PROJECT_ID, scope)
    selection = next(
        entry.selection_id for entry in observation.entries if entry.path == "modified.txt"
    )
    assert selection
    relay = A3OpaqueTestRelay(enabled_for_tests=True)
    task = asyncio.create_task(owner.serve(PROJECT_ID, scope, selection, b"z" * 32, relay))
    # Real native double observation completes, then Runtime waits for INIT.
    while runner.diff_count < 2 and not task.done():
        await asyncio.sleep(0.001)
    await asyncio.sleep(0)
    if change == "peer":
        live[0] = False
    elif change == "replace":
        A3TestReadOwner(
            reader,
            lifecycle,
            executor,
            peer,
            adapter.current,
            A3SyntheticTestKey(KEY),
            enabled_for_tests=True,
        )
    else:
        with services.database.transaction() as session:
            row = session.get(ControlPlaneSession, authenticated.session_id)
            binding = session.get(ProjectBindingRecord, (PROJECT_ID, 1))
            assert row and binding
            if change == "revoke":
                row.revoked_at = row.last_seen_at
            elif change == "auth_epoch":
                row.auth_epoch += 1
            elif change == "idle":
                row.idle_expires_at = row.last_seen_at
            elif change == "absolute":
                row.expires_at = row.last_seen_at
            elif change == "binding":
                binding.status = "RECONCILIATION_REQUIRED"
    with pytest.raises(RuntimeOperationError):
        await asyncio.wait_for(task, 2)
    assert relay._closed.is_set() and owner.selectors._active == 0
    assert len(owner.selectors._burned_nonces) == 1
    with pytest.raises(ValueError):
        await relay.browser_send(b"late", lambda: None)


def test_auth_epoch_changes_scope_and_adapter_contains_no_session_object(
    initialized_services: ControlPlaneServices,
) -> None:
    adapter, authenticated, _ = api(initialized_services)
    changed = dataclasses.replace(authenticated, auth_epoch=authenticated.auth_epoch + 1)
    other = A3SessionCurrentness(initialized_services, changed, runtime_epoch=lambda: "9")
    assert adapter.session_scope != other.session_scope
    assert other.current(PROJECT_ID, other.session_scope) is None


@pytest.mark.anyio
async def test_test_owner_disabled_by_default(
    tmp_path: Path, initialized_services: ControlPlaneServices
) -> None:
    from agentbox_protocol.a3_content import ContentError

    _, adapter, _, lifecycle, executor, peer, _, _, reader = await runtime(
        tmp_path, initialized_services
    )
    with pytest.raises(ContentError):
        A3TestReadOwner(reader, lifecycle, executor, peer, adapter.current, A3SyntheticTestKey(KEY))


@pytest.mark.anyio
@pytest.mark.parametrize("direction", ["runtime", "browser"])
@pytest.mark.parametrize("fault", ["cancel", "duplicate"])
async def test_opaque_receive_cancellation_and_duplicate_are_terminal(
    direction: str, fault: str
) -> None:
    relay = A3OpaqueTestRelay(enabled_for_tests=True)
    receive = relay.receive if direction == "runtime" else relay.browser_receive
    task = asyncio.create_task(receive())
    await asyncio.sleep(0)
    if fault == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(ValueError):
            await receive()
        with pytest.raises(ValueError):
            await task
    assert relay._closed.is_set() and not relay._receiving
    with pytest.raises(ValueError):
        await receive()
    with pytest.raises(ValueError):
        await relay.browser_send(b"late", lambda: None)


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["cancel", "close", "duplicate"])
async def test_opaque_receive_cleanup_await_is_fenced(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    relay = A3OpaqueTestRelay(enabled_for_tests=True)
    relay._outgoing.put_nowait(b"opaque")
    entered, release = asyncio.Event(), asyncio.Event()
    original = asyncio.gather

    async def paused(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(asyncio, "gather", paused)
    task = asyncio.create_task(relay.browser_receive())
    await entered.wait()
    assert relay._outgoing in relay._receiving
    if fault == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        if fault == "close":
            relay.close()
        else:
            with pytest.raises(ValueError):
                await relay.browser_receive()
        release.set()
        with pytest.raises(ValueError):
            await task
    assert relay._closed.is_set() and not relay._receiving
    with pytest.raises(ValueError):
        await relay.browser_receive()


def test_session_currentness_preserves_existing_configured_policy(
    initialized_services: ControlPlaneServices, clock: Any
) -> None:
    services = initialized_services
    adapter, authenticated, _ = api(services)
    # Existing session authority chooses expiry; A3 neither renews it nor invents
    # an unrelated WAW 8h/15min policy ceiling for ordinary Project content.
    with services.database.transaction() as session:
        row = session.get(ControlPlaneSession, authenticated.session_id)
        assert row
        row.expires_at = row.last_seen_at + timedelta(hours=12)
        row.idle_expires_at = row.last_seen_at + timedelta(hours=12)
    clock.advance(seconds=9 * 3600)
    assert adapter.current(PROJECT_ID, adapter.session_scope) is not None
    clock.advance(seconds=3 * 3600)
    assert adapter.current(PROJECT_ID, adapter.session_scope) is None
