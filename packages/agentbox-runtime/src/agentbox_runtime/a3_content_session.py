"""Single admitted staged read through a bounded opaque transport port.

No socket/API composition or production key acquisition occurs in this module.
The same selector owner holds the snapshot, active slot and burned nonce through
completion. Port uncertainty closes permanently; there is no retry or resume.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from agentbox_protocol.a3_content import ContentError, prepare_pages
from agentbox_protocol.a3_crypto import A3Runtime

from agentbox_runtime.git_staged_selectors import AdmittedStagedRead

_T = TypeVar("_T")


class OpaqueContentPort(Protocol):
    """Bounded single-frame custody; implementation must not buffer unbounded input.

    receive returns one <=24KiB record, or fails. send completion is not a peer
    receipt; an exception or cancellation is permanently uncertain delivery.
    send MUST call check_current after backpressure, immediately before actual
    publication with no intervening await. close synchronously invalidates pending
    I/O. No plaintext method exists.
    """

    async def receive(self) -> bytes: ...
    async def send(self, record: bytes, check_current: Callable[[], None]) -> None: ...
    def close(self) -> None: ...


async def serve_admitted_staged_read(
    admitted: AdmittedStagedRead,
    static_private_key: bytes,
    port: OpaqueContentPort,
    *,
    observed_at_ms: Callable[[], str] = lambda: str(time.time_ns() // 1_000_000),
    on_ready: Callable[[Callable[[], None]], Awaitable[None]] | None = None,
    on_complete: Callable[[Callable[[], None]], Awaitable[None]] | None = None,
    close_port: bool = True,
) -> None:
    """Read/preflight first; then one fresh handshake and one encrypted response.

    Only an owner-issued admitted handle is accepted. The external composition
    must authenticate READY/session/pin sources; test resolvers are not that proof.
    The original expiry never resets at handshake or a new channel instance.
    Native composition may install READY/COMPLETE callbacks; COMPLETE retains
    this same handle until its callback ends. With close_port=False the trusted
    caller must close it in finally after any bounded fixed-error disposition.
    """
    if type(admitted) is not AdmittedStagedRead:
        raise TypeError("sealed Runtime admission is required")
    profile: A3Runtime | None = None
    try:
        admitted.check()
        expiry_ns = admitted.expires_ns
        observation = await admitted.read()
        admitted.check()
        context = admitted.context
        # All capacity checks complete before creating keys or sending anything.
        pages = prepare_pages(context, observation.patch.encode("utf-8"), observed_at_ms())
        admitted.check()

        # Millisecond floor is conservative: never extends original nanosecond expiry.
        def clock() -> int:
            return time.monotonic_ns() // 1_000_000

        handshake_started_ns = time.monotonic_ns()
        profile = A3Runtime(
            context,
            static_private_key,
            clock_ms=clock,
            current=lambda: admitted.context,
            deadline_ms=expiry_ns // 1_000_000,
            original_expiry_ns=expiry_ns,
            clock_ns=time.monotonic_ns,
        )
        handshake_deadline_ns = min(expiry_ns, handshake_started_ns + 5_000_000_000)

        handshake_pending = True

        def check() -> None:
            admitted.check()
            assert profile is not None
            profile.check()
            if handshake_pending and time.monotonic_ns() >= handshake_deadline_ns:
                raise ContentError("PATCH_TIMEOUT")

        async def wait(operation: Callable[[], Awaitable[_T]]) -> _T:
            check()
            assert profile is not None
            end = handshake_deadline_ns if handshake_pending else expiry_ns
            remaining = (end - time.monotonic_ns()) / 1_000_000_000
            if remaining <= 0:
                raise ContentError("PATCH_TIMEOUT")

            async def guarded() -> _T:
                # wait_for schedules a new task: recheck inside that task too.
                check()
                result = await operation()
                check()
                return result

            pending = asyncio.create_task(asyncio.wait_for(guarded(), remaining))
            try:
                while not pending.done():
                    # Bounded idle revalidation: revocation does not wait for input.
                    remaining = (end - time.monotonic_ns()) / 1_000_000_000
                    if remaining <= 0:
                        raise ContentError("PATCH_TIMEOUT")
                    await asyncio.wait({pending}, timeout=min(remaining, 0.05))
                    check()
                result = pending.result()
                check()
                return result
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

        async def send(raw: bytes) -> None:
            check()
            await wait(lambda: port.send(raw, check))
            check()

        if on_ready is not None:
            await wait(lambda: on_ready(check))
        initial = await wait(port.receive)
        await send(profile.receive_init(initial))
        confirmation = await wait(port.receive)
        await send(profile.receive_confirm(confirmation))
        handshake_pending = False
        request = await wait(port.receive)
        profile.receive_read(request)
        check()
        for page in pages:
            # Crypto validates complete transcript and original nonce/selector.
            check()
            encrypted = profile.encrypt_record(page)
            await send(encrypted)
            check()
        if on_complete is not None:
            await wait(lambda: on_complete(check))
    finally:
        admitted.close()
        if profile is not None:
            profile.close()
        if close_port:
            port.close()
