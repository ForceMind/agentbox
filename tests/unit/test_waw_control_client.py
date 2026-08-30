from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
from agentbox_api.waw_control_client import (
    WAWControlClient,
    WAWControlClientError,
    validate_runtime_bind_attestation,
)
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


def _bind_response() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "status": "BOUND",
        "api_authority_epoch": "1",
        "runtime_epoch": "2",
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
        "host_manifest_digest": "a" * 64,
        "project_root_manifest_digest": "b" * 64,
        "enrollment_epoch": "1",
        "enrollment_state": "steady",
    }


def _client(path: Path, *, timeout_seconds: float = 2.0) -> WAWControlClient:
    return WAWControlClient(
        path,
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        expected_socket_uid=os.geteuid(),
        expected_socket_gid=os.getegid(),
        timeout_seconds=timeout_seconds,
    )


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

    server = await asyncio.start_unix_server(handler, path=path)
    path.chmod(0o660)
    return server


@pytest.mark.anyio
async def test_client_uses_dedicated_socket_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "workspace-control.sock"
    payload = encode_control_response(_response(), "workspace.workspace.start")
    server = await _serve_once(path, payload)
    try:
        client = _client(path)
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
            await _client(path).request("workspace.workspace.start", _request())
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
            await _client(path2).request("workspace.workspace.start", _request())
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
            await _client(path, timeout_seconds=0.05).request(
                "workspace.workspace.start", _request()
            )
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        assert raised.value.retryable is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_rejects_invalid_request_before_connect(tmp_path: Path) -> None:
    client = _client(tmp_path / "missing.sock")
    with pytest.raises(WAWControlClientError) as raised:
        await client.request("workspace.workspace.start", {"protocol_version": 1})
    assert raised.value.code == "PROTOCOL_INVALID"


@pytest.mark.anyio
async def test_client_rejects_untrusted_socket_mode_before_connect(tmp_path: Path) -> None:
    path = tmp_path / "workspace-control.sock"
    server = await _serve_once(
        path, encode_control_response(_response(), "workspace.workspace.start")
    )
    try:
        client = WAWControlClient(
            path,
            expected_peer_uid=os.geteuid(),
            expected_peer_gid=os.getegid(),
            expected_socket_uid=os.geteuid(),
            expected_socket_gid=os.getegid(),
            expected_socket_mode=0o600,
        )
        with pytest.raises(WAWControlClientError) as raised:
            await client.request("workspace.workspace.start", _request())
        assert raised.value.code == "WAW_SOCKET_PROVENANCE_INVALID"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_normalizes_oversized_response(tmp_path: Path) -> None:
    path = tmp_path / "workspace-control.sock"
    oversized = b"{" + b"x" * (16 * 1024) + b"}\n"
    server = await _serve_once(path, oversized)
    try:
        with pytest.raises(WAWControlClientError) as raised:
            await _client(path).request("workspace.workspace.start", _request())
        assert raised.value.code == "PROTOCOL_INVALID"
    finally:
        server.close()
        await server.wait_closed()


async def _cancellation_resistant_operation() -> None:
    """Remain pending after cancellation to model a stuck transport syscall."""

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        await asyncio.sleep(10)


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["connect", "read", "drain"])
async def test_cancellation_resistant_transport_is_bounded_and_poisoned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client = _client(tmp_path / "workspace-control.sock", timeout_seconds=0.01)
    if operation == "connect":
        path = tmp_path / "workspace-control.sock"
        server = await _serve_once(
            path, encode_control_response(_response(), "workspace.workspace.start")
        )
        monkeypatch.setattr(
            asyncio,
            "open_unix_connection",
            lambda *args, **kwargs: _cancellation_resistant_operation(),
        )
        try:
            started = time.monotonic()
            with pytest.raises(WAWControlClientError) as raised:
                await client.request("workspace.workspace.start", _request())
            assert time.monotonic() - started < 0.5
            assert raised.value.code == "RUNTIME_UNAVAILABLE"
        finally:
            server.close()
            await server.wait_closed()
    else:
        deadline = time.monotonic() + 0.01
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            await client._with_deadline(_cancellation_resistant_operation(), deadline)
        assert time.monotonic() - started < 0.5
    assert client.poisoned is True
    with pytest.raises(WAWControlClientError, match="poisoned"):
        await client.request("workspace.workspace.start", _request())


@pytest.mark.anyio
async def test_cancellation_resistant_wait_closed_is_bounded_and_poisoned(tmp_path: Path) -> None:
    class StuckWriter:
        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            await _cancellation_resistant_operation()

    client = _client(tmp_path / "unused.sock", timeout_seconds=1)
    started = time.monotonic()
    await client._close_writer(StuckWriter())  # type: ignore[arg-type]
    assert time.monotonic() - started < 0.5
    assert client.poisoned is True


@pytest.mark.anyio
async def test_reconnect_refuses_while_detached_operation_is_pending(tmp_path: Path) -> None:
    release = asyncio.Event()

    async def stuck() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()

    client = _client(tmp_path / "unused.sock", timeout_seconds=0.001)
    with pytest.raises(TimeoutError):
        await client._with_deadline(stuck(), time.monotonic() + 0.001)
    assert client.pending_operations == 1
    with pytest.raises(WAWControlClientError) as raised:
        await client.reconnect()
    assert raised.value.code == "RUNTIME_UNAVAILABLE"
    assert client.poisoned is True
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert client.pending_operations == 0
    await client.reconnect()
    assert client.poisoned is False


def test_bind_attestation_is_pinned_to_expected_anchor() -> None:
    response = _bind_response()
    assert (
        validate_runtime_bind_attestation(
            response,
            expected_runtime_host_installation_id="wri_" + "4" * 32,
            expected_runtime_host_installation_revision="1",
            expected_host_manifest_digest="a" * 64,
            expected_project_root_manifest_digest="b" * 64,
            expected_runtime_epoch="2",
        )
        == response
    )
    response["host_manifest_digest"] = "c" * 64
    with pytest.raises(WAWControlClientError) as raised:
        validate_runtime_bind_attestation(
            response,
            expected_runtime_host_installation_id="wri_" + "4" * 32,
            expected_runtime_host_installation_revision="1",
            expected_host_manifest_digest="a" * 64,
            expected_project_root_manifest_digest="b" * 64,
        )
    assert raised.value.code == "RUNTIME_INSTALLATION_MISMATCH"
