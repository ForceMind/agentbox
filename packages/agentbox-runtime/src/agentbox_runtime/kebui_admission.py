"""Default-off synthetic admission; no production source or execution writer.

The journal alone owns durable operation state. Sealed in-memory test content
adds no S03 authentication, wire action or production current-owner authority.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from agentbox_core.kebui_observation import ConversationScope, KebuiObservationError, parse_scope

SYNTHETIC_ADAPTER_PROFILE = "kebui-synthetic-adapter-v1"
MAX_REVISION = 2**64 - 1

if TYPE_CHECKING:
    from .kebui_content_admission import (
        SyntheticBodyConsumer,
        SyntheticContentHandle,
        SyntheticContentIssuer,
    )

_SAFE_CODES = frozenset(
    {
        "already_initialized",
        "busy",
        "capacity",
        "cas_conflict",
        "claim_retired",
        "commit_uncertain",
        "conflict",
        "directory_changed",
        "invalid_directory",
        "invalid_inventory",
        "invalid_metadata",
        "invalid_snapshot",
        "invalid_transition",
        "not_observed",
        "read_only",
        "revision_exhausted",
        "snapshot_changed",
        "store_unavailable",
        "disabled",
        "owner_unavailable",
        "content_unavailable",
        "invalid_content",
    }
)


class KebuiAdmissionError(RuntimeError):
    """Fixed safe error codes, never copied content, paths or adapter errors."""


def _safe_code(error: BaseException, fallback: str) -> str:
    if (
        type(error) is KebuiAdmissionError
        and len(error.args) == 1
        and type(error.args[0]) is str
        and error.args[0] in _SAFE_CODES
    ):
        return error.args[0]
    return fallback


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
        validated = None
        with suppress(KebuiObservationError, AttributeError, TypeError, ValueError):
            validated = parse_scope(scope_metadata(self.scope))
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

        Exclude replacement while entered. Readiness awaits hold neither this
        guard nor the pool lock; the fixed effect reacquires this guard followed
        by the pool and rechecks exact currentness after the last await. A context
        boolean or successful metadata validation is not authentication.
        """
        ...


class SyntheticDispatchPort(Protocol):
    consumer: SyntheticBodyConsumer

    def dispatch(
        self, request: AdmissionRequest, execution_id: str, handle: SyntheticContentHandle
    ) -> Awaitable[None]:
        """Synthetic readiness only: no body access, effect or receipt before return."""
        ...


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


@dataclass(slots=True, repr=False)
class _WorkerClaim:
    handle: SyntheticContentHandle
    ready: asyncio.Event
    slot: int
    record: AdmissionRecord | None = None
    task: asyncio.Task[AdmissionRecord] | None = None
    armed: bool = False
    retired: bool = False


