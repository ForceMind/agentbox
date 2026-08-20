"""Fixed-path, Runtime-owned Provider Secret Store foundation."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import grp
import os
import pwd
import re
import sqlite3
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Final

from agentbox_runtime.secret_crypto import (
    ROOT_KEY_BYTES,
    _SealedSecretEnvelope,
    _validate_envelope_structure,
    derive_key_id,
    run_secret_crypto_self_test,
)
from agentbox_runtime.secret_store_models import (
    ALGORITHM_ID,
    ENVELOPE_SCHEMA,
    KEYSET_MAX_BYTES,
    STORE_SCHEMA,
    SecretKeyset,
    SecretStoreError,
    SecretStoreFindingCode,
    SecretStoreHealth,
    SecretStoreHealthState,
    SecretStoreInitializeResult,
)

PRODUCTION_RUNTIME_HOME: Final = Path("/home/agentbox-runtime")
SECRET_STORE_RELATIVE_ROOT: Final = Path(".local/share/agentbox/provider-secrets/v1")
PRODUCTION_SECRET_STORE_ROOT: Final = PRODUCTION_RUNTIME_HOME / SECRET_STORE_RELATIVE_ROOT
SECRET_STORE_DATABASE = "store.sqlite3"
SECRET_STORE_KEYSET = "keyset.json"
SECRET_STORE_KEYS = "keys"
SECRET_STORE_LOCK = ".initialize.lock"
SECRET_STORE_MAX_BYTES = 128 * 1024 * 1024
SECRET_STORE_MAX_RECORDS = 4096
SECRET_STORE_BUSY_TIMEOUT_MS = 2_000
SECRET_STORE_SCHEMA_VERSION = 1
MAX_SCHEMA_OBJECTS = 32
MAX_DIRECTORY_ENTRIES = 16
KEK_WRAP_LIMIT = 2**32
_STAGING_NAME = re.compile(r"\.v1\.init-[0-9a-f]{32}")
_KEY_FILE_NAME = re.compile(r"[0-9a-f]{32}\.key")
_FIXED_PARENT_PARTS = (".local", "share", "agentbox", "provider-secrets")
_SCHEMA_DDL = """
CREATE TABLE secret_store_meta (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    store_schema TEXT NOT NULL CHECK (store_schema = 'agentbox.provider-secret-store.v1'),
    envelope_schema TEXT NOT NULL CHECK (envelope_schema = 'agentbox.provider-secret-envelope.v1'),
    algorithm_id TEXT NOT NULL CHECK (algorithm_id = 'A256GCM-HKDF-SHA256-v1'),
    created_at TEXT NOT NULL CHECK (length(created_at) BETWEEN 20 AND 35)
);
CREATE TABLE key_metadata (
    key_id TEXT PRIMARY KEY
        CHECK (length(key_id) = 32 AND key_id NOT GLOB '*[^0-9a-f]*'),
    key_version INTEGER NOT NULL UNIQUE CHECK (key_version = 1),
    key_state TEXT NOT NULL CHECK (key_state = 'current'),
    successful_wraps INTEGER NOT NULL DEFAULT 0
        CHECK (successful_wraps >= 0 AND successful_wraps < 4294967296),
    created_at TEXT NOT NULL CHECK (length(created_at) BETWEEN 20 AND 35)
);
CREATE TABLE secret_records (
    secret_record_id TEXT PRIMARY KEY
        CHECK (length(secret_record_id) = 36
               AND substr(secret_record_id, 1, 4) = 'sec_'
               AND substr(secret_record_id, 5) NOT GLOB '*[^0-9a-f]*'),
    runtime_installation_id TEXT NOT NULL
        CHECK (length(runtime_installation_id) = 36
               AND substr(runtime_installation_id, 1, 4) = 'rti_'
               AND substr(runtime_installation_id, 5) NOT GLOB '*[^0-9a-f]*'),
    credential_id TEXT NOT NULL
        CHECK (length(credential_id) = 36
               AND substr(credential_id, 1, 4) = 'crd_'
               AND substr(credential_id, 5) NOT GLOB '*[^0-9a-f]*'),
    credential_kind TEXT NOT NULL CHECK (credential_kind = 'api_key'),
    secret_version INTEGER NOT NULL CHECK (secret_version >= 1),
    envelope_schema TEXT NOT NULL CHECK (envelope_schema = 'agentbox.provider-secret-envelope.v1'),
    algorithm_id TEXT NOT NULL CHECK (algorithm_id = 'A256GCM-HKDF-SHA256-v1'),
    dek_envelope_id TEXT NOT NULL UNIQUE
        CHECK (length(dek_envelope_id) = 36
               AND substr(dek_envelope_id, 1, 4) = 'dek_'
               AND substr(dek_envelope_id, 5) NOT GLOB '*[^0-9a-f]*'),
    payload_nonce TEXT NOT NULL
        CHECK (length(payload_nonce) = 16
               AND payload_nonce NOT GLOB '*[^A-Za-z0-9_-]*'),
    payload_ciphertext TEXT NOT NULL
        CHECK (length(payload_ciphertext) BETWEEN 23 AND 21867
               AND payload_ciphertext NOT GLOB '*[^A-Za-z0-9_-]*'),
    payload_aad TEXT NOT NULL
        CHECK (length(payload_aad) BETWEEN 1 AND 5462
               AND payload_aad NOT GLOB '*[^A-Za-z0-9_-]*'),
    created_at TEXT NOT NULL CHECK (length(created_at) BETWEEN 20 AND 35),
    FOREIGN KEY (dek_envelope_id) REFERENCES dek_envelopes(dek_envelope_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE dek_envelopes (
    dek_envelope_id TEXT PRIMARY KEY
        CHECK (length(dek_envelope_id) = 36
               AND substr(dek_envelope_id, 1, 4) = 'dek_'
               AND substr(dek_envelope_id, 5) NOT GLOB '*[^0-9a-f]*'),
    secret_record_id TEXT NOT NULL UNIQUE
        CHECK (length(secret_record_id) = 36
               AND substr(secret_record_id, 1, 4) = 'sec_'
               AND substr(secret_record_id, 5) NOT GLOB '*[^0-9a-f]*'),
    kek_key_id TEXT NOT NULL
        CHECK (length(kek_key_id) = 32 AND kek_key_id NOT GLOB '*[^0-9a-f]*'),
    kek_key_version INTEGER NOT NULL CHECK (kek_key_version = 1),
    wrap_nonce TEXT NOT NULL
        CHECK (length(wrap_nonce) = 16
               AND wrap_nonce NOT GLOB '*[^A-Za-z0-9_-]*'),
    wrapped_dek TEXT NOT NULL
        CHECK (length(wrapped_dek) = 64
               AND wrapped_dek NOT GLOB '*[^A-Za-z0-9_-]*'),
    wrap_aad TEXT NOT NULL
        CHECK (length(wrap_aad) BETWEEN 1 AND 5462
               AND wrap_aad NOT GLOB '*[^A-Za-z0-9_-]*'),
    created_at TEXT NOT NULL CHECK (length(created_at) BETWEEN 20 AND 35),
    FOREIGN KEY (secret_record_id) REFERENCES secret_records(secret_record_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (kek_key_id) REFERENCES key_metadata(key_id)
);
CREATE UNIQUE INDEX idx_secret_records_credential_version
    ON secret_records(credential_id, secret_version);
CREATE UNIQUE INDEX idx_dek_envelopes_secret_record
    ON dek_envelopes(secret_record_id);
CREATE UNIQUE INDEX idx_dek_envelopes_wrap_nonce
    ON dek_envelopes(kek_key_id, wrap_nonce);
CREATE TRIGGER trg_secret_records_no_update
BEFORE UPDATE ON secret_records
BEGIN
    SELECT RAISE(ABORT, 'immutable secret record');
END;
CREATE TRIGGER trg_secret_records_no_delete
BEFORE DELETE ON secret_records
BEGIN
    SELECT RAISE(ABORT, 'immutable secret record');
END;
CREATE TRIGGER trg_dek_envelopes_no_update
BEFORE UPDATE ON dek_envelopes
BEGIN
    SELECT RAISE(ABORT, 'immutable DEK envelope');
END;
CREATE TRIGGER trg_dek_envelopes_no_delete
BEFORE DELETE ON dek_envelopes
BEGIN
    SELECT RAISE(ABORT, 'immutable DEK envelope');
END;
"""


@dataclass(frozen=True)
class _RuntimeIdentity:
    uid: int
    gid: int


class _RuntimeIdentityVerifier:
    def expected(self) -> _RuntimeIdentity:
        try:
            account = pwd.getpwnam("agentbox-runtime")
            group = grp.getgrnam("agentbox-runtime")
        except KeyError as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE) from exc
        if account.pw_gid != group.gr_gid:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE)
        try:
            uids = os.getresuid()
            gids = os.getresgid()
        except AttributeError as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE) from exc
        if uids != (account.pw_uid, account.pw_uid, account.pw_uid) or gids != (
            group.gr_gid,
            group.gr_gid,
            group.gr_gid,
        ):
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE)
        return _RuntimeIdentity(account.pw_uid, group.gr_gid)


class _InjectedIdentityVerifier(_RuntimeIdentityVerifier):
    def __init__(self, uid: int, gid: int) -> None:
        self._identity = _RuntimeIdentity(uid, gid)

    def expected(self) -> _RuntimeIdentity:
        return self._identity


class _SecretStoreLayout:
    def __init__(self, runtime_home: Path, identity: _RuntimeIdentity) -> None:
        self.runtime_home = runtime_home
        self.parent = runtime_home.joinpath(*_FIXED_PARENT_PARTS)
        self.root = self.parent / "v1"
        self.identity = identity


class RuntimeSecretStore:
    """Foundation-only Store. Production construction has one fixed path."""

    def __init__(
        self,
        *,
        _runtime_home: Path = PRODUCTION_RUNTIME_HOME,
        _identity_verifier: _RuntimeIdentityVerifier | None = None,
        _entropy: Callable[[int], bytes] = os.urandom,
        _fault: Callable[[str], None] | None = None,
    ) -> None:
        if _runtime_home != PRODUCTION_RUNTIME_HOME and _identity_verifier is None:
            raise TypeError("private test roots require a private identity verifier")
        self._runtime_home = _runtime_home
        self._identity_verifier = _identity_verifier or _RuntimeIdentityVerifier()
        self._entropy = _entropy
        self._fault = _fault or (lambda _point: None)

    @classmethod
    def _for_test(
        cls,
        runtime_home: Path,
        *,
        entropy: Callable[[int], bytes] = os.urandom,
        fault: Callable[[str], None] | None = None,
    ) -> RuntimeSecretStore:
        details = runtime_home.stat()
        return cls(
            _runtime_home=runtime_home,
            _identity_verifier=_InjectedIdentityVerifier(details.st_uid, details.st_gid),
            _entropy=entropy,
            _fault=fault,
        )

    def initialize(self) -> SecretStoreInitializeResult:
        try:
            identity = self._identity_verifier.expected()
            layout = _SecretStoreLayout(self._runtime_home, identity)
            old_umask = os.umask(0o077)
            try:
                return self._initialize_locked(layout)
            finally:
                os.umask(old_umask)
        except SecretStoreError as exc:
            if exc.code is SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE:
                return SecretStoreInitializeResult.SECRET_STORE_UNAVAILABLE
            return SecretStoreInitializeResult.SECRET_STORE_NEEDS_ATTENTION
        except (OSError, sqlite3.Error):
            return SecretStoreInitializeResult.SECRET_STORE_NEEDS_ATTENTION

    def health(self) -> SecretStoreHealth:
        try:
            identity = self._identity_verifier.expected()
            layout = _SecretStoreLayout(self._runtime_home, identity)
            presence = self._committed_presence(layout)
            if presence == "absent":
                return _health(
                    SecretStoreHealthState.UNINITIALIZED,
                    SecretStoreFindingCode.SECRET_STORE_UNINITIALIZED,
                )
            if presence == "ambiguous":
                return _health(
                    SecretStoreHealthState.NEEDS_ATTENTION,
                    SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION,
                )
            self._validate_committed_store(layout)
            return SecretStoreHealth(
                state=SecretStoreHealthState.HEALTHY,
                finding_codes=(),
                store_schema=STORE_SCHEMA,
                algorithm_schema=ALGORITHM_ID,
            )
        except SecretStoreError as exc:
            state = (
                SecretStoreHealthState.UNAVAILABLE
                if exc.code
                in {
                    SecretStoreFindingCode.SECRET_STORE_KEY_MISSING,
                    SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE,
                }
                else SecretStoreHealthState.NEEDS_ATTENTION
            )
            return _health(state, exc.code)
        except (OSError, sqlite3.Error):
            return _health(
                SecretStoreHealthState.NEEDS_ATTENTION,
                SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED,
            )

    def _initialize_locked(self, layout: _SecretStoreLayout) -> SecretStoreInitializeResult:
        home_fd = self._open_runtime_home(layout)
        parent_fd = -1
        lock_fd = -1
        stage_fd = -1
        try:
            parent_fd = self._ensure_parent_chain(home_fd, layout.identity)
            lock_fd = self._acquire_lock(parent_fd, layout.identity)
            names = _bounded_directory_names(parent_fd)
            if "v1" in names:
                health = self.health()
                if health.state is SecretStoreHealthState.HEALTHY:
                    return SecretStoreInitializeResult.ALREADY_INITIALIZED
                if health.state is SecretStoreHealthState.UNAVAILABLE:
                    return SecretStoreInitializeResult.SECRET_STORE_UNAVAILABLE
                return SecretStoreInitializeResult.SECRET_STORE_NEEDS_ATTENTION
            if names - {SECRET_STORE_LOCK}:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)
            staging_name = self._new_staging_name()
            os.mkdir(staging_name, mode=0o700, dir_fd=parent_fd)
            stage_fd = _open_dir_at(parent_fd, staging_name)
            _validate_directory_fd(stage_fd, layout.identity, exact_mode=0o700)
            self._fault("after_staging_directory_creation")

            os.mkdir(SECRET_STORE_KEYS, mode=0o700, dir_fd=stage_fd)
            keys_fd = _open_dir_at(stage_fd, SECRET_STORE_KEYS)
            try:
                root_key = bytearray(self._random(ROOT_KEY_BYTES))
                try:
                    key_id = derive_key_id(bytes(root_key))
                    _write_exclusive_file(keys_fd, f"{key_id}.key", root_key, 0o600)
                    self._fault("after_root_key_write")
                    os.fsync(keys_fd)
                    self._fault("after_key_fsync")
                finally:
                    _zero_buffer(root_key)
            finally:
                os.close(keys_fd)

            keyset = SecretKeyset.initial(key_id)
            _write_atomic_file(
                stage_fd,
                ".keyset.json.staging",
                SECRET_STORE_KEYSET,
                keyset.to_bytes(),
                0o600,
            )
            self._fault("after_keyset_write")
            self._create_empty_database(stage_fd, keyset)
            self._fault("after_store_creation")
            os.fsync(stage_fd)
            self._fault("after_store_fsync")
            self._validate_staging_store(stage_fd, layout.identity, keyset)
            self._fault("before_rename")
            _rename_noreplace(parent_fd, staging_name, parent_fd, "v1")
            self._fault("after_rename")
            self._fault("before_parent_fsync")
            os.fsync(parent_fd)
            self._fault("after_parent_fsync")
            self._fault("before_final_reopen")
            self._validate_committed_store(layout)
            return SecretStoreInitializeResult.INITIALIZED
        finally:
            for descriptor in (stage_fd, lock_fd, parent_fd, home_fd):
                if descriptor >= 0:
                    os.close(descriptor)

    def _open_runtime_home(self, layout: _SecretStoreLayout) -> int:
        if layout.runtime_home == PRODUCTION_RUNTIME_HOME:
            root_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            home_parent_fd = -1
            try:
                _validate_trusted_system_directory(root_fd)
                home_parent_fd = _open_dir_at(root_fd, "home")
                _validate_trusted_system_directory(home_parent_fd)
                descriptor = _open_dir_at(home_parent_fd, "agentbox-runtime")
            except Exception:
                if home_parent_fd >= 0:
                    os.close(home_parent_fd)
                os.close(root_fd)
                raise
            os.close(home_parent_fd)
            os.close(root_fd)
            try:
                _validate_directory_fd(descriptor, layout.identity, exact_mode=0o700)
            except Exception:
                os.close(descriptor)
                raise
            return descriptor
        try:
            descriptor = os.open(
                layout.runtime_home,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
        except OSError as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE) from exc
        try:
            _validate_directory_fd(descriptor, layout.identity, exact_mode=0o700)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def _committed_presence(self, layout: _SecretStoreLayout) -> str:
        home_fd = self._open_runtime_home(layout)
        current = os.dup(home_fd)
        try:
            for part in _FIXED_PARENT_PARTS:
                try:
                    next_fd = _open_dir_at(current, part)
                except FileNotFoundError:
                    return "absent"
                _validate_directory_fd(next_fd, layout.identity, exact_mode=0o700)
                os.close(current)
                current = next_fd
            names = _bounded_directory_names(current)
            if "v1" in names:
                return "present"
            return "absent" if not names - {SECRET_STORE_LOCK} else "ambiguous"
        finally:
            os.close(current)
            os.close(home_fd)

    def _ensure_parent_chain(self, home_fd: int, identity: _RuntimeIdentity) -> int:
        current = os.dup(home_fd)
        try:
            for part in _FIXED_PARENT_PARTS:
                try:
                    next_fd = _open_dir_at(current, part)
                except FileNotFoundError:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                    os.fsync(current)
                    next_fd = _open_dir_at(current, part)
                _validate_directory_fd(next_fd, identity, exact_mode=0o700)
                os.close(current)
                current = next_fd
            return current
        except Exception:
            os.close(current)
            raise

    def _acquire_lock(self, parent_fd: int, identity: _RuntimeIdentity) -> int:
        try:
            descriptor = os.open(
                SECRET_STORE_LOCK,
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
            _validate_regular_fd(descriptor, identity, exact_mode=0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return descriptor
        except BlockingIOError as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE) from exc
        except OSError as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_PERMISSION_INVALID) from exc

    def _new_staging_name(self) -> str:
        value = self._random(16)
        return f".v1.init-{value.hex()}"

    def _random(self, size: int) -> bytes:
        try:
            value = self._entropy(size)
        except Exception as exc:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE) from exc
        if not isinstance(value, bytes) or len(value) != size:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE)
        return value

    def _create_empty_database(self, stage_fd: int, keyset: SecretKeyset) -> None:
        database = f"/proc/self/fd/{stage_fd}/{SECRET_STORE_DATABASE}"
        created_at = _utc_timestamp()
        connection = sqlite3.connect(database, timeout=SECRET_STORE_BUSY_TIMEOUT_MS / 1000)
        try:
            connection.execute(f"PRAGMA busy_timeout={SECRET_STORE_BUSY_TIMEOUT_MS}")
            if connection.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA_DDL)
            if not connection.in_transaction:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            try:
                connection.execute(
                    "INSERT INTO secret_store_meta VALUES (1, ?, ?, ?, ?)",
                    (STORE_SCHEMA, ENVELOPE_SCHEMA, ALGORITHM_ID, created_at),
                )
                connection.execute(
                    "INSERT INTO key_metadata VALUES (?, 1, 'current', 0, ?)",
                    (keyset.current_key_id, created_at),
                )
                connection.execute(f"PRAGMA user_version={SECRET_STORE_SCHEMA_VERSION}")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        finally:
            connection.close()
        descriptor = os.open(
            SECRET_STORE_DATABASE,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=stage_fd,
        )
        try:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _validate_staging_store(
        self, stage_fd: int, identity: _RuntimeIdentity, keyset: SecretKeyset
    ) -> None:
        names = _bounded_directory_names(stage_fd)
        if names != {SECRET_STORE_KEYS, SECRET_STORE_KEYSET, SECRET_STORE_DATABASE}:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        keyset_fd = _open_regular_at(stage_fd, SECRET_STORE_KEYSET)
        store_fd = _open_regular_at(stage_fd, SECRET_STORE_DATABASE)
        keys_fd = _open_dir_at(stage_fd, SECRET_STORE_KEYS)
        try:
            _validate_regular_fd(keyset_fd, identity, exact_mode=0o600)
            _validate_regular_fd(store_fd, identity, exact_mode=0o600)
            _validate_directory_fd(keys_fd, identity, exact_mode=0o700)
            _verify_name_matches_fd(stage_fd, SECRET_STORE_KEYSET, keyset_fd)
            _verify_name_matches_fd(stage_fd, SECRET_STORE_DATABASE, store_fd)
            if _read_bounded_fd(keyset_fd, KEYSET_MAX_BYTES) != keyset.to_bytes():
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
            key_name = f"{keyset.current_key_id}.key"
            if _bounded_directory_names(keys_fd) != {key_name}:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
            key_fd = _open_regular_at(keys_fd, key_name)
            try:
                _validate_regular_fd(key_fd, identity, exact_mode=0o600)
                key = bytearray(_read_bounded_fd(key_fd, ROOT_KEY_BYTES))
                try:
                    if (
                        len(key) != ROOT_KEY_BYTES
                        or derive_key_id(bytes(key)) != keyset.current_key_id
                    ):
                        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
                finally:
                    _zero_buffer(key)
                _verify_name_matches_fd(keys_fd, key_name, key_fd)
            finally:
                os.close(key_fd)
            self._validate_database_fd(stage_fd, store_fd, keyset)
        finally:
            os.close(keys_fd)
            os.close(store_fd)
            os.close(keyset_fd)

    def _validate_committed_store(self, layout: _SecretStoreLayout) -> None:
        home_fd = self._open_runtime_home(layout)
        parent_fd = -1
        root_fd = -1
        try:
            parent_fd = self._open_existing_parent(home_fd, layout.identity)
            parent_names = _bounded_directory_names(parent_fd)
            if any(_STAGING_NAME.fullmatch(name) for name in parent_names):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)
            if parent_names - {SECRET_STORE_LOCK, "v1"}:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)
            root_fd = _open_dir_at(parent_fd, "v1")
            _validate_directory_fd(root_fd, layout.identity, exact_mode=0o700)
            _verify_name_matches_fd(parent_fd, "v1", root_fd)
            names = _bounded_directory_names(root_fd)
            allowed = {
                SECRET_STORE_KEYS,
                SECRET_STORE_KEYSET,
                SECRET_STORE_DATABASE,
                f"{SECRET_STORE_DATABASE}-journal",
            }
            if not {SECRET_STORE_KEYS, SECRET_STORE_KEYSET, SECRET_STORE_DATABASE}.issubset(names):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)
            if names - allowed:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)
            keyset_fd = _open_regular_at(root_fd, SECRET_STORE_KEYSET)
            store_fd = _open_regular_at(root_fd, SECRET_STORE_DATABASE)
            keys_fd = _open_dir_at(root_fd, SECRET_STORE_KEYS)
            try:
                _validate_regular_fd(keyset_fd, layout.identity, exact_mode=0o600)
                _validate_regular_fd(store_fd, layout.identity, exact_mode=0o600)
                _validate_directory_fd(keys_fd, layout.identity, exact_mode=0o700)
                _verify_name_matches_fd(root_fd, SECRET_STORE_KEYSET, keyset_fd)
                _verify_name_matches_fd(root_fd, SECRET_STORE_DATABASE, store_fd)
                if os.fstat(store_fd).st_size > SECRET_STORE_MAX_BYTES:
                    raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
                if f"{SECRET_STORE_DATABASE}-journal" in names:
                    journal_fd = _open_regular_at(root_fd, f"{SECRET_STORE_DATABASE}-journal")
                    try:
                        _validate_regular_fd(journal_fd, layout.identity, exact_mode=0o600)
                        if os.fstat(journal_fd).st_size > SECRET_STORE_MAX_BYTES:
                            raise SecretStoreError(
                                SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED
                            )
                        _verify_name_matches_fd(
                            root_fd, f"{SECRET_STORE_DATABASE}-journal", journal_fd
                        )
                    finally:
                        os.close(journal_fd)
                keyset = SecretKeyset.from_bytes(_read_bounded_fd(keyset_fd, KEYSET_MAX_BYTES))
                key_name = f"{keyset.current_key_id}.key"
                if _KEY_FILE_NAME.fullmatch(key_name) is None:
                    raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID)
                if _bounded_directory_names(keys_fd) != {key_name}:
                    raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEY_MISSING)
                key_fd = _open_regular_at(keys_fd, key_name)
                try:
                    _validate_regular_fd(key_fd, layout.identity, exact_mode=0o600)
                    root_key = bytearray(_read_bounded_fd(key_fd, ROOT_KEY_BYTES))
                    try:
                        if len(root_key) != ROOT_KEY_BYTES:
                            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_KEY_MISSING)
                        if derive_key_id(bytes(root_key)) != keyset.current_key_id:
                            raise SecretStoreError(
                                SecretStoreFindingCode.SECRET_STORE_KEYSET_INVALID
                            )
                    finally:
                        _zero_buffer(root_key)
                    _verify_name_matches_fd(keys_fd, key_name, key_fd)
                finally:
                    os.close(key_fd)
                self._validate_database_fd(root_fd, store_fd, keyset)
                _verify_name_matches_fd(root_fd, SECRET_STORE_KEYSET, keyset_fd)
                _verify_name_matches_fd(root_fd, SECRET_STORE_DATABASE, store_fd)
                if not run_secret_crypto_self_test():
                    raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
                _verify_name_matches_fd(parent_fd, "v1", root_fd)
            finally:
                os.close(keys_fd)
                os.close(store_fd)
                os.close(keyset_fd)
        finally:
            for descriptor in (root_fd, parent_fd, home_fd):
                if descriptor >= 0:
                    os.close(descriptor)

    def _open_existing_parent(self, home_fd: int, identity: _RuntimeIdentity) -> int:
        current = os.dup(home_fd)
        try:
            for part in _FIXED_PARENT_PARTS:
                next_fd = _open_dir_at(current, part)
                _validate_directory_fd(next_fd, identity, exact_mode=0o700)
                os.close(current)
                current = next_fd
            return current
        except Exception:
            os.close(current)
            raise

    def _validate_database_fd(self, root_fd: int, store_fd: int, keyset: SecretKeyset) -> None:
        if os.fstat(store_fd).st_size > SECRET_STORE_MAX_BYTES:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
        _verify_name_matches_fd(root_fd, SECRET_STORE_DATABASE, store_fd)
        database = f"/proc/self/fd/{root_fd}/{SECRET_STORE_DATABASE}"
        connection = sqlite3.connect(database, timeout=SECRET_STORE_BUSY_TIMEOUT_MS / 1000)
        try:
            connection.execute(f"PRAGMA busy_timeout={SECRET_STORE_BUSY_TIMEOUT_MS}")
            if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            if connection.execute("PRAGMA synchronous").fetchone() != (2,):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            if connection.execute("PRAGMA trusted_schema").fetchone() != (0,):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            if connection.execute("PRAGMA user_version").fetchone() != (
                SECRET_STORE_SCHEMA_VERSION,
            ):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_FORMAT_UNSUPPORTED)
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            rows = connection.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name LIMIT ?",
                (MAX_SCHEMA_OBJECTS + 1,),
            ).fetchall()
            if len(rows) > MAX_SCHEMA_OBJECTS or tuple(rows) != _expected_schema_inventory():
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            meta = connection.execute(
                "SELECT store_schema, envelope_schema, algorithm_id, created_at "
                "FROM secret_store_meta WHERE singleton_id = 1"
            ).fetchall()
            if (
                len(meta) != 1
                or meta[0][:3] != (STORE_SCHEMA, ENVELOPE_SCHEMA, ALGORITHM_ID)
                or not _is_canonical_utc_timestamp(meta[0][3])
            ):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_FORMAT_UNSUPPORTED)
            keys = connection.execute(
                "SELECT key_id, key_version, key_state, successful_wraps, created_at "
                "FROM key_metadata"
            ).fetchall()
            if not (
                len(keys) == 1
                and keys[0][:3] == (keyset.current_key_id, 1, "current")
                and type(keys[0][3]) is int
                and 0 <= keys[0][3] < KEK_WRAP_LIMIT
                and _is_canonical_utc_timestamp(keys[0][4])
            ):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            successful_wraps = int(keys[0][3])
            if successful_wraps >= KEK_WRAP_LIMIT - 1:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_ROTATION_REQUIRED)
            secret_count = int(
                connection.execute("SELECT COUNT(*) FROM secret_records").fetchone()[0]
            )
            envelope_count = int(
                connection.execute("SELECT COUNT(*) FROM dek_envelopes").fetchone()[0]
            )
            if (
                secret_count > SECRET_STORE_MAX_RECORDS
                or envelope_count != secret_count
                or successful_wraps < envelope_count
            ):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            malformed = connection.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM secret_records
                    WHERE envelope_schema != ? OR algorithm_id != ?
                       OR length(payload_nonce) != 16
                       OR length(payload_ciphertext) NOT BETWEEN 23 AND 21867
                       OR length(payload_aad) NOT BETWEEN 1 AND 5462
                    UNION ALL
                    SELECT 1 FROM dek_envelopes
                    WHERE length(wrap_nonce) != 16 OR length(wrapped_dek) != 64
                       OR length(wrap_aad) NOT BETWEEN 1 AND 5462
                )
                """,
                (ENVELOPE_SCHEMA, ALGORITHM_ID),
            ).fetchone()
            if malformed != (0,):
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            envelope_rows = connection.execute(
                """
                SELECT
                    sr.envelope_schema, sr.algorithm_id,
                    sr.runtime_installation_id, sr.credential_id,
                    sr.credential_kind, sr.secret_record_id, sr.secret_version,
                    sr.dek_envelope_id, de.kek_key_id, de.kek_key_version,
                    sr.payload_nonce, sr.payload_ciphertext, sr.payload_aad,
                    de.wrap_nonce, de.wrapped_dek, de.wrap_aad,
                    sr.created_at, de.created_at
                FROM secret_records AS sr
                JOIN dek_envelopes AS de
                  ON de.dek_envelope_id = sr.dek_envelope_id
                 AND de.secret_record_id = sr.secret_record_id
                ORDER BY sr.secret_record_id
                LIMIT ?
                """,
                (SECRET_STORE_MAX_RECORDS + 1,),
            ).fetchall()
            if len(envelope_rows) != secret_count:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
            for row in envelope_rows:
                if not _is_canonical_utc_timestamp(row[-2]) or not _is_canonical_utc_timestamp(
                    row[-1]
                ):
                    raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
                _validate_envelope_structure(_SealedSecretEnvelope(*row[:-2]))
        finally:
            connection.close()
        _verify_name_matches_fd(root_fd, SECRET_STORE_DATABASE, store_fd)
        if os.fstat(store_fd).st_size > SECRET_STORE_MAX_BYTES:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)


def _health(state: SecretStoreHealthState, finding: SecretStoreFindingCode) -> SecretStoreHealth:
    return SecretStoreHealth(state=state, finding_codes=(finding,))


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_canonical_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        return False
    try:
        observed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return _utc_timestamp_for(observed) == value


def _utc_timestamp_for(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        return ""
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=1)
def _expected_schema_inventory() -> tuple[tuple[str, str, str], ...]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.executescript(_SCHEMA_DDL)
        return tuple(
            connection.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
        )
    finally:
        connection.close()


def _open_dir_at(parent_fd: int, name: str) -> int:
    return os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=parent_fd,
    )


