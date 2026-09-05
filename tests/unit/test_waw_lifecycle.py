from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, workspace_id
from agentbox_protocol.waw_control import decode_control_response, encode_control_response
from agentbox_runtime.waw_cgroup_attestation import (
    WAWCgroupAttachmentLeaf,
    WAWCgroupAttestation,
    WAWCgroupLimits,
)
from agentbox_runtime.waw_cgroup_attestation_store import (
    WAWCgroupAttestationStore,
)
from agentbox_runtime.waw_control_server import WAWControlDispatchError
from agentbox_runtime.waw_encrypted_stream import (
    EncryptedStreamError,
    RuntimePeer,
    WAWEncryptedAttachmentService,
    WAWEncryptedRegistry,
)
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleIdentity,
    WAWLifecycleObservation,
    WAWLifecycleRegistry,
)
from agentbox_runtime.waw_peer_authority import (
    WAWPeerAuthority,
    WAWPeerAuthorityError,
    WAWPeerBindStatus,
    WAWPeerCandidate,
    WAWPeerLease,
    WAWPeerTransferPlan,
)
from agentbox_runtime.waw_workspace_attestation import (
    WAWWorkspaceAttestationError,
    WAWWorkspaceAttestationStore,
)

HOST = "wri_" + "4" * 32
PROJECT = "prj_" + "3" * 32
WORKSPACE = "aws_" + "2" * 32
DIGEST = "a" * 64


def bind_request(request_id: str = "wreq_" + "1" * 32) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "request_id": request_id,
        "action": "workspace.api_authority.bind",
        "api_authority_epoch": "1",
        "authority_nonce": "b" * 32,
    }


def register_request(
    *, revision: str = "1", previous: str | None = None, request_id: str | None = None
) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "request_id": request_id or "wreq_" + revision.zfill(32),
        "action": "workspace.project_binding.register",
        "project_id": PROJECT,
        "relative_key": "project-a",
        "project_revision": revision,
        "binding_revision": revision,
        "previous_binding_revision": previous,
        "previous_binding_digest": None if previous is None else DIGEST,
        "schema_version": "waw-project-binding-v1",
        "runtime_host_installation_id": HOST,
        "runtime_host_installation_revision": "1",
    }


def lifecycle_request(
    action: str,
    *,
    digest: str = DIGEST,
    generation: str = "1",
    request_id: str = "wreq_" + "5" * 32,
) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "request_id": request_id,
        "action": action,
        "workspace_id": WORKSPACE,
        "project_id": PROJECT,
        "agent_type": "claude",
        "generation": generation,
        "binding_revision": "1",
        "binding_digest": digest,
        "runtime_host_installation_id": HOST,
        "runtime_host_installation_revision": "1",
    }


def attachment_request(
    action: str, *, request_id: str, attachment_id: str = "att_" + "3" * 32
) -> dict[str, Any]:
    value = {
        **lifecycle_request(action, request_id=request_id),
        "attachment_id": attachment_id,
        "mode": "writer",
        "lease_number": "1",
        "auth_epoch": "1",
        "api_authority_epoch": "1",
        "runtime_epoch": "1",
    }
    if action.endswith("prepare"):
        value.update({"resume_cursor": None, "previous_runtime_epoch": None})
    return value


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, WAWLifecycleIdentity]] = []

    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("start", identity))
        return WAWLifecycleObservation(state="RUNNING")

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("stop", identity))
        return WAWLifecycleObservation(state="STOPPED", process_state="STOPPED")

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("status", identity))
        return WAWLifecycleObservation(state="RUNNING")

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("reconcile", identity))
        return WAWLifecycleObservation(state="RUNNING")


class InvalidExecutor(FakeExecutor):
    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("start", identity))
        return WAWLifecycleObservation(state="NOT_A_STATE")


class ObservationExecutor(FakeExecutor):
    def __init__(self, observation: WAWLifecycleObservation) -> None:
        super().__init__()
        self.observation = observation

    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("start", identity))
        return self.observation


class FailingAttestationStore:
    """Reserve succeeds, but the post-start read-back fails once."""

    fail_next_read = False

    def read(self, _workspace_id: str) -> None:
        if self.fail_next_read:
            self.fail_next_read = False
            raise WAWWorkspaceAttestationError("synthetic attestation read-back failure")
        return None

    def advance(self, **_kwargs: Any) -> None:
        self.fail_next_read = True


class RunningCleanupExecutor(FakeExecutor):
    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("stop", identity))
        return WAWLifecycleObservation(state="RUNNING")


