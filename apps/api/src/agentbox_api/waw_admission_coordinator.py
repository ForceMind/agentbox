"""Staged encrypted admission over closed, injected asynchronous ports.

This composes real authority, wire validation, durable metadata and bounded
publication. It does not open sockets, launch Runtime, decrypt frames, load keys,
or enable the production WebSocket route. Ports are trusted adapters: receive
must be cancellation-safe and bounded, and Runtime cleanup must fence this exact
connection including any in-flight prepare before attesting PTY closure.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from agentbox_core.waw_tickets import (
    ActiveAttachment,
    AdmissionStage,
    AttachmentAuthority,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
    StagedAttachment,
    TicketAuthorityError,
)
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.waw_wire import (
    ADMISSION_TIMEOUT_NS,
    Leg,
    WireError,
    WireFrame,
    WireSession,
    decode_wire_frame,
    encode_wire_frame,
    forward_wire_frame,
)

from agentbox_api.waw_admission import wire_admission_tuple
from agentbox_api.waw_input_budget import (
    BrowserDelivery,
    InputBudget,
    InputBudgetOwner,
)

_BA, _AB, _AR, _RA = tuple(Leg)
_T = TypeVar("_T")


class AdmissionFailure(RuntimeError):
    """Fixed metadata only; adapter exceptions are never exposed or chained."""

    def __init__(self, code: str = "PROTOCOL_INVALID", close_code: int = 4400) -> None:
        allowed = {
            "PROTOCOL_INVALID": 4400,
            "ATTACHMENT_NOT_READY": 4400,
            "ATTACHMENT_STALE": 4403,
            "ATTACHMENT_TICKET_INVALID": 4403,
            "ATTACHMENT_TICKET_REPLAYED": 4403,
            "ATTACHMENT_TICKET_EXPIRED": 4403,
            "ATTACHMENT_TICKET_UNAVAILABLE": 4429,
            "WORKSPACE_WRITER_BUSY": 4409,
            "ADMISSION_TIMEOUT": 4408,
            "ADMITTED_DELIVERY_FAILED": 1013,
            "OUTPUT_BACKPRESSURE": 1013,
            "RUNTIME_UNAVAILABLE": 1013,
        }
        if code not in allowed or close_code != allowed[code]:
            code, close_code = "PROTOCOL_INVALID", 4400
        self.code, self.close_code = code, close_code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class RuntimePrepareRequest:
    claims: AttachmentTuple
    runtime_epoch: str
    connection_id: object = field(repr=False)
    resume_cursor: str | None = None
    previous_runtime_epoch: str | None = None


@dataclass(frozen=True, repr=False)
class RuntimePrepared:
    claims: AttachmentTuple
    runtime_epoch: str
    connection_id: object = field(repr=False)
    capability: str = field(repr=False)


@dataclass(frozen=True, repr=False)
class RuntimeCleanupRequest:
    claims: AttachmentTuple
    runtime_epoch: str
    connection_id: object = field(repr=False)
    # Fixed INTERNAL_BOUNDED close, or None before a stream hello exists.
    close_frame: bytes | None = field(repr=False)


@dataclass(frozen=True, repr=False)
class RuntimeCleanupProof:
    claims: AttachmentTuple
    runtime_epoch: str
    connection_id: object = field(repr=False)
    result: str
    cleanup_state: str


class AdmissionRuntimePort(Protocol):
    """One provenance-verified, identity-bound Runtime connection, never a shell."""

    @property
    def connection_id(self) -> object: ...

    async def prepare(self, request: RuntimePrepareRequest) -> RuntimePrepared: ...

    async def send(self, frame: bytes) -> None: ...

    async def receive(self) -> bytes: ...

    async def close_and_cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupProof: ...

    def abort(self) -> None: ...


class AdmissionBrowserPort(Protocol):
    """Bounded complete ABWS messages; native WebSocket controls belong to R8."""

    async def receive(self) -> BrowserDelivery: ...

    async def send_key_frame(self, frame: bytes) -> None: ...

    def close(self, code: int) -> None: ...


class AdmissionRevalidator(Protocol):
    """Synchronous current Session/expiry/scope/workspace/epoch authorization.

    A production adapter must check current authoritative state, not compare a
    cached copy of the original arguments. False/exception permanently fences
    the attempt; it cannot later be reopened by a positive Runtime response.
    """

    def current(self, claims: AttachmentTuple, context: AuthenticatedAttachmentContext) -> bool: ...


class AdmissionAuditAction(StrEnum):
    PREPARED = "workspace.attachment_prepared"
    ADMITTED = "workspace.attachment_admitted"
    DETACHED = "workspace.attachment_detached"


@dataclass(frozen=True)
class AdmissionAuditEvent:
    """Closed persisted metadata: no digest, context hash, bearer or payload."""

    action: AdmissionAuditAction
    workspace_id: str
    attachment_id: str
    generation: int
    runtime_epoch: str
    api_authority_epoch: int
    reason_code: str | None


class AdmissionAuditPort(Protocol):
    """Return only after the fixed event is durable; bounded failure is mandatory."""

    async def persist(self, event: AdmissionAuditEvent) -> None: ...


@dataclass(frozen=True, repr=False)
class _PendingPermit:
    source: str


class PendingAdmissionBudget:
    """128 pending API handshakes, eight per trusted source, before allocation."""

    def __init__(self, *, maximum: int = 128, per_source: int = 8) -> None:
        if not 1 <= maximum <= 128 or not 1 <= per_source <= 8:
            raise ValueError("admission limits are invalid")
        self._maximum, self._per_source = maximum, per_source
        self._permits: dict[int, _PendingPermit] = {}
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._permits)

    def acquire(self, source: str) -> _PendingPermit:
        with self._lock:
            if (
                type(source) is not str
                or not 1 <= len(source) <= 128
                or len(self._permits) >= self._maximum
                or sum(item.source == source for item in self._permits.values()) >= self._per_source
            ):
                raise AdmissionFailure("ATTACHMENT_TICKET_UNAVAILABLE", 4429)
            permit = _PendingPermit(source)
            self._permits[id(permit)] = permit
            return permit

    def release(self, permit: _PendingPermit) -> None:
        with self._lock:
            if self._permits.get(id(permit)) is permit:
                del self._permits[id(permit)]


class BoundedAdmissionQueue:
    """Complete-frame quarantine and publication, with authority-gated readers.

    No output is returned before the complete ADMITTED frame. The shared 64 KiB
    cap includes every header and GAP, plus the quarantined ADMITTED frame.
    R8 drains this queue after run() before starting its ACTIVE relay.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._authority: AttachmentAuthority | None = None
        self._handle: StagedAttachment | None = None
        self._session: WireSession | None = None
        self._clock: Callable[[], int] = time.monotonic_ns
        self._admitted: bytes | None = None
        self._output: list[WireFrame] = []
        self._visible: deque[bytes] = deque()
        self._size = 0
        self._released = self._closed = False

    def bind(
        self,
        authority: AttachmentAuthority,
        handle: StagedAttachment,
        session: WireSession,
        clock: Callable[[], int],
    ) -> None:
        with self._lock:
            if self._handle is not None or self._closed:
                raise AdmissionFailure()
            self._authority, self._handle, self._session, self._clock = (
                authority,
                handle,
                session,
                clock,
            )

    def quarantine(self, admitted: bytes) -> None:
        with self._lock:
            if self._admitted is not None or self._closed or len(admitted) + self._size > 65536:
                raise AdmissionFailure("ADMITTED_DELIVERY_FAILED", 1013)
            self._admitted = admitted
            self._size += len(admitted)

    def append_runtime(self, frame: WireFrame) -> None:
        with self._lock:
            if (
                self._closed
                or self._released
                or self._admitted is None
                or frame.frame_type not in (F.OUTPUT, F.GAP)
                or frame.leg != _RA
                or len(frame.wire_bytes) + self._size > 65536
                or len(self._output) >= 256
            ):
                raise AdmissionFailure("OUTPUT_BACKPRESSURE", 1013)
            self._output.append(frame)
            self._size += len(frame.wire_bytes)

    def release(self) -> None:
        with self._lock:
            if (
                self._closed
                or self._released
                or self._admitted is None
                or self._session is None
                or self._handle is None
            ):
                raise AdmissionFailure("ADMITTED_DELIVERY_FAILED", 1013)
            # Validate the entire batch before making even ADMITTED readable.
            frames = [self._admitted]
            self._session.accept(
                _AB, self._admitted, stream_id=self._handle.connection_id, now=self._clock()
            )
            for frame in self._output:
                sequence = self._session.expected_sequence(_AB)
                wire = (
                    forward_wire_frame(frame, _AB, sequence)
                    if frame.frame_type == F.OUTPUT
                    else encode_wire_frame(F.GAP, _AB, frame.json_payload, sequence)
                )
                self._session.accept(
                    _AB, wire, stream_id=self._handle.connection_id, now=self._clock()
                )
                frames.append(wire)
            self._visible.extend(frames)
            self._admitted = None
            self._output.clear()
            self._released = True

    def read(self) -> bytes | None:
        # The authority lock is acquired before the queue lock, just as release.
        if self._authority is None or self._handle is None:
            return None
        try:
            return self._authority.read_published(self._handle, self)
        except TicketAuthorityError:
            return None

    def take(self) -> bytes | None:
        """Authority-internal reader; adapters use read(), never this method."""
        with self._lock:
            if self._closed or not self._visible:
                return None
            result = self._visible.popleft()
            self._size -= len(result)
            return result

    def discard(self) -> None:
        with self._lock:
            self._closed = True
            self._admitted = None
            self._output.clear()
            self._visible.clear()
            self._size = 0


