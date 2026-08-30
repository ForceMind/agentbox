"""Bounded in-memory WAW attachment ticket and writer-lease authority.

The authority is intentionally an adapter-free primitive.  It keeps only
ticket digests and metadata; bearer ticket text is returned to the caller once
and is never retained by the authority.  API/Runtime adapters must perform
their own authentication and persistence transactions around this object.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from threading import RLock

from agentbox_core.waw import (
    AgentType,
    WAWDomainError,
    validate_attachment_id,
    validate_binding_digest,
    validate_positive_u64,
    validate_project_id,
    validate_runtime_host_installation_id,
    validate_workspace_id,
)

_MAX_U64 = 2**64 - 1
_TICKET_PREFIX = "wat_"
_TOKEN_LENGTH = 32
_DECIMAL_U64 = re.compile(r"\A[1-9][0-9]{0,19}\Z")


class TicketErrorCode(StrEnum):
    """Stable bounded ticket/lease rejection classes."""

    INVALID = "ATTACHMENT_TICKET_INVALID"
    EXPIRED = "ATTACHMENT_TICKET_EXPIRED"
    REPLAYED = "ATTACHMENT_TICKET_REPLAYED"
    STALE = "ATTACHMENT_STALE"
    WRITER_BUSY = "WORKSPACE_WRITER_BUSY"
    CAPACITY = "ATTACHMENT_TICKET_UNAVAILABLE"
    SEQUENCE_EXHAUSTED = "SEQUENCE_EXHAUSTED"
    LEASE_EXPIRED = "ATTACHMENT_LEASE_EXPIRED"
    LEASE_MISMATCH = "ATTACHMENT_LEASE_MISMATCH"


class TicketAuthorityError(WAWDomainError):
    """A bounded ticket authority rejection with a stable public code."""

    def __init__(self, code: TicketErrorCode, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code.value)


@dataclass(frozen=True)
class AuthenticatedAttachmentContext:
    """API-only identity bound to a ticket/lease, never sent to Runtime."""

    session_id: str
    user_id: str
    authorization_scope: str
    origin: str
    runtime_epoch: str

    def __post_init__(self) -> None:
        for name, value, maximum in (
            ("session_id", self.session_id, 128),
            ("user_id", self.user_id, 128),
            ("authorization_scope", self.authorization_scope, 128),
            ("origin", self.origin, 256),
        ):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > maximum
                or any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in value)
            ):
                raise TicketAuthorityError(TicketErrorCode.INVALID, f"{name} is invalid")
        if (
            not isinstance(self.runtime_epoch, str)
            or _DECIMAL_U64.fullmatch(self.runtime_epoch) is None
            or int(self.runtime_epoch) > _MAX_U64
        ):
            raise TicketAuthorityError(TicketErrorCode.INVALID, "runtime_epoch is invalid")


@dataclass(frozen=True)
class AttachmentTuple:
    """The non-secret tuple that binds a ticket and lease to one generation."""

    workspace_id: str
    project_id: str
    agent_type: AgentType | str
    attachment_id: str
    lease_number: int
    generation: int
    auth_epoch: int
    api_authority_epoch: int
    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    binding_revision: int
    binding_digest: str
    mode: str = "writer"

    def __post_init__(self) -> None:
        validate_workspace_id(self.workspace_id)
        validate_project_id(self.project_id)
        try:
            agent = (
                self.agent_type
                if isinstance(self.agent_type, AgentType)
                else AgentType(self.agent_type)
            )
        except (TypeError, ValueError) as exc:
            raise TicketAuthorityError(TicketErrorCode.INVALID, "agent_type is invalid") from exc
        object.__setattr__(self, "agent_type", agent)
        validate_attachment_id(self.attachment_id)
        validate_positive_u64(self.lease_number, field="lease_number")
        validate_positive_u64(self.generation, field="generation")
        validate_positive_u64(self.auth_epoch, field="auth_epoch")
        validate_positive_u64(self.api_authority_epoch, field="api_authority_epoch")
        validate_runtime_host_installation_id(self.runtime_host_installation_id)
        validate_positive_u64(
            self.runtime_host_installation_revision,
            field="runtime_host_installation_revision",
        )
        validate_positive_u64(self.binding_revision, field="binding_revision")
        validate_binding_digest(self.binding_digest)
        if self.mode != "writer":
            raise TicketAuthorityError(TicketErrorCode.INVALID, "mode must be writer")


@dataclass(frozen=True)
class IssuedAttachmentTicket:
    """One transient response containing a bearer and its server-issued claims."""

    ticket: str
    claims: AttachmentTuple
    issued_at_monotonic: float
    expires_at_monotonic: float
    expires_at: datetime

    def __post_init__(self) -> None:
        if len(self.ticket) != len(_TICKET_PREFIX) + _TOKEN_LENGTH or not self.ticket.startswith(
            _TICKET_PREFIX
        ):
            raise TicketAuthorityError(TicketErrorCode.INVALID, "ticket format is invalid")
        try:
            int(self.ticket[len(_TICKET_PREFIX) :], 16)
        except ValueError as exc:
            raise TicketAuthorityError(TicketErrorCode.INVALID, "ticket format is invalid") from exc
        if self.expires_at_monotonic < self.issued_at_monotonic:
            raise TicketAuthorityError(TicketErrorCode.INVALID, "ticket expiry precedes issuance")


@dataclass(frozen=True)
class ActiveAttachment:
    """An admitted writer lease; terminal bytes and credentials are absent."""

    claims: AttachmentTuple
    opened_at_monotonic: float
    last_heartbeat_monotonic: float
    lease_expires_at_monotonic: float
    absolute_expires_at_monotonic: float
    context: AuthenticatedAttachmentContext | None = field(default=None, repr=False, compare=False)

    @property
    def workspace_id(self) -> str:
        return self.claims.workspace_id

    @property
    def attachment_id(self) -> str:
        return self.claims.attachment_id

    def active_at(self, now: float) -> bool:
        return now < self.lease_expires_at_monotonic and now < self.absolute_expires_at_monotonic


@dataclass(frozen=True)
class _PendingTicket:
    digest: bytes
    claims: AttachmentTuple
    issued_at_monotonic: float
    expires_at_monotonic: float
    context: AuthenticatedAttachmentContext | None = field(default=None, repr=False)


class AttachmentAuthority:
    """Single-process, bounded ticket and one-writer lease authority.

    ``clock`` must be a monotonic source.  The default is ``time.monotonic``;
    wall-clock ``expires_at`` is display metadata only.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        authority_epoch: int | None = None,
        lease_seed: int | None = None,
        ticket_ttl_seconds: float = 30.0,
        lease_ttl_seconds: float = 60.0,
        absolute_lease_seconds: float = 300.0,
        max_records: int = 64,
        replay_cache_size: int = 256,
    ) -> None:
        if ticket_ttl_seconds <= 0 or lease_ttl_seconds <= 0 or absolute_lease_seconds <= 0:
            raise ValueError("ticket and lease TTLs must be positive")
        if lease_ttl_seconds > absolute_lease_seconds:
            raise ValueError("lease TTL cannot exceed absolute lease lifetime")
        if max_records < 1 or replay_cache_size < 1:
            raise ValueError("authority capacities must be positive")
        self._clock = clock
        self._authority_epoch = _u64_or_random(authority_epoch)
        self._next_lease_number = _u64_or_random(lease_seed)
        self._ticket_ttl = ticket_ttl_seconds
        self._lease_ttl = lease_ttl_seconds
        self._absolute_lease = absolute_lease_seconds
        self._max_records = max_records
        self._pending: dict[bytes, _PendingTicket] = {}
        self._active: dict[str, ActiveAttachment] = {}
        self._replayed: deque[bytes] = deque(maxlen=replay_cache_size)
        self._lock = RLock()

    @property
    def authority_epoch(self) -> int:
        return self._authority_epoch

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._pending) + len(self._active)

    def issue(
        self,
        *,
        workspace_id: str,
        project_id: str,
        agent_type: AgentType | str,
        attachment_id: str,
        generation: int,
        auth_epoch: int,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: int,
        binding_revision: int,
        binding_digest: str,
        origin: str = "https://agentbox.invalid",
        expires_at: datetime | None = None,
        context: AuthenticatedAttachmentContext | None = None,
    ) -> IssuedAttachmentTicket:
        """Reserve one pending ticket without acquiring the writer slot."""

        with self._lock:
            now = self._clock()
            self.sweep(now=now)
            if len(self._pending) + len(self._active) >= self._max_records:
                raise TicketAuthorityError(
                    TicketErrorCode.CAPACITY, "attachment capacity is exhausted"
                )
            if not isinstance(origin, str) or not origin or len(origin) > 256:
                raise TicketAuthorityError(TicketErrorCode.INVALID, "origin is invalid")
            lease_number = self._allocate_lease_number()
            claims = AttachmentTuple(
                workspace_id=workspace_id,
                project_id=project_id,
                agent_type=agent_type,
                attachment_id=attachment_id,
                lease_number=lease_number,
                generation=generation,
                auth_epoch=auth_epoch,
                api_authority_epoch=self._authority_epoch,
                runtime_host_installation_id=runtime_host_installation_id,
                runtime_host_installation_revision=runtime_host_installation_revision,
                binding_revision=binding_revision,
                binding_digest=binding_digest,
            )
            # Origin is validated by the API boundary and is not needed here.
            del origin
            issued = IssuedAttachmentTicket(
                ticket=_new_ticket(),
                claims=claims,
                issued_at_monotonic=now,
                expires_at_monotonic=now + self._ticket_ttl,
                expires_at=expires_at or datetime.fromtimestamp(0),
            )
            digest = _ticket_digest(issued.ticket)
            if digest in self._pending or digest in self._replayed:
                raise TicketAuthorityError(TicketErrorCode.CAPACITY, "ticket collision")
            self._pending[digest] = _PendingTicket(
                digest,
                claims,
                issued.issued_at_monotonic,
                issued.expires_at_monotonic,
                context,
            )
            return issued

    def consume(
        self,
        ticket: str,
        expected: AttachmentTuple,
        *,
        now: float | None = None,
        context: AuthenticatedAttachmentContext | None = None,
    ) -> ActiveAttachment:
        """Atomically consume a ticket and acquire the workspace writer slot."""

        with self._lock:
            current = self._clock() if now is None else now
            digest = _ticket_digest(ticket)
            pending = self._pending.pop(digest, None)
            if pending is None:
                if digest in self._replayed:
                    raise TicketAuthorityError(
                        TicketErrorCode.REPLAYED, "ticket was already consumed"
                    )
                raise TicketAuthorityError(TicketErrorCode.INVALID, "ticket is unknown")
            self._replayed.append(digest)
            if current >= pending.expires_at_monotonic:
                raise TicketAuthorityError(TicketErrorCode.EXPIRED, "ticket has expired")
            if not _same_tuple(pending.claims, expected):
                raise TicketAuthorityError(TicketErrorCode.STALE, "ticket tuple does not match")
            if pending.context is not None and not _same_context(pending.context, context):
                raise TicketAuthorityError(TicketErrorCode.STALE, "ticket context does not match")
            if expected.workspace_id in self._active:
                active = self._active[expected.workspace_id]
                if active.active_at(current):
                    raise TicketAuthorityError(
                        TicketErrorCode.WRITER_BUSY, "workspace writer is busy"
                    )
                del self._active[expected.workspace_id]
            lease = ActiveAttachment(
                claims=expected,
                opened_at_monotonic=current,
                last_heartbeat_monotonic=current,
                lease_expires_at_monotonic=current + self._lease_ttl,
                absolute_expires_at_monotonic=current + self._absolute_lease,
                context=pending.context,
            )
            self._active[expected.workspace_id] = lease
            return lease

    def heartbeat(
        self,
        expected: AttachmentTuple,
        *,
        now: float | None = None,
        context: AuthenticatedAttachmentContext | None = None,
    ) -> ActiveAttachment:
        """Renew an exact active lease without changing its lease number."""

        with self._lock:
            current = self._clock() if now is None else now
            active = self._active.get(expected.workspace_id)
            if (
                active is None
                or not _same_tuple(active.claims, expected)
                or not _same_context(active.context, context)
            ):
                raise TicketAuthorityError(TicketErrorCode.LEASE_MISMATCH, "lease does not match")
            if not active.active_at(current):
                del self._active[expected.workspace_id]
                raise TicketAuthorityError(TicketErrorCode.LEASE_EXPIRED, "lease has expired")
            renewed_until = min(current + self._lease_ttl, active.absolute_expires_at_monotonic)
            updated = replace(
                active,
                last_heartbeat_monotonic=current,
                lease_expires_at_monotonic=renewed_until,
            )
            self._active[expected.workspace_id] = updated
            return updated

    def is_active(
        self,
        expected: AttachmentTuple,
        *,
        now: float | None = None,
        context: AuthenticatedAttachmentContext | None = None,
    ) -> bool:
        """Return whether the exact authority-held lease is still current."""

        with self._lock:
            current = self._clock() if now is None else now
            active = self._active.get(expected.workspace_id)
            if (
                active is None
                or not _same_tuple(active.claims, expected)
                or not _same_context(active.context, context)
            ):
                return False
            if not active.active_at(current):
                del self._active[expected.workspace_id]
                return False
            return True

    def detach(
        self,
        expected: AttachmentTuple,
        *,
        now: float | None = None,
        context: AuthenticatedAttachmentContext | None = None,
    ) -> ActiveAttachment:
        """Release only the exact active lease; stale callers cannot free a new writer."""

        with self._lock:
            current = self._clock() if now is None else now
            active = self._active.get(expected.workspace_id)
            if (
                active is None
                or not _same_tuple(active.claims, expected)
                or not _same_context(active.context, context)
            ):
                raise TicketAuthorityError(TicketErrorCode.LEASE_MISMATCH, "lease does not match")
            if not active.active_at(current):
                del self._active[expected.workspace_id]
                raise TicketAuthorityError(TicketErrorCode.LEASE_EXPIRED, "lease has expired")
            del self._active[expected.workspace_id]
            return active

    def invalidate_all(self) -> None:
        """Invalidate all volatile authority state on API restart/shutdown."""

        with self._lock:
            for digest in self._pending:
                self._replayed.append(digest)
            self._pending.clear()
            self._active.clear()

    def sweep(self, *, now: float | None = None) -> tuple[str, ...]:
        """Remove expired pending tickets and leases without evicting live records."""

        with self._lock:
            current = self._clock() if now is None else now
            expired: list[str] = []
            for digest, pending in tuple(self._pending.items()):
                if current >= pending.expires_at_monotonic:
                    del self._pending[digest]
                    self._replayed.append(digest)
                    expired.append(pending.claims.attachment_id)
            for workspace, active in tuple(self._active.items()):
                if not active.active_at(current):
                    del self._active[workspace]
                    expired.append(active.attachment_id)
            return tuple(expired)

    def _allocate_lease_number(self) -> int:
        number = self._next_lease_number
        if number == 0:
            number = 1
        if number > _MAX_U64:
            raise TicketAuthorityError(TicketErrorCode.SEQUENCE_EXHAUSTED)
        self._next_lease_number = number + 1
        return number


