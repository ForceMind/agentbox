"""Control Plane persistence service for WAW workspace metadata."""

from __future__ import annotations

import re
from enum import StrEnum

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.models import Project
from agentbox_core.waw import (
    AgentType,
    AgentWorkspaceSession,
    ReconciliationState,
    StopResult,
    WAWDomainError,
    WorkspaceState,
    WorkspaceStopOperation,
    managed_marker,
    managed_session_name,
)
from agentbox_core.waw_models import (
    AgentWorkspaceSessionRecord,
    RuntimeHostInstallation,
    WorkspaceStopOperationRecord,
)


class WorkspaceSessionError(RuntimeError):
    """Base class for bounded persistence-service failures."""


class WorkspaceSessionNotFound(WorkspaceSessionError):
    pass


class WorkspaceSessionConflict(WorkspaceSessionError):
    pass


class WorkspaceSessionNotReady(WorkspaceSessionError):
    pass


class WorkspaceStopNotFound(WorkspaceSessionError):
    pass


_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_DECIMAL_U64 = re.compile(r"\A(?:0|[1-9][0-9]{0,19})\Z")
_MAX_U64 = 2**64 - 1
_TERMINAL = frozenset({WorkspaceState.EXITED, WorkspaceState.STOPPED})
_RESTARTABLE = frozenset(
    {
        WorkspaceState.EXITED,
        WorkspaceState.STOPPED,
        WorkspaceState.MISSING,
        WorkspaceState.BROKEN,
        WorkspaceState.UNKNOWN,
    }
)


class RuntimeEpochClassification(StrEnum):
    """Durable interpretation of one verified Runtime bind epoch."""

    FIRST_BIND = "first_bind"
    API_RESTART = "api_restart"
    RUNTIME_RESTART = "runtime_restart"


class RuntimeEpochBindingError(WorkspaceSessionConflict):
    """The verified Runtime epoch cannot advance the durable host fence."""


def _runtime_epoch(value: str) -> int:
    if not isinstance(value, str) or _DECIMAL_U64.fullmatch(value) is None:
        raise RuntimeEpochBindingError("Runtime epoch is invalid")
    parsed = int(value)
    if parsed == 0 or parsed > _MAX_U64:
        raise RuntimeEpochBindingError("Runtime epoch is invalid")
    return parsed


