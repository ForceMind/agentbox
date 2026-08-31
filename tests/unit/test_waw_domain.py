from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from agentbox_core.waw import (
    AgentType,
    AgentWorkspaceSession,
    GenerationCounter,
    ReconciliationState,
    StopResult,
    WAWDomainError,
    WorkspaceState,
    WorkspaceStopOperation,
    WriterLease,
    WriterLeaseSlot,
    managed_marker,
    managed_session_name,
    validate_attachment_id,
    validate_binding_digest,
    validate_project_id,
    validate_runtime_host_installation_id,
    validate_workspace_id,
    workspace_id,
)

PROJECT_ID = "prj_" + "0" * 32
HOST_ID = "wri_" + "1" * 32
BINDING_DIGEST = "a" * 64


def _session(**overrides: object) -> AgentWorkspaceSession:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "agent_type": AgentType.CLAUDE,
        "runtime_host_installation_id": HOST_ID,
        "runtime_host_installation_revision": 3,
        "binding_revision": 1,
        "binding_digest": BINDING_DIGEST,
    }
    values.update(overrides)
    return AgentWorkspaceSession(**values)  # type: ignore[arg-type]


def test_workspace_identity_is_deterministic_and_agent_scoped() -> None:
    claude = workspace_id(PROJECT_ID, AgentType.CLAUDE)
    codex = workspace_id(PROJECT_ID, AgentType.CODEX)
    assert claude == "aws_fc4c3852af45ad8b9a6b6d7a4b8bee35"
    assert claude != codex
    assert validate_workspace_id(claude) == claude
    assert managed_session_name(PROJECT_ID, AgentType.CLAUDE).startswith("agentbox-waw-claude-")


def test_workspace_session_derives_id_name_and_generation_fenced_marker() -> None:
    value = _session()
    assert value.workspace_id == workspace_id(PROJECT_ID, AgentType.CLAUDE)
    assert value.runtime_session_name == "agentbox-waw-claude-2067a493e975cdc6"
    assert value.runtime_marker == managed_marker(
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=3,
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        workspace_id_value=value.workspace_id,
        generation=1,
        binding_revision=1,
        binding_digest=BINDING_DIGEST,
    )
    assert value.runtime_marker != replace_marker(value, generation=2)


def replace_marker(value: AgentWorkspaceSession, *, generation: int) -> str:
    return _session(generation=generation).runtime_marker


def test_workspace_id_cannot_be_reused_for_another_project_or_agent() -> None:
    with pytest.raises(WAWDomainError):
        _session(id=workspace_id(PROJECT_ID, AgentType.CODEX))
    with pytest.raises(WAWDomainError):
        _session(project_id="prj_" + "2" * 32, id=workspace_id(PROJECT_ID, AgentType.CLAUDE))


def test_state_machine_accepts_lifecycle_and_rejects_terminal_revival() -> None:
    running = _session().transition(WorkspaceState.RUNNING)
    assert running.state is WorkspaceState.RUNNING
    needs_login = running.transition(WorkspaceState.LOGIN_REQUIRED)
    stopping = needs_login.transition(WorkspaceState.STOPPING)
    stopped = stopping.transition(WorkspaceState.STOPPED)
    assert stopped.reconciliation_state is ReconciliationState.AUTHORITATIVE
    with pytest.raises(WAWDomainError):
        stopped.transition(WorkspaceState.RUNNING)


def test_generation_counter_is_immutable_monotonic_and_non_wrapping() -> None:
    counter = GenerationCounter()
    generation, counter = counter.allocate()
    assert generation == 1 and counter.current == 1
    second, counter = counter.allocate()
    assert second == 2 and counter.current == 2
    with pytest.raises(WAWDomainError):
        GenerationCounter(2**64 - 1).allocate()


def test_writer_lease_slot_allows_one_active_writer_and_exact_release() -> None:
    now = datetime(2026, 1, 1)
    lease = WriterLease(
        workspace_id=workspace_id(PROJECT_ID, AgentType.CLAUDE),
        attachment_id="att_" + "2" * 32,
        generation=1,
        lease_number=1,
        issued_at=now,
        expires_at=now + timedelta(seconds=5),
    )
    slot = WriterLeaseSlot().acquire(lease, now=now)
    with pytest.raises(WAWDomainError):
        slot.acquire(
            WriterLease(
                workspace_id=lease.workspace_id,
                attachment_id="att_" + "3" * 32,
                generation=1,
                lease_number=2,
                issued_at=now,
                expires_at=now + timedelta(seconds=5),
            ),
            now=now,
        )
    with pytest.raises(WAWDomainError):
        slot.release(
            replace_lease(lease, attachment_id="att_" + "3" * 32),
            now=now,
        )
    assert slot.release(lease, now=now).lease is None
    renewed_slot = slot.acquire(lease, now=now + timedelta(seconds=6))
    assert renewed_slot.lease == lease


def replace_lease(lease: WriterLease, **changes: object) -> WriterLease:
    values = {
        "workspace_id": lease.workspace_id,
        "attachment_id": lease.attachment_id,
        "generation": lease.generation,
        "lease_number": lease.lease_number,
        "issued_at": lease.issued_at,
        "expires_at": lease.expires_at,
    }
    values.update(changes)
    return WriterLease(**values)  # type: ignore[arg-type]


def test_stop_tombstone_is_generation_and_binding_keyed_and_idempotent() -> None:
    value = _session()
    operation = WorkspaceStopOperation(
        workspace_id=value.workspace_id,
        project_id=value.project_id,
        agent_type=value.agent_type,
        generation=value.generation,
        binding_revision=value.binding_revision,
        binding_digest=value.binding_digest,
        runtime_host_installation_id=value.runtime_host_installation_id,
        runtime_host_installation_revision=value.runtime_host_installation_revision,
    )
    assert operation.result is StopResult.PENDING
    stopped = operation.complete(StopResult.STOPPED)
    assert stopped.stop_operation_id == operation.stop_operation_id
    assert stopped.complete(StopResult.STOPPED) == stopped
    with pytest.raises(WAWDomainError):
        stopped.complete(StopResult.TIMEOUT)
    with pytest.raises(WAWDomainError):
        WorkspaceStopOperation(
            workspace_id=workspace_id(PROJECT_ID, AgentType.CODEX),
            project_id=PROJECT_ID,
            agent_type=AgentType.CLAUDE,
            generation=1,
            binding_revision=1,
            binding_digest=BINDING_DIGEST,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision=1,
        )


@pytest.mark.parametrize(
    "validator,value",
    [
        (validate_project_id, "project-a"),
        (validate_workspace_id, "aws_" + "0" * 32),
        (validate_attachment_id, "att_" + "0" * 32),
        (validate_runtime_host_installation_id, "wri_" + "0" * 32),
        (validate_binding_digest, "0" * 64),
    ],
)
def test_waw_identifiers_are_strict(validator: object, value: str) -> None:
    with pytest.raises(WAWDomainError):
        validator(value + "!")  # type: ignore[operator]
