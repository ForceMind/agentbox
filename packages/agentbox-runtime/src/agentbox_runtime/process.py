"""Strict subprocess boundary used only by Runtime adapters."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox_runtime.models import RuntimeOperationError

if TYPE_CHECKING:
    from agentbox_runtime.git_staged_snapshot import StagedGitSnapshot

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
        "GIT_ALLOW_PROTOCOL",
        "GIT_ASKPASS",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_EDITOR",
        "GIT_LFS_SKIP_SMUDGE",
        "GIT_PAGER",
        "GIT_SEQUENCE_EDITOR",
        "GIT_TERMINAL_PROMPT",
        "GCM_INTERACTIVE",
        "GH_PAGER",
        "GH_PROMPT_DISABLED",
        "PAGER",
        "SSH_ASKPASS",
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


def inspect_executable(path: Path, *, error_prefix: str = "CODEX") -> ExecutableIdentity:
    if not path.is_absolute():
        raise RuntimeOperationError(
            f"{error_prefix}_EXECUTABLE_INVALID",
            "Runtime executable is invalid",
            category="unavailable",
        )
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
        parent_details = resolved.parent.stat()
    except (OSError, RuntimeError) as exc:
        raise RuntimeOperationError(
            f"{error_prefix}_EXECUTABLE_INVALID",
            "Runtime executable is unavailable",
            category="unavailable",
        ) from exc
    if not stat.S_ISREG(details.st_mode) or not os.access(resolved, os.X_OK):
        raise RuntimeOperationError(
            f"{error_prefix}_EXECUTABLE_INVALID",
            "Runtime executable is invalid",
            category="unavailable",
        )
    if details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeOperationError(
            f"{error_prefix}_EXECUTABLE_INVALID",
            "Runtime executable permissions are unsafe",
            category="broken",
        )
    if parent_details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeOperationError(
            f"{error_prefix}_EXECUTABLE_INVALID",
            "Runtime executable directory permissions are unsafe",
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
        stdin_data: bytes | None = None,
        error_prefix: str = "CODEX",
    ) -> ProcessResult:
        return await self._run_internal(
            executable,
            arguments,
            environment=environment,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            stdout_limit=stdout_limit,
            stderr_limit=stderr_limit,
            sensitive_output=sensitive_output,
            stdin_data=stdin_data,
            error_prefix=error_prefix,
            pass_fds=(),
        )

    async def run_with_cwd_fd(
        self,
        executable: ExecutableIdentity,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        cwd_directory_fd: int,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        sensitive_output: bool = False,
        stdin_data: bytes | None = None,
        error_prefix: str = "GIT",
        staged_git_inputs: StagedGitSnapshot | None = None,
    ) -> ProcessResult:
        """Bind a fixed child cwd to a caller-held directory on Linux only.

        The caller must separately prove Project/repository authority. This
        method does not select an executable, argv, file or content action.
        """

        if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
            raise RuntimeOperationError(
                f"{error_prefix}_WORKING_DIRECTORY_UNAVAILABLE",
                "Descriptor-bound working directory is unavailable",
                category="unavailable",
            )
        if type(cwd_directory_fd) is not int or cwd_directory_fd < 0 or not cwd.is_absolute():
            raise RuntimeOperationError(
                f"{error_prefix}_WORKING_DIRECTORY_INVALID",
                "Descriptor-bound working directory is invalid",
                category="validation",
            )
        from agentbox_runtime.git_staged_snapshot import StagedGitSnapshot

        if staged_git_inputs is not None and type(staged_git_inputs) is not StagedGitSnapshot:
            raise TypeError("fixed staged Git input owner is required")
        if staged_git_inputs is not None and (
            cwd != staged_git_inputs.path
            or cwd_directory_fd != staged_git_inputs.directory_fd
            or error_prefix != "GIT"
        ):
            raise ValueError("staged Git inputs require their own fixed directory")
        input_fds = () if staged_git_inputs is None else staged_git_inputs.input_fds
        if len(input_fds) > 512:
            raise ValueError("staged Git input descriptor limit exceeded")
        try:
            held_fd = os.dup(cwd_directory_fd)
        except OSError as exc:
            raise RuntimeOperationError(
                f"{error_prefix}_WORKING_DIRECTORY_INVALID",
                "Descriptor-bound working directory is invalid",
                category="validation",
            ) from exc
        try:
            identity = self._checked_cwd_identity(held_fd, cwd, error_prefix=error_prefix)
            proc_cwd = Path(f"/proc/self/fd/{held_fd}")
            if self._stat_identity(os.stat(proc_cwd)) != identity:
                raise RuntimeOperationError(
                    f"{error_prefix}_WORKING_DIRECTORY_CHANGED",
                    "Descriptor-bound working directory changed",
                    category="conflict",
                )
            result = await self._run_internal(
                executable,
                arguments,
                environment=environment,
                cwd=proc_cwd,
                timeout_seconds=timeout_seconds,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
                sensitive_output=sensitive_output,
                stdin_data=stdin_data,
                error_prefix=error_prefix,
                pass_fds=(held_fd, *input_fds),
            )
            if self._checked_cwd_identity(held_fd, cwd, error_prefix=error_prefix) != identity:
                raise RuntimeOperationError(
                    f"{error_prefix}_WORKING_DIRECTORY_CHANGED",
                    "Descriptor-bound working directory changed",
                    category="conflict",
                )
            return result
        except OSError as exc:
            raise RuntimeOperationError(
                f"{error_prefix}_WORKING_DIRECTORY_CHANGED",
                "Descriptor-bound working directory changed",
                category="conflict",
            ) from exc
        finally:
            os.close(held_fd)

    @staticmethod
    def _stat_identity(details: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            details.st_dev,
            details.st_ino,
            details.st_uid,
            details.st_gid,
            details.st_mode,
        )

    @classmethod
    def _checked_cwd_identity(
        cls, descriptor: int, cwd: Path, *, error_prefix: str
    ) -> tuple[int, int, int, int, int]:
        held = os.fstat(descriptor)
        named = os.stat(cwd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(held.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or held.st_uid != os.geteuid()
            or held.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or cls._stat_identity(held) != cls._stat_identity(named)
        ):
            raise RuntimeOperationError(
                f"{error_prefix}_WORKING_DIRECTORY_CHANGED",
                "Descriptor-bound working directory changed",
                category="conflict",
            )
        return cls._stat_identity(held)

    async def _run_internal(
        self,
        executable: ExecutableIdentity,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
        sensitive_output: bool,
        stdin_data: bytes | None,
        error_prefix: str,
        pass_fds: tuple[int, ...],
    ) -> ProcessResult:
        del sensitive_output  # Classification is consumed by callers/log policy, never logged here.
        if timeout_seconds <= 0 or stdout_limit < 1 or stderr_limit < 1:
            raise ValueError("process limits must be positive")
        if stdin_data is not None and len(stdin_data) > 16 * 1024:
            raise ValueError("process stdin exceeds its fixed limit")
        current = inspect_executable(executable.path, error_prefix=error_prefix)
        if current != executable:
            raise RuntimeOperationError(
                f"{error_prefix}_EXECUTABLE_CHANGED",
                "Runtime executable changed after detection",
                category="conflict",
            )
        if not cwd.is_absolute() or not cwd.is_dir():
            raise RuntimeOperationError(
                f"{error_prefix}_WORKING_DIRECTORY_INVALID",
                "Runtime working directory is unavailable",
                category="unavailable",
            )
        argv = (str(current.path), *arguments)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                env=minimal_runtime_environment(environment),
                stdin=(
                    asyncio.subprocess.PIPE
                    if stdin_data is not None
                    else asyncio.subprocess.DEVNULL
                ),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                pass_fds=pass_fds,
            )
        except OSError as exc:
            raise RuntimeOperationError(
                f"{error_prefix}_EXECUTABLE_INVALID",
                "Runtime command could not start",
                category="unavailable",
            ) from exc

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_task = asyncio.create_task(
            self._read_bounded(process.stdout, stdout_limit, error_prefix=error_prefix)
        )
        stderr_task = asyncio.create_task(
            self._read_bounded(process.stderr, stderr_limit, error_prefix=error_prefix)
        )
        wait_task = asyncio.create_task(process.wait())
        try:
            if stdin_data is not None:
                assert process.stdin is not None
                try:
                    process.stdin.write(stdin_data)
                    await asyncio.wait_for(process.stdin.drain(), timeout=1)
                except (BrokenPipeError, ConnectionResetError, TimeoutError) as exc:
                    raise RuntimeOperationError(
                        f"{error_prefix}_STDIN_FAILED",
                        "Runtime command input could not be delivered",
                        category="broken",
                    ) from exc
                process.stdin.close()
            stdout, stderr, exit_code = await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task, wait_task),
                timeout=timeout_seconds,
            )
        except asyncio.CancelledError:
            await self._terminate(process)
            await self._finish_tasks(stdout_task, stderr_task, wait_task)
            raise
        except TimeoutError as exc:
            await self._terminate(process)
            await self._finish_tasks(stdout_task, stderr_task, wait_task)
            raise RuntimeOperationError(
                f"{error_prefix}_COMMAND_TIMEOUT",
                "Runtime command timed out",
                category="timeout",
                retryable=True,
            ) from exc
        except RuntimeOperationError:
            await self._terminate(process)
            await self._finish_tasks(stdout_task, stderr_task, wait_task)
            raise
        finally:
            if process.stdin is not None and not process.stdin.is_closing():
                process.stdin.close()
        return ProcessResult(argv=argv, exit_code=exit_code, stdout=stdout, stderr=stderr)

    async def _read_bounded(
        self, stream: asyncio.StreamReader, limit: int, *, error_prefix: str
    ) -> bytes:
        result = bytearray()
        while True:
            chunk = await stream.read(min(4096, limit + 1))
            if not chunk:
                return bytes(result)
            result.extend(chunk)
            if len(result) > limit:
                raise RuntimeOperationError(
                    f"{error_prefix}_OUTPUT_LIMIT_EXCEEDED",
                    "Runtime command exceeded its output limit",
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
