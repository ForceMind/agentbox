from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from agentbox_api.waw_control_client import WAWControlClient, WAWControlClientError
from agentbox_protocol.waw_control import encode_control_response


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


def _response() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "status": "STARTED",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "generation": "1",
        "state": "RUNNING",
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
    }


async def _serve_once(path: Path, payload: bytes, *, delay: float = 0) -> asyncio.AbstractServer:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        if delay:
            await asyncio.sleep(delay)
        writer.write(payload)
        try:
            await writer.drain()
        except (ConnectionError, BrokenPipeError):
            return
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_unix_server(handler, path=path)


@pytest.mark.anyio
async def test_client_uses_dedicated_socket_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "workspace-control.sock"
    payload = encode_control_response(_response(), "workspace.workspace.start")
    server = await _serve_once(path, payload)
    try:
        client = WAWControlClient(path)
        assert await client.request("workspace.workspace.start", _request()) == _response()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_rejects_trailing_bytes_and_request_id_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "workspace-control.sock"
    payload = encode_control_response(_response(), "workspace.workspace.start") + b"x"
    server = await _serve_once(path, payload)
    try:
        with pytest.raises(WAWControlClientError, match="trailing"):
            await WAWControlClient(path).request("workspace.workspace.start", _request())
    finally:
        server.close()
        await server.wait_closed()

    mismatch = {**_response(), "request_id": "wreq_" + "9" * 32}
    path2 = tmp_path / "workspace-control-2.sock"
    server = await _serve_once(
        path2, encode_control_response(mismatch, "workspace.workspace.start")
    )
    try:
        with pytest.raises(WAWControlClientError, match="invalid"):
            await WAWControlClient(path2).request("workspace.workspace.start", _request())
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_applies_two_second_monotonic_deadline(tmp_path: Path) -> None:
    path = tmp_path / "workspace-control.sock"
    server = await _serve_once(
        path, encode_control_response(_response(), "workspace.workspace.start"), delay=0.2
    )
    try:
        with pytest.raises(WAWControlClientError) as raised:
            await WAWControlClient(path, timeout_seconds=0.05).request(
                "workspace.workspace.start", _request()
            )
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        assert raised.value.retryable is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_rejects_invalid_request_before_connect(tmp_path: Path) -> None:
    client = WAWControlClient(tmp_path / "missing.sock")
    with pytest.raises(WAWControlClientError) as raised:
        await client.request("workspace.workspace.start", {"protocol_version": 1})
    assert raised.value.code == "PROTOCOL_INVALID"
