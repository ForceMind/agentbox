from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from agentbox_core.database import Database
from agentbox_core.errors import ProjectConflict, ProjectNotFound
from agentbox_core.models import Project
from agentbox_core.projects import ProjectService
from agentbox_core.waw import AgentType
from agentbox_core.waw_models import ProjectBindingRecord, RuntimeHostInstallation
from agentbox_core.waw_project_bindings import (
    ProjectBindingConflict,
    ProjectBindingNotReady,
    ProjectBindingService,
    ProjectBindingStatus,
)
from agentbox_core.waw_sessions import WorkspaceSessionNotReady, WorkspaceSessionService
from agentbox_protocol.waw_control import WAWControlError, validate_relative_key

PROJECT_ID = "prj_" + "1" * 32
HOST_ID = "wri_" + "2" * 32
DIGEST_1 = "a" * 64
DIGEST_2 = "b" * 64


def _seed(settings: Any, clock: Any) -> tuple[Database, ProjectBindingService]:
    database = Database(settings, clock)
    database.engine.dispose()
    import agentbox_core.waw_models  # noqa: F401
    from agentbox_core.models import Base

    Base.metadata.create_all(database.engine)
    now = clock.now()
    with database.transaction() as session:
        session.add(
            Project(
                id=PROJECT_ID,
                slug="demo",
                display_name="Demo",
                relative_path="demo",
                source_type="empty",
                state="ready",
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            RuntimeHostInstallation(
                id=HOST_ID,
                revision=1,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
            )
        )
    return database, ProjectBindingService(database, clock)


def _reserve(
    service: ProjectBindingService,
    *,
    project_revision: int = 1,
    predecessor_revision: int | None = None,
    predecessor_digest: str | None = None,
) -> ProjectBindingRecord:
    return service.reserve(
        project_id=PROJECT_ID,
        expected_project_revision=project_revision,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        expected_head_revision=predecessor_revision,
        expected_head_digest=predecessor_digest,
    )


def test_first_reservation_and_commit_are_exactly_idempotent(settings: Any, clock: Any) -> None:
    _database, service = _seed(settings, clock)

    first = _reserve(service)
    replay = _reserve(service)
    assert first.binding_revision == replay.binding_revision == 1
    assert first.status == replay.status == ProjectBindingStatus.PENDING.value
    assert first.binding_digest is None
    assert first.previous_binding_revision is None
    assert first.previous_binding_digest is None

    current = service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    replayed = service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    assert current.status == replayed.status == ProjectBindingStatus.CURRENT.value
    assert service.get_head(PROJECT_ID).binding_digest == DIGEST_1
    assert tuple(
        (row.project_id, row.binding_revision, row.binding_digest) for row in service.list_current()
    ) == (
        (PROJECT_ID, 1, DIGEST_1),
    )
    with pytest.raises(ProjectBindingConflict, match="differs"):
        service.commit(
            project_id=PROJECT_ID,
            binding_revision=1,
            expected_project_revision=1,
            binding_digest=DIGEST_2,
        )


def test_workspace_first_generation_is_derived_from_current_ledger(
    settings: Any, clock: Any
) -> None:
    database, service = _seed(settings, clock)
    sessions = WorkspaceSessionService(database, clock)
    with pytest.raises(WorkspaceSessionNotReady, match="binding is not current"):
        sessions.create_from_current_binding(
            project_id=PROJECT_ID,
            agent_type=AgentType.CLAUDE,
            authorization_scope="admin",
        )
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )

    workspace = sessions.create_from_current_binding(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
    )
    assert (workspace.binding_revision, workspace.binding_digest) == (1, DIGEST_1)
    assert workspace.executable_fingerprint is None
    assert workspace.executable_evidence_state == "UNOBSERVED"


def test_reserve_rejects_stale_project_and_predecessor(settings: Any, clock: Any) -> None:
    database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    with database.transaction() as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.revision = 2

    with pytest.raises(ProjectBindingNotReady):
        _reserve(
            service,
            project_revision=1,
            predecessor_revision=1,
            predecessor_digest=DIGEST_1,
        )
    with pytest.raises(ProjectBindingConflict, match="predecessor is stale"):
        _reserve(
            service,
            project_revision=2,
            predecessor_revision=1,
            predecessor_digest=DIGEST_2,
        )


