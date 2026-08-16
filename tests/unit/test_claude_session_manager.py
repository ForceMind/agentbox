from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_runtime import (
    AuthenticationState,
    CapabilityState,
    ClaudeAdapter,
    ClaudeCapabilities,
    ClaudeSessionManager,
    ClaudeSessionState,
    ProjectRegistry,
    RuntimeOperationError,
    TmuxAdapter,
    managed_session_marker,
    managed_session_name,
)
from agentbox_runtime.models import DiagnosticFinding
from agentbox_runtime.process import ExecutableIdentity, inspect_executable


class FakeClaudeAdapter(ClaudeAdapter):
    def __init__(self, executable: ExecutableIdentity) -> None:
        self.identity = executable

    def executable(self) -> ExecutableIdentity | None:
        return self.identity

    async def inspect(
        self,
    ) -> tuple[
        bool,
        str | None,
        AuthenticationState,
        ClaudeCapabilities,
        tuple[DiagnosticFinding, ...],
    ]:
        return (
            True,
            "1.fixture",
            AuthenticationState.UNKNOWN,
            ClaudeCapabilities(
                remote_control=CapabilityState.SUPPORTED,
                remote_start=CapabilityState.SUPPORTED,
                version=CapabilityState.SUPPORTED,
            ),
            (),
        )


class FakeTmuxAdapter(TmuxAdapter):
    def __init__(self, executable: ExecutableIdentity) -> None:
        self.identity = executable
        self.sessions: dict[str, str | None] = {}
        self.outputs: dict[str, bytes] = {}
        self.killed: list[str] = []
        self.created: list[tuple[str, Path, str]] = []
        self.dead: set[str] = set()
        self.interaction_prepared: list[str] = []
        self.create_output = b"Starting interactive terminal"

    def executable(self) -> ExecutableIdentity | None:
        return self.identity

    async def version(self) -> str | None:
        return "3.fixture"

    async def list_sessions(self) -> tuple[str, ...]:
        return tuple(self.sessions)

    async def has_session(self, session_name: str) -> bool:
        return session_name in self.sessions

    async def is_managed(self, session_name: str, managed_marker: str) -> bool:
        return self.sessions.get(session_name) == managed_marker

    async def create_session(
        self,
        session_name: str,
        *,
        cwd: Path,
        command: ExecutableIdentity,
        managed_marker: str,
    ) -> None:
        del command
        self.sessions[session_name] = managed_marker
        self.outputs[session_name] = self.create_output
        self.created.append((session_name, cwd, managed_marker))

    async def pane_dead(self, session_name: str) -> bool:
        return session_name in self.dead

    async def prepare_workspace_interaction(
        self,
        session_name: str,
        *,
        cwd: Path,
        command: ExecutableIdentity,
    ) -> None:
        del cwd, command
        self.dead.discard(session_name)
        self.outputs[session_name] = b"Do you trust this workspace?"
        self.interaction_prepared.append(session_name)

    async def capture_pane(self, session_name: str, *, lines: int = 200) -> bytes:
        del lines
        if session_name not in self.sessions:
            raise RuntimeOperationError("CLAUDE_SESSION_OUTPUT_UNAVAILABLE", "missing")
        return self.outputs.get(session_name, b"")

    async def kill_session(self, session_name: str) -> bool:
        if session_name not in self.sessions:
            return False
        self.killed.append(session_name)
        del self.sessions[session_name]
        return True


def binary(path: Path) -> ExecutableIdentity:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return inspect_executable(path)


def manager(tmp_path: Path) -> tuple[ClaudeSessionManager, FakeTmuxAdapter, Path]:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    project = project_root / "project-a"
    project.mkdir()
    identity = binary(tmp_path / "bin" / "runtime")
    tmux = FakeTmuxAdapter(identity)

    async def no_sleep(_seconds: float) -> None:
        return None

    value = ClaudeSessionManager(
        FakeClaudeAdapter(identity),
        tmux,
        ProjectRegistry(project_root),
        sleep=no_sleep,
    )
    return value, tmux, project


