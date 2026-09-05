from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType
from agentbox_runtime import server as server_subject
from agentbox_runtime import waw_peer_authority as peer_authority_subject
from agentbox_runtime.claude import ClaudeAdapter, ClaudeSessionManager
from agentbox_runtime.codex import CodexAdapter, CodexManager
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.server import (
    _ACTIONS,
    RuntimeExecutorServer,
    build_runtime_server_from_filesystem_v2,
)
from agentbox_runtime.tmux import TmuxAdapter
from agentbox_runtime.waw_auth_probe import (
    WAWCachedPublicAuthProbe,
    WAWPublicAuthProbeCache,
    WAWVendorPublicAuthBinding,
)
from agentbox_runtime.waw_bootstrap import WAWFixedRuntimeComposition
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWConflictError,
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)
from agentbox_runtime.waw_control_server import WAWControlServer
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_fixed_transport import WAWVerifiedExecutionAuthority
from agentbox_runtime.waw_peer_authority import (
    WAWPeerAuthority,
    WAWPeerBindStatus,
    WAWPeerCandidate,
)
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.waw_vendor_probe import (
    WAWIsolatedProbeCompletion,
    WAWProcessIsolationKind,
    WAWProcessIsolationPort,
    WAWVendorProbeFailure,
    WAWVendorProbeId,
    WAWVendorProbeParserId,
    WAWVendorProbeProfile,
    WAWVendorProbeRunner,
    waw_vendor_probe_output_digest,
)

FORMAL_PROJECT = "prj_" + "1" * 32


class _Providers:
    def __init__(self) -> None:
        self.claude = WAWLegacyClaudeState.ABSENT
        self.codex = WAWLegacyCodexState.ABSENT
        self.project_waw: tuple[WAWManagedConflictState, ...] = ()
        self.host_waw: tuple[WAWManagedConflictState, ...] = ()
        self.calls: list[str] = []

    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        assert project_id == FORMAL_PROJECT
        self.calls.append("claude")
        return self.claude

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        self.calls.append("codex")
        return self.codex

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        assert project_id == FORMAL_PROJECT
        self.calls.append("waw-project")
        return self.project_waw

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        self.calls.append("waw-host")
        return self.host_waw

    @staticmethod
    def formal_project_id(relative_key: str) -> str:
        if relative_key != "project-a":
            raise KeyError(relative_key)
        return FORMAL_PROJECT


class _QualifiedPort(WAWProcessIsolationPort):
    def __init__(self) -> None:
        super().__init__(
            isolation_kind=WAWProcessIsolationKind.PREBIRTH_CGROUP,
            production_qualified=True,
        )
        self.calls = 0

    async def execute(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> WAWIsolatedProbeCompletion:
        del profile, arguments, timeout_seconds, output_limit, terminate_grace_seconds
        self.calls += 1
        return WAWIsolatedProbeCompletion(
            0,
            b"",
            b"",
            WAWVendorProbeFailure.NONE,
            self.cleanup_proof(leader_reaped=True, descendants_remaining=0),
        )


def _managers(tmp_path: Path) -> tuple[CodexManager, ClaudeSessionManager]:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    (project_root / "project-a").mkdir()
    environment = {"HOME": str(tmp_path), "PATH": str(tmp_path / "empty")}
    codex = CodexManager(CodexAdapter(environment=environment))
    claude = ClaudeSessionManager(
        ClaudeAdapter(environment=environment),
        TmuxAdapter(environment=environment),
        ProjectRegistry(project_root),
    )
    return codex, claude


def _fixed_server(
    tmp_path: Path,
    providers: _Providers,
    *,
    runner: WAWVendorProbeRunner | None = None,
    bindings: dict[AgentType, WAWVendorPublicAuthBinding] | None = None,
) -> tuple[RuntimeExecutorServer, CodexManager, ClaudeSessionManager]:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
        enable_waw_fixed_process=True,
        legacy_claude=providers.legacy_claude,
        legacy_codex_remote=providers.legacy_codex_remote,
        waw_for_project=providers.waw_for_project,
        waw_for_host=providers.waw_for_host,
        formal_project_id_for_legacy=providers.formal_project_id,
        waw_vendor_probe_runner=runner,
        waw_vendor_auth_bindings=bindings,
    )
    return server, codex, claude


