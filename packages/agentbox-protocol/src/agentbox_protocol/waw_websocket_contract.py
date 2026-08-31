"""Contract-only WebSocket framing policy for future WAW transport.

This module validates already-parsed frame metadata and maintains an immutable
fragment/close state. It is not a WebSocket parser, network listener, Origin or
CSRF gate, Noise implementation, ABWS parser, PTY bridge, or authentication
boundary. It performs no I/O and never receives terminal payload bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, NoReturn, cast


class WAWWebSocketContractError(ValueError):
    """A metadata policy input or state transition is invalid."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class WAWWebSocketOpcode(StrEnum):
    CONTINUATION = "CONTINUATION"
    TEXT = "TEXT"
    BINARY = "BINARY"
    CLOSE = "CLOSE"
    PING = "PING"
    PONG = "PONG"


class WAWWebSocketDirection(StrEnum):
    CLIENT_TO_RUNTIME = "CLIENT_TO_RUNTIME"
    RUNTIME_TO_CLIENT = "RUNTIME_TO_CLIENT"


class WAWWebSocketState(StrEnum):
    OPEN = "OPEN"
    FRAGMENTED_BINARY = "FRAGMENTED_BINARY"
    CLOSE_SENT = "CLOSE_SENT"
    PEER_CLOSE_SEEN = "PEER_CLOSE_SEEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


_ALLOWED_CLOSE_CODES = frozenset(range(1000, 1004)) | frozenset(range(1007, 1015))


@dataclass(frozen=True)
class WAWWebSocketPolicy:
    """Fixed WAW metadata budgets; no network operation is performed."""

    max_frame_payload: int = 65536
    max_message_payload: int = 65536
    max_fragments: int = 64
    max_close_reason_bytes: int = 123
    max_close_frames: int = 2

    def __post_init__(self) -> None:
        if type(self.max_frame_payload) is not int or not 1 <= self.max_frame_payload <= 65536:
            raise ValueError("max_frame_payload must be in 1..65536")
        if type(self.max_message_payload) is not int or not 1 <= self.max_message_payload <= 65536:
            raise ValueError("max_message_payload must be in 1..65536")
        if type(self.max_fragments) is not int or not 1 <= self.max_fragments <= 256:
            raise ValueError("max_fragments must be in 1..256")
        if (
            type(self.max_close_reason_bytes) is not int
            or not 0 <= self.max_close_reason_bytes <= 123
        ):
            raise ValueError("max_close_reason_bytes must be in 0..123")
        if type(self.max_close_frames) is not int or not 1 <= self.max_close_frames <= 2:
            raise ValueError("max_close_frames must be in 1..2")


@dataclass(frozen=True)
class WAWWebSocketFrame:
    """Bounded parsed metadata; payload bytes are intentionally absent."""

    direction: WAWWebSocketDirection
    opcode: WAWWebSocketOpcode
    fin: bool
    masked: bool
    rsv1: bool
    rsv2: bool
    rsv3: bool
    payload_length: int
    close_code: int | None = None
    close_reason_bytes: int = 0
    close_reason_utf8_valid: bool = True


@dataclass(frozen=True)
class WAWWebSocketSession:
    """Immutable policy state for one synthetic connection."""

    state: WAWWebSocketState = WAWWebSocketState.OPEN
    message_payload_bytes: int = 0
    fragment_count: int = 0
    close_frames: int = 0


def _reject(code: str, message: str) -> NoReturn:
    raise WAWWebSocketContractError(code, message)


def _validate_policy(policy: WAWWebSocketPolicy) -> None:
    if type(policy) is not WAWWebSocketPolicy:
        _reject("PROTOCOL_INVALID", "policy must be an exact typed record")
    value = cast(Any, policy)
    if (
        type(value.max_frame_payload) is not int
        or not 1 <= value.max_frame_payload <= 65536
        or type(value.max_message_payload) is not int
        or not 1 <= value.max_message_payload <= 65536
        or type(value.max_fragments) is not int
        or not 1 <= value.max_fragments <= 256
        or type(value.max_close_reason_bytes) is not int
        or not 0 <= value.max_close_reason_bytes <= 123
        or type(value.max_close_frames) is not int
        or not 1 <= value.max_close_frames <= 2
    ):
        _reject("PROTOCOL_INVALID", "policy budget is invalid")


