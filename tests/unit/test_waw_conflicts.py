from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import cast

import pytest
from agentbox_core.waw import AgentType
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWConflictError,
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)

PROJECT = "prj_" + "1" * 32


@dataclass
class _Probe:
    claude: WAWLegacyClaudeState = WAWLegacyClaudeState.ABSENT
    codex: WAWLegacyCodexState = WAWLegacyCodexState.ABSENT
    project_waw: tuple[WAWManagedConflictState, ...] = ()
    host_waw: tuple[WAWManagedConflictState, ...] = ()
    fail: str | None = None
    calls: list[str] = field(default_factory=list)

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        assert project_id == PROJECT
        self.calls.append("claude")
        if self.fail == "claude":
            raise OSError("synthetic probe error")
        return self.claude

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        self.calls.append("codex")
        if self.fail == "codex":
            raise OSError("synthetic probe error")
        return self.codex

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        assert project_id == PROJECT
        self.calls.append("waw-project")
        if self.fail == "waw-project":
            raise OSError("synthetic probe error")
        return self.project_waw

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        self.calls.append("waw-host")
        if self.fail == "waw-host":
            raise OSError("synthetic probe error")
        return self.host_waw


@pytest.mark.parametrize(
    "state",
    [
        WAWLegacyClaudeState.STARTING,
        WAWLegacyClaudeState.RUNNING,
        WAWLegacyClaudeState.NEEDS_INTERACTION,
        WAWLegacyClaudeState.LOGIN_REQUIRED,
        WAWLegacyClaudeState.TRUST_REQUIRED,
        WAWLegacyClaudeState.BROKEN,
        WAWLegacyClaudeState.UNKNOWN,
    ],
)
@pytest.mark.parametrize("agent_type", list(AgentType))
def test_same_project_legacy_claude_blocks_every_waw_agent(
    state: WAWLegacyClaudeState, agent_type: AgentType
) -> None:
    probe = _Probe(claude=state)
    with pytest.raises(WAWConflictError) as raised:
        WAWConflictCoordinator(probe).acquire_waw_start(project_id=PROJECT, agent_type=agent_type)
    assert raised.value.code == "PROJECT_RUNTIME_ACTIVE"
    assert probe.calls == ["claude"]


@pytest.mark.parametrize(
    "state",
    [
        WAWLegacyCodexState.STARTING,
        WAWLegacyCodexState.RUNNING,
        WAWLegacyCodexState.NEEDS_INTERACTION,
        WAWLegacyCodexState.BROKEN,
        WAWLegacyCodexState.UNKNOWN,
    ],
)
@pytest.mark.parametrize("agent_type", list(AgentType))
def test_host_codex_remote_blocks_every_waw_agent(
    state: WAWLegacyCodexState, agent_type: AgentType
) -> None:
    probe = _Probe(codex=state)
    with pytest.raises(WAWConflictError) as raised:
        WAWConflictCoordinator(probe).acquire_waw_start(project_id=PROJECT, agent_type=agent_type)
    assert raised.value.code == "CODEX_REMOTE_CONFLICT"
    assert probe.calls == ["claude", "codex"]


@pytest.mark.parametrize(
    "claude",
    [WAWLegacyClaudeState.ABSENT, WAWLegacyClaudeState.STOPPED, WAWLegacyClaudeState.EXITED],
)
@pytest.mark.parametrize(
    "codex",
    [WAWLegacyCodexState.ABSENT, WAWLegacyCodexState.STOPPED, WAWLegacyCodexState.EXITED],
)
def test_only_positive_absence_or_terminal_legacy_states_allow_waw(
    claude: WAWLegacyClaudeState, codex: WAWLegacyCodexState
) -> None:
    with WAWConflictCoordinator(_Probe(claude=claude, codex=codex)).acquire_waw_start(
        project_id=PROJECT, agent_type=AgentType.CLAUDE
    ) as lease:
        assert lease.operation == "WAW_START"
        assert lease.project_id == PROJECT
        assert lease.agent_type is AgentType.CLAUDE
    assert lease.released


def test_claude_conflict_has_precedence_when_both_are_present() -> None:
    probe = _Probe(
        claude=WAWLegacyClaudeState.UNKNOWN,
        codex=WAWLegacyCodexState.RUNNING,
    )
    with pytest.raises(WAWConflictError) as raised:
        WAWConflictCoordinator(probe).acquire_waw_start(
            project_id=PROJECT, agent_type=AgentType.CODEX
        )
    assert raised.value.code == "PROJECT_RUNTIME_ACTIVE"
    assert probe.calls == ["claude"]


