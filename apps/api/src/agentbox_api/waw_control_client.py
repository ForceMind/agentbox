"""Bounded API-side client for the dedicated WAW control socket.

This client is intentionally a one-request/one-response transport.  It never
opens the legacy Runtime socket, unlinks socket paths, or exposes a generic
action gateway to callers.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import hmac
import inspect
import os
import select
import socket
import stat
import struct
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from agentbox_protocol.waw_control import (
    MAX_CONTROL_ENVELOPE,
    MAX_CONTROL_LINE,
    WAWControlError,
    decode_control_response,
    encode_control_request,
)


class WAWControlClientError(RuntimeError):
    """Transport or protocol failure talking to the WAW Runtime endpoint."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


_MAX_CANCELLATION_GRACE_SECONDS = 1.0


class BackgroundWorkOwner(Protocol):
    """Process owner which observes cancellation-resistant transport work."""

    def track_background(self, future: asyncio.Future[Any]) -> None: ...


_MAX_DETACHED_TASKS = 32


@dataclass(frozen=True)
class WAWSocketPathIdentity:
    """Stable identity observed for a root-owned Unix socket path."""

    device: int
    inode: int


@dataclass(frozen=True)
class _RuntimePeerObservation:
    pid: int
    uid: int
    gid: int
    pidfd: int


def _pidfd_current(pidfd: int) -> bool:
    """Return true only while the retained kernel process handle is live."""

    try:
        os.fstat(pidfd)
        poller = select.poll()
        poller.register(pidfd, select.POLLIN | select.POLLHUP | select.POLLERR | select.POLLNVAL)
        return not bool(poller.poll(0))
    except (OSError, ValueError):
        return False


def _peer_credentials(peer_socket: Any) -> tuple[int, int, int]:
    option = getattr(socket, "SO_PEERCRED", None)
    if type(option) is not int:
        raise WAWControlClientError(
            "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer credentials are not trusted"
        )
    try:
        raw = cast(
            bytes,
            peer_socket.getsockopt(socket.SOL_SOCKET, option, struct.calcsize("3i")),
        )
        pid, uid, gid = cast(tuple[int, int, int], struct.unpack("3i", raw))
    except (AttributeError, OSError, struct.error) as exc:
        raise WAWControlClientError(
            "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer credentials are not trusted"
        ) from exc
    if pid <= 1 or uid < 0 or gid < 0:
        raise WAWControlClientError(
            "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer credentials are not trusted"
        )
    return pid, uid, gid


def _peer_pidfd(peer_socket: Any, pid: int) -> int:
    """Capture the connected peer, preferring Linux's atomic socket pidfd."""

    option = getattr(socket, "SO_PEERPIDFD", None)
    if type(option) is int:
        try:
            pidfd = cast(int, peer_socket.getsockopt(socket.SOL_SOCKET, option))
        except OSError as exc:
            if exc.errno not in {
                errno.EINVAL,
                errno.ENOPROTOOPT,
                getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
                errno.EOPNOTSUPP,
            }:
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer pidfd is unavailable"
                ) from exc
        else:
            if type(pidfd) is not int or pidfd < 0:
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer pidfd is unavailable"
                )
            try:
                os.set_inheritable(pidfd, False)
            except OSError as exc:
                with contextlib.suppress(OSError):
                    os.close(pidfd)
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer pidfd is unavailable"
                ) from exc
            if not _pidfd_current(pidfd):
                with contextlib.suppress(OSError):
                    os.close(pidfd)
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer exited during authentication"
                )
            return pidfd
    opener = getattr(os, "pidfd_open", None)
    if not callable(opener):
        raise WAWControlClientError(
            "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer pidfd is unavailable"
        )
    pidfd = -1
    try:
        pidfd = cast(int, opener(pid, 0))
        os.set_inheritable(pidfd, False)
    except (OSError, OverflowError, ValueError) as exc:
        if pidfd >= 0:
            with contextlib.suppress(OSError):
                os.close(pidfd)
        raise WAWControlClientError(
            "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer pidfd is unavailable"
        ) from exc
    if not _pidfd_current(pidfd):
        with contextlib.suppress(OSError):
            os.close(pidfd)
        raise WAWControlClientError(
            "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer exited during authentication"
        )
    return pidfd


