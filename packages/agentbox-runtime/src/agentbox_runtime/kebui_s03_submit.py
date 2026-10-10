"""Explicit test-root S03 composition; no production source or route.

One root owns one endpoint/issuer/journal/consumer composition. Cryptographic
readiness never creates authority. Metadata currentness is deliberately separate
from the source clock so a lost/expired body cannot hide a durable UNKNOWN.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Never, SupportsIndex, TypeVar, cast

from agentbox_core.kebui_observation import ConversationScope
from agentbox_protocol.s03_submit import (
    MAX_BODY_BYTES,
    MAX_FRAME_BYTES,
    MAX_U64,
    RUNTIME_PIN,
    S03Error,
    SubmitContext,
    _RuntimeSession,
    build_context,
)
from agentbox_protocol.s03_submit import _safe_code as _s03_code

from .kebui_admission import (
    SYNTHETIC_ADAPTER_PROFILE,
    AdmissionRecord,
    AdmissionRequest,
    KebuiAdmissionError,
    KebuiTestAdmissionOwner,
    SyntheticOwnerContext,
    _safe_code,
    scope_metadata,
)
from .kebui_admission_journal import KebuiAdmissionJournal
from .kebui_content_admission import (
    SyntheticBodyConsumer,
    SyntheticContentHandle,
    SyntheticContentIssuer,
    synthetic_pool_usage,
)

CHANNEL_RESERVATION_BYTES = 1048576
TOMBSTONE_CAPACITY = 255
TOMBSTONE_RESERVED_BYTES = 1024
TOMBSTONE_RESERVATION_BYTES = 261120
PYTHON_COPY_LIMITS = {
    "wire": 10 * 22031,
    "base64": 12 * 21867,
    "ciphertext": 4 * 16400,
    "plaintext": 3 * 16384,
    "oracle": 16384,
    "context": 8 * 739,
    "aad": 8 * 101,
    "fixed": 65536,
}
PYTHON_COPY_SUBTOTAL = sum(PYTHON_COPY_LIMITS.values())
_SEAL = object()
_PROCESS_PID = os.getpid()
_PROCESS_LOCK = threading.RLock()
_LIVE_ROOT: SyntheticS03TestRoot | None = None
# Process-lifetime, bounded, body-free. Failed and closed requests remain spent.
_TOMBSTONES: set[bytes] = set()
_USED_CHANNELS: set[tuple[str, str]] = set()
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class S03Usage:
    channel_reserved_bytes: int
    tombstones: int
    tombstone_reserved_bytes: int
    active_waiters: int
    active_timers: int
    busy: bool


def s03_usage() -> S03Usage:
    if os.getpid() != _PROCESS_PID:
        raise S03Error("s03_revoked")
    with _PROCESS_LOCK:
        root = _LIVE_ROOT
        return S03Usage(
            CHANNEL_RESERVATION_BYTES if root is not None else 0,
            len(_TOMBSTONES),
            len(_TOMBSTONES) * TOMBSTONE_RESERVED_BYTES,
            int(root.deadlines.waiting) if root is not None and hasattr(root, "deadlines") else 0,
            int(root.deadlines.scheduled) if root is not None and hasattr(root, "deadlines") else 0,
            bool(root is not None and root._busy),
        )


class _NoTransfer:
    def __copy__(self) -> Never:
        raise S03Error("s03_unavailable")

    def __deepcopy__(self, memo: object) -> Never:
        raise S03Error("s03_unavailable")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise S03Error("s03_unavailable")


class SyntheticSubmitPermit(_NoTransfer):
    """Opaque, endpoint-bound process-local token. Never a wire field."""

    __slots__ = ("_root", "_endpoint", "_generation", "_spent", "_seal", "_context")

    def __init__(self, root: SyntheticS03TestRoot, endpoint: object, seal: object) -> None:
        if seal is not _SEAL:
            raise S03Error("s03_unavailable")
        self._root = root
        self._endpoint = endpoint
        self._generation = root._generation
        self._spent = False
        self._seal = seal
        self._context = root.context

    def __repr__(self) -> str:
        return "<SyntheticSubmitPermit>"

    def __init_subclass__(cls) -> None:
        raise S03Error("s03_unavailable")


class AdvancingFixtureClock:
    """Fixed synthetic Runtime origin, independent of the Web test clock."""

    def __init__(self) -> None:
        self._origin = time.monotonic_ns()

    def __call__(self) -> int:
        return 100000000000 + time.monotonic_ns() - self._origin


class DeadlineOwner:
    """One handle, one expiry Future, one actually drained IO continuation."""

    def __init__(self, root: SyntheticS03TestRoot, now: int) -> None:
        self._root = root
        self._loop = asyncio.get_running_loop()
        self._thread_id = threading.get_ident()
        self._control_handle: asyncio.Handle | None = None
        self._source_signal_requested = False
        self._cancel_requested = False
        self.expired: asyncio.Future[None] = self._loop.create_future()
        self._handle: asyncio.TimerHandle | None = None
        self._task: asyncio.Future[object] | None = None
        self._target = root._deadline_ns
        self._source_target = True
        self.waiting = False
        self._stopped = False
        self._schedule(now)

    @property
    def scheduled(self) -> bool:
        return self._handle is not None

    def _schedule(self, now: int) -> None:
        if self._handle is not None:
            self._handle.cancel()
        self._handle = self._loop.call_later(max(0, self._target - now) / 1e9, self._wake)

    def handshake(self, now: int) -> None:
        if now > MAX_U64 - 2000000000:
            self._root.revoke_source()
            raise S03Error("s03_revoked")
        self._target = min(self._root._deadline_ns, now + 2000000000)
        self._source_target = self._target == self._root._deadline_ns
        self._schedule(now)

    def check(self, now: int) -> None:
        # Scheduled callbacks can run late; every operation checks the unchanged
        # active target synchronously as well as the original source deadline.
        if self._stopped or self.expired.done():
            raise S03Error("s03_revoked")
        if now >= self._target:
            if now >= self._root._deadline_ns:
                self._root.revoke_source()
            else:
                self._root.close_transport()
                self.expired.set_result(None)
                self._target = self._root._deadline_ns
                self._source_target = True
                self._schedule(now)
            raise S03Error("s03_revoked")

    def ready(self, now: int) -> None:
        self._target = self._root._deadline_ns
        self._source_target = True
        self._schedule(now)

    def fire_for_test(self) -> None:
        """Dispatch the same timer callback after advancing a trusted unit clock."""
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        self._wake()

    def _wake(self) -> None:
        self._handle = None
        if self._stopped:
            return
        now = self._root._read_clock()
        if now is None or now >= self._root._deadline_ns:
            self._root.revoke_source()
        elif now >= self._target:
            self._root.close_transport()
            if not self.expired.done():
                self.expired.set_result(None)
            # Same handle is now only the original source lease timer.
            self._target = self._root._deadline_ns
            self._source_target = True
            self._schedule(now)
        else:
            self._schedule(now)

    def _request_control(self, *, source: bool = False, cancel: bool = False) -> None:
        # One fixed metadata-only cross-thread continuation. In particular a
        # thread guard/revoke race must never call Future.set_result off-loop.
        with self._root._lock:
            self._source_signal_requested |= source
            self._cancel_requested |= cancel
            if threading.get_ident() == self._thread_id:
                self._deliver_control()
            elif self._control_handle is None:
                self._control_handle = self._loop.call_soon_threadsafe(self._deliver_control)

    def _deliver_control(self) -> None:
        with self._root._lock:
            if self._control_handle is not None:
                self._control_handle.cancel()
                self._control_handle = None
            source, cancel = self._source_signal_requested, self._cancel_requested
            self._source_signal_requested = self._cancel_requested = False
            if source:
                if self._handle is not None:
                    self._handle.cancel()
                    self._handle = None
                if not self.expired.done():
                    self.expired.set_result(None)
            if cancel and self._task is not None and not self._task.done():
                self._task.cancel()

    def signal_source(self) -> None:
        self._request_control(source=True)

    async def wait_io(self, operation: Awaitable[_T]) -> _T:
        code: str | None = None
        canceled = False
        result: _T | None = None
        task: asyncio.Future[_T] | None = None
        done: set[asyncio.Future[object]] | None = None
        pending: set[asyncio.Future[object]] | None = None
        if self.waiting or self._stopped:
            if asyncio.iscoroutine(operation):
                operation.close()
            operation = cast(Awaitable[_T], None)
            raise S03Error("s03_busy")
        self.waiting = True
        try:
            if self.expired.done():
                if asyncio.iscoroutine(operation):
                    operation.close()
                raise S03Error("s03_revoked")
            task = asyncio.ensure_future(operation)
            operation = cast(Awaitable[_T], None)
            self._task = cast(asyncio.Future[object], task)
            done, pending = await asyncio.wait(
                (cast(asyncio.Future[object], task), cast(asyncio.Future[object], self.expired)),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self.expired in done:
                code = "s03_revoked"
            else:
                result = task.result()
                now = self._root._check_source()
                if self._root._opened and not self._root._consumed:
                    self.check(now)
        except asyncio.CancelledError:
            canceled = True
        except Exception:
            code = "s03_revoked"
        finally:
            operation = cast(Awaitable[_T], None)
            if task is not None:
                if not task.done():
                    task.cancel()
                with suppress(Exception, asyncio.CancelledError):
                    await task
            self._task = None
            self.waiting = False
            task = None
            if pending is not None:
                pending.clear()
            done = pending = None
        if canceled or code is not None:
            result = None
        if canceled:
            raise asyncio.CancelledError
        if code is not None:
            raise S03Error(code)
        return cast(_T, result)

    def cancel_io(self) -> None:
        self._request_control(cancel=True)

    def stop(self) -> None:
        self._stopped = True
        self.signal_source()
        self.cancel_io()


class _FixedReadiness:
    """Only fixed readiness; the unchanged owner alone invokes its consumer."""

    def __init__(self, root: SyntheticS03TestRoot) -> None:
        self._root = root
        self.consumer = SyntheticBodyConsumer()
        self.entered = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready.set()

    def hold(self) -> None:
        self._ready.clear()

    def release(self) -> None:
        self._ready.set()

    async def dispatch(
        self, request: AdmissionRequest, execution_id: str, handle: SyntheticContentHandle
    ) -> None:
        self.entered.set()
        if request is not handle.request or execution_id != self._root.context.execution_id:
            raise KebuiAdmissionError("owner_unavailable")
        # Source expiry must wake this last await but must not cancel the worker.
        # Its next unchanged owner/pool check creates conservative UNKNOWN.
        with suppress(S03Error):
            await self._root.deadlines.wait_io(self._ready.wait())


class SyntheticS03TestRoot(_NoTransfer):
    """Default-off explicit fixture construction, never a production authority."""

    __test__ = False

    def __init__(self, seal: object = None) -> None:
        if seal is not _SEAL:
            raise S03Error("s03_unavailable")
        self._pid = os.getpid()
        self._endpoint: object = None
        self._lock = threading.RLock()
        self._busy = False
        self._closed = False
        self._source_revoked = False
        self._current_valid = True
        self._generation = 0
        self._floor = 0
        self._session: _RuntimeSession | None = None
        self._permit: SyntheticSubmitPermit | None = None
        self._prepared: SyntheticContentHandle | None = None
        self._submitted = False
        self._opened = False
        self._transport_closed = False
        self._consumed = False
        self._deadline_ns = 0
        self._clock: Callable[[], int] = lambda: 0
        self.deadlines: DeadlineOwner
        self.context: SubmitContext
        self.issuer: SyntheticContentIssuer
        self.journal: KebuiAdmissionJournal
        self.owner: KebuiTestAdmissionOwner
        self.readiness: _FixedReadiness
        self._composition: tuple[object, ...] = ()
        self.original_identity_match = False
        self.decrypted_identity: int | None = None
        self.copy_peaks = dict.fromkeys(PYTHON_COPY_LIMITS, 0)
        self.copy_live = dict.fromkeys(PYTHON_COPY_LIMITS, 0)

    @classmethod
    def create_for_test(
        cls,
        *,
        directory: Path,
        endpoint: object,
        context: object,
        clock: Callable[[], int],
        deadline_ns: int,
        enabled: bool = False,
    ) -> SyntheticS03TestRoot:
        global _LIVE_ROOT
        if cls is not SyntheticS03TestRoot or enabled is not True:
            raise S03Error("s03_unavailable")
        root = cls(_SEAL)
        code: str | None = None
        reserved = False
        # Reserve BEFORE context/pin/key snapshots. Do not hold this lock while
        # acquiring root/current-owner/pool/journal locks.
        with _PROCESS_LOCK:
            if os.getpid() != _PROCESS_PID:
                code = "s03_revoked"
            elif _LIVE_ROOT is not None or len(_TOMBSTONES) >= TOMBSTONE_CAPACITY:
                code = "s03_busy"
            else:
                _LIVE_ROOT = root
                reserved = True
        if code is None:
            try:
                if type(deadline_ns) is not int or not 1 <= deadline_ns <= MAX_U64:
                    raise S03Error("s03_revoked")
                root._deadline_ns = deadline_ns
                root._clock = clock
                now = root._read_clock()
                if now is None or now >= deadline_ns:
                    raise S03Error("s03_revoked")
                root.context = build_context(context)
                if root.context.runtime_pin != RUNTIME_PIN:
                    raise S03Error()
                root._scope = root.context.scope
                root._execution_id = root.context.execution_id
                root._endpoint = endpoint
                root._hold("context", 8 * len(root.context.encoded))
                root._hold("fixed", 65536)
                # A bounded exact metadata key, not a context/body digest.
                tombstone = root.context.encoded[:-32]
                # Exclude channel, source lease, profile: key is scope/execution/request.
                end = len(root.context.encoded) - 32
                for name in ("adapter_profile", "source_lease_id", "channel_id"):
                    value = (
                        SYNTHETIC_ADAPTER_PROFILE
                        if name == "adapter_profile"
                        else getattr(root.context, name)
                    )
                    end -= 2 + len(value)
                tombstone = tombstone[:end]
                if len(tombstone) > TOMBSTONE_RESERVED_BYTES:
                    raise S03Error()
                pair = (root.context.channel_id, root.context.source_lease_id)
                with _PROCESS_LOCK:
                    if tombstone in _TOMBSTONES or any(
                        pair[0] == item[0] or pair[1] == item[1] for item in _USED_CHANNELS
                    ):
                        raise S03Error("s03_revoked")
                    _TOMBSTONES.add(tombstone)
                    _USED_CHANNELS.add(pair)
                root.journal = KebuiAdmissionJournal.initialize_for_test(
                    directory, expected_uid=os.getuid(), expected_gid=os.getgid()
                )
                root.issuer = SyntheticContentIssuer(deadline_ns=deadline_ns, clock=clock)
                root.readiness = _FixedReadiness(root)
                root.owner = KebuiTestAdmissionOwner(
                    root.journal, root, root.issuer, root.readiness, enabled=True
                )
                root._composition = (
                    root.owner,
                    root.issuer,
                    root.journal,
                    root.readiness,
                    root.readiness.consumer,
                )
                root._permit = SyntheticSubmitPermit(root, endpoint, _SEAL)
                root.deadlines = DeadlineOwner(root, now)
            except Exception as error:
                code = _s03_code(error) if type(error) is S03Error else "s03_unavailable"
        context = None
        if code is not None:
            root._construction_cleanup()
            if reserved:
                with _PROCESS_LOCK:
                    if _LIVE_ROOT is root:
                        _LIVE_ROOT = None
            raise S03Error(code)
        return root

    def _construction_cleanup(self) -> None:
        for name in ("issuer", "journal"):
            item = getattr(self, name, None)
            if item is not None:
                with suppress(Exception):
                    item.close()
        self._composition = ()
        if hasattr(self, "context"):
            self.context._retire()
        self._closed = True
        self._clock = lambda: 0
        self.copy_live = dict.fromkeys(PYTHON_COPY_LIMITS, 0)

    def __init_subclass__(cls) -> None:
        raise S03Error("s03_unavailable")

    @property
    def consumer(self) -> SyntheticBodyConsumer:
        return self.readiness.consumer

    @property
    def permit(self) -> SyntheticSubmitPermit:
        if self._permit is None:
            raise S03Error("s03_unavailable")
        return self._permit

    @property
    def state(self) -> str:
        return (
            self._session.state
            if self._session is not None
            else ("CLOSED" if self._transport_closed else "NEW")
        )

    @property
    def pool_drained(self) -> bool:
        usage = synthetic_pool_usage()
        return not any(
            (
                usage.entries,
                usage.retained_bytes,
                usage.staging_bytes,
                usage.validation_workspace_bytes,
                usage.worker_slots,
            )
        )

    def _hold(self, category: str, amount: int) -> None:
        if not 0 <= amount <= PYTHON_COPY_LIMITS[category]:
            raise S03Error("s03_busy")
        self.copy_live[category] = amount
        self.copy_peaks[category] = max(self.copy_peaks[category], amount)

    def _read_clock(self) -> int | None:
        now: object = None
        if self._source_revoked or self._pid != os.getpid() or os.getpid() != _PROCESS_PID:
            return None
        with suppress(Exception):
            now = self._clock()
        if type(now) is not int or not 0 <= now <= MAX_U64 or now < self._floor:
            return None
        self._floor = now
        return now

    def _check_source(self) -> int:
        now = self._read_clock()
        if now is None or now >= self._deadline_ns:
            self.revoke_source()
            raise S03Error("s03_revoked")
        return now

    @contextmanager
    def guard(self, scope: ConversationScope) -> Iterator[SyntheticOwnerContext]:
        # Deliberately NO source-clock/body checks. Metadata survives their loss.
        with self._lock:
            if (
                self._pid != os.getpid()
                or not self._current_valid
                or self._scope != self.context.scope
                or self._execution_id != self.context.execution_id
                or scope != self.context.scope
            ):
                self._current_valid = False
                raise KebuiAdmissionError("owner_unavailable")
            yield SyntheticOwnerContext(self.context.scope, self.context.execution_id)

    def _check_binding(self, endpoint: object) -> None:
        permit = self._permit
        if (
            self._closed
            or self._transport_closed
            or self._pid != os.getpid()
            or type(permit) is not SyntheticSubmitPermit
            or permit._seal is not _SEAL
            or permit._root is not self
            or permit._endpoint is not endpoint
            or endpoint is not self._endpoint
            or permit._generation != self._generation
            or self.context is not permit._context
            or self._composition
            != (self.owner, self.issuer, self.journal, self.readiness, self.consumer)
            or self.owner._owner is not self
            or self.owner._journal is not self.journal
            or self.owner._content is not self.issuer
            or self.owner._dispatch is not self.readiness
        ):
            raise S03Error("s03_revoked")
        now = self._check_source()
        if self._opened and not self._consumed:
            self.deadlines.check(now)

    @contextmanager
    def _flight(self, endpoint: object) -> Iterator[None]:
        # Nonqueueing serial claim precedes current-owner acquisition.
        with _PROCESS_LOCK:
            if _LIVE_ROOT is not self or self._busy:
                raise S03Error("s03_busy")
            self._busy = True
        try:
            with self.guard(self.context.scope):
                self._check_binding(endpoint)
                yield
        finally:
            with _PROCESS_LOCK:
                self._busy = False

    def open(self, endpoint: object) -> None:
        code: str | None = None
        try:
            with self._flight(endpoint):
                if self._opened:
                    raise S03Error("s03_revoked")
                self._opened = True
                now = self._check_source()
                self.deadlines.handshake(now)
                self._session = _RuntimeSession(self.context)
        except Exception as error:
            code = _s03_code(error) if type(error) is S03Error else "s03_revoked"
        if code is not None:
            if code != "s03_busy":
                self.close_transport()
            raise S03Error(code)

    def _charge_ingress(self, raw: object) -> None:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_FRAME_BYTES:
            raise S03Error()
        # Conservative copy-class upper bounds include regex captures, bounded
        # b64 validation, primitive temporaries and the caller's framed record.
        self._hold("wire", 10 * len(raw))
        self._hold("base64", 12 * min(21867, len(raw)))
        self._hold("ciphertext", 4 * min(16400, len(raw)))
        self._hold("aad", 8 * 101)

    def _clear_ingress(self) -> None:
        for category in ("wire", "base64", "ciphertext", "plaintext", "oracle", "aad"):
            self._hold(category, 0)

    def receive_handshake(self, raw: object, endpoint: object) -> bytes:
        result = None
        code = "s03_invalid"
        owned = False
        try:
            if not self._opened:
                self.open(endpoint)
            with self._flight(endpoint):
                owned = True
                self._charge_ingress(raw)
                if self._session is None:
                    raise S03Error("s03_revoked")
                result = self._session.receive_handshake(raw)
                now = self._check_source()
                self.deadlines.check(now)
                if self._session.state == "READY_SENT":
                    self.deadlines.ready(now)
        except Exception as error:
            code = _s03_code(error) if type(error) is S03Error else "s03_revoked"
            result = None
        finally:
            raw = None
            if owned:
                self._clear_ingress()
        if result is None:
            if code != "s03_busy":
                self.close_transport()
            raise S03Error(code)
        return result

    def receive_submit_and_prepare(
        self,
        raw: object,
        endpoint: object,
        *,
        oracle_case: str | None = None,
    ) -> SyntheticContentHandle:
        """Synchronous only; original decrypt bytes alias the unchanged issuer."""
        handle = None
        body = None
        code = "s03_invalid"
        admission_code: str | None = None
        owned = False
        try:
            with self._flight(endpoint):
                owned = True
                self._charge_ingress(raw)
                if self._permit is None or self._permit._spent or self._session is None:
                    raise S03Error("s03_revoked")
                self._permit._spent = True
                body = self._session._decrypt_submit(raw)
                self._hold("plaintext", 3 * len(body))
                self._check_source()
                # Final exact execution/scope guarded by the same reentrant lock;
                # the nested issuer.prepare guard must still see the frozen ID.
                handle = self.issuer.prepare(self.context.request_id, self.context.scope, body)
                self.decrypted_identity = id(body)
                if oracle_case is not None:
                    self._hold("oracle", MAX_BODY_BYTES)
                    self.original_identity_match = _matches_oracle(body, oracle_case)
                    if not self.original_identity_match:
                        raise S03Error()
                else:
                    # No oracle was requested; do not claim byte equality from
                    # successful cryptography or an object identity alone.
                    self.original_identity_match = False
                self._prepared = handle
                self._consumed = True
        except Exception as error:
            if type(error) is KebuiAdmissionError:
                admission_code = _safe_code(error, "content_unavailable")
            elif type(error) is S03Error:
                code = _s03_code(error)
        finally:
            body = raw = None
            if owned or code != "s03_busy":
                self.close_transport()
            if owned:
                self._clear_ingress()
        if handle is None or not self._consumed:
            if handle is not None:
                self.issuer._discard_prepared(handle)
                handle = None
            if admission_code is not None:
                raise KebuiAdmissionError(admission_code)
            raise S03Error(code)
        return handle

    async def submit_prepared(self, handle: SyntheticContentHandle) -> AdmissionRecord:
        # Only handle and metadata cross the first await. No raw/body parameter.
        if (
            type(handle) is not SyntheticContentHandle
            or handle is not self._prepared
            or self._submitted
        ):
            raise S03Error("s03_revoked")
        task = asyncio.current_task()
        if (task is not None and task.cancelling()) or self._source_revoked:
            self.issuer._discard_prepared(handle)
            self._prepared = None
            raise S03Error("s03_revoked")
        self._submitted = True
        self._prepared = None
        return await self.owner.submit(handle.request, handle)

    def close_transport(self) -> None:
        # Root guard -> short lane lock. This never takes the owner guard inside
        # a pool lock and never closes the source merely for normal EOF/consume.
        with self._lock:
            self._transport_closed = True
            if self._session is not None:
                self._session.close()
                self._session = None
            if hasattr(self, "deadlines") and not self._consumed:
                self.deadlines.cancel_io()

    def revoke_source(self) -> None:
        with self._lock:
            self._source_revoked = True
            self._generation += 1
            self.close_transport()
            if hasattr(self, "issuer"):
                self.issuer.close()
            if hasattr(self, "deadlines"):
                self.deadlines.signal_source()

    def replace_current_for_test(
        self,
        *,
        scope: ConversationScope | None = None,
        execution_id: str | None = None,
    ) -> None:
        with self._lock:
            if scope is not None:
                self._scope = scope
            if execution_id is not None:
                self._execution_id = execution_id
            self._current_valid = False
            self.revoke_source()

    async def aclose(self) -> None:
        global _LIVE_ROOT
        self.revoke_source()
        self.deadlines.stop()
        await self.owner.wait_for_idle()
        # Any external IO holder keeps the whole reservation until it drains.
        task = self.deadlines._task
        if task is not None:
            with suppress(Exception, asyncio.CancelledError):
                await task
        if self.deadlines.waiting:
            # The wrapper resumes after its child; one finite event-loop turn.
            await asyncio.sleep(0)
        if (
            self.deadlines.waiting
            or self.deadlines._control_handle is not None
            or self._busy
            or not self.pool_drained
        ):
            raise S03Error("s03_busy")
        self.journal.close()
        self._closed = True
        self._permit = None
        self._prepared = None
        self._clock = lambda: 0
        self.context._retire()
        self.copy_live = dict.fromkeys(PYTHON_COPY_LIMITS, 0)
        with _PROCESS_LOCK:
            if _LIVE_ROOT is self:
                _LIVE_ROOT = None

    def recovery_catalog(self, scenario: str, request: AdmissionRequest) -> dict[str, object]:
        return _make_catalog(self, scenario, request)


def _matches_oracle(body: bytes, case: str) -> bool:
    # Fixed synthetic test oracle only. No arbitrary reader/callback/body API.
    if case == "minimum":
        return body == b"x"
    if case == "ascii_16k":
        return body == b"x" * 16384
    if case == "nul_16k":
        return body == b"\x00" * 16384
    if case == "utf8_4byte_16k":
        return body == b"\xf0\x9f\x98\x80" * 4096
    return body == {
        "bom": b"\xef\xbb\xbftext",
        "quotes_backslashes": b'"\\',
        "crlf": b"a\r\n",
        "lf": b"a\n",
        "decomposed": b"e\xcc\x81",
        "composed": b"\xc3\xa9",
        "mixed_canary": b"synthetic S03\r\n\x00",
    }.get(case)


def _make_catalog(
    root: SyntheticS03TestRoot,
    scenario: str,
    request: AdmissionRequest,
) -> dict[str, object]:
    result = None
    try:
        if type(scenario) is not str or not re.fullmatch("[a-z_]{1,64}", scenario):
            raise S03Error()
        if type(request) is not AdmissionRequest or request.scope != root.context.scope:
            raise S03Error()
        if request.request_id != root.context.request_id or root.owner.read(request) is None:
            raise S03Error()
        directory = root.journal._directory
        details = directory.stat()
        result = {
            "schema": "s03-synthetic-recovery-v1",
            "scenario": scenario,
            "directory": str(directory.resolve()),
            "device": details.st_dev,
            "inode": details.st_ino,
            "scope": scope_metadata(request.scope),
            "execution_id": root.context.execution_id,
            "request_id": request.request_id,
            "content_admission_ref": request.content_admission_ref,
            "channel_id": root.context.channel_id,
            "source_lease_id": root.context.source_lease_id,
        }
        if len(json.dumps(result, separators=(",", ":"), ensure_ascii=True).encode("ascii")) > 4096:
            result = None
    except Exception:
        pass
    if result is None:
        raise S03Error("s03_unavailable")
    return result


class _RecoveryCurrent:
    def __init__(self, context: SubmitContext) -> None:
        self.context = context
        self.pid = os.getpid()
        self.lock = threading.RLock()

    @contextmanager
    def guard(self, scope: ConversationScope) -> Iterator[SyntheticOwnerContext]:
        with self.lock:
            if self.pid != os.getpid() or scope != self.context.scope:
                raise KebuiAdmissionError("owner_unavailable")
            yield SyntheticOwnerContext(scope, self.context.execution_id)


class SyntheticS03Recovery(_NoTransfer):
    """Trusted bounded catalog reopening, metadata only and never a new source."""

    def __init__(self, seal: object = None) -> None:
        if seal is not _SEAL:
            raise S03Error("s03_unavailable")
        self.owner: KebuiTestAdmissionOwner
        self.request: AdmissionRequest
        self.journal: KebuiAdmissionJournal

    @classmethod
    def open(
        cls,
        catalog: object,
        *,
        directory: Path,
        context: object,
        scenario: str,
    ) -> SyntheticS03Recovery:
        recovery = cls(_SEAL)
        good = False
        try:
            if type(catalog) is not dict or catalog.keys() != {
                "schema",
                "scenario",
                "directory",
                "device",
                "inode",
                "scope",
                "execution_id",
                "request_id",
                "content_admission_ref",
                "channel_id",
                "source_lease_id",
            }:
                raise S03Error()
            if any(type(key) is not str for key in catalog):
                raise S03Error()
            if type(scenario) is not str or not re.fullmatch("[a-z_]{1,64}", scenario):
                raise S03Error()
            limits = {
                "schema": 32,
                "scenario": 64,
                "directory": 1024,
                "execution_id": 37,
                "request_id": 37,
                "content_admission_ref": 37,
                "channel_id": 38,
                "source_lease_id": 38,
            }
            if any(
                type(catalog[key]) is not str or not 1 <= len(catalog[key]) <= maximum
                for key, maximum in limits.items()
            ):
                raise S03Error()
            if any(
                type(catalog[key]) is not int or not 0 <= catalog[key] <= MAX_U64
                for key in ("device", "inode")
            ):
                raise S03Error()
            scope = catalog["scope"]
            if type(scope) is not dict or len(scope) != 16:
                raise S03Error()
            if any(
                type(key) is not str or type(value) is not str or len(value) > 64
                for key, value in scope.items()
            ):
                raise S03Error()
            bound = build_context(context)
            if (
                catalog["schema"] != "s03-synthetic-recovery-v1"
                or catalog["scenario"] != scenario
                or type(catalog["directory"]) is not str
                or len(catalog["directory"]) > 1024
                or catalog["directory"] != str(directory.resolve())
                or type(catalog["device"]) is not int
                or type(catalog["inode"]) is not int
                or catalog["device"] != directory.stat().st_dev
                or catalog["inode"] != directory.stat().st_ino
                or catalog["scope"] != scope_metadata(bound.scope)
                or any(
                    catalog[name] != getattr(bound, name)
                    for name in ("execution_id", "request_id", "channel_id", "source_lease_id")
                )
            ):
                raise S03Error()
            if (
                len(json.dumps(catalog, separators=(",", ":"), ensure_ascii=True).encode("ascii"))
                > 4096
            ):
                raise S03Error()
            recovery.request = AdmissionRequest(
                bound.request_id,
                bound.scope,
                SYNTHETIC_ADAPTER_PROFILE,
                catalog["content_admission_ref"],
            )
            recovery.journal = KebuiAdmissionJournal.open_existing(
                directory,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                recover=True,
            )
            current = _RecoveryCurrent(bound)
            # No issuer; fixed dispatch is absent from all callable paths.
            recovery.owner = KebuiTestAdmissionOwner(
                recovery.journal,
                current,
                None,
                cast(_FixedReadiness, None),
                enabled=True,
            )
            if recovery.owner.read(recovery.request) is None:
                raise S03Error()
            good = True
        except Exception:
            pass
        catalog = context = None
        if not good:
            if hasattr(recovery, "journal"):
                recovery.journal.close()
            raise S03Error("s03_unavailable")
        return recovery

    def read(self) -> AdmissionRecord | None:
        return self.owner.read(self.request)

    def close(self) -> None:
        self.journal.close()

    def __init_subclass__(cls) -> None:
        raise S03Error("s03_unavailable")
