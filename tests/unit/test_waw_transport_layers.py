"""Synthetic in-memory contract composition tests; not production transport/E2E."""

from __future__ import annotations

import pytest
from agentbox_protocol.abws import FrameType, decode_frame, encode_frame
from agentbox_protocol.waw_noise_contract import (
    WAWNoiseMessageType,
    WAWNoiseRole,
)
from agentbox_protocol.waw_websocket_contract import (
    WAWWebSocketDirection,
    WAWWebSocketOpcode,
    WAWWebSocketSession,
    WAWWebSocketState,
    accept_frame,
)
from agentbox_protocol.waw_websocket_parser import (
    WAWWebSocketParseError,
    parse_websocket_frame,
)


def _wire(payload: bytes, *, opcode: int = 2, fin: bool = True) -> bytes:
    key = b"\x01\x02\x03\x04"
    header = bytes([(0x80 if fin else 0) | opcode, 0x80 | len(payload)]) + key
    return header + bytes(value ^ key[index % 4] for index, value in enumerate(payload))


def test_parser_metadata_feeds_policy_without_payload_leak() -> None:
    frame = parse_websocket_frame(_wire(b"opaque"), WAWWebSocketDirection.CLIENT_TO_RUNTIME)
    assert frame.opcode is WAWWebSocketOpcode.BINARY
    assert frame.payload_length == 6
    assert not hasattr(frame, "payload")
    assert accept_frame(WAWWebSocketSession(), frame) == WAWWebSocketSession()


def test_parser_and_policy_share_fragmentation_boundary() -> None:
    first = parse_websocket_frame(
        _wire(b"part", fin=False), WAWWebSocketDirection.CLIENT_TO_RUNTIME
    )
    session = accept_frame(WAWWebSocketSession(), first)
    assert session.state is WAWWebSocketState.FRAGMENTED_BINARY
    second = parse_websocket_frame(
        _wire(b"tail", opcode=0), WAWWebSocketDirection.CLIENT_TO_RUNTIME
    )
    assert accept_frame(session, second) == WAWWebSocketSession()


def test_control_frame_does_not_reset_policy_fragment_state() -> None:
    first = parse_websocket_frame(
        _wire(b"part", fin=False), WAWWebSocketDirection.CLIENT_TO_RUNTIME
    )
    session = accept_frame(WAWWebSocketSession(), first)
    ping = parse_websocket_frame(_wire(b"ping", opcode=9), WAWWebSocketDirection.CLIENT_TO_RUNTIME)
    assert accept_frame(session, ping) == session


def test_close_parser_metadata_feeds_policy_close_state() -> None:
    payload = (1000).to_bytes(2, "big")
    peer_close = parse_websocket_frame(
        _wire(payload, opcode=8), WAWWebSocketDirection.CLIENT_TO_RUNTIME
    )
    session = accept_frame(WAWWebSocketSession(), peer_close)
    assert session.state is WAWWebSocketState.PEER_CLOSE_SEEN


def test_runtime_direction_parser_requires_unmasked_frame() -> None:
    raw = bytes([0x82, 0x03]) + b"out"
    frame = parse_websocket_frame(raw, WAWWebSocketDirection.RUNTIME_TO_CLIENT)
    assert frame.masked is False

    with pytest.raises(WAWWebSocketParseError) as exc_info:
        parse_websocket_frame(_wire(b"out"), WAWWebSocketDirection.RUNTIME_TO_CLIENT)
    assert exc_info.value.code == "MASKING_INVALID"


def test_abws_layer_remains_independent_from_websocket_metadata() -> None:
    raw = encode_frame(FrameType.HEARTBEAT, {"protocol_version": 1}, 1)
    decoded = decode_frame(raw, expected_sequence=1)
    assert decoded.frame_type is FrameType.HEARTBEAT
    assert decoded.json_payload == {"protocol_version": 1}
    assert not hasattr(decoded, "websocket_frame")


def test_noise_markers_are_closed_metadata_enums_only() -> None:
    assert WAWNoiseMessageType.KEY_ATTEST.value == "KEY_ATTEST"
    assert WAWNoiseRole.RUNTIME.value == "RUNTIME"
    assert WAWNoiseMessageType.__members__.keys() >= {"WS_HELLO", "ADMITTED"}
