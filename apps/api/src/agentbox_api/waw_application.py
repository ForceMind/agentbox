"""Process-lifetime ownership for the WAW API control and stream boundary."""

from __future__ import annotations

import asyncio
import errno
import fcntl
import grp
import os
import pwd
import secrets
import stat
import threading
import time
import weakref
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from agentbox_core.configuration import Settings
from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw_tickets import AttachmentAuthority

from agentbox_api.waw_authorization import (
    SingleAdminWorkspacePolicy,
    WorkspaceAuthorizationPolicy,
)
from agentbox_api.waw_binding import WAWRuntimeBindCoordinator
from agentbox_api.waw_control_client import WAWControlClient
from agentbox_api.waw_host_anchor import WAWAPIHostAnchorError, load_waw_api_host_anchor_v2
from agentbox_api.waw_relay import RelayFailure, RuntimeSocketTrust, WAWStreamHandler

_PRODUCTION_LOCK_PATH = Path("/run/agentbox-waw-api/waw-api.v1.lock")
_PRODUCTION_ANCHOR_PATH = Path("/usr/share/agentbox/waw/api-host-anchor.v2.json")
_PRODUCTION_CONTROL_SOCKET_PATH = Path("/run/agentbox-waw/workspace-control.sock")
_PRODUCTION_RUNTIME_USER = "agentbox-runtime"
_PRODUCTION_RUNTIME_GROUP = "agentbox-runtime"
_PRODUCTION_API_USER = "agentbox"
_PRODUCTION_API_GROUP = "agentbox"
_PRODUCTION_IPC_GROUP = "agentbox-runtime-ipc"
_TEST_ONLY_LOCK_TOKEN = object()
_TEST_ONLY_APPLICATION_TOKEN = object()
_PRODUCTION_APPLICATION_TOKEN = object()
WAW_APPLICATION_SCOPE_KEY = "agentbox.waw_application"
_MAX_DETACH_OPERATIONS = 256


