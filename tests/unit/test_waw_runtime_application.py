from __future__ import annotations

import asyncio
import inspect
import socket
import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_runtime import waw_runtime_application as subject
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.server import RuntimeExecutorServer
from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_bootstrap import WAWFixedRuntimeComposition
from agentbox_runtime.waw_encrypted_server import WAWEncryptedServer
from agentbox_runtime.waw_encrypted_stream import WAWEncryptedRegistry
from agentbox_runtime.waw_peer_authority import WAWPeerAuthority
from agentbox_runtime.waw_runtime_application import (
    WAWRuntimeApplication,
    WAWRuntimeApplicationState,
    build_waw_runtime_application_from_filesystem_v2,
)


class _Registry:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.gate_open = False
        self.peer_authority = object()
        self.shutdown_clean = False

    def open_application_gate(self) -> None:
        self.events.append("gate.open")
        self.gate_open = True

    def close_application_gate(self) -> None:
        self.events.append("gate.close")
        self.gate_open = False


class _Encrypted:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def invalidate(self) -> None:
        self.events.append("registry.invalidate")


class _Stream:
    def __init__(
        self,
        events: list[str],
        *,
        clean: bool = True,
        close_entered: asyncio.Event | None = None,
        close_release: asyncio.Event | None = None,
    ) -> None:
        self.events = events
        self.expected_clean = clean
        self.shutdown_clean = False
        self.close_entered = close_entered
        self.close_release = close_release

    async def start(self) -> None:
        self.events.append("stream.start")

    def close(self) -> Any:
        self.events.append("stream.fence")

        async def finish() -> None:
            self.events.append("stream.wait")
            if self.close_entered is not None:
                self.close_entered.set()
            if self.close_release is not None:
                await self.close_release.wait()
            self.shutdown_clean = self.expected_clean

        return finish()


class _Control:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.shutdown_clean = False

    async def start(self) -> None:
        self.events.append("control.start")


class _Runtime:
    def __init__(
        self,
        events: list[str],
        registry: _Registry,
        *,
        start_failure: BaseException | None = None,
        control_clean: bool = True,
    ) -> None:
        self.events = events
        self.registry = registry
        self.start_failure = start_failure
        self.control_close_clean = control_clean
        self.legacy_shutdown_clean = False
        self.waw_control_server = _Control(events)
        self.waw_peer_authority = registry.peer_authority
        self.waw_fixed_runtime = SimpleNamespace(
            registry=registry,
            executor=SimpleNamespace(runtime_epoch="1"),
            runtime_epoch="1",
        )

    async def start(self, *, create_development_parent: bool = False) -> None:
        assert not self.registry.gate_open
        self.events.append(f"runtime.start:{create_development_parent}")
        if self.start_failure is not None:
            raise self.start_failure

    def close(self) -> Any:
        self.events.append("runtime.fence")

        async def finish() -> None:
            self.events.append("runtime.wait")
            self.legacy_shutdown_clean = True
            self.waw_control_server.shutdown_clean = self.control_close_clean
            self.registry.shutdown_clean = True

        return finish()


class _KeyPort:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False
        self.taken: _KeyPort | None = None

    def preflight(self) -> None:
        return None

    def private_key(self) -> bytes:
        return b"private-key-canary"

    def take(self) -> _KeyPort:
        if self.taken is not None:
            raise RuntimeError("key port already taken")
        self.taken = _KeyPort(self.events)
        return self.taken

    def close(self) -> bool:
        self.events.append("key.close")
        self.closed = True
        return True


class _Provider:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False
        self.taken: _Provider | None = None

    def create_executor(self, _epoch: str, _authority: Any) -> Any:
        raise AssertionError("behavior tests use already composed components")

    def take(self) -> _Provider:
        if self.taken is not None:
            raise RuntimeError("provider already taken")
        self.taken = _Provider(self.events)
        return self.taken

    def close(self) -> bool:
        self.events.append("provider.close")
        self.closed = True
        return True


