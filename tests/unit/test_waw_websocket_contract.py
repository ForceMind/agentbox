from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from agentbox_protocol.waw_websocket_contract import (
    WAWWebSocketContractError,
    WAWWebSocketDirection,
    WAWWebSocketFrame,
    WAWWebSocketOpcode,
    WAWWebSocketPolicy,
    WAWWebSocketSession,
    WAWWebSocketState,
    accept_frame,
)


def frame(
    opcode: WAWWebSocketOpcode = WAWWebSocketOpcode.BINARY,
    *,
    direction: WAWWebSocketDirection = WAWWebSocketDirection.CLIENT_TO_RUNTIME,
    fin: bool = True,
    payload_length: int = 4,
) -> WAWWebSocketFrame:
    return WAWWebSocketFrame(
        direction=direction,
        opcode=opcode,
        fin=fin,
        masked=direction is WAWWebSocketDirection.CLIENT_TO_RUNTIME,
        rsv1=False,
        rsv2=False,
        rsv3=False,
        payload_length=payload_length,
    )


def replace_frame(value: WAWWebSocketFrame, **changes: object) -> WAWWebSocketFrame:
    return cast(WAWWebSocketFrame, replace(cast(Any, value), **changes))


def test_binary_message_round_trip_returns_open_session() -> None:
    assert accept_frame(WAWWebSocketSession(), frame()) == WAWWebSocketSession()


def test_binary_fragmentation_requires_continuation_and_resets_on_fin() -> None:
    session = accept_frame(WAWWebSocketSession(), frame(fin=False, payload_length=8))
    assert session.state is WAWWebSocketState.FRAGMENTED_BINARY
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(session, frame(fin=True))
    assert exc_info.value.code == "FRAGMENTATION_INVALID"
    finished = accept_frame(
        session,
        frame(WAWWebSocketOpcode.CONTINUATION, fin=True, payload_length=2),
    )
    assert finished == WAWWebSocketSession()


def test_continuation_without_start_is_rejected() -> None:
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), frame(WAWWebSocketOpcode.CONTINUATION))
    assert exc_info.value.code == "FRAGMENTATION_INVALID"


def test_text_data_is_rejected() -> None:
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), frame(WAWWebSocketOpcode.TEXT))
    assert exc_info.value.code == "TEXT_FORBIDDEN"


@pytest.mark.parametrize(
    "direction,masked",
    [
        (WAWWebSocketDirection.CLIENT_TO_RUNTIME, False),
        (WAWWebSocketDirection.RUNTIME_TO_CLIENT, True),
    ],
)
def test_masking_is_directional(direction: WAWWebSocketDirection, masked: bool) -> None:
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(
            WAWWebSocketSession(), replace_frame(frame(direction=direction), masked=masked)
        )
    assert exc_info.value.code == "MASKING_INVALID"


@pytest.mark.parametrize("field", ["rsv1", "rsv2", "rsv3"])
def test_reserved_bits_are_rejected(field: str) -> None:
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), replace_frame(frame(), **{field: True}))
    assert exc_info.value.code == "EXTENSION_FORBIDDEN"


@pytest.mark.parametrize(
    "opcode",
    [WAWWebSocketOpcode.PING, WAWWebSocketOpcode.PONG, WAWWebSocketOpcode.CLOSE],
)
def test_control_frames_must_be_final_and_bounded(opcode: WAWWebSocketOpcode) -> None:
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), frame(opcode, fin=False, payload_length=4))
    assert exc_info.value.code == "CONTROL_FRAME_INVALID"
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), frame(opcode, payload_length=126))
    assert exc_info.value.code == "CONTROL_FRAME_INVALID"


def test_ping_and_pong_do_not_change_fragment_state() -> None:
    session = accept_frame(WAWWebSocketSession(), frame(fin=False, payload_length=8))
    assert accept_frame(session, frame(WAWWebSocketOpcode.PING, payload_length=5)) == session
    assert (
        accept_frame(
            session,
            frame(WAWWebSocketOpcode.PONG, direction=WAWWebSocketDirection.RUNTIME_TO_CLIENT),
        )
        == session
    )


def test_message_and_fragment_budgets_fail_closed() -> None:
    policy = WAWWebSocketPolicy(max_frame_payload=8, max_message_payload=10, max_fragments=2)
    session = accept_frame(WAWWebSocketSession(), frame(fin=False, payload_length=8), policy=policy)
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(
            session,
            frame(WAWWebSocketOpcode.CONTINUATION, fin=False, payload_length=3),
            policy=policy,
        )
    assert exc_info.value.code == "MESSAGE_TOO_LARGE"

    session = accept_frame(WAWWebSocketSession(), frame(fin=False, payload_length=1), policy=policy)
    session = accept_frame(
        session,
        frame(WAWWebSocketOpcode.CONTINUATION, fin=False, payload_length=1),
        policy=policy,
    )
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(
            session,
            frame(WAWWebSocketOpcode.CONTINUATION, fin=False, payload_length=1),
            policy=policy,
        )
    assert exc_info.value.code == "FRAGMENTATION_INVALID"