class RuntimePeerBorrow:
    """One connection-scoped duplicate of an already-bound Runtime pidfd."""

    def __init__(self, parent: BoundRuntimePeer, pidfd: int, generation: int) -> None:
        try:
            inheritable = os.get_inheritable(pidfd) if type(pidfd) is int and pidfd >= 0 else True
        except OSError:
            inheritable = True
        invalid = (
            type(parent) is not BoundRuntimePeer
            or type(pidfd) is not int
            or pidfd < 0
            or type(generation) is not int
            or generation <= 0
            or inheritable
        )
        if invalid:
            if type(pidfd) is int and pidfd >= 0:
                with contextlib.suppress(OSError):
                    os.close(pidfd)
            raise ValueError("Runtime peer borrow is invalid")
        self._parent = parent
        self._pidfd = pidfd
        self._generation = generation
        self._lock = threading.Lock()
        self._close_failure: WAWControlClientError | None = None

    @property
    def parent(self) -> BoundRuntimePeer:
        return self._parent

    @property
    def generation(self) -> int:
        return self._generation

    def current(self) -> bool:
        with self._lock:
            pidfd = self._pidfd
            return (
                pidfd >= 0
                and self._close_failure is None
                and self._parent.current(generation=self._generation)
                and _pidfd_current(pidfd)
            )

    def close(self) -> None:
        with self._lock:
            pidfd, self._pidfd = self._pidfd, -1
            failure = self._close_failure
        if failure is not None:
            raise failure
        if pidfd >= 0:
            try:
                os.close(pidfd)
            except OSError as exc:
                failure = WAWControlClientError(
                    "RUNTIME_UNAVAILABLE", "WAW Runtime peer borrow pidfd close failed"
                )
                with self._lock:
                    if self._close_failure is None:
                        self._close_failure = failure
                    failure = self._close_failure
                self._parent._borrow_close_failed(failure)
                raise failure from exc

    def fence_after_fork(self) -> None:
        """Close a pidfd inherited by an unsupported post-start fork child."""

        pidfd, self._pidfd = self._pidfd, -1
        if pidfd >= 0:
            with contextlib.suppress(OSError):
                os.close(pidfd)


class BoundRuntimePeer:
    """Process-lifetime Runtime identity published only after verified bind.

    Every connection borrows a duplicate of this retained pidfd.  A later
    numeric PID lookup is never used to construct a borrow, so PID reuse cannot
    substitute another Runtime after bind.
    """

    def __init__(
        self,
        observation: _RuntimePeerObservation,
        control_path: WAWSocketPathIdentity,
    ) -> None:
        if (
            type(observation) is not _RuntimePeerObservation
            or type(control_path) is not WAWSocketPathIdentity
            or type(observation.pid) is not int
            or observation.pid <= 1
            or type(observation.uid) is not int
            or observation.uid < 0
            or type(observation.gid) is not int
            or observation.gid < 0
            or type(observation.pidfd) is not int
            or observation.pidfd < 0
            or any(
                type(value) is not int or value < 0
                for value in (control_path.device, control_path.inode)
            )
        ):
            if type(observation) is _RuntimePeerObservation and observation.pidfd >= 0:
                with contextlib.suppress(OSError):
                    os.close(observation.pidfd)
            raise ValueError("bound Runtime peer identity is invalid")
        try:
            inheritable = os.get_inheritable(observation.pidfd)
        except OSError as exc:
            with contextlib.suppress(OSError):
                os.close(observation.pidfd)
            raise ValueError("bound Runtime peer pidfd is unavailable") from exc
        if inheritable or not _pidfd_current(observation.pidfd):
            with contextlib.suppress(OSError):
                os.close(observation.pidfd)
            raise ValueError("bound Runtime peer pidfd is not live and close-on-exec")
        self.pid = observation.pid
        self.uid = observation.uid
        self.gid = observation.gid
        self.control_path = control_path
        self._pidfd = observation.pidfd
        self._generation = 0
        self._owner_current: Callable[[BoundRuntimePeer, int], bool] | None = None
        self._poisoned = False
        self._closed = False
        self._close_failure: WAWControlClientError | None = None
        self._lock = threading.Lock()

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def poisoned(self) -> bool:
        with self._lock:
            return self._poisoned

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def close_failure(self) -> WAWControlClientError | None:
        with self._lock:
            return self._close_failure

    def _raise_close_failure(self) -> None:
        failure = self._close_failure
        if failure is not None:
            raise failure

    def _close_detached_pidfd(self, pidfd: int) -> None:
        if pidfd < 0:
            self._raise_close_failure()
            return
        try:
            os.close(pidfd)
        except OSError as exc:
            failure = WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime peer pidfd close failed"
            )
            with self._lock:
                if self._close_failure is None:
                    self._close_failure = failure
            raise failure from exc
        self._raise_close_failure()

    def _borrow_close_failed(self, failure: WAWControlClientError) -> None:
        with self._lock:
            if self._close_failure is None:
                self._close_failure = failure
            self._poisoned = True
            pidfd, self._pidfd = self._pidfd, -1
        self._close_detached_pidfd(pidfd)

    def _publish(
        self,
        *,
        generation: int,
        owner_current: Callable[[BoundRuntimePeer, int], bool],
    ) -> None:
        if type(generation) is not int or generation <= 0 or not callable(owner_current):
            raise ValueError("bound Runtime peer publication is invalid")
        with self._lock:
            if (
                self._closed
                or self._poisoned
                or self._owner_current is not None
                or not _pidfd_current(self._pidfd)
            ):
                raise WAWControlClientError(
                    "RUNTIME_UNAVAILABLE", "WAW Runtime peer is no longer current", retryable=True
                )
            self._generation = generation
            self._owner_current = owner_current

    def current(self, *, generation: int | None = None) -> bool:
        with self._lock:
            if self._closed or self._poisoned or self._pidfd < 0:
                return False
            actual_generation = self._generation
            owner_current = self._owner_current
            if generation is not None and generation != actual_generation:
                return False
            live = _pidfd_current(self._pidfd)
        if not live:
            self.poison()
            return False
        return owner_current is None or owner_current(self, actual_generation) is True

    def borrow(self, peer_socket: Any) -> RuntimePeerBorrow:
        """Match a connected socket, then duplicate only the retained pidfd."""

        try:
            pid, uid, gid = _peer_credentials(peer_socket)
        except WAWControlClientError:
            self.poison()
            raise
        with self._lock:
            generation = self._generation
            if (
                self._closed
                or self._poisoned
                or self._pidfd < 0
                or self._owner_current is None
                or (pid, uid, gid) != (self.pid, self.uid, self.gid)
                or not _pidfd_current(self._pidfd)
            ):
                mismatch = True
                duplicate = -1
            else:
                mismatch = False
                duplicate = -1
                try:
                    duplicate = os.dup(self._pidfd)
                    os.set_inheritable(duplicate, False)
                except OSError:
                    if duplicate >= 0:
                        with contextlib.suppress(OSError):
                            os.close(duplicate)
                    duplicate = -1
                    mismatch = True
        if mismatch:
            self.poison()
            raise WAWControlClientError(
                "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer changed after bind"
            )
        borrow = RuntimePeerBorrow(self, duplicate, generation)
        if not borrow.current():
            borrow.close()
            self.poison()
            raise WAWControlClientError(
                "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer changed after bind"
            )
        return borrow

    def poison(self) -> None:
        with self._lock:
            if self._closed or self._poisoned:
                pidfd = -1
            else:
                self._poisoned = True
                pidfd, self._pidfd = self._pidfd, -1
        self._close_detached_pidfd(pidfd)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                pidfd = -1
            else:
                self._closed = True
                pidfd, self._pidfd = self._pidfd, -1
        self._close_detached_pidfd(pidfd)

    def fence_after_fork(self) -> None:
        """Close the inherited pidfd in a post-lifespan fork child."""

        # at-fork child callbacks must not acquire locks which may have been
        # held by a vanished thread in the parent.
        pidfd, self._pidfd = self._pidfd, -1
        self._closed = True
        self._poisoned = True
        if pidfd >= 0:
            with contextlib.suppress(OSError):
                os.close(pidfd)


