"""Process-local custody for exact synthetic bytes, never an S03 source authority.

The single pool budgets owned payload, not Python RSS or secure erasure. Handles
carry metadata only. The sole body consumer is a fixed synchronous test effect;
no reader, loader, callback, hash or body history is exposed.
"""

from __future__ import annotations

import os
import secrets
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Never, SupportsIndex

from agentbox_core.kebui_observation import ConversationScope

from .kebui_admission import (
    MAX_REVISION,
    SYNTHETIC_ADAPTER_PROFILE,
    AdmissionRequest,
    KebuiAdmissionError,
    SyntheticDispatchReceipt,
    _safe_code,
)

if TYPE_CHECKING:
    from .kebui_admission import KebuiTestAdmissionOwner

MAX_BODY_BYTES = 16384
MAX_ENTRIES = 255
MAX_RETAINED_BYTES = MAX_ENTRIES * MAX_BODY_BYTES
MAX_BODY_LEDGER_BYTES = MAX_RETAINED_BYTES + MAX_BODY_BYTES
MAX_VALIDATION_WORKSPACE_BYTES = MAX_BODY_BYTES * 5
_SEAL = object()


class SyntheticContentHandle:
    """Nontransferable opaque handle; its request contains only safe metadata."""

    __slots__ = ("_request", "_seal")

    def __init__(self, request: AdmissionRequest, seal: object) -> None:
        if seal is not _SEAL:
            raise KebuiAdmissionError("content_unavailable")
        self._request = request
        self._seal = seal

    @property
    def request(self) -> AdmissionRequest:
        return self._request

    def __repr__(self) -> str:
        return "<SyntheticContentHandle>"

    def __copy__(self) -> SyntheticContentHandle:
        raise KebuiAdmissionError("content_unavailable")

    def __deepcopy__(self, memo: object) -> SyntheticContentHandle:
        raise KebuiAdmissionError("content_unavailable")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise KebuiAdmissionError("content_unavailable")

    def __init_subclass__(cls) -> None:
        raise KebuiAdmissionError("content_unavailable")


class SyntheticBodyConsumer:
    """Fixed bounded fake effect. Only metadata counters survive consumption."""

    __slots__ = ("calls", "byte_count", "last_body_identity")

    def __init__(self) -> None:
        self.calls = 0
        self.byte_count = 0
        self.last_body_identity: int | None = None

    def _consume(self, body: bytes) -> SyntheticDispatchReceipt:
        # Called only with the registered entry's original immutable object under
        # current-owner + pool. No callback, retained body, or await is allowed.
        if type(body) is not bytes or not 1 <= len(body) <= MAX_BODY_BYTES:
            raise KebuiAdmissionError("content_unavailable")
        if self.calls >= MAX_REVISION or self.byte_count > MAX_REVISION - len(body):
            raise KebuiAdmissionError("capacity")
        self.last_body_identity = id(body)
        self.byte_count += len(body)
        self.calls += 1
        return SyntheticDispatchReceipt("krcp_" + "1" * 32)

    def __init_subclass__(cls) -> None:
        raise KebuiAdmissionError("content_unavailable")


@dataclass(frozen=True, slots=True)
class SyntheticPoolUsage:
    entries: int
    retained_bytes: int
    staging_bytes: int
    validation_workspace_bytes: int
    worker_slots: int


@dataclass(slots=True, repr=False)
class _Entry:
    handle: SyntheticContentHandle
    execution_id: str
    deadline_ns: int
    body: bytes | None
    accepted_once: bool = False
    worker: bool = False
    available: bool = True
    effect_used: bool = False


class _Pool:
    def __init__(self) -> None:
        self.pid = os.getpid()
        self.lock = threading.RLock()
        self.issuer: SyntheticContentIssuer | None = None
        self.entries = 0
        self.retained_bytes = 0
        self.staging_bytes = 0
        self.validation_workspace_bytes = 0
        self.worker_slots = 0


_POOL = _Pool()


def synthetic_pool_usage() -> SyntheticPoolUsage:
    """Bounded metadata diagnostics, without accessing any body or source clock."""
    if os.getpid() != _POOL.pid:
        raise KebuiAdmissionError("content_unavailable")
    with _POOL.lock:
        return SyntheticPoolUsage(
            _POOL.entries,
            _POOL.retained_bytes,
            _POOL.staging_bytes,
            _POOL.validation_workspace_bytes,
            _POOL.worker_slots,
        )


def _valid_utf8(body: bytes) -> bool:
    # A failed decoder may own a second input payload. Return AFTER its handler
    # ends; never attach UnicodeDecodeError.object to a public exception chain.
    valid = False
    try:
        body.decode("utf-8", errors="strict")
        valid = True
    except UnicodeError:
        pass
    return valid