def test_project_state_mutations_increment_revision_with_cas_and_fence_commit(
    settings: Any, clock: Any
) -> None:
    database, bindings = _seed(settings, clock)
    projects = ProjectService(database, clock)
    attempt = _reserve(bindings)

    projects.mark_error(PROJECT_ID, expected_revision=1)
    errored = projects.get(PROJECT_ID)
    assert (errored.state, errored.revision) == ("error", 2)
    projects.mark_error(PROJECT_ID, expected_revision=2)
    assert projects.get(PROJECT_ID).revision == 2
    with pytest.raises(ProjectBindingNotReady):
        bindings.commit(
            project_id=PROJECT_ID,
            binding_revision=attempt.binding_revision,
            expected_project_revision=1,
            binding_digest=DIGEST_1,
        )
    with pytest.raises(ProjectConflict):
        projects.mark_ready(PROJECT_ID, expected_revision=1)

    projects.mark_ready(PROJECT_ID, expected_revision=2)
    ready = projects.get(PROJECT_ID)
    assert (ready.state, ready.revision) == ("ready", 3)
    projects.mark_ready(PROJECT_ID, expected_revision=3)
    assert projects.get(PROJECT_ID).revision == 3


def test_project_revision_change_atomically_fences_nonterminal_workspace(
    settings: Any, clock: Any
) -> None:
    database, _bindings = _seed(settings, clock)
    sessions = WorkspaceSessionService(database, clock)
    workspace = sessions.create(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest=DIGEST_1,
    )

    ProjectService(database, clock).mark_error(PROJECT_ID, expected_revision=1)

    fenced = sessions.get(workspace.id)
    assert (
        fenced.state,
        fenced.reconciliation_state,
        fenced.failure_code,
        fenced.revision,
    ) == ("UNKNOWN", "reconciliation_required", "PROJECT_BINDING_STALE", 2)


def test_project_reservation_discard_uses_revision_cas(settings: Any, clock: Any) -> None:
    database, _bindings = _seed(settings, clock)
    projects = ProjectService(database, clock)
    reserved = projects.reserve(name="Disposable", slug="disposable", source_type="empty")
    assert reserved.revision == 1
    with pytest.raises(ProjectConflict):
        projects.discard_reservation(reserved.id, expected_revision=2)
    projects.discard_reservation(reserved.id, expected_revision=1)
    with pytest.raises(ProjectNotFound):
        projects.get(reserved.id)


@pytest.mark.parametrize(
    "relative_key",
    ("Å", "bad/path", "bad\\path", ".", "..", " leading", "trailing ", "bad\x00key"),
)
def test_ledger_and_control_codec_share_relative_key_rejection(
    settings: Any, clock: Any, relative_key: str
) -> None:
    database, bindings = _seed(settings, clock)
    with pytest.raises(WAWControlError):
        validate_relative_key(relative_key)
    with database.transaction() as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.relative_path = relative_key
    with pytest.raises(ProjectBindingNotReady, match="WAW-compatible"):
        _reserve(bindings)


def test_next_revision_commits_only_over_exact_head(settings: Any, clock: Any) -> None:
    database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    with database.transaction() as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.revision = 2

    second = _reserve(
        service,
        project_revision=2,
        predecessor_revision=1,
        predecessor_digest=DIGEST_1,
    )
    assert (second.binding_revision, second.previous_binding_digest) == (2, DIGEST_1)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=2,
        expected_project_revision=2,
        binding_digest=DIGEST_2,
    )
    assert service.get(PROJECT_ID, 1).status == ProjectBindingStatus.SUPERSEDED.value
    assert service.get_head(PROJECT_ID).binding_revision == 2
    assert [(row.project_id, row.binding_revision) for row in service.list_replay_plan()] == [
        (PROJECT_ID, 2)
    ]


def test_unchanged_current_head_cannot_be_advanced_without_reconciliation(
    settings: Any, clock: Any
) -> None:
    _database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    with pytest.raises(ProjectBindingConflict, match="requires reconciliation"):
        _reserve(
            service,
            predecessor_revision=1,
            predecessor_digest=DIGEST_1,
        )
    service.require_reconciliation(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_binding_digest=DIGEST_1,
    )
    assert (
        _reserve(
            service,
            predecessor_revision=1,
            predecessor_digest=DIGEST_1,
        ).binding_revision
        == 2
    )


def test_nonterminal_workspace_fences_binding_advance(settings: Any, clock: Any) -> None:
    database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    WorkspaceSessionService(database, clock).create(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest=DIGEST_1,
    )
    with database.transaction() as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.revision = 2
    with pytest.raises(ProjectBindingConflict, match="non-terminal"):
        _reserve(
            service,
            project_revision=2,
            predecessor_revision=1,
            predecessor_digest=DIGEST_1,
        )


