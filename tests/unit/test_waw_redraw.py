from __future__ import annotations

import pytest
from agentbox_runtime.waw_pty import OutputFrame
from agentbox_runtime.waw_redraw import (
    BYTE_READ_LIMIT,
    MAX_BYTES,
    BoundedRedraw,
    RuntimeRedrawPublication,
    WAWRedrawError,
    trim_redraw_sentinels,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"", b""),
        (b"one", b"one"),
        (b"row\n" * 24, b"row\n" * 24),
        (b"row\n", b"row\n"),
        (b"\n" * 25, b"\n" * 24),
    ],
)
def test_trim_redraw_sentinels_accepts_the_fixed_row_boundary(raw: bytes, expected: bytes) -> None:
    redraw = trim_redraw_sentinels(raw)

    assert redraw.payload == expected
    assert redraw.has_more is (raw == b"\n" * 25)


def test_trim_redraw_sentinels_marks_and_discards_25th_unterminated_row() -> None:
    first_rows = b"row\n" * 24

    redraw = trim_redraw_sentinels(first_rows + b"unterminated-canary")

    assert redraw.payload == first_rows
    assert redraw.has_more
    assert b"canary" not in redraw.payload


def test_trim_redraw_sentinels_discards_a_nonempty_25th_row_with_lf() -> None:
    first_rows = b"row\n" * 24

    redraw = trim_redraw_sentinels(first_rows + b"row-25-canary\n")

    assert redraw.payload == first_rows
    assert redraw.has_more
    assert b"canary" not in redraw.payload


@pytest.mark.parametrize(
    ("size", "has_more"),
    [(MAX_BYTES, False), (BYTE_READ_LIMIT, True)],
)
def test_trim_redraw_sentinels_enforces_the_byte_boundary(size: int, has_more: bool) -> None:
    redraw = trim_redraw_sentinels(b"x" * size)

    assert redraw.payload == b"x" * MAX_BYTES
    assert redraw.has_more is has_more


def test_trim_redraw_sentinels_marks_both_sentinels_without_leaking_canary() -> None:
    raw = b"\n" * 24 + b"row-25-canary" + b"x" * (BYTE_READ_LIMIT - 24 - 13)

    redraw = trim_redraw_sentinels(raw)

    assert redraw.payload == b"\n" * 24
    assert redraw.has_more
    assert b"canary" not in redraw.payload


@pytest.mark.parametrize("raw", [None, bytearray(b"x"), b"x" * (BYTE_READ_LIMIT + 1)])
def test_trim_redraw_sentinels_rejects_invalid_reads(raw: object) -> None:
    with pytest.raises(WAWRedrawError):
        trim_redraw_sentinels(raw)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [b"x" * (MAX_BYTES + 1), b"\n" * 25, "not-bytes"],
)
def test_bounded_redraw_rejects_invalid_payloads(payload: object) -> None:
    with pytest.raises(WAWRedrawError):
        BoundedRedraw(payload, False)  # type: ignore[arg-type]


@pytest.mark.parametrize("has_more", [None, 1])
def test_bounded_redraw_rejects_invalid_has_more(has_more: object) -> None:
    with pytest.raises(WAWRedrawError):
        BoundedRedraw(b"", has_more)  # type: ignore[arg-type]


def test_runtime_redraw_publication_accepts_continuous_frames_and_baseline() -> None:
    frames = (OutputFrame(8, 10, b"abc"), OutputFrame(11, 12, b"de"))

    publication = RuntimeRedrawPublication(frames, baseline_cursor=12, has_more=True)

    assert publication.frames == frames
    assert publication.baseline_cursor == 12
    assert publication.has_more


def test_runtime_redraw_publication_accepts_empty_redraw_at_existing_baseline() -> None:
    publication = RuntimeRedrawPublication((), baseline_cursor=7, has_more=False)

    assert publication.baseline_cursor == 7


@pytest.mark.parametrize(
    "frames, baseline_cursor",
    [
        ((OutputFrame(1, 1, b"a"), OutputFrame(3, 3, b"b")), 3),
        ((OutputFrame(1, 1, b"a"),), 0),
        ((OutputFrame(1, 32769, b"x" * 32769),), 32769),
    ],
)
def test_runtime_redraw_publication_rejects_bad_frames_or_baseline(
    frames: tuple[OutputFrame, ...], baseline_cursor: int
) -> None:
    with pytest.raises(WAWRedrawError):
        RuntimeRedrawPublication(frames, baseline_cursor, has_more=False)


@pytest.mark.parametrize(
    "frames, baseline_cursor, has_more",
    [((), True, False), ((), 0, 1), ((), -1, False), ([], 0, False)],
)
def test_runtime_redraw_publication_rejects_invalid_types_or_empty_baseline(
    frames: object, baseline_cursor: object, has_more: object
) -> None:
    with pytest.raises(WAWRedrawError):
        RuntimeRedrawPublication(frames, baseline_cursor, has_more)  # type: ignore[arg-type]