class WAWAdmissionCoordinator:
    """One-shot API authority transaction; successful run returns an ACTIVE lease.

    A single browser reader rejects all premature non-key traffic while any
    Runtime/Audit await is pending. A Runtime reader validates responses and
    quarantines committed output while admitted Audit is pending. Reader tasks
    are stopped at successful handoff; ports must preserve unread data on cancel.
    """

    def __init__(
        self,
        *,
        authority: AttachmentAuthority,
        claims: AttachmentTuple,
        context: AuthenticatedAttachmentContext,
        runtime: AdmissionRuntimePort,
        browser: AdmissionBrowserPort,
        audit: AdmissionAuditPort,
        revalidator: AdmissionRevalidator,
        budget: PendingAdmissionBudget,
        source: str,
        started_at_ns: int,
        input_budget: InputBudget,
        queue: BoundedAdmissionQueue | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if type(started_at_ns) is not int or started_at_ns < 0 or runtime.connection_id is None:
            raise AdmissionFailure()
        self._authority, self._claims, self._context = authority, claims, context
        self._runtime, self._browser, self._audit, self._validator = (
            runtime,
            browser,
            audit,
            revalidator,
        )
        self._budget, self._source = budget, source
        self._connection = runtime.connection_id
        self._input_budget = input_budget
        self._input_budget.assert_identity(
            connection_id=self._connection,
            attachment_id=claims.attachment_id,
            runtime_epoch=context.runtime_epoch,
        )
        self._started, self._clock = started_at_ns, clock_ns
        self._wire_a = wire_admission_tuple(claims)
        self._wire = WireSession(
            self._wire_a,
            context.runtime_epoch,
            stream_id=self._connection,
            started_at=started_at_ns,
        )
        self.queue = BoundedAdmissionQueue() if queue is None else queue
        self._handle: StagedAttachment | None = None
        self._started_run = self._runtime_attempted = self._runtime_hello = False
        self._browser_expected: F | None = F.WS_HELLO
        self._browser_frames: asyncio.Queue[WireFrame] = asyncio.Queue(maxsize=1)
        self._runtime_frames: asyncio.Queue[WireFrame] = asyncio.Queue(maxsize=2)
        self._failed: asyncio.Future[AdmissionFailure] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._readers: list[asyncio.Task[None]] = []
        self._cleanup_task: asyncio.Task[None] | None = None
        self._cleanup_fence_error: BaseException | None = None
        self._last_now = started_at_ns
        self._runtime_negative: WireFrame | None = None
        self._browser_published = 0
        self._browser_writing = self._browser_write_uncertain = False

    @property
    def reservation(self) -> StagedAttachment | None:
        return self._handle

    @property
    def wire_session(self) -> WireSession:
        return self._wire

    def _check(self) -> int:
        now = self._clock()
        if (
            type(now) is not int
            or now < self._last_now
            or self._runtime.connection_id is not self._connection
        ):
            raise AdmissionFailure("ATTACHMENT_STALE", 4403)
        self._last_now = now
        if self._failed is not None and self._failed.done():
            raise self._failed.result()
        if now - self._started >= ADMISSION_TIMEOUT_NS:
            raise AdmissionFailure("ADMISSION_TIMEOUT", 4408)
        if self._validator.current(self._claims, self._context) is not True:
            raise AdmissionFailure("ATTACHMENT_STALE", 4403)
        if self._handle is not None:
            self._authority.check_reserved(self._handle, now=now / 1_000_000_000)
        return now

    def _spawn(self, operation: Awaitable[_T]) -> asyncio.Task[_T]:
        task = asyncio.ensure_future(operation)
        self._tasks.add(task)

        def done(completed: asyncio.Task[Any]) -> None:
            self._tasks.discard(completed)
            if not completed.cancelled():
                completed.exception()  # Consume failure without formatting/logging payloads.

        task.add_done_callback(done)
        return task

    async def _await(
        self, operation: Callable[[], Awaitable[_T]], *, retry_timeout: bool = False
    ) -> _T:
        now = self._check()
        task = self._spawn(operation())
        assert self._failed is not None
        remaining = (ADMISSION_TIMEOUT_NS - (now - self._started)) / 1_000_000_000
        # Only the first commit receive can use a shorter retry interval.
        timeout = min(remaining, 0.25) if retry_timeout else remaining
        done, _ = await asyncio.wait(
            (task, self._failed), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if task not in done:
            task.cancel()
            self._check()
            if retry_timeout and self._failed not in done:
                raise TimeoutError
            raise AdmissionFailure("ADMISSION_TIMEOUT", 4408)
        result = task.result()
        self._check()
        return result

    def _observe(self, leg: Leg, raw: bytes) -> WireFrame:
        return self._wire.accept(leg, raw, stream_id=self._connection, now=self._check())

    def _signal(self, error: AdmissionFailure) -> None:
        if self._failed is not None and not self._failed.done():
            self._failed.set_result(error)
        if self._handle is not None:
            try:
                self._authority.fence(self._handle)
            except BaseException as failure:
                if self._cleanup_fence_error is None:
                    self._cleanup_fence_error = failure
                raise
        self.queue.discard()

    def _admission_bytes(self, delivery: BrowserDelivery) -> bytes:
        if type(delivery) is not BrowserDelivery or type(delivery.wire_bytes) is not bytes:
            raise AdmissionFailure()
        if delivery.input_token is not None:
            self._input_budget.release(
                delivery.input_token, owner=InputBudgetOwner.BROWSER_DELIVERY
            )
            raise AdmissionFailure("ATTACHMENT_NOT_READY", 4400)
        return delivery.wire_bytes

    async def _read_browser(self) -> None:
        try:
            while True:
                raw = self._admission_bytes(await self._browser.receive())
                expected = self._browser_expected
                if expected is None:
                    raise AdmissionFailure("ATTACHMENT_NOT_READY", 4400)
                frame = self._observe(_BA, raw)
                if frame.frame_type != expected or self._browser_frames.full():
                    raise AdmissionFailure("ATTACHMENT_NOT_READY", 4400)
                self._browser_expected = None
                self._browser_frames.put_nowait(frame)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._signal(_normalized(exc))

    async def _read_runtime(self) -> None:
        try:
            while True:
                frame = self._observe(_RA, await self._runtime.receive())
                if frame.frame_type in (F.ERROR, F.STATE):
                    # Only a fully validated negative frame may become browser
                    # metadata. Signal immediately; never await another Runtime
                    # frame while ownership is still an admission reservation.
                    self._runtime_negative = frame
                    raise AdmissionFailure("RUNTIME_UNAVAILABLE", 1013)
                elif frame.frame_type in (F.OUTPUT, F.GAP) and self._wire.committed:
                    self.queue.append_runtime(frame)
                elif frame.frame_type in (
                    F.HELLO_ACK,
                    F.KEY_ATTEST,
                    F.KEY_CONFIRM_ACK,
                    F.STREAM_READY_ACK,
                    F.ADMISSION_COMMIT_ACK,
                ):
                    if (
                        frame.json_payload is not None
                        and frame.json_payload.get("result") == "rejected"
                    ):
                        self._runtime_negative = frame
                        raise AdmissionFailure("ADMITTED_DELIVERY_FAILED", 1013)
                    self._runtime_frames.put_nowait(frame)
                else:
                    raise AdmissionFailure("RUNTIME_UNAVAILABLE", 1013)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._signal(_normalized(exc))

    async def _browser_frame(self, kind: F) -> WireFrame:
        frame = await self._await(self._browser_frames.get)
        if frame.frame_type != kind:
            raise AdmissionFailure()
        return frame

    async def _runtime_frame(self, kind: F, *, retry_timeout: bool = False) -> WireFrame:
        frame = await self._await(self._runtime_frames.get, retry_timeout=retry_timeout)
        if frame.frame_type != kind:
            raise AdmissionFailure()
        return frame

    async def _stop_readers(self) -> None:
        """Finish cancellation before transferring single-reader port ownership.

        This runs while still quarantined and within the original admission
        deadline. A cancellation-resistant port cannot grant a successful
        handoff or permit ACTIVE publication.
        """
        for reader in self._readers:
            reader.cancel()
        if self._readers:
            await asyncio.wait(self._readers)

    async def _send_runtime(self, raw: bytes) -> None:
        self._observe(_AR, raw)
        await self._await(lambda: self._runtime.send(raw))

    async def _send_browser(self, source: WireFrame) -> None:
        raw = forward_wire_frame(source, _AB, self._wire.expected_sequence(_AB))
        self._observe(_AB, raw)
        await self._await(lambda: self._publish_browser(raw))

    async def _publish_browser(self, raw: bytes) -> None:
        self._browser_writing = True
        try:
            await self._browser.send_key_frame(raw)
            self._browser_published += 1
        except BaseException:
            # ASGI cancellation does not prove that no bytes were written.
            self._browser_write_uncertain = True
            raise
        finally:
            self._browser_writing = False

    async def _publish_runtime_failure(self, cleanup_deadline: float) -> None:
        """Best-effort fixed metadata, never a new publication/admission grant.

        A partially written key frame or a writer that has not retired permits
        only native close. The notification shares the cleanup deadline and is
        additionally capped at 100 ms; it cannot displace exact cleanup/Audit.
        """
        source, self._runtime_negative = self._runtime_negative, None
        if source is None or self._browser_writing or self._browser_write_uncertain:
            return

        def permitted() -> int:
            now = self._clock()
            if (
                type(now) is not int
                or now < self._last_now
                or now - self._started >= ADMISSION_TIMEOUT_NS
                or self._runtime.connection_id is not self._connection
                or self._validator.current(self._claims, self._context) is not True
                or self._wire.expected_sequence(_AB) != self._browser_published + 1
                or self._browser_writing
                or self._browser_write_uncertain
            ):
                raise AdmissionFailure("ATTACHMENT_STALE", 4403)
            self._last_now = now
            return now

        now = permitted()
        body = source.json_payload
        assert body is not None
        attested = self._browser_published >= 1
        kind = F.STATE if source.frame_type == F.STATE and attested else F.ERROR
        state = "UNKNOWN"
        if kind == F.STATE:
            payload = {name: value for name, value in body.items() if name != "runtime_epoch"}
            state = body["state"]
        elif source.frame_type == F.ERROR:
            # Correlation identifiers are hop-local metadata, unlike immutable
            # key/ciphertext payloads. Never expose the Runtime/caller ID.
            payload = {**body, "request_id": "wreq_" + secrets.token_hex(16)}
        else:
            payload = {
                "protocol_version": 1,
                "code": (
                    "ADMITTED_DELIVERY_FAILED"
                    if source.frame_type == F.ADMISSION_COMMIT_ACK
                    else "RUNTIME_UNAVAILABLE"
                ),
                "retryable": False,
                "request_id": "wreq_" + secrets.token_hex(16),
            }

        async def notify() -> None:
            checked_at = permitted()
            raw = encode_wire_frame(kind, _AB, payload, self._browser_published + 1)
            self._wire.accept(_AB, raw, stream_id=self._connection, now=checked_at)
            await self._publish_browser(raw)
            if attested:
                checked_at = permitted()
                raw = encode_wire_frame(
                    F.CLOSE,
                    _AB,
                    {
                        "protocol_version": 1,
                        "code": "RUNTIME_UNAVAILABLE",
                        "workspace_state_at_close": state,
                    },
                    self._browser_published + 1,
                )
                self._wire.accept(_AB, raw, stream_id=self._connection, now=checked_at)
                await self._publish_browser(raw)

        task = self._spawn(notify())
        timeout = min(
            0.1,
            max(0.0, cleanup_deadline - asyncio.get_running_loop().time()),
            (ADMISSION_TIMEOUT_NS - (now - self._started)) / 1_000_000_000,
        )
        done, _ = await asyncio.wait((task,), timeout=timeout)
        if task in done:
            task.result()
        else:
            task.cancel()

    def _advance(self, stage: AdmissionStage) -> None:
        assert self._handle is not None
        self._authority.advance(self._handle, stage, now=self._check() / 1_000_000_000)

    def _event(self, action: AdmissionAuditAction) -> AdmissionAuditEvent:
        return AdmissionAuditEvent(
            action,
            self._claims.workspace_id,
            self._claims.attachment_id,
            self._claims.generation,
            self._context.runtime_epoch,
            self._claims.api_authority_epoch,
            "ADMITTED_DELIVERY_FAILED" if action == AdmissionAuditAction.DETACHED else None,
        )

    def _origin(self, kind: F, extra: dict[str, Any] | None = None) -> bytes:
        return encode_wire_frame(
            kind,
            _AR,
            {
                "protocol_version": 1,
                **self._wire_a,
                "runtime_epoch": self._context.runtime_epoch,
                **(extra or {}),
            },
            self._wire.expected_sequence(_AR),
        )

    async def run(self) -> ActiveAttachment:
        if self._started_run:
            raise AdmissionFailure("ATTACHMENT_STALE", 4403)
        self._started_run = True
        permit: _PendingPermit | None = None
        self._failed = asyncio.get_running_loop().create_future()
        try:
            self._check()
            permit = self._budget.acquire(self._source)
            # Grammar/direction/sequence precede the burn; comparisons against
            # trusted tuple/epoch happen atomically with the authority's pop.
            # A bound WireSession check here would leave mismatched tickets live.
            hello = decode_wire_frame(
                self._admission_bytes(await self._await(self._browser.receive)),
                _BA,
                trusted_context=False,
            )
            if hello.frame_type != F.WS_HELLO or hello.hop_sequence != 1:
                raise AdmissionFailure()
            body = hello.json_payload
            assert body is not None
            self._handle = self._authority.reserve(
                body["ticket"],
                self._claims,
                context=self._context,
                connection_id=self._connection,
                started_at=self._started / 1_000_000_000,
                now=self._check() / 1_000_000_000,
                presented_claims={name: body[name] for name in self._wire_a},
                presented_runtime_epoch=body["runtime_epoch"],
            )
            self._observe(_BA, hello.wire_bytes)
            self.queue.bind(self._authority, self._handle, self._wire, self._clock)
            self._browser_expected = F.KEY_INIT
            self._readers.append(self._spawn(self._read_browser()))
            key_init = await self._browser_frame(F.KEY_INIT)
            request = RuntimePrepareRequest(
                self._claims,
                self._context.runtime_epoch,
                self._connection,
                body["resume_cursor"],
                body["previous_runtime_epoch"],
            )
            self._runtime_attempted = True
            prepared = await self._await(lambda: self._runtime.prepare(request))
            if (
                type(prepared) is not RuntimePrepared
                or prepared.claims != self._claims
                or prepared.runtime_epoch != self._context.runtime_epoch
                or prepared.connection_id is not self._connection
                or type(prepared.capability) is not str
                or re.fullmatch(r"[a-f0-9]{64}", prepared.capability) is None
            ):
                raise AdmissionFailure("ATTACHMENT_STALE", 4403)
            self._advance(AdmissionStage.RUNTIME_PREPARED)
            self._runtime_hello = True
            await self._send_runtime(
                self._origin(
                    F.RUNTIME_HELLO,
                    {
                        "capability": prepared.capability,
                        "resume_cursor": request.resume_cursor,
                        "previous_runtime_epoch": request.previous_runtime_epoch,
                    },
                )
            )
            del prepared, body, hello
            await self._send_runtime(forward_wire_frame(key_init, _AR, 2))
            self._readers.append(self._spawn(self._read_runtime()))
            hello_ack = await self._runtime_frame(F.HELLO_ACK)
            attest = await self._runtime_frame(F.KEY_ATTEST)
            self._browser_expected = F.KEY_CONFIRM
            await self._send_browser(attest)
            confirm = await self._browser_frame(F.KEY_CONFIRM)
            await self._send_runtime(forward_wire_frame(confirm, _AR, 3))
            confirm_ack = await self._runtime_frame(F.KEY_CONFIRM_ACK)
            await self._send_browser(confirm_ack)
            self._advance(AdmissionStage.VERIFIED)
            await self._await(
                lambda: self._audit.persist(self._event(AdmissionAuditAction.PREPARED))
            )
            self._advance(AdmissionStage.PREPARED_AUDITED)
            await self._send_runtime(self._origin(F.STREAM_READY))
            ready = await self._runtime_frame(F.STREAM_READY_ACK)
            self._advance(AdmissionStage.READY)
            baseline, ready_body = hello_ack.json_payload, ready.json_payload
            assert baseline is not None and ready_body is not None
            expiry = datetime.now(UTC) + timedelta(
                seconds=self._handle.lease_expires_at_monotonic - self._check() / 1_000_000_000
            )
            admitted = encode_wire_frame(
                F.ADMITTED,
                _AB,
                {
                    "protocol_version": 1,
                    **self._wire_a,
                    "runtime_epoch": self._context.runtime_epoch,
                    "state": "RUNNING",
                    "output_cursor": baseline["output_cursor"],
                    "lease_expires_at": expiry.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                },
                3,
            )
            self.queue.quarantine(admitted)
            self._advance(AdmissionStage.QUARANTINED)
            commit = self._origin(
                F.ADMISSION_COMMIT, {"admission_fence": ready_body["admission_fence"]}
            )
            await self._send_runtime(commit)
            try:
                await self._runtime_frame(F.ADMISSION_COMMIT_ACK, retry_timeout=True)
            except TimeoutError:
                await self._send_runtime(commit)  # Exact bytes, original hop 5, same connection.
                await self._runtime_frame(F.ADMISSION_COMMIT_ACK)
            self._advance(AdmissionStage.COMMITTED)
            await self._await(
                lambda: self._audit.persist(self._event(AdmissionAuditAction.ADMITTED))
            )
            await self._await(self._stop_readers)
            self._advance(AdmissionStage.ADMITTED_AUDITED)
            # No await exists between the final auth/deadline check and release.
            lease = self._authority.activate_with_publication(
                self._handle, self.queue, now=self._check() / 1_000_000_000
            )
            return lease
        except asyncio.CancelledError:
            await self._cleanup(AdmissionFailure("ATTACHMENT_STALE", 4403))
            raise
        except BaseException as exc:
            error = _normalized(exc)
            await self._cleanup(error)
            raise error from None
        finally:
            for reader in self._readers:
                reader.cancel()
            if permit is not None:
                self._budget.release(permit)

    async def _cleanup(self, error: AdmissionFailure) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_once(error))

            def consume(task: asyncio.Task[None]) -> None:
                if not task.cancelled():
                    task.exception()

            self._cleanup_task.add_done_callback(consume)
        task = self._cleanup_task
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.cancelled():
                    raise

    async def _cleanup_once(self, error: AdmissionFailure) -> None:
        try:
            self._signal(error)
        except BaseException as failure:
            if self._cleanup_fence_error is None:
                self._cleanup_fence_error = failure
        with suppress(BaseException):
            self.queue.discard()
        for task in tuple(self._tasks):
            with suppress(BaseException):
                task.cancel()
        proof: RuntimeCleanupProof | None = None
        audited = False
        # Cleanup has its separate one-second bound, never a renewed admission.
        deadline = asyncio.get_running_loop().time() + 1.0
        try:
            # Let cancelled writers publish their cancellation/uncertainty before
            # deciding whether a final fixed response can safely follow them.
            with suppress(BaseException):
                await asyncio.sleep(0)
                notification_task = self._spawn(self._publish_runtime_failure(deadline))
                notification_done, _ = await asyncio.wait(
                    (notification_task,),
                    timeout=min(0.1, max(0.0, deadline - asyncio.get_running_loop().time())),
                )
                if notification_task in notification_done:
                    notification_task.result()
                else:
                    notification_task.cancel()
            # Runtime proof failure does not excuse the independent mandatory
            # failure Audit attempt. Neither operation gets a fresh deadline.
            if self._handle is not None and self._runtime_attempted:
                close_frame = None
                if self._runtime_hello:
                    with suppress(BaseException):
                        close_frame = encode_wire_frame(
                            F.CLOSE,
                            _AR,
                            {
                                "protocol_version": 1,
                                "code": "INTERNAL_BOUNDED",
                                "workspace_state_at_close": "RUNNING",
                            },
                            self._wire.expected_sequence(_AR),
                        )
                with suppress(BaseException):
                    request = RuntimeCleanupRequest(
                        self._claims, self._context.runtime_epoch, self._connection, close_frame
                    )
                    cleanup_task = self._spawn(self._runtime.close_and_cleanup(request))
                    done, _ = await asyncio.wait(
                        (cleanup_task,),
                        timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
                    )
                    if cleanup_task in done:
                        proof = cleanup_task.result()
                    else:
                        cleanup_task.cancel()
            with suppress(BaseException):
                if self._handle is not None:
                    audit_task = self._spawn(
                        self._audit.persist(self._event(AdmissionAuditAction.DETACHED))
                    )
                    audit_done, _ = await asyncio.wait(
                        (audit_task,),
                        timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
                    )
                    if audit_task in audit_done:
                        audit_task.result()
                        audited = True
                    else:
                        audit_task.cancel()
        finally:
            with suppress(BaseException):
                self._runtime.abort()
            with suppress(BaseException):
                self._browser.close(error.close_code)
            with suppress(BaseException):
                self._input_budget.close()
            with suppress(BaseException):
                self._wire.close()
        if (
            self._handle is not None
            and self._cleanup_fence_error is None
            and audited
            and not any(not task.done() for task in self._tasks)
            and type(proof) is RuntimeCleanupProof
            and proof.claims == self._claims
            and proof.runtime_epoch == self._context.runtime_epoch
            and proof.connection_id is self._connection
            and proof.result in ("detached", "already_detached")
            and proof.cleanup_state == "ATTACH_PTY_CLOSED"
        ):
            self._authority.acknowledge_staged_cleanup(
                self._handle,
                connection_id=self._connection,
                cleanup_state="ATTACH_PTY_CLOSED",
                failure_audited=True,
            )
        if self._cleanup_fence_error is not None:
            raise self._cleanup_fence_error


def _normalized(error: BaseException) -> AdmissionFailure:
    if isinstance(error, AdmissionFailure):
        return error
    if isinstance(error, TicketAuthorityError):
        mapping = {
            "ADMITTED_DELIVERY_FAILED": 1013,
            "WORKSPACE_WRITER_BUSY": 4409,
            "ATTACHMENT_TICKET_UNAVAILABLE": 4429,
            "ATTACHMENT_TICKET_EXPIRED": 4403,
            "ATTACHMENT_TICKET_REPLAYED": 4403,
            "ATTACHMENT_TICKET_INVALID": 4403,
            "ATTACHMENT_STALE": 4403,
        }
        return AdmissionFailure(str(error.code), mapping.get(str(error.code), 4400))
    if isinstance(error, WireError):
        return AdmissionFailure()
    return AdmissionFailure("ADMITTED_DELIVERY_FAILED", 1013)
