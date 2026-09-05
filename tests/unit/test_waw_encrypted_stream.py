"""Actual Noise/wire over synthetic process, PTY and capture ports; no host proof."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.awce import decode_awce
from agentbox_protocol.waw_crypto_profile import BrowserCryptoProfile
from agentbox_protocol.waw_wire import Leg, decode_wire_frame, encode_wire_frame
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_encrypted_stream import (
    BoundedRedraw,
    EncryptedStreamError,
    RuntimePeer,
    WAWEncryptedRegistry,
    admission_fields,
)
from agentbox_runtime.waw_supervisor import (
    RuntimeAttachmentCleanupEvidence,
    RuntimeAttachmentLease,
    RuntimeProbeState,
    SupervisorState,
    WAWSupervisor,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from test_waw_supervisor import _attachment, _supervisor

AR, RA = Leg.API_TO_RUNTIME, Leg.RUNTIME_TO_API
KEY = bytes(range(32))
PIN = hashlib.sha256(
    X25519PrivateKey.from_private_bytes(KEY).public_key().public_bytes_raw()
).hexdigest()


def body(raw: bytes) -> dict[str, Any]:
    result = decode_wire_frame(raw, RA).json_payload
    assert result is not None
    return result


class Harness:
    def __init__(self, tmp_path: Path, *, redraw: bytes = b"", truncated: bool = False) -> None:
        self.now = 0.0
        self.valid = True
        self.peer_valid = True
        self.transport: Any
        self.supervisor, self.transport, workspace = _supervisor(tmp_path)
        self.supervisor.start()

        def close_attachment(lease: RuntimeAttachmentLease) -> RuntimeAttachmentCleanupEvidence:
            closed = self.transport.detach()
            return RuntimeAttachmentCleanupEvidence(
                lease,
                closed,
                0 if closed else 1,
            )

        self.transport.close_attachment = close_attachment
        self.claims = _attachment(workspace).claims
        self.peer = RuntimePeer(object(), "1", lambda: self.peer_valid)
        self.registry = WAWEncryptedRegistry(
            runtime_epoch="1", static_key=lambda: KEY, clock=lambda: self.now
        )
        self.redraw = BoundedRedraw(redraw, truncated)
        self.transport.redraw = self.redraw
        self.admission = admission_fields(self.claims)
        self.bound: dict[str, Any] = {"protocol_version": 1, **self.admission, "runtime_epoch": "1"}
        self.browser = BrowserCryptoProfile(self.admission, "1", PIN, clock=lambda: self.now)
        self.capability = self.prepare()
        self.session, self.hello = self.registry.open(self.peer, self.hello_raw())
        self.rx = 2

    def prepare(self, **kwargs: Any) -> str:
        return self.registry.prepare(
            peer=self.peer,
            claims=kwargs.pop("claims", self.claims),
            supervisor=self.supervisor,
            current=lambda: self.valid,
            **kwargs,
        )

    def hello_raw(self, **extra: Any) -> bytes:
        return encode_wire_frame(
            F.RUNTIME_HELLO,
            AR,
            {
                **self.bound,
                "capability": self.capability,
                "resume_cursor": None,
                "previous_runtime_epoch": None,
                **extra,
            },
            1,
        )

    def send(self, kind: F, payload: dict[str, Any] | bytes) -> tuple[bytes, ...]:
        raw = encode_wire_frame(kind, AR, payload, self.rx)
        self.rx += 1
        return self.session.receive(raw)

    def keys(self) -> None:
        attest = decode_wire_frame(self.send(F.KEY_INIT, self.browser.start())[0], RA)
        confirm = self.browser.receive_attest(attest.json_payload)
        ack = decode_wire_frame(self.send(F.KEY_CONFIRM, confirm)[0], RA)
        self.browser.receive_ack(ack.json_payload)

    def ready(self) -> bytes:
        ready = decode_wire_frame(self.send(F.STREAM_READY, self.bound)[0], RA)
        assert ready.json_payload is not None
        return encode_wire_frame(
            F.ADMISSION_COMMIT,
            AR,
            {**self.bound, "admission_fence": ready.json_payload["admission_fence"]},
            5,
        )

    def admit(self) -> bytes:
        self.keys()
        commit = self.ready()
        ack = self.session.receive(commit)[0]
        self.rx = 6
        assert body(ack)["result"] == "committed"
        return commit


def types(frames: tuple[bytes, ...]) -> list[F]:
    return [decode_wire_frame(frame, RA).frame_type for frame in frames]


def test_full_crypto_commit_input_output_detach(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"synthetic marked redraw\n")
    assert h.supervisor.snapshot().attachment_id is None
    h.admit()
    assert h.supervisor.snapshot().attachment_id == h.claims.attachment_id
    frames = h.session.output()
    assert types(frames) == [F.OUTPUT]
    envelope = decode_awce(decode_wire_frame(frames[0], RA).payload)
    assert envelope.crypto_sequence == 1
    assert (
        h.browser.decrypt_output(
            decode_wire_frame(frames[0], RA).payload, expected_cursor=envelope.stream_cursor
        )
        == b"synthetic marked redraw\n"
    )
    accepted = h.send(F.INPUT, h.browser.encrypt_input(b"hello"))
    assert body(accepted[0]) == {
        "protocol_version": 1,
        "runtime_input_hop_sequence": "6",
        "crypto_sequence": "1",
        "result": "accepted",
        "reason_code": None,
    }
    assert h.transport.writes == []
    terminal = h.session.flush_input()
    assert body(terminal[0])["result"] == "written_to_pty"
    assert h.transport.writes == [b"hello"]
    before = h.supervisor.snapshot().buffered_bytes
    detached = h.send(
        F.DETACH,
        {"protocol_version": 1, "attachment_id": h.claims.attachment_id, "lease_number": "1"},
    )
    assert types(detached) == [F.DETACH_ACK]
    assert h.session.cleanup_proof is not None
    assert h.session.cleanup_proof.confirmed
    assert h.supervisor.snapshot().buffered_bytes == before
    assert not h.transport.stopped
    assert h.registry.count == 0


def test_commit_retry_exact_once_no_writer_before_commit(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.keys()
    commit = h.ready()
    assert h.supervisor.snapshot().attachment_id is None
    first = h.session.receive(commit)
    assert h.session.receive(commit) == first
    with pytest.raises(EncryptedStreamError):
        h.session.receive(commit)
    assert h.session.closed


@pytest.mark.parametrize("stage", ["keys", "ready"])
def test_process_state_drift_never_commits(tmp_path: Path, stage: str) -> None:
    h = Harness(tmp_path)
    h.keys()
    commit = h.ready() if stage == "ready" else None
    original = h.transport.probe
    h.transport.probe = lambda: replace(original(), state=RuntimeProbeState.EXITED, exit_code=0)
    with pytest.raises(RuntimeOperationError):
        h.session.receive(commit) if commit else h.ready()
    assert h.session.closed
    assert h.supervisor.snapshot().attachment_id is None


def test_capability_burn_precedes_bound_mismatch(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.session.close()
    claims = replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2)
    cap = h.prepare(claims=claims)
    hello = encode_wire_frame(
        F.RUNTIME_HELLO,
        AR,
        {
            "protocol_version": 1,
            **admission_fields(claims),
            "runtime_epoch": "2",
            "capability": cap,
            "resume_cursor": None,
            "previous_runtime_epoch": None,
        },
        1,
    )
    with pytest.raises(EncryptedStreamError, match="ATTACHMENT_STALE"):
        h.registry.open(h.peer, hello)
    assert h.registry.count == 0
    with pytest.raises(EncryptedStreamError):
        h.prepare(claims=claims)


def test_untrusted_peer_cannot_burn_and_prepare_retry_exact(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.session.close()
    claims = replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2)
    cap = h.prepare(claims=claims)
    assert h.prepare(claims=claims) == cap
    with pytest.raises(EncryptedStreamError):
        h.registry.open(RuntimePeer(object(), "1", lambda: False), h.hello_raw(capability=cap))
    assert h.prepare(claims=claims) == cap


def test_queue_rejection_consumes_nonce_then_next_input_succeeds(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    for _ in range(4):
        assert body(h.send(F.INPUT, h.browser.encrypt_input(b"x"))[0])["result"] == "accepted"
    rejected = h.send(F.INPUT, h.browser.encrypt_input(b"rejected"))
    assert body(rejected[0])["reason_code"] == "INPUT_RATE_LIMITED"
    assert not h.session.closed
    h.session.flush_input()
    next_input = h.send(F.INPUT, h.browser.encrypt_input(b"next"))
    assert body(next_input[0])["crypto_sequence"] == "6"
    h.session.flush_input()
    assert h.transport.writes == [b"x"] * 4 + [b"next"]


def test_bad_ciphertext_no_ack_clears_ring_keeps_workspace(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"secret canary")
    h.admit()
    frame = h.browser.encrypt_input(b"danger")
    with pytest.raises(EncryptedStreamError, match="STREAM_CRYPTO_FAILURE"):
        h.send(F.INPUT, frame[:-1] + bytes([frame[-1] ^ 1]))
    assert h.transport.writes == []
    assert h.supervisor.snapshot().buffered_bytes == 0
    assert not h.transport.stopped
    assert h.session.cleanup_proof is not None
    assert h.session.cleanup_proof.confirmed


def test_partial_write_uncertain_and_no_replay(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.send(F.INPUT, h.browser.encrypt_input(b"abc"))

    def partial(_: bytes) -> None:
        h.transport.writes.append(b"a")
        raise OSError("synthetic partial write")

    h.transport.write = partial
    result = h.session.flush_input()
    assert body(result[0])["result"] == "write_uncertain"
    assert h.transport.writes == [b"a"]
    assert h.session.closed


def test_uncertain_cleanup_blocks_new_writer_then_retry_proves_close(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.transport.detach_confirmed = False
    assert not h.session.close().confirmed
    assert h.registry.count == 1
    with pytest.raises(EncryptedStreamError, match="WORKSPACE_WRITER_BUSY"):
        h.prepare(claims=replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2))
    h.transport.detach_confirmed = True
    assert h.session.close().confirmed
    assert h.registry.count == 0
    with pytest.raises(RuntimeOperationError, match="not running"):
        h.prepare(claims=replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2))
    assert h.supervisor.state is SupervisorState.RECONCILIATION_REQUIRED
    assert h.session.close().confirmed
    assert h.registry.count == 0


def test_revocation_cleanup_does_not_require_live_authority(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.valid = False
    with pytest.raises(EncryptedStreamError):
        h.session.tick()
    assert h.session.cleanup_proof is not None
    assert h.session.cleanup_proof.confirmed
    assert h.transport.writes == []


def test_health_10s_deadline_pong_does_not_renew(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.now = 5
    assert types(h.session.tick()) == [F.HEARTBEAT]
    h.send(F.PING, {"protocol_version": 1, "nonce": "00" * 8, "sent_at_monotonic_tick": "5"})
    h.now = 10
    assert types(h.session.tick()) == [F.CLOSE]
    assert h.session.closed


def test_exit_resolves_accepted_before_exit_and_clears_ring(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"data")
    h.admit()
    h.send(F.INPUT, h.browser.encrypt_input(b"pending"))
    original = h.transport.probe
    h.transport.probe = lambda: replace(original(), state=RuntimeProbeState.EXITED, exit_code=7)
    frames = h.session.tick()
    assert types(frames) == [F.ACK, F.EXIT, F.CLOSE]
    assert body(frames[0])["result"] == "write_uncertain"
    assert h.supervisor.snapshot().buffered_bytes == 0
    assert h.transport.writes == []


def test_fresh_capture_chunking_before_cursor_assignment(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"a" * 60000, truncated=True)
    h.admit()
    frames = h.session.output()
    assert types(frames) == [F.GAP, F.OUTPUT, F.OUTPUT]
    assert body(frames[0])["reason"] == "baseline_redraw"
    assert [
        decode_awce(decode_wire_frame(frame, RA).payload).crypto_sequence for frame in frames[1:]
    ] == [1, 2]
    assert h.supervisor.snapshot().next_cursor == 60001


def test_replay_new_keys_and_crop_before_encryption(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"a")
    h.admit()
    old_frames = h.session.output()
    old_context = decode_awce(decode_wire_frame(old_frames[0], RA).payload).context_id
    source = h.supervisor.output_source()
    for _ in range(3):
        h.supervisor.append_encrypted_output(source, b"x" * 32768)
    h.session.close()
    h.claims = replace(h.claims, attachment_id="att_" + "8" * 32, lease_number=2)
    h.admission = admission_fields(h.claims)
    h.bound = {"protocol_version": 1, **h.admission, "runtime_epoch": "1"}
    h.capability = h.prepare(resume_cursor="1", previous_runtime_epoch="1")
    h.session, _ = h.registry.open(
        h.peer, h.hello_raw(resume_cursor="1", previous_runtime_epoch="1")
    )
    h.browser = BrowserCryptoProfile(h.admission, "1", PIN, clock=lambda: h.now)
    h.rx = 2
    h.admit()
    frames = h.session.output()
    assert sum(map(len, frames)) <= 65536
    assert types(frames) == [F.GAP, F.OUTPUT]
    gap = body(frames[0])
    assert (gap["from_cursor"], gap["to_cursor"]) == ("2", "65538")
    envelope = decode_awce(decode_wire_frame(frames[1], RA).payload)
    assert envelope.context_id != old_context
    assert envelope.crypto_sequence == 1
    assert envelope.stream_cursor == 98305


def test_premature_output_and_shared_deadline_fail_closed(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    with pytest.raises(EncryptedStreamError, match="ATTACHMENT_NOT_READY"):
        h.session.output()
    assert h.session.closed


@pytest.mark.parametrize(
    "code",
    ["WAW_ATTACHMENT_REVOKED", "WAW_ATTACHMENT_EXPIRED", "WAW_PROBE_UNCONFIRMED"],
)
def test_fresh_redraw_preserves_attachment_and_probe_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    def fail(_self: WAWSupervisor, _lease: RuntimeAttachmentLease) -> Any:
        raise RuntimeOperationError(code, "synthetic exact failure", category="conflict")

    monkeypatch.setattr(WAWSupervisor, "publish_fresh_redraw", fail)
    with pytest.raises(RuntimeOperationError) as raised:
        Harness(tmp_path)
    assert raised.value.code == code


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("WAW_REDRAW_TIMEOUT", "OUTPUT_BACKPRESSURE"),
        ("WAW_REDRAW_CAPTURE_FAILED", "OUTPUT_BACKPRESSURE"),
        ("WAW_REDRAW_LIMIT_INVALID", "OUTPUT_BACKPRESSURE"),
        ("WAW_REDRAW_UNAVAILABLE", "RUNTIME_UNAVAILABLE"),
        ("WAW_REDRAW_IDENTITY_UNCONFIRMED", "RECONCILIATION_REQUIRED"),
    ],
)
def test_fresh_redraw_maps_only_closed_redraw_error_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    expected: str,
) -> None:
    def fail(_self: WAWSupervisor, _lease: RuntimeAttachmentLease) -> Any:
        raise RuntimeOperationError(code, "synthetic redraw failure", category="conflict")

    monkeypatch.setattr(WAWSupervisor, "publish_fresh_redraw", fail)
    with pytest.raises(EncryptedStreamError) as raised:
        Harness(tmp_path)
    assert raised.value.code == expected


def test_no_api_context_or_payload_repr(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    assert "ses_1" not in repr(h.session)
    assert h.capability not in repr(h.registry)
    assert not hasattr(h.session._lease, "context")
    assert h.supervisor.state is SupervisorState.RUNNING


def test_live_precommit_output_must_fit_selected_budget(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"a" * 32768)
    h.keys()
    h.supervisor.append_encrypted_output(h.supervisor.output_source(), b"b" * 32768)
    with pytest.raises(EncryptedStreamError, match="OUTPUT_BACKPRESSURE"):
        h.ready()
    assert h.session.closed
    assert h.supervisor.snapshot().attachment_id is None
    assert not h.transport.stopped


def test_terminal_ack_replays_body_once_with_next_outer_hop(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.send(F.INPUT, h.browser.encrypt_input(b"once"))
    terminal = decode_wire_frame(h.session.flush_input()[0], RA)
    replay = decode_wire_frame(h.session.replay_input_result(6, 1), RA)
    assert replay.json_payload == terminal.json_payload
    assert replay.hop_sequence == terminal.hop_sequence + 1
    assert h.transport.writes == [b"once"]
    with pytest.raises(EncryptedStreamError):
        h.session.replay_input_result(6, 1)
    h.session.close()
    with pytest.raises(EncryptedStreamError):
        h.session.replay_input_result(6, 1)


def test_shared_admission_deadline_closes_idle_handshake(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.now = 5
    with pytest.raises(EncryptedStreamError, match="ADMISSION_TIMEOUT"):
        h.session.tick()
    assert h.session.cleanup_proof is not None
    assert h.session.cleanup_proof.confirmed


def test_old_close_cannot_clear_new_attachment_output(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.session.close()
    h.prepare(claims=replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2))
    h.supervisor.append_encrypted_output(h.supervisor.output_source(), b"new data")
    h.session.close(clear_reason="crypto_failure")
    assert h.supervisor.snapshot().buffered_bytes == len(b"new data")
    assert h.registry.count == 1


def test_ring_clear_preserves_head_and_known_loss(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"abcdef")
    head = h.supervisor.snapshot().next_cursor
    h.supervisor.clear_runtime_output("crypto_failure")
    assert h.supervisor.snapshot().next_cursor == head
    h.supervisor.append_encrypted_output(h.supervisor.output_source(), b"new")
    replay = h.supervisor.replay_output(1, generation=1, runtime_epoch="1")
    assert (replay.gap_start, replay.gap_end) == (2, 6)
    assert h.supervisor.snapshot().next_cursor == 10


def test_bound_control_service_random_prepare_and_real_detach(tmp_path: Path) -> None:
    from agentbox_runtime.waw_encrypted_stream import WAWEncryptedAttachmentService

    h = Harness(tmp_path)
    h.session.close()
    claims = replace(h.claims, attachment_id="att_" + "8" * 32, lease_number=2)
    service = WAWEncryptedAttachmentService(
        h.registry,
        peer=lambda: h.peer,
        supervisor=lambda _: h.supervisor,
        current=lambda _: h.valid,
    )
    service.bind_authority({"api_authority_epoch": "1", "authority_nonce": "a" * 32})
    request = {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "action": "workspace.attach.prepare",
        **admission_fields(claims),
        "runtime_epoch": "1",
        "resume_cursor": None,
        "previous_runtime_epoch": None,
    }
    first = service.prepare(request)
    assert service.prepare(request) == first
    detach = {
        key: value
        for key, value in request.items()
        if key not in {"resume_cursor", "previous_runtime_epoch"}
    }
    detach["action"] = "workspace.attach.detach"
    detach["request_id"] = "wreq_" + "2" * 32
    h.transport.detach_confirmed = False
    assert service.detach(detach)["cleanup_state"] == "ATTACH_PTY_CLOSE_UNCERTAIN"
    assert h.registry.count == 1
    h.transport.detach_confirmed = True
    confirmed = service.detach(detach)
    assert confirmed["cleanup_state"] == "ATTACH_PTY_CLOSED"
    assert service.detach(detach) == confirmed
    with pytest.raises(EncryptedStreamError):
        service.detach({**detach, "request_id": "wreq_" + "3" * 32})
    assert h.registry.count == 0


def test_authority_bind_does_not_accept_different_peer_or_nonce(tmp_path: Path) -> None:
    from agentbox_runtime.waw_encrypted_stream import WAWEncryptedAttachmentService

    h = Harness(tmp_path)
    service = WAWEncryptedAttachmentService(
        h.registry,
        peer=lambda: h.peer,
        supervisor=lambda _: h.supervisor,
        current=lambda _: h.valid,
    )
    bind = {"api_authority_epoch": "1", "authority_nonce": "a" * 32}
    service.bind_authority(bind)
    service.bind_authority(bind)
    with pytest.raises(EncryptedStreamError):
        service.bind_authority({**bind, "authority_nonce": "b" * 32})
    h.peer = RuntimePeer(object(), "1", lambda: True)
    with pytest.raises(EncryptedStreamError):
        service.bind_authority(bind)


def test_authority_revoke_burns_prepared_capability_and_allows_new_peer(
    tmp_path: Path,
) -> None:
    from agentbox_runtime.waw_encrypted_stream import WAWEncryptedAttachmentService

    h = Harness(tmp_path)
    assert h.session.close().confirmed
    old_identity = object()
    old_peer = RuntimePeer(old_identity, "1", lambda: True)

    def legacy_peer_provider() -> RuntimePeer:
        raise AssertionError("explicit authority must be the only peer truth")

    service = WAWEncryptedAttachmentService(
        h.registry,
        peer=legacy_peer_provider,
        supervisor=lambda _: h.supervisor,
        current=lambda _: h.valid,
    )
    service.bind_authority(
        {"api_authority_epoch": "1", "authority_nonce": "a" * 32},
        old_peer,
    )
    old_claims = replace(h.claims, attachment_id="att_" + "8" * 32, lease_number=2)
    old_request = {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "action": "workspace.attach.prepare",
        **admission_fields(old_claims),
        "runtime_epoch": "1",
        "resume_cursor": None,
        "previous_runtime_epoch": None,
    }
    old_capability = service.prepare(old_request, old_peer)["capability"]

    class EqualIdentity:
        def __eq__(self, other: object) -> bool:
            return other is old_identity

    assert service.revoke_authority(EqualIdentity())
    assert h.registry.count == 1
    assert service.revoke_authority(old_identity)
    assert h.registry.count == 0
    assert all(entry[1] is not old_identity for entry in h.registry._completed.values())
    old_hello = encode_wire_frame(
        F.RUNTIME_HELLO,
        AR,
        {
            "protocol_version": 1,
            **admission_fields(old_claims),
            "runtime_epoch": "1",
            "capability": old_capability,
            "resume_cursor": None,
            "previous_runtime_epoch": None,
        },
        1,
    )
    with pytest.raises(EncryptedStreamError, match="ATTACHMENT_STALE"):
        h.registry.open(RuntimePeer(old_identity, "1", lambda: True), old_hello)

    new_identity = object()
    new_peer = RuntimePeer(new_identity, "2", lambda: True)
    service.bind_authority(
        {"api_authority_epoch": "2", "authority_nonce": "b" * 32},
        new_peer,
    )
    new_claims = replace(
        old_claims,
        attachment_id="att_" + "9" * 32,
        lease_number=3,
        api_authority_epoch=2,
    )
    new_request = {
        **old_request,
        "request_id": "wreq_" + "2" * 32,
        **admission_fields(new_claims),
    }
    assert service.prepare(new_request, new_peer)["status"] == "PREPARED"
    with pytest.raises(EncryptedStreamError, match="RUNTIME_PEER_FORBIDDEN"):
        service.prepare(
            {
                **new_request,
                "request_id": "wreq_" + "3" * 32,
                "attachment_id": "att_" + "a" * 32,
                "lease_number": "4",
            },
            old_peer,
        )

    detach = {
        key: value
        for key, value in new_request.items()
        if key not in {"resume_cursor", "previous_runtime_epoch"}
    }
    detach["action"] = "workspace.attach.detach"
    detach["request_id"] = "wreq_" + "4" * 32
    assert service.detach(detach, new_peer)["cleanup_state"] == "ATTACH_PTY_CLOSED"
    assert service._detach_requests
    assert service.revoke_authority(new_identity)
    assert not service._detach_requests
    assert all(entry[1] is not new_identity for entry in h.registry._completed.values())


def test_authority_revoke_fences_active_session_before_cleanup(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"sensitive output")
    h.admit()
    h.send(F.INPUT, h.browser.encrypt_input(b"queued input"))

    class Publication:
        def __init__(self) -> None:
            self.fences = 0

        def fence(self) -> bool:
            self.fences += 1
            return True

        def send(self, data: memoryview) -> int:
            raise AssertionError("revoked publication must not send")

    publication = Publication()
    h.session._publication = publication
    h.session._publication_fenced = False

    assert h.registry.revoke_authority(h.peer.identity)
    assert publication.fences == 1
    assert h.session.closed and not h.session._input and not h.session._baseline_records
    assert h.session.cleanup_proof is not None and h.session.cleanup_proof.confirmed
    assert h.registry.count == 0
    with pytest.raises(EncryptedStreamError, match="ATTACHMENT_STALE"):
        h.send(
            F.RESIZE,
            {
                "protocol_version": 1,
                "attachment_id": h.claims.attachment_id,
                "lease_number": str(h.claims.lease_number),
                "columns": 80,
                "rows": 24,
            },
        )


def test_authority_revoke_retains_uncertain_cleanup_and_burns_capability(
    tmp_path: Path,
) -> None:
    h = Harness(tmp_path)
    assert h.session.close().confirmed
    claims = replace(h.claims, attachment_id="att_" + "8" * 32, lease_number=2)
    capability = h.prepare(claims=claims)
    h.transport.detach_confirmed = False

    assert not h.registry.revoke_authority(h.peer.identity)
    assert h.registry.count == 1
    raw_hello = encode_wire_frame(
        F.RUNTIME_HELLO,
        AR,
        {
            "protocol_version": 1,
            **admission_fields(claims),
            "runtime_epoch": "1",
            "capability": capability,
            "resume_cursor": None,
            "previous_runtime_epoch": None,
        },
        1,
    )
    with pytest.raises(EncryptedStreamError, match="ATTACHMENT_STALE"):
        h.registry.open(h.peer, raw_hello)
    with pytest.raises(EncryptedStreamError, match="WORKSPACE_WRITER_BUSY"):
        h.prepare(claims=replace(claims, attachment_id="att_" + "9" * 32, lease_number=3))

    h.transport.detach_confirmed = True
    assert h.registry.revoke_authority(h.peer.identity)
    assert h.registry.count == 0


def test_authority_revoke_requires_publication_and_pty_confirmation(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()

    class Publication:
        def __init__(self) -> None:
            self.confirmed = False
            self.fences = 0

        def fence(self) -> bool:
            self.fences += 1
            return self.confirmed

        def send(self, data: memoryview) -> int:
            raise AssertionError("revoked publication must not send")

    publication = Publication()
    h.session._publication = publication
    h.session._publication_fenced = False

    assert not h.registry.revoke_authority(h.peer.identity)
    assert publication.fences == 1
    assert h.registry.count == 1
    assert h.supervisor.snapshot().attachment_id is None

    publication.confirmed = True
    assert h.registry.revoke_authority(h.peer.identity)
    assert publication.fences == 2
    assert h.registry.count == 0


def test_postdecrypt_authority_rejection_has_ack_and_no_write(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    crypto: Any = h.session._crypto
    original = crypto.decrypt_input

    def revoke_after_decrypt(raw: bytes) -> bytes:
        plaintext: bytes = original(raw)
        h.valid = False
        return plaintext

    crypto.decrypt_input = revoke_after_decrypt
    replies = h.send(F.INPUT, h.browser.encrypt_input(b"not written"))
    assert body(replies[0])["result"] == "rejected"
    assert body(replies[0])["reason_code"] == "ATTACHMENT_STALE"
    assert h.transport.writes == []
    assert h.session.closed


def test_ping_rate_limit_and_unsolicited_pong(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    ping = {"protocol_version": 1, "nonce": "a" * 16, "sent_at_monotonic_tick": "1"}
    assert types(h.send(F.PING, ping)) == [F.PONG]
    assert types(h.send(F.PING, ping)) == [F.PONG]
    assert types(h.send(F.PING, ping)) == [F.CLOSE]
    assert h.session.closed


def test_runtime_ping_timeout_does_not_renew_health(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    ping = body(h.session.ping())
    h.send(
        F.PONG,
        {
            "protocol_version": 1,
            "nonce": ping["nonce"],
            "echoed_sent_at_monotonic_tick": ping["sent_at_monotonic_tick"],
        },
    )
    h.session.ping()
    h.now = 5
    assert types(h.session.tick()) == [F.CLOSE]
    assert h.session.closed


def test_wrong_exact_cleanup_proof_never_releases_slot(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.transport.close_attachment = lambda lease: RuntimeAttachmentCleanupEvidence(
        replace(lease, claims=replace(lease.claims, attachment_id="att_" + "f" * 32)), True, 0
    )
    assert not h.session.close().confirmed
    assert h.registry.count == 1


def test_legacy_detach_boolean_is_not_encrypted_cleanup_capability(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.session.close()
    del h.transport.close_attachment
    with pytest.raises(RuntimeOperationError, match="cleanup port"):
        h.prepare(claims=replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2))


def test_close_during_inflight_write_never_reuses_writer_early(tmp_path: Path) -> None:
    import threading

    h = Harness(tmp_path)
    h.admit()
    h.send(F.INPUT, h.browser.encrypt_input(b"bounded"))
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    failures: list[BaseException] = []

    def write(data: bytes) -> None:
        entered.set()
        assert release.wait(2)
        h.transport.writes.append(data)

    h.transport.write = write

    def flush() -> None:
        try:
            h.session.flush_input()
        except EncryptedStreamError as exc:
            failures.append(exc)

    worker = threading.Thread(target=flush)
    worker.start()
    assert entered.wait(1)

    def cleanup() -> None:
        h.session.close()
        closed.set()

    closer = threading.Thread(target=cleanup)
    closer.start()
    assert not closed.wait(0.02)
    assert h.session.closed
    release.set()
    worker.join(2)
    closer.join(2)
    assert not worker.is_alive() and not closer.is_alive()
    assert h.registry.count == 0
    assert h.session.cleanup_proof is not None and h.session.cleanup_proof.confirmed
    assert failures  # late terminal ACK cannot be published after close fence
    assert not h.transport.stopped


@pytest.mark.parametrize("field,value", [("lease_number", 9), ("binding_digest", "b" * 64)])
def test_cleanup_evidence_cannot_substitute_same_id_claims(
    tmp_path: Path, field: str, value: Any
) -> None:
    h = Harness(tmp_path)
    h.admit()
    altered = replace(h.session._lease, claims=replace(h.claims, **{field: value}))
    h.transport.close_attachment = lambda _: RuntimeAttachmentCleanupEvidence(altered, True, 0)
    assert not h.session.close().confirmed
    assert h.registry.count == 1


def test_above_head_and_cross_epoch_replay_are_rejected(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"abcdef")
    h.session.close()
    claims = replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2)
    with pytest.raises(ValueError):
        h.prepare(claims=claims, resume_cursor="1", previous_runtime_epoch="2")
    cap = h.prepare(claims=claims, resume_cursor="7", previous_runtime_epoch="1")
    hello = encode_wire_frame(
        F.RUNTIME_HELLO,
        AR,
        {
            "protocol_version": 1,
            **admission_fields(claims),
            "runtime_epoch": "1",
            "capability": cap,
            "resume_cursor": "7",
            "previous_runtime_epoch": "1",
        },
        1,
    )
    with pytest.raises(EncryptedStreamError):
        h.registry.open(h.peer, hello)
    assert h.registry.count == 0


def test_output_cursor_above_binary64_exact_range(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.session.output()
    # Explicit synthetic ring position; no persisted/host cursor is invented.
    ring: Any = h.supervisor._ring
    ring._next_cursor = 2**53 + 7
    h.supervisor.append_encrypted_output(h.supervisor.output_source(), b"abc")
    frames = h.session.output()
    assert types(frames) == [F.GAP, F.OUTPUT]
    envelope = decode_awce(decode_wire_frame(frames[-1], RA).payload)
    assert envelope.stream_cursor == 2**53 + 9
    assert (
        h.browser.decrypt_output(
            decode_wire_frame(frames[-1], RA).payload, expected_cursor=2**53 + 9
        )
        == b"abc"
    )


def test_unpublished_ready_allocation_does_not_skip_failure_hop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentbox_runtime.waw_encrypted_server import _Publication
    from agentbox_runtime.waw_encrypted_stream import failure_profile

    h = Harness(tmp_path)
    h.keys()
    # HELLO_ACK / KEY_ATTEST / KEY_CONFIRM_ACK were delivered by the test port.
    published = _Publication(next_hop=4, hello_published=True)
    original = h.session._check

    def fail_after_constructing_ready(*, active: bool = False) -> float:
        if h.session._tx == 5:
            raise EncryptedStreamError("ATTACHMENT_STALE")
        return original(active=active)

    monkeypatch.setattr(h.session, "_check", fail_after_constructing_ready)
    with pytest.raises(EncryptedStreamError) as failure:
        h.ready()
    assert h.session._tx == 5  # No rollback of the allocation/crypto state.
    replies = failure_profile(failure.value, next_hop=published.next_hop, trusted_context=True)
    assert [decode_wire_frame(raw, RA).hop_sequence for raw in replies] == [4, 5]
    assert types(replies) == [F.ERROR, F.CLOSE]
    for raw in replies:
        published.begin(raw)
        published.complete(raw)
    assert published.next_hop == 6 and published.terminal
    assert h.session.closed


def test_partly_constructed_output_batch_has_no_publication_side_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentbox_runtime.waw_encrypted_stream import failure_profile

    h = Harness(tmp_path, redraw=b"data", truncated=True)
    h.admit()
    crypto: Any = h.session._crypto

    def fail_encrypt(*_: object, **__: object) -> bytes:
        raise RuntimeError("synthetic-private-key-and-output-canary")

    monkeypatch.setattr(crypto, "encrypt_output", fail_encrypt)
    with pytest.raises(RuntimeError) as failure:
        h.session.output()
    assert h.session._tx == 7  # GAP was constructed but no batch was returned.
    replies = failure_profile(failure.value, next_hop=6, trusted_context=True)
    assert [decode_wire_frame(raw, RA).hop_sequence for raw in replies] == [6, 7]
    assert all(b"synthetic-private" not in raw for raw in replies)
    assert body(replies[0])["code"] == "INTERNAL_BOUNDED"
    assert body(replies[1])["code"] == "RUNTIME_UNAVAILABLE"


def test_cleanup_exception_retains_fence_and_clears_transient_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = Harness(tmp_path, redraw=b"queued output")
    h.admit()
    h.send(F.INPUT, h.browser.encrypt_input(b"queued input"))

    def failure(*_: object, **__: object) -> None:
        raise RuntimeError("synthetic-cleanup-exception")

    monkeypatch.setattr(h.registry, "_cleanup", failure)
    proof = h.session.close()
    assert not proof.confirmed and h.registry.count == 1
    assert h.session.closed and not h.session._input and not h.session._baseline_records
    assert h.session._crypto is not None and h.session._crypto.closed
    assert h.transport.writes == []


def test_ring_cleanup_error_still_closes_pty_but_requires_complete_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = Harness(tmp_path, redraw=b"retained until cleanup")
    h.admit()
    original = h.supervisor.clear_runtime_output

    def failure(_: str) -> None:
        raise RuntimeError("synthetic-ring-cleanup-error")

    monkeypatch.setattr(h.supervisor, "clear_runtime_output", failure)
    assert not h.session.close(clear_reason="crypto_failure").confirmed
    assert h.registry.count == 1 and h.supervisor.snapshot().attachment_id is None
    monkeypatch.setattr(h.supervisor, "clear_runtime_output", original)
    assert h.session.close(clear_reason="crypto_failure").confirmed
    assert h.registry.count == 0 and h.supervisor.snapshot().buffered_bytes == 0


@pytest.mark.parametrize("failure_hop", [1, 2, 3, 4, 5, 6])
def test_actual_runtime_failure_is_accepted_by_full_four_leg_trace(
    tmp_path: Path,
    failure_hop: int,
) -> None:
    from agentbox_protocol.waw_wire import WireSession, forward_wire_frame
    from agentbox_runtime.waw_encrypted_stream import failure_profile

    h = Harness(tmp_path)
    browser_to_api, api_to_browser = Leg.BROWSER_TO_API, Leg.API_TO_BROWSER
    connection = object()
    trace = WireSession(h.admission, "1", stream_id=connection, started_at=0)

    def observe(leg: Leg, raw: bytes) -> bytes:
        trace.accept(leg, raw, stream_id=connection, now=1)
        return raw

    init = h.browser.start()
    if failure_hop == 2:
        init["noise_message_1"] = "A" * 43
    observe(
        browser_to_api,
        encode_wire_frame(
            F.WS_HELLO,
            browser_to_api,
            {
                **h.bound,
                "ticket": "wat_" + "a" * 32,
                "resume_cursor": None,
                "previous_runtime_epoch": None,
            },
            1,
        ),
    )
    browser_init = observe(browser_to_api, encode_wire_frame(F.KEY_INIT, browser_to_api, init, 2))
    observe(AR, h.hello_raw())
    runtime_init = observe(
        AR, forward_wire_frame(decode_wire_frame(browser_init, browser_to_api), AR, 2)
    )
    error: BaseException | None = None
    try:
        if failure_hop == 1:
            # The exact bearer was already consumed by the fixture's initial
            # open. This real endpoint rejects before publishing HELLO_ACK.
            h.registry.open(h.peer, h.hello_raw())
        observe(RA, h.hello)
        attest = observe(RA, h.session.receive(runtime_init)[0])
        observe(
            api_to_browser, forward_wire_frame(decode_wire_frame(attest, RA), api_to_browser, 1)
        )
        confirm = h.browser.receive_attest(body(attest))
        if failure_hop == 3:
            value = str(confirm["ciphertext"])
            confirm["ciphertext"] = ("A" if value[0] != "A" else "B") + value[1:]
        browser_confirm = observe(
            browser_to_api, encode_wire_frame(F.KEY_CONFIRM, browser_to_api, confirm, 3)
        )
        runtime_confirm = observe(
            AR, forward_wire_frame(decode_wire_frame(browser_confirm, browser_to_api), AR, 3)
        )
        ack = observe(RA, h.session.receive(runtime_confirm)[0])
        observe(api_to_browser, forward_wire_frame(decode_wire_frame(ack, RA), api_to_browser, 2))
        h.browser.receive_ack(body(ack))
        ready = observe(AR, encode_wire_frame(F.STREAM_READY, AR, h.bound, 4))
        if failure_hop == 4:
            h.valid = False
        ready_ack = observe(RA, h.session.receive(ready)[0])
        commit = observe(
            AR,
            encode_wire_frame(
                F.ADMISSION_COMMIT,
                AR,
                {**h.bound, "admission_fence": body(ready_ack)["admission_fence"]},
                5,
            ),
        )
        if failure_hop == 5:
            h.valid = False
        observe(RA, h.session.receive(commit)[0])
        observe(
            api_to_browser,
            encode_wire_frame(
                F.ADMITTED,
                api_to_browser,
                {
                    **h.bound,
                    "state": "RUNNING",
                    "output_cursor": "0",
                    "lease_expires_at": "2030-02-28T12:30:59.123456Z",
                },
                3,
            ),
        )
        encrypted = h.browser.encrypt_input(b"never written")
        bad = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
        browser_input = observe(browser_to_api, encode_wire_frame(F.INPUT, browser_to_api, bad, 4))
        runtime_input = observe(
            AR, forward_wire_frame(decode_wire_frame(browser_input, browser_to_api), AR, 6)
        )
        h.session.receive(runtime_input)
    except (EncryptedStreamError, RuntimeOperationError) as failure:
        error = failure
    assert error is not None
    emitted = failure_profile(error, next_hop=failure_hop, trusted_context=failure_hop > 1)
    assert len(emitted) == (1 if failure_hop <= 2 else 2)
    for raw in emitted:
        observe(RA, raw)
        frame = decode_wire_frame(raw, RA)
        assert frame.json_payload is not None
        translated = dict(frame.json_payload)
        if frame.frame_type == F.ERROR:
            translated["request_id"] = "wreq_" + "f" * 32
        observe(
            api_to_browser,
            encode_wire_frame(
                frame.frame_type,
                api_to_browser,
                translated,
                trace.expected_sequence(api_to_browser),
            ),
        )
    assert trace.failed
    assert not trace.admitted
    assert not h.transport.writes
    h.session.close()


@pytest.mark.parametrize("operation", ["input", "flush", "output"])
@pytest.mark.parametrize("expiry", ["health", "ping"])
def test_every_active_data_operation_checks_health_before_effects(
    tmp_path: Path,
    operation: str,
    expiry: str,
) -> None:
    h = Harness(tmp_path, redraw=b"do not publish after expiry")
    h.admit()
    if operation == "flush":
        h.send(F.INPUT, h.browser.encrypt_input(b"pending before expiry"))
    if expiry == "ping":
        h.session.ping()
    h.now = 10 if expiry == "health" else 5
    with pytest.raises(EncryptedStreamError, match="RUNTIME_UNAVAILABLE"):
        if operation == "input":
            h.send(F.INPUT, h.browser.encrypt_input(b"late input"))
        elif operation == "flush":
            h.session.flush_input()
        else:
            h.session.output()
    assert h.transport.writes == []
    assert h.session.closed
    assert h.session.cleanup_proof is not None and h.session.cleanup_proof.confirmed


def test_health_boundary_before_deadline_and_renewal(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.now = 9.999
    h.send(F.INPUT, h.browser.encrypt_input(b"in time"))
    h.session.flush_input()
    assert h.transport.writes == [b"in time"]
    h.send(
        F.HEARTBEAT,
        {
            "protocol_version": 1,
            "attachment_id": h.claims.attachment_id,
            "lease_number": "1",
            "sent_at_monotonic_tick": "1",
        },
    )
    h.now = 10
    h.send(F.INPUT, h.browser.encrypt_input(b"renewed"))
    h.session.flush_input()
    assert h.transport.writes == [b"in time", b"renewed"]


def test_needs_interaction_pauses_data_and_fresh_running_probe_resumes(tmp_path: Path) -> None:
    h = Harness(tmp_path, redraw=b"retained bounded ring")
    h.admit()
    original = h.transport.probe
    h.transport.probe = lambda: replace(original(), state=RuntimeProbeState.NEEDS_INTERACTION)
    frames = h.session.tick()
    assert types(frames) == [F.STATE]
    assert body(frames[0])["state"] == "NEEDS_INTERACTION"
    assert h.session.tick() == () and h.session.output() == ()
    rejected = h.send(F.INPUT, h.browser.encrypt_input(b"paused"))
    assert types(rejected) == [F.ACK]
    assert body(rejected[0])["reason_code"] == "WORKSPACE_NOT_RUNNING"
    assert h.transport.writes == [] and not h.session.closed
    h.transport.probe = original
    resumed = h.session.tick()
    assert types(resumed) == [F.STATE] and body(resumed[0])["state"] == "RUNNING"
    accepted = h.send(F.INPUT, h.browser.encrypt_input(b"fresh input"))
    assert body(accepted[0])["crypto_sequence"] == "2"
    h.session.flush_input()
    assert h.transport.writes == [b"fresh input"]
    assert types(h.session.output()) == [F.OUTPUT]


@pytest.mark.parametrize(
    "state",
    [
        RuntimeProbeState.LOGIN_REQUIRED,
        RuntimeProbeState.TRUST_REQUIRED,
        RuntimeProbeState.MISSING,
        RuntimeProbeState.COLLISION,
        RuntimeProbeState.UNKNOWN,
    ],
)
def test_nonexit_probe_emits_truthful_state_and_close(
    tmp_path: Path, state: RuntimeProbeState
) -> None:
    h = Harness(tmp_path, redraw=b"retain workspace history")
    h.admit()
    original = h.transport.probe
    h.transport.probe = lambda: replace(original(), state=state)
    frames = h.session.tick()
    assert types(frames) == [F.STATE, F.CLOSE]
    assert body(frames[0])["state"] == state.value
    assert body(frames[1])["workspace_state_at_close"] == state.value
    assert body(frames[1])["code"] == "ATTACHMENT_STALE"
    assert h.session.closed and not h.transport.stopped
    assert h.supervisor.snapshot().buffered_bytes == len(b"retain workspace history")


def test_accepted_input_resolves_before_paused_state_without_fake_exit(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.send(F.INPUT, h.browser.encrypt_input(b"accepted before state change"))
    original = h.transport.probe
    h.transport.probe = lambda: replace(original(), state=RuntimeProbeState.NEEDS_INTERACTION)
    frames = h.session.flush_input()
    assert types(frames) == [F.ACK, F.STATE]
    assert body(frames[0])["result"] == "write_uncertain"
    assert body(frames[1])["state"] == "NEEDS_INTERACTION"
    assert not h.transport.writes and not h.session.closed


def test_decrypted_input_on_login_state_has_no_fabricated_exit(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()
    original = h.transport.probe
    h.transport.probe = lambda: replace(original(), state=RuntimeProbeState.LOGIN_REQUIRED)
    frames = h.send(F.INPUT, h.browser.encrypt_input(b"not a login path"))
    assert types(frames) == [F.ACK, F.STATE, F.CLOSE]
    assert body(frames[0])["result"] == "rejected"
    assert body(frames[1])["state"] == "LOGIN_REQUIRED"
    assert not h.transport.writes and not h.transport.stopped


def test_partial_write_cleanup_preserves_fault_until_exact_stop_new_generation(
    tmp_path: Path,
) -> None:
    from agentbox_core.waw import managed_marker
    from agentbox_runtime.waw_pty import PtyGeometry
    from agentbox_runtime.waw_supervisor import WAWSupervisor
    from test_waw_supervisor import FakeTransport

    h = Harness(tmp_path)
    h.admit()
    old_lease = h.session._lease
    h.transport.fail_writes = True
    h.send(F.INPUT, h.browser.encrypt_input(b"uncertain old generation"))
    result = h.session.flush_input()
    assert body(result[0])["result"] == "write_uncertain"
    assert h.session.cleanup_proof is not None and h.session.cleanup_proof.confirmed
    assert h.supervisor.state is SupervisorState.INPUT_UNCERTAIN
    next_claims = replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2)
    with pytest.raises(RuntimeOperationError, match="not running"):
        h.prepare(claims=next_claims)
    assert h.supervisor.snapshot().attachment_id is None
    assert h.supervisor.state is SupervisorState.INPUT_UNCERTAIN
    assert h.registry.count == 0

    stop = h.supervisor._stop_binding
    assert h.supervisor.exact_stop(stop).state is SupervisorState.STOPPED
    next_stop = replace(stop, generation=2)
    command = replace(
        h.supervisor._command,
        managed_marker=managed_marker(
            runtime_host_installation_id=next_stop.runtime_host_installation_id,
            runtime_host_installation_revision=next_stop.runtime_host_installation_revision,
            project_id=next_stop.project_id,
            agent_type=next_stop.agent_type,
            workspace_id_value=next_stop.workspace_id,
            generation=2,
            binding_revision=next_stop.binding_revision,
            binding_digest=next_stop.binding_digest,
        ),
    )
    fresh: Any = FakeTransport()
    fresh.generation = 2
    original_start = fresh.start
    fresh.start = lambda command, geometry: replace(original_start(command, geometry), generation=2)
    fresh.close_attachment = lambda lease: RuntimeAttachmentCleanupEvidence(
        lease, fresh.detach(), 0
    )
    h.supervisor = WAWSupervisor(
        workspace_id=next_stop.workspace_id,
        generation=2,
        command=command,
        transport=fresh,
        geometry=PtyGeometry(120, 32),
        clock=lambda: h.now,
        attachment_validator=lambda _: True,
        stop_binding=next_stop,
        runtime_epoch="1",
    )
    h.supervisor.start()
    h.transport = fresh
    h.claims = replace(h.claims, generation=2, attachment_id="att_" + "8" * 32, lease_number=3)
    h.admission = admission_fields(h.claims)
    h.bound = {"protocol_version": 1, **h.admission, "runtime_epoch": "1"}
    h.capability = h.prepare()
    h.session, _ = h.registry.open(h.peer, h.hello_raw())
    h.browser = BrowserCryptoProfile(h.admission, "1", PIN, clock=lambda: h.now)
    h.rx = 2
    h.admit()
    assert old_lease.publication.invalidate()
    assert not h.session.closed  # Old exact lease cannot fence the new generation.
    h.send(F.INPUT, h.browser.encrypt_input(b"fresh generation"))
    h.session.flush_input()
    assert fresh.writes == [b"fresh generation"]


@pytest.mark.parametrize(
    "fault",
    [
        SupervisorState.INPUT_UNCERTAIN,
        SupervisorState.RECONCILIATION_REQUIRED,
        SupervisorState.BROKEN,
    ],
)
def test_exact_attachment_cleanup_does_not_reset_workspace_fault(
    tmp_path: Path,
    fault: SupervisorState,
) -> None:
    h = Harness(tmp_path)
    h.admit()
    h.supervisor._state = fault  # Explicit synthetic fault injection under no concurrent work.
    assert h.session.close().confirmed
    assert h.supervisor.state is fault
    with pytest.raises(RuntimeOperationError):
        h.prepare(claims=replace(h.claims, attachment_id="att_" + "7" * 32, lease_number=2))
    assert h.supervisor.state is fault and h.supervisor.snapshot().attachment_id is None


def test_stop_before_publication_bind_permanently_fences_later_binding() -> None:
    from agentbox_runtime.waw_supervisor import RuntimePublicationInvalidator

    invalidator = RuntimePublicationInvalidator()
    assert invalidator.invalidate()
    closed = False

    def fence() -> bool:
        nonlocal closed
        closed = True
        return True

    invalidator.bind(fence)
    assert closed and invalidator.invalidate()
    with pytest.raises(ValueError):
        invalidator.bind(fence)


def test_unconfirmed_socket_fence_prevents_exact_stop_process_effects(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.admit()

    class UnconfirmedPublication:
        def fence(self) -> bool:
            return False

        def send(self, data: memoryview) -> int:
            raise AssertionError("No socket write may follow the fence")

    h.session._publication = UnconfirmedPublication()
    h.session._publication_fenced = False
    with pytest.raises(RuntimeOperationError, match="Publication shutdown"):
        h.supervisor.exact_stop(h.supervisor._stop_binding)
    assert h.session.closed and not h.transport.stopped
    assert h.supervisor.state is SupervisorState.RECONCILIATION_REQUIRED
