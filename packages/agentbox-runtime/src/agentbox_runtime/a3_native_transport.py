"""Native A3 consumer of trusted connected descriptors; default uncomposed.

One existing selector owner, lifecycle and nonce ledger serve every bundle. Only
its event loop touches handles/crypto. A bounded command-reader thread dispatches
one command at a time; a dedicated socket answers fresh API currentness RPCs.
There are no listeners, connector paths, production keys or WAW key fallbacks.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import hashlib
import os
import secrets
import socket
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from typing import Protocol, cast

from agentbox_core.a3_native_io import NATIVE_IO_DEADLINE, NativeChannel, deadline_after
from agentbox_protocol.a3_admission import A3CurrentAdmission
from agentbox_protocol.a3_content import ERROR_CODES, ContentError
from agentbox_protocol.a3_transport import NativeFrame, NativeKind, facts_digest, facts_from_wire

from agentbox_runtime.a3_content_session import serve_admitted_staged_read
from agentbox_runtime.git_staged_reader import GitStagedPatchReader
from agentbox_runtime.git_staged_selectors import GitStagedSelectors, StagedSelectorContext
from agentbox_runtime.waw_lifecycle import WAWLifecycleRegistry, WAWProjectBinding
from agentbox_runtime.waw_peer_authority import WAWPeerLease
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor

_OPERATION: contextvars.ContextVar[A3NativeReservation | None] = contextvars.ContextVar(
    "a3_native_operation", default=None
)


class A3NativeKeyPort(Protocol):
    """Trusted bounded A3-only private-key borrow, never a loader or enrollment.

    Composition binds this borrow to the supplied host/revision/admission facts.
    The owner accepts exactly 32 bytes and releases the context on every outcome.
    An implementation must not acquire WAW key material as a fallback.
    """

    def borrow(self, facts: A3CurrentAdmission) -> AbstractContextManager[bytes]: ...


class A3NativeReadOwner:
    def __init__(
        self,
        reader: GitStagedPatchReader,
        lifecycle: WAWLifecycleRegistry,
        executor: WAWSupervisorExecutor,
        key_port: A3NativeKeyPort,
    ) -> None:
        if (
            type(lifecycle) is not WAWLifecycleRegistry
            or type(executor) is not WAWSupervisorExecutor
            or lifecycle.peer_authority is None
            or not callable(getattr(key_port, "borrow", None))
        ):
            raise ContentError("PATCH_UNAVAILABLE_CONFIG")
        self._loop = asyncio.get_running_loop()
        self._thread_id = threading.get_ident()
        self._lifecycle, self._executor, self._key = lifecycle, executor, key_port
        self._closed = False
        self._bundles: set[A3NativeReservation] = set()
        self.selectors = GitStagedSelectors(reader, context=self._resolve)
        lifecycle.replace_content_selector_owner(self.selectors)

    def _on_loop(self) -> None:
        if threading.get_ident() != self._thread_id:
            raise ContentError("PATCH_REVOKED")
        try:
            if asyncio.get_running_loop() is not self._loop:
                raise ContentError("PATCH_REVOKED")
        except RuntimeError:
            raise ContentError("PATCH_REVOKED") from None

    def reserve(self) -> A3NativeReservation:
        """Reserve BEFORE assembling descriptors; the sole cap includes partial bundles."""
        self._on_loop()
        if self._closed:
            raise ContentError("PATCH_REVOKED")
        if len(self._bundles) >= 4:
            raise ContentError("PATCH_UNAVAILABLE_BUSY")
        reservation = A3NativeReservation(self)
        self._bundles.add(reservation)
        return reservation

    @property
    def active_bundles(self) -> int:
        return len(self._bundles)

    def close(self) -> None:
        self._on_loop()
        self._closed = True
        self.selectors.close()
        for bundle in tuple(self._bundles):
            bundle.close()

    async def wait_closed(self) -> None:
        await asyncio.gather(*(bundle.wait_closed() for bundle in tuple(self._bundles)))

    def _resolve(self, project_id: str, scope: bytes) -> StagedSelectorContext | None:
        self._on_loop()
        operation = _OPERATION.get()
        if self._closed or operation is None or operation._owner is not self:
            return None
        try:
            facts = operation.current()
            binding = self._executor.content_project_binding(project_id)
            if (
                facts.project_id != project_id
                or facts.session_scope != scope
                or facts.runtime_epoch != self._executor.runtime_epoch
                or binding is None
            ):
                return None
            expected = WAWProjectBinding(
                facts.project_id,
                facts.relative_key,
                facts.project_revision,
                facts.binding_revision,
                facts.binding_digest,
                facts.runtime_host_installation_id,
                facts.runtime_host_installation_revision,
            )
            peer = operation._leases[0].runtime_peer
            if binding != expected or not self._lifecycle.content_project_current(
                binding,
                facts.runtime_epoch,
                peer,
                self.selectors,
            ):
                return None
            return StagedSelectorContext(binding, facts.runtime_epoch, scope)
        except Exception:
            return None


class A3NativeReservation:
    """One counted bundle, including incomplete handshakes and cleanup in progress."""

    def __init__(self, owner: A3NativeReadOwner) -> None:
        self._owner = owner
        self._deadline = deadline_after(1)
        self._closed = False
        self._accepted = False
        self._leases: list[WAWPeerLease] = []
        self._channels: dict[str, NativeChannel] = {}
        self._thread: threading.Thread | None = None
        self._work: asyncio.Task[None] | None = None
        self._command_task: asyncio.Task[tuple[NativeKind, dict[str, object]]] | None = None
        self._dispatch: concurrent.futures.Future[tuple[NativeKind, dict[str, object]]] | None = (
            None
        )
        self._cleanup = asyncio.Event()
        self._timer = owner._loop.call_later(1, self.close)
        self._facts: A3CurrentAdmission | None = None
        self._digest: str | None = None
        self._bundle_id: str | None = None
        self._port: _NativeOpaquePort | None = None
        self._last_live = -1
        self._last_challenge: str | None = None
        self._current_lock = threading.Lock()

    @property
    def closed(self) -> bool:
        return self._closed

    def accept(
        self, command: socket.socket, opaque: socket.socket, currentness: socket.socket
    ) -> A3NativeReservation:
        """Take custody of three fresh sockets; no descriptor or path comes from Web input."""
        self._owner._on_loop()
        sockets = (command, opaque, currentness)
        try:
            if (
                self._closed
                or self._accepted
                or time.monotonic_ns() >= self._deadline
                or len({sock.fileno() for sock in sockets}) != 3
                or len(
                    {
                        (os.fstat(sock.fileno()).st_dev, os.fstat(sock.fileno()).st_ino)
                        for sock in sockets
                    }
                )
                != 3
            ):
                raise ContentError("PATCH_REVOKED")
            self._accepted = True
            authority = self._owner._lifecycle.peer_authority
            assert authority is not None
            for sock in sockets:
                lease = authority.observe_stream_socket(sock)
                if lease is None:
                    raise ContentError("PATCH_REVOKED")
                self._leases.append(lease)
            identity = self._leases[0].runtime_peer.identity
            epoch = self._leases[0].runtime_peer.api_authority_epoch
            if any(
                lease.runtime_peer.identity is not identity
                or lease.runtime_peer.api_authority_epoch != epoch
                for lease in self._leases
            ):
                raise ContentError("PATCH_REVOKED")
            self._channels = {
                role: NativeChannel(sock, self._check_peer)
                for role, sock in zip(("command", "opaque", "currentness"), sockets, strict=True)
            }
            self._check_peer()
            self._thread = threading.Thread(target=self._run, name="a3-native-command", daemon=True)
            self._thread.start()
            return self
        except BaseException:
            for sock in sockets:
                with suppress(OSError):
                    sock.close()
            self.close()
            raise

    def _check_peer(self) -> None:
        if (
            self._closed
            or self._owner._closed
            or len(self._leases) != 3
            or any(not lease.current() for lease in self._leases)
        ):
            raise ContentError("PATCH_REVOKED")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for channel in self._channels.values():
            channel.close()
        with suppress(RuntimeError):
            self._owner._loop.call_soon_threadsafe(self._cancel_and_reap)

    def _cancel_and_reap(self) -> None:
        self._owner._on_loop()
        self._timer.cancel()
        if self._command_task is None:
            if self._dispatch is not None and not self._dispatch.done():
                self._dispatch.cancel()
        elif not self._command_task.done() and not self._command_task.cancelling():
            self._command_task.cancel()
        if self._work is not None and not self._work.done() and not self._work.cancelling():
            self._work.cancel()
        self._reap()

    def _reap(self) -> None:
        if self._cleanup.is_set():
            return
        if (
            (self._thread is not None and self._thread.is_alive())
            or (self._work is not None and not self._work.done())
            or (self._command_task is not None and not self._command_task.done())
            or any(not channel.shutdown_complete for channel in self._channels.values())
        ):
            self._owner._loop.call_later(0.01, self._reap)
            return
        for lease in self._leases:
            with suppress(Exception):
                lease.close()
        self._leases.clear()
        self._owner._bundles.discard(self)
        self._cleanup.set()

    async def wait_closed(self) -> None:
        await self._cleanup.wait()

    def current(self) -> A3CurrentAdmission:
        """Fresh full-tuple RPC on every resolver call. No positive answer is cached."""
        self._owner._on_loop()
        self._check_peer()
        if _OPERATION.get() is not self or self._facts is None or self._digest is None:
            raise ContentError("PATCH_REVOKED")
        if not self._current_lock.acquire(blocking=False):
            self.close()
            raise ContentError("PATCH_REVOKED")
        try:
            deadline = deadline_after(0.25, cap_ns=self._expiry())
            inherited = NATIVE_IO_DEADLINE.get()
            if inherited is not None:
                deadline = min(deadline, inherited)
            request: dict[str, object] = {
                "facts_digest": self._digest,
                "challenge": secrets.token_hex(16),
            }
            channel = self._channels["currentness"]
            channel.send(NativeKind.CURRENT, request, deadline_ns=deadline)
            frame = channel.receive(frozenset({NativeKind.CURRENT_REPLY}), deadline_ns=deadline)
            expected = {**request, "current": True}
            if frame.payload != expected:
                raise ContentError("PATCH_REVOKED")
            self._check_peer()
            return self._facts
        except BaseException:
            self.close()
            raise
        finally:
            self._current_lock.release()

    def _expiry(self) -> int | None:
        # This is copied once from the admitted handle on its owner loop.
        return self._port.expiry_ns if self._port is not None else None

    def _run(self) -> None:
        """No selector/admitted handle/crypto access occurs on this thread."""
        command = self._channels["command"]
        try:
            hellos: dict[str, dict[str, object]] = {}
            for role, channel in self._channels.items():
                frame = channel.receive(frozenset({NativeKind.HELLO}), deadline_ns=self._deadline)
                payload = cast(dict[str, object], frame.payload)
                if payload["role"] != role:
                    raise ContentError()
                hellos[role] = payload
            first = hellos["command"]
            if any(
                value["bundle_id"] != first["bundle_id"]
                or value["facts_digest"] != first["facts_digest"]
                for value in hellos.values()
            ):
                raise ContentError()
            self._bundle_id = cast(str, first["bundle_id"])
            self._digest = cast(str, first["facts_digest"])
            for role, channel in self._channels.items():
                channel.send(NativeKind.HELLO_ACK, hellos[role], deadline_ns=self._deadline)
            self._owner._loop.call_soon_threadsafe(self._timer.cancel)
            first_frame = command.receive(
                frozenset({NativeKind.OBSERVE, NativeKind.OPEN}), deadline_ns=deadline_after(1)
            )
            payload = cast(dict[str, object], first_frame.payload)
            facts = facts_from_wire(payload["facts"])
            if facts_digest(facts) != self._digest:
                raise ContentError()
            self._facts = facts
            deadline = deadline_after(5 if first_frame.kind is NativeKind.OBSERVE else 1)
            response = self._call(first_frame, deadline)
            command.send(*response, deadline_ns=deadline)
            if first_frame.kind is NativeKind.OBSERVE:
                # API must consume metadata before checker EOF fences its bundle.
                # Only disposition/EOF is legal; there is no second operation.
                command.receive(frozenset({NativeKind.CLOSE}), deadline_ns=deadline_after(1))
                return
            # Idle waiting never renews the authorization or partial-frame deadline.
            while not self._closed:
                command.wait_readable(deadline_after(30, cap_ns=self._expiry()))
                deadline = deadline_after(0.25, cap_ns=self._expiry())
                frame = command.receive(
                    frozenset(
                        {
                            NativeKind.PUBLISH_CHECK,
                            NativeKind.PUBLISHED,
                            NativeKind.LIVE,
                            NativeKind.CLOSE,
                        }
                    ),
                    deadline_ns=deadline,
                )
                if frame.kind is NativeKind.CLOSE:
                    return
                response = self._call(frame, deadline)
                command.send(*response, deadline_ns=deadline)
        except BaseException:
            # Never send arbitrary exception text or any content/selector facts.
            pass
        finally:
            self.close()

    def _call(self, frame: NativeFrame, deadline: int) -> tuple[NativeKind, dict[str, object]]:
        future = asyncio.run_coroutine_threadsafe(self._execute(frame, deadline), self._owner._loop)
        self._dispatch = future
        try:
            remaining = (deadline - time.monotonic_ns()) / 1_000_000_000
            if remaining <= 0:
                raise ContentError("PATCH_TIMEOUT")
            return future.result(timeout=remaining)
        finally:
            if not future.done():
                future.cancel()
            self._dispatch = None

    async def _execute(
        self, frame: NativeFrame, deadline: int
    ) -> tuple[NativeKind, dict[str, object]]:
        self._owner._on_loop()
        self._command_task = asyncio.current_task()
        token = _OPERATION.set(self)
        deadline_token = NATIVE_IO_DEADLINE.set(deadline)
        try:
            self._check_peer()
            payload = cast(dict[str, object], frame.payload)
            assert self._facts is not None
            facts = self._facts
            if frame.kind is NativeKind.OBSERVE:
                observed = await self._owner.selectors.observe(
                    facts.project_id, facts.session_scope
                )
                self.current()
                return NativeKind.METADATA, {
                    "snapshot_sha256": observed.snapshot_sha256,
                    "entries": [
                        {
                            "path": entry.path,
                            "kind": entry.kind,
                            "side": entry.side,
                            "selection_id": entry.selection_id,
                            "unavailable_code": entry.unavailable_code,
                        }
                        for entry in observed.entries
                    ],
                }
            if frame.kind is NativeKind.OPEN:
                if self._work is not None:
                    raise ContentError()
                NATIVE_IO_DEADLINE.set(None)
                self._work = asyncio.create_task(
                    self._serve(
                        cast(str, payload["selection_id"]),
                        bytes.fromhex(cast(str, payload["request_nonce"])),
                    )
                )
                return NativeKind.OWNED, {}
            port = self._port
            if port is None or port.guard is None:
                raise ContentError("PATCH_REVOKED")
            port.guard()
            if frame.kind is NativeKind.LIVE:
                sequence = cast(int, payload["observation_sequence"])
                challenge = cast(str, payload["challenge"])
                if sequence != self._last_live + 1 or challenge == self._last_challenge:
                    raise ContentError()
                self._last_live, self._last_challenge = sequence, challenge
                return NativeKind.LIVE_REPLY, payload
            if payload != port.pending or port.pending is None:
                raise ContentError()
            if frame.kind is NativeKind.PUBLISH_CHECK and not port.checked:
                port.checked = True
                return NativeKind.CHECKED, payload
            if frame.kind is NativeKind.PUBLISHED and port.checked and not port.published.is_set():
                port.published.set()
                return NativeKind.ACK, payload
            raise ContentError()
        finally:
            NATIVE_IO_DEADLINE.reset(deadline_token)
            _OPERATION.reset(token)

    async def _serve(self, selection_id: str, nonce: bytes) -> None:
        assert self._facts is not None
        facts = self._facts
        try:
            async with self._owner.selectors.admit(
                facts.project_id,
                facts.session_scope,
                selection_id,
                nonce,
            ) as admitted:
                port = _NativeOpaquePort(self, admitted.expires_ns)
                self._port = port
                with self._owner._key.borrow(facts) as private:
                    if type(private) is not bytes or len(private) != 32:
                        raise ContentError("PATCH_UNAVAILABLE_CONFIG")
                    await serve_admitted_staged_read(
                        admitted,
                        private,
                        port,
                        on_ready=port.ready,
                        on_complete=port.complete,
                        close_port=False,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = getattr(error, "code", str(error) if type(error) is ContentError else None)
            if code not in ERROR_CODES:
                code = "PATCH_REVOKED"
            if not self._closed and (self._port is None or self._port.guard is None):
                with suppress(Exception):
                    disposition = deadline_after(1)
                    await self._channels["opaque"].asend(
                        NativeKind.ERROR, {"code": code}, deadline_ns=disposition
                    )
                    # Let API publish the fixed error before observing EOF. This
                    # never revives admission and adds no new wire ACK/authority.
                    while not self._closed and time.monotonic_ns() < disposition:
                        await asyncio.sleep(0.01)
        finally:
            self.close()


class _NativeOpaquePort:
    def __init__(self, bundle: A3NativeReservation, expiry_ns: int) -> None:
        self.bundle = bundle
        self.expiry_ns = expiry_ns
        self.guard: Callable[[], None] | None = None
        self.pending: dict[str, object] | None = None
        self.checked = False
        self.published = asyncio.Event()
        self.sequence = 0

    def close(self) -> None:
        self.bundle.close()

    async def ready(self, check: Callable[[], None]) -> None:
        self.guard = check
        check()
        await self.bundle._channels["opaque"].asend(
            NativeKind.READY, {}, deadline_ns=deadline_after(1, cap_ns=self.expiry_ns), guard=check
        )

    async def receive(self) -> bytes:
        assert self.guard is not None
        frame = await self.bundle._channels["opaque"].areceive(
            frozenset({NativeKind.RECORD}),
            deadline_ns=deadline_after(1, cap_ns=self.expiry_ns),
            guard=self.guard,
        )
        return cast(bytes, frame.payload)

    async def send(self, record: bytes, check_current: Callable[[], None]) -> None:
        if self.pending is not None:
            raise ContentError()
        self.sequence += 1
        self.pending = {
            "record_sequence": self.sequence,
            "record_sha256": hashlib.sha256(record).hexdigest(),
        }
        self.checked = False
        self.published.clear()
        deadline = deadline_after(1, cap_ns=self.expiry_ns)
        try:
            await self.bundle._channels["opaque"].asend(
                NativeKind.RECORD, record, deadline_ns=deadline, guard=check_current
            )
            while not self.published.is_set():
                check_current()
                remaining = (deadline - time.monotonic_ns()) / 1_000_000_000
                if remaining <= 0:
                    raise ContentError("PATCH_TIMEOUT")
                await asyncio.sleep(min(remaining, 0.01))
            check_current()
        finally:
            self.pending = None

    async def complete(self, check: Callable[[], None]) -> None:
        check()
        await self.bundle._channels["opaque"].asend(
            NativeKind.COMPLETE,
            {},
            deadline_ns=deadline_after(1, cap_ns=self.expiry_ns),
            guard=check,
        )
        # Keep the original admitted handle, selector slot and close subscription.
        # COMPLETE is a display state, never a new/renewable content lease.
        channel = self.bundle._channels["opaque"]
        await channel.await_readable(self.expiry_ns, guard=check)
        # No additional crypto input is legal in completed display state.
        await channel.areceive(
            frozenset(), deadline_ns=deadline_after(1, cap_ns=self.expiry_ns), guard=check
        )