def _u64_or_random(value: int | None) -> int:
    if value is None:
        return secrets.randbelow(_MAX_U64) + 1
    validate_positive_u64(value)
    return value


def _new_ticket() -> str:
    return f"{_TICKET_PREFIX}{secrets.token_hex(16)}"


def _ticket_digest(ticket: str) -> bytes:
    if not isinstance(ticket, str) or len(ticket) != len(_TICKET_PREFIX) + _TOKEN_LENGTH:
        raise TicketAuthorityError(TicketErrorCode.INVALID, "ticket format is invalid")
    if not ticket.startswith(_TICKET_PREFIX):
        raise TicketAuthorityError(TicketErrorCode.INVALID, "ticket format is invalid")
    raw = ticket[len(_TICKET_PREFIX) :]
    if any(character not in "0123456789abcdef" for character in raw):
        raise TicketAuthorityError(TicketErrorCode.INVALID, "ticket format is invalid")
    return hashlib.sha256(ticket.encode("ascii")).digest()


def _same_tuple(left: AttachmentTuple, right: AttachmentTuple) -> bool:
    """Compare every immutable claim, including authority epoch and mode."""

    fields = (
        "workspace_id",
        "project_id",
        "agent_type",
        "attachment_id",
        "lease_number",
        "generation",
        "auth_epoch",
        "api_authority_epoch",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "binding_revision",
        "binding_digest",
        "mode",
    )
    return all(
        hmac.compare_digest(str(getattr(left, field)), str(getattr(right, field)))
        for field in fields
    )


def _same_context(
    left: AuthenticatedAttachmentContext | None,
    right: AuthenticatedAttachmentContext | None,
) -> bool:
    """Compare API-only session context without exposing it to Runtime/wire."""

    if left is None or right is None:
        return left is None and right is None
    fields = ("session_id", "user_id", "authorization_scope", "origin", "runtime_epoch")
    return all(hmac.compare_digest(getattr(left, field), getattr(right, field)) for field in fields)


__all__ = [
    "ActiveAttachment",
    "AuthenticatedAttachmentContext",
    "AttachmentAuthority",
    "AttachmentTuple",
    "IssuedAttachmentTicket",
    "TicketAuthorityError",
    "TicketErrorCode",
]
