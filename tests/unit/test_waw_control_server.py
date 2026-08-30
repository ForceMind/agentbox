from __future__ import annotations

import asyncio
import contextlib
import os
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_protocol.waw_control import decode_control_response
from agentbox_runtime.waw_control_server import (
    WAWControlDispatchError,
    WAWControlServer,
    _WAWControlDispatchPoisoned,
)


def _request() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "action": "workspace.workspace.start",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "generation": "1",
        "binding_revision": "1",
        "binding_digest": "a" * 64,
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
    }


def _response(request_id: str) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": request_id,
        "status": "STARTED",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": "prj_" + "3" * 32,
        "agent_type": "claude",
        "generation": "1",
        "state": "RUNNING",
        "runtime_host_installation_id": "wri_" + "4" * 32,
        "runtime_host_installation_revision": "1",
    }


async def _empty_response() -> dict[str, object]:
    return {}


Dispatch = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


async def _running_server(
    path: Path,
    dispatch: Dispatch,
    *,
    expected_peer_uid: int | None = None,
    expected_peer_gid: int | None = None,
    cancellation_grace_seconds: float = 0.05,
    max_active_connections: int = 64,
    max_active_dispatches: int = 16,
) -> tuple[WAWControlServer, socket.socket]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.listen(16)
    server = WAWControlServer(
        sock,
        dispatch,
        expected_peer_uid=os.geteuid() if expected_peer_uid is None else expected_peer_uid,
        expected_peer_gid=os.getegid() if expected_peer_gid is None else expected_peer_gid,
        timeout_seconds=0.2,
        cancellation_grace_seconds=cancellation_grace_seconds,
        max_active_connections=max_active_connections,
        max_active_dispatches=max_active_dispatches,
    )
    await server.start()
    return server, sock


async def _call(path: Path, payload: bytes) -> bytes:
    reader, writer = await asyncio.open_unix_connection(path)
    writer.write(payload)
    await writer.drain()
    raw = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return raw