def _composition(tmp_path: Path, epoch: str = "2") -> WAWFixedRuntimeComposition:
    projects = tmp_path / f"composition-projects-{epoch}"
    projects.mkdir(exist_ok=True)
    providers = _Providers()
    coordinator = WAWConflictCoordinator(providers)
    auth = object.__new__(WAWCachedPublicAuthProbe)
    auth._cache = WAWPublicAuthProbeCache()
    authority = object.__new__(WAWVerifiedExecutionAuthority)

    def unused(*_args: Any) -> Any:
        raise AssertionError("server composition test must not start a process")

    executor = WAWSupervisorExecutor(
        runtime_epoch=epoch,
        project_registry=ProjectRegistry(projects),
        command_factory=unused,
        transport_factory=unused,
        geometry=PtyGeometry(80, 24),
        clock=lambda: 0.0,
        attachment_validator=lambda _attachment: True,
        conflict_coordinator=coordinator,
        execution_authority=authority,
        auth_probe=auth,
    )

    class Registry:
        def __init__(self) -> None:
            self.peer_authority = WAWPeerAuthority(
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )

        async def begin_shutdown(self) -> None:
            return None

        async def wait_shutdown_workers(self) -> None:
            return None

    return WAWFixedRuntimeComposition(cast(Any, Registry()), executor, epoch, authority)


def _epoch_store(tmp_path: Path) -> WAWRuntimeEpochStore:
    directory = tmp_path / "server-epoch"
    directory.mkdir(mode=0o700)
    store = WAWRuntimeEpochStore(directory, expected_uid=os.geteuid(), expected_gid=os.getegid())
    assert store.bootstrap() == 1
    return store


def _issued_control(composition: WAWFixedRuntimeComposition) -> WAWControlServer:
    control = object.__new__(WAWControlServer)
    peer_authority = composition.registry.peer_authority
    assert type(peer_authority) is WAWPeerAuthority
    with server_subject._CONTROL_SERVER_ISSUE_LOCK:
        server_subject._CONTROL_SERVER_ISSUES[control] = (
            composition,
            composition.runtime_epoch,
            peer_authority,
        )
    return control


def test_legacy_only_server_keeps_fixed_process_inert(tmp_path: Path) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )

    assert server.waw_conflict_coordinator is None
    assert server.waw_public_auth_probe is None
    assert server.waw_auth_probe_cache is None
    assert codex.conflict_coordinator is None
    assert claude.conflict_coordinator is None


@pytest.mark.anyio
async def test_clean_nonfixed_restart_reuses_consumed_epoch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex, claude = _managers(tmp_path)
    calls = 0

    class EpochStore:
        def consume(self) -> int:
            nonlocal calls
            calls += 1
            return 7

    class RuntimeServer:
        def __init__(self, path: Path) -> None:
            self.path = path

        async def start_serving(self) -> None:
            return None

        def close(self) -> None:
            self.path.unlink(missing_ok=True)

        async def wait_closed(self) -> None:
            return None

    async def create_server(*_args: Any, path: Path, **_kwargs: Any) -> Any:
        Path(path).touch()
        return RuntimeServer(Path(path))

    monkeypatch.setattr(asyncio, "start_unix_server", create_server)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
        waw_epoch_store=cast(Any, EpochStore()),
    )
    await server.start()
    await server.close()
    await server.start()
    assert server.waw_runtime_epoch == 7 and calls == 1
    await server.close()


