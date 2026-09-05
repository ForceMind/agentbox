"""Synthetic composition coverage for the typed Runtime WAW executor."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import socket
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_core.waw_tickets import (
    ActiveAttachment,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
)
from agentbox_protocol.abws import ABWSFrame, FrameType
from agentbox_protocol.waw_wire import Leg, encode_wire_frame
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import inspect_executable
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_auth_probe import WAWPublicAuthEvidence, WAWPublicAuthResult
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWConflictError,
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)
from agentbox_runtime.waw_encrypted_stream import (
    RuntimePeer,
    WAWEncryptedRegistry,
    admission_fields,
)
from agentbox_runtime.waw_fixed_transport import (
    LinuxCgroupControlHandle,
    NativeWBREndpoint,
    WAWFixedTransport,
)
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleIdentity,
    WAWLifecycleRegistry,
    WAWProjectBinding,
)
from agentbox_runtime.waw_process_inspector import (
    FixedLaunchHandles,
    FixedLaunchRequest,
    FixedProcessBinding,
    FixedProcessIdentity,
    FixedStartProof,
    FixedStartState,
)
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_redraw import BoundedRedraw
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.waw_supervisor import (
    RuntimeAttachmentCleanupEvidence,
    RuntimeAttachmentLease,
    RuntimeProbeEvidence,
    RuntimeProbeState,
    RuntimeStartEvidence,
    RuntimeStopEvidence,
    SupervisorState,
)

PROJECT = "prj_" + "1" * 32
HOST = "wri_" + "2" * 32
DIGEST = "a" * 64


@dataclass
class FakeTransport:
    identity: WAWLifecycleIdentity
    marker: str
    starts: int = 0
    stops: int = 0
    detaches: int = 0
    writes: list[bytes] = field(default_factory=list)
    probe_state: RuntimeProbeState = RuntimeProbeState.RUNNING
    ready: bool = True
    start_gate: threading.Event | None = None
    fail_write: bool = False
    redraw: BoundedRedraw = field(default_factory=lambda: BoundedRedraw(b"", False))

    def start(self, command: Any, geometry: PtyGeometry) -> RuntimeStartEvidence:
        assert command.workspace_id == self.identity.workspace_id
        assert command.project_id == self.identity.project_id
        assert command.managed_marker == self.marker
        self.starts += 1
        if self.start_gate is not None:
            self.start_gate.wait(timeout=5)
        return RuntimeStartEvidence(
            self.identity.workspace_id,
            int(self.identity.generation),
            self.marker,
            SupervisorState.RUNNING,
            self.ready,
        )

    def write(self, data: bytes) -> None:
        if self.fail_write:
            raise OSError("synthetic delivery uncertainty")
        self.writes.append(data)

    def resize(self, geometry: PtyGeometry) -> None:
        assert geometry.columns > 0 and geometry.rows > 0

    def capture_redraw(self, _deadline: float) -> BoundedRedraw:
        return self.redraw

    def detach(self) -> bool:
        self.detaches += 1
        return True

    def stop(self) -> RuntimeStopEvidence:
        self.stops += 1
        return RuntimeStopEvidence(
            self.identity.workspace_id, int(self.identity.generation), self.marker, True, 0
        )

    def close_attachment(self, lease: RuntimeAttachmentLease) -> RuntimeAttachmentCleanupEvidence:
        return RuntimeAttachmentCleanupEvidence(lease, self.detach(), 0)

    def probe(self) -> RuntimeProbeEvidence:
        return RuntimeProbeEvidence(
            self.identity.workspace_id,
            int(self.identity.generation),
            self.marker,
            self.probe_state,
            -9 if self.probe_state is RuntimeProbeState.EXITED else None,
        )


def ident(agent: AgentType, generation: str = "1") -> WAWLifecycleIdentity:
    return WAWLifecycleIdentity(
        workspace_id(PROJECT, agent), PROJECT, agent.value, generation, "1", DIGEST, HOST, "1"
    )


def attachment(
    identity: WAWLifecycleIdentity, number: int = 1, epoch: str = "1"
) -> ActiveAttachment:
    claims = AttachmentTuple(
        identity.workspace_id,
        PROJECT,
        identity.agent_type,
        "att_" + str(number).zfill(32),
        number,
        int(identity.generation),
        1,
        1,
        HOST,
        1,
        1,
        DIGEST,
    )
    context = AuthenticatedAttachmentContext("session", "user", "scope", "origin", epoch, 1)
    return ActiveAttachment(claims, 0.0, 0.0, 100.0, 1000.0, context)


def setup(
    tmp_path: Path, agent: AgentType, generation: str = "1", epoch: str = "1"
) -> tuple[WAWSupervisorExecutor, WAWLifecycleIdentity, FakeTransport, Path]:
    root = tmp_path / "projects"
    project = root / "project-a"
    project.mkdir(parents=True)
    name = "claude" if agent is AgentType.CLAUDE else "codex"
    executable_path = tmp_path / name
    executable_path.write_text("#!/bin/sh\n")
    executable_path.chmod(0o755)
    identity = ident(agent, generation)
    marker = managed_marker(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        project_id=PROJECT,
        agent_type=agent,
        workspace_id_value=identity.workspace_id,
        generation=int(generation),
        binding_revision=1,
        binding_digest=DIGEST,
    )
    cls = WAWClaudeCommand if agent is AgentType.CLAUDE else WAWCodexCommand
    argv = ("remote-control",) if agent is AgentType.CLAUDE else ()
    executable = inspect_executable(executable_path)

    def factory(item: WAWLifecycleIdentity, configured: Any) -> WAWClaudeCommand | WAWCodexCommand:
        return cls(item.workspace_id, item.project_id, configured.path, executable, argv, marker)

    transport = FakeTransport(identity, marker)
    executor = WAWSupervisorExecutor(
        runtime_epoch=epoch,
        project_registry=ProjectRegistry(root),
        command_factory=factory,
        transport_factory=lambda _i, _c: transport,
        geometry=PtyGeometry(80, 24),
        clock=lambda: 0.0,
        attachment_validator=lambda a: a.active_at(0.0),
    )
    return executor, identity, transport, root


def generation_setup(
    tmp_path: Path,
    agent: AgentType,
    *,
    factory_entered: threading.Event | None = None,
    release_factory: threading.Event | None = None,
) -> tuple[WAWSupervisorExecutor, WAWLifecycleIdentity, dict[str, FakeTransport]]:
    root = tmp_path / "generation-projects"
    project = root / "project-a"
    project.mkdir(parents=True)
    executable_path = tmp_path / agent.value
    executable_path.write_text("#!/bin/sh\n")
    executable_path.chmod(0o755)
    executable = inspect_executable(executable_path)
    transports: dict[str, FakeTransport] = {}

    def command_factory(
        item: WAWLifecycleIdentity, configured: Any
    ) -> WAWClaudeCommand | WAWCodexCommand:
        marker = managed_marker(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision=1,
            project_id=PROJECT,
            agent_type=agent,
            workspace_id_value=item.workspace_id,
            generation=int(item.generation),
            binding_revision=1,
            binding_digest=DIGEST,
        )
        cls = WAWClaudeCommand if agent is AgentType.CLAUDE else WAWCodexCommand
        argv = ("remote-control",) if agent is AgentType.CLAUDE else ()
        return cls(item.workspace_id, item.project_id, configured.path, executable, argv, marker)

    def transport_factory(item: WAWLifecycleIdentity, command: Any) -> FakeTransport:
        transport = FakeTransport(item, command.managed_marker)
        transports[item.generation] = transport
        if item.generation == "2" and factory_entered is not None:
            factory_entered.set()
            if release_factory is not None:
                release_factory.wait(timeout=5)
        return transport

    executor = WAWSupervisorExecutor(
        runtime_epoch="1",
        project_registry=ProjectRegistry(root),
        command_factory=command_factory,
        transport_factory=transport_factory,
        geometry=PtyGeometry(80, 24),
        clock=lambda: 0.0,
        attachment_validator=lambda active: active.active_at(0.0),
    )
    return executor, ident(agent), transports


def binding(revision: str = "1", relative_key: str = "project-a") -> WAWProjectBinding:
    return WAWProjectBinding(PROJECT, relative_key, "1", revision, DIGEST, HOST, "1")


def _exercise_start_open_lock_order(tmp_dir: str, result: Any) -> None:
    """Run the lock-order schedule outside pytest so a regression cannot hang it."""

    tmp_path = Path(tmp_dir)
    root = tmp_path / "deadlock-projects"
    project = root / "project-a"
    project.mkdir(parents=True)
    executable_path = tmp_path / "codex"
    executable_path.write_text("#!/bin/sh\n")
    executable_path.chmod(0o755)
    executable = inspect_executable(executable_path)
    factory_entered = threading.Event()
    release_factory = threading.Event()
    open_has_supervisor = threading.Event()
    release_open_to_map = threading.Event()
    block_current = threading.Event()
    nested_map_to_supervisor = threading.Event()
    transports: dict[str, FakeTransport] = {}

    def command_factory(
        item: WAWLifecycleIdentity, configured: Any
    ) -> WAWClaudeCommand | WAWCodexCommand:
        marker = managed_marker(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision=1,
            project_id=PROJECT,
            agent_type=AgentType(item.agent_type),
            workspace_id_value=item.workspace_id,
            generation=int(item.generation),
            binding_revision=1,
            binding_digest=DIGEST,
        )
        return WAWCodexCommand(
            item.workspace_id, item.project_id, configured.path, executable, (), marker
        )

    def transport_factory(item: WAWLifecycleIdentity, command: Any) -> FakeTransport:
        transport = FakeTransport(item, command.managed_marker)
        transports[item.generation] = transport
        if item.generation == "2":
            factory_entered.set()
            release_factory.wait(timeout=5)
        return transport

    executor = WAWSupervisorExecutor(
        runtime_epoch="1",
        project_registry=ProjectRegistry(root),
        command_factory=command_factory,
        transport_factory=transport_factory,
        geometry=PtyGeometry(80, 24),
        clock=lambda: 0.0,
        attachment_validator=lambda active: active.active_at(0.0),
    )
    old_identity = ident(AgentType.CODEX)
    asyncio.run(executor.register_project_binding(binding()))
    asyncio.run(executor.start(old_identity))
    claims = attachment(old_identity).claims
    old_supervisor = executor.encrypted_supervisor(claims)
    peer = RuntimePeer(object(), "1", lambda: True)
    registry = WAWEncryptedRegistry(
        runtime_epoch="1", static_key=lambda: bytes(range(32)), clock=lambda: 0.0
    )

    def current() -> bool:
        if block_current.is_set():
            open_has_supervisor.set()
            release_open_to_map.wait(timeout=5)
        return executor.encrypted_binding_current(claims)

    capability = registry.prepare(
        peer=peer,
        claims=claims,
        supervisor=old_supervisor,
        current=current,
    )
    asyncio.run(executor.stop(old_identity))
    block_current.set()
    raw_hello = encode_wire_frame(
        FrameType.RUNTIME_HELLO,
        Leg.API_TO_RUNTIME,
        {
            "protocol_version": 1,
            **admission_fields(claims),
            "runtime_epoch": "1",
            "capability": capability,
            "resume_cursor": None,
            "previous_runtime_epoch": None,
        },
        1,
    )

    # The old implementation reads state twice. Its second read occurs while
    # holding the executor map, so this hook makes that exact ABBA edge visible.
    supervisor_class: Any = type(old_supervisor)
    original_state = cast(property, supervisor_class.state)
    original_getter = original_state.fget
    assert original_getter is not None
    state_reads = 0

    def observed_state(supervisor: Any) -> SupervisorState:
        nonlocal state_reads
        if supervisor is old_supervisor:
            state_reads += 1
            if state_reads == 2:
                nested_map_to_supervisor.set()
        return cast(SupervisorState, original_getter(supervisor))

    supervisor_class.state = property(observed_state)
    errors: list[str] = []

    def start_new_generation() -> None:
        try:
            asyncio.run(executor.start(_replace(old_identity, generation="2")))
        except BaseException as exc:
            errors.append(f"start:{type(exc).__name__}")

    def open_old_attachment() -> None:
        try:
            registry.open(peer, raw_hello)
        except BaseException as exc:
            errors.append(f"open:{type(exc).__name__}")

    start_thread = threading.Thread(target=start_new_generation, daemon=True)
    open_thread = threading.Thread(target=open_old_attachment, daemon=True)
    start_thread.start()
    if not factory_entered.wait(timeout=2):
        result.send({"setup": "start did not reach precommit"})
        return
    open_thread.start()
    if not open_has_supervisor.wait(timeout=2):
        result.send({"setup": "open did not acquire supervisor"})
        return
    release_factory.set()
    nested_map_to_supervisor.wait(timeout=0.5)

    probe_complete = threading.Event()

    def probe_map() -> None:
        executor.encrypted_binding_current(claims)
        probe_complete.set()

    probe_thread = threading.Thread(target=probe_map, daemon=True)
    probe_thread.start()
    map_available = probe_complete.wait(timeout=1)
    if not map_available:
        result.send(
            {
                "map_available": False,
                "nested_map_to_supervisor": nested_map_to_supervisor.is_set(),
            }
        )
        return

    release_open_to_map.set()
    start_thread.join(timeout=2)
    open_thread.join(timeout=2)
    result.send(
        {
            "map_available": True,
            "start_complete": not start_thread.is_alive(),
            "open_complete": not open_thread.is_alive(),
            "generation_2_started": transports.get("2", FakeTransport(old_identity, "")).starts,
            "errors": errors,
        }
    )


def test_start_and_late_old_open_use_supervisor_then_map_lock_order(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_exercise_start_open_lock_order,
        args=(str(tmp_path), sender),
    )
    process.start()
    sender.close()
    try:
        assert receiver.poll(10), "isolated lock-order process did not report"
        observed = receiver.recv()
        assert "setup" not in observed, observed
        assert observed["map_available"], observed
        assert observed["start_complete"], observed
        assert observed["open_complete"], observed
        assert observed["generation_2_started"] == 1, observed
    finally:
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


@pytest.mark.anyio
@pytest.mark.parametrize("agent", list(AgentType))
async def test_cleanup_fault_after_preflight_blocks_next_generation(
    tmp_path: Path, agent: AgentType
) -> None:
    factory_entered, release_factory = threading.Event(), threading.Event()
    executor, old_identity, transports = generation_setup(
        tmp_path,
        agent,
        factory_entered=factory_entered,
        release_factory=release_factory,
    )
    await executor.register_project_binding(binding())
    await executor.start(old_identity)
    claims = attachment(old_identity).claims
    supervisor = executor.encrypted_supervisor(claims)
    peer = RuntimePeer(object(), "1", lambda: True)
    registry = WAWEncryptedRegistry(
        runtime_epoch="1", static_key=lambda: bytes(range(32)), clock=lambda: 0.0
    )
    registry.prepare(
        peer=peer,
        claims=claims,
        supervisor=supervisor,
        current=lambda: executor.encrypted_binding_current(claims),
    )
    await executor.stop(old_identity)
    old_transport: Any = transports["1"]
    old_transport.close_attachment = lambda lease: RuntimeAttachmentCleanupEvidence(lease, False, 1)

    pending = asyncio.create_task(executor.start(_replace(old_identity, generation="2")))
    assert await asyncio.to_thread(factory_entered.wait, 2)
    proof = registry.cleanup(peer, claims)
    assert not proof.confirmed
    assert supervisor.state is SupervisorState.RECONCILIATION_REQUIRED
    release_factory.set()
    with pytest.raises(RuntimeOperationError, match="not positively stopped"):
        await pending
    assert transports["2"].starts == 0
    assert executor.encrypted_supervisor(claims) is supervisor


@pytest.mark.anyio
@pytest.mark.parametrize("drift", ["map", "binding", "inflight"])
async def test_start_final_commit_rejects_map_authority_drift(tmp_path: Path, drift: str) -> None:
    factory_entered, release_factory = threading.Event(), threading.Event()
    executor, old_identity, transports = generation_setup(
        tmp_path,
        AgentType.CODEX,
        factory_entered=factory_entered,
        release_factory=release_factory,
    )
    await executor.register_project_binding(binding())
    await executor.start(old_identity)
    await executor.stop(old_identity)
    pending = asyncio.create_task(executor.start(_replace(old_identity, generation="2")))
    assert await asyncio.to_thread(factory_entered.wait, 2)
    with executor._map_lock:
        if drift == "map":
            old_key = next(
                key
                for key in executor._supervisors
                if key.workspace_id == old_identity.workspace_id
            )
            executor._supervisors.pop(old_key)
        elif drift == "binding":
            _, configured = executor._bindings[PROJECT]
            executor._bindings[PROJECT] = (binding("2"), configured)
        else:
            executor._inflight_tokens[old_identity.workspace_id] = object()
    release_factory.set()
    with pytest.raises(RuntimeOperationError):
        await pending
    assert transports["2"].starts == 0
    assert all(key.generation != "2" for key in executor._supervisors)


async def _cancelled_start_worker_rejects_lost_inflight_reservation(tmp_path: Path) -> None:
    factory_entered, release_factory = threading.Event(), threading.Event()
    executor, old_identity, transports = generation_setup(
        tmp_path,
        AgentType.CLAUDE,
        factory_entered=factory_entered,
        release_factory=release_factory,
    )
    await executor.register_project_binding(binding())
    await executor.start(old_identity)
    await executor.stop(old_identity)
    pending = asyncio.create_task(executor.start(_replace(old_identity, generation="2")))
    assert await asyncio.to_thread(factory_entered.wait, 2)
    with executor._map_lock:
        worker = executor._inflight[old_identity.workspace_id]
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with executor._map_lock:
        executor._inflight_tokens[old_identity.workspace_id] = object()
    release_factory.set()
    _, unfinished = await asyncio.wait({worker}, timeout=2)
    assert not unfinished
    assert isinstance(worker.exception(), RuntimeOperationError)
    assert transports["2"].starts == 0
    assert all(key.generation != "2" for key in executor._supervisors)


def test_cancelled_start_worker_rejects_lost_inflight_reservation(tmp_path: Path) -> None:
    asyncio.run(_cancelled_start_worker_rejects_lost_inflight_reservation(tmp_path))


def reqs(identity: WAWLifecycleIdentity) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = {
        "protocol_version": 1,
        "workspace_id": identity.workspace_id,
        "project_id": PROJECT,
        "agent_type": identity.agent_type,
        "generation": identity.generation,
        "binding_revision": "1",
        "binding_digest": DIGEST,
        "runtime_host_installation_id": HOST,
        "runtime_host_installation_revision": "1",
    }
    return (
        {
            "protocol_version": 1,
            "request_id": "wreq_" + "1" * 32,
            "action": "workspace.api_authority.bind",
            "api_authority_epoch": "1",
            "authority_nonce": "b" * 32,
        },
        {
            "protocol_version": 1,
            "request_id": "wreq_" + "2" * 32,
            "action": "workspace.project_binding.register",
            "project_id": PROJECT,
            "relative_key": "project-a",
            "project_revision": "1",
            "binding_revision": "1",
            "previous_binding_revision": None,
            "previous_binding_digest": None,
            "schema_version": "waw-project-binding-v1",
            "runtime_host_installation_id": HOST,
            "runtime_host_installation_revision": "1",
        },
        {**base, "request_id": "wreq_" + "3" * 32, "action": "workspace.workspace.start"},
    )


@pytest.mark.anyio
@pytest.mark.parametrize("agent", list(AgentType))
async def test_registry_bridge_and_exact_stop_for_both_agents(
    tmp_path: Path, agent: AgentType
) -> None:
    executor, identity, transport, _ = setup(tmp_path, agent)
    registry = WAWLifecycleRegistry(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision="1",
        host_manifest_digest="c" * 64,
        project_root_manifest_digest="d" * 64,
        executor=executor,
        binding_digest_factory=lambda _: DIGEST,
    )
    bind, register, start = reqs(identity)
    assert (await registry.dispatch(bind))["status"] == "BOUND"
    assert (await registry.dispatch(register))["status"] == "REGISTERED"
    assert (await registry.dispatch(start))["status"] == "STARTED"
    status = {**start, "request_id": "wreq_" + "4" * 32, "action": "workspace.workspace.status"}
    assert (await registry.dispatch(status))["state"] == "RUNNING"
    prepare = {
        **start,
        "request_id": "wreq_" + "5" * 32,
        "action": "workspace.attach.prepare",
        "attachment_id": "att_" + "1" * 32,
        "mode": "writer",
        "lease_number": "1",
        "auth_epoch": "1",
        "api_authority_epoch": "1",
        "runtime_epoch": "1",
        "resume_cursor": None,
        "previous_runtime_epoch": None,
    }
    assert (await registry.dispatch(prepare))["status"] == "PREPARED"
    bridge = executor.bridge(identity, attachment(identity))
    bridge.attach()
    bridge.handle(ABWSFrame(FrameType.INPUT, 1, b"hello"))
    assert transport.writes == [b"hello"]
    bridge.handle(
        ABWSFrame(FrameType.RESIZE, 2, b"", {"protocol_version": 1, "columns": 100, "rows": 30})
    )
    bridge.handle(ABWSFrame(FrameType.DETACH, 3, b"", {"protocol_version": 1}))
    fresh = executor.bridge(identity, attachment(identity, 2))
    fresh.attach()
    fresh.handle(ABWSFrame(FrameType.INPUT, 1, b"again"))
    fresh.handle(ABWSFrame(FrameType.CLOSE, 2, b"", {"protocol_version": 1}))
    assert transport.detaches == 2
    stopped = await registry.dispatch(
        {**start, "request_id": "wreq_" + "6" * 32, "action": "workspace.workspace.stop"}
    )
    assert stopped["state"] == "STOPPED" and transport.stops == 1


@pytest.mark.anyio
@pytest.mark.parametrize("agent", list(AgentType))
async def test_duplicate_start_is_fenced(tmp_path: Path, agent: AgentType) -> None:
    executor, identity, transport, _ = setup(tmp_path, agent)
    await executor.register_project_binding(binding())
    await executor.start(identity)
    with pytest.raises(RuntimeOperationError):
        await executor.start(identity)
    assert transport.starts == 1


@pytest.mark.anyio
async def test_binding_is_required_and_live_rebind_is_fenced(tmp_path: Path) -> None:
    executor, identity, _transport, _ = setup(tmp_path, AgentType.CODEX)
    with pytest.raises(RuntimeOperationError):
        await executor.start(identity)
    await executor.register_project_binding(binding())
    await executor.start(identity)
    with pytest.raises(RuntimeOperationError):
        await executor.register_project_binding(binding("2"))
    with pytest.raises(RuntimeOperationError):
        await executor.register_project_binding(binding("3", "missing-project"))


@pytest.mark.anyio
async def test_runtime_epoch_fences_attachment_context(tmp_path: Path) -> None:
    executor, identity, _transport, _ = setup(tmp_path, AgentType.CLAUDE, epoch="7")
    await executor.register_project_binding(binding())
    await executor.start(identity)
    bridge = executor.bridge(identity, attachment(identity, epoch="1"))
    with pytest.raises(RuntimeOperationError):
        bridge.attach()
    valid = executor.bridge(identity, attachment(identity, 2, epoch="7"))
    valid.attach()


@pytest.mark.anyio
async def test_cancelled_binding_resolution_keeps_reservation_until_worker_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor, identity, _transport, root = setup(tmp_path, AgentType.CODEX)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    original = executor._resolve_binding

    def blocked(item: WAWProjectBinding) -> Any:
        entered.set()
        try:
            release.wait(timeout=5)
            return original(item)
        finally:
            finished.set()

    monkeypatch.setattr(executor, "_resolve_binding", blocked)
    pending = asyncio.create_task(executor.register_project_binding(binding()))
    try:
        await asyncio.to_thread(entered.wait, 2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        with pytest.raises(RuntimeOperationError):
            await executor.register_project_binding(binding())
        with pytest.raises(RuntimeOperationError):
            await executor.start(identity)
    finally:
        release.set()
    await asyncio.wait_for(asyncio.to_thread(finished.wait, 2), timeout=3)
    for _ in range(20):
        try:
            await executor.register_project_binding(binding())
            break
        except RuntimeOperationError:
            await asyncio.sleep(0)
    else:
        pytest.fail("cancelled binding reservation did not clear")
    assert (root / "project-a").is_dir()


@pytest.mark.anyio
async def test_registered_project_path_drift_is_rejected(tmp_path: Path) -> None:
    executor, identity, _transport, root = setup(tmp_path, AgentType.CLAUDE)
    await executor.register_project_binding(binding())
    (root / "project-a").rename(root / "project-moved")
    with pytest.raises(RuntimeOperationError):
        await executor.start(identity)


@pytest.mark.anyio
async def test_input_uncertain_is_not_cleared_by_probe_and_output_stays_fenced(
    tmp_path: Path,
) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CODEX)
    await executor.register_project_binding(binding())
    await executor.start(identity)
    stream = executor.bridge(identity, attachment(identity))
    stream.attach()
    transport.fail_write = True
    with pytest.raises(RuntimeOperationError, match="could not confirm"):
        stream.handle(ABWSFrame(FrameType.INPUT, 1, b"uncertain"))
    transport.fail_write = False
    with pytest.raises(RuntimeOperationError):
        stream.handle(ABWSFrame(FrameType.INPUT, 2, b"must-reconcile"))
    with pytest.raises(RuntimeOperationError):
        stream.output(0)
    assert (await executor.status(identity)).state == "RUNNING"


@pytest.mark.anyio
async def test_failed_start_retains_exact_supervisor_for_cleanup(tmp_path: Path) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CODEX)
    await executor.register_project_binding(binding())
    transport.ready = False
    with pytest.raises(RuntimeOperationError):
        await executor.start(identity)
    assert transport.starts == 1
    # The failed generation remains registered and can only be removed by the
    # same exact stop binding; a retry cannot silently spawn a second process.
    with pytest.raises(RuntimeOperationError):
        await executor.start(identity)
    stopped = await executor.stop(identity)
    assert stopped.state == "STOPPED" and transport.stops == 1


@pytest.mark.anyio
async def test_cancelled_start_keeps_inflight_fence(tmp_path: Path) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CLAUDE)
    await executor.register_project_binding(binding())
    gate = threading.Event()
    transport.start_gate = gate
    task = asyncio.create_task(executor.start(identity))
    for _ in range(100):
        if transport.starts:
            break
        await asyncio.sleep(0.001)
    assert transport.starts == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(RuntimeOperationError, match="already in progress"):
        await executor.start(_replace(identity, generation="2"))
    gate.set()
    # The worker is allowed to finish after caller cancellation, preserving the
    # supervisor map and preventing overlapping transport effects.
    await asyncio.sleep(0.05)
    assert transport.starts == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "state", [RuntimeProbeState.MISSING, RuntimeProbeState.COLLISION, RuntimeProbeState.UNKNOWN]
)
async def test_probe_mapping_is_fail_closed(tmp_path: Path, state: RuntimeProbeState) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CODEX)
    await executor.register_project_binding(binding())
    await executor.start(identity)
    transport.probe_state = state
    result = await executor.status(identity)
    assert (
        result.reconciliation_state
        == {
            RuntimeProbeState.MISSING: "missing",
            RuntimeProbeState.COLLISION: "collision",
            RuntimeProbeState.UNKNOWN: "unknown",
        }[state]
    )
    assert executor.bridge(identity, attachment(identity)).snapshot().state.value == "DETACHED"


@pytest.mark.anyio
async def test_cross_generation_binding_and_host_fail_closed(tmp_path: Path) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CLAUDE)
    await executor.register_project_binding(binding())
    await executor.start(identity)
    bad = [
        _replace(identity, generation="2"),
        _replace(identity, binding_revision="2"),
        _replace(identity, binding_digest="b" * 64),
        _replace(identity, runtime_host_installation_revision="2"),
    ]
    for item in bad:
        with pytest.raises(RuntimeOperationError):
            await executor.status(item)
    assert transport.starts == 1


@pytest.mark.anyio
async def test_same_generation_resume_after_login_uses_existing_supervisor_cas(
    tmp_path: Path,
) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CODEX, epoch="2")
    await executor.register_project_binding(binding())
    original_start = transport.start

    def login_required(command: Any, geometry: PtyGeometry) -> RuntimeStartEvidence:
        started = original_start(command, geometry)
        return replace(started, state=SupervisorState.LOGIN_REQUIRED)

    transport.start = login_required  # type: ignore[method-assign]
    resume_calls: list[WAWPublicAuthEvidence] = []

    def resume(evidence: WAWPublicAuthEvidence) -> RuntimeStartEvidence:
        resume_calls.append(evidence)
        return RuntimeStartEvidence(
            identity.workspace_id,
            int(identity.generation),
            transport.marker,
            SupervisorState.RUNNING,
            True,
        )

    transport.resume_after_login = resume  # type: ignore[attr-defined]
    started = await executor.start(identity)
    assert started.state == "LOGIN_REQUIRED"
    evidence = WAWPublicAuthEvidence(
        AgentType.CODEX,
        HOST,
        "1",
        "c" * 64,
        0.0,
        WAWPublicAuthResult.AUTHENTICATED,
    )
    resumed = await executor.resume_after_login(identity, evidence)
    assert resumed.state == "RUNNING"
    assert resume_calls == [evidence]
    assert transport.starts == 1
    with pytest.raises(RuntimeOperationError, match="not waiting"):
        await executor.resume_after_login(identity, evidence)


@pytest.mark.anyio
async def test_concurrent_login_resume_is_fenced_by_workspace_operation_slot(
    tmp_path: Path,
) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CLAUDE, epoch="2")
    await executor.register_project_binding(binding())
    original_start = transport.start

    def login_required(command: Any, geometry: PtyGeometry) -> RuntimeStartEvidence:
        return replace(original_start(command, geometry), state=SupervisorState.LOGIN_REQUIRED)

    transport.start = login_required  # type: ignore[method-assign]
    entered = threading.Event()
    release = threading.Event()

    def resume(_evidence: WAWPublicAuthEvidence) -> RuntimeStartEvidence:
        entered.set()
        release.wait(timeout=5)
        return RuntimeStartEvidence(
            identity.workspace_id,
            1,
            transport.marker,
            SupervisorState.RUNNING,
            True,
        )

    transport.resume_after_login = resume  # type: ignore[attr-defined]
    await executor.start(identity)
    evidence = WAWPublicAuthEvidence(
        AgentType.CLAUDE,
        HOST,
        "1",
        "c" * 64,
        0.0,
        WAWPublicAuthResult.AUTHENTICATED,
    )
    pending = asyncio.create_task(executor.resume_after_login(identity, evidence))
    assert await asyncio.to_thread(entered.wait, 2)
    with pytest.raises(RuntimeOperationError, match="already in progress"):
        await executor.resume_after_login(identity, evidence)
    release.set()
    assert (await pending).state == "RUNNING"


def _replace(identity: WAWLifecycleIdentity, **changes: str) -> WAWLifecycleIdentity:
    values = identity.__dict__ | changes
    return WAWLifecycleIdentity(**values)


@dataclass
class _ConflictProbe:
    claude: WAWLegacyClaudeState = WAWLegacyClaudeState.ABSENT
    codex: WAWLegacyCodexState = WAWLegacyCodexState.ABSENT
    project_waw: tuple[WAWManagedConflictState, ...] = ()
    calls: list[str] = field(default_factory=list)

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        assert project_id == PROJECT
        self.calls.append("claude")
        return self.claude

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        self.calls.append("codex")
        return self.codex

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        assert project_id == PROJECT
        return self.project_waw

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        return self.project_waw


@pytest.mark.anyio
async def test_executor_conflict_check_preserves_claude_precedence(tmp_path: Path) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CODEX)
    await executor.register_project_binding(binding())
    probe = _ConflictProbe(
        claude=WAWLegacyClaudeState.RUNNING,
        codex=WAWLegacyCodexState.RUNNING,
    )
    executor._conflicts = WAWConflictCoordinator(probe)
    with pytest.raises(RuntimeOperationError) as raised:
        await executor.start(identity)
    assert raised.value.code == "PROJECT_RUNTIME_ACTIVE"
    assert probe.calls == ["claude"]
    assert transport.starts == 0


@pytest.mark.anyio
async def test_executor_holds_shared_host_lease_through_transport_start_and_readback(
    tmp_path: Path,
) -> None:
    executor, identity, transport, _ = setup(tmp_path, AgentType.CLAUDE)
    await executor.register_project_binding(binding())
    probe = _ConflictProbe(project_waw=(WAWManagedConflictState.RUNNING,))
    executor._conflicts = WAWConflictCoordinator(probe)
    legacy = WAWConflictCoordinator(probe)
    gate = threading.Event()
    transport.start_gate = gate
    pending = asyncio.create_task(executor.start(identity))
    for _ in range(100):
        if transport.starts:
            break
        await asyncio.sleep(0.001)
    assert transport.starts == 1
    finished = threading.Event()
    outcomes: list[str] = []

    def racing_legacy() -> None:
        try:
            legacy.acquire_legacy_claude_start(project_id=PROJECT).release()
            outcomes.append("allowed")
        except WAWConflictError as exc:
            outcomes.append(exc.code)
        finished.set()

    thread = threading.Thread(target=racing_legacy)
    thread.start()
    assert not finished.wait(timeout=0.05)
    gate.set()
    assert (await pending).state == "RUNNING"
    assert finished.wait(timeout=1)
    thread.join(timeout=1)
    assert outcomes == ["PROJECT_RUNTIME_ACTIVE"]


@pytest.mark.anyio
async def test_cancelled_background_conflict_acquire_releases_late_lease(
    tmp_path: Path,
) -> None:
    executor, identity, _transport, _ = setup(tmp_path, AgentType.CLAUDE)
    probe = _ConflictProbe()
    coordinator = WAWConflictCoordinator(probe)
    executor._conflicts = coordinator
    blocking = WAWConflictCoordinator(probe).acquire_legacy_codex_start()
    pending = asyncio.create_task(executor._acquire_conflict_lease_async(executor._key(identity)))
    await asyncio.sleep(0.02)
    pending.cancel()
    blocking.release()
    with pytest.raises(asyncio.CancelledError):
        await pending
    # If the cancelled background thread leaked its eventual WAW lease, this
    # independent coordinator would block forever on the module host lock.
    acquired = await asyncio.wait_for(
        asyncio.to_thread(WAWConflictCoordinator(probe).acquire_legacy_codex_start),
        timeout=1,
    )
    acquired.release()


class _RestartNativePort:
    def start(self, request: FixedLaunchRequest) -> FixedStartProof:
        raise AssertionError("restart quarantine must not start or adopt")

    def open_attachment(self, _request: Any) -> Any:
        raise AssertionError("restart quarantine must not attach")

    def probe(self, _binding: FixedProcessBinding) -> RuntimeProbeEvidence:
        raise AssertionError("restart quarantine must not probe or adopt")

    def stop(self, _binding: FixedProcessBinding) -> RuntimeStopEvidence:
        raise AssertionError("restart quarantine must use destroy_fenced")

    def destroy_fenced(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        item = binding.identity
        return RuntimeStopEvidence(item.workspace_id, item.generation, item.managed_marker, True, 0)


class _AuthNativePort(_RestartNativePort):
    def __init__(self) -> None:
        self.starts = 0

    def start(self, request: FixedLaunchRequest) -> FixedStartProof:
        self.starts += 1
        return FixedStartProof(
            request,
            FixedStartState.RUNNING,
            FixedProcessBinding(request.identity, object(), object(), object()),
            1,
        )

    def probe(self, binding: FixedProcessBinding) -> RuntimeProbeEvidence:
        item = binding.identity
        return RuntimeProbeEvidence(
            item.workspace_id, item.generation, item.managed_marker, RuntimeProbeState.RUNNING
        )

    def stop(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        item = binding.identity
        return RuntimeStopEvidence(item.workspace_id, item.generation, item.managed_marker, True, 0)


class _AuthProbe:
    def __init__(self, result: WAWPublicAuthResult) -> None:
        self.result = result
        self.calls: list[tuple[AgentType, str, str, str, float]] = []

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        self.calls.append(
            (
                agent_type,
                runtime_host_installation_id,
                runtime_host_installation_revision,
                executable_fingerprint,
                checked_at_monotonic,
            )
        )
        return WAWPublicAuthEvidence(
            agent_type,
            runtime_host_installation_id,
            runtime_host_installation_revision,
            executable_fingerprint,
            checked_at_monotonic,
            self.result,
        )


class _BlockingAuthProbe(_AuthProbe):
    def __init__(self) -> None:
        super().__init__(WAWPublicAuthResult.AUTHENTICATED)
        self.entered = threading.Event()
        self.release = threading.Event()

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        self.entered.set()
        assert await asyncio.to_thread(self.release.wait, 5)
        return await super().probe(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )


def _install_fixed_auth_transport(
    executor: WAWSupervisorExecutor,
    lifecycle: WAWLifecycleIdentity,
    probe: _AuthProbe,
) -> _AuthNativePort:
    native = _AuthNativePort()

    def fixed_factory(_identity: WAWLifecycleIdentity, command: Any) -> WAWFixedTransport:
        item = FixedProcessIdentity(
            lifecycle.workspace_id,
            lifecycle.project_id,
            AgentType(lifecycle.agent_type),
            int(lifecycle.generation),
            "d" * 64,
            command.managed_marker,
            "b" * 64,
            lifecycle.runtime_host_installation_id,
            lifecycle.runtime_host_installation_revision,
            "2",
        )
        return WAWFixedTransport.development_only(
            identity=item,
            handles=FixedLaunchHandles(
                project_directory=object(),
                selected_home_directory=object(),
                temp_directory=object(),
                bridge_executable=object(),
                vendor_executable=object(),
                policy_directory=object(),
                wbr_endpoint=object(),
                cgroup=object(),
            ),
            executable_fingerprint="c" * 64,
            port=native,
            clock=lambda: 0.0,
        )

    executor._transport_factory = fixed_factory
    executor._auth_probe = probe
    executor._conflicts = WAWConflictCoordinator(_ConflictProbe())
    return native


@pytest.mark.anyio
async def test_restart_quarantine_returns_unknown_without_adopt_then_exact_destroy(
    tmp_path: Path,
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CODEX, epoch="2")
    item = FixedProcessIdentity(
        lifecycle.workspace_id,
        lifecycle.project_id,
        AgentType.CODEX,
        1,
        "d" * 64,
        managed_marker(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision=1,
            project_id=PROJECT,
            agent_type=AgentType.CODEX,
            workspace_id_value=lifecycle.workspace_id,
            generation=1,
            binding_revision=1,
            binding_digest=DIGEST,
        ),
        "b" * 64,
        HOST,
        "1",
        "2",
    )
    port = _RestartNativePort()
    fixed = WAWFixedTransport.development_only(
        identity=item,
        handles=FixedLaunchHandles(
            project_directory=object(),
            selected_home_directory=object(),
            temp_directory=object(),
            bridge_executable=object(),
            vendor_executable=object(),
            policy_directory=object(),
            wbr_endpoint=object(),
            cgroup=object(),
        ),
        executable_fingerprint="c" * 64,
        port=port,
        clock=lambda: 0.0,
    )
    old = replace(item, runtime_epoch="1")
    old_binding = FixedProcessBinding(old, object(), object(), object())
    executor.register_restart_quarantine(lifecycle, fixed, old_binding)
    observed = await executor.status(lifecycle)
    assert observed.state == "UNKNOWN"
    assert observed.reconciliation_state == "reconciliation_required"
    with pytest.raises(RuntimeOperationError, match="restart quarantine"):
        await executor.start(lifecycle)
    destroyed = await executor.destroy_fenced(lifecycle)
    assert destroyed.state == "STOPPED"


@pytest.mark.anyio
async def test_fresh_auth_gate_spawns_only_authenticated_and_resumes_same_generation(
    tmp_path: Path,
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CODEX, epoch="2")
    await executor.register_project_binding(binding())
    probe = _AuthProbe(WAWPublicAuthResult.UNAUTHENTICATED)
    native = _install_fixed_auth_transport(executor, lifecycle, probe)
    login = await executor.start(lifecycle)
    assert login.state == "LOGIN_REQUIRED" and login.process_state == "NOT_STARTED"
    assert native.starts == 0
    probe.result = WAWPublicAuthResult.AUTHENTICATED
    resumed = await executor.resume_after_login(lifecycle)
    assert resumed.state == "RUNNING" and resumed.process_state == "RUNNING"
    assert native.starts == 1
    assert [call[3] for call in probe.calls] == ["c" * 64, "c" * 64]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "code"),
    [
        (WAWPublicAuthResult.UNKNOWN, "WAW_AUTH_UNKNOWN"),
        (WAWPublicAuthResult.UNSUPPORTED, "WAW_PROFILE_UNSUPPORTED"),
    ],
)
async def test_unknown_or_unsupported_auth_fails_before_process_and_map_commit(
    tmp_path: Path, result: WAWPublicAuthResult, code: str
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CLAUDE, epoch="2")
    await executor.register_project_binding(binding())
    probe = _AuthProbe(result)
    native = _install_fixed_auth_transport(executor, lifecycle, probe)
    with pytest.raises(RuntimeOperationError) as raised:
        await executor.start(lifecycle)
    assert raised.value.code == code
    assert native.starts == 0
    with pytest.raises(RuntimeOperationError):
        executor.encrypted_supervisor(attachment(lifecycle).claims)


@pytest.mark.anyio
async def test_repeated_auth_failure_or_cancellation_aborts_every_unstarted_fd(
    tmp_path: Path,
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CODEX, epoch="2")
    await executor.register_project_binding(binding())
    native = _AuthNativePort()
    opened: list[tuple[tuple[int, ...], tuple[int, ...]]] = []

    def fixed_factory(_identity: WAWLifecycleIdentity, command: Any) -> WAWFixedTransport:
        pipes = tuple(os.pipe() for _ in range(4))
        reads = tuple(pair[0] for pair in pipes)
        writes = tuple(pair[1] for pair in pipes)
        opened.append((reads, writes))
        item = FixedProcessIdentity(
            lifecycle.workspace_id,
            lifecycle.project_id,
            AgentType.CODEX,
            1,
            "d" * 64,
            command.managed_marker,
            "b" * 64,
            HOST,
            "1",
            "2",
        )
        return WAWFixedTransport.development_only(
            identity=item,
            handles=FixedLaunchHandles(
                project_directory=reads[0],
                selected_home_directory=reads[1],
                temp_directory=reads[2],
                bridge_executable=object(),
                vendor_executable=object(),
                policy_directory=reads[3],
                wbr_endpoint=object(),
                cgroup=object(),
            ),
            executable_fingerprint="c" * 64,
            port=native,
            clock=lambda: 0.0,
        )

    class CyclingProbe(_AuthProbe):
        async def probe(
            self,
            *,
            agent_type: AgentType,
            runtime_host_installation_id: str,
            runtime_host_installation_revision: str,
            executable_fingerprint: str,
            checked_at_monotonic: float,
        ) -> WAWPublicAuthEvidence:
            index = len(opened) - 1
            if index % 3 == 2:
                raise asyncio.CancelledError
            self.result = (
                WAWPublicAuthResult.UNKNOWN if index % 3 == 0 else WAWPublicAuthResult.UNSUPPORTED
            )
            return await super().probe(
                agent_type=agent_type,
                runtime_host_installation_id=runtime_host_installation_id,
                runtime_host_installation_revision=runtime_host_installation_revision,
                executable_fingerprint=executable_fingerprint,
                checked_at_monotonic=checked_at_monotonic,
            )

    executor._transport_factory = fixed_factory
    executor._auth_probe = CyclingProbe(WAWPublicAuthResult.UNKNOWN)
    executor._conflicts = WAWConflictCoordinator(_ConflictProbe())
    for index in range(100):
        expected = asyncio.CancelledError if index % 3 == 2 else RuntimeOperationError
        with pytest.raises(expected):
            await executor.start(lifecycle)
        reads, writes = opened[-1]
        for descriptor in reads:
            with pytest.raises(OSError):
                os.fstat(descriptor)
        for descriptor in writes:
            os.close(descriptor)
    assert native.starts == 0


@pytest.mark.anyio
async def test_stale_valid_marker_aborts_transport_construction_ownership(
    tmp_path: Path,
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CODEX, epoch="2")
    await executor.register_project_binding(binding())
    original_factory = executor._command_factory
    stale_marker = managed_marker(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        project_id=PROJECT,
        agent_type=AgentType.CODEX,
        workspace_id_value=lifecycle.workspace_id,
        generation=2,
        binding_revision=1,
        binding_digest=DIGEST,
    )

    def stale_command(item: WAWLifecycleIdentity, configured: Any) -> WAWCodexCommand:
        command = original_factory(item, configured)
        assert type(command) is WAWCodexCommand
        return replace(command, managed_marker=stale_marker)

    baseline = len(os.listdir("/dev/fd"))
    owned: list[int] = []
    write_ends: list[int] = []
    constructed: list[tuple[WAWFixedTransport, LinuxCgroupControlHandle]] = []
    native = _AuthNativePort()

    def fixed_factory(_identity: WAWLifecycleIdentity, command: Any) -> WAWFixedTransport:
        pipes = tuple(os.pipe() for _ in range(4))
        owned.extend(pair[0] for pair in pipes)
        write_ends.extend(pair[1] for pair in pipes)
        endpoint_source, endpoint_controller = socket.socketpair()
        endpoint = object.__new__(NativeWBREndpoint)
        object.__setattr__(endpoint, "native", endpoint_source)
        object.__setattr__(endpoint, "controller", endpoint_controller)
        cgroup_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        owned.extend((endpoint_source.fileno(), endpoint_controller.fileno(), cgroup_fd))
        identity = FixedProcessIdentity(
            lifecycle.workspace_id,
            lifecycle.project_id,
            AgentType.CODEX,
            1,
            "d" * 64,
            command.managed_marker,
            "b" * 64,
            HOST,
            "1",
            "2",
        )
        cgroup = object.__new__(LinuxCgroupControlHandle)
        cgroup._descriptor = cgroup_fd
        cgroup._authority = cast(Any, object())
        cgroup._identity = identity
        cgroup._closed = False
        cgroup._consumed = False
        cgroup._lock = threading.RLock()
        transport = WAWFixedTransport.development_only(
            identity=identity,
            handles=FixedLaunchHandles(
                project_directory=pipes[0][0],
                selected_home_directory=pipes[1][0],
                temp_directory=pipes[2][0],
                bridge_executable=object(),
                vendor_executable=object(),
                policy_directory=pipes[3][0],
                wbr_endpoint=endpoint,
                cgroup=cgroup,
            ),
            executable_fingerprint="c" * 64,
            port=native,
            clock=lambda: 0.0,
        )
        constructed.append((transport, cgroup))
        return transport

    executor._command_factory = stale_command
    executor._transport_factory = fixed_factory
    try:
        with pytest.raises(RuntimeOperationError) as raised:
            await executor.start(lifecycle)
        assert raised.value.code == "WAW_BINDING_MISMATCH"
        transport, cgroup = constructed[0]
        assert transport._aborted_unstarted and transport._closed
        assert cgroup._closed and not cgroup.consumed
        assert native.starts == 0
        for descriptor in owned:
            with pytest.raises(OSError):
                os.fstat(descriptor)
    finally:
        for descriptor in write_ends:
            os.close(descriptor)
    assert len(os.listdir("/dev/fd")) == baseline


@pytest.mark.anyio
async def test_auth_probe_await_holds_shared_conflict_lease_until_start_readback(
    tmp_path: Path,
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CODEX, epoch="2")
    await executor.register_project_binding(binding())
    auth = _BlockingAuthProbe()
    _install_fixed_auth_transport(executor, lifecycle, auth)
    conflicts = _ConflictProbe(project_waw=(WAWManagedConflictState.RUNNING,))
    executor._conflicts = WAWConflictCoordinator(conflicts)
    legacy = WAWConflictCoordinator(conflicts)
    pending = asyncio.create_task(executor.start(lifecycle))
    assert await asyncio.to_thread(auth.entered.wait, 2)
    finished = threading.Event()
    outcomes: list[str] = []

    def legacy_start() -> None:
        try:
            legacy.acquire_legacy_claude_start(project_id=PROJECT).release()
            outcomes.append("allowed")
        except WAWConflictError as exc:
            outcomes.append(exc.code)
        finished.set()

    thread = threading.Thread(target=legacy_start)
    thread.start()
    assert not finished.wait(0.05)
    auth.release.set()
    assert (await pending).state == "RUNNING"
    assert finished.wait(1)
    thread.join(timeout=1)
    assert outcomes == ["PROJECT_RUNTIME_ACTIVE"]


def _mark_conflict_acquire(executor: WAWSupervisorExecutor) -> threading.Event:
    entered = threading.Event()
    original = executor._acquire_conflict_lease

    def marked(key: Any) -> Any:
        entered.set()
        return original(key)

    executor._acquire_conflict_lease = marked  # type: ignore[method-assign]
    return entered


@pytest.mark.anyio
async def test_cancelled_auth_start_lock_wait_releases_eventual_host_lease(
    tmp_path: Path,
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CODEX, epoch="2")
    await executor.register_project_binding(binding())
    auth = _AuthProbe(WAWPublicAuthResult.AUTHENTICATED)
    _install_fixed_auth_transport(executor, lifecycle, auth)
    holder = WAWConflictCoordinator(_ConflictProbe()).acquire_legacy_codex_start()
    entered = _mark_conflict_acquire(executor)
    pending = asyncio.create_task(executor.start(lifecycle))
    assert await asyncio.to_thread(entered.wait, 2)
    internal = executor._inflight[lifecycle.workspace_id]
    internal.cancel()
    await asyncio.sleep(0.02)
    assert not internal.done()
    holder.release()

    with pytest.raises(asyncio.CancelledError):
        await pending
    assert (await executor.start(lifecycle)).state == "RUNNING"


@pytest.mark.anyio
async def test_cancelled_auth_resume_lock_wait_releases_eventual_host_lease(
    tmp_path: Path,
) -> None:
    executor, lifecycle, _transport, _ = setup(tmp_path, AgentType.CLAUDE, epoch="2")
    await executor.register_project_binding(binding())
    auth = _AuthProbe(WAWPublicAuthResult.UNAUTHENTICATED)
    _install_fixed_auth_transport(executor, lifecycle, auth)
    assert (await executor.start(lifecycle)).state == "LOGIN_REQUIRED"
    auth.result = WAWPublicAuthResult.AUTHENTICATED
    holder = WAWConflictCoordinator(_ConflictProbe()).acquire_legacy_codex_start()
    entered = _mark_conflict_acquire(executor)
    pending = asyncio.create_task(executor.resume_after_login(lifecycle))
    assert await asyncio.to_thread(entered.wait, 2)
    internal = executor._inflight[lifecycle.workspace_id]
    internal.cancel()
    await asyncio.sleep(0.02)
    assert not internal.done()
    holder.release()

    with pytest.raises(asyncio.CancelledError):
        await pending
    assert (await executor.resume_after_login(lifecycle)).state == "RUNNING"


@pytest.mark.anyio
async def test_legacy_project_mapper_requires_one_current_unambiguous_binding(
    tmp_path: Path,
) -> None:
    executor, _identity, _transport, _ = setup(tmp_path, AgentType.CLAUDE)
    await executor.register_project_binding(binding())
    assert executor.formal_project_id_for_legacy("project-a") == PROJECT
    assert executor.formal_project_id_for_legacy("../project-a") is None

    current = executor._bindings.pop(PROJECT)
    assert executor.formal_project_id_for_legacy("project-a") is None
    executor._bindings[PROJECT] = current
    other = "prj_" + "9" * 32
    executor._bindings[other] = (replace(current[0], project_id=other), current[1])
    assert executor.formal_project_id_for_legacy("project-a") is None
    executor._bindings.pop(other)

    executor._binding_reserved.add(PROJECT)
    assert executor.formal_project_id_for_legacy("project-a") is None
    executor._binding_reserved.clear()
    executor._inflight_project_ids["other-workspace"] = PROJECT
    assert executor.formal_project_id_for_legacy("project-a") is None
