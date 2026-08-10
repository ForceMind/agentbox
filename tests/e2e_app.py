"""Isolated API application used only by the Playwright harness."""

from __future__ import annotations

import os

from agentbox_api.main import create_app
from agentbox_core.configuration import Environment, Settings
from agentbox_core.security import PasswordManager
from agentbox_core.services import build_services
from agentbox_runtime import (
    AuthenticationState,
    CapabilityState,
    ClaudeCapabilities,
    ClaudeSession,
    ClaudeSessionActionResult,
    ClaudeSessionOutput,
    ClaudeSessionState,
    ClaudeStatus,
    CodexCapabilities,
    CodexStatus,
    InstallationType,
    PairCodeResult,
    RemoteActionResult,
    RemoteState,
    WorkspaceState,
)


class E2ECodexRuntime:
    def __init__(self, pair_code: str) -> None:
        self._pair_code = pair_code
        self._remote_state = RemoteState.STOPPED

    async def status(self, request_id: str) -> CodexStatus:
        del request_id
        return CodexStatus(
            installed=True,
            version="0.e2e.fixture",
            selected_executable="/fixture/bin/codex",
            installation_type=InstallationType.STANDALONE,
            authentication=AuthenticationState.UNKNOWN,
            capabilities=CodexCapabilities(
                remote_control=CapabilityState.SUPPORTED,
                start=CapabilityState.SUPPORTED,
                stop=CapabilityState.SUPPORTED,
                pair=CapabilityState.SUPPORTED,
                status=CapabilityState.UNSUPPORTED,
            ),
            remote_state=self._remote_state,
            remote_confidence=(
                "inferred" if self._remote_state is RemoteState.RUNNING else "unknown"
            ),
        )

    async def start_remote(self, request_id: str) -> RemoteActionResult:
        del request_id
        self._remote_state = RemoteState.RUNNING
        return RemoteActionResult("started", self._remote_state)

    async def stop_remote(self, request_id: str) -> RemoteActionResult:
        del request_id
        self._remote_state = RemoteState.STOPPED
        return RemoteActionResult("stopped", self._remote_state)

    async def generate_pair_code(self, request_id: str) -> PairCodeResult:
        del request_id
        return PairCodeResult(self._pair_code)


class E2EClaudeRuntime:
    def __init__(self) -> None:
        self._states = {
            "project-a": ClaudeSessionState.STOPPED,
            "trust-project": ClaudeSessionState.NEEDS_INTERACTION,
        }

    def _session(self, project_id: str) -> ClaudeSession:
        state = self._states[project_id]
        name = f"agentbox-claude-{project_id}-e2efixture"
        return ClaudeSession(
            project_id=project_id,
            display_name="Project A" if project_id == "project-a" else "Trust Project",
            state=state,
            managed=True,
            session_name=name,
            attach_command=f"tmux attach-session -t ={name}",
            workspace_state=(
                WorkspaceState.REQUIRES_USER_CONFIRMATION
                if state is ClaudeSessionState.NEEDS_INTERACTION
                else WorkspaceState.UNKNOWN
            ),
            tmux_running=state is not ClaudeSessionState.STOPPED,
            remote_readiness=("ready" if state is ClaudeSessionState.RUNNING else "unknown"),
        )

    async def status(self, request_id: str) -> ClaudeStatus:
        del request_id
        return ClaudeStatus(
            installed=True,
            version="1.e2e.fixture",
            authentication=AuthenticationState.UNKNOWN,
            capabilities=ClaudeCapabilities(
                remote_control=CapabilityState.SUPPORTED,
                remote_start=CapabilityState.SUPPORTED,
                version=CapabilityState.SUPPORTED,
            ),
            tmux_installed=True,
            tmux_version="3.e2e.fixture",
            managed_sessions=sum(
                state is not ClaudeSessionState.STOPPED for state in self._states.values()
            ),
            unmanaged_sessions=2,
            workspace_interaction_warnings=1,
        )

    async def list_sessions(self, request_id: str) -> tuple[ClaudeSession, ...]:
        del request_id
        return tuple(self._session(project_id) for project_id in self._states)

    async def session(self, request_id: str, project_id: str) -> ClaudeSession:
        del request_id
        return self._session(project_id)

    async def start_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        del request_id
        if self._states[project_id] is not ClaudeSessionState.STOPPED:
            return ClaudeSessionActionResult("already_running", self._session(project_id))
        self._states[project_id] = ClaudeSessionState.RUNNING
        return ClaudeSessionActionResult("started", self._session(project_id))

    async def stop_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        del request_id
        if self._states[project_id] is ClaudeSessionState.STOPPED:
            return ClaudeSessionActionResult("already_stopped", self._session(project_id))
        self._states[project_id] = ClaudeSessionState.STOPPED
        return ClaudeSessionActionResult("stopped", self._session(project_id))

    async def recent_output(self, request_id: str, project_id: str) -> ClaudeSessionOutput:
        del request_id
        session = self._session(project_id)
        return ClaudeSessionOutput(
            project_id,
            session.session_name,
            "CLAUDE-OUTPUT-CANARY",
            truncated=False,
        )


settings = Settings()
if settings.env is not Environment.TEST:
    raise RuntimeError("the Playwright API fixture requires AGENTBOX_ENV=test")

username = os.environ["AGENTBOX_E2E_USERNAME"]
password = os.environ["AGENTBOX_E2E_PASSWORD"]
services = build_services(
    settings,
    password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
)
initialized, _existing_username = services.admin.status()
if not initialized:
    services.admin.initialize(username, password, request_id="req_e2e_bootstrap")

app = create_app(
    settings,
    services,
    E2ECodexRuntime(os.environ["AGENTBOX_E2E_PAIR_CODE"]),
    E2EClaudeRuntime(),
)
