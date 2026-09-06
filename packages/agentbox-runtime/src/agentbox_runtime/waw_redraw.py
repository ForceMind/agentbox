"""Pure bounded redraw contracts for the fixed WAW Runtime path.

This module only validates already-captured bytes and already-allocated output
frames.  It never invokes tmux, touches a pane, or retains either sentinel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentbox_runtime.waw_pty import MAX_OUTPUT_CURSOR, OutputFrame

REDRAW_MAX_ROWS = 24
ROW_READ_LIMIT = REDRAW_MAX_ROWS + 1
MAX_BYTES = 60 * 1024
BYTE_READ_LIMIT = MAX_BYTES + 1
DEADLINE = 1.0
MAX_FRAME_BYTES = 32 * 1024


class WAWRedrawError(ValueError):
    """A redraw capture or publication violates its bounded contract."""


def _physical_rows(payload: bytes) -> int:
    return payload.count(b"\n") + int(bool(payload) and not payload.endswith(b"\n"))


@dataclass(frozen=True, repr=False)
class BoundedRedraw:
    """Bounded redraw payload with only a one-bit indication of omitted data."""

    payload: bytes = field(repr=False)
    has_more: bool

    def __post_init__(self) -> None:
        if (
            type(self.payload) is not bytes
            or len(self.payload) > MAX_BYTES
            or _physical_rows(self.payload) > REDRAW_MAX_ROWS
            or type(self.has_more) is not bool
        ):
            raise WAWRedrawError("redraw payload is outside the fixed bounds")


def trim_redraw_sentinels(raw: bytes) -> BoundedRedraw:
    """Discard one byte and one physical-row look-ahead sentinel from ``raw``.

    ``raw`` must be the complete result of a fixed read capped at
    :data:`BYTE_READ_LIMIT`.  The function never returns the sentinel byte or
    the 25th physical row, including a blank row represented by ``b"\\n"``.
    """

    if type(raw) is not bytes or len(raw) > BYTE_READ_LIMIT:
        raise WAWRedrawError("redraw read must be bytes within the sentinel limit")

    byte_sentinel = len(raw) == BYTE_READ_LIMIT
    payload = raw[:MAX_BYTES] if byte_sentinel else raw
    row_sentinel = False
    newline_count = 0
    row_start = 0
    for offset, value in enumerate(payload):
        if value == ord("\n"):
            newline_count += 1
            if newline_count == ROW_READ_LIMIT:
                payload = payload[:row_start]
                row_sentinel = True
                break
            row_start = offset + 1

    if not row_sentinel and _physical_rows(payload) == ROW_READ_LIMIT:
        last_newline = payload.rfind(b"\n")
        payload = payload[: last_newline + 1]
        row_sentinel = True
    return BoundedRedraw(payload, byte_sentinel or row_sentinel)


@dataclass(frozen=True, repr=False)
class RuntimeRedrawPublication:
    """A continuous, bounded redraw publication and its post-selection cursor."""

    frames: tuple[OutputFrame, ...]
    baseline_cursor: int
    has_more: bool

    def __post_init__(self) -> None:
        if type(self.frames) is not tuple or type(self.has_more) is not bool:
            raise WAWRedrawError("redraw publication has invalid field types")
        if (
            type(self.baseline_cursor) is not int
            or not 0 <= self.baseline_cursor <= MAX_OUTPUT_CURSOR
        ):
            raise WAWRedrawError("baseline cursor is outside the output range")

        previous_end: int | None = None
        for frame in self.frames:
            if type(frame) is not OutputFrame or len(frame.payload) > MAX_FRAME_BYTES:
                raise WAWRedrawError("redraw frame is outside the publication limit")
            if previous_end is not None and frame.start_cursor != previous_end + 1:
                raise WAWRedrawError("redraw frame cursors are not continuous")
            previous_end = frame.end_cursor
        if previous_end is not None and self.baseline_cursor != previous_end:
            raise WAWRedrawError("baseline cursor must end the redraw publication")


__all__ = [
    "BYTE_READ_LIMIT",
    "DEADLINE",
    "MAX_BYTES",
    "MAX_FRAME_BYTES",
    "REDRAW_MAX_ROWS",
    "ROW_READ_LIMIT",
    "BoundedRedraw",
    "RuntimeRedrawPublication",
    "WAWRedrawError",
    "trim_redraw_sentinels",
]
