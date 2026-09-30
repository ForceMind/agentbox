"""Fixed filesystem-v2 Runtime startup; no caller-supplied resource paths."""

from __future__ import annotations

import asyncio
import concurrent.futures
import grp
import os
import pwd
import signal
import threading
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import TypeVar

from agentbox_runtime.capabilities import RuntimeCapabilityCollector
from agentbox_runtime.claude import ClaudeSessionManager
from agentbox_runtime.codex import CodexManager
from agentbox_runtime.models import ClaudeSessionState, RemoteState
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_activation import load_waw_activated_sockets
from agentbox_runtime.waw_conflicts import (
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_application import (
    WAWRuntimeApplication,
    build_waw_runtime_application_from_filesystem_v2,
)
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.waw_runtime_profile import (
    WAWRuntimeMode,
    WAWRuntimeProfileObservation,
    revalidate_waw_runtime_profile,
)
from agentbox_runtime.waw_runtime_provider import build_waw_deferred_production_executor_provider
from agentbox_runtime.waw_static_key import _open_waw_runtime_static_key
from agentbox_runtime.waw_vendor_enrollment import load_waw_vendor_enrollment
from agentbox_runtime.workspace import ProjectWorkspaceManager

_T = TypeVar("_T")


class _ProductionConflictProbe:
    """Bridge worker-thread start decisions to fresh, bounded legacy observations."""

    def __init__(self, codex: CodexManager, claude: ClaudeSessionManager) -> None:
        self._loop = asyncio.get_running_loop()
        self._loop_thread = threading.get_ident()
        self._codex = codex
        self._claude = claude
        self._executor: WAWSupervisorExecutor | None = None

    def bind(self, executor: WAWSupervisorExecutor) -> None:
        if self._executor is not None:
            raise RuntimeError("production conflict executor is already bound")
        self._executor = executor

    def formal_project_id_for_legacy(self, key: str) -> str | None:
        executor = self._executor
        return None if executor is None else executor.formal_project_id_for_legacy(key)

    def _observe(self, operation: Coroutine[object, object, _T]) -> _T:
        # A synchronous wait on the event-loop thread would deadlock admission.
        if threading.get_ident() == self._loop_thread or self._loop.is_closed():
            operation.close()
            raise RuntimeError("legacy observation requires the start worker")
        future = asyncio.run_coroutine_threadsafe(operation, self._loop)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise RuntimeError("legacy conflict observation timed out") from None

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        executor = self._executor
        if executor is None:
            return WAWLegacyClaudeState.UNKNOWN
        key = executor.relative_key_for_formal_project(project_id)
        if key is None:
            return WAWLegacyClaudeState.UNKNOWN
        observed = self._observe(self._claude.session(key))
        # Recheck the formal binding after the asynchronous observation.
        if executor.relative_key_for_formal_project(project_id) != key:
            return WAWLegacyClaudeState.UNKNOWN
        return {
            ClaudeSessionState.RUNNING: WAWLegacyClaudeState.RUNNING,
            ClaudeSessionState.STOPPED: WAWLegacyClaudeState.STOPPED,
            ClaudeSessionState.STARTING: WAWLegacyClaudeState.STARTING,
            ClaudeSessionState.NEEDS_INTERACTION: WAWLegacyClaudeState.NEEDS_INTERACTION,
            ClaudeSessionState.BROKEN: WAWLegacyClaudeState.BROKEN,
        }.get(observed.state, WAWLegacyClaudeState.UNKNOWN)

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        observed = self._observe(self._codex.status())
        # Process absence, CLI installation absence and unsupported status are
        # not positive host-global STOPPED evidence.
        if (
            observed.remote_state is RemoteState.STOPPED
            and observed.remote_confidence == "reported"
        ):
            return WAWLegacyCodexState.STOPPED
        if observed.remote_state is RemoteState.RUNNING:
            return WAWLegacyCodexState.RUNNING
        if observed.remote_state is RemoteState.BROKEN:
            return WAWLegacyCodexState.BROKEN
        return WAWLegacyCodexState.UNKNOWN

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        executor = self._executor
        return (
            (WAWManagedConflictState.UNKNOWN,)
            if executor is None
            else executor.managed_conflict_states(project_id)
        )

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        executor = self._executor
        return (
            (WAWManagedConflictState.UNKNOWN,)
            if executor is None
            else executor.managed_conflict_states()
        )


async def _serve_application(application: WAWRuntimeApplication) -> None:
    """Handle systemd SIGTERM through the application's exact cleanup owner."""

    loop = asyncio.get_running_loop()
    stopped = asyncio.Event()
    installed: list[signal.Signals] = []
    serving: asyncio.Task[None] | None = None
    stop_wait: asyncio.Task[bool] | None = None
    try:
        for number in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(number, stopped.set)
            installed.append(number)
        await application.start()
        serving = asyncio.create_task(application.serve_forever())
        stop_wait = asyncio.create_task(stopped.wait())
        done, _pending = await asyncio.wait(
            {serving, stop_wait}, return_when=asyncio.FIRST_COMPLETED
        )
        if serving in done:
            await serving
    finally:
        try:
            await application.close()
        finally:
            for task in (serving, stop_wait):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(task for task in (serving, stop_wait) if task is not None),
                return_exceptions=True,
            )
            for number in installed:
                loop.remove_signal_handler(number)