class CancellationResistantCleanupExecutor(FakeExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self.calls.append(("stop", identity))
        await self.release.wait()
        return WAWLifecycleObservation(state="STOPPED", process_state="STOPPED")


def cgroup_record() -> WAWCgroupAttestation:
    return WAWCgroupAttestation(
        workspace_id=WORKSPACE,
        project_id=PROJECT,
        agent_type="claude",
        generation=1,
        runtime_epoch="1",
        service_unit="agentbox-runtime.service",
        service_invocation_id="invocation-1",
        service_cgroup_device="0:31",
        service_cgroup_inode="10",
        service_cgroup_mount_id="11",
        delegated_subgroup="agentbox-runtime-supervisor",
        delegate_subgroup_device="0:31",
        delegate_subgroup_inode="12",
        delegate_subgroup_mount_id="11",
        cgroup_mount_id="11",
        cgroup_filesystem_id="host-cgroup2-1",
        workspace_relative_path="waw/ws-111-g1",
        workspace_device="0:31",
        workspace_inode="13",
        workload_relative_path="waw/ws-111-g1/workload",
        workload_device="0:31",
        workload_inode="14",
        attachment_leaves=(
            WAWCgroupAttachmentLeaf(
                attachment_id="att_" + "3" * 32,
                relative_path="waw/ws-111-g1/attachments/att-333",
                device="0:31",
                inode="15",
                lease_number=1,
                cleanup_state="LIVE",
            ),
        ),
        controller_configuration_digest="a" * 64,
        workspace_limits=WAWCgroupLimits(128 * 1024 * 1024, 0, 200_000, 100_000, 20),
        workload_limits=WAWCgroupLimits(120 * 1024 * 1024, 0, 190_000, 100_000, 16),
        attachment_limits=WAWCgroupLimits(8 * 1024 * 1024, 0, 10_000, 100_000, 4),
        last_frozen="0",
        last_populated="1",
        cleanup_state="LIVE",
    )


def registry(
    executor: FakeExecutor | None = None,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: Any | None = None,
    cgroup_attestation_timeout_seconds: float = 2.0,
    cleanup_timeout_seconds: float = 2.0,
    peer_authority: WAWPeerAuthority | None = None,
) -> WAWLifecycleRegistry:
    return WAWLifecycleRegistry(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision="1",
        host_manifest_digest="c" * 64,
        project_root_manifest_digest="d" * 64,
        executor=executor,
        binding_digest_factory=lambda _request: DIGEST,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
        cgroup_attestation_timeout_seconds=cgroup_attestation_timeout_seconds,
        cleanup_timeout_seconds=cleanup_timeout_seconds,
        peer_authority=peer_authority,
    )


def observed_peer(
    authority: WAWPeerAuthority, pid: int, descriptor: int
) -> WAWPeerCandidate | WAWPeerLease:
    peer = authority.observe_control(pid, os.geteuid(), os.getegid(), descriptor)
    assert type(peer) in {WAWPeerCandidate, WAWPeerLease}
    return cast(WAWPeerCandidate | WAWPeerLease, peer)


def encrypted_service() -> WAWEncryptedAttachmentService:
    def forbidden_peer() -> RuntimePeer:
        raise AssertionError("typed dispatch must supply the Runtime peer")

    streams = WAWEncryptedRegistry(runtime_epoch="1", static_key=lambda: b"k" * 32)
    return WAWEncryptedAttachmentService(
        streams,
        peer=forbidden_peer,
        supervisor=cast(Any, lambda _claims: None),
        current=lambda _claims: True,
    )


@pytest.mark.anyio
async def test_binding_gate_and_idempotent_bind_and_register() -> None:
    runtime = registry()
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(register_request())
    assert exc_info.value.code == "BINDING_BOOTSTRAP_REQUIRED"

    first_bind = bind_request()
    assert (await runtime.dispatch(first_bind))["status"] == "BOUND"
    assert (await runtime.dispatch(first_bind))["status"] == "ALREADY_BOUND"
    assert first_bind["request_id"] not in runtime._request_cache
    assert (await runtime.dispatch(bind_request("wreq_" + "2" * 32)))["status"] == "ALREADY_BOUND"
    first = await runtime.dispatch(register_request())
    assert first["status"] == "REGISTERED"
    duplicate = await runtime.dispatch(register_request(request_id="wreq_" + "6" * 32))
    assert duplicate["status"] == "ALREADY_CURRENT"


@pytest.mark.anyio
async def test_peer_authority_bind_repeat_and_terminal_transfer() -> None:
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    old_read, old_write = os.pipe()
    new_read, new_write = os.pipe()
    candidate = observed_peer(authority, 101, old_read)
    try:
        with pytest.raises(WAWControlDispatchError) as unbound:
            await runtime.dispatch(register_request(), candidate)
        assert unbound.value.code == "BINDING_BOOTSTRAP_REQUIRED"

        assert (await runtime.dispatch(bind_request(), candidate))["status"] == "BOUND"
        foreign = observed_peer(authority, 202, new_read)
        with pytest.raises(WAWControlDispatchError) as conflict:
            await runtime.dispatch(bind_request(), foreign)
        assert conflict.value.code == "RUNTIME_INSTALLATION_MISMATCH"
        foreign.close()
        old_lease = observed_peer(authority, 101, old_read)
        assert type(old_lease) is WAWPeerLease
        assert (await runtime.dispatch(bind_request("wreq_" + "2" * 32), old_lease))[
            "status"
        ] == "ALREADY_BOUND"
        current_lease = observed_peer(authority, 101, old_read)
        assert type(current_lease) is WAWPeerLease
        assert (await runtime.dispatch(register_request(), current_lease))["status"] == "REGISTERED"

        os.close(old_write)
        old_write = -1
        replacement = observed_peer(authority, 202, new_read)
        transfer_request = {
            **bind_request("wreq_" + "3" * 32),
            "api_authority_epoch": "2",
            "authority_nonce": "c" * 32,
        }
        assert (await runtime.dispatch(transfer_request, replacement))["status"] == "BOUND"
        assert not old_lease.current() and not current_lease.current()
    finally:
        for peer in (
            candidate,
            locals().get("foreign"),
            locals().get("old_lease"),
            locals().get("current_lease"),
            locals().get("replacement"),
        ):
            if isinstance(peer, (WAWPeerCandidate, WAWPeerLease)):
                peer.close()
        authority.close()
        os.close(old_read)
        if old_write >= 0:
            os.close(old_write)
        os.close(new_read)
        os.close(new_write)


@pytest.mark.anyio
async def test_peer_authority_bind_never_uses_generic_request_cache() -> None:
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    read_fd, write_fd = os.pipe()
    candidate = observed_peer(authority, 101, read_fd)
    try:
        request = bind_request()
        assert (await runtime.dispatch(request, candidate))["status"] == "BOUND"
        lease = observed_peer(authority, 101, read_fd)
        assert type(lease) is WAWPeerLease
        assert (await runtime.dispatch(request, lease))["status"] == "ALREADY_BOUND"
        assert request["request_id"] not in runtime._request_cache
        lease.close()
    finally:
        candidate.close()
        authority.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["first", "already", "transfer"])
