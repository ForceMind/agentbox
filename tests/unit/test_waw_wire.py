"""Public synthetic metadata only; these tests are not host/Noise qualification."""

from __future__ import annotations

import json
import struct
import time
from typing import Any

import pytest
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.awce import encode_awce_header
from agentbox_protocol.waw_crypto_context import derive_context
from agentbox_protocol.waw_wire import (
    ADMISSION_TIMEOUT_NS,
    INPUT_LIMIT,
    OUTPUT_LIMIT,
    Leg,
    WireError,
    WireSession,
    decode_wire_frame,
    encode_wire_frame,
    forward_wire_frame,
    validate_payload,
)

BA, AB, AR, RA = tuple(Leg)
A = {
    "attachment_id": "att_" + "1" * 32,
    "workspace_id": "aws_" + "2" * 32,
    "project_id": "prj_" + "3" * 32,
    "agent_type": "codex",
    "runtime_host_installation_id": "wri_" + "4" * 32,
    "runtime_host_installation_revision": "18446744073709551615",
    "auth_epoch": "2",
    "api_authority_epoch": "3",
    "lease_number": "4",
    "generation": "5",
    "binding_revision": "6",
    "mode": "writer",
    "binding_digest": "5" * 64,
}
EPOCH = "18446744073709551615"
C = derive_context(A, EPOCH)
LEASE = {key: A[key] for key in ("attachment_id", "lease_number")}
PROFILES = {
    BA: [1, 3, 5, 9, 11, 12, 13, 15],
    AB: [4, 6, 8, 10, 14, 16, 17, 18, 19, 20, 21, 26, 27],
    AR: [2, 3, 5, 9, 11, 12, 13, 14, 15, 20, 22, 24],
    RA: [4, 6, 7, 10, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 26, 27],
}


def opaque(kind: F, size: int = 1, sequence: int = 1, cursor: int = 1) -> bytes:
    return encode_awce_header(
        crypto_envelope_version=1,
        direction_id=1 if kind == F.INPUT else 2,
        flags=0,
        crypto_sequence=sequence,
        stream_cursor=0 if kind == F.INPUT else cursor,
        context_id=bytes.fromhex("6" * 32),
        ciphertext_length=size + 16,
    ) + b"x" * (size + 16)


def payload(kind: F, leg: Leg) -> dict[str, Any] | bytes:
    base: dict[str, Any] = {"protocol_version": 1}
    admission = A | {"runtime_epoch": EPOCH}
    if kind in (F.WS_HELLO, F.RUNTIME_HELLO):
        return (
            base
            | admission
            | {"resume_cursor": None, "previous_runtime_epoch": None}
            | ({"ticket": "wat_" + "a" * 32} if kind == F.WS_HELLO else {"capability": "b" * 64})
        )
    if kind in (F.KEY_INIT, F.KEY_ATTEST):
        return (
            base
            | admission
            | {"noise_protocol": "Noise_NX_25519_AESGCM_SHA256", "crypto_envelope_version": 1}
            | (
                {"browser_ephemeral_public_key": "A" * 43, "noise_message_1": "A" * 43}
                if kind == F.KEY_INIT
                else {
                    "runtime_attestation_x25519_fingerprint": "7" * 64,
                    "runtime_ephemeral_public_key": "A" * 43,
                    "noise_message_2": "A" * 171,
                }
            )
        )
    if kind in (F.KEY_CONFIRM, F.KEY_CONFIRM_ACK):
        return (
            base
            | C
            | {"noise_protocol": "Noise_NX_25519_AESGCM_SHA256", "ciphertext": "A" * 64}
            | (
                {"status": "verified", "transcript_context_hash": "6" * 64}
                if kind == F.KEY_CONFIRM_ACK
                else {}
            )
        )
    if kind in (F.HELLO_ACK, F.ADMITTED, F.STREAM_READY_ACK):
        return (
            base
            | admission
            | {"state": "RUNNING", "output_cursor": "0"}
            | (
                {"input_limit": INPUT_LIMIT, "output_limit": OUTPUT_LIMIT}
                if kind == F.HELLO_ACK
                else (
                    {"lease_expires_at": "2030-02-28T12:30:59.123456Z"}
                    if kind == F.ADMITTED
                    else {"admission_fence": "8" * 64}
                )
            )
        )
    if kind in (F.STREAM_READY, F.ADMISSION_COMMIT, F.ADMISSION_COMMIT_ACK):
        return (
            base
            | admission
            | (
                {"admission_fence": "8" * 64}
                if kind == F.ADMISSION_COMMIT
                else (
                    {"result": "committed", "reason_code": None}
                    if kind == F.ADMISSION_COMMIT_ACK
                    else {}
                )
            )
        )
    if kind in (F.INPUT, F.OUTPUT):
        return opaque(kind)
    if kind == F.RESIZE:
        return base | LEASE | {"columns": 80, "rows": 24}
    if kind == F.RESIZE_ACK:
        return (
            base
            | LEASE
            | {
                "acknowledged_hop_sequence": "6",
                "requested_columns": 80,
                "requested_rows": 24,
                "effective_columns": 80,
                "effective_rows": 24,
                "result": "applied",
                "reason_code": None,
            }
        )
    if kind == F.HEARTBEAT:
        return base | LEASE | {"sent_at_monotonic_tick": "18446744073709551615"}
    if kind in (F.PING, F.PONG):
        return base | {
            "nonce": "9" * 16,
            "sent_at_monotonic_tick" if kind == F.PING else "echoed_sent_at_monotonic_tick": "1",
        }
    if kind == F.DETACH:
        return base | LEASE
    if kind == F.DETACH_ACK:
        return (
            base
            | (admission if leg == RA else LEASE)
            | {
                "acknowledged_hop_sequence": "6",
                "result": "detached",
                "cleanup_state": "ATTACH_PTY_CLOSED",
                "reason_code": None,
            }
        )
    if kind == F.EXIT:
        return base | {"state": "EXITED", "exit_code": -128}
    if kind == F.GAP:
        return base | {
            "from_cursor": "1",
            "to_cursor": "18446744073709551615",
            "reason": "ring_overflow",
        }
    if kind == F.ACK:
        return (
            base
            | {
                "runtime_input_hop_sequence": "6",
                "crypto_sequence": "1",
                "result": "accepted",
                "reason_code": None,
            }
            | ({"browser_input_hop_sequence": "4"} if leg == AB else {})
        )
    if kind == F.ERROR:
        return base | {
            "code": "PROTOCOL_INVALID",
            "retryable": False,
            "request_id": "wreq_" + "a" * 32,
        }
    if kind == F.CLOSE:
        return base | {"code": "ATTACHMENT_STALE", "workspace_state_at_close": "RUNNING"}
    if kind == F.STATE:
        return (
            base
            | {key: A[key] for key in ("workspace_id", "project_id", "agent_type", "generation")}
            | {"state": "RUNNING", "reason_code": None}
            | ({"runtime_epoch": EPOCH} if leg == RA else {})
        )
    raise AssertionError(kind)


