from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from agentbox_core.waw import AgentType
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
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)

FORMAL_PROJECT = "prj_" + "1" * 32


class FakeClaudeAdapter(ClaudeAdapter):
    def __init__(self, executable: ExecutableIdentity, *, installed: bool = True) -> None:
        self.identity = executable
        self.installed = installed

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
            self.installed,
            "1.fixture" if self.installed else None,
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


class ConflictProbe:
    def __init__(self, states: tuple[WAWManagedConflictState, ...] = ()) -> None:
        self.states = states
        self.calls: list[str] = []

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        del project_id
        return WAWLegacyClaudeState.ABSENT

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        return WAWLegacyCodexState.ABSENT

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        self.calls.append(project_id)
        return self.states

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        return self.states


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
async def test_bound_waw_rows_block_legacy_claude_before_spawn(tmp_path: Path) -> None:
    sessions, tmux, _project = manager(tmp_path)
    probe = ConflictProbe((WAWManagedConflictState.LOGIN_REQUIRED,))
    sessions.bind_conflict_coordinator(
        WAWConflictCoordinator(probe),
        formal_project_id_for_legacy=lambda relative_key: (
            FORMAL_PROJECT if relative_key == "project-a" else ""
        ),
    )

    with pytest.raises(RuntimeOperationError) as raised:
        await sessions.start("project-a")

    assert raised.value.code == "PROJECT_RUNTIME_ACTIVE"
    assert probe.calls == [FORMAL_PROJECT]
    assert tmux.created == []


@pytest.mark.anyio
async def test_missing_formal_project_mapping_fails_closed_before_host_probe(
    tmp_path: Path,
) -> None:
    sessions, tmux, _project = manager(tmp_path)
    probe = ConflictProbe()
    sessions.bind_conflict_coordinator(
        WAWConflictCoordinator(probe),
        formal_project_id_for_legacy=lambda _relative_key: None,
    )

    with pytest.raises(RuntimeOperationError) as raised:
        await sessions.start("project-a")

    assert raised.value.code == "PROJECT_RUNTIME_ACTIVE"
    assert probe.calls == []
    assert tmux.created == []


@pytest.mark.anyio
async def test_legacy_claude_holds_host_lease_through_spawn_readback(tmp_path: Path) -> None:
    sessions, tmux, _project = manager(tmp_path)
    probe = ConflictProbe()
    coordinator = WAWConflictCoordinator(probe)
    sessions.bind_conflict_coordinator(
        coordinator,
        formal_project_id_for_legacy=lambda relative_key: (
            FORMAL_PROJECT if relative_key == "project-a" else ""
        ),
    )
    entered_create = asyncio.Event()
    release_create = asyncio.Event()
    original_create = tmux.create_session

    async def paused_create(*args: object, **kwargs: object) -> None:
        entered_create.set()
        await release_create.wait()
        await original_create(*args, **kwargs)  # type: ignore[arg-type]

    tmux.create_session = paused_create  # type: ignore[method-assign]
    start = asyncio.create_task(sessions.start("project-a"))
    await asyncio.wait_for(entered_create.wait(), timeout=1)
    competing = asyncio.create_task(
        asyncio.to_thread(
            coordinator.acquire_legacy_codex_start,
        )
    )
    await asyncio.sleep(0.02)
    assert not competing.done()
    release_create.set()
    assert (await start).outcome == "started"
    (await competing).release()


@pytest.mark.anyio
async def test_cancelled_legacy_claude_lock_wait_cannot_leak_host_lease(tmp_path: Path) -> None:
    sessions, _tmux, _project = manager(tmp_path)
    probe = ConflictProbe()
    coordinator = WAWConflictCoordinator(probe)
    sessions.bind_conflict_coordinator(
        coordinator,
        formal_project_id_for_legacy=lambda _relative_key: FORMAL_PROJECT,
    )
    holder = coordinator.acquire_waw_start(
        project_id=FORMAL_PROJECT,
        agent_type=AgentType.CLAUDE,
    )
    pending = asyncio.create_task(sessions.start("project-a"))
    await asyncio.sleep(0.02)
    pending.cancel()
    await asyncio.sleep(0.02)
    assert not pending.done()
    holder.release()

    with pytest.raises(asyncio.CancelledError):
        await pending
    replacement = await asyncio.wait_for(
        asyncio.to_thread(coordinator.acquire_legacy_codex_start),
        timeout=1,
    )
    replacement.release()


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


@pytest.mark.anyio
async def test_capability_status_does_not_scan_managed_sessions_when_claude_is_absent(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    (project_root / "project-a").mkdir()
    identity = binary(tmp_path / "bin" / "runtime")
    tmux = FakeTmuxAdapter(identity)

    async def forbidden_session_probe(_session_name: str) -> bool:
        raise AssertionError("Claude absence must skip managed-session probes")

    tmux.has_session = forbidden_session_probe  # type: ignore[assignment]
    sessions = ClaudeSessionManager(
        FakeClaudeAdapter(identity, installed=False),
        tmux,
        ProjectRegistry(project_root),
    )
    status = await sessions.capability_status()

    assert status.installed is False
    assert status.tmux_installed is True
    assert status.managed_session_count is None
    assert status.managed_session_evidence_available is False
