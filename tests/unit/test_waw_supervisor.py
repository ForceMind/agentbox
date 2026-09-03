from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, WorkspaceStopOperation, managed_marker, workspace_id
from agentbox_core.waw_tickets import (
    ActiveAttachment,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
)
from agentbox_protocol.abws import FrameType, decode_frame, encode_frame
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_managed_command import WAWManagedCommand, validate_managed_command
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_stream_bridge import WAWStreamBridge, WAWStreamState
from agentbox_runtime.waw_supervisor import (
    RuntimeProbeEvidence,
    RuntimeProbeState,
    RuntimeStartEvidence,
    RuntimeStopEvidence,
    SupervisorState,
    WAWSupervisor,
)


class FakeTransport:
    def __init__(self) -> None:
        self.started = False
        self.commands: list[WAWManagedCommand] = []
        self.writes: list[bytes] = []
        self.resizes: list[PtyGeometry] = []
        self.stopped = False
        self.fail_writes = False
        self.detach_confirmed = True
        self.stop_closed = True
        self.workspace_id = ""
        self.generation = 1
        self.marker = ""

    def start(self, command: WAWManagedCommand, geometry: PtyGeometry) -> RuntimeStartEvidence:
        assert command.argv == (("remote-control",) if type(command) is WAWClaudeCommand else ())
        self.commands.append(command)
        self.started = True
        self.resizes.append(geometry)
        self.workspace_id = command.workspace_id
        self.marker = command.managed_marker
        return RuntimeStartEvidence(
            command.workspace_id,
            1,
            command.managed_marker,
            SupervisorState.RUNNING,
            True,
        )

    def write(self, data: bytes) -> None:
        if self.fail_writes:
            raise OSError("pty closed")
        self.writes.append(data)

    def detach(self) -> bool:
        return self.detach_confirmed

    def resize(self, geometry: PtyGeometry) -> None:
        self.resizes.append(geometry)

    def stop(self) -> RuntimeStopEvidence:
        self.stopped = True
        return RuntimeStopEvidence(
            self.workspace_id,
            self.generation,
            self.marker,
            self.stop_closed,
            0 if self.stop_closed else 1,
        )

    def probe(self) -> RuntimeProbeEvidence:
        return RuntimeProbeEvidence(
            self.workspace_id,
            self.generation,
            self.marker,
            RuntimeProbeState.STOPPED if self.stopped else RuntimeProbeState.RUNNING,
        )


def _attachment(workspace: str, *, attachment_id: str = "att_" + "2" * 32) -> ActiveAttachment:
    claims = AttachmentTuple(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        agent_type=(
            AgentType.CODEX
            if workspace == workspace_id("prj_" + "1" * 32, AgentType.CODEX)
            else AgentType.CLAUDE
        ),
        attachment_id=attachment_id,
        lease_number=1,
        generation=1,
        auth_epoch=1,
        api_authority_epoch=1,
        runtime_host_installation_id="wri_" + "3" * 32,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="a" * 64,
    )
    return ActiveAttachment(
        claims,
        0.0,
        0.0,
        100.0,
        200.0,
        AuthenticatedAttachmentContext("ses_1", "usr_1", "waw", "https://agentbox", "1", 1),
    )


def _supervisor(
    tmp_path: Path, *, runtime_epoch: str = "1", agent_type: AgentType = AgentType.CLAUDE
) -> tuple[WAWSupervisor, FakeTransport, str]:
    workspace = workspace_id("prj_" + "1" * 32, agent_type)
    stop_binding = WorkspaceStopOperation(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        agent_type=agent_type,
        generation=1,
        binding_revision=1,
        binding_digest="a" * 64,
        runtime_host_installation_id="wri_" + "3" * 32,
        runtime_host_installation_revision=1,
    )
    executable_path = tmp_path / agent_type.value
    executable_path.write_text("#!/bin/sh\n", encoding="utf-8")
    executable_path.chmod(0o755)
    details = executable_path.stat()
    command_type = WAWClaudeCommand if agent_type is AgentType.CLAUDE else WAWCodexCommand
    command = command_type(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        cwd=tmp_path,
        executable=ExecutableIdentity(
            executable_path,
            details.st_dev,
            details.st_ino,
            details.st_mode,
            details.st_size,
            details.st_mtime_ns,
        ),
        argv=("remote-control",) if agent_type is AgentType.CLAUDE else (),
        managed_marker=managed_marker(
            runtime_host_installation_id=stop_binding.runtime_host_installation_id,
            runtime_host_installation_revision=stop_binding.runtime_host_installation_revision,
            project_id=stop_binding.project_id,
            agent_type=stop_binding.agent_type,
            workspace_id_value=stop_binding.workspace_id,
            generation=stop_binding.generation,
            binding_revision=stop_binding.binding_revision,
            binding_digest=stop_binding.binding_digest,
        ),
    )
    transport = FakeTransport()
    return (
        WAWSupervisor(
            workspace_id=workspace,
            generation=1,
            command=command,
            transport=transport,
            geometry=PtyGeometry(80, 24),
            clock=lambda: 1.0,
            attachment_validator=lambda _: True,
            stop_binding=stop_binding,
            runtime_epoch=runtime_epoch,
        ),
        transport,
        workspace,
    )


