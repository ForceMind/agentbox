"""Pure WAW-3 recovery and resume fencing contracts.

This module contains no transport, process, filesystem, or persistence logic.
It classifies an attachment resume request using the complete immutable
workspace identity and deliberately fails closed at every epoch boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agentbox_core.waw import (
    AgentType,
    validate_attachment_id,
    validate_binding_digest,
    validate_positive_u64,
    validate_project_id,
    validate_runtime_host_installation_id,
    validate_workspace_id,
    workspace_id,
)


class RecoveryError(ValueError):
    """A malformed or stale recovery claim."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class RecoveryDecision(StrEnum):
    REPLAY = "REPLAY"
    FRESH_ATTACHMENT = "FRESH_ATTACHMENT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class RecoveryIdentity:
    """Exact non-secret identity required to resume output."""

    workspace_id: str
    project_id: str
    agent_type: str
    generation: int
    binding_revision: int
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    runtime_epoch: int
    api_authority_epoch: int
    attachment_id: str
    lease_number: int
    session_id: str
    auth_epoch: int
    mode: str = "writer"

    def __post_init__(self) -> None:
        try:
            validate_workspace_id(self.workspace_id)
            validate_project_id(self.project_id)
            validate_attachment_id(self.attachment_id)
            validate_runtime_host_installation_id(self.runtime_host_installation_id)
            validate_binding_digest(self.binding_digest)
            agent = AgentType(self.agent_type)
            if self.workspace_id != workspace_id(self.project_id, agent):
                raise ValueError("workspace identity does not match")
        except (TypeError, ValueError) as exc:
            raise RecoveryError(
                "RECOVERY_IDENTITY_INVALID", "canonical identity is invalid"
            ) from exc
        if not isinstance(self.session_id, str) or not self.session_id:
            raise RecoveryError("RECOVERY_IDENTITY_INVALID", "session_id is required")
        if self.mode != "writer":
            raise RecoveryError("RECOVERY_IDENTITY_INVALID", "mode must be writer")
        for field in (
            "generation",
            "binding_revision",
            "runtime_host_installation_revision",
            "runtime_epoch",
            "api_authority_epoch",
            "lease_number",
            "auth_epoch",
        ):
            value = getattr(self, field)
            try:
                validate_positive_u64(value, field=field)
            except (TypeError, ValueError) as exc:
                raise RecoveryError("RECOVERY_IDENTITY_INVALID", f"{field} is invalid") from exc


@dataclass(frozen=True)
class ResumeHint:
    """The only accepted cursor/epoch combinations for attachment prepare."""

    resume_cursor: int | None
    previous_runtime_epoch: int | None

    def validate(self, *, current_runtime_epoch: int) -> ResumeHint:
        if type(current_runtime_epoch) is not int or not 1 <= current_runtime_epoch <= 2**64 - 1:
            raise RecoveryError("RESUME_HINT_INVALID", "current runtime epoch is invalid")
        cursor = self.resume_cursor
        previous = self.previous_runtime_epoch
        if cursor is not None and (type(cursor) is not int or not 0 <= cursor <= 2**64 - 1):
            raise RecoveryError("RESUME_HINT_INVALID", "resume cursor must be non-negative")
        if previous is not None and (type(previous) is not int or not 1 <= previous <= 2**64 - 1):
            raise RecoveryError("RESUME_HINT_INVALID", "previous runtime epoch must be positive")
        # Fresh attachment after API restart: null/null or 0/null only.
        if cursor in (None, 0) and previous is None:
            return self
        # Replay is valid only inside the same Runtime epoch.  Any other
        # epoch is a reconciliation boundary, never a synthetic GAP.
        if cursor is not None and cursor > 0 and previous == current_runtime_epoch:
            return self
        raise RecoveryError(
            "RESUME_HINT_INVALID",
            "resume requires a positive cursor bound to the current runtime epoch",
        )


def classify_resume(
    *,
    expected: RecoveryIdentity,
    actual: RecoveryIdentity,
    hint: ResumeHint,
) -> RecoveryDecision:
    """Classify a resume without ever permitting cross-epoch replay."""

    stable_fields = (
        "workspace_id",
        "project_id",
        "agent_type",
        "generation",
        "binding_revision",
        "binding_digest",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_epoch",
        "api_authority_epoch",
        "session_id",
        "auth_epoch",
        "mode",
    )
    if all(getattr(expected, field) == getattr(actual, field) for field in stable_fields):
        hint.validate(current_runtime_epoch=expected.runtime_epoch)
        return (
            RecoveryDecision.REPLAY
            if hint.resume_cursor not in (None, 0)
            else RecoveryDecision.FRESH_ATTACHMENT
        )
    if (
        expected.workspace_id == actual.workspace_id
        and expected.project_id == actual.project_id
        and expected.agent_type == actual.agent_type
        and expected.generation == actual.generation
        and expected.binding_revision == actual.binding_revision
        and expected.binding_digest == actual.binding_digest
        and expected.runtime_host_installation_id == actual.runtime_host_installation_id
        and expected.runtime_host_installation_revision == actual.runtime_host_installation_revision
        and expected.session_id == actual.session_id
        and expected.auth_epoch == actual.auth_epoch
        and expected.mode == actual.mode
        and expected.runtime_epoch != actual.runtime_epoch
    ):
        raise RecoveryError(
            "RECONCILIATION_REQUIRED",
            "Runtime epoch changed; output replay is fenced",
        )
    if (
        expected.workspace_id == actual.workspace_id
        and expected.project_id == actual.project_id
        and expected.agent_type == actual.agent_type
        and expected.generation == actual.generation
        and expected.binding_revision == actual.binding_revision
        and expected.binding_digest == actual.binding_digest
        and expected.runtime_host_installation_id == actual.runtime_host_installation_id
        and expected.runtime_host_installation_revision == actual.runtime_host_installation_revision
        and expected.runtime_epoch == actual.runtime_epoch
        and expected.api_authority_epoch != actual.api_authority_epoch
        and expected.session_id == actual.session_id
        and expected.auth_epoch == actual.auth_epoch
        and expected.mode == actual.mode
    ):
        hint.validate(current_runtime_epoch=expected.runtime_epoch)
        if hint.resume_cursor not in (None, 0):
            raise RecoveryError(
                "RECONCILIATION_REQUIRED", "API restart requires a fresh attachment"
            )
        return RecoveryDecision.FRESH_ATTACHMENT
    if (
        expected.workspace_id == actual.workspace_id
        and expected.project_id == actual.project_id
        and expected.agent_type == actual.agent_type
        and expected.generation == actual.generation
        and expected.binding_revision == actual.binding_revision
        and expected.binding_digest == actual.binding_digest
        and expected.runtime_host_installation_id == actual.runtime_host_installation_id
        and expected.runtime_host_installation_revision == actual.runtime_host_installation_revision
        and expected.runtime_epoch == actual.runtime_epoch
        and expected.api_authority_epoch == actual.api_authority_epoch
    ):
        raise RecoveryError("RECOVERY_IDENTITY_STALE", "session or authorization identity changed")
    if (
        expected.workspace_id == actual.workspace_id
        and expected.project_id == actual.project_id
        and expected.agent_type == actual.agent_type
    ):
        raise RecoveryError(
            "RECONCILIATION_REQUIRED",
            "workspace generation, binding, host, or Runtime epoch changed",
        )
    raise RecoveryError("RECOVERY_IDENTITY_STALE", "recovery identity does not match")


__all__ = ["RecoveryDecision", "RecoveryError", "RecoveryIdentity", "ResumeHint", "classify_resume"]
