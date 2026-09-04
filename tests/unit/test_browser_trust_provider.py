from __future__ import annotations

import base64
import hashlib
import io
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import agentbox_browser_trust.records as trust_records
import pytest
from agentbox_browser_trust.codec import (
    TrustCodecError,
    b64url_encode,
    canonical_json,
    read_frame,
    read_native_message,
    strict_json,
    write_frame,
    write_native_message,
)
from agentbox_browser_trust.native_host import bridge
from agentbox_browser_trust.packaging import (
    BrowserTrustPackageError,
    build_client_bundle,
    chrome_extension_id,
)
from agentbox_browser_trust.protocol import TrustProtocolError, TrustProtocolSession
from agentbox_browser_trust.records import TrustRecordError, canonical_origin, validate_enrollment
from agentbox_browser_trust.store import (
    BrowserTrustStore,
    BrowserTrustStoreError,
    verify_origin_network,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/waw_trust/public-v1.json"
VALID_TIME = datetime(2030, 1, 15, tzinfo=UTC)


class _Duplex:
    def __init__(self, incoming: bytes = b"") -> None:
        self.incoming = io.BytesIO(incoming)
        self.outgoing = io.BytesIO()

    def read(self, size: int = -1, /) -> bytes:
        return self.incoming.read(size)

    def write(self, value: bytes, /) -> int:
        return self.outgoing.write(value)

    def flush(self) -> None:
        return None


class _Chunked(_Duplex):
    def read(self, size: int = -1, /) -> bytes:
        return self.incoming.read(min(1, size))

    def write(self, value: bytes, /) -> int:
        return self.outgoing.write(value[:2])


def _records() -> tuple[bytes, bytes, bytes]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bootstrap = canonical_json(fixture["bootstrap"], limit=4096)
    root = canonical_json(fixture["records"][1]["record"], limit=4096)
    pin = canonical_json(fixture["records"][0]["record"], limit=4096)
    return bootstrap, root, pin


def _candidate() -> bytes:
    bootstrap, root, pin = _records()
    return canonical_json(
        {
            "schema_version": "waw-trust-enrollment-v1",
            "bootstrap_record": b64url_encode(bootstrap),
            "root_records": [b64url_encode(root)],
            "pin_record": b64url_encode(pin),
            "network_policy": "production",
        }
    )


def test_native_codec_is_canonical_bounded_and_little_endian() -> None:
    message = {"protocol_version": 1, "type": "PING"}
    stream = io.BytesIO()
    write_native_message(stream, message)
    raw = stream.getvalue()
    assert raw[:4] == len(raw[4:]).to_bytes(4, "little")
    assert read_native_message(io.BytesIO(raw)) == message
    with pytest.raises(TrustCodecError):
        strict_json(b'{"type":"PING", "protocol_version":1}')
    with pytest.raises(TrustCodecError):
        strict_json(b'{"type":"PING","type":"PING"}')
    chunked = _Chunked()
    write_native_message(chunked, message)
    chunked.incoming = io.BytesIO(chunked.outgoing.getvalue())
    assert read_native_message(chunked) == message


def test_public_record_chain_and_origin_match_frozen_fixture() -> None:
    bootstrap, root, pin = _records()
    value = validate_enrollment(bootstrap, (root,), pin, now=VALID_TIME)
    assert value.root_revision == 1
    assert value.pin_revision == 7
    assert value.origin == "https://example.agentbox.test"
    assert value.root_active
    assert canonical_origin("https://[2001:db8::1]:8443") == "https://[2001:db8::1]:8443"
    for invalid in (
        "https://[::ffff:192.0.2.1]:8443",
        "https://EXAMPLE.agentbox.test",
        "https://example.agentbox.test:443",
        "http://example.agentbox.test",
    ):
        with pytest.raises(TrustRecordError):
            canonical_origin(invalid)


def test_record_validation_rejects_time_signature_and_floor_mutations() -> None:
    bootstrap, root, pin = _records()
    with pytest.raises(TrustRecordError):
        validate_enrollment(bootstrap, (root,), pin, now=datetime(2026, 1, 1, tzinfo=UTC))
    changed = dict(cast(dict[str, object], strict_json(pin, limit=4096)))
    changed["pin_revision"] = 8
    with pytest.raises(TrustRecordError):
        validate_enrollment(
            bootstrap,
            (root,),
            canonical_json(changed, limit=4096),
            now=VALID_TIME,
        )
    with pytest.raises(TrustRecordError):
        validate_enrollment(
            bootstrap,
            (root,),
            pin,
            now=VALID_TIME,
            minimum_pin_revision=8,
        )


def test_store_persists_floors_time_and_provider_session_identity(tmp_path: Path) -> None:
    now = [VALID_TIME]
    store = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: now[0],
        network_verifier=lambda _origin, _policy: True,
    )
    fingerprint = store.initialize()
    assert len(fingerprint) == 64
    state = store.install(_candidate())
    assert state.enrollment.pin_revision == 7
    first = store.snapshot()
    assert first["provider_epoch"] == state.value["provider_epoch"]
    assert first["trusted_time"] == {
        "utc": "2030-01-15T00:00:00.000Z",
        "non_backward": True,
    }
    signature = store.sign_session({"document_id": "doc", "origin": state.enrollment.origin})
    assert len(signature) == 86

    now[0] += timedelta(seconds=1)
    journal = store.journal_path.read_bytes()
    second = store.snapshot()
    assert second["provider_epoch"] == first["provider_epoch"]
    assert second["trusted_time"] != first["trusted_time"]
    assert store.journal_path.read_bytes() == journal
    assert store.time_path.stat().st_size <= 4096
    reopened = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: now[0],
        network_verifier=lambda _origin, _policy: True,
    )
    assert reopened.snapshot() == second

    now[0] -= timedelta(seconds=2)
    with pytest.raises(BrowserTrustStoreError):
        reopened.snapshot()
    with pytest.raises(BrowserTrustStoreError):
        store.install(_candidate())


