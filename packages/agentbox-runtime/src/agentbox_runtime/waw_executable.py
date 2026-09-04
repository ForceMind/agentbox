"""Descriptor-held provenance for trusted WAW Runtime executable inventory.

This is not a Runtime action, manifest loader or process launcher. Only trusted
Runtime composition may supply pins; requests can never supply paths or pins.
The Linux x86_64 ELF header check rejects scripts and foreign formats, but does
not establish loader/library integrity, vendor version support or runnability.
After a strict inventory load, a verified handle can produce one nominal,
one-shot descriptor handoff while holding the same revalidation lock. Immutable
installation/namespace policy and actual execution remain separate gates.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import os
import platform
import re
import stat
import struct
import sys
import threading
import weakref
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox_runtime.waw_process_profile import ExecutableInventoryV1

_close = os.close
_fstat = os.fstat
_open = os.open
_pread = os.pread
_MAX_BYTES = 256 * 1024 * 1024
_READ_BYTES = 64 * 1024
_MAX_COMPONENTS = 128
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_LAUNCH_HANDLE_TOKEN = object()


class WAWExecutableError(RuntimeError):
    """The trusted executable inventory or its live provenance is unsafe."""


class WAWExecutableKind(StrEnum):
    TMUX = "tmux"
    PANE_BOOTSTRAP = "pane_bootstrap"
    BRIDGE = "bridge"
    ATTACH_SUPERVISOR = "attach_supervisor"
    CLAUDE = "claude"
    CODEX = "codex"


@dataclass(frozen=True)
class WAWExecutablePin:
    """Trusted installation input, never accepted from an API or browser."""

    path: Path
    sha256: str
    max_bytes: int = _MAX_BYTES

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, Path)
            or not self.path.is_absolute()
            or self.path.anchor != "/"
            or len(self.path.parts) < 2
            or len(self.path.parts) > _MAX_COMPONENTS
            or ".." in self.path.parts
            or "\x00" in str(self.path)
            or len(os.fsencode(self.path)) > 4096
        ):
            raise WAWExecutableError("executable inventory path is invalid")
        if type(self.sha256) is not str or not _DIGEST.fullmatch(self.sha256):
            raise WAWExecutableError("executable SHA-256 pin is invalid")
        if type(self.max_bytes) is not int or not 64 <= self.max_bytes <= _MAX_BYTES:
            raise WAWExecutableError("executable byte limit is invalid")


@dataclass(frozen=True)
class WAWExecutableIdentity:
    kind: WAWExecutableKind
    path: Path
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int
    links: int
    sha256: str


@dataclass(frozen=True)
class _Node:
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    # Directory content timestamps are deliberately excluded: unrelated package
    # updates do not change the ancestry identity/ownership/permission proof.
    file_state: tuple[int, int, int, int] | None


class WAWExecutableInventory:
    """Copy trusted pins once; select only a closed executable kind thereafter."""

    def __init__(self, pins: Mapping[WAWExecutableKind, WAWExecutablePin]) -> None:
        if not isinstance(pins, Mapping):
            raise WAWExecutableError("executable inventory is invalid")
        copied = dict(pins)
        if len(copied) > len(WAWExecutableKind):
            raise WAWExecutableError("executable inventory is invalid")
        for kind, pin in copied.items():
            if type(kind) is not WAWExecutableKind or type(pin) is not WAWExecutablePin:
                raise WAWExecutableError("executable inventory entry is invalid")
            pin.__post_init__()
        self._pins = copied
        self._version_records: dict[WAWExecutableKind, tuple[str, str]] = {}
        self._inventory_digest: str | None = None

    @classmethod
    def from_manifest(cls, manifest: ExecutableInventoryV1) -> WAWExecutableInventory:
        """Construct a production exact-six inventory from a strict v1 record."""

        from agentbox_runtime.waw_process_profile import (
            ExecutableInventoryV1,
            decode_executable_inventory_v1,
            encode_executable_inventory_v1,
        )

        if type(manifest) is not ExecutableInventoryV1:
            raise WAWExecutableError("strict executable inventory manifest is required")
        try:
            checked = decode_executable_inventory_v1(encode_executable_inventory_v1(manifest))
            pins = {
                WAWExecutableKind(entry.kind): WAWExecutablePin(
                    Path(entry.path), entry.sha256, entry.max_bytes
                )
                for entry in checked.executables
            }
        except (ValueError, TypeError) as exc:
            raise WAWExecutableError("strict executable inventory manifest is invalid") from exc
        if tuple(pins) != tuple(WAWExecutableKind):
            raise WAWExecutableError("executable inventory is not exact-six")
        result = cls(pins)
        result._inventory_digest = hashlib.sha256(
            encode_executable_inventory_v1(checked)
        ).hexdigest()
        result._version_records = {
            WAWExecutableKind(entry.kind): (entry.version_identity, entry.version_probe_id)
            for entry in checked.executables
        }
        return result

    def version_record(self, kind: WAWExecutableKind) -> tuple[str, str]:
        """Return the fixed version identity/probe pair of a strict inventory."""

        if type(kind) is not WAWExecutableKind or kind not in self._version_records:
            raise WAWExecutableError("executable kind has no strict version record")
        return self._version_records[kind]

    def open(self, kind: WAWExecutableKind) -> WAWVerifiedExecutable:
        """Open and attest one known pin without executing or exporting its FD."""
        if type(kind) is not WAWExecutableKind or kind not in self._pins:
            raise WAWExecutableError("executable kind has no trusted pin")
        _validate_runtime()
        pin = self._pins[kind]
        fds: list[int] = []
        try:
            nodes = _open_path(pin, fds)
            _verify(pin, fds, nodes)
            details = nodes[-1]
            assert details.file_state is not None
            size, modified_ns, changed_ns, links = details.file_state
            identity = WAWExecutableIdentity(
                kind,
                pin.path,
                details.device,
                details.inode,
                details.uid,
                details.gid,
                details.mode,
                size,
                modified_ns,
                changed_ns,
                links,
                pin.sha256,
            )
            return WAWVerifiedExecutable(
                pin,
                identity,
                tuple(fds),
                nodes,
                inventory_digest=self._inventory_digest,
                version_record=self._version_records.get(kind),
            )
        except BaseException as exc:
            _close_fds(fds)
            if isinstance(exc, OSError):
                raise WAWExecutableError("executable provenance is unavailable") from exc
            raise


class WAWVerifiedExecutable:
    """Own the full no-follow descriptor chain until explicit/context close.

    Instances come from inventory.open(). A failed revalidation permanently
    closes the handle. Calls to revalidate/close are serialized, so close cannot
    recycle a descriptor while a check is using it. No raw descriptor escapes.
    """

    def __init__(
        self,
        pin: WAWExecutablePin,
        identity: WAWExecutableIdentity,
        fds: tuple[int, ...],
        nodes: tuple[_Node, ...],
        *,
        inventory_digest: str | None,
        version_record: tuple[str, str] | None,
    ) -> None:
        self._pin = pin
        self._identity = identity
        self._fds = fds
        self._nodes = nodes
        self._inventory_digest = inventory_digest
        self._version_record = version_record
        self._lock = threading.Lock()
        self._finalizer = weakref.finalize(self, _close_fds, fds)

    @property
    def identity(self) -> WAWExecutableIdentity:
        """Immutable original observation; this alone never authorizes a launch."""
        return self._identity

    @property
    def closed(self) -> bool:
        with self._lock:
            return not self._finalizer.alive

    def revalidate(self) -> WAWExecutableIdentity:
        with self._lock:
            self._require_open()
            try:
                _validate_runtime()
                _verify(self._pin, self._fds, self._nodes)
            except BaseException as exc:
                self._finalizer()
                if isinstance(exc, OSError):
                    raise WAWExecutableError("executable provenance is unavailable") from exc
                raise
            return self._identity

    def close(self) -> None:
        with self._lock:
            self._finalizer()

    def create_launch_handle(
        self,
        *,
        expected_kind: WAWExecutableKind,
        profile_digest: str,
    ) -> WAWExecutableLaunchHandle:
        """Revalidate and duplicate the held final FD without reopening a path."""

        if type(expected_kind) is not WAWExecutableKind or expected_kind is not self._identity.kind:
            raise WAWExecutableError("executable launch kind does not match")
        if (
            type(profile_digest) is not str
            or _DIGEST.fullmatch(profile_digest) is None
            or profile_digest == "0" * 64
        ):
            raise WAWExecutableError("executable launch profile digest is invalid")
        with self._lock:
            self._require_open()
            if self._inventory_digest is None or self._version_record is None:
                raise WAWExecutableError("executable has no strict inventory launch binding")
            try:
                _validate_runtime()
                _verify(self._pin, self._fds, self._nodes)
                descriptor = fcntl.fcntl(self._fds[-1], fcntl.F_DUPFD_CLOEXEC, 64)
                _verify_launch_descriptor(descriptor, self._identity)
            except BaseException as exc:
                if "descriptor" in locals():
                    with suppress(OSError):
                        _close(descriptor)
                self._finalizer()
                if isinstance(exc, OSError):
                    raise WAWExecutableError("executable launch handoff failed") from exc
                raise
            return WAWExecutableLaunchHandle(
                _LAUNCH_HANDLE_TOKEN,
                descriptor=descriptor,
                identity=self._identity,
                inventory_digest=self._inventory_digest,
                version_identity=self._version_record[0],
                version_probe_id=self._version_record[1],
                profile_digest=profile_digest,
            )

    def __enter__(self) -> WAWVerifiedExecutable:
        with self._lock:
            self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if not self._finalizer.alive:
            raise WAWExecutableError("executable handle is closed")


class WAWExecutableLaunchHandle:
    """Nominal, one-shot executable FD handoff for fixed Runtime launch."""

    def __init__(
        self,
        token: object,
        *,
        descriptor: int,
        identity: WAWExecutableIdentity,
        inventory_digest: str,
        version_identity: str,
        version_probe_id: str,
        profile_digest: str,
    ) -> None:
        if token is not _LAUNCH_HANDLE_TOKEN:
            raise WAWExecutableError("executable launch handles are not caller-constructible")
        self._descriptor = descriptor
        self._identity = identity
        self._inventory_digest = inventory_digest
        self._version_identity = version_identity
        self._version_probe_id = version_probe_id
        self._profile_digest = profile_digest
        self._lock = threading.Lock()
        self._finalizer = weakref.finalize(self, _close_launch_fd, descriptor)

    @property
    def identity(self) -> WAWExecutableIdentity:
        return self._identity

    @property
    def inventory_digest(self) -> str:
        return self._inventory_digest

    @property
    def version_identity(self) -> str:
        return self._version_identity

    @property
    def version_probe_id(self) -> str:
        return self._version_probe_id

    @property
    def profile_digest(self) -> str:
        return self._profile_digest

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._descriptor < 0

    def take(self, expected_kind: WAWExecutableKind) -> int:
        """Transfer the descriptor once after one final inode identity check."""

        if type(expected_kind) is not WAWExecutableKind or expected_kind is not self._identity.kind:
            raise WAWExecutableError("executable launch kind does not match")
        with self._lock:
            if self._descriptor < 0:
                raise WAWExecutableError("executable launch handle is closed or consumed")
            try:
                _verify_launch_descriptor(self._descriptor, self._identity)
            except BaseException:
                self._finalizer()
                self._descriptor = -1
                raise
            descriptor = self._descriptor
            self._finalizer.detach()
            self._descriptor = -1
            return descriptor

    def close(self) -> None:
        with self._lock:
            if self._descriptor >= 0:
                self._finalizer()
                self._descriptor = -1

    def __enter__(self) -> WAWExecutableLaunchHandle:
        if self.closed:
            raise WAWExecutableError("executable launch handle is closed or consumed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _runtime_identity() -> tuple[str, str, int]:
    return sys.platform, platform.machine(), os.geteuid()


def _validate_runtime() -> None:
    system, machine, uid = _runtime_identity()
    if system != "linux" or machine != "x86_64" or uid == 0:
        raise WAWExecutableError("executable verification requires non-root Linux x86_64 Runtime")


def _stat_at(name: str, parent: int | None) -> os.stat_result:
    return os.stat(name, dir_fd=parent, follow_symlinks=False)


def _node(details: os.stat_result, *, directory: bool, max_bytes: int) -> _Node:
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected_type(details.st_mode)
        or details.st_uid != 0
        or details.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or details.st_mode & (stat.S_ISUID | stat.S_ISGID)
    ):
        raise WAWExecutableError("executable path ownership, type or permissions are unsafe")
    file_state = None
    if not directory:
        # Requiring other-read/execute is conservative and avoids assuming a
        # particular Runtime supplementary group; root/special privilege is not
        # a permitted fallback. ACL masks granting write also set group-write.
        if details.st_mode & 0o005 != 0o005 or not 64 <= details.st_size <= max_bytes:
            raise WAWExecutableError("executable file mode or size is invalid")
        file_state = (details.st_size, details.st_mtime_ns, details.st_ctime_ns, details.st_nlink)
    return _Node(
        details.st_dev, details.st_ino, details.st_uid, details.st_gid, details.st_mode, file_state
    )


def _open_path(pin: WAWExecutablePin, fds: list[int]) -> tuple[_Node, ...]:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    fds.append(_open("/", flags | os.O_DIRECTORY))
    nodes = [_node(_fstat(fds[0]), directory=True, max_bytes=pin.max_bytes)]
    components = pin.path.parts[1:]
    for index, component in enumerate(components):
        directory = index < len(components) - 1
        before = _node(_stat_at(component, fds[-1]), directory=directory, max_bytes=pin.max_bytes)
        fds.append(_open(component, flags | (os.O_DIRECTORY if directory else 0), dir_fd=fds[-1]))
        after = _node(_fstat(fds[-1]), directory=directory, max_bytes=pin.max_bytes)
        if before != after:
            raise WAWExecutableError("executable path changed while opening")
        nodes.append(after)
    return tuple(nodes)


def _assert_path(
    pin: WAWExecutablePin, fds: tuple[int, ...] | list[int], nodes: tuple[_Node, ...]
) -> None:
    for index, (fd, expected) in enumerate(zip(fds, nodes, strict=True)):
        directory = index < len(fds) - 1
        current = _node(_fstat(fd), directory=directory, max_bytes=pin.max_bytes)
        linked = _node(
            _stat_at(pin.path.parts[index], None if index == 0 else fds[index - 1]),
            directory=directory,
            max_bytes=pin.max_bytes,
        )
        after = _node(_fstat(fd), directory=directory, max_bytes=pin.max_bytes)
        if current != expected or linked != expected or after != expected:
            raise WAWExecutableError("executable descriptor or pathname identity changed")


def _verify(
    pin: WAWExecutablePin, fds: tuple[int, ...] | list[int], nodes: tuple[_Node, ...]
) -> None:
    _assert_path(pin, fds, nodes)
    digest = hashlib.sha256()
    offset = 0
    header = b""
    while True:
        chunk = _pread(fds[-1], min(_READ_BYTES, pin.max_bytes - offset + 1), offset)
        if not chunk:
            break
        offset += len(chunk)
        if offset > pin.max_bytes:
            raise WAWExecutableError("executable exceeds its byte limit")
        digest.update(chunk)
        if len(header) < 64:
            header += chunk[: 64 - len(header)]
            if len(header) == 64:
                _validate_elf_header(header)
    if len(header) != 64 or nodes[-1].file_state is None or offset != nodes[-1].file_state[0]:
        raise WAWExecutableError("executable file length changed or is invalid")
    if not hmac.compare_digest(digest.hexdigest(), pin.sha256):
        raise WAWExecutableError("executable SHA-256 pin does not match")
    _assert_path(pin, fds, nodes)


def _validate_elf_header(header: bytes) -> None:
    # ELF64, little endian, current identification/version, System V/Linux ABI,
    # ET_EXEC or ET_DYN (PIE), EM_X86_64, and the exact ELF64 header size. This
    # deliberately does not claim that program segments or dynamic dependencies
    # are safe or runnable; trusted digest/version installation proof is separate.
    if (
        header[:7] != b"\x7fELF\x02\x01\x01"
        or header[7] not in (0, 3)
        or header[8] != 0
        or struct.unpack_from("<HHI", header, 16) not in ((2, 62, 1), (3, 62, 1))
        or struct.unpack_from("<H", header, 52)[0] != 64
    ):
        raise WAWExecutableError("executable is not a Linux x86_64 ELF image")


def _verify_launch_descriptor(descriptor: int, identity: WAWExecutableIdentity) -> None:
    try:
        details = _fstat(descriptor)
    except OSError as exc:
        raise WAWExecutableError("executable launch descriptor is unavailable") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_dev != identity.device
        or details.st_ino != identity.inode
        or details.st_uid != identity.uid
        or details.st_gid != identity.gid
        or details.st_mode != identity.mode
        or details.st_size != identity.size
        or details.st_mtime_ns != identity.modified_ns
        or details.st_ctime_ns != identity.changed_ns
        or details.st_nlink != identity.links
    ):
        raise WAWExecutableError("executable launch descriptor identity changed")


def _close_fds(fds: tuple[int, ...] | list[int]) -> None:
    for fd in reversed(fds):
        with suppress(OSError):
            _close(fd)


def _close_launch_fd(descriptor: int) -> None:
    with suppress(OSError):
        _close(descriptor)


__all__ = [
    "WAWExecutableError",
    "WAWExecutableIdentity",
    "WAWExecutableInventory",
    "WAWExecutableKind",
    "WAWExecutableLaunchHandle",
    "WAWExecutablePin",
    "WAWVerifiedExecutable",
]
