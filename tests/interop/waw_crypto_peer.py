"""Bounded in-memory profile peer; captured pipes contain public test bytes only."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from agentbox_protocol.waw_crypto_context import canonical_context_bytes, derive_context
from agentbox_protocol.waw_crypto_profile import BrowserCryptoProfile, RuntimeCryptoProfile

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 200_000
_HEX = re.compile(r"[0-9a-f]*\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,19})\Z")


def raw(value: object) -> bytes:
    if type(value) is not str or len(value) > 100_000 or not _HEX.fullmatch(value):
        raise ValueError("invalid bounded test bytes")
    return bytes.fromhex(value)


def cursor(value: object) -> int:
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise ValueError("invalid test cursor")
    result = int(value)
    if result > 2**64 - 1:
        raise ValueError("test cursor overflow")
    return result


class Peer:
    def __init__(self) -> None:
        self.vector = json.loads((ROOT / "tests/fixtures/waw_crypto/profile-v1.json").read_bytes())
        self.keys = json.loads(
            (ROOT / "tests/fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json").read_bytes()
        )
        self.profile: BrowserCryptoProfile | RuntimeCryptoProfile | None = None

    def request(self, request: dict[str, Any]) -> dict[str, object]:
        action = request.get("action")
        if action == "init" and self.profile is None:
            if request.get("role") == "browser":
                self.profile = BrowserCryptoProfile(
                    self.vector["admission"],
                    self.vector["runtime_epoch"],
                    self.vector["runtime_fingerprint"],
                    ephemeral_private_key=raw(self.keys["init_ephemeral"]),
                )
            elif request.get("role") == "runtime":
                self.profile = RuntimeCryptoProfile(
                    self.vector["admission"],
                    self.vector["runtime_epoch"],
                    raw(self.keys["resp_static"]),
                    ephemeral_private_key=raw(self.keys["resp_ephemeral"]),
                    random_bytes=lambda size: bytes(range(size)),
                )
            else:
                raise ValueError("unsupported peer role")
            context = canonical_context_bytes(
                derive_context(self.vector["admission"], self.vector["runtime_epoch"])
            )
            return {"ok": True, "context": context.decode("ascii")}
        profile = self.profile
        if profile is None:
            raise ValueError("peer unavailable")
        try:
            if action == "start" and isinstance(profile, BrowserCryptoProfile):
                return {"ok": True, "frame": profile.start()}
            if action == "attest" and isinstance(profile, BrowserCryptoProfile):
                return {"ok": True, "frame": profile.receive_attest(request["frame"])}
            if action == "ack" and isinstance(profile, BrowserCryptoProfile):
                profile.receive_ack(request["frame"])
                return {"ok": True}
            if action == "hello" and isinstance(profile, RuntimeCryptoProfile):
                return {"ok": True, "frame": profile.receive_init(request["frame"])}
            if action == "confirm" and isinstance(profile, RuntimeCryptoProfile):
                return {"ok": True, "frame": profile.receive_confirm(request["frame"])}
            if action == "encrypt":
                plaintext = raw(request["plaintext"])
                ciphertext = (
                    profile.encrypt_input(plaintext)
                    if isinstance(profile, BrowserCryptoProfile)
                    else profile.encrypt_output(plaintext, cursor(request["cursor"]))
                )
                return {"ok": True, "ciphertext": ciphertext.hex()}
            if action == "decrypt":
                ciphertext = raw(request["ciphertext"])
                plaintext = (
                    profile.decrypt_output(ciphertext, expected_cursor=cursor(request["cursor"]))
                    if isinstance(profile, BrowserCryptoProfile)
                    else profile.decrypt_input(ciphertext)
                )
                return {"ok": True, "plaintext": plaintext.hex()}
            if action == "status":
                return {
                    "ok": True,
                    "closed": profile.closed,
                    "ready": profile.crypto_ready,
                    "hash": profile.transcript_context_hash.hex(),
                    "context_id": profile.context_id.hex(),
                }
            raise ValueError("unsupported peer operation")
        except Exception:
            # No exception text, SQL, key, frame, ciphertext or plaintext logging.
            return {"ok": False, "closed": profile.closed}

    def close(self) -> None:
        if self.profile is not None:
            self.profile.destroy()


def main() -> None:
    peer = Peer()
    try:
        for _ in range(64):
            line = sys.stdin.buffer.readline(LIMIT + 1)
            if not line:
                return
            if len(line) > LIMIT or not line.endswith(b"\n"):
                raise ValueError("bounded test request required")
            request = json.loads(line)
            if type(request) is not dict:
                raise ValueError("test object required")
            encoded = json.dumps(peer.request(request), separators=(",", ":"))
            if len(encoded) > LIMIT:
                raise ValueError("bounded response required")
            sys.stdout.write(encoded + "\n")
            sys.stdout.flush()
        raise ValueError("test request cap reached")
    finally:
        peer.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("WAW profile interop peer failed\n")
        sys.exit(1)
