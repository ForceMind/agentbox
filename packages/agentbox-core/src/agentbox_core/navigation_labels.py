"""Transactional per-admin label catalog and formal Project assignments.

Name/color and atomic catalog behaviors adapt getpaseo/paseo sources at
30178c4f58b67f8472901356e1484022bd835de0 (Apache-2.0).
Copyright (c) 2025-present Mohamed Boudra. AgentBox owns this schema and API.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.errors import (
    InvalidSession,
    NavigationLabelConflict,
    NavigationLabelLimitExceeded,
    NavigationLabelNameTaken,
    NavigationLabelNotFound,
    NavigationLabelValidationError,
    ProjectLabelConflict,
    ProjectNotFound,
    WorkspaceLabelConflict,
)
from agentbox_core.models import (
    AdminUser,
    NavigationLabel,
    Project,
    ProjectLabelAssignment,
    ProjectLabelSet,
    WorkspaceLabelAssignment,
    WorkspaceLabelSet,
)
from agentbox_core.utc import aware_utc
from agentbox_core.waw import AgentType, workspace_id

_ADMIN_ID = re.compile(r"adm_[0-9a-f]{32}\Z")
_PROJECT_ID = re.compile(r"prj_[0-9a-f]{32}\Z")
_LABEL_ID = re.compile(r"lbl_[0-9a-f]{32}\Z")
_COLORS = frozenset(
    {"violet", "sky", "emerald", "orange", "pink", "indigo", "teal", "red", "amber", "blue"}
)
_MAX_REVISION = 2**53 - 1
_MAX_CATALOG = 128
_MAX_ASSIGNED = 32
_MAX_PROJECT_SETS = 10_000
_MAX_WORKSPACE_SETS = 20_000


class LabelAudit(Protocol):
    def record(
        self,
        session: Session,
        *,
        actor_type: str,
        actor_id: str | None,
        action: str,
        result: str,
        request_id: str | None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object: ...


@dataclass(frozen=True)
class NavigationLabelState:
    id: str
    name: str
    color: str
    revision: int
    updated_at: datetime


@dataclass(frozen=True)
class ProjectLabelSetState:
    project_id: str
    labels: tuple[NavigationLabelState, ...]
    revision: int
    updated_at: datetime | None


@dataclass(frozen=True)
class WorkspaceLabelSetState:
    workspace_id: str
    project_id: str
    agent_type: str
    labels: tuple[NavigationLabelState, ...]
    revision: int
    updated_at: datetime | None


@dataclass(frozen=True)
class LabelDeleteImpact:
    affected_project_count: int
    affected_workspace_count: int


class NavigationLabelService:
    def __init__(self, database: Database, clock: Clock, audit: LabelAudit) -> None:
        self._database = database
        self._clock = clock
        self._audit = audit

    @staticmethod
    def _admin_id(value: str) -> str:
        if type(value) is not str or _ADMIN_ID.fullmatch(value) is None:
            raise InvalidSession()
        return value

    @staticmethod
    def _project_id(value: str) -> str:
        if type(value) is not str or _PROJECT_ID.fullmatch(value) is None:
            raise NavigationLabelValidationError()
        return value

    @staticmethod
    def _label_id(value: str) -> str:
        if type(value) is not str or _LABEL_ID.fullmatch(value) is None:
            raise NavigationLabelValidationError()
        return value

    @staticmethod
    def _agent_type(value: str) -> AgentType:
        if type(value) is not str or value not in ("claude", "codex"):
            raise NavigationLabelValidationError()
        return AgentType(value)

    @staticmethod
    def _revision(value: int) -> int:
        if type(value) is not int or not 0 <= value <= _MAX_REVISION:
            raise NavigationLabelValidationError()
        return value

    @staticmethod
    def _name(value: str) -> tuple[str, str]:
        if type(value) is not str or unicodedata.normalize("NFC", value) != value:
            raise NavigationLabelValidationError()
        if any(unicodedata.category(char).startswith("C") and not char.isspace() for char in value):
            raise NavigationLabelValidationError()
        name = re.sub(r"\s+", " ", value).strip()
        if not 1 <= len(name) <= 64 or len(name.encode("utf-8")) > 128:
            raise NavigationLabelValidationError()
        key = name.lower()
        if len(key) > 128 or len(key.encode("utf-8")) > 128:
            raise NavigationLabelValidationError()
        return name, key

    @staticmethod
    def _color(value: str) -> str:
        if type(value) is not str or value not in _COLORS:
            raise NavigationLabelValidationError()
        return value

    @staticmethod
    def _state(row: NavigationLabel) -> NavigationLabelState:
        return NavigationLabelState(
            row.id, row.name, row.color, row.revision, aware_utc(row.updated_at)
        )

    @staticmethod
    def _require_admin(session: Session, admin_id: str) -> None:
        user = session.get(AdminUser, admin_id)
        if user is None or not user.is_active:
            raise InvalidSession()

    @staticmethod
    def _require_project(session: Session, project_id: str) -> None:
        if session.get(Project, project_id) is None:
            raise ProjectNotFound()

    def list_catalog(self, admin_user_id: str) -> tuple[NavigationLabelState, ...]:
        admin_id = self._admin_id(admin_user_id)
        with self._database.transaction() as session:
            self._require_admin(session, admin_id)
            rows = tuple(
                session.scalars(
                    select(NavigationLabel)
                    .where(NavigationLabel.admin_user_id == admin_id)
                    .order_by(NavigationLabel.name_key)
                    .limit(_MAX_CATALOG + 1)
                )
            )
            if len(rows) > _MAX_CATALOG:
                raise NavigationLabelLimitExceeded()
            return tuple(self._state(row) for row in rows)

    def create(
        self, admin_user_id: str, *, name: str, color: str, request_id: str | None
    ) -> NavigationLabelState:
        admin_id = self._admin_id(admin_user_id)
        normalized, key = self._name(name)
        selected_color = self._color(color)
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._require_admin(session, admin_id)
            if (
                session.scalar(
                    select(NavigationLabel.id).where(
                        NavigationLabel.admin_user_id == admin_id, NavigationLabel.name_key == key
                    )
                )
                is not None
            ):
                raise NavigationLabelNameTaken()
            count = session.scalar(
                select(func.count())
                .select_from(NavigationLabel)
                .where(NavigationLabel.admin_user_id == admin_id)
            )
            if count is None or count >= _MAX_CATALOG:
                raise NavigationLabelLimitExceeded()
            now = self._clock.now()
            row = NavigationLabel(
                id=f"lbl_{secrets.token_hex(16)}",
                admin_user_id=admin_id,
                name=normalized,
                name_key=key,
                color=selected_color,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            self._audit.record(
                session,
                actor_type="admin",
                actor_id=admin_id,
                action="navigation.label.create",
                result="succeeded",
                request_id=request_id,
                target_type="navigation_label",
                target_id=row.id,
                metadata={"label_id": row.id, "revision": 1},
            )
            return self._state(row)

    def update(
        self,
        admin_user_id: str,
        label_id: str,
        *,
        name: str,
        color: str,
        expected_revision: int,
        request_id: str | None,
    ) -> NavigationLabelState:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._label_id(label_id)
        normalized, key = self._name(name)
        selected_color = self._color(color)
        expected = self._revision(expected_revision)
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._require_admin(session, admin_id)
            row = session.get(NavigationLabel, target_id)
            if row is None or row.admin_user_id != admin_id:
                raise NavigationLabelNotFound()
            if row.revision != expected:
                raise NavigationLabelConflict()
            if (
                key != row.name_key
                and session.scalar(
                    select(NavigationLabel.id).where(
                        NavigationLabel.admin_user_id == admin_id, NavigationLabel.name_key == key
                    )
                )
                is not None
            ):
                raise NavigationLabelNameTaken()
            if row.name != normalized or row.color != selected_color:
                if row.revision >= _MAX_REVISION:
                    raise NavigationLabelConflict()
                row.name = normalized
                row.name_key = key
                row.color = selected_color
                row.revision += 1
                row.updated_at = self._clock.now()
                session.flush()
            result = self._state(row)
            self._audit.record(
                session,
                actor_type="admin",
                actor_id=admin_id,
                action="navigation.label.update",
                result="succeeded",
                request_id=request_id,
                target_type="navigation_label",
                target_id=target_id,
                metadata={"label_id": target_id, "revision": result.revision},
            )
            return result

    def get_project(self, admin_user_id: str, project_id: str) -> ProjectLabelSetState:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._project_id(project_id)
        with self._database.transaction() as session:
            self._require_admin(session, admin_id)
            self._require_project(session, target_id)
            return self._project_state(session, admin_id, target_id)

    def set_project(
        self,
        admin_user_id: str,
        project_id: str,
        label_id: str,
        *,
        assigned: bool,
        expected_revision: int,
        request_id: str | None,
    ) -> ProjectLabelSetState:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._project_id(project_id)
        label_key = self._label_id(label_id)
        expected = self._revision(expected_revision)
        if type(assigned) is not bool:
            raise NavigationLabelValidationError()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._require_admin(session, admin_id)
            self._require_project(session, target_id)
            definition = session.get(NavigationLabel, label_key)
            if definition is None or definition.admin_user_id != admin_id:
                raise NavigationLabelNotFound()
            label_set = session.get(ProjectLabelSet, (admin_id, target_id))
            revision = label_set.revision if label_set is not None else 0
            if revision != expected:
                raise ProjectLabelConflict()
            assignment = session.get(ProjectLabelAssignment, (admin_id, target_id, label_key))
            changed = assigned != (assignment is not None)
            if changed:
                if label_set is not None and label_set.revision >= _MAX_REVISION:
                    raise ProjectLabelConflict()
                now = self._clock.now()
                if label_set is None:
                    label_set = ProjectLabelSet(
                        admin_user_id=admin_id, project_id=target_id, revision=1, updated_at=now
                    )
                    session.add(label_set)
                    session.flush()
                else:
                    label_set.revision += 1
                    label_set.updated_at = now
                if assigned:
                    count = session.scalar(
                        select(func.count())
                        .select_from(ProjectLabelAssignment)
                        .where(
                            ProjectLabelAssignment.admin_user_id == admin_id,
                            ProjectLabelAssignment.project_id == target_id,
                        )
                    )
                    if count is None or count >= _MAX_ASSIGNED:
                        raise NavigationLabelLimitExceeded()
                    last_position = session.scalar(
                        select(func.max(ProjectLabelAssignment.position)).where(
                            ProjectLabelAssignment.admin_user_id == admin_id,
                            ProjectLabelAssignment.project_id == target_id,
                        )
                    )
                    session.add(
                        ProjectLabelAssignment(
                            admin_user_id=admin_id,
                            project_id=target_id,
                            label_id=label_key,
                            position=0 if last_position is None else last_position + 1,
                        )
                    )
                else:
                    assert assignment is not None
                    session.delete(assignment)
                session.flush()
            result = self._project_state(session, admin_id, target_id)
            self._audit.record(
                session,
                actor_type="admin",
                actor_id=admin_id,
                action="project.label.set",
                result="succeeded",
                request_id=request_id,
                target_type="project",
                target_id=target_id,
                metadata={
                    "project_id": target_id,
                    "label_id": label_key,
                    "assigned": assigned,
                    "revision": result.revision,
                },
            )
            return result

    def _project_state(
        self, session: Session, admin_id: str, project_id: str
    ) -> ProjectLabelSetState:
        label_set = session.get(ProjectLabelSet, (admin_id, project_id))
        if label_set is None:
            return ProjectLabelSetState(project_id, (), 0, None)
        assignments = tuple(
            session.scalars(
                select(ProjectLabelAssignment)
                .where(
                    ProjectLabelAssignment.admin_user_id == admin_id,
                    ProjectLabelAssignment.project_id == project_id,
                )
                .order_by(ProjectLabelAssignment.position, ProjectLabelAssignment.label_id)
                .limit(_MAX_ASSIGNED + 1)
            )
        )
        if len(assignments) > _MAX_ASSIGNED:
            raise NavigationLabelLimitExceeded()
        labels: list[NavigationLabelState] = []
        for assigned in assignments:
            definition = session.get(NavigationLabel, assigned.label_id)
            if definition is None or definition.admin_user_id != admin_id:
                raise ProjectLabelConflict()
            labels.append(self._state(definition))
        return ProjectLabelSetState(
            project_id, tuple(labels), label_set.revision, aware_utc(label_set.updated_at)
        )

    def get_workspace(
        self, admin_user_id: str, project_id: str, agent_type: str
    ) -> WorkspaceLabelSetState:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._project_id(project_id)
        agent = self._agent_type(agent_type)
        with self._database.transaction() as session:
            self._require_admin(session, admin_id)
            self._require_project(session, target_id)
            return self._workspace_state(session, admin_id, target_id, agent)

    def set_workspace(
        self,
        admin_user_id: str,
        project_id: str,
        agent_type: str,
        label_id: str,
        *,
        assigned: bool,
        expected_revision: int,
        request_id: str | None,
    ) -> WorkspaceLabelSetState:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._project_id(project_id)
        agent = self._agent_type(agent_type)
        label_key = self._label_id(label_id)
        expected = self._revision(expected_revision)
        if type(assigned) is not bool:
            raise NavigationLabelValidationError()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._require_admin(session, admin_id)
            self._require_project(session, target_id)
            definition = session.get(NavigationLabel, label_key)
            if definition is None or definition.admin_user_id != admin_id:
                raise NavigationLabelNotFound()
            key = (admin_id, target_id, agent.value)
            label_set = session.get(WorkspaceLabelSet, key)
            revision = label_set.revision if label_set is not None else 0
            if revision != expected:
                raise WorkspaceLabelConflict()
            assignment = session.get(WorkspaceLabelAssignment, (*key, label_key))
            if assigned != (assignment is not None):
                if label_set is not None and label_set.revision >= _MAX_REVISION:
                    raise WorkspaceLabelConflict()
                now = self._clock.now()
                if label_set is None:
                    label_set = WorkspaceLabelSet(
                        admin_user_id=admin_id,
                        project_id=target_id,
                        agent_type=agent.value,
                        revision=1,
                        updated_at=now,
                    )
                    session.add(label_set)
                    session.flush()
                else:
                    label_set.revision += 1
                    label_set.updated_at = now
                if assigned:
                    count = session.scalar(
                        select(func.count())
                        .select_from(WorkspaceLabelAssignment)
                        .where(
                            WorkspaceLabelAssignment.admin_user_id == admin_id,
                            WorkspaceLabelAssignment.project_id == target_id,
                            WorkspaceLabelAssignment.agent_type == agent.value,
                        )
                    )
                    if count is None or count >= _MAX_ASSIGNED:
                        raise NavigationLabelLimitExceeded()
                    last_position = session.scalar(
                        select(func.max(WorkspaceLabelAssignment.position)).where(
                            WorkspaceLabelAssignment.admin_user_id == admin_id,
                            WorkspaceLabelAssignment.project_id == target_id,
                            WorkspaceLabelAssignment.agent_type == agent.value,
                        )
                    )
                    session.add(
                        WorkspaceLabelAssignment(
                            admin_user_id=admin_id,
                            project_id=target_id,
                            agent_type=agent.value,
                            label_id=label_key,
                            position=0 if last_position is None else last_position + 1,
                        )
                    )
                else:
                    assert assignment is not None
                    session.delete(assignment)
                session.flush()
            result = self._workspace_state(session, admin_id, target_id, agent)
            self._audit.record(
                session,
                actor_type="admin",
                actor_id=admin_id,
                action="workspace.label.set",
                result="succeeded",
                request_id=request_id,
                target_type="workspace",
                target_id=result.workspace_id,
                metadata={
                    "workspace_id": result.workspace_id,
                    "project_id": target_id,
                    "agent_type": agent.value,
                    "label_id": label_key,
                    "assigned": assigned,
                    "revision": result.revision,
                },
            )
            return result

    def _workspace_state(
        self, session: Session, admin_id: str, project_id: str, agent: AgentType
    ) -> WorkspaceLabelSetState:
        label_set = session.get(WorkspaceLabelSet, (admin_id, project_id, agent.value))
        identity = workspace_id(project_id, agent)
        if label_set is None:
            return WorkspaceLabelSetState(identity, project_id, agent.value, (), 0, None)
        assignments = tuple(
            session.scalars(
                select(WorkspaceLabelAssignment)
                .where(
                    WorkspaceLabelAssignment.admin_user_id == admin_id,
                    WorkspaceLabelAssignment.project_id == project_id,
                    WorkspaceLabelAssignment.agent_type == agent.value,
                )
                .order_by(WorkspaceLabelAssignment.position, WorkspaceLabelAssignment.label_id)
                .limit(_MAX_ASSIGNED + 1)
            )
        )
        if len(assignments) > _MAX_ASSIGNED:
            raise NavigationLabelLimitExceeded()
        labels: list[NavigationLabelState] = []
        for assigned in assignments:
            definition = session.get(NavigationLabel, assigned.label_id)
            if definition is None or definition.admin_user_id != admin_id:
                raise WorkspaceLabelConflict()
            labels.append(self._state(definition))
        return WorkspaceLabelSetState(
            identity,
            project_id,
            agent.value,
            tuple(labels),
            label_set.revision,
            aware_utc(label_set.updated_at),
        )

    def delete(
        self,
        admin_user_id: str,
        label_id: str,
        *,
        expected_revision: int,
        expected_affected_project_count: int,
        expected_affected_workspace_count: int = 0,
        request_id: str | None,
    ) -> LabelDeleteImpact:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._label_id(label_id)
        expected = self._revision(expected_revision)
        if (
            type(expected_affected_project_count) is not int
            or not 0 <= expected_affected_project_count <= _MAX_PROJECT_SETS
            or type(expected_affected_workspace_count) is not int
            or not 0 <= expected_affected_workspace_count <= _MAX_WORKSPACE_SETS
        ):
            raise NavigationLabelValidationError()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._require_admin(session, admin_id)
            row = session.get(NavigationLabel, target_id)
            if row is None or row.admin_user_id != admin_id:
                raise NavigationLabelNotFound()
            if row.revision != expected:
                raise NavigationLabelConflict()
            project_ids = tuple(
                session.scalars(
                    select(ProjectLabelAssignment.project_id)
                    .where(
                        ProjectLabelAssignment.admin_user_id == admin_id,
                        ProjectLabelAssignment.label_id == target_id,
                    )
                    .limit(_MAX_PROJECT_SETS + 1)
                )
            )
            if len(project_ids) > _MAX_PROJECT_SETS:
                raise NavigationLabelLimitExceeded()
            if len(project_ids) != expected_affected_project_count:
                raise NavigationLabelConflict()
            workspace_keys = tuple(
                session.execute(
                    select(WorkspaceLabelAssignment.project_id, WorkspaceLabelAssignment.agent_type)
                    .where(
                        WorkspaceLabelAssignment.admin_user_id == admin_id,
                        WorkspaceLabelAssignment.label_id == target_id,
                    )
                    .limit(_MAX_WORKSPACE_SETS + 1)
                )
            )
            if len(workspace_keys) > _MAX_WORKSPACE_SETS:
                raise NavigationLabelLimitExceeded()
            if len(workspace_keys) != expected_affected_workspace_count:
                raise NavigationLabelConflict()
            for project_id in project_ids:
                label_set = session.get(ProjectLabelSet, (admin_id, project_id))
                if label_set is None or label_set.revision >= _MAX_REVISION:
                    raise ProjectLabelConflict()
                label_set.revision += 1
                label_set.updated_at = self._clock.now()
            for project_id, agent_type in workspace_keys:
                workspace_set = session.get(WorkspaceLabelSet, (admin_id, project_id, agent_type))
                if workspace_set is None or workspace_set.revision >= _MAX_REVISION:
                    raise WorkspaceLabelConflict()
                workspace_set.revision += 1
                workspace_set.updated_at = self._clock.now()
            session.delete(row)
            session.flush()
            self._audit.record(
                session,
                actor_type="admin",
                actor_id=admin_id,
                action="navigation.label.delete",
                result="succeeded",
                request_id=request_id,
                target_type="navigation_label",
                target_id=target_id,
                metadata={
                    "label_id": target_id,
                    "affected_project_count": len(project_ids),
                    "affected_workspace_count": len(workspace_keys),
                },
            )
            return LabelDeleteImpact(len(project_ids), len(workspace_keys))

    def inspect_delete(self, admin_user_id: str, label_id: str) -> LabelDeleteImpact:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._label_id(label_id)
        with self._database.transaction() as session:
            self._require_admin(session, admin_id)
            row = session.get(NavigationLabel, target_id)
            if row is None or row.admin_user_id != admin_id:
                raise NavigationLabelNotFound()
            count = session.scalar(
                select(func.count())
                .select_from(ProjectLabelAssignment)
                .where(
                    ProjectLabelAssignment.admin_user_id == admin_id,
                    ProjectLabelAssignment.label_id == target_id,
                )
            )
            if count is None or count > _MAX_PROJECT_SETS:
                raise NavigationLabelLimitExceeded()
            workspace_count = session.scalar(
                select(func.count())
                .select_from(WorkspaceLabelAssignment)
                .where(
                    WorkspaceLabelAssignment.admin_user_id == admin_id,
                    WorkspaceLabelAssignment.label_id == target_id,
                )
            )
            if workspace_count is None or workspace_count > _MAX_WORKSPACE_SETS:
                raise NavigationLabelLimitExceeded()
            return LabelDeleteImpact(count, workspace_count)


__all__ = [
    "NavigationLabelService",
    "NavigationLabelState",
    "ProjectLabelSetState",
    "WorkspaceLabelSetState",
    "LabelDeleteImpact",
]