async def test_committed_service_bind_failure_revokes_before_authority_close(
    phase: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    service = encrypted_service()
    runtime.configure_encrypted_attachments(service)
    old_read, old_write = os.pipe()
    new_read, new_write = os.pipe()
    candidate = observed_peer(authority, 101, old_read)
    fail_bind = False
    events: list[tuple[str, object | None]] = []
    bound_identity: object | None = None

    def bind(_request: dict[str, Any], peer: RuntimePeer | None = None) -> None:
        nonlocal bound_identity
        assert peer is not None
        bound_identity = peer.identity
        events.append(("bind", peer.identity))
        if fail_bind:
            raise EncryptedStreamError("RUNTIME_PEER_FORBIDDEN")

    def revoke(identity: object) -> bool:
        nonlocal bound_identity
        events.append(("invalidate", identity))
        if bound_identity is identity:
            bound_identity = None
        events.append(("cleanup", identity))
        return True

    real_close = authority.close

    def close_authority() -> None:
        if not authority._closed:
            events.append(("authority-close", None))
        real_close()

    monkeypatch.setattr(service, "bind_authority", bind)
    monkeypatch.setattr(service, "revoke_authority", revoke)
    monkeypatch.setattr(authority, "close", close_authority)
    peers: list[WAWPeerCandidate | WAWPeerLease] = [candidate]
    try:
        if phase != "first":
            await runtime.dispatch(bind_request(), candidate)
            events.clear()
        if phase == "transfer":
            os.close(old_write)
            old_write = -1
            selected = observed_peer(authority, 202, new_read)
            request = {
                **bind_request("wreq_" + "3" * 32),
                "api_authority_epoch": "2",
                "authority_nonce": "c" * 32,
            }
        elif phase == "already":
            selected = observed_peer(authority, 101, old_read)
            request = bind_request("wreq_" + "2" * 32)
        else:
            selected = candidate
            request = bind_request()
        if selected is not candidate:
            peers.append(selected)
        runtime._attachments["old"] = {"authority": "old"}
        runtime._request_cache["wreq_" + "f" * 32] = (
            "old",
            {"status": "OLD"},
        )
        fail_bind = True
        with pytest.raises(WAWControlDispatchError) as raised:
            await runtime.dispatch(request, selected)
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        kinds = [kind for kind, _identity in events]
        assert kinds == (
            ["invalidate", "cleanup", "bind", "invalidate", "cleanup", "authority-close"]
            if phase == "transfer"
            else ["bind", "invalidate", "cleanup", "authority-close"]
        )
        assert runtime._authority is None and runtime._request_cache == {}
        assert runtime._attachments == {} and runtime._authority_quarantined
        with pytest.raises(WAWPeerAuthorityError) as closed:
            authority.borrow()
        assert closed.value.code == "AUTHORITY_CLOSED"
    finally:
        for peer in peers:
            peer.close()
        with suppress(WAWPeerAuthorityError):
            authority.close()
        os.close(old_read)
        if old_write >= 0:
            os.close(old_write)
        os.close(new_read)
        os.close(new_write)


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["borrow", "lease_close"])
async def test_post_commit_peer_fault_revokes_existing_service_authority(
    fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    service = encrypted_service()
    runtime.configure_encrypted_attachments(service)
    read_fd, write_fd = os.pipe()
    candidate = observed_peer(authority, 101, read_fd)
    revoked: list[object] = []
    monkeypatch.setattr(service, "bind_authority", lambda _request, _peer=None: None)

    def revoke(identity: object) -> bool:
        revoked.append(identity)
        return True

    monkeypatch.setattr(service, "revoke_authority", revoke)
    try:
        await runtime.dispatch(bind_request(), candidate)
        identity = runtime._peer_authority_identity
        lease = observed_peer(authority, 101, read_fd)
        assert type(lease) is WAWPeerLease and identity is not None
        real_borrow = authority.borrow

        if fault == "borrow":

            def failed_borrow() -> WAWPeerLease | None:
                raise WAWPeerAuthorityError("PEER_NOT_CURRENT")

            monkeypatch.setattr(authority, "borrow", failed_borrow)
        else:

            def close_failing_borrow() -> WAWPeerLease | None:
                borrowed = real_borrow()
                assert borrowed is not None
                real_lease_close = borrowed.close

                def failed_close() -> None:
                    real_lease_close()
                    raise OSError("synthetic lease close failure")

                borrowed.close = failed_close  # type: ignore[method-assign]
                return borrowed

            monkeypatch.setattr(authority, "borrow", close_failing_borrow)

        with pytest.raises(WAWControlDispatchError) as raised:
            await runtime.dispatch(bind_request("wreq_" + "2" * 32), lease)
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        assert revoked == [identity]
        lease.close()
    finally:
        candidate.close()
        with suppress(WAWPeerAuthorityError):
            authority.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.anyio
async def test_already_bound_commit_close_failure_fences_session_before_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_waw_encrypted_stream import Harness

    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    harness = Harness(tmp_path)

    def forbidden_peer() -> RuntimePeer:
        raise AssertionError("typed dispatch must supply the Runtime peer")

    service = WAWEncryptedAttachmentService(
        harness.registry,
        peer=forbidden_peer,
        supervisor=lambda _claims: harness.supervisor,
        current=lambda _claims: harness.valid,
    )
    runtime.configure_encrypted_attachments(service)
    read_fd, write_fd = os.pipe()
    candidate = observed_peer(authority, 101, read_fd)
    events: list[str] = []

    class Publication:
        def fence(self) -> bool:
            events.append("publication-fence")
            return True

        def send(self, _data: memoryview) -> int:
            raise AssertionError("revoked publication must not send")

    try:
        await runtime.dispatch(bind_request(), candidate)
        bound_lease = authority.borrow()
        assert bound_lease is not None
        runtime_peer = bound_lease.runtime_peer
        bound_lease.close()
        record = next(iter(harness.registry._records.values()))
        record.peer = runtime_peer
        harness.session._publication = Publication()
        harness.session._publication_fenced = False
        original_cleanup = harness.transport.close_attachment

        def cleanup(lease: Any) -> Any:
            events.append("pty-cleanup")
            return original_cleanup(lease)

        harness.transport.close_attachment = cleanup
        original_plan_close = WAWPeerTransferPlan.close

        def failed_plan_close(plan: WAWPeerTransferPlan) -> None:
            original_plan_close(plan)
            events.append("plan-close-failed")
            raise OSError("synthetic plan close failure")

        monkeypatch.setattr(WAWPeerTransferPlan, "close", failed_plan_close)
        original_authority_close = authority.close

        def close_authority() -> None:
            if not authority._closed:
                events.append("authority-close")
            original_authority_close()

        monkeypatch.setattr(authority, "close", close_authority)
        control_lease = observed_peer(authority, 101, read_fd)
        assert type(control_lease) is WAWPeerLease
        with pytest.raises(WAWControlDispatchError) as raised:
            await runtime.dispatch(bind_request("wreq_" + "2" * 32), control_lease)
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        assert events == [
            "plan-close-failed",
            "publication-fence",
            "pty-cleanup",
            "authority-close",
        ]
        assert harness.session.closed and harness.registry.count == 0
        assert runtime._authority is None and runtime._authority_quarantined
        control_lease.close()
    finally:
        candidate.close()
        with suppress(WAWPeerAuthorityError):
            authority.close()
        harness.session.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["first", "transfer"])
