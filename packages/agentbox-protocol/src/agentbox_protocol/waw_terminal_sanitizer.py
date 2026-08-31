"""Bounded pure sanitizer for synthetic terminal-output bytes.

This is a transport-independent display reducer, not a Secret scrubber, XSS
defense, terminal emulator, or incremental stream parser. The caller must pass
one complete bounded output record; partial UTF-8/ESC/OSC records are rejected.
The module has no PTY, WebSocket, Noise, browser, CLI, filesystem, or network
integration and never returns or persists raw terminal bytes.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum

MAX_INPUT_BYTES = 64 * 1024
MAX_OUTPUT_TEXT_BYTES = 24 * 1024
MAX_EVENT_COUNT = 4096
MAX_ESCAPE_BYTES = 4096


class SanitizerEventKind(StrEnum):
    TEXT = "TEXT"
    NEWLINE = "NEWLINE"
    CARRIAGE_RETURN = "CARRIAGE_RETURN"
    DROPPED_CONTROL = "DROPPED_CONTROL"
    TRUNCATED = "TRUNCATED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class SanitizerEvent:
    """Closed event containing no raw/control payload bytes."""

    kind: SanitizerEventKind
    text: str = ""


@dataclass(frozen=True)
class SanitizedText:
    """Frozen bounded sanitized result."""

    text: str
    events: tuple[SanitizerEvent, ...]


def _terminal(kind: SanitizerEventKind) -> SanitizedText:
    return SanitizedText(text="", events=(SanitizerEvent(kind=kind),))


def _append_event(events: list[SanitizerEvent], kind: SanitizerEventKind, text: str = "") -> bool:
    if len(events) >= MAX_EVENT_COUNT:
        return False
    events.append(SanitizerEvent(kind=kind, text=text))
    return True


def _skip_escape(raw: bytes, start: int) -> int | None:
    """Return the byte offset after one bounded ESC sequence, or None."""

    if start + 1 >= len(raw):
        return None
    introducer = raw[start + 1]
    if introducer == ord("["):
        end = min(len(raw), start + MAX_ESCAPE_BYTES)
        for index in range(start + 2, end):
            if 0x40 <= raw[index] <= 0x7E:
                return index + 1
        return None
    if introducer in {ord("]"), ord("P"), ord("^"), ord("_"), ord("X")}:
        end = min(len(raw), start + MAX_ESCAPE_BYTES)
        index = start + 2
        while index < end:
            if raw[index] == 0x07 and introducer == ord("]"):
                return index + 1
            if raw[index] == 0x1B and index + 1 < end and raw[index + 1] == ord("\\"):
                return index + 2
            index += 1
        return None
    return start + 2


def _skip_c1_sequence(raw: bytes, start: int) -> int | None:
    """Skip one raw C1 CSI/OSC/DCS-family sequence within the byte budget."""

    introducer = raw[start]
    end = min(len(raw), start + MAX_ESCAPE_BYTES)
    if introducer == 0x9B:
        for index in range(start + 1, end):
            if 0x40 <= raw[index] <= 0x7E:
                return index + 1
        return None
    if introducer == 0x9C:
        return start + 1
    if introducer in {0x9D, 0x90, 0x98, 0x9E, 0x9F}:
        index = start + 1
        while index < end:
            if raw[index] == 0x07 and introducer == 0x9D:
                return index + 1
            if raw[index] == 0x9C:
                return index + 1
            if raw[index] == 0x1B and index + 1 < end and raw[index + 1] == 0x5C:
                return index + 2
            index += 1
        return None
    return start + 1


def _decode_scalar(raw: bytes, start: int) -> tuple[str, int] | None:
    """Decode one strict UTF-8 scalar, returning None for malformed input."""

    first = raw[start]
    if first < 0x80:
        return chr(first), start + 1
    if 0x80 <= first <= 0x9F:
        return "", start + 1
    if 0xC2 <= first <= 0xDF:
        width = 2
    elif 0xE0 <= first <= 0xEF:
        width = 3
    elif 0xF0 <= first <= 0xF4:
        width = 4
    else:
        return None
    end = start + width
    if end > len(raw):
        return None
    chunk = raw[start:end]
    if any(value < 0x80 or value > 0xBF for value in chunk[1:]):
        return None
    if width == 3 and ((first == 0xE0 and chunk[1] < 0xA0) or (first == 0xED and chunk[1] >= 0xA0)):
        return None
    if width == 4 and ((first == 0xF0 and chunk[1] < 0x90) or (first == 0xF4 and chunk[1] >= 0x90)):
        return None
    try:
        return chunk.decode("utf-8", "strict"), end
    except UnicodeDecodeError:
        return None


def sanitize_terminal_output(raw: bytes) -> SanitizedText:
    """Sanitize one complete bounded record without retaining raw bytes."""

    if type(raw) is not bytes:
        return _terminal(SanitizerEventKind.REJECTED)
    if len(raw) > MAX_INPUT_BYTES:
        return _terminal(SanitizerEventKind.TRUNCATED)

    output: list[str] = []
    events: list[SanitizerEvent] = []
    output_bytes = 0
    pending_text: list[str] = []
    pending_bytes = 0

    def flush_text() -> bool:
        nonlocal pending_bytes
        if not pending_text:
            return True
        text = "".join(pending_text)
        if not _append_event(events, SanitizerEventKind.TEXT, text):
            return False
        output.append(text)
        pending_text.clear()
        pending_bytes = 0
        return True

    def add_text(char: str) -> bool:
        nonlocal output_bytes, pending_bytes
        size = len(char.encode("utf-8"))
        if output_bytes + size > MAX_OUTPUT_TEXT_BYTES:
            flush_text()
            _append_event(events, SanitizerEventKind.TRUNCATED)
            return False
        pending_text.append(char)
        pending_bytes += size
        output_bytes += size
        return True

    def drop_control() -> bool:
        if not flush_text():
            return False
        if not _append_event(events, SanitizerEventKind.DROPPED_CONTROL):
            _append_event(events, SanitizerEventKind.TRUNCATED)
            return False
        return True

    def add_separator(char: str, kind: SanitizerEventKind) -> bool:
        nonlocal output_bytes
        if not flush_text() or output_bytes + 1 > MAX_OUTPUT_TEXT_BYTES:
            _append_event(events, SanitizerEventKind.TRUNCATED)
            return False
        if not _append_event(events, kind):
            _append_event(events, SanitizerEventKind.TRUNCATED)
            return False
        output.append(char)
        output_bytes += 1
        return True

    index = 0
    while index < len(raw):
        byte = raw[index]
        if byte == 0x1B:
            if not flush_text():
                break
            end = _skip_escape(raw, index)
            if end is None:
                return _terminal(SanitizerEventKind.REJECTED)
            if not _append_event(events, SanitizerEventKind.DROPPED_CONTROL):
                return _terminal(SanitizerEventKind.TRUNCATED)
            index = end
            continue
        if byte == 0x0A:
            if not add_separator("\n", SanitizerEventKind.NEWLINE):
                break
            index += 1
            continue
        if byte == 0x0D:
            if not add_separator("\r", SanitizerEventKind.CARRIAGE_RETURN):
                break
            index += 1
            continue
        if byte == 0x09:
            if not add_text("\t"):
                break
            index += 1
            continue
        if byte in {0x90, 0x98, 0x9B, 0x9D, 0x9E, 0x9F}:
            if not flush_text():
                break
            end = _skip_c1_sequence(raw, index)
            if end is None:
                return _terminal(SanitizerEventKind.REJECTED)
            if not _append_event(events, SanitizerEventKind.DROPPED_CONTROL):
                return _terminal(SanitizerEventKind.TRUNCATED)
            index = end
            continue
        if byte == 0x9C:
            if not drop_control():
                break
            index += 1
            continue
        if byte < 0x20 or 0x7F <= byte <= 0x9F:
            if not drop_control():
                break
            index += 1
            continue
        decoded = _decode_scalar(raw, index)
        if decoded is None:
            return _terminal(SanitizerEventKind.REJECTED)
        char, index = decoded
        if not char:
            if not drop_control():
                break
            continue
        if unicodedata.category(char) in {"Cc", "Cf"}:
            if not drop_control():
                break
            continue
        if not add_text(char):
            break
    flush_text()
    return SanitizedText("".join(output), tuple(events))


__all__ = [
    "MAX_EVENT_COUNT",
    "MAX_ESCAPE_BYTES",
    "MAX_INPUT_BYTES",
    "MAX_OUTPUT_TEXT_BYTES",
    "SanitizedText",
    "SanitizerEvent",
    "SanitizerEventKind",
    "sanitize_terminal_output",
]