@pytest.mark.anyio
async def test_start_is_project_scoped_duplicate_safe_and_restart_discoverable(
    tmp_path: Path,
) -> None:
    sessions, tmux, project = manager(tmp_path)
    first = await sessions.start("project-a")
    second = await sessions.start("project-a")
    expected_name = managed_session_name("project-a")

    assert first.outcome == "started"
    assert first.session.state is ClaudeSessionState.STARTING
    assert second.outcome == "already_running"
    assert tmux.created == [(expected_name, project.resolve(), managed_session_marker("project-a"))]
    restarted = ClaudeSessionManager(
        sessions._adapter,
        tmux,
        sessions._projects,
    )
    discovered = await restarted.session("project-a")
    assert discovered.managed is True
    assert discovered.tmux_running is True
    assert discovered.state is ClaudeSessionState.UNKNOWN


@pytest.mark.anyio
async def test_workspace_prompt_requires_interaction_and_is_never_accepted(tmp_path: Path) -> None:
    sessions, tmux, _project = manager(tmp_path)
    name = managed_session_name("project-a")
    tmux.sessions[name] = managed_session_marker("project-a")
    tmux.outputs[name] = b"Do you trust this workspace?"

    observed = await sessions.session("project-a")
    assert observed.state is ClaudeSessionState.NEEDS_INTERACTION
    assert observed.workspace_state.value == "requires_user_confirmation"
    assert tmux.created == []


@pytest.mark.anyio
async def test_start_prepares_live_manual_trust_pane_without_accepting(tmp_path: Path) -> None:
    sessions, tmux, _project = manager(tmp_path)
    name = managed_session_name("project-a")
    tmux.create_output = b"Do you trust this workspace?"
    tmux.dead.add(name)

    started = await sessions.start("project-a")

    assert started.session.state is ClaudeSessionState.NEEDS_INTERACTION
    assert started.session.workspace_state.value == "requires_user_confirmation"
    assert started.session.remote_readiness == "unknown"
    assert tmux.interaction_prepared == [name]


@pytest.mark.anyio
async def test_stop_kills_only_exact_marked_session(tmp_path: Path) -> None:
    sessions, tmux, _project = manager(tmp_path)
    exact = managed_session_name("project-a")
    similar = f"{exact}-similar"
    tmux.sessions[exact] = managed_session_marker("project-a")
    tmux.sessions[similar] = "v1:ffffffffffffffff"
    tmux.sessions["claude-legacy"] = None

    stopped = await sessions.stop("project-a")
    assert stopped.outcome == "stopped"
    assert tmux.killed == [exact]
    assert similar in tmux.sessions and "claude-legacy" in tmux.sessions
    assert (await sessions.stop("project-a")).outcome == "already_stopped"


@pytest.mark.anyio
async def test_exact_unmanaged_collision_cannot_be_observed_stopped_or_captured(
    tmp_path: Path,
) -> None:
    sessions, tmux, _project = manager(tmp_path)
    exact = managed_session_name("project-a")
    tmux.sessions[exact] = None

    for operation in (
        sessions.session("project-a"),
        sessions.start("project-a"),
        sessions.stop("project-a"),
        sessions.recent_output("project-a"),
    ):
        with pytest.raises(RuntimeOperationError):
            await operation
    assert tmux.killed == []


@pytest.mark.anyio
async def test_recent_output_is_bounded_sanitized_and_ephemeral(tmp_path: Path) -> None:
    sessions, tmux, _project = manager(tmp_path)
    name = managed_session_name("project-a")
    tmux.sessions[name] = managed_session_marker("project-a")
    tmux.outputs[name] = b"\x1b[31mCLAUDE-OUTPUT-CANARY\x1b[0m\x00"

    output = await sessions.recent_output("project-a")
    assert output.output == "CLAUDE-OUTPUT-CANARY"
    assert output.sensitive is True
    assert "\x1b" not in output.output and "\x00" not in output.output


@pytest.mark.anyio
async def test_capability_status_counts_only_exact_managed_sessions_without_pane_access(
    tmp_path: Path,
) -> None:
    sessions, tmux, _project = manager(tmp_path)
    name = managed_session_name("project-a")
    tmux.sessions[name] = managed_session_marker("project-a")
    tmux.outputs[name] = b"CLAUDE-PANE-SECRET-CANARY"

    async def forbidden_capture(_session_name: str, *, lines: int = 200) -> bytes:
        del lines
        raise AssertionError("capability collection must not capture a tmux pane")

    tmux.capture_pane = forbidden_capture  # type: ignore[assignment]
    status = await sessions.capability_status()

    assert status.installed is True
    assert status.tmux_installed is True
    assert status.managed_session_count == 1
    assert status.managed_session_evidence_available is True
    assert tmux.killed == []
    assert tmux.created == []