@pytest.mark.parametrize(
    ("failed_probe", "expected"),
    [
        ("claude", "PROJECT_RUNTIME_ACTIVE"),
        ("codex", "CODEX_REMOTE_CONFLICT"),
        ("waw-project", "PROJECT_RUNTIME_ACTIVE"),
        ("waw-host", "CODEX_REMOTE_CONFLICT"),
    ],
)
def test_probe_errors_fail_closed(failed_probe: str, expected: str) -> None:
    probe = _Probe(fail=failed_probe)
    coordinator = WAWConflictCoordinator(probe)
    with pytest.raises(WAWConflictError) as raised:
        if failed_probe == "waw-project":
            coordinator.acquire_legacy_claude_start(project_id=PROJECT)
        elif failed_probe == "waw-host":
            coordinator.acquire_legacy_codex_start()
        else:
            coordinator.acquire_waw_start(project_id=PROJECT, agent_type=AgentType.CLAUDE)
    assert raised.value.code == expected


@pytest.mark.parametrize(
    "state",
    [
        state
        for state in WAWManagedConflictState
        if state
        not in {
            WAWManagedConflictState.ABSENT,
            WAWManagedConflictState.STOPPED,
            WAWManagedConflictState.EXITED,
        }
    ],
)
def test_every_nonterminal_waw_state_blocks_both_legacy_start_directions(
    state: WAWManagedConflictState,
) -> None:
    for method in ("claude", "codex"):
        probe = _Probe(project_waw=(state,), host_waw=(state,))
        coordinator = WAWConflictCoordinator(probe)
        with pytest.raises(WAWConflictError) as raised:
            if method == "claude":
                expected = "PROJECT_RUNTIME_ACTIVE"
                coordinator.acquire_legacy_claude_start(project_id=PROJECT)
            else:
                expected = "CODEX_REMOTE_CONFLICT"
                coordinator.acquire_legacy_codex_start()
        assert raised.value.code == expected


@pytest.mark.parametrize(
    "states",
    [
        (),
        (WAWManagedConflictState.ABSENT,),
        (WAWManagedConflictState.STOPPED, WAWManagedConflictState.EXITED),
    ],
)
def test_only_terminal_waw_rows_allow_legacy_starts(
    states: tuple[WAWManagedConflictState, ...],
) -> None:
    probe = _Probe(project_waw=states, host_waw=states)
    coordinator = WAWConflictCoordinator(probe)
    coordinator.acquire_legacy_claude_start(project_id=PROJECT).release()
    coordinator.acquire_legacy_codex_start().release()


def test_untyped_probe_state_fails_closed() -> None:
    probe = _Probe()
    probe.claude = cast(WAWLegacyClaudeState, "STOPPED")
    with pytest.raises(WAWConflictError) as raised:
        WAWConflictCoordinator(probe).acquire_waw_start(
            project_id=PROJECT, agent_type=AgentType.CLAUDE
        )
    assert raised.value.code == "PROJECT_RUNTIME_ACTIVE"


def test_waw_lease_serializes_racing_legacy_start_until_recheck() -> None:
    probe = _Probe(project_waw=(WAWManagedConflictState.RUNNING,))
    coordinator = WAWConflictCoordinator(probe)
    waw_lease = coordinator.acquire_waw_start(project_id=PROJECT, agent_type=AgentType.CODEX)
    entered = threading.Event()
    finished = threading.Event()
    outcome: list[str] = []

    def legacy_start() -> None:
        entered.set()
        try:
            with coordinator.acquire_legacy_claude_start(project_id=PROJECT):
                outcome.append("allowed")
        except WAWConflictError as exc:
            outcome.append(exc.code)
        finished.set()

    thread = threading.Thread(target=legacy_start)
    thread.start()
    assert entered.wait(timeout=1)
    assert not finished.wait(timeout=0.05)
    probe.project_waw = (WAWManagedConflictState.STOPPED,)
    waw_lease.release()
    assert finished.wait(timeout=1)
    thread.join(timeout=1)
    assert outcome == ["allowed"]


def test_legacy_lease_serializes_racing_waw_start_until_recheck() -> None:
    probe = _Probe()
    legacy_coordinator = WAWConflictCoordinator(probe)
    waw_coordinator = WAWConflictCoordinator(probe)
    legacy_lease = legacy_coordinator.acquire_legacy_codex_start()
    entered = threading.Event()
    finished = threading.Event()
    outcome: list[str] = []

    def waw_start() -> None:
        entered.set()
        try:
            with waw_coordinator.acquire_waw_start(project_id=PROJECT, agent_type=AgentType.CLAUDE):
                outcome.append("allowed")
        except WAWConflictError as exc:
            outcome.append(exc.code)
        finished.set()

    thread = threading.Thread(target=waw_start)
    thread.start()
    assert entered.wait(timeout=1)
    assert not finished.wait(timeout=0.05)
    probe.codex = WAWLegacyCodexState.RUNNING
    legacy_lease.release()
    assert finished.wait(timeout=1)
    thread.join(timeout=1)
    assert outcome == ["CODEX_REMOTE_CONFLICT"]


def test_coordinator_has_no_adopt_migrate_or_stop_surface() -> None:
    public = {name for name in dir(WAWConflictCoordinator(_Probe())) if not name.startswith("_")}
    assert public == {
        "acquire_legacy_claude_start",
        "acquire_legacy_codex_start",
        "acquire_waw_start",
    }