class RuntimeBindExchange:
    """Unpublished bind response and candidate pidfd owned by one client."""

    def __init__(
        self,
        owner: WAWControlClient,
        response: dict[str, Any],
        candidate: BoundRuntimePeer,
    ) -> None:
        if (
            type(owner) is not WAWControlClient
            or type(response) is not dict
            or type(candidate) is not BoundRuntimePeer
        ):
            raise TypeError("Runtime bind exchange inputs are invalid")
        self._owner = owner
        self._response = dict(response)
        self._candidate: BoundRuntimePeer | None = candidate
        self._published = False
        self._close_failure: WAWControlClientError | None = None

    @property
    def response(self) -> dict[str, Any]:
        return dict(self._response)

    def publish(
        self,
        *,
        generation: int,
        owner_current: Callable[[BoundRuntimePeer, int], bool],
    ) -> BoundRuntimePeer:
        candidate = self._candidate
        if candidate is None or self._published:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime bind exchange is no longer available"
            )
        try:
            self._owner._publish_exchange(self)
            candidate._publish(generation=generation, owner_current=owner_current)
        except BaseException as original:
            self._candidate = None
            close_failure: WAWControlClientError | None = None
            try:
                candidate.close()
            except WAWControlClientError as exc:
                self._close_failure = close_failure = exc
                self._owner._record_close_failure(exc)
            finally:
                self._owner._release_inflight_peer_fd(candidate)
                self._owner._publication_failed()
            if close_failure is not None:
                raise close_failure from original
            raise
        self._candidate = None
        self._published = True
        self._owner._release_inflight_peer_fd(candidate)
        return candidate

    def invalidate(self) -> None:
        candidate, self._candidate = self._candidate, None
        try:
            if candidate is not None:
                candidate.poison()
        except WAWControlClientError as exc:
            self._close_failure = exc
            raise
        finally:
            if candidate is not None:
                self._owner._release_inflight_peer_fd(candidate)
            self._owner._invalidate_exchange(self)

    def close(self) -> None:
        candidate, self._candidate = self._candidate, None
        try:
            if candidate is not None:
                candidate.close()
            elif self._close_failure is not None:
                raise self._close_failure
        except WAWControlClientError as exc:
            self._close_failure = exc
            raise
        finally:
            if candidate is not None:
                self._owner._release_inflight_peer_fd(candidate)
            self._owner._close_exchange(self)

    def fence_after_fork(self) -> None:
        """Discard an unpublished candidate inherited by a child process."""

        candidate, self._candidate = self._candidate, None
        self._closed = True
        if candidate is not None:
            candidate.fence_after_fork()
            self._owner._release_inflight_peer_fd(candidate)