class WAWAPIApplicationError(RuntimeError):
    """Bounded process-owner failure without filesystem or peer details."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class WAWMode(StrEnum):
    """Explicit API composition mode; host activation remains a separate operation."""

    DISABLED = "DISABLED"
    FILESYSTEM_V2 = "FILESYSTEM_V2"


class WAWWorkLedger:
    """One process-owned ledger for WAW routes and cancellation-resistant work."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process_id: int | None = None
        self._accepting = True
        self._route_tasks: set[asyncio.Task[Any]] = set()
        self._background_work: set[asyncio.Future[Any]] = set()
        self._detach_operations: OrderedDict[tuple[object, ...], tuple[str, bool]] = OrderedDict()
        self._drain_task: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._failure: BaseException | None = None
        self._routes_drained = False
        self._closed = False

    def bind_process(self, process_id: int) -> None:
        if type(process_id) is not int or process_id <= 0:
            raise ValueError("WAW work-ledger process identity is invalid")
        with self._lock:
            if self._process_id is not None and self._process_id != process_id:
                raise WAWAPIApplicationError(
                    "WAW_API_SINGLETON_UNSAFE", "WAW work ledger crossed a process fork"
                )
            self._process_id = process_id

    def _process_current(self) -> bool:
        return self._process_id is None or self._process_id == os.getpid()

    @property
    def accepting(self) -> bool:
        with self._lock:
            return self._accepting and not self._closed and self._process_current()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._route_tasks)

    @property
    def background_count(self) -> int:
        with self._lock:
            return len(self._background_work)

    @property
    def routes_drained(self) -> bool:
        with self._lock:
            operation = self._drain_task
            return (
                self._routes_drained
                and not self._route_tasks
                and operation is not None
                and operation.done()
                and not operation.cancelled()
                and operation.exception() is None
            )

    @property
    def shutdown_clean(self) -> bool:
        with self._lock:
            operation = self._close_task
            return (
                self._closed
                and not self._accepting
                and not self._route_tasks
                and not self._background_work
                and not self._detach_operations
                and self._failure is None
                and operation is not None
                and operation.done()
                and not operation.cancelled()
                and operation.exception() is None
            )

    def register_route(self, task: asyncio.Task[Any]) -> bool:
        with self._lock:
            if not self._accepting or self._closed or not self._process_current():
                return False
            self._route_tasks.add(task)
            return True

    def unregister_route(self, task: asyncio.Task[Any]) -> None:
        with self._lock:
            self._route_tasks.discard(task)

    def track_background(self, future: asyncio.Future[Any]) -> None:
        with self._lock:
            if self._closed or not self._process_current():
                self._record_failure_locked(
                    WAWAPIApplicationError(
                        "WAW_API_SHUTDOWN_INCOMPLETE",
                        "WAW background work appeared after owner shutdown",
                    )
                )
            self._background_work.add(future)

        def completed(value: asyncio.Future[Any]) -> None:
            failure: BaseException | None = None
            if value.cancelled():
                failure = WAWAPIApplicationError(
                    "WAW_API_SHUTDOWN_INCOMPLETE",
                    "WAW background work was cancelled before completion",
                )
            else:
                try:
                    failure = value.exception()
                except BaseException:
                    failure = WAWAPIApplicationError(
                        "WAW_API_SHUTDOWN_INCOMPLETE",
                        "WAW background work completion was unavailable",
                    )
            with self._lock:
                if failure is not None:
                    self._record_failure_locked(
                        WAWAPIApplicationError(
                            "WAW_API_SHUTDOWN_INCOMPLETE",
                            "WAW background work did not close cleanly",
                        )
                    )
                self._background_work.discard(value)

        future.add_done_callback(completed)

    def begin_shutdown(self) -> None:
        with self._lock:
            self._accepting = False

    def drain_routes(self) -> Coroutine[Any, Any, None]:
        self.begin_shutdown()
        with self._lock:
            if self._drain_task is None:
                self._drain_task = asyncio.create_task(self._perform_drain_routes())
            operation = self._drain_task
        return self._await_operation(operation)

    async def _perform_drain_routes(self) -> None:
        current = asyncio.current_task()
        while True:
            with self._lock:
                tasks = tuple(task for task in self._route_tasks if task is not current)
            if not tasks:
                break
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            with self._lock:
                for task in tasks:
                    self._route_tasks.discard(task)
            failure = next(
                (
                    result
                    for result in results
                    if isinstance(result, BaseException)
                    and not isinstance(result, asyncio.CancelledError)
                ),
                None,
            )
            if failure is not None:
                with self._lock:
                    self._record_failure_locked(failure)
                raise failure
        with self._lock:
            self._routes_drained = True

    def close(self) -> Coroutine[Any, Any, None]:
        self.begin_shutdown()
        with self._lock:
            if self._close_task is None:
                self._close_task = asyncio.create_task(self._perform_close())
            operation = self._close_task
        return self._await_operation(operation)

    async def _perform_close(self) -> None:
        await self.drain_routes()
        while True:
            with self._lock:
                background = tuple(self._background_work)
            if not background:
                break
            results = await asyncio.gather(*background, return_exceptions=True)
            failure = next(
                (result for result in results if isinstance(result, BaseException)), None
            )
            if failure is not None:
                wrapped = WAWAPIApplicationError(
                    "WAW_API_SHUTDOWN_INCOMPLETE", "WAW background work did not close cleanly"
                )
                with self._lock:
                    self._record_failure_locked(wrapped)
                raise wrapped from failure
        with self._lock:
            if self._route_tasks or self._background_work:
                failure = WAWAPIApplicationError(
                    "WAW_API_SHUTDOWN_INCOMPLETE", "WAW work remains active"
                )
                self._record_failure_locked(failure)
                raise failure
            for key, (_operation_id, detached) in tuple(self._detach_operations.items()):
                if detached:
                    del self._detach_operations[key]
            if self._detach_operations:
                failure = WAWAPIApplicationError(
                    "WAW_API_SHUTDOWN_INCOMPLETE",
                    "WAW detach cleanup remains uncertain",
                )
                self._record_failure_locked(failure)
                raise failure
            if self._failure is not None:
                raise self._failure
            self._closed = True

    async def _await_operation(self, operation: asyncio.Task[None]) -> None:
        interrupted = False
        while True:
            try:
                await asyncio.shield(operation)
                break
            except asyncio.CancelledError:
                if operation.cancelled():
                    raise
                interrupted = True
        if interrupted:
            raise asyncio.CancelledError

    def detach_operation(self, key: tuple[object, ...]) -> tuple[str, bool]:
        with self._lock:
            if not self._accepting or self._closed or not self._process_current():
                raise WAWAPIApplicationError(
                    "WAW_API_UNAVAILABLE", "WAW detach operation owner is unavailable"
                )
            current = self._detach_operations.get(key)
            if current is not None:
                self._detach_operations.move_to_end(key)
                return current
            if len(self._detach_operations) >= _MAX_DETACH_OPERATIONS:
                completed = next(
                    (
                        candidate
                        for candidate, (_operation_id, detached) in self._detach_operations.items()
                        if detached
                    ),
                    None,
                )
                if completed is None:
                    raise WAWAPIApplicationError(
                        "WAW_API_CAPACITY", "WAW detach operation capacity is unavailable"
                    )
                del self._detach_operations[completed]
            operation_id = f"wdo_{secrets.token_hex(16)}"
            value = (operation_id, False)
            self._detach_operations[key] = value
            return value

    def mark_detached(self, key: tuple[object, ...], operation_id: str) -> None:
        with self._lock:
            current = self._detach_operations.get(key)
            if current is None or current[0] != operation_id:
                raise WAWAPIApplicationError(
                    "WAW_API_UNAVAILABLE", "WAW detach operation identity changed"
                )
            self._detach_operations[key] = (operation_id, True)
            self._detach_operations.move_to_end(key)

    def _record_failure_locked(self, failure: BaseException) -> None:
        if self._failure is None:
            self._failure = failure

    def fence_after_fork(self) -> None:
        """Permanently retire a ledger copied after lifespan startup."""

        if self._process_current():
            return
        self._accepting = False
        self._route_tasks.clear()
        self._background_work.clear()
        self._detach_operations.clear()
        self._routes_drained = False
        self._closed = True
        self._failure = WAWAPIApplicationError(
            "WAW_API_SINGLETON_UNSAFE", "WAW work ledger crossed a process fork"
        )


