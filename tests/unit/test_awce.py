from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from agentbox_protocol.awce import (
    HEADER_SIZE,
    INPUT_DIRECTION,
    MAX_CIPHERTEXT_SIZE,
    MAX_ENVELOPE_SIZE,
    MAX_OUTPUT_CURSOR,
    MAX_TERMINAL_SEQUENCE,
    OUTPUT_DIRECTION,
    AWCEEnvelope,
    AWCEError,
    IncompleteAWCE,
    TrailingAWCEBytes,
    decode_awce,
    encode_awce,
    encode_awce_header,
)

CONTEXT_ID = bytes(range(16))
CIPHERTEXT = b"x" + b"t" * 16
FIXTURE = bytes.fromhex(
    "41574345010100000000000000000001000000000000000000000011000102030405060708090a0b0c0d0e0f"
    "7874747474747474747474747474747474"
)


def _envelope(**changes: object) -> AWCEEnvelope:
    fields: dict[str, object] = {
        "crypto_envelope_version": 1,
        "direction_id": INPUT_DIRECTION,
        "flags": 0,
        "crypto_sequence": 1,
        "stream_cursor": 0,
        "context_id": CONTEXT_ID,
        "ciphertext": CIPHERTEXT,
    }
    fields.update(changes)
    return AWCEEnvelope(**fields)  # type: ignore[arg-type]


def _header_fields(**changes: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "crypto_envelope_version": 1,
        "direction_id": INPUT_DIRECTION,
        "flags": 0,
        "crypto_sequence": 1,
        "stream_cursor": 0,
        "context_id": CONTEXT_ID,
        "ciphertext_length": len(CIPHERTEXT),
    }
    fields.update(changes)
    return fields


def test_fixed_binary_layout_fixture_is_independent_of_encoder() -> None:
    decoded = decode_awce(FIXTURE)
    assert len(FIXTURE) == HEADER_SIZE + len(CIPHERTEXT) == 61
    assert decoded.crypto_envelope_version == 1
    assert decoded.direction_id == INPUT_DIRECTION
    assert decoded.flags == 0
    assert decoded.crypto_sequence == 1
    assert decoded.stream_cursor == 0
    assert decoded.context_id == CONTEXT_ID
    assert decoded.ciphertext == CIPHERTEXT
    assert encode_awce(decoded) == FIXTURE


def test_header_encoder_matches_independent_vector_and_envelope_prefix() -> None:
    envelope = _envelope()
    header = encode_awce_header(**_header_fields())
    assert header == FIXTURE[:HEADER_SIZE]
    assert len(header) == HEADER_SIZE
    assert encode_awce(envelope).startswith(header)


def test_header_encoder_accepts_high_bits_and_maximum_boundaries() -> None:
    header = encode_awce_header(
        **_header_fields(
            direction_id=OUTPUT_DIRECTION,
            crypto_sequence=MAX_TERMINAL_SEQUENCE,
            stream_cursor=MAX_OUTPUT_CURSOR,
            ciphertext_length=MAX_CIPHERTEXT_SIZE,
        )
    )
    assert len(header) == HEADER_SIZE
    assert header[8:16] == MAX_TERMINAL_SEQUENCE.to_bytes(8, "big")
    assert header[16:24] == MAX_OUTPUT_CURSOR.to_bytes(8, "big")
    assert header[24:28] == MAX_CIPHERTEXT_SIZE.to_bytes(4, "big")


@pytest.mark.parametrize(
    "changes",
    [
        {"ciphertext_length": 16},
        {"ciphertext_length": MAX_CIPHERTEXT_SIZE + 1},
        {"ciphertext_length": True},
        {"ciphertext_length": 17.0},
        {"context_id": b"too short"},
        {"context_id": bytearray(CONTEXT_ID)},
        {"direction_id": INPUT_DIRECTION, "stream_cursor": 1},
        {"direction_id": OUTPUT_DIRECTION, "stream_cursor": 0},
    ],
)
def test_header_encoder_rejects_invalid_length_type_context_or_cursor(
    changes: dict[str, object],
) -> None:
    with pytest.raises(AWCEError):
        encode_awce_header(**_header_fields(**changes))


