from __future__ import annotations

import struct

import pytest
from agentbox_protocol.abws import (
    HEADER_SIZE,
    MAGIC,
    MAX_FRAME,
    MAX_JSON_PAYLOAD,
    MAX_PAYLOAD,
    ABWSError,
    ABWSFrameType,
    ABWSParser,
    IncompleteFrame,
    TrailingBytes,
    decode_frame,
    encode_frame,
    iter_frames,
)


def _control(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {"protocol_version": 1, "request_id": "wreq_fixture"}
    payload.update(changes)
    return payload


def test_round_trip_control_frame_uses_exact_24_byte_header() -> None:
    encoded = encode_frame(ABWSFrameType.WS_HELLO, _control(action="hello"), 1)

    assert len(encoded) == HEADER_SIZE + len(encoded[HEADER_SIZE:])
    assert encoded[:4] == MAGIC
    assert encoded[4] == 1
    assert struct.unpack("!H", encoded[6:8])[0] == 0
    assert struct.unpack("!I", encoded[8:12])[0] == len(encoded) - HEADER_SIZE
    assert struct.unpack("!Q", encoded[12:20])[0] == 1
    assert struct.unpack("!I", encoded[20:24])[0] == 0

    frame = decode_frame(encoded, expected_sequence=1)
    assert frame.frame_type is ABWSFrameType.WS_HELLO
    assert frame.hop_sequence == 1
    assert frame.json_payload == _control(action="hello")


def test_input_and_output_are_opaque_bytes_only() -> None:
    payload = b"\x00\xffterminal ciphertext"
    for frame_type in (ABWSFrameType.INPUT, ABWSFrameType.OUTPUT):
        frame = decode_frame(encode_frame(frame_type, payload, 4))
        assert frame.payload == payload
        assert frame.json_payload is None

    with pytest.raises(TypeError):
        encode_frame(ABWSFrameType.INPUT, "text", 1)
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.INPUT, b"x" * 49_213, 1)


@pytest.mark.parametrize(
    "header_change",
    [
        lambda header: b"NOPE" + header[4:],
        lambda header: header[:4] + b"\x02" + header[5:],
        lambda header: header[:6] + b"\x00\x01" + header[8:],
        lambda header: header[:20] + b"\x00\x00\x00\x01",
        lambda header: header[:5] + b"\xff" + header[6:],
    ],
)
def test_header_magic_version_flags_reserved_and_unknown_type_are_rejected(header_change) -> None:
    valid = encode_frame(ABWSFrameType.PING, _control(nonce="0123456789abcdef"), 1)
    with pytest.raises(ABWSError):
        decode_frame(header_change(valid[:HEADER_SIZE]) + valid[HEADER_SIZE:])


def test_unknown_type_is_rejected() -> None:
    valid = bytearray(encode_frame(ABWSFrameType.PING, _control(), 1))
    valid[5] = 255
    with pytest.raises(ABWSError):
        decode_frame(valid)


def test_length_bounds_and_truncation_are_rejected() -> None:
    valid = encode_frame(ABWSFrameType.INPUT, b"x", 1)
    with pytest.raises(IncompleteFrame):
        decode_frame(valid[:-1])

    oversized = bytearray(valid[:HEADER_SIZE])
    oversized[8:12] = (MAX_PAYLOAD + 1).to_bytes(4, "big")
    with pytest.raises(ABWSError):
        decode_frame(oversized)

    # A valid parser-ceiling frame is still bounded by MAX_FRAME.
    raw = encode_frame(ABWSFrameType.INPUT, b"x" * 49_212, 1)
    assert len(raw) <= MAX_FRAME


def test_single_frame_decode_rejects_trailing_and_stream_decode_allows_concatenation() -> None:
    first = encode_frame(ABWSFrameType.PING, _control(), 1)
    second = encode_frame(ABWSFrameType.PONG, _control(), 2)
    with pytest.raises(TrailingBytes):
        decode_frame(first + second)
    assert [frame.frame_type for frame in iter_frames(first + second)] == [
        ABWSFrameType.PING,
        ABWSFrameType.PONG,
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"\xff",
        b"[]",
        b'{"protocol_version":1,"protocol_version":1}',
        b'{"protocol_version":1,"value":NaN}',
        b'{"protocol_version":1,"value":"\\ud800"}',
        b'{"protocol_version":true}',
        b'{"protocol_version":2}',
    ],
)
def test_control_payload_is_strict_rfc8259_utf8_object(payload: bytes) -> None:
    header = struct.pack("!4sBBHIQI", MAGIC, 1, ABWSFrameType.PING, 0, len(payload), 1, 0)
    with pytest.raises(ABWSError):
        decode_frame(header + payload)


def test_control_encode_rejects_missing_or_boolean_protocol_version_and_nan() -> None:
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.PING, {}, 1)
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.PING, {"protocol_version": True}, 1)
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.PING, {"protocol_version": 1, "value": float("nan")}, 1)
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.PING, {"protocol_version": 1, 7: "key"}, 1)


def test_json_payload_limit_is_independent_of_outer_parser_limit() -> None:
    payload = {"protocol_version": 1, "value": "x" * MAX_JSON_PAYLOAD}
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.PING, payload, 1)


def test_control_json_depth_and_key_count_are_bounded() -> None:
    too_many_keys = {"protocol_version": 1}
    too_many_keys.update({f"k{index}": index for index in range(64)})
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.PING, too_many_keys, 1)

    nested: object = {"leaf": "x"}
    for _ in range(17):
        nested = {"value": nested}
    with pytest.raises(ABWSError):
        encode_frame(ABWSFrameType.PING, {"protocol_version": 1, "value": nested}, 1)


def test_incremental_parser_enforces_contiguous_sequences_and_bounds_buffer() -> None:
    first = encode_frame(ABWSFrameType.PING, _control(), 1)
    second = encode_frame(ABWSFrameType.PONG, _control(), 2)
    parser = ABWSParser()
    output = []
    for byte in first + second:
        output.extend(parser.feed(bytes([byte])))
    assert [item.hop_sequence for item in output] == [1, 2]
    parser.finish()

    gap = ABWSParser()
    with pytest.raises(ABWSError):
        gap.feed(encode_frame(ABWSFrameType.PING, _control(), 2))

    partial = ABWSParser()
    with pytest.raises(ABWSError):
        partial.feed(b"x" * (MAX_FRAME + 1))


def test_incremental_parser_rejects_incomplete_frame_at_finish() -> None:
    parser = ABWSParser()
    parser.feed(encode_frame(ABWSFrameType.PING, _control(), 1)[:-1])
    with pytest.raises(IncompleteFrame):
        parser.finish()
