from __future__ import annotations

from typing import Any

import pytest
from agentbox_core.database import Database
from agentbox_core.models import Project
from agentbox_core.waw import AgentType, WAWDomainError, WorkspaceState, workspace_id
from agentbox_core.waw_models import (
    AgentWorkspaceSessionRecord,
    RuntimeHostInstallation,
    WorkspaceStopOperationRecord,
)
from agentbox_core.waw_sessions import (
    ExecutableEvidenceState,
    RuntimeEpochBindingError,
    RuntimeEpochClassification,
    WorkspaceExecutableEvidenceRequired,
    WorkspaceSessionConflict,
    WorkspaceSessionNotReady,
    WorkspaceSessionService,
)


def _seed(
    settings: Any, clock: Any, *, project_state: str = "ready"
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


def _create(
    service: WorkspaceSessionService, project_id: str, host_id: str
) -> AgentWorkspaceSessionRecord:
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


def test_create_is_deterministic_and_metadata_only(settings: Any, clock: Any) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    assert row.id == workspace_id(project_id, AgentType.CLAUDE)
    assert row.generation == 1
    assert row.state == WorkspaceState.STARTING.value
    assert row.runtime_marker.startswith("waw-v1:wri_")
    assert row.executable_evidence_state == ExecutableEvidenceState.STALE.value
    assert not service.executable_evidence_is_current(row, runtime_epoch="1")
    assert not hasattr(row, "terminal")


def test_executable_evidence_is_exact_generation_epoch_cas(settings: Any, clock: Any) -> None:
    _database, service, project_id, host_id = _seed(settings, clock)
    row = service.create(
        project_id=project_id,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="a" * 64,
    )
    assert row.executable_fingerprint is None
    assert row.executable_evidence_state == ExecutableEvidenceState.UNOBSERVED.value
    with pytest.raises(WorkspaceExecutableEvidenceRequired):
        service.require_current_executable_evidence(row, runtime_epoch="7")

    verified = service.record_executable_evidence(
        row.id,
        expected_revision=row.revision,
        generation=row.generation,
        runtime_epoch="7",
        executable_fingerprint="b" * 64,
    )
    assert service.executable_evidence_is_current(verified, runtime_epoch="7")
    service.require_current_executable_evidence(verified, runtime_epoch="7")
    assert not service.executable_evidence_is_current(verified, runtime_epoch="8")
    replay = service.record_executable_evidence(
        row.id,
        expected_revision=row.revision,
        generation=row.generation,
        runtime_epoch="7",
        executable_fingerprint="b" * 64,
    )
    assert replay.revision == verified.revision
    with pytest.raises(WorkspaceSessionConflict):
        service.record_executable_evidence(
            row.id,
            expected_revision=verified.revision,
            generation=row.generation,
            runtime_epoch="7",
            executable_fingerprint="c" * 64,
        )


def test_runtime_epoch_advance_stales_verified_executable_evidence(
    settings: Any, clock: Any
) -> None:
    _database, service, project_id, host_id = _seed(settings, clock)
    row = service.create(
        project_id=project_id,
        agent_type=AgentType.CLAUDE,
        authorization_scope="admin",
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="a" * 64,
    )
    row = service.record_executable_evidence(
        row.id,
        expected_revision=row.revision,
        generation=1,
        runtime_epoch="7",
        executable_fingerprint="b" * 64,
    )
    service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="7",
    )
    service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="8",
    )
    stale = service.get(row.id)
    assert stale.executable_evidence_state == ExecutableEvidenceState.STALE.value
    assert not service.executable_evidence_is_current(stale, runtime_epoch="8")


def test_runtime_epoch_first_and_same_bind_preserve_workspace(settings: Any, clock: Any) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)

    first = service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="18446744073709551615",
    )
    same = service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="18446744073709551615",
    )

    assert first is RuntimeEpochClassification.FIRST_BIND
    assert same is RuntimeEpochClassification.API_RESTART
    preserved = service.get(row.id)
    assert (preserved.state, preserved.revision, preserved.failure_code) == (
        WorkspaceState.STARTING.value,
        1,
        None,
    )
    with database.transaction() as session:
        host = session.get(RuntimeHostInstallation, host_id)
        assert host is not None
        assert host.last_runtime_epoch == "18446744073709551615"


def test_runtime_epoch_advance_atomically_fences_only_nonterminal_workspaces(
    settings: Any, clock: Any
) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    active = _create(service, project_id, host_id)
    active = service.transition(active.id, expected_revision=1, state=WorkspaceState.RUNNING)
    pending_stop = service.begin_stop(active.id, expected_revision=active.revision)
    active = service.get(active.id)
    terminal = service.create(
        project_id=project_id,
        agent_type=AgentType.CODEX,
        authorization_scope="admin",
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="c" * 64,
        executable_fingerprint="d" * 64,
    )
    terminal = service.transition(terminal.id, expected_revision=1, state=WorkspaceState.RUNNING)
    terminal = service.transition(terminal.id, expected_revision=2, state=WorkspaceState.EXITED)
    service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="7",
    )

    result = service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="8",
    )

    assert result is RuntimeEpochClassification.RUNTIME_RESTART
    fenced = service.get(active.id)
    assert (fenced.state, fenced.reconciliation_state, fenced.failure_code) == (
        WorkspaceState.UNKNOWN.value,
        "reconciliation_required",
        "RUNTIME_RESTART",
    )
    assert fenced.revision == active.revision + 1
    unchanged = service.get(terminal.id)
    assert (unchanged.state, unchanged.revision, unchanged.failure_code) == (
        WorkspaceState.EXITED.value,
        terminal.revision,
        terminal.failure_code,
    )
    with database.transaction() as session:
        host = session.get(RuntimeHostInstallation, host_id)
        assert host is not None and host.last_runtime_epoch == "8"
        stop = session.get(WorkspaceStopOperationRecord, pending_stop.id)
        assert stop is not None
        assert (stop.result, stop.failure_code) == (
            "RECONCILIATION_REQUIRED",
            "RUNTIME_RESTART",
        )
    with pytest.raises(WorkspaceSessionConflict):
        service.complete_stop(pending_stop.id, result="STOPPED")
    assert service.get(active.id).state == WorkspaceState.UNKNOWN.value