@pytest.mark.parametrize(
    "close_code,close_reason_bytes,payload_length,utf8_valid",
    [
        (None, 0, 1, True),
        (1005, 0, 2, True),
        (1016, 0, 2, True),
        (2000, 0, 2, True),
        (1000, 1, 2, True),
        (1000, 0, 3, True),
        (1000, 1, 3, False),
    ],
)
def test_close_payload_metadata_is_strict(
    close_code: int | None,
    close_reason_bytes: int,
    payload_length: int,
    utf8_valid: bool,
) -> None:
    value = replace_frame(
        frame(WAWWebSocketOpcode.CLOSE, payload_length=payload_length),
        close_code=close_code,
        close_reason_bytes=close_reason_bytes,
        close_reason_utf8_valid=utf8_valid,
    )
    with pytest.raises(WAWWebSocketContractError):
        accept_frame(WAWWebSocketSession(), value)


def test_close_handshake_is_directional_and_terminal() -> None:
    peer_close = frame(WAWWebSocketOpcode.CLOSE, payload_length=0)
    session = accept_frame(WAWWebSocketSession(), peer_close)
    assert session.state is WAWWebSocketState.PEER_CLOSE_SEEN
    local_close = frame(
        WAWWebSocketOpcode.CLOSE,
        direction=WAWWebSocketDirection.RUNTIME_TO_CLIENT,
        payload_length=0,
    )
    closed = accept_frame(session, local_close)
    assert closed.state is WAWWebSocketState.CLOSED
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(closed, frame())
    assert exc_info.value.code == "WEBSOCKET_TERMINAL"


def test_duplicate_close_and_data_after_local_close_are_rejected() -> None:
    local_close = frame(
        WAWWebSocketOpcode.CLOSE,
        direction=WAWWebSocketDirection.RUNTIME_TO_CLIENT,
        payload_length=0,
    )
    session = accept_frame(WAWWebSocketSession(), local_close)
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(session, local_close)
    assert exc_info.value.code == "CLOSE_REPLAY"
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(session, frame())
    assert exc_info.value.code == "WEBSOCKET_TERMINAL"


def test_close_budget_is_explicitly_bounded() -> None:
    policy = WAWWebSocketPolicy(max_close_frames=1)
    local_close = frame(
        WAWWebSocketOpcode.CLOSE,
        direction=WAWWebSocketDirection.RUNTIME_TO_CLIENT,
        payload_length=0,
    )
    session = accept_frame(WAWWebSocketSession(), local_close, policy=policy)
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(session, frame(WAWWebSocketOpcode.CLOSE, payload_length=0), policy=policy)
    assert exc_info.value.code == "CLOSE_REPLAY"


@pytest.mark.parametrize(
    "state,close_frames,fragment_count,message_payload_bytes",
    [
        (WAWWebSocketState.OPEN, 1, 0, 0),
        (WAWWebSocketState.FRAGMENTED_BINARY, 0, 0, 1),
        (WAWWebSocketState.CLOSE_SENT, 1, 1, 0),
        (WAWWebSocketState.CLOSED, 1, 0, 0),
    ],
)
def test_session_state_and_counters_must_be_consistent(
    state: WAWWebSocketState,
    close_frames: int,
    fragment_count: int,
    message_payload_bytes: int,
) -> None:
    forged = WAWWebSocketSession(
        state=state,
        close_frames=close_frames,
        fragment_count=fragment_count,
        message_payload_bytes=message_payload_bytes,
    )
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(forged, frame())
    assert exc_info.value.code == "PROTOCOL_INVALID"


def test_typed_subclass_and_invalid_session_are_rejected() -> None:
    class DerivedFrame(WAWWebSocketFrame):
        pass

    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), DerivedFrame(**frame().__dict__))
    assert exc_info.value.code == "PROTOCOL_INVALID"
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(
            cast(
                WAWWebSocketSession,
                replace(cast(Any, WAWWebSocketSession()), state="OPEN"),
            ),
            frame(),
        )
    assert exc_info.value.code == "PROTOCOL_INVALID"


def test_policy_rejects_invalid_budget_configuration() -> None:
    with pytest.raises(ValueError):
        WAWWebSocketPolicy(max_frame_payload=0)
    with pytest.raises(ValueError):
        WAWWebSocketPolicy(max_close_reason_bytes=124)


def test_policy_subclass_or_mutated_policy_is_rejected() -> None:
    class DerivedPolicy(WAWWebSocketPolicy):
        pass

    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), frame(), policy=DerivedPolicy())
    assert exc_info.value.code == "PROTOCOL_INVALID"
    malformed = WAWWebSocketPolicy()
    object.__setattr__(malformed, "max_message_payload", 0)
    with pytest.raises(WAWWebSocketContractError) as exc_info:
        accept_frame(WAWWebSocketSession(), frame(), policy=malformed)
    assert exc_info.value.code == "PROTOCOL_INVALID"