class WAWAPIProcessLock:
    """Descriptor-held, nonblocking singleton lock acquired only by lifespan."""

    def __init__(
        self,
        path: Path = _PRODUCTION_LOCK_PATH,
        *,
        expected_uid: int | None = None,
        expected_gid: int | None = None,
        _test_only_token: object | None = None,
    ) -> None:
        if path != _PRODUCTION_LOCK_PATH and _test_only_token is not _TEST_ONLY_LOCK_TOKEN:
            raise ValueError("production WAW API lock path is fixed")
        self._path = path
        self._test_only = _test_only_token is _TEST_ONLY_LOCK_TOKEN
        if not self._test_only and (expected_uid is not None or expected_gid is not None):
            raise ValueError("production WAW API lock identity is fixed")
        self._expected_uid = (
            (os.geteuid() if expected_uid is None else expected_uid) if self._test_only else 0
        )
        self._expected_gid = (
            (os.getegid() if expected_gid is None else expected_gid) if self._test_only else 0
        )
        if self._expected_uid < 0 or self._expected_gid < 0:
            raise ValueError("WAW API lock identity is invalid")
        self._descriptor = -1
        self._parent_descriptor = -1
        self._identity: tuple[int, int] | None = None
        self._acquired_pid: int | None = None
        self._released = False
        self._terminal_failure: WAWAPIApplicationError | None = None
        _PROCESS_LOCKS.add(self)

    @classmethod
    def production(cls) -> WAWAPIProcessLock:
        return cls()

    @classmethod
    def test_only(
        cls,
        path: Path,
        *,
        expected_uid: int | None = None,
        expected_gid: int | None = None,
    ) -> WAWAPIProcessLock:
        return cls(
            path,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            _test_only_token=_TEST_ONLY_LOCK_TOKEN,
        )

    @property
    def path(self) -> Path:
        return self._path

    @property
    def acquired(self) -> bool:
        if self._descriptor < 0 or self._released or self._terminal_failure is not None:
            return False
        try:
            self.revalidate()
        except WAWAPIApplicationError:
            return False
        return True

    @property
    def poisoned(self) -> bool:
        return self._terminal_failure is not None

    @property
    def terminal_failure(self) -> WAWAPIApplicationError | None:
        return self._terminal_failure

    @property
    def has_owned_fd(self) -> bool:
        return self._descriptor >= 0 or self._parent_descriptor >= 0

    @property
    def test_only_mode(self) -> bool:
        return self._test_only

    def _validate(self, details: os.stat_result) -> tuple[int, int]:
        expected_mode = 0o600 if self._test_only else 0o444
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_IMODE(details.st_mode) != expected_mode
            or details.st_uid != self._expected_uid
            or details.st_gid != self._expected_gid
            or details.st_nlink != 1
        ):
            raise WAWAPIApplicationError(
                "WAW_API_SINGLETON_UNSAFE", "WAW API singleton lock metadata is unsafe"
            )
        return details.st_dev, details.st_ino

    @staticmethod
    def _validate_production_directory(details: os.stat_result) -> None:
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != 0
            or details.st_gid != 0
            or details.st_mode & 0o022
        ):
            raise WAWAPIApplicationError(
                "WAW_API_SINGLETON_UNSAFE", "WAW API singleton directory is unsafe"
            )

    def _open_production_parent(self) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        current = os.open("/", flags)
        try:
            self._validate_production_directory(os.fstat(current))
            for component in ("run", "agentbox-waw-api"):
                following = os.open(component, flags, dir_fd=current)
                try:
                    self._validate_production_directory(os.fstat(following))
                except BaseException:
                    os.close(following)
                    raise
                os.close(current)
                current = following
            return current
        except BaseException:
            os.close(current)
            raise

    def _path_details(self, parent_descriptor: int | None = None) -> os.stat_result:
        if self._test_only:
            return os.stat(self._path, follow_symlinks=False)
        parent = self._parent_descriptor if parent_descriptor is None else parent_descriptor
        if parent < 0:
            raise WAWAPIApplicationError(
                "WAW_API_SINGLETON_UNSAFE", "WAW API singleton directory is unavailable"
            )
        self._validate_production_directory(os.fstat(parent))
        return os.stat(self._path.name, dir_fd=parent, follow_symlinks=False)

    def _record_terminal(self, failure: WAWAPIApplicationError) -> WAWAPIApplicationError:
        if self._terminal_failure is None:
            self._terminal_failure = failure
        return self._terminal_failure

    def acquire(self) -> None:
        if self._terminal_failure is not None:
            raise self._terminal_failure
        if self._descriptor >= 0:
            self.revalidate()
            return
        if self._released:
            raise WAWAPIApplicationError(
                "WAW_API_SINGLETON_UNAVAILABLE", "WAW API singleton lock owner is retired"
            )
        parent_descriptor = -1
        if self._test_only:
            flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
            target: Path | str = self._path
            mode = 0o600
            directory_argument: dict[str, int] = {}
        else:
            try:
                parent_descriptor = self._open_production_parent()
            except OSError as exc:
                raise WAWAPIApplicationError(
                    "WAW_API_SINGLETON_UNAVAILABLE", "WAW API singleton directory is unavailable"
                ) from exc
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            target = self._path.name
            mode = 0o444
            directory_argument = {"dir_fd": parent_descriptor}
        try:
            descriptor = os.open(target, flags, mode, **directory_argument)
        except OSError as exc:
            if parent_descriptor >= 0:
                os.close(parent_descriptor)
            code = (
                "WAW_API_SINGLETON_UNSAFE"
                if exc.errno == errno.ELOOP
                else "WAW_API_SINGLETON_UNAVAILABLE"
            )
            raise WAWAPIApplicationError(code, "WAW API singleton lock is unavailable") from exc
        try:
            before = self._validate(os.fstat(descriptor))
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EAGAIN):
                    raise WAWAPIApplicationError(
                        "WAW_API_SINGLETON_UNAVAILABLE",
                        "another WAW API process owns the singleton lock",
                    ) from exc
                raise
            after = self._validate(os.fstat(descriptor))
            path_details = self._path_details(parent_descriptor if parent_descriptor >= 0 else None)
            path_identity = self._validate(path_details)
            if before != after or after != path_identity:
                raise WAWAPIApplicationError(
                    "WAW_API_SINGLETON_UNSAFE", "WAW API singleton lock identity changed"
                )
        except BaseException:
            os.close(descriptor)
            if parent_descriptor >= 0:
                os.close(parent_descriptor)
            raise
        self._descriptor = descriptor
        self._parent_descriptor = parent_descriptor
        self._identity = after
        self._acquired_pid = os.getpid()

    def revalidate(self) -> None:
        if self._terminal_failure is not None:
            raise self._terminal_failure
        if self._descriptor < 0 or self._identity is None or self._released:
            raise WAWAPIApplicationError(
                "WAW_API_SINGLETON_UNAVAILABLE", "WAW API singleton lock is not held"
            )
        if self._acquired_pid != os.getpid():
            self.fence_after_fork()
            assert self._terminal_failure is not None
            raise self._terminal_failure
        try:
            descriptor_identity = self._validate(os.fstat(self._descriptor))
            path_identity = self._validate(self._path_details())
            if descriptor_identity != self._identity or path_identity != self._identity:
                raise WAWAPIApplicationError(
                    "WAW_API_SINGLETON_UNSAFE", "WAW API singleton lock identity changed"
                )
        except WAWAPIApplicationError as exc:
            failure = self._record_terminal(exc)
            raise failure from exc
        except OSError as exc:
            failure = WAWAPIApplicationError(
                "WAW_API_SINGLETON_UNSAFE", "WAW API singleton lock identity is unavailable"
            )
            raise self._record_terminal(failure) from exc

    def release(self) -> None:
        if self._released:
            return
        if self._terminal_failure is not None:
            raise self._terminal_failure
        self.revalidate()
        parent_descriptor = self._parent_descriptor
        descriptor = self._descriptor
        self._parent_descriptor = -1
        if parent_descriptor >= 0:
            try:
                os.close(parent_descriptor)
            except OSError as exc:
                self._parent_descriptor = parent_descriptor
                failure = self._record_terminal(
                    WAWAPIApplicationError(
                        "WAW_API_SHUTDOWN_INCOMPLETE",
                        "WAW API singleton directory close failed",
                    )
                )
                raise failure from exc
        self._descriptor = -1
        try:
            os.close(descriptor)
        except OSError as exc:
            failure = self._record_terminal(
                WAWAPIApplicationError(
                    "WAW_API_SHUTDOWN_INCOMPLETE", "WAW API singleton lock release failed"
                )
            )
            raise failure from exc
        self._identity = None
        self._acquired_pid = None
        self._released = True

    def fence_after_fork(self) -> None:
        """Close inherited descriptors and make the child copy permanently unusable."""

        if self._acquired_pid is None or self._acquired_pid == os.getpid():
            return
        descriptor, self._descriptor = self._descriptor, -1
        parent, self._parent_descriptor = self._parent_descriptor, -1
        for candidate in (descriptor, parent):
            if candidate >= 0:
                with suppress(OSError):
                    os.close(candidate)
        self._identity = None
        self._released = True
        self._terminal_failure = WAWAPIApplicationError(
            "WAW_API_SINGLETON_UNSAFE", "WAW API singleton lock crossed a process fork"
        )


