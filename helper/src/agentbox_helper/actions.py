"""Fixed executable and argv mapping for root-only Helper actions."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass

from agentbox_helper.protocol import HelperAction

SYSTEMCTL = "/usr/bin/systemctl"
AGENTBOX_SERVICES = (
    "agentbox-runtime.service",
    "agentbox-worker.service",
    "agentbox-api.service",
)
AGENTBOX_ENABLE_UNITS = (*AGENTBOX_SERVICES, "agentbox-helper.socket")


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    code: str
    message: str


def action_argv(action: HelperAction) -> tuple[str, ...]:
    mapping = {
        HelperAction.SYSTEMD_DAEMON_RELOAD: (SYSTEMCTL, "daemon-reload"),
        HelperAction.SYSTEMD_START_AGENTBOX: (SYSTEMCTL, "start", *AGENTBOX_SERVICES),
        HelperAction.SYSTEMD_STOP_AGENTBOX: (
            SYSTEMCTL,
            "stop",
            *reversed(AGENTBOX_SERVICES),
        ),
        HelperAction.SYSTEMD_RESTART_AGENTBOX: (SYSTEMCTL, "restart", *AGENTBOX_SERVICES),
        HelperAction.SYSTEMD_ENABLE_AGENTBOX: (SYSTEMCTL, "enable", *AGENTBOX_ENABLE_UNITS),
        HelperAction.SYSTEMD_DISABLE_AGENTBOX: (SYSTEMCTL, "disable", *AGENTBOX_ENABLE_UNITS),
    }
    return mapping[action]


class FixedActionRunner:
    async def run(self, action: HelperAction) -> ActionResult:
        argv = action_argv(action)
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        }
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd="/",
                env=environment,
                start_new_session=True,
            )
            return_code = await asyncio.wait_for(process.wait(), timeout=30)
        except TimeoutError:
            if "process" in locals() and process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            return ActionResult(False, "HELPER_ACTION_TIMEOUT", "AgentBox action timed out")
        except OSError:
            return ActionResult(False, "HELPER_ACTION_UNAVAILABLE", "AgentBox action unavailable")
        if return_code != os.EX_OK:
            return ActionResult(False, "HELPER_ACTION_FAILED", "AgentBox action failed")
        return ActionResult(True, "HELPER_ACTION_SUCCEEDED", "AgentBox action completed")
