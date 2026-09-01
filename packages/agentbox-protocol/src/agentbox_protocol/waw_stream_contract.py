"""Typed, bounded WAW-1 synthetic stream contract.

This module describes the messages a stream bridge may interpret.  It does
not perform I/O, cryptography, WebSocket upgrades, PTY operations, or secret
handling.  Terminal bytes remain opaque and are bounded by ABWS/PTY limits.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from agentbox_protocol.abws import ABWSError, ABWSFrame, FrameType


class WAWStreamContractError(ABWSError):
    """A stream frame is not in the fixed WAW-1 contract."""


@dataclass(frozen=True)
class WAWResize:
    columns: int
    rows: int


@dataclass(frozen=True)
class WAWReplay:
    after_cursor: int


def _control(frame: ABWSFrame, *, allowed: frozenset[str]) -> Mapping[str, Any]:
    if frame.json_payload is None:
        raise WAWStreamContractError("WAW stream control frame requires JSON")
    payload = frame.json_payload
    if set(payload) - allowed or payload.get("protocol_version") != 1:
        raise WAWStreamContractError("WAW stream control payload fields are not allowed")
    return payload


def decode_resize(frame: ABWSFrame) -> WAWResize:
    if frame.frame_type is not FrameType.RESIZE:
        raise WAWStreamContractError("expected RESIZE frame")
    payload = _control(frame, allowed=frozenset({"protocol_version", "columns", "rows"}))
    if type(payload.get("columns")) is not int or type(payload.get("rows")) is not int:
        raise WAWStreamContractError("resize geometry must contain integer columns and rows")
    return WAWResize(payload["columns"], payload["rows"])


def decode_replay(frame: ABWSFrame) -> WAWReplay:
    if frame.frame_type is not FrameType.STATE:
        raise WAWStreamContractError("expected STATE replay request")
    payload = _control(frame, allowed=frozenset({"protocol_version", "after_cursor"}))
    value = payload.get("after_cursor")
    if type(value) is not int or not 0 <= value < 2**64 - 1:
        raise WAWStreamContractError("after_cursor must be a usable uint64 cursor")
    return WAWReplay(value)


def validate_empty_control(frame: ABWSFrame, frame_type: FrameType) -> None:
    if frame.frame_type is not frame_type:
        raise WAWStreamContractError(f"expected {frame_type.name} frame")
    _control(frame, allowed=frozenset({"protocol_version"}))


__all__ = [
    "WAWReplay",
    "WAWResize",
    "WAWStreamContractError",
    "decode_replay",
    "decode_resize",
    "validate_empty_control",
]