async def test_unpublished_commit_failure_closes_without_revoking_unrelated_identity(
    phase: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    service = encrypted_service()
    runtime.configure_encrypted_attachments(service)
    old_read, old_write = os.pipe()
    new_read, new_write = os.pipe()
    candidate = observed_peer(authority, 101, old_read)
    revoked: list[object] = []
    monkeypatch.setattr(service, "bind_authority", lambda _request, _peer=None: None)

    def revoke(identity: object) -> bool:
        revoked.append(identity)
        return True

    monkeypatch.setattr(service, "revoke_authority", revoke)
    peers: list[WAWPeerCandidate | WAWPeerLease] = [candidate]
    try:
        old_identity: object | None = None
        if phase == "transfer":
            await runtime.dispatch(bind_request(), candidate)
            old_identity = runtime._peer_authority_identity
            assert old_identity is not None
            os.close(old_write)
            old_write = -1
            selected = observed_peer(authority, 202, new_read)
            peers.append(selected)
            request = {
                **bind_request("wreq_" + "3" * 32),
                "api_authority_epoch": "2",
                "authority_nonce": "c" * 32,
            }
        else:
            selected = candidate
            request = bind_request()

        def failed_commit(_plan: WAWPeerTransferPlan) -> WAWPeerBindStatus:
            raise WAWPeerAuthorityError("TRANSFER_STALE")

        monkeypatch.setattr(authority, "commit_bind", failed_commit)
        runtime._attachments["old"] = {"authority": "old"}
        runtime._request_cache["wreq_" + "f" * 32] = ("old", {"status": "OLD"})
        with pytest.raises(WAWControlDispatchError) as raised:
            await runtime.dispatch(request, selected)
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        assert revoked == ([] if old_identity is None else [old_identity])
        assert authority._closed and runtime._authority is None
        assert not runtime._attachments and not runtime._request_cache
    finally:
        for peer in peers:
            peer.close()
        with suppress(WAWPeerAuthorityError):
            authority.close()
        os.close(old_read)
        if old_write >= 0:
            os.close(old_write)
        os.close(new_read)
        os.close(new_write)


@pytest.mark.anyio
async def test_shutdown_revokes_then_leaves_authority_close_to_application_owner() -> None:
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    service = encrypted_service()
    runtime.configure_encrypted_attachments(service)
    read_fd, write_fd = os.pipe()
    candidate = observed_peer(authority, 101, read_fd)
    revoked: list[object] = []
    release = asyncio.Event()
    worker = asyncio.create_task(release.wait())
    runtime._encrypted_operations.add(cast(Any, worker))
    worker.add_done_callback(lambda task: runtime._encrypted_done(cast(Any, task)))
    monkeypatch_target = cast(Any, service)
    monkeypatch_target.bind_authority = lambda _request, _peer=None: None

    def revoke(identity: object) -> bool:
        revoked.append(identity)
        return True

    monkeypatch_target.revoke_authority = revoke
    try:
        await runtime.dispatch(bind_request(), candidate)
        identity = runtime._peer_authority_identity
        assert identity is not None
        runtime._attachments["old"] = {"authority": "old"}
        runtime._request_cache["wreq_" + "f" * 32] = ("old", {"status": "OLD"})

        await runtime.begin_shutdown()
        await runtime.begin_shutdown()

        assert revoked == [identity]
        assert runtime._authority is None and not runtime._attachments
        assert not runtime._request_cache and not authority._closed
        rejected_peer = observed_peer(authority, 101, read_fd)
        try:
            with pytest.raises(WAWControlDispatchError) as stopped:
                await runtime.dispatch(bind_request(), rejected_peer)
            assert stopped.value.code == "RUNTIME_UNAVAILABLE"
        finally:
            rejected_peer.close()

        authority.close()
        wait = asyncio.create_task(runtime.wait_shutdown_workers())
        await asyncio.sleep(0)
        assert not wait.done()
        release.set()
        await wait
        await runtime.wait_shutdown_workers()
    finally:
        release.set()
        await worker
        candidate.close()
        with suppress(WAWPeerAuthorityError):
            authority.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.anyio
async def test_shutdown_revoke_failure_is_sticky_but_does_not_close_authority() -> None:
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    runtime = registry(peer_authority=authority)
    service = encrypted_service()
    runtime.configure_encrypted_attachments(service)
    read_fd, write_fd = os.pipe()
    candidate = observed_peer(authority, 101, read_fd)
    monkeypatch_target = cast(Any, service)
    monkeypatch_target.bind_authority = lambda _request, _peer=None: None
    monkeypatch_target.revoke_authority = lambda _identity: False
    try:
        await runtime.dispatch(bind_request(), candidate)
        with pytest.raises(WAWControlDispatchError) as first:
            await runtime.begin_shutdown()
        with pytest.raises(WAWControlDispatchError) as repeated:
            await runtime.begin_shutdown()
        assert repeated.value is first.value
        assert not authority._closed and runtime._authority_quarantine_identities
        authority.close()
        with pytest.raises(WAWControlDispatchError) as waited:
            await runtime.wait_shutdown_workers()
        assert waited.value is first.value
    finally:
        candidate.close()
        with suppress(WAWPeerAuthorityError):
            authority.close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.anyio
async def test_attachment_prepare_and_detach_require_exact_tuple_and_cleanup_ack() -> None:
    runtime = registry(FakeExecutor())
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    prepared = await runtime.dispatch(
        attachment_request("workspace.attach.prepare", request_id="wreq_" + "7" * 32)
    )
    assert prepared["status"] == "PREPARED"
    assert len(prepared["capability"]) == 64
    detached = await runtime.dispatch(
        attachment_request("workspace.attach.detach", request_id="wreq_" + "8" * 32)
    )
    assert detached["status"] == "DETACHED"
    assert detached["cleanup_state"] == "ATTACH_PTY_CLOSED"
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(
            attachment_request("workspace.attach.detach", request_id="wreq_" + "9" * 32)
        )
    assert exc_info.value.code == "ATTACHMENT_STALE"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "resume_cursor,previous_runtime_epoch",
    [("8", None), ("0", "1"), ("8", "2")],
)
async def test_attachment_prepare_rejects_resume_hint_outside_closed_set(
    resume_cursor: str, previous_runtime_epoch: str | None
) -> None:
    runtime = registry(FakeExecutor())
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    request = attachment_request("workspace.attach.prepare", request_id="wreq_" + "a" * 32)
    request["resume_cursor"] = resume_cursor
    request["previous_runtime_epoch"] = previous_runtime_epoch
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(request)
    assert exc_info.value.code == "RESUME_HINT_INVALID"