def _validate_frame(frame: WAWWebSocketFrame, policy: WAWWebSocketPolicy) -> None:
    if type(frame) is not WAWWebSocketFrame:
        _reject("PROTOCOL_INVALID", "frame must be an exact typed record")
    value = cast(Any, frame)
    if not isinstance(value.direction, WAWWebSocketDirection):
        _reject("PROTOCOL_INVALID", "direction is invalid")
    if not isinstance(value.opcode, WAWWebSocketOpcode):
        _reject("PROTOCOL_INVALID", "opcode is invalid")
    if type(value.fin) is not bool or type(value.masked) is not bool:
        _reject("PROTOCOL_INVALID", "FIN/masking flags must be booleans")
    if type(value.rsv1) is not bool or type(value.rsv2) is not bool or type(value.rsv3) is not bool:
        _reject("PROTOCOL_INVALID", "RSV flags must be booleans")
    if value.rsv1 or value.rsv2 or value.rsv3:
        _reject("EXTENSION_FORBIDDEN", "WebSocket extensions are not enabled")
    if (
        type(value.payload_length) is not int
        or not 0 <= value.payload_length <= policy.max_frame_payload
    ):
        _reject("FRAME_TOO_LARGE", "frame payload exceeds the fixed limit")
    expected_mask = value.direction is WAWWebSocketDirection.CLIENT_TO_RUNTIME
    if value.masked is not expected_mask:
        _reject("MASKING_INVALID", "frame masking does not match its fixed direction")
    if value.opcode in {
        WAWWebSocketOpcode.CLOSE,
        WAWWebSocketOpcode.PING,
        WAWWebSocketOpcode.PONG,
    } and (not value.fin or value.payload_length > 125):
        _reject("CONTROL_FRAME_INVALID", "control frames must be final and at most 125 bytes")
    if value.opcode is WAWWebSocketOpcode.CLOSE:
        if value.payload_length == 1:
            _reject("CLOSE_PAYLOAD_INVALID", "close payload cannot contain one byte")
        if value.payload_length == 0:
            if value.close_code is not None or value.close_reason_bytes != 0:
                _reject("CLOSE_PAYLOAD_INVALID", "empty close payload has no code or reason")
        else:
            if (
                type(value.close_code) is not int
                or value.close_code not in _ALLOWED_CLOSE_CODES
                and not 3000 <= value.close_code <= 4999
            ):
                _reject("CLOSE_CODE_INVALID", "close code is outside the allowed range")
            if (
                type(value.close_reason_bytes) is not int
                or not 0 <= value.close_reason_bytes <= policy.max_close_reason_bytes
            ):
                _reject("CLOSE_REASON_INVALID", "close reason exceeds the fixed limit")
            if value.close_reason_bytes != value.payload_length - 2:
                _reject("CLOSE_REASON_INVALID", "close reason length does not match payload")
            if type(value.close_reason_utf8_valid) is not bool or not value.close_reason_utf8_valid:
                _reject("CLOSE_REASON_INVALID", "close reason UTF-8 is invalid")
    elif value.close_code is not None or value.close_reason_bytes != 0:
        _reject("PROTOCOL_INVALID", "close metadata is forbidden on non-close frames")


def _validate_session_invariants(session: WAWWebSocketSession, policy: WAWWebSocketPolicy) -> None:
    value = cast(Any, session)
    if value.state in {WAWWebSocketState.OPEN, WAWWebSocketState.REJECTED}:
        if value.message_payload_bytes != 0 or value.fragment_count != 0 or value.close_frames != 0:
            _reject("PROTOCOL_INVALID", "open/rejected session counters are inconsistent")
    elif value.state is WAWWebSocketState.FRAGMENTED_BINARY:
        if value.fragment_count < 1 or value.close_frames != 0:
            _reject("PROTOCOL_INVALID", "fragmented session counters are inconsistent")
    elif value.state in {WAWWebSocketState.CLOSE_SENT, WAWWebSocketState.PEER_CLOSE_SEEN}:
        if value.message_payload_bytes != 0 or value.fragment_count != 0 or value.close_frames != 1:
            _reject("PROTOCOL_INVALID", "closing session counters are inconsistent")
    elif value.state is WAWWebSocketState.CLOSED and (
        value.message_payload_bytes != 0 or value.fragment_count != 0 or value.close_frames != 2
    ):
        _reject("PROTOCOL_INVALID", "closed session counters are inconsistent")
    if value.close_frames > policy.max_close_frames:
        _reject("PROTOCOL_INVALID", "session close budget is invalid")


