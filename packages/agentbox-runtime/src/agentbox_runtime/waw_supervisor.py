"""Bounded Runtime supervisor contract for one Web Agent Workspace.

The supervisor is deliberately transport-agnostic.  A Runtime adapter may
implement :class:`WAWTransport` with a real PTY, but the adapter receives only
the already validated fixed command contract.  This module owns lifecycle and
attachment fencing; it never accepts a shell command, path, executable, or
secret from a caller.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock, RLock
from typing import Protocol

from agentbox_core.waw import (
    StopResult,
    WorkspaceStopOperation,
    managed_marker,
    validate_positive_u64,
    validate_workspace_id,
)
from agentbox_core.waw_tickets import ActiveAttachment, AttachmentTuple

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_auth_probe import WAWPublicAuthEvidence
from agentbox_runtime.waw_managed_command import (
    WAWManagedCommand,
    managed_command_agent_type,
    validate_managed_command,
)
from agentbox_runtime.waw_pty import OutputReplay, OutputRing, PtyGeometry, validate_input


class RuntimePublicationInvalidator:
    """One exact Runtime lease's nonblocking publication shutdown hook.

    It never acquires a registry/supervisor lock from its callback. A Stop that
    wins before stream binding permanently fences a later bind as well.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._callback: Callable[[], bool] | None = None
        self._bound = self._invalidated = False

    def bind(self, callback: Callable[[], bool]) -> None:
        with self._lock:
            if self._bound:
                raise ValueError("Runtime publication is already bound")
            self._bound = True
            self._callback = callback
            invalidated = self._invalidated
        if invalidated and callback() is not True:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED", "Publication shutdown is unconfirmed", category="conflict"
            )

    def invalidate(self) -> bool:
        with self._lock:
            self._invalidated = True
            callback = self._callback
        return callback is None or callback() is True


@dataclass(frozen=True, repr=False)
class RuntimeAttachmentLease:
    """Runtime-only authority; deliberately contains no API Session identity."""

    claims: AttachmentTuple
    runtime_epoch: str
    expires_at: float
    current: Callable[[], bool] = field(repr=False, compare=False)
    publication: RuntimePublicationInvalidator = field(
        default_factory=RuntimePublicationInvalidator, repr=False, compare=False
    )

    @property
    def attachment_id(self) -> str:
        return self.claims.attachment_id

    def active_at(self, now: float) -> bool:
        return now < self.expires_at


AttachmentLease = ActiveAttachment | RuntimeAttachmentLease


@dataclass(frozen=True)
class RuntimeAttachmentCleanupEvidence:
    """Exact attach-child/PTY close evidence supplied by a qualified Runtime port."""

    lease: RuntimeAttachmentLease
    closed: bool
    remaining_members: int


class SupervisorState(StrEnum):
    ADMITTED = "ADMITTED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    NEEDS_INTERACTION = "NEEDS_INTERACTION"
    TRUST_REQUIRED = "TRUST_REQUIRED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    DETACHED = "DETACHED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    BROKEN = "BROKEN"
    INPUT_UNCERTAIN = "INPUT_UNCERTAIN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class RuntimeStartEvidence:
    workspace_id: str
    generation: int
    managed_marker: str
    state: SupervisorState
    ready: bool


@dataclass(frozen=True)
class RuntimeStopEvidence:
    workspace_id: str
    generation: int
    managed_marker: str
    closed: bool
    remaining_members: int


class RuntimeProbeState(StrEnum):
    RUNNING = "RUNNING"
    NEEDS_INTERACTION = "NEEDS_INTERACTION"
    TRUST_REQUIRED = "TRUST_REQUIRED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    STOPPED = "STOPPED"
    MISSING = "MISSING"
    EXITED = "EXITED"
    COLLISION = "COLLISION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RuntimeProbeEvidence:
    """Read-only observation of one exact Runtime process binding."""

    workspace_id: str
    generation: int
    managed_marker: str
    state: RuntimeProbeState
    exit_code: int | None = None


class WAWTransport(Protocol):
    """The only side-effecting operations a WAW Runtime adapter may expose."""

    def start(self, command: WAWManagedCommand, geometry: PtyGeometry) -> RuntimeStartEvidence: ...

    def write(self, data: bytes) -> None: ...

    def detach(self) -> bool: ...

    def resize(self, geometry: PtyGeometry) -> None: ...

    def stop(self) -> RuntimeStopEvidence: ...


