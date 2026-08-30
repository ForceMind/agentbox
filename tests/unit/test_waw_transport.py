from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agentbox_core.waw import AgentType, workspace_id
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_supervisor import SupervisorState
from agentbox_runtime.waw_transport import WAWTmuxTransport


class FakeTmux:
    def __init__(self) -> None:
        self.sessions: dict[str, str] = {}
        self.calls: list[tuple[str, object]] = []
        self.writes: list[bytes] = []
        self.resizes: list[tuple[str, int, int]] = []
        self.pane_is_dead = False
        self.pane_process = "claude"

    async def has_session(self, session_name: str) -> bool:
        self.calls.append(("has", session_name))
        return session_name in self.sessions

    async def is_managed(self, session_name: str, managed_marker: str) -> bool:
        self.calls.append(("managed", (session_name, managed_marker)))
        return self.sessions.get(session_name) == managed_marker

    async def pane_dead(self, session_name: str) -> bool:
        self.calls.append(("dead", session_name))
        return self.pane_is_dead

    async def pane_command(self, session_name: str) -> str:
        self.calls.append(("command", session_name))
        return self.pane_process

    async def create_session(
        self,
        session_name: str,
        *,
        cwd: Path,
        command: ExecutableIdentity,
        managed_marker: str,
    ) -> None:
        self.calls.append(("create", (session_name, cwd, command.path, command, managed_marker)))
        self.sessions[session_name] = managed_marker

    async def kill_session(self, session_name: str) -> bool:
        self.calls.append(("kill", session_name))
        return self.sessions.pop(session_name, None) is not None

    async def write_input(self, session_name: str, data: bytes) -> None:
        self.calls.append(("write", session_name))
        if session_name not in self.sessions:
            raise RuntimeError("missing session")
        self.writes.append(data)

    async def resize_window(self, session_name: str, *, columns: int, rows: int) -> None:
        self.calls.append(("resize", session_name))
        if session_name not in self.sessions:
            raise RuntimeError("missing session")
        self.resizes.append((session_name, columns, rows))


def _command(tmp_path: Path, *, project_id: str = "prj_" + "1" * 32) -> WAWClaudeCommand:
    executable = tmp_path / "claude"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    details = executable.stat()
    workspace = workspace_id(project_id, AgentType.CLAUDE)
    return WAWClaudeCommand(
        workspace_id=workspace,
        project_id=project_id,
        cwd=tmp_path,
        executable=ExecutableIdentity(
            executable.resolve(),
            details.st_dev,
            details.st_ino,
            details.st_mode,
            details.st_size,
            details.st_mtime_ns,
        ),
        argv=("remote-control",),
        managed_marker="waw-v1:wri_" + "2" * 32 + ":" + "3" * 32,
    )


def test_tmux_transport_binds_fixed_command_and_typed_lifecycle(tmp_path: Path) -> None:
    command = _command(tmp_path)
    tmux = FakeTmux()
    transport = WAWTmuxTransport(
        workspace_id=command.workspace_id,
        generation=3,
        tmux=tmux,
        managed_marker=command.managed_marker,
    )

    evidence = transport.start(command, PtyGeometry(80, 24))
    assert evidence.workspace_id == command.workspace_id
    assert evidence.generation == 3
    assert evidence.managed_marker == command.managed_marker
    assert evidence.state is SupervisorState.RUNNING
    assert evidence.ready is True

    transport.write(b"echo safe\r")
    transport.resize(PtyGeometry(100, 30))
    assert tmux.writes == [b"echo safe\r"]
    assert tmux.resizes[-1][1:] == (100, 30)
    assert transport.detach() is True
    assert transport.detach() is False

    stopped = transport.stop()
    assert stopped.closed is True
    assert stopped.remaining_members == 0
    assert stopped.generation == 3
    with pytest.raises(RuntimeOperationError):
        transport.write(b"late")


