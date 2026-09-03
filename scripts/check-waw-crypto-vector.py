"""Independent public WAW profile vector from PyCA primitives, not product code.

The Noise reference is first checked against the existing upstream Noise-C
vector. All private inputs are already public test-vector values. No host key,
credential, runtime state or live terminal byte is read or written.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import struct
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json"
TARGET = ROOT / "tests/fixtures/waw_crypto/profile-v1.json"
ADMISSION = {
    "attachment_id": "att_" + "4" * 32,
    "workspace_id": "aws_" + "1" * 32,
    "project_id": "prj_" + "2" * 32,
    "agent_type": "codex",
    "runtime_host_installation_id": "wri_" + "3" * 32,
    "runtime_host_installation_revision": "7",
    "auth_epoch": "5",
    "api_authority_epoch": "9007199254740993",
    "lease_number": "18446744073709551615",
    "mode": "writer",
    "generation": "9223372036854775809",
    "binding_revision": "9",
    "binding_digest": "a" * 64,
}
# Hand-authored exact key order and bytes; no product context/JCS function is used.
CONTEXT = (
    '{"agent_type":"codex","api_authority_epoch":"9007199254740993",'
    '"attachment_id":"att_44444444444444444444444444444444","auth_epoch":"5",'
    '"binding_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    '"binding_revision":"9","crypto_envelope_version":1,"generation":"9223372036854775809",'
    '"lease_number":"18446744073709551615","project_id":"prj_22222222222222222222222222222222",'
    '"protocol_id":"agentbox-waw/v1","runtime_epoch":"13",'
    '"runtime_host_installation_id":"wri_33333333333333333333333333333333",'
    '"runtime_host_installation_revision":"7","workspace_id":"aws_11111111111111111111111111111111"}'
).encode("ascii")


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("public reference vector mismatch")


def digest(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def expand(chaining: bytes, material: bytes) -> tuple[bytes, bytes]:
    temporary = hmac.digest(chaining, material, "sha256")
    first = hmac.digest(temporary, b"\x01", "sha256")
    return first, hmac.digest(temporary, first + b"\x02", "sha256")


def public(private: bytes) -> bytes:
    return X25519PrivateKey.from_private_bytes(private).public_key().public_bytes_raw()


def dh(private: bytes, peer: bytes) -> bytes:
    return X25519PrivateKey.from_private_bytes(private).exchange(
        X25519PublicKey.from_public_bytes(peer)
    )


def encrypt(key: bytes, sequence: int, plaintext: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).encrypt(b"\0" * 4 + sequence.to_bytes(8, "big"), plaintext, aad)


def reference(
    initiator: bytes,
    responder: bytes,
    static: bytes,
    prologue: bytes,
    first_payload: bytes,
    second_payload: bytes,
) -> tuple[bytes, bytes, bytes, bytes, bytes]:
    initial = b"Noise_NX_25519_AESGCM_SHA256".ljust(32, b"\0")
    chaining = initial
    transcript = digest(initial + prologue)
    first_public = public(initiator)
    second_public = public(responder)
    transcript = digest(transcript + first_public)
    transcript = digest(transcript + first_payload)
    first = first_public + first_payload
    transcript = digest(transcript + second_public)
    chaining, key = expand(chaining, dh(responder, first_public))
    encrypted_static = encrypt(key, 0, public(static), transcript)
    transcript = digest(transcript + encrypted_static)
    chaining, key = expand(chaining, dh(static, first_public))
    encrypted_payload = encrypt(key, 0, second_payload, transcript)
    transcript = digest(transcript + encrypted_payload)
    outgoing, incoming = expand(chaining, b"")
    return (
        first,
        second_public + encrypted_static + encrypted_payload,
        transcript,
        outgoing,
        incoming,
    )


def header(direction: int, cursor: int, plaintext_length: int, transcript: bytes) -> bytes:
    return struct.pack(
        ">4sBBHQQI16s", b"AWCE", 1, direction, 0, 1, cursor, plaintext_length + 16, transcript[:16]
    )


def build() -> dict[str, object]:
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    initiator = bytes.fromhex(source["init_ephemeral"])
    responder = bytes.fromhex(source["resp_ephemeral"])
    static = bytes.fromhex(source["resp_static"])
    messages = source["messages"]
    first, second, transcript, outgoing, incoming = reference(
        initiator,
        responder,
        static,
        bytes.fromhex(source["init_prologue"]),
        bytes.fromhex(messages[0]["payload"]),
        bytes.fromhex(messages[1]["payload"]),
    )
    require(first.hex() == messages[0]["ciphertext"])
    require(second.hex() == messages[1]["ciphertext"])
    require(transcript.hex() == source["handshake_hash"])
    for index, message in enumerate(messages[2:]):
        key = outgoing if index % 2 == 0 else incoming
        require(
            encrypt(key, index // 2, bytes.fromhex(message["payload"])).hex()
            == message["ciphertext"]
        )
    challenge = bytes(range(32))
    first, second, transcript, outgoing, incoming = reference(
        initiator, responder, static, CONTEXT, b"", challenge
    )
    confirm = digest(
        b"agentbox-waw/noise-confirm/v1" + struct.pack(">I", 32) + challenge + transcript
    )
    canary = digest(b"agentbox-waw/noise-confirm-ack/v1")
    require(canary.hex() == "fbb2854eb233e77bae587d1480d40192379527e27de780b24010ec97714490c3")
    input_payload = b"public WAW input vector"
    output_payload = b"public WAW output vector"
    output_cursor = 9007199254740993
    input_header = header(1, 0, len(input_payload), transcript)
    output_header = header(2, output_cursor, len(output_payload), transcript)
    return {
        "schema": "agentbox-public-waw-profile-vector-v1",
        "source_vector_sha256": digest(source_bytes).hex(),
        "admission": ADMISSION,
        "runtime_epoch": "13",
        "canonical_context_utf8": CONTEXT.decode("ascii"),
        "canonical_context_sha256": digest(CONTEXT).hex(),
        "runtime_fingerprint": digest(public(static)).hex(),
        "challenge": challenge.hex(),
        "noise_message_1": first.hex(),
        "noise_message_2": second.hex(),
        "transcript_context_hash": transcript.hex(),
        "context_id": transcript[:16].hex(),
        "key_confirm_plaintext": confirm.hex(),
        "key_confirm_ciphertext": encrypt(outgoing, 0, confirm).hex(),
        "key_confirm_ack_ciphertext": encrypt(incoming, 0, canary).hex(),
        "input_plaintext": input_payload.hex(),
        "output_plaintext": output_payload.hex(),
        "output_cursor": str(output_cursor),
        "input_awce": (
            input_header
            + encrypt(outgoing, 1, input_payload, input_header + transcript + b"browser-to-runtime")
        ).hex(),
        "output_awce": (
            output_header
            + encrypt(
                incoming, 1, output_payload, output_header + transcript + b"runtime-to-browser"
            )
        ).hex(),
    }


def main() -> None:
    if sys.argv[1:] not in ([], ["--write"]):
        raise ValueError("unsupported vector operation")
    expected = build()
    if sys.argv[1:] == ["--write"]:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(json.dumps(expected, indent=2) + "\n")
    else:
        require(json.loads(TARGET.read_bytes()) == expected)
    print("WAW profile reference PASS: upstream Noise-C oracle and fixed application vector")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("WAW profile reference FAILED (public payloads and key inputs omitted)\n")
        sys.exit(1)
