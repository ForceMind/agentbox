"""Independent tmp-only K2 metadata journal, not a production Runtime store.

A bounded canonical snapshot contains records AND their derived active-turn
slots. A held-directory nonblocking flock serializes every read/CAS/write.
Explicit recovery retires all unfinished claims to UNKNOWN, never dispatches.
File/directory fsync barriers establish only local software commit discipline,
not real power-loss qualification, malicious rollback detection or writer rights.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from agentbox_core.kebui_observation import KebuiObservationError, parse_scope

from .kebui_admission import (
    FINISHED_PHASES,
    MAX_REVISION,
    AdmissionPhase,
    AdmissionRecord,
    AdmissionRequest,
    KebuiAdmissionError,
    scope_metadata,
    validate_id,
    validate_revision,
)

MAX_RECORDS = 255
RECORD_RESERVED_BYTES = 4096
HEADER_RESERVED_BYTES = 4096
MAX_SNAPSHOT_BYTES = 1024 * 1024
_SCHEMA = "kebui-synthetic-admission-v1"
_FILENAME = "admission.json"
_RECORD_FIELDS = {
    "request",
    "execution_id",
    "phase",
    "record_revision",
    "receipt_ref",
    "terminal_status",
}
_REQUEST_FIELDS = {"request_id", "scope", "adapter_profile", "content_admission_ref", "operation"}


@dataclass(frozen=True, slots=True)
class _Snapshot:
    journal_revision: str
    records: tuple[AdmissionRecord, ...]


def _request_dict(request: AdmissionRequest) -> dict[str, object]:
    return {
        "request_id": request.request_id,
        "scope": scope_metadata(request.scope),
        "adapter_profile": request.adapter_profile,
        "content_admission_ref": request.content_admission_ref,
        "operation": request.operation,
    }


def _record_dict(record: AdmissionRecord) -> dict[str, object]:
    return {
        "request": _request_dict(record.request),
        "execution_id": record.execution_id,
        "phase": record.phase.value,
        "record_revision": record.record_revision,
        "receipt_ref": record.receipt_ref,
        "terminal_status": record.terminal_status,
    }


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def reserved_record_bytes(record: AdmissionRecord) -> int:
    """Measure the largest complete framed successor, not today's short record.

    All admitted strings are bounded ASCII. UTF-8, quotes, delimiters and null
    slots are nevertheless charged as bytes by the actual canonical encoder.
    """
    value = _record_dict(record)
    value["record_revision"] = str(MAX_REVISION)
    value["phase"] = max((phase.value for phase in AdmissionPhase), key=len)
    value["receipt_ref"] = "krcp_" + "f" * 32
    value["terminal_status"] = "completed"
    return len(_json(value)) + 1  # including the list delimiter


def _encode(snapshot: _Snapshot) -> bytes:
    if len(snapshot.records) > MAX_RECORDS:
        raise KebuiAdmissionError("capacity")
    header = {"schema_version": _SCHEMA, "journal_revision": str(MAX_REVISION), "records": []}
    if len(_json(header)) + 1 > HEADER_RESERVED_BYTES:
        raise KebuiAdmissionError("capacity")
    if any(reserved_record_bytes(record) > RECORD_RESERVED_BYTES for record in snapshot.records):
        raise KebuiAdmissionError("capacity")
    payload = (
        _json(
            {
                "schema_version": _SCHEMA,
                "journal_revision": snapshot.journal_revision,
                "records": [_record_dict(record) for record in snapshot.records],
            }
        )
        + b"\n"
    )
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise KebuiAdmissionError("capacity")
    return payload


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or value.keys() != fields:
        raise KebuiAdmissionError("invalid_snapshot")
    return cast(dict[str, object], value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise KebuiAdmissionError("invalid_snapshot")
        result[key] = value
    return result


def _slot(record: AdmissionRecord) -> tuple[str, str, str]:
    scope = record.request.scope
    return scope.host_id, scope.project_id, scope.agent_type.value


def _decode(payload: bytes) -> _Snapshot:
    try:
        root = _object(
            json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object),
            {"schema_version", "journal_revision", "records"},
        )
        if root["schema_version"] != _SCHEMA:
            raise KebuiAdmissionError("invalid_snapshot")
        revision = validate_revision(root["journal_revision"])
        values = root["records"]
        if type(values) is not list or len(values) > MAX_RECORDS:
            raise KebuiAdmissionError("invalid_snapshot")
        records = []
        seen: set[str] = set()
        slots: set[tuple[str, str, str]] = set()
        for value in values:
            row = _object(value, _RECORD_FIELDS)
            req = _object(row["request"], _REQUEST_FIELDS)
            request = AdmissionRequest(
                request_id=cast(str, req["request_id"]),
                scope=parse_scope(req["scope"]),
                adapter_profile=cast(str, req["adapter_profile"]),
                content_admission_ref=cast(str, req["content_admission_ref"]),
                operation=cast(str, req["operation"]),
            )
            if type(row["phase"]) is not str:
                raise KebuiAdmissionError("invalid_snapshot")
            record = AdmissionRecord(
                request=request,
                execution_id=cast(str, row["execution_id"]),
                phase=AdmissionPhase(row["phase"]),
                record_revision=validate_revision(row["record_revision"]),
                receipt_ref=cast(str | None, row["receipt_ref"]),
                terminal_status=cast(str | None, row["terminal_status"]),
            )
            if request.request_id in seen or int(record.record_revision) > int(revision):
                raise KebuiAdmissionError("invalid_snapshot")
            seen.add(request.request_id)
            if record.phase not in FINISHED_PHASES:
                if _slot(record) in slots:
                    raise KebuiAdmissionError("invalid_snapshot")
                slots.add(_slot(record))
            records.append(record)
        snapshot = _Snapshot(revision, tuple(records))
        if _encode(snapshot) != payload:
            raise KebuiAdmissionError("invalid_snapshot")
        return snapshot
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, KebuiObservationError):
        raise KebuiAdmissionError("invalid_snapshot") from None


def _next(revision: str) -> str:
    if int(revision) >= MAX_REVISION:
        raise KebuiAdmissionError("revision_exhausted")
    return str(int(revision) + 1)


class KebuiAdmissionJournal:
    """Explicit synthetic initialization, recovery or read-only observation.

    ``open_existing(recover=True)`` is test-owner recovery, not reader authority:
    it durably retires every unfinished claim. ``recover=False`` permits reads
    only. A second live instance never acquires another instance's dispatch claim.
    Neither path is wired into production or proves current execution ownership.
    """

    def __init__(self, directory: Path, *, expected_uid: int, expected_gid: int) -> None:
        if not isinstance(directory, Path) or not directory.is_absolute():
            raise KebuiAdmissionError("invalid_directory")
        if (
            type(expected_uid) is not int
            or expected_uid < 0
            or type(expected_gid) is not int
            or expected_gid < 0
        ):
            raise KebuiAdmissionError("invalid_directory")
        self._directory = directory
        self._uid, self._gid = expected_uid, expected_gid
        self._pid = os.getpid()
        self._fd = -1
        self._fenced = False
        self._readonly = True
        self._mutex = threading.Lock()
        self._live: set[str] = set()
        try:
            before = os.lstat(directory)
            self._validate_directory(before)
            self._fd = os.open(
                directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
            )
            self._identity = (before.st_dev, before.st_ino)
            self._check_directory()
        except (OSError, KebuiAdmissionError):
            self.close()
            raise KebuiAdmissionError("invalid_directory") from None

    @classmethod
    def initialize_for_test(
        cls, directory: Path, *, expected_uid: int, expected_gid: int
    ) -> KebuiAdmissionJournal:
        journal = cls(directory, expected_uid=expected_uid, expected_gid=expected_gid)
        try:
            with journal._locked():
                journal._check_inventory(empty=True)
                try:
                    os.stat(_FILENAME, dir_fd=journal._fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise KebuiAdmissionError("already_initialized")
                journal._commit(_Snapshot("1", ()))
            journal._readonly = False
            return journal
        except BaseException:
            journal.close()
            raise

    @classmethod
    def open_existing(
        cls, directory: Path, *, expected_uid: int, expected_gid: int, recover: bool = True
    ) -> KebuiAdmissionJournal:
        journal = cls(directory, expected_uid=expected_uid, expected_gid=expected_gid)
        try:
            with journal._locked():
                snapshot = journal._read_barrier()
                if recover is True:
                    records = tuple(
                        (
                            replace(
                                record,
                                phase=AdmissionPhase.UNKNOWN,
                                record_revision=_next(record.record_revision),
                            )
                            if record.phase not in FINISHED_PHASES
                            and record.phase is not AdmissionPhase.UNKNOWN
                            else record
                        )
                        for record in snapshot.records
                    )
                    if records != snapshot.records:
                        journal._commit(_Snapshot(_next(snapshot.journal_revision), records))
                    journal._readonly = False
            return journal
        except BaseException:
            journal.close()
            raise

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
        self._live.clear()

    def __enter__(self) -> KebuiAdmissionJournal:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _validate_directory(self, details: os.stat_result) -> None:
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != self._uid
            or details.st_gid != self._gid
            or stat.S_IMODE(details.st_mode) != 0o700
            or details.st_nlink < 2
        ):
            raise KebuiAdmissionError("invalid_directory")

    def _check_directory(self) -> None:
        held = os.fstat(self._fd)
        current = os.lstat(self._directory)
        for details in (held, current):
            self._validate_directory(details)
            if (details.st_dev, details.st_ino) != self._identity:
                raise KebuiAdmissionError("directory_changed")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if self._fenced or self._fd < 0 or os.getpid() != self._pid:
            raise KebuiAdmissionError("store_unavailable")
        if not self._mutex.acquire(blocking=False):
            raise KebuiAdmissionError("busy")
        locked = False
        try:
            self._check_directory()
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                raise KebuiAdmissionError("busy") from None
            self._check_directory()
            yield
            self._check_directory()
        except OSError:
            self._fenced = True
            raise KebuiAdmissionError("store_unavailable") from None
        except KebuiAdmissionError as exc:
            if str(exc) not in {
                "busy",
                "capacity",
                "conflict",
                "not_observed",
                "cas_conflict",
                "claim_retired",
                "invalid_transition",
                "already_initialized",
                "read_only",
                "invalid_metadata",
            }:
                self._fenced = True
            raise
        finally:
            if locked:
                with suppress(OSError):
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._mutex.release()

    def _validate_file(self, details: os.stat_result) -> None:
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or details.st_uid != self._uid
            or details.st_gid != self._gid
            or stat.S_IMODE(details.st_mode) != 0o600
            or not 0 < details.st_size <= MAX_SNAPSHOT_BYTES
        ):
            raise KebuiAdmissionError("invalid_snapshot")

    def _file_identity(self, fd: int, before: os.stat_result) -> None:
        for current in (os.fstat(fd), os.stat(_FILENAME, dir_fd=self._fd, follow_symlinks=False)):
            self._validate_file(current)
            if (
                current.st_dev,
                current.st_ino,
                current.st_size,
                current.st_mtime_ns,
                current.st_ctime_ns,
            ) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ):
                raise KebuiAdmissionError("snapshot_changed")
        self._check_directory()

    def _check_inventory(self, *, empty: bool = False) -> None:
        # A dedicated directory has only one committed snapshot. Examine at most
        # two entries; never list an unbounded directory or delete orphan files.
        with os.scandir(self._fd) as entries:
            first = next(entries, None)
            if empty:
                if first is not None:
                    raise KebuiAdmissionError("invalid_inventory")
            elif first is None or first.name != _FILENAME or next(entries, None) is not None:
                raise KebuiAdmissionError("invalid_inventory")

    def _read_barrier(self) -> _Snapshot:
        # Every read performs the barrier, including cross-instance new snapshots.
        # Observing visible TERMINAL alone never releases a slot or proves commit.
        self._check_inventory()
        fd = os.open(
            _FILENAME, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._fd
        )
        try:
            before = os.fstat(fd)
            self._validate_file(before)
            chunks = []
            remaining = MAX_SNAPSHOT_BYTES + 1
            while remaining:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            payload = b"".join(chunks)
            if len(payload) != before.st_size or len(payload) > MAX_SNAPSHOT_BYTES:
                raise KebuiAdmissionError("invalid_snapshot")
            snapshot = _decode(payload)
            self._file_identity(fd, before)
            os.fsync(fd)
            os.fsync(self._fd)
            self._file_identity(fd, before)
            self._check_inventory()
            return snapshot
        finally:
            os.close(fd)

    def _commit(self, snapshot: _Snapshot) -> None:
        payload = _encode(snapshot)
        name = ".admission-" + secrets.token_hex(16) + ".tmp"
        try:
            self._check_directory()
            fd = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=self._fd,
            )
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
                os.fsync(fd)
                before = os.fstat(fd)
                self._validate_file(before)
                temp = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
                if (temp.st_dev, temp.st_ino) != (before.st_dev, before.st_ino):
                    raise KebuiAdmissionError("snapshot_changed")
                self._check_directory()
                os.replace(name, _FILENAME, src_dir_fd=self._fd, dst_dir_fd=self._fd)
                os.fsync(self._fd)
                # rename may change ctime; compare against the held inode after
                # rename, whose identity still comes from our open temporary FD.
                after = os.fstat(fd)
                if (after.st_dev, after.st_ino, after.st_size) != (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                ):
                    raise KebuiAdmissionError("snapshot_changed")
                self._file_identity(fd, after)
            finally:
                os.close(fd)
            if self._read_barrier() != snapshot:
                raise KebuiAdmissionError("snapshot_changed")
        except (OSError, KebuiAdmissionError):
            self._fenced = True
            raise KebuiAdmissionError("commit_uncertain") from None
        finally:
            with suppress(OSError):
                os.unlink(name, dir_fd=self._fd)

    @staticmethod
    def _find(snapshot: _Snapshot, request: AdmissionRequest) -> AdmissionRecord | None:
        if type(request) is not AdmissionRequest:
            raise KebuiAdmissionError("invalid_metadata")
        for record in snapshot.records:
            if record.request.request_id == request.request_id:
                if record.request != request:
                    raise KebuiAdmissionError("conflict")
                return record
        return None

    def read(self, request: AdmissionRequest) -> AdmissionRecord | None:
        """None is NOT_OBSERVED, never proof a previous effect did not occur."""
        with self._locked():
            return self._find(self._read_barrier(), request)

    def accept(self, request: AdmissionRequest, execution_id: str) -> tuple[AdmissionRecord, bool]:
        validate_id(execution_id, "kexe_")
        if self._readonly:
            raise KebuiAdmissionError("read_only")
        with self._locked():
            snapshot = self._read_barrier()
            existing = self._find(snapshot, request)
            if existing is not None:
                if existing.execution_id != execution_id:
                    raise KebuiAdmissionError("conflict")
                return existing, False
            record = AdmissionRecord(request, execution_id, AdmissionPhase.ACCEPTED, "1")
            if (
                len(snapshot.records) >= MAX_RECORDS
                or reserved_record_bytes(record) > RECORD_RESERVED_BYTES
            ):
                raise KebuiAdmissionError("capacity")
            if any(
                item.phase not in FINISHED_PHASES and _slot(item) == _slot(record)
                for item in snapshot.records
            ):
                raise KebuiAdmissionError("busy")
            self._commit(_Snapshot(_next(snapshot.journal_revision), (*snapshot.records, record)))
            self._live.add(request.request_id)
            return record, True

    def transition(
        self,
        request: AdmissionRequest,
        expected_revision: str,
        phase: AdmissionPhase,
        *,
        receipt_ref: str | None = None,
        terminal_status: str | None = None,
    ) -> AdmissionRecord:
        validate_revision(expected_revision)
        if type(phase) is not AdmissionPhase:
            raise KebuiAdmissionError("invalid_metadata")
        if self._readonly:
            raise KebuiAdmissionError("read_only")
        with self._locked():
            snapshot = self._read_barrier()
            record = self._find(snapshot, request)
            if record is None:
                raise KebuiAdmissionError("not_observed")
            if record.record_revision != expected_revision:
                raise KebuiAdmissionError("cas_conflict")
            if request.request_id not in self._live:
                raise KebuiAdmissionError("claim_retired")
            allowed = {
                AdmissionPhase.ACCEPTED: {
                    AdmissionPhase.DISPATCH_FENCED,
                    AdmissionPhase.REJECTED_BEFORE_DISPATCH,
                    AdmissionPhase.UNKNOWN,
                },
                AdmissionPhase.DISPATCH_FENCED: {
                    AdmissionPhase.ACKNOWLEDGED,
                    AdmissionPhase.TERMINAL,
                    AdmissionPhase.UNKNOWN,
                },
                AdmissionPhase.ACKNOWLEDGED: {AdmissionPhase.TERMINAL, AdmissionPhase.UNKNOWN},
            }
            if phase not in allowed.get(record.phase, set()):
                raise KebuiAdmissionError("invalid_transition")
            if (
                phase is AdmissionPhase.TERMINAL
                and record.phase is AdmissionPhase.ACKNOWLEDGED
                and receipt_ref != record.receipt_ref
            ):
                raise KebuiAdmissionError("conflict")
            if phase is AdmissionPhase.UNKNOWN:
                if receipt_ref is not None or terminal_status is not None:
                    raise KebuiAdmissionError("invalid_metadata")
                receipt_ref = record.receipt_ref
            updated = replace(
                record,
                phase=phase,
                record_revision=_next(record.record_revision),
                receipt_ref=receipt_ref,
                terminal_status=terminal_status,
            )
            records = tuple(
                updated if item.request.request_id == request.request_id else item
                for item in snapshot.records
            )
            self._commit(_Snapshot(_next(snapshot.journal_revision), records))
            if phase in FINISHED_PHASES or phase is AdmissionPhase.UNKNOWN:
                self._live.discard(request.request_id)
            return updated