@pytest.mark.anyio
async def test_close_is_shared_and_caller_cancellation_does_not_cancel_cleanup(
    tmp_path: Path,
) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    class Control:
        def close(self) -> Any:
            nonlocal calls
            calls += 1
            entered.set()

            async def finish() -> None:
                await release.wait()

            return finish()

    server._waw_control_server = cast(Any, Control())
    first = asyncio.create_task(server.close())
    await entered.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert server._close_operation is not None and not server._close_operation.done()

    release.set()
    await server.close()
    await server.close()
    assert calls == 1
    with pytest.raises(RuntimeError, match="unavailable"):
        await server.start()


@pytest.mark.anyio
async def test_close_during_start_owns_and_closes_late_listener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    entered, release = asyncio.Event(), asyncio.Event()
    events: list[str] = []

    class LateServer:
        def close(self) -> None:
            events.append("close")

        async def wait_closed(self) -> None:
            events.append("wait")

        async def start_serving(self) -> None:
            raise AssertionError("closed start must not serve")

    async def delayed_start(*_args: Any, **_kwargs: Any) -> Any:
        entered.set()
        await release.wait()
        return LateServer()

    monkeypatch.setattr(asyncio, "start_unix_server", delayed_start)
    start = asyncio.create_task(server.start())
    await entered.wait()
    closing = server.close()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await start
    await closing

    assert events == []
    assert server._server is None
    assert server._close_operation is not None and server._close_operation.done()


@pytest.mark.anyio
@pytest.mark.parametrize("cancel_stage", ["listener", "control"])
async def test_start_cancellation_cleans_partial_listener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cancel_stage: str,
) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    entered = asyncio.Event()
    events: list[str] = []

    class PartialServer:
        def close(self) -> None:
            events.append("listener-close")

        async def wait_closed(self) -> None:
            events.append("listener-wait")

        async def start_serving(self) -> None:
            if cancel_stage == "listener":
                entered.set()
                await asyncio.Event().wait()

    class Control:
        async def start(self) -> None:
            entered.set()
            await asyncio.Event().wait()

        def close(self) -> Any:
            async def finish() -> None:
                events.append("control-close")

            return finish()

    async def create_server(*_args: Any, path: Path, **_kwargs: Any) -> Any:
        Path(path).touch()
        return PartialServer()

    monkeypatch.setattr(asyncio, "start_unix_server", create_server)
    if cancel_stage == "control":
        server._waw_control_server = cast(Any, Control())
    start = asyncio.create_task(server.start())
    await entered.wait()
    start.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start
    assert server._server is None
    assert events.count("listener-close") == 1
    assert events.count("listener-wait") == 1


@pytest.mark.anyio
async def test_close_cancels_waiting_connection_worker(tmp_path: Path) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    entered = asyncio.Event()

    async def worker() -> None:
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(worker())
    server._connection_tasks.add(task)
    await entered.wait()
    await server.close()
    assert task.cancelled() and not server._connection_tasks


@pytest.mark.anyio
async def test_cancellation_resistant_connection_poison_is_bounded_and_sticky(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_subject, "_CONNECTION_SHUTDOWN_GRACE_SECONDS", 0.001)
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def worker() -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue

    task = asyncio.create_task(worker())
    server._connection_tasks.add(task)
    await entered.wait()
    try:
        with pytest.raises(RuntimeError, match="timed out") as first:
            await server.close()
        await cancelled.wait()
        assert server._poisoned and not task.done()
        with pytest.raises(RuntimeError) as repeated:
            await server.close()
        assert repeated.value is first.value
    finally:
        release.set()
        await task


@pytest.mark.anyio
async def test_direct_close_operation_cancellation_becomes_sticky_failure(tmp_path: Path) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    entered, release = asyncio.Event(), asyncio.Event()

    class Control:
        def close(self) -> Any:
            async def finish() -> None:
                entered.set()
                await release.wait()

            return finish()

    server._waw_control_server = cast(Any, Control())
    waiting = asyncio.create_task(server.close())
    await entered.wait()
    assert server._close_operation is not None
    server._close_operation.cancel()
    release.set()
    with pytest.raises(RuntimeError, match="cancelled") as first:
        await waiting
    assert server._poisoned
    with pytest.raises(RuntimeError) as repeated:
        await server.close()
    assert repeated.value is first.value