def record(kind: F, leg: Leg) -> dict[str, Any]:
    result = payload(kind, leg)
    assert isinstance(result, dict)
    return result


def raw_json(kind: F, text: str | bytes, seq: int = 1) -> bytes:
    data = text.encode() if isinstance(text, str) else text
    return struct.pack("!4sBBHIQI", b"ABWS", 1, kind, 0, len(data), seq, 0) + data


def encoded(kind: F, leg: Leg, seq: int) -> bytes:
    return encode_wire_frame(kind, leg, payload(kind, leg), seq)


@pytest.mark.parametrize("leg", list(Leg))
@pytest.mark.parametrize("kind", list(F))
def test_every_type_on_every_direction(kind: F, leg: Leg) -> None:
    if kind.value not in PROFILES[leg]:
        with pytest.raises(WireError, match="^PROTOCOL_INVALID$"):
            validate_payload(kind, leg, {})
        return
    frame = decode_wire_frame(encoded(kind, leg, 1), leg, admission=A, runtime_epoch=EPOCH)
    assert frame.frame_type == kind and frame.hop_sequence == 1
    assert frame.json_payload == (None if kind in (F.INPUT, F.OUTPUT) else payload(kind, leg))
    assert "wat_" not in repr(frame) and "capability" not in repr(frame)


@pytest.mark.parametrize(
    "leg,kind",
    [(leg, F(kind)) for leg, kinds in PROFILES.items() for kind in kinds if kind not in (9, 10)],
)
def test_all_profiles_are_exact_flat_records(leg: Leg, kind: F) -> None:
    data = record(kind, leg)
    for key in data:
        missing = {k: v for k, v in data.items() if k != key}
        with pytest.raises(WireError):
            validate_payload(kind, leg, missing)
        with pytest.raises(WireError):
            validate_payload(kind, leg, data | {key: []})
    for forbidden in ("command", "context", "ticket_extra", "input_sequence"):
        with pytest.raises(WireError):
            validate_payload(kind, leg, data | {forbidden: "forbidden"})


@pytest.mark.parametrize(
    "value",
    [0, 1, True, 1.0, "", "0", "01", "+1", "1 ", " 1", "-1", "1e0", "18446744073709551616", "１"],
)
def test_canonical_positive_uint64(value: object) -> None:
    with pytest.raises(WireError):
        validate_payload(F.DETACH, BA, record(F.DETACH, BA) | {"lease_number": value})


@pytest.mark.parametrize("key", list(A))
def test_every_admission_field_is_bound(key: str) -> None:
    data = record(F.KEY_INIT, BA)
    alternatives = {"agent_type": "claude", "binding_digest": "e" * 64, "mode": "viewer"}
    data[key] = alternatives.get(key, A[key][:-1] + ("9" if A[key][-1] != "9" else "8"))
    with pytest.raises(WireError):
        validate_payload(F.KEY_INIT, BA, data, admission=A)


