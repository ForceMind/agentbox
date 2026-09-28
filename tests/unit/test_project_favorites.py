from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from typing import Any

import pytest
from agentbox_core.errors import (
    InvalidSession,
    ProjectFavoriteConflict,
    ProjectFavoriteLimitExceeded,
    ProjectFavoriteValidationError,
    ProjectNotFound,
)
from agentbox_core.models import AdminUser, AuditEvent, ProjectFavorite
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol import ProjectFavoriteData, ProjectFavoriteSetRequest
from conftest import migrate_database
from pydantic import ValidationError
from sqlalchemy import select


def seed(services: ControlPlaneServices) -> tuple[str, str]:
    project = services.projects.reserve(name="Favorite fixture", slug=None, source_type="empty")
    with services.database.transaction() as session:
        admin = session.scalar(select(AdminUser).where(AdminUser.is_active.is_(True)))
        assert admin is not None
        return admin.id, project.id


def test_favorite_revision_cas_noop_and_audit(initialized_services: ControlPlaneServices) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    favorites = services.favorites
    assert favorites.list(admin_id) == ()

    absent = favorites.set(
        admin_id, project_id, favorite=False, expected_revision=0, request_id="req_absent"
    )
    assert (absent.favorite, absent.revision, absent.updated_at) == (False, 0, None)
    created = favorites.set(
        admin_id, project_id, favorite=True, expected_revision=0, request_id="req_create"
    )
    assert created.favorite and created.revision == 1
    assert isinstance(created.updated_at, datetime)
    same = favorites.set(
        admin_id, project_id, favorite=True, expected_revision=1, request_id="req_same"
    )
    assert same == created
    removed = favorites.set(
        admin_id, project_id, favorite=False, expected_revision=1, request_id="req_remove"
    )
    assert not removed.favorite and removed.revision == 2
    assert favorites.list(admin_id) == (removed,)
    with pytest.raises(ProjectFavoriteConflict):
        favorites.set(
            admin_id, project_id, favorite=True, expected_revision=1, request_id="req_stale"
        )
    with services.database.transaction() as session:
        rows = tuple(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == "project.favorite.set")
                .order_by(AuditEvent.created_at)
            )
        )
        assert len(rows) == 4
        assert all(row.target_id == project_id for row in rows)
        assert all(row.metadata_json["project_id"] == project_id for row in rows)
        assert all("Favorite fixture" not in str(row.metadata_json) for row in rows)
        removed_audit = next(row for row in rows if row.request_id == "req_remove")
        assert removed_audit.metadata_json["favorite"] is False
        assert removed_audit.metadata_json["revision"] == 2


def test_favorite_rejects_invalid_input_unknown_project_and_inactive_admin(
    initialized_services: ControlPlaneServices,
) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    with pytest.raises(ProjectFavoriteValidationError):
        services.favorites.set(
            admin_id,
            project_id,
            favorite=True,
            expected_revision=True,
            request_id="req_invalid",
        )
    with pytest.raises(ProjectFavoriteValidationError):
        services.favorites.set(
            admin_id,
            project_id,
            favorite="true",  # type: ignore[arg-type]
            expected_revision=0,
            request_id="req_invalid",
        )
    with pytest.raises(ProjectNotFound):
        services.favorites.set(
            admin_id,
            "prj_" + "f" * 32,
            favorite=True,
            expected_revision=0,
            request_id="req_missing",
        )
    with services.database.transaction() as session:
        admin = session.get(AdminUser, admin_id)
        assert admin is not None
        admin.is_active = False
    with pytest.raises(InvalidSession):
        services.favorites.list(admin_id)
    with pytest.raises(InvalidSession):
        services.favorites.set(
            admin_id, project_id, favorite=True, expected_revision=0, request_id="req_revoked"
        )


def test_two_clients_cannot_both_create_revision_one(
    initialized_services: ControlPlaneServices,
) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    barrier = Barrier(2)

    def attempt(index: int) -> tuple[str, int | None]:
        barrier.wait(timeout=5)
        try:
            result = services.favorites.set(
                admin_id,
                project_id,
                favorite=True,
                expected_revision=0,
                request_id=f"req_race_{index}",
            )
            return "succeeded", result.revision
        except ProjectFavoriteConflict:
            return "conflict", None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sorted(outcomes) == [("conflict", None), ("succeeded", 1)]
    with services.database.transaction() as session:
        assert session.get(ProjectFavorite, (admin_id, project_id)) is not None