@pytest.mark.anyio
async def test_dispatches_valid_request_and_closes_connection(tmp_path: Path) -> None:
    seen: list[dict[str, object]] = []

    async def dispatch(request: dict[str, object]) -> dict[str, object]:
        seen.append(request)
        return _response(cast(str, request["request_id"]))

    server, sock = await _running_server(tmp_path / "control.sock", dispatch)
    try:
        import json

        raw = await _call(tmp_path / "control.sock", json.dumps(_request()).encode() + b"\n")
        assert decode_control_response(
            raw,
            "workspace.workspace.start",
            expected_request_id=cast(str, _request()["request_id"]),
        ) == _response(cast(str, _request()["request_id"]))
        assert seen == [_request()]
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_server_rejects_unexpected_peer_credentials(tmp_path: Path) -> None:
    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        raise AssertionError("unexpected peer must not dispatch")

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch, expected_peer_gid=os.getegid() + 1)
    try:
        import json

        with pytest.raises(ConnectionResetError):
            await _call(path, json.dumps(_request()).encode() + b"\n")
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_rejects_malformed_oversized_and_trailing_requests(tmp_path: Path) -> None:
    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        raise AssertionError("malformed requests must not dispatch")

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch)
    try:
        malformed = (
            b'{"protocol_version":1,"request_id":"wreq_'
            + b"1" * 32
            + b'","action":"workspace.workspace.start","extra":1}\n'
        )
        response = await _call(path, malformed)
        assert b'"error_code":"PROTOCOL_INVALID"' in response
        oversized = b'{"request_id":"wreq_' + b"1" * 32 + b'","padding":"' + b"x" * 5000 + b'"}\n'
        response = await _call(path, oversized)
        assert b'"error_code":"PROTOCOL_INVALID"' in response
        import json

        payload = json.dumps(_request(), separators=(",", ":")).encode() + b"\n{}\n"
        response = await _call(path, payload)
        assert b'"error_code":"PROTOCOL_INVALID"' in response
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_dispatch_timeout_and_typed_error_response(tmp_path: Path) -> None:
    async def dispatch(request: dict[str, object]) -> dict[str, object]:
        if cast(str, request["request_id"]).endswith("1" * 32):
            await asyncio.sleep(0.5)
        raise WAWControlDispatchError("WORKSPACE_NOT_RUNNING", retryable=True)

    server, sock = await _running_server(tmp_path / "control.sock", dispatch)
    try:
        import json

        raw = await _call(tmp_path / "control.sock", json.dumps(_request()).encode() + b"\n")
        assert b'"error_code":"INTERNAL_BOUNDED"' in raw
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_cancellation_resistant_dispatch_poison_listener_and_closes_connection(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    late_effects: list[str] = []

    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Model an adapter that cannot stop immediately.  It performs a
            # late side effect only after the test explicitly releases it.
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    # Ignore repeated cancellation to model a truly
                    # cancellation-resistant dispatcher; the server must
                    # still isolate it and never reuse the listener.
                    continue
            late_effects.append("late")
            return _response(cast(str, _request["request_id"]))
        raise AssertionError("unreachable")

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch)
    try:
        import json

        request = json.dumps(_request(), separators=(",", ":")).encode() + b"\n"
        call = asyncio.create_task(_call(path, request))
        await asyncio.wait_for(started.wait(), timeout=1)
        raw = await asyncio.wait_for(call, timeout=1)
        assert raw == b""
        assert server._poisoned is True

        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert late_effects == ["late"]

        # The listener is closed after poisoning; no later request can reuse
        # the still-running dispatcher or observe its late response.
        with pytest.raises(
            (ConnectionRefusedError, ConnectionResetError, BrokenPipeError, FileNotFoundError)
        ):
            await _call(path, request)
    finally:
        release.set()
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_server_fences_dispatch_response_with_wrong_request_id(tmp_path: Path) -> None:
    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        return _response("wreq_" + "9" * 32)

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch)
    try:
        import json

        raw = await _call(path, json.dumps(_request()).encode() + b"\n")
        assert b'"error_code":"INTERNAL_BOUNDED"' in raw
        assert b'"request_id":"wreq_' + b"1" * 32 in raw
    finally:
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_poison_cancels_active_dispatches_on_two_connections(tmp_path: Path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    cancelled: list[str] = []

    async def dispatch(request: dict[str, object]) -> dict[str, object]:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(cast(str, request["request_id"]))
            await release.wait()
            raise
        raise AssertionError("unreachable")

    path = tmp_path / "control.sock"
    server, sock = await _running_server(
        path, dispatch, max_active_connections=4, max_active_dispatches=2
    )
    try:
        import json

        first = _request()
        second = _request() | {"request_id": "wreq_" + "4" * 32}
        calls = [
            asyncio.create_task(
                _call(path, json.dumps(request, separators=(",", ":")).encode() + b"\n")
            )
            for request in (first, second)
        ]
        await asyncio.wait_for(started.wait(), timeout=1)
        # Allow the second handler to enter dispatch before poisoning.
        while len(server._dispatch_tasks) < 2:
            await asyncio.sleep(0)
        server._poison_listener()
        release.set()
        assert await asyncio.wait_for(calls[0], timeout=1) == b""
        assert await asyncio.wait_for(calls[1], timeout=1) == b""
        assert set(cancelled) == {first["request_id"], second["request_id"]}
    finally:
        release.set()
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_close_while_dispatching_is_bounded_and_poisoned(tmp_path: Path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            raise
        raise AssertionError("unreachable")

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch)
    try:
        import json

        call = asyncio.create_task(
            _call(path, json.dumps(_request(), separators=(",", ":")).encode() + b"\n")
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        close_task = asyncio.create_task(server.close())
        await asyncio.wait_for(close_task, timeout=1)
        assert server._poisoned is True
        release.set()
        assert await asyncio.wait_for(call, timeout=1) == b""
    finally:
        release.set()
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_dispatch_limit_fails_closed_for_second_connection(tmp_path: Path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(request: dict[str, object]) -> dict[str, object]:
        started.set()
        await release.wait()
        return _response(cast(str, request["request_id"]))

    path = tmp_path / "control.sock"
    server, sock = await _running_server(path, dispatch, max_active_dispatches=1)
    try:
        import json

        first = _request()
        second = _request() | {"request_id": "wreq_" + "5" * 32}
        first_call = asyncio.create_task(
            _call(path, json.dumps(first, separators=(",", ":")).encode() + b"\n")
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        second_raw = await _call(path, json.dumps(second, separators=(",", ":")).encode() + b"\n")
        assert b'"error_code":"CONTROL_BUSY"' in second_raw
        release.set()
        assert await asyncio.wait_for(first_call, timeout=1)
    finally:
        release.set()
        await server.close()
        sock.close()


@pytest.mark.anyio
async def test_late_dispatch_exception_is_consumed_after_listener_poison(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    loop_errors: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def exception_handler(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        loop_errors.append(context)

    loop.set_exception_handler(exception_handler)

    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
            raise RuntimeError("late dispatch failure") from None
        raise AssertionError("unreachable")

    class FakeListeningSocket:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM

        def getsockopt(self, _level: int, option: int) -> int:
            assert option == socket.SO_ACCEPTCONN
            return 1

        def get_inheritable(self) -> bool:
            return False

    server = WAWControlServer(
        cast(Any, FakeListeningSocket()),
        dispatch,
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        timeout_seconds=0.2,
        cancellation_grace_seconds=0.01,
    )
    try:
        dispatch_call = asyncio.create_task(
            server._dispatch_with_deadline(_request(), server._monotonic() + 0.01)
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        with pytest.raises(_WAWControlDispatchPoisoned):
            await asyncio.wait_for(dispatch_call, timeout=1)
        assert server._poisoned is True

        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not any("late dispatch failure" in str(item) for item in loop_errors)
    finally:
        release.set()
        loop.set_exception_handler(previous_handler)
        await server.close()


@pytest.mark.anyio
async def test_cancellation_resistant_writer_close_poison_is_not_reused() -> None:
    release = asyncio.Event()

    class ResistantWriter:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                raise RuntimeError("late writer close failure") from None

    class FakeListeningSocket:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM

        def getsockopt(self, _level: int, option: int) -> int:
            assert option == socket.SO_ACCEPTCONN
            return 1

        def get_inheritable(self) -> bool:
            return False

    server = WAWControlServer(
        cast(Any, FakeListeningSocket()),
        lambda _request: _empty_response(),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        cancellation_grace_seconds=0.01,
    )
    writer = ResistantWriter()
    try:
        await server._close_writer(cast(Any, writer))
        assert writer.closed is True
        assert server._poisoned is True
        assert server._closing is True
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not server._io_tasks
    finally:
        release.set()
        await server.close()


@pytest.mark.parametrize("operation", ["read", "drain", "wait_closed"])
@pytest.mark.anyio
async def test_external_cancellation_cancels_child_io_and_poison_consumes_late_error(
    operation: str,
) -> None:
    """Handler/close cancellation must not leave an untracked I/O task."""

    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = asyncio.Event()
    loop_errors: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def exception_handler(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        loop_errors.append(context)

    loop.set_exception_handler(exception_handler)

    async def child_io() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            # Simulate a cancellation-resistant reader/writer close.  The
            # server must poison immediately, then consume this late error
            # once the operation eventually terminates.
            await release.wait()
            raise RuntimeError(f"late {operation} failure") from None

    class FakeListeningSocket:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM

        def getsockopt(self, _level: int, option: int) -> int:
            assert option == socket.SO_ACCEPTCONN
            return 1

        def get_inheritable(self) -> bool:
            return False

    server = WAWControlServer(
        cast(Any, FakeListeningSocket()),
        lambda _request: _empty_response(),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        cancellation_grace_seconds=0.01,
    )
    io_task = asyncio.create_task(server._bounded_io(child_io(), 1.0))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        io_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(io_task, timeout=1)
        assert cancelled.is_set()
        assert server._poisoned is True
        assert server._closing is True
        assert len(server._io_tasks) == 1

        release.set()
        await asyncio.wait_for(cancelled.wait(), timeout=1)
        for _ in range(3):
            await asyncio.sleep(0)
        assert not server._io_tasks
        assert not any(f"late {operation} failure" in str(item) for item in loop_errors)
    finally:
        release.set()
        if not io_task.done():
            io_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await io_task
        loop.set_exception_handler(previous_handler)
        await server.close()


@pytest.mark.anyio
async def test_external_dispatch_cancellation_is_quarantined_and_cleanup_is_detached() -> None:
    """Outer cancellation must not abandon a cancellation-resistant dispatch."""

    started = asyncio.Event()
    release = asyncio.Event()
    late_effects: list[str] = []

    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            late_effects.append("late")
            raise RuntimeError("late dispatch failure") from None
        raise AssertionError("unreachable")

    class FakeListeningSocket:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM

        def getsockopt(self, _level: int, option: int) -> int:
            assert option == socket.SO_ACCEPTCONN
            return 1

        def get_inheritable(self) -> bool:
            return False

    server = WAWControlServer(
        cast(Any, FakeListeningSocket()),
        dispatch,
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        cancellation_grace_seconds=0.01,
    )
    dispatch_call = asyncio.create_task(
        server._dispatch_with_deadline(_request(), server._monotonic() + 1)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        dispatch_call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(dispatch_call, timeout=1)
        # A second cancellation of the already-cancelled outer task must not
        # affect the detached observer or the tracked child dispatch.
        dispatch_call.cancel()
        assert server._poisoned is True
        assert server._closing is True
        assert len(server._dispatch_tasks) == 1

        release.set()
        for _ in range(5):
            await asyncio.sleep(0)
        assert late_effects == ["late"]
        assert not server._dispatch_tasks
        assert not server._cleanup_tasks
    finally:
        release.set()
        if not dispatch_call.done():
            dispatch_call.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await dispatch_call
        await server.close()


@pytest.mark.parametrize("repeat_action", ["observer_cancel", "server_close"])
@pytest.mark.anyio
async def test_repeated_cancellation_observer_keeps_pending_dispatch_quarantined(
    repeat_action: str,
) -> None:
    """Repeated cancellation cannot detach or reuse a late dispatch task."""

    started = asyncio.Event()
    release = asyncio.Event()
    late_failure = asyncio.Event()
    loop_errors: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def exception_handler(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        loop_errors.append(context)

    loop.set_exception_handler(exception_handler)

    async def dispatch(_request: dict[str, object]) -> dict[str, object]:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Ignore repeated cancellation to model a cancellation-resistant
            # adapter.  The eventual exception must still be consumed by the
            # dispatch task's done callback.
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    continue
            late_failure.set()
            raise RuntimeError("late repeated-cancellation failure") from None
        raise AssertionError("unreachable")

    class FakeListeningSocket:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM

        def getsockopt(self, _level: int, option: int) -> int:
            assert option == socket.SO_ACCEPTCONN
            return 1

        def get_inheritable(self) -> bool:
            return False

    server = WAWControlServer(
        cast(Any, FakeListeningSocket()),
        dispatch,
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        cancellation_grace_seconds=0.01,
    )
    dispatch_call = asyncio.create_task(
        server._dispatch_with_deadline(_request(), server._monotonic() + 1)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        dispatch_call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(dispatch_call, timeout=1)

        # The outer owner is already cancelled.  Its child remains tracked,
        # and the independent observer is the only cleanup owner left.
        assert len(server._dispatch_tasks) == 1
        assert len(server._cleanup_tasks) == 1
        cleanup = next(iter(server._cleanup_tasks))

        if repeat_action == "observer_cancel":
            cleanup.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(cleanup, timeout=1)
        else:
            close_task = asyncio.create_task(server.close())
            await asyncio.wait_for(close_task, timeout=1)

        # Repeated cancellation or close must not claim that the resistant
        # child has terminated.  The poisoned listener is never reusable.
        assert server._poisoned is True
        assert len(server._dispatch_tasks) == 1

        release.set()
        await asyncio.wait_for(late_failure.wait(), timeout=1)

        async def wait_for_registries_to_empty() -> None:
            while server._dispatch_tasks or server._cleanup_tasks:
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_for_registries_to_empty(), timeout=1)
        assert not server._dispatch_tasks
        assert not server._cleanup_tasks
        assert not any("late repeated-cancellation failure" in str(item) for item in loop_errors)
    finally:
        release.set()
        if not dispatch_call.done():
            dispatch_call.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await dispatch_call
        loop.set_exception_handler(previous_handler)
        await server.close()


async def _scenario_external_close_cancellation_finishes_independent_cleanup_fail_closed() -> None:
    """Cancelling close cannot interrupt cleanup or report a clean restartable state."""

    release = asyncio.Event()

    class ResistantAsyncServer:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            await release.wait()

    class FakeListeningSocket:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM

        def getsockopt(self, _level: int, option: int) -> int:
            assert option == socket.SO_ACCEPTCONN
            return 1

        def get_inheritable(self) -> bool:
            return False

    server = WAWControlServer(
        cast(Any, FakeListeningSocket()),
        lambda _request: _empty_response(),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        cancellation_grace_seconds=1.0,
    )
    resistant = ResistantAsyncServer()
    server._server = cast(Any, resistant)
    close_call = asyncio.create_task(server.close())
    try:
        # Let the independent close operation enter wait_closed before
        # cancelling its caller.  A repeated cancellation is intentionally
        # applied to the already-cancelled owner as a regression guard.
        while not resistant.closed:
            await asyncio.sleep(0)
        close_call.cancel()
        # Do not await the cancelled owner through ``wait_for``: on newer
        # asyncio versions that wrapper can propagate the owner's cancellation
        # into the test runner.  One loop turn is sufficient to make the
        # cancellation terminal while the shielded operation continues.
        with contextlib.suppress(asyncio.CancelledError):
            await close_call
        assert close_call.cancelled() is True
        assert server._poisoned is True
        assert server._closing is True
        assert server._server is not None

        release.set()
        operation = server._close_operation
        assert operation is not None
        for _ in range(1000):
            if operation.done():
                break
            await asyncio.sleep(0)
        assert operation.done() is True
        assert operation.cancelled() is False
        for _ in range(3):
            await asyncio.sleep(0)

        # Cleanup completed, but cancellation remains a terminal poisoned
        # state: no subsequent start may reuse this listener.
        assert resistant.closed is True
        assert server._server is None
        assert server._connection_tasks == set()
        assert server._dispatch_tasks == set()
        assert server._io_tasks == set()
        assert server._cleanup_tasks == set()
        assert server._writers == set()
        assert server._poisoned is True
        assert server._closing is True
        with pytest.raises(RuntimeError, match="poisoned"):
            await server.start()
    finally:
        release.set()
        if not close_call.done():
            close_call.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await close_call
        await server.close()


def test_external_close_cancellation_finishes_independent_cleanup_fail_closed() -> None:
    # Run this cancellation-specific scenario under a plain asyncio runner;
    # anyio's task runner intentionally propagates child cancellation scopes.
    asyncio.run(_scenario_external_close_cancellation_finishes_independent_cleanup_fail_closed())


async def _scenario_concurrent_close_callers_share_operation() -> None:
    """Concurrent close callers share one worker across caller cancellation."""

    release = asyncio.Event()
    wait_closed_entered = asyncio.Event()
    worker_calls = 0

    class ResistantAsyncServer:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            wait_closed_entered.set()
            await release.wait()

    class FakeListeningSocket:
        family = socket.AF_UNIX
        type = socket.SOCK_STREAM

        def getsockopt(self, _level: int, option: int) -> int:
            assert option == socket.SO_ACCEPTCONN
            return 1

        def get_inheritable(self) -> bool:
            return False

    server = WAWControlServer(
        cast(Any, FakeListeningSocket()),
        lambda _request: _empty_response(),
        expected_peer_uid=os.geteuid(),
        expected_peer_gid=os.getegid(),
        cancellation_grace_seconds=1.0,
    )
    resistant = ResistantAsyncServer()
    server._server = cast(Any, resistant)

    original_perform_close = server._perform_close

    async def counted_perform_close() -> None:
        nonlocal worker_calls
        worker_calls += 1
        await original_perform_close()

    # Keep the production implementation unchanged while observing whether
    # two callers accidentally create two independent close workers.
    cast(Any, server)._perform_close = counted_perform_close

    first = asyncio.create_task(server.close())
    second = asyncio.create_task(server.close())
    try:
        await asyncio.wait_for(wait_closed_entered.wait(), timeout=1)
        operation = server._close_operation
        assert operation is not None
        assert worker_calls == 1

        # The first caller is cancelled while the shared operation remains in
        # wait_closed.  The second caller must continue waiting on that same
        # operation rather than starting a replacement worker.
        first.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await first
        assert first.cancelled() is True
        assert second.done() is False
        assert server._close_operation is operation

        release.set()
        await asyncio.wait_for(second, timeout=1)
        assert worker_calls == 1

        # Let the operation's completion callback run.  It may clear only its
        # own operation reference and must leave no stale cleanup registration.
        for _ in range(3):
            await asyncio.sleep(0)
        assert operation.done() is True
        if cast(Any, server)._cleanup_tasks:
            pytest.fail("close completion left a stale cleanup task")
        if server._close_operation is not None:
            pytest.fail("close completion left a stale operation reference")
    finally:
        release.set()
        for task in (first, second):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await server.close()


def test_concurrent_close_callers_share_operation() -> None:
    # Use a plain asyncio runner because anyio cancellation scopes propagate
    # cancellation into the caller that is intentionally being cancelled.
    asyncio.run(_scenario_concurrent_close_callers_share_operation())