def validate_runtime_bind_attestation(
    response: dict[str, Any],
    *,
    expected_runtime_host_installation_id: str,
    expected_runtime_host_installation_revision: str,
    expected_host_manifest_digest: str,
    expected_project_root_manifest_digest: str,
    expected_runtime_epoch: str | None = None,
    expected_enrollment_epoch: str | None = None,
    expected_enrollment_state: str | None = None,
) -> dict[str, Any]:
    """Require a bind response to match the locally trusted host anchor."""

    if response.get("status") not in {"BOUND", "ALREADY_BOUND"}:
        raise WAWControlClientError(
            "RUNTIME_INSTALLATION_MISMATCH", "Runtime did not provide a bound attestation"
        )
    checks = (
        ("runtime_host_installation_id", expected_runtime_host_installation_id),
        ("runtime_host_installation_revision", expected_runtime_host_installation_revision),
        ("host_manifest_digest", expected_host_manifest_digest),
        ("project_root_manifest_digest", expected_project_root_manifest_digest),
    )
    for field, expected in checks:
        actual = response.get(field)
        if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
            raise WAWControlClientError(
                "RUNTIME_INSTALLATION_MISMATCH", "Runtime bind attestation does not match anchor"
            )
    if expected_runtime_epoch is not None:
        actual_epoch = response.get("runtime_epoch")
        if not isinstance(actual_epoch, str) or not hmac.compare_digest(
            actual_epoch, expected_runtime_epoch
        ):
            raise WAWControlClientError(
                "RUNTIME_INSTALLATION_MISMATCH", "Runtime epoch does not match anchor"
            )
    for enrollment_field, enrollment_expected in (
        ("enrollment_epoch", expected_enrollment_epoch),
        ("enrollment_state", expected_enrollment_state),
    ):
        if enrollment_expected is not None:
            actual = response.get(enrollment_field)
            if not isinstance(actual, str) or not hmac.compare_digest(actual, enrollment_expected):
                raise WAWControlClientError(
                    "RUNTIME_INSTALLATION_MISMATCH",
                    "Runtime enrollment does not match anchor",
                )
    return response


def _check_socket_path(
    path: Path, *, expected_uid: int, expected_gid: int, expected_mode: int
) -> WAWSocketPathIdentity:
    """Reject symlink/socket replacement and unexpected DAC ownership before I/O."""

    try:
        parent = path.parent
        parent_stat = os.lstat(parent)
        details = os.lstat(path)
    except OSError as exc:
        raise WAWControlClientError(
            "RUNTIME_UNAVAILABLE",
            "WAW Runtime control socket provenance is unavailable",
            retryable=True,
        ) from exc
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_ISLNK(parent_stat.st_mode)
        or not stat.S_ISSOCK(details.st_mode)
        or details.st_uid != expected_uid
        or details.st_gid != expected_gid
        or stat.S_IMODE(details.st_mode) != expected_mode
    ):
        raise WAWControlClientError(
            "WAW_SOCKET_PROVENANCE_INVALID", "WAW Runtime control socket provenance is invalid"
        )
    return WAWSocketPathIdentity(details.st_dev, details.st_ino)


