"""Synthetic composition coverage for the typed Runtime WAW executor."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_core.waw_tickets import (
    ActiveAttachment,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
)
from agentbox_protocol.abws import ABWSFrame, FrameType
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import inspect_executable
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleIdentity,
    WAWLifecycleRegistry,
    WAWProjectBinding,
)
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.waw_supervisor import (
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

    def detach(self) -> bool:
        self.detaches += 1
        return True

    def stop(self) -> RuntimeStopEvidence:
        self.stops += 1
        return RuntimeStopEvidence(
            self.identity.workspace_id, int(self.identity.generation), self.marker, True, 0
        )

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


def binding(revision: str = "1", relative_key: str = "project-a") -> WAWProjectBinding:
    return WAWProjectBinding(PROJECT, relative_key, "1", revision, DIGEST, HOST, "1")


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


def _replace(identity: WAWLifecycleIdentity, **changes: str) -> WAWLifecycleIdentity:
    values = identity.__dict__ | changes
    return WAWLifecycleIdentity(**values)
