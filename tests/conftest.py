from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_core.clock import Clock
from agentbox_core.configuration import Environment, Settings
from agentbox_core.security import PasswordManager
from agentbox_core.services import ControlPlaneServices, build_services
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
from alembic import command
from alembic.config import Config
from pydantic import SecretStr


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class FakeClock(Clock):
    current: datetime = datetime(2026, 8, 9, 0, 0, 0)

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


class FakeCodexRuntime:
    def __init__(self, pair_code: str = "PAIR-SECRET-CANARY-API-9Q2X") -> None:
        self.pair_code = pair_code
        self.remote_state = RemoteState.STOPPED
        self.calls: list[str] = []

    async def status(self, request_id: str) -> CodexStatus:
        del request_id
        self.calls.append("status")
        return CodexStatus(
            installed=True,
            version="0.test.fixture",
            selected_executable="/fixture/bin/codex",
            installation_type=InstallationType.STANDALONE,
            authentication=AuthenticationState.AUTHENTICATED,
            capabilities=CodexCapabilities(
                remote_control=CapabilityState.SUPPORTED,
                start=CapabilityState.SUPPORTED,
                stop=CapabilityState.SUPPORTED,
                pair=CapabilityState.SUPPORTED,
                status=CapabilityState.UNSUPPORTED,
            ),
            remote_state=self.remote_state,
            remote_confidence=(
                "inferred" if self.remote_state is RemoteState.RUNNING else "unknown"
            ),
        )

    async def start_remote(self, request_id: str) -> RemoteActionResult:
        del request_id
        self.calls.append("start")
        self.remote_state = RemoteState.RUNNING
        return RemoteActionResult("started", self.remote_state)

    async def stop_remote(self, request_id: str) -> RemoteActionResult:
        del request_id
        self.calls.append("stop")
        self.remote_state = RemoteState.STOPPED
        return RemoteActionResult("stopped", self.remote_state)

    async def generate_pair_code(self, request_id: str) -> PairCodeResult:
        del request_id
        self.calls.append("pair")
        return PairCodeResult(self.pair_code)


class FakeClaudeRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.states: dict[str, ClaudeSessionState] = {
            "project-a": ClaudeSessionState.STOPPED,
            "trust-project": ClaudeSessionState.NEEDS_INTERACTION,
        }
        self.output_canary = "CLAUDE-OUTPUT-CANARY"

    def _session(self, project_id: str) -> ClaudeSession:
        state = self.states.get(project_id, ClaudeSessionState.STOPPED)
        session_name = f"agentbox-claude-{project_id}-fixture"
        return ClaudeSession(
            project_id=project_id,
            display_name=project_id,
            state=state,
            managed=True,
            session_name=session_name,
            attach_command=f"tmux attach-session -t ={session_name}",
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
        self.calls.append("status")
        return ClaudeStatus(
            installed=True,
            version="1.test.fixture",
            authentication=AuthenticationState.UNKNOWN,
            capabilities=ClaudeCapabilities(
                remote_control=CapabilityState.SUPPORTED,
                remote_start=CapabilityState.SUPPORTED,
                version=CapabilityState.SUPPORTED,
            ),
            tmux_installed=True,
            tmux_version="3.test.fixture",
            managed_sessions=sum(
                state is not ClaudeSessionState.STOPPED for state in self.states.values()
            ),
            unmanaged_sessions=2,
            workspace_interaction_warnings=1,
        )

    async def list_sessions(self, request_id: str) -> tuple[ClaudeSession, ...]:
        del request_id
        self.calls.append("list")
        return tuple(self._session(project_id) for project_id in self.states)

    async def session(self, request_id: str, project_id: str) -> ClaudeSession:
        del request_id
        self.calls.append(f"session:{project_id}")
        return self._session(project_id)

    async def start_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        del request_id
        self.calls.append(f"start:{project_id}")
        if self.states.get(project_id) is ClaudeSessionState.RUNNING:
            return ClaudeSessionActionResult("already_running", self._session(project_id))
        self.states[project_id] = ClaudeSessionState.RUNNING
        return ClaudeSessionActionResult("started", self._session(project_id))

    async def stop_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        del request_id
        self.calls.append(f"stop:{project_id}")
        if self.states.get(project_id) is ClaudeSessionState.STOPPED:
            return ClaudeSessionActionResult("already_stopped", self._session(project_id))
        self.states[project_id] = ClaudeSessionState.STOPPED
        return ClaudeSessionActionResult("stopped", self._session(project_id))

    async def recent_output(self, request_id: str, project_id: str) -> ClaudeSessionOutput:
        del request_id
        self.calls.append(f"output:{project_id}")
        session = self._session(project_id)
        return ClaudeSessionOutput(
            project_id, session.session_name, self.output_canary, truncated=False
        )


def migrate_database(database_url: str, revision: str = "head") -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, revision)


def downgrade_database(database_url: str, revision: str = "-1") -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, revision)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        env=Environment.TEST,
        database_url=f"sqlite+pysqlite:///{data_dir / 'agentbox.db'}",
        data_dir=data_dir,
        secret_key=SecretStr("test-only-secret-key-with-at-least-thirty-two-bytes"),
        session_ttl=3600,
        session_idle_ttl=600,
        session_retention=60,
        login_rate_limit=5,
        login_rate_window=300,
        login_lock_duration=300,
        argon2_max_concurrency=2,
        recent_auth_ttl=60,
        allowed_origins=("http://testserver",),
    )


@pytest.fixture
def password_manager() -> PasswordManager:
    return PasswordManager(time_cost=1, memory_cost=8192, parallelism=1)


@pytest.fixture
def services(
    settings: Settings,
    clock: FakeClock,
    password_manager: PasswordManager,
) -> Iterator[ControlPlaneServices]:
    migrate_database(settings.database_url)
    value = build_services(settings, clock=clock, password_manager=password_manager)
    yield value
    value.database.close()


@pytest.fixture
def initialized_services(services: ControlPlaneServices) -> ControlPlaneServices:
    services.admin.initialize("maintainer", "a sufficiently long passphrase")
    return services


@pytest.fixture
def codex_runtime() -> FakeCodexRuntime:
    return FakeCodexRuntime()


@pytest.fixture
def claude_runtime() -> FakeClaudeRuntime:
    return FakeClaudeRuntime()


@pytest.fixture
async def client(
    settings: Settings,
    initialized_services: ControlPlaneServices,
    codex_runtime: FakeCodexRuntime,
    claude_runtime: FakeClaudeRuntime,
) -> AsyncIterator[httpx.AsyncClient]:
    application = create_app(settings, initialized_services, codex_runtime, claude_runtime)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.fixture
def origin_headers() -> dict[str, str]:
    return {"Origin": "http://testserver"}
