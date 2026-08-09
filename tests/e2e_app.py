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
    CodexCapabilities,
    CodexStatus,
    InstallationType,
    PairCodeResult,
    RemoteActionResult,
    RemoteState,
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

app = create_app(settings, services, E2ECodexRuntime(os.environ["AGENTBOX_E2E_PAIR_CODE"]))
