"""Bounded opaque TEST wiring only. No endpoint or production application import."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

_LIMIT = 24 * 1024


class A3OpaqueTestRelay:
    """One frame per direction, fail-closed loss; never accepts plaintext objects."""

    def __init__(self, *, enabled_for_tests: bool = False) -> None:
        if enabled_for_tests is not True:
            raise ValueError("A3 relay is disabled")
        self._incoming: asyncio.Queue[bytes] = asyncio.Queue(1)
        self._outgoing: asyncio.Queue[bytes] = asyncio.Queue(1)
        self._closed = asyncio.Event()
        self._consumed = {self._incoming: asyncio.Event(), self._outgoing: asyncio.Event()}
        self._sending: set[asyncio.Queue[bytes]] = set()
        self._receiving: set[asyncio.Queue[bytes]] = set()

    def close(self) -> None:
        self._closed.set()
        for event in self._consumed.values():
            event.set()
        for queue in (self._incoming, self._outgoing):
            while not queue.empty():
                queue.get_nowait()

    def _check(self, raw: bytes | None = None) -> None:
        if self._closed.is_set() or (
            raw is not None and (type(raw) is not bytes or not 1 <= len(raw) <= _LIMIT)
        ):
            self.close()
            raise ValueError("A3 opaque relay unavailable")

    async def _get(self, queue: asyncio.Queue[bytes]) -> bytes:
        self._check()
        if queue in self._receiving:
            self.close()
            raise ValueError("A3 opaque relay busy")
        self._receiving.add(queue)
        get = asyncio.create_task(queue.get())
        closed = asyncio.create_task(self._closed.wait())
        try:
            try:
                await asyncio.wait((get, closed), return_when=asyncio.FIRST_COMPLETED)
                self._check()
                raw = get.result()
                self._check(raw)
            finally:
                for task in (get, closed):
                    task.cancel()
                await asyncio.gather(get, closed, return_exceptions=True)
            # Cleanup is awaited: fence again before returning any opaque record.
            self._check(raw)
            self._consumed[queue].set()
            return raw
        except BaseException:
            self.close()
            raise
        finally:
            self._receiving.discard(queue)

    async def _put(
        self, queue: asyncio.Queue[bytes], raw: bytes, check_current: Callable[[], None]
    ) -> None:
        try:
            self._check(raw)
            # No queue of waiting senders and no uncertain automatic retry.
            if queue in self._sending or queue.full():
                raise ValueError("A3 opaque relay busy")
            self._sending.add(queue)
            event = self._consumed[queue]
            event.clear()
            check_current()
            self._check(raw)
            queue.put_nowait(raw)
            # Hold sender ownership until dequeued; max one whole record/direction.
            await event.wait()
            self._check()
            check_current()
        except BaseException:
            self.close()
            raise
        finally:
            self._sending.discard(queue)

    async def receive(self) -> bytes:
        return await self._get(self._incoming)

    async def send(self, raw: bytes, check_current: Callable[[], None]) -> None:
        await self._put(self._outgoing, raw, check_current)

    async def browser_send(self, raw: bytes, check_current: Callable[[], None]) -> None:
        await self._put(self._incoming, raw, check_current)

    async def browser_receive(self) -> bytes:
        return await self._get(self._outgoing)