@pytest.mark.anyio
async def test_binding_revision_requires_exact_predecessor_digest() -> None:
    runtime = registry()
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    stale = register_request(revision="2", previous="1", request_id="wreq_" + "8" * 32)
    stale["previous_binding_digest"] = "f" * 64
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(stale)
    assert exc_info.value.code == "PROJECT_IDENTITY_CHANGED"
    current = register_request(revision="2", previous="1", request_id="wreq_" + "9" * 32)
    assert (await runtime.dispatch(current))["status"] == "REGISTERED"


@pytest.mark.anyio
async def test_missing_binding_registry_rejects_revision_jump() -> None:
    runtime = registry()
    await runtime.dispatch(bind_request())
    jumped = register_request(revision="2", previous="1")
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(jumped)
    assert exc_info.value.code == "PROJECT_IDENTITY_CHANGED"


@pytest.mark.anyio
async def test_start_attestation_failure_attempts_exact_cleanup() -> None:
    executor = FakeExecutor()
    runtime = registry(executor, cast(WAWWorkspaceAttestationStore, FailingAttestationStore()))
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    assert [kind for kind, _identity in executor.calls] == ["start", "stop"]


@pytest.mark.anyio
async def test_start_attestation_cleanup_requires_positive_stopped_evidence() -> None:
    executor = RunningCleanupExecutor()
    runtime = registry(executor, cast(WAWWorkspaceAttestationStore, FailingAttestationStore()))
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"


@pytest.mark.anyio
async def test_cleanup_timeout_releases_registry_and_consumes_detached_result() -> None:
    executor = CancellationResistantCleanupExecutor()
    runtime = registry(
        executor,
        cast(WAWWorkspaceAttestationStore, FailingAttestationStore()),
        cleanup_timeout_seconds=0.001,
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    assert [kind for kind, _identity in executor.calls] == ["start", "stop"]
    assert len(runtime._detached_cleanup_tasks) == 1
    executor.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(runtime._detached_cleanup_tasks) == 0


@pytest.mark.anyio
async def test_cleanup_timeout_quarantines_new_generation_until_stop_finishes() -> None:
    executor = CancellationResistantCleanupExecutor()
    runtime = registry(
        executor,
        cast(WAWWorkspaceAttestationStore, FailingAttestationStore()),
        cleanup_timeout_seconds=0.001,
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError):
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(
            lifecycle_request(
                "workspace.workspace.start", generation="2", request_id="wreq_" + "9" * 32
            )
        )
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    with pytest.raises(WAWControlDispatchError) as blocked:
        await runtime.dispatch(
            lifecycle_request("workspace.workspace.status", request_id="wreq_" + "a" * 32)
        )
    assert blocked.value.code == "RECONCILIATION_REQUIRED"
    reconcile = await runtime.dispatch(
        lifecycle_request("workspace.workspace.reconcile", request_id="wreq_" + "b" * 32)
    )
    assert reconcile["status"] == "RECONCILIATION_REQUIRED"
    assert (
        decode_control_response(
            encode_control_response(reconcile, "workspace.workspace.reconcile"),
            "workspace.workspace.reconcile",
            expected_request_id=reconcile["request_id"],
        )
        == reconcile
    )
    with pytest.raises(WAWControlDispatchError) as blocked_stop:
        await runtime.dispatch(
            lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "c" * 32)
        )
    assert blocked_stop.value.code == "RECONCILIATION_REQUIRED"
    executor.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Executor STOPPED is necessary but not sufficient; a host-gated
    # EMPTY_DURABLE read-back is still required to clear quarantine.
    assert len(runtime._cleanup_quarantine) == 1