def test_reconciliation_preserves_replayable_attempt(settings: Any, clock: Any) -> None:
    _database, service = _seed(settings, clock)
    attempt = _reserve(service)
    reconciled = service.require_reconciliation(
        project_id=PROJECT_ID,
        binding_revision=attempt.binding_revision,
        expected_binding_digest=None,
    )
    assert reconciled.status == ProjectBindingStatus.RECONCILIATION_REQUIRED.value
    assert _reserve(service).binding_revision == attempt.binding_revision
    committed = service.commit(
        project_id=PROJECT_ID,
        binding_revision=attempt.binding_revision,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    assert committed.status == ProjectBindingStatus.CURRENT.value


def test_reconciling_current_binding_atomically_fences_matching_workspace(
    settings: Any, clock: Any
) -> None:
    database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    workspace = WorkspaceSessionService(database, clock).create(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest=DIGEST_1,
    )

    service.require_reconciliation(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_binding_digest=DIGEST_1,
    )

    fenced = WorkspaceSessionService(database, clock).get(workspace.id)
    assert (
        fenced.state,
        fenced.reconciliation_state,
        fenced.failure_code,
        fenced.revision,
    ) == ("UNKNOWN", "reconciliation_required", "BINDING_RECONCILIATION_REQUIRED", 2)


def test_reconciling_current_binding_does_not_interrupt_exact_stop(
    settings: Any, clock: Any
) -> None:
    database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    sessions = WorkspaceSessionService(database, clock)
    workspace = sessions.create(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest=DIGEST_1,
    )
    operation = sessions.begin_stop(workspace.id, expected_revision=workspace.revision)

    service.require_reconciliation(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_binding_digest=DIGEST_1,
    )

    assert sessions.get(workspace.id).state == "STOPPING"
    completed = sessions.complete_stop(operation.id, result="STOPPED")
    assert completed.result == "STOPPED"


def test_repeated_current_binding_reconciliation_does_not_rebump_workspace(
    settings: Any, clock: Any
) -> None:
    database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    sessions = WorkspaceSessionService(database, clock)
    workspace = sessions.create(
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest=DIGEST_1,
    )
    service.require_reconciliation(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_binding_digest=DIGEST_1,
    )
    first = sessions.get(workspace.id)
    clock.advance(seconds=1)

    service.require_reconciliation(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_binding_digest=DIGEST_1,
    )

    second = sessions.get(workspace.id)
    assert (
        second.revision,
        second.updated_at,
        second.last_seen_at,
    ) == (
        first.revision,
        first.updated_at,
        first.last_seen_at,
    )


def test_replay_plan_is_project_sorted_and_prefers_open_attempt(settings: Any, clock: Any) -> None:
    database, service = _seed(settings, clock)
    second_project_id = "prj_" + "0" * 32
    with database.transaction() as session:
        now = clock.now()
        session.add(
            Project(
                id=second_project_id,
                slug="before-demo",
                display_name="Before Demo",
                relative_path="before-demo",
                source_type="empty",
                state="ready",
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    with database.transaction() as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.revision = 2
    _reserve(
        service,
        project_revision=2,
        predecessor_revision=1,
        predecessor_digest=DIGEST_1,
    )
    service.reserve(
        project_id=second_project_id,
        expected_project_revision=1,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        expected_head_revision=None,
        expected_head_digest=None,
    )

    plan = service.list_replay_plan()
    assert [(row.project_id, row.binding_revision) for row in plan] == [
        (second_project_id, 1),
        (PROJECT_ID, 2),
    ]


def test_replay_plan_blocks_digest_known_reconciliation(settings: Any, clock: Any) -> None:
    _database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    service.require_reconciliation(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_binding_digest=DIGEST_1,
    )
    with pytest.raises(ProjectBindingConflict, match="BINDING_INVENTORY_MISMATCH"):
        service.list_replay_plan()


def test_replay_plan_revalidates_project_revision(settings: Any, clock: Any) -> None:
    database, service = _seed(settings, clock)
    _reserve(service)
    service.commit(
        project_id=PROJECT_ID,
        binding_revision=1,
        expected_project_revision=1,
        binding_digest=DIGEST_1,
    )
    with database.transaction() as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.revision = 2
    with pytest.raises(ProjectBindingNotReady):
        service.list_replay_plan()


def test_replay_plan_is_bounded(settings: Any, clock: Any) -> None:
    database, service = _seed(settings, clock)
    for index in range(257):
        project_id = f"prj_{index:032x}"
        with database.transaction() as session:
            now = clock.now()
            session.add(
                Project(
                    id=project_id,
                    slug=f"project-{index}",
                    display_name=f"Project {index}",
                    relative_path=f"project-{index}",
                    source_type="empty",
                    state="ready",
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        service.reserve(
            project_id=project_id,
            expected_project_revision=1,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision=1,
            expected_head_revision=None,
            expected_head_digest=None,
        )
    with pytest.raises(ProjectBindingConflict, match="BINDING_REPLAY_INCOMPLETE"):
        service.list_replay_plan()


def test_concurrent_first_reservation_converges_on_one_attempt(settings: Any, clock: Any) -> None:
    database, service = _seed(settings, clock)
    barrier = Barrier(2)

    def reserve_together(_index: int) -> int:
        barrier.wait()
        return _reserve(service).binding_revision

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            revisions = tuple(executor.map(reserve_together, range(2)))
        assert revisions == (1, 1)
        with database.transaction() as session:
            assert session.query(ProjectBindingRecord).count() == 1
    finally:
        database.close()
