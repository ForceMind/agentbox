"""Thin, fixed-operation tmux adapter with exact managed-session targets."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import (
    ControlledProcessRunner,
    ExecutableIdentity,
    ProcessResult,
    inspect_executable,
    minimal_runtime_environment,
)

SAFE_SESSION_NAME = re.compile(r"\A[A-Za-z0-9_-]{1,80}\Z")
_VERSION = re.compile(r"\btmux\s+([^\s]+)", re.IGNORECASE)


class TmuxAdapter:
    """Expose only the tmux operations required by Claude session management."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        runner: ControlledProcessRunner | None = None,
    ) -> None:
        self._environment = minimal_runtime_environment(environment or os.environ)
        self._runner = runner or ControlledProcessRunner()

    def executable(self) -> ExecutableIdentity | None:
        selected = shutil.which("tmux", path=self._environment.get("PATH", ""))
        if selected is None:
            return None
        try:
            return inspect_executable(Path(selected).absolute(), error_prefix="TMUX")
        except RuntimeOperationError:
            return None

    async def version(self) -> str | None:
        identity = self.executable()
        if identity is None:
            return None
        result = await self._run(identity, ("-V",), allow_nonzero=True)
        match = _VERSION.search(self._text(result))
        return match.group(1)[:64] if result.exit_code == 0 and match else None

    async def list_sessions(self) -> tuple[str, ...]:
        identity = self._require_executable()
        result = await self._run(
            identity,
            ("list-sessions", "-F", "#{session_name}"),
            allow_nonzero=True,
        )
        if result.exit_code != 0:
            text = self._text(result).lower()
            empty_server = (
                "no server running" in text
                or "no sessions" in text
                or "failed to connect" in text
                or ("error connecting to" in text and "no such file" in text)
            )
            if empty_server:
                return ()
            raise RuntimeOperationError("TMUX_LIST_FAILED", "tmux sessions could not be listed")
        sessions: list[str] = []
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            name = line.strip()
            if SAFE_SESSION_NAME.fullmatch(name) and name not in sessions:
                sessions.append(name)
        return tuple(sessions)

    async def has_session(self, session_name: str) -> bool:
        self._validate_name(session_name)
        result = await self._run(
            self._require_executable(),
            ("has-session", "-t", f"={session_name}"),
            allow_nonzero=True,
        )
        if result.exit_code == 0:
            return True
        if result.exit_code == 1:
            return False
        raise RuntimeOperationError("TMUX_STATUS_FAILED", "tmux session state is unavailable")

    async def create_session(
        self,
        session_name: str,
        *,
        cwd: Path,
        command: ExecutableIdentity,
        managed_marker: str,
    ) -> None:
        self._validate_name(session_name)
        self._validate_marker(managed_marker)
        self._validate_cwd(cwd)
        self._validate_command(command)
        holding_command = self._holding_executable()
        # tmux documents that new-session and respawn-pane execute a multi-argument
        # shell-command directly, without sh -c. A short, fingerprinted sleep keeps
        # the pane alive while remain-on-exit is set before Claude starts. This
        # preserves a failed Workspace Trust prompt for explicit terminal attach.
        # Every command and separator below is fixed; callers cannot add tmux argv.
        result = await self._run(
            self._require_executable(),
            (
                "new-session",
                "-d",
                "-s",
                session_name,
                "-c",
                str(cwd),
                "-e",
                f"AGENTBOX_MANAGED_SESSION={managed_marker}",
                str(holding_command.path),
                "30",
                ";",
                "set-window-option",
                "-t",
                f"={session_name}:0",
                "remain-on-exit",
                "on",
                ";",
                "respawn-pane",
                "-k",
                "-t",
                f"={session_name}:0.0",
                "-c",
                str(cwd),
                str(command.path),
                "remote-control",
            ),
            allow_nonzero=True,
            timeout=10,
        )
        if result.exit_code != 0:
            # A partial command sequence can leave only the exact session that
            # this call atomically marked. Best-effort cleanup never targets an
            # unmarked/colliding session; a surviving marked session remains
            # visible and safely stoppable after a Runtime restart.
            with contextlib.suppress(RuntimeOperationError):
                if await self.has_session(session_name) and await self.is_managed(
                    session_name, managed_marker
                ):
                    await self.kill_session(session_name)
            raise RuntimeOperationError(
                "CLAUDE_SESSION_START_FAILED", "Claude tmux session could not be created"
            )

    async def pane_dead(self, session_name: str) -> bool:
        self._validate_name(session_name)
        result = await self._run(
            self._require_executable(),
            ("display-message", "-p", "-t", f"={session_name}:0.0", "#{pane_dead}"),
            allow_nonzero=True,
        )
        value = result.stdout.decode("utf-8", errors="replace").strip()
        if result.exit_code != 0 or value not in {"0", "1"}:
            raise RuntimeOperationError(
                "CLAUDE_SESSION_STATE_UNAVAILABLE",
                "Claude session pane state is unavailable",
                category="unavailable",
            )
        return value == "1"

    async def prepare_workspace_interaction(
        self,
        session_name: str,
        *,
        cwd: Path,
        command: ExecutableIdentity,
    ) -> None:
        """Start public interactive Claude for manual Trust input, never acceptance."""
        self._validate_name(session_name)
        self._validate_cwd(cwd)
        self._validate_command(command)
        # The fixed `--` keeps this a multi-argument tmux command, so tmux
        # executes Claude directly instead of treating a single argument as sh -c.
        result = await self._run(
            self._require_executable(),
            (
                "respawn-pane",
                "-k",
                "-t",
                f"={session_name}:0.0",
                "-c",
                str(cwd),
                str(command.path),
                "--",
            ),
            allow_nonzero=True,
            timeout=10,
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "CLAUDE_WORKSPACE_INTERACTION_FAILED",
                "Claude Workspace Trust interaction could not be prepared",
            )

    async def is_managed(self, session_name: str, managed_marker: str) -> bool:
        self._validate_name(session_name)
        self._validate_marker(managed_marker)
        result = await self._run(
            self._require_executable(),
            (
                "show-environment",
                "-t",
                f"={session_name}",
                "AGENTBOX_MANAGED_SESSION",
            ),
            allow_nonzero=True,
        )
        if result.exit_code != 0:
            return False
        value = result.stdout.decode("utf-8", errors="replace").strip()
        return value == f"AGENTBOX_MANAGED_SESSION={managed_marker}"

    async def capture_pane(self, session_name: str, *, lines: int = 200) -> bytes:
        self._validate_name(session_name)
        if not 1 <= lines <= 200:
            raise ValueError("capture line limit must be between 1 and 200")
        result = await self._run(
            self._require_executable(),
            (
                "capture-pane",
                "-p",
                "-t",
                f"={session_name}:0.0",
                "-S",
                f"-{lines}",
            ),
            allow_nonzero=True,
            stdout_limit=48 * 1024,
            sensitive_output=True,
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "CLAUDE_SESSION_OUTPUT_UNAVAILABLE",
                "Claude session output is unavailable",
                category="unavailable",
            )
        return result.stdout

    async def kill_session(self, session_name: str) -> bool:
        self._validate_name(session_name)
        if not await self.has_session(session_name):
            return False
        result = await self._run(
            self._require_executable(),
            ("kill-session", "-t", f"={session_name}"),
            allow_nonzero=True,
            timeout=10,
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "CLAUDE_SESSION_STOP_FAILED", "Claude tmux session could not be stopped"
            )
        return True

    async def write_input(self, session_name: str, data: bytes) -> None:
        """Deliver bounded opaque bytes through a fixed tmux buffer path.

        ``send-keys`` treats its arguments as key names and therefore cannot
        safely carry arbitrary terminal bytes.  Loading a bounded stdin buffer
        and pasting it to the exact managed pane keeps the caller payload out
        of argv and out of shell parsing.  The buffer name is derived solely
        from the already validated session name and is deleted by paste.
        """

        self._validate_name(session_name)
        if not isinstance(data, bytes) or not data or len(data) > 16 * 1024:
            raise RuntimeOperationError(
                "TMUX_INPUT_INVALID",
                "tmux input is outside the fixed byte limit",
                category="validation",
            )
        if not await self.has_session(session_name):
            raise RuntimeOperationError(
                "TMUX_SESSION_UNAVAILABLE", "tmux session is unavailable", category="unavailable"
            )
        buffer_name = self._input_buffer_name(session_name)
        loaded = await self._run(
            self._require_executable(),
            ("load-buffer", "-b", buffer_name, "-"),
            allow_nonzero=True,
            timeout=5,
            stdin_data=data,
        )
        if loaded.exit_code != 0:
            raise RuntimeOperationError(
                "TMUX_INPUT_FAILED", "tmux input buffer could not be loaded", category="broken"
            )
        pasted = await self._run(
            self._require_executable(),
            (
                "paste-buffer",
                "-d",
                "-b",
                buffer_name,
                "-t",
                f"={session_name}:0.0",
            ),
            allow_nonzero=True,
            timeout=5,
        )
        if pasted.exit_code != 0:
            raise RuntimeOperationError(
                "TMUX_INPUT_FAILED", "tmux input buffer could not be pasted", category="broken"
            )

    async def resize_window(self, session_name: str, *, columns: int, rows: int) -> None:
        """Resize only the exact managed pane using bounded geometry."""

        self._validate_name(session_name)
        if type(columns) is not int or not 8 <= columns <= 240:
            raise RuntimeOperationError(
                "TMUX_GEOMETRY_INVALID",
                "tmux columns are outside the fixed limit",
                category="validation",
            )
        if type(rows) is not int or not 1 <= rows <= 200:
            raise RuntimeOperationError(
                "TMUX_GEOMETRY_INVALID",
                "tmux rows are outside the fixed limit",
                category="validation",
            )
        if not await self.has_session(session_name):
            raise RuntimeOperationError(
                "TMUX_SESSION_UNAVAILABLE", "tmux session is unavailable", category="unavailable"
            )
        result = await self._run(
            self._require_executable(),
            (
                "resize-window",
                "-t",
                f"={session_name}:0",
                "-x",
                str(columns),
                "-y",
                str(rows),
            ),
            allow_nonzero=True,
            timeout=5,
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "TMUX_RESIZE_FAILED", "tmux window could not be resized", category="broken"
            )

    def _require_executable(self) -> ExecutableIdentity:
        identity = self.executable()
        if identity is None:
            raise RuntimeOperationError(
                "TMUX_NOT_INSTALLED", "tmux is not available", category="unavailable"
            )
        return identity

    def _holding_executable(self) -> ExecutableIdentity:
        selected = shutil.which("sleep", path=self._environment.get("PATH", ""))
        if selected is None:
            raise RuntimeOperationError(
                "TMUX_HOLD_EXECUTABLE_INVALID",
                "The fixed tmux holding command is unavailable",
                category="unavailable",
            )
        return inspect_executable(Path(selected).absolute(), error_prefix="TMUX_HOLD")

    @staticmethod
    def _validate_cwd(cwd: Path) -> None:
        try:
            resolved_cwd = cwd.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise RuntimeOperationError(
                "CLAUDE_PROJECT_INVALID", "Project directory is invalid", category="validation"
            ) from exc
        if not cwd.is_absolute() or cwd.is_symlink() or resolved_cwd != cwd or not cwd.is_dir():
            raise RuntimeOperationError(
                "CLAUDE_PROJECT_INVALID", "Project directory is invalid", category="validation"
            )

    @staticmethod
    def _validate_command(command: ExecutableIdentity) -> None:
        if inspect_executable(command.path, error_prefix="CLAUDE") != command:
            raise RuntimeOperationError(
                "CLAUDE_EXECUTABLE_CHANGED",
                "Claude executable changed after detection",
                category="conflict",
            )

    async def _run(
        self,
        identity: ExecutableIdentity,
        arguments: tuple[str, ...],
        *,
        allow_nonzero: bool,
        timeout: float = 5,
        stdout_limit: int = 16 * 1024,
        sensitive_output: bool = False,
        stdin_data: bytes | None = None,
    ) -> ProcessResult:
        if stdin_data is None:
            result = await self._runner.run(
                identity,
                arguments,
                environment=self._environment,
                cwd=Path(self._environment.get("HOME", "/")),
                timeout_seconds=timeout,
                stdout_limit=stdout_limit,
                stderr_limit=8192,
                sensitive_output=sensitive_output,
                error_prefix="TMUX",
            )
        else:
            result = await self._runner.run(
                identity,
                arguments,
                environment=self._environment,
                cwd=Path(self._environment.get("HOME", "/")),
                timeout_seconds=timeout,
                stdout_limit=stdout_limit,
                stderr_limit=8192,
                sensitive_output=sensitive_output,
                stdin_data=stdin_data,
                error_prefix="TMUX",
            )
        if result.exit_code != 0 and not allow_nonzero:
            raise RuntimeOperationError("TMUX_COMMAND_FAILED", "tmux command failed")
        return result

    @staticmethod
    def _validate_name(session_name: str) -> None:
        if not SAFE_SESSION_NAME.fullmatch(session_name):
            raise RuntimeOperationError(
                "TMUX_SESSION_NAME_INVALID", "tmux session name is invalid", category="validation"
            )

    @staticmethod
    def _validate_marker(marker: str) -> None:
        if not re.fullmatch(r"(?:v1:[a-f0-9]{16}|waw-v1:wri_[0-9a-f]{32}:[0-9a-f]{32})", marker):
            raise RuntimeOperationError(
                "TMUX_SESSION_MARKER_INVALID",
                "tmux session marker is invalid",
                category="validation",
            )

    @staticmethod
    def _input_buffer_name(session_name: str) -> str:
        """Derive a bounded tmux buffer name without exposing caller text."""

        # Session names are already closed to ASCII ``[A-Za-z0-9_-]``.  Keep
        # the prefix fixed and bound the result for tmux's buffer namespace.
        return f"agentbox-waw-input-{session_name}"[:120]

    @staticmethod
    def _text(result: ProcessResult) -> str:
        return (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")
