"""Bound temporary UDS transport tests using synthetic Runtime process/peer ports."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import struct
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.waw_crypto_profile import BrowserCryptoProfile
from agentbox_protocol.waw_wire import decode_wire_frame, encode_wire_frame
from agentbox_runtime.waw_encrypted_server import WAWEncryptedServer
from agentbox_runtime.waw_encrypted_stream import admission_fields
from test_waw_encrypted_stream import AR, PIN, RA, Harness, body


class TestListeningSocket(socket.socket):
    """Real UDS I/O; macOS lacks Linux SO_ACCEPTCONN, so only that probe is synthetic."""

    __test__ = False

    def getsockopt(self, *args: Any, **kwargs: Any) -> Any:
        if sys.platform == "darwin" and args[1] == socket.SO_ACCEPTCONN:
            return 1
        return super().getsockopt(*args, **kwargs)


def prepared(h: Harness) -> bytes:
    h.session.close()
    h.claims = replace(h.claims, attachment_id="att_" + "9" * 32, lease_number=2)
    h.admission = admission_fields(h.claims)
    h.bound = {"protocol_version": 1, **h.admission, "runtime_epoch": "1"}
    h.capability = h.prepare()
    h.browser = BrowserCryptoProfile(h.admission, "1", PIN, clock=lambda: h.now)
    return h.hello_raw()


async def read_frame(reader: asyncio.StreamReader) -> bytes:
    async with asyncio.timeout(3):
        header = await reader.readexactly(24)
        length = struct.unpack("!4sBBHIQI", header)[4]
        return header + await reader.readexactly(length)


def test_real_temporary_uds_fragmented_handshake_input_cleanup(tmp_path: Path) -> None:
    async def scenario() -> None:
        h = Harness(tmp_path)
        hello = prepared(h)
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            path = directory + "/stream.sock"
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(path)
            sock.listen(4)
            server = WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: h.peer)
            await server.start()
            reader, writer = await asyncio.open_unix_connection(path)
            try:
                # Fragment the actual ABWS header and payload across writes.
                for part in (hello[:3], hello[3:17], hello[17:32], hello[32:]):
                    writer.write(part)
                    await writer.drain()
                    await asyncio.sleep(0)
                assert decode_wire_frame(await read_frame(reader), RA).frame_type is F.HELLO_ACK
                writer.write(encode_wire_frame(F.KEY_INIT, AR, h.browser.start(), 2))
                attest = decode_wire_frame(await read_frame(reader), RA)
                writer.write(
                    encode_wire_frame(
                        F.KEY_CONFIRM, AR, h.browser.receive_attest(attest.json_payload), 3
                    )
                )
                h.browser.receive_ack(body(await read_frame(reader)))
                writer.write(encode_wire_frame(F.STREAM_READY, AR, h.bound, 4))
                ready = body(await read_frame(reader))
                writer.write(
                    encode_wire_frame(
                        F.ADMISSION_COMMIT,
                        AR,
                        {**h.bound, "admission_fence": ready["admission_fence"]},
                        5,
                    )
                )
                assert (
                    decode_wire_frame(await read_frame(reader), RA).frame_type
                    is F.ADMISSION_COMMIT_ACK
                )
                writer.write(
                    encode_wire_frame(F.INPUT, AR, h.browser.encrypt_input(b"uds-input"), 6)
                )
                assert body(await read_frame(reader))["result"] == "accepted"
                assert body(await read_frame(reader))["result"] == "written_to_pty"
                assert h.transport.writes == [b"uds-input"]
                writer.write(
                    encode_wire_frame(
                        F.DETACH,
                        AR,
                        {
                            "protocol_version": 1,
                            "attachment_id": h.claims.attachment_id,
                            "lease_number": "2",
                        },
                        7,
                    )
                )
                detached = decode_wire_frame(await read_frame(reader), RA)
                assert detached.frame_type is F.DETACH_ACK
                assert detached.json_payload is not None
                assert detached.json_payload["cleanup_state"] == "ATTACH_PTY_CLOSED"
                assert not h.transport.stopped
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()
            assert h.registry.count == 0
            assert not server.poisoned

    asyncio.run(scenario())


def test_unverified_peer_rejected_before_capability_burn(tmp_path: Path) -> None:
    async def scenario() -> None:
        h = Harness(tmp_path)
        hello = prepared(h)
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(directory + "/stream.sock")
            sock.listen(1)
            server = WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: None)
            await server.start()
            reader, writer = await asyncio.open_unix_connection(directory + "/stream.sock")
            writer.write(hello)
            with contextlib.suppress(ConnectionResetError, BrokenPipeError):
                assert await reader.read() == b""
            writer.close()
            with contextlib.suppress(ConnectionResetError, BrokenPipeError):
                await writer.wait_closed()
            assert h.prepare() == h.capability
            h.registry.cleanup(h.peer, h.claims)
            await server.close()

    asyncio.run(scenario())


def test_partial_frame_timeout_and_oversize_header_do_not_allocate_session(tmp_path: Path) -> None:
    async def scenario() -> None:
        h = Harness(tmp_path)
        hello = prepared(h)
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(directory + "/stream.sock")
            sock.listen(2)
            server = WAWEncryptedServer(
                sock, h.registry, peer_verifier=lambda _: h.peer, frame_timeout=0.05
            )
            await server.start()
            for payload in (hello[:7], struct.pack("!4sBBHIQI", b"ABWS", 1, 2, 0, 65512, 1, 0)):
                reader, writer = await asyncio.open_unix_connection(directory + "/stream.sock")
                writer.write(payload)
                failure = decode_wire_frame(await read_frame(reader), RA)
                assert failure.frame_type is F.ERROR and failure.hop_sequence == 1
                async with asyncio.timeout(1):
                    assert await reader.read() == b""
                writer.close()
                await writer.wait_closed()
            assert h.prepare() == h.capability
            h.registry.cleanup(h.peer, h.claims)
            await server.close()

    asyncio.run(scenario())


def test_listener_rejects_nonlistening_socket(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(ValueError):
            WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: h.peer)
    finally:
        sock.close()
        h.session.close()


@pytest.mark.parametrize("decision", [False, 1, "raise", True])
def test_control_peer_authorizer_requires_exact_true_and_closes_rejected_pidfd(
    monkeypatch: pytest.MonkeyPatch,
    decision: object,
) -> None:
    import os

    from agentbox_runtime.waw_control_server import WAWControlServer

    server = object.__new__(WAWControlServer)
    server._expected_peer_uid = 42
    server._expected_peer_gid = 43
    read_fd, write_fd = os.pipe()
    seen: list[tuple[int, int, int, int]] = []

    def authorize(pid: int, uid: int, gid: int, pidfd: int) -> bool:
        seen.append((pid, uid, gid, pidfd))
        if decision == "raise":
            raise RuntimeError("synthetic verifier failure")
        return decision  # type: ignore[return-value]

    server._peer_authorizer = authorize
    monkeypatch.setattr(os, "pidfd_open", lambda *_: read_fd, raising=False)
    monkeypatch.setattr(socket, "SO_PEERCRED", 17, raising=False)

    class PeerSocket:
        def getsockopt(self, *_: object) -> bytes:
            return struct.pack("3i", 123, 42, 43)

    class Writer:
        def get_extra_info(self, _: str) -> PeerSocket:
            return PeerSocket()

    try:
        result = server._peer_pidfd(Writer())  # type: ignore[arg-type]
        assert seen == [(123, 42, 43, read_fd)]
        if decision is True:
            assert result == read_fd
            os.close(read_fd)
        else:
            assert result is None
            with pytest.raises(OSError):
                os.fstat(read_fd)
    finally:
        os.close(write_fd)


@pytest.mark.parametrize(
    "stage", ["hello", "key_init", "confirm", "ready", "commit", "active", "cleanup"]
)
def test_failure_profiles_use_stage_publication_hops(tmp_path: Path, stage: str) -> None:
    from agentbox_runtime.waw_supervisor import RuntimeProbeState

    async def scenario() -> None:
        h = Harness(tmp_path)
        hello = prepared(h)
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            path = directory + "/stream.sock"
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(path)
            sock.listen(2)
            server = WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: h.peer)
            await server.start()
            reader, writer = await asyncio.open_unix_connection(path)
            expected = 1
            try:
                if stage == "hello":
                    hello = h.hello_raw(runtime_epoch="2")
                writer.write(hello)
                if stage != "hello":
                    assert decode_wire_frame(await read_frame(reader), RA).frame_type is F.HELLO_ACK
                    expected = 2
                    init = h.browser.start()
                    if stage == "key_init":
                        init["noise_message_1"] = "A" * 43
                    writer.write(encode_wire_frame(F.KEY_INIT, AR, init, 2))
                    if stage != "key_init":
                        attest = decode_wire_frame(await read_frame(reader), RA)
                        confirm = h.browser.receive_attest(attest.json_payload)
                        expected = 3
                        if stage == "confirm":
                            ciphertext = str(confirm["ciphertext"])
                            confirm["ciphertext"] = (
                                "A" if ciphertext[0] != "A" else "B"
                            ) + ciphertext[1:]
                        writer.write(encode_wire_frame(F.KEY_CONFIRM, AR, confirm, 3))
                        if stage != "confirm":
                            h.browser.receive_ack(body(await read_frame(reader)))
                            expected = 4
                            original = h.transport.probe
                            if stage in {"ready", "cleanup"}:
                                if stage == "cleanup":

                                    def fail_cleanup(*_: object, **__: object) -> None:
                                        raise RuntimeError("synthetic-sensitive-cleanup-detail")

                                    h.registry._cleanup = fail_cleanup  # type: ignore[method-assign,assignment]
                                h.transport.probe = lambda: replace(
                                    original(), state=RuntimeProbeState.EXITED, exit_code=0
                                )
                            writer.write(encode_wire_frame(F.STREAM_READY, AR, h.bound, 4))
                            if stage not in {"ready", "cleanup"}:
                                ready = body(await read_frame(reader))
                                expected = 5
                                if stage == "commit":
                                    h.transport.probe = lambda: replace(
                                        original(), state=RuntimeProbeState.EXITED, exit_code=0
                                    )
                                writer.write(
                                    encode_wire_frame(
                                        F.ADMISSION_COMMIT,
                                        AR,
                                        {**h.bound, "admission_fence": ready["admission_fence"]},
                                        5,
                                    )
                                )
                                if stage == "active":
                                    assert (
                                        decode_wire_frame(await read_frame(reader), RA).frame_type
                                        is F.ADMISSION_COMMIT_ACK
                                    )
                                    expected = 6
                                    encrypted = h.browser.encrypt_input(b"no plaintext escape")
                                    writer.write(
                                        encode_wire_frame(
                                            F.INPUT,
                                            AR,
                                            encrypted[:-1] + bytes([encrypted[-1] ^ 1]),
                                            6,
                                        )
                                    )
                error = decode_wire_frame(await read_frame(reader), RA)
                assert error.frame_type is F.ERROR and error.hop_sequence == expected
                assert error.json_payload is not None
                assert str(error.json_payload["request_id"]).startswith("wreq_")
                assert error.json_payload["retryable"] is False
                if expected >= 3:
                    close = decode_wire_frame(await read_frame(reader), RA)
                    assert close.frame_type is F.CLOSE and close.hop_sequence == expected + 1
                async with asyncio.timeout(1):
                    assert await reader.read() == b""
            finally:
                writer.close()
                with contextlib.suppress(ConnectionResetError, BrokenPipeError):
                    await writer.wait_closed()
                await server.close()
            assert h.registry.count == (1 if stage == "cleanup" else 0)
            if stage == "cleanup":
                record = h.registry._records[h.claims.attachment_id]
                assert record.session is not None and record.session.closed
                assert (
                    record.session.cleanup_proof is not None
                    and not record.session.cleanup_proof.confirmed
                )
            assert not h.transport.stopped and not h.transport.writes

    asyncio.run(scenario())


def test_uncertain_partial_write_never_appends_failure_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness(tmp_path)
        hello = prepared(h)
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            path = directory + "/stream.sock"
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(path)
            sock.listen(1)
            server = WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: h.peer)
            from agentbox_runtime.waw_encrypted_server import _SocketPublication

            original = _SocketPublication.send
            partial_written = False

            def partial_send(port: _SocketPublication, data: memoryview) -> int:
                nonlocal partial_written
                if partial_written:
                    raise OSError("synthetic-partial-send")
                if data[5] == F.KEY_ATTEST:
                    partial_written = True
                    return original(port, data[:11])
                return original(port, data)

            monkeypatch.setattr(_SocketPublication, "send", partial_send)
            await server.start()
            reader, writer = await asyncio.open_unix_connection(path)
            try:
                writer.write(hello)
                assert decode_wire_frame(await read_frame(reader), RA).frame_type is F.HELLO_ACK
                writer.write(encode_wire_frame(F.KEY_INIT, AR, h.browser.start(), 2))
                async with asyncio.timeout(2):
                    partial = await reader.read()
                assert len(partial) == 11 and partial[:4] == b"ABWS" and partial[5] == F.KEY_ATTEST
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()
            assert h.registry.count == 0

    asyncio.run(scenario())


async def admit_connection(
    h: Harness, hello: bytes, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    writer.write(hello)
    assert decode_wire_frame(await read_frame(reader), RA).frame_type is F.HELLO_ACK
    writer.write(encode_wire_frame(F.KEY_INIT, AR, h.browser.start(), 2))
    attest = body(await read_frame(reader))
    writer.write(encode_wire_frame(F.KEY_CONFIRM, AR, h.browser.receive_attest(attest), 3))
    h.browser.receive_ack(body(await read_frame(reader)))
    writer.write(encode_wire_frame(F.STREAM_READY, AR, h.bound, 4))
    ready = body(await read_frame(reader))
    writer.write(
        encode_wire_frame(
            F.ADMISSION_COMMIT, AR, {**h.bound, "admission_fence": ready["admission_fence"]}, 5
        )
    )
    assert decode_wire_frame(await read_frame(reader), RA).frame_type is F.ADMISSION_COMMIT_ACK


@pytest.mark.parametrize(
    "fence", ["cleanup", "authority", "health", "partial", "stop", "partial_stop"]
)
def test_actual_socket_publication_cannot_outlive_session_fence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fence: str,
) -> None:
    from agentbox_runtime.waw_encrypted_server import _SocketPublication

    async def scenario() -> None:
        h = Harness(tmp_path, redraw=b"ciphertext must not escape a closed attachment")
        hello = prepared(h)
        cleanup_before_send: list[bool] = []
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            path = directory + "/stream.sock"
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(path)
            sock.listen(1)
            server = WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: h.peer)
            operation = server._operation

            async def after_output(function: Any, timeout: float) -> Any:
                result = await operation(function, timeout)
                if (
                    getattr(function, "__name__", "") == "output"
                    and result
                    and fence not in {"partial", "partial_stop"}
                ):
                    live = h.registry._records[h.claims.attachment_id].session
                    assert live is not None
                    if fence == "cleanup":
                        cleanup_before_send.append(live.close().confirmed)
                    elif fence == "stop":
                        live._supervisor.exact_stop(live._supervisor._stop_binding)
                    elif fence == "authority":
                        h.valid = False
                    else:
                        h.now = 10
                return result

            monkeypatch.setattr(server, "_operation", after_output)
            if fence in {"partial", "partial_stop"}:
                send = _SocketPublication.send

                def partial_send(port: _SocketPublication, data: memoryview) -> int:
                    if len(data) >= 24 and data[5] == F.OUTPUT:
                        count = send(port, data[:13])
                        live = h.registry._records[h.claims.attachment_id].session
                        assert live is not None
                        if fence == "partial_stop":
                            import threading

                            stopped = threading.Event()

                            def stop() -> None:
                                live._supervisor.exact_stop(live._supervisor._stop_binding)
                                stopped.set()

                            stopper = threading.Thread(target=stop)
                            stopper.start()
                            # publish_chunk still owns the registry lock here.
                            # A Stop callback taking it would deadlock this wait.
                            assert stopped.wait(1)
                            stopper.join(1)
                        else:
                            cleanup_before_send.append(live.close().confirmed)
                        return count
                    return send(port, data)

                monkeypatch.setattr(_SocketPublication, "send", partial_send)
            await server.start()
            reader, writer = await asyncio.open_unix_connection(path)
            try:
                await admit_connection(h, hello, reader, writer)
                async with asyncio.timeout(2):
                    remainder = await reader.read()
                assert len(remainder) == (13 if fence in {"partial", "partial_stop"} else 0)
                if fence in {"partial", "partial_stop"}:
                    assert remainder[:4] == b"ABWS" and remainder[5] == F.OUTPUT
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()
            if fence in {"cleanup", "partial"}:
                assert cleanup_before_send == [True]
            assert h.registry.count == 0
            assert h.transport.stopped == (fence in {"stop", "partial_stop"})

    asyncio.run(scenario())


def test_terminal_control_drain_holds_runtime_reservation_until_socket_fenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        h = Harness(tmp_path)
        hello = prepared(h)
        observed: list[tuple[int, bool]] = []
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            path = directory + "/stream.sock"
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(path)
            sock.listen(1)
            server = WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: h.peer)
            operation = server._operation

            async def before_detach_ack(function: Any, timeout: float) -> Any:
                result = await operation(function, timeout)
                if (
                    isinstance(result, tuple)
                    and result
                    and type(result[0]) is bytes
                    and decode_wire_frame(result[-1], RA).frame_type is F.DETACH_ACK
                ):
                    live = h.registry._records[h.claims.attachment_id].session
                    assert live is not None and live.cleanup_proof is not None
                    observed.append((h.registry.count, live.cleanup_proof.confirmed))
                return result

            monkeypatch.setattr(server, "_operation", before_detach_ack)
            await server.start()
            reader, writer = await asyncio.open_unix_connection(path)
            try:
                await admit_connection(h, hello, reader, writer)
                writer.write(
                    encode_wire_frame(
                        F.DETACH,
                        AR,
                        {
                            "protocol_version": 1,
                            "attachment_id": h.claims.attachment_id,
                            "lease_number": "2",
                        },
                        6,
                    )
                )
                assert decode_wire_frame(await read_frame(reader), RA).frame_type is F.DETACH_ACK
                async with asyncio.timeout(2):
                    assert await reader.read() == b""
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()
            assert observed == [(1, True)]
            assert h.registry.count == 0

    asyncio.run(scenario())


def test_exact_stop_fences_pending_handshake_before_first_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentbox_runtime.waw_encrypted_stream import WAWEncryptedSession

    async def scenario() -> None:
        h = Harness(tmp_path)
        hello = prepared(h)
        with tempfile.TemporaryDirectory(prefix="waw-r7-", dir="/tmp") as directory:
            path = directory + "/stream.sock"
            sock = TestListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(path)
            sock.listen(1)
            server = WAWEncryptedServer(sock, h.registry, peer_verifier=lambda _: h.peer)
            operation = server._operation

            async def stop_pending(function: Any, timeout: float) -> Any:
                result = await operation(function, timeout)
                if (
                    isinstance(result, tuple)
                    and result
                    and isinstance(result[0], WAWEncryptedSession)
                ):
                    live = result[0]
                    live._supervisor.exact_stop(live._supervisor._stop_binding)
                return result

            monkeypatch.setattr(server, "_operation", stop_pending)
            await server.start()
            reader, writer = await asyncio.open_unix_connection(path)
            try:
                writer.write(hello)
                async with asyncio.timeout(2):
                    assert await reader.read() == b""
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()
            assert h.transport.stopped and h.registry.count == 0

    asyncio.run(scenario())
