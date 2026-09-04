"""Crash-fail-closed trust state, floors, time high-water and session signing."""

from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import os
import re
import secrets
import socket
import stat
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from agentbox_browser_trust.codec import (
    TRUSTD_MESSAGE_MAX,
    b64url_decode,
    b64url_encode,
    canonical_json,
    exact_object,
    strict_json,
)
from agentbox_browser_trust.records import (
    ValidatedEnrollment,
    create_authenticated_checkpoint,
    validate_enrollment,
)

STATE_KEYS = frozenset(
    {
        "schema_version",
        "provider_epoch",
        "store_generation",
        "bootstrap_record",
        "root_records",
        "authenticated_checkpoint",
        "pin_record",
        "root_revision",
        "pin_revision",
        "pin_record_sha256",
        "runtime_attestation_fingerprint",
        "retired_pin_fingerprints",
        "retired_root_key_ids",
        "revoked_root_key_ids",
        "installation_fingerprint",
        "origin",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "network_policy",
        "trusted_utc",
        "journal_digest",
    }
)
ENROLLMENT_KEYS = frozenset(
    {
        "schema_version",
        "bootstrap_record",
        "root_records",
        "pin_record",
        "network_policy",
    }
)
JOURNAL_KEYS = frozenset(
    {
        "schema_version",
        "sequence",
        "previous_digest",
        "state_digest",
        "root_revision",
        "pin_revision",
        "trusted_utc",
    }
)
TIME_KEYS = frozenset(
    {
        "schema_version",
        "provider_epoch",
        "sequence",
        "trusted_utc",
        "signature",
    }
)
TRUST_JOURNAL_MAX = 16 * 1024 * 1024


class BrowserTrustStoreError(RuntimeError):
    """The independent trust store is unavailable or cannot prove monotonicity."""

    def __init__(self, reason: str = "lost") -> None:
        self.reason = reason
        super().__init__("browser trust store is unavailable")


def _fail(reason: str = "lost") -> NoReturn:
    raise BrowserTrustStoreError(reason)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        _fail()
    normalized = value.astimezone(UTC)
    return normalized.strftime("%Y-%m-%dT%H:%M:%S.") + f"{normalized.microsecond // 1000:03d}Z"


def _parse_utc(value: object) -> datetime:
    if type(value) is not str:
        _fail()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        _fail()
    if _utc_text(parsed) != value:
        _fail()
    return parsed


def _positive_int(value: object) -> int:
    if type(value) is not int or value < 1 or value > (1 << 53) - 1:
        _fail()
    return value


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class StoredTrustState:
    raw: bytes
    value: dict[str, object]
    enrollment: ValidatedEnrollment


