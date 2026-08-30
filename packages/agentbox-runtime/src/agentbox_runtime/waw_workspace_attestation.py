"""Durable WAW workspace generation/provenance fences."""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = "waw-workspace-attestation-v1"
_MAX_BYTES = 4096
_ID = re.compile(r"\A(?:aws|wri)_[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_MAX_U64 = 2**64 - 1


class WAWWorkspaceAttestationError(RuntimeError):
    """A durable workspace provenance record is absent, stale, or unsafe."""


@dataclass(frozen=True)
class WAWWorkspaceAttestation:
    workspace_id: str
    min_generation: int
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    runtime_epoch: str


class WAWWorkspaceAttestationStore:
    """Persist one monotonic generation floor per WAW workspace."""

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

    def read(self, workspace_id: str) -> WAWWorkspaceAttestation | None:
        _validate_id(workspace_id, "workspace_id")
        with self._locked_directory() as directory_fd:
            return self._read_locked(directory_fd, workspace_id)

    def advance(
        self,
        *,
        workspace_id: str,
        generation: int,
        binding_revision: str,
        binding_digest: str,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        runtime_epoch: str,
    ) -> WAWWorkspaceAttestation:
        _validate_id(workspace_id, "workspace_id")
        if type(generation) is not int or not 1 <= generation <= _MAX_U64:
            raise WAWWorkspaceAttestationError("generation is invalid")
        _validate_decimal(binding_revision, "binding_revision")
        _validate_digest(binding_digest, "binding_digest")
        _validate_id(runtime_host_installation_id, "runtime_host_installation_id")
        _validate_decimal(runtime_host_installation_revision, "runtime_host_installation_revision")
        _validate_decimal(runtime_epoch, "runtime_epoch")
        with self._locked_directory() as directory_fd:
            current = self._read_locked(directory_fd, workspace_id)
            if current is not None:
                if generation <= current.min_generation:
                    raise WAWWorkspaceAttestationError("generation floor would move backwards")
                if (
                    binding_revision != current.binding_revision
                    or binding_digest != current.binding_digest
                    or runtime_host_installation_id != current.runtime_host_installation_id
                    or runtime_host_installation_revision
                    != current.runtime_host_installation_revision
                    or runtime_epoch != current.runtime_epoch
                ):
                    raise WAWWorkspaceAttestationError("workspace provenance changed")
            elif generation != 1:
                raise WAWWorkspaceAttestationError("missing first-generation attestation")
            record = WAWWorkspaceAttestation(
                workspace_id=workspace_id,
                min_generation=generation,
                binding_revision=binding_revision,
                binding_digest=binding_digest,
                runtime_host_installation_id=runtime_host_installation_id,
                runtime_host_installation_revision=runtime_host_installation_revision,
                runtime_epoch=runtime_epoch,
            )
            self._write_locked(directory_fd, record)
            return record

    @contextmanager
    def _locked_directory(self) -> Iterator[int]:
        try:
            details = os.lstat(self._directory)
        except OSError as exc:
            raise WAWWorkspaceAttestationError("attestation directory is unavailable") from exc
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or details.st_uid != self._expected_uid
            or details.st_gid != self._expected_gid
            or stat.S_IMODE(details.st_mode) != 0o700
        ):
            raise WAWWorkspaceAttestationError("attestation directory provenance is invalid")
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
                raise WAWWorkspaceAttestationError("attestation directory changed during open")
            fcntl.flock(fd, fcntl.LOCK_EX)
        except (OSError, ValueError, WAWWorkspaceAttestationError) as exc:
            with suppress(OSError):
                if fd >= 0:
                    os.close(fd)
            raise WAWWorkspaceAttestationError("attestation directory cannot be locked") from exc
        try:
            yield fd
        finally:
            with suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_locked(self, directory_fd: int, workspace_id: str) -> WAWWorkspaceAttestation | None:
        name = f"{workspace_id}.json"
        try:
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WAWWorkspaceAttestationError("attestation file cannot be opened") from exc
        try:
            details = os.fstat(fd)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != self._expected_uid
                or details.st_gid != self._expected_gid
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_size > _MAX_BYTES
            ):
                raise WAWWorkspaceAttestationError("attestation file provenance is invalid")
            raw = _read_bounded(fd)
        except OSError as exc:
            raise WAWWorkspaceAttestationError("attestation file cannot be read") from exc
        finally:
            os.close(fd)
        if len(raw) > _MAX_BYTES:
            raise WAWWorkspaceAttestationError("attestation file is oversized")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise WAWWorkspaceAttestationError("attestation JSON is invalid") from exc
        expected = {
            "schema_version",
            "workspace_id",
            "min_generation",
            "binding_revision",
            "binding_digest",
            "runtime_host_installation_id",
            "runtime_host_installation_revision",
            "runtime_epoch",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise WAWWorkspaceAttestationError("attestation fields are invalid")
        if value["schema_version"] != _SCHEMA or value["workspace_id"] != workspace_id:
            raise WAWWorkspaceAttestationError("attestation identity is invalid")
        generation = value["min_generation"]
        if type(generation) is not int or not 1 <= generation <= _MAX_U64:
            raise WAWWorkspaceAttestationError("attestation generation is invalid")
        _validate_decimal(value["binding_revision"], "binding_revision")
        _validate_digest(value["binding_digest"], "binding_digest")
        _validate_id(value["runtime_host_installation_id"], "runtime_host_installation_id")
        _validate_decimal(
            value["runtime_host_installation_revision"], "runtime_host_installation_revision"
        )
        _validate_decimal(value["runtime_epoch"], "runtime_epoch")
        return WAWWorkspaceAttestation(
            workspace_id=workspace_id,
            min_generation=generation,
            binding_revision=value["binding_revision"],
            binding_digest=value["binding_digest"],
            runtime_host_installation_id=value["runtime_host_installation_id"],
            runtime_host_installation_revision=value["runtime_host_installation_revision"],
            runtime_epoch=value["runtime_epoch"],
        )

    def _write_locked(self, directory_fd: int, record: WAWWorkspaceAttestation) -> None:
        name = f".attestation.{secrets.token_hex(12)}.tmp"
        payload = json.dumps(
            {
                "binding_digest": record.binding_digest,
                "binding_revision": record.binding_revision,
                "min_generation": record.min_generation,
                "runtime_epoch": record.runtime_epoch,
                "runtime_host_installation_id": record.runtime_host_installation_id,
                "runtime_host_installation_revision": record.runtime_host_installation_revision,
                "schema_version": _SCHEMA,
                "workspace_id": record.workspace_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short attestation write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(
                name,
                f"{record.workspace_id}.json",
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            os.fsync(directory_fd)
        except (OSError, ValueError) as exc:
            raise WAWWorkspaceAttestationError("attestation update could not be committed") from exc
        finally:
            with suppress(OSError):
                os.unlink(name, dir_fd=directory_fd)


def _validate_id(value: object, field: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise WAWWorkspaceAttestationError(f"{field} is invalid")


def _validate_digest(value: object, field: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise WAWWorkspaceAttestationError(f"{field} is invalid")


def _validate_decimal(value: object, field: str) -> None:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value) or int(value) > 2**64 - 1:
        raise WAWWorkspaceAttestationError(f"{field} is invalid")


def _read_bounded(fd: int) -> bytes:
    chunks: list[bytes] = []
    remaining = _MAX_BYTES + 1
    while remaining:
        block = os.read(fd, min(1024, remaining))
        if not block:
            break
        chunks.append(block)
        remaining -= len(block)
    raw = b"".join(chunks)
    if len(raw) > _MAX_BYTES:
        raise WAWWorkspaceAttestationError("attestation file is oversized")
    return raw


__all__ = [
    "WAWWorkspaceAttestation",
    "WAWWorkspaceAttestationError",
    "WAWWorkspaceAttestationStore",
]
