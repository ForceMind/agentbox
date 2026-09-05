"""Real R6/R8 authority, wire and socket adapters; synthetic host/PTY evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import tempfile
from pathlib import Path
from typing import Any

import agentbox_api.waw_control_client as control_subject
import pytest
from agentbox_api.waw_admission_coordinator import AdmissionAuditAction as A
from agentbox_api.waw_admission_coordinator import RuntimeCleanupRequest, RuntimePrepareRequest
from agentbox_api.waw_application import WAWWorkLedger
from agentbox_api.waw_control_client import (
    BoundRuntimePeer,
    RuntimePeerBorrow,
    WAWControlClient,
    WAWSocketPathIdentity,
)
from agentbox_api.waw_input_budget import InputBudgetOverflow, InputBudgetOwner
from agentbox_api.waw_relay import (
    DurableAdmissionAudit,
    FailedAdmissionBudget,
    RelayFailure,
    RuntimeSocketTrust,
    UnixRuntimePort,
    WAWCiphertextRelay,
    WAWStreamHandler,
    _canonical_origin,
)
from agentbox_core.configuration import Settings
from agentbox_core.models import AuditEvent, ControlPlaneSession
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.abws import encode_frame
from agentbox_protocol.awce import encode_awce_header
from agentbox_protocol.waw_control import decode_control_request, encode_control_response
from agentbox_protocol.waw_crypto_profile import BrowserCryptoProfile, RuntimeCryptoProfile
from agentbox_protocol.waw_wire import Leg, decode_wire_frame, encode_wire_frame
from conftest import FakeClock
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from sqlalchemy import select
from support.waw_admission import Harness

BA, AB, AR, RA = tuple(Leg)


def _published_runtime_peer() -> tuple[BoundRuntimePeer, int, dict[str, object]]:
    retained, writer = os.pipe()
    peer = BoundRuntimePeer(
        control_subject._RuntimePeerObservation(
            pid=7331,
            uid=os.getuid(),
            gid=os.getgid(),
            pidfd=retained,
        ),
        WAWSocketPathIdentity(3, 5),
    )
    owner: dict[str, object] = {"peer": peer, "generation": 1}
    peer._publish(
        generation=1,
        owner_current=lambda candidate, generation: (
            owner["peer"] is candidate and owner["generation"] == generation
        ),
    )
    return peer, writer, owner


def relay(h: Harness) -> WAWCiphertextRelay:
    return WAWCiphertextRelay(
        h.coordinator,
        authority=h.authority,
        claims=h.ticket.claims,
        context=h.context,
        browser=h.browser,
        runtime=h.runtime,
        audit=h.audit,
        revalidator=h.validator,
        input_budget=h.input_budget,
        clock=lambda: h.clock.ns / 1e9,
    )


async def active() -> tuple[Harness, WAWCiphertextRelay]:
    h = Harness()
    result = relay(h)
    await h.coordinator.run()
    admitted = h.coordinator.queue.read()
    assert admitted is not None
    await h.browser.send_key_frame(admitted)
    result._browser_published_next = 4
    result.lease.begin(
        attachment_id=h.ticket.claims.attachment_id,
        generation=h.ticket.claims.generation,
        lease_number=h.ticket.claims.lease_number,
        owner=result.owner,
    )
    result.lease.commit_admission()
    return h, result


def input_frame(
    r: WAWCiphertextRelay, *, size: int = 1, crypto: int = 1, output: bool = False
) -> bytes:
    leg = RA if output else BA
    envelope = encode_awce_header(
        crypto_envelope_version=1,
        direction_id=2 if output else 1,
        flags=0,
        crypto_sequence=crypto,
        stream_cursor=crypto if output else 0,
        context_id=bytes.fromhex("e" * 32),
        ciphertext_length=size + 16,
    ) + b"x" * (size + 16)
    return encode_frame(F.OUTPUT if output else F.INPUT, envelope, r.wire.expected_sequence(leg))


def ack(
    r: WAWCiphertextRelay, *, hop: int, result: str, crypto: int = 1, reason: str | None = None
) -> bytes:
    return encode_wire_frame(
        F.ACK,
        RA,
        {
            "protocol_version": 1,
            "runtime_input_hop_sequence": str(hop),
            "crypto_sequence": str(crypto),
            "result": result,
            "reason_code": reason,
        },
        r.wire.expected_sequence(RA),
    )


def control(r: WAWCiphertextRelay, kind: F, leg: Leg = BA, **extra: Any) -> bytes:
    body = {
        "protocol_version": 1,
        "attachment_id": r.claims.attachment_id,
        "lease_number": str(r.claims.lease_number),
        **extra,
    }
    return encode_wire_frame(kind, leg, body, r.wire.expected_sequence(leg))


def test_input_ack_mapping_terminal_replay_and_exit_order() -> None:
    async def run() -> None:
        h, r = await active()
        r.browser_frame(h.browser.delivery(control(r, F.HEARTBEAT, sent_at_monotonic_tick="1")))
        original = input_frame(r)
        r.browser_frame(h.browser.delivery(original))
        forwarded, _, _ = r._runtime_queue.items.get_nowait()
        assert decode_wire_frame(forwarded, AR).payload == decode_wire_frame(original, BA).payload
        assert decode_wire_frame(original, BA).hop_sequence == 5
        assert decode_wire_frame(forwarded, AR).hop_sequence == 6
        for result in ("accepted", "written_to_pty", "written_to_pty"):
            r.runtime_frame(ack(r, hop=6, result=result))
            body = decode_wire_frame(r._browser_queue.items.get_nowait()[0], AB).json_payload
            assert (
                body is not None
                and body["browser_input_hop_sequence"] == "5"
                and body["runtime_input_hop_sequence"] == "6"
            )
        with pytest.raises(RelayFailure):
            r.runtime_frame(ack(r, hop=6, result="written_to_pty"))

    asyncio.run(run())


@pytest.mark.parametrize(
    "case",
    [
        "unknown",
        "crypto",
        "terminal_before_accepted",
        "accepted_duplicate",
        "changed_terminal",
        "late",
        "after_exit",
    ],
)
def test_ack_invalid_reference_state_or_deadline_closes(case: str) -> None:
    async def run() -> None:
        h, r = await active()
        r.browser_frame(h.browser.delivery(input_frame(r)))
        raw = ack(r, hop=6, result="accepted")
        if case == "unknown":
            raw = ack(r, hop=7, result="accepted")
        elif case == "crypto":
            raw = ack(r, hop=6, result="accepted", crypto=2)
        elif case == "terminal_before_accepted":
            raw = ack(r, hop=6, result="written_to_pty")
        elif case in ("accepted_duplicate", "changed_terminal", "after_exit"):
            r.runtime_frame(raw)
            if case != "accepted_duplicate":
                r.runtime_frame(ack(r, hop=6, result="written_to_pty"))
            if case == "after_exit":
                r.runtime_frame(
                    encode_wire_frame(
                        F.EXIT,
                        RA,
                        {"protocol_version": 1, "state": "EXITED", "exit_code": 0},
                        r.wire.expected_sequence(RA),
                    )
                )
            raw = ack(
                r,
                hop=6,
                result="accepted" if case == "accepted_duplicate" else "write_uncertain",
                reason=None if case == "accepted_duplicate" else "INPUT_WRITE_UNCERTAIN",
            )
        elif case == "late":
            h.clock.ns += 5_000_000_000
        with pytest.raises((RelayFailure, ValueError)):
            r.runtime_frame(raw)

    asyncio.run(run())


@pytest.mark.parametrize(("kind", "limit"), [("input", 16384), ("output", 32768)])
def test_active_directional_size_rejects_before_forward(kind: str, limit: int) -> None:
    async def run() -> None:
        h, r = await active()
        with pytest.raises(RelayFailure) as error:
            raw = input_frame(r, size=limit + 1, output=kind == "output")
            if kind == "output":
                r.runtime_frame(raw)
            else:
                r.browser_frame(h.browser.delivery(raw))
        assert error.value.close_code == 1009
        assert r._runtime_queue.items.empty() and r._browser_queue.items.empty()

    asyncio.run(run())


def test_input_rate_first_drop_allocates_no_runtime_hop_or_ack_and_cleanup() -> None:
    async def run() -> None:
        h, r = await active()
        r.browser_frame(h.browser.delivery(input_frame(r, size=16384)))
        next_hop = r.wire.expected_sequence(AR)
        with pytest.raises(RelayFailure) as error:
            r.browser_frame(h.browser.delivery(input_frame(r, crypto=2)))
        assert error.value.code == "INPUT_RATE_LIMITED"
        assert r.wire.expected_sequence(AR) == next_hop and len(r._inputs) == 1
        assert r._browser_queue.items.empty()
        await r.close(error.value)
        assert h.browser.closed == 4429 and not h.active()
        assert len(r.input_uncertain) == 1
        assert h.authority.record_count == 0
        close = decode_wire_frame(h.runtime.cleanup_requests[0].close_frame, AR)
        assert (
            close.json_payload is not None and close.json_payload["code"] == "CONTROL_RATE_LIMITED"
        )

    asyncio.run(run())


@pytest.mark.parametrize("ending", ["complete", "cancel", "close_pending"])
def test_input_credit_runtime_send_lifecycle_is_exact(ending: str) -> None:
    async def run() -> None:
        h, r = await active()
        delivery = h.browser.delivery(input_frame(r))
        token = delivery.input_token
        assert token is not None
        assert h.input_budget.owner_bytes[InputBudgetOwner.BROWSER_DELIVERY] == token.size
        r.browser_frame(delivery)
        assert h.input_budget.owner_bytes[InputBudgetOwner.RELAY_RUNTIME_PENDING] == token.size
        assert h.input_budget.reserved_bytes == token.size
        if ending == "close_pending":
            await r.close(RelayFailure("ATTACHMENT_STALE", 4403))
            assert not token.live
            assert h.input_budget.reserved_bytes == h.input_budget.live_count == 0
            return

        h.runtime.block = F.INPUT
        writer = asyncio.create_task(r._writer(r._runtime_queue, browser=False))
        await asyncio.wait_for(h.runtime.entered.wait(), 1)
        assert h.input_budget.owner_bytes[InputBudgetOwner.RUNTIME_SEND_INFLIGHT] == token.size
        if ending == "complete":
            h.runtime.resume.set()
            async with asyncio.timeout(1):
                while token.live:
                    await asyncio.sleep(0)
            writer.cancel()
        else:
            writer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writer
        assert not token.live
        assert h.input_budget.reserved_bytes == h.input_budget.live_count == 0
        await r.close(RelayFailure("ATTACHMENT_STALE", 4403))
        assert not h.input_budget.release(token, owner=InputBudgetOwner.RUNTIME_SEND_INFLIGHT)

    asyncio.run(run())


def test_native_ready_overflow_synchronously_fences_relay_before_new_hop() -> None:
    async def run() -> None:
        h, r = await active()
        r.browser_frame(h.browser.delivery(input_frame(r, size=16384)))
        expected_runtime_hop = r.wire.expected_sequence(AR)
        assert len(r._inputs) == 1
        h.input_budget.reserve_native(16468)
        h.input_budget.reserve_native(16468)
        with pytest.raises(InputBudgetOverflow):
            h.input_budget.reserve_native(16468)
        assert r._publication_fenced and h.runtime.aborted and not h.active()
        assert r._failure is not None and r._failure.code == "INPUT_RATE_LIMITED"
        assert r.wire.expected_sequence(AR) == expected_runtime_hop
        assert len(r._inputs) == 1 and r._browser_queue.items.empty()
        assert len(h.runtime.sent) == 5  # Admission only; queued INPUT was never sent.
        await r.close(r._failure)
        assert h.input_budget.reserved_bytes == h.input_budget.live_count == 0

    asyncio.run(run())


def test_output_control_reserve_and_first_overflow_no_gap() -> None:
    async def run() -> None:
        h, r = await active()
        for n in range(1, 6):
            r.runtime_frame(input_frame(r, size=32768, crypto=n, output=True))
        with pytest.raises(RelayFailure) as error:
            r.runtime_frame(input_frame(r, size=32768, crypto=6, output=True))
        assert error.value.code == "OUTPUT_BACKPRESSURE"
        assert r._browser_queue.sizes[1] == 0
        await r.close(error.value)
        assert h.browser.closed == 1013 and h.authority.record_count == 0
        assert not r._browser_queue.sizes[0]

    asyncio.run(run())


def test_resize_single_correlation_and_nonterminal_rate_error() -> None:
    async def run() -> None:
        h, r = await active()
        r.browser_frame(h.browser.delivery(control(r, F.RESIZE, columns=120, rows=32)))
        r.browser_frame(h.browser.delivery(control(r, F.RESIZE, columns=121, rows=32)))
        error = decode_wire_frame(r._browser_queue.items.get_nowait()[0], AB)
        assert (
            error.frame_type == F.ERROR
            and error.json_payload is not None
            and error.json_payload["retryable"]
        )
        r.runtime_frame(
            control(
                r,
                F.RESIZE_ACK,
                RA,
                acknowledged_hop_sequence="6",
                requested_columns=120,
                requested_rows=32,
                effective_columns=120,
                effective_rows=32,
                result="applied",
                reason_code=None,
            )
        )
        translated = decode_wire_frame(r._browser_queue.items.get_nowait()[0], AB).json_payload
        assert translated is not None and translated["acknowledged_hop_sequence"] == "4"
        r.browser_frame(h.browser.delivery(input_frame(r)))

    asyncio.run(run())


@pytest.mark.parametrize("positive", [True, False])
def test_revocation_and_cleanup_proof_control_slot_reuse(positive: bool) -> None:
    async def run() -> None:
        h, r = await active()
        h.runtime.cleanup_positive = positive
        h.validator.valid = False
        with pytest.raises(RelayFailure) as error:
            r.browser_frame(h.browser.delivery(input_frame(r)))
        assert r._runtime_queue.items.empty()
        await r.close(error.value)
        assert h.authority.record_count == (0 if positive else 1)
        assert not h.active()

    asyncio.run(run())


def test_stale_lease_cannot_renew_or_detach_and_runtime_health_is_independent() -> None:
    async def run() -> None:
        h, r = await active()
        h.clock.ns += 30_000_000_000
        with pytest.raises(RelayFailure):
            r.browser_frame(h.browser.delivery(control(r, F.HEARTBEAT, sent_at_monotonic_tick="1")))
        with pytest.raises(RelayFailure):
            r.browser_frame(h.browser.delivery(control(r, F.DETACH)))
        h, r = await active()
        h.clock.ns += 10_000_000_000
        with pytest.raises(RelayFailure) as error:
            await r._watch()
        assert error.value.code == "RUNTIME_UNAVAILABLE"

    asyncio.run(run())


def test_full_relay_run_real_crypto_keeps_api_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        h = Harness()

        def now() -> float:
            return h.clock.ns / 1e9

        key = bytes(range(32))
        pin = hashlib.sha256(
            X25519PrivateKey.from_private_bytes(key).public_key().public_bytes_raw()
        ).hexdigest()
        browser_crypto = BrowserCryptoProfile(h.a, "2", pin, clock=now)
        runtime_crypto = RuntimeCryptoProfile(h.a, "2", key, clock=now)
        h.browser.incoming.get_nowait()
        h.browser.incoming.get_nowait()
        h.browser.incoming.put_nowait(h.frame(F.WS_HELLO, BA, 1))
        h.browser.incoming.put_nowait(encode_wire_frame(F.KEY_INIT, BA, browser_crypto.start(), 2))
        runtime_send = h.runtime.send
        delivered = asyncio.Event()
        canary = b"R8-PRIVATE-TERMINAL-CANARY"
        output_plaintext = b"R8-PRIVATE-OUTPUT-CANARY"
        output_ciphertext = b""

        async def send_runtime(raw: bytes) -> None:
            frame = decode_wire_frame(raw, AR)
            if frame.frame_type == F.KEY_INIT:
                h.runtime.sent.append(raw)
                h.runtime._reply(F.HELLO_ACK, 1)
                h.runtime.incoming.put_nowait(
                    encode_wire_frame(
                        F.KEY_ATTEST, RA, runtime_crypto.receive_init(frame.json_payload), 2
                    )
                )
            elif frame.frame_type == F.KEY_CONFIRM:
                h.runtime.sent.append(raw)
                h.runtime.incoming.put_nowait(
                    encode_wire_frame(
                        F.KEY_CONFIRM_ACK, RA, runtime_crypto.receive_confirm(frame.json_payload), 3
                    )
                )
            elif frame.frame_type == F.INPUT:
                h.runtime.sent.append(raw)
                assert runtime_crypto.decrypt_input(frame.payload) == canary
                r.runtime_frame(ack(r, hop=frame.hop_sequence, result="accepted"))
                r.runtime_frame(ack(r, hop=frame.hop_sequence, result="written_to_pty"))
            else:
                await runtime_send(raw)

        async def send_browser(raw: bytes) -> None:
            nonlocal output_ciphertext
            frame = decode_wire_frame(raw, AB)
            h.browser.sent.append(raw)
            if frame.frame_type == F.KEY_ATTEST:
                confirm = browser_crypto.receive_attest(frame.json_payload)
                h.browser.incoming.put_nowait(encode_wire_frame(F.KEY_CONFIRM, BA, confirm, 3))
            elif frame.frame_type == F.KEY_CONFIRM_ACK:
                browser_crypto.receive_ack(frame.json_payload)
            elif frame.frame_type == F.ADMITTED:
                assert browser_crypto.crypto_ready
                h.browser.incoming.put_nowait(
                    encode_wire_frame(F.INPUT, BA, browser_crypto.encrypt_input(canary), 4)
                )
                output_ciphertext = runtime_crypto.encrypt_output(output_plaintext, 1)
                h.runtime.incoming.put_nowait(
                    encode_wire_frame(F.OUTPUT, RA, output_ciphertext, r.wire.expected_sequence(RA))
                )
            elif frame.frame_type == F.OUTPUT:
                assert frame.payload == output_ciphertext
                assert (
                    browser_crypto.decrypt_output(frame.payload, expected_cursor=1)
                    == output_plaintext
                )
            elif (
                frame.frame_type == F.ACK
                and frame.json_payload is not None
                and frame.json_payload["result"] == "written_to_pty"
            ):
                delivered.set()
            await asyncio.sleep(0)

        monkeypatch.setattr(h.runtime, "send", send_runtime)
        monkeypatch.setattr(h.browser, "send_key_frame", send_browser)
        r = relay(h)
        task = asyncio.create_task(r.run())
        await asyncio.wait_for(delivered.wait(), 2)
        assert all(
            canary not in raw and output_plaintext not in raw
            for raw in h.browser.sent + h.runtime.sent
        )
        assert canary.decode() not in repr(r.__dict__)
        assert not any("crypto" in name for name in r.__dict__)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert h.authority.record_count == 0

    asyncio.run(run())


def test_uds_read_handoff_preserves_partial_frame_and_fixed_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        import agentbox_api.waw_relay as module

        h = Harness()
        directory = tempfile.TemporaryDirectory(prefix="r8-", dir="/tmp")
        path = Path(directory.name) / "stream.sock"
        control_path = Path(directory.name) / "control.sock"
        monkeypatch.setattr(module, "_STREAM_PATH", path)
        first = encode_wire_frame(
            F.HEARTBEAT,
            RA,
            {
                "protocol_version": 1,
                "attachment_id": h.ticket.claims.attachment_id,
                "lease_number": str(h.ticket.claims.lease_number),
                "sent_at_monotonic_tick": "1",
            },
            6,
        )
        wrote_header, release = asyncio.Event(), asyncio.Event()
        actions: list[str] = []

        async def stream(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write(first[:24])
            await writer.drain()
            wrote_header.set()
            await release.wait()
            writer.write(first[24:] + first)
            await writer.drain()
            await _reader.read()
            writer.close()

        async def control_server(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            request = decode_control_request(await reader.readline())
            action = request.pop("action")
            actions.append(action)
            if action.endswith("prepare"):
                response = {**request, "status": "PREPARED", "capability": "c" * 64}
            else:
                response = {
                    **request,
                    "status": "DETACHED",
                    "cleanup_state": "ATTACH_PTY_CLOSED",
                    "reason_code": None,
                }
            writer.write(encode_control_response(response, action))
            await writer.drain()
            writer.close()

        stream_server = await asyncio.start_unix_server(stream, path)
        server = await asyncio.start_unix_server(control_server, control_path)
        os.chmod(control_path, 0o660)
        client = WAWControlClient(
            control_path,
            expected_peer_uid=os.getuid(),
            expected_peer_gid=os.getgid(),
            expected_socket_uid=os.lstat(control_path).st_uid,
            expected_socket_gid=os.lstat(control_path).st_gid,
        )
        # This test isolates reader handoff. Production peer ownership is tested
        # through the bound coordinator/control-path suites.
        peer_reader, peer_writer = os.pipe()
        monkeypatch.setattr(
            client,
            "_capture_unbound_peer",
            lambda _socket: control_subject._RuntimePeerObservation(
                pid=os.getpid(),
                uid=os.getuid(),
                gid=os.getgid(),
                pidfd=os.dup(peer_reader),
            ),
        )

        class Control:
            attestation = {"runtime_epoch": "2"}

            def borrow_runtime_peer(self, _peer_socket: object) -> RuntimePeerBorrow:
                raise AssertionError("reader-handoff fixture bypasses stream connect")

            async def request_lifecycle(
                self, action: str, request: dict[str, Any]
            ) -> dict[str, Any]:
                return await client._request_unbound_test_only(action, request)

        port = UnixRuntimePort(Control(), RuntimeSocketTrust(os.getgid(), os.getuid(), os.getgid()))

        async def connect_fixture() -> None:
            peer = socket.socket(socket.AF_UNIX)
            peer.setblocking(False)
            await asyncio.get_running_loop().sock_connect(peer, str(path))
            port._socket = peer

        monkeypatch.setattr(port, "_connect", connect_fixture)
        monkeypatch.setattr(port, "_current", lambda: None)
        prepared = await port.prepare(
            RuntimePrepareRequest(h.ticket.claims, "2", port.connection_id)
        )
        assert prepared.capability == "c" * 64
        task = asyncio.create_task(port.receive())
        await wrote_header.wait()
        await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await port.receive() == first
        assert await port.receive() == first
        proof = await port.close_and_cleanup(
            RuntimeCleanupRequest(h.ticket.claims, "2", port.connection_id, None)
        )
        assert proof.cleanup_state == "ATTACH_PTY_CLOSED"
        assert actions == ["workspace.attach.prepare", "workspace.attach.detach"]
        server.close()
        stream_server.close()
        await server.wait_closed()
        await stream_server.wait_closed()
        os.close(peer_reader)
        os.close(peer_writer)
        directory.cleanup()

    asyncio.run(run())


def test_read_only_cookie_auth_and_durable_metadata(
    services: ControlPlaneServices, settings: Settings, clock: FakeClock
) -> None:
    password = "r8 synthetic authentication password"
    services.admin.initialize("admin", password)
    issued = services.auth.login(
        username="admin", password=password, source_identifier="fixture", request_id=None
    )
    h = Harness()
    handler = object.__new__(WAWStreamHandler)
    handler.services, handler.settings = services, settings
    with services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, issued.session_id)
        assert stored is not None
        before = stored.last_seen_at, stored.idle_expires_at
    clock.advance(seconds=1)
    authenticated = handler._authenticate(issued.token)
    assert authenticated.session_id == issued.session_id
    with services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, issued.session_id)
        assert stored is not None and (stored.last_seen_at, stored.idle_expires_at) == before

    async def persist() -> None:
        await h.coordinator.run()
        audit = DurableAdmissionAudit(services, issued.user_id)
        for event in h.audit.events:
            await audit.persist(event)

    asyncio.run(persist())
    with services.database.transaction() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action.like("workspace.attachment_%"))
        ).all()
        assert len(events) == 2
        retained = json.dumps([event.metadata_json for event in events])
        assert (
            h.ticket.ticket not in retained
            and issued.token not in retained
            and "private-session" not in retained
        )


@pytest.mark.parametrize(
    "origin",
    [
        "https://EXAMPLE.test",
        "https://example.test:443",
        "https://example.test/",
        "https://example.test.",
        "https://127.000.0.1",
        "https://[0:0:0:0:0:0:0:1]",
        "https://a..test",
        "http://example.test",
        "https://example.test:0444",
    ],
)
def test_noncanonical_origin_rejected(origin: str) -> None:
    with pytest.raises(RelayFailure):
        _canonical_origin(origin)


def test_failed_attempt_budget_bounded_without_bearer_keys() -> None:
    budget = FailedAdmissionBudget()
    for _ in range(5):
        budget.check("session:fixture", 1, failed=True)
    with pytest.raises(RelayFailure):
        budget.check("session:fixture", 2)
    budget.check("session:fixture", 61)
    assert len(budget._failures) == 0


def test_actual_api_upgrade_admission_and_revocation_fences_next_input(
    services: ControlPlaneServices, settings: Settings
) -> None:
    async def run() -> None:
        import base64
        import time
        from datetime import datetime

        from agentbox_api.main import create_app
        from agentbox_api.waw_admission import wire_admission_tuple
        from agentbox_api.waw_authorization import SingleAdminWorkspacePolicy
        from agentbox_api.waw_websocket_protocol import WAWWebSocketProtocol
        from agentbox_core.models import Project
        from agentbox_core.waw import AgentType
        from agentbox_core.waw_models import AgentWorkspaceSessionRecord, RuntimeHostInstallation
        from agentbox_core.waw_tickets import AttachmentAuthority, AuthenticatedAttachmentContext
        from agentbox_protocol.waw_crypto_context import derive_context
        from uvicorn import Config, Server

        password = "r8 synthetic full route password"
        services.admin.initialize("admin", password)
        issued = services.auth.login(
            username="admin", password=password, source_identifier="fixture", request_id=None
        )
        h = Harness()
        c = h.ticket.claims
        now = datetime(2026, 8, 9)
        with services.database.transaction() as session:
            session.add(
                Project(
                    id=c.project_id,
                    slug="relay-fixture",
                    display_name="Relay fixture",
                    relative_path="relay-fixture",
                    source_type="local",
                    repository_url=None,
                    default_branch="main",
                    state="ready",
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                RuntimeHostInstallation(
                    id=c.runtime_host_installation_id,
                    revision=1,
                    runtime_type="agentbox-runtime-linux-v1",
                    created_at=now,
                    updated_at=now,
                )
            )
        workspace = services.workspaces.create(
            project_id=c.project_id,
            agent_type=AgentType.CODEX,
            authorization_scope="admin",
            runtime_host_installation_id=c.runtime_host_installation_id,
            runtime_host_installation_revision=1,
            binding_revision=1,
            binding_digest=c.binding_digest,
            executable_fingerprint="d" * 64,
        )
        with services.database.transaction() as session:
            stored = session.get(AgentWorkspaceSessionRecord, workspace.id)
            assert stored is not None
            stored.state = "RUNNING"
        authority = AttachmentAuthority(clock=time.monotonic, authority_epoch=4)
        context = AuthenticatedAttachmentContext(
            issued.session_id, issued.user_id, "admin", "http://localhost", "2", issued.auth_epoch
        )
        h.ticket = authority.issue(
            workspace_id=workspace.id,
            project_id=c.project_id,
            agent_type=AgentType.CODEX,
            attachment_id=c.attachment_id,
            generation=workspace.generation,
            auth_epoch=issued.auth_epoch,
            runtime_host_installation_id=c.runtime_host_installation_id,
            runtime_host_installation_revision=1,
            binding_revision=1,
            binding_digest=c.binding_digest,
            origin=context.origin,
            context=context,
        )
        h.a = wire_admission_tuple(h.ticket.claims)
        h.c = derive_context(h.a, "2")

        class Control:
            attestation = {"runtime_epoch": "2"}

            def borrow_runtime_peer(self, _peer_socket: object) -> RuntimePeerBorrow:
                raise AssertionError("backpressure fixture uses an installed socket")

            async def request_lifecycle(
                self, action: str, request: dict[str, Any]
            ) -> dict[str, Any]:
                raise AssertionError("synthetic admission port owns this test Runtime")

        active_settings = settings.model_copy(update={"allowed_origins": ("http://localhost",)})
        handler = WAWStreamHandler.test_only(
            services=services,
            settings=active_settings,
            authority=authority,
            control=Control(),
            policy=SingleAdminWorkspacePolicy(),
            work_ledger=WAWWorkLedger(),
            runtime_factory=lambda _control: h.runtime,
        )
        app = create_app(
            active_settings,
            services=services,
            waw_attachment_authority=authority,
            waw_stream_handler=handler,
        )
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        address = sock.getsockname()
        server = Server(
            Config(
                app,
                lifespan="off",
                ws=WAWWebSocketProtocol,
                access_log=False,
                proxy_headers=False,
                log_level="critical",
            )
        )
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            await asyncio.sleep(0.001)
        reader, writer = await asyncio.open_connection(*address)

        def send(raw: bytes) -> None:
            key = b"abcd"
            prefix = (
                bytes((0x82, 0x80 | len(raw)))
                if len(raw) < 126
                else b"\x82\xfe" + len(raw).to_bytes(2, "big")
            )
            writer.write(
                prefix + key + bytes(value ^ key[index % 4] for index, value in enumerate(raw))
            )

        async def receive() -> tuple[int, bytes]:
            first, length = await asyncio.wait_for(reader.readexactly(2), 3)
            if length == 126:
                length = int.from_bytes(await reader.readexactly(2), "big")
            return first & 15, await reader.readexactly(length)

        try:
            writer.write(
                (
                    f"GET /api/v1/workspaces/{workspace.id}/stream HTTP/1.1\r\n"
                    "Host: localhost\r\nOrigin: http://localhost\r\n"
                    "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    "Sec-WebSocket-Version: 13\r\n"
                    "Sec-WebSocket-Protocol: agentbox-waw-v1\r\n"
                    f"Sec-WebSocket-Key: {base64.b64encode(b'0123456789abcdef').decode()}\r\n"
                    f"Cookie: agentbox_session={issued.token}\r\n\r\n"
                ).encode()
            )
            response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
            assert response.startswith(b"HTTP/1.1 101")
            send(h.frame(F.WS_HELLO, BA, 1))
            send(h.frame(F.KEY_INIT, BA, 2))
            opcode, raw = await receive()
            assert opcode == 2 and decode_wire_frame(raw, AB).frame_type == F.KEY_ATTEST
            send(h.frame(F.KEY_CONFIRM, BA, 3))
            assert decode_wire_frame((await receive())[1], AB).frame_type == F.KEY_CONFIRM_ACK
            assert decode_wire_frame((await receive())[1], AB).frame_type == F.ADMITTED
            assert authority.active_count == 1
            with services.database.transaction() as session:
                stored_session = session.get(ControlPlaneSession, issued.session_id)
                assert stored_session is not None
                stored_session.auth_epoch += 1
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
            send(encode_wire_frame(F.INPUT, BA, envelope, 4))
            opcode, raw = await receive()
            assert opcode == 8 and int.from_bytes(raw, "big") == 4403
            assert all(decode_wire_frame(raw, AR).frame_type != F.INPUT for raw in h.runtime.sent)
            assert authority.active_count == 0 and authority.record_count == 0
        finally:
            writer.close()
            await writer.wait_closed()
            server.should_exit = True
            await serving

    asyncio.run(run())


@pytest.mark.parametrize("detach", [False, True])
def test_runtime_terminal_batch_drains_before_transport_cleanup(detach: bool) -> None:
    async def run() -> None:
        h = Harness()
        r = relay(h)
        task = asyncio.create_task(r.run())
        async with asyncio.timeout(2):
            while len(h.browser.sent) < 3:
                await asyncio.sleep(0.001)
            if detach:
                h.browser.incoming.put_nowait(control(r, F.DETACH))
                while not any(
                    decode_wire_frame(raw, AR).frame_type == F.DETACH for raw in h.runtime.sent
                ):
                    await asyncio.sleep(0.001)
                h.runtime.incoming.put_nowait(
                    encode_wire_frame(
                        F.DETACH_ACK,
                        RA,
                        {
                            "protocol_version": 1,
                            **h.a,
                            "runtime_epoch": "2",
                            "acknowledged_hop_sequence": "6",
                            "result": "detached",
                            "cleanup_state": "ATTACH_PTY_CLOSED",
                            "reason_code": None,
                        },
                        6,
                    )
                )
            else:
                h.runtime.incoming.put_nowait(
                    encode_wire_frame(
                        F.EXIT, RA, {"protocol_version": 1, "state": "EXITED", "exit_code": 0}, 6
                    )
                )
                h.runtime.incoming.put_nowait(
                    encode_wire_frame(
                        F.CLOSE,
                        RA,
                        {
                            "protocol_version": 1,
                            "code": "WORKSPACE_EXITED",
                            "workspace_state_at_close": "EXITED",
                        },
                        7,
                    )
                )
            await task
        assert [decode_wire_frame(raw, AB).frame_type for raw in h.browser.sent][-2:] == [
            F.DETACH_ACK if detach else F.EXIT,
            F.CLOSE,
        ]
        assert h.browser.closed == 1000 and h.authority.record_count == 0

    asyncio.run(run())


def test_cancellation_resistant_cleanup_is_bounded_and_never_releases_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        h, r = await active()
        original = h.runtime.close_and_cleanup
        release = asyncio.Event()

        async def blocked(request: RuntimeCleanupRequest) -> Any:
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
            return await original(request)

        monkeypatch.setattr(h.runtime, "close_and_cleanup", blocked)
        started = asyncio.get_running_loop().time()
        await r.close(RelayFailure("ATTACHMENT_STALE", 4403))
        assert asyncio.get_running_loop().time() - started < 1.2
        assert h.authority.record_count == 1 and not h.active()
        assert len(h.audit.events) == 3
        release.set()
        if r._cleanup_tasks:
            await asyncio.gather(*r._cleanup_tasks)
        assert h.authority.record_count == 1

    asyncio.run(run())


def test_ack_map_capacity_does_not_allocate_a_257th_reference() -> None:
    async def run() -> None:
        h, r = await active()
        for n in range(1, 257):
            r.browser_frame(h.browser.delivery(input_frame(r, crypto=n)))
            queued = r._runtime_queue.items.get_nowait()
            r._runtime_queue.done(queued)
        before = r.wire.expected_sequence(AR)
        with pytest.raises(RelayFailure) as error:
            r.browser_frame(h.browser.delivery(input_frame(r, crypto=257)))
        assert error.value.code == "INPUT_RATE_LIMITED"
        assert r.wire.expected_sequence(AR) == before and len(r._inputs) == 256

    asyncio.run(run())


@pytest.mark.parametrize("fence", ["exit", "detach", "error", "state"])
def test_terminal_fence_discards_unpublished_ciphertext_without_hop_gap(fence: str) -> None:
    async def run() -> None:
        h, r = await active()
        r.runtime_frame(input_frame(r, output=True))
        unpublished_hop = r._browser_published_next
        with pytest.raises(RelayFailure) as failure:
            if fence == "detach":
                r.browser_frame(h.browser.delivery(control(r, F.DETACH)))
            else:
                kind, body = {
                    "exit": (F.EXIT, {"protocol_version": 1, "state": "EXITED", "exit_code": 0}),
                    "error": (
                        F.ERROR,
                        {
                            "protocol_version": 1,
                            "code": "RUNTIME_UNAVAILABLE",
                            "retryable": False,
                            "request_id": "wreq_" + "a" * 32,
                        },
                    ),
                    "state": (
                        F.STATE,
                        {
                            "protocol_version": 1,
                            "workspace_id": r.claims.workspace_id,
                            "project_id": r.claims.project_id,
                            "agent_type": str(r.claims.agent_type),
                            "generation": str(r.claims.generation),
                            "runtime_epoch": r.context.runtime_epoch,
                            "state": "LOGIN_REQUIRED",
                            "reason_code": "WORKSPACE_AUTH_REQUIRED",
                        },
                    ),
                }[fence]
                r.runtime_frame(encode_wire_frame(kind, RA, body, r.wire.expected_sequence(RA)))
        assert r._browser_queue.items.empty() and r._browser_queue.sizes == [0, 0]
        assert r._browser_published_next == unpublished_hop
        assert r.wire.expected_sequence(AB) > unpublished_hop
        await r.close(failure.value)
        assert [decode_wire_frame(raw, AB).frame_type for raw in h.browser.sent] == [
            F.KEY_ATTEST,
            F.KEY_CONFIRM_ACK,
            F.ADMITTED,
        ]
        assert h.authority.record_count == 0

    asyncio.run(run())


@pytest.mark.parametrize("condition", ["revoked", "expired", "health", "exited", "detaching"])
def test_every_queued_output_rechecks_permission_without_terminal_exception(condition: str) -> None:
    async def run() -> None:
        h, r = await active()
        r.runtime_frame(input_frame(r, output=True))
        if condition == "revoked":
            h.validator.valid = False
        elif condition == "expired":
            h.clock.ns += 30_000_000_000
        elif condition == "health":
            h.clock.ns += 10_000_000_000
        elif condition == "exited":
            r._exited = True
        else:
            r._detaching = True
        with pytest.raises(RelayFailure):
            await r._writer(r._browser_queue, browser=True)
        assert r._browser_published_next == 4
        assert all(decode_wire_frame(raw, AB).frame_type != F.OUTPUT for raw in h.browser.sent)
        await r.close(RelayFailure("ATTACHMENT_STALE", 4403))

    asyncio.run(run())


def test_revocation_blocks_already_queued_terminal_metadata() -> None:
    async def run() -> None:
        h, r = await active()
        r.runtime_frame(
            encode_wire_frame(
                F.EXIT, RA, {"protocol_version": 1, "state": "EXITED", "exit_code": 0}, 6
            )
        )
        h.validator.valid = False
        with pytest.raises(RelayFailure):
            await r._writer(r._browser_queue, browser=True)
        assert r._browser_published_next == 4
        assert all(decode_wire_frame(raw, AB).frame_type != F.EXIT for raw in h.browser.sent)
        await r.close(RelayFailure("ATTACHMENT_STALE", 4403))

    asyncio.run(run())


def test_terminal_fence_aborts_partial_output_and_never_appends_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        h, r = await active()
        entered, released = asyncio.Event(), asyncio.Event()
        prefixes: list[bytes] = []
        aborted = False

        async def partial(frame: bytes) -> None:
            prefixes.append(frame[:13])
            entered.set()
            await released.wait()
            raise RelayFailure("ATTACHMENT_STALE", 4403)

        def abort(code: int) -> None:
            nonlocal aborted
            aborted = True
            h.browser.close(code)
            released.set()

        monkeypatch.setattr(h.browser, "send_key_frame", partial)
        monkeypatch.setattr(h.browser, "abort", abort, raising=False)
        r.runtime_frame(input_frame(r, output=True))
        writing = asyncio.create_task(r._writer(r._browser_queue, browser=True))
        await entered.wait()
        with pytest.raises(RelayFailure):
            r.runtime_frame(
                encode_wire_frame(
                    F.EXIT,
                    RA,
                    {"protocol_version": 1, "state": "EXITED", "exit_code": 0},
                    r.wire.expected_sequence(RA),
                )
            )
        with pytest.raises(RelayFailure):
            await writing
        await r.close(RelayFailure("ATTACHMENT_STALE", 4403))
        assert aborted and r._publication_uncertain and r._browser_published_next == 4
        assert len(prefixes) == 1 and len(prefixes[0]) == 13
        assert h.authority.record_count == 0

    asyncio.run(run())


def test_completed_output_frontier_preserves_contiguous_terminal_metadata() -> None:
    async def run() -> None:
        h, r = await active()
        r.runtime_frame(input_frame(r, output=True))
        writing = asyncio.create_task(r._writer(r._browser_queue, browser=True))
        async with asyncio.timeout(2):
            while r._browser_published_next != 5:
                await asyncio.sleep(0)
            r.runtime_frame(
                encode_wire_frame(
                    F.EXIT, RA, {"protocol_version": 1, "state": "EXITED", "exit_code": 0}, 7
                )
            )
            r.runtime_frame(
                encode_wire_frame(
                    F.CLOSE,
                    RA,
                    {
                        "protocol_version": 1,
                        "code": "WORKSPACE_EXITED",
                        "workspace_state_at_close": "EXITED",
                    },
                    8,
                )
            )
            with pytest.raises(RelayFailure) as failure:
                await writing
        assert failure.value.close_code == 1000 and r._browser_published_next == 7
        frames = [decode_wire_frame(raw, AB) for raw in h.browser.sent]
        assert [frame.hop_sequence for frame in frames] == list(range(1, 7))
        assert [frame.frame_type for frame in frames][-3:] == [F.OUTPUT, F.EXIT, F.CLOSE]
        await r.close(failure.value)

    asyncio.run(run())


@pytest.mark.parametrize("table", ["runtime_ping", "runtime_response", "browser_ping"])
@pytest.mark.parametrize("operation", ["input", "runtime_write", "browser_write"])
def test_ping_deadline_is_an_immediate_io_fence(table: str, operation: str) -> None:
    async def run() -> None:
        h, r = await active()
        if table == "runtime_ping":
            h.clock.ns += 20_000_000_000
            r.last_runtime_heartbeat = h.clock.ns / 1e9
            watcher = asyncio.create_task(r._watch())
            async with asyncio.timeout(1):
                while not r._runtime_ping:
                    await asyncio.sleep(0)
            watcher.cancel()
            with pytest.raises(asyncio.CancelledError):
                await watcher
        else:
            leg = RA if table == "runtime_response" else BA
            raw = encode_wire_frame(
                F.PING,
                leg,
                {"protocol_version": 1, "nonce": "a" * 16, "sent_at_monotonic_tick": "1"},
                r.wire.expected_sequence(leg),
            )
            if leg == RA:
                r.runtime_frame(raw)
            else:
                r.browser_frame(h.browser.delivery(raw))
        if operation == "runtime_write":
            r.browser_frame(h.browser.delivery(input_frame(r)))
        elif operation == "browser_write":
            r.runtime_frame(input_frame(r, output=True))
        h.clock.ns += 5_000_000_000
        with pytest.raises(RelayFailure):
            if operation == "input":
                r.browser_frame(h.browser.delivery(input_frame(r)))
            elif operation == "runtime_write":
                await r._writer(r._runtime_queue, browser=False)
            else:
                await r._writer(r._browser_queue, browser=True)
        assert r._publication_fenced and h.runtime.aborted and not h.active()
        assert all(decode_wire_frame(raw, AR).frame_type != F.INPUT for raw in h.runtime.sent)
        assert all(decode_wire_frame(raw, AB).frame_type != F.OUTPUT for raw in h.browser.sent)
        await r.close(RelayFailure("ATTACHMENT_STALE", 4403))

    asyncio.run(run())


def test_runtime_error_gets_fresh_browser_correlation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        _h, r = await active()
        monkeypatch.setattr(
            "agentbox_api.waw_relay.secrets.token_hex", lambda size: "b" * (size * 2)
        )
        body = {
            "protocol_version": 1,
            "code": "RUNTIME_UNAVAILABLE",
            "retryable": False,
            "request_id": "wreq_" + "a" * 32,
        }
        r.runtime_frame(encode_wire_frame(F.ERROR, RA, body, 6))
        translated = decode_wire_frame(r._browser_queue.items.get_nowait()[0], AB).json_payload
        assert translated == {**body, "request_id": "wreq_" + "b" * 32}

    asyncio.run(run())


def test_uds_backpressure_rechecks_guard_before_resuming_kernel_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        class Control:
            attestation = {"runtime_epoch": "2"}

            def borrow_runtime_peer(self, _peer_socket: object) -> RuntimePeerBorrow:
                raise AssertionError("backpressure fixture uses an installed socket")

            async def request_lifecycle(
                self, action: str, request: dict[str, Any]
            ) -> dict[str, Any]:
                raise AssertionError("No control operation in this transport test")

        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        left.setblocking(False)
        right.setblocking(False)
        left.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        filled = 0
        while True:
            try:
                filled += left.send(b"x" * 4096)
            except BlockingIOError:
                break
        port = UnixRuntimePort(Control(), RuntimeSocketTrust(os.getgid(), os.getuid(), os.getgid()))
        port._socket = left
        monkeypatch.setattr(port, "_current", lambda: None)
        allowed = True
        checks = 0

        def guard(_raw: bytes) -> None:
            nonlocal checks
            checks += 1
            if not allowed:
                port.abort()
                raise RelayFailure("ATTACHMENT_STALE", 4403)

        port.install_send_guard(guard)
        raw = encode_wire_frame(
            F.HEARTBEAT,
            AR,
            {
                "protocol_version": 1,
                "attachment_id": "att_" + "a" * 32,
                "lease_number": "1",
                "sent_at_monotonic_tick": "1",
            },
            6,
        )
        sending = asyncio.create_task(port.send(raw))
        async with asyncio.timeout(1):
            while port._write_waiter is None:
                await asyncio.sleep(0)
        allowed = False
        observed = bytearray()
        while len(observed) < filled:
            observed.extend(
                await asyncio.get_running_loop().sock_recv(right, filled - len(observed))
            )
        with pytest.raises(RelayFailure):
            await asyncio.wait_for(sending, 1)
        assert checks >= 2 and observed == b"x" * filled
        assert await asyncio.get_running_loop().sock_recv(right, 65536) == b""
        right.close()

    asyncio.run(run())


def test_authority_fence_failure_propagates_and_does_not_release_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        h, r = await active()

        def failure(_handle: Any) -> None:
            raise RuntimeError("synthetic authority fence failure")

        monkeypatch.setattr(h.authority, "fence", failure)
        with pytest.raises(RuntimeError, match="synthetic authority fence failure"):
            r._fence_io(RelayFailure("ATTACHMENT_STALE", 4403))
        assert r._publication_fenced and h.runtime.aborted
        assert h.authority.record_count == 1
        assert not h.runtime.cleanup_requests  # Abort is never a positive cleanup proof.

    asyncio.run(run())


def test_run_cancellation_propagates_fence_failure_after_complete_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        h = Harness()
        r = relay(h)
        fence_error = RuntimeError("synthetic authority fence failure")

        def fail_fence(_handle: Any) -> None:
            raise fence_error

        monkeypatch.setattr(h.authority, "fence", fail_fence)
        running = asyncio.create_task(r.run())
        async with asyncio.timeout(2):
            while len(h.browser.sent) < 3:
                await asyncio.sleep(0.001)
        running.cancel()
        with pytest.raises(RuntimeError) as raised:
            await running
        assert raised.value is fence_error
        assert len(h.runtime.cleanup_requests) == 1
        assert [event.action for event in h.audit.events][-1:] == [A.DETACHED]
        assert h.runtime.aborted and h.browser.closed == 4403
        assert h.input_budget.closed and r.wire.closed
        assert h.authority.record_count == 1

    asyncio.run(run())


def test_concurrent_and_repeated_close_share_fence_result_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        h, r = await active()
        fence_error = RuntimeError("synthetic authority fence failure")
        cleanup_error = RuntimeError("secondary Runtime cleanup failure")
        audit_error = RuntimeError("secondary Audit failure")
        cleanup_entered, cleanup_release = asyncio.Event(), asyncio.Event()
        fence_calls = 0
        audit_calls = 0

        def fail_fence(_handle: Any) -> None:
            nonlocal fence_calls
            fence_calls += 1
            raise fence_error

        async def fail_cleanup(request: RuntimeCleanupRequest) -> Any:
            h.runtime.cleanup_requests.append(request)
            cleanup_entered.set()
            await cleanup_release.wait()
            raise cleanup_error

        async def fail_audit(event: Any) -> None:
            nonlocal audit_calls
            audit_calls += 1
            assert event.action == A.DETACHED
            raise audit_error

        monkeypatch.setattr(h.authority, "fence", fail_fence)
        monkeypatch.setattr(h.runtime, "close_and_cleanup", fail_cleanup)
        monkeypatch.setattr(h.audit, "persist", fail_audit)
        first = asyncio.create_task(r.close(RelayFailure("ATTACHMENT_STALE", 4403)))
        await asyncio.wait_for(cleanup_entered.wait(), 1)
        shared = r._close_task
        second = asyncio.create_task(r.close(RelayFailure("PROTOCOL_INVALID", 4400)))
        first.cancel()
        cleanup_release.set()
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert len(results) == 2
        assert results[0] is fence_error and results[1] is fence_error
        assert r._close_task is shared and shared is not None and shared.done()
        with pytest.raises(RuntimeError) as repeated:
            await r.close(RelayFailure("RUNTIME_UNAVAILABLE", 1013))
        assert repeated.value is fence_error
        assert fence_calls == len(h.runtime.cleanup_requests) == audit_calls == 1
        assert h.runtime.aborted and h.browser.closed == 4403
        assert h.input_budget.closed and r.wire.closed
        assert h.authority.record_count == 1

    asyncio.run(run())


@pytest.mark.parametrize("fence_fails", [False, True])
def test_close_frame_emit_failure_still_runs_fixed_cleanup(
    monkeypatch: pytest.MonkeyPatch, fence_fails: bool
) -> None:
    async def run() -> None:
        h, r = await active()
        emit = r._emit
        fence_error = RuntimeError("synthetic authority fence failure")

        def fail_close_emit(kind: F, leg: Leg, body: dict[str, Any]) -> bytes:
            if kind == F.CLOSE and leg == AR:
                raise RuntimeError("secondary CLOSE encode failure")
            return emit(kind, leg, body)

        def fail_fence(_handle: Any) -> None:
            raise fence_error

        monkeypatch.setattr(r, "_emit", fail_close_emit)
        if fence_fails:
            monkeypatch.setattr(h.authority, "fence", fail_fence)
            with pytest.raises(RuntimeError) as raised:
                await r.close(RelayFailure("ATTACHMENT_STALE", 4403))
            assert raised.value is fence_error
        else:
            await r.close(RelayFailure("ATTACHMENT_STALE", 4403))
        assert len(h.runtime.cleanup_requests) == 1
        assert h.runtime.cleanup_requests[0].close_frame is None
        assert [event.action for event in h.audit.events][-1:] == [A.DETACHED]
        assert h.input_budget.closed and r.wire.closed
        assert h.authority.record_count == (1 if fence_fails else 0)

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["input_rate", "input_size", "malformed", "output_queue"])
def test_first_fatal_frame_fences_other_writers_before_return(failure: str) -> None:
    async def run() -> None:
        h, r = await active()
        if failure == "input_rate":
            r.browser_frame(h.browser.delivery(input_frame(r, size=16384)))
        elif failure == "output_queue":
            for sequence in range(1, 6):
                r.runtime_frame(input_frame(r, size=32768, crypto=sequence, output=True))
        with pytest.raises(RelayFailure) as error:
            if failure == "input_rate":
                r.browser_frame(h.browser.delivery(input_frame(r, crypto=2)))
            elif failure == "input_size":
                r.browser_frame(h.browser.delivery(input_frame(r, size=16385)))
            elif failure == "malformed":
                r.runtime_frame(b"invalid")
            else:
                r.runtime_frame(input_frame(r, size=32768, crypto=6, output=True))
        assert r._publication_fenced and not h.active() and h.runtime.aborted
        with pytest.raises(RelayFailure):
            r.runtime_frame(input_frame(r, output=True))
        if not r._browser_queue.items.empty():
            with pytest.raises(RelayFailure):
                await r._writer(r._browser_queue, browser=True)
        if not r._runtime_queue.items.empty():
            with pytest.raises(RelayFailure):
                await r._writer(r._runtime_queue, browser=False)
        assert all(decode_wire_frame(raw, AB).frame_type != F.OUTPUT for raw in h.browser.sent)
        assert all(decode_wire_frame(raw, AR).frame_type != F.INPUT for raw in h.runtime.sent)
        await r.close(error.value)

    asyncio.run(run())


def test_native_close_blocks_queued_runtime_input_before_reader_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        h, r = await active()
        r.browser_frame(h.browser.delivery(input_frame(r)))
        monkeypatch.setattr(h.browser, "transport_open", False, raising=False)
        with pytest.raises(RelayFailure):
            await r._writer(r._runtime_queue, browser=False)
        assert r._publication_fenced and h.runtime.aborted and not h.active()
        assert all(decode_wire_frame(raw, AR).frame_type != F.INPUT for raw in h.runtime.sent)
        await r.close(RelayFailure("ATTACHMENT_STALE", 4403))

    asyncio.run(run())


def test_stream_abort_closes_only_its_bound_peer_borrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, writer, _owner = _published_runtime_peer()
    monkeypatch.setattr(
        control_subject,
        "_peer_credentials",
        lambda _socket: (7331, os.getuid(), os.getgid()),
    )

    class Control:
        attestation = {"runtime_epoch": "2"}

        def borrow_runtime_peer(self, peer_socket: object) -> RuntimePeerBorrow:
            return peer.borrow(peer_socket)

        async def request_lifecycle(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError((action, request))

    port = UnixRuntimePort(Control(), RuntimeSocketTrust(os.getgid(), os.getuid(), os.getgid()))
    borrow = peer.borrow(object())
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    port._peer_borrow = borrow
    port._socket = left

    port.abort()
    port.abort()

    assert not borrow.current()
    assert peer.current()
    right.close()
    peer.close()
    os.close(writer)


def test_control_rebind_generation_immediately_fences_old_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer, writer, owner = _published_runtime_peer()
    monkeypatch.setattr(
        control_subject,
        "_peer_credentials",
        lambda _socket: (7331, os.getuid(), os.getgid()),
    )

    class Control:
        attestation = {"runtime_epoch": "2"}

        def borrow_runtime_peer(self, peer_socket: object) -> RuntimePeerBorrow:
            return peer.borrow(peer_socket)

        async def request_lifecycle(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError((action, request))

    port = UnixRuntimePort(Control(), RuntimeSocketTrust(os.getgid(), os.getuid(), os.getgid()))
    port._peer_borrow = peer.borrow(object())
    owner["peer"] = object()
    owner["generation"] = 2

    with pytest.raises(RelayFailure) as raised:
        port._current()

    assert raised.value.code == "RUNTIME_UNAVAILABLE"
    port.abort()
    peer.close()
    os.close(writer)
