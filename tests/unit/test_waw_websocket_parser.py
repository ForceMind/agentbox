from __future__ import annotations

from typing import Any, cast

import pytest
from agentbox_protocol.waw_websocket_contract import (
    WAWWebSocketDirection,
    WAWWebSocketFrame,
    WAWWebSocketOpcode,
    WAWWebSocketPolicy,
    WAWWebSocketSession,
    accept_frame,
)
from agentbox_protocol.waw_websocket_parser import (
    MAX_FRAME_INPUT,
    WAWWebSocketParseError,
    parse_websocket_frame,
)

CLIENT = WAWWebSocketDirection.CLIENT_TO_RUNTIME
RUNTIME = WAWWebSocketDirection.RUNTIME_TO_CLIENT


def wire(
    payload: bytes = b"data",
    *,
    opcode: int = 2,
    fin: bool = True,
    masked: bool = True,
    length_code: int | None = None,
    declared_length: int | None = None,
    key: bytes = b"\x01\x02\x03\x04",
) -> bytes:
    length = len(payload) if declared_length is None else declared_length
    code = length if length_code is None else length_code
    header = bytes([(0x80 if fin else 0) | opcode, (0x80 if masked else 0) | code])
    if code == 126:
        header += length.to_bytes(2, "big")
    elif code == 127:
        header += length.to_bytes(8, "big")
    body = payload
    if masked:
        body = bytes(value ^ key[index % 4] for index, value in enumerate(payload))
        header += key
    return header + body


def parse(
    raw: bytes,
    direction: WAWWebSocketDirection = CLIENT,
    *,
    policy: WAWWebSocketPolicy | None = None,
) -> WAWWebSocketFrame:
    return parse_websocket_frame(raw, direction, policy=policy)


def test_parses_one_binary_frame_and_returns_metadata_only() -> None:
    value = parse(wire(b"hello"))
    assert value.opcode is WAWWebSocketOpcode.BINARY
    assert value.payload_length == 5
    assert not hasattr(value, "payload")
    assert accept_frame(WAWWebSocketSession(), value).state.value == "OPEN"


@pytest.mark.parametrize("payload_length", [125, 126, 65535, 65536])
def test_accepts_canonical_length_encodings(payload_length: int) -> None:
    payload = b"x" * payload_length
    if payload_length < 126:
        raw = wire(payload)
    elif payload_length < 65536:
        raw = wire(payload, length_code=126)
    else:
        raw = wire(payload, length_code=127)
    assert parse(raw).payload_length == payload_length


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\x82",
        b"\x82\xfe\x00",
        b"\x82\xff\x00\x00\x00\x00\x00\x01",
        wire(b"data", declared_length=8),
        wire(b"data") + b"trailing",
    ],
)
def test_truncated_noncanonical_or_trailing_frames_fail_closed(raw: bytes) -> None:
    with pytest.raises(WAWWebSocketParseError):
        parse(raw)


def test_nonminimal_extended_lengths_fail_closed() -> None:
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire(b"x" * 125, length_code=126))
    assert exc_info.value.code == "LENGTH_NON_CANONICAL"
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire(b"x" * 125, length_code=127))
    assert exc_info.value.code == "LENGTH_NON_CANONICAL"


def test_127_length_high_bit_and_oversized_input_are_rejected() -> None:
    raw = bytes([0x82, 0xFF]) + (2**63).to_bytes(8, "big") + b"\x00\x00\x00\x00"
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(raw)
    assert exc_info.value.code == "LENGTH_OVERFLOW"
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(b"x" * (MAX_FRAME_INPUT + 1))
    assert exc_info.value.code == "FRAME_TOO_LARGE"


@pytest.mark.parametrize(
    "direction,masked",
    [(CLIENT, False), (RUNTIME, True)],
)
def test_mask_direction_is_enforced(direction: WAWWebSocketDirection, masked: bool) -> None:
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire(masked=masked), direction)
    assert exc_info.value.code == "MASKING_INVALID"


@pytest.mark.parametrize("first", [0xC2, 0xA2, 0x82 | 0x40, 0x82 | 0x20, 0x82 | 0x10])
def test_reserved_or_text_opcodes_and_rsv_bits_fail_closed(first: int) -> None:
    raw = bytes([first, 0x84]) + b"\x01\x02\x03\x04" + b"data"
    with pytest.raises(WAWWebSocketParseError):
        parse(raw)


def test_control_frame_and_close_metadata_are_bounded_and_validated() -> None:
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire(b"x" * 126, opcode=9, length_code=126))
    assert exc_info.value.code == "CONTROL_FRAME_INVALID"

    close_payload = (1000).to_bytes(2, "big") + b"ok"
    value = parse(wire(close_payload, opcode=8))
    assert value.close_code == 1000
    assert value.close_reason_bytes == 2
    assert value.close_reason_utf8_valid is True

    masked_close = parse(wire(close_payload, opcode=8), CLIENT)
    assert masked_close.close_code == 1000
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire((1016).to_bytes(2, "big"), opcode=8))
    assert exc_info.value.code == "CLOSE_CODE_INVALID"


def test_invalid_close_utf8_and_missing_mask_fail_closed() -> None:
    payload = (1000).to_bytes(2, "big") + b"\xff"
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire(payload, opcode=8))
    assert exc_info.value.code == "CLOSE_REASON_INVALID"
    raw = bytes([0x82, 0x84]) + b"data"
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(raw)
    assert exc_info.value.code == "FRAME_TRUNCATED"


def test_policy_mutation_and_direction_type_fail_closed() -> None:
    malformed = WAWWebSocketPolicy()
    object.__setattr__(malformed, "max_frame_payload", 0)
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire(), CLIENT, policy=malformed)
    assert exc_info.value.code == "PROTOCOL_INVALID"
    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse(wire(), cast(Any, "CLIENT_TO_RUNTIME"))
    assert exc_info.value.code == "PROTOCOL_INVALID"
