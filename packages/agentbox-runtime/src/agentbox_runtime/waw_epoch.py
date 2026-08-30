"""Durable, monotonic Runtime epoch allocation for WAW authority fencing."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import secrets
import stat
from contextlib import suppress
from pathlib import Path

MAX_U64 = 2**64 - 1
_SCHEMA = "waw-runtime-epoch-v1"
_MAX_BYTES = 4096
_DECIMAL = re.compile(r"\A(?:[1-9][0-9]{0,19})\Z")


class WAWRuntimeEpochError(RuntimeError):
    """The Runtime epoch trust root is missing, malformed, or unsafe."""


class WAWRuntimeEpochStore:
    """Consume a Runtime-only epoch counter with crash-safe replacement."""

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

    def bootstrap(self) -> int:
        """Create the first positive epoch after an external enrollment fence.

        The root installer must hold the WAW-row/bootstrap fence before calling
        this one-time operation.  This store verifies that no counter exists,
        writes the first consumed value (``1``) durably, and never overwrites an
        existing counter.  Normal Runtime startup must use :meth:`consume`.
        """

        directory_fd = self._open_directory()
        try:
            try:
                fcntl.flock(directory_fd, fcntl.LOCK_EX)
            except OSError as exc:
                raise WAWRuntimeEpochError("epoch directory cannot be locked") from exc
            try:
                fd = os.open(
                    "epoch.json",
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except FileNotFoundError:
                self._replace_epoch(directory_fd, 1)
                return 1
            except OSError as exc:
                raise WAWRuntimeEpochError("epoch file cannot be inspected") from exc
            else:
                os.close(fd)
                raise WAWRuntimeEpochError("Runtime epoch counter is already initialized")
        finally:
            with suppress(OSError):
                fcntl.flock(directory_fd, fcntl.LOCK_UN)
            os.close(directory_fd)

    def consume(self) -> int:
        directory_fd = self._open_directory()
        try:
            try:
                fcntl.flock(directory_fd, fcntl.LOCK_EX)
            except OSError as exc:
                raise WAWRuntimeEpochError("epoch directory cannot be locked") from exc
            current = self._read_epoch(directory_fd)
            if current == MAX_U64:
                raise WAWRuntimeEpochError("Runtime epoch sequence is exhausted")
            next_epoch = current + 1
            self._replace_epoch(directory_fd, next_epoch)
            return next_epoch
        finally:
            with suppress(OSError):
                fcntl.flock(directory_fd, fcntl.LOCK_UN)
            os.close(directory_fd)

    def _open_directory(self) -> int:
        try:
            details = os.lstat(self._directory)
        except OSError as exc:
            raise WAWRuntimeEpochError("epoch directory is unavailable") from exc
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or details.st_uid != self._expected_uid
            or details.st_gid != self._expected_gid
            or stat.S_IMODE(details.st_mode) != 0o700
        ):
            raise WAWRuntimeEpochError("epoch directory provenance is invalid")
        try:
            directory_fd = os.open(
                self._directory,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except OSError as exc:
            raise WAWRuntimeEpochError("epoch directory cannot be opened safely") from exc
        try:
            opened = os.fstat(directory_fd)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_dev != details.st_dev
                or opened.st_ino != details.st_ino
                or opened.st_uid != self._expected_uid
                or opened.st_gid != self._expected_gid
                or stat.S_IMODE(opened.st_mode) != 0o700
            ):
                raise WAWRuntimeEpochError("epoch directory changed during open")
            return directory_fd
        except Exception:
            os.close(directory_fd)
            raise

    def _read_epoch(self, directory_fd: int) -> int:
        try:
            fd = os.open(
                "epoch.json",
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            raise WAWRuntimeEpochError("epoch file is unavailable") from exc
        try:
            details = os.fstat(fd)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != self._expected_uid
                or details.st_gid != self._expected_gid
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_size > _MAX_BYTES
            ):
                raise WAWRuntimeEpochError("epoch file provenance is invalid")
            payload = _read_bounded(fd)
        except OSError as exc:
            raise WAWRuntimeEpochError("epoch file cannot be read") from exc
        finally:
            os.close(fd)
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise WAWRuntimeEpochError("epoch file JSON is invalid") from exc
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "epoch"}
            or value["schema_version"] != _SCHEMA
            or not isinstance(value["epoch"], str)
            or not _DECIMAL.fullmatch(value["epoch"])
        ):
            raise WAWRuntimeEpochError("epoch record is invalid")
        try:
            epoch = int(value["epoch"])
        except ValueError as exc:
            raise WAWRuntimeEpochError("epoch record is invalid") from exc
        if not 1 <= epoch <= MAX_U64:
            raise WAWRuntimeEpochError("epoch record is outside uint64 domain")
        return epoch

    def _replace_epoch(self, directory_fd: int, epoch: int) -> None:
        temp_name = f".epoch.{secrets.token_hex(12)}.tmp"
        payload = json.dumps(
            {"epoch": str(epoch), "schema_version": _SCHEMA},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        try:
            fd = os.open(
                temp_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                _write_all(fd, payload)
                os.fsync(fd)
                details = os.fstat(fd)
                if details.st_uid != self._expected_uid or details.st_gid != self._expected_gid:
                    raise WAWRuntimeEpochError("temporary epoch provenance is invalid")
            finally:
                os.close(fd)
            os.replace(temp_name, "epoch.json", src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
        except (OSError, ValueError) as exc:
            raise WAWRuntimeEpochError("epoch update could not be committed") from exc
        finally:
            with suppress(OSError):
                os.unlink(temp_name, dir_fd=directory_fd)


def _read_bounded(fd: int) -> str:
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
        raise WAWRuntimeEpochError("epoch file exceeds bounded size")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WAWRuntimeEpochError("epoch file is not UTF-8") from exc


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "short epoch write")
        view = view[written:]


__all__ = ["MAX_U64", "WAWRuntimeEpochError", "WAWRuntimeEpochStore"]
