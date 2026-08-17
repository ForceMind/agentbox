from __future__ import annotations

import grp
import json
import os
import pwd
import sqlite3
import stat
import threading
from pathlib import Path
from types import SimpleNamespace

import agentbox_runtime.secret_store as secret_store_module
import pytest
from agentbox_runtime.secret_crypto import _SecretEnvelopeCodec, derive_key_id
from agentbox_runtime.secret_store import (
    SECRET_STORE_DATABASE,
    SECRET_STORE_KEYS,
    SECRET_STORE_KEYSET,
    RuntimeSecretStore,
    _RuntimeIdentityVerifier,
)
from agentbox_runtime.secret_store_models import (
    SecretKeyset,
    SecretStoreError,
    SecretStoreHealthState,
    SecretStoreInitializeResult,
)
from support.failure_injection import InjectedCrash

EXPECTED_TABLES = {
    "secret_store_meta",
    "key_metadata",
    "secret_records",
    "dek_envelopes",
}
EXPECTED_INDEXES = {
    "idx_secret_records_credential_version",
    "idx_dek_envelopes_secret_record",
    "idx_dek_envelopes_wrap_nonce",
}


def _foundation(tmp_path: Path) -> tuple[RuntimeSecretStore, Path]:
    home = tmp_path / "runtime-home"
    home.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    store = RuntimeSecretStore._for_test(home)
    return store, home / ".local/share/agentbox/provider-secrets/v1"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _database(root: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(root / SECRET_STORE_DATABASE)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _insert_pair(
    connection: sqlite3.Connection,
    *,
    suffix: str,
    version: int,
    wrap_nonce: str,
) -> None:
    secret_id = f"sec_{suffix * 32}"
    envelope_id = f"dek_{suffix * 32}"
    connection.execute(
        """
        INSERT INTO secret_records VALUES (?, ?, ?, 'api_key', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            secret_id,
            "rti_11111111111111111111111111111111",
            "crd_22222222222222222222222222222222",
            version,
            "agentbox.provider-secret-envelope.v1",
            "A256GCM-HKDF-SHA256-v1",
            envelope_id,
            "A" * 16,
            "B" * 23,
            "C" * 16,
            "2026-08-17T00:00:00Z",
        ),
    )
    key_id = connection.execute("SELECT key_id FROM key_metadata").fetchone()[0]
    connection.execute(
        """
        INSERT INTO dek_envelopes VALUES (?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (
            envelope_id,
            secret_id,
            key_id,
            wrap_nonce,
            "D" * 64,
            "E" * 16,
            "2026-08-17T00:00:00Z",
        ),
    )


def test_clean_initialization_creates_exact_empty_store(tmp_path: Path) -> None:
    store, root = _foundation(tmp_path)

    assert store.health().state is SecretStoreHealthState.UNINITIALIZED
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    health = store.health()

    assert health.state is SecretStoreHealthState.HEALTHY
    assert health.finding_codes == ()
    assert set(path.name for path in root.iterdir()) == {
        SECRET_STORE_KEYS,
        SECRET_STORE_KEYSET,
        SECRET_STORE_DATABASE,
    }
    assert _mode(root) == 0o700
    assert _mode(root / SECRET_STORE_KEYS) == 0o700
    assert _mode(root / SECRET_STORE_KEYSET) == 0o600
    assert _mode(root / SECRET_STORE_DATABASE) == 0o600
    keyset = SecretKeyset.from_bytes((root / SECRET_STORE_KEYSET).read_bytes())
    key = root / SECRET_STORE_KEYS / f"{keyset.current_key_id}.key"
    assert _mode(key) == 0o600
    assert len(key.read_bytes()) == 32
    assert key.stat().st_nlink == 1
    with _database(root) as connection:
        objects = connection.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        assert {name for kind, name in objects if kind == "table"} == EXPECTED_TABLES
        assert {name for kind, name in objects if kind == "index"} == EXPECTED_INDEXES
        assert connection.execute("SELECT COUNT(*) FROM secret_records").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM dek_envelopes").fetchone() == (0,)
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)


def test_second_initialization_is_idempotent_and_does_not_generate_another_key(
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def entropy(size: int) -> bytes:
        calls.append(size)
        return os.urandom(size)

    home = tmp_path / "runtime-home"
    home.mkdir(mode=0o700)
    store = RuntimeSecretStore._for_test(home, entropy=entropy)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    first_calls = tuple(calls)
    keyset_before = (
        home / secret_store_module.SECRET_STORE_RELATIVE_ROOT / "keyset.json"
    ).read_bytes()

    assert store.initialize() is SecretStoreInitializeResult.ALREADY_INITIALIZED
    assert tuple(calls) == first_calls
    assert (
        home / secret_store_module.SECRET_STORE_RELATIVE_ROOT / "keyset.json"
    ).read_bytes() == keyset_before


@pytest.mark.parametrize("present", ("key", "keyset", "store", "directory"))
def test_partial_committed_state_never_generates_a_replacement_key(
    tmp_path: Path, present: str
) -> None:
    store, root = _foundation(tmp_path)
    root.mkdir(mode=0o700, parents=True)
    if present == "key":
        keys = root / SECRET_STORE_KEYS
        keys.mkdir(mode=0o700)
        (keys / f"{'1' * 32}.key").write_bytes(b"K" * 32)
        os.chmod(keys / f"{'1' * 32}.key", 0o600)
    elif present == "keyset":
        (root / SECRET_STORE_KEYSET).write_bytes(SecretKeyset.initial("1" * 32).to_bytes())
        os.chmod(root / SECRET_STORE_KEYSET, 0o600)
    elif present == "store":
        (root / SECRET_STORE_DATABASE).write_bytes(b"not-a-store")
        os.chmod(root / SECRET_STORE_DATABASE, 0o600)

    assert store.initialize() is SecretStoreInitializeResult.SECRET_STORE_NEEDS_ATTENTION
    assert not list(root.rglob("*.key")) if present != "key" else True


def test_missing_key_from_valid_store_is_unavailable_and_not_replaced(tmp_path: Path) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    key_path = next((root / SECRET_STORE_KEYS).glob("*.key"))
    key_path.unlink()

    assert store.health().state is SecretStoreHealthState.UNAVAILABLE
    assert store.initialize() is SecretStoreInitializeResult.SECRET_STORE_UNAVAILABLE
    assert list((root / SECRET_STORE_KEYS).iterdir()) == []


@pytest.mark.parametrize(
    "point",
    (
        "after_staging_directory_creation",
        "after_root_key_write",
        "after_key_fsync",
        "after_keyset_write",
        "after_store_creation",
        "after_store_fsync",
        "before_rename",
    ),
)
def test_precommit_crash_preserves_staging_and_requires_attention(
    tmp_path: Path, point: str
) -> None:
    store, root = _foundation(tmp_path)

    def crash(observed: str) -> None:
        if observed == point:
            raise InjectedCrash()

    crashing = RuntimeSecretStore._for_test(store._runtime_home, fault=crash)
    with pytest.raises(InjectedCrash):
        crashing.initialize()

    assert not root.exists()
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION
    assert store.initialize() is SecretStoreInitializeResult.SECRET_STORE_NEEDS_ATTENTION


@pytest.mark.parametrize(
    "point",
    ("after_rename", "before_parent_fsync", "after_parent_fsync", "before_final_reopen"),
)
def test_postcommit_interruption_reopens_as_already_initialized(tmp_path: Path, point: str) -> None:
    store, _root = _foundation(tmp_path)

    def crash(observed: str) -> None:
        if observed == point:
            raise InjectedCrash()

    crashing = RuntimeSecretStore._for_test(store._runtime_home, fault=crash)
    with pytest.raises(InjectedCrash):
        crashing.initialize()

    assert store.health().state is SecretStoreHealthState.HEALTHY
    assert store.initialize() is SecretStoreInitializeResult.ALREADY_INITIALIZED


def test_concurrent_initialize_is_bounded_by_fixed_local_lock(tmp_path: Path) -> None:
    store, _root = _foundation(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    first_result: list[SecretStoreInitializeResult] = []

    def pause(point: str) -> None:
        if point == "after_staging_directory_creation":
            entered.set()
            assert release.wait(timeout=5)

    first = RuntimeSecretStore._for_test(store._runtime_home, fault=pause)
    thread = threading.Thread(target=lambda: first_result.append(first.initialize()))
    thread.start()
    assert entered.wait(timeout=5)
    try:
        assert store.initialize() is SecretStoreInitializeResult.SECRET_STORE_UNAVAILABLE
    finally:
        release.set()
        thread.join(timeout=5)
    assert first_result == [SecretStoreInitializeResult.INITIALIZED]


@pytest.mark.parametrize("target", ("v1", "keyset", "store", "key", "journal"))
def test_symlink_substitution_fails_closed(tmp_path: Path, target: str) -> None:
    store, root = _foundation(tmp_path)
    if target == "v1":
        root.parent.mkdir(parents=True, mode=0o700)
        root.symlink_to(tmp_path)
    else:
        assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
        if target == "keyset":
            path = root / SECRET_STORE_KEYSET
        elif target == "store":
            path = root / SECRET_STORE_DATABASE
        elif target == "key":
            path = next((root / SECRET_STORE_KEYS).iterdir())
        else:
            path = root / f"{SECRET_STORE_DATABASE}-journal"
        if path.exists():
            path.unlink()
        path.symlink_to(tmp_path / "outside")

    assert store.health().state is not SecretStoreHealthState.HEALTHY


@pytest.mark.parametrize("target", ("store", "key"))
def test_hard_linked_protected_file_fails_closed(tmp_path: Path, target: str) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    path = (
        root / SECRET_STORE_DATABASE
        if target == "store"
        else next((root / SECRET_STORE_KEYS).iterdir())
    )
    os.link(path, tmp_path / f"linked-{target}")

    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION


def test_parent_symlink_and_fifo_substitution_fail_without_traversal_or_blocking(
    tmp_path: Path,
) -> None:
    store, root = _foundation(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (store._runtime_home / ".local").symlink_to(outside)
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION
    assert store.initialize() is SecretStoreInitializeResult.SECRET_STORE_NEEDS_ATTENTION

    (store._runtime_home / ".local").unlink()
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    keyset = root / SECRET_STORE_KEYSET
    keyset.unlink()
    os.mkfifo(keyset, mode=0o600)
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION


def test_name_to_inode_replacement_is_detected_after_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    original = secret_store_module._verify_name_matches_fd
    replaced = False

    def replace_after_check(parent_fd: int, name: str, descriptor: int) -> None:
        nonlocal replaced
        original(parent_fd, name, descriptor)
        if name == SECRET_STORE_DATABASE and not replaced:
            replaced = True
            old = root / SECRET_STORE_DATABASE
            replacement = root / "replacement"
            replacement.write_bytes(old.read_bytes())
            os.chmod(replacement, 0o600)
            old.rename(root / "original-store")
            replacement.rename(old)

    monkeypatch.setattr(secret_store_module, "_verify_name_matches_fd", replace_after_check)
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION
    assert replaced is True


def test_runtime_identity_verifier_requires_real_effective_and_saved_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda _name: SimpleNamespace(pw_uid=1234, pw_gid=2345),
    )
    monkeypatch.setattr(
        grp,
        "getgrnam",
        lambda _name: SimpleNamespace(gr_gid=2345),
    )
    monkeypatch.setattr(os, "getresuid", lambda: (1234, 1234, 1234))
    monkeypatch.setattr(os, "getresgid", lambda: (2345, 2345, 2345))
    assert _RuntimeIdentityVerifier().expected() == secret_store_module._RuntimeIdentity(1234, 2345)

    monkeypatch.setattr(os, "getresuid", lambda: (1234, 1234, 0))
    with pytest.raises(SecretStoreError, match="SECRET_STORE_UNAVAILABLE"):
        _RuntimeIdentityVerifier().expected()


@pytest.mark.parametrize("target", ("root", "keys", "keyset", "store"))
def test_permission_drift_fails_closed(tmp_path: Path, target: str) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    path = {
        "root": root,
        "keys": root / SECRET_STORE_KEYS,
        "keyset": root / SECRET_STORE_KEYSET,
        "store": root / SECRET_STORE_DATABASE,
    }[target]
    os.chmod(path, _mode(path) | 0o020)

    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION


@pytest.mark.parametrize("kind", ("table", "view", "trigger", "index"))
def test_unexpected_sqlite_schema_object_fails_health(tmp_path: Path, kind: str) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    statement = {
        "table": "CREATE TABLE unexpected(value TEXT)",
        "view": "CREATE VIEW unexpected AS SELECT singleton_id FROM secret_store_meta",
        "trigger": "CREATE TRIGGER unexpected AFTER UPDATE ON key_metadata BEGIN SELECT 1; END",
        "index": "CREATE INDEX unexpected ON key_metadata(key_state)",
    }[kind]
    with sqlite3.connect(root / SECRET_STORE_DATABASE) as connection:
        connection.execute(statement)

    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION


def test_foreign_key_violation_and_truncated_store_fail_health(tmp_path: Path) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    with sqlite3.connect(root / SECRET_STORE_DATABASE) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            """
            INSERT INTO secret_records VALUES (?, ?, ?, 'api_key', 1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sec_11111111111111111111111111111111",
                "rti_11111111111111111111111111111111",
                "crd_22222222222222222222222222222222",
                "agentbox.provider-secret-envelope.v1",
                "A256GCM-HKDF-SHA256-v1",
                "dek_11111111111111111111111111111111",
                "A" * 16,
                "B" * 23,
                "C" * 16,
                "2026-08-17T00:00:00Z",
            ),
        )
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION

    (root / SECRET_STORE_DATABASE).write_bytes(b"truncated")
    os.chmod(root / SECRET_STORE_DATABASE, 0o600)
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION


def test_unique_secret_identity_version_and_wrap_nonce_constraints(tmp_path: Path) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    with _database(root) as connection:
        _insert_pair(connection, suffix="1", version=1, wrap_nonce="N" * 16)
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_pair(connection, suffix="2", version=1, wrap_nonce="O" * 16)
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_pair(connection, suffix="2", version=2, wrap_nonce="N" * 16)
        connection.rollback()


def test_store_size_record_count_and_wal_policy_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    monkeypatch.setattr(secret_store_module, "SECRET_STORE_MAX_BYTES", 1)
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION
    monkeypatch.undo()
    monkeypatch.setattr(secret_store_module, "SECRET_STORE_MAX_RECORDS", -1)
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION
    monkeypatch.undo()
    with sqlite3.connect(root / SECRET_STORE_DATABASE) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION


def test_exact_envelope_aad_chain_is_structurally_verified_by_health(tmp_path: Path) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    keyset = SecretKeyset.from_bytes((root / SECRET_STORE_KEYSET).read_bytes())
    root_key = (root / SECRET_STORE_KEYS / f"{keyset.current_key_id}.key").read_bytes()
    codec = _SecretEnvelopeCodec(
        root_key,
        runtime_installation_id="rti_11111111111111111111111111111111",
        kek_key_id=derive_key_id(root_key),
    )
    envelope = codec.seal_for_internal_verification(
        credential_id="crd_22222222222222222222222222222222",
        credential_kind="api_key",
        secret_version=1,
        plaintext=b"synthetic-test-only-value",
    )
    with _database(root) as connection:
        connection.execute(
            """
            INSERT INTO secret_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope.secret_record_id,
                envelope.runtime_installation_id,
                envelope.credential_id,
                envelope.credential_kind,
                envelope.secret_version,
                envelope.envelope_schema,
                envelope.algorithm_id,
                envelope.dek_envelope_id,
                envelope.payload_nonce,
                envelope.payload_ciphertext,
                envelope.payload_aad,
                "2026-08-17T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO dek_envelopes VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope.dek_envelope_id,
                envelope.secret_record_id,
                envelope.kek_key_id,
                envelope.kek_key_version,
                envelope.wrap_nonce,
                envelope.wrapped_dek,
                envelope.wrap_aad,
                "2026-08-17T00:00:00Z",
            ),
        )
        connection.execute("UPDATE key_metadata SET successful_wraps = 1")
    assert store.health().state is SecretStoreHealthState.HEALTHY

    with _database(root) as connection:
        connection.execute(
            "UPDATE secret_records SET payload_aad = ?",
            ("A" * len(envelope.payload_aad),),
        )
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION


def test_kek_wrap_counter_hard_limit_blocks_without_automatic_rotation(tmp_path: Path) -> None:
    store, root = _foundation(tmp_path)
    assert store.initialize() is SecretStoreInitializeResult.INITIALIZED
    with _database(root) as connection:
        connection.execute("UPDATE key_metadata SET successful_wraps = ?", (2**32 - 1,))
    assert store.health().state is SecretStoreHealthState.NEEDS_ATTENTION
    with _database(root) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE key_metadata SET successful_wraps = ?", (2**32,))


def test_keyset_rejects_duplicates_unknown_fields_and_nondeterminism() -> None:
    valid = SecretKeyset.initial("1" * 32)
    payload = valid.to_bytes()
    assert SecretKeyset.from_bytes(payload) == valid
    value = json.loads(payload)
    value["unknown"] = True
    with pytest.raises(Exception, match="SECRET_STORE_KEYSET_INVALID"):
        SecretKeyset.from_bytes(json.dumps(value).encode())
    duplicate = payload.rstrip(b"\n").replace(
        b'{"current_key_id":', b'{"schema":"duplicate","current_key_id":'
    )
    with pytest.raises(Exception, match="SECRET_STORE_KEYSET_INVALID"):
        SecretKeyset.from_bytes(duplicate)