def test_store_detects_installation_key_loss_during_active_snapshots(tmp_path: Path) -> None:
    store = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: VALID_TIME,
        network_verifier=lambda _origin, _policy: True,
    )
    store.initialize()
    store.install(_candidate())
    store.key_path.unlink()
    with pytest.raises(BrowserTrustStoreError):
        store.snapshot()


def test_checkpoint_preserves_a_verified_expired_ancestor_across_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkpoint is durable evidence, never an import-supplied trust shortcut."""

    def public(key: ed25519.Ed25519PrivateKey) -> str:
        return b64url_encode(
            key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        )

    def signed(domain: bytes, body: dict[str, object], key: ed25519.Ed25519PrivateKey) -> bytes:
        unsigned = {name: value for name, value in body.items() if name != "signature"}
        return canonical_json(
            {
                **unsigned,
                "signature": b64url_encode(key.sign(domain + b"\0" + canonical_json(unsigned))),
            }
        )

    bootstrap_key = ed25519.Ed25519PrivateKey.generate()
    root_one_key = ed25519.Ed25519PrivateKey.generate()
    root_two_key = ed25519.Ed25519PrivateKey.generate()
    bootstrap = canonical_json(
        {
            "schema_version": "waw-runtime-bootstrap-v1",
            "key_id": "bootstrap-2029",
            "public_key": public(bootstrap_key),
        }
    )
    monkeypatch.setattr(trust_records, "BOOTSTRAP_PUBLIC_KEY", public(bootstrap_key))
    monkeypatch.setattr(
        trust_records, "BOOTSTRAP_POLICY_SHA256", hashlib.sha256(bootstrap).hexdigest()
    )
    root_one = signed(
        b"agentbox-waw/runtime-root/v1",
        {
            "schema_version": "waw-runtime-root-v1",
            "root_revision": 1,
            "key_id": "checkpoint-root-1",
            "public_key": public(root_one_key),
            "signer_key_id": "bootstrap-2029",
            "state": "ACTIVE",
            "valid_from": "2030-01-01T00:00:00.000Z",
            "valid_until": "2034-12-31T00:00:00.000Z",
            "revoked_at": None,
            "supersedes_key_id": None,
            "signature_algorithm": "Ed25519",
            "signature": "",
        },
        bootstrap_key,
    )
    root_two = signed(
        b"agentbox-waw/runtime-root/v1",
        {
            "schema_version": "waw-runtime-root-v1",
            "root_revision": 2,
            "key_id": "checkpoint-root-2",
            "public_key": public(root_two_key),
            "signer_key_id": "checkpoint-root-1",
            "state": "ACTIVE",
            "valid_from": "2034-01-01T00:00:00.000Z",
            "valid_until": "2036-12-31T00:00:00.000Z",
            "revoked_at": None,
            "supersedes_key_id": "checkpoint-root-1",
            "signature_algorithm": "Ed25519",
            "signature": "",
        },
        root_one_key,
    )
    pin = signed(
        b"agentbox-waw/runtime-pin/v1",
        {
            "schema_version": "waw-runtime-pin.v1",
            "repository": "ForceMind/agentbox",
            "origin": "https://example.agentbox.test",
            "pin_revision": 1,
            "runtime_host_installation_id": "wri_0123456789abcdef0123456789abcdef",
            "runtime_host_installation_revision": 1,
            "runtime_attestation_x25519_fingerprint": "a" * 64,
            "valid_from": "2034-01-01T00:00:00.000Z",
            "valid_until": "2036-01-01T00:00:00.000Z",
            "revoked_at": None,
            "supersedes_fingerprint": None,
            "signature_algorithm": "Ed25519",
            "key_id": "checkpoint-root-2",
            "signature": "",
        },
        root_two_key,
    )
    skipped_first_root = signed(
        b"agentbox-waw/runtime-root/v1",
        {
            "schema_version": "waw-runtime-root-v1",
            "root_revision": 2,
            "key_id": "skipped-root",
            "public_key": public(ed25519.Ed25519PrivateKey.generate()),
            "signer_key_id": "bootstrap-2029",
            "state": "ACTIVE",
            "valid_from": "2030-01-01T00:00:00.000Z",
            "valid_until": "2036-12-31T00:00:00.000Z",
            "revoked_at": None,
            "supersedes_key_id": None,
            "signature_algorithm": "Ed25519",
            "signature": "",
        },
        bootstrap_key,
    )
    with pytest.raises(TrustRecordError):
        validate_enrollment(
            bootstrap, (skipped_first_root,), pin, now=datetime(2034, 6, 1, tzinfo=UTC)
        )
    candidate = canonical_json(
        {
            "schema_version": "waw-trust-enrollment-v1",
            "bootstrap_record": b64url_encode(bootstrap),
            "root_records": [b64url_encode(root_one), b64url_encode(root_two)],
            "pin_record": b64url_encode(pin),
            "network_policy": "production",
        }
    )
    now = [datetime(2034, 6, 1, tzinfo=UTC)]
    store = BrowserTrustStore(
        tmp_path / "trust", clock=lambda: now[0], network_verifier=lambda _origin, _policy: True
    )
    store.initialize()
    store.install(candidate)
    checkpoint = store.snapshot()["authenticated_checkpoint"]
    assert isinstance(checkpoint, dict) and checkpoint["root_revision"] == 2

    now[0] = datetime(2035, 1, 1, 0, 5, 1, tzinfo=UTC)
    restarted = BrowserTrustStore(
        tmp_path / "trust", clock=lambda: now[0], network_verifier=lambda _origin, _policy: True
    )
    resumed = restarted.snapshot()
    assert resumed["authenticated_checkpoint"] == checkpoint
    with pytest.raises(TrustRecordError):
        validate_enrollment(bootstrap, (root_one, root_two), pin, now=now[0])
    assert (
        validate_enrollment(
            bootstrap,
            (root_one, root_two),
            pin,
            now=now[0],
            authenticated_checkpoint=checkpoint,
            retired_root_key_ids=frozenset({"checkpoint-root-1"}),
        ).root_revision
        == 2
    )

    root_three_key = ed25519.Ed25519PrivateKey.generate()
    root_three = signed(
        b"agentbox-waw/runtime-root/v1",
        {
            "schema_version": "waw-runtime-root-v1",
            "root_revision": 3,
            "key_id": "checkpoint-root-3",
            "public_key": public(root_three_key),
            "signer_key_id": "checkpoint-root-2",
            "state": "ACTIVE",
            "valid_from": "2036-01-01T00:00:00.000Z",
            "valid_until": "2038-12-31T00:00:00.000Z",
            "revoked_at": None,
            "supersedes_key_id": "checkpoint-root-2",
            "signature_algorithm": "Ed25519",
            "signature": "",
        },
        root_two_key,
    )
    now[0] = datetime(2036, 1, 1, 0, 0, 1, tzinfo=UTC)
    pin_two = signed(
        b"agentbox-waw/runtime-pin/v1",
        {
            "schema_version": "waw-runtime-pin.v1",
            "repository": "ForceMind/agentbox",
            "origin": "https://example.agentbox.test",
            "pin_revision": 2,
            "runtime_host_installation_id": "wri_0123456789abcdef0123456789abcdef",
            "runtime_host_installation_revision": 1,
            "runtime_attestation_x25519_fingerprint": "b" * 64,
            "valid_from": "2036-01-01T00:00:00.001Z",
            "valid_until": "2037-01-01T00:00:00.000Z",
            "revoked_at": None,
            "supersedes_fingerprint": "a" * 64,
            "signature_algorithm": "Ed25519",
            "key_id": "checkpoint-root-3",
            "signature": "",
        },
        root_three_key,
    )
    candidate_three = canonical_json(
        {
            "schema_version": "waw-trust-enrollment-v1",
            "bootstrap_record": b64url_encode(bootstrap),
            "root_records": [
                b64url_encode(root_one),
                b64url_encode(root_two),
                b64url_encode(root_three),
            ],
            "pin_record": b64url_encode(pin_two),
            "network_policy": "production",
        }
    )
    batch_revocation = signed(
        b"agentbox-waw/runtime-root/v1",
        {
            "schema_version": "waw-runtime-root-v1",
            "root_revision": 4,
            "key_id": "checkpoint-root-3",
            "public_key": public(root_three_key),
            "signer_key_id": "bootstrap-2029",
            "state": "REVOKED",
            "valid_from": "2036-01-01T00:00:00.000Z",
            "valid_until": "2038-12-31T00:00:00.000Z",
            "revoked_at": "2036-01-01T00:00:00.001Z",
            "supersedes_key_id": "checkpoint-root-3",
            "signature_algorithm": "Ed25519",
            "signature": "",
        },
        bootstrap_key,
    )
    batch_candidate = canonical_json(
        {
            "schema_version": "waw-trust-enrollment-v1",
            "bootstrap_record": b64url_encode(bootstrap),
            "root_records": [
                b64url_encode(root_one),
                b64url_encode(root_two),
                b64url_encode(root_three),
                b64url_encode(batch_revocation),
            ],
            "pin_record": b64url_encode(pin_two),
            "network_policy": "production",
        }
    )
    before = (
        restarted.state_path.read_bytes(),
        restarted.journal_path.read_bytes(),
        restarted.time_path.read_bytes(),
    )
    with pytest.raises(BrowserTrustStoreError):
        restarted.install(batch_candidate)
    assert before == (
        restarted.state_path.read_bytes(),
        restarted.journal_path.read_bytes(),
        restarted.time_path.read_bytes(),
    )
    assert (
        BrowserTrustStore(
            tmp_path / "trust", clock=lambda: now[0], network_verifier=lambda _origin, _policy: True
        ).snapshot()["authenticated_checkpoint"]
        == checkpoint
    )
    restarted.install(candidate_three)
    checkpoint_three = restarted.snapshot()["authenticated_checkpoint"]
    assert isinstance(checkpoint_three, dict) and checkpoint_three["root_revision"] == 3

    now[0] = datetime(2037, 1, 1, 0, 0, 1, tzinfo=UTC)
    pin_three = signed(
        b"agentbox-waw/runtime-pin/v1",
        {
            "schema_version": "waw-runtime-pin.v1",
            "repository": "ForceMind/agentbox",
            "origin": "https://example.agentbox.test",
            "pin_revision": 3,
            "runtime_host_installation_id": "wri_0123456789abcdef0123456789abcdef",
            "runtime_host_installation_revision": 1,
            "runtime_attestation_x25519_fingerprint": "c" * 64,
            "valid_from": "2037-01-01T00:00:00.001Z",
            "valid_until": "2038-01-01T00:00:00.000Z",
            "revoked_at": None,
            "supersedes_fingerprint": "b" * 64,
            "signature_algorithm": "Ed25519",
            "key_id": "checkpoint-root-3",
            "signature": "",
        },
        root_three_key,
    )
    candidate_pin_only = canonical_json(
        {
            "schema_version": "waw-trust-enrollment-v1",
            "bootstrap_record": b64url_encode(bootstrap),
            "root_records": [
                b64url_encode(root_one),
                b64url_encode(root_two),
                b64url_encode(root_three),
            ],
            "pin_record": b64url_encode(pin_three),
            "network_policy": "production",
        }
    )
    restarted.install(candidate_pin_only)
    assert restarted.snapshot()["authenticated_checkpoint"] == checkpoint_three
    final_restart = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: now[0] + timedelta(seconds=301),
        network_verifier=lambda _origin, _policy: True,
    )
    assert final_restart.snapshot()["authenticated_checkpoint"] == checkpoint_three

    revoked_root = signed(
        b"agentbox-waw/runtime-root/v1",
        {
            "schema_version": "waw-runtime-root-v1",
            "root_revision": 4,
            "key_id": "checkpoint-root-3",
            "public_key": public(root_three_key),
            "signer_key_id": "bootstrap-2029",
            "state": "REVOKED",
            "valid_from": "2036-01-01T00:00:00.000Z",
            "valid_until": "2038-12-31T00:00:00.000Z",
            "revoked_at": "2037-01-01T00:00:00.001Z",
            "supersedes_key_id": "checkpoint-root-3",
            "signature_algorithm": "Ed25519",
            "signature": "",
        },
        bootstrap_key,
    )
    revoked_pin = signed(
        b"agentbox-waw/runtime-pin/v1",
        {
            "schema_version": "waw-runtime-pin.v1",
            "repository": "ForceMind/agentbox",
            "origin": "https://example.agentbox.test",
            "pin_revision": 4,
            "runtime_host_installation_id": "wri_0123456789abcdef0123456789abcdef",
            "runtime_host_installation_revision": 1,
            "runtime_attestation_x25519_fingerprint": "c" * 64,
            "valid_from": "2037-01-01T00:00:00.001Z",
            "valid_until": "2038-01-01T00:00:00.000Z",
            "revoked_at": "2037-01-01T00:00:00.001Z",
            "supersedes_fingerprint": "c" * 64,
            "signature_algorithm": "Ed25519",
            "key_id": "checkpoint-root-3",
            "signature": "",
        },
        root_three_key,
    )
    revoked_candidate = canonical_json(
        {
            "schema_version": "waw-trust-enrollment-v1",
            "bootstrap_record": b64url_encode(bootstrap),
            "root_records": [
                b64url_encode(root_one),
                b64url_encode(root_two),
                b64url_encode(root_three),
                b64url_encode(revoked_root),
            ],
            "pin_record": b64url_encode(revoked_pin),
            "network_policy": "production",
        }
    )
    revoked = final_restart.install(revoked_candidate)
    assert not revoked.enrollment.root_active
    assert final_restart.snapshot()["authenticated_checkpoint"] == checkpoint_three
    terminal_restart = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: now[0] + timedelta(seconds=302),
        network_verifier=lambda _origin, _policy: True,
    )
    assert not terminal_restart._load_required().enrollment.root_active
    assert terminal_restart.snapshot()["authenticated_checkpoint"] == checkpoint_three

    original_state = terminal_restart.state_path.read_bytes()
    for mutation in (
        "checkpoint-drop",
        "checkpoint-digest",
        "checkpoint-accepted-at",
        "retired-missing",
        "retired-extra",
        "revoked-missing",
        "revoked-extra",
    ):
        altered = json.loads(original_state)
        if mutation == "checkpoint-drop":
            altered["authenticated_checkpoint"] = None
        elif mutation == "checkpoint-digest":
            cast(dict[str, object], altered["authenticated_checkpoint"])["root_history_sha256"] = (
                "0" * 64
            )
        elif mutation == "checkpoint-accepted-at":
            cast(dict[str, object], altered["authenticated_checkpoint"])[
                "accepted_at"
            ] = "2038-01-01T00:00:00.000Z"
        elif mutation == "retired-missing":
            altered["retired_root_key_ids"] = ["checkpoint-root-1"]
        elif mutation == "retired-extra":
            altered["retired_root_key_ids"] = ["extra-root"]
        elif mutation == "revoked-missing":
            altered["revoked_root_key_ids"] = []
        else:
            altered["revoked_root_key_ids"] = ["extra-root"]
        terminal_restart.state_path.write_bytes(canonical_json(altered))
        with pytest.raises(BrowserTrustStoreError):
            BrowserTrustStore(
                tmp_path / "trust",
                clock=lambda: now[0] + timedelta(seconds=302),
                network_verifier=lambda _origin, _policy: True,
            ).snapshot()
    terminal_restart.state_path.write_bytes(original_state)


def test_hung_network_verifier_does_not_hold_store_or_process_lock(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def blocked(_origin: str, _policy: str) -> bool:
        entered.set()
        release.wait(2)
        return True

    store = BrowserTrustStore(
        tmp_path / "trust", clock=lambda: VALID_TIME, network_verifier=blocked
    )
    store.initialize()
    errors: list[BaseException] = []

    def install() -> None:
        try:
            store.install(_candidate())
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=install)
    worker.start()
    assert entered.wait(1)
    started = time.monotonic()
    assert len(store.installation_fingerprint()) == 64
    assert time.monotonic() - started < 0.5
    release.set()
    worker.join(2)
    assert not worker.is_alive() and not errors
    store.close()


def test_loopback_policy_requires_a_literal_loopback_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentbox_browser_trust.store.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    assert verify_origin_network("https://127.0.0.1:8443", "loopback-development")
    assert not verify_origin_network("https://localhost:8443", "loopback-development")


def test_store_rejects_journal_or_state_rollback_and_unsafe_modes(tmp_path: Path) -> None:
    store = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: VALID_TIME,
        network_verifier=lambda _origin, _policy: True,
    )
    store.initialize()
    store.install(_candidate())
    state_before = store.state_path.read_bytes()
    store.journal_path.write_bytes(store.journal_path.read_bytes() + b"{}\n")
    with pytest.raises(BrowserTrustStoreError):
        store.snapshot()
    store.journal_path.write_bytes(store.journal_path.read_bytes().rsplit(b"{}\n", 1)[0])
    store.state_path.write_bytes(state_before)
    store.state_path.chmod(0o644)
    with pytest.raises(BrowserTrustStoreError):
        store.snapshot()


def test_protocol_binds_document_epoch_nonce_and_sequences(tmp_path: Path) -> None:
    store = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: VALID_TIME,
        network_verifier=lambda _origin, _policy: True,
    )
    fingerprint = store.initialize()
    state = store.install(_candidate())
    session = TrustProtocolSession(
        store,
        {
            "type": "BROKER_OPEN",
            "protocol_version": 1,
            "origin": state.enrollment.origin,
            "document_id": "12345678-abcd-4321-abcd-123456789abc",
            "native_nonce": "n" * 43,
            "provider_installation_key_fingerprint": fingerprint,
        },
    )
    broker = session.broker_opened()
    assert broker["type"] == "BROKER_OPENED"
    nonce = "a" * 43
    opened = session.handle(
        {
            "type": "OPEN",
            "protocol_version": 1,
            "page_nonce": nonce,
            "sequence": "1",
            "correlation_id": "req_" + "b" * 32,
        }
    )
    assert opened["type"] == "OPENED" and opened["sequence"] == "1"
    snapshot = session.handle(
        {
            "type": "SNAPSHOT_GET",
            "protocol_version": 1,
            "page_nonce": nonce,
            "sequence": "2",
            "correlation_id": "req_" + "c" * 32,
        }
    )
    assert snapshot["type"] == "SNAPSHOT"
    assert snapshot["snapshot"]["provider_epoch"] == state.value["provider_epoch"]  # type: ignore[index]
    with pytest.raises(TrustProtocolError):
        session.handle(
            {
                "type": "PING",
                "protocol_version": 1,
                "page_nonce": nonce,
                "sequence": "2",
                "correlation_id": "req_" + "d" * 32,
            }
        )
    invalidated = session.invalidate("changed")
    assert invalidated["type"] == "INVALIDATE"


def test_protocol_open_reuses_its_initial_atomic_snapshot(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def network(origin: str, policy: str) -> bool:
        calls.append((origin, policy))
        return True

    store = BrowserTrustStore(
        tmp_path / "trust", clock=lambda: VALID_TIME, network_verifier=network
    )
    fingerprint = store.initialize()
    store.install(_candidate())
    calls.clear()
    session = TrustProtocolSession(
        store,
        {
            "type": "BROKER_OPEN",
            "protocol_version": 1,
            "origin": "https://example.agentbox.test",
            "document_id": "12345678-abcd-4321-abcd-123456789abc",
            "native_nonce": "n" * 43,
            "provider_installation_key_fingerprint": fingerprint,
        },
    )
    assert len(calls) == 1
    assert (
        session.handle(
            {
                "type": "OPEN",
                "protocol_version": 1,
                "page_nonce": "a" * 43,
                "sequence": "1",
                "correlation_id": "req_" + "b" * 32,
            }
        )["type"]
        == "OPENED"
    )
    assert len(calls) == 1


def test_native_host_verifies_trustd_identity_before_forwarding(tmp_path: Path) -> None:
    store = BrowserTrustStore(
        tmp_path / "trust",
        clock=lambda: VALID_TIME,
        network_verifier=lambda _origin, _policy: True,
    )
    fingerprint = store.initialize()
    state = store.install(_candidate())
    broker_open = {
        "type": "BROKER_OPEN",
        "protocol_version": 1,
        "origin": state.enrollment.origin,
        "document_id": "12345678-abcd-4321-abcd-123456789abc",
        "native_nonce": "n" * 43,
        "provider_installation_key_fingerprint": fingerprint,
    }
    session = TrustProtocolSession(store, broker_open)
    provider_close = {
        "type": "CLOSE",
        "protocol_version": 1,
        "page_nonce": "a" * 43,
        "sequence": "1",
        "correlation_id": "req_" + "b" * 32,
        "reason": "closed",
    }
    trustd_incoming = io.BytesIO()
    write_frame(
        trustd_incoming,
        canonical_json(session.broker_opened(), limit=4096),
        limit=4096,
        little_endian=False,
    )
    write_frame(
        trustd_incoming,
        canonical_json(provider_close),
        limit=512 * 1024,
        little_endian=False,
    )
    trustd = _Duplex(trustd_incoming.getvalue())
    chrome_incoming = io.BytesIO()
    write_native_message(chrome_incoming, broker_open)
    write_native_message(
        chrome_incoming,
        {
            "type": "CLOSE",
            "protocol_version": 1,
            "page_nonce": "a" * 43,
            "sequence": "1",
            "correlation_id": "req_" + "b" * 32,
        },
    )
    chrome_incoming.seek(0)
    chrome_output = io.BytesIO()
    bridge(chrome_incoming, chrome_output, trustd)
    chrome_output.seek(0)
    assert read_native_message(chrome_output) == provider_close
    trustd.outgoing.seek(0)
    assert (
        strict_json(read_frame(trustd.outgoing, limit=4096, little_endian=False), limit=4096)
        == broker_open
    )


def test_managed_client_bundle_cross_pins_public_inputs(tmp_path: Path) -> None:
    extension = tmp_path / "extension"
    extension.mkdir()
    (extension / "manifest.json").write_text(
        '{"background":{"service_worker":"serviceWorker.js","type":"module"},'
        '"incognito":"not_allowed","manifest_version":3,"name":"inert",'
        '"description":"inert trust bridge",'
        '"permissions":["nativeMessaging","storage"],'
        '"storage":{"managed_schema":"managed_schema.json"},"version":"0.3.0.4"}',
        encoding="utf-8",
    )
    for name in (
        "managed_schema.json",
        "protocol.d.ts",
        "protocol.js",
        "serviceWorker.d.ts",
        "serviceWorker.js",
    ):
        (extension / name).write_text("export {};\n", encoding="utf-8")
    public_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    encoded_key = base64.b64encode(public_key).decode("ascii")
    extension_id = chrome_extension_id(public_key)
    output = tmp_path / "bundle"
    build_client_bundle(
        output,
        extension_dist=extension,
        extension_id=extension_id,
        extension_public_key=encoded_key,
        origin="https://example.agentbox.test:8443",
        update_url="https://updates.agentbox.test/chrome/update.xml",
        provider_fingerprint="a" * 64,
        client_uids=(1000,),
    )
    manifest = strict_json((output / "extension/manifest.json").read_bytes())
    assert manifest["key"] == encoded_key  # type: ignore[index]
    assert manifest["externally_connectable"] == {  # type: ignore[index]
        "matches": ["https://example.agentbox.test/*"]
    }
    native = strict_json(
        (output / "native-messaging/com.forcemind.agentbox.waw_trust.json").read_bytes()
    )
    assert native["allowed_origins"] == [f"chrome-extension://{extension_id}/"]  # type: ignore[index]
    policy = strict_json((output / "chrome-policy/agentbox-waw-trust.json").read_bytes())
    assert extension_id in policy["ExtensionSettings"]  # type: ignore[index]
    with pytest.raises(BrowserTrustPackageError):
        build_client_bundle(
            tmp_path / "bad",
            extension_dist=extension,
            extension_id="a" * 32,
            extension_public_key=encoded_key,
            origin="https://example.agentbox.test:8443",
            update_url="https://updates.agentbox.test/chrome/update.xml",
            provider_fingerprint="a" * 64,
            client_uids=(1000,),
        )
    (extension / "unexpected.js").write_text("secret", encoding="utf-8")
    with pytest.raises(BrowserTrustPackageError):
        build_client_bundle(
            tmp_path / "unexpected",
            extension_dist=extension,
            extension_id=extension_id,
            extension_public_key=encoded_key,
            origin="https://example.agentbox.test:8443",
            update_url="https://updates.agentbox.test/chrome/update.xml",
            provider_fingerprint="a" * 64,
            client_uids=(1000,),
        )