def test_round_trip_output_and_immutable_redacted_record() -> None:
    envelope = _envelope(
        direction_id=OUTPUT_DIRECTION,
        crypto_sequence=7,
        stream_cursor=19,
        context_id=b"context-id-12345",
        ciphertext=b"opaque output" + b"t" * 16,
    )
    assert decode_awce(encode_awce(envelope)) == envelope
    assert "opaque output" not in repr(envelope)
    assert "context-id-12345" not in repr(envelope)
    with pytest.raises(FrozenInstanceError):
        envelope.crypto_sequence = 8  # type: ignore[misc]


@pytest.mark.parametrize(
    ("direction_id", "stream_cursor"),
    [
        (INPUT_DIRECTION, 0),
        (OUTPUT_DIRECTION, 1),
        (OUTPUT_DIRECTION, MAX_OUTPUT_CURSOR),
    ],
)
def test_direction_cursor_contract(direction_id: int, stream_cursor: int) -> None:
    envelope = _envelope(direction_id=direction_id, stream_cursor=stream_cursor)
    assert decode_awce(encode_awce(envelope))


@pytest.mark.parametrize(
    "changes",
    [
        {"crypto_envelope_version": 2},
        {"crypto_envelope_version": True},
        {"direction_id": 0},
        {"direction_id": 3},
        {"direction_id": True},
        {"flags": 1},
        {"flags": True},
        {"crypto_sequence": 0},
        {"crypto_sequence": MAX_TERMINAL_SEQUENCE + 1},
        {"crypto_sequence": True},
        {"stream_cursor": True},
        {"stream_cursor": MAX_OUTPUT_CURSOR + 1},
        {"context_id": b"too short"},
        {"context_id": bytearray(CONTEXT_ID)},
        {"ciphertext": b"t" * 16},
        {"ciphertext": b"x" * (MAX_CIPHERTEXT_SIZE + 1)},
        {"ciphertext": bytearray(CIPHERTEXT)},
        {"direction_id": INPUT_DIRECTION, "stream_cursor": 1},
        {"direction_id": OUTPUT_DIRECTION, "stream_cursor": 0},
    ],
)
def test_constructor_rejects_invalid_typed_or_boundary_fields(changes: dict[str, object]) -> None:
    with pytest.raises(AWCEError):
        _envelope(**changes)


def test_minimum_and_maximum_ciphertext_boundaries() -> None:
    minimum = _envelope(ciphertext=b"p" + b"t" * 16)
    maximum = _envelope(ciphertext=b"p" * MAX_CIPHERTEXT_SIZE)
    assert len(encode_awce(minimum)) == 61
    assert len(encode_awce(maximum)) == MAX_ENVELOPE_SIZE
    assert decode_awce(encode_awce(maximum)) == maximum


@pytest.mark.parametrize(
    "mutator",
    [
        lambda raw: b"NOPE" + raw[4:],
        lambda raw: raw[:4] + b"\x02" + raw[5:],
        lambda raw: raw[:5] + b"\x03" + raw[6:],
        lambda raw: raw[:6] + b"\x00\x01" + raw[8:],
        lambda raw: raw[:8] + b"\0" * 8 + raw[16:],
        lambda raw: raw[:16] + b"\0" * 7 + b"\x01" + raw[24:],
        lambda raw: raw[:24] + b"\0\0\0\x10" + raw[28:],
    ],
)
def test_decode_rejects_each_mutated_header_field(mutator: object) -> None:
    with pytest.raises(AWCEError):
        decode_awce(mutator(FIXTURE))  # type: ignore[operator]


def test_decode_preserves_opaque_context_id_bytes() -> None:
    mutated = FIXTURE[:28] + b"\0" * 16 + FIXTURE[44:]
    assert decode_awce(mutated).context_id == b"\0" * 16


def test_decode_rejects_short_oversize_and_trailing_data() -> None:
    with pytest.raises(IncompleteAWCE):
        decode_awce(FIXTURE[: HEADER_SIZE - 1])
    with pytest.raises(IncompleteAWCE):
        decode_awce(FIXTURE[:-1])
    with pytest.raises(TrailingAWCEBytes):
        decode_awce(FIXTURE + b"x")
    with pytest.raises(AWCEError):
        decode_awce(b"A" * (MAX_ENVELOPE_SIZE + 1))
    with pytest.raises(TypeError):
        decode_awce(bytearray(FIXTURE))