@dataclass(frozen=True)
class WAWAPIComponents:
    """The exact objects created after the singleton lock is held."""

    control_client: WAWControlClient | None
    bind_coordinator: WAWRuntimeBindCoordinator
    attachment_authority: AttachmentAuthority
    authorization_policy: WorkspaceAuthorizationPolicy
    stream_handler: WAWStreamHandler
    work_ledger: WAWWorkLedger


WAWAPIComponentFactory = Callable[[int, str, WAWWorkLedger], WAWAPIComponents]


class WAWAPIApplicationState(StrEnum):
    NEW = "NEW"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    QUIESCING = "QUIESCING"
    DRAINED = "DRAINED"
    CLOSED = "CLOSED"
    POISONED = "POISONED"


class WAWAPIApplication:
    """One process owner for WAW authority, routes, control and background work."""

    def __init__(
        self,
        factory: WAWAPIComponentFactory,
        *,
        settings: Settings,
        services: ControlPlaneServices,
        process_lock: WAWAPIProcessLock,
        _construction_token: object,
    ) -> None:
        if _construction_token not in {
            _TEST_ONLY_APPLICATION_TOKEN,
            _PRODUCTION_APPLICATION_TOKEN,
        }:
            raise ValueError("WAW API application requires a closed construction entry")
        self._factory = factory
        self._process_lock = process_lock
        self._test_only = _construction_token is _TEST_ONLY_APPLICATION_TOKEN
        if not self._test_only and self._process_lock.test_only_mode:
            raise ValueError("production WAW API application requires the fixed process lock")
        self._settings = settings
        self._services = services
        self._work_ledger = WAWWorkLedger()
        self._components: WAWAPIComponents | None = None
        self._state = WAWAPIApplicationState.NEW
        self._start_operation: asyncio.Task[None] | None = None
        self._close_operation: asyncio.Task[None] | None = None
        self._shutdown_failure: BaseException | None = None
        self._shutdown_clean = False
        self._close_requested = False
        self._lifespan_pid: int | None = None
        _APPLICATIONS.add(self)

    @classmethod
    def production(cls, settings: Settings, services: ControlPlaneServices) -> WAWAPIApplication:
        return cls(
            lambda epoch, nonce, ledger: _build_production_components(
                settings, services, epoch, nonce, ledger
            ),
            settings=settings,
            services=services,
            process_lock=WAWAPIProcessLock.production(),
            _construction_token=_PRODUCTION_APPLICATION_TOKEN,
        )

    @classmethod
    def test_only(
        cls,
        factory: WAWAPIComponentFactory,
        *,
        settings: Settings,
        services: ControlPlaneServices,
        process_lock: WAWAPIProcessLock,
    ) -> WAWAPIApplication:
        return cls(
            factory,
            settings=settings,
            services=services,
            process_lock=process_lock,
            _construction_token=_TEST_ONLY_APPLICATION_TOKEN,
        )

    @property
    def test_only_mode(self) -> bool:
        return self._test_only

    @property
    def state(self) -> WAWAPIApplicationState:
        self._ensure_process_current()
        return self._state

    def bind_control_plane(self, settings: Settings, services: ControlPlaneServices) -> None:
        """Verify that FastAPI uses the exact immutable graph bound at construction."""

        if self._state is not WAWAPIApplicationState.NEW:
            raise WAWAPIApplicationError(
                "WAW_API_COMPOSITION_INVALID", "WAW API root graph was bound too late"
            )
        if self._settings is not settings or self._services is not services:
            raise WAWAPIApplicationError(
                "WAW_API_COMPOSITION_INVALID", "WAW API root graph cannot be replaced"
            )

    @property
    def shutdown_clean(self) -> bool:
        return self._shutdown_clean

    def _require_components(self) -> WAWAPIComponents:
        self._ensure_process_current()
        components = self._components
        if components is None or self._state is not WAWAPIApplicationState.RUNNING:
            raise WAWAPIApplicationError(
                "WAW_API_UNAVAILABLE", "WAW API application is unavailable"
            )
        try:
            self._process_lock.revalidate()
        except BaseException as exc:
            self.poison_shutdown(exc)
            raise WAWAPIApplicationError(
                "WAW_API_UNAVAILABLE", "WAW API application is unavailable"
            ) from exc
        return components

    @property
    def bind_coordinator(self) -> WAWRuntimeBindCoordinator:
        return self._require_components().bind_coordinator

    @property
    def attachment_authority(self) -> AttachmentAuthority:
        return self._require_components().attachment_authority

    @property
    def authorization_policy(self) -> WorkspaceAuthorizationPolicy:
        return self._require_components().authorization_policy

    @property
    def stream_handler(self) -> WAWStreamHandler:
        return self._require_components().stream_handler

    @property
    def readiness_checks(self) -> dict[str, bool]:
        self._ensure_process_current()
        components = self._components
        running = self._state is WAWAPIApplicationState.RUNNING
        if running and components is not None:
            try:
                self._process_lock.revalidate()
                runtime_bound = components.bind_coordinator.bound
                stream_owner = components.stream_handler.accepting
            except BaseException as exc:
                self.poison_shutdown(exc)
                running = runtime_bound = stream_owner = False
        else:
            runtime_bound = stream_owner = False
        return {
            "waw_api_singleton": running,
            "waw_runtime_bound": running and runtime_bound,
            "waw_stream_owner": running and stream_owner,
        }

    def register_route(self, task: asyncio.Task[Any]) -> bool:
        self._require_components()
        return self._work_ledger.register_route(task)

    def unregister_route(self, task: asyncio.Task[Any]) -> None:
        self._work_ledger.unregister_route(task)

    def detach_operation(self, key: tuple[object, ...]) -> tuple[str, bool]:
        self._require_components()
        return self._work_ledger.detach_operation(key)

    def mark_detached(self, key: tuple[object, ...], operation_id: str) -> None:
        self._require_components()
        self._work_ledger.mark_detached(key, operation_id)

    def start(self) -> Coroutine[Any, Any, None]:
        self._ensure_process_current(allow_unbound=True)
        if self._start_operation is None:
            if self._state is not WAWAPIApplicationState.NEW:

                async def invalid() -> None:
                    raise WAWAPIApplicationError(
                        "WAW_API_UNAVAILABLE", "WAW API application cannot be restarted"
                    )

                return invalid()
            self._lifespan_pid = os.getpid()
            self._work_ledger.bind_process(self._lifespan_pid)
            self._state = WAWAPIApplicationState.STARTING
            self._start_operation = asyncio.create_task(self._perform_start())
        return self._await_operation(self._start_operation)

    async def _perform_start(self) -> None:
        try:
            self._process_lock.acquire()
            authority_epoch = secrets.randbelow((1 << 64) - 1) + 1
            authority_nonce = secrets.token_hex(16)
            produced = self._factory(authority_epoch, authority_nonce, self._work_ledger)
            if type(produced) is not WAWAPIComponents:
                raise WAWAPIApplicationError(
                    "WAW_API_COMPOSITION_INVALID", "WAW API component factory is invalid"
                )
            self._components = produced
            self._validate_components(produced, authority_epoch, authority_nonce)
            if self._close_requested:
                raise WAWAPIApplicationError(
                    "WAW_API_UNAVAILABLE", "WAW API application startup was fenced"
                )
            await produced.bind_coordinator.bind()
            if self._close_requested or not produced.bind_coordinator.bound:
                raise WAWAPIApplicationError(
                    "WAW_API_UNAVAILABLE", "WAW Runtime binding was not published"
                )
            self._process_lock.revalidate()
            self._state = WAWAPIApplicationState.RUNNING
        except BaseException:
            self._state = WAWAPIApplicationState.POISONED
            await self._cleanup_failed_start()
            raise

    def _validate_components(
        self, value: WAWAPIComponents, authority_epoch: int, authority_nonce: str
    ) -> None:
        if type(value.bind_coordinator) is not WAWRuntimeBindCoordinator:
            raise WAWAPIApplicationError(
                "WAW_API_COMPOSITION_INVALID", "WAW API bind coordinator is invalid"
            )
        if type(value.attachment_authority) is not AttachmentAuthority:
            raise WAWAPIApplicationError(
                "WAW_API_COMPOSITION_INVALID", "WAW API attachment authority is invalid"
            )
        if type(value.stream_handler) is not WAWStreamHandler:
            raise WAWAPIApplicationError(
                "WAW_API_COMPOSITION_INVALID", "WAW API stream handler is invalid"
            )
        if value.work_ledger is not self._work_ledger:
            raise WAWAPIApplicationError(
                "WAW_API_COMPOSITION_INVALID", "WAW API work ledger is inconsistent"
            )
        if not self._test_only:
            if type(value.control_client) is not WAWControlClient:
                raise WAWAPIApplicationError(
                    "WAW_API_COMPOSITION_INVALID", "WAW API control client is invalid"
                )
            if type(value.authorization_policy) is not SingleAdminWorkspacePolicy:
                raise WAWAPIApplicationError(
                    "WAW_API_COMPOSITION_INVALID", "WAW API authorization policy is invalid"
                )
            assert value.control_client is not None
            if not value.bind_coordinator.owns_control_client(value.control_client):
                raise WAWAPIApplicationError(
                    "WAW_API_COMPOSITION_INVALID",
                    "WAW API control client ownership is inconsistent",
                )
        if (
            value.attachment_authority.authority_epoch != authority_epoch
            or not value.bind_coordinator.owns_authority_identity(
                str(authority_epoch), authority_nonce
            )
            or value.stream_handler.authority is not value.attachment_authority
            or value.stream_handler.control is not value.bind_coordinator
            or value.stream_handler.policy is not value.authorization_policy
            or value.stream_handler.settings is not self._settings
            or value.stream_handler.services is not self._services
            or value.stream_handler.work_ledger is not self._work_ledger
        ):
            raise WAWAPIApplicationError(
                "WAW_API_COMPOSITION_INVALID", "WAW API component ownership is inconsistent"
            )

    def _begin_shutdown(self) -> None:
        self._close_requested = True
        self._work_ledger.begin_shutdown()
        components = self._components
        if components is not None:
            components.stream_handler.begin_shutdown()
            components.attachment_authority.begin_shutdown()

    async def _cleanup_failed_start(self) -> None:
        self._begin_shutdown()
        components = self._components
        if components is not None:
            for close in (components.stream_handler.close, components.bind_coordinator.close):
                try:
                    await close()
                except BaseException as exc:
                    if self._shutdown_failure is None:
                        self._shutdown_failure = exc
        try:
            await self._work_ledger.close()
        except BaseException as exc:
            if self._shutdown_failure is None:
                self._shutdown_failure = exc
        if components is not None and self._components_shutdown_clean(components):
            self._components = None

    def close(self) -> Coroutine[Any, Any, None]:
        self._ensure_process_current()
        if (
            self._close_operation is not None
            and self._close_operation.done()
            and self._shutdown_failure is not None
        ):

            async def failed() -> None:
                assert self._shutdown_failure is not None
                raise self._shutdown_failure

            return failed()
        if self._close_operation is None:
            self._begin_shutdown()
            if self._state is not WAWAPIApplicationState.POISONED:
                self._state = WAWAPIApplicationState.QUIESCING
            self._close_operation = asyncio.create_task(self._perform_close())
        return self._await_operation(self._close_operation)

    async def _perform_close(self) -> None:
        start = self._start_operation
        current = asyncio.current_task()
        if start is not None and start is not current and not start.done():
            with suppress(BaseException):
                await asyncio.shield(start)
        components = self._components
        if components is not None:
            for close in (components.stream_handler.close, components.bind_coordinator.close):
                try:
                    await close()
                except BaseException as exc:
                    if self._shutdown_failure is None:
                        self._shutdown_failure = exc
        try:
            await self._work_ledger.close()
        except BaseException as exc:
            if self._shutdown_failure is None:
                self._shutdown_failure = exc
        if components is not None:
            if self._shutdown_failure is not None or not self._components_shutdown_clean(
                components
            ):
                self._state = WAWAPIApplicationState.POISONED
                if self._shutdown_failure is not None:
                    raise self._shutdown_failure
                raise WAWAPIApplicationError(
                    "WAW_API_SHUTDOWN_INCOMPLETE", "WAW API application shutdown is incomplete"
                )
            self._components = None
        elif self._shutdown_failure is not None or not self._work_ledger.shutdown_clean:
            self._state = WAWAPIApplicationState.POISONED
            if self._shutdown_failure is not None:
                raise self._shutdown_failure
            raise WAWAPIApplicationError(
                "WAW_API_SHUTDOWN_INCOMPLETE", "WAW API work ledger did not close"
            )
        if self._process_lock.poisoned:
            self._state = WAWAPIApplicationState.POISONED
            failure = self._process_lock.terminal_failure
            assert failure is not None
            raise failure
        self._state = (
            WAWAPIApplicationState.DRAINED
            if self._process_lock.has_owned_fd
            else WAWAPIApplicationState.CLOSED
        )
        self._shutdown_clean = self._state is WAWAPIApplicationState.CLOSED

    def finalize_after_database_close(self) -> None:
        """Release the singleton only after every database user and DB are closed."""

        self._ensure_process_current()
        if self._state is WAWAPIApplicationState.CLOSED and self._shutdown_clean:
            return
        if self._state is not WAWAPIApplicationState.DRAINED or self._components is not None:
            self._state = WAWAPIApplicationState.POISONED
            raise WAWAPIApplicationError(
                "WAW_API_SHUTDOWN_INCOMPLETE", "WAW API application is not drained"
            )
        try:
            self._process_lock.release()
        except BaseException as exc:
            self.poison_shutdown(exc)
            raise
        self._shutdown_clean = True
        self._state = WAWAPIApplicationState.CLOSED

    def poison_shutdown(self, failure: BaseException) -> None:
        if self._shutdown_failure is None:
            self._shutdown_failure = failure
        self._begin_shutdown()
        self._shutdown_clean = False
        self._state = WAWAPIApplicationState.POISONED

    def _components_shutdown_clean(self, value: WAWAPIComponents) -> bool:
        control_clean = value.control_client is None or value.control_client.shutdown_clean
        return (
            value.stream_handler.shutdown_clean
            and value.attachment_authority.shutdown_clean
            and value.bind_coordinator.shutdown_clean
            and value.work_ledger.shutdown_clean
            and control_clean
        )

    async def _await_operation(self, operation: asyncio.Task[None]) -> None:
        interrupted = False
        while True:
            try:
                await asyncio.shield(operation)
                break
            except asyncio.CancelledError:
                if operation.cancelled():
                    raise
                interrupted = True
        if interrupted:
            raise asyncio.CancelledError

    def _ensure_process_current(self, *, allow_unbound: bool = False) -> None:
        if self._lifespan_pid is None and allow_unbound:
            return
        if self._lifespan_pid is not None and self._lifespan_pid != os.getpid():
            self.fence_after_fork()
        if self._lifespan_pid is not None and self._lifespan_pid != os.getpid():
            raise WAWAPIApplicationError(
                "WAW_API_SINGLETON_UNSAFE", "WAW API application crossed a process fork"
            )

    def fence_after_fork(self) -> None:
        """Fence an owner copied after lifespan startup and close known identity FDs."""

        if self._lifespan_pid is None or self._lifespan_pid == os.getpid():
            return
        failure = WAWAPIApplicationError(
            "WAW_API_SINGLETON_UNSAFE", "WAW API application crossed a process fork"
        )
        self._shutdown_failure = failure
        self._shutdown_clean = False
        self._close_requested = True
        self._state = WAWAPIApplicationState.POISONED
        components = self._components
        if components is not None:
            components.stream_handler.fence_after_fork()
            components.bind_coordinator.fence_after_fork()
        self._work_ledger.fence_after_fork()
        self._process_lock.fence_after_fork()