@pytest.mark.parametrize("epoch", ["١", "0", "9" * 21])
@pytest.mark.parametrize("agent_type", list(AgentType))
def test_supervisor_rejects_noncanonical_runtime_epoch(
    tmp_path: Path, agent_type: AgentType, epoch: str
) -> None:
    with pytest.raises(RuntimeOperationError, match="canonical"):
        _supervisor(tmp_path, agent_type=agent_type, runtime_epoch=epoch)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_bridge_same_epoch_replay_is_bound_and_exposes_output(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, _transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    bridge = WAWStreamBridge(supervisor, attachment)
    bridge.attach()
    supervisor.append_output(supervisor.output_source(), b"ok")
    assert bridge.output(0)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_bridge_rejects_missing_context_and_mismatched_generation_or_epoch(
    tmp_path: Path,
    agent_type: AgentType,
) -> None:
    supervisor, _transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    with pytest.raises(RuntimeOperationError, match="identity"):
        WAWStreamBridge(supervisor, replace(attachment, context=None))
    bridge = WAWStreamBridge(supervisor, attachment)
    bridge.attach()
    supervisor.append_output(supervisor.output_source(), b"secret")
    assert attachment.context is not None
    mismatched = replace(attachment, context=replace(attachment.context, runtime_epoch="2"))
    epoch_bridge = WAWStreamBridge(supervisor, mismatched)
    with pytest.raises(RuntimeOperationError, match="Runtime epoch"):
        epoch_bridge.attach()
    with pytest.raises(RuntimeOperationError, match="current state"):
        epoch_bridge.output(0)
    with pytest.raises(RuntimeOperationError, match="Runtime epoch"):
        supervisor.write_input(mismatched, b"never-written")
    assert _transport.writes == []
    with pytest.raises(RuntimeOperationError, match="Runtime epoch"):
        supervisor.replay_output(0, generation=1, runtime_epoch="2")
    with pytest.raises(RuntimeOperationError, match="generation"):
        supervisor.replay_output(0, generation=2, runtime_epoch="1")
    generation_bridge = WAWStreamBridge(
        supervisor, replace(attachment, claims=replace(attachment.claims, generation=2))
    )
    with pytest.raises(RuntimeOperationError, match="binding"):
        generation_bridge.attach()


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_lifecycle_fences_input_resize_replay_detach_and_stop(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    attachment = _attachment(workspace)
    assert supervisor.state is SupervisorState.ADMITTED
    supervisor.start()
    supervisor.attach(attachment)
    output_source = supervisor.output_source()
    supervisor.write_input(attachment, b"hello\r")
    supervisor.resize(attachment, PtyGeometry(100, 30))
    supervisor.append_output(output_source, b"ok")
    replay = supervisor.replay_output(0, generation=1, runtime_epoch="1")
    assert replay.kind == "frames"
    assert replay.frames[0].payload == b"ok"
    supervisor.detach(attachment)
    assert supervisor.snapshot().state is SupervisorState.DETACHED
    reconnected = _attachment(workspace, attachment_id="att_" + "5" * 32)
    supervisor.attach(reconnected)
    supervisor.stop(reconnected)
    assert supervisor.snapshot().state.value == SupervisorState.STOPPED.value
    assert transport.started and transport.writes == [b"hello\r"] and transport.stopped


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_stale_attachment_and_input_failure_fail_closed(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    supervisor.attach(attachment)
    stale = _attachment(workspace, attachment_id="att_" + "4" * 32)
    with pytest.raises(RuntimeOperationError, match="writer attachment"):
        supervisor.write_input(stale, b"x")

    transport.fail_writes = True
    with pytest.raises(RuntimeOperationError, match="confirm"):
        supervisor.write_input(attachment, b"x")
    assert supervisor.state is SupervisorState.INPUT_UNCERTAIN


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_forged_same_id_claims_and_reconnect_are_rejected(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    supervisor.attach(attachment)
    forged = replace(
        attachment,
        claims=replace(attachment.claims, binding_digest="b" * 64),
    )
    with pytest.raises(RuntimeOperationError, match="binding"):
        supervisor.write_input(forged, b"x")
    supervisor.detach(attachment)
    with pytest.raises(RuntimeOperationError, match="fresh attachment"):
        supervisor.attach(attachment)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_detach_requires_positive_runtime_ack(tmp_path: Path, agent_type: AgentType) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    supervisor.attach(attachment)
    transport.detach_confirmed = False
    with pytest.raises(RuntimeOperationError, match="confirm"):
        supervisor.detach(attachment)
    assert supervisor.state is SupervisorState.RUNNING


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_heartbeat_replaces_immutable_authority_lease(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    supervisor.attach(attachment)
    renewed = replace(
        attachment,
        last_heartbeat_monotonic=2.0,
        lease_expires_at_monotonic=150.0,
    )
    supervisor.heartbeat(attachment, renewed)
    with pytest.raises(RuntimeOperationError, match="writer attachment"):
        supervisor.write_input(attachment, b"old")
    supervisor.write_input(renewed, b"new")


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_output_is_not_available_after_exact_stop(tmp_path: Path, agent_type: AgentType) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    attachment = _attachment(workspace)
    supervisor.start()
    supervisor.attach(attachment)
    output_source = supervisor.output_source()
    supervisor.append_output(output_source, b"x")
    supervisor.stop(attachment)
    with pytest.raises(RuntimeOperationError, match="unavailable"):
        supervisor.replay_output(0, generation=1, runtime_epoch="1")


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_output_replay_rejects_cross_generation_cursor(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    source = supervisor.output_source()
    supervisor.append_output(source, b"x")
    with pytest.raises(RuntimeOperationError, match="generation"):
        supervisor.replay_output(0, generation=2)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_output_requires_runtime_admission(tmp_path: Path, agent_type: AgentType) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    forged_source = object()
    with pytest.raises(RuntimeOperationError, match="source"):
        supervisor.append_output(forged_source, b"x")  # type: ignore[arg-type]


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_exact_stop_does_not_require_browser_attachment(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    operation = WorkspaceStopOperation(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        agent_type=agent_type,
        generation=1,
        binding_revision=1,
        binding_digest="a" * 64,
        runtime_host_installation_id="wri_" + "3" * 32,
        runtime_host_installation_revision=1,
    )
    supervisor.exact_stop(operation)
    assert transport.stopped is True


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_exact_stop_rejects_stale_binding(tmp_path: Path, agent_type: AgentType) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    operation = WorkspaceStopOperation(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        agent_type=agent_type,
        generation=1,
        binding_revision=1,
        binding_digest="b" * 64,
        runtime_host_installation_id="wri_" + "3" * 32,
        runtime_host_installation_revision=1,
    )
    with pytest.raises(RuntimeOperationError, match="does not match"):
        supervisor.exact_stop(operation)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_exact_stop_rejects_terminal_operation_replay(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    operation = WorkspaceStopOperation(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        agent_type=agent_type,
        generation=1,
        binding_revision=1,
        binding_digest="a" * 64,
        runtime_host_installation_id="wri_" + "3" * 32,
        runtime_host_installation_revision=1,
        result="STOPPED",
    )
    with pytest.raises(RuntimeOperationError, match="pending"):
        supervisor.exact_stop(operation)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_unconfirmed_stop_preserves_reconciliation_state(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    transport.stop_closed = False
    operation = WorkspaceStopOperation(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        agent_type=agent_type,
        generation=1,
        binding_revision=1,
        binding_digest="a" * 64,
        runtime_host_installation_id="wri_" + "3" * 32,
        runtime_host_installation_revision=1,
    )
    with pytest.raises(RuntimeOperationError, match="exact close"):
        supervisor.exact_stop(operation)
    assert supervisor.state is SupervisorState.RECONCILIATION_REQUIRED


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_abws_full_flow_uses_the_same_agent_fenced_supervisor(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    bridge = WAWStreamBridge(supervisor, attachment)
    bridge.attach()
    reply = bridge.handle(decode_frame(encode_frame(FrameType.INPUT, b"prompt\r", 1)))
    assert decode_frame(reply[0]).frame_type is FrameType.ACK
    assert transport.writes == [b"prompt\r"]
    reply = bridge.handle(
        decode_frame(
            encode_frame(FrameType.RESIZE, {"protocol_version": 1, "columns": 100, "rows": 30}, 2)
        )
    )
    assert decode_frame(reply[0]).frame_type is FrameType.RESIZE_ACK
    assert transport.resizes[-1] == PtyGeometry(100, 30)
    supervisor.append_output(supervisor.output_source(), b"output")
    reply = bridge.handle(
        decode_frame(encode_frame(FrameType.STATE, {"protocol_version": 1, "after_cursor": 0}, 3))
    )
    assert [decode_frame(frame).payload for frame in reply] == [b"output"]
    bridge.handle(decode_frame(encode_frame(FrameType.DETACH, {"protocol_version": 1}, 4)))
    assert not bool(transport.stopped)
    fresh = _attachment(workspace, attachment_id="att_" + "5" * 32)
    fresh = replace(fresh, claims=replace(fresh.claims, lease_number=2))
    reconnect = WAWStreamBridge(supervisor, fresh)
    reconnect.attach()
    assert [decode_frame(frame).payload for frame in reconnect.output(0)] == [b"output"]
    with pytest.raises(RuntimeOperationError):
        bridge.output(0)
    supervisor.exact_stop(
        WorkspaceStopOperation(
            workspace_id=workspace,
            project_id="prj_" + "1" * 32,
            agent_type=agent_type,
            generation=1,
            binding_revision=1,
            binding_digest="a" * 64,
            runtime_host_installation_id="wri_" + "3" * 32,
            runtime_host_installation_revision=1,
        )
    )
    assert supervisor.state is SupervisorState.STOPPED
    assert transport.stopped
    with pytest.raises(RuntimeOperationError):
        reconnect.output(0)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_other_agent_cannot_write_or_stop_the_current_workspace(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    supervisor.attach(_attachment(workspace))
    other = AgentType.CODEX if agent_type is AgentType.CLAUDE else AgentType.CLAUDE
    other_workspace = workspace_id("prj_" + "1" * 32, other)
    with pytest.raises(RuntimeOperationError):
        supervisor.write_input(_attachment(other_workspace), b"wrong-agent")
    with pytest.raises(RuntimeOperationError):
        supervisor.exact_stop(
            WorkspaceStopOperation(
                workspace_id=other_workspace,
                project_id="prj_" + "1" * 32,
                agent_type=other,
                generation=1,
                binding_revision=1,
                binding_digest="a" * 64,
                runtime_host_installation_id="wri_" + "3" * 32,
                runtime_host_installation_revision=1,
            )
        )
    assert transport.writes == []
    assert not transport.stopped


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_command_is_revalidated_before_any_transport_start(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, _ = _supervisor(tmp_path, agent_type=agent_type)
    (tmp_path / agent_type.value).write_text("replaced executable contents\n")
    with pytest.raises(RuntimeOperationError):
        supervisor.start()
    assert not transport.started
    assert transport.commands == []


def test_structural_command_and_subclass_cannot_widen_the_allowlist(tmp_path: Path) -> None:
    supervisor, transport, _ = _supervisor(tmp_path)
    supervisor.start()
    command = transport.commands[0]
    forged = SimpleNamespace(**command.__dict__)
    with pytest.raises(RuntimeOperationError, match="supported WAW command"):
        validate_managed_command(cast(WAWManagedCommand, forged))

    class UnapprovedCommand(WAWClaudeCommand):
        pass

    subclass = UnapprovedCommand(**command.__dict__)
    with pytest.raises(RuntimeOperationError, match="supported WAW command"):
        validate_managed_command(subclass)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_close_releases_only_the_attachment_and_rejects_late_replay(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    bridge = WAWStreamBridge(supervisor, _attachment(workspace))
    bridge.attach()
    supervisor.append_output(supervisor.output_source(), b"still-running")
    reply = bridge.handle(decode_frame(encode_frame(FrameType.CLOSE, {"protocol_version": 1}, 1)))
    assert decode_frame(reply[0]).frame_type is FrameType.CLOSE
    assert bridge.state is WAWStreamState.CLOSED
    assert supervisor.state is SupervisorState.DETACHED
    assert not transport.stopped
    with pytest.raises(RuntimeOperationError):
        bridge.handle(
            decode_frame(
                encode_frame(FrameType.STATE, {"protocol_version": 1, "after_cursor": 0}, 2)
            )
        )
    assert bridge.state is WAWStreamState.CLOSED


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_failed_close_does_not_release_a_writer_or_kill_the_workspace(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    bridge = WAWStreamBridge(supervisor, attachment)
    bridge.attach()
    transport.detach_confirmed = False
    with pytest.raises(RuntimeOperationError):
        bridge.handle(decode_frame(encode_frame(FrameType.CLOSE, {"protocol_version": 1}, 1)))
    assert supervisor.snapshot().attachment_id == attachment.attachment_id
    assert supervisor.state is SupervisorState.RUNNING
    assert not transport.stopped


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_probe_preserves_input_uncertainty_and_detached_writer_state(
    tmp_path: Path, agent_type: AgentType
) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    attachment = _attachment(workspace)
    supervisor.attach(attachment)
    transport.fail_writes = True
    with pytest.raises(RuntimeOperationError):
        supervisor.write_input(attachment, b"uncertain")
    assert supervisor.probe().state is RuntimeProbeState.RUNNING
    assert supervisor.state is SupervisorState.INPUT_UNCERTAIN
    transport.fail_writes = False
    with pytest.raises(RuntimeOperationError, match="Input is paused"):
        supervisor.write_input(attachment, b"do not replay")
    supervisor.detach(attachment)
    before = supervisor.snapshot()
    assert supervisor.probe().state is RuntimeProbeState.RUNNING
    assert supervisor.snapshot() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", 2),
        ("generation", True),
        ("managed_marker", "waw-v1:wri_" + "9" * 32 + ":" + "9" * 32),
        ("state", "RUNNING"),
        ("exit_code", 0),
        ("state", RuntimeProbeState.EXITED),
    ],
)
def test_probe_rejects_ambiguous_or_stale_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    supervisor, transport, _ = _supervisor(tmp_path)
    supervisor.start()
    # Deliberately inject malformed external evidence past static annotations.
    evidence = replace(transport.probe(), **cast(dict[str, Any], {field: value}))
    monkeypatch.setattr(transport, "probe", lambda: evidence)
    with pytest.raises(RuntimeOperationError, match="observation is not exact"):
        supervisor.probe()


def test_missing_probe_never_falls_back_to_running_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor, transport, _ = _supervisor(tmp_path)
    supervisor.start()
    monkeypatch.setattr(transport, "probe", None)
    with pytest.raises(RuntimeOperationError, match="observation is unavailable"):
        supervisor.probe()
    assert supervisor.state is SupervisorState.RUNNING


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_stream_replay_rechecks_current_attachment_authority(
    tmp_path: Path, agent_type: AgentType, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor, _, workspace = _supervisor(tmp_path, agent_type=agent_type)
    supervisor.start()
    bridge = WAWStreamBridge(supervisor, _attachment(workspace))
    bridge.attach()
    supervisor.append_output(supervisor.output_source(), b"private output")
    monkeypatch.setattr(supervisor, "_attachment_validator", lambda _attachment: False)
    with pytest.raises(RuntimeOperationError, match="no longer current"):
        bridge.output(0)
    with pytest.raises(RuntimeOperationError, match="no longer current"):
        bridge.handle(
            decode_frame(
                encode_frame(FrameType.STATE, {"protocol_version": 1, "after_cursor": 0}, 1)
            )
        )
