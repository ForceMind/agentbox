"""Synthetic bounded WAW-1 stream bridge.

The bridge composes already-admitted ABWS frames with ``WAWSupervisor``.  It
does not listen on a socket, decrypt Noise payloads, spawn a process, or
accept command/path/secret fields.  It is suitable for Fake Runtime tests and
is deliberately transport-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agentbox_core.waw_tickets import ActiveAttachment
from agentbox_protocol.abws import ABWSError, ABWSFrame, FrameType, encode_frame
from agentbox_protocol.waw_stream_contract import (
    WAWStreamContractError,
    decode_replay,
    decode_resize,
    validate_empty_control,
)

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_supervisor import WAWSupervisor


class WAWStreamState(StrEnum):
    DETACHED = "DETACHED"
    ATTACHED = "ATTACHED"
    CLOSED = "CLOSED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class WAWStreamSnapshot:
    state: WAWStreamState
    next_sequence: int
    output_cursor: int


class WAWStreamBridge:
    """Bounded one-attachment bridge around a pre-started supervisor."""

    def __init__(self, supervisor: WAWSupervisor, attachment: ActiveAttachment) -> None:
        self._supervisor = supervisor
        self._attachment = attachment
        self._state = WAWStreamState.DETACHED
        self._next_sequence = 1

    @property
    def state(self) -> WAWStreamState:
        return self._state

    def snapshot(self) -> WAWStreamSnapshot:
        view = self._supervisor.snapshot()
        return WAWStreamSnapshot(self._state, self._next_sequence, view.next_cursor)

    def attach(self) -> WAWStreamSnapshot:
        self._ensure(WAWStreamState.DETACHED)
        self._supervisor.attach(self._attachment)
        self._state = WAWStreamState.ATTACHED
        return self.snapshot()

    def handle(self, frame: ABWSFrame) -> tuple[bytes, ...]:
        """Apply one already-decoded inbound frame and return encoded replies."""
        if not isinstance(frame, ABWSFrame):
            raise TypeError("frame must be an ABWSFrame")
        try:
            if frame.frame_type is FrameType.INPUT:
                self._ensure(WAWStreamState.ATTACHED)
                self._supervisor.write_input(self._attachment, frame.payload)
                return (self._reply(FrameType.ACK, {"protocol_version": 1, "ack": "INPUT"}),)
            if frame.frame_type is FrameType.RESIZE:
                self._ensure(WAWStreamState.ATTACHED)
                geometry = decode_resize(frame)
                self._supervisor.resize(
                    self._attachment, PtyGeometry(geometry.columns, geometry.rows)
                )
                return (
                    self._reply(
                        FrameType.RESIZE_ACK,
                        {"protocol_version": 1, "columns": geometry.columns, "rows": geometry.rows},
                    ),
                )
            if frame.frame_type is FrameType.STATE:
                replay = decode_replay(frame)
                result = self._supervisor.replay_output(replay.after_cursor)
                if result.kind == "gap":
                    return (
                        self._reply(
                            FrameType.GAP,
                            {
                                "protocol_version": 1,
                                "start_cursor": result.gap_start,
                                "end_cursor": result.gap_end,
                                "next_cursor": result.next_cursor,
                            },
                        ),
                    )
                replies = [
                    encode_frame(FrameType.OUTPUT, item.payload, self._take_sequence())
                    for item in result.frames
                ]
                if not replies:
                    replies.append(
                        self._reply(
                            FrameType.STATE,
                            {"protocol_version": 1, "next_cursor": result.next_cursor},
                        )
                    )
                return tuple(replies)
            if frame.frame_type is FrameType.DETACH:
                self._ensure(WAWStreamState.ATTACHED)
                validate_empty_control(frame, FrameType.DETACH)
                self._supervisor.detach(self._attachment)
                self._state = WAWStreamState.DETACHED
                return (self._reply(FrameType.DETACH_ACK, {"protocol_version": 1}),)
            if frame.frame_type is FrameType.CLOSE:
                validate_empty_control(frame, FrameType.CLOSE)
                self._state = WAWStreamState.CLOSED
                return (self._reply(FrameType.CLOSE, {"protocol_version": 1}),)
            raise WAWStreamContractError("frame type is not permitted by WAW stream bridge")
        except (ABWSError, RuntimeOperationError, ValueError):
            self._state = WAWStreamState.ERROR
            raise

    def output(self, after_cursor: int) -> tuple[bytes, ...]:
        """Read bounded replay as OUTPUT/GAP frames for synthetic consumers."""
        self._ensure(WAWStreamState.ATTACHED, WAWStreamState.DETACHED)
        result = self._supervisor.replay_output(after_cursor)
        if result.kind == "gap":
            return (
                self._reply(
                    FrameType.GAP,
                    {
                        "protocol_version": 1,
                        "start_cursor": result.gap_start,
                        "end_cursor": result.gap_end,
                        "next_cursor": result.next_cursor,
                    },
                ),
            )
        return tuple(
            encode_frame(FrameType.OUTPUT, item.payload, self._take_sequence())
            for item in result.frames
        )

    def _ensure(self, *states: WAWStreamState) -> None:
        if self._state not in states:
            raise RuntimeOperationError(
                "WAW_STREAM_STATE",
                "stream operation is invalid in the current state",
                category="conflict",
            )

    def _take_sequence(self) -> int:
        value = self._next_sequence
        self._next_sequence += 1
        return value

    def _reply(self, frame_type: FrameType, payload: dict[str, object]) -> bytes:
        return encode_frame(frame_type, payload, self._take_sequence())


__all__ = ["WAWStreamBridge", "WAWStreamSnapshot", "WAWStreamState"]
