"""Runtime-only durable storage for validated dynamic cgroup attestations.

The store persists only codec-validated metadata produced by a Runtime host
read-back layer.  It never reads cgroupfs or accepts a path/command from API or
Browser callers.  The read-back producer and its host authentication remain a
separate host gate.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from agentbox_runtime.waw_cgroup_attestation import (
    WAWCgroupAttestation,
    WAWCgroupAttestationError,
    decode_waw_cgroup_attestation,
    encode_waw_cgroup_attestation,
)

_MAX_BYTES = 64 * 1024
_MAX_RECORD_FILES = 256
_WORKSPACE_ID = re.compile(r"\Aaws_[0-9a-f]{32}\Z")
_RECORD_FILE = re.compile(r"\A[0-9a-f]{32}-g([1-9][0-9]{0,19})\.json\Z")
_STATES = {"LIVE": 0, "FENCED": 1, "EMPTY_DURABLE": 2}


class WAWCgroupAttestationStoreError(RuntimeError):
    """The Runtime-only attestation store is unavailable or inconsistent."""


class WAWCgroupAttestationStore:
    """Persist one validated cgroup attestation per workspace generation."""

    def __init__(self, directory: Path, *, expected_uid: int, expected_gid: int) -> None:
        if not isinstance(directory, Path):
            raise TypeError("directory must be a Path")
        if type(expected_uid) is not int or expected_uid < 0:
            raise ValueError("expected_uid must be a non-negative integer")
        if type(expected_gid) is not int or expected_gid < 0:
            raise ValueError("expected_gid must be a non-negative integer")
        self._directory = directory
        self._expected_uid = expected_uid
        self._expected_gid = expected_gid

    def read(self, *, workspace_id: str, generation: int) -> WAWCgroupAttestation | None:
        _validate_key(workspace_id, generation)
        with self._locked_directory() as directory_fd:
            return self._read_locked(directory_fd, workspace_id, generation)

    def has_unresolved(self, *, workspace_id: str) -> bool:
        """Return whether any persisted generation is not EMPTY_DURABLE.

        This is a conservative restart-hydration query.  A LIVE or FENCED
        record keeps the workspace quarantined until an explicit host-gated
        empty acknowledgement advances that record.
        """

        return self.latest_unresolved(workspace_id=workspace_id) is not None

    def unresolved_generations(self, *, workspace_id: str) -> tuple[int, ...]:
        """Return all non-empty generation numbers in ascending order."""

        if not isinstance(workspace_id, str) or _WORKSPACE_ID.fullmatch(workspace_id) is None:
            raise WAWCgroupAttestationStoreError("workspace_id is invalid")
        with self._locked_directory() as directory_fd:
            records = self._records_for_workspace_locked(directory_fd, workspace_id)
            return tuple(
                record.generation for record in records if record.cleanup_state != "EMPTY_DURABLE"
            )

    def latest_generation(self, *, workspace_id: str) -> int | None:
        """Return the highest persisted generation for a workspace."""

        if not isinstance(workspace_id, str) or _WORKSPACE_ID.fullmatch(workspace_id) is None:
            raise WAWCgroupAttestationStoreError("workspace_id is invalid")
        with self._locked_directory() as directory_fd:
            latest = self._latest_record_locked(directory_fd, workspace_id)
            return None if latest is None else latest.generation

    def latest_unresolved(self, *, workspace_id: str) -> WAWCgroupAttestation | None:
        """Return the highest-generation non-empty record for a workspace."""

        if not isinstance(workspace_id, str) or _WORKSPACE_ID.fullmatch(workspace_id) is None:
            raise WAWCgroupAttestationStoreError("workspace_id is invalid")
        with self._locked_directory() as directory_fd:
            records = self._records_for_workspace_locked(directory_fd, workspace_id)
            unresolved = [record for record in records if record.cleanup_state != "EMPTY_DURABLE"]
            return unresolved[-1] if unresolved else None

    def write(self, record: WAWCgroupAttestation) -> WAWCgroupAttestation:
        if not isinstance(record, WAWCgroupAttestation):
            raise TypeError("record must be WAWCgroupAttestation")
        try:
            raw = encode_waw_cgroup_attestation(record)
        except WAWCgroupAttestationError as exc:
            raise WAWCgroupAttestationStoreError("attestation validation failed") from exc
        with self._locked_directory() as directory_fd:
            current = self._read_locked(directory_fd, record.workspace_id, record.generation)
            if current is not None:
                _validate_update(current, record)
                if encode_waw_cgroup_attestation(current) == raw:
                    return current
            elif record.generation != 1:
                previous = self._latest_record_locked(directory_fd, record.workspace_id)
                if previous is None:
                    raise WAWCgroupAttestationStoreError(
                        "missing first-generation cgroup attestation"
                    )
                if record.generation != previous.generation + 1:
                    raise WAWCgroupAttestationStoreError("cgroup attestation generation has a gap")
                if (
                    record.project_id != previous.project_id
                    or record.agent_type != previous.agent_type
                    or record.runtime_epoch != previous.runtime_epoch
                ):
                    raise WAWCgroupAttestationStoreError(
                        "cgroup attestation lifecycle identity changed"
                    )
                if previous.cleanup_state != "EMPTY_DURABLE":
                    raise WAWCgroupAttestationStoreError("previous cgroup attestation is not empty")
            self._replace_locked(directory_fd, record, raw)
        return record

    def acknowledge_empty(self, record: WAWCgroupAttestation) -> bool:
        """Atomically persist an EMPTY_DURABLE record and report full cleanup.

        The caller must have obtained host-gated empty read-back.  This method
        only performs the durable compare-and-ack under one store lock; it does
        not read cgroupfs or authenticate the host producer.
        """

        if not isinstance(record, WAWCgroupAttestation):
            raise TypeError("record must be WAWCgroupAttestation")
        if (
            record.cleanup_state != "EMPTY_DURABLE"
            or record.last_populated != "0"
            or record.attachment_leaves
        ):
            raise WAWCgroupAttestationStoreError("empty acknowledgement is invalid")
        try:
            raw = encode_waw_cgroup_attestation(record)
        except WAWCgroupAttestationError as exc:
            raise WAWCgroupAttestationStoreError("attestation validation failed") from exc
        with self._locked_directory() as directory_fd:
            records = self._records_for_workspace_locked(directory_fd, record.workspace_id)
            unresolved = [item for item in records if item.cleanup_state != "EMPTY_DURABLE"]
            if not unresolved or record.generation != unresolved[-1].generation:
                raise WAWCgroupAttestationStoreError(
                    "empty acknowledgement does not target latest unresolved generation"
                )
            current = self._read_locked(directory_fd, record.workspace_id, record.generation)
            if current is None:
                raise WAWCgroupAttestationStoreError("empty acknowledgement record is missing")
            _validate_update(current, record)
            self._replace_locked(directory_fd, record, raw)
            remaining = self._records_for_workspace_locked(directory_fd, record.workspace_id)
            return not any(item.cleanup_state != "EMPTY_DURABLE" for item in remaining)

    @contextmanager
    def _locked_directory(self) -> Iterator[int]:
        try:
            details = os.lstat(self._directory)
        except OSError as exc:
            raise WAWCgroupAttestationStoreError("attestation directory is unavailable") from exc
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or details.st_uid != self._expected_uid
            or details.st_gid != self._expected_gid
            or stat.S_IMODE(details.st_mode) != 0o700
        ):
            raise WAWCgroupAttestationStoreError("attestation directory provenance is invalid")
        fd = -1
        try:
            fd = os.open(
                self._directory,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            opened = os.fstat(fd)
            if (
                opened.st_dev != details.st_dev
                or opened.st_ino != details.st_ino
                or opened.st_uid != self._expected_uid
                or opened.st_gid != self._expected_gid
                or stat.S_IMODE(opened.st_mode) != 0o700
            ):
                raise WAWCgroupAttestationStoreError("attestation directory changed during open")
            fcntl.flock(fd, fcntl.LOCK_EX)
        except (OSError, WAWCgroupAttestationStoreError) as exc:
            with suppress(OSError):
                if fd >= 0:
                    os.close(fd)
            if isinstance(exc, WAWCgroupAttestationStoreError):
                raise
            raise WAWCgroupAttestationStoreError("attestation directory cannot be locked") from exc
        try:
            yield fd
        finally:
            with suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_locked(
        self, directory_fd: int, workspace_id: str, generation: int
    ) -> WAWCgroupAttestation | None:
        name = _record_name(workspace_id, generation)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WAWCgroupAttestationStoreError("attestation file cannot be opened") from exc
        try:
            first = os.fstat(fd)
            if (
                not stat.S_ISREG(first.st_mode)
                or first.st_uid != self._expected_uid
                or first.st_gid != self._expected_gid
                or stat.S_IMODE(first.st_mode) != 0o600
                or first.st_nlink != 1
                or first.st_size < 0
                or first.st_size > _MAX_BYTES
            ):
                raise WAWCgroupAttestationStoreError("attestation file provenance is invalid")
            payload = bytearray()
            while len(payload) <= _MAX_BYTES:
                chunk = os.read(fd, min(8192, _MAX_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            if len(payload) > _MAX_BYTES:
                raise WAWCgroupAttestationStoreError("attestation file is oversized")
            second = os.fstat(fd)
            fields = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            if any(getattr(first, field) != getattr(second, field) for field in fields):
                raise WAWCgroupAttestationStoreError("attestation file changed during read")
        except WAWCgroupAttestationStoreError:
            raise
        except OSError as exc:
            raise WAWCgroupAttestationStoreError("attestation file cannot be read") from exc
        finally:
            with suppress(OSError):
                os.close(fd)
        try:
            record = decode_waw_cgroup_attestation(bytes(payload))
        except WAWCgroupAttestationError as exc:
            raise WAWCgroupAttestationStoreError("attestation record is invalid") from exc
        if record.workspace_id != workspace_id or record.generation != generation:
            raise WAWCgroupAttestationStoreError("attestation record key mismatch")
        return record

    def _latest_record_locked(
        self, directory_fd: int, workspace_id: str
    ) -> WAWCgroupAttestation | None:
        records = self._records_for_workspace_locked(directory_fd, workspace_id)
        return records[-1] if records else None

    def _records_for_workspace_locked(
        self, directory_fd: int, workspace_id: str
    ) -> list[WAWCgroupAttestation]:
        prefix = hashlib.sha256(workspace_id.encode("ascii")).hexdigest()[:32] + "-g"
        try:
            names = os.listdir(directory_fd)
        except OSError as exc:
            raise WAWCgroupAttestationStoreError("attestation directory cannot be listed") from exc
        candidates = [name for name in names if name.startswith(prefix)]
        if len(candidates) > _MAX_RECORD_FILES:
            raise WAWCgroupAttestationStoreError("too many attestation records")
        records: list[WAWCgroupAttestation] = []
        for name in candidates:
            match = _RECORD_FILE.fullmatch(name)
            if match is None:
                raise WAWCgroupAttestationStoreError("attestation filename is invalid")
            record = self._read_locked(directory_fd, workspace_id, int(match.group(1)))
            if record is not None:
                records.append(record)
        return sorted(records, key=lambda record: record.generation)

    def _replace_locked(self, directory_fd: int, record: WAWCgroupAttestation, raw: bytes) -> None:
        name = _record_name(record.workspace_id, record.generation)
        temporary = f".cgroup-attestation.{secrets.token_hex(12)}.tmp"
        fd = -1
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_fd,
            )
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short attestation write")
                view = view[written:]
            os.fsync(fd)
            details = os.fstat(fd)
            if (
                details.st_uid != self._expected_uid
                or details.st_gid != self._expected_gid
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 1
            ):
                raise WAWCgroupAttestationStoreError("temporary attestation provenance is invalid")
        except (OSError, WAWCgroupAttestationStoreError) as exc:
            raise WAWCgroupAttestationStoreError(
                "attestation update could not be prepared"
            ) from exc
        finally:
            if fd >= 0:
                with suppress(OSError):
                    os.close(fd)
        try:
            os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
        except OSError as exc:
            raise WAWCgroupAttestationStoreError(
                "attestation update could not be committed"
            ) from exc
        finally:
            with suppress(OSError):
                os.unlink(temporary, dir_fd=directory_fd)


def _validate_key(workspace_id: str, generation: int) -> None:
    if not isinstance(workspace_id, str) or _WORKSPACE_ID.fullmatch(workspace_id) is None:
        raise WAWCgroupAttestationStoreError("workspace_id is invalid")
    if type(generation) is not int or not 1 <= generation <= 2**64 - 1:
        raise WAWCgroupAttestationStoreError("generation is invalid")


def _record_name(workspace_id: str, generation: int) -> str:
    _validate_key(workspace_id, generation)
    digest = hashlib.sha256(workspace_id.encode("ascii")).hexdigest()[:32]
    return f"{digest}-g{generation}.json"


def _validate_update(current: WAWCgroupAttestation, updated: WAWCgroupAttestation) -> None:
    immutable = (
        "workspace_id",
        "project_id",
        "agent_type",
        "generation",
        "runtime_epoch",
        "service_unit",
        "service_invocation_id",
        "service_cgroup_device",
        "service_cgroup_inode",
        "service_cgroup_mount_id",
        "delegated_subgroup",
        "delegate_subgroup_device",
        "delegate_subgroup_inode",
        "delegate_subgroup_mount_id",
        "cgroup_mount_id",
        "cgroup_filesystem_id",
        "workspace_relative_path",
        "workspace_device",
        "workspace_inode",
        "workload_relative_path",
        "workload_device",
        "workload_inode",
        "controller_configuration_digest",
        "workspace_limits",
        "workload_limits",
        "attachment_limits",
    )
    if any(getattr(current, field) != getattr(updated, field) for field in immutable):
        raise WAWCgroupAttestationStoreError("attestation immutable identity changed")
    if _STATES[updated.cleanup_state] < _STATES[current.cleanup_state]:
        raise WAWCgroupAttestationStoreError("attestation cleanup state moved backwards")
    if current.cleanup_state == "EMPTY_DURABLE" and updated != current:
        raise WAWCgroupAttestationStoreError("EMPTY_DURABLE attestation cannot be changed")
    if current.last_populated == "0" and updated.last_populated == "1":
        raise WAWCgroupAttestationStoreError("attestation populated state moved backwards")
    if updated.cleanup_state == "EMPTY_DURABLE" and (
        updated.attachment_leaves or updated.last_populated != "0"
    ):
        raise WAWCgroupAttestationStoreError("EMPTY_DURABLE attestation is not empty")


__all__ = [
    "WAWCgroupAttestationStore",
    "WAWCgroupAttestationStoreError",
]
