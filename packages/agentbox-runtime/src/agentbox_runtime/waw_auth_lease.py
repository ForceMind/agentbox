"""Sealed auth-probe lease over one fixed transport cgroup and scratch tree.

A production, not-yet-started :class:`WAWFixedTransport` lends its prepared
generation cgroup to exactly one sealed auth lease at a time.  The lease
owner holds a verified scratch root, creates one exclusive ``0700`` scratch
source directory per borrow, and dups the cgroup workload descriptor for the
lease.  Release is synchronous so cancellation cannot interleave: it proves
the cgroup stayed empty, exclusively removes every scratch entry, and only
then returns interactive launch capability.  Any uncertainty poisons the
lease, the transport, and the owner.  The module retains metadata only; it
never reads credential or key material.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import stat
import threading

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_fixed_transport import (
    _CGROUP_AUTH_TOKEN,
    LinuxCgroupControlHandle,
    WAWFixedTransport,
    WAWVerifiedExecutionAuthority,
)
from agentbox_runtime.waw_process_inspector import FixedProcessIdentity

_AUTH_LEASE_TOKEN = object()
_MINIMUM_DUP_FD = 64
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _lease_failure(code: str, message: str) -> RuntimeOperationError:
    return RuntimeOperationError(code, message, category="conflict")


def _close_fd(descriptor: int) -> None:
    with contextlib.suppress(OSError):
        os.close(descriptor)


class WAWSealedAuthLease:
    """Opaque one-generation auth lease issued only by ``WAWAuthLeaseOwner.borrow``."""

    def __init__(
        self,
        token: object,
        *,
        identity: FixedProcessIdentity,
        owner: WAWAuthLeaseOwner,
        transport: WAWFixedTransport,
        cgroup: LinuxCgroupControlHandle,
        cgroup_fd: int,
        workspace_fd: int,
        scratch_name: str,
        scratch_fd: int,
    ) -> None:
        if token is not _AUTH_LEASE_TOKEN:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Sealed auth leases are not caller-constructible",
                category="unavailable",
            )
        self._identity = identity
        self._owner = owner
        self._transport = transport
        self._cgroup = cgroup
        self._cgroup_fd = cgroup_fd
        self._workspace_fd = workspace_fd
        self._scratch_name = scratch_name
        self._scratch_fd = scratch_fd
        self._state = "OWNED"
        self._lock = threading.RLock()

    @property
    def identity(self) -> FixedProcessIdentity:
        return self._identity

    def cgroup_fd(self) -> int:
        """Dup the borrowed cgroup workload directory; the caller closes it.

        Distributed dups are not reclaimed by ``release``; the probe path must
        close every dup it made before releasing the lease.
        """

        with self._lock:
            self._require_owned()
            return fcntl.fcntl(self._cgroup_fd, fcntl.F_DUPFD_CLOEXEC, _MINIMUM_DUP_FD)

    def scratch_fd(self) -> int:
        """Dup the exclusive auth scratch source directory; the caller closes it.

        Distributed dups are not reclaimed by ``release``; the probe path must
        close every dup it made before releasing the lease.
        """

        with self._lock:
            self._require_owned()
            return fcntl.fcntl(self._scratch_fd, fcntl.F_DUPFD_CLOEXEC, _MINIMUM_DUP_FD)

    def _require_owned(self) -> None:
        if self._state == "POISONED":
            raise _lease_failure("WAW_AUTH_LEASE_POISONED", "Sealed auth lease is poisoned")
        if self._state != "OWNED":
            raise _lease_failure("WAW_AUTH_LEASE_STALE", "Sealed auth lease is released")

    def __repr__(self) -> str:
        return f"WAWSealedAuthLease(state={self._state!r})"


class WAWAuthLeaseOwner:
    """Issue and reclaim the single sealed auth lease of one fixed transport."""

    def __init__(self, authority: WAWVerifiedExecutionAuthority, *, scratch_root: int) -> None:
        if type(authority) is not WAWVerifiedExecutionAuthority:
            raise TypeError("verified execution authority is required")
        if type(scratch_root) is not int or scratch_root < 0:
            raise TypeError("auth scratch root must be a directory descriptor")
        try:
            details = os.fstat(scratch_root)
        except OSError as exc:
            raise _lease_failure(
                "WAW_AUTH_LEASE_STALE", "Auth scratch root is unavailable"
            ) from exc
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.geteuid()
            or stat.S_IMODE(details.st_mode) & 0o022 != 0
        ):
            raise _lease_failure("WAW_AUTH_LEASE_STALE", "Auth scratch root provenance is invalid")
        try:
            self._scratch_root = fcntl.fcntl(scratch_root, fcntl.F_DUPFD_CLOEXEC, _MINIMUM_DUP_FD)
        except OSError as exc:
            raise _lease_failure(
                "WAW_AUTH_LEASE_STALE", "Auth scratch root cannot be held"
            ) from exc
        self._authority = authority
        self._closed = False
        self._poisoned = False
        self._lock = threading.RLock()

    @property
    def authority(self) -> WAWVerifiedExecutionAuthority:
        return self._authority

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def closed(self) -> bool:
        return self._closed

    def borrow(self, transport: WAWFixedTransport) -> WAWSealedAuthLease:
        """Borrow one not-yet-started production transport for auth observation."""

        with self._lock:
            self._require_usable()
            if type(transport) is not WAWFixedTransport:
                raise TypeError("exact fixed transport is required")
            if transport._production is not True:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_STALE", "Production fixed transport is required"
                )
            if transport.execution_authority is not self._authority:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_STALE", "Transport is not bound to this authority"
                )
            transport._auth_borrow_precheck()
            identity = transport.process_identity
            cgroup = transport._handles.cgroup
            if type(cgroup) is not LinuxCgroupControlHandle or not cgroup.production_qualified_for(
                self._authority, identity
            ):
                raise _lease_failure(
                    "WAW_AUTH_LEASE_STALE", "Transport cgroup is not authority-qualified"
                )
            if cgroup.populated() != 0 or cgroup.frozen() != 0:
                raise _lease_failure("WAW_AUTH_LEASE_BUSY", "Transport cgroup is not empty")
            return self._borrow_checked(transport, identity, cgroup)

    def _borrow_checked(
        self,
        transport: WAWFixedTransport,
        identity: FixedProcessIdentity,
        cgroup: LinuxCgroupControlHandle,
    ) -> WAWSealedAuthLease:
        workspace_fd = -1
        scratch_fd = -1
        cgroup_fd = -1
        scratch_name = f"auth-probe-g{identity.generation}"
        created = False
        borrowed = False
        try:
            try:
                workspace_fd = os.open(
                    identity.workspace_hash, _DIRECTORY_FLAGS, dir_fd=self._scratch_root
                )
            except OSError as exc:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_STALE", "Auth workspace scratch root is unavailable"
                ) from exc
            self._require_owned_directory(os.fstat(workspace_fd))
            try:
                os.mkdir(scratch_name, 0o700, dir_fd=workspace_fd)
            except FileExistsError:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_BUSY", "Auth scratch residue remains"
                ) from None
            except OSError as exc:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_STALE", "Auth scratch source cannot be created"
                ) from exc
            created = True
            try:
                scratch_fd = os.open(scratch_name, _DIRECTORY_FLAGS, dir_fd=workspace_fd)
                self._require_owned_directory(os.fstat(scratch_fd))
            except OSError as exc:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_STALE", "Auth scratch source cannot be verified"
                ) from exc
            try:
                cgroup_fd = fcntl.fcntl(cgroup._fd(), fcntl.F_DUPFD_CLOEXEC, _MINIMUM_DUP_FD)
            except OSError as exc:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_STALE", "Auth cgroup descriptor cannot be held"
                ) from exc
            cgroup._set_auth_borrowed(_CGROUP_AUTH_TOKEN, True)
            borrowed = True
            lease = WAWSealedAuthLease(
                _AUTH_LEASE_TOKEN,
                identity=identity,
                owner=self,
                transport=transport,
                cgroup=cgroup,
                cgroup_fd=cgroup_fd,
                workspace_fd=workspace_fd,
                scratch_name=scratch_name,
                scratch_fd=scratch_fd,
            )
            transport._borrow_auth_lease(lease)
            return lease
        except BaseException:
            rollback_clean = True
            if borrowed:
                try:
                    cgroup._set_auth_borrowed(_CGROUP_AUTH_TOKEN, False)
                except BaseException:
                    rollback_clean = False
            if created and workspace_fd >= 0:
                try:
                    os.rmdir(scratch_name, dir_fd=workspace_fd)
                except OSError:
                    rollback_clean = False
            for descriptor in (cgroup_fd, scratch_fd, workspace_fd):
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError:
                        rollback_clean = False
            if not rollback_clean:
                transport._poison_from_auth_lease()
                self._poison()
            raise

    def release(self, lease: WAWSealedAuthLease) -> None:
        """Reclaim one lease; synchronous so cancellation cannot interleave."""

        with self._lock:
            self._require_usable()
            if type(lease) is not WAWSealedAuthLease:
                raise TypeError("exact sealed auth lease is required")
            if (
                lease._owner is not self
                or lease._state != "OWNED"
                or getattr(lease._transport, "_auth_lease", None) is not lease
            ):
                self._poison_triple(lease)
                raise _lease_failure(
                    "WAW_AUTH_LEASE_POISONED", "Sealed auth lease ownership is inconsistent"
                )
            try:
                self._release_ceremony(lease)
            except BaseException as exc:
                self._poison_triple(lease)
                if isinstance(exc, RuntimeOperationError) and exc.code == "WAW_AUTH_LEASE_POISONED":
                    raise
                raise _lease_failure(
                    "WAW_AUTH_LEASE_POISONED", "Sealed auth lease release is uncertain"
                ) from exc

    def _release_ceremony(self, lease: WAWSealedAuthLease) -> None:
        cgroup = lease._cgroup
        if cgroup.populated() != 0 or cgroup.frozen() != 0:
            raise _lease_failure("WAW_AUTH_LEASE_POISONED", "Auth cgroup is not empty at release")
        _clean_scratch_directory(lease._scratch_fd)
        os.rmdir(lease._scratch_name, dir_fd=lease._workspace_fd)
        if cgroup.populated() != 0 or cgroup.frozen() != 0:
            raise _lease_failure(
                "WAW_AUTH_LEASE_POISONED", "Auth cgroup became live during release"
            )
        for descriptor in (lease._cgroup_fd, lease._scratch_fd, lease._workspace_fd):
            os.close(descriptor)
        lease._cgroup_fd = -1
        lease._scratch_fd = -1
        lease._workspace_fd = -1
        cgroup._set_auth_borrowed(_CGROUP_AUTH_TOKEN, False)
        lease._transport._release_auth_lease(lease)
        lease._state = "RELEASED"

    def close(self) -> None:
        """Idempotently release the held scratch-root descriptor; terminal state."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            _close_fd(self._scratch_root)

    def _require_usable(self) -> None:
        if self._closed or self._poisoned:
            raise _lease_failure(
                "WAW_AUTH_LEASE_POISONED", "Auth lease owner is closed or poisoned"
            )

    @staticmethod
    def _require_owned_directory(details: os.stat_result) -> None:
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.geteuid()
            or stat.S_IMODE(details.st_mode) != 0o700
        ):
            raise _lease_failure(
                "WAW_AUTH_LEASE_STALE", "Auth scratch directory provenance is invalid"
            )

    def _poison_triple(self, lease: WAWSealedAuthLease) -> None:
        lease._state = "POISONED"
        poison_transport = getattr(lease._transport, "_poison_from_auth_lease", None)
        if callable(poison_transport):
            poison_transport()
        self._poison()

    def _poison(self) -> None:
        self._poisoned = True