@pytest.mark.parametrize(
    "kind,leg,field,length",
    [
        (F.KEY_INIT, BA, "noise_message_1", 43),
        (F.KEY_INIT, BA, "browser_ephemeral_public_key", 43),
        (F.KEY_ATTEST, RA, "noise_message_2", 171),
        (F.KEY_ATTEST, RA, "runtime_ephemeral_public_key", 43),
        (F.KEY_CONFIRM, BA, "ciphertext", 64),
        (F.KEY_CONFIRM_ACK, RA, "ciphertext", 64),
    ],
)
def test_opaque_key_metadata_encoding(kind: F, leg: Leg, field: str, length: int) -> None:
    for value in (
        "A" * (length - 1),
        "A" * (length + 1),
        "A" * (length - 1) + "=",
        "A" * (length - 1) + "+",
        "A" * (length - 1) + " ",
        "A" * (length - 1) + "é",
    ):
        with pytest.raises(WireError):
            validate_payload(kind, leg, record(kind, leg) | {field: value})
    if length in (43, 171):
        with pytest.raises(WireError):
            validate_payload(kind, leg, record(kind, leg) | {field: "A" * (length - 1) + "B"})
    # The API metadata codec does not parse NX or compare duplicate e bytes.
    if kind == F.KEY_INIT:
        assert validate_payload(kind, leg, record(kind, leg) | {field: "B" * 42 + "A"})


@pytest.mark.parametrize(
    "text",
    [
        b"\xff",
        b"\xef\xbb\xbf{}",
        b'{"protocol_version":1,"protocol_version":1}',
        b'{"protocol_version":1,"x":{"same":1,"same":2}}',
        b'{"protocol_version":1,"x":NaN}',
        b'{"protocol_version":1,"x":Infinity}',
        b'{"protocol_version":1,"x":1e999}',
        b'{"protocol_version":1,"x":"\\ud800"}',
        b'{"protocol_version":1,"\\udfff":1}',
        b'{"protocol_version":1}true',
        b'{"protocol_version":1}\x00',
        b"[" * 17 + b"]" * 17,
        b"{" + b",".join(b'"k%d":0' % i for i in range(65)) + b"}",
        b" " * 4097,
    ],
)
def test_strict_json_boundaries(text: bytes) -> None:
    with pytest.raises(WireError):
        decode_wire_frame(raw_json(F.ERROR, text), AB, trusted_context=False)


@pytest.mark.parametrize("key", ["protocol_version", "crypto_envelope_version"])
@pytest.mark.parametrize("token", ["true", '"1"', "1.0", "1e0"])
def test_version_raw_literal(key: str, token: str) -> None:
    text = json.dumps(record(F.KEY_INIT, BA), separators=(",", ":")).replace(
        f'"{key}":1', f'"{key}":{token}'
    )
    with pytest.raises(WireError):
        decode_wire_frame(raw_json(F.KEY_INIT, text), BA)


def test_numbers_are_exact_and_key_relay_preserves_bytes() -> None:
    text = json.dumps(record(F.RESIZE, BA)).replace('"columns": 80', '"columns": 8.0e1')
    assert decode_wire_frame(raw_json(F.RESIZE, text), BA).json_payload == record(F.RESIZE, BA)
    for token in (
        "8.00000000000000000000000000001e1",
        "80.0000000000000001",
        "240.00000000000000000001",
        "1e-999",
    ):
        with pytest.raises(WireError):
            decode_wire_frame(raw_json(F.RESIZE, text.replace("8.0e1", token)), BA)
    text = " \n" + json.dumps(record(F.KEY_INIT, BA), indent=1) + "\t"
    original = decode_wire_frame(raw_json(F.KEY_INIT, text, 2), BA)
    forwarded = forward_wire_frame(original, AR, 7)
    assert forwarded[24:] == original.payload == text.encode()
    assert forwarded[:12] == original.wire_bytes[:12]
    assert forwarded[20:] == original.wire_bytes[20:]
    data = original.json_payload
    assert data is not None
    data["noise_message_1"] = "corruption"
    assert original.json_payload != data
    assert "noise_message_1" not in repr(original)


@pytest.mark.parametrize(
    "kind,leg,limit",
    [
        (F.INPUT, BA, INPUT_LIMIT),
        (F.INPUT, AR, INPUT_LIMIT),
        (F.OUTPUT, RA, OUTPUT_LIMIT),
        (F.OUTPUT, AB, OUTPUT_LIMIT),
    ],
)
def test_active_directional_size_and_envelope_boundaries(kind: F, leg: Leg, limit: int) -> None:
    for size in (1, limit):
        assert len(encode_wire_frame(kind, leg, opaque(kind, size), 1)) == 24 + 44 + size + 16
    with pytest.raises(WireError):
        validate_payload(kind, leg, opaque(kind, limit + 1))
    wrong = F.OUTPUT if kind == F.INPUT else F.INPUT
    with pytest.raises(WireError):
        validate_payload(kind, leg, opaque(wrong))
    for offset in (0, 4, 5, 6, 7, 24):
        bad = bytearray(opaque(kind))
        bad[offset] ^= 255
        with pytest.raises(WireError):
            validate_payload(kind, leg, bytes(bad))
    for offset in (8, 16):
        bad = bytearray(opaque(kind))
        bad[offset : offset + 8] = (2**64 - 1).to_bytes(8, "big")
        with pytest.raises(WireError):
            validate_payload(kind, leg, bytes(bad))


