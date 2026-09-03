"""Bounded stdio peer for public synthetic WAW wire codec interoperability.

This peer is test-only.  It exposes only closed codec operations over one
request/response pipe, holds no key material and never logs request payloads.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from agentbox_protocol.abws import FrameType
from agentbox_protocol.waw_wire import (
    Leg,
    WireError,
    decode_wire_frame,
    encode_wire_frame,
    forward_wire_frame,
)

_LIMIT = 200_000
_MAX_REQUESTS = 256
_ACTIONS = frozenset({"encode", "decode", "forward"})


def _hex_bytes(value: object) -> bytes:
    if type(value) is not str or len(value) > 2 * 65_536 or len(value) % 2:
        raise ValueError("invalid bounded bytes")
    return bytes.fromhex(value)


def _hop(value: object) -> int:
    if type(value) is not str or len(value) > 20 or not value.isdecimal():
        raise ValueError("invalid hop")
    return int(value)


def _frame_type(value: object) -> FrameType:
    if type(value) is not int or isinstance(value, bool):
        raise ValueError("invalid frame type")
    return FrameType(value)


def _leg(value: object) -> Leg:
    if type(value) is not str:
        raise ValueError("invalid leg")
    return Leg(value)


def _encode(request: dict[str, Any]) -> dict[str, object]:
    if set(request) != {"action", "frame_type", "leg", "hop", "payload"}:
        raise ValueError("invalid encode request")
    kind = _frame_type(request["frame_type"])
    payload: object
    if kind in (FrameType.INPUT, FrameType.OUTPUT):
        payload = _hex_bytes(request["payload"])
    elif type(request["payload"]) is dict:
        payload = request["payload"]
    else:
        raise ValueError("invalid control payload")
    try:
        wire = encode_wire_frame(kind, _leg(request["leg"]), payload, _hop(request["hop"]))
        return {
            "ok": True,
            "wire": wire.hex(),
        }
    except (WireError, ValueError, TypeError):
        return {"ok": False}


def _decode(request: dict[str, Any]) -> dict[str, object]:
    if set(request) != {"action", "leg", "wire"}:
        raise ValueError("invalid decode request")
    try:
        frame = decode_wire_frame(_hex_bytes(request["wire"]), _leg(request["leg"]))
        return {"ok": True, "payload": frame.payload.hex()}
    except (WireError, ValueError, TypeError):
        return {"ok": False}


def _forward(request: dict[str, Any]) -> dict[str, object]:
    if set(request) != {"action", "source_leg", "target_leg", "hop", "wire"}:
        raise ValueError("invalid forward request")
    try:
        frame = decode_wire_frame(_hex_bytes(request["wire"]), _leg(request["source_leg"]))
        wire = forward_wire_frame(frame, _leg(request["target_leg"]), _hop(request["hop"]))
        return {
            "ok": True,
            "wire": wire.hex(),
        }
    except (WireError, ValueError, TypeError):
        return {"ok": False}


def _handle(request: object) -> dict[str, object]:
    if type(request) is not dict or request.get("action") not in _ACTIONS:
        raise ValueError("invalid operation")
    action = request["action"]
    if action == "encode":
        return _encode(request)
    if action == "decode":
        return _decode(request)
    return _forward(request)


def run() -> None:
    for count in range(_MAX_REQUESTS + 1):
        raw = sys.stdin.buffer.readline(_LIMIT + 1)
        if not raw:
            return
        if count == _MAX_REQUESTS or len(raw) > _LIMIT or not raw.endswith(b"\n"):
            raise ValueError("bounded request required")
        result = _handle(json.loads(raw))
        encoded = json.dumps(result, separators=(",", ":"))
        if len(encoded) > _LIMIT:
            raise ValueError("bounded response required")
        sys.stdout.write(encoded + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.stderr.write("WAW wire interop peer failed\n")
        sys.exit(1)
