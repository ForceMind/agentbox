"""Runtime-owned, fixed WAW encrypted attachment endpoint.

No API module, Session identity, command, pathname or credential is accepted.
Trusted Runtime composition supplies already-qualified supervisor, peer, redraw
and in-memory key ports. These ports are software seams, not host qualification.
The API's browser 30s stale/60s grace and HTTP 15min/8h authorization checks remain
its separate responsibility; Runtime enforces its independent 10s health fence.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from agentbox_core.waw_recovery import ResumeHint
from agentbox_core.waw_tickets import AttachmentTuple
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.awce import decode_awce
from agentbox_protocol.waw_crypto_context import ADMISSION_KEYS, validate_admission, validate_u64
from agentbox_protocol.waw_crypto_profile import OUTPUT_LIMIT, RuntimeCryptoProfile, WAWCryptoError
from agentbox_protocol.waw_wire import (
    ERROR_CODES,
    Leg,
    WireError,
    WireFrame,
    decode_wire_frame,
    encode_wire_frame,
)

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_pty import OutputFrame, PtyGeometry
from agentbox_runtime.waw_redraw import BoundedRedraw as BoundedRedraw
from agentbox_runtime.waw_supervisor import (
    RuntimeAttachmentLease,
    RuntimeProbeState,
    SupervisorState,
    WAWSupervisor,
)

AR = Leg.API_TO_RUNTIME
RA = Leg.RUNTIME_TO_API
_MAX_CURSOR = 2**64 - 2


class EncryptedStreamError(RuntimeError):
    """Normalized diagnostics never contain bearers or terminal data."""

    def __init__(self, code: str = "PROTOCOL_INVALID") -> None:
        self.code = code
        super().__init__(code)


def failure_profile(
    error: BaseException,
    *,
    next_hop: int,
    trusted_context: bool,
    workspace_state: str = "UNKNOWN",
) -> tuple[bytes, ...]:
    """Create one closed failure profile from the transport's publication cursor.

    ``next_hop`` is the next never-published Runtime hop, NOT the session's
    allocation counter. The transport must suppress this profile after any
    partially written/uncertain frame or terminal CLOSE. No crypto is reused.
    """
    if type(next_hop) is not int or not 1 <= next_hop <= 2**64 - 1:
        return ()
    code = "INTERNAL_BOUNDED"
    close_code = "RUNTIME_UNAVAILABLE"
    if isinstance(error, (EncryptedStreamError, RuntimeOperationError)):
        candidate = error.code
        if candidate in ERROR_CODES:
            code = candidate
        elif candidate == "ADMISSION_TIMEOUT":
            code, close_code = "ATTACHMENT_NOT_READY", "ADMISSION_TIMEOUT"
        elif candidate.startswith("WAW_ATTACHMENT"):
            code = "ATTACHMENT_STALE"
        elif candidate.startswith("WAW_PROBE"):
            code = "RECONCILIATION_REQUIRED"
    elif isinstance(error, WAWCryptoError):
        code = "STREAM_CRYPTO_FAILURE"
    elif isinstance(error, WireError):
        code = "PROTOCOL_INVALID"
    elif isinstance(error, TimeoutError):
        code, close_code = (
            ("RUNTIME_UNAVAILABLE", "RUNTIME_UNAVAILABLE")
            if trusted_context and next_hop >= 6
            else ("ATTACHMENT_NOT_READY", "ADMISSION_TIMEOUT")
        )
    if code == "STREAM_CRYPTO_FAILURE" and next_hop <= 3:
        code = "KEY_CONFIRM_FAILED"
    close_codes = {
        "ATTACHMENT_STALE",
        "PROTOCOL_INVALID",
        "SEQUENCE_EXHAUSTED",
        "RUNTIME_UNAVAILABLE",
        "WORKSPACE_EXITED",
        "WORKSPACE_STOPPED",
        "OUTPUT_BACKPRESSURE",
        "TERMINAL_PARSE_LIMIT",
        "CONTROL_RATE_LIMITED",
    }
    if code in close_codes:
        close_code = code
    elif code in {"KEY_CONFIRM_FAILED", "STREAM_CRYPTO_FAILURE"}:
        close_code = "PROTOCOL_INVALID"
    elif code in {"WORKSPACE_NOT_RUNNING", "RECONCILIATION_REQUIRED"}:
        close_code, workspace_state = "ATTACHMENT_STALE", "UNKNOWN"
    # A correlation identifier is freshly generated locally, never taken from
    # exception text, a caller field, the capability or a key-derived value.
    request_id = "wreq_" + secrets.token_hex(16)
    error_frame = encode_wire_frame(
        F.ERROR,
        RA,
        {
            "protocol_version": 1,
            "code": code,
            "retryable": False,
            "request_id": request_id,
        },
        next_hop,
        trusted_context=trusted_context,
    )
    # WAIT_HELLO_ACK and WAIT_KEY_ATTEST terminate on ERROR alone. A
    # validated tuple/request ID is not permission to append CLOSE in those
    # phases; KEY_ATTEST must have been fully published first.
    if not trusted_context or next_hop <= 2 or next_hop == 2**64 - 1:
        return (error_frame,)
    close_frame = encode_wire_frame(
        F.CLOSE,
        RA,
        {
            "protocol_version": 1,
            "code": close_code,
            "workspace_state_at_close": workspace_state,
        },
        next_hop + 1,
    )
    return error_frame, close_frame


class RuntimePublicationPort(Protocol):
    """Trusted one-socket publication capability; never a caller-selected endpoint."""

    def send(self, data: memoryview) -> int: ...

    def fence(self) -> bool: ...


@dataclass(frozen=True, repr=False)
class RuntimePeer:
    """Already authenticated sole API process/authority identity.

    ``identity`` is the canonical process-lifetime handle shared by the trusted
    control and stream peer verifier. A numeric PID alone is not this identity.
    ``current`` must check retained pidfd and authority binding, not UID alone.
    """

    identity: object
    api_authority_epoch: str
    current: Callable[[], bool] = field(repr=False)


@dataclass(frozen=True, repr=False)
class RuntimeCleanup:
    claims: AttachmentTuple
    runtime_epoch: str
    result: str
    cleanup_state: str

    @property
    def confirmed(self) -> bool:
        return self.cleanup_state == "ATTACH_PTY_CLOSED"


def admission_fields(claims: AttachmentTuple) -> dict[str, str]:
    return validate_admission({key: str(getattr(claims, key)) for key in ADMISSION_KEYS})


@dataclass(repr=False)
class _Prepared:
    claims: AttachmentTuple
    peer: RuntimePeer
    supervisor: WAWSupervisor
    lease: RuntimeAttachmentLease
    hints: tuple[str | None, str | None]
    started: float
    capability: str = field(repr=False)
    consumed: bool = False
    session: WAWEncryptedSession | None = None
    cleanup: RuntimeCleanup | None = None


class WAWEncryptedRegistry:
    """Bounded volatile capability authority for fixed Runtime attach operations.

    ``prepare`` is called only after authenticated control authorization. The
    random capability is retained only until burn/expiry to permit the specified
    exact PREPARED response-loss retry. Terminal records carry no bearer/bytes.
    """

    def __init__(
        self,
        *,
        runtime_epoch: str,
        static_key: Callable[[], bytes],
        clock: Callable[[], float] = time.monotonic,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
        maximum: int = 32,
    ) -> None:
        self.runtime_epoch = validate_u64(runtime_epoch)
        if type(maximum) is not int or not 1 <= maximum <= 32:
            raise ValueError("invalid Runtime attachment capacity")
        self._static_key = static_key
        self._clock = clock
        self._random = random_bytes
        self._maximum = maximum
        self._records: dict[str, _Prepared] = {}
        self._retired: deque[str] = deque(maxlen=1024)
        self._completed: OrderedDict[str, tuple[AttachmentTuple, object, float, RuntimeCleanup]] = (
            OrderedDict()
        )
        self._invalidated = threading.Event()
        self._lock = threading.RLock()
        self._last_tick = self._now()

    def _now(self) -> float:
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise EncryptedStreamError("INTERNAL_BOUNDED")
        if now < getattr(self, "_last_tick", now):
            raise EncryptedStreamError("INTERNAL_BOUNDED")
        self._last_tick = now
        return now

    @staticmethod
    def _peer(peer: RuntimePeer) -> None:
        if type(peer) is not RuntimePeer or peer.current() is not True:
            raise EncryptedStreamError("RUNTIME_PEER_FORBIDDEN")
        validate_u64(peer.api_authority_epoch)

    def prepare(
        self,
        *,
        peer: RuntimePeer,
        claims: AttachmentTuple,
        supervisor: WAWSupervisor,
        resume_cursor: str | None = None,
        previous_runtime_epoch: str | None = None,
        current: Callable[[], bool],
    ) -> str:
        """Reserve without a writer; exact unconsumed retries return one bearer."""
        with self._lock:
            self._peer(peer)
            if self._invalidated.is_set():
                raise EncryptedStreamError("RUNTIME_UNAVAILABLE")
            admission_fields(claims)
            if peer.api_authority_epoch != str(claims.api_authority_epoch):
                raise EncryptedStreamError("ATTACHMENT_STALE")
            if resume_cursor is not None and (
                type(resume_cursor) is not str
                or not resume_cursor.isascii()
                or not resume_cursor.isdecimal()
                or (len(resume_cursor) > 1 and resume_cursor.startswith("0"))
                or len(resume_cursor) > 20
                or not 0 <= int(resume_cursor) <= _MAX_CURSOR
            ):
                raise EncryptedStreamError()
            if previous_runtime_epoch is not None:
                validate_u64(previous_runtime_epoch)
            ResumeHint(
                None if resume_cursor is None else int(resume_cursor),
                None if previous_runtime_epoch is None else int(previous_runtime_epoch),
            ).validate(current_runtime_epoch=int(self.runtime_epoch))
            now = self._now()
            self.sweep()
            existing = self._records.get(claims.attachment_id)
            hints = (resume_cursor, previous_runtime_epoch)
            if existing is not None:
                if (
                    not existing.consumed
                    and now < existing.started + 5
                    and existing.claims == claims
                    and existing.peer.identity is peer.identity
                    and existing.hints == hints
                    and existing.supervisor is supervisor
                ):
                    return existing.capability
                raise EncryptedStreamError("ATTACHMENT_PREPARE_REPLAY")
            if claims.attachment_id in self._retired:
                raise EncryptedStreamError("ATTACHMENT_PREPARE_REPLAY")
            if len(self._records) >= self._maximum:
                raise EncryptedStreamError("WORKSPACE_RESOURCE_LIMITED")
            if any(
                item.claims.workspace_id == claims.workspace_id for item in self._records.values()
            ):
                raise EncryptedStreamError("WORKSPACE_WRITER_BUSY")
            material = self._random(32)
            if type(material) is not bytes or len(material) != 32:
                raise EncryptedStreamError("RANDOMNESS_UNAVAILABLE")
            capability = material.hex()
            if any(
                hmac.compare_digest(item.capability, capability) for item in self._records.values()
            ):
                raise EncryptedStreamError("RANDOMNESS_UNAVAILABLE")
            lease = RuntimeAttachmentLease(
                claims,
                self.runtime_epoch,
                now + 8 * 3600,
                lambda: not self._invalidated.is_set()
                and peer.current() is True
                and current() is True,
            )
            supervisor.reserve_runtime_attachment(lease)
            record = _Prepared(claims, peer, supervisor, lease, hints, now, capability)
            self._records[claims.attachment_id] = record
            try:
                with supervisor.runtime_attachment_guard(lease):
                    pass
            except BaseException:
                self._cleanup(record)
                raise
            return capability

    def open(
        self,
        peer: RuntimePeer,
        raw_hello: bytes,
        *,
        publication: RuntimePublicationPort | None = None,
    ) -> tuple[WAWEncryptedSession, bytes]:
        with self._lock:
            self._peer(peer)  # Unauthenticated peers cannot burn someone else's capability.
            hello = decode_wire_frame(raw_hello, AR)
            if hello.frame_type is not F.RUNTIME_HELLO or hello.hop_sequence != 1:
                raise EncryptedStreamError()
            body = hello.json_payload
            assert body is not None
            capability = body["capability"]
            record = next(
                (
                    item
                    for item in self._records.values()
                    if not item.consumed and hmac.compare_digest(item.capability, capability)
                ),
                None,
            )
            if record is None:
                raise EncryptedStreamError("ATTACHMENT_STALE")
            # Burn before comparing ANY tuple/epoch/hint field (including peer epoch).
            record.consumed = True
            record.capability = ""
            try:
                if (
                    peer.identity is not record.peer.identity
                    or peer.api_authority_epoch != str(record.claims.api_authority_epoch)
                    or self._now() >= record.started + 5
                    or {key: body[key] for key in ADMISSION_KEYS} != admission_fields(record.claims)
                    or body["runtime_epoch"] != self.runtime_epoch
                    or (body["resume_cursor"], body["previous_runtime_epoch"]) != record.hints
                ):
                    raise EncryptedStreamError("ATTACHMENT_STALE")
                session = WAWEncryptedSession(self, record, publication=publication)
                record.session = session
                return session, session.hello_ack()
            except BaseException:
                if record.session is not None:
                    record.session.close()
                else:
                    self._cleanup(record)
                raise

    def cleanup(self, peer: RuntimePeer, claims: AttachmentTuple) -> RuntimeCleanup:
        with self._lock:
            self._peer(peer)
            record = self._records.get(claims.attachment_id)
            if record is None:
                completed = self._completed.get(claims.attachment_id)
                if (
                    completed is not None
                    and completed[0] == claims
                    and completed[1] is peer.identity
                    and self._now() < completed[2]
                ):
                    return replace(completed[3], result="already_detached")
            if (
                record is None
                or record.claims != claims
                or record.peer.identity is not peer.identity
            ):
                raise EncryptedStreamError("ATTACHMENT_STALE")
            if record.session is not None:
                return record.session.close()
            return self._cleanup(record)

    def revoke_authority(self, identity: object) -> bool:
        """Fence and clean every attachment owned by one API authority.

        This is an identity-scoped transfer primitive, not a Runtime-wide
        invalidation. Capabilities are burned for the whole matching set before
        any socket or PTY cleanup begins. A record remains as a quarantine slot
        unless both publication fencing and exact PTY cleanup are confirmed.
        """
        with self._lock:
            records = tuple(
                record for record in self._records.values() if record.peer.identity is identity
            )
            for record in records:
                record.consumed = True
                record.capability = ""

            publication_fenced: dict[str, bool] = {}
            for record in records:
                session = record.session
                publication_fenced[record.claims.attachment_id] = (
                    True if session is None else session.invalidate()
                )

            confirmed = True
            for record in records:
                try:
                    session = record.session
                    proof = (
                        self._cleanup(record)
                        if session is None
                        else session._close_after_invalidation()
                    )
                except Exception:
                    confirmed = False
                    continue
                if not publication_fenced[record.claims.attachment_id] or not proof.confirmed:
                    confirmed = False

            # Authority transfer must not preserve an old process's idempotency
            # replies. _cleanup may have just created one, so purge after cleanup.
            for attachment_id, completed in tuple(self._completed.items()):
                if completed[1] is identity:
                    del self._completed[attachment_id]
            return confirmed and all(
                self._records.get(record.claims.attachment_id) is not record for record in records
            )

    def _cleanup(self, record: _Prepared, *, release: bool = True) -> RuntimeCleanup:
        record.consumed = True
        record.capability = ""
        if record.cleanup is None or not record.cleanup.confirmed:
            try:
                confirmed = record.supervisor.cleanup_runtime_attachment(record.lease)
            except Exception:
                confirmed = False
            record.cleanup = RuntimeCleanup(
                record.claims,
                self.runtime_epoch,
                "detached" if confirmed else "rejected",
                "ATTACH_PTY_CLOSED" if confirmed else "ATTACH_PTY_CLOSE_UNCERTAIN",
            )
        if (
            record.cleanup.confirmed
            and release
            and self._records.get(record.claims.attachment_id) is record
        ):
            expires = self._now() + 300
            self._completed[record.claims.attachment_id] = (
                record.claims,
                record.peer.identity,
                expires,
                record.cleanup,
            )
            self._records.pop(record.claims.attachment_id, None)
            self._retired.append(record.claims.attachment_id)
            while len(self._completed) > 1024:
                self._completed.popitem(last=False)
        return record.cleanup

    def invalidate(self) -> None:
        """Fail closed immediately without waiting for an in-flight Runtime lock."""
        self._invalidated.set()

    def sweep(self) -> None:
        with self._lock:
            now = self._now()
            for attachment_id, completed in tuple(self._completed.items()):
                if now >= completed[2]:
                    del self._completed[attachment_id]
            for record in tuple(self._records.values()):
                if record.session is None and (
                    now >= record.started + 5 or not record.peer.current()
                ):
                    self._cleanup(record)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._records)


@dataclass(repr=False)
class _PendingInput:
    hop: int
    crypto_sequence: int
    payload: bytes = field(repr=False)
    admitted_at: float


class WAWEncryptedSession:
    """One two-leg Runtime FSM with end-to-end crypto and exact PTY fences."""

    def __init__(
        self,
        registry: WAWEncryptedRegistry,
        record: _Prepared,
        *,
        publication: RuntimePublicationPort | None = None,
    ) -> None:
        self._registry, self._record = registry, record
        self._publication = publication
        self._publication_fenced = publication is None
        self._control_drain_until: float | None = None
        self._supervisor, self._lease = record.supervisor, record.lease
        self._clock = registry._clock
        self._admission = admission_fields(record.claims)
        self._epoch = registry.runtime_epoch
        self._phase = "WAIT_KEY_INIT"
        self._rx, self._tx = 2, 1
        self._lock = registry._lock
        self._closing = threading.Event()
        self._crypto: RuntimeCryptoProfile | None = None
        self._commit: bytes | None = None
        self._commit_ack: bytes | None = None
        self._commit_retried = False
        self._detach: bytes | None = None
        self._detach_ack: bytes | None = None
        self._detach_at = 0.0
        self._detach_retried = False
        self._fence = ""
        self._observed_process_state = RuntimeProbeState.RUNNING
        self._input: deque[_PendingInput] = deque()
        self._input_bytes = 0
        self._baseline_records: tuple[OutputFrame, ...] = ()
        self._baseline_gap: tuple[int, int, str] | None = None
        self._last_health = self._last_sent_health = registry._now()
        self._health_tick = 0
        self._control_tokens = 2.0
        self._control_tick = self._last_health
        self._pings: dict[str, tuple[str, float]] = {}
        self._sent_ping_tokens = 2.0
        self._sent_ping_tick = self._last_health
        self._baseline_sent = False
        self._terminal_acks: OrderedDict[tuple[int, int], tuple[float, str, str | None, bool]] = (
            OrderedDict()
        )
        self._output_window = int(self._last_health)
        self._output_used = 0
        self._cleanup_proof: RuntimeCleanup | None = None
        self._baseline = self._cursor = 0
        self._lease.publication.bind(self.invalidate)
        try:
            with self._supervisor.runtime_attachment_guard(self._lease):
                self._prepare_output()
                self._crypto = RuntimeCryptoProfile(
                    self._admission,
                    self._epoch,
                    registry._static_key(),
                    clock=self._clock,
                    admission_started_at=record.started,
                )
        except BaseException:
            if self._crypto is not None:
                self._crypto.destroy()
            raise

    @property
    def closed(self) -> bool:
        return self._closing.is_set()

    @property
    def committed(self) -> bool:
        return self._phase == "COMMITTED" and not self.closed

    @property
    def cleanup_proof(self) -> RuntimeCleanup | None:
        return self._cleanup_proof

    def _bound(self, **extra: Any) -> dict[str, Any]:
        return {"protocol_version": 1, **self._admission, "runtime_epoch": self._epoch, **extra}

    def _emit(
        self, kind: F, payload: dict[str, Any] | bytes, *, cleanup_reply: bool = False
    ) -> bytes:
        if self.closed and not cleanup_reply:
            raise EncryptedStreamError("ATTACHMENT_STALE")
        if self._tx > 2**64 - 1:
            raise EncryptedStreamError("SEQUENCE_EXHAUSTED")
        raw = encode_wire_frame(
            kind, RA, payload, self._tx, admission=self._admission, runtime_epoch=self._epoch
        )
        self._tx += 1
        return raw

    def _check(self, *, active: bool = False, check_health: bool = True) -> float:
        now = self._registry._now()
        if self.closed or not self._record.peer.current() or not self._lease.current():
            raise EncryptedStreamError("ATTACHMENT_STALE")
        if now >= self._lease.expires_at:
            raise EncryptedStreamError("ATTACHMENT_STALE")
        if self._phase != "COMMITTED" and now >= self._record.started + 5:
            raise EncryptedStreamError("ADMISSION_TIMEOUT")
        if active and self._phase != "COMMITTED":
            raise EncryptedStreamError("ATTACHMENT_NOT_READY")
        if check_health and self._phase == "COMMITTED" and self._health_expired(now):
            raise EncryptedStreamError("RUNTIME_UNAVAILABLE")
        return now

    def _health_expired(self, now: float) -> bool:
        return now >= self._last_health + 10 or any(now >= ping[1] for ping in self._pings.values())

    def hello_ack(self) -> bytes:
        with self._lock, self._supervisor.runtime_attachment_guard(self._lease):
            self._check()
            if self._tx != 1:
                raise EncryptedStreamError()
            return self._emit(
                F.HELLO_ACK,
                self._bound(
                    state="RUNNING",
                    output_cursor=str(self._baseline),
                    input_limit=16384,
                    output_limit=32768,
                ),
            )

    def receive(self, raw: bytes) -> tuple[bytes, ...]:
        with self._lock:
            try:
                now = self._registry._now()
                if (
                    self._detach is not None
                    and raw == self._detach
                    and not self._detach_retried
                    and now < self._detach_at + 1
                ):
                    self._detach_retried = True
                    assert self._detach_ack is not None
                    return (self._detach_ack,)
                self._check()
                if self._commit is not None and raw == self._commit:
                    if (
                        self._commit_retried
                        or now >= self._record.started + 5
                        or self._rx != 6
                        or self._tx != 6
                    ):
                        raise EncryptedStreamError()
                    with self._supervisor.runtime_attachment_guard(
                        self._lease, require_writer=True
                    ):
                        self._commit_retried = True
                        assert self._commit_ack is not None
                        return (self._commit_ack,)
                frame = decode_wire_frame(
                    raw, AR, admission=self._admission, runtime_epoch=self._epoch
                )
                if frame.hop_sequence != self._rx:
                    raise EncryptedStreamError()
                self._rx += 1
                if frame.frame_type is F.CLOSE:
                    self.close(drain_control=True)
                    return ()
                body = frame.json_payload
                crypto = self._crypto
                assert crypto is not None
                if self._phase == "WAIT_KEY_INIT" and frame.frame_type is F.KEY_INIT:
                    reply = self._emit(F.KEY_ATTEST, crypto.receive_init(body))
                    self._phase = "WAIT_KEY_CONFIRM"
                    return (reply,)
                if self._phase == "WAIT_KEY_CONFIRM" and frame.frame_type is F.KEY_CONFIRM:
                    reply = self._emit(F.KEY_CONFIRM_ACK, crypto.receive_confirm(body))
                    self._phase = "WAIT_READY"
                    return (reply,)
                if self._phase == "WAIT_READY" and frame.frame_type is F.STREAM_READY:
                    with self._supervisor.runtime_attachment_guard(self._lease):
                        self._check()
                        self._verify_precommit_output()
                        self._fence = secrets.token_hex(32)
                        reply = self._emit(
                            F.STREAM_READY_ACK,
                            self._bound(
                                state="RUNNING",
                                output_cursor=str(self._baseline),
                                admission_fence=self._fence,
                            ),
                        )
                        self._check()
                        self._phase = "WAIT_COMMIT"
                    return (reply,)
                if self._phase == "WAIT_COMMIT" and frame.frame_type is F.ADMISSION_COMMIT:
                    assert body is not None
                    if not hmac.compare_digest(body["admission_fence"], self._fence):
                        raise EncryptedStreamError("ATTACHMENT_STALE")
                    with self._supervisor.runtime_attachment_guard(self._lease):
                        self._check()
                        live = self._verify_precommit_output()
                        self._supervisor.commit_runtime_attachment(self._lease)
                        self._baseline_records += live
                        reply = self._emit(
                            F.ADMISSION_COMMIT_ACK,
                            self._bound(result="committed", reason_code=None),
                        )
                        self._commit, self._commit_ack = raw, reply
                        self._check()
                        self._phase = "COMMITTED"
                        self._last_health = self._last_sent_health = now
                    return (reply,)
                self._check(active=True)
                return self._active(frame, raw, now)
            except WAWCryptoError:
                self.close(clear_reason="crypto_failure", drain_control=True)
                raise EncryptedStreamError("STREAM_CRYPTO_FAILURE") from None
            except BaseException:
                self.close(drain_control=True)
                raise

    def _active(self, frame: WireFrame, raw: bytes, now: float) -> tuple[bytes, ...]:
        kind, body = frame.frame_type, frame.json_payload
        if kind is F.INPUT:
            return self._receive_input(frame, now)
        assert body is not None
        if kind in (F.HEARTBEAT, F.RESIZE, F.DETACH) and (
            body["attachment_id"] != self._lease.attachment_id
            or body["lease_number"] != str(self._lease.claims.lease_number)
        ):
            raise EncryptedStreamError("ATTACHMENT_STALE")
        if kind is F.HEARTBEAT:
            tick = int(body["sent_at_monotonic_tick"])
            if tick <= self._health_tick or now < self._last_health + 5:
                raise EncryptedStreamError("CONTROL_RATE_LIMITED")
            self._health_tick, self._last_health = tick, now
            return ()
        if kind in (F.PING, F.PONG):
            self._control_tokens = min(2.0, self._control_tokens + (now - self._control_tick) * 2)
            self._control_tick = now
            if self._control_tokens < 1:
                reply = self._emit(
                    F.CLOSE,
                    {
                        "protocol_version": 1,
                        "code": "CONTROL_RATE_LIMITED",
                        "workspace_state_at_close": self._workspace_state(),
                    },
                )
                self.close(drain_control=True)
                return (reply,)
            self._control_tokens -= 1
        if kind is F.PING:
            return (
                self._emit(
                    F.PONG,
                    {
                        "protocol_version": 1,
                        "nonce": body["nonce"],
                        "echoed_sent_at_monotonic_tick": body["sent_at_monotonic_tick"],
                    },
                ),
            )
        if kind is F.PONG:
            pending_ping = self._pings.pop(body["nonce"], None)
            if (
                pending_ping is None
                or pending_ping[0] != body["echoed_sent_at_monotonic_tick"]
                or now >= pending_ping[1]
            ):
                raise EncryptedStreamError()
            return ()
        if kind is F.RESIZE:
            with self._supervisor.runtime_attachment_guard(self._lease, require_writer=True):
                self._supervisor.resize(self._lease, PtyGeometry(body["columns"], body["rows"]))
                return (
                    self._emit(
                        F.RESIZE_ACK,
                        {
                            "protocol_version": 1,
                            "attachment_id": self._lease.attachment_id,
                            "lease_number": str(self._lease.claims.lease_number),
                            "acknowledged_hop_sequence": str(frame.hop_sequence),
                            "requested_columns": body["columns"],
                            "requested_rows": body["rows"],
                            "effective_columns": body["columns"],
                            "effective_rows": body["rows"],
                            "result": "applied",
                            "reason_code": None,
                        },
                    ),
                )
        if kind is F.DETACH:
            outcomes = self.flush_input()
            proof = self.close(drain_control=True)
            reply = self._emit(
                F.DETACH_ACK,
                self._bound(
                    acknowledged_hop_sequence=str(frame.hop_sequence),
                    result=proof.result,
                    cleanup_state=proof.cleanup_state,
                    reason_code=None if proof.confirmed else "DETACH_FAILED",
                ),
                cleanup_reply=True,
            )
            self._detach, self._detach_ack, self._detach_at = raw, reply, now
            return (*outcomes, reply)
        raise EncryptedStreamError()

    def _receive_input(self, frame: WireFrame, now: float) -> tuple[bytes, ...]:
        assert self._crypto is not None
        # Decrypt before queue/state rejection. Malformed/auth failures produce no ACK.
        plaintext = self._crypto.decrypt_input(frame.payload)
        sequence = decode_awce(frame.payload).crypto_sequence
        before_ack = self._tx
        try:
            with self._supervisor.runtime_attachment_guard(
                self._lease, require_writer=True, require_running=False
            ) as evidence:
                self._check(active=True)
                reason = self._input_rejection(evidence.state)
                if reason is None and (
                    len(self._input) >= 4 or self._input_bytes + len(plaintext) + 84 > 65536
                ):
                    reason = "INPUT_RATE_LIMITED"
                if reason is not None:
                    reply = self._ack(frame.hop_sequence, sequence, "rejected", reason)
                    if reason != "INPUT_RATE_LIMITED":
                        state = (
                            RuntimeProbeState.UNKNOWN
                            if reason == "RECONCILIATION_REQUIRED"
                            else evidence.state
                        )
                        return (reply, *self._process_state(state, evidence.exit_code))
                    return (reply,)
                state_frames = self._process_state(evidence.state)
                self._input.append(_PendingInput(frame.hop_sequence, sequence, plaintext, now))
                self._input_bytes += len(plaintext) + 84
                return (*state_frames, self._ack(frame.hop_sequence, sequence, "accepted", None))
        except (RuntimeOperationError, EncryptedStreamError) as exc:
            # An authority/state change after successful AEAD but before queue
            # admission is a terminal rejection; the receive nonce is spent.
            if self._tx == before_ack and not self.closed:
                code = getattr(exc, "code", "")
                reason = "ATTACHMENT_STALE" if "ATTACHMENT" in code else "RECONCILIATION_REQUIRED"
                reply = self._ack(frame.hop_sequence, sequence, "rejected", reason)
                self.close(drain_control=True)
                return (reply,)
            raise

    def _input_rejection(self, state: RuntimeProbeState) -> str | None:
        if state is RuntimeProbeState.EXITED:
            return "WORKSPACE_EXITED"
        if state is RuntimeProbeState.STOPPED:
            return "WORKSPACE_STOPPED"
        if self._supervisor.state is SupervisorState.INPUT_UNCERTAIN:
            return "RECONCILIATION_REQUIRED"
        return None if state is RuntimeProbeState.RUNNING else "WORKSPACE_NOT_RUNNING"

    def _ack(self, hop: int, crypto_sequence: int, result: str, reason: str | None) -> bytes:
        if result != "accepted":
            now = self._clock()
            self._prune_acks(now)
            if len(self._terminal_acks) < 256:
                self._terminal_acks[(hop, crypto_sequence)] = (now, result, reason, False)
        return self._emit(
            F.ACK,
            {
                "protocol_version": 1,
                "runtime_input_hop_sequence": str(hop),
                "crypto_sequence": str(crypto_sequence),
                "result": result,
                "reason_code": reason,
            },
        )

    def _prune_acks(self, now: float) -> None:
        for key, entry in tuple(self._terminal_acks.items()):
            if now >= entry[0] + 5:
                del self._terminal_acks[key]

    def replay_input_result(self, runtime_hop: int, crypto_sequence: int) -> bytes:
        """Trusted delivery retry: same terminal metadata once, next outer hop."""
        with self._lock:
            now = self._check(active=True)
            self._prune_acks(now)
            key = (runtime_hop, crypto_sequence)
            entry = self._terminal_acks.get(key)
            if entry is None or entry[3]:
                raise EncryptedStreamError()
            self._terminal_acks[key] = (*entry[:3], True)
            return self._emit(
                F.ACK,
                {
                    "protocol_version": 1,
                    "runtime_input_hop_sequence": str(runtime_hop),
                    "crypto_sequence": str(crypto_sequence),
                    "result": entry[1],
                    "reason_code": entry[2],
                },
            )

    def flush_input(self) -> tuple[bytes, ...]:
        with self._lock:
            replies: list[bytes] = []
            try:
                self._check(active=True)
                while self._input:
                    pending = self._input[0]
                    outcome = "write_uncertain"
                    try:
                        with self._supervisor.runtime_attachment_guard(
                            self._lease, require_writer=True, require_running=False
                        ) as evidence:
                            if evidence.state is not RuntimeProbeState.RUNNING:
                                replies.extend(
                                    self._process_state(evidence.state, evidence.exit_code)
                                )
                                return tuple(replies)
                            replies.extend(self._process_state(evidence.state))
                            self._input.popleft()
                            self._input_bytes -= len(pending.payload) + 84
                            self._check(active=True)
                            if self._clock() >= pending.admitted_at + 5:
                                raise EncryptedStreamError("INPUT_WRITE_UNCERTAIN")
                            self._supervisor.write_input(self._lease, pending.payload)
                            outcome = "written_to_pty"
                    except (RuntimeOperationError, EncryptedStreamError):
                        if self._input and self._input[0] is pending:
                            self._input.popleft()
                            self._input_bytes -= len(pending.payload) + 84
                    replies.append(
                        self._ack(
                            pending.hop,
                            pending.crypto_sequence,
                            outcome,
                            None if outcome == "written_to_pty" else "INPUT_WRITE_UNCERTAIN",
                        )
                    )
                    if outcome == "write_uncertain":
                        while self._input:
                            queued = self._input.popleft()
                            replies.append(
                                self._ack(
                                    queued.hop,
                                    queued.crypto_sequence,
                                    "write_uncertain",
                                    "INPUT_WRITE_UNCERTAIN",
                                )
                            )
                        self._input_bytes = 0
                        self.close(drain_control=True)
                        break
                return tuple(replies)
            except BaseException:
                self.close(drain_control=True)
                raise

    def _verify_precommit_output(self) -> tuple[OutputFrame, ...]:
        """Live bytes cannot silently expand the fixed selected admission queue."""
        replay = self._supervisor.replay_output(
            self._baseline, generation=self._lease.claims.generation, runtime_epoch=self._epoch
        )
        if replay.kind != "frames":
            raise EncryptedStreamError("OUTPUT_BACKPRESSURE")
        records = self._baseline_records + replay.frames
        size = sum(len(item.payload) + 84 for item in records)
        if self._baseline_gap is not None:
            size += len(encode_wire_frame(F.GAP, RA, self._gap_payload(self._baseline_gap), 1))
        if size > 65536 or any(len(item.payload) > OUTPUT_LIMIT for item in records):
            raise EncryptedStreamError("OUTPUT_BACKPRESSURE")
        return replay.frames

    def _prepare_output(self) -> None:
        resume = self._record.hints[0]
        head = self._supervisor.snapshot().next_cursor - 1
        if resume not in (None, "0"):
            assert resume is not None
            cursor = int(resume)
            if cursor > head:
                raise EncryptedStreamError()
            self._cursor = cursor
            replay = self._supervisor.replay_output(
                cursor, generation=self._lease.claims.generation, runtime_epoch=self._epoch
            )
            gap = None
            if replay.kind == "gap":
                assert replay.gap_start is not None and replay.gap_end is not None
                gap = (replay.gap_start, replay.gap_end + 1, "cursor_expired")
                replay = self._supervisor.replay_output(
                    replay.gap_end,
                    generation=self._lease.claims.generation,
                    runtime_epoch=self._epoch,
                )
            records = replay.frames
        else:
            try:
                publication = self._supervisor.publish_fresh_redraw(self._lease)
            except RuntimeOperationError as exc:
                if exc.code == "WAW_REDRAW_IDENTITY_UNCONFIRMED":
                    raise EncryptedStreamError("RECONCILIATION_REQUIRED") from None
                if exc.code == "WAW_REDRAW_UNAVAILABLE":
                    raise EncryptedStreamError("RUNTIME_UNAVAILABLE") from None
                if exc.code in {
                    "WAW_REDRAW_TIMEOUT",
                    "WAW_REDRAW_CAPTURE_FAILED",
                    "WAW_REDRAW_LIMIT_INVALID",
                }:
                    raise EncryptedStreamError("OUTPUT_BACKPRESSURE") from None
                raise
            records = publication.frames
            gap = (0, 0, "baseline_redraw") if publication.has_more else None
            head = publication.baseline_cursor
        self._baseline = head
        self._baseline_records, self._baseline_gap = self._select(records, gap, 65536)

    def _gap_payload(self, gap: tuple[int, int, str]) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "from_cursor": str(gap[0]),
            "to_cursor": str(gap[1]),
            "reason": gap[2],
        }

    def _select(
        self, records: tuple[OutputFrame, ...], gap: tuple[int, int, str] | None, budget: int
    ) -> tuple[tuple[OutputFrame, ...], tuple[int, int, str] | None]:
        if any(len(item.payload) > OUTPUT_LIMIT for item in records):
            raise EncryptedStreamError("OUTPUT_BACKPRESSURE")
        selected = list(records)
        while True:
            size = sum(len(item.payload) + 84 for item in selected)
            if gap is not None:
                size += len(encode_wire_frame(F.GAP, RA, self._gap_payload(gap), 1))
            if size <= budget:
                return tuple(selected), gap
            if len(selected) <= 1 or (gap is not None and gap[2] == "baseline_redraw"):
                raise EncryptedStreamError("OUTPUT_BACKPRESSURE")
            omitted = selected.pop(0)
            start = gap[0] if gap is not None else omitted.start_cursor
            gap = (start, omitted.end_cursor + 1, "slow_client")

    def output(self, *, maximum_encoded_bytes: int = 65536) -> tuple[bytes, ...]:
        with self._lock:
            try:
                now = self._check(active=True)
                if int(now) != self._output_window:
                    self._output_window, self._output_used = int(now), 0
                if self._output_used + maximum_encoded_bytes > 1024 * 1024:
                    return ()
                if (
                    type(maximum_encoded_bytes) is not int
                    or not 512 <= maximum_encoded_bytes <= 65536
                ):
                    raise ValueError("invalid encoded output budget")
                with self._supervisor.runtime_attachment_guard(
                    self._lease, require_writer=True, require_running=False
                ) as evidence:
                    self._check(active=True)
                    state_frames = self._process_state(evidence.state, evidence.exit_code)
                    if state_frames or evidence.state is not RuntimeProbeState.RUNNING:
                        return state_frames
                    if not self._baseline_sent:
                        records, gap = self._select(
                            self._baseline_records, self._baseline_gap, maximum_encoded_bytes
                        )
                        self._baseline_sent = True
                        self._baseline_records, self._baseline_gap = (), None
                        next_cursor = records[-1].end_cursor if records else self._baseline
                    else:
                        replay = self._supervisor.replay_output(
                            self._cursor,
                            generation=self._lease.claims.generation,
                            runtime_epoch=self._epoch,
                            attachment=self._lease,
                        )
                        gap = None
                        if replay.kind == "gap":
                            assert replay.gap_start is not None and replay.gap_end is not None
                            gap = (replay.gap_start, replay.gap_end + 1, "ring_overflow")
                            replay = self._supervisor.replay_output(
                                replay.gap_end,
                                generation=self._lease.claims.generation,
                                runtime_epoch=self._epoch,
                                attachment=self._lease,
                            )
                        records, gap = self._select(replay.frames, gap, maximum_encoded_bytes)
                        next_cursor = self._supervisor.snapshot().next_cursor - 1
                    result: list[bytes] = []
                    if gap is not None:
                        result.append(self._emit(F.GAP, self._gap_payload(gap)))
                    assert self._crypto is not None
                    for record in records:
                        self._check(active=True)
                        result.append(
                            self._emit(
                                F.OUTPUT,
                                self._crypto.encrypt_output(
                                    record.payload, stream_cursor=record.end_cursor
                                ),
                            )
                        )
                    self._check(active=True)
                    self._cursor = next_cursor
                    self._output_used += sum(len(frame) for frame in result)
                    return tuple(result)
            except WAWCryptoError:
                self.close(clear_reason="crypto_failure", drain_control=True)
                raise EncryptedStreamError("STREAM_CRYPTO_FAILURE") from None
            except BaseException:
                self.close(drain_control=True)
                raise

    def ping(self) -> bytes:
        """Bounded Runtime-originated hop-local health request, never a lease renewal."""
        with self._lock:
            now = self._check(active=True)
            self._sent_ping_tokens = min(
                2.0, self._sent_ping_tokens + (now - self._sent_ping_tick) * 2
            )
            self._sent_ping_tick = now
            if len(self._pings) >= 2 or self._sent_ping_tokens < 1:
                raise EncryptedStreamError("CONTROL_RATE_LIMITED")
            nonce = secrets.token_hex(8)
            if nonce in self._pings:
                raise EncryptedStreamError("RANDOMNESS_UNAVAILABLE")
            tick = str(max(1, int(now * 1000)))
            self._pings[nonce] = (tick, now + 5)
            self._sent_ping_tokens -= 1
            return self._emit(
                F.PING, {"protocol_version": 1, "nonce": nonce, "sent_at_monotonic_tick": tick}
            )

    def tick(self) -> tuple[bytes, ...]:
        with self._lock:
            try:
                now = self._check(check_health=False)
                if not self.committed:
                    self._verify_precommit_output()
                    assert self._crypto is not None
                    self._crypto.check_deadline()
                    return ()
                if self._health_expired(now):
                    reply = self._emit(
                        F.CLOSE,
                        {
                            "protocol_version": 1,
                            "code": "RUNTIME_UNAVAILABLE",
                            "workspace_state_at_close": self._workspace_state(),
                        },
                    )
                    self.close(drain_control=True)
                    return (reply,)
                with self._supervisor.runtime_attachment_guard(
                    self._lease, require_writer=True, require_running=False
                ) as evidence:
                    state_frames = self._process_state(evidence.state, evidence.exit_code)
                    if state_frames:
                        return state_frames
                if now >= self._last_sent_health + 5:
                    self._last_sent_health = now
                    return (
                        self._emit(
                            F.HEARTBEAT,
                            {
                                "protocol_version": 1,
                                "attachment_id": self._lease.attachment_id,
                                "lease_number": str(self._lease.claims.lease_number),
                                "sent_at_monotonic_tick": str(max(1, int(now * 1000))),
                            },
                        ),
                    )
                return ()
            except BaseException:
                self.close(drain_control=True)
                raise

    def _workspace_state(self) -> str:
        state = self._supervisor.state.value
        return (
            "RUNNING"
            if state in {"DETACHED", "INPUT_UNCERTAIN"}
            else state if state in {"RUNNING", "STOPPED", "STOPPING", "BROKEN"} else "UNKNOWN"
        )

    def _process_state(
        self,
        state: RuntimeProbeState,
        exit_code: int | None = None,
    ) -> tuple[bytes, ...]:
        """Publish observed state without inventing process-exit evidence."""
        if state in {RuntimeProbeState.EXITED, RuntimeProbeState.STOPPED}:
            return self._terminal(state, exit_code)
        replies: list[bytes] = []
        if state is not RuntimeProbeState.RUNNING:
            while self._input:
                pending = self._input.popleft()
                replies.append(
                    self._ack(
                        pending.hop,
                        pending.crypto_sequence,
                        "write_uncertain",
                        "INPUT_WRITE_UNCERTAIN",
                    )
                )
            self._input_bytes = 0
        if state is not self._observed_process_state:
            self._observed_process_state = state
            reason = {
                RuntimeProbeState.LOGIN_REQUIRED: "WORKSPACE_AUTH_REQUIRED",
                RuntimeProbeState.TRUST_REQUIRED: "WORKSPACE_TRUST_REQUIRED",
                RuntimeProbeState.MISSING: "WORKSPACE_MISSING",
                RuntimeProbeState.COLLISION: "WORKSPACE_COLLISION",
                RuntimeProbeState.UNKNOWN: "RECONCILIATION_REQUIRED",
            }.get(state)
            replies.append(
                self._emit(
                    F.STATE,
                    {
                        "protocol_version": 1,
                        "workspace_id": self._admission["workspace_id"],
                        "project_id": self._admission["project_id"],
                        "agent_type": self._admission["agent_type"],
                        "generation": self._admission["generation"],
                        "runtime_epoch": self._epoch,
                        "state": state.value,
                        "reason_code": reason,
                    },
                )
            )
        if state not in {RuntimeProbeState.RUNNING, RuntimeProbeState.NEEDS_INTERACTION}:
            replies.append(
                self._emit(
                    F.CLOSE,
                    {
                        "protocol_version": 1,
                        "code": "ATTACHMENT_STALE",
                        "workspace_state_at_close": state.value,
                    },
                )
            )
            self.close(drain_control=True)
        return tuple(replies)

    def _terminal(
        self, state: RuntimeProbeState, exit_code: int | None = None
    ) -> tuple[bytes, ...]:
        if state not in {RuntimeProbeState.EXITED, RuntimeProbeState.STOPPED}:
            raise EncryptedStreamError("RECONCILIATION_REQUIRED")
        replies = []
        while self._input:
            pending = self._input.popleft()
            replies.append(
                self._ack(
                    pending.hop, pending.crypto_sequence, "write_uncertain", "INPUT_WRITE_UNCERTAIN"
                )
            )
        self._input_bytes = 0
        terminal = (
            state.value
            if state
            in {
                RuntimeProbeState.EXITED,
                RuntimeProbeState.STOPPED,
                RuntimeProbeState.MISSING,
                RuntimeProbeState.COLLISION,
                RuntimeProbeState.UNKNOWN,
            }
            else "BROKEN"
        )
        replies.append(
            self._emit(F.EXIT, {"protocol_version": 1, "state": terminal, "exit_code": exit_code})
        )
        replies.append(
            self._emit(
                F.CLOSE,
                {
                    "protocol_version": 1,
                    "code": (
                        "WORKSPACE_STOPPED"
                        if state is RuntimeProbeState.STOPPED
                        else "WORKSPACE_EXITED"
                    ),
                    "workspace_state_at_close": terminal,
                },
            )
        )
        self.close(clear_reason="exit", drain_control=True)
        return tuple(replies)

    def publish_chunk(self, raw: bytes, offset: int) -> int:
        """Check each actual nonblocking socket write under the attachment lock.

        A writable await never carries permission forward: the server calls
        this method again afterward. Control-drain frames cannot contain output.
        """
        with self._lock:
            publication = self._publication
            if publication is None or self._publication_fenced:
                raise EncryptedStreamError("ATTACHMENT_STALE")
            if self.closed:
                if (
                    self._control_drain_until is None
                    or self._clock() >= self._control_drain_until
                    or not self._record.peer.current()
                    or len(raw) < 24
                    or raw[5] not in {F.ACK, F.STATE, F.EXIT, F.ERROR, F.CLOSE, F.DETACH_ACK}
                ):
                    raise EncryptedStreamError("ATTACHMENT_STALE")
            else:
                self._check()
            return publication.send(memoryview(raw)[offset:])

    def publication_timeout(self, maximum: float) -> float:
        """Bound a socket-writable wait by the same current publication deadline."""
        with self._lock:
            now = self._clock()
            if self.closed:
                if self._control_drain_until is None:
                    raise EncryptedStreamError("ATTACHMENT_STALE")
                deadline = self._control_drain_until
            elif self._phase == "COMMITTED":
                deadline = min(
                    [self._last_health + 10, *(entry[1] for entry in self._pings.values())]
                )
            else:
                deadline = self._record.started + 5
            return max(0.0, min(maximum, deadline - now))

    def invalidate(self) -> bool:
        """Synchronously revoke the socket without taking the registry lock."""
        self._closing.set()
        self._control_drain_until = None
        if self._publication is not None:
            try:
                self._publication_fenced = self._publication.fence() is True
            except Exception:
                self._publication_fenced = False
        return self._publication_fenced

    def close(
        self,
        *,
        clear_reason: str | None = None,
        drain_control: bool = False,
    ) -> RuntimeCleanup:
        if drain_control:
            self._closing.set()
            if self._control_drain_until is None and not self._publication_fenced:
                self._control_drain_until = self._clock() + 1.0
        else:
            self.invalidate()

        return self._close_after_invalidation(
            clear_reason=clear_reason,
            drain_control=drain_control,
        )

    def _close_after_invalidation(
        self,
        *,
        clear_reason: str | None = None,
        drain_control: bool = False,
    ) -> RuntimeCleanup:
        """Finish cleanup without retrying an already attempted publication fence."""
        cleanup_failed = not drain_control and not self._publication_fenced
        if self._crypto is not None:
            try:
                self._crypto.destroy()
            except Exception:
                cleanup_failed = True
        with self._lock:
            if self._cleanup_proof is not None and self._cleanup_proof.confirmed:
                if cleanup_failed:
                    return RuntimeCleanup(
                        self._lease.claims, self._epoch, "rejected", "ATTACH_PTY_CLOSE_UNCERTAIN"
                    )
                if self._publication_fenced:
                    try:
                        self._registry._cleanup(self._record)
                    except Exception:
                        return RuntimeCleanup(
                            self._lease.claims,
                            self._epoch,
                            "rejected",
                            "ATTACH_PTY_CLOSE_UNCERTAIN",
                        )
                return self._cleanup_proof
            self._phase = "CLOSED"
            self._input.clear()
            self._terminal_acks.clear()
            self._pings.clear()
            self._input_bytes = 0
            self._baseline_records, self._baseline_gap = (), None
            if clear_reason is not None:
                try:
                    self._supervisor.clear_runtime_output(clear_reason)
                except Exception:
                    cleanup_failed = True
            try:
                proof = self._registry._cleanup(
                    self._record,
                    release=not cleanup_failed and self._publication_fenced,
                )
            except Exception:
                proof = RuntimeCleanup(
                    self._lease.claims, self._epoch, "rejected", "ATTACH_PTY_CLOSE_UNCERTAIN"
                )
            self._cleanup_proof = (
                proof
                if not cleanup_failed
                else RuntimeCleanup(
                    self._lease.claims, self._epoch, "rejected", "ATTACH_PTY_CLOSE_UNCERTAIN"
                )
            )
            return self._cleanup_proof

    def __repr__(self) -> str:
        return "WAWEncryptedSession(<Runtime-owned>)"


class WAWEncryptedAttachmentService:
    """Fixed control prepare/detach adapter; no synthetic capability fallback.

    The enclosing control server must admit the exact bound sole API process.
    Providers are trusted Runtime composition inputs, never wire parameters.
    """

    def __init__(
        self,
        registry: WAWEncryptedRegistry,
        *,
        peer: Callable[[], RuntimePeer],
        supervisor: Callable[[AttachmentTuple], WAWSupervisor],
        current: Callable[[AttachmentTuple], bool],
    ) -> None:
        self.registry = registry
        self._peer_provider, self._supervisor_provider = peer, supervisor
        self._current = current
        self._bound_authority: tuple[object, str, bytes] | None = None
        self._detach_requests: OrderedDict[
            str, tuple[str, AttachmentTuple, object, float, dict[str, Any]]
        ] = OrderedDict()

    def _runtime_peer(self, peer: RuntimePeer | None) -> RuntimePeer:
        peer = self._peer_provider() if peer is None else peer
        self.registry._peer(peer)
        return peer

    def bind_authority(
        self,
        request: dict[str, Any],
        peer: RuntimePeer | None = None,
    ) -> None:
        with self.registry._lock:
            peer = self._runtime_peer(peer)
            if request["api_authority_epoch"] != peer.api_authority_epoch:
                raise EncryptedStreamError("RUNTIME_PEER_FORBIDDEN")
            digest = hashlib.sha256(request["authority_nonce"].encode("ascii")).digest()
            current = self._bound_authority
            if current is not None and (
                current[0] is not peer.identity
                or current[1] != peer.api_authority_epoch
                or not hmac.compare_digest(current[2], digest)
            ):
                raise EncryptedStreamError("RUNTIME_PEER_FORBIDDEN")
            self._bound_authority = (peer.identity, peer.api_authority_epoch, digest)

    def _bound_peer(self, peer: RuntimePeer | None) -> RuntimePeer:
        peer = self._runtime_peer(peer)
        bound = self._bound_authority
        if bound is None or bound[0] is not peer.identity or bound[1] != peer.api_authority_epoch:
            raise EncryptedStreamError("RUNTIME_PEER_FORBIDDEN")
        return peer

    def revoke_authority(self, identity: object) -> bool:
        """Drop one bound API authority and its exact attachment/cache state."""
        with self.registry._lock:
            bound = self._bound_authority
            if bound is not None and bound[0] is identity:
                self._bound_authority = None
            for attachment_id, entry in tuple(self._detach_requests.items()):
                if entry[2] is identity:
                    del self._detach_requests[attachment_id]
            return self.registry.revoke_authority(identity)

    def _claims(self, request: dict[str, Any]) -> AttachmentTuple:
        values = {key: request[key] for key in ADMISSION_KEYS}
        validate_admission(values)
        for key in (
            "lease_number",
            "generation",
            "auth_epoch",
            "api_authority_epoch",
            "runtime_host_installation_revision",
            "binding_revision",
        ):
            values[key] = int(values[key])
        if request["runtime_epoch"] != self.registry.runtime_epoch:
            raise EncryptedStreamError("ATTACHMENT_STALE")
        return AttachmentTuple(**values)

    def prepare(
        self,
        request: dict[str, Any],
        peer: RuntimePeer | None = None,
    ) -> dict[str, Any]:
        with self.registry._lock:
            claims = self._claims(request)
            capability = self.registry.prepare(
                peer=self._bound_peer(peer),
                claims=claims,
                supervisor=self._supervisor_provider(claims),
                current=lambda: self._current(claims),
                resume_cursor=request["resume_cursor"],
                previous_runtime_epoch=request["previous_runtime_epoch"],
            )
            return {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "PREPARED",
                **admission_fields(claims),
                "runtime_epoch": self.registry.runtime_epoch,
                "resume_cursor": request["resume_cursor"],
                "previous_runtime_epoch": request["previous_runtime_epoch"],
                "capability": capability,
            }

    def detach(
        self,
        request: dict[str, Any],
        peer: RuntimePeer | None = None,
    ) -> dict[str, Any]:
        with self.registry._lock:
            claims = self._claims(request)
            peer = self._bound_peer(peer)
            now = self.registry._now()
            for attachment_id, entry in tuple(self._detach_requests.items()):
                if now >= entry[3]:
                    del self._detach_requests[attachment_id]
            cached = self._detach_requests.get(claims.attachment_id)
            if cached is not None:
                if (
                    cached[0] != request["request_id"]
                    or cached[1] != claims
                    or cached[2] is not peer.identity
                ):
                    raise EncryptedStreamError("ATTACHMENT_STALE")
                if cached[4]["cleanup_state"] == "ATTACH_PTY_CLOSED":
                    return dict(cached[4])
            elif len(self._detach_requests) >= 1024:
                raise EncryptedStreamError("RUNTIME_UNAVAILABLE")
            proof = self.registry.cleanup(peer, claims)
            result = {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "DETACHED" if proof.confirmed else "REJECTED",
                **admission_fields(claims),
                "runtime_epoch": self.registry.runtime_epoch,
                "cleanup_state": proof.cleanup_state,
                "reason_code": None if proof.confirmed else "RECONCILIATION_REQUIRED",
            }
            self._detach_requests[claims.attachment_id] = (
                request["request_id"],
                claims,
                peer.identity,
                now + 300,
                result,
            )
            return result