@pytest.mark.anyio
async def test_close_preserves_first_error_but_completes_later_stages(tmp_path: Path) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    events: list[str] = []
    first_error = RuntimeError("synthetic-control-close-failure")
    worker_release = asyncio.Event()

    class Control:
        def close(self) -> Any:
            events.append("control")

            async def finish() -> None:
                raise first_error

            return finish()

    class RuntimeServer:
        def close(self) -> None:
            events.append("runtime-close")

        async def wait_closed(self) -> None:
            events.append("runtime-wait")

    class Authority:
        def close(self) -> None:
            events.append("authority")
            worker_release.set()

    class Lifecycle:
        async def begin_shutdown(self) -> None:
            events.append("lifecycle-begin")

        async def wait_shutdown_workers(self) -> None:
            events.append("lifecycle-wait")

    class FixedRuntime:
        registry = Lifecycle()

    class Writer:
        def close(self) -> None:
            events.append("writer")

    async def worker() -> None:
        await worker_release.wait()
        events.append("worker")

    task = asyncio.create_task(worker())
    server._waw_control_server = cast(Any, Control())
    server._server = cast(Any, RuntimeServer())
    server._waw_fixed_runtime = cast(Any, FixedRuntime())
    server._waw_peer_authority = cast(Any, Authority())
    server._writers.add(cast(Any, Writer()))
    server._connection_tasks.add(task)

    with pytest.raises(RuntimeError) as raised:
        await server.close()
    assert raised.value is first_error
    assert events == [
        "control",
        "runtime-close",
        "lifecycle-begin",
        "authority",
        "lifecycle-wait",
        "runtime-wait",
        "writer",
    ]
    with pytest.raises(RuntimeError) as repeated:
        await server.close()
    assert repeated.value is first_error


@pytest.mark.anyio
async def test_close_invalidates_runtime_peer_and_closes_retained_pidfd_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex, claude = _managers(tmp_path)
    server = RuntimeExecutorServer(
        tmp_path / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
    )
    authority = WAWPeerAuthority(expected_uid=os.geteuid(), expected_gid=os.getegid())
    read_fd, write_fd = os.pipe()
    candidate = authority.observe_control(101, os.geteuid(), os.getegid(), read_fd)
    assert type(candidate) is WAWPeerCandidate
    plan = authority.prepare_bind(
        candidate,
        api_authority_epoch="9",
        nonce_digest=b"a" * 32,
    )
    assert authority.commit_bind(plan) is WAWPeerBindStatus.BOUND
    lease = authority.borrow()
    assert lease is not None
    runtime_peer = lease.runtime_peer
    lease.close()
    retained = authority._current
    assert retained is not None
    retained_pidfd = retained.pidfd
    close_calls = 0
    original_close = authority.close

    def counted_close() -> None:
        nonlocal close_calls
        close_calls += 1
        original_close()

    monkeypatch.setattr(authority, "close", counted_close)
    monkeypatch.setattr(peer_authority_subject, "_pidfd_current", lambda _fd: True)
    server._waw_peer_authority = authority
    try:
        assert runtime_peer.current()
        await server.close()
        assert not runtime_peer.current()
        with pytest.raises(OSError):
            os.fstat(retained_pidfd)
        await server.close()
        assert close_calls == 1
    finally:
        original_close()
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.anyio
async def test_server_uses_preconsumed_composition_without_second_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _epoch_store(tmp_path)
    assert store.consume() == 2
    composition = _composition(tmp_path)
    manager_root = tmp_path / "server"
    manager_root.mkdir()
    codex, claude = _managers(manager_root)
    socket_root = Path(tempfile.mkdtemp(prefix="ab-s-", dir="/tmp"))

    class FakeAsyncServer:
        async def start_serving(self) -> None:
            return None

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    async def fake_start_unix_server(*_args: Any, path: Path, **_kwargs: Any) -> Any:
        Path(path).write_bytes(b"")
        return FakeAsyncServer()

    async def no_control_effect(_self: WAWControlServer) -> None:
        return None

    monkeypatch.setattr(asyncio, "start_unix_server", fake_start_unix_server)
    monkeypatch.setattr(WAWControlServer, "start", no_control_effect)
    monkeypatch.setattr(WAWControlServer, "close", no_control_effect)
    server = RuntimeExecutorServer(
        socket_root / "runtime.sock",
        codex,
        allowed_peer_uids=frozenset({os.geteuid()}),
        claude_manager=claude,
        enable_waw_fixed_process=True,
        formal_project_id_for_legacy=_Providers.formal_project_id,
        waw_control_server=_issued_control(composition),
        waw_fixed_runtime=composition,
    )
    try:
        await server.start(create_development_parent=True)
        await server.close()
    finally:
        shutil.rmtree(socket_root, ignore_errors=True)
    assert server.waw_runtime_epoch == 2
    assert store.consume() == 3


