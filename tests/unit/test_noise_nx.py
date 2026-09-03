from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

import pytest
from agentbox_protocol.noise_nx import (
    MAX_MESSAGE_SIZE,
    CipherState,
    NoiseNXError,
    NXInitiator,
    NXResponder,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

PROLOGUE = b"agentbox-waw-test-prologue"
I_EPHEMERAL = b"\x01" * 32
R_STATIC = b"\x02" * 32
R_EPHEMERAL = b"\x03" * 32


def _handshake() -> tuple[NXInitiator, NXResponder]:
    initiator = NXInitiator(PROLOGUE, I_EPHEMERAL)
    responder = NXResponder(PROLOGUE, R_STATIC, R_EPHEMERAL)
    message1 = initiator.write_message1(b"hello")
    assert responder.read_message1(message1) == b"hello"
    message2 = responder.write_message2(b"ready")
    assert initiator.read_message2(message2) == b"ready"
    return initiator, responder


def test_nx_handshake_split_and_bidirectional_transport() -> None:
    initiator, responder = _handshake()
    left = initiator.take_transport()
    right = responder.take_transport()
    assert left.handshake_hash == right.handshake_hash
    assert (
        left.remote_static_public_key
        == X25519PrivateKey.from_private_bytes(R_STATIC).public_key().public_bytes_raw()
    )
    assert right.remote_static_public_key == b""
    encrypted = left.send.encrypt(b"request", b"header")
    assert right.receive.decrypt(encrypted, b"header") == b"request"
    encrypted = right.send.encrypt(b"response", b"header")
    assert left.receive.decrypt(encrypted, b"header") == b"response"


def test_independent_noise_c_nx_vector_matches_handshake_and_transport() -> None:
    vector = json.loads(
        (Path(__file__).parents[1] / "fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json").read_text()
    )
    initiator = NXInitiator(
        bytes.fromhex(vector["init_prologue"]), bytes.fromhex(vector["init_ephemeral"])
    )
    responder = NXResponder(
        bytes.fromhex(vector["resp_prologue"]),
        bytes.fromhex(vector["resp_static"]),
        bytes.fromhex(vector["resp_ephemeral"]),
    )
    messages = vector["messages"]
    message1 = initiator.write_message1(bytes.fromhex(messages[0]["payload"]))
    assert message1.hex() == messages[0]["ciphertext"]
    assert responder.read_message1(message1) == bytes.fromhex(messages[0]["payload"])
    message2 = responder.write_message2(bytes.fromhex(messages[1]["payload"]))
    assert message2.hex() == messages[1]["ciphertext"]
    assert initiator.read_message2(message2) == bytes.fromhex(messages[1]["payload"])
    left = initiator.take_transport()
    right = responder.take_transport()
    assert left.handshake_hash.hex() == vector["handshake_hash"]
    assert right.handshake_hash == left.handshake_hash
    for index, message in enumerate(messages[2:]):
        payload = bytes.fromhex(message["payload"])
        if index % 2 == 0:
            ciphertext = left.send.encrypt(payload)
            assert ciphertext.hex() == message["ciphertext"]
            assert right.receive.decrypt(ciphertext) == payload
        else:
            ciphertext = right.send.encrypt(payload)
            assert ciphertext.hex() == message["ciphertext"]
            assert left.receive.decrypt(ciphertext) == payload


def test_nx_prologue_or_static_tampering_fails_closed() -> None:
    initiator = NXInitiator(PROLOGUE, I_EPHEMERAL)
    responder = NXResponder(b"different", R_STATIC, R_EPHEMERAL)
    message1 = initiator.write_message1()
    responder.read_message1(message1)
    message2 = responder.write_message2()
    with pytest.raises(NoiseNXError):
        initiator.read_message2(message2)
    with pytest.raises(NoiseNXError):
        initiator.read_message2(message2)


def test_nx_state_order_and_single_take() -> None:
    initiator, responder = _handshake()
    transport = initiator.take_transport()
    with pytest.raises(NoiseNXError):
        initiator.take_transport()
    transport.destroy()
    with pytest.raises(NoiseNXError):
        transport.send.encrypt(b"late")
    with pytest.raises(NoiseNXError):
        responder.write_message2()


def test_nx_low_order_ephemeral_is_rejected() -> None:
    responder = NXResponder(PROLOGUE, R_STATIC, R_EPHEMERAL)
    responder.read_message1(b"\0" * 32)
    with pytest.raises(NoiseNXError):
        responder.write_message2()


def test_nx_tamper_closes_cipher_direction_without_retry() -> None:
    initiator, responder = _handshake()
    left = initiator.take_transport()
    right = responder.take_transport()
    encrypted = bytearray(left.send.encrypt(b"payload"))
    encrypted[-1] ^= 1
    with pytest.raises(NoiseNXError):
        right.receive.decrypt(bytes(encrypted))
    with pytest.raises(NoiseNXError):
        right.receive.decrypt(bytes(encrypted))


def test_cipherstate_counter_exhaustion_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    state = CipherState(b"k" * 32)
    object.__setattr__(state, "_CipherState__nonce", 2**64 - 1)
    with pytest.raises(NoiseNXError, match="exhausted"):
        state.encrypt(b"x")
    with pytest.raises(NoiseNXError, match="closed"):
        state.encrypt(b"x")


def test_cipherstate_concurrent_encryptions_advance_nonce_without_reuse() -> None:
    state = CipherState(b"k" * 32)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ciphertexts = list(
            pool.map(lambda index: state.encrypt(index.to_bytes(2, "big")), range(64))
        )
    assert state.nonce == 64
    assert len(set(ciphertexts)) == 64


@pytest.mark.parametrize("method", ["encrypt", "decrypt"])
def test_cipherstate_malformed_type_destroys_direction(method: str) -> None:
    state = CipherState(b"k" * 32)
    with pytest.raises(NoiseNXError):
        getattr(state, method)(None)
    with pytest.raises(NoiseNXError, match="closed"):
        state.encrypt(b"x")


def test_cipherstate_bad_associated_data_destroys_direction() -> None:
    state = CipherState(b"k" * 32)
    with pytest.raises(NoiseNXError):
        state.encrypt(b"x", None)
    with pytest.raises(NoiseNXError, match="closed"):
        state.encrypt(b"x")


def test_handshake_concurrent_destroy_take_and_duplicate_write_cannot_resurrect() -> None:
    initiator, _responder = _handshake()

    def capture(operation: object) -> object:
        try:
            return operation()  # type: ignore[operator]
        except NoiseNXError as error:
            return error

    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(
            pool.map(
                capture, (initiator.destroy, initiator.take_transport, initiator.write_message1)
            )
        )
    assert all(outcome is None or isinstance(outcome, NoiseNXError) for outcome in outcomes)
    with pytest.raises(NoiseNXError):
        initiator.take_transport()


@pytest.mark.parametrize("payload_size", [MAX_MESSAGE_SIZE - 32, MAX_MESSAGE_SIZE - 31])
def test_nx_message_size_is_bounded(payload_size: int) -> None:
    initiator = NXInitiator(PROLOGUE, I_EPHEMERAL)
    context = (
        nullcontext() if payload_size == MAX_MESSAGE_SIZE - 32 else pytest.raises(NoiseNXError)
    )
    with context:
        message = initiator.write_message1(b"x" * payload_size)
        assert len(message) <= MAX_MESSAGE_SIZE
