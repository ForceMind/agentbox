from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from agentbox_core.errors import (
    InvalidSession,
    NavigationLabelConflict,
    NavigationLabelLimitExceeded,
    NavigationLabelNameTaken,
    NavigationLabelNotFound,
    NavigationLabelValidationError,
    ProjectLabelConflict,
    ProjectNotFound,
)
from agentbox_core.models import (
    AdminUser,
    AuditEvent,
    Project,
    ProjectLabelAssignment,
    ProjectLabelSet,
)
from agentbox_core.navigation_labels import NavigationLabelService
from agentbox_core.services import ControlPlaneServices, build_services
from conftest import migrate_database
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def seed(services: ControlPlaneServices) -> tuple[str, str]:
    project = services.projects.reserve(name="Label fixture", slug=None, source_type="empty")
    with services.database.transaction() as session:
        admin = session.scalar(select(AdminUser).where(AdminUser.is_active.is_(True)))
        assert admin is not None
        return admin.id, project.id


def test_catalog_assignment_cas_rename_delete_and_audit(
    initialized_services: ControlPlaneServices,
) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    labels = services.navigation_labels
    assert labels.list_catalog(admin_id) == ()
    assert labels.get_project(admin_id, project_id).revision == 0

    first = labels.create(admin_id, name="  Team\tReview  ", color="sky", request_id="req_create")
    assert first.name == "Team Review" and first.revision == 1
    with pytest.raises(NavigationLabelNameTaken):
        labels.create(admin_id, name="team review", color="red", request_id="req_duplicate")
    assigned = labels.set_project(
        admin_id, project_id, first.id, assigned=True, expected_revision=0, request_id="req_assign"
    )
    assert assigned.revision == 1 and [value.id for value in assigned.labels] == [first.id]
    same = labels.set_project(
        admin_id, project_id, first.id, assigned=True, expected_revision=1, request_id="req_same"
    )
    assert same == assigned
    with pytest.raises(ProjectLabelConflict):
        labels.set_project(
            admin_id,
            project_id,
            first.id,
            assigned=False,
            expected_revision=0,
            request_id="req_stale",
        )

    edited = labels.update(
        admin_id,
        first.id,
        name="TEAM REVIEW",
        color="red",
        expected_revision=1,
        request_id="req_edit",
    )
    assert edited.id == first.id and edited.revision == 2 and edited.color == "red"
    projected = labels.get_project(admin_id, project_id)
    assert projected.revision == 1 and projected.labels[0].name == "TEAM REVIEW"
    with pytest.raises(NavigationLabelConflict):
        labels.update(
            admin_id,
            first.id,
            name="stale",
            color="blue",
            expected_revision=1,
            request_id="req_stale_edit",
        )
    second = labels.create(admin_id, name="Other", color="blue", request_id="req_second")
    with pytest.raises(NavigationLabelNameTaken):
        labels.update(
            admin_id,
            first.id,
            name="other",
            color="pink",
            expected_revision=2,
            request_id="req_collision",
        )
    assert (
        next(item for item in labels.list_catalog(admin_id) if item.id == first.id).color == "red"
    )
    assert labels.inspect_delete(admin_id, first.id) == 1
    assert (
        labels.delete(
            admin_id,
            first.id,
            expected_revision=2,
            expected_affected_project_count=1,
            request_id="req_delete",
        )
        == 1
    )
    cleared = labels.get_project(admin_id, project_id)
    assert cleared.revision == 2 and cleared.labels == ()
    with pytest.raises(NavigationLabelNotFound):
        labels.set_project(
            admin_id,
            project_id,
            first.id,
            assigned=True,
            expected_revision=2,
            request_id="req_old_id",
        )
    assert labels.list_catalog(admin_id) == (second,)
    with services.database.transaction() as session:
        assert session.get(ProjectLabelSet, (admin_id, project_id)) is not None
        assert session.scalars(select(ProjectLabelAssignment)).all() == []
        events = tuple(
            session.scalars(select(AuditEvent).where(AuditEvent.action.like("%.label.%")))
        )
        assert events
        assert all("Team Review" not in str(event.metadata_json) for event in events)


def test_invalid_inputs_unknown_project_and_audit_rollback(
    initialized_services: ControlPlaneServices, clock: Any
) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    with pytest.raises(NavigationLabelValidationError):
        services.navigation_labels.create(
            admin_id, name="\u202ehidden", color="sky", request_id="req_invalid"
        )
    with pytest.raises(NavigationLabelValidationError):
        services.navigation_labels.create(
            admin_id, name="okay", color="unknown", request_id="req_color"
        )
    label = services.navigation_labels.create(
        admin_id, name="Design", color="violet", request_id="req_good"
    )
    with pytest.raises(ProjectNotFound):
        services.navigation_labels.set_project(
            admin_id,
            "prj_" + "f" * 32,
            label.id,
            assigned=True,
            expected_revision=0,
            request_id="req_missing",
        )

    class BrokenAudit:
        def record(self, *args: Any, **kwargs: Any) -> object:
            raise RuntimeError("audit unavailable")

    broken = NavigationLabelService(services.database, clock, BrokenAudit())
    with pytest.raises(RuntimeError, match="audit unavailable"):
        broken.set_project(
            admin_id,
            project_id,
            label.id,
            assigned=True,
            expected_revision=0,
            request_id="req_broken_audit",
        )
    assert services.navigation_labels.get_project(admin_id, project_id).revision == 0