def test_server_rejects_epoch_store_or_mismatched_composition_before_effects(
    tmp_path: Path,
) -> None:
    composition = _composition(tmp_path)
    store = _epoch_store(tmp_path)
    mutual_root = tmp_path / "mutual"
    mutual_root.mkdir()
    codex, claude = _managers(mutual_root)
    with pytest.raises(ValueError, match="mutually exclusive"):
        RuntimeExecutorServer(
            tmp_path / "never-created.sock",
            codex,
            allowed_peer_uids=frozenset({os.geteuid()}),
            claude_manager=claude,
            enable_waw_fixed_process=True,
            formal_project_id_for_legacy=_Providers.formal_project_id,
            waw_control_server=_issued_control(composition),
            waw_fixed_runtime=composition,
            waw_epoch_store=store,
        )
    assert codex.conflict_coordinator is None
    assert claude.conflict_coordinator is None
    assert not (tmp_path / "never-created.sock").exists()
    assert store.consume() == 2

    mismatch_root = tmp_path / "mismatch"
    mismatch_root.mkdir()
    codex, claude = _managers(mismatch_root)
    mismatched = replace(composition, runtime_epoch="3")
    with pytest.raises(RuntimeOperationError, match="composition"):
        RuntimeExecutorServer(
            tmp_path / "also-never.sock",
            codex,
            allowed_peer_uids=frozenset({os.geteuid()}),
            claude_manager=claude,
            enable_waw_fixed_process=True,
            formal_project_id_for_legacy=_Providers.formal_project_id,
            waw_control_server=_issued_control(mismatched),
            waw_fixed_runtime=mismatched,
        )
    assert codex.conflict_coordinator is None
    assert claude.conflict_coordinator is None
    assert not (tmp_path / "also-never.sock").exists()


def test_server_rejects_unissued_or_wrong_composition_control_before_effects(
    tmp_path: Path,
) -> None:
    composition = _composition(tmp_path)
    for index, control in enumerate(
        (
            object.__new__(WAWControlServer),
            _issued_control(replace(composition, runtime_epoch="3")),
        )
    ):
        manager_root = tmp_path / f"control-{index}"
        manager_root.mkdir()
        codex, claude = _managers(manager_root)
        socket_path = tmp_path / f"control-{index}.sock"
        with pytest.raises(RuntimeOperationError, match="composition"):
            RuntimeExecutorServer(
                socket_path,
                codex,
                allowed_peer_uids=frozenset({os.geteuid()}),
                claude_manager=claude,
                enable_waw_fixed_process=True,
                formal_project_id_for_legacy=_Providers.formal_project_id,
                waw_control_server=control,
                waw_fixed_runtime=composition,
            )
        assert codex.conflict_coordinator is None
        assert claude.conflict_coordinator is None
        assert not socket_path.exists()