def _application(
    *,
    stream_clean: bool = True,
    start_failure: BaseException | None = None,
    close_entered: asyncio.Event | None = None,
    close_release: asyncio.Event | None = None,
    control_clean: bool = True,
) -> tuple[WAWRuntimeApplication, list[str], _KeyPort, _Provider]:
    events: list[str] = []
    registry = _Registry(events)
    runtime = _Runtime(
        events,
        registry,
        start_failure=start_failure,
        control_clean=control_clean,
    )
    stream = _Stream(
        events,
        clean=stream_clean,
        close_entered=close_entered,
        close_release=close_release,
    )
    key = _KeyPort(events)
    provider = _Provider(events)
    app = object.__new__(WAWRuntimeApplication)
    app._runtime = cast(Any, runtime)
    app._stream = cast(Any, stream)
    app._encrypted = cast(Any, _Encrypted(events))
    app._registry = cast(Any, registry)
    app._composition = cast(Any, runtime.waw_fixed_runtime)
    app._key_port = key
    app._executor_provider = provider
    app._state = WAWRuntimeApplicationState.NEW
    app._state_lock = threading.RLock()
    app._start_operation = None
    app._close_operation = None
    app._shutdown_evidence = None
    app._startup_failure = None
    app._key_closed = False
    app._provider_closed = False
    return app, events, key, provider


@pytest.mark.anyio
async def test_start_opens_gate_only_after_stream_and_runtime_are_ready() -> None:
    app, events, _key, _provider = _application()

    await app.start(create_development_parent=True)

    assert app.ready and app.state is WAWRuntimeApplicationState.RUNNING
    assert events == ["stream.start", "control.start", "runtime.start:True", "gate.open"]


@pytest.mark.anyio
async def test_close_fences_all_admission_before_ports_and_publishes_evidence() -> None:
    app, events, key, provider = _application()
    await app.start()
    events.clear()

    close_wait = app.close()
    assert events == [
        "gate.close",
        "registry.invalidate",
        "stream.fence",
        "runtime.fence",
    ]
    await close_wait

    assert events == [
        "gate.close",
        "registry.invalidate",
        "stream.fence",
        "runtime.fence",
        "stream.wait",
        "runtime.wait",
        "key.close",
        "provider.close",
    ]
    assert key.closed and provider.closed
    assert app.state is WAWRuntimeApplicationState.CLOSED
    assert app.shutdown_evidence is not None and app.shutdown_evidence.clean


@pytest.mark.anyio
async def test_close_caller_cancellation_does_not_cancel_component_cleanup() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    app, _events, _key, _provider = _application(
        close_entered=entered,
        close_release=release,
    )
    await app.start()
    waiter = asyncio.create_task(app.close())
    await entered.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert app._close_operation is not None and not app._close_operation.done()
    release.set()
    await app.close()
    assert app.state is WAWRuntimeApplicationState.CLOSED


@pytest.mark.anyio
async def test_direct_close_operation_cancellation_is_sticky_poison() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    app, _events, _key, _provider = _application(
        close_entered=entered,
        close_release=release,
    )
    await app.start()
    waiting = asyncio.create_task(app.close())
    await entered.wait()
    assert app._close_operation is not None
    app._close_operation.cancel()
    release.set()
    with pytest.raises(RuntimeOperationError, match="shutdown is incomplete") as first:
        await waiting
    assert app.state is WAWRuntimeApplicationState.POISONED
    with pytest.raises(RuntimeOperationError) as repeated:
        await app.close()
    assert repeated.value is first.value


@pytest.mark.anyio
async def test_incomplete_stream_keeps_key_and_provider_owned_and_is_sticky() -> None:
    app, _events, key, provider = _application(stream_clean=False)
    await app.start()
    with pytest.raises(RuntimeOperationError, match="shutdown is incomplete") as first:
        await app.close()
    assert app.state is WAWRuntimeApplicationState.POISONED
    assert not key.closed and not provider.closed
    with pytest.raises(RuntimeOperationError) as repeated:
        await app.close()
    assert repeated.value is first.value


@pytest.mark.anyio
async def test_control_incomplete_keeps_executor_provider_but_closes_stream_key() -> None:
    app, _events, key, provider = _application(control_clean=False)
    await app.start()
    with pytest.raises(RuntimeOperationError, match="shutdown is incomplete"):
        await app.close()
    assert key.closed and not provider.closed
    assert app.shutdown_evidence is not None
    assert app.shutdown_evidence.stream_clean
    assert not app.shutdown_evidence.control_clean


@pytest.mark.anyio
async def test_start_failure_never_opens_gate_and_closes_into_poison() -> None:
    failure = RuntimeError("synthetic legacy start failure")
    app, events, _key, _provider = _application(start_failure=failure)
    with pytest.raises(RuntimeError, match="synthetic legacy"):
        await app.start()
    assert "gate.open" not in events
    assert app.state is WAWRuntimeApplicationState.POISONED


