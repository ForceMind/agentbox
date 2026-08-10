"""Versioned, bounded Unix-socket client for the non-root Runtime Executor."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agentbox_runtime.models import (
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
    DiagnosticFinding,
    GitActionResult,
    GitBranch,
    GitHubProjectStatus,
    GitHubPullRequestResult,
    GitHubStatus,
    GitInstallationStatus,
    GitStatus,
    InstallationType,
    PairCodeResult,
    ProjectWorkspace,
    RemoteActionResult,
    RemoteState,
    RuntimeOperationError,
    WorkspaceState,
)

RUNTIME_PROTOCOL_VERSION = 1
MAX_RUNTIME_FRAME = 64 * 1024

# A complete status probe can sequentially consume up to 58 seconds across the
# public Codex version/help/login/npm/status commands. A mutation can then use a
# further 30 seconds for the fixed start/stop/Pair command. Keep the RPC budgets
# above those adapter bounds so the caller does not time out while a mutation is
# still able to take effect in the Runtime Executor.
DEFAULT_CODEX_STATUS_RPC_TIMEOUT_SECONDS = 70.0
DEFAULT_CODEX_MUTATION_RPC_TIMEOUT_SECONDS = 100.0
DEFAULT_CLAUDE_STATUS_RPC_TIMEOUT_SECONDS = 35.0
DEFAULT_CLAUDE_MUTATION_RPC_TIMEOUT_SECONDS = 35.0


@runtime_checkable
class CodexRuntimeClient(Protocol):
    async def status(self, request_id: str) -> CodexStatus: ...

    async def start_remote(self, request_id: str) -> RemoteActionResult: ...

    async def stop_remote(self, request_id: str) -> RemoteActionResult: ...

    async def generate_pair_code(self, request_id: str) -> PairCodeResult: ...


@runtime_checkable
class ClaudeRuntimeClient(Protocol):
    async def status(self, request_id: str) -> ClaudeStatus: ...

    async def list_sessions(self, request_id: str) -> tuple[ClaudeSession, ...]: ...

    async def session(self, request_id: str, project_id: str) -> ClaudeSession: ...

    async def start_session(
        self, request_id: str, project_id: str
    ) -> ClaudeSessionActionResult: ...

    async def stop_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult: ...

    async def recent_output(self, request_id: str, project_id: str) -> ClaudeSessionOutput: ...


@runtime_checkable
class ProjectRuntimeClient(Protocol):
    async def list_workspaces(self, request_id: str) -> tuple[ProjectWorkspace, ...]: ...
    async def create_workspace(
        self, request_id: str, project_key: str, operation_id: str
    ) -> GitActionResult: ...
    async def clone_workspace(
        self, request_id: str, project_key: str, operation_id: str, repository_url: str
    ) -> GitActionResult: ...
    async def finalize_workspace(
        self, request_id: str, project_key: str, operation_id: str
    ) -> GitActionResult: ...
    async def rollback_workspace(
        self, request_id: str, project_key: str, operation_id: str
    ) -> GitActionResult: ...
    async def git_status(self, request_id: str, project_key: str) -> GitStatus: ...
    async def git_global_status(self, request_id: str) -> GitInstallationStatus: ...
    async def branches(self, request_id: str, project_key: str) -> tuple[GitBranch, ...]: ...
    async def create_branch(
        self, request_id: str, project_key: str, branch: str
    ) -> GitActionResult: ...
    async def switch_branch(
        self, request_id: str, project_key: str, branch: str
    ) -> GitActionResult: ...
    async def pull(self, request_id: str, project_key: str) -> GitActionResult: ...
    async def push(self, request_id: str, project_key: str) -> GitActionResult: ...
    async def github_status(self, request_id: str) -> GitHubStatus: ...
    async def github_project_status(
        self, request_id: str, project_key: str
    ) -> GitHubProjectStatus: ...
    async def create_draft_pr(
        self, request_id: str, project_key: str, title: str, body: str, base: str | None
    ) -> GitHubPullRequestResult: ...


class UnixCodexRuntimeClient:
    def __init__(
        self,
        socket_path: Path,
        *,
        status_timeout_seconds: float = DEFAULT_CODEX_STATUS_RPC_TIMEOUT_SECONDS,
        mutation_timeout_seconds: float = DEFAULT_CODEX_MUTATION_RPC_TIMEOUT_SECONDS,
        error_prefix: str = "CODEX",
    ) -> None:
        if status_timeout_seconds <= 0 or mutation_timeout_seconds <= 0:
            raise ValueError("Runtime RPC timeouts must be positive")
        self._socket_path = socket_path
        self._status_timeout_seconds = status_timeout_seconds
        self._mutation_timeout_seconds = mutation_timeout_seconds
        self._error_prefix = error_prefix

    async def status(self, request_id: str) -> CodexStatus:
        return _decode_status(
            await self._request(
                "codex.status", request_id, timeout_seconds=self._status_timeout_seconds
            )
        )

    async def start_remote(self, request_id: str) -> RemoteActionResult:
        return _decode_action(
            await self._request(
                "codex.remote.start",
                request_id,
                timeout_seconds=self._mutation_timeout_seconds,
            )
        )

    async def stop_remote(self, request_id: str) -> RemoteActionResult:
        return _decode_action(
            await self._request(
                "codex.remote.stop",
                request_id,
                timeout_seconds=self._mutation_timeout_seconds,
            )
        )

    async def generate_pair_code(self, request_id: str) -> PairCodeResult:
        data = await self._request(
            "codex.pair", request_id, timeout_seconds=self._mutation_timeout_seconds
        )
        code = data.get("code")
        expires_at = data.get("expires_at")
        if not isinstance(code, str) or not (4 <= len(code) <= 64):
            raise _protocol_error()
        if expires_at is not None and not isinstance(expires_at, str):
            raise _protocol_error()
        return PairCodeResult(code=code, expires_at=expires_at)

    async def _request(
        self,
        action: str,
        request_id: str,
        *,
        timeout_seconds: float,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "protocol_version": RUNTIME_PROTOCOL_VERSION,
            "action": action,
            "request_id": request_id,
        }
        if project_id is not None:
            request["project_id"] = project_id
        encoded = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self._socket_path), timeout=2
            )
        except (OSError, TimeoutError) as exc:
            raise RuntimeOperationError(
                f"{self._error_prefix}_RUNTIME_UNAVAILABLE",
                "Runtime Executor is unavailable",
                category="unavailable",
                retryable=True,
            ) from exc
        try:
            writer.write(encoded)
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
            if not raw or len(raw) > MAX_RUNTIME_FRAME or not raw.endswith(b"\n"):
                raise _protocol_error()
            payload = json.loads(raw)
            if (
                not isinstance(payload, dict)
                or payload.get("protocol_version") != 1
                or payload.get("request_id") != request_id
            ):
                raise ValueError("invalid envelope")
            error = payload.get("error")
            if error is not None:
                if not isinstance(error, dict):
                    raise ValueError("invalid error")
                raise RuntimeOperationError(
                    str(error.get("code", f"{self._error_prefix}_RUNTIME_BROKEN"))[:80],
                    str(error.get("message", "Runtime operation failed"))[:256],
                    category=str(error.get("category", "broken"))[:32],
                    retryable=bool(error.get("retryable", False)),
                    retry_after=(
                        int(error["retry_after"])
                        if isinstance(error.get("retry_after"), int)
                        else None
                    ),
                )
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError("invalid data")
            return data
        except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
            raise _protocol_error() from exc
        except TimeoutError as exc:
            raise RuntimeOperationError(
                f"{self._error_prefix}_RUNTIME_TIMEOUT",
                "Runtime Executor timed out",
                category="timeout",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise RuntimeOperationError(
                f"{self._error_prefix}_RUNTIME_UNAVAILABLE",
                "Runtime Executor is unavailable",
                category="unavailable",
                retryable=True,
            ) from exc
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()


def _protocol_error() -> RuntimeOperationError:
    return RuntimeOperationError(
        "RUNTIME_PROTOCOL_INVALID",
        "Runtime Executor returned an invalid response",
        category="broken",
    )


def _decode_status(data: dict[str, Any]) -> CodexStatus:
    try:
        capabilities_raw = data["capabilities"]
        diagnostics_raw = data.get("diagnostics", [])
        if not isinstance(capabilities_raw, dict) or not isinstance(diagnostics_raw, list):
            raise ValueError("invalid nested status")
        capabilities = CodexCapabilities(
            **{
                key: CapabilityState(capabilities_raw[key])
                for key in CodexCapabilities.__annotations__
            }
        )
        diagnostics = tuple(
            DiagnosticFinding(
                code=str(item["code"])[:80],
                severity=str(item["severity"])[:16],
                summary=str(item["summary"])[:256],
                remediation=(str(item["remediation"])[:512] if item.get("remediation") else None),
            )
            for item in diagnostics_raw
            if isinstance(item, dict)
        )
        alternatives_raw = data.get("alternatives", [])
        if not isinstance(alternatives_raw, list):
            raise ValueError("invalid alternatives")
        return CodexStatus(
            installed=bool(data["installed"]),
            version=str(data["version"])[:64] if data.get("version") is not None else None,
            selected_executable=(
                str(data["selected_executable"])[:4096]
                if data.get("selected_executable") is not None
                else None
            ),
            alternatives=tuple(str(value)[:4096] for value in alternatives_raw[:16]),
            installation_type=InstallationType(data["installation_type"]),
            conflict_detected=bool(data["conflict_detected"]),
            authentication=AuthenticationState(data["authentication"]),
            capabilities=capabilities,
            remote_state=RemoteState(data["remote_state"]),
            remote_confidence=str(data["remote_confidence"])[:32],
            diagnostics=diagnostics[:32],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _protocol_error() from exc


def _decode_action(data: dict[str, Any]) -> RemoteActionResult:
    try:
        return RemoteActionResult(
            outcome=str(data["outcome"])[:64],
            remote_state=RemoteState(data["remote_state"]),
        )
    except (KeyError, ValueError) as exc:
        raise _protocol_error() from exc


class UnixClaudeRuntimeClient:
    """Typed Claude client sharing the same bounded UDS transport."""

    def __init__(
        self,
        socket_path: Path,
        *,
        status_timeout_seconds: float = DEFAULT_CLAUDE_STATUS_RPC_TIMEOUT_SECONDS,
        mutation_timeout_seconds: float = DEFAULT_CLAUDE_MUTATION_RPC_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = UnixCodexRuntimeClient(
            socket_path,
            status_timeout_seconds=status_timeout_seconds,
            mutation_timeout_seconds=mutation_timeout_seconds,
            error_prefix="CLAUDE",
        )
        self._status_timeout_seconds = status_timeout_seconds
        self._mutation_timeout_seconds = mutation_timeout_seconds

    async def status(self, request_id: str) -> ClaudeStatus:
        data = await self._transport._request(
            "claude.status", request_id, timeout_seconds=self._status_timeout_seconds
        )
        return _decode_claude_status(data)

    async def list_sessions(self, request_id: str) -> tuple[ClaudeSession, ...]:
        data = await self._transport._request(
            "claude.sessions.list", request_id, timeout_seconds=self._status_timeout_seconds
        )
        raw = data.get("sessions")
        if not isinstance(raw, list) or len(raw) > 1000:
            raise _protocol_error()
        return tuple(_decode_claude_session(item) for item in raw)

    async def session(self, request_id: str, project_id: str) -> ClaudeSession:
        return _decode_claude_session(
            await self._transport._request(
                "claude.session.status",
                request_id,
                timeout_seconds=self._status_timeout_seconds,
                project_id=project_id,
            )
        )

    async def start_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        return _decode_claude_action(
            await self._transport._request(
                "claude.session.start",
                request_id,
                timeout_seconds=self._mutation_timeout_seconds,
                project_id=project_id,
            )
        )

    async def stop_session(self, request_id: str, project_id: str) -> ClaudeSessionActionResult:
        return _decode_claude_action(
            await self._transport._request(
                "claude.session.stop",
                request_id,
                timeout_seconds=self._mutation_timeout_seconds,
                project_id=project_id,
            )
        )

    async def recent_output(self, request_id: str, project_id: str) -> ClaudeSessionOutput:
        data = await self._transport._request(
            "claude.session.output",
            request_id,
            timeout_seconds=self._status_timeout_seconds,
            project_id=project_id,
        )
        try:
            output = data["output"]
            if not isinstance(output, str) or len(output.encode("utf-8")) > 32 * 1024:
                raise ValueError("invalid output")
            return ClaudeSessionOutput(
                project_id=str(data["project_id"])[:80],
                session_name=str(data["session_name"])[:80],
                output=output,
                truncated=bool(data["truncated"]),
                sensitive=bool(data["sensitive"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _protocol_error() from exc


class UnixProjectRuntimeClient:
    """Typed Project/Git/GitHub client; no path, argv, or environment fields exist."""

    def __init__(self, socket_path: Path) -> None:
        self._transport = UnixCodexRuntimeClient(socket_path, error_prefix="PROJECT")

    async def _request(self, action: str, request_id: str, **parameters: object) -> dict[str, Any]:
        request = {
            "protocol_version": RUNTIME_PROTOCOL_VERSION,
            "action": action,
            "request_id": request_id,
            **parameters,
        }
        return await _typed_transport_request(
            self._transport,
            request,
            timeout_seconds=330 if action in {"project.clone", "git.pull", "git.push"} else 90,
        )

    async def list_workspaces(self, request_id: str) -> tuple[ProjectWorkspace, ...]:
        data = await self._request("project.list", request_id)
        raw = data.get("projects")
        if (
            not isinstance(raw, list)
            or len(raw) > 1000
            or any(
                not isinstance(item, dict)
                or not isinstance(item.get("project_key"), str)
                or not isinstance(item.get("display_name"), str)
                for item in raw
            )
        ):
            raise _protocol_error()
        return tuple(
            ProjectWorkspace(str(item["project_key"])[:80], str(item["display_name"])[:128])
            for item in raw
        )

    async def create_workspace(
        self, request_id: str, project_key: str, operation_id: str
    ) -> GitActionResult:
        return _decode_git_action(
            await self._request(
                "project.create", request_id, project_key=project_key, operation_id=operation_id
            )
        )

    async def clone_workspace(
        self, request_id: str, project_key: str, operation_id: str, repository_url: str
    ) -> GitActionResult:
        return _decode_git_action(
            await self._request(
                "project.clone",
                request_id,
                project_key=project_key,
                operation_id=operation_id,
                repository_url=repository_url,
            )
        )

    async def finalize_workspace(
        self, request_id: str, project_key: str, operation_id: str
    ) -> GitActionResult:
        return _decode_git_action(
            await self._request(
                "project.finalize", request_id, project_key=project_key, operation_id=operation_id
            )
        )

    async def rollback_workspace(
        self, request_id: str, project_key: str, operation_id: str
    ) -> GitActionResult:
        return _decode_git_action(
            await self._request(
                "project.rollback", request_id, project_key=project_key, operation_id=operation_id
            )
        )

    async def git_status(self, request_id: str, project_key: str) -> GitStatus:
        data = await self._request("git.status", request_id, project_key=project_key)
        try:
            return GitStatus(
                is_repository=bool(data["is_repository"]),
                branch=str(data["branch"])[:128] if data.get("branch") is not None else None,
                detached_head=bool(data.get("detached_head", False)),
                unborn_branch=bool(data.get("unborn_branch", False)),
                upstream=str(data["upstream"])[:128] if data.get("upstream") is not None else None,
                ahead=int(data.get("ahead", 0)),
                behind=int(data.get("behind", 0)),
                staged_count=int(data.get("staged_count", 0)),
                unstaged_count=int(data.get("unstaged_count", 0)),
                untracked_count=int(data.get("untracked_count", 0)),
                conflicted_count=int(data.get("conflicted_count", 0)),
                clean=bool(data.get("clean", True)),
                remote_url=(
                    str(data["remote_url"])[:512] if data.get("remote_url") is not None else None
                ),
                submodules_detected=bool(data.get("submodules_detected", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _protocol_error() from exc

    async def git_global_status(self, request_id: str) -> GitInstallationStatus:
        data = await self._request("git.global.status", request_id)
        try:
            return GitInstallationStatus(
                bool(data["installed"]),
                str(data["version"])[:64] if data.get("version") is not None else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _protocol_error() from exc

    async def branches(self, request_id: str, project_key: str) -> tuple[GitBranch, ...]:
        data = await self._request("git.branches.list", request_id, project_key=project_key)
        raw = data.get("branches")
        if (
            not isinstance(raw, list)
            or len(raw) > 500
            or any(
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("current"), bool)
                for item in raw
            )
        ):
            raise _protocol_error()
        return tuple(GitBranch(str(item["name"])[:128], bool(item["current"])) for item in raw)

    async def create_branch(
        self, request_id: str, project_key: str, branch: str
    ) -> GitActionResult:
        return _decode_git_action(
            await self._request(
                "git.branch.create", request_id, project_key=project_key, branch=branch
            )
        )

    async def switch_branch(
        self, request_id: str, project_key: str, branch: str
    ) -> GitActionResult:
        return _decode_git_action(
            await self._request(
                "git.branch.switch", request_id, project_key=project_key, branch=branch
            )
        )

    async def pull(self, request_id: str, project_key: str) -> GitActionResult:
        return _decode_git_action(
            await self._request("git.pull", request_id, project_key=project_key)
        )

    async def push(self, request_id: str, project_key: str) -> GitActionResult:
        return _decode_git_action(
            await self._request("git.push", request_id, project_key=project_key)
        )

    async def github_status(self, request_id: str) -> GitHubStatus:
        data = await self._request("github.status", request_id)
        try:
            return GitHubStatus(
                bool(data["installed"]),
                str(data["version"])[:64] if data.get("version") is not None else None,
                AuthenticationState(data["authentication"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _protocol_error() from exc

    async def github_project_status(self, request_id: str, project_key: str) -> GitHubProjectStatus:
        data = await self._request("github.project.status", request_id, project_key=project_key)
        try:
            return GitHubProjectStatus(
                available=bool(data["available"]),
                repository=str(data["repository"])[:256] if data.get("repository") else None,
                pull_request_number=(
                    int(data["pull_request_number"])
                    if data.get("pull_request_number") is not None
                    else None
                ),
                pull_request_title=(
                    str(data["pull_request_title"])[:256]
                    if data.get("pull_request_title")
                    else None
                ),
                pull_request_state=(
                    str(data["pull_request_state"])[:32] if data.get("pull_request_state") else None
                ),
                pull_request_draft=(
                    bool(data["pull_request_draft"])
                    if data.get("pull_request_draft") is not None
                    else None
                ),
                pull_request_url=(
                    str(data["pull_request_url"])[:512] if data.get("pull_request_url") else None
                ),
                pull_request_base=(
                    str(data["pull_request_base"])[:128] if data.get("pull_request_base") else None
                ),
                pull_request_head=(
                    str(data["pull_request_head"])[:128] if data.get("pull_request_head") else None
                ),
                mergeability=(str(data["mergeability"])[:32] if data.get("mergeability") else None),
                checks=str(data.get("checks", "unknown"))[:16],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _protocol_error() from exc

    async def create_draft_pr(
        self, request_id: str, project_key: str, title: str, body: str, base: str | None
    ) -> GitHubPullRequestResult:
        data = await self._request(
            "github.pr.create",
            request_id,
            project_key=project_key,
            title=title,
            body=body,
            base=base,
        )
        try:
            return GitHubPullRequestResult(
                int(data["number"]) if data.get("number") is not None else None,
                str(data["url"])[:512],
                bool(data.get("draft", True)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _protocol_error() from exc


async def _typed_transport_request(
    transport: UnixCodexRuntimeClient, request: dict[str, object], *, timeout_seconds: float
) -> dict[str, Any]:
    encoded = json.dumps(request, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(transport._socket_path), timeout=2
        )
    except (OSError, TimeoutError) as exc:
        raise RuntimeOperationError(
            "PROJECT_RUNTIME_UNAVAILABLE",
            "Runtime Executor is unavailable",
            category="unavailable",
            retryable=True,
        ) from exc
    try:
        writer.write(encoded)
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
        if not raw or len(raw) > MAX_RUNTIME_FRAME or not raw.endswith(b"\n"):
            raise _protocol_error()
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or payload.get("protocol_version") != 1
            or payload.get("request_id") != request["request_id"]
        ):
            raise _protocol_error()
        error = payload.get("error")
        if error is not None and not isinstance(error, dict):
            raise _protocol_error()
        if isinstance(error, dict):
            raise RuntimeOperationError(
                str(error.get("code", "PROJECT_RUNTIME_BROKEN"))[:80],
                str(error.get("message", "Runtime operation failed"))[:256],
                category=str(error.get("category", "broken"))[:32],
                retryable=bool(error.get("retryable", False)),
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise _protocol_error()
        return data
    except TimeoutError as exc:
        raise RuntimeOperationError(
            "PROJECT_RUNTIME_TIMEOUT",
            "Runtime Executor timed out",
            category="timeout",
            retryable=True,
        ) from exc
    except (json.JSONDecodeError, UnicodeError, OSError) as exc:
        raise _protocol_error() from exc
    finally:
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()


def _decode_git_action(data: dict[str, Any]) -> GitActionResult:
    try:
        return GitActionResult(
            str(data["outcome"])[:64],
            str(data["branch"])[:128] if data.get("branch") is not None else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _protocol_error() from exc


def _decode_claude_status(data: dict[str, Any]) -> ClaudeStatus:
    try:
        capabilities = data["capabilities"]
        diagnostics_raw = data.get("diagnostics", [])
        if not isinstance(capabilities, dict) or not isinstance(diagnostics_raw, list):
            raise ValueError("invalid Claude status")
        return ClaudeStatus(
            installed=bool(data["installed"]),
            version=str(data["version"])[:64] if data.get("version") is not None else None,
            authentication=AuthenticationState(data["authentication"]),
            capabilities=ClaudeCapabilities(
                remote_control=CapabilityState(capabilities["remote_control"]),
                remote_start=CapabilityState(capabilities["remote_start"]),
                version=CapabilityState(capabilities["version"]),
            ),
            tmux_installed=bool(data["tmux_installed"]),
            tmux_version=(
                str(data["tmux_version"])[:64] if data.get("tmux_version") is not None else None
            ),
            managed_sessions=int(data["managed_sessions"]),
            unmanaged_sessions=int(data["unmanaged_sessions"]),
            workspace_interaction_warnings=int(data["workspace_interaction_warnings"]),
            diagnostics=tuple(
                DiagnosticFinding(
                    code=str(item["code"])[:80],
                    severity=str(item["severity"])[:16],
                    summary=str(item["summary"])[:256],
                    remediation=(
                        str(item["remediation"])[:512] if item.get("remediation") else None
                    ),
                )
                for item in diagnostics_raw[:32]
                if isinstance(item, dict)
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _protocol_error() from exc


def _decode_claude_session(data: object) -> ClaudeSession:
    if not isinstance(data, dict):
        raise _protocol_error()
    try:
        return ClaudeSession(
            project_id=str(data["project_id"])[:80],
            display_name=str(data["display_name"])[:128],
            state=ClaudeSessionState(data["state"]),
            managed=bool(data["managed"]),
            session_name=str(data["session_name"])[:80],
            attach_command=str(data["attach_command"])[:192],
            workspace_state=WorkspaceState(data["workspace_state"]),
            tmux_running=bool(data["tmux_running"]),
            remote_readiness=str(data["remote_readiness"])[:32],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _protocol_error() from exc


def _decode_claude_action(data: dict[str, Any]) -> ClaudeSessionActionResult:
    try:
        outcome = str(data["outcome"])
        if outcome not in {"started", "stopped", "already_running", "already_stopped"}:
            raise ValueError("invalid outcome")
        return ClaudeSessionActionResult(outcome, _decode_claude_session(data["session"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise _protocol_error() from exc
