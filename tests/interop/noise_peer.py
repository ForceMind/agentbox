"""Bounded stdio peer for public-vector Node/Python interoperability tests.

This is test infrastructure, never a Runtime/API entrypoint. It reads only the
fixed public Noise-C fixture, exchanges synthetic ciphertext through pipes, and
reports bounded results without printing exception details or plaintext.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agentbox_protocol.noise_nx import NoiseNXError, NoiseTransport, NXInitiator, NXResponder

_LIMIT = 200_000
_AD = b"agentbox-noise-interop/ad"


def run() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json"
    fixture = json.loads(fixture_path.read_bytes())
    prologue = bytes.fromhex(fixture["init_prologue"])
    messages = fixture["messages"]
    initiator: NXInitiator | None = None
    responder: NXResponder | None = None
    transport: NoiseTransport | None = None
    try:
        while raw := sys.stdin.buffer.readline(_LIMIT + 1):
            if len(raw) > _LIMIT or not raw.endswith(b"\n"):
                raise ValueError("bounded test request required")
            request: dict[str, Any] = json.loads(raw)
            action = request.get("action")
            result: dict[str, Any]
            try:
                if action == "init" and initiator is None and responder is None:
                    if request["role"] == "initiator":
                        initiator = NXInitiator(prologue, bytes.fromhex(fixture["init_ephemeral"]))
                    elif request["role"] == "responder":
                        responder = NXResponder(
                            prologue,
                            bytes.fromhex(fixture["resp_static"]),
                            bytes.fromhex(fixture["resp_ephemeral"]),
                        )
                    else:
                        raise ValueError("invalid test role")
                    result = {"ok": True}
                elif action == "write1" and initiator is not None:
                    result = {
                        "message": initiator.write_message1(
                            bytes.fromhex(messages[0]["payload"])
                        ).hex()
                    }
                elif action == "read1" and responder is not None:
                    payload = responder.read_message1(bytes.fromhex(request["message"]))
                    result = {"matches": payload == bytes.fromhex(messages[0]["payload"])}
                elif action == "write2" and responder is not None:
                    result = {
                        "message": responder.write_message2(
                            bytes.fromhex(messages[1]["payload"])
                        ).hex()
                    }
                elif action == "read2" and initiator is not None:
                    payload = initiator.read_message2(bytes.fromhex(request["message"]))
                    result = {"matches": payload == bytes.fromhex(messages[1]["payload"])}
                elif action == "split" and transport is None:
                    handshake = initiator if initiator is not None else responder
                    if handshake is None:
                        raise ValueError("test handshake missing")
                    transport = handshake.take_transport()
                    result = {
                        "hash": transport.handshake_hash.hex(),
                        "remote_public_key": transport.remote_static_public_key.hex(),
                    }
                elif action == "encrypt" and transport is not None:
                    payload = b"synthetic Python-to-WebCrypto input"
                    result = {"ciphertext": transport.send.encrypt(payload, _AD).hex()}
                elif action in {"vector_encrypt", "vector_decrypt"} and transport is not None:
                    index = request.get("index")
                    if type(index) is not int or not 2 <= index < len(messages):
                        raise ValueError("invalid public vector index")
                    item = messages[index]
                    if action == "vector_encrypt":
                        result = {
                            "ciphertext": transport.send.encrypt(
                                bytes.fromhex(item["payload"])
                            ).hex()
                        }
                    else:
                        payload = transport.receive.decrypt(bytes.fromhex(request["ciphertext"]))
                        result = {"matches": payload == bytes.fromhex(item["payload"])}
                elif action == "decrypt" and transport is not None:
                    payload = transport.receive.decrypt(bytes.fromhex(request["ciphertext"]), _AD)
                    result = {"matches": payload == b"synthetic WebCrypto-to-Python input"}
                elif action == "destroy" and transport is not None:
                    transport.destroy()
                    result = {"ok": True}
                else:
                    raise ValueError("invalid test operation")
            except NoiseNXError:
                result = {"rejected": True}
            sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    finally:
        if transport is not None:
            transport.destroy()
        if initiator is not None:
            initiator.destroy()
        if responder is not None:
            responder.destroy()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        sys.stderr.write("Noise interop peer failed\n")
        sys.exit(1)
