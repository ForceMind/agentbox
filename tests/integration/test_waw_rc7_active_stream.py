"""RC7 active-stream failure cases over the real relay state machine.

The test ports are deliberately local and ephemeral.  They exercise the real
relay and its Unix writer adapter without network, filesystem, or production
fault switches.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import socket
from typing import Any, cast

import pytest
from agentbox_api.waw_admission_coordinator import AdmissionAuditAction as A
from agentbox_api.waw_admission_coordinator import RuntimeCleanupProof
from agentbox_api.waw_control_client import RuntimePeerBorrow
from agentbox_api.waw_relay import (
    RelayFailure,
    RuntimeSocketTrust,
    UnixRuntimePort,
    WAWCiphertextRelay,
)
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.abws import encode_frame
from agentbox_protocol.awce import encode_awce_header
from agentbox_protocol.waw_wire import Leg, decode_wire_frame, encode_wire_frame, forward_wire_frame
from support.waw_admission import Harness
from support.waw_failure_injection import CheckpointPlan, StreamCheckpoint

BA, AB, AR, RA = tuple(Leg)


async def _active() -> tuple[Harness, WAWCiphertextRelay]:
    harness = Harness()
    relay = WAWCiphertextRelay(
        harness.coordinator,
        authority=harness.authority,
        claims=harness.ticket.claims,
        context=harness.context,
        browser=harness.browser,
        runtime=harness.runtime,
        audit=harness.audit,
        revalidator=harness.validator,
        input_budget=harness.input_budget,
        clock=lambda: harness.clock.ns / 1_000_000_000,
    )
    await harness.coordinator.run()
    admitted = harness.coordinator.queue.read()
    assert admitted is not None
    await harness.browser.send_key_frame(admitted)
    relay._browser_published_next = 4
    relay.lease.begin(
        attachment_id=harness.ticket.claims.attachment_id,
        generation=harness.ticket.claims.generation,
        lease_number=harness.ticket.claims.lease_number,
        owner=relay.owner,
    )
    relay.lease.commit_admission()
    return harness, relay


def _input(relay: WAWCiphertextRelay) -> bytes:
    envelope = (
        encode_awce_header(
            crypto_envelope_version=1,
            direction_id=1,
            flags=0,
            crypto_sequence=1,
            stream_cursor=0,
            context_id=bytes.fromhex("e" * 32),
            ciphertext_length=17,
        )
        + b"x" * 17
    )
    return encode_frame(F.INPUT, envelope, relay.wire.expected_sequence(BA))


def _output(relay: WAWCiphertextRelay) -> bytes:
    envelope = (
        encode_awce_header(
            crypto_envelope_version=1,
            direction_id=2,
            flags=0,
            crypto_sequence=1,
            stream_cursor=1,
            context_id=bytes.fromhex("e" * 32),
            ciphertext_length=17,
        )
        + b"x" * 17
    )
    return encode_frame(F.OUTPUT, envelope, relay.wire.expected_sequence(RA))


def _control(relay: WAWCiphertextRelay, kind: F, **extra: Any) -> bytes:
    return encode_wire_frame(
        kind,
        BA,
        {
            "protocol_version": 1,
            "attachment_id": relay.claims.attachment_id,
            "lease_number": str(relay.claims.lease_number),
            **extra,
        },
        relay.wire.expected_sequence(BA),
    )


class _PrefixThenAgainSocket:
    """A socketpair endpoint that makes one real prefix write, then EAGAIN."""

    def __init__(self, endpoint: socket.socket, *, prefix: int) -> None:
        self.endpoint = endpoint
        self.prefix = prefix
        self.calls = 0

    def send(self, data: memoryview) -> int:
        self.calls += 1
        if self.calls == 1:
            return self.endpoint.send(data[: self.prefix])
        if self.calls == 2:
            raise BlockingIOError(errno.EAGAIN, "rc7 controlled backpressure")
        return self.endpoint.send(data)

    def close(self) -> None:
        self.endpoint.close()


class _PortControl:
    attestation = {"runtime_epoch": "2"}

    async def request_lifecycle(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError((action, request))

    def borrow_runtime_peer(self, peer_socket: object) -> RuntimePeerBorrow:
        raise AssertionError(peer_socket)


async def _close_with_evidence(
    harness: Harness,
    relay: WAWCiphertextRelay,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove positive cleanup releases the exact writer before replacement."""

    proofs: list[RuntimeCleanupProof] = []
    original_cleanup = harness.runtime.close_and_cleanup

    async def capture(request: Any) -> RuntimeCleanupProof:
        proof = await original_cleanup(request)
        proofs.append(proof)
        return proof

    monkeypatch.setattr(harness.runtime, "close_and_cleanup", capture)
    await relay.close(relay._failure or RelayFailure("ATTACHMENT_STALE", 4403))
    assert len(harness.runtime.cleanup_requests) == 1
    assert harness.runtime.cleanup_requests[0].claims == harness.ticket.claims
    assert proofs == [
        RuntimeCleanupProof(
            harness.ticket.claims,
            harness.context.runtime_epoch,
            harness.runtime.connection_id,
            "detached",
            "ATTACH_PTY_CLOSED",
        )
    ]
    assert harness.audit.events[-1].action is A.DETACHED
    assert harness.authority.record_count == harness.authority.active_count == 0
    assert harness.input_budget.closed and relay.wire.closed and not relay._cleanup_tasks

    replacement = harness.authority.issue(
        workspace_id=harness.ticket.claims.workspace_id,
        project_id=harness.ticket.claims.project_id,
        agent_type=harness.ticket.claims.agent_type,
        attachment_id="att_" + "f" * 32,
        generation=harness.ticket.claims.generation + 1,
        auth_epoch=harness.context.auth_epoch,
        runtime_host_installation_id=harness.ticket.claims.runtime_host_installation_id,
        runtime_host_installation_revision=harness.ticket.claims.runtime_host_installation_revision,
        binding_revision=harness.ticket.claims.binding_revision,
        binding_digest=harness.ticket.claims.binding_digest,
        context=harness.context,
    )
    replacement_lease = harness.authority.consume(
        replacement.ticket, replacement.claims, context=harness.context
    )
    assert replacement_lease.claims == replacement.claims
    harness.authority.detach(replacement.claims, context=harness.context)
    assert harness.authority.record_count == harness.authority.active_count == 0


