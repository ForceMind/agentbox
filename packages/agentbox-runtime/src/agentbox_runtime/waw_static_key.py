"""Runtime-only custody for the fixed WAW X25519 static key."""

from __future__ import annotations

import grp
import hashlib
import hmac
import os
import pwd
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority

_RUNTIME_ACCOUNT = "agentbox-runtime"
_FIXED_KEY_PATH = Path("/var/lib/agentbox-waw/keys-v1/static-x25519.key")
_FIXED_ROOT = Path(_FIXED_KEY_PATH.anchor)
_DIRECTORY_COMPONENTS = _FIXED_KEY_PATH.parent.parts[1:]
_KEY_FILENAME = _FIXED_KEY_PATH.name
_KEY_BYTES = 32


class WAWRuntimeStaticKeyError(RuntimeError):
    """The fixed Runtime key or its custody lifecycle is unavailable."""


class WAWRuntimeStaticKeyConstructionCleanupError(WAWRuntimeStaticKeyError):
    """A failed construction left at least one descriptor close uncertain."""

    def __init__(self, original_failure: BaseException) -> None:
        super().__init__("Runtime static key construction cleanup is incomplete")
        self.original_failure = original_failure


class _StaticKeySyscalls:
    def open(
        self,
        path: str | Path,
        flags: int,
        *,
        dir_fd: int | None = None,
    ) -> int:
        return os.open(path, flags, dir_fd=dir_fd)

    def close(self, fd: int) -> None:
        os.close(fd)

    def fstat(self, fd: int) -> Any:
        return os.fstat(fd)

    def stat(self, name: str, *, dir_fd: int) -> Any:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)

    def pread(self, fd: int, length: int, offset: int) -> bytes:
        return os.pread(fd, length, offset)


_SYSCALLS = _StaticKeySyscalls()


@dataclass(frozen=True)
class _Identity:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def capture(cls, details: Any) -> _Identity:
        return cls(
            details.st_dev,
            details.st_ino,
            details.st_mode,
            details.st_uid,
            details.st_gid,
            details.st_nlink,
            details.st_size,
            details.st_mtime_ns,
            details.st_ctime_ns,
        )

    @property
    def stable_directory_identity(self) -> tuple[int, ...]:
        return (self.device, self.inode, self.mode, self.uid, self.gid)


@dataclass(frozen=True)
class _Directory:
    fd: int
    name: str | None
    parent_index: int | None
    role: str
    opened: _Identity


