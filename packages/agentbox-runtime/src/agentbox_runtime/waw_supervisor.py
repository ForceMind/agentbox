"""Bounded Runtime supervisor contract for one Web Agent Workspace.

The supervisor is deliberately transport-agnostic.  A Runtime adapter may
implement :class:`WAWTransport` with a real PTY, but the adapter receives only
the already validated fixed command contract.  This module owns lifecycle and
attachment fencing; it never accepts a shell command, path, executable, or
secret from a caller.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from agentbox_core.waw import validate_positive_u64, validate_workspace_id
from agentbox_core.waw_tickets import ActiveAttachment

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_pty import OutputReplay, OutputRing, PtyGeometry, validate_input


class SupervisorState(StrEnum):
    ADMITTED = "ADMITTED"
    RUNNING = "RUNNING"
    DETACHED = "DETACHED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    BROKEN = "BROKEN"
    INPUT_UNCERTAIN = "INPUT_UNCERTAIN"


class WAWTransport(Protocol):
    """The only side-effecting operations a WAW Runtime adapter may expose."""

    def start(self, command: WAWClaudeCommand, geometry: PtyGeometry) -> None: ...

    def write(self, data: bytes) -> None: ...

    def resize(self, geometry: PtyGeometry) -> None: ...

    def stop(self) -> None: ...


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
        command: WAWClaudeCommand,
        transport: WAWTransport,
        geometry: PtyGeometry,
        clock: Callable[[], float],
        output_capacity_bytes: int = 256 * 1024,
    ) -> None:
        validate_workspace_id(workspace_id)
        validate_positive_u64(generation, field="generation")
        if command.workspace_id != workspace_id:
            raise RuntimeOperationError(
                "WAW_WORKSPACE_MISMATCH",
                "Runtime command workspace does not match",
                category="validation",
            )
        self._workspace_id = workspace_id
        self._generation = generation
        self._command = command
        self._transport = transport
        self._geometry = geometry
        self._clock = clock
        self._ring = OutputRing(capacity_bytes=output_capacity_bytes)
        self._state = SupervisorState.ADMITTED
        self._attachment: ActiveAttachment | None = None

    @property
    def state(self) -> SupervisorState:
        return self._state

    def snapshot(self) -> SupervisorSnapshot:
        return SupervisorSnapshot(
            workspace_id=self._workspace_id,
            generation=self._generation,
            state=self._state,
            geometry=self._geometry,
            next_cursor=self._ring.next_cursor,
            buffered_bytes=self._ring.buffered_bytes,
            attachment_id=(self._attachment.attachment_id if self._attachment else None),
        )

    def start(self) -> SupervisorSnapshot:
        if self._state is not SupervisorState.ADMITTED:
            raise RuntimeOperationError(
                "WAW_START_INVALID", "Workspace is not admitted for start", category="conflict"
            )
        try:
            self._transport.start(self._command, self._geometry)
        except Exception as exc:
            self._state = SupervisorState.BROKEN
            raise RuntimeOperationError(
                "WAW_START_FAILED", "Runtime transport could not start", category="unavailable"
            ) from exc
        self._state = SupervisorState.RUNNING
        return self.snapshot()

    def attach(self, attachment: ActiveAttachment) -> SupervisorSnapshot:
        self._check_attachment(attachment)
        if self._state not in {SupervisorState.RUNNING, SupervisorState.DETACHED}:
            raise RuntimeOperationError(
                "WAW_ATTACH_INVALID", "Workspace is not attachable", category="conflict"
            )
        if (
            self._attachment is not None
            and self._attachment.attachment_id != attachment.attachment_id
        ):
            raise RuntimeOperationError(
                "WAW_WRITER_BUSY", "Workspace already has a writer attachment", category="conflict"
            )
        self._attachment = attachment
        self._state = SupervisorState.RUNNING
        return self.snapshot()

    def detach(self, attachment: ActiveAttachment) -> SupervisorSnapshot:
        self._require_attachment(attachment)
        self._attachment = None
        self._state = SupervisorState.DETACHED
        return self.snapshot()

    def write_input(self, attachment: ActiveAttachment, data: bytes) -> None:
        self._require_attachment(attachment)
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

    def resize(self, attachment: ActiveAttachment, geometry: PtyGeometry) -> SupervisorSnapshot:
        self._require_attachment(attachment)
        try:
            self._transport.resize(geometry)
        except Exception as exc:
            self._state = SupervisorState.BROKEN
            raise RuntimeOperationError(
                "WAW_RESIZE_FAILED", "Runtime could not resize the PTY", category="broken"
            ) from exc
        self._geometry = geometry
        return self.snapshot()

    def append_output(self, payload: bytes) -> int:
        if self._state not in {
            SupervisorState.RUNNING,
            SupervisorState.DETACHED,
            SupervisorState.INPUT_UNCERTAIN,
        }:
            raise RuntimeOperationError(
                "WAW_OUTPUT_INVALID", "Workspace is not producing output", category="conflict"
            )
        return self._ring.append(payload).end_cursor

    def replay_output(self, after_cursor: int) -> OutputReplay:
        if self._state is SupervisorState.STOPPED:
            raise RuntimeOperationError(
                "WAW_OUTPUT_STOPPED", "Stopped workspace output is unavailable", category="conflict"
            )
        return self._ring.replay(after_cursor)

    def stop(self, attachment: ActiveAttachment) -> SupervisorSnapshot:
        self._require_attachment(attachment)
        if self._state in {SupervisorState.STOPPING, SupervisorState.STOPPED}:
            raise RuntimeOperationError(
                "WAW_STOP_INVALID", "Workspace is already stopping or stopped", category="conflict"
            )
        self._state = SupervisorState.STOPPING
        try:
            self._transport.stop()
        except Exception as exc:
            self._state = SupervisorState.BROKEN
            raise RuntimeOperationError(
                "WAW_STOP_FAILED", "Runtime transport could not stop", category="broken"
            ) from exc
        self._attachment = None
        self._state = SupervisorState.STOPPED
        return self.snapshot()

    def _check_attachment(self, attachment: ActiveAttachment) -> None:
        claims = attachment.claims
        if claims.workspace_id != self._workspace_id or claims.generation != self._generation:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_STALE",
                "Attachment does not match this workspace generation",
                category="conflict",
            )
        if not attachment.active_at(self._clock()):
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_EXPIRED", "Attachment lease is expired", category="conflict"
            )

    def _require_attachment(self, attachment: ActiveAttachment) -> None:
        self._check_attachment(attachment)
        if self._attachment is None or self._attachment.attachment_id != attachment.attachment_id:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_REQUIRED",
                "An active writer attachment is required",
                category="conflict",
            )


__all__ = ["SupervisorSnapshot", "SupervisorState", "WAWSupervisor", "WAWTransport"]