class KebuiTestAdmissionOwner:
    """Inert test composition; metadata readers need no surviving body issuer."""

    __test__ = False

    def __init__(
        self,
        journal: AdmissionJournalPort,
        current_owner: SyntheticCurrentOwnerPort,
        content_admission: SyntheticContentIssuer | None,
        dispatch: SyntheticDispatchPort,
        *,
        enabled: bool = False,
    ) -> None:
        from .kebui_content_admission import (
            MAX_ENTRIES,
            SyntheticBodyConsumer,
            SyntheticContentIssuer,
        )

        self._journal = journal
        self._owner = current_owner
        self._content = content_admission
        self._dispatch = dispatch
        self._enabled = enabled is True
        self._workers: set[asyncio.Task[AdmissionRecord]] = set()
        # Reserve reliable metadata ownership before acceptance, independent of
        # fallible Task/set/callback registration after the journal commits.
        self._claims: list[_WorkerClaim | None] = [None] * MAX_ENTRIES
        self._consumer: SyntheticBodyConsumer | None = None
        code: str | None = None
        try:
            if content_admission is not None:
                if type(content_admission) is not SyntheticContentIssuer:
                    raise KebuiAdmissionError("content_unavailable")
                consumer = dispatch.consumer
                if type(consumer) is not SyntheticBodyConsumer:
                    raise KebuiAdmissionError("content_unavailable")
                self._consumer = consumer
                content_admission._bind(self, current_owner, journal)
        except Exception as error:
            code = _safe_code(error, "content_unavailable")
        if code is not None:
            raise KebuiAdmissionError(code)

    @contextmanager
    def _guard(self, request: AdmissionRequest) -> Iterator[SyntheticOwnerContext]:
        if type(request) is not AdmissionRequest:
            raise KebuiAdmissionError("invalid_metadata")
        entered = False
        try:
            guard = self._owner.guard(request.scope)
            context = guard.__enter__()
            entered = True
        except Exception:
            pass
        if not entered:
            raise KebuiAdmissionError("owner_unavailable")
        code: str | None = None
        canceled = False
        try:
            yield context
        except asyncio.CancelledError:
            canceled = True
        except Exception as error:
            code = _safe_code(error, "store_unavailable")
        finally:
            # Never give a port an original error/body, or allow it to suppress a
            # journal/CAS failure. Exit failures are rebuilt outside the handler.
            try:
                guard.__exit__(None, None, None)
            except Exception:
                code = "owner_unavailable"
        if canceled:
            raise asyncio.CancelledError
        if code is not None:
            raise KebuiAdmissionError(code)

    def _validate_metadata(self, request: AdmissionRequest, context: SyntheticOwnerContext) -> None:
        self._check_enabled()
        if type(request) is not AdmissionRequest or type(context) is not SyntheticOwnerContext:
            raise KebuiAdmissionError("owner_unavailable")
        if context.scope != request.scope:
            raise KebuiAdmissionError("owner_unavailable")
        validate_id(context.execution_id, "kexe_")

    def _check_enabled(self) -> None:
        if not self._enabled:
            raise KebuiAdmissionError("disabled")

    def _reserve_claim(self, handle: SyntheticContentHandle) -> _WorkerClaim:
        for index, existing in enumerate(self._claims):
            if existing is None:
                claim = _WorkerClaim(handle, asyncio.Event(), index)
                self._claims[index] = claim
                return claim
        raise KebuiAdmissionError("capacity")

    def _retain_worker(self, worker: asyncio.Task[AdmissionRecord]) -> None:
        self._workers.add(worker)

    def _register_worker(self, worker: asyncio.Task[AdmissionRecord]) -> None:
        worker.add_done_callback(self._worker_done)

    async def submit(
        self, request: AdmissionRequest, handle: SyntheticContentHandle | None = None
    ) -> AdmissionRecord:
        from .kebui_content_admission import SyntheticContentHandle

        claim: _WorkerClaim | None = None
        record: AdmissionRecord | None = None
        durable = False
        failed = False
        canceled = False
        code = "content_unavailable"
        coroutine = None
        try:
            self._check_enabled()
            with self._guard(request) as context:
                self._validate_metadata(request, context)
                if self._content is None or type(handle) is not SyntheticContentHandle:
                    raise KebuiAdmissionError("content_unavailable")
                with self._content._locked():
                    entry = self._content._entry(handle, self, request, context.execution_id)
                    previous = self._journal.read(request)
                    if previous is not None:
                        # A duplicate NEVER reconstructs a witness from equality
                        # of record values, an issued ref, or recreated bytes.
                        if not entry.accepted_once:
                            raise KebuiAdmissionError("content_unavailable")
                        record, created = self._journal.accept(request, context.execution_id)
                        if created:
                            raise KebuiAdmissionError("store_unavailable")
                    else:
                        if entry.accepted_once:
                            raise KebuiAdmissionError("content_unavailable")
                        claim = self._reserve_claim(handle)
                        self._content._reserve_worker(entry)
                        record, created = self._journal.accept(request, context.execution_id)
                        if not created:
                            raise KebuiAdmissionError("content_unavailable")
                        durable = True
                        claim.record = record
                        self._content._accept_witness(entry)
                        coroutine = self._run(claim)
                        worker = asyncio.create_task(coroutine)
                        if not isinstance(worker, asyncio.Task):
                            raise KebuiAdmissionError("store_unavailable")
                        claim.task = worker
                        self._retain_worker(worker)
                        self._register_worker(worker)
            # Even eager factories can only await an unarmed gate. Owner guard
            # exit, retention and callback registration must all succeed first.
            if claim is not None:
                claim.armed = True
                claim.ready.set()
        except asyncio.CancelledError:
            failed = True
            canceled = True
        except Exception as error:
            failed = True
            code = _safe_code(error, "store_unavailable")
        if failed:
            if claim is not None:
                claim.armed = False
                if self._content is not None:
                    self._content._revoke(claim.handle)
                if claim.task is not None:
                    claim.task.cancel()
                    # No locks span this drain. Until the unarmed task actually
                    # retires its reserved slot and payload remain charged.
                    with suppress(Exception, asyncio.CancelledError):
                        await claim.task
                elif coroutine is not None:
                    coroutine.close()
                self._retire_claim(claim)
            elif self._content is not None and type(handle) is SyntheticContentHandle:
                self._content._discard_prepared(handle)
            if durable:
                # This call is OUTSIDE the original exception handler: secondary
                # journal errors cannot inherit port/body exceptions as context.
                record = self._unknown(request)
                if not canceled:
                    return record
            if canceled:
                raise asyncio.CancelledError
            raise KebuiAdmissionError(code)
        if record is None:
            raise KebuiAdmissionError("store_unavailable")
        if claim is None:
            return record
        if claim.task is None:
            raise KebuiAdmissionError("store_unavailable")
        # A canceled waiter never cancels the admitted worker or its resources.
        return await asyncio.shield(claim.task)

    def _retire_claim(self, claim: _WorkerClaim) -> None:
        if claim.retired:
            return
        claim.retired = True
        self._claims[claim.slot] = None
        if claim.task is not None:
            self._workers.discard(claim.task)
        if self._content is not None:
            self._content._worker_retired(claim.handle)

    def _worker_done(self, worker: asyncio.Task[AdmissionRecord]) -> None:
        for claim in self._claims:
            if claim is not None and claim.task is worker:
                self._retire_claim(claim)
                break
        self._workers.discard(worker)
        if not worker.cancelled():
            worker.exception()

    async def wait_for_idle(self) -> None:
        """Drain retained fake workers; this is not a cancellation operation."""
        tasks = tuple(claim.task for claim in self._claims if claim is not None and claim.task)
        if tasks:
            await asyncio.gather(
                *(asyncio.shield(worker) for worker in tasks), return_exceptions=True
            )
        for claim in self._claims:
            if claim is not None and claim.task is not None and claim.task.done():
                self._retire_claim(claim)

    def _unknown(self, request: AdmissionRequest) -> AdmissionRecord:
        result: AdmissionRecord | None = None
        code = "store_unavailable"
        try:
            observed = self._journal.read(request)
            if observed is None:
                raise KebuiAdmissionError("not_observed")
            if observed.phase in FINISHED_PHASES or observed.phase is AdmissionPhase.UNKNOWN:
                result = observed
            else:
                result = self._journal.transition(
                    request, observed.record_revision, AdmissionPhase.UNKNOWN
                )
        except Exception as error:
            code = _safe_code(error, "store_unavailable")
        if result is None:
            raise KebuiAdmissionError(code)
        return result

    async def _run(self, claim: _WorkerClaim) -> AdmissionRecord:
        accepted = claim.record
        if accepted is None:
            raise KebuiAdmissionError("store_unavailable")
        request = accepted.request
        result: AdmissionRecord | None = None
        try:
            try:
                await claim.ready.wait()
                if not claim.armed or self._content is None or self._consumer is None:
                    raise KebuiAdmissionError("content_unavailable")
                with self._guard(request) as context:
                    self._validate_metadata(request, context)
                    if context.execution_id != accepted.execution_id:
                        raise KebuiAdmissionError("owner_unavailable")
                    with self._content._locked():
                        self._content._entry(
                            claim.handle, self, request, context.execution_id, accepted=True
                        )
                        current = self._journal.transition(
                            request, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED
                        )
                # Only the opaque handle crosses this await, never a body borrow.
                await self._dispatch.dispatch(request, accepted.execution_id, claim.handle)
                with self._guard(request) as context:
                    self._validate_metadata(request, context)
                    if context.execution_id != accepted.execution_id:
                        raise KebuiAdmissionError("owner_unavailable")
                    with self._content._locked():
                        observed = self._journal.read(request)
                        if observed != current:
                            raise KebuiAdmissionError("cas_conflict")
                        receipt = self._content._effect(
                            claim.handle, self, request, context.execution_id, self._consumer
                        )
                        result = self._journal.transition(
                            request,
                            current.record_revision,
                            AdmissionPhase.ACKNOWLEDGED,
                            receipt_ref=receipt.receipt_ref,
                        )
            except (Exception, asyncio.CancelledError):
                # A guard exit can fail AFTER the effect and ACK commit. Do not
                # let that captured result bypass conservative UNKNOWN handling.
                result = None
            if result is None:
                if self._content is not None:
                    self._content._revoke(claim.handle)
                result = self._unknown(request)
            return result
        finally:
            self._retire_claim(claim)

    def read(self, request: AdmissionRequest) -> AdmissionRecord | None:
        result: AdmissionRecord | None = None
        code: str | None = None
        try:
            self._check_enabled()
            with self._guard(request) as context:
                self._validate_metadata(request, context)
                result = self._journal.read(request)
                if result is not None and result.execution_id != context.execution_id:
                    raise KebuiAdmissionError("owner_unavailable")
        except Exception as error:
            code = _safe_code(error, "store_unavailable")
        if code is not None:
            raise KebuiAdmissionError(code)
        return result

    def reject_before_dispatch(
        self, request: AdmissionRequest, expected_revision: str
    ) -> AdmissionRecord:
        result: AdmissionRecord | None = None
        code: str | None = None
        try:
            self._check_enabled()
            with self._guard(request) as context:
                self._validate_metadata(request, context)
                record = self._journal.read(request)
                if record is None or record.execution_id != context.execution_id:
                    raise KebuiAdmissionError("owner_unavailable")
                result = self._journal.transition(
                    request, expected_revision, AdmissionPhase.REJECTED_BEFORE_DISPATCH
                )
        except Exception as error:
            code = _safe_code(error, "store_unavailable")
        if code is not None or result is None:
            raise KebuiAdmissionError(code or "store_unavailable")
        return result

    def acknowledge_terminal(
        self,
        request: AdmissionRequest,
        expected_revision: str,
        receipt: SyntheticTerminalReceipt,
    ) -> AdmissionRecord:
        result: AdmissionRecord | None = None
        code: str | None = None
        try:
            self._check_enabled()
            if type(receipt) is not SyntheticTerminalReceipt:
                raise KebuiAdmissionError("invalid_metadata")
            with self._guard(request) as context:
                self._validate_metadata(request, context)
                record = self._journal.read(request)
                if record is None or record.execution_id != context.execution_id:
                    raise KebuiAdmissionError("owner_unavailable")
                result = self._journal.transition(
                    request,
                    expected_revision,
                    AdmissionPhase.TERMINAL,
                    receipt_ref=receipt.receipt_ref,
                    terminal_status=receipt.status,
                )
        except Exception as error:
            code = _safe_code(error, "store_unavailable")
        if code is not None or result is None:
            raise KebuiAdmissionError(code or "store_unavailable")
        return result
