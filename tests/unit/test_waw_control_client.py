from __future__ import annotations

import asyncio
import contextlib
import os
import select
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import agentbox_api.waw_control_client as control_subject
import pytest
from agentbox_api.waw_control_client import (
    BoundRuntimePeer,
    RuntimePeerBorrow,
    WAWControlClient,
    WAWControlClientError,
    WAWSocketPathIdentity,
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


def _bind_request() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "action": "workspace.api_authority.bind",
        "api_authority_epoch": "1",
        "authority_nonce": "c" * 32,
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


@pytest.fixture
def socket_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix=".waw-control-", dir=Path.cwd()) as directory:
        yield Path(directory)


@pytest.fixture(autouse=True)
def _synthetic_peer_capture(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Portable test pidfds; production has no injected peer-capture port."""

    writers: list[int] = []

    def capture(
        client: WAWControlClient, _peer_socket: object
    ) -> control_subject._RuntimePeerObservation:
        reader, writer = os.pipe()
        os.set_inheritable(reader, False)
        writers.append(writer)
        return control_subject._RuntimePeerObservation(
            pid=os.getpid(),
            uid=client._expected_peer_uid,
            gid=client._expected_peer_gid,
            pidfd=reader,
        )

    monkeypatch.setattr(WAWControlClient, "_capture_unbound_peer", capture)
    yield
    for descriptor in writers:
        with contextlib.suppress(OSError):
            os.close(descriptor)


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
async def test_client_uses_dedicated_socket_and_round_trips(socket_dir: Path) -> None:
    path = socket_dir / "control.sock"
    payload = encode_control_response(_response(), "workspace.workspace.start")
    server = await _serve_once(path, payload)
    try:
        client = _client(path)
        assert (
            await client._request_unbound_test_only("workspace.workspace.start", _request())
            == _response()
        )
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_bind_exchange_transfers_peer_only_on_explicit_publication(
    socket_dir: Path,
) -> None:
    path = socket_dir / "control.sock"
    server = await _serve_once(
        path,
        encode_control_response(_bind_response(), "workspace.api_authority.bind"),
    )
    client = _client(path)
    peer: BoundRuntimePeer | None = None
    try:
        exchange = await client.bind_exchange("workspace.api_authority.bind", _bind_request())
        assert exchange.response == _bind_response()
        owner: dict[str, object] = {"peer": None, "generation": 1}
        peer = exchange.publish(
            generation=1,
            owner_current=lambda candidate, generation: (
                owner["peer"] is candidate and owner["generation"] == generation
            ),
        )
        owner["peer"] = peer
        exchange.close()
        assert peer.current()
        await client.close()
        assert peer.current()
    finally:
        if peer is not None:
            peer.close()
        await client.close()
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_close_fences_unpublished_exchange_before_worker_acquires_lock(
    socket_dir: Path,
) -> None:
    client = _client(socket_dir / "unused.sock")
    retained, writer = os.pipe()
    candidate = BoundRuntimePeer(
        control_subject._RuntimePeerObservation(
            pid=4242,
            uid=os.geteuid(),
            gid=os.getegid(),
            pidfd=retained,
        ),
        WAWSocketPathIdentity(1, 2),
    )
    exchange = control_subject.RuntimeBindExchange(client, _bind_response(), candidate)
    client._pending_exchange = exchange

    close_wait = client.close()
    with pytest.raises(WAWControlClientError):
        exchange.publish(generation=1, owner_current=lambda _peer, _generation: True)
    await close_wait

    assert client.closed and client.poisoned and candidate.closed
    with pytest.raises(OSError):
        os.fstat(retained)
    os.close(writer)


@pytest.mark.anyio
async def test_client_rejects_trailing_bytes_and_request_id_mismatch(
    socket_dir: Path,
) -> None:
    path = socket_dir / "control.sock"
    payload = encode_control_response(_response(), "workspace.workspace.start") + b"x"
    server = await _serve_once(path, payload)
    try:
        with pytest.raises(WAWControlClientError, match="trailing"):
            await _client(path)._request_unbound_test_only("workspace.workspace.start", _request())
    finally:
        server.close()
        await server.wait_closed()

    mismatch = {**_response(), "request_id": "wreq_" + "9" * 32}
    path2 = socket_dir / "control-2.sock"
    server = await _serve_once(
        path2, encode_control_response(mismatch, "workspace.workspace.start")
    )
    try:
        with pytest.raises(WAWControlClientError, match="invalid"):
            await _client(path2)._request_unbound_test_only("workspace.workspace.start", _request())
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_applies_two_second_monotonic_deadline(socket_dir: Path) -> None:
    path = socket_dir / "control.sock"
    server = await _serve_once(
        path, encode_control_response(_response(), "workspace.workspace.start"), delay=0.2
    )
    try:
        with pytest.raises(WAWControlClientError) as raised:
            await _client(path, timeout_seconds=0.05)._request_unbound_test_only(
                "workspace.workspace.start", _request()
            )
        assert raised.value.code == "RUNTIME_UNAVAILABLE"
        assert raised.value.retryable is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_rejects_invalid_request_before_connect(socket_dir: Path) -> None:
    client = _client(socket_dir / "missing.sock")
    with pytest.raises(WAWControlClientError) as raised:
        await client._request_unbound_test_only(
            "workspace.workspace.start", {"protocol_version": 1}
        )
    assert raised.value.code == "PROTOCOL_INVALID"


@pytest.mark.anyio
async def test_client_rejects_untrusted_socket_mode_before_connect(socket_dir: Path) -> None:
    path = socket_dir / "control.sock"
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
            await client._request_unbound_test_only("workspace.workspace.start", _request())
        assert raised.value.code == "WAW_SOCKET_PROVENANCE_INVALID"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.anyio
async def test_client_normalizes_oversized_response(socket_dir: Path) -> None:
    path = socket_dir / "control.sock"
    oversized = b"{" + b"x" * (16 * 1024) + b"}\n"
    server = await _serve_once(path, oversized)
    try:
        with pytest.raises(WAWControlClientError) as raised:
            await _client(path)._request_unbound_test_only("workspace.workspace.start", _request())
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
    socket_dir: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    client = _client(socket_dir / "control.sock", timeout_seconds=0.01)
    if operation == "connect":
        path = socket_dir / "control.sock"
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
                await client._request_unbound_test_only("workspace.workspace.start", _request())
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
    with pytest.raises(WAWControlClientError, match="unavailable"):
        await client._request_unbound_test_only("workspace.workspace.start", _request())


@pytest.mark.anyio
async def test_cancellation_resistant_wait_closed_is_bounded_and_poisoned(
    socket_dir: Path,
) -> None:
    class StuckWriter:
        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            await _cancellation_resistant_operation()

    client = _client(socket_dir / "unused.sock", timeout_seconds=1)
    started = time.monotonic()
    await client._close_writer(StuckWriter())  # type: ignore[arg-type]
    assert time.monotonic() - started < 0.5
    assert client.poisoned is True


@pytest.mark.anyio
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_wait_closed_failure_irreversibly_poisons_client(
    socket_dir: Path, asynchronous: bool
) -> None:
    class BrokenWriter:
        def close(self) -> None:
            return None

        def wait_closed(self) -> object:
            if not asynchronous:
                raise OSError("synthetic synchronous close failure")

            async def fail() -> None:
                raise OSError("synthetic asynchronous close failure")

            return fail()

    client = _client(socket_dir / "unused.sock")
    await client._close_writer(BrokenWriter())  # type: ignore[arg-type]
    assert client.poisoned is True


@pytest.mark.parametrize("events,expected", [([], True), ([(100_000, select.POLLHUP)], False)])
def test_pidfd_liveness_uses_poll_for_high_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    events: list[tuple[int, int]],
    expected: bool,
) -> None:
    observed: list[tuple[int, int, int]] = []

    class Poller:
        def register(self, descriptor: int, mask: int) -> None:
            observed.append((descriptor, mask, -1))

        def poll(self, timeout: int) -> list[tuple[int, int]]:
            observed.append((-1, -1, timeout))
            return events

    monkeypatch.setattr("agentbox_api.waw_control_client.os.fstat", lambda _descriptor: object())
    monkeypatch.setattr("agentbox_api.waw_control_client.select.poll", Poller)
    assert control_subject._pidfd_current(100_000) is expected
    assert observed[0][0] == 100_000 and observed[-1] == (-1, -1, 0)


@pytest.mark.anyio
async def test_close_is_irreversible_while_detached_operation_finishes(
    socket_dir: Path,
) -> None:
    release = asyncio.Event()

    async def stuck() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()

    client = _client(socket_dir / "unused.sock", timeout_seconds=0.001)
    with pytest.raises(TimeoutError):
        await client._with_deadline(stuck(), time.monotonic() + 0.001)
    assert client.pending_operations == 1
    await client.close()
    await client.close()
    assert client.closed is True and client.poisoned is True
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert client.pending_operations == 0
    with pytest.raises(WAWControlClientError) as raised:
        await client._request_unbound_test_only("workspace.workspace.start", _request())
    assert raised.value.code == "RUNTIME_UNAVAILABLE"


@pytest.mark.anyio
async def test_replacement_requires_terminal_close_and_returns_fresh_owner(
    socket_dir: Path,
) -> None:
    client = _client(socket_dir / "unused.sock")
    with pytest.raises(WAWControlClientError):
        client.replacement_after_close()
    await client.close()

    replacement = client.replacement_after_close()
    with pytest.raises(WAWControlClientError):
        client.replacement_after_close()

    assert type(replacement) is WAWControlClient
    assert replacement is not client
    assert not replacement.closed and not replacement.poisoned
    assert replacement.socket_path == client.socket_path
    await replacement.close()


@pytest.mark.anyio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_replacement_rejects_failed_or_cancelled_close(
    socket_dir: Path, monkeypatch: pytest.MonkeyPatch, cancelled: bool
) -> None:
    client = _client(socket_dir / "unused.sock")

    async def fail_close() -> None:
        if cancelled:
            await asyncio.Event().wait()
        raise RuntimeError("synthetic close failure")

    monkeypatch.setattr(client, "_perform_close", fail_close)
    close_wait = client.close()
    operation = client._close_operation
    assert operation is not None
    if cancelled:
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_wait
    else:
        with pytest.raises(RuntimeError, match="synthetic"):
            await close_wait
    with pytest.raises(WAWControlClientError):
        client.replacement_after_close()


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


def _published_peer(*, pid: int = 4242) -> tuple[BoundRuntimePeer, int, int, dict[str, object]]:
    retained, writer = os.pipe()
    os.set_inheritable(retained, False)
    peer = BoundRuntimePeer(
        control_subject._RuntimePeerObservation(
            pid=pid,
            uid=os.geteuid(),
            gid=os.getegid(),
            pidfd=retained,
        ),
        WAWSocketPathIdentity(7, 11),
    )
    owner: dict[str, object] = {"peer": peer, "generation": 1, "open": True}
    peer._publish(
        generation=1,
        owner_current=lambda candidate, generation: (
            owner["open"] is True
            and owner["peer"] is candidate
            and owner["generation"] == generation
        ),
    )
    return peer, retained, writer, owner


def test_bound_peer_borrow_duplicates_only_retained_pidfd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, retained, writer, _owner = _published_peer()
    original_dup = os.dup
    duplicated: list[int] = []

    def duplicate(descriptor: int) -> int:
        duplicated.append(descriptor)
        return original_dup(descriptor)

    monkeypatch.setattr(
        control_subject, "_peer_credentials", lambda _socket: (4242, os.geteuid(), os.getegid())
    )
    monkeypatch.setattr(os, "dup", duplicate)
    monkeypatch.setattr(
        os,
        "pidfd_open",
        lambda *_args: (_ for _ in ()).throw(AssertionError("borrow reopened numeric PID")),
        raising=False,
    )
    borrow = peer.borrow(object())
    assert type(borrow) is RuntimePeerBorrow
    assert borrow.parent is peer and borrow.generation == 1 and borrow.current()
    assert duplicated == [retained]
    borrow.close()
    borrow.close()
    assert peer.current()
    peer.close()
    os.close(writer)


def test_same_uid_different_pid_irreversibly_poisons_bound_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, _retained, writer, _owner = _published_peer()
    monkeypatch.setattr(
        control_subject,
        "_peer_credentials",
        lambda _socket: (4243, os.geteuid(), os.getegid()),
    )

    with pytest.raises(WAWControlClientError) as raised:
        peer.borrow(object())

    assert raised.value.code == "RUNTIME_PEER_FORBIDDEN"
    assert peer.poisoned and not peer.current()
    peer.close()
    os.close(writer)


def test_pid_reuse_cannot_replace_an_exited_retained_pidfd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, _retained, writer, _owner = _published_peer()
    os.close(writer)
    monkeypatch.setattr(
        control_subject,
        "_peer_credentials",
        lambda _socket: (4242, os.geteuid(), os.getegid()),
    )

    with pytest.raises(WAWControlClientError):
        peer.borrow(object())

    assert peer.poisoned and not peer.current()


def test_borrow_checks_coordinator_object_identity_and_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, _retained, writer, owner = _published_peer()
    monkeypatch.setattr(
        control_subject,
        "_peer_credentials",
        lambda _socket: (4242, os.geteuid(), os.getegid()),
    )
    borrow = peer.borrow(object())
    owner["generation"] = 2
    assert not borrow.current()
    borrow.close()
    peer.close()
    os.close(writer)


def test_bound_peer_poison_and_close_release_retained_fd_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, retained, writer, _owner = _published_peer()
    original_close = os.close
    closed: list[int] = []

    def close(descriptor: int) -> None:
        if descriptor == retained:
            closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(os, "close", close)
    peer.poison()
    peer.poison()
    peer.close()
    peer.close()
    assert closed == [retained]
    original_close(writer)