def test_favorite_rows_survive_service_restart(settings: Any, clock: Any) -> None:
    from agentbox_core.services import build_services

    migrate_database(settings.database_url)
    first = build_services(settings, clock=clock)
    try:
        first.admin.initialize("maintainer", "a sufficiently long passphrase")
        admin_id, project_id = seed(first)
        first.favorites.set(
            admin_id, project_id, favorite=True, expected_revision=0, request_id="req_restart"
        )
    finally:
        first.database.close()
    second = build_services(settings, clock=clock)
    try:
        observed = [
            (row.project_id, row.favorite, row.revision) for row in second.favorites.list(admin_id)
        ]
        assert observed == [(project_id, True, 1)]
    finally:
        second.database.close()


def test_favorite_audit_failure_rolls_back_in_the_same_transaction(
    initialized_services: ControlPlaneServices, clock: Any
) -> None:
    from agentbox_core.favorites import ProjectFavoriteService

    class BrokenAudit:
        def record(self, *args: Any, **kwargs: Any) -> object:
            raise RuntimeError("audit unavailable")

    services = initialized_services
    admin_id, project_id = seed(services)
    broken = ProjectFavoriteService(services.database, clock, BrokenAudit())
    with pytest.raises(RuntimeError, match="audit unavailable"):
        broken.set(
            admin_id, project_id, favorite=True, expected_revision=0, request_id="req_broken_audit"
        )
    assert services.favorites.list(admin_id) == ()


def test_favorite_is_per_admin_and_archived_project_remains_a_valid_preference(
    initialized_services: ControlPlaneServices, clock: Any
) -> None:
    from agentbox_core.models import Project

    services = initialized_services
    old_admin_id, project_id = seed(services)
    services.favorites.set(
        old_admin_id, project_id, favorite=True, expected_revision=0, request_id="req_old_admin"
    )
    new_admin_id = "adm_" + "b" * 32
    with services.database.transaction() as session:
        old_admin = session.get(AdminUser, old_admin_id)
        project = session.get(Project, project_id)
        assert old_admin is not None and project is not None
        old_admin.is_active = False
        project.state = "archived"
        project.archived_at = clock.now()
        session.flush()
        session.add(
            AdminUser(
                id=new_admin_id,
                username="next-maintainer",
                username_normalized="next-maintainer",
                password_hash="fixture-hash",
                is_active=True,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
    assert services.favorites.list(new_admin_id) == ()
    with pytest.raises(InvalidSession):
        services.favorites.list(old_admin_id)
    archived = services.favorites.set(
        new_admin_id, project_id, favorite=True, expected_revision=0, request_id="req_archived"
    )
    assert archived.favorite and archived.revision == 1


def test_favorite_protocol_rejects_inconsistent_or_extra_metadata() -> None:
    project_id = "prj_" + "a" * 32
    current = datetime.now(UTC)
    assert (
        ProjectFavoriteData(
            project_id=project_id, favorite=False, revision=0, updated_at=None
        ).revision
        == 0
    )
    assert ProjectFavoriteData(
        project_id=project_id, favorite=True, revision=1, updated_at=current
    ).favorite
    for value in (
        {"project_id": project_id, "favorite": True, "revision": 0, "updated_at": None},
        {"project_id": project_id, "favorite": True, "revision": 1, "updated_at": None},
        {
            "project_id": project_id,
            "favorite": False,
            "revision": 1,
            "updated_at": current,
            "path": "/etc/passwd",
        },
    ):
        with pytest.raises(ValidationError):
            ProjectFavoriteData.model_validate(value)
    with pytest.raises(ValidationError):
        ProjectFavoriteSetRequest.model_validate({"favorite": "true", "expected_revision": 0})


def test_favorite_capacity_fails_without_partial_success(
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agentbox_core.favorites as favorite_module

    services = initialized_services
    admin_id, first_id = seed(services)
    second = services.projects.reserve(name="Another favorite", slug=None, source_type="empty")
    monkeypatch.setattr(favorite_module, "_MAX_RECORDS", 1)
    services.favorites.set(
        admin_id, first_id, favorite=True, expected_revision=0, request_id="req_first"
    )
    with pytest.raises(ProjectFavoriteLimitExceeded):
        services.favorites.set(
            admin_id,
            second.id,
            favorite=True,
            expected_revision=0,
            request_id="req_over_limit",
        )
    assert [row.project_id for row in services.favorites.list(admin_id)] == [first_id]
