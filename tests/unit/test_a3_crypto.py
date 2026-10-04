"""Real A3 encryption with synthetic keys; no production trust/key authority."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from agentbox_protocol.a3_content import ContentError, application_aad, prepare_pages
from agentbox_protocol.a3_crypto import A3Browser, A3Runtime, decode_key, decode_record

VECTOR = json.loads((Path(__file__).parents[1] / "fixtures/a3_content/crypto-v1.json").read_bytes())
C = VECTOR["context"]


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def pair(
    now: list[int] | None = None, current: list[Any] | None = None, pin: list[str] | None = None
) -> tuple[A3Browser, A3Runtime]:
    now = now if now is not None else [0]
    current = current if current is not None else [C]
    pin = pin if pin is not None else [VECTOR["runtime_fingerprint"]]
    browser = A3Browser(
        C,
        expected_pin=lambda: pin[0],
        ephemeral_private_key=bytes.fromhex(VECTOR["init_ephemeral"]),
        clock_ms=lambda: now[0],
        current=lambda: current[0],
        deadline_ms=30000,
    )
    runtime = A3Runtime(
        C,
        bytes.fromhex(VECTOR["resp_static"]),
        ephemeral_private_key=bytes.fromhex(VECTOR["resp_ephemeral"]),
        random_bytes=lambda n: bytes.fromhex(VECTOR["challenge"]),
        clock_ms=lambda: now[0],
        current=lambda: current[0],
        deadline_ms=30000,
    )
    return browser, runtime


def ready(browser: A3Browser, runtime: A3Runtime) -> list[bytes]:
    initial = browser.start()
    attest = runtime.receive_init(initial)
    confirm = browser.receive_attest(attest)
    assert (browser.crypto_ready, runtime.crypto_ready) == (False, False)
    ack = runtime.receive_confirm(confirm)
    assert (runtime.crypto_ready, browser.crypto_ready) == (True, False)
    browser.receive_ack(ack)
    assert browser.crypto_ready
    return [initial, attest, confirm, ack]


def read(browser: A3Browser, runtime: A3Runtime) -> bytes:
    request = browser.encrypt_read(VECTOR["plaintexts"][0].encode())
    assert runtime.receive_read(request) == VECTOR["plaintexts"][0].encode()
    return request


def test_independent_literal_every_key_record_and_complete_encrypted_read() -> None:
    browser, runtime = pair()
    assert ready(browser, runtime) == [x.encode() for x in VECTOR["key_frames"]]
    assert read(browser, runtime) == VECTOR["records"][0].encode()
    page = runtime.encrypt_record(VECTOR["plaintexts"][1].encode())
    assert page == VECTOR["records"][1].encode()
    assert browser.receive_record(page) is None
    end = runtime.encrypt_record(VECTOR["plaintexts"][2].encode())
    assert end == VECTOR["records"][2].encode()
    assert browser.receive_record(end) == bytes.fromhex(VECTOR["patch_hex"])
    assert not browser.crypto_ready
    with pytest.raises(ContentError):
        browser.receive_record(end)


@pytest.mark.parametrize("step", ["init", "attest", "confirm", "ack", "read", "page", "end"])
def test_tamper_always_closes_without_plaintext(step: str) -> None:
    browser, runtime = pair()
    wire = browser.start()
    pipeline = [
        runtime.receive_init,
        browser.receive_attest,
        runtime.receive_confirm,
        browser.receive_ack,
    ]
    steps = ["init", "attest", "confirm", "ack"]
    for name, operation in zip(steps, pipeline, strict=True):
        if step == name:
            value = json.loads(wire)
            value["data"] = ("A" if value["data"][0] != "A" else "B") + value["data"][1:]
            with pytest.raises(ContentError):
                if name == "init":
                    # NX message1 is unauthenticated until the responder proves the transcript.
                    browser.receive_attest(runtime.receive_init(canonical(value)))
                else:
                    operation(canonical(value))
            assert not (runtime if name == "confirm" else browser).crypto_ready
            return
        wire = operation(wire)  # type: ignore[assignment]
    request = browser.encrypt_read(VECTOR["plaintexts"][0].encode())
    if step == "read":
        value = json.loads(request)
        value["context_digest"] = "f" * 64
        with pytest.raises(ContentError):
            runtime.receive_read(canonical(value))
        return
    runtime.receive_read(request)
    page = runtime.encrypt_record(VECTOR["plaintexts"][1].encode())
    if step == "end":
        assert browser.receive_record(page) is None
        page = runtime.encrypt_record(VECTOR["plaintexts"][2].encode())
    value = json.loads(page)
    value["ciphertext"] = ("A" if value["ciphertext"][0] != "A" else "B") + value["ciphertext"][1:]
    with pytest.raises(ContentError):
        browser.receive_record(canonical(value))
    assert not browser.crypto_ready


@pytest.mark.parametrize(
    "change",
    ["project_id", "runtime_epoch", "session_scope", "request_nonce", "selector_commitment"],
)
def test_currentness_loss_is_permanent(change: str) -> None:
    current: list[Any] = [dict(C)]
    browser, runtime = pair(current=current)
    ready(browser, runtime)
    current[0][change] = "2" if change == "runtime_epoch" else "f" * 64
    with pytest.raises(ContentError):
        browser.check()
    current[0] = C
    with pytest.raises(ContentError):
        browser.check()


@pytest.mark.parametrize("when", [4999, 5000, 5001, 30000])
def test_exact_handshake_expiry(when: int) -> None:
    now = [0]
    browser, runtime = pair(now=now)
    initial = browser.start()
    now[0] = when
    if when < 5000:
        browser.receive_ack(
            runtime.receive_confirm(browser.receive_attest(runtime.receive_init(initial)))
        )
    else:
        with pytest.raises(ContentError):
            runtime.receive_init(initial)


def test_read_expiry_and_pin_drift_close() -> None:
    now = [0]
    pin = [VECTOR["runtime_fingerprint"]]
    browser, runtime = pair(now=now, pin=pin)
    ready(browser, runtime)
    read(browser, runtime)
    pin[0] = "0" * 64
    with pytest.raises(ContentError):
        browser.check()
    now[0] = 30000
    with pytest.raises(ContentError):
        runtime.encrypt_record(VECTOR["plaintexts"][1].encode())


def test_wrong_pin_and_ack_advertised_hash() -> None:
    browser, runtime = pair(pin=["0" * 64])
    with pytest.raises(ContentError):
        browser.receive_attest(runtime.receive_init(browser.start()))
    browser, runtime = pair()
    confirm = browser.receive_attest(runtime.receive_init(browser.start()))
    ack = json.loads(runtime.receive_confirm(confirm))
    ack["transcript_hash"] = "0" * 64
    with pytest.raises(ContentError):
        browser.receive_ack(canonical(ack))


@pytest.mark.parametrize("kind", ["replay", "lost_page", "wrong_inner"])
def test_valid_crypto_cannot_publish_incomplete_or_inconsistent_content(kind: str) -> None:
    browser, runtime = pair()
    ready(browser, runtime)
    read(browser, runtime)
    page = runtime.encrypt_record(VECTOR["plaintexts"][1].encode())
    end = runtime.encrypt_record(VECTOR["plaintexts"][2].encode())
    if kind == "replay":
        assert browser.receive_record(page) is None
        bad = page
    elif kind == "lost_page":
        bad = end
    else:
        # A malicious authenticated peer: envelope PAGE, inner context nonce changed.
        browser, runtime = pair()
        ready(browser, runtime)
        read(browser, runtime)
        inner = json.loads(VECTOR["plaintexts"][1])
        inner["request_nonce"] = "f" * 64
        assert runtime._transport is not None
        encrypted = runtime._transport.send.encrypt(
            canonical(inner), application_aad(C, VECTOR["final_hash"], "PATCH_PAGE", 0)
        )
        value = json.loads(VECTOR["records"][1])
        value["ciphertext"] = base64.urlsafe_b64encode(encrypted).decode().rstrip("=")
        bad = canonical(value)
    with pytest.raises(ContentError):
        browser.receive_record(bad)
    with pytest.raises(ContentError):
        browser.receive_record(end)


@pytest.mark.parametrize(
    "invalid", [b"", b"x" * 24577, b'{"nested":{}}', b"{}\n", b'{"a":1,"a":1}', b'{"a":1e3}']
)
def test_strict_bounded_opaque_parsers(invalid: bytes) -> None:
    for decode in (decode_key, decode_record):
        with pytest.raises(ContentError):
            decode(invalid)


def test_exact_max_outer_byte_proof_and_capacity_preflight() -> None:
    # Longest allowed kind, two-digit sequence, full max PAGE+tag and fixed context.
    raw = canonical(
        {
            "domain": "agentbox-a3-content/record/v1",
            "context_digest": "f" * 64,
            "kind": "PATCH_PAGE",
            "sequence": 15,
            "ciphertext": base64.urlsafe_b64encode(b"x" * 16400).decode().rstrip("="),
        }
    )
    assert len(json.loads(raw)["ciphertext"]) == 21867
    assert len(raw) == 22043
    decode_record(raw)
    # Longest kind (PATCH_ERROR) uses sequence0, so it has the same overhead.
    assert (
        len(raw.replace(b"PATCH_PAGE", b"PATCH_ERROR").replace(b'"sequence":15', b'"sequence":0'))
        == 22043
    )
    browser, runtime = pair()
    ready(browser, runtime)
    read(browser, runtime)
    pages = prepare_pages(C, b"x" * 191504, "1791111111111")
    assert len(pages) == 17
    result = None
    for page in pages:
        encrypted = runtime.encrypt_record(page)
        assert len(encrypted) <= 22043
        result = browser.receive_record(encrypted)
    assert result == b"x" * 191504
    with pytest.raises(ContentError, match="PATCH_TOO_LARGE"):
        prepare_pages(C, b"x" * 191505, "1791111111111")


def test_encrypted_error_is_terminal_and_never_returns_patch() -> None:
    browser, runtime = pair()
    ready(browser, runtime)
    read(browser, runtime)
    error = canonical(
        {
            "protocol_id": "agentbox-a3-content/v1",
            "protocol_version": 1,
            "context_digest": json.loads(VECTOR["plaintexts"][0])["context_digest"],
            "request_nonce": C["request_nonce"],
            "kind": "PATCH_ERROR",
            "code": "PATCH_STALE",
        }
    )
    encrypted = runtime.encrypt_record(error)
    assert decode_record(encrypted)["kind"] == "PATCH_ERROR"
    with pytest.raises(ContentError, match="PATCH_STALE"):
        browser.receive_record(encrypted)
    with pytest.raises(ContentError):
        runtime.encrypt_record(error)


@pytest.mark.parametrize("length", [100, 4301, 10000])
def test_huge_integer_parsing_never_exposes_untrusted_values(length: int) -> None:
    for decode in (decode_key, decode_record):
        with pytest.raises(ContentError) as error:
            decode(b'{"sequence":' + b"9" * length + b"}")
        assert str(error.value) == "PATCH_PROTOCOL_INVALID"