def _open_regular_at(parent_fd: int, name: str) -> int:
    return os.open(
        name,
        os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=parent_fd,
    )


def _bounded_directory_names(descriptor: int, *, maximum: int = MAX_DIRECTORY_ENTRIES) -> set[str]:
    names: set[str] = set()
    with os.scandir(descriptor) as entries:
        for entry in entries:
            if len(names) >= maximum:
                raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)
            names.add(entry.name)
    return names


def _validate_directory_fd(descriptor: int, identity: _RuntimeIdentity, *, exact_mode: int) -> None:
    details = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != identity.uid
        or details.st_gid != identity.gid
        or stat.S_IMODE(details.st_mode) != exact_mode
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_PERMISSION_INVALID)


def _validate_trusted_system_directory(descriptor: int) -> None:
    details = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != 0
        or details.st_gid != 0
        or stat.S_IMODE(details.st_mode) & 0o022
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_PERMISSION_INVALID)


def _validate_regular_fd(descriptor: int, identity: _RuntimeIdentity, *, exact_mode: int) -> None:
    details = os.fstat(descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or details.st_uid != identity.uid
        or details.st_gid != identity.gid
        or stat.S_IMODE(details.st_mode) != exact_mode
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_PERMISSION_INVALID)


def _verify_name_matches_fd(parent_fd: int, name: str, descriptor: int) -> None:
    opened = os.fstat(descriptor)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        opened.st_dev != named.st_dev
        or opened.st_ino != named.st_ino
        or stat.S_IFMT(opened.st_mode) != stat.S_IFMT(named.st_mode)
    ):
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)