@pytest.mark.anyio
async def test_start_rejects_fenced_or_unpopulated_cgroup_attestation(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    executor = FakeExecutor()
    runtime = registry(
        executor,
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: replace(
            cgroup_record(), attachment_leaves=(), cleanup_state="FENCED", last_populated="0"
        ),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    persisted = store.read(workspace_id=WORKSPACE, generation=1)
    assert persisted is not None
    assert persisted.cleanup_state == "FENCED"


@pytest.mark.anyio
async def test_start_persists_cgroup_attestation_before_exposing_generation(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    executor = FakeExecutor()
    runtime = registry(
        executor,
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    response = await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert response["status"] == "STARTED"
    assert store.read(workspace_id=WORKSPACE, generation=1) == cgroup_record()


@pytest.mark.anyio
async def test_stop_persists_fenced_cgroup_attestation_before_returning(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )

    def factory(
        _identity: WAWLifecycleIdentity, observation: WAWLifecycleObservation
    ) -> WAWCgroupAttestation:
        if observation.state == "STOPPED":
            return replace(cgroup_record(), attachment_leaves=(), cleanup_state="FENCED")
        return cgroup_record()

    runtime = registry(
        FakeExecutor(),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=factory,
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    response = await runtime.dispatch(
        lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "7" * 32)
    )
    assert response["status"] == "STOPPED"
    persisted = store.read(workspace_id=WORKSPACE, generation=1)
    assert persisted is not None
    assert persisted.cleanup_state == "FENCED"


@pytest.mark.anyio
async def test_stop_rejects_live_cgroup_attestation_and_fences_record(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    runtime = registry(
        FakeExecutor(),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(
            lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "8" * 32)
        )
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    persisted = store.read(workspace_id=WORKSPACE, generation=1)
    assert persisted is not None
    assert persisted.cleanup_state == "FENCED"


@pytest.mark.anyio
async def test_workspace_attestation_failure_fences_cgroup_record_after_cleanup(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    runtime = registry(
        FakeExecutor(),
        cast(WAWWorkspaceAttestationStore, FailingAttestationStore()),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    persisted = store.read(workspace_id=WORKSPACE, generation=1)
    assert persisted is not None
    assert persisted.cleanup_state == "FENCED"


@pytest.mark.anyio
async def test_host_gated_empty_acknowledgement_is_required_to_clear_quarantine(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    runtime = registry(
        FakeExecutor(),
        cast(WAWWorkspaceAttestationStore, FailingAttestationStore()),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError):
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert len(runtime._cleanup_quarantine) == 1
    fenced = store.read(workspace_id=WORKSPACE, generation=1)
    assert fenced is not None
    empty = replace(
        fenced,
        attachment_leaves=(),
        last_populated="0",
        cleanup_state="EMPTY_DURABLE",
    )
    await runtime.acknowledge_cgroup_cleanup(
        empty,
        binding_revision="1",
        binding_digest=DIGEST,
    )
    assert len(runtime._cleanup_quarantine) == 0
    assert store.read(workspace_id=WORKSPACE, generation=1) == empty


@pytest.mark.anyio
async def test_empty_acknowledgement_binds_active_binding_identity(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    runtime = registry(
        FakeExecutor(),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    runtime._cleanup_quarantine.add(WORKSPACE)
    empty = replace(
        cgroup_record(),
        attachment_leaves=(),
        last_populated="0",
        cleanup_state="EMPTY_DURABLE",
    )

    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await runtime.acknowledge_cgroup_cleanup(
            empty,
            binding_revision="2",
            binding_digest=DIGEST,
        )
    assert WORKSPACE in runtime._cleanup_quarantine

    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await runtime.acknowledge_cgroup_cleanup(
            empty,
            binding_revision="1",
            binding_digest="b" * 64,
        )
    assert WORKSPACE in runtime._cleanup_quarantine

    await runtime.acknowledge_cgroup_cleanup(
        empty,
        binding_revision="1",
        binding_digest=DIGEST,
    )
    assert WORKSPACE not in runtime._cleanup_quarantine


@pytest.mark.anyio
async def test_cleanup_acknowledgement_waits_for_registry_mutation_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    fenced = replace(cgroup_record(), attachment_leaves=(), cleanup_state="FENCED")
    store.write(fenced)
    runtime = registry(
        FakeExecutor(),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    runtime._cleanup_quarantine.add(WORKSPACE)
    empty = replace(fenced, last_populated="0", cleanup_state="EMPTY_DURABLE")

    entered = asyncio.Event()
    original = runtime._acknowledge_cgroup_cleanup_unlocked

    def wrapped(
        record: WAWCgroupAttestation,
        *,
        binding_revision: str | None,
        binding_digest: str | None,
    ) -> None:
        entered.set()
        original(
            record,
            binding_revision=binding_revision,
            binding_digest=binding_digest,
        )

    monkeypatch.setattr(runtime, "_acknowledge_cgroup_cleanup_unlocked", wrapped)

    await runtime._lock.acquire()
    task = asyncio.create_task(
        runtime.acknowledge_cgroup_cleanup(
            empty,
            binding_revision="1",
            binding_digest=DIGEST,
        )
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(entered.wait(), timeout=0.1)
    runtime._lock.release()
    await asyncio.wait_for(entered.wait(), timeout=1)
    await task
    assert WORKSPACE not in runtime._cleanup_quarantine


@pytest.mark.anyio
async def test_restart_acknowledgement_requires_hydrated_project_binding(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    fenced = replace(cgroup_record(), attachment_leaves=(), cleanup_state="FENCED")
    store.write(fenced)
    runtime = registry(
        FakeExecutor(),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    empty = replace(fenced, last_populated="0", cleanup_state="EMPTY_DURABLE")

    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await runtime.acknowledge_cgroup_cleanup(empty)
    assert WORKSPACE not in runtime._cleanup_quarantine

    await runtime.acknowledge_cgroup_cleanup(
        empty,
        binding_revision="1",
        binding_digest=DIGEST,
    )
    assert WORKSPACE not in runtime._cleanup_quarantine


@pytest.mark.anyio
async def test_registry_restart_hydrates_fenced_quarantine_before_executor_start(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    fenced = replace(cgroup_record(), attachment_leaves=(), cleanup_state="FENCED")
    store.write(fenced)

    executor = FakeExecutor()
    runtime = registry(
        executor,
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    assert executor.calls == []


@pytest.mark.anyio
async def test_empty_ack_must_target_highest_unresolved_generation(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    generation_one = replace(
        cgroup_record(), attachment_leaves=(), last_populated="0", cleanup_state="EMPTY_DURABLE"
    )
    generation_two = replace(
        cgroup_record(),
        generation=2,
        workspace_relative_path="waw/ws-111-g2",
        workspace_inode="23",
        workload_relative_path="waw/ws-111-g2/workload",
        workload_inode="24",
        attachment_leaves=(),
        cleanup_state="FENCED",
    )
    store.write(generation_one)
    store.write(generation_two)

    runtime = registry(
        FakeExecutor(),
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: cgroup_record(),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    runtime._cleanup_quarantine.add(WORKSPACE)
    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await runtime.acknowledge_cgroup_cleanup(
            replace(generation_one, last_populated="0", cleanup_state="EMPTY_DURABLE"),
            binding_revision="1",
            binding_digest=DIGEST,
        )
    assert WORKSPACE in runtime._cleanup_quarantine

    await runtime.acknowledge_cgroup_cleanup(
        replace(generation_two, last_populated="0", cleanup_state="EMPTY_DURABLE"),
        binding_revision="1",
        binding_digest=DIGEST,
    )
    assert WORKSPACE not in runtime._cleanup_quarantine


def test_cgroup_attestation_store_and_factory_must_be_paired(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    with pytest.raises(ValueError, match="provided together"):
        registry(cgroup_attestation_store=store)


@pytest.mark.anyio
async def test_async_cgroup_factory_timeout_cleans_up_and_fences_start(tmp_path: Path) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )

    async def slow_factory(
        _identity: WAWLifecycleIdentity, _observation: WAWLifecycleObservation
    ) -> WAWCgroupAttestation:
        await asyncio.sleep(0.05)
        return cgroup_record()

    executor = FakeExecutor()
    runtime = registry(
        executor,
        cgroup_attestation_store=store,
        cgroup_attestation_factory=slow_factory,
        cgroup_attestation_timeout_seconds=0.001,
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    assert [kind for kind, _identity in executor.calls] == ["start", "stop"]
    assert store.read(workspace_id=WORKSPACE, generation=1) is None


@pytest.mark.anyio
async def test_cgroup_attestation_mismatch_cleans_up_and_keeps_generation_fenced(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    store = WAWCgroupAttestationStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )
    executor = FakeExecutor()
    runtime = registry(
        executor,
        cgroup_attestation_store=store,
        cgroup_attestation_factory=lambda _identity, _observation: replace(
            cgroup_record(), runtime_epoch="9"
        ),
    )
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
    assert [kind for kind, _identity in executor.calls] == ["start", "stop"]
    persisted = store.read(workspace_id=WORKSPACE, generation=1)
    assert persisted is not None
    assert persisted.cleanup_state == "FENCED"


@pytest.mark.anyio
async def test_lifecycle_fences_identity_before_executor() -> None:
    executor = FakeExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())

    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start", digest="e" * 64))
    assert exc_info.value.code == "PROJECT_IDENTITY_CHANGED"
    assert executor.calls == []


@pytest.mark.anyio
async def test_lifecycle_registry_rejects_unknown_agent_type() -> None:
    executor = FakeExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    request = lifecycle_request("workspace.workspace.start")
    request["agent_type"] = "arbitrary-provider"
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(request)
    assert exc_info.value.code == "WAW_AGENT_UNSUPPORTED"
    assert executor.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "observation",
    (
        WAWLifecycleObservation(state="RUNNING", process_state="STOPPED"),
        WAWLifecycleObservation(state="STOPPED", process_state="RUNNING"),
        WAWLifecycleObservation(state="STOPPED", process_state="STOPPED", exit_code=0),
        WAWLifecycleObservation(state="EXITED", process_state="STOPPED"),
        WAWLifecycleObservation(state="RUNNING", process_state="RUNNING", exit_code=0),
        WAWLifecycleObservation(
            state="RUNNING", process_state="RUNNING", reconciliation_state="missing"
        ),
        WAWLifecycleObservation(
            state="STOPPED", process_state="STOPPED", reconciliation_state="reconciliation_required"
        ),
    ),
)
async def test_lifecycle_rejects_contradictory_observations(
    observation: WAWLifecycleObservation,
) -> None:
    runtime = registry(ObservationExecutor(observation))
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "INTERNAL_BOUNDED"


@pytest.mark.anyio
async def test_lifecycle_dispatches_typed_start_status_stop_and_reconcile() -> None:
    executor = FakeExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())

    start = await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert (
        decode_control_response(
            encode_control_response(start, "workspace.workspace.start"),
            "workspace.workspace.start",
            expected_request_id=cast(str, start["request_id"]),
        )
        == start
    )
    assert start["status"] == "STARTED"
    assert start["state"] == "RUNNING"
    again = await runtime.dispatch(
        lifecycle_request("workspace.workspace.start", request_id="wreq_" + "6" * 32)
    )
    assert again["status"] == "ALREADY_RUNNING"
    status = await runtime.dispatch(
        lifecycle_request("workspace.workspace.status", request_id="wreq_" + "7" * 32)
    )
    assert status["status"] == "STATUS"
    reconcile = await runtime.dispatch(
        lifecycle_request("workspace.workspace.reconcile", request_id="wreq_" + "8" * 32)
    )
    assert reconcile["status"] == "RECONCILED"
    stop = await runtime.dispatch(
        lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "9" * 32)
    )
    assert stop["status"] == "STOPPED"
    assert [name for name, _ in executor.calls] == ["start", "status", "reconcile", "stop"]


@pytest.mark.anyio
async def test_host_mismatch_has_no_side_effect() -> None:
    executor = FakeExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    request = lifecycle_request("workspace.workspace.start")
    request["runtime_host_installation_revision"] = "2"
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(request)
    assert exc_info.value.code == "RUNTIME_INSTALLATION_MISMATCH"
    assert executor.calls == []


@pytest.mark.anyio
async def test_generation_floor_and_stop_are_idempotent() -> None:
    executor = FakeExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    first_stop = await runtime.dispatch(
        lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "6" * 32)
    )
    second_stop = await runtime.dispatch(
        lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "7" * 32)
    )
    assert first_stop["status"] == "STOPPED"
    assert second_stop["status"] == "ALREADY_STOPPED"
    assert [name for name, _ in executor.calls] == ["start", "stop"]
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(
            lifecycle_request("workspace.workspace.start", request_id="wreq_" + "8" * 32)
        )
    assert exc_info.value.code == "PROJECT_IDENTITY_CHANGED"
    restarted = await runtime.dispatch(
        lifecycle_request(
            "workspace.workspace.start", generation="2", request_id="wreq_" + "9" * 32
        )
    )
    assert restarted["status"] == "STARTED"


@pytest.mark.anyio
async def test_codex_lifecycle_uses_same_fenced_synthetic_contract() -> None:
    """Codex is admitted by the closed Runtime agent set without real login/process use."""

    executor = FakeExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request("wreq_" + "a" * 32))
    await runtime.dispatch(register_request(request_id="wreq_" + "b" * 32))

    codex_workspace = workspace_id(PROJECT, AgentType.CODEX)
    start = lifecycle_request(
        "workspace.workspace.start",
        request_id="wreq_" + "c" * 32,
    )
    start.update({"agent_type": AgentType.CODEX.value, "workspace_id": codex_workspace})
    assert (await runtime.dispatch(start))["status"] == "STARTED"

    attach = attachment_request("workspace.attach.prepare", request_id="wreq_" + "d" * 32)
    attach.update({"agent_type": AgentType.CODEX.value, "workspace_id": codex_workspace})
    prepared = await runtime.dispatch(attach)
    assert prepared["status"] == "PREPARED"
    assert prepared["agent_type"] == AgentType.CODEX.value

    status = lifecycle_request("workspace.workspace.status", request_id="wreq_" + "e" * 32)
    status.update({"agent_type": AgentType.CODEX.value, "workspace_id": codex_workspace})
    assert (await runtime.dispatch(status))["state"] == "RUNNING"

    stop = lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "f" * 32)
    stop.update({"agent_type": AgentType.CODEX.value, "workspace_id": codex_workspace})
    assert (await runtime.dispatch(stop))["status"] == "STOPPED"
    assert [name for name, identity in executor.calls] == ["start", "status", "stop"]
    assert all(identity.agent_type == AgentType.CODEX.value for _, identity in executor.calls)


@pytest.mark.anyio
@pytest.mark.parametrize("generation", ("18446744073709551615", "18446744073709551616"))
async def test_lifecycle_generation_enforces_uint64_upper_bound(generation: str) -> None:
    runtime = registry(FakeExecutor())
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    request = lifecycle_request("workspace.workspace.start", generation=generation)
    if generation == "18446744073709551615":
        assert (await runtime.dispatch(request))["status"] == "STARTED"
    else:
        with pytest.raises(WAWControlDispatchError) as exc_info:
            await runtime.dispatch(request)
        assert exc_info.value.code == "PROTOCOL_INVALID"


@pytest.mark.anyio
async def test_invalid_start_observation_requires_cleanup_and_consumes_generation() -> None:
    executor = InvalidExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "INTERNAL_BOUNDED"
    assert [method for method, _ in executor.calls] == ["start", "stop"]
    assert executor.calls[0][1] == executor.calls[1][1]
    stopped = await runtime.dispatch(
        lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "6" * 32)
    )
    assert stopped["status"] == "ALREADY_STOPPED"
    with pytest.raises(WAWControlDispatchError, match="PROJECT_IDENTITY_CHANGED"):
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))


@pytest.mark.anyio
async def test_failed_start_cleanup_can_retry_exact_stop_without_durable_stores() -> None:
    class UncertainExecutor(InvalidExecutor):
        closed = False

        async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
            self.calls.append(("stop", identity))
            if not self.closed:
                raise RuntimeError("synthetic cleanup failure")
            return WAWLifecycleObservation(state="STOPPED", process_state="STOPPED")

    executor = UncertainExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await runtime.dispatch(lifecycle_request("workspace.workspace.start", generation="2"))
    with pytest.raises(WAWControlDispatchError):
        await runtime.dispatch(lifecycle_request("workspace.workspace.stop", generation="2"))
    assert [method for method, _ in executor.calls] == ["start", "stop"]
    executor.closed = True
    stopped = await runtime.dispatch(
        lifecycle_request("workspace.workspace.stop", request_id="wreq_" + "6" * 32)
    )
    assert stopped["status"] == "STOPPED"
    with pytest.raises(WAWControlDispatchError, match="PROJECT_IDENTITY_CHANGED"):
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))


@pytest.mark.anyio
async def test_durable_attestation_fences_generation_across_registry_restart(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "attestations"
    directory.mkdir(mode=0o700)
    store = WAWWorkspaceAttestationStore(
        directory, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )
    first = registry(FakeExecutor(), store)
    await first.dispatch(bind_request())
    await first.dispatch(register_request())
    await first.dispatch(lifecycle_request("workspace.workspace.start"))

    restarted = registry(FakeExecutor(), store)
    await restarted.dispatch(bind_request("wreq_" + "6" * 32))
    await restarted.dispatch(register_request(request_id="wreq_" + "7" * 32))
    with pytest.raises(WAWControlDispatchError) as stale:
        await restarted.dispatch(
            lifecycle_request("workspace.workspace.start", request_id="wreq_" + "8" * 32)
        )
    assert stale.value.code == "RECONCILIATION_REQUIRED"


@pytest.mark.anyio
async def test_generation_reservation_failure_prevents_executor_side_effects() -> None:
    class RejectReservation(FailingAttestationStore):
        def advance(self, **_kwargs: Any) -> None:
            raise WAWWorkspaceAttestationError("synthetic durable write failure")

    executor = FakeExecutor()
    runtime = registry(executor, cast(WAWWorkspaceAttestationStore, RejectReservation()))
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert executor.calls == []


@pytest.mark.anyio
async def test_failed_executor_generation_is_durable_before_side_effect_and_restart(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "attestations"
    directory.mkdir(mode=0o700)
    store = WAWWorkspaceAttestationStore(
        directory, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )

    class FailedAfterSideEffect(FakeExecutor):
        async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
            persisted = store.read(identity.workspace_id)
            assert persisted is not None
            assert persisted.min_generation == int(identity.generation)
            self.calls.append(("start", identity))
            raise RuntimeError("synthetic process started before readiness failure")

        async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
            self.calls.append(("stop", identity))
            raise RuntimeError("synthetic cleanup unavailable")

    first_executor = FailedAfterSideEffect()
    first = registry(first_executor, store)
    await first.dispatch(bind_request())
    await first.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
        await first.dispatch(lifecycle_request("workspace.workspace.start"))
    assert [method for method, _ in first_executor.calls] == ["start", "stop"]
    restarted_executor = FakeExecutor()
    restarted = registry(restarted_executor, store)
    await restarted.dispatch(bind_request())
    await restarted.dispatch(register_request())
    for generation in ("1", "2"):
        with pytest.raises(WAWControlDispatchError, match="RECONCILIATION_REQUIRED"):
            await restarted.dispatch(
                lifecycle_request("workspace.workspace.start", generation=generation)
            )
    assert restarted_executor.calls == []