class _WAWRuntimeStaticKey:
    """Descriptor-held fixed key with one-use authority and ownership transfer."""

    def __init__(
        self,
        *,
        directories: tuple[_Directory, ...],
        key_fd: int,
        key_opened: _Identity,
        runtime_uid: int,
        runtime_gid: int,
        ancestor_uid: int,
        syscalls: _StaticKeySyscalls,
    ) -> None:
        self._directories = directories
        self._key_fd = key_fd
        self._key_opened = key_opened
        self._runtime_uid = runtime_uid
        self._runtime_gid = runtime_gid
        self._ancestor_uid = ancestor_uid
        self._syscalls = syscalls
        self._state = "OWNED"
        self._preflight_complete = False
        self._bound_authority: WAWVerifiedExecutionAuthority | None = None
        self._bound_fingerprint: str | None = None
        self._close_result: bool | None = None
        self._lock = threading.RLock()

    def take(self) -> _WAWRuntimeStaticKey:
        with self._lock:
            self._require_owned()
            transferred = object.__new__(_WAWRuntimeStaticKey)
            transferred._directories = self._directories
            transferred._key_fd = self._key_fd
            transferred._key_opened = self._key_opened
            transferred._runtime_uid = self._runtime_uid
            transferred._runtime_gid = self._runtime_gid
            transferred._ancestor_uid = self._ancestor_uid
            transferred._syscalls = self._syscalls
            transferred._state = "OWNED"
            transferred._preflight_complete = self._preflight_complete
            transferred._bound_authority = self._bound_authority
            transferred._bound_fingerprint = self._bound_fingerprint
            transferred._close_result = None
            transferred._lock = threading.RLock()
            self._directories = ()
            self._key_fd = -1
            self._state = "TRANSFERRED"
            return transferred

    def preflight(self) -> None:
        with self._lock:
            self._require_owned()
            try:
                self._read_validated_key()
            except BaseException:
                self._poison()
                raise
            self._preflight_complete = True

    def bind_authority(self, authority: WAWVerifiedExecutionAuthority) -> None:
        with self._lock:
            self._require_owned()
            if not self._preflight_complete:
                raise WAWRuntimeStaticKeyError("Runtime static key preflight is incomplete")
            if self._bound_authority is not None or self._bound_fingerprint is not None:
                self._poison()
                raise WAWRuntimeStaticKeyError("Runtime static key authority is already bound")
            if type(authority) is not WAWVerifiedExecutionAuthority:
                self._poison()
                raise WAWRuntimeStaticKeyError("Runtime static key authority is invalid")
            try:
                raw = self._read_validated_key()
                fingerprint = _public_fingerprint(raw)
                expected = authority.runtime_attestation_x25519_fingerprint
                if not hmac.compare_digest(fingerprint, expected):
                    raise WAWRuntimeStaticKeyError("Runtime static key authority does not match")
            except BaseException:
                self._poison()
                raise
            self._bound_authority = authority
            self._bound_fingerprint = fingerprint

    def private_key(self) -> bytes:
        with self._lock:
            self._require_owned()
            authority = self._bound_authority
            fingerprint = self._bound_fingerprint
            if authority is None or fingerprint is None:
                raise WAWRuntimeStaticKeyError("Runtime static key authority is not bound")
            try:
                raw = self._read_validated_key()
                observed = _public_fingerprint(raw)
                expected = authority.runtime_attestation_x25519_fingerprint
                if not (
                    hmac.compare_digest(observed, fingerprint)
                    and hmac.compare_digest(observed, expected)
                ):
                    raise WAWRuntimeStaticKeyError("Runtime static key changed after binding")
                return raw
            except BaseException:
                self._poison()
                raise

    def close(self) -> bool:
        with self._lock:
            if self._state == "TRANSFERRED":
                return True
            if self._close_result is not None:
                return self._close_result
            descriptors = [self._key_fd, *(item.fd for item in reversed(self._directories))]
            self._key_fd = -1
            self._directories = ()
            self._bound_authority = None
            self._bound_fingerprint = None
            self._state = "CLOSED"
            clean = True
            for descriptor in descriptors:
                if descriptor < 0:
                    continue
                try:
                    self._syscalls.close(descriptor)
                except BaseException:
                    clean = False
            self._close_result = clean
            return clean

    def _read_validated_key(self) -> bytes:
        before_directories, before_key = self._validate_tree()
        try:
            raw = self._syscalls.pread(self._key_fd, _KEY_BYTES + 1, 0)
        except OSError:
            raise WAWRuntimeStaticKeyError("Runtime static key cannot be read") from None
        after_directories, after_key = self._validate_tree()
        if before_directories != after_directories or before_key != after_key:
            raise WAWRuntimeStaticKeyError("Runtime static key changed during read")
        if len(raw) != _KEY_BYTES:
            raise WAWRuntimeStaticKeyError("Runtime static key has invalid size")
        return raw

    def _validate_tree(self) -> tuple[tuple[_Identity, ...], _Identity]:
        if self._key_fd < 0 or len(self._directories) != 5:
            raise WAWRuntimeStaticKeyError("Runtime static key custody is unavailable")
        captured: list[_Identity] = []
        try:
            for item in self._directories:
                observed = _Identity.capture(self._syscalls.fstat(item.fd))
                self._validate_directory(observed, item.role)
                if observed.stable_directory_identity != item.opened.stable_directory_identity:
                    raise WAWRuntimeStaticKeyError("Runtime static key parent changed")
                if item.parent_index is not None and item.name is not None:
                    parent_fd = self._directories[item.parent_index].fd
                    entry = _Identity.capture(self._syscalls.stat(item.name, dir_fd=parent_fd))
                    if entry.stable_directory_identity != observed.stable_directory_identity:
                        raise WAWRuntimeStaticKeyError("Runtime static key parent entry changed")
                captured.append(observed)
            key = _Identity.capture(self._syscalls.fstat(self._key_fd))
            self._validate_key(key)
            if key != self._key_opened:
                raise WAWRuntimeStaticKeyError("Runtime static key descriptor changed")
            entry = _Identity.capture(
                self._syscalls.stat(_KEY_FILENAME, dir_fd=self._directories[-1].fd)
            )
            if entry != key:
                raise WAWRuntimeStaticKeyError("Runtime static key entry changed")
            return tuple(captured), key
        except WAWRuntimeStaticKeyError:
            raise
        except OSError:
            raise WAWRuntimeStaticKeyError("Runtime static key provenance is unavailable") from None

    def _validate_directory(self, details: _Identity, role: str) -> None:
        _validate_directory_identity(
            details,
            role=role,
            runtime_uid=self._runtime_uid,
            runtime_gid=self._runtime_gid,
            ancestor_uid=self._ancestor_uid,
        )

    def _validate_key(self, details: _Identity) -> None:
        _validate_key_identity(details, self._runtime_uid, self._runtime_gid)

    def _require_owned(self) -> None:
        if self._state != "OWNED":
            raise WAWRuntimeStaticKeyError("Runtime static key custody is unavailable")

    def _poison(self) -> None:
        if self._state == "OWNED":
            self._state = "POISONED"

    def __repr__(self) -> str:
        return f"_WAWRuntimeStaticKey(state={self._state!r})"


