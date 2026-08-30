from __future__ import annotations

from dataclasses import replace

import pytest
from agentbox_core.waw import AgentType, workspace_id
from agentbox_runtime.claude import managed_session_name
from agentbox_runtime.models import (
    ClaudeSession,
    ClaudeSessionActionResult,
    ClaudeSessionState,
    RuntimeOperationError,
)
from agentbox_runtime.waw_claude_executor import WAWClaudeLifecycleExecutor
from agentbox_runtime.waw_control_server import WAWControlDispatchError
from agentbox_runtime.waw_lifecycle import WAWLifecycleIdentity

PROJECT = "prj_" + "1" * 32
WORKSPACE = workspace_id(PROJECT, AgentType.CLAUDE)
IDENTITY = WAWLifecycleIdentity(
    workspace_id=WORKSPACE,
    project_id=PROJECT,
    agent_type="claude",
    generation="1",
    binding_revision="1",
    binding_digest="a" * 64,
    runtime_host_installation_id="wri_" + "3" * 32,
    runtime_host_installation_revision="1",
)


def _session(state: ClaudeSessionState, *, tmux_running: bool = True) -> ClaudeSession:
    return ClaudeSession(
        project_id=PROJECT,
        display_name="Project A",
        state=state,
        managed=True,
        session_name=managed_session_name(PROJECT),
        attach_command=f"tmux attach-session -t ={managed_session_name(PROJECT)}",
        tmux_running=tmux_running,
    )


class FakeManager:
    def __init__(self, state: ClaudeSessionState = ClaudeSessionState.RUNNING) -> None:
        self.state = state
        self.calls: list[tuple[str, str]] = []

    async def start(self, project: str) -> ClaudeSessionActionResult:
        self.calls.append(("start", project))
        return ClaudeSessionActionResult("started", _session(self.state))

    async def stop(self, project: str) -> ClaudeSessionActionResult:
        self.calls.append(("stop", project))
        return ClaudeSessionActionResult(
            "stopped", _session(ClaudeSessionState.STOPPED, tmux_running=False)
        )

    async def session(self, project: str) -> ClaudeSession:
        self.calls.append(("session", project))
        return _session(self.state, tmux_running=self.state is not ClaudeSessionState.STOPPED)


@pytest.mark.anyio
async def test_maps_start_and_resolves_formal_project() -> None:
    manager = FakeManager(ClaudeSessionState.RUNNING)
    executor = WAWClaudeLifecycleExecutor(
        manager, lambda project_id: "project-a", runtime_epoch="7"
    )
    observation = await executor.start(IDENTITY)
    assert observation.state == "RUNNING"
    assert observation.process_state == "RUNNING"
    assert observation.runtime_epoch == "7"
    assert manager.calls == [("start", "project-a")]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("state", "expected", "reconciliation"),
    [
        (ClaudeSessionState.STOPPED, "STOPPED", "authoritative"),
        (ClaudeSessionState.STARTING, "STARTING", "authoritative"),
        (ClaudeSessionState.NEEDS_INTERACTION, "NEEDS_INTERACTION", "authoritative"),
        (ClaudeSessionState.UNKNOWN, "UNKNOWN", "unknown"),
    ],
)
async def test_maps_status_state_machine(
    state: ClaudeSessionState, expected: str, reconciliation: str
) -> None:
    executor = WAWClaudeLifecycleExecutor(
        FakeManager(state), lambda _project_id: "project-a", runtime_epoch="1"
    )
    observation = await executor.status(IDENTITY)
    assert observation.state == expected
    assert observation.reconciliation_state == reconciliation


@pytest.mark.anyio
async def test_normalizes_collision_and_login_errors() -> None:
    class ErrorManager(FakeManager):
        def __init__(self, code: str) -> None:
            super().__init__()
            self.code = code

        async def start(self, _project: str) -> ClaudeSessionActionResult:
            raise RuntimeOperationError(self.code, "bounded")

    collision = WAWClaudeLifecycleExecutor(
        ErrorManager("CLAUDE_SESSION_COLLISION"), lambda _id: "project-a", runtime_epoch="1"
    )
    assert (await collision.start(IDENTITY)).state == "COLLISION"
    login = WAWClaudeLifecycleExecutor(
        ErrorManager("CLAUDE_UNAUTHENTICATED"), lambda _id: "project-a", runtime_epoch="1"
    )
    assert (await login.start(IDENTITY)).state == "LOGIN_REQUIRED"


@pytest.mark.anyio
async def test_does_not_claim_broken_for_retryable_runtime_failure() -> None:
    class UnavailableManager(FakeManager):
        async def start(self, _project: str) -> ClaudeSessionActionResult:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "temporarily unavailable",
                category="unavailable",
                retryable=True,
            )

    executor = WAWClaudeLifecycleExecutor(
        UnavailableManager(), lambda _id: "project-a", runtime_epoch="1"
    )
    observation = await executor.start(IDENTITY)
    assert observation.state == "UNKNOWN"
    assert observation.reconciliation_state == "reconciliation_required"


@pytest.mark.anyio
async def test_invalid_resolver_result_is_bounded_error() -> None:
    executor = WAWClaudeLifecycleExecutor(FakeManager(), lambda _id: "", runtime_epoch="1")
    with pytest.raises(RuntimeOperationError, match="Formal Project"):
        await executor.start(IDENTITY)


def test_rejects_invalid_runtime_epoch() -> None:
    with pytest.raises(ValueError):
        WAWClaudeLifecycleExecutor(FakeManager(), lambda _id: "project-a", runtime_epoch="01")


@pytest.mark.anyio
async def test_never_executes_claude_manager_for_codex_identity() -> None:
    identity = replace(IDENTITY, agent_type="codex")
    executor = WAWClaudeLifecycleExecutor(FakeManager(), lambda _id: "project-a", runtime_epoch="1")
    with pytest.raises(WAWControlDispatchError, match="WAW_AGENT_UNSUPPORTED"):
        await executor.start(identity)


@pytest.mark.anyio
async def test_rejects_workspace_identity_mismatch_before_manager_call() -> None:
    identity = replace(IDENTITY, workspace_id="aws_" + "9" * 32)
    manager = FakeManager()
    executor = WAWClaudeLifecycleExecutor(manager, lambda _id: "project-a", runtime_epoch="1")
    with pytest.raises(WAWControlDispatchError, match="PROJECT_IDENTITY_CHANGED"):
        await executor.start(identity)
    assert manager.calls == []