def test_conditional_schemas_and_zero_cursor_rules() -> None:
    positive: list[tuple[F, Leg, dict[str, Any]]] = [
        (
            F.RESIZE_ACK,
            RA,
            {
                "result": "rejected",
                "reason_code": "RESIZE_FAILED",
                "effective_columns": None,
                "effective_rows": None,
            },
        ),
        (
            F.DETACH_ACK,
            RA,
            {
                "result": "rejected",
                "cleanup_state": "ATTACH_PTY_CLOSE_UNCERTAIN",
                "reason_code": "DETACH_FAILED",
            },
        ),
        (F.DETACH_ACK, AB, {"result": "already_detached"}),
        (
            F.ADMISSION_COMMIT_ACK,
            RA,
            {"result": "rejected", "reason_code": "RECONCILIATION_REQUIRED"},
        ),
        (F.ACK, RA, {"result": "written_to_pty"}),
        (F.ACK, AB, {"result": "write_uncertain", "reason_code": "INPUT_WRITE_UNCERTAIN"}),
        (F.ACK, RA, {"result": "rejected", "reason_code": "INPUT_RATE_LIMITED"}),
        (F.GAP, AB, {"reason": "baseline_redraw", "from_cursor": "0", "to_cursor": "0"}),
    ]
    for kind, leg, overrides in positive:
        assert validate_payload(kind, leg, record(kind, leg) | overrides)
    negative: list[tuple[F, Leg, dict[str, Any]]] = [
        (F.RESIZE_ACK, RA, {"effective_columns": 79}),
        (F.RESIZE_ACK, AB, {"result": "rejected"}),
        (F.DETACH_ACK, RA, {"cleanup_state": "ATTACH_PTY_CLOSE_UNCERTAIN"}),
        (F.DETACH_ACK, AB, {"result": "rejected", "reason_code": "DETACH_IN_PROGRESS"}),
        (F.ADMISSION_COMMIT_ACK, RA, {"result": "rejected"}),
        (F.ADMISSION_COMMIT_ACK, RA, {"result": "rejected", "reason_code": "INTERNAL_BOUNDED"}),
        (F.ACK, RA, {"result": "write_uncertain"}),
        (F.ACK, RA, {"reason_code": "INPUT_RATE_LIMITED"}),
        (F.ACK, RA, {"result": "rejected", "reason_code": "INPUT_WRITE_UNCERTAIN"}),
        (F.ACK, RA, {"browser_input_hop_sequence": "4"}),
        (F.GAP, AB, {"reason": "baseline_redraw"}),
        (F.GAP, RA, {"from_cursor": "0"}),
        (F.GAP, RA, {"from_cursor": "18446744073709551615"}),
        (F.GAP, RA, {"to_cursor": "1"}),
        (F.STATE, AB, {"runtime_epoch": EPOCH}),
        (F.CLOSE, RA, {"code": "INTERNAL_BOUNDED"}),
        (F.CLOSE, AB, {"code": "INTERNAL_BOUNDED"}),
        (F.CLOSE, AR, {"code": "WORKSPACE_EXITED"}),
        (F.ERROR, AB, {"code": "new_error"}),
        (F.ERROR, AB, {"request_id": None}),
        (F.ADMITTED, AB, {"lease_expires_at": "2030-02-29T00:00:00.123456Z"}),
        (F.ADMITTED, AB, {"lease_expires_at": "2030-03-01T00:00:00.123Z"}),
    ]
    for kind, leg, overrides in negative:
        with pytest.raises(WireError):
            validate_payload(kind, leg, record(kind, leg) | overrides)
    assert validate_payload(F.CLOSE, AR, record(F.CLOSE, AR) | {"code": "INTERNAL_BOUNDED"})


TRACE = [
    (BA, F.WS_HELLO),
    (BA, F.KEY_INIT),
    (AR, F.RUNTIME_HELLO),
    (AR, F.KEY_INIT),
    (RA, F.HELLO_ACK),
    (RA, F.KEY_ATTEST),
    (AB, F.KEY_ATTEST),
    (BA, F.KEY_CONFIRM),
    (AR, F.KEY_CONFIRM),
    (RA, F.KEY_CONFIRM_ACK),
    (AB, F.KEY_CONFIRM_ACK),
    (AR, F.STREAM_READY),
    (RA, F.STREAM_READY_ACK),
    (AR, F.ADMISSION_COMMIT),
    (RA, F.ADMISSION_COMMIT_ACK),
    (AB, F.ADMITTED),
]


