"""Socket-activated, peer-authenticated Privileged Helper server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import struct
from collections.abc import Awaitable, Callable

from agentbox_helper.actions import ActionResult, FixedActionRunner
from agentbox_helper.protocol import HelperAction, HelperRequest, HelperResponse

logger = logging.getLogger("agentbox.helper")


class HelperServer:
    def __init__(
        self,
        *,
        allowed_peer_uids: frozenset[int],
        runner: Callable[[HelperAction], Awaitable[ActionResult]],
        max_concurrent_requests: int = 4,
        action_timeout_seconds: float = 35,
    ) -> None:
        self._allowed_peer_uids = allowed_peer_uids
        self._runner = runner
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        if action_timeout_seconds <= 0:
            raise ValueError("Helper action timeout must be positive")
        self._action_timeout_seconds = action_timeout_seconds

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request: HelperRequest | None = None
        peer_uid = self._peer_uid(writer)
        try:
            if peer_uid is None or peer_uid not in self._allowed_peer_uids:
                await self._write(
                    writer,
                    HelperResponse(None, False, "HELPER_PEER_FORBIDDEN", "Helper peer forbidden"),
                )
                return
            raw = await asyncio.wait_for(reader.readline(), timeout=5)
            request = HelperRequest.decode(raw)
            if self._semaphore.locked():
                await self._write(
                    writer,
                    HelperResponse(
                        request.request_id,
                        False,
                        "HELPER_BUSY",
                        "Helper request capacity reached",
                    ),
                )
                return
            async with self._semaphore:
                try:
                    result = await asyncio.wait_for(
                        self._runner(request.action), timeout=self._action_timeout_seconds
                    )
                except TimeoutError:
                    result = ActionResult(
                        False, "HELPER_ACTION_TIMEOUT", "AgentBox action timed out"
                    )
            logger.info(
                "helper_action action=%s caller_uid=%d request_id=%s result=%s",
                request.action.value,
                peer_uid,
                request.request_id,
                "succeeded" if result.ok else "failed",
            )
            await self._write(
                writer,
                HelperResponse(request.request_id, result.ok, result.code, result.message),
            )
        except (TimeoutError, ValueError):
            await self._write(
                writer,
                HelperResponse(
                    request.request_id if request else None,
                    False,
                    "HELPER_PROTOCOL_INVALID",
                    "Helper request is invalid",
                ),
            )
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    @staticmethod
    def _peer_uid(writer: asyncio.StreamWriter) -> int | None:
        peer = writer.get_extra_info("socket")
        if peer is None or not hasattr(socket, "SO_PEERCRED"):
            return None
        credentials = peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", credentials)
        return int(uid)

    @staticmethod
    async def _write(writer: asyncio.StreamWriter, response: HelperResponse) -> None:
        writer.write(response.encode())
        await writer.drain()


def _systemd_listen_socket() -> socket.socket:
    if os.environ.get("LISTEN_PID") != str(os.getpid()) or os.environ.get("LISTEN_FDS") != "1":
        raise RuntimeError("agentbox-helper requires exactly one systemd socket")
    inherited = socket.socket(fileno=3)
    inherited.setblocking(False)
    return inherited


async def _main() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("agentbox-helper must run as root")
    raw_uids = os.environ.get("AGENTBOX_HELPER_ALLOWED_UIDS", "")
    if not raw_uids:
        raise RuntimeError("AGENTBOX_HELPER_ALLOWED_UIDS is required")
    try:
        allowed = frozenset(int(value) for value in raw_uids.split(","))
    except ValueError as exc:
        raise RuntimeError("AGENTBOX_HELPER_ALLOWED_UIDS is invalid") from exc
    action_runner = FixedActionRunner()
    helper = HelperServer(allowed_peer_uids=allowed, runner=action_runner.run)
    completed = asyncio.Event()

    async def handle_once(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await helper.handle(reader, writer)
        finally:
            completed.set()

    server = await asyncio.start_unix_server(handle_once, sock=_systemd_listen_socket())
    async with server:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(completed.wait(), timeout=30)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