def _build_production_components(
    settings: Settings,
    services: ControlPlaneServices,
    authority_epoch: int,
    authority_nonce: str,
    work_ledger: WAWWorkLedger,
) -> WAWAPIComponents:
    """Build the sole fixed filesystem-v2 graph after the process lock is held."""

    try:
        anchor = load_waw_api_host_anchor_v2(_PRODUCTION_ANCHOR_PATH).anchor
        runtime_uid = pwd.getpwnam(_PRODUCTION_RUNTIME_USER).pw_uid
        runtime_gid = grp.getgrnam(_PRODUCTION_RUNTIME_GROUP).gr_gid
        api_uid = pwd.getpwnam(_PRODUCTION_API_USER).pw_uid
        api_gid = grp.getgrnam(_PRODUCTION_API_GROUP).gr_gid
        ipc_gid = grp.getgrnam(_PRODUCTION_IPC_GROUP).gr_gid
    except (KeyError, OSError, WAWAPIHostAnchorError) as exc:
        raise WAWAPIApplicationError(
            "WAW_API_COMPOSITION_UNAVAILABLE", "WAW production identity is unavailable"
        ) from exc
    if (
        os.geteuid() != api_uid
        or os.getegid() != api_gid
        or ipc_gid not in os.getgroups()
        or runtime_uid == api_uid
        or len({api_gid, runtime_gid, ipc_gid}) != 3
    ):
        raise WAWAPIApplicationError(
            "WAW_API_COMPOSITION_UNAVAILABLE", "WAW production identity is unavailable"
        )
    client = WAWControlClient(
        _PRODUCTION_CONTROL_SOCKET_PATH,
        expected_peer_uid=runtime_uid,
        expected_peer_gid=runtime_gid,
        expected_socket_uid=0,
        expected_socket_gid=ipc_gid,
        background_owner=work_ledger,
    )
    coordinator = WAWRuntimeBindCoordinator(
        client,
        api_authority_epoch=str(authority_epoch),
        authority_nonce=authority_nonce,
        expected_runtime_host_installation_id=anchor.runtime_host_installation_id,
        expected_runtime_host_installation_revision=anchor.runtime_host_installation_revision,
        expected_host_manifest_digest=anchor.host_manifest_digest,
        expected_project_root_manifest_digest=anchor.project_root_manifest_digest,
        expected_enrollment_epoch=anchor.enrollment_epoch,
        expected_enrollment_state=anchor.enrollment_state,
        request_id_factory=lambda: f"wreq_{secrets.token_hex(16)}",
        runtime_epoch_classifier=services.workspaces,
    )
    authority = AttachmentAuthority(clock=time.monotonic, authority_epoch=authority_epoch)
    policy = SingleAdminWorkspacePolicy()
    try:
        handler = WAWStreamHandler.production(
            services=services,
            settings=settings,
            authority=authority,
            control=coordinator,
            policy=policy,
            work_ledger=work_ledger,
            socket_trust=RuntimeSocketTrust(ipc_gid, runtime_uid, runtime_gid),
        )
    except RelayFailure as exc:
        raise WAWAPIApplicationError(
            "WAW_API_COMPOSITION_UNAVAILABLE", "WAW production stream is unavailable"
        ) from exc
    return WAWAPIComponents(client, coordinator, authority, policy, handler, work_ledger)


_PROCESS_LOCKS: weakref.WeakSet[WAWAPIProcessLock] = weakref.WeakSet()
_APPLICATIONS: weakref.WeakSet[WAWAPIApplication] = weakref.WeakSet()


def _fence_inherited_waw_owners() -> None:
    for application in tuple(_APPLICATIONS):
        application.fence_after_fork()
    for process_lock in tuple(_PROCESS_LOCKS):
        process_lock.fence_after_fork()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_fence_inherited_waw_owners)


__all__ = [
    "WAWAPIApplication",
    "WAWAPIApplicationError",
    "WAWAPIApplicationState",
    "WAW_APPLICATION_SCOPE_KEY",
    "WAWAPIComponentFactory",
    "WAWAPIComponents",
    "WAWAPIProcessLock",
    "WAWMode",
    "WAWWorkLedger",
]
