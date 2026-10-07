"""Real native peer-proof cost/fences; no claim about historical READY latency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from agentbox_core.a3_native_io import NATIVE_IO_DEADLINE, Guard, NativeChannel, deadline_after
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.a3_content import ContentError
from agentbox_protocol.a3_transport import NativeKind
from agentbox_runtime.waw_peer_authority import WAWPeerAuthority, WAWPeerLease
from test_a3_native_transport import Client, native_owner


@dataclass
class NativePeerChannel:
    authority: WAWPeerAuthority
    channel: NativeChannel
    peer: NativeChannel
    leases: tuple[WAWPeerLease, ...]


@pytest.fixture
async def native_peer_channel(
    tmp_path: Path, initialized_services: ControlPlaneServices
) -> AsyncIterator[NativePeerChannel]:
    # This is the existing same-process native fixture, not host qualification.
    # accept() obtains all three leases from actual SO_PEERCRED and pidfd_open.
    owner, facts, authority, _ = await native_owner(tmp_path, initialized_services)
    client: Client | None = None
    leases: tuple[WAWPeerLease, ...] = ()
    try:
        client = Client(owner, facts)
        await client.start()
        leases = tuple(client.bundle._leases)
        assert len(leases) == 3 and len({lease.fileno() for lease in leases}) == 3
        assert all(lease.current() for lease in leases)
        channel = client.bundle._channels["opaque"]
        channel.check()
        yield NativePeerChannel(authority, channel, client.channels["opaque"], leases)
    finally:
        try:
            if client is not None:
                await client.close()
        finally:
            owner.close()
            await owner.wait_closed()
            authority.close()
        assert owner.active_bundles == 0 and owner.selectors._active == 0
        assert authority.shutdown_clean and all(lease.closed for lease in leases)
        if client is not None:
            assert all(item.shutdown_complete for item in client.channels.values())
            assert all(item.shutdown_complete for item in client.bundle._channels.values())


@pytest.mark.anyio
async def test_no_extra_guard_does_not_repeat_actual_three_lease_peer_proof(
    native_peer_channel: NativePeerChannel, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = native_peer_channel.channel
    real_proof = channel._current
    proofs = 0

    def counted_proof() -> None:
        nonlocal proofs
        real_proof()
        proofs += 1

    monkeypatch.setattr(channel, "_current", counted_proof)
    # Isolate one fence from waits, scheduling and READY. Both old proof calls
    # really complete, so the old implementation fails specifically with 2 != 1.
    remaining = channel._check(deadline_after(1), None)
    assert remaining > 0
    assert proofs == 1, f"duplicate-native-peer-proof: completed_proofs={proofs}, leases=3"
    assert not channel.closed and all(lease.current() for lease in native_peer_channel.leases)


@pytest.mark.anyio
async def test_current_callback_close_fails_without_needing_a_second_peer_proof(
    native_peer_channel: NativePeerChannel, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = native_peer_channel.channel
    real_proof = channel._current
    proofs = 0

    def close_after_proof() -> None:
        nonlocal proofs
        real_proof()
        proofs += 1
        channel.close()

    monkeypatch.setattr(channel, "_current", close_after_proof)
    with pytest.raises(ContentError, match="PATCH_REVOKED"):
        channel._check(deadline_after(1), None)
    assert proofs == 1 and channel.closed and channel.shutdown_complete


@pytest.mark.anyio
async def test_extra_guard_never_runs_with_already_revoked_native_authority(
    native_peer_channel: NativePeerChannel,
) -> None:
    rig = native_peer_channel
    guard_called = False

    def guard() -> None:
        nonlocal guard_called
        guard_called = True

    rig.authority.close()
    assert all(not lease.current() for lease in rig.leases)
    with pytest.raises(ContentError, match="PATCH_REVOKED"):
        rig.channel._check(deadline_after(1), guard)
    assert not guard_called


@pytest.mark.anyio
async def test_extra_guard_exception_preserves_error_and_restores_inherited_deadline(
    native_peer_channel: NativePeerChannel,
) -> None:
    channel = native_peer_channel.channel
    deadline = deadline_after(0.5)
    inherited = deadline_after(1)
    token = NATIVE_IO_DEADLINE.set(inherited)
    failure = ContentError("PATCH_REVOKED")
    guard_called = False

    def guard() -> None:
        nonlocal guard_called
        guard_called = True
        assert NATIVE_IO_DEADLINE.get() == min(deadline, inherited)
        assert all(lease.current() for lease in native_peer_channel.leases)
        raise failure

    try:
        with pytest.raises(ContentError) as caught:
            channel.send(NativeKind.RECORD, b"opaque", deadline_ns=deadline, guard=guard)
        assert guard_called and caught.value is failure
        assert NATIVE_IO_DEADLINE.get() == inherited
        assert channel.closed and channel.shutdown_complete
    finally:
        NATIVE_IO_DEADLINE.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("revocation", ["authority", "channel"])
async def test_extra_guard_cannot_revoke_native_peer_and_allow_send(
    native_peer_channel: NativePeerChannel,
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
    revocation: str,
) -> None:
    rig = native_peer_channel
    channel = rig.channel
    deadline = deadline_after(1)
    inherited = deadline_after(0.5)
    token = NATIVE_IO_DEADLINE.set(inherited)
    guard_returned = False
    writes = 0
    original_socket = channel._socket

    class CheckedSocket:
        def __getattr__(self, name: str) -> Any:
            return getattr(original_socket, name)

        def send(self, raw: Any) -> int:
            nonlocal writes
            writes += 1
            return original_socket.send(raw)

    def guard() -> None:
        nonlocal guard_returned
        assert NATIVE_IO_DEADLINE.get() == min(deadline, inherited)
        assert all(lease.current() for lease in rig.leases)
        if revocation == "authority":
            rig.authority.close()
            assert rig.authority.shutdown_clean
            assert all(not lease.current() for lease in rig.leases)
        else:
            channel.close()
        guard_returned = True

    monkeypatch.setattr(channel, "_socket", CheckedSocket())
    try:
        with pytest.raises(ContentError, match="PATCH_REVOKED"):
            if asynchronous:
                await channel.asend(NativeKind.RECORD, b"opaque", deadline_ns=deadline, guard=guard)
            else:
                channel.send(NativeKind.RECORD, b"opaque", deadline_ns=deadline, guard=guard)
        assert guard_returned and writes == 0
        assert NATIVE_IO_DEADLINE.get() == inherited
        assert channel.closed and channel.shutdown_complete
    finally:
        NATIVE_IO_DEADLINE.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("operation", ["send", "header", "body", "readiness"])
async def test_no_extra_guard_rechecks_real_authority_after_actual_readiness(
    native_peer_channel: NativePeerChannel,
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
    operation: str,
) -> None:
    rig = native_peer_channel
    channel = rig.channel
    original_socket = channel._socket
    original_wait, original_await = channel._wait, channel._await
    waits = 0
    syscalls = 0
    revoked_after_ready = False

    class CheckedSocket:
        # Every I/O is forwarded to the original socket. The assertion makes an
        # attempted syscall after revocation fail even if bundle cleanup races it.
        def __getattr__(self, name: str) -> Any:
            return getattr(original_socket, name)

        def send(self, raw: Any) -> int:
            nonlocal syscalls
            assert not revoked_after_ready, "send attempted after actual authority revocation"
            syscalls += 1
            return original_socket.send(raw)

        def recv(self, size: int) -> bytes:
            nonlocal syscalls
            assert not revoked_after_ready, "recv attempted after actual authority revocation"
            syscalls += 1
            return original_socket.recv(size)

    def after_ready() -> None:
        nonlocal waits, revoked_after_ready
        waits += 1
        if waits == (2 if operation == "body" else 1):
            assert all(lease.current() for lease in rig.leases)
            rig.authority.close()
            assert rig.authority.shutdown_clean
            assert all(not lease.current() for lease in rig.leases)
            revoked_after_ready = True

    def waiting(write: bool, end: int, guard: Guard | None) -> None:
        assert guard is None
        original_wait(write, end, guard)
        after_ready()

    async def awaiting(write: bool, end: int, guard: Guard | None) -> None:
        assert guard is None
        await original_await(write, end, guard)
        after_ready()

    if operation != "send":
        await rig.peer.asend(NativeKind.RECORD, b"opaque", deadline_ns=deadline_after(1))
    monkeypatch.setattr(channel, "_socket", CheckedSocket())
    monkeypatch.setattr(channel, "_wait", waiting)
    monkeypatch.setattr(channel, "_await", awaiting)
    with pytest.raises(ContentError, match="PATCH_REVOKED"):
        if operation == "send":
            if asynchronous:
                await channel.asend(NativeKind.RECORD, b"opaque", deadline_ns=deadline_after(1))
            else:
                channel.send(NativeKind.RECORD, b"opaque", deadline_ns=deadline_after(1))
        elif operation == "readiness":
            if asynchronous:
                await channel.await_readable(deadline_after(1))
            else:
                channel.wait_readable(deadline_after(1))
        elif asynchronous:
            await channel.areceive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
        else:
            channel.receive(frozenset({NativeKind.RECORD}), deadline_ns=deadline_after(1))
    assert revoked_after_ready and waits == (2 if operation == "body" else 1)
    assert syscalls == (1 if operation == "body" else 0)
    assert channel.closed and channel.shutdown_complete
