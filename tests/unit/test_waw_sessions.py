from __future__ import annotations

import pytest
from agentbox_core.database import Database
from agentbox_core.models import Project
from agentbox_core.waw import AgentType, WAWDomainError, WorkspaceState, workspace_id
from agentbox_core.waw_models import RuntimeHostInstallation
from agentbox_core.waw_sessions import (
    WorkspaceSessionConflict,
    WorkspaceSessionNotReady,
    WorkspaceSessionService,
)


def _seed(
    settings, clock, *, project_state: str = "ready"
) -> tuple[Database, WorkspaceSessionService, str, str]:
    database = Database(settings, clock)
    database.engine.dispose()
    # The migration fixture is intentionally avoided here: this unit test only
    # exercises the WAW tables and uses the same SQLite metadata contracts.
    import agentbox_core.waw_models  # noqa: F401
    from agentbox_core.models import Base

    Base.metadata.create_all(database.engine)
    project_id = "prj_" + "1" * 32
    host_id = "wri_" + "2" * 32
    now = clock.now()
    with database.transaction() as session:
        session.add(
            Project(
                id=project_id,
                slug="demo",
                display_name="Demo",
                relative_path="demo",
                source_type="empty",
                state=project_state,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            RuntimeHostInstallation(
                id=host_id,
                revision=1,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
            )
        )
    return database, WorkspaceSessionService(database, clock), project_id, host_id


def _create(service: WorkspaceSessionService, project_id: str, host_id: str):
    return service.create(
        project_id=project_id,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="a" * 64,
        executable_fingerprint="b" * 64,
    )


def test_create_is_deterministic_and_metadata_only(settings, clock) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    assert row.id == workspace_id(project_id, AgentType.CLAUDE)
    assert row.generation == 1
    assert row.state == WorkspaceState.STARTING.value
    assert row.runtime_marker.startswith("waw-v1:wri_")
    assert not hasattr(row, "terminal")


def test_duplicate_and_non_ready_project_are_rejected(settings, clock) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    _create(service, project_id, host_id)
    with pytest.raises(WorkspaceSessionConflict):
        _create(service, project_id, host_id)
    project_id2 = "prj_" + "3" * 32
    host_id2 = "wri_" + "4" * 32
    now = clock.now()
    with database.transaction() as session:
        session.add(
            Project(
                id=project_id2,
                slug="creating",
                display_name="Creating",
                relative_path="creating",
                source_type="empty",
                state="creating",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            RuntimeHostInstallation(
                id=host_id2,
                revision=1,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
            )
        )
    with pytest.raises(WorkspaceSessionNotReady):
        _create(service, project_id2, host_id2)


def test_transition_uses_domain_and_compare_and_swap(settings, clock) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    updated = service.transition(row.id, expected_revision=1, state=WorkspaceState.RUNNING)
    assert updated.revision == 2
    with pytest.raises(WorkspaceSessionConflict):
        service.transition(row.id, expected_revision=1, state=WorkspaceState.STOPPING)
    with pytest.raises(WAWDomainError):
        service.transition(row.id, expected_revision=2, state=WorkspaceState.STOPPED)


def test_begin_start_fences_generation_and_marker(settings, clock) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    row = service.transition(row.id, expected_revision=1, state=WorkspaceState.RUNNING)
    row = service.transition(row.id, expected_revision=2, state=WorkspaceState.EXITED)
    restarted = service.begin_start(row.id, expected_revision=3)
    assert restarted.generation == 2
    assert restarted.revision == 4
    assert restarted.state == WorkspaceState.STARTING.value
    assert restarted.runtime_marker != row.runtime_marker
