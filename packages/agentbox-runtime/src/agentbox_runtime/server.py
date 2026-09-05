"""Minimal non-root Runtime Executor for allowlisted Codex and Claude actions."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import os
import socket
import stat
import struct
import threading
import weakref
from collections.abc import Callable, Coroutine, Mapping
from pathlib import Path
from typing import Any

from agentbox_core.waw import AgentType
from agentbox_protocol.runtime_capabilities import (
    RUNTIME_CAPABILITY_ACTION,
    RuntimeCapabilityQuery,
)

from agentbox_runtime.capabilities import RuntimeCapabilityCollector
from agentbox_runtime.claude import ClaudeAdapter, ClaudeSessionManager
from agentbox_runtime.codex import CodexAdapter, CodexManager
from agentbox_runtime.git import GitAdapter, validate_branch_name, validate_git_repository_url
from agentbox_runtime.github import GitHubAdapter, validate_pr_body, validate_pr_title
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import ProjectRegistry, validate_project_id
from agentbox_runtime.rpc import (
    MAX_RUNTIME_FRAME,
    RUNTIME_PROTOCOL_VERSION,
    strict_json_loads,
    validate_request_id,
)
from agentbox_runtime.tmux import TmuxAdapter
from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_auth_probe import (
    WAWCachedPublicAuthProbe,
    WAWPublicAuthEvidence,
    WAWPublicAuthProbe,
    WAWPublicAuthProbeCache,
    WAWVendorPublicAuthBinding,
    WAWVendorPublicAuthProbeAdapter,
)
from agentbox_runtime.waw_bootstrap import (
    WAWFixedRuntimeComposition,
    build_waw_control_server,
    create_waw_lifecycle_registry_from_filesystem_bundle,
)
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)
from agentbox_runtime.waw_control_server import WAWControlServer
from agentbox_runtime.waw_epoch import WAWRuntimeEpochError, WAWRuntimeEpochStore
from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority
from agentbox_runtime.waw_lifecycle import BindingDigestFactory
from agentbox_runtime.waw_peer_authority import WAWPeerAuthority
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.waw_vendor_probe import WAWVendorProbeRunner
from agentbox_runtime.workspace import ProjectWorkspaceManager, validate_operation_id

_CODEX_ACTIONS = frozenset(
    {"codex.status", "codex.remote.start", "codex.remote.stop", "codex.pair"}
)
_CLAUDE_GLOBAL_ACTIONS = frozenset({"claude.status", "claude.sessions.list"})
_CLAUDE_PROJECT_ACTIONS = frozenset(
    {
        "claude.session.status",
        "claude.session.start",
        "claude.session.stop",
        "claude.session.output",
    }
)
_ACTIONS = _CODEX_ACTIONS | _CLAUDE_GLOBAL_ACTIONS | _CLAUDE_PROJECT_ACTIONS
_ACTIONS |= frozenset({RUNTIME_CAPABILITY_ACTION})
_PROJECT_ACTION_KEYS: dict[str, frozenset[str]] = {
    "project.list": frozenset(),
    "project.create": frozenset({"project_key", "operation_id"}),
    "project.clone": frozenset({"project_key", "operation_id", "repository_url"}),
    "project.finalize": frozenset({"project_key", "operation_id"}),
    "project.rollback": frozenset({"project_key", "operation_id"}),
    "git.status": frozenset({"project_key"}),
    "git.global.status": frozenset(),
    "git.branches.list": frozenset({"project_key"}),
    "git.branch.create": frozenset({"project_key", "branch"}),
    "git.branch.switch": frozenset({"project_key", "branch"}),
    "git.pull": frozenset({"project_key"}),
    "git.push": frozenset({"project_key"}),
    "github.status": frozenset(),
    "github.project.status": frozenset({"project_key"}),
    "github.pr.create": frozenset({"project_key", "title", "body", "base"}),
}
_ACTIONS |= frozenset(_PROJECT_ACTION_KEYS)
_CONTROL_SERVER_ISSUES: weakref.WeakKeyDictionary[
    WAWControlServer, tuple[WAWFixedRuntimeComposition, str, WAWPeerAuthority]
] = weakref.WeakKeyDictionary()
_CONTROL_SERVER_ISSUE_LOCK = threading.Lock()
_CONNECTION_SHUTDOWN_GRACE_SECONDS = 0.05


class _RuntimeConflictProbe:
    """Closed callback composition; callbacks must be bounded synchronous probes."""

    def __init__(
        self,
        *,
        legacy_claude: Callable[[str], WAWLegacyClaudeState],
        legacy_codex_remote: Callable[[], WAWLegacyCodexState],
        waw_for_project: Callable[[str], tuple[WAWManagedConflictState, ...]],
        waw_for_host: Callable[[], tuple[WAWManagedConflictState, ...]],
    ) -> None:
        self._legacy_claude = legacy_claude
        self._legacy_codex_remote = legacy_codex_remote
        self._waw_for_project = waw_for_project
        self._waw_for_host = waw_for_host

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        return self._legacy_claude(project_id)

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        return self._legacy_codex_remote()

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        return self._waw_for_project(project_id)

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        return self._waw_for_host()


class RuntimeExecutorServer:
    def __init__(
        self,
        socket_path: Path,
        manager: CodexManager,
        *,
        allowed_peer_uids: frozenset[int],
        allowed_peer_gids: frozenset[int] | None = None,
        claude_manager: ClaudeSessionManager | None = None,
        project_manager: ProjectWorkspaceManager | None = None,
        capability_collector: RuntimeCapabilityCollector | None = None,
        read_timeout_seconds: float = 5.0,
        write_timeout_seconds: float = 5.0,
        trailing_timeout_seconds: float = 0.01,
        waw_epoch_store: WAWRuntimeEpochStore | None = None,
        waw_control_server: WAWControlServer | None = None,
        enable_waw_fixed_process: bool = False,
        legacy_claude: Callable[[str], WAWLegacyClaudeState] | None = None,
        legacy_codex_remote: Callable[[], WAWLegacyCodexState] | None = None,
        waw_for_project: Callable[[str], tuple[WAWManagedConflictState, ...]] | None = None,
        waw_for_host: Callable[[], tuple[WAWManagedConflictState, ...]] | None = None,
        formal_project_id_for_legacy: Callable[[str], str | None] | None = None,
        waw_vendor_probe_runner: WAWVendorProbeRunner | None = None,
        waw_vendor_auth_bindings: Mapping[AgentType, WAWVendorPublicAuthBinding] | None = None,
        waw_auth_probe_cache: WAWPublicAuthProbeCache | None = None,
        waw_fixed_runtime: WAWFixedRuntimeComposition | None = None,
    ) -> None:
        if read_timeout_seconds <= 0 or write_timeout_seconds <= 0 or trailing_timeout_seconds <= 0:
            raise ValueError("Runtime socket timeouts must be positive")
        if (
            waw_fixed_runtime is not None
            and type(waw_fixed_runtime) is not WAWFixedRuntimeComposition
        ):
            raise TypeError("waw_fixed_runtime must be WAWFixedRuntimeComposition")
        if waw_fixed_runtime is not None and waw_epoch_store is not None:
            raise ValueError("waw_fixed_runtime and waw_epoch_store are mutually exclusive")
        if waw_fixed_runtime is not None and not enable_waw_fixed_process:
            raise ValueError("waw_fixed_runtime requires fixed-process mode")
        self._socket_path = socket_path
        self._manager = manager
        self._claude_manager = claude_manager
        self._project_manager = project_manager
        self._capability_collector = capability_collector
        self._allowed_peer_uids = allowed_peer_uids
        self._allowed_peer_gids = allowed_peer_gids or frozenset({os.getegid()})
        self._read_timeout_seconds = read_timeout_seconds
        self._write_timeout_seconds = write_timeout_seconds
        self._trailing_timeout_seconds = trailing_timeout_seconds
        self._waw_epoch_store: WAWRuntimeEpochStore | None = waw_epoch_store
        self._waw_control_server = waw_control_server
        self._waw_fixed_runtime = waw_fixed_runtime
        self._waw_public_auth_probe: WAWPublicAuthProbe | None = None
        self._waw_auth_probe_cache: WAWPublicAuthProbeCache | None = None
        self._waw_conflict_coordinator: WAWConflictCoordinator | None = None
        self._waw_peer_authority: WAWPeerAuthority | None = None
        self._waw_runtime_epoch: int | None = None
        if waw_fixed_runtime is not None:
            if any(
                value is not None
                for value in (
                    legacy_claude,
                    legacy_codex_remote,
                    waw_for_project,
                    waw_for_host,
                    waw_vendor_probe_runner,
                    waw_vendor_auth_bindings,
                    waw_auth_probe_cache,
                )
            ):
                raise ValueError("fixed composition owns conflict and auth providers")
            coordinator = waw_fixed_runtime.executor.conflict_coordinator
            auth_probe = waw_fixed_runtime.executor.auth_probe
            peer_authority = waw_fixed_runtime.registry.peer_authority
            with _CONTROL_SERVER_ISSUE_LOCK:
                control_issue = (
                    _CONTROL_SERVER_ISSUES.pop(waw_control_server, None)
                    if type(waw_control_server) is WAWControlServer
                    else None
                )
            if (
                type(coordinator) is not WAWConflictCoordinator
                or type(auth_probe) is not WAWCachedPublicAuthProbe
                or type(peer_authority) is not WAWPeerAuthority
                or waw_fixed_runtime.executor.runtime_epoch != waw_fixed_runtime.runtime_epoch
                or waw_fixed_runtime.executor.execution_authority
                is not waw_fixed_runtime.execution_authority
                or control_issue is None
                or control_issue[0] is not waw_fixed_runtime
                or control_issue[1] != waw_fixed_runtime.runtime_epoch
                or control_issue[2] is not peer_authority
                or not callable(formal_project_id_for_legacy)
                or type(self._manager) is not CodexManager
                or type(self._claude_manager) is not ClaudeSessionManager
                or self._manager.conflict_coordinator is not None
                or self._claude_manager.conflict_coordinator is not None
            ):
                raise RuntimeOperationError(
                    "WAW_COMPOSITION_MISMATCH",
                    "Server cannot bind the exact fixed Runtime composition",
                    category="conflict",
                )
            assert waw_control_server is not None
            self._waw_public_auth_probe = auth_probe
            self._waw_auth_probe_cache = auth_probe.cache
            self._waw_conflict_coordinator = coordinator
            self._waw_peer_authority = peer_authority
            self._manager.bind_conflict_coordinator(coordinator)
            self._claude_manager.bind_conflict_coordinator(
                coordinator,
                formal_project_id_for_legacy=formal_project_id_for_legacy,
            )
            self._waw_runtime_epoch = int(waw_fixed_runtime.runtime_epoch)
        else:
            self._waw_public_auth_probe, self._waw_auth_probe_cache = self._configure_waw_auth(
                enable=enable_waw_fixed_process,
                runner=waw_vendor_probe_runner,
                bindings=waw_vendor_auth_bindings,
                cache=waw_auth_probe_cache,
            )
            self._waw_conflict_coordinator = self._configure_waw_conflicts(
                enable=enable_waw_fixed_process,
                legacy_claude=legacy_claude,
                legacy_codex_remote=legacy_codex_remote,
                waw_for_project=waw_for_project,
                waw_for_host=waw_for_host,
                formal_project_id_for_legacy=formal_project_id_for_legacy,
            )
            self._waw_runtime_epoch = None
        self._server: asyncio.AbstractServer | None = None
        self._closing = False
        self._closed = False
        self._poisoned = False
        self._start_task: asyncio.Task[Any] | None = None
        self._close_operation: asyncio.Task[None] | None = None
        self._connection_tasks: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def waw_runtime_epoch(self) -> int | None:
        """The immutable epoch consumed before WAW traffic can be served."""

        return self._waw_runtime_epoch

    @property
    def waw_conflict_coordinator(self) -> WAWConflictCoordinator | None:
        """Return the one coordinator shared by legacy and fixed WAW paths."""

        return self._waw_conflict_coordinator

    @property
    def waw_fixed_runtime(self) -> WAWFixedRuntimeComposition | None:
        return self._waw_fixed_runtime

    @property
    def waw_peer_authority(self) -> WAWPeerAuthority | None:
        """Return the authority shared by control, lifecycle and stream wiring."""

        return self._waw_peer_authority

    @property
    def waw_public_auth_probe(self) -> WAWPublicAuthProbe | None:
        """The inert adapter configured for fixed-process local composition."""

        return self._waw_public_auth_probe

    @property
    def waw_auth_probe_cache(self) -> WAWPublicAuthProbeCache | None:
        return self._waw_auth_probe_cache

    async def refresh_waw_public_auth_evidence(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence | None:
        """Run the configured local probe; this is not an RPC/Web action."""

        if self._waw_public_auth_probe is None or self._waw_auth_probe_cache is None:
            return None
        return await self._waw_public_auth_probe.probe(
            agent_type=agent_type,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            executable_fingerprint=executable_fingerprint,
            checked_at_monotonic=checked_at_monotonic,
        )

    @staticmethod
    def _configure_waw_auth(
        *,
        enable: bool,
        runner: WAWVendorProbeRunner | None,
        bindings: Mapping[AgentType, WAWVendorPublicAuthBinding] | None,
        cache: WAWPublicAuthProbeCache | None,
    ) -> tuple[WAWPublicAuthProbe | None, WAWPublicAuthProbeCache | None]:
        configured = (runner is not None, bindings is not None)
        if not enable:
            if any(configured) or cache is not None:
                raise ValueError("WAW auth probe configuration requires fixed-process mode")
            return None, None
        if any(configured) and not all(configured):
            raise ValueError("WAW vendor runner and bindings must be provided together")
        if cache is not None and type(cache) is not WAWPublicAuthProbeCache:
            raise TypeError("waw_auth_probe_cache must be WAWPublicAuthProbeCache")
        actual_cache = cache or WAWPublicAuthProbeCache()
        if runner is None or bindings is None:
            return None, actual_cache
        adapter = WAWVendorPublicAuthProbeAdapter(runner, bindings)
        return WAWCachedPublicAuthProbe(adapter, actual_cache), actual_cache

    def _configure_waw_conflicts(
        self,
        *,
        enable: bool,
        legacy_claude: Callable[[str], WAWLegacyClaudeState] | None,
        legacy_codex_remote: Callable[[], WAWLegacyCodexState] | None,
        waw_for_project: Callable[[str], tuple[WAWManagedConflictState, ...]] | None,
        waw_for_host: Callable[[], tuple[WAWManagedConflictState, ...]] | None,
        formal_project_id_for_legacy: Callable[[str], str | None] | None,
    ) -> WAWConflictCoordinator | None:
        if type(enable) is not bool:
            raise TypeError("enable_waw_fixed_process must be bool")
        providers = (
            legacy_claude,
            legacy_codex_remote,
            waw_for_project,
            waw_for_host,
            formal_project_id_for_legacy,
        )
        if not enable:
            if any(provider is not None for provider in providers):
                raise ValueError("WAW conflict providers require fixed-process mode")
            return None
        if not all(callable(provider) for provider in providers):
            raise ValueError("fixed-process mode requires all conflict providers")
        assert legacy_claude is not None
        assert legacy_codex_remote is not None
        assert waw_for_project is not None
        assert waw_for_host is not None
        assert formal_project_id_for_legacy is not None
        if (
            type(self._manager) is not CodexManager
            or type(self._claude_manager) is not ClaudeSessionManager
        ):
            raise TypeError("fixed-process mode requires concrete legacy managers")
        if (
            self._manager.conflict_coordinator is not None
            or self._claude_manager.conflict_coordinator is not None
        ):
            raise RuntimeOperationError(
                "WAW_CONFLICT_COORDINATOR_BOUND",
                "Legacy manager conflict coordinator is already bound",
                category="conflict",
            )
        probe = _RuntimeConflictProbe(
            legacy_claude=legacy_claude,
            legacy_codex_remote=legacy_codex_remote,
            waw_for_project=waw_for_project,
            waw_for_host=waw_for_host,
        )
        coordinator = WAWConflictCoordinator(probe)
        self._manager.bind_conflict_coordinator(coordinator)
        self._claude_manager.bind_conflict_coordinator(
            coordinator,
            formal_project_id_for_legacy=formal_project_id_for_legacy,
        )
        return coordinator

    async def start(self, *, create_development_parent: bool = False) -> None:
        self._reset_clean_nonfixed_restart()
        if self._closing or self._closed or self._close_operation is not None:
            raise RuntimeError("Runtime server is unavailable")
        if self._server is not None:
            return
        current_task = asyncio.current_task()
        if current_task is None:
            raise RuntimeError("Runtime server requires an asyncio task")
        start_task = self._start_task
        if start_task is not None and start_task is not current_task:
            await asyncio.shield(start_task)
            return
        self._start_task = current_task
        try:
            if self._waw_epoch_store is not None and self._waw_runtime_epoch is None:
                try:
                    self._waw_runtime_epoch = self._waw_epoch_store.consume()
                except WAWRuntimeEpochError as exc:
                    raise RuntimeError("WAW Runtime epoch trust root is unavailable") from exc
            parent = self._socket_path.parent
            if create_development_parent:
                parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not parent.is_dir():
                raise RuntimeError("Runtime socket parent does not exist")
            if self._socket_path.exists() or self._socket_path.is_symlink():
                details = self._socket_path.lstat()
                if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.geteuid():
                    raise RuntimeError("refusing to replace an unexpected Runtime socket path")
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                probe.settimeout(0.2)
                try:
                    probe.connect(str(self._socket_path))
                except OSError as exc:
                    if exc.errno not in {errno.ECONNREFUSED, errno.ENOENT}:
                        raise RuntimeError("Runtime socket state cannot be verified") from exc
                    try:
                        current = self._socket_path.lstat()
                    except FileNotFoundError:
                        current = None
                    if current is not None:
                        if (
                            not stat.S_ISSOCK(current.st_mode)
                            or current.st_uid != os.geteuid()
                            or (current.st_dev, current.st_ino) != (details.st_dev, details.st_ino)
                        ):
                            raise RuntimeError(
                                "Runtime socket changed during stale-state check"
                            ) from exc
                        self._socket_path.unlink()
                else:
                    raise RuntimeError("Runtime socket already has an active server")
                finally:
                    probe.close()
            self._server = await asyncio.start_unix_server(
                self._accept_connection,
                path=self._socket_path,
                start_serving=False,
                limit=MAX_RUNTIME_FRAME + 1,
            )
            if self._closing or self._closed:
                raise RuntimeError("Runtime server is unavailable")
            configured_gid = os.environ.get("AGENTBOX_RUNTIME_SOCKET_GID")
            if configured_gid:
                try:
                    socket_gid = int(configured_gid)
                except ValueError as exc:
                    raise RuntimeError("AGENTBOX_RUNTIME_SOCKET_GID must be an integer") from exc
                if socket_gid not in os.getgroups() and socket_gid != os.getegid():
                    raise RuntimeError("Runtime socket group is not assigned to this process")
                os.chown(self._socket_path, -1, socket_gid)
            self._socket_path.chmod(0o660)
            await self._server.start_serving()
            if self._closing or self._closed:
                raise RuntimeError("Runtime server is unavailable")
            if self._waw_control_server is not None:
                await self._waw_control_server.start()
        except BaseException:
            await self._cleanup_failed_start()
            raise
        finally:
            if self._start_task is current_task:
                self._start_task = None

    def _reset_clean_nonfixed_restart(self) -> None:
        operation = self._close_operation
        if operation is None:
            return
        if (
            self._waw_fixed_runtime is not None
            or self._waw_control_server is not None
            or self._poisoned
            or not operation.done()
            or operation.cancelled()
            or operation.exception() is not None
            or self._server is not None
            or self._start_task is not None
            or self._connection_tasks
            or self._writers
        ):
            return
        self._close_operation = None
        self._closing = False
        self._closed = False

    async def _cleanup_failed_start(self) -> None:
        if self._closing:
            partial = self._take_runtime_server()
            if partial is not None:
                with contextlib.suppress(BaseException):
                    partial.close()
                with contextlib.suppress(BaseException):
                    await partial.wait_closed()
            return
        self._start_task = None
        with contextlib.suppress(BaseException):
            await self.close()

    def close(self) -> Coroutine[Any, Any, None]:
        """Start or join the one independently owned shutdown operation."""

        self._closing = True
        self._closed = True
        operation = self._close_operation
        if operation is None:
            operation = asyncio.create_task(self._perform_close())
            self._close_operation = operation
            operation.add_done_callback(self._consume_close_operation)
        return self._wait_for_close(operation)

    async def _wait_for_close(self, operation: asyncio.Task[None]) -> None:
        await asyncio.shield(operation)

    @staticmethod
    def _consume_close_operation(operation: asyncio.Task[Any]) -> None:
        with contextlib.suppress(BaseException):
            operation.result()

    async def _perform_close(self) -> None:
        failures: dict[int, BaseException] = {}

        def failed(stage: int, error: BaseException) -> None:
            if isinstance(error, asyncio.CancelledError):
                self._poisoned = True
                error = RuntimeError("Runtime shutdown was cancelled")
            failures.setdefault(stage, error)

        control_close: Coroutine[Any, Any, None] | None = None
        if self._waw_control_server is not None:
            try:
                # WAWControlServer.close synchronously marks the listener closed
                # before returning its independently owned cleanup awaitable.
                control_close = self._waw_control_server.close()
            except BaseException as exc:
                failed(0, exc)

        runtime_server = self._take_runtime_server()
        if runtime_server is not None:
            try:
                # asyncio.Server.close synchronously stops new admission.
                runtime_server.close()
            except BaseException as exc:
                failed(1, exc)

        lifecycle = None if self._waw_fixed_runtime is None else self._waw_fixed_runtime.registry
        if lifecycle is not None:
            try:
                await lifecycle.begin_shutdown()
            except BaseException as exc:
                failed(2, exc)

        authority = self._waw_peer_authority
        if authority is not None:
            try:
                authority.close()
            except BaseException as exc:
                failed(3, exc)

        start_task = self._start_task
        if start_task is not None and start_task is not asyncio.current_task():
            start_task.cancel()
            try:
                done, pending = await asyncio.wait(
                    {start_task}, timeout=_CONNECTION_SHUTDOWN_GRACE_SECONDS
                )
            except BaseException as exc:
                failed(4, exc)
                done, pending = set(), {start_task}
            if done:
                with contextlib.suppress(BaseException):
                    start_task.result()
            if pending:
                self._poisoned = True
                failed(4, RuntimeError("Runtime start shutdown timed out"))
                start_task.add_done_callback(self._consume_close_operation)
            late_server = self._take_runtime_server()
            if late_server is not None and late_server is not runtime_server:
                try:
                    late_server.close()
                except BaseException as exc:
                    failed(4, exc)
                try:
                    await late_server.wait_closed()
                except BaseException as exc:
                    failed(4, exc)

        if lifecycle is not None:
            try:
                await lifecycle.wait_shutdown_workers()
            except BaseException as exc:
                failed(4, exc)

        if control_close is not None:
            try:
                await control_close
            except BaseException as exc:
                failed(0, exc)
        if runtime_server is not None:
            try:
                await runtime_server.wait_closed()
            except BaseException as exc:
                failed(1, exc)

        for writer in tuple(self._writers):
            try:
                writer.close()
            except BaseException as exc:
                failed(5, exc)
        tasks = tuple(self._connection_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            try:
                done, pending = await asyncio.wait(
                    tasks,
                    timeout=_CONNECTION_SHUTDOWN_GRACE_SECONDS,
                )
            except BaseException as exc:
                failed(5, exc)
                done = {task for task in tasks if task.done()}
                pending = set(tasks) - done
            for task in done:
                self._connection_tasks.discard(task)
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except BaseException as exc:
                    failed(5, exc)
            if pending:
                self._poisoned = True
                failed(5, RuntimeError("Runtime connection shutdown timed out"))
                for task in pending:
                    task.add_done_callback(self._connection_done)

        try:
            details = self._socket_path.lstat()
            if stat.S_ISSOCK(details.st_mode) and details.st_uid == os.geteuid():
                self._socket_path.unlink()
        except FileNotFoundError:
            pass
        except BaseException as exc:
            failed(6, exc)

        self._closing = False
        if failures:
            raise failures[min(failures)]

    def _take_runtime_server(self) -> asyncio.AbstractServer | None:
        server, self._server = self._server, None
        return server

    def _accept_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if self._closing or self._closed:
            writer.close()
            return
        task = asyncio.create_task(self._handle(reader, writer))
        self._connection_tasks.add(task)
        self._writers.add(writer)
        task.add_done_callback(self._connection_done)

    def _connection_done(self, task: asyncio.Task[None]) -> None:
        self._connection_tasks.discard(task)
        with contextlib.suppress(BaseException):
            task.result()

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("Runtime server is not started")
        async with self._server:
            await self._server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_id: str | None = None
        try:
            if self._closing or self._closed:
                return
            if not self._peer_allowed(writer):
                await self._write_error(
                    writer, "RUNTIME_PEER_FORBIDDEN", "Runtime peer is forbidden"
                )
                return
            raw = await asyncio.wait_for(reader.readline(), timeout=self._read_timeout_seconds)
            if not raw or len(raw) > MAX_RUNTIME_FRAME or not raw.endswith(b"\n"):
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            request = strict_json_loads(raw)
            if (
                not isinstance(request, dict)
                or type(request.get("protocol_version")) is not int
                or request["protocol_version"] != RUNTIME_PROTOCOL_VERSION
                or not isinstance(request.get("action"), str)
                or request["action"] not in _ACTIONS
                or not isinstance(request.get("request_id"), str)
            ):
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            try:
                validate_request_id(request["request_id"])
            except RuntimeOperationError:
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            try:
                trailing = await asyncio.wait_for(
                    reader.read(1), timeout=self._trailing_timeout_seconds
                )
            except TimeoutError:
                trailing = b""
            if trailing:
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            action = request["action"]
            expected_keys = {"protocol_version", "action", "request_id"}
            if action == RUNTIME_CAPABILITY_ACTION:
                expected_keys = set(RuntimeCapabilityQuery.model_fields)
            if action in _CLAUDE_PROJECT_ACTIONS:
                expected_keys.add("project_id")
            expected_keys.update(_PROJECT_ACTION_KEYS.get(action, ()))
            if set(request) != expected_keys:
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            if action in _CLAUDE_PROJECT_ACTIONS:
                try:
                    raw_project_id = request.get("project_id")
                    if not isinstance(raw_project_id, str):
                        raise RuntimeOperationError(
                            "CLAUDE_PROJECT_INVALID",
                            "Project identifier is invalid",
                            category="validation",
                        )
                    validate_project_id(raw_project_id)
                except RuntimeOperationError:
                    await self._write_error(
                        writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                    )
                    return
            if action in _PROJECT_ACTION_KEYS:
                try:
                    self._validate_project_action(action, request)
                except RuntimeOperationError:
                    await self._write_error(
                        writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                    )
                    return
            request_id = request["request_id"]
            data = await self._dispatch(request)
            await self._write(
                writer,
                {
                    "protocol_version": 1,
                    "request_id": request_id,
                    "data": data,
                    "error": None,
                },
            )
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeError,
            ValueError,
            RecursionError,
        ):
            await self._write_error(
                writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
            )
        except RuntimeOperationError as exc:
            await self._write(
                writer,
                {
                    "protocol_version": 1,
                    "request_id": request_id,
                    "data": None,
                    "error": {
                        "code": exc.code,
                        "category": exc.category,
                        "message": exc.message,
                        "retryable": exc.retryable,
                        "retry_after": exc.retry_after,
                    },
                },
            )
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            self._writers.discard(writer)

    def _peer_allowed(self, writer: asyncio.StreamWriter) -> bool:
        transport_socket = writer.get_extra_info("socket")
        if transport_socket is None or not hasattr(socket, "SO_PEERCRED"):
            return False
        try:
            credentials = transport_socket.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
            _pid, uid, gid = struct.unpack("3i", credentials)
        except (OSError, struct.error):
            return False
        return uid in self._allowed_peer_uids and gid in self._allowed_peer_gids

    async def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        action = str(request["action"])
        if action == RUNTIME_CAPABILITY_ACTION:
            if self._capability_collector is None:
                raise RuntimeOperationError(
                    "RUNTIME_MANAGER_UNAVAILABLE",
                    "Runtime capability manager is unavailable",
                    category="unavailable",
                    retryable=True,
                )
            query = RuntimeCapabilityQuery.model_validate_json(
                json.dumps(request, separators=(",", ":"), ensure_ascii=False)
            )
            return (await self._capability_collector.collect(query)).model_dump(mode="json")
        if action == "codex.status":
            return (await self._manager.status()).to_dict()
        if action == "codex.remote.start":
            return (await self._manager.start_remote()).to_dict()
        if action == "codex.remote.stop":
            return (await self._manager.stop_remote()).to_dict()
        if action == "codex.pair":
            return (await self._manager.generate_pair_code()).to_dict()
        if action.startswith("claude.") and self._claude_manager is None:
            raise RuntimeOperationError(
                "CLAUDE_RUNTIME_UNAVAILABLE",
                "Claude Runtime manager is unavailable",
                category="unavailable",
            )
        if self._claude_manager is not None:
            if action == "claude.status":
                return (await self._claude_manager.status()).to_dict()
            if action == "claude.sessions.list":
                return {
                    "sessions": [
                        session.to_dict() for session in await self._claude_manager.list_sessions()
                    ]
                }
            project_id = str(request.get("project_id", ""))
            if action == "claude.session.status":
                return (await self._claude_manager.session(project_id)).to_dict()
            if action == "claude.session.start":
                return (await self._claude_manager.start(project_id)).to_dict()
            if action == "claude.session.stop":
                return (await self._claude_manager.stop(project_id)).to_dict()
            if action == "claude.session.output":
                return (await self._claude_manager.recent_output(project_id)).to_dict()
        if action in _PROJECT_ACTION_KEYS and self._project_manager is None:
            raise RuntimeOperationError(
                "PROJECT_RUNTIME_UNAVAILABLE",
                "Project Runtime manager is unavailable",
                category="unavailable",
            )
        if self._project_manager is not None:
            project_key = str(request.get("project_key", ""))
            operation_id = str(request.get("operation_id", ""))
            if action == "project.list":
                return {
                    "projects": [item.to_dict() for item in self._project_manager.list_workspaces()]
                }
            if action == "project.create":
                return (await self._project_manager.create(project_key, operation_id)).to_dict()
            if action == "project.clone":
                return (
                    await self._project_manager.clone(
                        project_key, operation_id, str(request["repository_url"])
                    )
                ).to_dict()
            if action == "project.finalize":
                return self._project_manager.finalize(project_key, operation_id).to_dict()
            if action == "project.rollback":
                return self._project_manager.rollback(project_key, operation_id).to_dict()
            if action == "git.status":
                return (await self._project_manager.git_status(project_key)).to_dict()
            if action == "git.global.status":
                return (await self._project_manager.git_global_status()).to_dict()
            if action == "git.branches.list":
                return {
                    "branches": [
                        branch.to_dict()
                        for branch in await self._project_manager.branches(project_key)
                    ]
                }
            if action == "git.branch.create":
                return (
                    await self._project_manager.create_branch(project_key, str(request["branch"]))
                ).to_dict()
            if action in {"git.branch.switch", "git.pull"}:
                await self._require_inactive_claude(project_key)
            if action == "git.branch.switch":
                return (
                    await self._project_manager.switch_branch(project_key, str(request["branch"]))
                ).to_dict()
            if action == "git.pull":
                return (await self._project_manager.pull(project_key)).to_dict()
            if action == "git.push":
                return (await self._project_manager.push(project_key)).to_dict()
            if action == "github.status":
                return (await self._project_manager.github_global_status()).to_dict()
            if action == "github.project.status":
                return (await self._project_manager.github_status(project_key)).to_dict()
            if action == "github.pr.create":
                return (
                    await self._project_manager.create_draft_pr(
                        project_key,
                        title=str(request["title"]),
                        body=str(request["body"]),
                        base=(str(request["base"]) if request["base"] is not None else None),
                    )
                ).to_dict()
        raise RuntimeOperationError(
            "RUNTIME_ACTION_UNSUPPORTED", "Runtime action is unsupported", category="unsupported"
        )

    async def _require_inactive_claude(self, project_key: str) -> None:
        if self._claude_manager is None:
            return
        session = await self._claude_manager.session(project_key)
        if session.tmux_running:
            raise RuntimeOperationError(
                "PROJECT_RUNTIME_ACTIVE",
                "Stop the managed Claude session before changing the workspace",
                category="conflict",
            )

    @staticmethod
    def _validate_project_action(action: str, request: dict[str, Any]) -> None:
        if "project_key" in _PROJECT_ACTION_KEYS[action]:
            value = request.get("project_key")
            if not isinstance(value, str):
                raise RuntimeOperationError("PROJECT_INPUT_INVALID", "Project input is invalid")
            validate_project_id(value)
        if "operation_id" in _PROJECT_ACTION_KEYS[action]:
            value = request.get("operation_id")
            if not isinstance(value, str):
                raise RuntimeOperationError(
                    "PROJECT_OPERATION_INVALID", "Project operation is invalid"
                )
            validate_operation_id(value)
        if action == "project.clone":
            value = request.get("repository_url")
            if not isinstance(value, str):
                raise RuntimeOperationError(
                    "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid"
                )
            validate_git_repository_url(value)
        if "branch" in _PROJECT_ACTION_KEYS[action]:
            value = request.get("branch")
            if not isinstance(value, str):
                raise RuntimeOperationError("GIT_BRANCH_INVALID", "Branch name is invalid")
            validate_branch_name(value)
        if action == "github.pr.create":
            title, body, base = request.get("title"), request.get("body"), request.get("base")
            if (
                not isinstance(title, str)
                or not isinstance(body, str)
                or not (base is None or isinstance(base, str))
            ):
                raise RuntimeOperationError(
                    "GITHUB_PR_INPUT_INVALID", "Pull request input is invalid"
                )
            validate_pr_title(title)
            validate_pr_body(body)
            if base is not None:
                validate_branch_name(base)

    async def _write_error(self, writer: asyncio.StreamWriter, code: str, message: str) -> None:
        await self._write(
            writer,
            {
                "protocol_version": 1,
                "request_id": None,
                "data": None,
                "error": {
                    "code": code,
                    "category": "forbidden" if code.endswith("FORBIDDEN") else "validation",
                    "message": message,
                    "retryable": False,
                    "retry_after": None,
                },
            },
        )

    async def _write(self, writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        # UTF-8 avoids the six-byte \uXXXX expansion for bounded Unicode pane
        # output. The payload cap leaves room for worst-case JSON quoting inside
        # the unchanged 64 KiB Runtime frame.
        encoded = (
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        )
        if len(encoded) > MAX_RUNTIME_FRAME:
            encoded = (
                b'{"protocol_version":1,"request_id":null,"data":null,'
                b'"error":{"code":"RUNTIME_RESPONSE_TOO_LARGE",'
                b'"category":"broken","message":"Runtime response exceeded its limit",'
                b'"retryable":false,"retry_after":null}}\n'
            )
        writer.write(encoded)
        await asyncio.wait_for(writer.drain(), timeout=self._write_timeout_seconds)


def build_runtime_server_from_filesystem_v2(
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
    executor_factory: Callable[[str, WAWVerifiedExecutionAuthority], WAWSupervisorExecutor],
    binding_digest_factory: BindingDigestFactory,
    project_manager: ProjectWorkspaceManager | None = None,
    capability_collector: RuntimeCapabilityCollector | None = None,
) -> RuntimeExecutorServer:
    """Build one R11 server from the sole filesystem-v2 epoch composition."""

    composition = create_waw_lifecycle_registry_from_filesystem_bundle(
        runtime_manifest_path=runtime_manifest_path,
        public_directory=public_directory,
        expected_runtime_gid=expected_runtime_gid,
        epoch_store=epoch_store,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
    )
    control_server = build_waw_control_server(
        sockets=activated_sockets,
        registry=composition.registry,
        expected_peer_uid=waw_control_peer_uid,
        expected_peer_gid=waw_control_peer_gid,
    )
    peer_authority = composition.registry.peer_authority
    if type(peer_authority) is not WAWPeerAuthority:
        raise RuntimeOperationError(
            "WAW_COMPOSITION_MISMATCH",
            "Control server did not retain the fixed Runtime peer authority",
            category="conflict",
        )
    with _CONTROL_SERVER_ISSUE_LOCK:
        _CONTROL_SERVER_ISSUES[control_server] = (
            composition,
            composition.runtime_epoch,
            peer_authority,
        )
    return RuntimeExecutorServer(
        socket_path,
        manager,
        allowed_peer_uids=allowed_peer_uids,
        allowed_peer_gids=allowed_peer_gids,
        claude_manager=claude_manager,
        project_manager=project_manager,
        capability_collector=capability_collector,
        waw_control_server=control_server,
        enable_waw_fixed_process=True,
        formal_project_id_for_legacy=formal_project_id_for_legacy,
        waw_fixed_runtime=composition,
    )


async def _main() -> None:
    environment = os.environ.get("AGENTBOX_ENV", "development")
    if environment not in {"development", "test", "production"}:
        raise RuntimeError("AGENTBOX_ENV must be development, test, or production")
    socket_path = Path(os.environ.get("AGENTBOX_RUNTIME_SOCKET", ".agentbox-dev/runtime.sock"))
    if environment == "production" and (
        not socket_path.is_absolute() or socket_path.parent != Path("/run/agentbox")
    ):
        raise RuntimeError("production Runtime socket must be beneath /run/agentbox")
    configured_uids = os.environ.get("AGENTBOX_RUNTIME_ALLOWED_UIDS")
    configured_gids = os.environ.get("AGENTBOX_RUNTIME_ALLOWED_GIDS")
    if environment == "production" and (not configured_uids or not configured_gids):
        raise RuntimeError("Runtime peer UID and GID allowlists are required in production")
    allowed = (
        frozenset(int(value) for value in configured_uids.split(","))
        if configured_uids
        else frozenset({os.geteuid()})
    )
    allowed_gids = (
        frozenset(int(value) for value in configured_gids.split(","))
        if configured_gids
        else frozenset({os.getegid()})
    )
    try:
        pair_cooldown = int(os.environ.get("AGENTBOX_CODEX_PAIR_COOLDOWN", "10"))
    except ValueError as exc:
        raise RuntimeError("AGENTBOX_CODEX_PAIR_COOLDOWN must be an integer") from exc
    if not 5 <= pair_cooldown <= 300:
        raise RuntimeError("AGENTBOX_CODEX_PAIR_COOLDOWN must be between 5 and 300 seconds")
    project_registry = ProjectRegistry(
        Path(
            os.environ.get(
                "AGENTBOX_PROJECT_ROOT",
                (
                    "/srv/agentbox/projects"
                    if environment == "production"
                    else ".agentbox-dev/projects"
                ),
            )
        )
    )
    git = GitAdapter()
    github = GitHubAdapter(git)
    claude_manager = ClaudeSessionManager(ClaudeAdapter(), TmuxAdapter(), project_registry)
    codex_manager = CodexManager(CodexAdapter(), pair_cooldown_seconds=pair_cooldown)
    server = RuntimeExecutorServer(
        socket_path,
        codex_manager,
        allowed_peer_uids=allowed,
        allowed_peer_gids=allowed_gids,
        claude_manager=claude_manager,
        project_manager=ProjectWorkspaceManager(project_registry, git, github),
        capability_collector=RuntimeCapabilityCollector(codex_manager, claude_manager),
    )
    await server.start(create_development_parent=environment != "production")
    try:
        await server.serve_forever()
    finally:
        await server.close()


def main() -> None:
    asyncio.run(_main())


__all__ = [
    "RuntimeExecutorServer",
    "build_runtime_server_from_filesystem_v2",
    "main",
]
