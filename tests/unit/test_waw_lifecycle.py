from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
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
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleIdentity,
    WAWLifecycleObservation,
    WAWLifecycleRegistry,
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
    def advance(self, **_kwargs: Any) -> None:
        raise WAWWorkspaceAttestationError("synthetic attestation failure")


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
    )


@pytest.mark.anyio
async def test_binding_gate_and_idempotent_bind_and_register() -> None:
    runtime = registry()
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(register_request())
    assert exc_info.value.code == "BINDING_BOOTSTRAP_REQUIRED"

    assert (await runtime.dispatch(bind_request()))["status"] == "BOUND"
    assert (await runtime.dispatch(bind_request("wreq_" + "2" * 32)))["status"] == "ALREADY_BOUND"
    first = await runtime.dispatch(register_request())
    assert first["status"] == "REGISTERED"
    duplicate = await runtime.dispatch(register_request(request_id="wreq_" + "6" * 32))
    assert duplicate["status"] == "ALREADY_CURRENT"


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
    executor.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(runtime._cleanup_quarantine) == 0


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
async def test_lifecycle_registry_is_claude_only() -> None:
    executor = FakeExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    request = lifecycle_request("workspace.workspace.start")
    request["agent_type"] = "codex"
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
async def test_invalid_observation_does_not_poison_registry() -> None:
    executor = InvalidExecutor()
    runtime = registry(executor)
    await runtime.dispatch(bind_request())
    await runtime.dispatch(register_request())
    with pytest.raises(WAWControlDispatchError) as exc_info:
        await runtime.dispatch(lifecycle_request("workspace.workspace.start"))
    assert exc_info.value.code == "INTERNAL_BOUNDED"
    assert len(executor.calls) == 1
    assert executor.calls[0][0] == "start"
    with pytest.raises(WAWControlDispatchError) as missing:
        await runtime.dispatch(
            lifecycle_request("workspace.workspace.status", request_id="wreq_" + "6" * 32)
        )
    assert missing.value.code == "WORKSPACE_NOT_FOUND"


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