class BrowserTrustStore:
    """One service-owned store; every mismatch blocks snapshots and rotation."""

    def __init__(
        self,
        directory: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        network_verifier: Callable[[str, str], bool] | None = None,
        expected_uid: int | None = None,
        expected_gid: int | None = None,
    ) -> None:
        self.directory = directory
        self.clock = clock
        self.network_verifier = network_verifier or verify_origin_network
        self.expected_uid = os.geteuid() if expected_uid is None else expected_uid
        self.expected_gid = os.getegid() if expected_gid is None else expected_gid
        self.state_path = directory / "current.v1.json"
        self.journal_path = directory / "floor-time.v1.jsonl"
        self.key_path = directory / "installation-ed25519.v1.key"
        self.time_path = directory / "trusted-time.v1.json"
        self.lock_path = directory / "writer.v1.lock"
        self._lock = threading.RLock()
        self._network_capacity = threading.BoundedSemaphore(4)
        self._network_workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="trust-dns")

    def initialize(self) -> str:
        with self._lock:
            self._ensure_directory(create=True)
            with self._process_lock(create=True):
                key_exists = os.path.lexists(self.key_path)
                state_exists = (
                    os.path.lexists(self.state_path)
                    or os.path.lexists(self.journal_path)
                    or os.path.lexists(self.time_path)
                )
                if state_exists and not key_exists:
                    _fail()
                if key_exists:
                    key = self._load_key()
                else:
                    key = Ed25519PrivateKey.generate()
                    raw = key.private_bytes(
                        serialization.Encoding.Raw,
                        serialization.PrivateFormat.Raw,
                        serialization.NoEncryption(),
                    )
                    self._atomic_write(self.key_path, raw, 0o600)
                return _digest(
                    key.public_key().public_bytes(
                        serialization.Encoding.Raw,
                        serialization.PublicFormat.Raw,
                    )
                )

    def installation_public_key(self) -> bytes:
        with self._lock, self._process_lock():
            return (
                self._load_key()
                .public_key()
                .public_bytes(
                    serialization.Encoding.Raw,
                    serialization.PublicFormat.Raw,
                )
            )

    def installation_fingerprint(self) -> str:
        return _digest(self.installation_public_key())

    def sign_session(self, value: object) -> str:
        raw = canonical_json(value, limit=4096)
        with self._lock, self._process_lock():
            return b64url_encode(self._load_key().sign(b"agentbox-waw/trustd-session/v1\0" + raw))

    def close(self) -> None:
        self._network_workers.shutdown(wait=False, cancel_futures=True)

    def _installation_fingerprint_locked(self) -> str:
        public_key = (
            self._load_key()
            .public_key()
            .public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        )
        return _digest(public_key)

    def _verify_network(self, origin: str, policy: str) -> bool:
        if not self._network_capacity.acquire(blocking=False):
            return False
        try:
            future = self._network_workers.submit(self.network_verifier, origin, policy)
        except RuntimeError:
            self._network_capacity.release()
            return False

        def release(_future: object) -> None:
            self._network_capacity.release()

        future.add_done_callback(release)
        try:
            return future.result(timeout=1.0) is True
        except Exception:
            return False

    def _candidate(
        self,
        candidate_raw: bytes,
        now: datetime,
        minimum_root: int,
        minimum_pin: int,
        old: StoredTrustState | None,
    ) -> tuple[ValidatedEnrollment, str]:
        try:
            candidate = exact_object(
                strict_json(candidate_raw, limit=TRUSTD_MESSAGE_MAX), ENROLLMENT_KEYS
            )
            if candidate["schema_version"] != "waw-trust-enrollment-v1":
                _fail()
            roots_value = candidate["root_records"]
            if type(roots_value) is not list or not 1 <= len(roots_value) <= 64:
                _fail()
            network_policy = candidate["network_policy"]
            if network_policy not in ("production", "loopback-development"):
                _fail()
            enrollment = validate_enrollment(
                b64url_decode(candidate["bootstrap_record"], limit=4096),
                tuple(b64url_decode(value, limit=4096) for value in roots_value),
                b64url_decode(candidate["pin_record"], limit=4096),
                now=now,
                minimum_root_revision=minimum_root,
                minimum_pin_revision=minimum_pin,
                authenticated_checkpoint=(
                    old.value["authenticated_checkpoint"] if old is not None else None
                ),
                retired_root_key_ids=(
                    self._root_key_ids(old.value["retired_root_key_ids"])
                    if old is not None
                    else frozenset()
                ),
                revoked_root_key_ids=(
                    self._root_key_ids(old.value["revoked_root_key_ids"])
                    if old is not None
                    else frozenset()
                ),
            )
            return enrollment, network_policy
        except ValueError:
            _fail()

    def install(self, candidate_raw: bytes) -> StoredTrustState:
        with self._lock, self._process_lock():
            self._ensure_directory(create=False)
            observed_old = self._load_optional()
        preliminary, network_policy = self._candidate(
            candidate_raw,
            self.clock(),
            observed_old.enrollment.root_revision if observed_old else 0,
            observed_old.enrollment.pin_revision if observed_old else 0,
            observed_old,
        )
        if not self._verify_network(preliminary.origin, network_policy):
            _fail("changed")
        with self._lock, self._process_lock():
            self._ensure_directory(create=False)
            old = self._load_optional()
            now = self.clock()
            minimum_root = old.enrollment.root_revision if old else 0
            minimum_pin = old.enrollment.pin_revision if old else 0
            enrollment, locked_policy = self._candidate(
                candidate_raw, now, minimum_root, minimum_pin, old
            )
            if locked_policy != network_policy or enrollment.origin != preliminary.origin:
                _fail("changed")
            if old and enrollment.origin != old.enrollment.origin:
                _fail()
            if old and _parse_utc(self._read_time(old)["trusted_utc"]) > now:
                _fail("time-backward")
            if (
                old
                and enrollment.bootstrap_record == old.enrollment.bootstrap_record
                and enrollment.root_records == old.enrollment.root_records
                and enrollment.pin_record == old.enrollment.pin_record
                and network_policy == old.value["network_policy"]
            ):
                return old
            retired_pin_fingerprints: list[str] = []
            if old:
                old_roots = old.enrollment.root_records
                if enrollment.root_revision == old.enrollment.root_revision and (
                    enrollment.root_records != old_roots
                    or enrollment.authenticated_checkpoint != old.value["authenticated_checkpoint"]
                ):
                    _fail()
                if enrollment.root_revision > old.enrollment.root_revision and (
                    len(enrollment.root_records) <= len(old_roots)
                    or enrollment.root_records[: len(old_roots)] != old_roots
                ):
                    _fail()
                # A persisted checkpoint can advance only one root transition
                # per atomic install. Reject a proposed ACTIVE+REVOKED batch
                # before journal, time, or state writes can begin.
                if len(enrollment.root_records) > len(old_roots) + 1:
                    _fail()
                retired_value = old.value["retired_pin_fingerprints"]
                if type(retired_value) is not list or any(
                    type(item) is not str or not re.fullmatch(r"[a-f0-9]{64}", item)
                    for item in retired_value
                ):
                    _fail()
                retired_pin_fingerprints = list(retired_value)
                if enrollment.pin_revision == old.enrollment.pin_revision:
                    _fail()
                if (
                    enrollment.pin_supersedes_fingerprint
                    != old.enrollment.runtime_attestation_fingerprint
                ):
                    _fail()
                if enrollment.pin_revoked_at is not None:
                    if (
                        enrollment.runtime_attestation_fingerprint
                        != old.enrollment.runtime_attestation_fingerprint
                    ):
                        _fail()
                elif (
                    enrollment.runtime_attestation_fingerprint
                    == old.enrollment.runtime_attestation_fingerprint
                    or enrollment.runtime_attestation_fingerprint in retired_pin_fingerprints
                    or _parse_utc(enrollment.pin_valid_from)
                    <= _parse_utc(old.enrollment.pin_valid_until)
                ):
                    _fail()
                if old.enrollment.runtime_attestation_fingerprint not in retired_pin_fingerprints:
                    retired_pin_fingerprints.append(old.enrollment.runtime_attestation_fingerprint)
            generation = _positive_int(old.value["store_generation"]) + 1 if old else 1
            trusted_utc = _utc_text(now)
            provider_epoch = "pte_" + secrets.token_hex(16)
            checkpoint = (
                old.value["authenticated_checkpoint"]
                if old is not None
                and (
                    enrollment.root_revision == old.enrollment.root_revision
                    or not enrollment.root_active
                )
                else create_authenticated_checkpoint(enrollment.root_records, trusted_utc)
            )
            state_without_journal: dict[str, object] = {
                "schema_version": "waw-browser-trust-state-v1",
                "provider_epoch": provider_epoch,
                "store_generation": generation,
                "bootstrap_record": b64url_encode(enrollment.bootstrap_record),
                "root_records": [b64url_encode(value) for value in enrollment.root_records],
                "authenticated_checkpoint": checkpoint,
                "pin_record": b64url_encode(enrollment.pin_record),
                "root_revision": enrollment.root_revision,
                "pin_revision": enrollment.pin_revision,
                "pin_record_sha256": enrollment.pin_record_sha256,
                "runtime_attestation_fingerprint": enrollment.runtime_attestation_fingerprint,
                "retired_pin_fingerprints": retired_pin_fingerprints,
                "retired_root_key_ids": sorted(enrollment.retired_root_key_ids),
                "revoked_root_key_ids": sorted(enrollment.revoked_root_key_ids),
                "installation_fingerprint": self._installation_fingerprint_locked(),
                "origin": enrollment.origin,
                "runtime_host_installation_id": enrollment.runtime_host_installation_id,
                "runtime_host_installation_revision": enrollment.runtime_host_installation_revision,
                "network_policy": network_policy,
                "trusted_utc": trusted_utc,
            }
            state_digest = _digest(canonical_json(state_without_journal))
            previous_digest = old.value["journal_digest"] if old else "0" * 64
            if type(previous_digest) is not str:
                _fail()
            entry = {
                "schema_version": "waw-browser-trust-floor-time-v1",
                "sequence": generation,
                "previous_digest": previous_digest,
                "state_digest": state_digest,
                "root_revision": enrollment.root_revision,
                "pin_revision": enrollment.pin_revision,
                "trusted_utc": trusted_utc,
            }
            journal_raw = canonical_json(entry)
            journal_digest = _digest(journal_raw)
            state = {**state_without_journal, "journal_digest": journal_digest}
            state_raw = canonical_json(state)
            time_raw = self._encode_time(provider_epoch, 1, trusted_utc)
            self._append_journal(journal_raw)
            self._atomic_write(self.time_path, time_raw, 0o600)
            self._atomic_write(self.state_path, state_raw, 0o600)
            return self._decode_state(state_raw, now=now)

    def snapshot(self) -> dict[str, object]:
        with self._lock, self._process_lock():
            state = self._load_required()
            observed_epoch = state.value["provider_epoch"]
            observed_generation = state.value["store_generation"]
            observed_origin = state.enrollment.origin
            observed_policy = str(state.value["network_policy"])
        if not self._verify_network(observed_origin, observed_policy):
            _fail("changed")
        with self._lock, self._process_lock():
            state = self._load_required()
            if (
                state.value["provider_epoch"] != observed_epoch
                or state.value["store_generation"] != observed_generation
                or state.enrollment.origin != observed_origin
                or state.value["network_policy"] != observed_policy
            ):
                _fail("changed")
            now = self.clock()
            time_value = self._read_time(state)
            previous_time = _parse_utc(time_value["trusted_utc"])
            if now < previous_time:
                _fail("time-backward")
            # Persist the time high-water before exposing a new trusted instant.
            if _utc_text(now) != time_value["trusted_utc"]:
                time_value = self._advance_time(state, time_value, now)
            value = state.value
            return {
                "schema_version": "waw-trust-provider-snapshot-v1",
                "provider_epoch": value["provider_epoch"],
                "bootstrap_record": value["bootstrap_record"],
                "root_records": value["root_records"],
                "pin_record": value["pin_record"],
                "authenticated_checkpoint": value["authenticated_checkpoint"],
                "persisted_floors": {
                    "root_revision": value["root_revision"],
                    "pin": {
                        "origin": value["origin"],
                        "runtime_host_installation_id": value["runtime_host_installation_id"],
                        "pin_revision": value["pin_revision"],
                    },
                },
                "trusted_time": {
                    "utc": time_value["trusted_utc"],
                    "non_backward": True,
                },
                "origin_network_proof": {
                    "effective_origin": value["origin"],
                    "admitted_api_origin": value["origin"],
                    "runtime_host_installation_id": value["runtime_host_installation_id"],
                    "network_policy": value["network_policy"],
                    "verified": True,
                },
            }

    def _encode_time(self, provider_epoch: str, sequence: int, trusted_utc: str) -> bytes:
        body = {
            "schema_version": "waw-browser-trust-time-v1",
            "provider_epoch": provider_epoch,
            "sequence": sequence,
            "trusted_utc": trusted_utc,
        }
        signature = self._load_key().sign(
            b"agentbox-waw/trusted-time/v1\0" + canonical_json(body, limit=4096)
        )
        return canonical_json({**body, "signature": b64url_encode(signature)}, limit=4096)

    def _read_time(self, state: StoredTrustState) -> dict[str, object]:
        raw = self._read_regular(self.time_path, 0o600, 4096)
        value = exact_object(strict_json(raw, limit=4096), TIME_KEYS)
        if (
            value["schema_version"] != "waw-browser-trust-time-v1"
            or value["provider_epoch"] != state.value["provider_epoch"]
        ):
            _fail()
        _positive_int(value["sequence"])
        trusted = _parse_utc(value["trusted_utc"])
        if trusted < _parse_utc(state.value["trusted_utc"]):
            _fail()
        signature = b64url_decode(value["signature"], size=64, limit=64)
        body = {key: item for key, item in value.items() if key != "signature"}
        public_key = (
            self._load_key()
            .public_key()
            .public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        )
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature,
                b"agentbox-waw/trusted-time/v1\0" + canonical_json(body, limit=4096),
            )
        except (InvalidSignature, ValueError):
            _fail()
        return value

    def _advance_time(
        self,
        state: StoredTrustState,
        old: dict[str, object],
        now: datetime,
    ) -> dict[str, object]:
        raw = self._encode_time(
            str(state.value["provider_epoch"]),
            _positive_int(old["sequence"]) + 1,
            _utc_text(now),
        )
        self._atomic_write(self.time_path, raw, 0o600)
        return exact_object(strict_json(raw, limit=4096), TIME_KEYS)

    def _load_optional(self) -> StoredTrustState | None:
        if (
            not self.state_path.exists()
            and not self.journal_path.exists()
            and not self.time_path.exists()
        ):
            return None
        return self._load_required()

    def _load_required(self) -> StoredTrustState:
        try:
            self._ensure_directory(create=False)
            state_raw = self._read_regular(self.state_path, 0o600, TRUSTD_MESSAGE_MAX)
            state = self._decode_state(state_raw, now=self.clock())
            if state.value["installation_fingerprint"] != self._installation_fingerprint_locked():
                _fail()
            self._read_time(state)
            return state
        except (OSError, ValueError):
            _fail()

    def _decode_state(self, raw: bytes, *, now: datetime) -> StoredTrustState:
        value = exact_object(strict_json(raw), STATE_KEYS)
        if value["schema_version"] != "waw-browser-trust-state-v1":
            _fail()
        generation = _positive_int(value["store_generation"])
        roots_value = value["root_records"]
        if type(roots_value) is not list:
            _fail()
        persisted_time = _parse_utc(value["trusted_utc"])
        enrollment = validate_enrollment(
            b64url_decode(value["bootstrap_record"], limit=4096),
            tuple(b64url_decode(item, limit=4096) for item in roots_value),
            b64url_decode(value["pin_record"], limit=4096),
            now=max(now, persisted_time),
            minimum_root_revision=_positive_int(value["root_revision"]),
            minimum_pin_revision=_positive_int(value["pin_revision"]),
            authenticated_checkpoint=value["authenticated_checkpoint"],
            retired_root_key_ids=self._root_key_ids(value["retired_root_key_ids"]),
            revoked_root_key_ids=self._root_key_ids(value["revoked_root_key_ids"]),
            verify_persisted_tombstones=True,
        )
        if (
            value["root_revision"] != enrollment.root_revision
            or value["pin_revision"] != enrollment.pin_revision
            or value["pin_record_sha256"] != enrollment.pin_record_sha256
            or value["runtime_attestation_fingerprint"]
            != enrollment.runtime_attestation_fingerprint
            or value["origin"] != enrollment.origin
            or value["runtime_host_installation_id"] != enrollment.runtime_host_installation_id
            or value["runtime_host_installation_revision"]
            != enrollment.runtime_host_installation_revision
            or value["network_policy"] not in ("production", "loopback-development")
        ):
            _fail()
        retired = value["retired_pin_fingerprints"]
        if (
            type(retired) is not list
            or len(retired) > 4096
            or len(set(retired)) != len(retired)
            or any(
                type(item) is not str or not re.fullmatch(r"[a-f0-9]{64}", item) for item in retired
            )
            or (
                enrollment.pin_revoked_at is None
                and enrollment.runtime_attestation_fingerprint in retired
            )
        ):
            _fail()
        last = self._verify_journal()
        if (
            last["sequence"] != generation
            or last["journal_digest"] != value["journal_digest"]
            or last["root_revision"] != enrollment.root_revision
            or last["pin_revision"] != enrollment.pin_revision
            or last["trusted_utc"] != value["trusted_utc"]
        ):
            _fail()
        state_without_journal = {
            key: item for key, item in value.items() if key != "journal_digest"
        }
        if last["state_digest"] != _digest(canonical_json(state_without_journal)):
            _fail()
        return StoredTrustState(raw=raw, value=value, enrollment=enrollment)

    @staticmethod
    def _root_key_ids(value: object) -> frozenset[str]:
        if (
            type(value) is not list
            or len(value) > 4096
            or len(set(value)) != len(value)
            or any(
                type(item) is not str or not re.fullmatch(r"[a-z0-9._-]{1,64}", item)
                for item in value
            )
        ):
            _fail()
        return frozenset(value)

    def _verify_journal(self) -> dict[str, object]:
        raw = self._read_regular(self.journal_path, 0o600, TRUST_JOURNAL_MAX)
        lines = raw.splitlines()
        if not lines or len(lines) > 1_000_000:
            _fail()
        previous = "0" * 64
        last: dict[str, object] | None = None
        for index, line in enumerate(lines, 1):
            entry = exact_object(strict_json(line), JOURNAL_KEYS)
            if (
                entry["schema_version"] != "waw-browser-trust-floor-time-v1"
                or _positive_int(entry["sequence"]) != index
                or entry["previous_digest"] != previous
            ):
                _fail()
            digest = _digest(line)
            previous = digest
            last = {**entry, "journal_digest": digest}
        assert last is not None
        return last

    def _append_journal(self, raw: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.journal_path, flags, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                _fail()
            if info.st_uid != self.expected_uid or info.st_gid != self.expected_gid:
                _fail()
            payload = raw + b"\n"
            if info.st_size + len(payload) > TRUST_JOURNAL_MAX:
                _fail()
            written = 0
            while written < len(payload):
                count = os.write(descriptor, payload[written:])
                if count < 1:
                    _fail()
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _atomic_write(self, path: Path, raw: bytes, mode: int) -> None:
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(16)}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, mode)
        try:
            written = 0
            while written < len(raw):
                count = os.write(descriptor, raw[written:])
                if count < 1:
                    _fail()
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        directory_fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _read_regular(self, path: Path, mode: int, limit: int) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != mode
                or info.st_uid != self.expected_uid
                or info.st_gid != self.expected_gid
                or info.st_size < 1
                or info.st_size > limit
            ):
                _fail()
            raw = os.read(descriptor, limit + 1)
            if len(raw) != info.st_size:
                _fail()
            return raw
        finally:
            os.close(descriptor)

    def _load_key(self) -> Ed25519PrivateKey:
        self._ensure_directory(create=False)
        raw = self._read_regular(self.key_path, 0o600, 32)
        if len(raw) != 32:
            _fail()
        try:
            return Ed25519PrivateKey.from_private_bytes(raw)
        except ValueError:
            _fail()

    @contextmanager
    def _process_lock(self, *, create: bool = False) -> Iterator[None]:
        flags = os.O_RDWR | (os.O_CREAT if create else 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
        except OSError:
            _fail()
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != self.expected_uid
                or info.st_gid != self.expected_gid
            ):
                _fail()
            deadline = time.monotonic() + 1.0
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        _fail()
                    time.sleep(0.01)
            info = os.fstat(descriptor)
            if info.st_size == 0:
                if not create:
                    _fail()
                os.write(descriptor, b"waw-browser-trust-writer-v1\n")
                os.fsync(descriptor)
            else:
                if info.st_size > 128:
                    _fail()
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.read(descriptor, 129) != b"waw-browser-trust-writer-v1\n":
                    _fail()
            yield
        finally:
            with suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _ensure_directory(self, *, create: bool) -> None:
        if create:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != self.expected_uid
            or info.st_gid != self.expected_gid
        ):
            _fail()
        allowed = {
            self.state_path.name,
            self.journal_path.name,
            self.key_path.name,
            self.time_path.name,
            self.lock_path.name,
        }
        children = list(self.directory.iterdir())
        if len(children) > len(allowed) or any(child.name not in allowed for child in children):
            _fail()


def verify_origin_network(origin: str, policy: str) -> bool:
    host = urlsplit(origin).hostname
    if not host or policy not in ("production", "loopback-development"):
        return False
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError):
        return False
    if not addresses:
        return False
    if policy == "loopback-development":
        return host in {"127.0.0.1", "::1"} and all(address.is_loopback for address in addresses)
    return all(
        not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        )
        for address in addresses
    )