def _write_exclusive_file(parent_fd: int, name: str, payload: bytes | bytearray, mode: int) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        mode,
        dir_fd=parent_fd,
    )
    try:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError(errno.EIO, "short write")
            written += count
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_atomic_file(
    parent_fd: int,
    staging_name: str,
    final_name: str,
    payload: bytes,
    mode: int,
) -> None:
    _write_exclusive_file(parent_fd, staging_name, payload, mode)
    _rename_noreplace(parent_fd, staging_name, parent_fd, final_name)
    os.fsync(parent_fd)


def _read_bounded_fd(descriptor: int, maximum: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    value = os.read(descriptor, maximum + 1)
    if len(value) > maximum:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_INTEGRITY_FAILED)
    return value


def _zero_buffer(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


def _rename_noreplace(old_parent_fd: int, old_name: str, new_parent_fd: int, new_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_UNAVAILABLE)
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        old_parent_fd,
        old_name.encode("ascii"),
        new_parent_fd,
        new_name.encode("ascii"),
        1,
    )
    if result != 0:
        observed_errno = ctypes.get_errno()
        if observed_errno == errno.EEXIST:
            raise SecretStoreError(SecretStoreFindingCode.SECRET_STORE_NEEDS_ATTENTION)
        raise OSError(observed_errno, os.strerror(observed_errno))
