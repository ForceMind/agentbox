"""Minimal non-root Runtime Executor for allowlisted Codex actions."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import stat
import struct
from pathlib import Path
from typing import Any

from agentbox_runtime.codex import CodexAdapter, CodexManager
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.rpc import MAX_RUNTIME_FRAME, RUNTIME_PROTOCOL_VERSION

_ACTIONS = frozenset({"codex.status", "codex.remote.start", "codex.remote.stop", "codex.pair"})


class RuntimeExecutorServer:
    def __init__(
        self,
        socket_path: Path,
        manager: CodexManager,
        *,
        allowed_peer_uids: frozenset[int],
    ) -> None:
        self._socket_path = socket_path
        self._manager = manager
        self._allowed_peer_uids = allowed_peer_uids
        self._server: asyncio.AbstractServer | None = None

    async def start(self, *, create_development_parent: bool = False) -> None:
        parent = self._socket_path.parent
        if create_development_parent:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not parent.is_dir():
            raise RuntimeError("Runtime socket parent does not exist")
        if self._socket_path.exists() or self._socket_path.is_symlink():
            details = self._socket_path.lstat()
            if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.geteuid():
                raise RuntimeError("refusing to replace an unexpected Runtime socket path")
            raise RuntimeError("Runtime socket already exists")
        self._server = await asyncio.start_unix_server(
            self._handle, path=self._socket_path, start_serving=False
        )
        self._socket_path.chmod(0o660)
        await self._server.start_serving()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            details = self._socket_path.lstat()
            if stat.S_ISSOCK(details.st_mode) and details.st_uid == os.geteuid():
                self._socket_path.unlink()
        except FileNotFoundError:
            pass

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("Runtime server is not started")
        async with self._server:
            await self._server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_id: str | None = None
        try:
            if not self._peer_allowed(writer):
                await self._write_error(
                    writer, "RUNTIME_PEER_FORBIDDEN", "Runtime peer is forbidden"
                )
                return
            raw = await asyncio.wait_for(reader.readline(), timeout=5)
            if not raw or len(raw) > MAX_RUNTIME_FRAME or not raw.endswith(b"\n"):
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            request = json.loads(raw)
            if (
                not isinstance(request, dict)
                or set(request) != {"protocol_version", "action", "request_id"}
                or request.get("protocol_version") != RUNTIME_PROTOCOL_VERSION
                or request.get("action") not in _ACTIONS
                or not isinstance(request.get("request_id"), str)
                or not (1 <= len(request["request_id"]) <= 64)
            ):
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            request_id = request["request_id"]
            data = await self._dispatch(request["action"])
            await self._write(
                writer,
                {
                    "protocol_version": 1,
                    "request_id": request_id,
                    "data": data,
                    "error": None,
                },
            )
        except (TimeoutError, json.JSONDecodeError, UnicodeError):
            await self._write_error(
                writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
            )
        except RuntimeOperationError as exc:
            await self._write(
                writer,
                {
                    "protocol_version": 1,
                    "request_id": request_id,
                    "data": None,
                    "error": {
                        "code": exc.code,
                        "category": exc.category,
                        "message": exc.message,
                        "retryable": exc.retryable,
                        "retry_after": exc.retry_after,
                    },
                },
            )
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    def _peer_allowed(self, writer: asyncio.StreamWriter) -> bool:
        transport_socket = writer.get_extra_info("socket")
        if transport_socket is None or not hasattr(socket, "SO_PEERCRED"):
            return False
        credentials = transport_socket.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
        )
        _pid, uid, _gid = struct.unpack("3i", credentials)
        return uid in self._allowed_peer_uids

    async def _dispatch(self, action: str) -> dict[str, Any]:
        if action == "codex.status":
            return (await self._manager.status()).to_dict()
        if action == "codex.remote.start":
            return (await self._manager.start_remote()).to_dict()
        if action == "codex.remote.stop":
            return (await self._manager.stop_remote()).to_dict()
        if action == "codex.pair":
            return (await self._manager.generate_pair_code()).to_dict()
        raise RuntimeOperationError(
            "RUNTIME_ACTION_UNSUPPORTED", "Runtime action is unsupported", category="unsupported"
        )

    async def _write_error(self, writer: asyncio.StreamWriter, code: str, message: str) -> None:
        await self._write(
            writer,
            {
                "protocol_version": 1,
                "request_id": None,
                "data": None,
                "error": {
                    "code": code,
                    "category": "forbidden" if code.endswith("FORBIDDEN") else "validation",
                    "message": message,
                    "retryable": False,
                    "retry_after": None,
                },
            },
        )

    @staticmethod
    async def _write(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_RUNTIME_FRAME:
            encoded = (
                b'{"protocol_version":1,"request_id":null,"data":null,'
                b'"error":{"code":"RUNTIME_RESPONSE_TOO_LARGE",'
                b'"category":"broken","message":"Runtime response exceeded its limit",'
                b'"retryable":false,"retry_after":null}}\n'
            )
        writer.write(encoded)
        await writer.drain()


async def _main() -> None:
    environment = os.environ.get("AGENTBOX_ENV", "development")
    socket_path = Path(os.environ.get("AGENTBOX_RUNTIME_SOCKET", ".agentbox-dev/runtime.sock"))
    if environment == "production" and (
        not socket_path.is_absolute() or socket_path.parent != Path("/run/agentbox")
    ):
        raise RuntimeError("production Runtime socket must be beneath /run/agentbox")
    configured_uids = os.environ.get("AGENTBOX_RUNTIME_ALLOWED_UIDS")
    if environment == "production" and not configured_uids:
        raise RuntimeError("AGENTBOX_RUNTIME_ALLOWED_UIDS is required in production")
    allowed = (
        frozenset(int(value) for value in configured_uids.split(","))
        if configured_uids
        else frozenset({os.geteuid()})
    )
    try:
        pair_cooldown = int(os.environ.get("AGENTBOX_CODEX_PAIR_COOLDOWN", "10"))
    except ValueError as exc:
        raise RuntimeError("AGENTBOX_CODEX_PAIR_COOLDOWN must be an integer") from exc
    if not 5 <= pair_cooldown <= 300:
        raise RuntimeError("AGENTBOX_CODEX_PAIR_COOLDOWN must be between 5 and 300 seconds")
    server = RuntimeExecutorServer(
        socket_path,
        CodexManager(CodexAdapter(), pair_cooldown_seconds=pair_cooldown),
        allowed_peer_uids=allowed,
    )
    await server.start(create_development_parent=environment != "production")
    try:
        await server.serve_forever()
    finally:
        await server.close()


def main() -> None:
    asyncio.run(_main())
