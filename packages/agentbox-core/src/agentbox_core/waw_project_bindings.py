"""Durable Control Plane ledger for typed WAW Project registration."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from agentbox_protocol.waw_control import WAWControlError, validate_relative_key
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.models import Project
from agentbox_core.waw_models import (
    AgentWorkspaceSessionRecord,
    ProjectBindingRecord,
    RuntimeHostInstallation,
)

_PROJECT_ID = re.compile(r"\Aprj_[0-9a-f]{32}\Z")
_HOST_ID = re.compile(r"\Awri_[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_MAX_SQLITE_SEQUENCE = 2**63 - 1
MAX_REPLAY_BINDINGS = 256
_TERMINAL_WORKSPACE_STATES = ("EXITED", "STOPPED")
_RECONCILIATION_FENCE_EXCLUDED_WORKSPACE_STATES = ("EXITED", "STOPPED", "STOPPING")


class ProjectBindingStatus(StrEnum):
    PENDING = "PENDING"
    CURRENT = "CURRENT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    SUPERSEDED = "SUPERSEDED"


class ProjectBindingError(RuntimeError):
    """Base class for bounded binding-ledger failures."""


class ProjectBindingNotFound(ProjectBindingError):
    pass


class ProjectBindingConflict(ProjectBindingError):
    pass


class ProjectBindingNotReady(ProjectBindingError):
    pass


def _positive_integer(value: int, *, field: str) -> int:
    if type(value) is not int or value < 1 or value > _MAX_SQLITE_SEQUENCE:
        raise ProjectBindingConflict(f"{field} is invalid")
    return value


def _identifier(value: str, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ProjectBindingConflict(f"{field} is invalid")
    return value


def _digest(value: str, *, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ProjectBindingConflict(f"{field} is invalid")
    return value


class ProjectBindingService:
    """Allocate and commit one monotonic Project binding chain.

    Runtime calls are deliberately outside this service.  ``reserve`` commits
    the exact request snapshot before a caller performs I/O; ``commit`` then
    accepts only the matching Runtime-attested digest.  A retry observes the
    same open attempt or the already committed row.
    """

    def __init__(self, database: Database, clock: Clock) -> None:
        self._database = database
        self._clock = clock

    def get(self, project_id: str, binding_revision: int) -> ProjectBindingRecord:
        project = _identifier(project_id, field="project_id", pattern=_PROJECT_ID)
        revision = _positive_integer(binding_revision, field="binding_revision")
        with self._database.transaction() as session:
            row = session.get(ProjectBindingRecord, (project, revision))
            if row is None:
                raise ProjectBindingNotFound(project_id)
            return row

    def get_head(self, project_id: str) -> ProjectBindingRecord:
        project = _identifier(project_id, field="project_id", pattern=_PROJECT_ID)
        with self._database.transaction() as session:
            row = session.scalar(
                select(ProjectBindingRecord).where(
                    ProjectBindingRecord.project_id == project,
                    ProjectBindingRecord.binding_digest.is_not(None),
                    ProjectBindingRecord.status.in_(
                        (
                            ProjectBindingStatus.CURRENT.value,
                            ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                        )
                    ),
                )
            )
            if row is None:
                raise ProjectBindingNotFound(project_id)
            return row

    def get_open_attempt(self, project_id: str) -> ProjectBindingRecord:
        project = _identifier(project_id, field="project_id", pattern=_PROJECT_ID)
        with self._database.transaction() as session:
            row = session.scalar(
                select(ProjectBindingRecord).where(
                    ProjectBindingRecord.project_id == project,
                    ProjectBindingRecord.binding_digest.is_(None),
                    ProjectBindingRecord.status.in_(
                        (
                            ProjectBindingStatus.PENDING.value,
                            ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                        )
                    ),
                )
            )
            if row is None:
                raise ProjectBindingNotFound(project_id)
            return row

    def list_current(self, *, limit: int = MAX_REPLAY_BINDINGS) -> tuple[ProjectBindingRecord, ...]:
        if type(limit) is not int or not 1 <= limit <= MAX_REPLAY_BINDINGS:
            raise ProjectBindingConflict("binding enumeration limit is invalid")
        with self._database.transaction() as session:
            rows = tuple(
                session.scalars(
                    select(ProjectBindingRecord)
                    .where(ProjectBindingRecord.status == ProjectBindingStatus.CURRENT.value)
                    .order_by(ProjectBindingRecord.project_id)
                    .limit(limit + 1)
                )
            )
        if len(rows) > limit:
            raise ProjectBindingConflict("binding enumeration limit exceeded")
        return rows

    def list_replay_plan(
        self, *, limit: int = MAX_REPLAY_BINDINGS
    ) -> tuple[ProjectBindingRecord, ...]:
        """Return one deterministic binding attempt per Project for Runtime replay.

        The result is ordered by ``project_id`` and contains at most 256 rows.
        An open ``PENDING`` (including a digest-less reconciliation attempt) is
        selected before its current head.  A digest-known reconciliation state is
        an inventory-drift blocker, never a replayable current binding.
        """

        if type(limit) is not int or not 1 <= limit <= MAX_REPLAY_BINDINGS:
            raise ProjectBindingConflict("binding replay limit is invalid")
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            rows = tuple(
                session.scalars(
                    select(ProjectBindingRecord)
                    .where(
                        ProjectBindingRecord.status.in_(
                            (
                                ProjectBindingStatus.PENDING.value,
                                ProjectBindingStatus.CURRENT.value,
                                ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                            )
                        )
                    )
                    .order_by(
                        ProjectBindingRecord.project_id,
                        ProjectBindingRecord.binding_revision,
                    )
                    .limit((limit * 2) + 1)
                )
            )
            by_project: dict[str, list[ProjectBindingRecord]] = {}
            for row in rows:
                by_project.setdefault(row.project_id, []).append(row)
            if len(rows) > limit * 2 or len(by_project) > limit:
                raise ProjectBindingConflict("BINDING_REPLAY_INCOMPLETE")

            plan: list[ProjectBindingRecord] = []
            for project_id in sorted(by_project):
                candidates = by_project[project_id]
                if any(
                    row.status == ProjectBindingStatus.RECONCILIATION_REQUIRED.value
                    and row.binding_digest is not None
                    for row in candidates
                ):
                    raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")
                open_attempt = next(
                    (
                        row
                        for row in candidates
                        if row.binding_digest is None
                        and row.status
                        in {
                            ProjectBindingStatus.PENDING.value,
                            ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                        }
                    ),
                    None,
                )
                current = next(
                    (row for row in candidates if row.status == ProjectBindingStatus.CURRENT.value),
                    None,
                )
                selected = open_attempt or current
                if selected is None:
                    raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")
                self._validate_replay_candidate(session, selected)
                self._validate_replay_predecessor(session, selected)
                plan.append(selected)
            return tuple(plan)

    @staticmethod
    def _validate_replay_candidate(session: Session, row: ProjectBindingRecord) -> None:
        project = session.get(Project, row.project_id)
        if (
            project is None
            or project.archived_at is not None
            or project.state != "ready"
            or project.revision != row.project_revision
            or project.relative_path != row.relative_key
        ):
            raise ProjectBindingNotReady(row.project_id)
        host = session.get(RuntimeHostInstallation, row.runtime_host_installation_id)
        if host is None or host.revision != row.runtime_host_installation_revision:
            raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")

    @staticmethod
    def _validate_replay_predecessor(session: Session, row: ProjectBindingRecord) -> None:
        if row.binding_revision == 1:
            if row.previous_binding_revision is not None or row.previous_binding_digest is not None:
                raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")
            return
        if (
            row.previous_binding_revision != row.binding_revision - 1
            or row.previous_binding_digest is None
        ):
            raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")
        predecessor = session.get(
            ProjectBindingRecord, (row.project_id, row.previous_binding_revision)
        )
        if predecessor is None or predecessor.binding_digest != row.previous_binding_digest:
            raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")
        if row.binding_digest is None:
            if predecessor.status != ProjectBindingStatus.CURRENT.value:
                raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")
        elif predecessor.status != ProjectBindingStatus.SUPERSEDED.value:
            raise ProjectBindingConflict("BINDING_INVENTORY_MISMATCH")

    def reserve(
        self,
        *,
        project_id: str,
        expected_project_revision: int,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: int,
        expected_head_revision: int | None,
        expected_head_digest: str | None,
    ) -> ProjectBindingRecord:
        """Persist or replay the exact next registration attempt.

        Callers pass the head they previously observed.  ``None``/``None`` is
        accepted only for the first binding.  An existing byte-equivalent open
        attempt is returned, making process crash recovery deterministic.
        """

        project_key = _identifier(project_id, field="project_id", pattern=_PROJECT_ID)
        project_revision = _positive_integer(
            expected_project_revision, field="expected_project_revision"
        )
        host_id = _identifier(
            runtime_host_installation_id,
            field="runtime_host_installation_id",
            pattern=_HOST_ID,
        )
        host_revision = _positive_integer(
            runtime_host_installation_revision,
            field="runtime_host_installation_revision",
        )
        if (expected_head_revision is None) != (expected_head_digest is None):
            raise ProjectBindingConflict("binding predecessor is incomplete")
        if expected_head_revision is not None:
            predecessor_revision = _positive_integer(
                expected_head_revision, field="expected_head_revision"
            )
            assert expected_head_digest is not None
            predecessor_digest = _digest(expected_head_digest, field="expected_head_digest")
        else:
            predecessor_revision = None
            predecessor_digest = None

        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
            project = session.get(Project, project_key)
            if (
                project is None
                or project.archived_at is not None
                or project.state != "ready"
                or project.revision != project_revision
            ):
                raise ProjectBindingNotReady(project_key)
            try:
                relative_key = validate_relative_key(project.relative_path)
            except WAWControlError as exc:
                raise ProjectBindingNotReady("Project relative key is not WAW-compatible") from exc
            host = session.get(RuntimeHostInstallation, host_id)
            if host is None or host.revision != host_revision:
                raise ProjectBindingConflict("runtime host identity is not current")

            open_attempt = session.scalar(
                select(ProjectBindingRecord).where(
                    ProjectBindingRecord.project_id == project_key,
                    ProjectBindingRecord.binding_digest.is_(None),
                    ProjectBindingRecord.status.in_(
                        (
                            ProjectBindingStatus.PENDING.value,
                            ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                        )
                    ),
                )
            )
            if open_attempt is not None:
                expected = (
                    relative_key,
                    project_revision,
                    predecessor_revision,
                    predecessor_digest,
                    host_id,
                    host_revision,
                )
                observed = (
                    open_attempt.relative_key,
                    open_attempt.project_revision,
                    open_attempt.previous_binding_revision,
                    open_attempt.previous_binding_digest,
                    open_attempt.runtime_host_installation_id,
                    open_attempt.runtime_host_installation_revision,
                )
                if observed != expected:
                    raise ProjectBindingConflict("another binding attempt is pending")
                return open_attempt

            head = session.scalar(
                select(ProjectBindingRecord).where(
                    ProjectBindingRecord.project_id == project_key,
                    ProjectBindingRecord.binding_digest.is_not(None),
                    ProjectBindingRecord.status.in_(
                        (
                            ProjectBindingStatus.CURRENT.value,
                            ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                        )
                    ),
                )
            )
            if head is None:
                if predecessor_revision is not None or predecessor_digest is not None:
                    raise ProjectBindingConflict("binding predecessor does not exist")
                binding_revision = 1
            else:
                if (
                    head.binding_revision != predecessor_revision
                    or head.binding_digest != predecessor_digest
                ):
                    raise ProjectBindingConflict("binding predecessor is stale")
                if relative_key != head.relative_key and project_revision == head.project_revision:
                    raise ProjectBindingConflict(
                        "Project identity changed without a revision advance"
                    )
                if (
                    head.status == ProjectBindingStatus.CURRENT.value
                    and project_revision == head.project_revision
                    and relative_key == head.relative_key
                    and host_id == head.runtime_host_installation_id
                    and host_revision == head.runtime_host_installation_revision
                ):
                    raise ProjectBindingConflict(
                        "current binding requires reconciliation before an unchanged advance"
                    )
                if head.binding_revision >= _MAX_SQLITE_SEQUENCE:
                    raise ProjectBindingConflict("binding revision is exhausted")
                live_workspace = session.scalar(
                    select(AgentWorkspaceSessionRecord.id)
                    .where(
                        AgentWorkspaceSessionRecord.project_id == project_key,
                        AgentWorkspaceSessionRecord.state.not_in(_TERMINAL_WORKSPACE_STATES),
                    )
                    .limit(1)
                )
                if live_workspace is not None:
                    raise ProjectBindingConflict(
                        "Project binding cannot advance while a workspace is non-terminal"
                    )
                binding_revision = head.binding_revision + 1

            row = ProjectBindingRecord(
                project_id=project_key,
                binding_revision=binding_revision,
                relative_key=relative_key,
                project_revision=project_revision,
                binding_digest=None,
                previous_binding_revision=predecessor_revision,
                previous_binding_digest=predecessor_digest,
                runtime_host_installation_id=host_id,
                runtime_host_installation_revision=host_revision,
                status=ProjectBindingStatus.PENDING.value,
                created_at=now,
                updated_at=now,
            )
            try:
                session.add(row)
                session.flush()
            except IntegrityError as exc:
                raise ProjectBindingConflict("binding reservation conflicted") from exc
            return row

    def commit(
        self,
        *,
        project_id: str,
        binding_revision: int,
        expected_project_revision: int,
        binding_digest: str,
    ) -> ProjectBindingRecord:
        """CAS one Runtime-attested attempt to CURRENT, or replay its result."""

        project_key = _identifier(project_id, field="project_id", pattern=_PROJECT_ID)
        revision = _positive_integer(binding_revision, field="binding_revision")
        project_revision = _positive_integer(
            expected_project_revision, field="expected_project_revision"
        )
        digest = _digest(binding_digest, field="binding_digest")
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
            row = session.get(ProjectBindingRecord, (project_key, revision))
            if row is None:
                raise ProjectBindingNotFound(project_key)
            if row.status == ProjectBindingStatus.CURRENT.value:
                if row.binding_digest == digest and row.project_revision == project_revision:
                    return row
                raise ProjectBindingConflict("binding attestation differs from current")
            if (
                row.status
                not in {
                    ProjectBindingStatus.PENDING.value,
                    ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                }
                or row.binding_digest is not None
            ):
                raise ProjectBindingConflict("binding attempt is not committable")
            project = session.get(Project, project_key)
            try:
                current_relative_key = (
                    validate_relative_key(project.relative_path) if project is not None else None
                )
            except WAWControlError as exc:
                raise ProjectBindingNotReady("Project relative key is not WAW-compatible") from exc
            if (
                project is None
                or project.archived_at is not None
                or project.state != "ready"
                or project.revision != project_revision
                or current_relative_key != row.relative_key
                or row.project_revision != project_revision
            ):
                raise ProjectBindingNotReady(project_key)
            host = session.get(RuntimeHostInstallation, row.runtime_host_installation_id)
            if host is None or host.revision != row.runtime_host_installation_revision:
                raise ProjectBindingConflict("runtime host identity changed")

            predecessor: ProjectBindingRecord | None = None
            if row.previous_binding_revision is not None:
                predecessor = session.get(
                    ProjectBindingRecord,
                    (project_key, row.previous_binding_revision),
                )
                if (
                    predecessor is None
                    or predecessor.binding_digest != row.previous_binding_digest
                    or predecessor.status
                    not in {
                        ProjectBindingStatus.CURRENT.value,
                        ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                    }
                ):
                    raise ProjectBindingConflict("binding predecessor changed")
            else:
                existing_head = session.scalar(
                    select(ProjectBindingRecord).where(
                        ProjectBindingRecord.project_id == project_key,
                        ProjectBindingRecord.binding_digest.is_not(None),
                        ProjectBindingRecord.status.in_(
                            (
                                ProjectBindingStatus.CURRENT.value,
                                ProjectBindingStatus.RECONCILIATION_REQUIRED.value,
                            )
                        ),
                    )
                )
                if existing_head is not None:
                    raise ProjectBindingConflict("first binding already has a head")

            if predecessor is not None:
                predecessor.status = ProjectBindingStatus.SUPERSEDED.value
                predecessor.updated_at = now
            row.binding_digest = digest
            row.status = ProjectBindingStatus.CURRENT.value
            row.updated_at = now
            session.flush()
            return row

    def require_reconciliation(
        self,
        *,
        project_id: str,
        binding_revision: int,
        expected_binding_digest: str | None,
    ) -> ProjectBindingRecord:
        """CAS an open attempt or current head to a fail-closed state."""

        project_key = _identifier(project_id, field="project_id", pattern=_PROJECT_ID)
        revision = _positive_integer(binding_revision, field="binding_revision")
        digest = (
            None
            if expected_binding_digest is None
            else _digest(expected_binding_digest, field="expected_binding_digest")
        )
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            now = self._database.transaction_now(session)
            row = session.get(ProjectBindingRecord, (project_key, revision))
            if row is None:
                raise ProjectBindingNotFound(project_key)
            if row.binding_digest != digest:
                raise ProjectBindingConflict("binding reconciliation target is stale")
            if row.status == ProjectBindingStatus.RECONCILIATION_REQUIRED.value:
                if row.binding_digest is not None:
                    self._fence_binding_workspaces(session, row, now)
                return row
            if row.status not in {
                ProjectBindingStatus.PENDING.value,
                ProjectBindingStatus.CURRENT.value,
            }:
                raise ProjectBindingConflict("binding is not reconcilable")
            row.status = ProjectBindingStatus.RECONCILIATION_REQUIRED.value
            row.updated_at = now
            if row.binding_digest is not None:
                self._fence_binding_workspaces(session, row, now)
            session.flush()
            return row

    @staticmethod
    def _fence_binding_workspaces(
        session: Session, binding: ProjectBindingRecord, now: datetime
    ) -> None:
        """Atomically retire live workspace rows bound to a reconciled head."""

        assert binding.binding_digest is not None
        already_fenced = (
            (AgentWorkspaceSessionRecord.state == "UNKNOWN")
            & (AgentWorkspaceSessionRecord.reconciliation_state == "reconciliation_required")
            & (AgentWorkspaceSessionRecord.failure_code == "BINDING_RECONCILIATION_REQUIRED")
        )
        predicate = (
            AgentWorkspaceSessionRecord.project_id == binding.project_id,
            AgentWorkspaceSessionRecord.binding_revision == binding.binding_revision,
            AgentWorkspaceSessionRecord.binding_digest == binding.binding_digest,
            AgentWorkspaceSessionRecord.state.not_in(
                _RECONCILIATION_FENCE_EXCLUDED_WORKSPACE_STATES
            ),
            ~already_fenced,
        )
        exhausted = session.scalar(
            select(AgentWorkspaceSessionRecord.id)
            .where(*predicate, AgentWorkspaceSessionRecord.revision >= _MAX_SQLITE_SEQUENCE)
            .limit(1)
        )
        if exhausted is not None:
            raise ProjectBindingConflict("workspace revision is exhausted")
        session.execute(
            update(AgentWorkspaceSessionRecord)
            .where(*predicate)
            .values(
                state="UNKNOWN",
                reconciliation_state="reconciliation_required",
                failure_code="BINDING_RECONCILIATION_REQUIRED",
                revision=AgentWorkspaceSessionRecord.revision + 1,
                updated_at=now,
                last_seen_at=now,
            )
        )


__all__ = [
    "ProjectBindingConflict",
    "ProjectBindingError",
    "ProjectBindingNotFound",
    "ProjectBindingNotReady",
    "ProjectBindingService",
    "ProjectBindingStatus",
    "MAX_REPLAY_BINDINGS",
]