@pytest.mark.anyio
async def test_rc7_input_partial_write_then_eagain_revoke_never_retries_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, relay = await _active()
    plan = CheckpointPlan.single(StreamCheckpoint.INPUT_PUBLISHED)
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    left.setblocking(False)
    right.setblocking(False)
    partial = _PrefixThenAgainSocket(left, prefix=11)
    port = UnixRuntimePort(
        _PortControl(), RuntimeSocketTrust(os.getgid(), os.getuid(), os.getgid())
    )
    monkeypatch.setattr(port, "_current", lambda: None)
    monkeypatch.setattr(port, "_socket", cast(socket.socket, partial))
    monkeypatch.setattr(port, "_connection", harness.runtime.connection_id)

    async def wait_writable() -> None:
        await plan.arrive(StreamCheckpoint.INPUT_PUBLISHED)

    monkeypatch.setattr(port, "_wait_writable", wait_writable)
    relay.runtime = port
    port.install_send_guard(relay._before_runtime_write)
    assert harness.active()
    input_raw = _input(relay)
    delivery = harness.browser.delivery(input_raw)
    expected_prefix_digest = hashlib.sha256(
        forward_wire_frame(decode_wire_frame(input_raw, BA), AR, relay.wire.expected_sequence(AR))[
            :11
        ]
    ).digest()
    del input_raw
    relay.browser_frame(delivery)
    del delivery
    writing = asyncio.create_task(relay._writer(relay._runtime_queue, browser=False))

    await asyncio.wait_for(plan.observe(StreamCheckpoint.INPUT_PUBLISHED), 1)
    harness.validator.valid = False
    assert plan.release(StreamCheckpoint.INPUT_PUBLISHED)
    with pytest.raises(RelayFailure) as failed:
        await asyncio.wait_for(writing, 1)
    assert failed.value.code == "ATTACHMENT_STALE"
    plan.assert_complete()
    prefix = await asyncio.wait_for(asyncio.get_running_loop().sock_recv(right, 65536), 1)
    assert len(prefix) == 11 and hashlib.sha256(prefix).digest() == expected_prefix_digest
    del prefix
    assert await asyncio.wait_for(asyncio.get_running_loop().sock_recv(right, 65536), 1) == b""
    assert partial.calls == 2
    assert relay._publication_fenced and port._aborted
    right.close()
    relay.runtime = harness.runtime
    await _close_with_evidence(harness, relay, monkeypatch)