def accept_frame(
    session: WAWWebSocketSession,
    frame: WAWWebSocketFrame,
    *,
    policy: WAWWebSocketPolicy | None = None,
) -> WAWWebSocketSession:
    """Apply one parsed frame to an immutable policy state."""

    if type(session) is not WAWWebSocketSession:
        _reject("PROTOCOL_INVALID", "session must be an exact typed record")
    policy = WAWWebSocketPolicy() if policy is None else policy
    _validate_policy(policy)
    value = cast(Any, session)
    if not isinstance(value.state, WAWWebSocketState):
        _reject("PROTOCOL_INVALID", "session state is invalid")
    if (
        type(value.message_payload_bytes) is not int
        or not 0 <= value.message_payload_bytes <= policy.max_message_payload
    ):
        _reject("PROTOCOL_INVALID", "session message budget is invalid")
    if (
        type(value.fragment_count) is not int
        or not 0 <= value.fragment_count <= policy.max_fragments
    ):
        _reject("PROTOCOL_INVALID", "session fragment budget is invalid")
    if (
        type(value.close_frames) is not int
        or not 0 <= value.close_frames <= policy.max_close_frames
    ):
        _reject("PROTOCOL_INVALID", "session close budget is invalid")
    _validate_session_invariants(session, policy)
    _validate_frame(frame, policy)
    if value.state in {WAWWebSocketState.CLOSED, WAWWebSocketState.REJECTED}:
        _reject("WEBSOCKET_TERMINAL", "WebSocket policy state is terminal")
    if frame.opcode is WAWWebSocketOpcode.TEXT:
        _reject("TEXT_FORBIDDEN", "WAW accepts binary data only")
    if frame.opcode in {WAWWebSocketOpcode.BINARY, WAWWebSocketOpcode.CONTINUATION}:
        if value.state in {WAWWebSocketState.CLOSE_SENT, WAWWebSocketState.PEER_CLOSE_SEEN}:
            _reject("WEBSOCKET_TERMINAL", "data is forbidden after close")
        if frame.opcode is WAWWebSocketOpcode.BINARY:
            if value.state is not WAWWebSocketState.OPEN:
                _reject(
                    "FRAGMENTATION_INVALID", "new binary data cannot start during fragmentation"
                )
        elif value.state is not WAWWebSocketState.FRAGMENTED_BINARY:
            _reject("FRAGMENTATION_INVALID", "continuation requires an active binary message")
        total = value.message_payload_bytes + frame.payload_length
        if total > policy.max_message_payload:
            _reject("MESSAGE_TOO_LARGE", "logical message exceeds the fixed limit")
        fragments = (
            value.fragment_count + 1
            if value.state is WAWWebSocketState.FRAGMENTED_BINARY or not frame.fin
            else 0
        )
        if fragments > policy.max_fragments:
            _reject("FRAGMENTATION_INVALID", "fragment count exceeds the fixed limit")
        if frame.fin:
            return WAWWebSocketSession()
        return WAWWebSocketSession(
            state=WAWWebSocketState.FRAGMENTED_BINARY,
            message_payload_bytes=total,
            fragment_count=fragments,
        )
    if frame.opcode in {WAWWebSocketOpcode.PING, WAWWebSocketOpcode.PONG}:
        if value.state in {WAWWebSocketState.CLOSE_SENT, WAWWebSocketState.PEER_CLOSE_SEEN}:
            _reject("WEBSOCKET_TERMINAL", "control data is forbidden after close")
        return session
    if frame.opcode is WAWWebSocketOpcode.CLOSE:
        if value.close_frames >= policy.max_close_frames:
            _reject("CLOSE_REPLAY", "close frame budget is exhausted")
        if value.state in {WAWWebSocketState.CLOSE_SENT, WAWWebSocketState.PEER_CLOSE_SEEN}:
            if (
                frame.direction is WAWWebSocketDirection.CLIENT_TO_RUNTIME
                and value.state is WAWWebSocketState.CLOSE_SENT
            ) or (
                frame.direction is WAWWebSocketDirection.RUNTIME_TO_CLIENT
                and value.state is WAWWebSocketState.PEER_CLOSE_SEEN
            ):
                return WAWWebSocketSession(
                    state=WAWWebSocketState.CLOSED,
                    close_frames=value.close_frames + 1,
                )
            _reject("CLOSE_REPLAY", "duplicate close direction is forbidden")
        if frame.direction is WAWWebSocketDirection.RUNTIME_TO_CLIENT:
            return WAWWebSocketSession(
                state=WAWWebSocketState.CLOSE_SENT,
                close_frames=1,
            )
        return WAWWebSocketSession(
            state=WAWWebSocketState.PEER_CLOSE_SEEN,
            close_frames=1,
        )
    _reject("OPCODE_FORBIDDEN", "opcode is not allowed by WAW policy")


__all__ = [
    "WAWWebSocketContractError",
    "WAWWebSocketDirection",
    "WAWWebSocketFrame",
    "WAWWebSocketOpcode",
    "WAWWebSocketPolicy",
    "WAWWebSocketSession",
    "WAWWebSocketState",
    "accept_frame",
]
