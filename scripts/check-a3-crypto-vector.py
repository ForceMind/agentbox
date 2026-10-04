"""Independent synthetic A3 vectors: PyCA/Noise-C oracle, no product imports.

Reuses only the existing TEST oracle algorithm, not WAW profile/context/frame code.
The upstream Noise-C oracle is rechecked before deriving the dedicated A3 transcript.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tests/fixtures/a3_content/crypto-v2.json"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def build() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location(
        "noise_test_oracle", ROOT / "scripts/check-waw-crypto-vector.py"
    )
    assert spec is not None and spec.loader is not None
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    # This verifies every upstream Noise-C handshake/hash/transport ciphertext first.
    oracle.build()
    source = json.loads(oracle.SOURCE.read_bytes())
    fixture = json.loads((ROOT / "tests/fixtures/a3_content/v1.json").read_bytes())
    context = fixture["context_json"].encode("ascii")
    challenge = bytes(range(32))
    first, second, transcript, outgoing, incoming = oracle.reference(
        bytes.fromhex(source["init_ephemeral"]),
        bytes.fromhex(source["resp_ephemeral"]),
        bytes.fromhex(source["resp_static"]),
        b"agentbox-a3-content/noise-prologue/v2\0" + context,
        b"",
        challenge + (30000).to_bytes(4, "big"),
    )
    confirm = oracle.digest(
        b"agentbox-a3-content/noise-confirm/v2" + (32).to_bytes(4, "big") + challenge + transcript
    )
    ack = oracle.digest(b"agentbox-a3-content/noise-confirm-ack/v2")
    digest = oracle.digest(context).hex()

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def key(kind: str, data: bytes, **extra: str) -> str:
        return canonical(
            {
                "protocol_id": "agentbox-a3-content/crypto/v2",
                "protocol_version": 2,
                "context_digest": digest,
                "kind": kind,
                "data": b64(data),
                **extra,
            }
        ).decode()

    records = []
    for index, raw in enumerate(fixture["messages_json"][:3]):
        message = json.loads(raw)
        kind = message["kind"]
        sequence = message.get("sequence", 0)
        aad = canonical(
            {
                "domain": "agentbox-a3-content/aad/v1",
                "context_digest": digest,
                "transcript_hash": transcript.hex(),
                "kind": kind,
                "sequence": sequence,
                "direction": "browser-to-runtime" if index == 0 else "runtime-to-browser",
            }
        )
        cipher = oracle.encrypt(
            outgoing if index == 0 else incoming,
            1 if index == 0 else index,
            raw.encode("ascii"),
            aad,
        )
        records.append(
            canonical(
                {
                    "domain": "agentbox-a3-content/record/v2",
                    "context_digest": digest,
                    "kind": kind,
                    "sequence": sequence,
                    "ciphertext": b64(cipher),
                }
            ).decode()
        )
    return {
        "schema": "agentbox-a3-public-crypto-vector/v2",
        "source_vector_sha256": oracle.digest(oracle.SOURCE.read_bytes()).hex(),
        "context_json": fixture["context_json"],
        "context": fixture["context"],
        "init_ephemeral": source["init_ephemeral"],
        "resp_ephemeral": source["resp_ephemeral"],
        "resp_static": source["resp_static"],
        "runtime_public": oracle.public(bytes.fromhex(source["resp_static"])).hex(),
        "runtime_fingerprint": oracle.digest(
            oracle.public(bytes.fromhex(source["resp_static"]))
        ).hex(),
        "challenge": challenge.hex(),
        "remaining_ms": 30000,
        "final_hash": transcript.hex(),
        "key_frames": [
            key("A3_KEY_INIT", first),
            key("A3_KEY_ATTEST", second),
            key("A3_KEY_CONFIRM", oracle.encrypt(outgoing, 0, confirm)),
            key(
                "A3_KEY_CONFIRM_ACK",
                oracle.encrypt(incoming, 0, ack),
                transcript_hash=transcript.hex(),
            ),
        ],
        "plaintexts": fixture["messages_json"][:3],
        "records": records,
        "patch_hex": fixture["patch_hex"],
    }


def main() -> None:
    if sys.argv[1:] not in ([], ["--write"]):
        raise ValueError("unsupported fixture operation")
    expected = build()
    if sys.argv[1:] == ["--write"]:
        TARGET.write_text(json.dumps(expected, indent=2) + "\n")
    elif json.loads(TARGET.read_bytes()) != expected:
        raise ValueError("A3 independent vector mismatch")
    print("A3 crypto reference PASS: upstream Noise-C oracle and dedicated A3 vector")


if __name__ == "__main__":
    main()
