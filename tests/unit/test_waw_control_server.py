from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

import pytest
from agentbox_protocol.waw_control import decode_control_response
from agentbox_runtime.waw_control_server import WAWControlDispatchError, WAWControlServer


def _request() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "action": "workspace.workspace.start",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "generation": "1",
        "binding_revision": "1",
        "binding_digest": "a" * 64,
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
    }


def _response(request_id: str) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": request_id,
        "status": "STARTED",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "generation": "1",
        "state": "RUNNING",
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
    }


Dispatch = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


async def _running_server(path: Path, dispatch: Dispatch) -> tuple[WAWControlServer, socket.socket]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.listen(16)
    server = WAWControlServer(sock, dispatch, timeout_seconds=0.2)
    await server.start()
    return server, sock


async def _call(path: Path, payload: bytes) -> bytes:
    reader, writer = await asyncio.open_unix_connection(path)
    writer.write(payload)
    await writer.drain()
    raw = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return raw


@pytest.mark.anyio
async def test_dispatches_valid_request_and_closes_connection(tmp_path: Path) -> None:
    seen: list[dict[str, object]] = []

    async def dispatch(request: dict[str, object]) -> dict[str, object]:
        seen.append(request)
        return _response(cast(str, request["request_id"]))

    server, sock = await _running_server(tmp_path / "control.sock", dispatch)
    try:
        import json

        raw = await _call(tmp_path / "control.sock", json.dumps(_request()).encode() + b"\n")
        assert decode_control_response(
            raw,
            "workspace.workspace.start",
            expected_request_id=cast(str, _request()["request_id"]),
        ) == _response(cast(str, _request()["request_id"]))
        assert seen == [_request()]
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_rejects_malformed_oversized_and_trailing_requests(tmp_path: Path) -> None:
    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        raise AssertionError("malformed requests must not dispatch")

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch)
    try:
        malformed = (
            b'{"protocol_version":1,"request_id":"wreq_'
            + b"1" * 32
            + b'","action":"workspace.workspace.start","extra":1}\n'
        )
        response = await _call(path, malformed)
        assert b'"error_code":"PROTOCOL_INVALID"' in response
        oversized = b'{"request_id":"wreq_' + b"1" * 32 + b'","padding":"' + b"x" * 5000 + b'"}\n'
        response = await _call(path, oversized)
        assert b'"error_code":"PROTOCOL_INVALID"' in response
        import json

        payload = json.dumps(_request(), separators=(",", ":")).encode() + b"\n{}\n"
        response = await _call(path, payload)
        assert b'"error_code":"PROTOCOL_INVALID"' in response
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_dispatch_timeout_and_typed_error_response(tmp_path: Path) -> None:
    async def dispatch(request: dict[str, object]) -> dict[str, object]:
        if cast(str, request["request_id"]).endswith("1" * 32):
            await asyncio.sleep(0.5)
        raise WAWControlDispatchError("WORKSPACE_NOT_RUNNING", retryable=True)

    server, sock = await _running_server(tmp_path / "control.sock", dispatch)
    try:
        import json

        raw = await _call(tmp_path / "control.sock", json.dumps(_request()).encode() + b"\n")
        assert b'"error_code":"INTERNAL_BOUNDED"' in raw
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_server_fences_dispatch_response_with_wrong_request_id(tmp_path: Path) -> None:
    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        return _response("wreq_" + "9" * 32)

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch)
    try:
        import json

        raw = await _call(path, json.dumps(_request()).encode() + b"\n")
        assert b'"error_code":"INTERNAL_BOUNDED"' in raw
        assert b'"request_id":"wreq_' + b"1" * 32 in raw
    finally:
        await server.close()
        sock.close()