def test_tmux_transport_rejects_workspace_and_marker_drift(tmp_path: Path) -> None:
    command = _command(tmp_path)
    tmux = FakeTmux()
    transport = WAWTmuxTransport(
        workspace_id=command.workspace_id,
        generation=1,
        tmux=tmux,
        managed_marker=command.managed_marker,
    )
    wrong_workspace = "aws_" + "4" * 32
    mismatched_transport = WAWTmuxTransport(
        workspace_id=wrong_workspace,
        generation=1,
        tmux=tmux,
    )
    with pytest.raises(RuntimeOperationError, match="workspace"):
        mismatched_transport.start(command, PtyGeometry(80, 24))

    wrong_marker = WAWClaudeCommand(
        workspace_id=command.workspace_id,
        project_id=command.project_id,
        cwd=command.cwd,
        executable=command.executable,
        argv=command.argv,
        managed_marker="waw-v1:wri_" + "5" * 32 + ":" + "6" * 32,
    )
    with pytest.raises(RuntimeOperationError, match="marker"):
        transport.start(wrong_marker, PtyGeometry(80, 24))


def test_tmux_transport_adopts_only_exact_marked_session(tmp_path: Path) -> None:
    command = _command(tmp_path)
    tmux = FakeTmux()
    transport = WAWTmuxTransport(
        workspace_id=command.workspace_id,
        generation=1,
        tmux=tmux,
    )
    # A colliding target with a different marker must not be killed or adopted.
    from agentbox_runtime.waw_transport import _managed_session_name

    tmux.sessions[_managed_session_name(command.project_id)] = "v1:" + "a" * 16
    with pytest.raises(RuntimeOperationError, match="marker"):
        transport.start(command, PtyGeometry(80, 24))
    assert not any(kind == "kill" for kind, _ in tmux.calls)


def test_tmux_transport_revalidates_marker_before_input_and_resize(tmp_path: Path) -> None:
    command = _command(tmp_path)
    tmux = FakeTmux()
    transport = WAWTmuxTransport(
        workspace_id=command.workspace_id,
        generation=1,
        tmux=tmux,
        managed_marker=command.managed_marker,
    )
    transport.start(command, PtyGeometry(80, 24))
    session_name = transport.session_name
    assert session_name is not None
    tmux.sessions[session_name] = "waw-v1:wri_" + "9" * 32 + ":" + "8" * 32
    with pytest.raises(RuntimeOperationError, match="marker"):
        transport.write(b"x")
    with pytest.raises(RuntimeOperationError, match="marker"):
        transport.resize(PtyGeometry(100, 30))


def test_tmux_transport_rejects_dead_pane_readiness(tmp_path: Path) -> None:
    command = _command(tmp_path)
    tmux = FakeTmux()
    tmux.pane_is_dead = True
    transport = WAWTmuxTransport(
        workspace_id=command.workspace_id,
        generation=1,
        tmux=tmux,
        managed_marker=command.managed_marker,
    )
    with pytest.raises(RuntimeOperationError, match="exited"):
        transport.start(command, PtyGeometry(80, 24))


def test_tmux_transport_rejects_wrong_pane_process(tmp_path: Path) -> None:
    command = _command(tmp_path)
    tmux = FakeTmux()
    tmux.pane_process = "bash"
    transport = WAWTmuxTransport(
        workspace_id=command.workspace_id,
        generation=1,
        tmux=tmux,
        managed_marker=command.managed_marker,
    )
    with pytest.raises(RuntimeOperationError, match="Claude"):
        transport.start(command, PtyGeometry(80, 24))


def test_resolve_timeout_cancels_worker_without_late_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agentbox_runtime.waw_transport as waw_transport

    mutated = False

    async def delayed_mutation() -> None:
        nonlocal mutated
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return
        mutated = True

    monkeypatch.setattr(waw_transport, "_RESOLVE_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(RuntimeOperationError, match="timed out"):
        waw_transport._resolve(delayed_mutation())
    assert mutated is False