@pytest.mark.parametrize(
    "value",
    ["", "0", "00", "01", "+1", "-1", "1 ", "x", "18446744073709551616"],
)
def test_runtime_epoch_rejects_noncanonical_or_out_of_range_without_mutation(
    settings: Any, clock: Any, value: str
) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    with pytest.raises(RuntimeEpochBindingError, match="Runtime epoch is invalid"):
        service.classify_runtime_epoch(
            runtime_host_installation_id=host_id,
            runtime_host_installation_revision=1,
            observed_runtime_epoch=value,
        )
    with database.transaction() as session:
        host = session.get(RuntimeHostInstallation, host_id)
        assert host is not None and host.last_runtime_epoch is None
    assert service.get(row.id).revision == row.revision


def test_runtime_epoch_rejects_stale_or_wrong_host_without_partial_fence(
    settings: Any, clock: Any
) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="9",
    )
    for candidate_host, revision, epoch in (
        (host_id, 1, "8"),
        (host_id, 2, "10"),
        ("wri_" + "f" * 32, 1, "10"),
    ):
        with pytest.raises(RuntimeEpochBindingError):
            service.classify_runtime_epoch(
                runtime_host_installation_id=candidate_host,
                runtime_host_installation_revision=revision,
                observed_runtime_epoch=epoch,
            )
    with database.transaction() as session:
        host = session.get(RuntimeHostInstallation, host_id)
        assert host is not None and host.last_runtime_epoch == "9"
    preserved = service.get(row.id)
    assert (preserved.state, preserved.revision) == (row.state, row.revision)


def test_duplicate_and_non_ready_project_are_rejected(settings: Any, clock: Any) -> None:
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


def test_host_revision_cannot_change_while_workspace_is_bound(settings: Any, clock: Any) -> None:
    from sqlalchemy.exc import IntegrityError

    database, service, project_id, host_id = _seed(settings, clock)
    _create(service, project_id, host_id)
    with pytest.raises(IntegrityError), database.transaction() as session:
        host = session.get(RuntimeHostInstallation, host_id)
        assert host is not None
        host.revision = 2
        session.flush()


def test_transition_uses_domain_and_compare_and_swap(settings: Any, clock: Any) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    updated = service.transition(row.id, expected_revision=1, state=WorkspaceState.RUNNING)
    assert updated.revision == 2
    with pytest.raises(WorkspaceSessionConflict):
        service.transition(row.id, expected_revision=1, state=WorkspaceState.STOPPING)
    with pytest.raises(WAWDomainError):
        service.transition(row.id, expected_revision=2, state=WorkspaceState.STOPPED)


def test_begin_start_fences_generation_and_marker(settings: Any, clock: Any) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    row = service.transition(row.id, expected_revision=1, state=WorkspaceState.RUNNING)
    row = service.transition(row.id, expected_revision=2, state=WorkspaceState.EXITED)
    restarted = service.begin_start(row.id, expected_revision=3)
    assert restarted.generation == 2
    assert restarted.revision == 4
    assert restarted.state == WorkspaceState.STARTING.value
    assert restarted.runtime_marker != row.runtime_marker


def test_begin_and_complete_stop_are_generation_bound(settings: Any, clock: Any) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="7",
    )
    row = _create(service, project_id, host_id)
    row = service.transition(row.id, expected_revision=1, state=WorkspaceState.RUNNING)
    operation = service.begin_stop(row.id, expected_revision=row.revision)
    assert operation.result == "PENDING"
    stopping = service.get(row.id)
    assert stopping.state == WorkspaceState.STOPPING.value
    completed = service.complete_stop(operation.id, result="STOPPED")
    assert completed.result == "STOPPED"
    stopped = service.get(row.id)
    assert stopped.state == WorkspaceState.STOPPED.value
    assert stopped.reconciliation_state == "authoritative"
    service.classify_runtime_epoch(
        runtime_host_installation_id=host_id,
        runtime_host_installation_revision=1,
        observed_runtime_epoch="8",
    )
    preserved = service.get(row.id)
    assert (preserved.state, preserved.revision) == (stopped.state, stopped.revision)


def test_stop_timeout_requires_reconciliation(settings: Any, clock: Any) -> None:
    database, service, project_id, host_id = _seed(settings, clock)
    row = _create(service, project_id, host_id)
    row = service.transition(row.id, expected_revision=1, state=WorkspaceState.RUNNING)
    operation = service.begin_stop(row.id, expected_revision=row.revision)
    service.complete_stop(operation.id, result="TIMEOUT", failure_code="STOP_TIMEOUT")
    reconciled = service.get(row.id)
    assert reconciled.state == WorkspaceState.UNKNOWN.value
    assert reconciled.reconciliation_state == "reconciliation_required"
