"""Same-process, separate-loop guard budgets; not separate-process/host evidence."""

from __future__ import annotations

import asyncio
import concurrent.futures
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import test_a3_admission as admission_case
import test_a3_native_transport as native_case
from agentbox_core.a3_native_io import deadline_after
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.a3_transport import NativeKind, facts_digest
from test_git_staged_reader import stage
from test_git_staged_selectors import setup


class _ReservationProxy:
    """Test only: descriptor composition runs on the real Runtime owner loop."""

    def __init__(self, owner: _OwnerProxy, reservation: Any) -> None:
        self.owner, self.actual = owner, reservation

    def __getattr__(self, name: str) -> Any:
        return getattr(self.actual, name)

    def accept(self, *sockets: Any) -> _ReservationProxy:
        self.owner.invoke(lambda: self.actual.accept(*sockets))
        return self

    def close(self) -> None:
        self.owner.loop.call_soon_threadsafe(self.actual.close)

    async def wait_closed(self) -> None:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(self.actual.wait_closed(), self.owner.loop)
        )


class _OwnerProxy:
    def __init__(
        self, owner: Any, loop: asyncio.AbstractEventLoop, thread: threading.Thread
    ) -> None:
        self.actual, self.loop, self.thread = owner, loop, thread

    def __getattr__(self, name: str) -> Any:
        # Only fixture counters/selector state are read from the API test thread.
        return getattr(self.actual, name)

    def invoke(self, operation: Callable[[], Any]) -> Any:
        result: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def call() -> None:
            try:
                result.set_result(operation())
            except BaseException as error:
                result.set_exception(error)

        self.loop.call_soon_threadsafe(call)
        return result.result(timeout=3)

    def reserve(self) -> _ReservationProxy:
        return _ReservationProxy(self, self.invoke(self.actual.reserve))

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.actual.close)

    async def wait_closed(self) -> None:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(self.actual.wait_closed(), self.loop)
        )
        if self.actual._closed:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=3)
            assert not self.thread.is_alive()
            self.loop.close()


@pytest.mark.anyio
@pytest.mark.parametrize("reply_delay_ms", [8])
async def test_independent_api_loop_live_and_record_publication_keep_fixed_budgets(
    tmp_path: Path,
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
    reply_delay_ms: int,
) -> None:
    """The old duplicate guards starve a 250ms command despite small fresh-RPC RTT.

    API issues LIVE independently while Runtime is doing synchronous currentness
    work. Putting both on one event loop masks the queueing failure. No product
    deadline, publication guard, nonce ledger or admission fact is replaced.
    """
    original_owner = native_case.native_owner
    original_setup = setup
    original_rpc = native_case.Client.rpc
    original_close = native_case.Client.close
    heartbeat_tasks: dict[native_case.Client, asyncio.Task[None]] = {}
    command_locks: dict[native_case.Client, asyncio.Lock] = {}
    heartbeat_failures: list[str] = []
    live_replies = 0
    current_calls = 0

    def larger_patch(*args: Any, **kwargs: Any) -> Any:
        result = original_setup(*args, **kwargs)
        project = result[1]
        (project / "modified.txt").write_text(
            "staged secret-canary content\n" + "x" * 24000 + "\n", encoding="utf-8"
        )
        stage(project, "modified.txt")
        return result

    async def independent_owner(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, name="a3-runtime-test-loop", daemon=True)
        thread.start()
        try:
            owner, facts, authority, lifecycle = await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(original_owner(*args, **kwargs), loop)
            )
            return _OwnerProxy(owner, loop, thread), facts, authority, lifecycle
        except BaseException:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=3)
            loop.close()
            raise

    def delayed_checker(client: native_case.Client) -> None:
        nonlocal current_calls
        channel = client.channels["currentness"]
        try:
            while True:
                channel.wait_readable(deadline_after(30))
                frame = channel.receive(
                    frozenset({NativeKind.CURRENT}), deadline_ns=deadline_after(0.25)
                )
                payload = cast(dict[str, object], frame.payload)
                assert payload["facts_digest"] == facts_digest(client.facts)
                client.calls += 1
                current_calls += 1
                # Dedicated checker delay does not block the independent API loop.
                time.sleep(reply_delay_ms / 1000)
                channel.send(
                    NativeKind.CURRENT_REPLY,
                    {**payload, "current": client.live},
                    deadline_ns=deadline_after(0.25),
                )
        except Exception:
            channel.close()

    async def heartbeat(client: native_case.Client) -> None:
        nonlocal live_replies
        sequence = 1  # The fixture explicitly completed challenge zero after READY.
        while client.live:
            await asyncio.sleep(0.25)
            try:
                async with command_locks[client]:
                    payload = {
                        "observation_sequence": sequence,
                        "challenge": secrets.token_hex(16),
                    }
                    response = await original_rpc(
                        client, NativeKind.LIVE, payload, NativeKind.LIVE_REPLY
                    )
                    assert response == payload
                    sequence += 1
                    live_replies += 1
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if client.live:
                    heartbeat_failures.append(type(error).__name__)
                return

    async def serial_rpc(
        client: native_case.Client,
        kind: NativeKind,
        payload: dict[str, object],
        response: NativeKind,
    ) -> dict[str, object]:
        lock = command_locks.setdefault(client, asyncio.Lock())
        async with lock:
            result = await original_rpc(client, kind, payload, response)
        if kind is NativeKind.LIVE and payload["observation_sequence"] == 0:
            assert client not in heartbeat_tasks
            heartbeat_tasks[client] = asyncio.create_task(heartbeat(client))
        return result

    async def close_client(client: native_case.Client) -> None:
        task = heartbeat_tasks.pop(client, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await original_close(client)

    monkeypatch.setattr(admission_case, "setup", larger_patch)
    monkeypatch.setattr(native_case, "native_owner", independent_owner)
    monkeypatch.setattr(native_case.Client, "checker", delayed_checker)
    monkeypatch.setattr(native_case.Client, "rpc", serial_rpc)
    monkeypatch.setattr(native_case.Client, "close", close_client)
    # This exercises actual admission/Git/crypto/record ACK/END and original-owner
    # retention, then revokes currentness and confirms cleanup with the nonce burned.
    await native_case.test_native_records_hold_admission_through_publication_complete_and_revoke(
        tmp_path, initialized_services
    )
    assert not heartbeat_failures
    assert live_replies >= 1 and current_calls > 0
    assert not heartbeat_tasks
