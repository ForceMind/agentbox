"""Single-owner Runtime application composition for the WAW software path."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from agentbox_runtime.capabilities import RuntimeCapabilityCollector
from agentbox_runtime.claude import ClaudeSessionManager
from agentbox_runtime.codex import CodexManager
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.server import (
    RuntimeExecutorServer,
    _build_runtime_server_from_filesystem_v2,
)
from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_bootstrap import _build_waw_encrypted_stream_server
from agentbox_runtime.waw_encrypted_server import WAWEncryptedServer
from agentbox_runtime.waw_encrypted_stream import WAWEncryptedRegistry
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority
from agentbox_runtime.waw_lifecycle import BindingDigestFactory
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.workspace import ProjectWorkspaceManager


class WAWRuntimeApplicationState(StrEnum):
    NEW = "NEW"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    POISONED = "POISONED"


@runtime_checkable
class WAWRuntimeStaticKeyPort(Protocol):
    """Runtime-only key custody port; application code never stores key bytes."""

    def preflight(self) -> None: ...

    def take(self) -> WAWRuntimeStaticKeyPort: ...

    def private_key(self) -> bytes: ...

    def close(self) -> bool: ...


@runtime_checkable
class WAWRuntimeExecutorProvider(Protocol):
    """Own the production executor and all lower fixed Runtime resources."""

    def create_executor(
        self,
        runtime_epoch: str,
        authority: WAWVerifiedExecutionAuthority,
    ) -> WAWSupervisorExecutor: ...

    def take(self) -> WAWRuntimeExecutorProvider: ...

    def close(self) -> bool: ...


@dataclass(frozen=True)
class WAWRuntimeShutdownEvidence:
    stream_clean: bool
    lifecycle_clean: bool
    control_clean: bool
    legacy_clean: bool
    key_port_closed: bool
    executor_provider_closed: bool

    @property
    def clean(self) -> bool:
        return all(
            (
                self.stream_clean,
                self.lifecycle_clean,
                self.control_clean,
                self.legacy_clean,
                self.key_port_closed,
                self.executor_provider_closed,
            )
        )


_APPLICATION_TOKEN = object()
_CONSTRUCTION_TOKEN = object()


class WAWRuntimeConstructionCleanup:
    """Retain a partial composition until reverse cleanup is confirmed."""

    def __init__(self, token: object) -> None:
        if token is not _CONSTRUCTION_TOKEN:
            raise RuntimeError("construction cleanup is not caller-constructible")
        self.sockets: WAWActivatedSockets | None = None
        self.key_port: WAWRuntimeStaticKeyPort | None = None
        self.executor_provider: WAWRuntimeExecutorProvider | None = None
        self.runtime_server: RuntimeExecutorServer | None = None
        self.stream_server: WAWEncryptedServer | None = None
        self._control_raw_closed = False
        self._stream_raw_closed = False
        self._key_closed = False
        self._provider_closed = False
        self._clean = False
        self._operation: asyncio.Task[bool] | None = None
        self._lock = threading.RLock()

    @property
    def clean(self) -> bool:
        return self._clean

    async def close(self) -> bool:
        with self._lock:
            operation = self._operation
            if operation is None or (operation.done() and not self._clean):
                operation = asyncio.create_task(self._perform_close())
                self._operation = operation
        return await asyncio.shield(operation)

    async def _perform_close(self) -> bool:
        stream_clean = self.stream_server is None and self.sockets is None
        runtime_clean = self.runtime_server is None and self.sockets is None
        if self.stream_server is not None:
            with contextlib.suppress(BaseException):
                await self.stream_server.close()
            stream_clean = self.stream_server.shutdown_clean
        elif self.sockets is not None and not self._stream_raw_closed:
            try:
                self.sockets.stream.close()
            except BaseException:
                stream_clean = False
            else:
                self._stream_raw_closed = stream_clean = True
        else:
            stream_clean = self._stream_raw_closed or self.sockets is None
        if self.runtime_server is not None:
            with contextlib.suppress(BaseException):
                await self.runtime_server.close()
            runtime_clean = self.runtime_server.shutdown_clean
        elif self.sockets is not None and not self._control_raw_closed:
            try:
                self.sockets.control.close()
            except BaseException:
                runtime_clean = False
            else:
                self._control_raw_closed = runtime_clean = True
        else:
            runtime_clean = self._control_raw_closed or self.sockets is None
        if self.key_port is not None and stream_clean and not self._key_closed:
            with contextlib.suppress(BaseException):
                self._key_closed = self.key_port.close() is True
        if (
            self.executor_provider is not None
            and stream_clean
            and runtime_clean
            and not self._provider_closed
        ):
            with contextlib.suppress(BaseException):
                self._provider_closed = self.executor_provider.close() is True
        key_clean = self.key_port is None or self._key_closed
        provider_clean = self.executor_provider is None or self._provider_closed
        self._clean = stream_clean and runtime_clean and key_clean and provider_clean
        return self._clean

    def __repr__(self) -> str:
        return f"WAWRuntimeConstructionCleanup(clean={self.clean!r})"


class WAWRuntimeApplicationBuildError(RuntimeOperationError):
    def __init__(self, cleanup: WAWRuntimeConstructionCleanup) -> None:
        super().__init__(
            "RUNTIME_UNAVAILABLE",
            "WAW Runtime application construction cleanup is incomplete",
            category="unavailable",
        )
        self.cleanup = cleanup


class WAWRuntimeApplication:
    """Own stream, control/lifecycle/legacy, key and executor provider once."""

    def __init__(
        self,
        token: object,
        *,
        runtime_server: RuntimeExecutorServer,
        stream_server: WAWEncryptedServer,
        encrypted_registry: WAWEncryptedRegistry,
        key_port: WAWRuntimeStaticKeyPort,
        executor_provider: WAWRuntimeExecutorProvider,
    ) -> None:
        if token is not _APPLICATION_TOKEN:
            raise RuntimeOperationError(
                "WAW_COMPOSITION_MISMATCH",
                "Runtime application is not caller-constructible",
                category="conflict",
            )
        composition = runtime_server.waw_fixed_runtime
        if (
            type(runtime_server) is not RuntimeExecutorServer
            or type(stream_server) is not WAWEncryptedServer
            or type(encrypted_registry) is not WAWEncryptedRegistry
            or composition is None
            or composition.registry._encrypted_attachments is None
            or composition.registry._encrypted_attachments.registry is not encrypted_registry
            or encrypted_registry.runtime_epoch != composition.runtime_epoch
            or not isinstance(key_port, WAWRuntimeStaticKeyPort)
            or not isinstance(executor_provider, WAWRuntimeExecutorProvider)
        ):
            raise RuntimeOperationError(
                "WAW_COMPOSITION_MISMATCH",
                "Runtime application components are not exact",
                category="conflict",
            )
        self._runtime = runtime_server
        self._stream = stream_server
        self._encrypted = encrypted_registry
        self._registry = composition.registry
        self._composition = composition
        self._key_port = key_port
        self._executor_provider = executor_provider
        self._state = WAWRuntimeApplicationState.NEW
        self._state_lock = threading.RLock()
        self._start_operation: asyncio.Task[None] | None = None
        self._close_operation: asyncio.Task[None] | None = None
        self._shutdown_evidence: WAWRuntimeShutdownEvidence | None = None
        self._startup_failure: BaseException | None = None
        self._key_closed = False
        self._provider_closed = False

    @property
    def state(self) -> WAWRuntimeApplicationState:
        with self._state_lock:
            return self._state

    @property
    def ready(self) -> bool:
        return (
            self.state is WAWRuntimeApplicationState.RUNNING
            and self._registry.application_gate_open
        )

    @property
    def shutdown_evidence(self) -> WAWRuntimeShutdownEvidence | None:
        return self._shutdown_evidence

    async def start(self, *, create_development_parent: bool = False) -> None:
        with self._state_lock:
            if self._state is WAWRuntimeApplicationState.RUNNING:
                return
            if self._state not in {
                WAWRuntimeApplicationState.NEW,
                WAWRuntimeApplicationState.STARTING,
            }:
                raise RuntimeError("WAW Runtime application is unavailable")
            operation = self._start_operation
            if operation is None:
                self._state = WAWRuntimeApplicationState.STARTING
                operation = asyncio.create_task(
                    self._perform_start(create_development_parent=create_development_parent)
                )
                self._start_operation = operation
                operation.add_done_callback(self._consume_operation)
        await asyncio.shield(operation)

    async def _perform_start(self, *, create_development_parent: bool) -> None:
        try:
            await self._registry.restore_project_binding_inventory()
            self._require_starting()
            await self._stream.start()
            self._require_starting()
            control = self._runtime.waw_control_server
            if control is None:
                raise RuntimeError("WAW Runtime control server is unavailable")
            await control.start()
            self._require_starting()
            await self._runtime.start(create_development_parent=create_development_parent)
            self._require_starting()
            if (
                self._runtime.waw_fixed_runtime is not self._composition
                or self._runtime.waw_peer_authority is not self._registry.peer_authority
                or self._composition.executor.runtime_epoch != self._composition.runtime_epoch
            ):
                raise RuntimeError("WAW Runtime composition changed during startup")
            if not self._registry.binding_inventory_finalize_required:
                self._registry.open_application_gate()
            with self._state_lock:
                if self._state is not WAWRuntimeApplicationState.STARTING:
                    self._registry.close_application_gate()
                    raise RuntimeError("WAW Runtime startup lost ownership")
                self._state = WAWRuntimeApplicationState.RUNNING
        except BaseException as exc:
            self._startup_failure = exc
            with contextlib.suppress(BaseException):
                await self.close()
            raise

    def _require_starting(self) -> None:
        if self.state is not WAWRuntimeApplicationState.STARTING:
            raise RuntimeError("WAW Runtime startup was fenced")

    def close(self) -> Coroutine[object, object, None]:
        """Synchronously fence admission and join one shielded close operation."""

        with self._state_lock:
            operation = self._close_operation
            if operation is None:
                self._registry.close_application_gate()
                initial_error = self._startup_failure
                try:
                    self._encrypted.invalidate()
                except BaseException as exc:
                    if initial_error is None:
                        initial_error = exc
                self._state = WAWRuntimeApplicationState.CLOSING
                stream_wait = asyncio.create_task(self._stream.close())
                runtime_wait = asyncio.create_task(self._runtime.close())
                operation = asyncio.create_task(
                    self._perform_close(stream_wait, runtime_wait, initial_error)
                )
                self._close_operation = operation
                operation.add_done_callback(self._consume_operation)
        return self._await_close(operation)

    async def _await_close(self, operation: asyncio.Task[None]) -> None:
        await asyncio.shield(operation)

    async def _perform_close(
        self,
        stream_wait: asyncio.Task[None],
        runtime_wait: asyncio.Task[None],
        initial_error: BaseException | None,
    ) -> None:
        failure = initial_error
        for attempt in range(2):
            try:
                await self._perform_close_body(stream_wait, runtime_wait, failure)
                return
            except asyncio.CancelledError as exc:
                if failure is None:
                    failure = exc
                current = asyncio.current_task()
                if current is not None:
                    while current.cancelling():
                        current.uncancel()
                if attempt == 1:
                    break
        self._shutdown_evidence = WAWRuntimeShutdownEvidence(
            False,
            False,
            False,
            False,
            self._key_closed,
            self._provider_closed,
        )
        with self._state_lock:
            self._state = WAWRuntimeApplicationState.POISONED
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "WAW Runtime application shutdown was cancelled",
            category="unavailable",
        ) from failure

    async def _perform_close_body(
        self,
        stream_wait: asyncio.Task[None],
        runtime_wait: asyncio.Task[None],
        initial_error: BaseException | None,
    ) -> None:
        first_error = initial_error
        start = self._start_operation
        current = asyncio.current_task()
        if start is not None and start is not current and not start.done():
            start.cancel()
        for task in (stream_wait, runtime_wait):
            try:
                await asyncio.shield(task)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        stream_clean = bool(getattr(self._stream, "shutdown_clean", False))
        control = self._runtime.waw_control_server
        control_clean = control is not None and control.shutdown_clean
        lifecycle_clean = self._registry.shutdown_clean
        legacy_clean = self._runtime.legacy_shutdown_clean
        if stream_clean and not self._key_closed:
            try:
                self._key_closed = self._key_port.close() is True
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if (
            stream_clean
            and control_clean
            and lifecycle_clean
            and legacy_clean
            and not self._provider_closed
        ):
            try:
                self._provider_closed = self._executor_provider.close() is True
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        evidence = WAWRuntimeShutdownEvidence(
            stream_clean,
            lifecycle_clean,
            control_clean,
            legacy_clean,
            self._key_closed,
            self._provider_closed,
        )
        self._shutdown_evidence = evidence
        with self._state_lock:
            self._state = (
                WAWRuntimeApplicationState.CLOSED
                if evidence.clean and first_error is None
                else WAWRuntimeApplicationState.POISONED
            )
        if self._state is WAWRuntimeApplicationState.POISONED:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "WAW Runtime application shutdown is incomplete",
                category="unavailable",
            ) from first_error

    @staticmethod
    def _consume_operation(operation: asyncio.Task[None]) -> None:
        with contextlib.suppress(BaseException):
            operation.result()

    def __repr__(self) -> str:
        return f"WAWRuntimeApplication(state={self.state.value!r})"


async def build_waw_runtime_application_from_filesystem_v2(
    *,
    socket_path: Path,
    manager: CodexManager,
    claude_manager: ClaudeSessionManager,
    allowed_peer_uids: frozenset[int],
    allowed_peer_gids: frozenset[int],
    formal_project_id_for_legacy: Callable[[str], str | None],
    activated_sockets: WAWActivatedSockets,
    waw_control_peer_uid: int,
    waw_control_peer_gid: int,
    runtime_manifest_path: Path,
    public_directory: Path,
    expected_runtime_gid: int,
    epoch_store: WAWRuntimeEpochStore,
    executor_provider: WAWRuntimeExecutorProvider,
    key_port: WAWRuntimeStaticKeyPort,
    clock: Callable[[], float],
    binding_digest_factory: BindingDigestFactory | None = None,
    project_manager: ProjectWorkspaceManager | None = None,
    capability_collector: RuntimeCapabilityCollector | None = None,
) -> WAWRuntimeApplication:
    """Compose one epoch and one control/stream/legacy Runtime application."""

    if type(activated_sockets) is not WAWActivatedSockets:
        raise TypeError("loader-produced WAW activated sockets are required")
    if not isinstance(executor_provider, WAWRuntimeExecutorProvider) or not isinstance(
        key_port, WAWRuntimeStaticKeyPort
    ):
        raise TypeError("typed Runtime executor and key ports are required")
    owned_sockets: WAWActivatedSockets | None = None
    owned_key: WAWRuntimeStaticKeyPort | None = None
    owned_provider: WAWRuntimeExecutorProvider | None = None
    runtime_server: RuntimeExecutorServer | None = None
    stream_server: WAWEncryptedServer | None = None
    cleanup = WAWRuntimeConstructionCleanup(_CONSTRUCTION_TOKEN)
    try:
        owned_sockets = activated_sockets.take()
        cleanup.sockets = owned_sockets
        owned_key = key_port.take()
        cleanup.key_port = owned_key
        owned_provider = executor_provider.take()
        cleanup.executor_provider = owned_provider
        if (
            owned_key is key_port
            or owned_provider is executor_provider
            or not isinstance(owned_key, WAWRuntimeStaticKeyPort)
            or not isinstance(owned_provider, WAWRuntimeExecutorProvider)
        ):
            raise RuntimeOperationError(
                "WAW_COMPOSITION_MISMATCH",
                "Runtime port ownership transfer is invalid",
                category="conflict",
            )
        owned_key.preflight()
        runtime_server = _build_runtime_server_from_filesystem_v2(
            socket_path=socket_path,
            manager=manager,
            claude_manager=claude_manager,
            allowed_peer_uids=allowed_peer_uids,
            allowed_peer_gids=allowed_peer_gids,
            formal_project_id_for_legacy=formal_project_id_for_legacy,
            activated_sockets=owned_sockets,
            waw_control_peer_uid=waw_control_peer_uid,
            waw_control_peer_gid=waw_control_peer_gid,
            runtime_manifest_path=runtime_manifest_path,
            public_directory=public_directory,
            expected_runtime_gid=expected_runtime_gid,
            epoch_store=epoch_store,
            executor_factory=owned_provider.create_executor,
            binding_digest_factory=binding_digest_factory,
            project_manager=project_manager,
            capability_collector=capability_collector,
        )
        cleanup.runtime_server = runtime_server
        composition = runtime_server.waw_fixed_runtime
        authority = runtime_server.waw_peer_authority
        if composition is None or authority is None:
            raise RuntimeOperationError(
                "WAW_COMPOSITION_MISMATCH",
                "Runtime fixed composition is unavailable",
                category="conflict",
            )
        composition.registry.configure_application_gate()
        stream_server, encrypted = _build_waw_encrypted_stream_server(
            sockets=owned_sockets,
            registry=composition.registry,
            executor=composition.executor,
            runtime_epoch=composition.runtime_epoch,
            static_key=owned_key.private_key,
            peer_authority=authority,
            expected_peer_uid=waw_control_peer_uid,
            expected_peer_gid=waw_control_peer_gid,
            clock=clock,
        )
        cleanup.stream_server = stream_server
        return WAWRuntimeApplication(
            _APPLICATION_TOKEN,
            runtime_server=runtime_server,
            stream_server=stream_server,
            encrypted_registry=encrypted,
            key_port=owned_key,
            executor_provider=owned_provider,
        )
    except BaseException as exc:
        if not await cleanup.close():
            raise WAWRuntimeApplicationBuildError(cleanup) from exc
        if isinstance(exc, (RuntimeOperationError, TypeError, ValueError)):
            raise
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "WAW Runtime application construction failed",
            category="unavailable",
        ) from exc


__all__ = [
    "WAWRuntimeApplication",
    "WAWRuntimeApplicationBuildError",
    "WAWRuntimeApplicationState",
    "WAWRuntimeConstructionCleanup",
    "WAWRuntimeExecutorProvider",
    "WAWRuntimeShutdownEvidence",
    "WAWRuntimeStaticKeyPort",
    "build_waw_runtime_application_from_filesystem_v2",
]
