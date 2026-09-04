#!/usr/bin/env python3
"""Verify unchanged public trust fixtures with independent PyCA primitives.

This checks the already canonical ASCII fixture bytes only. It is not the
browser verifier, general JCS implementation, lifecycle or enrollment authority.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def decode(value: str, size: int) -> bytes:
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(raw) != size or base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != value:
        raise ValueError("noncanonical public fixture encoding")
    return raw


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "tests/fixtures/waw_trust/public-v1.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    bootstrap = fixture["bootstrap"]
    canonical = json.dumps(bootstrap, sort_keys=True, separators=(",", ":")).encode("ascii")
    if hashlib.sha256(canonical).hexdigest() != fixture["bootstrap_policy_sha256"]:
        raise ValueError("bootstrap fixture digest mismatch")
    keys = {bootstrap["key_id"]: decode(bootstrap["public_key"], 32)}
    records = fixture["records"]
    # Root records establish only the public keys used by these fixture checks.
    # Runtime lifecycle acceptance and current-time validity are not implied.
    for item in records:
        record = item["record"]
        if record["schema_version"] == "waw-runtime-root-v1":
            keys[record["key_id"]] = decode(record["public_key"], 32)
    for item in records:
        record = dict(item["record"])
        signature = decode(record.pop("signature"), 64)
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")
        if canonical != item["canonical_without_signature"].encode("ascii"):
            raise ValueError("signed fixture bytes changed")
        signed = item["domain"].encode("ascii") + b"\0" + canonical
        if hashlib.sha256(signed).hexdigest() != item["signed_bytes_sha256"]:
            raise ValueError("signed fixture digest mismatch")
        signer = record.get("signer_key_id", record["key_id"])
        verifier = Ed25519PublicKey.from_public_bytes(keys[signer])
        verifier.verify(signature, signed)
        for changed in (signed[1:], b"!" + signed[1:], signed.replace(b"\0", b"", 1)):
            try:
                verifier.verify(signature, changed)
            except InvalidSignature:
                continue
            raise ValueError("mutated signed fixture accepted")
    print("WAW trust public fixtures: bootstrap digest, 3 signatures and 9 mutations passed")


if __name__ == "__main__":
    main()