class WorkspaceSessionService:
    """Bounded CRUD and optimistic state transitions for one WAW row."""

    def __init__(self, database: Database, clock: Clock) -> None:
        self._database = database
        self._clock = clock

    def get(self, workspace_id_value: str) -> AgentWorkspaceSessionRecord:
        with self._database.transaction() as session:
            row = session.get(AgentWorkspaceSessionRecord, workspace_id_value)
            if row is None:
                raise WorkspaceSessionNotFound(workspace_id_value)
            return row

    def classify_runtime_epoch(
        self,
        *,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: int,
        observed_runtime_epoch: str,
    ) -> RuntimeEpochClassification:
        """Persist one verified bind epoch and atomically fence a Runtime restart."""

        observed = _runtime_epoch(observed_runtime_epoch)
        if (
            not isinstance(runtime_host_installation_id, str)
            or type(runtime_host_installation_revision) is not int
            or runtime_host_installation_revision < 1
        ):
            raise RuntimeEpochBindingError("Runtime host identity is invalid")
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
            host = session.get(RuntimeHostInstallation, runtime_host_installation_id)
            if host is None or host.revision != runtime_host_installation_revision:
                raise RuntimeEpochBindingError("Runtime host identity is not current")
            previous_raw = host.last_runtime_epoch
            if previous_raw is None:
                host.last_runtime_epoch = observed_runtime_epoch
                host.updated_at = now
                session.flush()
                return RuntimeEpochClassification.FIRST_BIND
            previous = _runtime_epoch(previous_raw)
            if observed < previous:
                raise RuntimeEpochBindingError("Runtime epoch is stale")
            host.updated_at = now
            if observed == previous:
                session.flush()
                return RuntimeEpochClassification.API_RESTART
            host.last_runtime_epoch = observed_runtime_epoch
            session.execute(
                update(AgentWorkspaceSessionRecord)
                .where(
                    AgentWorkspaceSessionRecord.runtime_host_installation_id
                    == runtime_host_installation_id,
                    AgentWorkspaceSessionRecord.runtime_host_installation_revision
                    == runtime_host_installation_revision,
                    AgentWorkspaceSessionRecord.state.not_in(
                        tuple(state.value for state in _TERMINAL)
                    ),
                )
                .values(
                    state=WorkspaceState.UNKNOWN.value,
                    reconciliation_state=ReconciliationState.RECONCILIATION_REQUIRED.value,
                    failure_code="RUNTIME_RESTART",
                    revision=AgentWorkspaceSessionRecord.revision + 1,
                    updated_at=now,
                    last_seen_at=now,
                )
            )
            session.execute(
                update(WorkspaceStopOperationRecord)
                .where(
                    WorkspaceStopOperationRecord.runtime_host_installation_id
                    == runtime_host_installation_id,
                    WorkspaceStopOperationRecord.runtime_host_installation_revision
                    == runtime_host_installation_revision,
                    WorkspaceStopOperationRecord.result == StopResult.PENDING.value,
                )
                .values(
                    result=StopResult.RECONCILIATION_REQUIRED.value,
                    failure_code="RUNTIME_RESTART",
                    updated_at=now,
                )
            )
            session.flush()
            return RuntimeEpochClassification.RUNTIME_RESTART

    def create(
        self,
        *,
        project_id: str,
        agent_type: AgentType | str,
        authorization_scope: str,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: int,
        binding_revision: int,
        binding_digest: str,
        executable_fingerprint: str,
    ) -> AgentWorkspaceSessionRecord:
        """Create the first-generation STARTING row after Project readiness checks."""

        now = self._clock.now()
        agent = AgentType(agent_type)
        if not authorization_scope or len(authorization_scope) > 128:
            raise WAWDomainError("authorization_scope is invalid")
        if not _HEX64.fullmatch(executable_fingerprint):
            raise WAWDomainError("executable_fingerprint must be lowercase SHA-256")
        workspace = AgentWorkspaceSession(
            project_id=project_id,
            agent_type=agent,
            runtime_host_installation_id=runtime_host_installation_id,
            runtime_host_installation_revision=runtime_host_installation_revision,
            binding_revision=binding_revision,
            binding_digest=binding_digest,
            generation=1,
        )
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            project = session.get(Project, project_id)
            if project is None or project.archived_at is not None or project.state != "ready":
                raise WorkspaceSessionNotReady(project_id)
            host = session.get(RuntimeHostInstallation, runtime_host_installation_id)
            if host is None or host.revision != runtime_host_installation_revision:
                raise WorkspaceSessionConflict("runtime host identity is not current")
            row = AgentWorkspaceSessionRecord(
                id=workspace.workspace_id,
                project_id=project_id,
                authorization_scope=authorization_scope,
                runtime_host_installation_id=runtime_host_installation_id,
                runtime_host_installation_revision=runtime_host_installation_revision,
                runtime_type="agentbox-runtime-linux-v1",
                agent_type=agent.value,
                state=WorkspaceState.STARTING.value,
                runtime_session_name=managed_session_name(project_id, agent),
                runtime_marker=managed_marker(
                    runtime_host_installation_id=runtime_host_installation_id,
                    runtime_host_installation_revision=runtime_host_installation_revision,
                    project_id=project_id,
                    agent_type=agent,
                    workspace_id_value=workspace.workspace_id,
                    generation=1,
                    binding_revision=binding_revision,
                    binding_digest=binding_digest,
                ),
                executable_fingerprint=executable_fingerprint,
                generation=1,
                binding_revision=binding_revision,
                binding_digest=binding_digest,
                revision=1,
                created_at=now,
                updated_at=now,
                last_seen_at=now,
                reconciliation_state=ReconciliationState.AUTHORITATIVE.value,
            )
            try:
                session.add(row)
                session.flush()
            except IntegrityError as exc:
                raise WorkspaceSessionConflict(
                    "Project/AgentType workspace already exists"
                ) from exc
            return row

    def transition(
        self,
        workspace_id_value: str,
        *,
        expected_revision: int,
        state: WorkspaceState | str,
        reconciliation_state: ReconciliationState | str | None = None,
        exit_code: int | None = None,
        failure_code: str | None = None,
    ) -> AgentWorkspaceSessionRecord:
        """Apply one domain-checked transition with compare-and-swap revision."""

        if type(expected_revision) is not int or expected_revision < 1:
            raise WorkspaceSessionConflict("expected revision is invalid")
        target = WorkspaceState(state)
        now = self._clock.now()
        with self._database.transaction() as session:
            row = session.get(AgentWorkspaceSessionRecord, workspace_id_value)
            if row is None:
                raise WorkspaceSessionNotFound(workspace_id_value)
            if row.revision != expected_revision:
                raise WorkspaceSessionConflict("workspace revision is stale")
            current = AgentWorkspaceSession(
                project_id=row.project_id,
                agent_type=row.agent_type,
                runtime_host_installation_id=row.runtime_host_installation_id,
                runtime_host_installation_revision=row.runtime_host_installation_revision,
                binding_revision=row.binding_revision,
                binding_digest=row.binding_digest,
                generation=row.generation,
                state=row.state,
                reconciliation_state=row.reconciliation_state,
                id=row.id,
            )
            next_domain = current.transition(target, reconciliation_state=reconciliation_state)
            row.state = WorkspaceState(next_domain.state).value
            if reconciliation_state is not None:
                row.reconciliation_state = ReconciliationState(
                    next_domain.reconciliation_state
                ).value
            row.exit_code = exit_code
            row.failure_code = failure_code
            row.revision += 1
            row.updated_at = now
            row.last_seen_at = now
            session.flush()
            return row

    def begin_start(
        self, workspace_id_value: str, *, expected_revision: int
    ) -> AgentWorkspaceSessionRecord:
        """Allocate exactly one next generation before a restartable spawn."""

        now = self._clock.now()
        with self._database.transaction() as session:
            row = session.get(AgentWorkspaceSessionRecord, workspace_id_value)
            if row is None:
                raise WorkspaceSessionNotFound(workspace_id_value)
            if row.revision != expected_revision or WorkspaceState(row.state) not in _RESTARTABLE:
                raise WorkspaceSessionConflict("workspace is stale or not restartable")
            if row.generation >= 2**63 - 1:
                raise WorkspaceSessionConflict("generation sequence exhausted")
            row.generation += 1
            row.state = WorkspaceState.STARTING.value
            row.reconciliation_state = ReconciliationState.AUTHORITATIVE.value
            row.runtime_marker = managed_marker(
                runtime_host_installation_id=row.runtime_host_installation_id,
                runtime_host_installation_revision=row.runtime_host_installation_revision,
                project_id=row.project_id,
                agent_type=row.agent_type,
                workspace_id_value=row.id,
                generation=row.generation,
                binding_revision=row.binding_revision,
                binding_digest=row.binding_digest,
            )
            row.exit_code = None
            row.failure_code = None
            row.revision += 1
            row.updated_at = now
            row.last_seen_at = now
            session.flush()
            return row

    def begin_stop(
        self, workspace_id_value: str, *, expected_revision: int
    ) -> WorkspaceStopOperationRecord:
        """Persist one generation/binding-bound Stop intent before Runtime work."""

        now = self._clock.now()
        with self._database.transaction() as session:
            row = session.get(AgentWorkspaceSessionRecord, workspace_id_value)
            if row is None:
                raise WorkspaceSessionNotFound(workspace_id_value)
            if row.revision != expected_revision:
                raise WorkspaceSessionConflict("workspace revision is stale")
            current = AgentWorkspaceSession(
                project_id=row.project_id,
                agent_type=row.agent_type,
                runtime_host_installation_id=row.runtime_host_installation_id,
                runtime_host_installation_revision=row.runtime_host_installation_revision,
                binding_revision=row.binding_revision,
                binding_digest=row.binding_digest,
                generation=row.generation,
                state=row.state,
                reconciliation_state=row.reconciliation_state,
                id=row.id,
            )
            current.transition(WorkspaceState.STOPPING)
            operation = WorkspaceStopOperation(
                workspace_id=row.id,
                project_id=row.project_id,
                agent_type=row.agent_type,
                generation=row.generation,
                binding_revision=row.binding_revision,
                binding_digest=row.binding_digest,
                runtime_host_installation_id=row.runtime_host_installation_id,
                runtime_host_installation_revision=row.runtime_host_installation_revision,
            )
            record = WorkspaceStopOperationRecord(
                id=operation.stop_operation_id,
                workspace_id=row.id,
                project_id=row.project_id,
                agent_type=row.agent_type,
                generation=row.generation,
                binding_revision=row.binding_revision,
                binding_digest=row.binding_digest,
                runtime_host_installation_id=row.runtime_host_installation_id,
                runtime_host_installation_revision=row.runtime_host_installation_revision,
                result=StopResult(operation.result).value,
                created_at=now,
                updated_at=now,
            )
            row.state = WorkspaceState.STOPPING.value
            row.reconciliation_state = ReconciliationState.STOPPING.value
            row.revision += 1
            row.updated_at = now
            session.add(record)
            session.flush()
            return record

    def complete_stop(
        self,
        stop_operation_id: str,
        *,
        result: StopResult | str,
        failure_code: str | None = None,
    ) -> WorkspaceStopOperationRecord:
        """Record exact-stop evidence outcome and reconcile the session."""

        outcome = StopResult(result)
        if outcome is StopResult.PENDING:
            raise WorkspaceSessionConflict("stop completion result must be terminal")
        now = self._clock.now()
        with self._database.transaction() as session:
            record = session.get(WorkspaceStopOperationRecord, stop_operation_id)
            if record is None:
                raise WorkspaceStopNotFound(stop_operation_id)
            if record.result != StopResult.PENDING.value:
                if record.result == outcome.value:
                    return record
                raise WorkspaceSessionConflict("stop operation is already terminal")
            if failure_code is not None and (
                not failure_code
                or len(failure_code) > 64
                or any(ord(character) < 32 for character in failure_code)
            ):
                raise WorkspaceSessionConflict("stop failure code is invalid")
            row = session.get(AgentWorkspaceSessionRecord, record.workspace_id)
            if row is None or (
                row.project_id != record.project_id
                or row.agent_type != record.agent_type
                or row.generation != record.generation
                or row.binding_revision != record.binding_revision
                or row.binding_digest != record.binding_digest
                or row.runtime_host_installation_id != record.runtime_host_installation_id
                or row.runtime_host_installation_revision
                != record.runtime_host_installation_revision
                or row.state != WorkspaceState.STOPPING.value
                or row.reconciliation_state != ReconciliationState.STOPPING.value
            ):
                raise WorkspaceSessionConflict("stop operation binding is stale")
            record.result = outcome.value
            record.failure_code = failure_code
            record.updated_at = now
            row.state = (
                WorkspaceState.STOPPED.value
                if outcome is StopResult.STOPPED
                else WorkspaceState.UNKNOWN.value
            )
            row.reconciliation_state = (
                ReconciliationState.AUTHORITATIVE.value
                if outcome is StopResult.STOPPED
                else ReconciliationState.RECONCILIATION_REQUIRED.value
            )
            row.failure_code = failure_code
            row.revision += 1
            row.updated_at = now
            row.last_seen_at = now
            session.flush()
            return record


__all__ = [
    "RuntimeEpochBindingError",
    "RuntimeEpochClassification",
    "WorkspaceSessionConflict",
    "WorkspaceSessionError",
    "WorkspaceSessionNotFound",
    "WorkspaceSessionNotReady",
    "WorkspaceStopNotFound",
    "WorkspaceSessionService",
]
