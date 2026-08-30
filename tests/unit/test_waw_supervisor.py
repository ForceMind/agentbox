from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from agentbox_core.waw import AgentType, workspace_id
from agentbox_core.waw_tickets import ActiveAttachment, AttachmentTuple
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_supervisor import (
    RuntimeStartEvidence,
    RuntimeStopEvidence,
    SupervisorState,
    WAWSupervisor,
)


class FakeTransport:
    def __init__(self) -> None:
        self.started = False
        self.writes: list[bytes] = []
        self.resizes: list[PtyGeometry] = []
        self.stopped = False
        self.fail_writes = False
        self.detach_confirmed = True
        self.workspace_id = ""
        self.generation = 1
        self.marker = ""

    def start(self, command: WAWClaudeCommand, geometry: PtyGeometry) -> RuntimeStartEvidence:
        assert command.argv == ("remote-control",)
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
            True,
            0,
        )


def _attachment(workspace: str, *, attachment_id: str = "att_" + "2" * 32) -> ActiveAttachment:
    claims = AttachmentTuple(
        workspace_id=workspace,
        project_id="prj_" + "1" * 32,
        agent_type=AgentType.CLAUDE,
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
    return ActiveAttachment(claims, 0.0, 0.0, 100.0, 200.0)


def _supervisor(tmp_path: Path) -> tuple[WAWSupervisor, FakeTransport, str]:
    workspace = workspace_id("prj_" + "1" * 32, AgentType.CLAUDE)
    executable_path = tmp_path / "claude"
    executable_path.write_text("#!/bin/sh\n", encoding="utf-8")
    executable_path.chmod(0o755)
    details = executable_path.stat()
    command = WAWClaudeCommand(
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
        argv=("remote-control",),
        managed_marker="waw-v1:wri_" + "2" * 32 + ":" + "3" * 32,
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
        ),
        transport,
        workspace,
    )


def test_lifecycle_fences_input_resize_replay_detach_and_stop(tmp_path: Path) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path)
    attachment = _attachment(workspace)
    assert supervisor.state is SupervisorState.ADMITTED
    supervisor.start()
    supervisor.attach(attachment)
    supervisor.write_input(attachment, b"hello\r")
    supervisor.resize(attachment, PtyGeometry(100, 30))
    supervisor.append_output(b"ok")
    replay = supervisor.replay_output(0)
    assert replay.kind == "frames"
    assert replay.frames[0].payload == b"ok"
    supervisor.detach(attachment)
    assert supervisor.snapshot().state is SupervisorState.DETACHED
    reconnected = _attachment(workspace, attachment_id="att_" + "5" * 32)
    supervisor.attach(reconnected)
    supervisor.stop(reconnected)
    assert supervisor.snapshot().state.value == SupervisorState.STOPPED.value
    assert transport.started and transport.writes == [b"hello\r"] and transport.stopped


def test_stale_attachment_and_input_failure_fail_closed(tmp_path: Path) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path)
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


def test_forged_same_id_claims_and_reconnect_are_rejected(tmp_path: Path) -> None:
    supervisor, _, workspace = _supervisor(tmp_path)
    supervisor.start()
    attachment = _attachment(workspace)
    supervisor.attach(attachment)
    forged = replace(
        attachment,
        claims=replace(attachment.claims, binding_digest="b" * 64),
    )
    with pytest.raises(RuntimeOperationError, match="writer attachment"):
        supervisor.write_input(forged, b"x")
    supervisor.detach(attachment)
    with pytest.raises(RuntimeOperationError, match="fresh attachment"):
        supervisor.attach(attachment)


def test_detach_requires_positive_runtime_ack(tmp_path: Path) -> None:
    supervisor, transport, workspace = _supervisor(tmp_path)
    supervisor.start()
    attachment = _attachment(workspace)
    supervisor.attach(attachment)
    transport.detach_confirmed = False
    with pytest.raises(RuntimeOperationError, match="confirm"):
        supervisor.detach(attachment)
    assert supervisor.state is SupervisorState.RUNNING


def test_output_is_not_available_after_exact_stop(tmp_path: Path) -> None:
    supervisor, _, workspace = _supervisor(tmp_path)
    attachment = _attachment(workspace)
    supervisor.start()
    supervisor.attach(attachment)
    supervisor.append_output(b"x")
    supervisor.stop(attachment)
    with pytest.raises(RuntimeOperationError, match="unavailable"):
        supervisor.replay_output(0)