def test_filesystem_v2_builder_retains_the_only_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    composition = _composition(tmp_path)
    monkeypatch.setattr(
        "agentbox_runtime.server.create_waw_lifecycle_registry_from_filesystem_bundle",
        lambda **_kwargs: composition,
    )
    control = object.__new__(WAWControlServer)
    control_arguments: dict[str, Any] = {}

    def build_control(**kwargs: Any) -> WAWControlServer:
        control_arguments.update(kwargs)
        return control

    monkeypatch.setattr(server_subject, "build_waw_control_server", build_control)
    manager_root = tmp_path / "builder"
    manager_root.mkdir()
    codex, claude = _managers(manager_root)

    server = build_runtime_server_from_filesystem_v2(
        socket_path=tmp_path / "builder.sock",
        manager=codex,
        claude_manager=claude,
        allowed_peer_uids=frozenset({os.geteuid()}),
        allowed_peer_gids=frozenset({os.getegid()}),
        formal_project_id_for_legacy=_Providers.formal_project_id,
        activated_sockets=cast(Any, object()),
        waw_control_peer_uid=os.geteuid(),
        waw_control_peer_gid=os.getegid(),
        runtime_manifest_path=tmp_path / "runtime-v2",
        public_directory=tmp_path / "public-v2",
        expected_runtime_gid=os.getegid(),
        epoch_store=_epoch_store(tmp_path),
        executor_factory=cast(Any, object()),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert server.waw_fixed_runtime is composition
    assert server.waw_runtime_epoch == 2
    assert server.waw_peer_authority is composition.registry.peer_authority
    assert control_arguments["registry"] is composition.registry


def test_local_login_and_trust_are_not_runtime_rpc_actions() -> None:
    assert not any("login" in action or "trust" in action for action in _ACTIONS)


def test_fixed_process_mode_rejects_partial_conflict_configuration(tmp_path: Path) -> None:
    codex, claude = _managers(tmp_path)
    providers = _Providers()
    with pytest.raises(ValueError, match="all conflict providers"):
        RuntimeExecutorServer(
            tmp_path / "runtime.sock",
            codex,
            allowed_peer_uids=frozenset({os.geteuid()}),
            claude_manager=claude,
            enable_waw_fixed_process=True,
            legacy_claude=providers.legacy_claude,
            legacy_codex_remote=providers.legacy_codex_remote,
            waw_for_project=providers.waw_for_project,
            waw_for_host=providers.waw_for_host,
        )
    assert codex.conflict_coordinator is None
    assert claude.conflict_coordinator is None


def test_fixed_process_server_binds_one_coordinator_to_both_managers(tmp_path: Path) -> None:
    providers = _Providers()
    server, codex, claude = _fixed_server(tmp_path, providers)

    assert server.waw_conflict_coordinator is not None
    assert codex.conflict_coordinator is server.waw_conflict_coordinator
    assert claude.conflict_coordinator is server.waw_conflict_coordinator
    assert server.waw_public_auth_probe is None
    assert server.waw_auth_probe_cache is not None


@pytest.mark.anyio
async def test_bound_waw_rows_reverse_block_both_legacy_start_paths(tmp_path: Path) -> None:
    providers = _Providers()
    providers.project_waw = (WAWManagedConflictState.LOGIN_REQUIRED,)
    providers.host_waw = (WAWManagedConflictState.RUNNING,)
    _server, codex, claude = _fixed_server(tmp_path, providers)

    with pytest.raises(RuntimeOperationError) as claude_error:
        await claude.start("project-a")
    with pytest.raises(RuntimeOperationError) as codex_error:
        await codex.start_remote()

    assert claude_error.value.code == "PROJECT_RUNTIME_ACTIVE"
    assert codex_error.value.code == "CODEX_REMOTE_CONFLICT"
    assert providers.calls == ["waw-project", "waw-host"]


def test_shared_coordinator_keeps_claude_precedence_and_fail_closed(tmp_path: Path) -> None:
    providers = _Providers()
    providers.claude = WAWLegacyClaudeState.UNKNOWN
    providers.codex = WAWLegacyCodexState.RUNNING
    server, _codex, _claude = _fixed_server(tmp_path, providers)
    coordinator = server.waw_conflict_coordinator
    assert coordinator is not None

    with pytest.raises(WAWConflictError) as raised:
        coordinator.acquire_waw_start(
            project_id=FORMAL_PROJECT,
            agent_type=AgentType.CODEX,
        )

    assert raised.value.code == "PROJECT_RUNTIME_ACTIVE"
    assert providers.calls == ["claude"]


@pytest.mark.anyio
async def test_missing_vendor_runner_does_not_execute_or_fabricate_auth(tmp_path: Path) -> None:
    server, _codex, _claude = _fixed_server(tmp_path, _Providers())

    assert (
        await server.refresh_waw_public_auth_evidence(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id="wri_" + "1" * 32,
            runtime_host_installation_revision="1",
            executable_fingerprint="a" * 64,
            checked_at_monotonic=10.0,
        )
        is None
    )


def test_vendor_runner_without_bindings_is_rejected_before_manager_binding(tmp_path: Path) -> None:
    providers = _Providers()
    with pytest.raises(ValueError, match="runner and bindings"):
        _fixed_server(tmp_path, providers, runner=cast(WAWVendorProbeRunner, object()))


@pytest.mark.anyio
async def test_server_refreshes_auth_only_through_injected_qualified_runner(
    tmp_path: Path,
) -> None:
    port = _QualifiedPort()
    versions = {AgentType.CLAUDE: "2.1.226", AgentType.CODEX: "0.146.1"}
    fingerprints = {AgentType.CLAUDE: "a" * 64, AgentType.CODEX: "b" * 64}
    profiles = {
        AgentType.CLAUDE: WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1["claude"]["profile_id"]),
            AgentType.CLAUDE,
            versions[AgentType.CLAUDE],
            WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1,
            WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
            tmp_path / "claude",
            tmp_path,
            (("HOME", str(tmp_path)),),
        ),
        AgentType.CODEX: WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1["codex"]["profile_id"]),
            AgentType.CODEX,
            versions[AgentType.CODEX],
            WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
            WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
            tmp_path / "codex",
            tmp_path,
            (("HOME", str(tmp_path)),),
            waw_vendor_probe_output_digest(b"Not logged in\n", b""),
        ),
    }
    bindings = {
        agent_type: WAWVendorPublicAuthBinding(
            agent_type,
            "wri_" + "1" * 32,
            "1",
            fingerprints[agent_type],
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            versions[agent_type],
        )
        for agent_type in AgentType
    }
    server, _codex, _claude = _fixed_server(
        tmp_path,
        _Providers(),
        runner=WAWVendorProbeRunner(profiles, port),
        bindings=bindings,
    )

    evidence = await server.refresh_waw_public_auth_evidence(
        agent_type=AgentType.CLAUDE,
        runtime_host_installation_id="wri_" + "1" * 32,
        runtime_host_installation_revision="1",
        executable_fingerprint="a" * 64,
        checked_at_monotonic=10.0,
    )

    assert type(server.waw_public_auth_probe) is WAWCachedPublicAuthProbe
    assert evidence is not None and evidence.result.value == "AUTHENTICATED"
    assert port.calls == 1
    cache = server.waw_auth_probe_cache
    assert cache is not None
    assert (
        cache.fresh(
            agent_type=AgentType.CLAUDE,
            runtime_host_installation_id="wri_" + "1" * 32,
            runtime_host_installation_revision="1",
            executable_fingerprint="a" * 64,
            now_monotonic=11.0,
        )
        == evidence
    )