def _public_fingerprint(raw: bytes) -> str:
    try:
        public = X25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw()
    except (TypeError, ValueError) as exc:
        raise WAWRuntimeStaticKeyError("Runtime static key material is invalid") from exc
    return hashlib.sha256(public).hexdigest()


def _validate_directory_identity(
    details: _Identity,
    *,
    role: str,
    runtime_uid: int,
    runtime_gid: int,
    ancestor_uid: int,
) -> None:
    if not stat.S_ISDIR(details.mode):
        raise WAWRuntimeStaticKeyError("Runtime static key parent is invalid")
    mode = stat.S_IMODE(details.mode)
    if role == "ancestor":
        valid = details.uid == ancestor_uid and mode & 0o022 == 0
    elif role == "runtime-root":
        valid = details.uid == ancestor_uid and details.gid == runtime_gid and mode == 0o750
    else:
        valid = details.uid == runtime_uid and details.gid == runtime_gid and mode == 0o700
    if not valid:
        raise WAWRuntimeStaticKeyError("Runtime static key parent provenance is invalid")


def _validate_key_identity(details: _Identity, runtime_uid: int, runtime_gid: int) -> None:
    if (
        not stat.S_ISREG(details.mode)
        or details.uid != runtime_uid
        or details.gid != runtime_gid
        or stat.S_IMODE(details.mode) != 0o600
        or details.links != 1
        or details.size != _KEY_BYTES
    ):
        raise WAWRuntimeStaticKeyError("Runtime static key provenance is invalid")


def _open_waw_runtime_static_key() -> _WAWRuntimeStaticKey:
    """Open the fixed production key as the exact non-root Runtime account."""

    try:
        account = pwd.getpwnam(_RUNTIME_ACCOUNT)
        group = grp.getgrnam(_RUNTIME_ACCOUNT)
    except (KeyError, OSError):
        raise WAWRuntimeStaticKeyError("Runtime static key identity is unavailable") from None
    if account.pw_uid == 0 or account.pw_gid != group.gr_gid:
        raise WAWRuntimeStaticKeyError("Runtime static key identity is invalid")
    _require_exact_process_identity(account.pw_uid, group.gr_gid)
    return _open_fixed_key(
        root=_FIXED_ROOT,
        runtime_uid=account.pw_uid,
        runtime_gid=group.gr_gid,
        ancestor_uid=0,
        syscalls=_SYSCALLS,
    )


def _open_waw_runtime_static_key_test_only(
    root: Path,
    *,
    syscalls: _StaticKeySyscalls = _SYSCALLS,
) -> _WAWRuntimeStaticKey:
    """Open a fixture tree while preserving production provenance checks."""

    if not isinstance(root, Path) or not root.is_absolute():
        raise TypeError("test root must be an absolute Path")
    runtime_uid = os.geteuid()
    runtime_gid = os.getegid()
    if runtime_uid == 0:
        raise WAWRuntimeStaticKeyError("Runtime static key identity is invalid")
    _require_exact_process_identity(runtime_uid, runtime_gid)
    return _open_fixed_key(
        root=root,
        runtime_uid=runtime_uid,
        runtime_gid=runtime_gid,
        ancestor_uid=runtime_uid,
        syscalls=syscalls,
    )


