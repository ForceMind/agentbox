"""Retained pidfd authority for the sole live WAW API process."""

from __future__ import annotations

import os
import re
import select
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock, RLock
from typing import TypeAlias

from agentbox_runtime.waw_encrypted_stream import RuntimePeer

_POSITIVE_U64 = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_MAX_U64 = 2**64 - 1
_POLL_TERMINAL = select.POLLIN | select.POLLERR | select.POLLHUP | select.POLLNVAL

_dup = os.dup
_close = os.close
_fstat = os.fstat
_set_inheritable = os.set_inheritable
_poll = select.poll


class WAWPeerAuthorityError(RuntimeError):
    """A peer binding or transfer violated the closed authority contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WAWPeerBindStatus(StrEnum):
    BOUND = "BOUND"
    ALREADY_BOUND = "ALREADY_BOUND"


@dataclass(frozen=True)
class WAWProcessIdentity:
    pid: int
    device: int
    inode: int


@dataclass(frozen=True)
class WAWRuntimePeerIdentity:
    process: WAWProcessIdentity
    generation: int


class _PidfdOwner:
    def __init__(self, identity: WAWProcessIdentity, pidfd: int) -> None:
        self._identity = identity
        self._pidfd: int | None = pidfd
        self._fd_lock = Lock()

    @property
    def identity(self) -> WAWProcessIdentity:
        return self._identity

    @property
    def closed(self) -> bool:
        with self._fd_lock:
            return self._pidfd is None

    def fileno(self) -> int:
        with self._fd_lock:
            if self._pidfd is None:
                raise WAWPeerAuthorityError("PEER_CLOSED")
            return self._pidfd

    def current(self) -> bool:
        with self._fd_lock:
            return self._pidfd is not None and _pidfd_current(self._pidfd)

    def close(self) -> None:
        descriptor: int | None
        with self._fd_lock:
            descriptor, self._pidfd = self._pidfd, None
        if descriptor is not None:
            _close(descriptor)

    def _take_pidfd(self) -> int:
        with self._fd_lock:
            if self._pidfd is None:
                raise WAWPeerAuthorityError("PEER_CLOSED")
            descriptor, self._pidfd = self._pidfd, None
            return descriptor


class WAWPeerCandidate(_PidfdOwner):
    """One observed live caller process; no request metadata is attached."""


class WAWPeerLease(_PidfdOwner):
    """Borrowed view of one exact retained authority generation."""

    def __init__(
        self,
        authority: WAWPeerAuthority,
        identity: WAWRuntimePeerIdentity,
        pidfd: int,
        api_authority_epoch: str,
    ) -> None:
        super().__init__(identity.process, pidfd)
        self._authority = authority
        self._runtime_identity = identity
        self._api_authority_epoch = api_authority_epoch
        self._view = RuntimePeer(
            identity,
            api_authority_epoch,
            lambda: authority._runtime_peer_current(identity),
        )

    @property
    def runtime_identity(self) -> WAWRuntimePeerIdentity:
        return self._runtime_identity

    @property
    def runtime_peer(self) -> RuntimePeer:
        return self._view

    @property
    def api_authority_epoch(self) -> str:
        return self._api_authority_epoch

    def current(self) -> bool:
        return self._authority._lease_current(self)

    def _current_under_authority(self) -> bool:
        with self._fd_lock:
            return self._pidfd is not None and _pidfd_current(self._pidfd)


class WAWPeerTransferPlan(_PidfdOwner):
    """Single-use CAS plan owning the candidate/lease pidfd until commit."""

    def __init__(
        self,
        token: object,
        identity: WAWProcessIdentity,
        pidfd: int,
        *,
        api_authority_epoch: str,
        nonce_digest: bytes,
        status: WAWPeerBindStatus,
        authority_version: int,
        expected_generation: int | None,
        revocation_required: bool,
        replaces_generation: int | None,
    ) -> None:
        super().__init__(identity, pidfd)
        self._token = token
        self._api_authority_epoch = api_authority_epoch
        self._nonce_digest = nonce_digest
        self._status = status
        self._authority_version = authority_version
        self._expected_generation = expected_generation
        self._revocation_required = revocation_required
        self._replaces_generation = replaces_generation

    @property
    def api_authority_epoch(self) -> str:
        return self._api_authority_epoch

    @property
    def nonce_digest(self) -> bytes:
        return self._nonce_digest

    @property
    def status(self) -> WAWPeerBindStatus:
        return self._status

    @property
    def authority_version(self) -> int:
        return self._authority_version

    @property
    def expected_generation(self) -> int | None:
        return self._expected_generation

    @property
    def revocation_required(self) -> bool:
        return self._revocation_required

    @property
    def replaces_generation(self) -> int | None:
        return self._replaces_generation


ObservedPeer: TypeAlias = WAWPeerCandidate | WAWPeerLease | None


@dataclass
class _CurrentAuthority:
    identity: WAWRuntimePeerIdentity
    pidfd: int
    api_authority_epoch: str
    nonce_digest: bytes


class WAWPeerAuthority:
    """Serialize one live API authority and irreversible generation transfers."""

    def __init__(
        self,
        *,
        expected_uid: int,
        expected_gid: int,
        max_retired_epochs: int = 64,
    ) -> None:
        if type(expected_uid) is not int or expected_uid < 0:
            raise ValueError("expected_uid is invalid")
        if type(expected_gid) is not int or expected_gid < 0:
            raise ValueError("expected_gid is invalid")
        if type(max_retired_epochs) is not int or not 1 <= max_retired_epochs <= 1024:
            raise ValueError("max_retired_epochs is invalid")
        self._expected_uid = expected_uid
        self._expected_gid = expected_gid
        self._max_retired = max_retired_epochs
        self._retired: set[str] = set()
        self._current: _CurrentAuthority | None = None
        self._pending: WAWPeerTransferPlan | None = None
        self._next_generation = 1
        self._version = 0
        self._closed = False
        self._poisoned = False
        self._close_failure: WAWPeerAuthorityError | None = None
        self._lock = RLock()

    @property
    def poisoned(self) -> bool:
        with self._lock:
            return self._poisoned

    @property
    def retired_epochs(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._retired))

    def observe_control(self, pid: int, uid: int, gid: int, pidfd: int) -> ObservedPeer:
        if any(type(value) is not int for value in (pid, uid, gid)) or pid <= 0:
            raise WAWPeerAuthorityError("PEER_INVALID")
        with self._lock:
            self._require_open()
        if uid != self._expected_uid or gid != self._expected_gid:
            return None
        if type(pidfd) is not int or pidfd < 0:
            raise WAWPeerAuthorityError("PEER_INVALID")
        identity = _process_identity(pid, pidfd)
        if not _pidfd_current(pidfd):
            raise WAWPeerAuthorityError("PEER_NOT_CURRENT")
        with self._lock:
            self._require_open()
            current = self._current
            if (
                current is not None
                and self._current_live(current)
                and current.identity.process == identity
            ):
                return self._borrow_locked(current)
            duplicate = _duplicate_pidfd(pidfd)
            try:
                if _process_identity(pid, duplicate) != identity or not _pidfd_current(duplicate):
                    raise WAWPeerAuthorityError("PEER_NOT_CURRENT")
                return WAWPeerCandidate(identity, duplicate)
            except BaseException:
                _close(duplicate)
                raise

    def borrow(self) -> WAWPeerLease | None:
        with self._lock:
            self._require_open()
            current = self._current
            if current is None or not self._current_live(current):
                return None
            return self._borrow_locked(current)

    def prepare_bind(
        self,
        peer: WAWPeerCandidate | WAWPeerLease,
        *,
        api_authority_epoch: str,
        nonce_digest: bytes,
    ) -> WAWPeerTransferPlan:
        epoch = _validate_epoch(api_authority_epoch)
        nonce = _validate_nonce_digest(nonce_digest)
        if type(peer) not in {WAWPeerCandidate, WAWPeerLease}:
            raise TypeError("peer must be an observed candidate or lease")
        if type(peer) is WAWPeerLease and peer._authority is not self:
            raise WAWPeerAuthorityError("PEER_INVALID")
        with self._lock:
            self._require_open()
            if self._pending is not None:
                raise WAWPeerAuthorityError("TRANSFER_IN_PROGRESS")
            if not peer.current():
                raise WAWPeerAuthorityError("PEER_NOT_CURRENT")
            current = self._current
            status = WAWPeerBindStatus.BOUND
            expected_generation: int | None = None
            revocation_required = False
            replaces_generation: int | None = None
            if current is not None and self._current_live(current):
                if current.identity.process != peer.identity:
                    raise WAWPeerAuthorityError("AUTHORITY_CONFLICT")
                if current.api_authority_epoch != epoch or current.nonce_digest != nonce:
                    raise WAWPeerAuthorityError("AUTHORITY_CONFLICT")
                status = WAWPeerBindStatus.ALREADY_BOUND
                expected_generation = current.identity.generation
            else:
                if epoch in self._retired:
                    raise WAWPeerAuthorityError("EPOCH_RETIRED")
                if current is not None:
                    if epoch == current.api_authority_epoch:
                        raise WAWPeerAuthorityError("EPOCH_RETIRED")
                    replaces_generation = current.identity.generation
                    descriptor = self._detach_terminal_current_locked(current)
                    revocation_required = True
                    try:
                        _close(descriptor)
                    except OSError:
                        raise self._record_close_failure() from None
            descriptor = peer._take_pidfd()
            plan = WAWPeerTransferPlan(
                object(),
                peer.identity,
                descriptor,
                api_authority_epoch=epoch,
                nonce_digest=nonce,
                status=status,
                authority_version=self._version,
                expected_generation=expected_generation,
                revocation_required=revocation_required,
                replaces_generation=replaces_generation,
            )
            self._pending = plan
            return plan

    def commit_bind(self, plan: WAWPeerTransferPlan) -> WAWPeerBindStatus:
        if type(plan) is not WAWPeerTransferPlan:
            raise TypeError("plan must be WAWPeerTransferPlan")
        with self._lock:
            self._require_open()
            if self._pending is not plan or plan.authority_version != self._version:
                if self._pending is plan and plan.revocation_required:
                    self._poisoned = True
                raise WAWPeerAuthorityError("TRANSFER_STALE")
            if not plan.current():
                self._fail_pending_locked(plan, poison=plan.revocation_required)
                raise WAWPeerAuthorityError("PEER_NOT_CURRENT")
            if plan.status is WAWPeerBindStatus.ALREADY_BOUND:
                current = self._current
                if (
                    current is None
                    or current.identity.generation != plan.expected_generation
                    or current.identity.process != plan.identity
                    or not self._current_live(current)
                ):
                    self._fail_pending_locked(plan, poison=False)
                    raise WAWPeerAuthorityError("TRANSFER_STALE")
                self._pending = None
                self._version += 1
                try:
                    plan.close()
                except OSError:
                    raise self._record_close_failure() from None
                return WAWPeerBindStatus.ALREADY_BOUND
            if self._current is not None or plan.api_authority_epoch in self._retired:
                self._fail_pending_locked(plan, poison=plan.revocation_required)
                raise WAWPeerAuthorityError("TRANSFER_STALE")
            try:
                descriptor = plan._take_pidfd()
            except WAWPeerAuthorityError:
                self._fail_pending_locked(plan, poison=plan.revocation_required)
                raise
            identity = WAWRuntimePeerIdentity(plan.identity, self._next_generation)
            self._next_generation += 1
            self._current = _CurrentAuthority(
                identity,
                descriptor,
                plan.api_authority_epoch,
                plan.nonce_digest,
            )
            self._pending = None
            self._version += 1
            return WAWPeerBindStatus.BOUND

    def fail_bind(self, plan: WAWPeerTransferPlan) -> None:
        if type(plan) is not WAWPeerTransferPlan:
            raise TypeError("plan must be WAWPeerTransferPlan")
        with self._lock:
            self._require_open()
            if self._pending is not plan:
                raise WAWPeerAuthorityError("TRANSFER_STALE")
            self._fail_pending_locked(plan, poison=plan.revocation_required)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                if self._close_failure is not None:
                    raise self._close_failure
                return
            self._closed = True
            pending, self._pending = self._pending, None
            current, self._current = self._current, None
            self._version += 1
        first_error: WAWPeerAuthorityError | None = None
        if pending is not None:
            try:
                pending.close()
            except OSError:
                first_error = WAWPeerAuthorityError("PEER_CLOSE_FAILED")
        if current is not None:
            try:
                _close(current.pidfd)
            except OSError:
                if first_error is None:
                    first_error = WAWPeerAuthorityError("PEER_CLOSE_FAILED")
        if first_error is not None:
            self._record_close_failure(first_error)
        with self._lock:
            failure = self._close_failure
        if failure is not None:
            raise failure

    def _borrow_locked(self, current: _CurrentAuthority) -> WAWPeerLease:
        duplicate = _duplicate_pidfd(current.pidfd)
        if not _pidfd_current(duplicate):
            _close(duplicate)
            raise WAWPeerAuthorityError("PEER_NOT_CURRENT")
        return WAWPeerLease(
            self,
            current.identity,
            duplicate,
            current.api_authority_epoch,
        )

    def _lease_current(self, lease: WAWPeerLease) -> bool:
        with self._lock:
            current = self._current
            return (
                not self._closed
                and not self._poisoned
                and current is not None
                and current.identity is lease.runtime_identity
                and self._current_live(current)
                and lease._current_under_authority()
            )

    def _runtime_peer_current(self, identity: WAWRuntimePeerIdentity) -> bool:
        with self._lock:
            current = self._current
            return (
                not self._closed
                and not self._poisoned
                and current is not None
                and current.identity is identity
                and self._current_live(current)
            )

    def _current_live(self, current: _CurrentAuthority) -> bool:
        return _pidfd_current(current.pidfd)

    def _detach_terminal_current_locked(self, current: _CurrentAuthority) -> int:
        if current.api_authority_epoch not in self._retired:
            if len(self._retired) >= self._max_retired:
                raise WAWPeerAuthorityError("RETIRED_EPOCHS_FULL")
            self._retired.add(current.api_authority_epoch)
        self._current = None
        self._version += 1
        return current.pidfd

    def _fail_pending_locked(self, plan: WAWPeerTransferPlan, *, poison: bool) -> None:
        self._pending = None
        self._version += 1
        self._poisoned |= poison
        try:
            plan.close()
        except OSError:
            raise self._record_close_failure() from None

    def _record_close_failure(
        self, failure: WAWPeerAuthorityError | None = None
    ) -> WAWPeerAuthorityError:
        with self._lock:
            self._poisoned = True
            if self._close_failure is None:
                self._close_failure = failure or WAWPeerAuthorityError("PEER_CLOSE_FAILED")
            return self._close_failure

    def _require_open(self) -> None:
        if self._closed:
            raise WAWPeerAuthorityError("AUTHORITY_CLOSED")
        if self._poisoned:
            raise WAWPeerAuthorityError("AUTHORITY_POISONED")


def _validate_epoch(value: str) -> str:
    if type(value) is not str or _POSITIVE_U64.fullmatch(value) is None:
        raise WAWPeerAuthorityError("EPOCH_INVALID")
    if int(value) > _MAX_U64:
        raise WAWPeerAuthorityError("EPOCH_INVALID")
    return value


def _validate_nonce_digest(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) != 32:
        raise WAWPeerAuthorityError("NONCE_DIGEST_INVALID")
    return value


def _process_identity(pid: int, pidfd: int) -> WAWProcessIdentity:
    try:
        details = _fstat(pidfd)
    except OSError as exc:
        raise WAWPeerAuthorityError("PEER_INVALID") from exc
    return WAWProcessIdentity(pid, details.st_dev, details.st_ino)


def _duplicate_pidfd(pidfd: int) -> int:
    try:
        duplicate = _dup(pidfd)
        try:
            _set_inheritable(duplicate, False)
        except BaseException:
            _close(duplicate)
            raise
        return duplicate
    except OSError as exc:
        raise WAWPeerAuthorityError("PEER_INVALID") from exc


def _pidfd_current(pidfd: int) -> bool:
    try:
        poller = _poll()
        poller.register(pidfd, _POLL_TERMINAL)
        return not any(events & _POLL_TERMINAL for _descriptor, events in poller.poll(0))
    except (OSError, OverflowError, ValueError):
        return False


__all__ = [
    "ObservedPeer",
    "WAWPeerAuthority",
    "WAWPeerAuthorityError",
    "WAWPeerBindStatus",
    "WAWPeerCandidate",
    "WAWPeerLease",
    "WAWPeerTransferPlan",
    "WAWProcessIdentity",
    "WAWRuntimePeerIdentity",
]