def session(count: int = 16) -> tuple[WireSession, object]:
    token = object()
    result = WireSession(A, EPOCH, stream_id=token, started_at=0)
    for leg, kind in TRACE[:count]:
        result.accept(
            leg, encoded(kind, leg, result.expected_sequence(leg)), stream_id=token, now=1
        )
    return result, token


def observe(
    s: WireSession,
    token: object,
    leg: Leg,
    kind: F,
    data: dict[str, Any] | bytes | None = None,
    now: int = 2,
) -> bytes:
    raw = encode_wire_frame(
        kind, leg, payload(kind, leg) if data is None else data, s.expected_sequence(leg)
    )
    s.accept(leg, raw, stream_id=token, now=now)
    return raw


def test_exact_normal_trace_and_first_active_counters() -> None:
    s, token = session()
    assert s.admitted and s.committed and not s.closed
    assert [s.expected_sequence(leg) for leg in Leg] == [4, 4, 6, 6]
    for leg, kind in [(BA, F.INPUT), (AR, F.INPUT), (RA, F.OUTPUT), (AB, F.OUTPUT)]:
        observe(s, token, leg, kind)
    observe(s, token, BA, F.HEARTBEAT)
    observe(s, token, AR, F.HEARTBEAT)
    observe(s, token, RA, F.HEARTBEAT)
    observe(s, token, BA, F.INPUT, opaque(F.INPUT, sequence=2))
    observe(s, token, AR, F.INPUT, opaque(F.INPUT, sequence=2))


@pytest.mark.parametrize("index", range(len(TRACE)))
def test_no_active_frame_can_interrupt_handshake(index: int) -> None:
    s, token = session(index)
    expected = s.expected_sequence(BA)
    with pytest.raises(WireError):
        observe(s, token, BA, F.INPUT)
    assert s.closed and s.expected_sequence(BA) == expected


def test_commit_retry_exactly_once_then_normal_sequence() -> None:
    s, token = session(15)
    commit = encoded(F.ADMISSION_COMMIT, AR, 5)
    ack = encoded(F.ADMISSION_COMMIT_ACK, RA, 5)
    assert s.accept(AR, commit, stream_id=token, now=2).replay
    assert s.accept(RA, ack, stream_id=token, now=3).replay
    assert s.expected_sequence(AR) == s.expected_sequence(RA) == 6
    observe(s, token, AB, F.ADMITTED, now=4)
    assert s.admitted
    with pytest.raises(WireError):
        s.accept(AR, commit, stream_id=token, now=5)


@pytest.mark.parametrize(
    "variation", ["second", "altered", "stream", "late", "early_ack", "after_terminal"]
)
def test_commit_retry_rejections(variation: str) -> None:
    s, token = session(15)
    raw = encoded(F.ADMISSION_COMMIT, AR, 5)
    now = 2
    if variation == "second":
        s.accept(AR, raw, stream_id=token, now=now)
    if variation == "altered":
        raw = raw_json(F.ADMISSION_COMMIT, json.dumps(record(F.ADMISSION_COMMIT, AR), indent=1), 5)
    if variation == "stream":
        token = object()
    if variation == "late":
        now = ADMISSION_TIMEOUT_NS
    if variation == "after_terminal":
        observe(s, token, RA, F.ERROR)
    leg = AR
    if variation == "early_ack":
        raw = encoded(F.ADMISSION_COMMIT_ACK, RA, 5)
        leg = RA
    with pytest.raises(WireError):
        s.accept(leg, raw, stream_id=token, now=now)
    assert s.closed


def test_key_relay_and_baseline_fence_mutations_close() -> None:
    s, token = session(3)
    raw = raw_json(F.KEY_INIT, json.dumps(record(F.KEY_INIT, AR), indent=1), 2)
    with pytest.raises(WireError):
        s.accept(AR, raw, stream_id=token, now=2)
    for count, leg, kind, key, new in [
        (12, RA, F.STREAM_READY_ACK, "output_cursor", "1"),
        (13, AR, F.ADMISSION_COMMIT, "admission_fence", "f" * 64),
        (15, AB, F.ADMITTED, "runtime_epoch", "1"),
    ]:
        s, token = session(count)
        with pytest.raises(WireError):
            observe(s, token, leg, kind, record(kind, leg) | {key: new})


def test_pre_context_and_trusted_failure_order() -> None:
    token = object()
    s = WireSession(A, EPOCH, stream_id=token, started_at=0)
    raw = encode_wire_frame(
        F.ERROR, AB, record(F.ERROR, AB) | {"request_id": None}, 1, trusted_context=False
    )
    s.accept(AB, raw, stream_id=token, now=1)
    with pytest.raises(WireError):
        observe(s, token, AB, F.CLOSE)
    for count in (4, 5):
        s, token = session(count)
        observe(s, token, RA, F.ERROR)
        with pytest.raises(WireError):
            observe(s, token, RA, F.CLOSE)
    for count in (6, 12, 14):
        s, token = session(count)
        observe(
            s,
            token,
            RA,
            F.STATE,
            record(F.STATE, RA) | {"state": "UNKNOWN", "reason_code": "RECONCILIATION_REQUIRED"},
        )
        observe(s, token, RA, F.CLOSE)
        observe(s, token, AB, F.ERROR)
        if count == 6:
            with pytest.raises(WireError):
                observe(s, token, AB, F.CLOSE)
        else:
            observe(s, token, AB, F.CLOSE)
        assert not s.admitted


