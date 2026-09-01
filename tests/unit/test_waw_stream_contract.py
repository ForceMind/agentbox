from __future__ import annotations

from unittest.mock import Mock

import pytest
from agentbox_protocol.abws import ABWSFrame, FrameType, decode_frame, encode_frame
from agentbox_protocol.waw_stream_contract import (
    WAWStreamContractError,
    decode_replay,
    decode_resize,
    validate_empty_control,
)
from agentbox_runtime.waw_pty import OutputFrame, OutputReplay, PtyGeometry
from agentbox_runtime.waw_stream_bridge import WAWStreamBridge, WAWStreamState
from agentbox_runtime.waw_supervisor import SupervisorSnapshot, SupervisorState


def _frame(kind: FrameType, payload: dict[str, object]) -> ABWSFrame:
    return decode_frame(encode_frame(kind, payload, 1))


def test_resize_and_replay_are_closed_bounded_controls() -> None:
    assert (
        decode_resize(
            _frame(FrameType.RESIZE, {"protocol_version": 1, "columns": 80, "rows": 24})
        ).columns
        == 80
    )
    assert (
        decode_replay(
            _frame(FrameType.STATE, {"protocol_version": 1, "after_cursor": 0})
        ).after_cursor
        == 0
    )
    validate_empty_control(_frame(FrameType.DETACH, {"protocol_version": 1}), FrameType.DETACH)


@pytest.mark.parametrize(
    "kind,payload",
    [
        (FrameType.RESIZE, {"protocol_version": 1, "columns": 80, "rows": 24, "path": "/tmp"}),
        (FrameType.STATE, {"protocol_version": 1, "after_cursor": -1}),
        (FrameType.DETACH, {"protocol_version": 1, "input": "arbitrary"}),
    ],
)
def test_stream_controls_reject_extra_or_invalid_fields(
    kind: FrameType, payload: dict[str, object]
) -> None:
    frame = _frame(kind, payload)
    with pytest.raises(WAWStreamContractError):
        if kind is FrameType.RESIZE:
            decode_resize(frame)
        elif kind is FrameType.STATE:
            decode_replay(frame)
        else:
            validate_empty_control(frame, kind)


def test_stream_contract_never_accepts_control_payload_as_input() -> None:
    with pytest.raises(TypeError):
        encode_frame(FrameType.INPUT, {"command": "rm"}, 1)  # type: ignore[arg-type]


def test_bridge_routes_input_resize_replay_detach_and_close() -> None:
    supervisor = Mock()
    supervisor.snapshot.side_effect = lambda: SupervisorSnapshot(
        "waw_prj_1", 1, SupervisorState.RUNNING, PtyGeometry(80, 24), 3, 2, "att_1"
    )
    supervisor.replay_output.return_value = OutputReplay("frames", (OutputFrame(1, 2, b"ok"),), 2)
    attachment = Mock()
    bridge = WAWStreamBridge(supervisor, attachment)
    assert bridge.attach().state is WAWStreamState.ATTACHED
    bridge.handle(decode_frame(encode_frame(FrameType.INPUT, b"x", 1)))
    bridge.handle(_frame(FrameType.RESIZE, {"protocol_version": 1, "columns": 100, "rows": 30}))
    output = bridge.handle(_frame(FrameType.STATE, {"protocol_version": 1, "after_cursor": 0}))
    assert decode_frame(output[0]).frame_type is FrameType.OUTPUT
    bridge.handle(_frame(FrameType.DETACH, {"protocol_version": 1}))
    bridge.handle(_frame(FrameType.CLOSE, {"protocol_version": 1}))
    assert bridge.state is WAWStreamState.CLOSED