@pytest.mark.anyio
async def test_rc7_output_publication_pending_gap_is_not_published_after_revoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, relay = await _active()
    plan = CheckpointPlan.single(StreamCheckpoint.OUTPUT_PUBLICATION_PENDING)
    original_send = harness.browser.send_key_frame

    async def guarded_send(raw: bytes) -> None:
        await plan.arrive(StreamCheckpoint.OUTPUT_PUBLICATION_PENDING)
        relay._before_browser_write(raw)
        await original_send(raw)

    monkeypatch.setattr(harness.browser, "send_key_frame", guarded_send)
    relay.runtime_frame(_output(relay))
    relay.runtime_frame(
        encode_wire_frame(
            F.GAP,
            RA,
            {
                "protocol_version": 1,
                "from_cursor": "1",
                "to_cursor": "2",
                "reason": "ring_overflow",
            },
            relay.wire.expected_sequence(RA),
        )
    )
    writing = asyncio.create_task(relay._writer(relay._browser_queue, browser=True))

    await asyncio.wait_for(plan.observe(StreamCheckpoint.OUTPUT_PUBLICATION_PENDING), 1)
    harness.validator.valid = False
    assert plan.release(StreamCheckpoint.OUTPUT_PUBLICATION_PENDING)
    with pytest.raises(RelayFailure) as failed:
        await asyncio.wait_for(writing, 1)
    assert failed.value.code == "ATTACHMENT_STALE"
    plan.assert_complete()
    assert relay._publication_fenced and relay._browser_published_next == 4
    published = [decode_wire_frame(raw, AB).frame_type for raw in harness.browser.sent]
    assert F.OUTPUT not in published and F.GAP not in published
    await _close_with_evidence(harness, relay, monkeypatch)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("checkpoint", "kind", "body"),
    (
        (StreamCheckpoint.HEARTBEAT_PENDING, F.HEARTBEAT, {"sent_at_monotonic_tick": "1"}),
        (StreamCheckpoint.RESIZE_PENDING, F.RESIZE, {"columns": 120, "rows": 32}),
    ),
)
async def test_rc7_delayed_control_write_rechecks_post_fence_guard(
    checkpoint: StreamCheckpoint,
    kind: F,
    body: dict[str, int | str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, relay = await _active()
    plan = CheckpointPlan.single(checkpoint)
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    left.setblocking(False)
    right.setblocking(False)
    partial = _PrefixThenAgainSocket(left, prefix=11)
    port = UnixRuntimePort(
        _PortControl(), RuntimeSocketTrust(os.getgid(), os.getuid(), os.getgid())
    )
    monkeypatch.setattr(port, "_current", lambda: None)
    monkeypatch.setattr(port, "_socket", cast(socket.socket, partial))
    monkeypatch.setattr(port, "_connection", harness.runtime.connection_id)

    async def wait_writable() -> None:
        await plan.arrive(checkpoint)

    monkeypatch.setattr(port, "_wait_writable", wait_writable)
    relay.runtime = port
    port.install_send_guard(relay._before_runtime_write)
    if kind is F.HEARTBEAT:
        relay._queue_runtime(
            relay._emit(
                F.HEARTBEAT,
                AR,
                {
                    "protocol_version": 1,
                    "attachment_id": relay.claims.attachment_id,
                    "lease_number": str(relay.claims.lease_number),
                    "sent_at_monotonic_tick": "1",
                },
            )
        )
    else:
        relay.browser_frame(harness.browser.delivery(_control(relay, kind, **body)))
    writing = asyncio.create_task(relay._writer(relay._runtime_queue, browser=False))

    await asyncio.wait_for(plan.observe(checkpoint), 1)
    harness.validator.valid = False
    assert plan.release(checkpoint)
    with pytest.raises(RelayFailure) as failed:
        await asyncio.wait_for(writing, 1)
    assert failed.value.code == "ATTACHMENT_STALE"
    plan.assert_complete()
    assert relay._publication_fenced and port._aborted and partial.calls == 2
    prefix = await asyncio.wait_for(asyncio.get_running_loop().sock_recv(right, 65536), 1)
    assert len(prefix) == 11
    assert await asyncio.wait_for(asyncio.get_running_loop().sock_recv(right, 65536), 1) == b""
    right.close()
    relay.runtime = harness.runtime
    await _close_with_evidence(harness, relay, monkeypatch)
