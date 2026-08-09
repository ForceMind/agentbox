"""Strict subprocess boundary used only by Runtime adapters."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agentbox_runtime.models import RuntimeOperationError

ALLOWED_ENVIRONMENT = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "TERM",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
    }
)


@dataclass(frozen=True)
class ExecutableIdentity:
    path: Path
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: bytes
    stderr: bytes


def minimal_runtime_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Copy only Runtime essentials; credentials are intentionally omitted."""
    environment = {
        key: value
        for key, value in source.items()
        if key in ALLOWED_ENVIRONMENT and "\x00" not in value
    }
    raw_path = environment.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    path_entries: list[str] = []
    for entry in raw_path.split(os.pathsep):
        if entry and Path(entry).is_absolute() and entry not in path_entries:
            path_entries.append(entry)
    environment["PATH"] = os.pathsep.join(path_entries) or "/usr/local/bin:/usr/bin:/bin"
    environment.setdefault("LANG", "C.UTF-8")
    return environment


def inspect_executable(path: Path) -> ExecutableIdentity:
    if not path.is_absolute():
        raise RuntimeOperationError(
            "CODEX_EXECUTABLE_INVALID", "Codex executable is invalid", category="unavailable"
        )
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
        parent_details = resolved.parent.stat()
    except (OSError, RuntimeError) as exc:
        raise RuntimeOperationError(
            "CODEX_EXECUTABLE_INVALID", "Codex executable is unavailable", category="unavailable"
        ) from exc
    if not stat.S_ISREG(details.st_mode) or not os.access(resolved, os.X_OK):
        raise RuntimeOperationError(
            "CODEX_EXECUTABLE_INVALID", "Codex executable is invalid", category="unavailable"
        )
    if details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeOperationError(
            "CODEX_EXECUTABLE_INVALID",
            "Codex executable permissions are unsafe",
            category="broken",
        )
    if parent_details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeOperationError(
            "CODEX_EXECUTABLE_INVALID",
            "Codex executable directory permissions are unsafe",
            category="broken",
        )
    return ExecutableIdentity(
        path=resolved,
        device=details.st_dev,
        inode=details.st_ino,
        mode=details.st_mode,
        size=details.st_size,
        modified_ns=details.st_mtime_ns,
    )


class ControlledProcessRunner:
    """Execute a prebuilt argv without a shell, with hard resource bounds."""

    def __init__(self, *, terminate_grace_seconds: float = 1.0) -> None:
        self._terminate_grace_seconds = terminate_grace_seconds

    async def run(
        self,
        executable: ExecutableIdentity,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        sensitive_output: bool = False,
    ) -> ProcessResult:
        del sensitive_output  # Classification is consumed by callers/log policy, never logged here.
        if timeout_seconds <= 0 or stdout_limit < 1 or stderr_limit < 1:
            raise ValueError("process limits must be positive")
        current = inspect_executable(executable.path)
        if current != executable:
            raise RuntimeOperationError(
                "CODEX_EXECUTABLE_CHANGED",
                "Codex executable changed after detection",
                category="conflict",
            )
        if not cwd.is_absolute() or not cwd.is_dir():
            raise RuntimeOperationError(
                "CODEX_WORKING_DIRECTORY_INVALID",
                "Codex working directory is unavailable",
                category="unavailable",
            )
        argv = (str(current.path), *arguments)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                env=minimal_runtime_environment(environment),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            raise RuntimeOperationError(
                "CODEX_EXECUTABLE_INVALID", "Codex command could not start", category="unavailable"
            ) from exc

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_task = asyncio.create_task(self._read_bounded(process.stdout, stdout_limit))
        stderr_task = asyncio.create_task(self._read_bounded(process.stderr, stderr_limit))
        wait_task = asyncio.create_task(process.wait())
        try:
            stdout, stderr, exit_code = await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task, wait_task),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            await self._terminate(process)
            await self._finish_tasks(stdout_task, stderr_task, wait_task)
            raise RuntimeOperationError(
                "CODEX_COMMAND_TIMEOUT",
                "Codex command timed out",
                category="timeout",
                retryable=True,
            ) from exc
        except RuntimeOperationError:
            await self._terminate(process)
            await self._finish_tasks(stdout_task, stderr_task, wait_task)
            raise
        return ProcessResult(argv=argv, exit_code=exit_code, stdout=stdout, stderr=stderr)

    async def _read_bounded(self, stream: asyncio.StreamReader, limit: int) -> bytes:
        result = bytearray()
        while True:
            chunk = await stream.read(min(4096, limit + 1))
            if not chunk:
                return bytes(result)
            result.extend(chunk)
            if len(result) > limit:
                raise RuntimeOperationError(
                    "CODEX_OUTPUT_LIMIT_EXCEEDED",
                    "Codex command exceeded its output limit",
                    category="broken",
                )

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=self._terminate_grace_seconds)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()

    @staticmethod
    async def _finish_tasks(*tasks: asyncio.Task[object]) -> None:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