def _require_exact_process_identity(runtime_uid: int, runtime_gid: int) -> None:
    uid_values = (
        os.getresuid() if hasattr(os, "getresuid") else (os.getuid(), os.geteuid(), os.geteuid())
    )
    gid_values = (
        os.getresgid() if hasattr(os, "getresgid") else (os.getgid(), os.getegid(), os.getegid())
    )
    if any(value != runtime_uid for value in uid_values) or any(
        value != runtime_gid for value in gid_values
    ):
        raise WAWRuntimeStaticKeyError("Runtime static key process identity is invalid")


def _open_fixed_key(
    *,
    root: Path,
    runtime_uid: int,
    runtime_gid: int,
    ancestor_uid: int,
    syscalls: _StaticKeySyscalls,
) -> _WAWRuntimeStaticKey:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    key_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptors: list[int] = []
    directories: list[_Directory] = []
    failure: BaseException | None = None
    try:
        root_fd = syscalls.open(root, directory_flags)
        descriptors.append(root_fd)
        root_identity = _Identity.capture(syscalls.fstat(root_fd))
        _validate_directory_identity(
            root_identity,
            role="ancestor",
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
            ancestor_uid=ancestor_uid,
        )
        directories.append(_Directory(root_fd, None, None, "ancestor", root_identity))
        parent_fd = root_fd
        for index, component in enumerate(_DIRECTORY_COMPONENTS):
            role = "ancestor" if index < 2 else "runtime-root" if index == 2 else "key-root"
            entry = _Identity.capture(syscalls.stat(component, dir_fd=parent_fd))
            _validate_directory_identity(
                entry,
                role=role,
                runtime_uid=runtime_uid,
                runtime_gid=runtime_gid,
                ancestor_uid=ancestor_uid,
            )
            child_fd = syscalls.open(component, directory_flags, dir_fd=parent_fd)
            descriptors.append(child_fd)
            opened = _Identity.capture(syscalls.fstat(child_fd))
            if entry.stable_directory_identity != opened.stable_directory_identity:
                raise WAWRuntimeStaticKeyError("Runtime static key parent changed during open")
            _validate_directory_identity(
                opened,
                role=role,
                runtime_uid=runtime_uid,
                runtime_gid=runtime_gid,
                ancestor_uid=ancestor_uid,
            )
            directories.append(_Directory(child_fd, component, index, role, opened))
            parent_fd = child_fd
        key_entry = _Identity.capture(syscalls.stat(_KEY_FILENAME, dir_fd=parent_fd))
        _validate_key_identity(key_entry, runtime_uid, runtime_gid)
        key_fd = syscalls.open(_KEY_FILENAME, key_flags, dir_fd=parent_fd)
        descriptors.append(key_fd)
        key_opened = _Identity.capture(syscalls.fstat(key_fd))
        if key_entry != key_opened:
            raise WAWRuntimeStaticKeyError("Runtime static key changed during open")
        _validate_key_identity(key_opened, runtime_uid, runtime_gid)
        port = _WAWRuntimeStaticKey(
            directories=tuple(directories),
            key_fd=key_fd,
            key_opened=key_opened,
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
            ancestor_uid=ancestor_uid,
            syscalls=syscalls,
        )
        port._validate_tree()
        descriptors.clear()
        return port
    except BaseException as exc:
        failure = _safe_construction_failure(exc)

    cleanup_clean = True
    for descriptor in reversed(descriptors):
        try:
            syscalls.close(descriptor)
        except BaseException:
            cleanup_clean = False
    if not cleanup_clean:
        assert failure is not None
        raise WAWRuntimeStaticKeyConstructionCleanupError(failure) from failure
    assert failure is not None
    raise failure


def _safe_construction_failure(failure: BaseException) -> BaseException:
    if isinstance(failure, WAWRuntimeStaticKeyError) or not isinstance(failure, Exception):
        return failure
    return WAWRuntimeStaticKeyError("Runtime static key cannot be opened safely")
