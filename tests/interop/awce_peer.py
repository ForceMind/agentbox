"""Bounded stdio peer for AWCE Python/TypeScript interoperability checks.

This test-only process accepts a small fixed operation set. It exchanges bounded
opaque synthetic bytes through captured pipes; the parent never logs payloads.
Failures expose fixed messages only, without exception details.
"""

from __future__ import annotations

import json
import sys

from agentbox_protocol.awce import AWCEEnvelope, AWCEError, decode_awce, encode_awce

_LIMIT = 200_000
_OPERATIONS = frozenset({"decode_reencode", "encode"})


def _hex_bytes(value: object) -> bytes:
    if type(value) is not str or len(value) > 100_000:
        raise ValueError("invalid bounded opaque bytes")
    return bytes.fromhex(value)


def _uint(value: object) -> int:
    if type(value) is not str or len(value) > 20 or not value.isdecimal():
        raise ValueError("invalid unsigned integer")
    return int(value)


def _int(value: object) -> int:
    if type(value) is not int:
        raise ValueError("invalid integer")
    return value


def _handle(request: object) -> dict[str, object]:
    if type(request) is not dict or request.get("action") not in _OPERATIONS:
        raise ValueError("invalid test operation")
    if request["action"] == "decode_reencode":
        raw = _hex_bytes(request.get("envelope"))
        try:
            return {"ok": True, "envelope": encode_awce(decode_awce(raw)).hex()}
        except (AWCEError, TypeError):
            return {"ok": False}

    try:
        envelope = AWCEEnvelope(
            crypto_envelope_version=_int(request.get("version")),
            direction_id=_int(request.get("direction")),
            flags=_int(request.get("flags")),
            crypto_sequence=_uint(request.get("sequence")),
            stream_cursor=_uint(request.get("cursor")),
            context_id=_hex_bytes(request.get("context_id")),
            ciphertext=_hex_bytes(request.get("ciphertext")),
        )
        return {"ok": True, "envelope": encode_awce(envelope).hex()}
    except (AWCEError, TypeError, ValueError):
        return {"ok": False}


def run() -> None:
    while raw := sys.stdin.buffer.readline(_LIMIT + 1):
        if len(raw) > _LIMIT or not raw.endswith(b"\n"):
            raise ValueError("bounded test request required")
        result = _handle(json.loads(raw))
        encoded = json.dumps(result, separators=(",", ":"))
        if len(encoded) > _LIMIT:
            raise ValueError("bounded test response required")
        sys.stdout.write(encoded + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.stderr.write("AWCE interop peer failed\n")
        sys.exit(1)