def test_labels_survive_service_restart(settings: Any, clock: Any) -> None:
    migrate_database(settings.database_url)
    first = build_services(settings, clock=clock)
    try:
        first.admin.initialize("maintainer", "a sufficiently long passphrase")
        admin_id, project_id = seed(first)
        label = first.navigation_labels.create(
            admin_id, name="Persistent", color="teal", request_id="req_create"
        )
        first.navigation_labels.set_project(
            admin_id,
            project_id,
            label.id,
            assigned=True,
            expected_revision=0,
            request_id="req_assign",
        )
    finally:
        first.database.close()
    second = build_services(settings, clock=clock)
    try:
        observed = second.navigation_labels.get_project(admin_id, project_id)
        assert observed.revision == 1 and observed.labels[0].id == label.id
    finally:
        second.database.close()


def test_two_clients_cannot_assign_from_one_project_revision(
    initialized_services: ControlPlaneServices,
) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    first = services.navigation_labels.create(
        admin_id, name="First", color="blue", request_id="req_first"
    )
    second = services.navigation_labels.create(
        admin_id, name="Second", color="pink", request_id="req_second"
    )
    barrier = Barrier(2)

    def attempt(label_id: str) -> str:
        barrier.wait(timeout=5)
        try:
            services.navigation_labels.set_project(
                admin_id,
                project_id,
                label_id,
                assigned=True,
                expected_revision=0,
                request_id=f"req_{label_id}",
            )
            return "succeeded"
        except ProjectLabelConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (first.id, second.id)))
    assert sorted(outcomes) == ["conflict", "succeeded"]
    observed = services.navigation_labels.get_project(admin_id, project_id)
    assert observed.revision == 1 and len(observed.labels) == 1


def test_two_clients_cannot_create_one_normalized_name(
    initialized_services: ControlPlaneServices,
) -> None:
    services = initialized_services
    admin_id, _project_id = seed(services)
    barrier = Barrier(2)

    def attempt(item: tuple[str, int]) -> str:
        name, index = item
        barrier.wait(timeout=5)
        try:
            services.navigation_labels.create(
                admin_id, name=name, color="sky", request_id=f"req_label_race_{index}"
            )
            return "succeeded"
        except NavigationLabelNameTaken:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (("Team Review", 0), ("TEAM  REVIEW", 1))))
    assert sorted(outcomes) == ["conflict", "succeeded"]
    assert len(services.navigation_labels.list_catalog(admin_id)) == 1


