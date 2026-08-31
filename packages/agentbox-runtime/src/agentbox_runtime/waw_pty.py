"""Pure bounded contracts used by the future WAW PTY supervisor.

No PTY, process, socket, filesystem or shell operation occurs here.  The
supervisor is responsible for connecting these contracts to a fixed Runtime
process only after admission and lifecycle fencing have succeeded.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from agentbox_core.waw import validate_positive_u64

MIN_COLUMNS = 8
MAX_COLUMNS = 240
MIN_ROWS = 1
MAX_ROWS = 200
MAX_INPUT_BYTES = 16 * 1024
MAX_OUTPUT_FRAME_BYTES = 48 * 1024
MAX_OUTPUT_BUFFER_BYTES = 256 * 1024
MAX_U64 = 2**64 - 1
MAX_OUTPUT_CURSOR = MAX_U64 - 1


class WAWPTYError(ValueError):
    """A PTY contract value is invalid or cannot be represented safely."""


@dataclass(frozen=True)
class PtyGeometry:
    columns: int
    rows: int

    def __post_init__(self) -> None:
        if type(self.columns) is not int or not MIN_COLUMNS <= self.columns <= MAX_COLUMNS:
            raise WAWPTYError("columns must be an integer in 8..240")
        if type(self.rows) is not int or not MIN_ROWS <= self.rows <= MAX_ROWS:
            raise WAWPTYError("rows must be an integer in 1..200")


def validate_input(data: bytes) -> bytes:
    """Accept only bounded opaque PTY input bytes; never interpret shell syntax."""

    if not isinstance(data, bytes) or not data or len(data) > MAX_INPUT_BYTES:
        raise WAWPTYError("PTY input must be non-empty bytes within the fixed limit")
    return data


@dataclass(frozen=True)
class OutputFrame:
    start_cursor: int
    end_cursor: int
    payload: bytes

    def __post_init__(self) -> None:
        validate_positive_u64(self.start_cursor, field="start_cursor")
        validate_positive_u64(self.end_cursor, field="end_cursor")
        if self.end_cursor < self.start_cursor or self.end_cursor - self.start_cursor + 1 != len(
            self.payload
        ):
            raise WAWPTYError("output cursor range does not match payload length")
        if not self.payload or len(self.payload) > MAX_OUTPUT_FRAME_BYTES:
            raise WAWPTYError("output frame size is outside the fixed limit")


@dataclass(frozen=True)
class OutputReplay:
    kind: Literal["frames", "gap"]
    frames: tuple[OutputFrame, ...]
    next_cursor: int
    gap_start: int | None = None
    gap_end: int | None = None


class OutputRing:
    """Bounded volatile output history with fail-closed cursor replay."""

    def __init__(self, *, capacity_bytes: int = MAX_OUTPUT_BUFFER_BYTES) -> None:
        if type(capacity_bytes) is not int or not 1 <= capacity_bytes <= MAX_OUTPUT_BUFFER_BYTES:
            raise WAWPTYError("output buffer capacity is invalid")
        self._capacity = capacity_bytes
        self._frames: deque[OutputFrame] = deque()
        self._bytes = 0
        self._next_cursor = 1
        self._dropped_until = 0

    @property
    def next_cursor(self) -> int:
        return self._next_cursor

    @property
    def buffered_bytes(self) -> int:
        return self._bytes

    def append(self, payload: bytes) -> OutputFrame:
        if not isinstance(payload, bytes) or not payload:
            raise WAWPTYError("output must be non-empty bytes")
        if len(payload) > MAX_OUTPUT_FRAME_BYTES:
            raise WAWPTYError("output frame exceeds the fixed limit")
        end = self._next_cursor + len(payload) - 1
        if end > MAX_OUTPUT_CURSOR:
            raise WAWPTYError("output cursor exhausted")
        frame = OutputFrame(self._next_cursor, end, payload)
        self._next_cursor = end + 1
        self._frames.append(frame)
        self._bytes += len(payload)
        while self._bytes > self._capacity:
            removed = self._frames.popleft()
            self._bytes -= len(removed.payload)
            self._dropped_until = removed.end_cursor
        return frame

    def replay(self, after_cursor: int) -> OutputReplay:
        if type(after_cursor) is not int or not 0 <= after_cursor <= MAX_OUTPUT_CURSOR:
            raise WAWPTYError("after_cursor must be zero or a usable output cursor")
        if after_cursor < self._dropped_until:
            return OutputReplay(
                "gap", (), self._next_cursor - 1, after_cursor + 1, self._dropped_until
            )
        if not self._frames:
            return OutputReplay("frames", (), after_cursor)
        oldest = self._frames[0].start_cursor
        if after_cursor < oldest - 1:
            return OutputReplay("gap", (), self._next_cursor - 1, after_cursor + 1, oldest - 1)
        frames = tuple(frame for frame in self._frames if frame.end_cursor > after_cursor)
        return OutputReplay("frames", frames, self._next_cursor - 1)


__all__ = [
    "MAX_COLUMNS",
    "MAX_INPUT_BYTES",
    "MAX_OUTPUT_BUFFER_BYTES",
    "MAX_OUTPUT_FRAME_BYTES",
    "MAX_ROWS",
    "MIN_COLUMNS",
    "MIN_ROWS",
    "OutputFrame",
    "OutputReplay",
    "OutputRing",
    "PtyGeometry",
    "WAWPTYError",
    "validate_input",
]
