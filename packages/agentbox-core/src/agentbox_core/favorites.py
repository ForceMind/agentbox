"""Transactional, per-admin Project favorite metadata with revision CAS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.errors import (
    InvalidSession,
    ProjectFavoriteConflict,
    ProjectFavoriteLimitExceeded,
    ProjectFavoriteValidationError,
    ProjectNotFound,
)
from agentbox_core.models import AdminUser, Project, ProjectFavorite
from agentbox_core.utc import aware_utc

_ADMIN_ID = re.compile(r"adm_[0-9a-f]{32}\Z")
_PROJECT_ID = re.compile(r"prj_[0-9a-f]{32}\Z")
_MAX_REVISION = 2**63 - 1
_MAX_RECORDS = 10_000


class FavoriteAudit(Protocol):
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
class ProjectFavoriteState:
    project_id: str
    favorite: bool
    revision: int
    updated_at: datetime | None


class ProjectFavoriteService:
    def __init__(self, database: Database, clock: Clock, audit: FavoriteAudit) -> None:
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
            raise ProjectFavoriteValidationError()
        return value

    @staticmethod
    def _state(row: ProjectFavorite) -> ProjectFavoriteState:
        return ProjectFavoriteState(
            row.project_id, row.favorite, row.revision, aware_utc(row.updated_at)
        )

    def list(self, admin_user_id: str) -> tuple[ProjectFavoriteState, ...]:
        admin_id = self._admin_id(admin_user_id)
        with self._database.transaction() as session:
            user = session.get(AdminUser, admin_id)
            if user is None or not user.is_active:
                raise InvalidSession()
            rows = tuple(
                session.scalars(
                    select(ProjectFavorite)
                    .where(ProjectFavorite.admin_user_id == admin_id)
                    .order_by(ProjectFavorite.project_id)
                    .limit(_MAX_RECORDS + 1)
                )
            )
            if len(rows) > _MAX_RECORDS:
                raise ProjectFavoriteLimitExceeded()
            return tuple(self._state(row) for row in rows)

    def set(
        self,
        admin_user_id: str,
        project_id: str,
        *,
        favorite: bool,
        expected_revision: int,
        request_id: str | None,
    ) -> ProjectFavoriteState:
        admin_id = self._admin_id(admin_user_id)
        target_id = self._project_id(project_id)
        if (
            type(favorite) is not bool
            or type(expected_revision) is not int
            or not 0 <= expected_revision <= _MAX_REVISION
        ):
            raise ProjectFavoriteValidationError()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            user = session.get(AdminUser, admin_id)
            if user is None or not user.is_active:
                raise InvalidSession()
            if session.get(Project, target_id) is None:
                raise ProjectNotFound()
            row = session.get(ProjectFavorite, (admin_id, target_id))
            current_revision = row.revision if row is not None else 0
            if expected_revision != current_revision:
                raise ProjectFavoriteConflict()
            if row is None and not favorite:
                result = ProjectFavoriteState(target_id, False, 0, None)
            elif row is None:
                count = session.scalar(
                    select(func.count())
                    .select_from(ProjectFavorite)
                    .where(ProjectFavorite.admin_user_id == admin_id)
                )
                if count is None or count >= _MAX_RECORDS:
                    raise ProjectFavoriteLimitExceeded()
                row = ProjectFavorite(
                    admin_user_id=admin_id,
                    project_id=target_id,
                    favorite=True,
                    revision=1,
                    updated_at=self._clock.now(),
                )
                session.add(row)
                session.flush()
                result = self._state(row)
            elif row.favorite == favorite:
                result = self._state(row)
            else:
                if row.revision >= _MAX_REVISION:
                    raise ProjectFavoriteConflict()
                row.favorite = favorite
                row.revision += 1
                row.updated_at = self._clock.now()
                session.flush()
                result = self._state(row)
            self._audit.record(
                session,
                actor_type="admin",
                actor_id=admin_id,
                action="project.favorite.set",
                result="succeeded",
                request_id=request_id,
                target_type="project",
                target_id=target_id,
                metadata={
                    "project_id": target_id,
                    "favorite": result.favorite,
                    "revision": result.revision,
                },
            )
            return result


__all__ = ["ProjectFavoriteService", "ProjectFavoriteState"]
