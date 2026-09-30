"""Fixed non-secret vendor enrollment publication for the local installer.

No API, Worker or Root Helper entry point is added. The caller supplies a
verified manifest observation and keeps the installer lifecycle lock held.
Publication never replaces an existing enrollment. Interrupted publication
can only be resumed explicitly with the same canonical observation.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from agentbox_runtime.waw_vendor_enrollment import encode_waw_vendor_enrollment

_RECORD = "vendor-enrollment.v1.json"
_PENDING = "vendor-enrollment.v1.pending"
_LIMIT = 1024
_OPEN = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


class WAWEnrollmentPublicationError(RuntimeError):
    """A fixed publication is unsafe, conflicting or incomplete."""


@dataclass(frozen=True)
class WAWEnrollmentPublication:
    status: str
    record_sha256: str


def _identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_uid,
        details.st_gid,
        details.st_mode,
        details.st_nlink,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


class WAWEnrollmentPublisher:
    def __init__(self, root: Path, *, owner_uid: int, root_gid: int, runtime_gid: int) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or ".." in root.parts:
            raise ValueError("installer root is invalid")
        if any(type(value) is not int or value < 0 for value in (owner_uid, root_gid, runtime_gid)):
            raise ValueError("installer identity is invalid")
        self.root = root
        self.owner_uid = owner_uid
        self.root_gid = root_gid
        self.runtime_gid = runtime_gid

    @contextmanager
    def _parent(self) -> Iterator[tuple[int, Callable[[], None]]]:
        parts = ("var", "lib", "agentbox-waw")
        descriptors: list[int] = []
        observed: list[tuple[int, ...]] = []
        try:
            for index, component in enumerate((str(self.root), *parts)):
                descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    **({"dir_fd": descriptors[-1]} if descriptors else {}),
                )
                descriptors.append(descriptor)
                details = os.fstat(descriptor)
                mode = stat.S_IMODE(details.st_mode)
                if (
                    not stat.S_ISDIR(details.st_mode)
                    or details.st_uid != self.owner_uid
                    or mode & 0o022
                ):
                    raise WAWEnrollmentPublicationError("enrollment parent provenance is invalid")
                if index == len(parts) and (mode != 0o750 or details.st_gid != self.runtime_gid):
                    raise WAWEnrollmentPublicationError("enrollment directory is invalid")
                observed.append(_identity(details)[:5])

            def verify() -> None:
                if _identity(os.stat(self.root, follow_symlinks=False))[:5] != observed[0]:
                    raise WAWEnrollmentPublicationError("installer root changed")
                for index, descriptor in enumerate(descriptors):
                    if _identity(os.fstat(descriptor))[:5] != observed[index]:
                        raise WAWEnrollmentPublicationError("enrollment parent changed")
                    if index:
                        entry = os.stat(
                            parts[index - 1], dir_fd=descriptors[index - 1], follow_symlinks=False
                        )
                        if _identity(entry)[:5] != observed[index]:
                            raise WAWEnrollmentPublicationError("enrollment parent entry changed")

            verify()
            yield descriptors[-1], verify
            verify()
        finally:
            uncertain = False
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    uncertain = True
            if uncertain:
                raise WAWEnrollmentPublicationError("enrollment directory cleanup is uncertain")

    def _read(
        self, parent: int, name: str, *, pending: bool
    ) -> tuple[bytes, os.stat_result] | None:
        try:
            descriptor = os.open(name, _OPEN, dir_fd=parent)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(descriptor)
            allowed = {(self.runtime_gid, 0o440)}
            if pending:
                allowed.add((self.root_gid, 0o600))
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != self.owner_uid
                or (before.st_gid, stat.S_IMODE(before.st_mode)) not in allowed
                or before.st_nlink not in (1, 2)
                or not 0 <= before.st_size <= _LIMIT
                or (pending and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink != 1)
            ):
                raise WAWEnrollmentPublicationError("enrollment file provenance is invalid")
            chunks = bytearray()
            while len(chunks) < before.st_size:
                chunk = os.read(descriptor, before.st_size - len(chunks))
                if not chunk:
                    raise WAWEnrollmentPublicationError("enrollment read is incomplete")
                chunks.extend(chunk)
            if os.read(descriptor, 1):
                raise WAWEnrollmentPublicationError("enrollment grew while reading")
            after = os.fstat(descriptor)
            entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if _identity(before) != _identity(after) or _identity(before) != _identity(entry):
                raise WAWEnrollmentPublicationError("enrollment file changed")
            return bytes(chunks), before
        finally:
            os.close(descriptor)

    def _stage(self, parent: int, raw: bytes, pending: tuple[bytes, os.stat_result] | None) -> None:
        if pending is not None and pending[0] == raw and stat.S_IMODE(pending[1].st_mode) == 0o440:
            if pending[1].st_nlink != 1:
                raise WAWEnrollmentPublicationError("pending enrollment has unknown links")
            return
        flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        if pending is None:
            flags |= os.O_CREAT | os.O_EXCL
        elif (
            stat.S_IMODE(pending[1].st_mode) != 0o600
            or pending[1].st_gid != self.root_gid
            or pending[1].st_nlink != 1
            or not raw.startswith(pending[0])
        ):
            raise WAWEnrollmentPublicationError("pending enrollment does not match observation")
        descriptor = os.open(_PENDING, flags, 0o600, dir_fd=parent)
        try:
            details = os.fstat(descriptor)
            if pending is not None and _identity(details) != _identity(pending[1]):
                raise WAWEnrollmentPublicationError("pending enrollment changed before writing")
            if pending is None:
                os.fchown(descriptor, self.owner_uid, self.root_gid)
            offset = len(pending[0]) if pending is not None else 0
            os.lseek(descriptor, offset, os.SEEK_SET)
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise WAWEnrollmentPublicationError("enrollment write is incomplete")
                offset += written
            os.fsync(descriptor)
            os.fchown(descriptor, self.owner_uid, self.runtime_gid)
            os.fchmod(descriptor, 0o440)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent)

    def publish(
        self,
        fields: dict[str, object],
        *,
        revalidate: Callable[[], None],
        recover: bool = False,
        plan: bool = False,
    ) -> WAWEnrollmentPublication:
        if not callable(revalidate) or type(recover) is not bool or type(plan) is not bool:
            raise TypeError("enrollment publication arguments are invalid")
        raw = encode_waw_vendor_enrollment(fields)
        digest = hashlib.sha256(raw).hexdigest()
        try:
            with self._parent() as (parent, verify):
                revalidate()
                record = self._read(parent, _RECORD, pending=False)
                pending = self._read(parent, _PENDING, pending=True)
                if record is not None and record[0] != raw:
                    raise WAWEnrollmentPublicationError(
                        "existing enrollment differs; replacement is refused"
                    )
                if pending is not None and not recover:
                    raise WAWEnrollmentPublicationError(
                        "publication is pending; explicit recovery is required"
                    )
                if pending is not None and not raw.startswith(pending[0]):
                    raise WAWEnrollmentPublicationError(
                        "pending enrollment differs from observation"
                    )
                if (
                    pending is not None
                    and stat.S_IMODE(pending[1].st_mode) == 0o440
                    and pending[0] != raw
                ):
                    raise WAWEnrollmentPublicationError("ready enrollment is incomplete")
                if record is not None:
                    if pending is not None:
                        if (
                            record[1].st_nlink != 2
                            or pending[1].st_nlink != 2
                            or (record[1].st_dev, record[1].st_ino)
                            != (pending[1].st_dev, pending[1].st_ino)
                            or pending[0] != raw
                        ):
                            raise WAWEnrollmentPublicationError(
                                "publication ownership is inconsistent"
                            )
                    elif record[1].st_nlink != 1:
                        raise WAWEnrollmentPublicationError("existing enrollment has unknown links")
                if plan:
                    return WAWEnrollmentPublication("planned", digest)
                if record is None:
                    self._stage(parent, raw, pending)
                    verify()
                    revalidate()
                    verify()
                    os.link(
                        _PENDING,
                        _RECORD,
                        src_dir_fd=parent,
                        dst_dir_fd=parent,
                        follow_symlinks=False,
                    )
                    os.fsync(parent)
                if record is None or pending is not None:
                    staged = self._read(parent, _PENDING, pending=True)
                    published = self._read(parent, _RECORD, pending=False)
                    if (
                        staged is None
                        or published is None
                        or staged[0] != raw
                        or published[0] != raw
                        or _identity(staged[1]) != _identity(published[1])
                        or published[1].st_nlink != 2
                    ):
                        raise WAWEnrollmentPublicationError(
                            "published enrollment identity is uncertain"
                        )
                    verify()
                    revalidate()
                    verify()
                    os.unlink(_PENDING, dir_fd=parent)
                os.fsync(parent)
                final = self._read(parent, _RECORD, pending=False)
                if final is None or final[0] != raw or final[1].st_nlink != 1:
                    raise WAWEnrollmentPublicationError("enrollment readback is invalid")
                verify()
                revalidate()
                status = (
                    "recovered"
                    if pending is not None
                    else "published" if record is None else "unchanged"
                )
                return WAWEnrollmentPublication(status, digest)
        except OSError as exc:
            raise WAWEnrollmentPublicationError(
                "enrollment filesystem operation is unavailable"
            ) from exc
