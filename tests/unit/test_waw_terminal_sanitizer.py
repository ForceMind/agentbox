from __future__ import annotations

import pytest
from agentbox_protocol.waw_terminal_sanitizer import (
    MAX_ESCAPE_BYTES,
    MAX_EVENT_COUNT,
    MAX_INPUT_BYTES,
    MAX_OUTPUT_TEXT_BYTES,
    SanitizedText,
    SanitizerEventKind,
    sanitize_terminal_output,
)


def kinds(value: SanitizedText) -> tuple[SanitizerEventKind, ...]:
    return tuple(event.kind for event in value.events)


def test_text_newline_carriage_return_and_tab_are_typed() -> None:
    result = sanitize_terminal_output(b"hello\nworld\r\t")
    assert result.text == "hello\nworld\r\t"
    assert kinds(result) == (
        SanitizerEventKind.TEXT,
        SanitizerEventKind.NEWLINE,
        SanitizerEventKind.TEXT,
        SanitizerEventKind.CARRIAGE_RETURN,
        SanitizerEventKind.TEXT,
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"\x00\x01\x07\x08\x0b\x0c\x7f",
        b"".join(chr(codepoint).encode("utf-8") for codepoint in range(0x80, 0xA0)),
    ],
)
def test_control_and_c1_bytes_are_dropped(raw: bytes) -> None:
    result = sanitize_terminal_output(raw)
    assert result.text == ""
    assert all(event.kind is SanitizerEventKind.DROPPED_CONTROL for event in result.events)


def test_raw_c1_bytes_are_dropped_without_discarding_neighboring_text() -> None:
    result = sanitize_terminal_output(b"before\x80after")
    assert result.text == "beforeafter"
    assert SanitizerEventKind.DROPPED_CONTROL in kinds(result)


@pytest.mark.parametrize(
    "sequence",
    [
        b"\x9b31m",
        b"\x9d52;c;clipboard\x07",
        b"\x905;discard\x9c",
        b"\x98discard\x9c",
        b"\x9ediscard\x9c",
        b"\x9fdiscard\x9c",
    ],
)
def test_raw_c1_sequences_drop_entire_payload(sequence: bytes) -> None:
    result = sanitize_terminal_output(b"before" + sequence + b"after")
    assert result.text == "beforeafter"


@pytest.mark.parametrize("raw", [b"\xc0\xaf", b"\xed\xa0\x80", b"\xf4\x90\x80\x80", b"\xe2\x82"])
def test_invalid_utf8_is_rejected_without_echo(raw: bytes) -> None:
    result = sanitize_terminal_output(raw)
    assert result == SanitizedText("", (result.events[0],))
    assert result.events[0].kind is SanitizerEventKind.REJECTED
    assert result.events[0].text == ""


def test_oversized_input_is_truncated_without_echo() -> None:
    result = sanitize_terminal_output(b"x" * (MAX_INPUT_BYTES + 1))
    assert result.text == ""
    assert kinds(result) == (SanitizerEventKind.TRUNCATED,)


@pytest.mark.parametrize(
    "sequence",
    [
        b"\x1b[31mred\x1b[0m",
        b"\x1b]52;c;clipboard\x07",
        b"\x1b]8;;https://example.test\x1b\\link\x1b]8;;\x1b\\",
        b"\x1bPdiscard\x1b\\",
        b"\x1b^discard\x1b\\",
        b"\x1b_discard\x1b\\",
        b"\x1bXdiscard\x1b\\",
    ],
)
def test_escape_osc_and_private_sequences_are_dropped(sequence: bytes) -> None:
    result = sanitize_terminal_output(b"before" + sequence + b"after")
    expected = "beforeredafter" if sequence == b"\x1b[31mred\x1b[0m" else "beforeafter"
    if b"link" in sequence:
        expected = "beforelinkafter"
    assert result.text == expected
    assert SanitizerEventKind.DROPPED_CONTROL in kinds(result)


@pytest.mark.parametrize(
    "sequence", [b"\x1b", b"\x1b]unterminated", b"\x1bPunterminated", b"\x1b[31"]
)
def test_unterminated_escape_sequences_fail_closed(sequence: bytes) -> None:
    result = sanitize_terminal_output(sequence)
    assert result.text == ""
    assert kinds(result) == (SanitizerEventKind.REJECTED,)


def test_oversized_escape_sequence_fails_closed() -> None:
    result = sanitize_terminal_output(b"\x1b]" + b"x" * MAX_ESCAPE_BYTES)
    assert result.text == ""
    assert kinds(result) == (SanitizerEventKind.REJECTED,)


def test_osc_bel_and_st_terminators_resynchronize() -> None:
    bel = sanitize_terminal_output(b"a\x1b]0;title\x07b")
    st = sanitize_terminal_output(b"a\x1b]0;title\x1b\\b")
    assert bel.text == st.text == "ab"


def test_output_text_and_event_budgets_are_bounded() -> None:
    result = sanitize_terminal_output(("x" * (MAX_OUTPUT_TEXT_BYTES + 1)).encode())
    assert len(result.text.encode()) <= MAX_OUTPUT_TEXT_BYTES
    assert len(result.events) <= MAX_EVENT_COUNT
    assert result.events[-1].kind is SanitizerEventKind.TRUNCATED


def test_result_and_events_are_frozen_typed_records() -> None:
    result = sanitize_terminal_output(b"ok")
    assert isinstance(result, SanitizedText)
    assert result.events[0].kind is SanitizerEventKind.TEXT
    with pytest.raises(AttributeError):
        result.text = "changed"  # type: ignore[misc]


def test_non_bytes_are_rejected() -> None:
    result = sanitize_terminal_output(bytearray(b"not accepted"))  # type: ignore[arg-type]
    assert kinds(result) == (SanitizerEventKind.REJECTED,)