def _clean_scratch_directory(scratch_fd: int) -> None:
    """Remove every regular file and empty directory; anything else is uncertain.

    Regular files are unlinked without a chmod (the owned 0700 parent grants
    the directory rights), and directories are opened ``O_NOFOLLOW`` before an
    fd-based fchmod so a swapped symlink can never redirect the mode change.
    """

    for name in os.listdir(scratch_fd):
        if name in (".", "..") or "/" in name or "\x00" in name:
            raise _lease_failure("WAW_AUTH_LEASE_POISONED", "Auth scratch entry is invalid")
        details = os.lstat(name, dir_fd=scratch_fd)
        if stat.S_ISREG(details.st_mode):
            os.unlink(name, dir_fd=scratch_fd)
        elif stat.S_ISDIR(details.st_mode):
            child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=scratch_fd)
            try:
                os.fchmod(child_fd, 0o700)
                nested = os.listdir(child_fd)
            finally:
                os.close(child_fd)
            if nested:
                raise _lease_failure(
                    "WAW_AUTH_LEASE_POISONED", "Auth scratch directory is not empty"
                )
            os.rmdir(name, dir_fd=scratch_fd)
        else:
            raise _lease_failure("WAW_AUTH_LEASE_POISONED", "Auth scratch entry type is unexpected")
    if os.listdir(scratch_fd):
        raise _lease_failure("WAW_AUTH_LEASE_POISONED", "Auth scratch cleanup is incomplete")


__all__ = [
    "WAWAuthLeaseOwner",
    "WAWSealedAuthLease",
]