class OutputSource:
    """Opaque Runtime-owned admission for PTY output.

    The object is intentionally identity-only: callers cannot forge a source
    by reproducing workspace metadata, and a source is invalidated when the
    supervisor generation stops.
    """

    __slots__ = ()


@dataclass(frozen=True)
class SupervisorSnapshot:
    workspace_id: str
    generation: int
    state: SupervisorState
    geometry: PtyGeometry
    next_cursor: int
    buffered_bytes: int
    attachment_id: str | None


class WAWSupervisor:
    """One-generation lifecycle fence around a fixed WAW Runtime transport."""

    def __init__(
        self,
        *,
        workspace_id: str,
        generation: int,
        command: WAWManagedCommand,
        transport: WAWTransport,
        geometry: PtyGeometry,
        clock: Callable[[], float],
        attachment_validator: Callable[[ActiveAttachment], bool],
        stop_binding: WorkspaceStopOperation,
        output_capacity_bytes: int = 256 * 1024,
        runtime_epoch: str,
    ) -> None:
        command = validate_managed_command(command)
        validate_workspace_id(workspace_id)
        validate_positive_u64(generation, field="generation")
        if command.workspace_id != workspace_id:
            raise RuntimeOperationError(
                "WAW_WORKSPACE_MISMATCH",
                "Runtime command workspace does not match",
                category="validation",
            )
        if (
            stop_binding.workspace_id != workspace_id
            or stop_binding.project_id != command.project_id
            or stop_binding.agent_type is not managed_command_agent_type(command)
            or stop_binding.generation != generation
            or managed_marker(
                runtime_host_installation_id=stop_binding.runtime_host_installation_id,
                runtime_host_installation_revision=stop_binding.runtime_host_installation_revision,
                project_id=stop_binding.project_id,
                agent_type=stop_binding.agent_type,
                workspace_id_value=stop_binding.workspace_id,
                generation=stop_binding.generation,
                binding_revision=stop_binding.binding_revision,
                binding_digest=stop_binding.binding_digest,
            )
            != command.managed_marker
        ):
            raise RuntimeOperationError(
                "WAW_BINDING_MISMATCH",
                "Runtime command does not match the durable workspace binding",
                category="validation",
            )
        self._workspace_id = workspace_id
        self._generation = generation
        self._command = command
        self._transport = transport
        self._geometry = geometry
        self._clock = clock
        self._attachment_validator = attachment_validator
        self._stop_binding = stop_binding
        if (
            not isinstance(runtime_epoch, str)
            or not runtime_epoch.isascii()
            or not runtime_epoch.isdecimal()
            or runtime_epoch.startswith("0")
            or int(runtime_epoch) > 2**64 - 1
        ):
            raise RuntimeOperationError(
                "WAW_RUNTIME_EPOCH_INVALID",
                "Runtime epoch must be canonical",
                category="validation",
            )
        self._runtime_epoch = runtime_epoch
        self._ring = OutputRing(capacity_bytes=output_capacity_bytes)
        self._state = SupervisorState.ADMITTED
        self._attachment: AttachmentLease | None = None
        self._runtime_pending: RuntimeAttachmentLease | None = None
        self._output_source: OutputSource | None = None
        self._lock = RLock()

    @property
    def state(self) -> SupervisorState:
        with self._lock:
            return self._state

    def snapshot(self) -> SupervisorSnapshot:
        with self._lock:
            return SupervisorSnapshot(
                workspace_id=self._workspace_id,
                generation=self._generation,
                state=self._state,
                geometry=self._geometry,
                next_cursor=self._ring.next_cursor,
                buffered_bytes=self._ring.buffered_bytes,
                attachment_id=(self._attachment.attachment_id if self._attachment else None),
            )

    def fixed_executable_fingerprint(self) -> str:
        """Return only the fixed transport's public executable fingerprint."""

        with self._lock:
            value = getattr(self._transport, "executable_fingerprint", None)
            if (
                type(value) is not str
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Fixed executable fingerprint is unavailable",
                    category="unavailable",
                )
            return value

    @contextmanager
    def stopped_generation_guard(self, operation: WorkspaceStopOperation) -> Iterator[None]:
        """Hold an exact positive STOPPED fence through an executor map commit."""

        with self._lock:
            if not _same_stop_binding(operation, self._stop_binding):
                raise RuntimeOperationError(
                    "WAW_GENERATION_STALE",
                    "Previous workspace generation binding is stale",
                    category="conflict",
                )
            if self._state is not SupervisorState.STOPPED:
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED",
                    "Previous workspace generation is not positively stopped",
                    category="conflict",
                )
            yield

    def start(self) -> SupervisorSnapshot:
        with self._lock:
            if self._state is not SupervisorState.ADMITTED:
                raise RuntimeOperationError(
                    "WAW_START_INVALID", "Workspace is not admitted for start", category="conflict"
                )
            try:
                validate_managed_command(self._command)
                evidence = self._transport.start(self._command, self._geometry)
                if (
                    evidence.workspace_id != self._workspace_id
                    or evidence.generation != self._generation
                    or evidence.managed_marker != self._command.managed_marker
                    or not evidence.ready
                    or evidence.state
                    not in {
                        SupervisorState.RUNNING,
                        SupervisorState.NEEDS_INTERACTION,
                        SupervisorState.TRUST_REQUIRED,
                        SupervisorState.LOGIN_REQUIRED,
                    }
                ):
                    raise RuntimeOperationError(
                        "WAW_START_UNCONFIRMED",
                        "Runtime start evidence is not admissible",
                        category="conflict",
                    )
            except Exception as exc:
                self._state = SupervisorState.BROKEN
                raise RuntimeOperationError(
                    "WAW_START_FAILED", "Runtime transport could not start", category="unavailable"
                ) from exc
            self._output_source = OutputSource()
            bind_output_sink = getattr(self._transport, "bind_output_sink", None)
            if callable(bind_output_sink):
                source = self._output_source
                try:
                    bind_output_sink(lambda payload: self.append_encrypted_output(source, payload))
                except Exception as exc:
                    self._state = SupervisorState.BROKEN
                    raise RuntimeOperationError(
                        "WAW_START_FAILED",
                        "Runtime output producer could not be admitted",
                        category="unavailable",
                    ) from exc
            self._state = evidence.state
            return self.snapshot()

    def resume_after_login(self, evidence: WAWPublicAuthEvidence) -> SupervisorSnapshot:
        """CAS one LOGIN_REQUIRED generation into its first process spawn."""

        with self._lock:
            if self._state is not SupervisorState.LOGIN_REQUIRED:
                raise RuntimeOperationError(
                    "WAW_RESUME_INVALID", "Workspace is not waiting for login", category="conflict"
                )
            resume = getattr(self._transport, "resume_after_login", None)
            if not callable(resume):
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Fixed login resume port is unavailable",
                    category="unavailable",
                )
            validate_resume = getattr(self._transport, "validate_resume_evidence", None)
            if callable(validate_resume):
                validate_resume(evidence)
            self._state = SupervisorState.STARTING
            try:
                resumed = resume(evidence)
                if (
                    type(resumed) is not RuntimeStartEvidence
                    or resumed.workspace_id != self._workspace_id
                    or resumed.generation != self._generation
                    or resumed.managed_marker != self._command.managed_marker
                    or not resumed.ready
                    or resumed.state
                    not in {
                        SupervisorState.RUNNING,
                        SupervisorState.NEEDS_INTERACTION,
                        SupervisorState.TRUST_REQUIRED,
                    }
                ):
                    raise RuntimeOperationError(
                        "WAW_RESUME_UNCONFIRMED",
                        "Runtime resume evidence is not admissible",
                        category="conflict",
                    )
            except Exception as exc:
                self._state = SupervisorState.RECONCILIATION_REQUIRED
                if isinstance(exc, RuntimeOperationError):
                    raise
                raise RuntimeOperationError(
                    "WAW_RESUME_FAILED",
                    "Runtime could not resume after login",
                    category="unavailable",
                ) from exc
            self._state = resumed.state
            return self.snapshot()

    def attach(self, attachment: AttachmentLease) -> SupervisorSnapshot:
        with self._lock:
            self._check_attachment(attachment)
            if self._runtime_pending is not None and self._runtime_pending is not attachment:
                raise RuntimeOperationError(
                    "WORKSPACE_WRITER_BUSY", "Runtime writer is reserved", category="conflict"
                )
            if self._state not in {SupervisorState.RUNNING, SupervisorState.DETACHED}:
                raise RuntimeOperationError(
                    "WAW_ATTACH_INVALID", "Workspace is not attachable", category="conflict"
                )
            if self._attachment is not None and self._attachment.claims != attachment.claims:
                raise RuntimeOperationError(
                    "WAW_WRITER_BUSY",
                    "Workspace already has a writer attachment",
                    category="conflict",
                )
            if (
                self._attachment is None
                and getattr(self, "_last_attachment_id", None) == attachment.attachment_id
            ):
                raise RuntimeOperationError(
                    "WAW_ATTACHMENT_REPLAYED",
                    "Reconnect requires a fresh attachment",
                    category="conflict",
                )
            # A detached browser may reconnect after the underlying provider
            # process has exited.  If the transport exposes the optional
            # reconciliation probe, require fresh exact marker/process
            # evidence before reacquiring the writer slot.  Legacy test
            # doubles without this probe retain their existing behavior; the
            # production tmux transport implements it.
            if self._state is SupervisorState.DETACHED:
                reconcile = getattr(self._transport, "reconcile", None)
                if callable(reconcile):
                    try:
                        evidence = reconcile()
                        if (
                            evidence.workspace_id != self._workspace_id
                            or evidence.generation != self._generation
                            or evidence.managed_marker != self._command.managed_marker
                            or not evidence.ready
                            or evidence.state
                            not in {
                                SupervisorState.RUNNING,
                                SupervisorState.NEEDS_INTERACTION,
                                SupervisorState.TRUST_REQUIRED,
                                SupervisorState.LOGIN_REQUIRED,
                            }
                        ):
                            raise RuntimeOperationError(
                                "WAW_ATTACH_UNCONFIRMED",
                                "Runtime process is not live for reconnect",
                                category="conflict",
                            )
                    except RuntimeOperationError:
                        raise
                    except Exception as exc:
                        raise RuntimeOperationError(
                            "WAW_ATTACH_UNCONFIRMED",
                            "Runtime process could not be reconciled for reconnect",
                            category="conflict",
                        ) from exc
            if isinstance(attachment, RuntimeAttachmentLease):
                open_attachment = getattr(self._transport, "open_attachment", None)
                if not callable(open_attachment):
                    if getattr(self._transport, "requires_commit_attachment", False) is True:
                        raise RuntimeOperationError(
                            "RUNTIME_UNAVAILABLE",
                            "Exact fixed PTY attachment port is unavailable",
                            category="unavailable",
                        )
                else:
                    try:
                        opened = open_attachment(attachment, self._geometry)
                        if (
                            type(opened) is not RuntimeStartEvidence
                            or opened.workspace_id != self._workspace_id
                            or opened.generation != self._generation
                            or opened.managed_marker != self._command.managed_marker
                            or opened.state is not SupervisorState.RUNNING
                            or opened.ready is not True
                        ):
                            raise RuntimeOperationError(
                                "WAW_ATTACH_UNCONFIRMED",
                                "Fixed PTY attachment evidence is not exact",
                                category="conflict",
                            )
                    except Exception as exc:
                        # A failed attach fences only this reservation. Positive
                        # typed cleanup releases it; uncertainty retains the
                        # reconciliation fence without declaring the process broken.
                        cleaned = self.cleanup_runtime_attachment(attachment)
                        if not cleaned:
                            self._state = SupervisorState.RECONCILIATION_REQUIRED
                        if isinstance(exc, RuntimeOperationError):
                            raise
                        raise RuntimeOperationError(
                            "WAW_ATTACH_UNCONFIRMED",
                            "Fixed PTY attachment could not be committed",
                            category="conflict",
                        ) from exc
            self._attachment = attachment
            self._state = SupervisorState.RUNNING
            return self.snapshot()

    @contextmanager
    def runtime_attachment_guard(
        self,
        attachment: RuntimeAttachmentLease,
        *,
        require_writer: bool = False,
        require_running: bool = True,
    ) -> Iterator[RuntimeProbeEvidence]:
        """Hold the process/state/binding/lease fence through caller publication.

        Only the exact Runtime-created reservation may enter. Probe is mandatory;
        legacy transports without exact read-only evidence fail closed.
        """
        with self._lock:
            self._check_attachment(attachment)
            if self._runtime_pending is not attachment:
                raise RuntimeOperationError(
                    "WAW_ATTACHMENT_STALE", "Runtime reservation is stale", category="conflict"
                )
            if require_writer and self._attachment is not attachment:
                raise RuntimeOperationError(
                    "WAW_ATTACHMENT_REQUIRED", "Writer is not committed", category="conflict"
                )
            evidence = self.probe()
            if require_running and (
                evidence.state is not RuntimeProbeState.RUNNING
                or self._state not in {SupervisorState.RUNNING, SupervisorState.DETACHED}
            ):
                raise RuntimeOperationError(
                    "WORKSPACE_NOT_RUNNING", "Exact process is not running", category="conflict"
                )
            yield evidence
            self._check_attachment(attachment)

    def reserve_runtime_attachment(self, attachment: RuntimeAttachmentLease) -> None:
        """Reserve one exact attachment without acquiring a writer or opening PTYs."""
        with self._lock:
            self._check_attachment(attachment)
            if not callable(getattr(self._transport, "close_attachment", None)):
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Exact attachment cleanup port is unavailable",
                    category="unavailable",
                )
            if self._runtime_pending is not None or self._attachment is not None:
                raise RuntimeOperationError(
                    "WORKSPACE_WRITER_BUSY", "Runtime writer is reserved", category="conflict"
                )
            if getattr(self, "_last_attachment_id", None) == attachment.attachment_id:
                raise RuntimeOperationError(
                    "WAW_ATTACHMENT_STALE", "Runtime attachment was retired", category="conflict"
                )
            self._runtime_pending = attachment

    def commit_runtime_attachment(self, attachment: RuntimeAttachmentLease) -> None:
        with self.runtime_attachment_guard(attachment):
            self.attach(attachment)

    def cleanup_runtime_attachment(self, attachment: RuntimeAttachmentLease) -> bool:
        """Close only the exact reserved PTY, even after authority revocation.

        False or exception retains the reservation. A new writer can never be
        closed by an old cleanup request. No underlying workspace Stop occurs.
        """
        with self._lock:
            if self._runtime_pending is not attachment:
                return False
            if self._attachment is not None and self._attachment is not attachment:
                return False
            try:
                close_attachment = getattr(self._transport, "close_attachment", None)
                evidence = close_attachment(attachment) if callable(close_attachment) else None
                confirmed = (
                    type(evidence) is RuntimeAttachmentCleanupEvidence
                    and evidence.lease is attachment
                    and evidence.closed is True
                    and type(evidence.remaining_members) is int
                    and evidence.remaining_members == 0
                )
            except Exception:
                confirmed = False
            if not confirmed:
                self._state = SupervisorState.RECONCILIATION_REQUIRED
                return False
            self._runtime_pending = None
            self._attachment = None
            self._last_attachment_id = attachment.attachment_id
            # PTY closure releases attachment resources, not workspace fault
            # authority. INPUT_UNCERTAIN/BROKEN/reconciliation and lifecycle
            # states keep their existing recovery gates across new tickets.
            if self._state in {SupervisorState.RUNNING, SupervisorState.DETACHED}:
                self._state = SupervisorState.DETACHED
            return True

    def clear_runtime_output(self, reason: str) -> None:
        """Discard volatile plaintext on the closed security/lifecycle event set."""
        if reason not in {"crypto_failure", "runtime_epoch", "exit", "stop"}:
            raise ValueError("unsupported output-clear event")
        with self._lock:
            self._ring.clear()

    def probe(self) -> RuntimeProbeEvidence:
        """Require fresh exact evidence without changing attachment or input state.

        Legacy test transports may omit the capability, but callers that need
        lifecycle observations must fail closed instead of using a snapshot.
        A probe never clears INPUT_UNCERTAIN or grants a reconnect writer.
        """

        with self._lock:
            probe = getattr(self._transport, "probe", None)
            if not callable(probe):
                raise RuntimeOperationError(
                    "WAW_PROBE_UNAVAILABLE",
                    "Runtime observation is unavailable",
                    category="unavailable",
                )
            evidence = probe()
            if (
                type(evidence) is not RuntimeProbeEvidence
                or evidence.workspace_id != self._workspace_id
                or type(evidence.generation) is not int
                or evidence.generation != self._generation
                or evidence.managed_marker != self._command.managed_marker
                or type(evidence.state) is not RuntimeProbeState
                or (
                    evidence.state is RuntimeProbeState.EXITED
                    and evidence.exit_code is not None
                    and (
                        type(evidence.exit_code) is not int or not -128 <= evidence.exit_code <= 255
                    )
                )
                or (
                    evidence.state is not RuntimeProbeState.EXITED
                    and evidence.exit_code is not None
                )
                or (
                    self._state is SupervisorState.STOPPED
                    and evidence.state is not RuntimeProbeState.STOPPED
                )
            ):
                raise RuntimeOperationError(
                    "WAW_PROBE_UNCONFIRMED", "Runtime observation is not exact", category="conflict"
                )
            return evidence

    def detach(self, attachment: AttachmentLease) -> SupervisorSnapshot:
        with self._lock:
            self._require_attachment(attachment)
            if isinstance(attachment, RuntimeAttachmentLease):
                if not self.cleanup_runtime_attachment(attachment):
                    raise RuntimeOperationError(
                        "WAW_DETACH_UNCONFIRMED",
                        "Runtime did not prove attach-child/PTY closure",
                        category="conflict",
                    )
                return self.snapshot()
            try:
                detached = self._transport.detach()
            except Exception as exc:
                self._state = SupervisorState.BROKEN
                raise RuntimeOperationError(
                    "WAW_DETACH_FAILED",
                    "Runtime could not close the PTY attachment",
                    category="broken",
                ) from exc
            if not detached:
                raise RuntimeOperationError(
                    "WAW_DETACH_UNCONFIRMED",
                    "Runtime did not confirm PTY closure",
                    category="conflict",
                )
            self._last_attachment_id = attachment.attachment_id
            self._attachment = None
            self._state = SupervisorState.DETACHED
            return self.snapshot()

    def write_input(self, attachment: AttachmentLease, data: bytes) -> None:
        with self._lock:
            self._require_attachment(attachment)
            if self._state is SupervisorState.INPUT_UNCERTAIN:
                raise RuntimeOperationError(
                    "WAW_INPUT_RECONCILIATION_REQUIRED",
                    "Input is paused pending explicit reconciliation",
                    category="conflict",
                )
            payload = validate_input(data)
            try:
                self._transport.write(payload)
            except Exception as exc:
                # PTY delivery is not replay-safe: callers must decide whether to
                # retry after this explicit uncertain outcome.
                self._state = SupervisorState.INPUT_UNCERTAIN
                raise RuntimeOperationError(
                    "WAW_INPUT_UNCERTAIN",
                    "Runtime could not confirm PTY input delivery",
                    category="broken",
                ) from exc

    def heartbeat(self, current: ActiveAttachment, renewed: ActiveAttachment) -> SupervisorSnapshot:
        """Replace the immutable authority lease after an exact heartbeat."""

        with self._lock:
            self._require_attachment(current)
            self._check_attachment(renewed)
            if renewed.claims != current.claims:
                raise RuntimeOperationError(
                    "WAW_ATTACHMENT_STALE",
                    "Heartbeat changed immutable attachment claims",
                    category="conflict",
                )
            if renewed.last_heartbeat_monotonic <= current.last_heartbeat_monotonic:
                raise RuntimeOperationError(
                    "WAW_HEARTBEAT_STALE",
                    "Heartbeat did not advance the attachment lease",
                    category="conflict",
                )
            self._attachment = renewed
            return self.snapshot()

    def resize(self, attachment: AttachmentLease, geometry: PtyGeometry) -> SupervisorSnapshot:
        with self._lock:
            self._require_attachment(attachment)
            if self._state is SupervisorState.INPUT_UNCERTAIN:
                raise RuntimeOperationError(
                    "WAW_INPUT_RECONCILIATION_REQUIRED",
                    "Resize is paused pending input reconciliation",
                    category="conflict",
                )
            try:
                self._transport.resize(geometry)
            except Exception as exc:
                if isinstance(attachment, RuntimeAttachmentLease):
                    cleaned = self.cleanup_runtime_attachment(attachment)
                else:
                    try:
                        cleaned = self._transport.detach() is True
                    except Exception:
                        cleaned = False
                    if cleaned:
                        self._last_attachment_id = attachment.attachment_id
                        self._attachment = None
                        self._state = SupervisorState.DETACHED
                if not cleaned:
                    self._state = SupervisorState.RECONCILIATION_REQUIRED
                raise RuntimeOperationError(
                    "WAW_RESIZE_FAILED",
                    "Runtime could not resize and retain the PTY attachment",
                    category="conflict",
                ) from exc
            self._geometry = geometry
            return self.snapshot()

    def produce_output(self) -> int:
        """Run one fixed nonblocking producer read through the admitted sink."""

        with self._lock:
            producer = getattr(self._transport, "produce_output", None)
            if not callable(producer):
                raise RuntimeOperationError(
                    "WAW_OUTPUT_INVALID",
                    "Fixed output producer is unavailable",
                    category="conflict",
                )
            produced = producer()
            if type(produced) is not int or produced < 0:
                raise RuntimeOperationError(
                    "WAW_OUTPUT_INVALID",
                    "Fixed output producer returned invalid evidence",
                    category="broken",
                )
            return produced

    def output_source(self) -> OutputSource:
        """Return the current Runtime-only output admission handle."""
        with self._lock:
            if self._output_source is None:
                raise RuntimeOperationError(
                    "WAW_OUTPUT_INVALID", "Workspace output is not admitted", category="conflict"
                )
            return self._output_source

    def append_output(self, source: OutputSource, payload: bytes) -> int:
        with self._lock:
            if source is not self._output_source:
                raise RuntimeOperationError(
                    "WAW_OUTPUT_SOURCE_INVALID",
                    "Output source is not admitted for this generation",
                    category="conflict",
                )
            if self._state not in {
                SupervisorState.RUNNING,
                SupervisorState.DETACHED,
                SupervisorState.INPUT_UNCERTAIN,
            }:
                raise RuntimeOperationError(
                    "WAW_OUTPUT_INVALID", "Workspace is not producing output", category="conflict"
                )
            return self._ring.append(payload).end_cursor

    def append_encrypted_output(self, source: OutputSource, payload: bytes) -> tuple[int, ...]:
        """Chunk the bounded producer read before allocating shared cursors."""
        if type(payload) is not bytes or not 1 <= len(payload) <= 64 * 1024:
            raise ValueError("producer read exceeds fixed bound")
        with self._lock:
            return tuple(
                self.append_output(source, payload[offset : offset + 32768])
                for offset in range(0, len(payload), 32768)
            )

    def replay_output(
        self,
        after_cursor: int,
        *,
        generation: int | None = None,
        runtime_epoch: str | None = None,
        attachment: AttachmentLease | None = None,
    ) -> OutputReplay:
        with self._lock:
            if attachment is not None:
                self._require_attachment(attachment)
            if generation is None or generation != self._generation:
                raise RuntimeOperationError(
                    "WAW_OUTPUT_STALE",
                    "Output cursor belongs to a different workspace generation",
                    category="conflict",
                )
            if self._state is SupervisorState.STOPPED:
                raise RuntimeOperationError(
                    "WAW_OUTPUT_STOPPED",
                    "Stopped workspace output is unavailable",
                    category="conflict",
                )
            if runtime_epoch is None or runtime_epoch != self._runtime_epoch:
                raise RuntimeOperationError(
                    "WAW_OUTPUT_STALE",
                    "Output cursor belongs to a different Runtime epoch",
                    category="conflict",
                )
            if self._attachment is not None:
                producer = getattr(self._transport, "produce_output", None)
                if callable(producer):
                    produced = producer()
                    if type(produced) is not int or produced < 0:
                        raise RuntimeOperationError(
                            "WAW_OUTPUT_INVALID",
                            "Fixed output producer returned invalid evidence",
                            category="broken",
                        )
            return self._ring.replay(after_cursor)

    def stop(self, attachment: AttachmentLease) -> SupervisorSnapshot:
        with self._lock:
            self._require_attachment(attachment)
            return self._stop_transport()

    def exact_stop(self, operation: WorkspaceStopOperation) -> SupervisorSnapshot:
        """Execute a durable generation-bound Stop without trusting a browser lease."""
        with self._lock:
            if not _same_stop_binding(operation, self._stop_binding):
                raise RuntimeOperationError(
                    "WAW_STOP_STALE",
                    "Stop operation does not match this workspace",
                    category="conflict",
                )
            if operation.result is not StopResult.PENDING:
                raise RuntimeOperationError(
                    "WAW_STOP_INVALID",
                    "Only a pending Stop operation may initiate Runtime stop",
                    category="conflict",
                )
            if self._state in {SupervisorState.STOPPING, SupervisorState.STOPPED}:
                raise RuntimeOperationError(
                    "WAW_STOP_INVALID",
                    "Workspace is already stopping or stopped",
                    category="conflict",
                )
            return self._stop_transport()

    def _stop_transport(self) -> SupervisorSnapshot:
        if self._state in {SupervisorState.STOPPING, SupervisorState.STOPPED}:
            raise RuntimeOperationError(
                "WAW_STOP_INVALID", "Workspace is already stopping or stopped", category="conflict"
            )
        self._state = SupervisorState.STOPPING
        # Revoke the exact pending/active stream before process effects. The
        # callback only marks closed and shuts down its one socket; it does not
        # wait for the registry lock that a concurrent sender may own.
        if self._runtime_pending is not None:
            try:
                fenced = self._runtime_pending.publication.invalidate()
            except Exception:
                fenced = False
            if not fenced:
                self._state = SupervisorState.RECONCILIATION_REQUIRED
                raise RuntimeOperationError(
                    "WAW_STOP_UNCONFIRMED",
                    "Publication shutdown is unconfirmed",
                    category="conflict",
                )
        try:
            evidence = self._transport.stop()
            if (
                evidence.workspace_id != self._workspace_id
                or evidence.generation != self._generation
                or evidence.managed_marker != self._command.managed_marker
                or not evidence.closed
                or evidence.remaining_members != 0
            ):
                self._state = SupervisorState.RECONCILIATION_REQUIRED
                raise RuntimeOperationError(
                    "WAW_STOP_UNCONFIRMED",
                    "Runtime did not provide exact close evidence",
                    category="conflict",
                )
        except RuntimeOperationError as exc:
            if self._state is SupervisorState.RECONCILIATION_REQUIRED:
                raise
            self._state = SupervisorState.BROKEN
            raise RuntimeOperationError(
                "WAW_STOP_FAILED", "Runtime transport could not stop", category="broken"
            ) from exc
        except Exception as exc:
            self._state = SupervisorState.BROKEN
            raise RuntimeOperationError(
                "WAW_STOP_FAILED", "Runtime transport could not stop", category="broken"
            ) from exc
        self._attachment = None
        self._output_source = None
        self._state = SupervisorState.STOPPED
        self._ring.clear()
        return self.snapshot()

    def _check_attachment(self, attachment: AttachmentLease) -> None:
        claims = attachment.claims
        epoch = (
            attachment.runtime_epoch
            if isinstance(attachment, RuntimeAttachmentLease)
            else attachment.context.runtime_epoch if attachment.context is not None else None
        )
        if epoch != self._runtime_epoch:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_STALE",
                "Attachment belongs to a different Runtime epoch",
                category="conflict",
            )
        if (
            claims.workspace_id != self._workspace_id
            or claims.project_id != self._stop_binding.project_id
            or claims.agent_type is not self._stop_binding.agent_type
            or claims.generation != self._generation
            or claims.runtime_host_installation_id
            != self._stop_binding.runtime_host_installation_id
            or claims.runtime_host_installation_revision
            != self._stop_binding.runtime_host_installation_revision
            or claims.binding_revision != self._stop_binding.binding_revision
            or claims.binding_digest != self._stop_binding.binding_digest
        ):
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_STALE",
                "Attachment does not match this workspace binding",
                category="conflict",
            )
        if not attachment.active_at(self._clock()):
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_EXPIRED", "Attachment lease is expired", category="conflict"
            )
        valid = (
            attachment.current()
            if isinstance(attachment, RuntimeAttachmentLease)
            else self._attachment_validator(attachment)
        )
        if not valid:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_REVOKED",
                "Attachment is no longer current at the authority",
                category="conflict",
            )

    def _require_attachment(self, attachment: AttachmentLease) -> None:
        self._check_attachment(attachment)
        if self._attachment is None or self._attachment is not attachment:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_REQUIRED",
                "An active writer attachment is required",
                category="conflict",
            )


def _same_stop_binding(left: WorkspaceStopOperation, right: WorkspaceStopOperation) -> bool:
    return (
        left.workspace_id == right.workspace_id
        and left.project_id == right.project_id
        and left.agent_type is right.agent_type
        and left.generation == right.generation
        and left.binding_revision == right.binding_revision
        and left.binding_digest == right.binding_digest
        and left.runtime_host_installation_id == right.runtime_host_installation_id
        and left.runtime_host_installation_revision == right.runtime_host_installation_revision
    )


__all__ = [
    "RuntimeProbeEvidence",
    "RuntimeProbeState",
    "RuntimeStartEvidence",
    "RuntimeStopEvidence",
    "OutputSource",
    "SupervisorSnapshot",
    "SupervisorState",
    "WAWSupervisor",
    "WAWTransport",
]