def test_catalog_and_assignment_capacity_fail_without_partial_write(
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agentbox_core.navigation_labels as module

    services = initialized_services
    admin_id, project_id = seed(services)
    first = services.navigation_labels.create(
        admin_id, name="First", color="sky", request_id="req_first"
    )
    monkeypatch.setattr(module, "_MAX_CATALOG", 1)
    with pytest.raises(NavigationLabelLimitExceeded):
        services.navigation_labels.create(
            admin_id, name="Second", color="red", request_id="req_over_catalog"
        )
    assert services.navigation_labels.list_catalog(admin_id) == (first,)
    monkeypatch.setattr(module, "_MAX_CATALOG", 128)
    second = services.navigation_labels.create(
        admin_id, name="Second", color="red", request_id="req_second"
    )
    monkeypatch.setattr(module, "_MAX_ASSIGNED", 1)
    services.navigation_labels.set_project(
        admin_id,
        project_id,
        first.id,
        assigned=True,
        expected_revision=0,
        request_id="req_assign_first",
    )
    with pytest.raises(NavigationLabelLimitExceeded):
        services.navigation_labels.set_project(
            admin_id,
            project_id,
            second.id,
            assigned=True,
            expected_revision=1,
            request_id="req_over_assigned",
        )
    observed = services.navigation_labels.get_project(admin_id, project_id)
    assert observed.revision == 1 and [value.id for value in observed.labels] == [first.id]


def test_label_scope_archived_project_and_foreign_key_fence(
    initialized_services: ControlPlaneServices, clock: Any
) -> None:
    services = initialized_services
    old_admin, project_id = seed(services)
    old_label = services.navigation_labels.create(
        old_admin, name="Old", color="red", request_id="req_old"
    )
    new_admin = "adm_" + "b" * 32
    with services.database.transaction() as session:
        old_user = session.get(AdminUser, old_admin)
        project = session.get(Project, project_id)
        assert old_user is not None and project is not None
        old_user.is_active = False
        project.state = "archived"
        project.archived_at = clock.now()
        session.add(
            AdminUser(
                id=new_admin,
                username="next-maintainer",
                username_normalized="next-maintainer",
                password_hash="fixture-hash",
                is_active=True,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
    with pytest.raises(InvalidSession):
        services.navigation_labels.list_catalog(old_admin)
    assert services.navigation_labels.list_catalog(new_admin) == ()
    with pytest.raises(NavigationLabelNotFound):
        services.navigation_labels.set_project(
            new_admin,
            project_id,
            old_label.id,
            assigned=True,
            expected_revision=0,
            request_id="req_cross_admin",
        )
    new_label = services.navigation_labels.create(
        new_admin, name="Archived", color="teal", request_id="req_new"
    )
    result = services.navigation_labels.set_project(
        new_admin,
        project_id,
        new_label.id,
        assigned=True,
        expected_revision=0,
        request_id="req_archived",
    )
    assert result.revision == 1 and result.labels[0].id == new_label.id
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(
            ProjectLabelAssignment(
                admin_user_id=new_admin,
                project_id=project_id,
                label_id="lbl_" + "f" * 32,
                position=1,
            )
        )
        session.flush()


def test_physical_project_delete_cascades_assignments_but_keeps_catalog(
    initialized_services: ControlPlaneServices,
) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    label = services.navigation_labels.create(
        admin_id, name="Keep", color="amber", request_id="req_create"
    )
    services.navigation_labels.set_project(
        admin_id,
        project_id,
        label.id,
        assigned=True,
        expected_revision=0,
        request_id="req_assign",
    )
    with services.database.transaction() as session:
        project = session.get(Project, project_id)
        assert project is not None
        session.delete(project)
    with services.database.transaction() as session:
        assert session.get(ProjectLabelSet, (admin_id, project_id)) is None
        assert session.scalars(select(ProjectLabelAssignment)).all() == []
    assert services.navigation_labels.list_catalog(admin_id) == (label,)


def test_delete_audit_failure_rolls_back_catalog_and_project_revision(
    initialized_services: ControlPlaneServices, clock: Any
) -> None:
    services = initialized_services
    admin_id, project_id = seed(services)
    label = services.navigation_labels.create(
        admin_id, name="Retained", color="orange", request_id="req_create"
    )
    services.navigation_labels.set_project(
        admin_id,
        project_id,
        label.id,
        assigned=True,
        expected_revision=0,
        request_id="req_assign",
    )

    class BrokenAudit:
        def record(self, *args: Any, **kwargs: Any) -> object:
            raise RuntimeError("audit unavailable")

    broken = NavigationLabelService(services.database, clock, BrokenAudit())
    with pytest.raises(RuntimeError, match="audit unavailable"):
        broken.delete(
            admin_id,
            label.id,
            expected_revision=1,
            expected_affected_project_count=1,
            request_id="req_delete",
        )
    assert services.navigation_labels.list_catalog(admin_id) == (label,)
    observed = services.navigation_labels.get_project(admin_id, project_id)
    assert observed.revision == 1 and observed.labels[0].id == label.id


def test_delete_impact_count_is_rechecked_atomically(
    initialized_services: ControlPlaneServices,
) -> None:
    services = initialized_services
    admin_id, first_project = seed(services)
    second_project = services.projects.reserve(
        name="Second label target", slug=None, source_type="empty"
    )
    label = services.navigation_labels.create(
        admin_id, name="Shared", color="pink", request_id="req_create"
    )
    services.navigation_labels.set_project(
        admin_id,
        first_project,
        label.id,
        assigned=True,
        expected_revision=0,
        request_id="req_first",
    )
    assert services.navigation_labels.inspect_delete(admin_id, label.id) == 1
    services.navigation_labels.set_project(
        admin_id,
        second_project.id,
        label.id,
        assigned=True,
        expected_revision=0,
        request_id="req_second",
    )
    with pytest.raises(NavigationLabelConflict):
        services.navigation_labels.delete(
            admin_id,
            label.id,
            expected_revision=1,
            expected_affected_project_count=1,
            request_id="req_stale_count",
        )
    assert services.navigation_labels.inspect_delete(admin_id, label.id) == 2
    assert services.navigation_labels.get_project(admin_id, first_project).revision == 1
    assert services.navigation_labels.get_project(admin_id, second_project.id).revision == 1
    assert (
        services.navigation_labels.delete(
            admin_id,
            label.id,
            expected_revision=1,
            expected_affected_project_count=2,
            request_id="req_confirmed_delete",
        )
        == 2
    )
