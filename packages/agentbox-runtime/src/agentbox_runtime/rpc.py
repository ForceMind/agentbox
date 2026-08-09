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
    CodexCapabilities,
    CodexStatus,
    DiagnosticFinding,
    InstallationType,
    PairCodeResult,
    RemoteActionResult,
    RemoteState,
    RuntimeOperationError,
)

RUNTIME_PROTOCOL_VERSION = 1
MAX_RUNTIME_FRAME = 64 * 1024


@runtime_checkable
class CodexRuntimeClient(Protocol):
    async def status(self, request_id: str) -> CodexStatus: ...

    async def start_remote(self, request_id: str) -> RemoteActionResult: ...

    async def stop_remote(self, request_id: str) -> RemoteActionResult: ...

    async def generate_pair_code(self, request_id: str) -> PairCodeResult: ...


class UnixCodexRuntimeClient:
    def __init__(self, socket_path: Path, *, timeout_seconds: float = 40) -> None:
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds

    async def status(self, request_id: str) -> CodexStatus:
        return _decode_status(await self._request("codex.status", request_id))

    async def start_remote(self, request_id: str) -> RemoteActionResult:
        return _decode_action(await self._request("codex.remote.start", request_id))

    async def stop_remote(self, request_id: str) -> RemoteActionResult:
        return _decode_action(await self._request("codex.remote.stop", request_id))

    async def generate_pair_code(self, request_id: str) -> PairCodeResult:
        data = await self._request("codex.pair", request_id)
        code = data.get("code")
        expires_at = data.get("expires_at")
        if not isinstance(code, str) or not (4 <= len(code) <= 64):
            raise _protocol_error()
        if expires_at is not None and not isinstance(expires_at, str):
            raise _protocol_error()
        return PairCodeResult(code=code, expires_at=expires_at)

    async def _request(self, action: str, request_id: str) -> dict[str, Any]:
        encoded = (
            json.dumps(
                {
                    "protocol_version": RUNTIME_PROTOCOL_VERSION,
                    "action": action,
                    "request_id": request_id,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self._socket_path), timeout=2
            )
        except (OSError, TimeoutError) as exc:
            raise RuntimeOperationError(
                "CODEX_RUNTIME_UNAVAILABLE",
                "Codex Runtime Executor is unavailable",
                category="unavailable",
                retryable=True,
            ) from exc
        try:
            writer.write(encoded)
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=self._timeout_seconds)
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
                    str(error.get("code", "CODEX_RUNTIME_BROKEN"))[:80],
                    str(error.get("message", "Codex Runtime operation failed"))[:256],
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
                "CODEX_RUNTIME_TIMEOUT",
                "Codex Runtime Executor timed out",
                category="timeout",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise RuntimeOperationError(
                "CODEX_RUNTIME_UNAVAILABLE",
                "Codex Runtime Executor is unavailable",
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
