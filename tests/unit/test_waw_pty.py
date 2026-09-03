from __future__ import annotations

import pytest
from agentbox_runtime.waw_pty import (
    MAX_INPUT_BYTES,
    OutputRing,
    PtyGeometry,
    WAWPTYError,
    validate_input,
)


@pytest.mark.parametrize("columns", [True, 7, 241, 8.0])
def test_geometry_rejects_invalid_columns_without_clamping(columns: object) -> None:
    with pytest.raises(WAWPTYError):
        PtyGeometry(columns=columns, rows=24)  # type: ignore[arg-type]


@pytest.mark.parametrize("rows", [True, 0, 201, 1.0])
def test_geometry_rejects_invalid_rows_without_clamping(rows: object) -> None:
    with pytest.raises(WAWPTYError):
        PtyGeometry(columns=80, rows=rows)  # type: ignore[arg-type]


def test_input_is_bounded_opaque_bytes() -> None:
    assert validate_input(b"hello\x00\x1b") == b"hello\x00\x1b"
    with pytest.raises(WAWPTYError):
        validate_input(b"")
    with pytest.raises(WAWPTYError):
        validate_input(b"x" * (MAX_INPUT_BYTES + 1))


def test_output_ring_replays_and_reports_gap_after_eviction() -> None:
    ring = OutputRing(capacity_bytes=8)
    first = ring.append(b"abcd")
    second = ring.append(b"efgh")
    third = ring.append(b"ij")
    assert (first.start_cursor, first.end_cursor) == (1, 4)
    assert (second.start_cursor, second.end_cursor) == (5, 8)
    assert third.start_cursor == 9
    replay = ring.replay(4)
    assert replay.kind == "frames"
    assert b"".join(frame.payload for frame in replay.frames) == b"efghij"
    gap = ring.replay(1)
    assert gap.kind == "gap"
    assert gap.gap_start == 2
    assert gap.gap_end == 4
    baseline = ring.replay(0)
    assert baseline.kind == "gap"


def test_output_ring_retains_exactly_2000_logical_lines_in_one_frame() -> None:
    ring = OutputRing()
    payload = b"line\n" * 1999 + b"tail"

    frame = ring.append(payload)

    replay = ring.replay(0)
    assert replay.kind == "frames"
    assert replay.frames == (frame,)


def test_output_ring_evicts_complete_frame_when_2001st_logical_line_is_added() -> None:
    ring = OutputRing()
    first = ring.append(b"\n" * 2000)
    tail = ring.append(b"tail")

    replay = ring.replay(first.end_cursor)
    assert replay.kind == "frames"
    assert replay.frames == (tail,)
    gap = ring.replay(0)
    assert gap.kind == "gap"
    assert (gap.gap_start, gap.gap_end) == (1, first.end_cursor)


def test_output_ring_evicts_one_frame_that_alone_contains_2001_lines() -> None:
    ring = OutputRing()
    frame = ring.append(b"\n" * 2000 + b"tail")

    gap = ring.replay(0)
    assert gap.kind == "gap"
    assert (gap.gap_start, gap.gap_end) == (1, frame.end_cursor)
    replay = ring.replay(frame.end_cursor)
    assert replay.kind == "frames" and replay.frames == ()


def test_output_ring_counts_unterminated_tail_across_records_once() -> None:
    ring = OutputRing()
    first = ring.append(b"line\n" * 1999 + b"tail")
    second = ring.append(b" continues\n")

    replay = ring.replay(0)
    assert replay.kind == "frames"
    assert replay.frames == (first, second)


def test_output_ring_clear_keeps_cursor_gap_and_resets_line_retention() -> None:
    ring = OutputRing()
    first = ring.append(b"\n" * 2000)
    ring.clear()
    tail = ring.append(b"tail")

    gap = ring.replay(0)
    assert gap.kind == "gap"
    assert (gap.gap_start, gap.gap_end) == (1, first.end_cursor)
    replay = ring.replay(first.end_cursor)
    assert replay.kind == "frames"
    assert replay.frames == (tail,)


def test_output_cursor_exhaustion_fails_closed() -> None:
    ring = OutputRing()
    ring._next_cursor = 2**64
    with pytest.raises(WAWPTYError):
        ring.append(b"x")


def test_resume_cursor_rejects_reserved_exhaustion_value() -> None:
    with pytest.raises(WAWPTYError):
        OutputRing().replay(2**64 - 1)
