from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from agentbox_protocol.awce import MAX_OUTPUT_CURSOR, decode_awce, encode_awce_header
from agentbox_protocol.noise_nx import CipherState, NoiseNXError, NXInitiator, NXResponder
from agentbox_protocol.waw_crypto_context import canonical_context_bytes, derive_context
from agentbox_protocol.waw_crypto_profile import (
    ACK_CANARY,
    KEY_FRAME_KEYS,
    BrowserCryptoProfile,
    RuntimeCryptoProfile,
    WAWCryptoError,
    decode_base64url,
    encode_base64url,
    validate_key_frame,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Public synthetic fixtures only. Never deployment/runtime/Provider keys.
STATIC = bytes([2]) * 32
EPHEMERAL_I = bytes([1]) * 32
EPHEMERAL_R = bytes([3]) * 32
CHALLENGE = bytes([4]) * 32
PIN = hashlib.sha256(
    X25519PrivateKey.from_private_bytes(STATIC).public_key().public_bytes_raw()
).hexdigest()
ADMISSION = {
    "attachment_id": "att_" + "1" * 32,
    "workspace_id": "aws_" + "2" * 32,
    "project_id": "prj_" + "3" * 32,
    "agent_type": "codex",
    "runtime_host_installation_id": "wri_" + "4" * 32,
    "runtime_host_installation_revision": "7",
    "auth_epoch": "8",
    "api_authority_epoch": "9",
    "lease_number": "10",
    "mode": "writer",
    "generation": "11",
    "binding_revision": "12",
    "binding_digest": "a" * 64,
}


def pair(**kwargs: Any) -> tuple[BrowserCryptoProfile, RuntimeCryptoProfile]:
    return (
        BrowserCryptoProfile(ADMISSION, "13", PIN, ephemeral_private_key=EPHEMERAL_I, **kwargs),
        RuntimeCryptoProfile(
            ADMISSION,
            "13",
            STATIC,
            ephemeral_private_key=EPHEMERAL_R,
            random_bytes=lambda length: CHALLENGE,
            **kwargs,
        ),
    )


def ready() -> tuple[BrowserCryptoProfile, RuntimeCryptoProfile]:
    browser, runtime = pair()
    init = browser.start()
    attest = runtime.receive_init(init)
    confirm = browser.receive_attest(attest)
    ack = runtime.receive_confirm(confirm)
    assert runtime.crypto_ready and not browser.crypto_ready
    browser.receive_ack(ack)
    return browser, runtime


def stage(name: str) -> tuple[Any, dict[str, str | int], Any]:
    browser, runtime = pair()
    init = browser.start()
    if name == "KEY_INIT":
        return runtime.receive_init, init, runtime
    attest = runtime.receive_init(init)
    if name == "KEY_ATTEST":
        return browser.receive_attest, attest, browser
    confirm = browser.receive_attest(attest)
    if name == "KEY_CONFIRM":
        return runtime.receive_confirm, confirm, runtime
    ack = runtime.receive_confirm(confirm)
    return browser.receive_ack, ack, browser


def test_real_crypto_complete_profile_and_exact_wire_sizes() -> None:
    browser, runtime = ready()
    assert browser.crypto_ready and runtime.crypto_ready
    assert browser.transcript_context_hash == runtime.transcript_context_hash
    assert browser.context_id == runtime.context_id == browser.transcript_context_hash[:16]
    assert ACK_CANARY.hex() == "fbb2854eb233e77bae587d1480d40192379527e27de780b24010ec97714490c3"
    for size in (1, 16384):
        encrypted = browser.encrypt_input(b"i" * size)
        assert len(encrypted) == 44 + size + 16
        envelope = decode_awce(encrypted)
        assert envelope.crypto_sequence == (1 if size == 1 else 2)
        assert envelope.stream_cursor == 0
        assert runtime.decrypt_input(encrypted) == b"i" * size
    for cursor, size in ((9, 1), (12, 32768)):
        encrypted = runtime.encrypt_output(b"o" * size, cursor)
        assert len(encrypted) == 44 + size + 16
        assert browser.decrypt_output(encrypted, expected_cursor=cursor) == b"o" * size


@pytest.mark.parametrize("name", sorted(KEY_FRAME_KEYS))
def test_key_frames_allow_strict_json_bytes_and_have_exact_fields(name: str) -> None:
    receive, frame, _owner = stage(name)
    assert frame.keys() == KEY_FRAME_KEYS[name]
    assert validate_key_frame(name, json.dumps(frame).encode()) == frame
    if name == "KEY_INIT":
        assert len(decode_base64url(frame["noise_message_1"], 32)) == 32
    elif name == "KEY_ATTEST":
        assert len(decode_base64url(frame["noise_message_2"], 128)) == 128
    else:
        assert len(decode_base64url(frame["ciphertext"], 48)) == 48
    receive(json.dumps(frame).encode())


@pytest.mark.parametrize(
    "name,key", [(name, key) for name, keys in KEY_FRAME_KEYS.items() for key in sorted(keys)]
)
@pytest.mark.parametrize("change", ["missing", "mutated"])
def test_every_key_frame_field_is_bound_and_fail_closed(name: str, key: str, change: str) -> None:
    receive, frame, owner = stage(name)
    if change == "missing":
        del frame[key]
    else:
        item = frame[key]
        if type(item) is int:
            frame[key] = 2
        elif key == "agent_type":
            frame[key] = "claude"
        elif key.endswith("_id") and key != "protocol_id":
            frame[key] = str(item)[:-1] + "f"
        elif str(item).isdecimal():
            frame[key] = str(int(str(item)) + 1)
        else:
            frame[key] = "invalid"
    with pytest.raises(WAWCryptoError):
        receive(frame)
    assert owner.closed and not owner.crypto_ready
    with pytest.raises(WAWCryptoError):
        receive(frame)


@pytest.mark.parametrize("name", sorted(KEY_FRAME_KEYS))
@pytest.mark.parametrize(
    "kind",
    [
        "extra",
        "duplicate",
        "nested",
        "version_bool",
        "version_float",
        "version_string",
        "trailing",
        "utf8",
        "oversize",
    ],
)
def test_strict_frame_parsing(name: str, kind: str) -> None:
    receive, frame, owner = stage(name)
    value: object = frame
    if kind == "extra":
        frame["extra"] = "x"
    elif kind == "duplicate":
        value = json.dumps(frame).encode()[:-1] + b',"protocol_version":1}'
    elif kind == "nested":
        value = {"context": frame}
    elif kind.startswith("version_"):
        value = {
            **frame,
            "protocol_version": {"version_bool": True, "version_float": 1.0, "version_string": "1"}[
                kind
            ],
        }
    elif kind == "trailing":
        value = json.dumps(frame).encode() + b" null"
    elif kind == "utf8":
        value = b"{\xff}"
    elif kind == "oversize":
        value = b" " * 4097
    with pytest.raises(WAWCryptoError):
        receive(value)
    assert owner.closed


@pytest.mark.parametrize(
    "name,key,length",
    [
        ("KEY_INIT", "noise_message_1", 32),
        ("KEY_ATTEST", "noise_message_2", 128),
        ("KEY_CONFIRM", "ciphertext", 48),
        ("KEY_CONFIRM_ACK", "ciphertext", 48),
    ],
)
@pytest.mark.parametrize("mutation", ["padding", "whitespace", "byte", "short", "long"])
def test_noise_payload_mutations_fail_closed(
    name: str, key: str, length: int, mutation: str
) -> None:
    receive, frame, owner = stage(name)
    raw = decode_base64url(frame[key], length)
    if mutation == "padding":
        frame[key] = str(frame[key]) + "="
    elif mutation == "whitespace":
        frame[key] = " " + str(frame[key])[1:]
    elif mutation == "byte":
        frame[key] = encode_base64url(raw[:-1] + bytes([raw[-1] ^ 1]))
    elif mutation == "short":
        frame[key] = encode_base64url(raw[:-1])
    else:
        frame[key] = encode_base64url(raw + b"x")
    with pytest.raises(WAWCryptoError):
        receive(frame)
    assert owner.closed


def test_noncanonical_base64_unused_bits() -> None:
    canonical = encode_base64url(bytes(32))
    with pytest.raises(WAWCryptoError):
        decode_base64url(canonical[:-1] + "B", 32)


def test_decrypted_static_must_match_independent_pin_even_if_metadata_matches() -> None:
    browser = BrowserCryptoProfile(ADMISSION, "13", "b" * 64)
    runtime = RuntimeCryptoProfile(ADMISSION, "13", STATIC)
    attest = runtime.receive_init(browser.start())
    attest["runtime_attestation_x25519_fingerprint"] = "b" * 64
    with pytest.raises(WAWCryptoError):
        browser.receive_attest(attest)
    assert browser.closed


@pytest.mark.parametrize("challenge", [b"", bytes(31), bytes(33), None, bytearray(32)])
def test_runtime_rng_failures_destroy_state(challenge: Any) -> None:
    browser = BrowserCryptoProfile(ADMISSION, "13", PIN)
    runtime = RuntimeCryptoProfile(ADMISSION, "13", STATIC, random_bytes=lambda length: challenge)
    with pytest.raises(WAWCryptoError):
        runtime.receive_init(browser.start())
    assert runtime.closed


def test_all_zero_32_byte_challenge_completes_handshake_and_confirmation() -> None:
    browser = BrowserCryptoProfile(ADMISSION, "13", PIN)
    runtime = RuntimeCryptoProfile(ADMISSION, "13", STATIC, random_bytes=lambda length: bytes(32))
    attest = runtime.receive_init(browser.start())
    confirm = browser.receive_attest(attest)
    ack = runtime.receive_confirm(confirm)
    browser.receive_ack(ack)
    assert browser.crypto_ready and runtime.crypto_ready
    assert runtime.decrypt_input(browser.encrypt_input(b"input")) == b"input"
    assert (
        browser.decrypt_output(runtime.encrypt_output(b"output", 1), expected_cursor=1) == b"output"
    )


def test_valid_aead_with_wrong_confirmation_plaintext_is_rejected() -> None:
    runtime = RuntimeCryptoProfile(ADMISSION, "13", STATIC)
    initiator = NXInitiator(canonical_context_bytes(derive_context(ADMISSION, "13")))
    message1 = initiator.write_message1()
    _receive, init, _owner = stage("KEY_INIT")
    init.update(
        browser_ephemeral_public_key=encode_base64url(message1),
        noise_message_1=encode_base64url(message1),
    )
    attest = runtime.receive_init(init)
    initiator.read_message2(decode_base64url(attest["noise_message_2"], 128))
    transport = initiator.take_transport()
    confirm = {
        **derive_context(ADMISSION, "13"),
        "protocol_version": 1,
        "noise_protocol": "Noise_NX_25519_AESGCM_SHA256",
        "ciphertext": encode_base64url(transport.send.encrypt(bytes(32))),
    }
    with pytest.raises(WAWCryptoError):
        runtime.receive_confirm(confirm)
    assert runtime.closed


@pytest.mark.parametrize("offset", range(44))
def test_every_immutable_header_byte_is_authenticated_or_rejected(offset: int) -> None:
    browser, runtime = ready()
    encrypted = bytearray(browser.encrypt_input(b"input"))
    encrypted[offset] ^= 1
    with pytest.raises(WAWCryptoError):
        runtime.decrypt_input(bytes(encrypted))
    assert runtime.closed
    with pytest.raises(WAWCryptoError):
        runtime.encrypt_output(b"late", 1)


@pytest.mark.parametrize(
    "scenario", ["replay", "out_of_order", "tag", "other_context", "direction"]
)
def test_bad_awce_destroys_both_directions_without_retry(scenario: str) -> None:
    browser, runtime = ready()
    first = browser.encrypt_input(b"one")
    invalid = first
    if scenario == "replay":
        runtime.decrypt_input(first)
    elif scenario == "out_of_order":
        invalid = browser.encrypt_input(b"two")
    elif scenario == "tag":
        invalid = first[:-1] + bytes([first[-1] ^ 1])
    elif scenario == "other_context":
        other = BrowserCryptoProfile({**ADMISSION, "auth_epoch": "14"}, "13", PIN)
        peer = RuntimeCryptoProfile({**ADMISSION, "auth_epoch": "14"}, "13", STATIC)
        other.receive_ack(
            peer.receive_confirm(other.receive_attest(peer.receive_init(other.start())))
        )
        invalid = other.encrypt_input(b"other")
    else:
        invalid = runtime.encrypt_output(b"wrong", 1)
    with pytest.raises(WAWCryptoError):
        runtime.decrypt_input(invalid)
    assert runtime.closed
    with pytest.raises(WAWCryptoError):
        runtime.decrypt_input(first)


@pytest.mark.parametrize(
    "method,size", [("input", 0), ("input", 16385), ("output", 0), ("output", 32769)]
)
def test_active_chunk_limits_are_smaller_than_generic_awce(method: str, size: int) -> None:
    browser, runtime = ready()
    with pytest.raises(WAWCryptoError):
        if method == "input":
            browser.encrypt_input(bytes(size))
        else:
            runtime.encrypt_output(bytes(size), 1)
    assert browser.closed if method == "input" else runtime.closed


@pytest.mark.parametrize("cursor", [0, -1, True, 1.0, MAX_OUTPUT_CURSOR + 1])
def test_output_cursor_type_and_range(cursor: Any) -> None:
    _browser, runtime = ready()
    with pytest.raises(WAWCryptoError):
        runtime.encrypt_output(b"x", cursor)
    assert runtime.closed


def test_output_cursor_exact_expectation_and_no_repeat() -> None:
    browser, runtime = ready()
    encrypted = runtime.encrypt_output(b"x", 12)
    with pytest.raises(WAWCryptoError):
        browser.decrypt_output(encrypted, expected_cursor=11)
    assert browser.closed
    with pytest.raises(WAWCryptoError):
        runtime.encrypt_output(b"x", 12)
    assert runtime.closed


def test_counter_maximum_and_exhaustion_close_both_directions() -> None:
    browser, runtime = ready()
    assert browser._transport is not None and runtime._transport is not None
    # Test-only counter seam; the public API never exposes nonce selection.
    object.__setattr__(browser._transport.send, "_CipherState__nonce", 2**64 - 2)
    object.__setattr__(runtime._transport.receive, "_CipherState__nonce", 2**64 - 2)
    encrypted = browser.encrypt_input(b"last")
    assert decode_awce(encrypted).crypto_sequence == 2**64 - 2
    assert runtime.decrypt_input(encrypted) == b"last"
    with pytest.raises(WAWCryptoError):
        browser.encrypt_input(b"exhausted")
    assert browser.closed


def test_maximum_output_cursor() -> None:
    browser, runtime = ready()
    encrypted = runtime.encrypt_output(b"last", MAX_OUTPUT_CURSOR)
    assert browser.decrypt_output(encrypted, expected_cursor=MAX_OUTPUT_CURSOR) == b"last"
    with pytest.raises(WAWCryptoError):
        runtime.encrypt_output(b"again", MAX_OUTPUT_CURSOR)


def test_fresh_reconnect_destroys_old_keys_and_rejects_old_ciphertext() -> None:
    browser1 = BrowserCryptoProfile(ADMISSION, "13", PIN)
    runtime1 = RuntimeCryptoProfile(ADMISSION, "13", STATIC)
    browser1.receive_ack(
        runtime1.receive_confirm(browser1.receive_attest(runtime1.receive_init(browser1.start())))
    )
    old_hash = browser1.transcript_context_hash
    encrypted = browser1.encrypt_input(b"old")
    browser1.destroy()
    runtime1.destroy()
    browser2 = BrowserCryptoProfile(ADMISSION, "13", PIN)
    runtime2 = RuntimeCryptoProfile(ADMISSION, "13", STATIC)
    browser2.receive_ack(
        runtime2.receive_confirm(browser2.receive_attest(runtime2.receive_init(browser2.start())))
    )
    assert browser2.transcript_context_hash != old_hash
    with pytest.raises(WAWCryptoError):
        runtime2.decrypt_input(encrypted)


def test_shared_deadline_and_late_operation_fail_closed() -> None:
    tick = [10.0]
    browser, runtime = pair(clock=lambda: tick[0], admission_started_at=8.0)
    init = browser.start()
    tick[0] = 12.99
    attest = runtime.receive_init(init)
    tick[0] = 13.0
    with pytest.raises(WAWCryptoError):
        browser.receive_attest(attest)
    assert browser.closed
    with pytest.raises(WAWCryptoError):
        runtime.check_deadline()
    assert runtime.closed


@pytest.mark.parametrize("close", [True, False])
def test_close_or_deadline_inside_rng_cannot_resurrect(close: bool) -> None:
    tick = [0.0]

    def random(length: int) -> bytes:
        if close:
            runtime.destroy()
        else:
            tick[0] = 5.0
        return CHALLENGE

    browser = BrowserCryptoProfile(ADMISSION, "13", PIN, clock=lambda: tick[0])
    runtime = RuntimeCryptoProfile(
        ADMISSION, "13", STATIC, random_bytes=random, clock=lambda: tick[0]
    )
    with pytest.raises(WAWCryptoError):
        runtime.receive_init(browser.start())
    assert runtime.closed


def test_cancelled_operation_destroys_profile() -> None:
    def interrupted(length: int) -> bytes:
        raise KeyboardInterrupt

    browser = BrowserCryptoProfile(ADMISSION, "13", PIN)
    runtime = RuntimeCryptoProfile(ADMISSION, "13", STATIC, random_bytes=interrupted)
    with pytest.raises(KeyboardInterrupt):
        runtime.receive_init(browser.start())
    assert runtime.closed


def _destroy_during_paused_operation(
    owner: BrowserCryptoProfile | RuntimeCryptoProfile,
    operation: Callable[[], object],
    entered: threading.Event,
    release: threading.Event,
) -> None:
    with ThreadPoolExecutor(max_workers=3) as pool:
        running = pool.submit(operation)
        try:
            assert entered.wait(2), "operation did not reach the deterministic pause"
            closing = pool.submit(owner.destroy)
            assert owner._closing.wait(2), "destroy did not publish its close request"
            # A separate observer must complete while both the operation and
            # resource cleanup are paused; readiness cannot depend on that lock.
            snapshot = pool.submit(lambda: (owner.closed, owner.crypto_ready))
            assert snapshot.result(timeout=2) == (True, False)
            assert not closing.done(), "cleanup must retain the operation lock"
        finally:
            release.set()
        with pytest.raises(WAWCryptoError, match="closed"):
            running.result(timeout=2)
        closing.result(timeout=2)
    assert owner.closed and not owner.crypto_ready
    assert owner._handshake is None and owner._transport is None
    assert owner.transcript_context_hash == owner.context_id == b""
    with pytest.raises(WAWCryptoError, match="closed"):
        operation()


def test_cross_thread_destroy_fences_paused_runtime_rng_before_attest() -> None:
    entered, release = threading.Event(), threading.Event()

    def paused_rng(length: int) -> bytes:
        assert length == 32
        entered.set()
        assert release.wait(5), "test did not release RNG"
        return CHALLENGE

    browser = BrowserCryptoProfile(ADMISSION, "13", PIN)
    runtime = RuntimeCryptoProfile(ADMISSION, "13", STATIC, random_bytes=paused_rng)
    init = browser.start()
    handshake = runtime._handshake
    assert isinstance(handshake, NXResponder)
    _destroy_during_paused_operation(runtime, lambda: runtime.receive_init(init), entered, release)
    with pytest.raises(NoiseNXError):
        handshake.write_message2(CHALLENGE)
    with pytest.raises(WAWCryptoError, match="closed"):
        runtime.encrypt_output(b"late", 1)
    with pytest.raises(WAWCryptoError, match="closed"):
        runtime.decrypt_input(b"late")


@pytest.mark.parametrize(
    "role,method",
    [
        ("browser", "encrypt"),
        ("browser", "decrypt"),
        ("runtime", "encrypt"),
        ("runtime", "decrypt"),
    ],
)
def test_cross_thread_destroy_discards_paused_aead_result_and_destroys_both_directions(
    role: str,
    method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser, runtime = ready()
    entered, release = threading.Event(), threading.Event()
    owner = browser if role == "browser" else runtime
    transport = owner._transport
    assert transport is not None and owner.crypto_ready
    if role == "browser":
        if method == "encrypt":
            operation = partial(browser.encrypt_input, b"discarded input")
        else:
            raw = runtime.encrypt_output(b"discarded output", 1)
            operation = partial(browser.decrypt_output, raw, expected_cursor=1)
    elif method == "encrypt":
        operation = partial(runtime.encrypt_output, b"discarded output", 1)
    else:
        raw = browser.encrypt_input(b"discarded input")
        operation = partial(runtime.decrypt_input, raw)

    class PausingAESGCM:
        def __init__(self, key: bytes) -> None:
            self._delegate = AESGCM(key)

        def _pause(self, result: bytes, current: str) -> bytes:
            if method == current:
                entered.set()
                assert release.wait(5), "test did not release AEAD"
            return result

        def encrypt(self, nonce: bytes, plaintext: bytes, associated_data: bytes) -> bytes:
            return self._pause(self._delegate.encrypt(nonce, plaintext, associated_data), "encrypt")

        def decrypt(self, nonce: bytes, ciphertext: bytes, associated_data: bytes) -> bytes:
            return self._pause(
                self._delegate.decrypt(nonce, ciphertext, associated_data), "decrypt"
            )

    monkeypatch.setattr("agentbox_protocol.noise_nx.AESGCM", PausingAESGCM)
    _destroy_during_paused_operation(owner, operation, entered, release)
    # Positive cleanup is separate from the immediately visible close request.
    # References captured before closing must also be permanently unusable.
    with pytest.raises(NoiseNXError, match="closed"):
        transport.send.encrypt(b"late")
    with pytest.raises(NoiseNXError, match="closed"):
        transport.receive.decrypt(bytes(17))
    if role == "browser":
        with pytest.raises(WAWCryptoError, match="closed"):
            browser.encrypt_input(b"late")
        with pytest.raises(WAWCryptoError, match="closed"):
            browser.decrypt_output(b"late", expected_cursor=2)
    else:
        with pytest.raises(WAWCryptoError, match="closed"):
            runtime.encrypt_output(b"late", 2)
        with pytest.raises(WAWCryptoError, match="closed"):
            runtime.decrypt_input(b"late")


def test_concurrent_encryption_serializes_counter_and_close_cannot_reopen() -> None:
    browser, runtime = ready()
    with ThreadPoolExecutor(max_workers=8) as pool:
        encrypted = list(pool.map(lambda i: browser.encrypt_input(bytes([i])), range(64)))
    envelopes = sorted(encrypted, key=lambda raw: decode_awce(raw).crypto_sequence)
    assert [decode_awce(raw).crypto_sequence for raw in envelopes] == list(range(1, 65))
    assert set(runtime.decrypt_input(raw) for raw in envelopes) == {bytes([i]) for i in range(64)}
    browser.destroy()
    assert browser.closed and not browser.crypto_ready
    assert browser.context_id == browser.transcript_context_hash == b""
    with pytest.raises(WAWCryptoError):
        browser.encrypt_input(b"late")
    assert repr(browser) == "<BrowserCryptoProfile redacted>"
    assert STATIC.hex() not in repr(runtime)


@pytest.mark.parametrize("operation", ["start", "input", "ack"])
def test_wrong_order_never_creates_crypto_ready(operation: str) -> None:
    browser, _runtime = pair()
    with pytest.raises(WAWCryptoError):
        if operation == "start":
            browser.start()
            browser.start()
        elif operation == "input":
            browser.encrypt_input(b"premature")
        else:
            browser.receive_ack({})
    assert browser.closed and not browser.crypto_ready


def raw_responder() -> tuple[BrowserCryptoProfile, Any, dict[str, str | int], bytes]:
    """Existing NX peer, without the application-profile implementation."""
    browser = BrowserCryptoProfile(ADMISSION, "13", PIN, ephemeral_private_key=EPHEMERAL_I)
    init = browser.start()
    responder = NXResponder(
        canonical_context_bytes(derive_context(ADMISSION, "13")), STATIC, EPHEMERAL_R
    )
    responder.read_message1(decode_base64url(init["noise_message_1"], 32))
    message2 = responder.write_message2(CHALLENGE)
    attest = {
        **init,
        "runtime_attestation_x25519_fingerprint": PIN,
        "runtime_ephemeral_public_key": encode_base64url(message2[:32]),
        "noise_message_2": encode_base64url(message2),
    }
    del attest["browser_ephemeral_public_key"], attest["noise_message_1"]
    confirm = browser.receive_attest(attest)
    transport = responder.take_transport()
    h = transport.handshake_hash
    # Explicit frozen formula, independent of the profile's helper/constants.
    expected = hashlib.sha256(
        b"agentbox-waw/noise-confirm/v1" + b"\0\0\0\x20" + CHALLENGE + h
    ).digest()
    assert transport.receive.decrypt(decode_base64url(confirm["ciphertext"], 48), b"") == expected
    ack = {
        **derive_context(ADMISSION, "13"),
        "protocol_version": 1,
        "noise_protocol": "Noise_NX_25519_AESGCM_SHA256",
        "status": "verified",
        "transcript_context_hash": h.hex(),
    }
    return browser, transport, ack, h


def test_confirmation_and_awce_match_independently_constructed_noise_peer() -> None:
    browser, transport, ack, h = raw_responder()
    ack["ciphertext"] = encode_base64url(
        transport.send.encrypt(hashlib.sha256(b"agentbox-waw/noise-confirm-ack/v1").digest(), b"")
    )
    browser.receive_ack(ack)
    encrypted = browser.encrypt_input(b"raw input")
    envelope = decode_awce(encrypted)
    assert envelope.crypto_sequence == 1 and envelope.context_id == h[:16]
    assert (
        transport.receive.decrypt(envelope.ciphertext, encrypted[:44] + h + b"browser-to-runtime")
        == b"raw input"
    )
    output_header = encode_awce_header(
        crypto_envelope_version=1,
        direction_id=2,
        flags=0,
        crypto_sequence=1,
        stream_cursor=8,
        context_id=h[:16],
        ciphertext_length=26,
    )
    output = output_header + transport.send.encrypt(
        b"raw output", output_header + h + b"runtime-to-browser"
    )
    assert browser.decrypt_output(output, expected_cursor=8) == b"raw output"


@pytest.mark.parametrize("bad", ["canary", "AD", "hash", "counter"])
def test_raw_peer_cannot_substitute_ack_canary_ad_hash_or_nonce(bad: str) -> None:
    browser, transport, ack, _h = raw_responder()
    if bad == "counter":
        transport.send.encrypt(b"skipped")
    ack["ciphertext"] = encode_base64url(
        transport.send.encrypt(
            bytes(32) if bad == "canary" else ACK_CANARY, b"x" if bad == "AD" else b""
        )
    )
    if bad == "hash":
        ack["transcript_context_hash"] = "f" * 64
    with pytest.raises(WAWCryptoError):
        browser.receive_ack(ack)
    assert browser.closed


@pytest.mark.parametrize("bad", ["label", "hash", "outer_header", "cursor", "nonce"])
def test_output_aad_is_exact_and_does_not_include_outer_hop(bad: str) -> None:
    browser, transport, ack, h = raw_responder()
    ack["ciphertext"] = encode_base64url(transport.send.encrypt(ACK_CANARY))
    browser.receive_ack(ack)
    header = encode_awce_header(
        crypto_envelope_version=1,
        direction_id=2,
        flags=0,
        crypto_sequence=1,
        stream_cursor=1,
        context_id=h[:16],
        ciphertext_length=17,
    )
    if bad == "label":
        aad = header + h + b"browser-to-runtime"
    elif bad == "hash":
        aad = header + h.hex().encode() + b"runtime-to-browser"
    elif bad == "outer_header":
        aad = bytes(24) + header + h + b"runtime-to-browser"
    elif bad == "cursor":
        aad = header[:23] + b"\x02" + header[24:] + h + b"runtime-to-browser"
    else:
        aad = header + h + b"runtime-to-browser"
        transport.send.encrypt(b"skip")
    ciphertext = transport.send.encrypt(b"x", aad)
    with pytest.raises(WAWCryptoError):
        browser.decrypt_output(header + ciphertext, expected_cursor=1)
    assert browser.closed


@pytest.mark.parametrize("direction,size", [(1, 16385), (2, 32769)])
def test_receive_rejects_generic_valid_but_active_oversize_before_aead(
    direction: int, size: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, runtime = ready()
    header = encode_awce_header(
        crypto_envelope_version=1,
        direction_id=direction,
        flags=0,
        crypto_sequence=1,
        stream_cursor=0 if direction == 1 else 1,
        context_id=runtime.context_id,
        ciphertext_length=size + 16,
    )
    raw = header + bytes(size + 16)
    assert decode_awce(raw).ciphertext_length == size + 16
    calls = []
    original = CipherState.decrypt

    def capture(self: CipherState, ciphertext: object, associated_data: object = b"") -> bytes:
        calls.append(True)
        return original(self, ciphertext, associated_data)

    monkeypatch.setattr(CipherState, "decrypt", capture)
    with pytest.raises(WAWCryptoError):
        if direction == 1:
            runtime.decrypt_input(raw)
        else:
            browser.decrypt_output(raw, expected_cursor=1)
    assert calls == []


def test_ack_completion_after_deadline_cannot_publish_crypto_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = [0.0]
    browser, runtime = pair(clock=lambda: tick[0])
    ack = runtime.receive_confirm(browser.receive_attest(runtime.receive_init(browser.start())))
    original = CipherState.decrypt

    def complete_late(
        self: CipherState, ciphertext: object, associated_data: object = b""
    ) -> bytes:
        result = original(self, ciphertext, associated_data)
        tick[0] = 5.0
        return result

    monkeypatch.setattr(CipherState, "decrypt", complete_late)
    with pytest.raises(WAWCryptoError):
        browser.receive_ack(ack)
    assert browser.closed and not browser.crypto_ready


@pytest.mark.parametrize("role", ["browser", "runtime"])
@pytest.mark.parametrize("outcome", ["success", "timeout", "close"])
def test_crypto_readiness_publishes_only_after_final_guard(
    role: str,
    outcome: str,
) -> None:
    entered, release = threading.Event(), threading.Event()
    target: list[BrowserCryptoProfile | RuntimeCryptoProfile | None] = [None]

    def guarded_clock() -> float:
        owner = target[0]
        if owner is not None and owner._phase == "CRYPTO_READY":
            # This is the wrapper's final guard: the inner confirmation method
            # has completed but its provisional phase must remain unobservable.
            entered.set()
            assert release.wait(5), "test did not release the final guard"
            return 5.0 if outcome == "timeout" else 0.0
        return 0.0

    browser, runtime = pair(clock=guarded_clock)
    confirm = browser.receive_attest(runtime.receive_init(browser.start()))
    operation: Callable[[], object]
    if role == "browser":
        ack = runtime.receive_confirm(confirm)
        owner: BrowserCryptoProfile | RuntimeCryptoProfile = browser
        operation = partial(browser.receive_ack, ack)
    else:
        owner = runtime
        operation = partial(runtime.receive_confirm, confirm)
    target[0] = owner

    def is_ready() -> bool:
        # The value can change in another thread; avoid static property narrowing.
        return owner.crypto_ready

    assert not is_ready() and not owner._published_ready.is_set()

    if outcome == "close":
        _destroy_during_paused_operation(owner, operation, entered, release)
        assert not owner._published_ready.is_set()
        return

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(operation)
        try:
            assert entered.wait(2), "operation did not reach the final guard"
            assert not running.done()
            snapshot = pool.submit(lambda: (owner.closed, owner.crypto_ready))
            assert snapshot.result(timeout=2) == (False, False)
            assert not owner._published_ready.is_set()
        finally:
            release.set()
        if outcome == "timeout":
            with pytest.raises(WAWCryptoError, match="deadline"):
                running.result(timeout=2)
            assert owner.closed and not is_ready()
            assert not owner._published_ready.is_set()
        else:
            running.result(timeout=2)
            assert is_ready() and owner._published_ready.is_set()
            owner.destroy()
            assert owner.closed and not is_ready()
            assert not owner._published_ready.is_set()


@pytest.mark.parametrize("bad_tick", [-1.0, float("nan"), float("inf"), True])
def test_bad_clock_closes_pending_profile(bad_tick: float) -> None:
    tick = [0.0]
    browser, _runtime = pair(clock=lambda: tick[0])
    tick[0] = bad_tick
    with pytest.raises(WAWCryptoError):
        browser.check_deadline()
    assert browser.closed


def test_profile_matches_independent_primitive_trace_vector() -> None:
    fixtures = Path(__file__).parents[1] / "fixtures"
    vector = json.loads((fixtures / "waw_crypto/profile-v1.json").read_text())
    noise = json.loads((fixtures / "noise_nx/noise-c-nx-aesgcm-sha256.json").read_text())
    browser = BrowserCryptoProfile(
        vector["admission"],
        vector["runtime_epoch"],
        vector["runtime_fingerprint"],
        ephemeral_private_key=bytes.fromhex(noise["init_ephemeral"]),
    )
    runtime = RuntimeCryptoProfile(
        vector["admission"],
        vector["runtime_epoch"],
        bytes.fromhex(noise["resp_static"]),
        ephemeral_private_key=bytes.fromhex(noise["resp_ephemeral"]),
        random_bytes=lambda length: bytes.fromhex(vector["challenge"]),
    )
    canonical = canonical_context_bytes(
        derive_context(vector["admission"], vector["runtime_epoch"])
    )
    assert canonical == vector["canonical_context_utf8"].encode()
    assert hashlib.sha256(canonical).hexdigest() == vector["canonical_context_sha256"]
    init = browser.start()
    assert decode_base64url(init["noise_message_1"], 32).hex() == vector["noise_message_1"]
    attest = runtime.receive_init(init)
    assert decode_base64url(attest["noise_message_2"], 128).hex() == vector["noise_message_2"]
    confirm = browser.receive_attest(attest)
    assert decode_base64url(confirm["ciphertext"], 48).hex() == vector["key_confirm_ciphertext"]
    ack = runtime.receive_confirm(confirm)
    assert decode_base64url(ack["ciphertext"], 48).hex() == vector["key_confirm_ack_ciphertext"]
    browser.receive_ack(ack)
    assert browser.transcript_context_hash.hex() == vector["transcript_context_hash"]
    assert browser.context_id.hex() == vector["context_id"]
    input_bytes = bytes.fromhex(vector["input_plaintext"])
    input_envelope = browser.encrypt_input(input_bytes)
    assert input_envelope.hex() == vector["input_awce"]
    assert runtime.decrypt_input(input_envelope) == input_bytes
    output_bytes = bytes.fromhex(vector["output_plaintext"])
    cursor = int(vector["output_cursor"])
    output_envelope = runtime.encrypt_output(output_bytes, cursor)
    assert output_envelope.hex() == vector["output_awce"]
    assert browser.decrypt_output(output_envelope, expected_cursor=cursor) == output_bytes
