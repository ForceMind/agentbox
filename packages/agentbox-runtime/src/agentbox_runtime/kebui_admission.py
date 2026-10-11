"""Default-off K2 admission candidate for synthetic, metadata-only test ports.

There is no production constructor, wire action, content processor or execution
writer here. The journal's active-turn reservation does not authorize a writer.
S03 immutable content equality and a production current-owner port remain absent.
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import Awaitable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Protocol

from agentbox_core.kebui_observation import ConversationScope, KebuiObservationError, parse_scope

SYNTHETIC_ADAPTER_PROFILE = "kebui-synthetic-adapter-v1"
MAX_REVISION = 2**64 - 1


class KebuiAdmissionError(RuntimeError):
    """Fixed safe error codes, never copied content, paths or adapter errors."""


class AdmissionPhase(StrEnum):
    ACCEPTED = "accepted"
    DISPATCH_FENCED = "dispatch_fenced"
    ACKNOWLEDGED = "acknowledged"
    TERMINAL = "terminal"
    REJECTED_BEFORE_DISPATCH = "rejected_before_dispatch"
    UNKNOWN = "unknown"


FINISHED_PHASES = frozenset({AdmissionPhase.TERMINAL, AdmissionPhase.REJECTED_BEFORE_DISPATCH})
TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})


def validate_id(value: object, prefix: str) -> str:
    if type(value) is not str or len(value) != len(prefix) + 32:
        raise KebuiAdmissionError("invalid_metadata")
    if not re.fullmatch(re.escape(prefix) + "[0-9a-f]{32}", value):
        raise KebuiAdmissionError("invalid_metadata")
    return value


def validate_revision(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 20
        or not re.fullmatch("[1-9][0-9]{0,19}", value)
        or int(value) > MAX_REVISION
    ):
        raise KebuiAdmissionError("invalid_metadata")
    return value


def scope_metadata(scope: ConversationScope) -> dict[str, object]:
    if type(scope) is not ConversationScope:
        raise KebuiAdmissionError("invalid_metadata")
    value = {field.name: getattr(scope, field.name) for field in fields(ConversationScope)}
    # The existing parser returns an AgentType enum; do not coerce caller fields.
    value["agent_type"] = scope.agent_type.value
    return value


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    request_id: str
    scope: ConversationScope
    adapter_profile: str
    content_admission_ref: str
    operation: str = "submit_turn"

    def __post_init__(self) -> None:
        validate_id(self.request_id, "kreq_")
        validate_id(self.content_admission_ref, "ksyn_")
        if (
            type(self.adapter_profile) is not str
            or self.adapter_profile != SYNTHETIC_ADAPTER_PROFILE
            or type(self.operation) is not str
            or self.operation != "submit_turn"
        ):
            raise KebuiAdmissionError("invalid_metadata")
        try:
            validated = parse_scope(scope_metadata(self.scope))
        except (KebuiObservationError, AttributeError, TypeError, ValueError):
            raise KebuiAdmissionError("invalid_metadata") from None
        if validated != self.scope:
            raise KebuiAdmissionError("invalid_metadata")


@dataclass(frozen=True, slots=True)
class AdmissionRecord:
    request: AdmissionRequest
    execution_id: str
    phase: AdmissionPhase
    record_revision: str
    receipt_ref: str | None = None
    terminal_status: str | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not AdmissionRequest or type(self.phase) is not AdmissionPhase:
            raise KebuiAdmissionError("invalid_metadata")
        validate_id(self.execution_id, "kexe_")
        validate_revision(self.record_revision)
        if self.receipt_ref is not None:
            validate_id(self.receipt_ref, "krcp_")
        if self.phase is AdmissionPhase.TERMINAL:
            if (
                type(self.terminal_status) is not str
                or self.terminal_status not in TERMINAL_STATUSES
                or self.receipt_ref is None
            ):
                raise KebuiAdmissionError("invalid_metadata")
        elif self.terminal_status is not None:
            raise KebuiAdmissionError("invalid_metadata")
        if self.phase is AdmissionPhase.ACKNOWLEDGED and self.receipt_ref is None:
            raise KebuiAdmissionError("invalid_metadata")
        if (
            self.phase
            in {
                AdmissionPhase.ACCEPTED,
                AdmissionPhase.DISPATCH_FENCED,
                AdmissionPhase.REJECTED_BEFORE_DISPATCH,
            }
            and self.receipt_ref is not None
        ):
            raise KebuiAdmissionError("invalid_metadata")


@dataclass(frozen=True, slots=True)
class SyntheticOwnerContext:
    scope: ConversationScope
    execution_id: str


@dataclass(frozen=True, slots=True)
class SyntheticDispatchReceipt:
    receipt_ref: str

    def __post_init__(self) -> None:
        validate_id(self.receipt_ref, "krcp_")


@dataclass(frozen=True, slots=True)
class SyntheticTerminalReceipt:
    """Positive synthetic terminal evidence bound to the same dispatch receipt."""

    status: str
    receipt_ref: str

    def __post_init__(self) -> None:
        validate_id(self.receipt_ref, "krcp_")
        if type(self.status) is not str or self.status not in TERMINAL_STATUSES:
            raise KebuiAdmissionError("invalid_metadata")


class SyntheticCurrentOwnerPort(Protocol):
    def guard(self, scope: ConversationScope) -> AbstractContextManager[SyntheticOwnerContext]:
        """Test-only exact context and exclusive structured/no-TUI writer guard.

        Retain the exclusion while entered, including an awaited synthetic
        dispatch. The effect port must use this same guard at its effect boundary.
        A context boolean or successful metadata validation is not authentication.
        """
        ...


class SyntheticContentAdmissionPort(Protocol):
    def validate(self, request: AdmissionRequest) -> bool:
        """Prove a current immutable SYNTHETIC binding; never accept body/hash."""
        ...


class SyntheticDispatchPort(Protocol):
    def dispatch(
        self, request: AdmissionRequest, execution_id: str
    ) -> Awaitable[SyntheticDispatchReceipt]: ...


class AdmissionJournalPort(Protocol):
    def accept(
        self, request: AdmissionRequest, execution_id: str
    ) -> tuple[AdmissionRecord, bool]: ...

    def read(self, request: AdmissionRequest) -> AdmissionRecord | None: ...

    def transition(
        self,
        request: AdmissionRequest,
        expected_revision: str,
        phase: AdmissionPhase,
        *,
        receipt_ref: str | None = None,
        terminal_status: str | None = None,
    ) -> AdmissionRecord: ...


class KebuiTestAdmissionOwner:
    """Inert test composition; owns waiters, not processes or production writers."""

    __test__ = False

    def __init__(
        self,
        journal: AdmissionJournalPort,
        current_owner: SyntheticCurrentOwnerPort,
        content_admission: SyntheticContentAdmissionPort,
        dispatch: SyntheticDispatchPort,
        *,
        enabled: bool = False,
    ) -> None:
        self._journal = journal
        self._owner = current_owner
        self._content = content_admission
        self._dispatch = dispatch
        self._enabled = enabled is True
        self._workers: set[asyncio.Task[AdmissionRecord]] = set()

    @contextmanager
    def _guard(self, request: AdmissionRequest) -> Iterator[SyntheticOwnerContext]:
        if type(request) is not AdmissionRequest:
            raise KebuiAdmissionError("invalid_metadata")
        try:
            guard = self._owner.guard(request.scope)
            context = guard.__enter__()
        except Exception:
            raise KebuiAdmissionError("owner_unavailable") from None
        try:
            yield context
        except BaseException:
            try:
                guard.__exit__(*sys.exc_info())
            except Exception:
                raise KebuiAdmissionError("owner_unavailable") from None
            # Ports cannot suppress journal/CAS/dispatch failures.
            raise
        else:
            try:
                guard.__exit__(None, None, None)
            except Exception:
                raise KebuiAdmissionError("owner_unavailable") from None

    def _validate(self, request: AdmissionRequest, context: SyntheticOwnerContext) -> None:
        if not self._enabled:
            raise KebuiAdmissionError("disabled")
        if type(request) is not AdmissionRequest or type(context) is not SyntheticOwnerContext:
            raise KebuiAdmissionError("owner_unavailable")
        if context.scope != request.scope:
            raise KebuiAdmissionError("owner_unavailable")
        validate_id(context.execution_id, "kexe_")
        try:
            valid = self._content.validate(request)
        except Exception:
            raise KebuiAdmissionError("content_unavailable") from None
        if valid is not True:
            raise KebuiAdmissionError("content_unavailable")

    def _check_enabled(self) -> None:
        if not self._enabled:
            raise KebuiAdmissionError("disabled")

    async def submit(self, request: AdmissionRequest) -> AdmissionRecord:
        self._check_enabled()
        with self._guard(request) as context:
            self._validate(request, context)
            record, created = self._journal.accept(request, context.execution_id)
        if not created:
            return record
        # No await between durable acceptance and retaining the worker. Caller
        # cancellation only stops shielded waiting, never retires a dispatch claim.
        worker = asyncio.create_task(self._run(record))
        self._workers.add(worker)
        worker.add_done_callback(self._worker_done)
        return await asyncio.shield(worker)

    def _worker_done(self, worker: asyncio.Task[AdmissionRecord]) -> None:
        self._workers.discard(worker)
        if not worker.cancelled():
            worker.exception()  # Retrieve errors even if the caller left.

    async def wait_for_idle(self) -> None:
        """Drain retained fake workers; this is not a cancellation operation."""
        if self._workers:
            await asyncio.gather(*(asyncio.shield(worker) for worker in tuple(self._workers)))

    async def _run(self, accepted: AdmissionRecord) -> AdmissionRecord:
        request = accepted.request
        current = accepted
        try:
            with self._guard(request) as context:
                self._validate(request, context)
                if context.execution_id != accepted.execution_id:
                    raise KebuiAdmissionError("owner_unavailable")
                current = self._journal.transition(
                    request, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED
                )
                # No journal lock spans the port; the exact owner guard does.
                receipt = await self._dispatch.dispatch(request, context.execution_id)
            with self._guard(request) as context:
                self._validate(request, context)
                if context.execution_id != accepted.execution_id:
                    raise KebuiAdmissionError("owner_unavailable")
                if type(receipt) is not SyntheticDispatchReceipt:
                    raise KebuiAdmissionError("invalid_metadata")
                return self._journal.transition(
                    request,
                    current.record_revision,
                    AdmissionPhase.ACKNOWLEDGED,
                    receipt_ref=receipt.receipt_ref,
                )
        except (Exception, asyncio.CancelledError):
            # UNKNOWN is conservative bookkeeping, not dispatch or fresh authority.
            # A winning rejection/terminal/recovery must never be overwritten.
            observed = self._journal.read(request)
            if observed is None:
                raise KebuiAdmissionError("not_observed") from None
            if observed.phase in FINISHED_PHASES or observed.phase is AdmissionPhase.UNKNOWN:
                return observed
            return self._journal.transition(
                request, observed.record_revision, AdmissionPhase.UNKNOWN
            )

    def read(self, request: AdmissionRequest) -> AdmissionRecord | None:
        self._check_enabled()
        with self._guard(request) as context:
            self._validate(request, context)
            record = self._journal.read(request)
            if record is not None and record.execution_id != context.execution_id:
                raise KebuiAdmissionError("owner_unavailable")
            return record

    def reject_before_dispatch(
        self, request: AdmissionRequest, expected_revision: str
    ) -> AdmissionRecord:
        self._check_enabled()
        with self._guard(request) as context:
            self._validate(request, context)
            record = self._journal.read(request)
            if record is None or record.execution_id != context.execution_id:
                raise KebuiAdmissionError("owner_unavailable")
            return self._journal.transition(
                request, expected_revision, AdmissionPhase.REJECTED_BEFORE_DISPATCH
            )

    def acknowledge_terminal(
        self,
        request: AdmissionRequest,
        expected_revision: str,
        receipt: SyntheticTerminalReceipt,
    ) -> AdmissionRecord:
        self._check_enabled()
        if type(receipt) is not SyntheticTerminalReceipt:
            raise KebuiAdmissionError("invalid_metadata")
        with self._guard(request) as context:
            self._validate(request, context)
            record = self._journal.read(request)
            if record is None or record.execution_id != context.execution_id:
                raise KebuiAdmissionError("owner_unavailable")
            return self._journal.transition(
                request,
                expected_revision,
                AdmissionPhase.TERMINAL,
                receipt_ref=receipt.receipt_ref,
                terminal_status=receipt.status,
            )