def test_terminal_exit_is_translated_and_disallows_later_output() -> None:
    s, token = session()
    observe(s, token, RA, F.EXIT)
    observe(s, token, RA, F.CLOSE)
    observe(s, token, AB, F.EXIT)
    observe(s, token, AB, F.CLOSE)
    with pytest.raises(WireError):
        observe(s, token, RA, F.OUTPUT)


def test_detach_request_one_retry_and_exact_terminal_mapping() -> None:
    s, token = session()
    observe(s, token, BA, F.DETACH)
    raw = observe(s, token, AR, F.DETACH)
    assert s.accept(AR, raw, stream_id=token, now=3).replay
    observe(s, token, RA, F.DETACH_ACK, now=4)
    observe(
        s,
        token,
        AB,
        F.DETACH_ACK,
        record(F.DETACH_ACK, AB) | {"acknowledged_hop_sequence": "4"},
        now=4,
    )
    observe(s, token, RA, F.CLOSE, now=4)
    observe(s, token, AB, F.CLOSE, now=4)
    assert not s.admitted


@pytest.mark.parametrize("variation", ["browser", "second", "after_ack", "late", "changed"])
def test_detach_retry_fails_closed(variation: str) -> None:
    s, token = session()
    browser = observe(s, token, BA, F.DETACH)
    raw = observe(s, token, AR, F.DETACH)
    leg = AR
    now = 3
    if variation == "browser":
        raw = browser
        leg = BA
    if variation == "second":
        s.accept(AR, raw, stream_id=token, now=3)
    if variation == "after_ack":
        observe(s, token, RA, F.DETACH_ACK)
    if variation == "late":
        now = 2 + ADMISSION_TIMEOUT_NS
    if variation == "changed":
        raw = raw_json(F.DETACH, json.dumps(record(F.DETACH, AR), indent=1), 6)
    with pytest.raises(WireError):
        s.accept(leg, raw, stream_id=token, now=now)


def test_wrong_sequence_and_header_bounds_fail_without_allocation() -> None:
    for seq in (0, 2, 2**64 - 1):
        s, token = session(0)
        raw = raw_json(F.WS_HELLO, json.dumps(record(F.WS_HELLO, BA)), seq)
        with pytest.raises(WireError):
            s.accept(BA, raw, stream_id=token, now=1)
        assert s.expected_sequence(BA) == 1 and s.closed
    raw = encoded(F.KEY_INIT, BA, 2)
    for changed in (raw + b"x", raw + raw, raw[:-1], b"", b"ABWS"):
        with pytest.raises(WireError):
            decode_wire_frame(changed, BA)
    for offset in (0, 4, 5, 6, 7, 8, 20, 23):
        mutated = bytearray(raw)
        mutated[offset] ^= 255
        with pytest.raises(WireError):
            decode_wire_frame(mutated, BA)


def test_cpu_deadline_is_checked_before_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0, 5_000_001])
    raw = encoded(F.KEY_INIT, BA, 2)
    monkeypatch.setattr(time, "thread_time_ns", lambda: next(ticks))
    with pytest.raises(WireError):
        decode_wire_frame(raw, BA)


@pytest.mark.parametrize(
    "field,valid,invalid",
    [
        ("columns", [8, 240], [0, 7, 241, True, 8.5, "80", None]),
        ("rows", [1, 200], [0, 201, False, 1.1, "24", None]),
    ],
)
def test_number_field_boundaries(field: str, valid: list[int], invalid: list[object]) -> None:
    value: object
    for value in valid:
        assert validate_payload(F.RESIZE, BA, record(F.RESIZE, BA) | {field: value})
    for value in invalid:
        with pytest.raises(WireError):
            validate_payload(F.RESIZE, BA, record(F.RESIZE, BA) | {field: value})


def test_timestamp_and_exit_bounds() -> None:
    value: object
    for value in (-128, 255, None):
        assert validate_payload(F.EXIT, RA, record(F.EXIT, RA) | {"exit_code": value})
    for value in (-129, 256, False, 1.5, "1"):
        with pytest.raises(WireError):
            validate_payload(F.EXIT, RA, record(F.EXIT, RA) | {"exit_code": value})
    for value in ("2000-02-29T23:59:59.999999Z", "0001-01-01T00:00:00.000000Z"):
        assert validate_payload(
            F.ADMITTED, AB, record(F.ADMITTED, AB) | {"lease_expires_at": value}
        )
    for value in (
        "1900-02-29T00:00:00.000000Z",
        "0000-01-01T00:00:00.000000Z",
        "2030-01-01T00:00:60.000000Z",
        "2030-01-01T24:00:00.000000Z",
    ):
        with pytest.raises(WireError):
            validate_payload(F.ADMITTED, AB, record(F.ADMITTED, AB) | {"lease_expires_at": value})