def test_production_builder_exposes_only_typed_ports() -> None:
    from agentbox_runtime import server as runtime_server_subject
    from agentbox_runtime import waw_bootstrap as bootstrap_subject

    parameters = inspect.signature(build_waw_runtime_application_from_filesystem_v2).parameters
    assert "executor_provider" in parameters and "key_port" in parameters
    assert "executor_factory" not in parameters and "static_key" not in parameters
    assert not hasattr(runtime_server_subject, "build_runtime_server_from_filesystem_v2")
    assert not hasattr(bootstrap_subject, "build_waw_encrypted_servers")
    assert not hasattr(bootstrap_subject, "build_waw_encrypted_stream_server")
    assert not hasattr(bootstrap_subject, "create_waw_encrypted_servers_test_only")


@pytest.mark.anyio
async def test_production_builder_uses_one_composition_and_typed_port_methods(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_waw_lifecycle import registry as lifecycle_registry

    events: list[str] = []
    registry = lifecycle_registry()
    authority = WAWPeerAuthority(expected_uid=1001, expected_gid=1002)
    registry.configure_peer_authority(authority)
    executor = SimpleNamespace(runtime_epoch="1")
    composition = WAWFixedRuntimeComposition(
        registry,
        cast(Any, executor),
        "1",
        cast(Any, object()),
    )
    runtime = object.__new__(RuntimeExecutorServer)
    runtime._waw_fixed_runtime = composition
    runtime._waw_peer_authority = authority
    encrypted = WAWEncryptedRegistry(runtime_epoch="1", static_key=lambda: b"k" * 32)
    stream = object.__new__(WAWEncryptedServer)
    key = _KeyPort(events)
    provider = _Provider(events)
    captured: dict[str, Any] = {}

    def build_runtime(**kwargs: Any) -> RuntimeExecutorServer:
        captured["executor_factory"] = kwargs["executor_factory"]
        return runtime

    def build_stream(**kwargs: Any) -> tuple[WAWEncryptedServer, WAWEncryptedRegistry]:
        captured.update(kwargs)
        registry._encrypted_attachments = cast(
            Any,
            SimpleNamespace(registry=encrypted),
        )
        return stream, encrypted

    monkeypatch.setattr(subject, "_build_runtime_server_from_filesystem_v2", build_runtime)
    monkeypatch.setattr(subject, "_build_waw_encrypted_stream_server", build_stream)
    control, control_peer = socket.socketpair()
    stream_socket, stream_peer = socket.socketpair()
    activated = WAWActivatedSockets(control, stream_socket)
    try:
        app = await build_waw_runtime_application_from_filesystem_v2(
            socket_path=tmp_path / "runtime.sock",
            manager=cast(Any, object()),
            claude_manager=cast(Any, object()),
            allowed_peer_uids=frozenset({1001}),
            allowed_peer_gids=frozenset({1002}),
            formal_project_id_for_legacy=lambda _value: None,
            activated_sockets=activated,
            waw_control_peer_uid=1001,
            waw_control_peer_gid=1002,
            runtime_manifest_path=tmp_path / "runtime.json",
            public_directory=tmp_path,
            expected_runtime_gid=1002,
            epoch_store=cast(Any, object()),
            executor_provider=provider,
            key_port=key,
            binding_digest_factory=lambda _request: "a" * 64,
            clock=lambda: 0.0,
        )

        assert type(app) is WAWRuntimeApplication
        assert getattr(captured["executor_factory"], "__self__", None) is provider.taken
        assert getattr(captured["static_key"], "__self__", None) is key.taken
        assert captured["peer_authority"] is authority
        assert captured["registry"] is registry and captured["executor"] is executor
        assert registry._application_gate_required and not registry._application_gate_open
        assert activated.control.fileno() == activated.stream.fileno() == -1
        assert events == []
    finally:
        owned = captured.get("sockets")
        if isinstance(owned, WAWActivatedSockets):
            owned.close()
        control_peer.close()
        stream_peer.close()


@pytest.mark.anyio
async def test_builder_failure_after_runtime_reverses_owned_resources(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_waw_lifecycle import registry as lifecycle_registry

    events: list[str] = []
    runtime = object.__new__(RuntimeExecutorServer)
    registry = lifecycle_registry()
    authority = WAWPeerAuthority(expected_uid=1001, expected_gid=1002)
    registry.configure_peer_authority(authority)
    runtime._waw_fixed_runtime = WAWFixedRuntimeComposition(
        registry,
        cast(Any, SimpleNamespace(runtime_epoch="1")),
        "1",
        cast(Any, object()),
    )
    runtime._waw_peer_authority = authority

    owned: WAWActivatedSockets | None = None

    async def close_runtime(_self: RuntimeExecutorServer) -> None:
        assert owned is not None
        owned.control.close()
        events.append("runtime.close")

    def build_runtime(**kwargs: Any) -> RuntimeExecutorServer:
        nonlocal owned
        owned = kwargs["activated_sockets"]
        events.append("runtime.build")
        return runtime

    def fail_stream(**_kwargs: Any) -> Any:
        events.append("stream.build")
        raise RuntimeError("synthetic stream construction failure")

    key = _KeyPort(events)
    provider = _Provider(events)
    monkeypatch.setattr(subject, "_build_runtime_server_from_filesystem_v2", build_runtime)
    monkeypatch.setattr(subject, "_build_waw_encrypted_stream_server", fail_stream)
    monkeypatch.setattr(RuntimeExecutorServer, "close", close_runtime)
    monkeypatch.setattr(
        RuntimeExecutorServer,
        "shutdown_clean",
        property(lambda _self: True),
    )
    control, control_peer = socket.socketpair()
    stream_socket, stream_peer = socket.socketpair()
    activated = WAWActivatedSockets(control, stream_socket)
    try:
        with pytest.raises(RuntimeOperationError, match="construction failed"):
            await build_waw_runtime_application_from_filesystem_v2(
                socket_path=tmp_path / "runtime.sock",
                manager=cast(Any, object()),
                claude_manager=cast(Any, object()),
                allowed_peer_uids=frozenset({1001}),
                allowed_peer_gids=frozenset({1002}),
                formal_project_id_for_legacy=lambda _value: None,
                activated_sockets=activated,
                waw_control_peer_uid=1001,
                waw_control_peer_gid=1002,
                runtime_manifest_path=tmp_path / "runtime.json",
                public_directory=tmp_path,
                expected_runtime_gid=1002,
                epoch_store=cast(Any, object()),
                executor_provider=provider,
                key_port=key,
                binding_digest_factory=lambda _request: "a" * 64,
                clock=lambda: 0.0,
            )
        assert owned is not None
        assert owned.control.fileno() == owned.stream.fileno() == -1
    finally:
        control_peer.close()
        stream_peer.close()
    assert events == [
        "runtime.build",
        "stream.build",
        "runtime.close",
        "key.close",
        "provider.close",
    ]


@pytest.mark.anyio
async def test_construction_cleanup_retains_incomplete_owner_for_retry() -> None:
    events: list[str] = []

    class PartialRuntime:
        shutdown_clean = False

        async def close(self) -> None:
            events.append("runtime.close")

    cleanup = subject.WAWRuntimeConstructionCleanup(subject._CONSTRUCTION_TOKEN)
    cleanup.runtime_server = cast(Any, PartialRuntime())
    cleanup.key_port = _KeyPort(events)
    cleanup.executor_provider = _Provider(events)

    assert not await cleanup.close()
    assert cleanup.runtime_server is not None
    assert cleanup.executor_provider is not None
    assert events == ["runtime.close", "key.close"]

    cast(Any, cleanup.runtime_server).shutdown_clean = True
    assert await cleanup.close()
    assert cleanup.clean
    assert events == ["runtime.close", "key.close", "runtime.close", "provider.close"]
    error = subject.WAWRuntimeApplicationBuildError(cleanup)
    assert error.cleanup is cleanup
    assert "private-key-canary" not in repr(cleanup)


@pytest.mark.anyio
async def test_construction_stream_worker_retains_both_runtime_ports() -> None:
    events: list[str] = []

    class PartialStream:
        shutdown_clean = False

        async def close(self) -> None:
            events.append("stream.close")

    class CleanRuntime:
        shutdown_clean = True

        async def close(self) -> None:
            events.append("runtime.close")

    cleanup = subject.WAWRuntimeConstructionCleanup(subject._CONSTRUCTION_TOKEN)
    cleanup.stream_server = cast(Any, PartialStream())
    cleanup.runtime_server = cast(Any, CleanRuntime())
    cleanup.key_port = _KeyPort(events)
    cleanup.executor_provider = _Provider(events)

    assert not await cleanup.close()
    assert events == ["stream.close", "runtime.close"]

    cast(Any, cleanup.stream_server).shutdown_clean = True
    assert await cleanup.close()
    assert events == [
        "stream.close",
        "runtime.close",
        "stream.close",
        "runtime.close",
        "key.close",
        "provider.close",
    ]


def test_repr_contains_state_only() -> None:
    app, _events, _key, _provider = _application()
    assert repr(app) == "WAWRuntimeApplication(state='NEW')"
    assert "private-key-canary" not in repr(app)