class WAWControlClient:
    """Issue one strict control request on a dedicated Unix socket."""

    def __init__(
        self,
        socket_path: Path,
        *,
        expected_peer_uid: int,
        expected_peer_gid: int,
        expected_socket_uid: int,
        expected_socket_gid: int,
        expected_socket_mode: int = 0o660,
        timeout_seconds: float = 2.0,
        cancellation_grace_seconds: float = 0.05,
        monotonic: Callable[[], float] = time.monotonic,
        background_owner: BackgroundWorkOwner | None = None,
    ) -> None:
        if not isinstance(socket_path, Path):
            raise TypeError("socket_path must be a Path")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 < cancellation_grace_seconds <= _MAX_CANCELLATION_GRACE_SECONDS:
            raise ValueError("cancellation_grace_seconds must be in (0, 1]")
        if type(expected_peer_uid) is not int or expected_peer_uid < 0:
            raise ValueError("expected_peer_uid must be a non-negative integer")
        if type(expected_peer_gid) is not int or expected_peer_gid < 0:
            raise ValueError("expected_peer_gid must be a non-negative integer")
        if type(expected_socket_uid) is not int or expected_socket_uid < 0:
            raise ValueError("expected_socket_uid must be a non-negative integer")
        if type(expected_socket_gid) is not int or expected_socket_gid < 0:
            raise ValueError("expected_socket_gid must be a non-negative integer")
        if type(expected_socket_mode) is not int or not 0 <= expected_socket_mode <= 0o7777:
            raise ValueError("expected_socket_mode must be an octal file mode")
        self._socket_path = socket_path
        self._expected_peer_uid = expected_peer_uid
        self._expected_peer_gid = expected_peer_gid
        self._expected_socket_uid = expected_socket_uid
        self._expected_socket_gid = expected_socket_gid
        self._expected_socket_mode = expected_socket_mode
        self._timeout_seconds = timeout_seconds
        self._cancellation_grace_seconds = cancellation_grace_seconds
        self._monotonic = monotonic
        self._background_owner = background_owner
        self._poisoned = False
        self._closing = False
        self._closed = False
        self._request_lock = asyncio.Lock()
        self._detached_tasks: set[asyncio.Future[Any]] = set()
        self._inflight_sockets: set[socket.socket] = set()
        self._inflight_peer_fds: set[BoundRuntimePeer | RuntimePeerBorrow] = set()
        self._pending_exchange: RuntimeBindExchange | None = None
        self._close_operation: asyncio.Task[None] | None = None
        self._replacement_issued = False
        self._close_failure: WAWControlClientError | None = None

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    @property
    def poisoned(self) -> bool:
        """Whether this process-lifetime transport owner is irreversibly fenced."""

        return self._poisoned

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def pending_operations(self) -> int:
        """Number of cancellation-resistant operations still owned by client."""

        return len(self._detached_tasks)

    @property
    def shutdown_clean(self) -> bool:
        """Whether every transport-owned exchange and task terminated cleanly."""

        operation = self._close_operation
        return (
            self._closed
            and not self._poisoned
            and self._close_failure is None
            and self._pending_exchange is None
            and not self._detached_tasks
            and not self._inflight_sockets
            and not self._inflight_peer_fds
            and operation is not None
            and operation.done()
            and not operation.cancelled()
            and operation.exception() is None
        )

    async def bind_exchange(self, action: str, request: dict[str, Any]) -> RuntimeBindExchange:
        """Return an unpublished peer/attestation pair for the sole bind action."""

        if action != "workspace.api_authority.bind":
            self._poison()
            raise WAWControlClientError("PROTOCOL_INVALID", "WAW bind action is invalid")
        self._require_open()
        async with self._request_lock:
            self._require_open()
            if self._pending_exchange is not None:
                self._poison()
                raise WAWControlClientError(
                    "RUNTIME_UNAVAILABLE", "WAW Runtime bind publication is pending"
                )
            response, candidate = await self._request(action, request, bound_peer=None)
            if candidate is None:
                self._poison()
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime bind peer is unavailable"
                )
            try:
                self._require_open()
            except BaseException:
                try:
                    candidate.close()
                finally:
                    self._release_inflight_peer_fd(candidate)
                raise
            exchange = RuntimeBindExchange(self, response, candidate)
            self._pending_exchange = exchange
            return exchange

    async def request_bound(
        self,
        action: str,
        request: dict[str, Any],
        bound_peer: BoundRuntimePeer,
    ) -> dict[str, Any]:
        """Issue one request through the exact peer published by bind."""

        if type(bound_peer) is not BoundRuntimePeer:
            self._poison()
            raise WAWControlClientError(
                "RUNTIME_PEER_FORBIDDEN", "A bound Runtime peer is required"
            )
        self._require_open()
        async with self._request_lock:
            self._require_open()
            if self._pending_exchange is not None or not bound_peer.current():
                bound_peer.poison()
                self._poison()
                raise WAWControlClientError(
                    "RUNTIME_UNAVAILABLE", "WAW Runtime peer is no longer current", retryable=True
                )
            try:
                response, candidate = await self._request(action, request, bound_peer=bound_peer)
            except BaseException:
                bound_peer.poison()
                raise
            if candidate is not None:
                try:
                    candidate.close()
                finally:
                    self._release_inflight_peer_fd(candidate)
                bound_peer.poison()
                self._poison()
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "Bound control request returned a new peer"
                )
            return response

    async def _request_unbound_test_only(
        self, action: str, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Low-level transport seam for tests; production callers use the coordinator."""

        self._require_open()
        async with self._request_lock:
            self._require_open()
            response, candidate = await self._request(action, request, bound_peer=None)
            if candidate is not None:
                try:
                    candidate.close()
                finally:
                    self._release_inflight_peer_fd(candidate)
            return response

    def _require_open(self) -> None:
        if self._closing or self._closed or self._poisoned:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE",
                "WAW Runtime control transport is unavailable",
                retryable=True,
            )

    async def _request(
        self,
        action: str,
        request: dict[str, Any],
        *,
        bound_peer: BoundRuntimePeer | None,
    ) -> tuple[dict[str, Any], BoundRuntimePeer | None]:
        """Send one request while retaining either a candidate or bound peer."""

        self._require_open()
        candidate: BoundRuntimePeer | None = None
        borrow: RuntimePeerBorrow | None = None
        try:
            encoded = encode_control_request(request)
            request_id = request["request_id"]
        except (KeyError, WAWControlError, TypeError, ValueError) as exc:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            raise WAWControlClientError(
                "PROTOCOL_INVALID", "WAW control request is invalid"
            ) from exc
        if request.get("action") != action:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            raise WAWControlClientError(
                "PROTOCOL_INVALID", "WAW control action does not match request"
            )
        if len(encoded) > MAX_CONTROL_LINE or len(encoded) > MAX_CONTROL_ENVELOPE:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            raise WAWControlClientError("PROTOCOL_INVALID", "WAW control request is oversized")

        try:
            deadline = self._monotonic() + self._timeout_seconds
            before_path = _check_socket_path(
                self._socket_path,
                expected_uid=self._expected_socket_uid,
                expected_gid=self._expected_socket_gid,
                expected_mode=self._expected_socket_mode,
            )
            if bound_peer is not None and before_path != bound_peer.control_path:
                raise WAWControlClientError(
                    "WAW_SOCKET_PROVENANCE_INVALID",
                    "WAW Runtime control socket changed after bind",
                )
        except BaseException:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            raise
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter
        transport_socket: socket.socket | None = None
        result: tuple[dict[str, Any], BoundRuntimePeer | None] | None = None
        try:
            reader, writer, transport_socket = await self._open_registered_connection(deadline)
        except (OSError, TimeoutError) as exc:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime control endpoint is unavailable", retryable=True
            ) from exc
        try:
            after_path = _check_socket_path(
                self._socket_path,
                expected_uid=self._expected_socket_uid,
                expected_gid=self._expected_socket_gid,
                expected_mode=self._expected_socket_mode,
            )
            if after_path != before_path:
                raise WAWControlClientError(
                    "WAW_SOCKET_PROVENANCE_INVALID", "WAW Runtime socket changed during connect"
                )
            peer_socket = writer.get_extra_info("socket")
            if peer_socket is None or not hasattr(peer_socket, "getsockopt"):
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer credentials are not trusted"
                )
            if bound_peer is None:
                observation = self._capture_unbound_peer(peer_socket)
                try:
                    candidate = BoundRuntimePeer(observation, before_path)
                except (TypeError, ValueError) as exc:
                    raise WAWControlClientError(
                        "RUNTIME_PEER_FORBIDDEN", "WAW Runtime bind peer is invalid"
                    ) from exc
                self._register_inflight_peer_fd(candidate)
            else:
                borrow = bound_peer.borrow(peer_socket)
                self._register_inflight_peer_fd(borrow)
            writer.write(encoded)
            await self._with_deadline(writer.drain(), deadline)
            try:
                raw = await self._with_deadline(reader.readline(), deadline)
            except (asyncio.LimitOverrunError, ValueError) as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response exceeds its bounded line limit"
                ) from exc
            if not raw or len(raw) > MAX_CONTROL_LINE or not raw.endswith(b"\n"):
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response framing is invalid"
                )
            try:
                response = decode_control_response(raw, action, expected_request_id=request_id)
            except WAWControlError as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response is invalid"
                ) from exc
            # The listener closes after the single response.  Any byte after
            # that response would represent a concatenated/trailed record.
            try:
                trailing = await self._with_deadline(reader.read(1), deadline)
            except TimeoutError as exc:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response did not terminate"
                ) from exc
            if trailing:
                raise WAWControlClientError(
                    "PROTOCOL_INVALID", "WAW control response has trailing bytes"
                )
            if candidate is not None and not candidate.current():
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer exited before bind publication"
                )
            if borrow is not None and not borrow.current():
                raise WAWControlClientError(
                    "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer changed during control response"
                )
            result = response, candidate
        except asyncio.CancelledError:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            if candidate is not None:
                candidate.poison()
            raise
        except WAWControlClientError:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            if candidate is not None:
                candidate.poison()
            raise
        except (OSError, TimeoutError) as exc:
            self._poison()
            if bound_peer is not None:
                bound_peer.poison()
            if candidate is not None:
                candidate.poison()
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime control request timed out", retryable=True
            ) from exc
        finally:
            try:
                await self._close_writer(writer)
            finally:
                if transport_socket is not None:
                    self._release_inflight_socket(transport_socket)
                try:
                    if borrow is not None:
                        borrow.close()
                finally:
                    if borrow is not None:
                        self._release_inflight_peer_fd(borrow)
                    if self._poisoned and candidate is not None:
                        try:
                            candidate.poison()
                        finally:
                            self._release_inflight_peer_fd(candidate)
                    if self._poisoned and bound_peer is not None:
                        bound_peer.poison()
        if self._poisoned:
            if candidate is not None:
                candidate.poison()
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime control transport cleanup was uncertain"
            )
        return result

    def _capture_unbound_peer(self, peer_socket: Any) -> _RuntimePeerObservation:
        pid, uid, gid = _peer_credentials(peer_socket)
        if uid != self._expected_peer_uid or gid != self._expected_peer_gid:
            raise WAWControlClientError(
                "RUNTIME_PEER_FORBIDDEN", "WAW Runtime peer credentials are not trusted"
            )
        pidfd = _peer_pidfd(peer_socket, pid)
        return _RuntimePeerObservation(pid, uid, gid, pidfd)

    def _publish_exchange(self, exchange: RuntimeBindExchange) -> None:
        if (
            self._closing
            or self._closed
            or self._poisoned
            or self._pending_exchange is not exchange
        ):
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime bind exchange owner is unavailable"
            )
        self._pending_exchange = None

    def _register_inflight_socket(self, transport_socket: socket.socket) -> None:
        """Make a live transport descriptor reachable by the at-fork fence."""

        self._inflight_sockets.add(transport_socket)

    def _release_inflight_socket(self, transport_socket: socket.socket) -> None:
        self._inflight_sockets.discard(transport_socket)
        with contextlib.suppress(OSError):
            transport_socket.close()

    def _register_inflight_peer_fd(self, owner: BoundRuntimePeer | RuntimePeerBorrow) -> None:
        self._inflight_peer_fds.add(owner)

    def _release_inflight_peer_fd(self, owner: BoundRuntimePeer | RuntimePeerBorrow) -> None:
        self._inflight_peer_fds.discard(owner)

    def _invalidate_exchange(self, exchange: RuntimeBindExchange) -> None:
        if self._pending_exchange is exchange:
            self._pending_exchange = None
        self._poison()

    def _close_exchange(self, exchange: RuntimeBindExchange) -> None:
        if self._pending_exchange is exchange:
            self._pending_exchange = None

    def _publication_failed(self) -> None:
        self._poison()

    def _poison(self) -> None:
        if self._poisoned:
            return
        self._poisoned = True
        exchange = self._pending_exchange
        self._pending_exchange = None
        if exchange is not None:
            try:
                exchange.invalidate()
            except WAWControlClientError as exc:
                self._record_close_failure(exc)

    def _record_close_failure(self, failure: WAWControlClientError) -> None:
        if self._close_failure is None:
            self._close_failure = failure
        self._poisoned = True

    def close(self) -> Coroutine[Any, Any, None]:
        """Irreversibly stop this transport and observe its bounded child work."""

        self._closing = True
        operation = self._close_operation
        if operation is None:
            operation = asyncio.create_task(self._perform_close())
            self._close_operation = operation
        return self._await_close_operation(operation)

    async def _await_close_operation(self, operation: asyncio.Task[None]) -> None:
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError:
            self._poison()
            raise

    async def _perform_close(self) -> None:
        async with self._request_lock:
            if self._closed:
                return
            self._closed = True
            exchange, self._pending_exchange = self._pending_exchange, None
            if exchange is not None:
                try:
                    exchange.close()
                except WAWControlClientError as exc:
                    self._record_close_failure(exc)
            tasks = tuple(self._detached_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                _done, pending = await asyncio.wait(tasks, timeout=self._cancellation_grace_seconds)
                if pending:
                    self._poison()
            if self._inflight_sockets or self._inflight_peer_fds:
                self._record_close_failure(
                    WAWControlClientError(
                        "RUNTIME_UNAVAILABLE",
                        "WAW Runtime control descriptors remain in flight",
                    )
                )
            if self._close_failure is not None:
                raise self._close_failure

    def replacement_after_close(self) -> WAWControlClient:
        """Create a fresh transport generation after this owner is fully closed."""

        operation = self._close_operation
        if (
            not self._closed
            or operation is None
            or not operation.done()
            or operation.cancelled()
            or operation.exception() is not None
            or self._close_failure is not None
            or self._pending_exchange is not None
            or self._detached_tasks
            or self._replacement_issued
        ):
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE",
                "WAW Runtime control replacement is not yet safe",
                retryable=True,
            )
        self._replacement_issued = True
        return WAWControlClient(
            self._socket_path,
            expected_peer_uid=self._expected_peer_uid,
            expected_peer_gid=self._expected_peer_gid,
            expected_socket_uid=self._expected_socket_uid,
            expected_socket_gid=self._expected_socket_gid,
            expected_socket_mode=self._expected_socket_mode,
            timeout_seconds=self._timeout_seconds,
            cancellation_grace_seconds=self._cancellation_grace_seconds,
            monotonic=self._monotonic,
            background_owner=self._background_owner,
        )

    def _track_task(self, task: asyncio.Future[Any]) -> None:
        """Track detached work and consume its eventual result."""

        if len(self._detached_tasks) >= _MAX_DETACHED_TASKS:
            self._poison()
            task.cancel()
            task.add_done_callback(self._consume_late_task)
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE",
                "WAW Runtime control transport exceeded pending operation limit",
                retryable=True,
            )
        self._detached_tasks.add(task)
        if self._background_owner is not None:
            self._background_owner.track_background(task)
        task.add_done_callback(self._consume_task)

    def fence_after_fork(self) -> None:
        """Fence a client copied after lifespan startup without using its old loop."""

        self._closing = True
        self._closed = True
        self._poisoned = True
        exchange, self._pending_exchange = self._pending_exchange, None
        if exchange is not None:
            exchange.fence_after_fork()
        for transport_socket in tuple(self._inflight_sockets):
            with contextlib.suppress(OSError):
                transport_socket.close()
        self._inflight_sockets.clear()
        for owner in tuple(self._inflight_peer_fds):
            owner.fence_after_fork()
        self._inflight_peer_fds.clear()
        self._detached_tasks.clear()

    def _forget_task(self, task: asyncio.Future[Any]) -> None:
        self._detached_tasks.discard(task)

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        """Close without allowing a broken wait_closed() to hold the request."""

        try:
            writer.close()
        except (OSError, RuntimeError):
            self._poison()
            return
        try:
            close_wait = writer.wait_closed()
        except (OSError, RuntimeError):
            self._poison()
            return
        close_wait_any: Any = close_wait
        if not inspect.isawaitable(close_wait_any):
            self._poison()
            return
        task = asyncio.ensure_future(close_wait_any)
        self._track_task(task)
        try:
            _done, pending = await asyncio.wait({task}, timeout=self._cancellation_grace_seconds)
        except asyncio.CancelledError:
            self._poison()
            task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.shield(self._finish_cancel(task))
            raise
        if pending:
            self._poison()
            task.cancel()
        else:
            self._forget_task(task)
            try:
                task.result()
            except BaseException:
                self._poison()

    async def _open_registered_connection(
        self, deadline: float
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, socket.socket]:
        """Register the AF_UNIX fd before connect and retain it through I/O."""

        transport_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            transport_socket.set_inheritable(False)
            transport_socket.setblocking(False)
            self._register_inflight_socket(transport_socket)
            await self._with_deadline(
                self._connect_registered_socket(transport_socket),
                deadline,
            )
            reader, writer = await self._with_deadline(
                asyncio.open_unix_connection(
                    sock=transport_socket,
                    limit=MAX_CONTROL_LINE + 1,
                ),
                deadline,
            )
            return reader, writer, transport_socket
        except BaseException:
            self._release_inflight_socket(transport_socket)
            raise

    async def _connect_registered_socket(self, transport_socket: socket.socket) -> None:
        await asyncio.get_running_loop().sock_connect(
            transport_socket, os.fspath(self._socket_path)
        )

    @staticmethod
    def _consume_late_task(task: asyncio.Future[Any]) -> None:
        # The callback is rebound per instance below; this static method is
        # retained for compatibility with existing tests/callers.
        with contextlib.suppress(BaseException):
            task.result()

    def _consume_task(self, task: asyncio.Future[Any]) -> None:
        self._forget_task(task)
        self._consume_late_task(task)

    async def _with_deadline(self, awaitable: Any, deadline: float) -> Any:
        """Await with a hard deadline and bounded cancellation cleanup.

        ``asyncio.wait_for`` may itself exceed its timeout while waiting for a
        cancellation-resistant coroutine to acknowledge cancellation.  Keep
        the request bounded by detaching that operation after a short grace
        period and poison this client so no later request can reuse it.
        """

        remaining = deadline - self._monotonic()
        if remaining <= 0:
            self._poison()
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError("WAW control deadline exceeded")
        task = asyncio.ensure_future(awaitable)
        self._track_task(task)
        try:
            done, _pending = await asyncio.wait({task}, timeout=remaining)
        except asyncio.CancelledError:
            self._poison()
            task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.shield(self._finish_cancel(task))
            raise
        if done:
            self._forget_task(task)
            return task.result()

        self._poison()
        task.cancel()
        _cancelled_done, cancelled_pending = await asyncio.wait(
            {task}, timeout=self._cancellation_grace_seconds
        )
        if cancelled_pending:
            self._poison()
            # The task owns the operation and may finish later.  Consume its
            # eventual exception without keeping the request alive.
            task.add_done_callback(self._consume_task)
        else:
            self._forget_task(task)
            with contextlib.suppress(BaseException):
                task.result()
        raise TimeoutError("WAW control deadline exceeded")

    async def _finish_cancel(self, task: asyncio.Future[Any]) -> None:
        """Give cancellation a small grace window, never joining indefinitely."""

        done, pending = await asyncio.wait({task}, timeout=self._cancellation_grace_seconds)
        if not pending:
            self._forget_task(task)
        for completed in done:
            with contextlib.suppress(BaseException):
                completed.result()
        if pending:
            # Keep it registered until the callback below observes terminal
            # completion; reconnect remains fail-closed in the meantime.
            task.add_done_callback(self._consume_task)


__all__ = [
    "BoundRuntimePeer",
    "RuntimeBindExchange",
    "RuntimePeerBorrow",
    "WAWControlClient",
    "WAWControlClientError",
    "WAWSocketPathIdentity",
    "validate_runtime_bind_attestation",
]