class SyntheticContentIssuer:
    """Explicit trusted-test-root source lease, bound once to one composition.

    The absolute deadline belongs to the synthetic source, not a request or A3
    TTL. Explicit close is required; garbage collection never releases budgets.
    This Python seal is an accidental-miswiring defense, not authentication.
    """

    def __init__(self, *, deadline_ns: int, clock: Callable[[], int]) -> None:
        self._pid = os.getpid()
        self._closed = True
        self._deadline_ns = deadline_ns
        self._clock = clock
        self._floor = 0
        self._admission: KebuiTestAdmissionOwner | None = None
        self._composition: tuple[object, object, object] | None = None
        self._entries: dict[str, _Entry] = {}
        if type(deadline_ns) is not int or not 1 <= deadline_ns <= MAX_REVISION:
            raise KebuiAdmissionError("content_unavailable")
        if self._pid != _POOL.pid:
            raise KebuiAdmissionError("content_unavailable")
        code: str | None = None
        with _POOL.lock:
            if _POOL.issuer is not None:
                code = "busy"
            else:
                now: object = None
                with suppress(Exception):
                    now = clock()
                if type(now) is not int or not 0 <= now < deadline_ns:
                    code = "content_unavailable"
                else:
                    self._floor = now
                    self._closed = False
                    _POOL.issuer = self
        if code is not None:
            raise KebuiAdmissionError(code)

    def __copy__(self) -> SyntheticContentIssuer:
        raise KebuiAdmissionError("content_unavailable")

    def __deepcopy__(self, memo: object) -> SyntheticContentIssuer:
        raise KebuiAdmissionError("content_unavailable")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        raise KebuiAdmissionError("content_unavailable")

    def __init_subclass__(cls) -> None:
        raise KebuiAdmissionError("content_unavailable")

    def _bind(self, admission: KebuiTestAdmissionOwner, current: object, journal: object) -> None:
        with self._locked():
            if self._composition is not None:
                raise KebuiAdmissionError("content_unavailable")
            self._composition = (admission, current, journal)
            self._admission = admission

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if os.getpid() != _POOL.pid or self._pid != _POOL.pid:
            raise KebuiAdmissionError("content_unavailable")
        if not _POOL.lock.acquire(blocking=False):
            raise KebuiAdmissionError("busy")
        try:
            self._check_locked()
            yield
        finally:
            _POOL.lock.release()

    def _check_locked(self) -> None:
        if self._closed or _POOL.issuer is not self or self._pid != os.getpid():
            raise KebuiAdmissionError("content_unavailable")
        now: object = None
        with suppress(Exception):
            now = self._clock()
        if (
            type(now) is not int
            or not 0 <= now <= MAX_REVISION
            or now < self._floor
            or now >= self._deadline_ns
        ):
            self._close_locked()
            raise KebuiAdmissionError("content_unavailable")
        self._floor = now

    def _entry(
        self,
        handle: SyntheticContentHandle,
        admission: KebuiTestAdmissionOwner,
        request: AdmissionRequest,
        execution_id: str,
        *,
        accepted: bool = False,
    ) -> _Entry:
        if (
            type(handle) is not SyntheticContentHandle
            or handle._seal is not _SEAL
            or self._composition is None
            or self._composition[0] is not admission
            or self._composition[1] is not admission._owner
            or self._composition[2] is not admission._journal
        ):
            raise KebuiAdmissionError("content_unavailable")
        entry = self._entries.get(request.request_id)
        if entry is None or entry.handle is not handle or not entry.available or entry.body is None:
            raise KebuiAdmissionError("content_unavailable")
        if entry.handle.request != request or entry.execution_id != execution_id:
            raise KebuiAdmissionError("conflict")
        if entry.deadline_ns != self._deadline_ns or (accepted and not entry.accepted_once):
            raise KebuiAdmissionError("content_unavailable")
        return entry

    def prepare(
        self, request_id: str, scope: ConversationScope, body: bytes
    ) -> SyntheticContentHandle:
        """Issue/refine the same exact binding; capture execution under its guard."""
        result: SyntheticContentHandle | None = None
        success = False
        staged = False
        code = "content_unavailable"
        try:
            if type(body) is not bytes or not 1 <= len(body) <= MAX_BODY_BYTES:
                raise KebuiAdmissionError("invalid_content")
            if self._admission is None:
                raise KebuiAdmissionError("content_unavailable")
            self._reserve_staging(len(body))
            staged = True
            template = AdmissionRequest(
                request_id, scope, SYNTHETIC_ADAPTER_PROFILE, "ksyn_" + "0" * 32
            )
            with self._admission._guard(template) as context:
                self._admission._validate_metadata(template, context)
                with self._locked():
                    result = self._prepare_locked(template, context.execution_id, body)
            success = True
        except Exception as error:
            code = _safe_code(error, "content_unavailable")
        finally:
            if staged:
                with _POOL.lock:
                    _POOL.staging_bytes = 0
        if not success or result is None:
            if result is not None:
                self._discard_prepared(result)
            raise KebuiAdmissionError(code)
        return result

    @staticmethod
    def _reserve_staging(length: int) -> None:
        # A short pool-only reservation precedes (and releases before) entering
        # current-owner. Competing ingress fails BUSY even if its owner guard
        # would otherwise queue behind validation. No reverse nested lock order.
        if os.getpid() != _POOL.pid:
            raise KebuiAdmissionError("content_unavailable")
        if not _POOL.lock.acquire(blocking=False):
            raise KebuiAdmissionError("busy")
        try:
            if _POOL.staging_bytes:
                raise KebuiAdmissionError("busy")
            _POOL.staging_bytes = length
        finally:
            _POOL.lock.release()

    def _prepare_locked(
        self, template: AdmissionRequest, execution_id: str, body: bytes
    ) -> SyntheticContentHandle:
        _POOL.validation_workspace_bytes = MAX_VALIDATION_WORKSPACE_BYTES
        try:
            if not _valid_utf8(body):
                raise KebuiAdmissionError("invalid_content")
            existing = self._entries.get(template.request_id)
            if existing is not None:
                if (
                    existing.handle.request.scope != template.scope
                    or existing.execution_id != execution_id
                    or existing.body != body
                ):
                    raise KebuiAdmissionError("conflict")
                if not existing.available:
                    raise KebuiAdmissionError("content_unavailable")
                return existing.handle
            if (
                _POOL.entries >= MAX_ENTRIES
                or _POOL.retained_bytes + len(body) > MAX_RETAINED_BYTES
            ):
                raise KebuiAdmissionError("capacity")
            request = AdmissionRequest(
                template.request_id,
                template.scope,
                SYNTHETIC_ADAPTER_PROFILE,
                "ksyn_" + secrets.token_hex(16),
            )
            handle = SyntheticContentHandle(request, _SEAL)
            entry = _Entry(handle, execution_id, self._deadline_ns, body)
            self._entries[request.request_id] = entry
            _POOL.entries += 1
            _POOL.retained_bytes += len(body)
            return handle
        finally:
            _POOL.validation_workspace_bytes = 0

    def _reserve_worker(self, entry: _Entry) -> None:
        if entry.worker or _POOL.worker_slots >= MAX_ENTRIES:
            raise KebuiAdmissionError("busy")
        entry.worker = True
        _POOL.worker_slots += 1

    def _accept_witness(self, entry: _Entry) -> None:
        self._check_locked()
        if entry.accepted_once or not entry.available or not entry.worker:
            raise KebuiAdmissionError("content_unavailable")
        entry.accepted_once = True

    def _effect(
        self,
        handle: SyntheticContentHandle,
        admission: KebuiTestAdmissionOwner,
        request: AdmissionRequest,
        execution_id: str,
        consumer: SyntheticBodyConsumer,
    ) -> SyntheticDispatchReceipt:
        # Caller holds current-owner then pool. Recheck clock at the final
        # linearization point, before borrowing the entry's original object.
        self._check_locked()
        entry = self._entry(handle, admission, request, execution_id, accepted=True)
        if entry.effect_used or not entry.worker or type(consumer) is not SyntheticBodyConsumer:
            raise KebuiAdmissionError("content_unavailable")
        entry.effect_used = True
        body = entry.body
        if body is None:
            raise KebuiAdmissionError("content_unavailable")
        return consumer._consume(body)

    def _discard_prepared(self, handle: SyntheticContentHandle) -> None:
        with _POOL.lock:
            entry = self._entries.get(handle.request.request_id)
            if entry is not None and entry.handle is handle and not entry.accepted_once:
                entry.available = False
                self._retire_locked(entry)

    def _revoke(self, handle: SyntheticContentHandle) -> None:
        # Internal cleanup takes only the pool lock and never calls current-owner.
        with _POOL.lock:
            entry = self._entries.get(handle.request.request_id)
            if entry is not None and entry.handle is handle:
                entry.available = False
                if not entry.worker:
                    self._retire_locked(entry)

    def _worker_retired(self, handle: SyntheticContentHandle) -> None:
        with _POOL.lock:
            entry = self._entries.get(handle.request.request_id)
            if entry is None or entry.handle is not handle:
                return
            if entry.worker:
                entry.worker = False
                _POOL.worker_slots -= 1
            if self._closed or not entry.available or not entry.accepted_once:
                self._retire_locked(entry)

    def _retire_locked(self, entry: _Entry) -> None:
        if entry.worker or entry.body is None:
            return
        _POOL.retained_bytes -= len(entry.body)
        _POOL.entries -= 1
        entry.body = None
        entry.available = False
        self._entries.pop(entry.handle.request.request_id, None)

    def _close_locked(self) -> None:
        self._closed = True
        if _POOL.issuer is self:
            _POOL.issuer = None
        for entry in tuple(self._entries.values()):
            entry.available = False
            self._retire_locked(entry)

    def close(self) -> None:
        """Revoke now; a live worker retains its charged payload until retirement.

        This pool-only cleanup never acquires current-owner in reverse order.
        The shared pool lock serializes it with every synchronous body borrow.
        """
        if self._pid != os.getpid() or _POOL.pid != os.getpid():
            raise KebuiAdmissionError("content_unavailable")
        with _POOL.lock:
            self._close_locked()