def test_extreme_number_exponents_always_fail_bounded_and_close() -> None:
    for token in ("1e" + "9" * 1000, "1e-" + "9" * 1000):
        text = json.dumps(record(F.RESIZE, BA)).replace('"columns": 80', '"columns": ' + token)
        s, identity = session()
        with pytest.raises(WireError, match="^PROTOCOL_INVALID$"):
            s.accept(BA, raw_json(F.RESIZE, text, 4), stream_id=identity, now=2)
        assert s.closed and s.expected_sequence(BA) == 4


def test_no_internal_input_before_admitted_but_committed_output_may_be_quarantined() -> None:
    s, identity = session(15)
    observe(s, identity, RA, F.OUTPUT)
    assert not s.admitted
    with pytest.raises(WireError):
        observe(s, identity, AR, F.INPUT)


@pytest.mark.parametrize(
    "variation", ["crypto_skip", "crypto_replay", "context", "cursor_regression"]
)
def test_active_envelope_context_and_sequence_fences(variation: str) -> None:
    s, identity = session()
    leg, kind = (RA, F.OUTPUT) if variation == "cursor_regression" else (BA, F.INPUT)
    if variation in ("crypto_replay", "cursor_regression"):
        observe(s, identity, leg, kind)
    raw = opaque(kind, sequence=2 if variation in ("crypto_skip", "cursor_regression") else 1)
    if variation == "context":
        raw = raw[:28] + b"z" + raw[29:]
    with pytest.raises(WireError):
        observe(s, identity, leg, kind, raw)
    assert s.closed


@pytest.mark.parametrize("leg,count", [(RA, 6), (RA, 12), (RA, 14), (AB, 7), (AB, 15)])
def test_running_state_never_substitutes_admission_success(leg: Leg, count: int) -> None:
    s, identity = session(count)
    with pytest.raises(WireError):
        observe(s, identity, leg, F.STATE)
    assert s.closed


def test_browser_wait_key_attest_requires_error_then_transport_only() -> None:
    s, identity = session(6)
    with pytest.raises(WireError):
        observe(s, identity, AB, F.STATE, record(F.STATE, AB) | {"state": "UNKNOWN"})
    s, identity = session(6)
    observe(s, identity, AB, F.ERROR)
    with pytest.raises(WireError):
        observe(s, identity, AB, F.CLOSE)


def test_late_running_state_cannot_reopen_terminal_trace() -> None:
    s, identity = session()
    observe(s, identity, RA, F.EXIT)
    with pytest.raises(WireError):
        observe(s, identity, AB, F.STATE)
    assert s.closed


def test_active_needs_interaction_is_metadata_not_an_implicit_close() -> None:
    s, identity = session()
    for leg in (RA, AB):
        observe(s, identity, leg, F.STATE, record(F.STATE, leg) | {"state": "NEEDS_INTERACTION"})
    assert not s.failed and s.admitted
    observe(s, identity, BA, F.HEARTBEAT)


@pytest.mark.parametrize("kind,source,target", [(F.INPUT, BA, AR), (F.OUTPUT, RA, AB)])
def test_opaque_relay_requires_fifo_source_and_exact_bytes(
    kind: F, source: Leg, target: Leg
) -> None:
    s, identity = session()
    with pytest.raises(WireError):
        observe(s, identity, target, kind)
    s, identity = session()
    original = opaque(kind)
    observe(s, identity, source, kind, original)
    altered = original[:-1] + b"!"
    with pytest.raises(WireError):
        observe(s, identity, target, kind, altered)
    s, identity = session()
    for sequence in (1, 2):
        observe(s, identity, source, kind, opaque(kind, sequence=sequence, cursor=sequence))
    with pytest.raises(WireError):
        observe(s, identity, target, kind, opaque(kind, sequence=2, cursor=2))


@pytest.mark.parametrize("kind,source", [(F.INPUT, BA), (F.OUTPUT, RA)])
def test_pending_relay_entry_cap(kind: F, source: Leg) -> None:
    s, identity = session()
    for sequence in range(1, 257):
        observe(s, identity, source, kind, opaque(kind, sequence=sequence, cursor=sequence))
    expected = s.expected_sequence(source)
    with pytest.raises(WireError):
        observe(s, identity, source, kind, opaque(kind, sequence=257, cursor=257))
    assert s.closed and s.expected_sequence(source) == expected