async def run_waw_production(
    *,
    socket_path: Path,
    codex_manager: CodexManager,
    claude_manager: ClaudeSessionManager,
    projects: ProjectRegistry,
    project_manager: ProjectWorkspaceManager,
    allowed_uids: frozenset[int],
    allowed_gids: frozenset[int],
    profile: WAWRuntimeProfileObservation,
) -> None:
    if profile.mode is not WAWRuntimeMode.FILESYSTEM_V2:
        raise RuntimeError("filesystem-v2 Runtime profile is required")
    runtime = pwd.getpwnam("agentbox-runtime")
    runtime_gid = grp.getgrnam("agentbox-runtime").gr_gid
    control = pwd.getpwnam("agentbox")
    control_gid = grp.getgrnam("agentbox").gr_gid
    ipc_gid = grp.getgrnam("agentbox-runtime-ipc").gr_gid
    if (
        runtime.pw_uid == 0
        or runtime_gid == 0
        or runtime.pw_gid != runtime_gid
        or control.pw_uid == 0
        or control_gid == 0
        or control.pw_gid != control_gid
        or ipc_gid == 0
        or allowed_uids != frozenset({control.pw_uid})
        or allowed_gids != frozenset({control_gid})
        or os.getresuid() != (runtime.pw_uid,) * 3
        or os.getresgid() != (runtime_gid,) * 3
    ):
        raise RuntimeError("WAW production process or Control Plane identity is invalid")
    revalidate_waw_runtime_profile(profile)
    probe = _ProductionConflictProbe(codex_manager, claude_manager)
    provider = build_waw_deferred_production_executor_provider(
        project_registry=projects,
        enrollment=load_waw_vendor_enrollment(),
        conflict_probe=probe,
        geometry=PtyGeometry(columns=80, rows=24),
        clock=time.monotonic,
        # Production permits RuntimeAttachmentLease only; the encrypted
        # registry supplies its own current() guard, not API ActiveAttachment.
        attachment_validator=lambda _attachment: False,
    )
    try:
        key = _open_waw_runtime_static_key()
    except BaseException:
        provider.close()
        raise
    try:
        sockets = load_waw_activated_sockets(expected_uid=runtime.pw_uid, expected_gid=ipc_gid)
    except BaseException:
        key.close()
        provider.close()
        raise
    try:
        application = await build_waw_runtime_application_from_filesystem_v2(
            socket_path=socket_path,
            manager=codex_manager,
            claude_manager=claude_manager,
            allowed_peer_uids=allowed_uids,
            allowed_peer_gids=allowed_gids,
            formal_project_id_for_legacy=probe.formal_project_id_for_legacy,
            activated_sockets=sockets,
            waw_control_peer_uid=control.pw_uid,
            waw_control_peer_gid=control_gid,
            runtime_manifest_path=Path("/var/lib/agentbox-waw/runtime-host-installation.v2.json"),
            public_directory=Path("/usr/share/agentbox/waw"),
            expected_runtime_gid=runtime_gid,
            epoch_store=WAWRuntimeEpochStore(
                Path("/var/lib/agentbox-waw/runtime-epoch-v1"),
                expected_uid=runtime.pw_uid,
                expected_gid=runtime_gid,
            ),
            executor_provider=provider,
            key_port=key,
            clock=time.monotonic,
            project_manager=project_manager,
            capability_collector=RuntimeCapabilityCollector(codex_manager, claude_manager),
        )
    except BaseException:
        # Transferred handles are inert; the builder owns partial cleanup.
        sockets.close()
        key.close()
        provider.close()
        raise
    try:
        probe.bind(application.executor)
        revalidate_waw_runtime_profile(profile)
        await _serve_application(application)
    finally:
        await application.close()
