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
    InstallationType,
    PairCodeResult,
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