@pytest.mark.parametrize(
    "count,kind,leg,size,accepted",
    [
        (16, F.INPUT, BA, INPUT_LIMIT, 3),
        (15, F.OUTPUT, RA, OUTPUT_LIMIT, 1),
        (16, F.OUTPUT, RA, OUTPUT_LIMIT, 7),
    ],
)
def test_pending_relay_encoded_byte_caps(
    count: int, kind: F, leg: Leg, size: int, accepted: int
) -> None:
    s, identity = session(count)
    for sequence in range(1, accepted + 1):
        observe(s, identity, leg, kind, opaque(kind, size, sequence, sequence))
    with pytest.raises(WireError):
        observe(s, identity, leg, kind, opaque(kind, size, accepted + 1, accepted + 1))
    assert s.closed


def test_draining_exact_relay_frees_bounded_records() -> None:
    s, identity = session()
    for sequence in range(1, 300):
        data = opaque(F.INPUT, sequence=sequence)
        observe(s, identity, BA, F.INPUT, data)
        observe(s, identity, AR, F.INPUT, data)
    assert not s.closed


def test_concurrent_duplicate_hop_serializes_before_sequence_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    s, identity = session()
    raw = encoded(F.HEARTBEAT, BA, 4)
    entered = threading.Event()
    release = threading.Event()
    second_attempt = threading.Event()
    calls: list[int] = []
    original = s._phase

    def held_phase(frame: Any) -> None:
        original(frame)
        calls.append(1)
        entered.set()
        assert release.wait(2)

    monkeypatch.setattr(s, "_phase", held_phase)

    def accept(second: bool) -> bool:
        if second:
            second_attempt.set()
        try:
            s.accept(BA, raw, stream_id=identity, now=2)
            return True
        except WireError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(accept, False)
        assert entered.wait(2)
        second = executor.submit(accept, True)
        assert second_attempt.wait(2)
        # The first call holds the session lock across validation and commit.
        assert not second.done()
        release.set()
        assert sorted([first.result(2), second.result(2)]) == [False, True]
    assert len(calls) == 1 and s.expected_sequence(BA) == 5 and s.closed


# A fresh interpreter imports the product once, then receives already-encoded
# synthetic public frames. No encoder, strptime warmup, mocked timer or GC policy
# change runs inside that interpreter before or during measured decode calls.
_FRESH_DECODE_PROBE = r"""
import gc
import json
import sys
import time
from agentbox_protocol.waw_wire import Leg, WireError, decode_wire_frame

request = json.load(sys.stdin)
frames = [(bytes.fromhex(item["hex"]), Leg(item["leg"])) for item in request["frames"]]
collections = [0]

def collected(phase, info):
    if phase == "start":
        collections[0] += 1

gc.callbacks.append(collected)
measurements = []
failures = []
for index in range(request["count"]):
    raw, leg = frames[index % len(frames)]
    before = collections[0]
    started = time.thread_time_ns()
    try:
        decode_wire_frame(raw, leg)
        error_code = None
    except WireError:
        error_code = "PROTOCOL_INVALID"
    elapsed = time.thread_time_ns() - started
    measurements.append(elapsed)
    if error_code is not None:
        failures.append({"index": index, "code": error_code, "cpu_ns": elapsed,
                         "gc_during_decode": before != collections[0]})
measurements.sort()
print(json.dumps({"count": len(measurements), "failures": failures,
                  "max_cpu_ns": measurements[-1],
                  "p50_cpu_ns": measurements[len(measurements) // 2],
                  "p95_cpu_ns": measurements[len(measurements) * 95 // 100],
                  "gc_collections": collections[0], "gc_enabled": gc.isenabled(),
                  "strptime_loaded": "_strptime" in sys.modules}))
"""


def _fresh_decode_measurement(profiles: list[tuple[F, Leg]], count: int) -> dict[str, Any]:
    import subprocess
    import sys

    frames = [
        {"hex": raw_json(kind, json.dumps(record(kind, leg))).hex(), "leg": leg.value}
        for kind, leg in profiles
    ]
    completed = subprocess.run(
        [sys.executable, "-c", _FRESH_DECODE_PROBE],
        input=json.dumps({"frames": frames, "count": count}),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


@pytest.mark.parametrize("kind,leg", [(F.ADMITTED, AB), (F.HELLO_ACK, RA)])
def test_first_decode_in_fresh_interpreter_meets_real_cpu_budget(kind: F, leg: Leg) -> None:
    measured = _fresh_decode_measurement([(kind, leg)], 1)
    assert measured["count"] == 1 and measured["failures"] == [], measured
    assert measured["max_cpu_ns"] <= 5_000_000, measured
    assert measured["gc_enabled"] and not measured["strptime_loaded"], measured


def test_repeated_valid_decodes_use_real_clock_with_normal_gc() -> None:
    measured = _fresh_decode_measurement(
        [(F.PONG, AB), (F.DETACH_ACK, RA), (F.ADMITTED, AB), (F.KEY_INIT, BA)], 5000
    )
    assert measured["count"] == 5000 and measured["failures"] == [], measured
    assert measured["gc_enabled"] and not measured["strptime_loaded"], measured
