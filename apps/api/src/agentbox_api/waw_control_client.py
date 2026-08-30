"""Bounded API-side client for the dedicated WAW control socket.

This client is intentionally a one-request/one-response transport.  It never
opens the legacy Runtime socket, unlinks socket paths, or exposes a generic
action gateway to callers.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentbox_protocol.waw_control import (
    MAX_CONTROL_ENVELOPE,
    MAX_CONTROL_LINE,
    WAWControlError,
    decode_control_response,
    encode_control_request,
)


class WAWControlClientError(RuntimeError):
    """Transport or protocol failure talking to the WAW Runtime endpoint."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class WAWControlClient:
    """Issue one strict control request on a dedicated Unix socket."""

    def __init__(
        self,
        socket_path: Path,
        *,
        timeout_seconds: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(socket_path, Path):
            raise TypeError("socket_path must be a Path")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds
        self._monotonic = monotonic

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        """Send one validated request and decode its matching response."""

        try:
            encoded = encode_control_request(request)
            request_id = request["request_id"]
        except (KeyError, WAWControlError, TypeError, ValueError) as exc:
            raise WAWControlClientError(
                "PROTOCOL_INVALID", "WAW control request is invalid"
            ) from exc
        if request.get("action") != action:
            raise WAWControlClientError(
                "PROTOCOL_INVALID", "WAW control action does not match request"
            )
        if len(encoded) > MAX_CONTROL_LINE or len(encoded) > MAX_CONTROL_ENVELOPE:
            raise WAWControlClientError("PROTOCOL_INVALID", "WAW control request is oversized")

        deadline = self._monotonic() + self._timeout_seconds
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter
        try:
            reader, writer = await self._with_deadline(
                asyncio.open_unix_connection(self._socket_path, limit=MAX_CONTROL_LINE + 1),
                deadline,
            )
        except (OSError, TimeoutError) as exc:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime control endpoint is unavailable", retryable=True
            ) from exc
        try:
            writer.write(encoded)
            await self._with_deadline(writer.drain(), deadline)
            raw = await self._with_deadline(reader.readline(), deadline)
            if not raw or len(raw) > MAX_CONTROL_LINE or not raw.endswith(b"\n"):
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response framing is invalid"
                )
            try:
                response = decode_control_response(raw, action, expected_request_id=request_id)
            except WAWControlError as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response is invalid"
                ) from exc
            # The listener closes after the single response.  Any byte after
            # that response would represent a concatenated/trailed record.
            try:
                trailing = await self._with_deadline(reader.read(1), deadline)
            except TimeoutError as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response did not terminate"
                ) from exc
            if trailing:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response has trailing bytes"
                )
            return response
        except (OSError, TimeoutError) as exc:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime control request timed out", retryable=True
            ) from exc
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    async def _with_deadline(self, awaitable: Any, deadline: float) -> Any:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError("WAW control deadline exceeded")
        return await asyncio.wait_for(awaitable, timeout=remaining)


__all__ = ["WAWControlClient", "WAWControlClientError"]
