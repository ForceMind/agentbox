from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import cast

import pytest
from agentbox_api.waw_authorization import SingleAdminWorkspacePolicy
from agentbox_api.waw_control_client import WAWControlClientError
from agentbox_api.workspaces import (
    WAWRequestIdError,
    WorkspaceMetadata,
    WorkspaceRuntimeStatus,
    _validate_lifecycle_response_identity,
    _validate_runtime_status_epoch,
    _validate_runtime_status_identity,
    _waw_request_id,
    _workspace_id_or_404,
)
from agentbox_core.services import AuthenticatedSession
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from fastapi import HTTPException
from pydantic import ValidationError


def _metadata() -> dict[str, object]:
    now = datetime(2026, 8, 30, 0, 0, 0)
    return {
        "id": "aws_" + "1" * 32,
        "project_id": "prj_" + "2" * 32,
        "agent_type": "claude",
        "state": "STARTING",
        "reconciliation_state": "authoritative",
        "generation": 1,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
        "exit_code": None,
        "failure_code": None,
    }


def test_workspace_metadata_is_non_secret_and_terminal_free() -> None:
    value = WorkspaceMetadata.model_validate(_metadata())
    assert value.agent_type == "claude"
    assert "terminal" not in value.model_dump()
    assert "ticket" not in value.model_dump()
    assert "secret" not in value.model_dump()


def test_waw_request_id_randomness_failure_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_count: int) -> str:
        raise RuntimeError("entropy unavailable")

    monkeypatch.setattr("agentbox_api.workspaces.secrets.token_hex", fail)
    with pytest.raises(WAWRequestIdError):
        _waw_request_id()


def test_workspace_metadata_rejects_unknown_fields() -> None:
    payload = _metadata()
    payload["terminal_output"] = "must not cross API metadata boundary"
    with pytest.raises(ValidationError):
        WorkspaceMetadata.model_validate(payload)


def test_runtime_status_is_metadata_only() -> None:
    value = WorkspaceRuntimeStatus.model_validate(
        {
            "workspace_id": "aws_" + "1" * 32,
            "project_id": "prj_" + "2" * 32,
            "agent_type": "claude",
            "generation": "1",
            "binding_revision": "1",
            "binding_digest": "a" * 64,
            "state": "RUNNING",
            "reconciliation_state": "authoritative",
            "runtime_epoch": "2",
            "process_state": "RUNNING",
            "exit_code": None,
            "attachment_capacity": {"admitted": "0", "pending": "0", "limit": "32"},
        }
    )
    assert "terminal" not in value.model_dump()
    assert "ticket" not in value.model_dump()
    with pytest.raises(ValidationError):
        WorkspaceRuntimeStatus.model_validate({**value.model_dump(), "terminal": "forbidden"})
    with pytest.raises(ValidationError):
        WorkspaceRuntimeStatus.model_validate(
            {
                **value.model_dump(),
                "attachment_capacity": {
                    "admitted": "0",
                    "pending": "0",
                    "limit": "32",
                    "ticket": "forbidden",
                },
            }
        )


def test_runtime_status_identity_is_fenced_to_database_row() -> None:
    status = WorkspaceRuntimeStatus.model_validate(
        {
            "workspace_id": "aws_" + "1" * 32,
            "project_id": "prj_" + "2" * 32,
            "agent_type": "claude",
            "generation": "3",
            "binding_revision": "4",
            "binding_digest": "a" * 64,
            "state": "RUNNING",
            "reconciliation_state": "authoritative",
            "runtime_epoch": "2",
            "process_state": "RUNNING",
            "exit_code": None,
            "attachment_capacity": {"admitted": "0", "pending": "0", "limit": "32"},
        }
    )
    row = cast(
        AgentWorkspaceSessionRecord,
        SimpleNamespace(
            id=status.workspace_id,
            project_id=status.project_id,
            agent_type=status.agent_type,
            generation=3,
            binding_revision=4,
            binding_digest=status.binding_digest,
        ),
    )
    _validate_runtime_status_identity(status, row)
    row.project_id = "prj_" + "9" * 32
    with pytest.raises(WAWControlClientError, match="identity"):
        _validate_runtime_status_identity(status, row)


def test_runtime_status_epoch_is_fenced_to_bound_attestation() -> None:
    status = WorkspaceRuntimeStatus.model_validate(
        {
            "workspace_id": "aws_" + "1" * 32,
            "project_id": "prj_" + "2" * 32,
            "agent_type": "claude",
            "generation": "1",
            "binding_revision": "1",
            "binding_digest": "a" * 64,
            "state": "RUNNING",
            "reconciliation_state": "authoritative",
            "runtime_epoch": "2",
            "process_state": "RUNNING",
            "exit_code": None,
            "attachment_capacity": {"admitted": "0", "pending": "0", "limit": "32"},
        }
    )
    coordinator = SimpleNamespace(attestation={"runtime_epoch": "1"})
    with pytest.raises(WAWControlClientError, match="epoch"):
        _validate_runtime_status_epoch(status, coordinator)


def test_runtime_status_epoch_requires_verified_bind_attestation() -> None:
    status = WorkspaceRuntimeStatus.model_validate(
        {
            "workspace_id": "aws_" + "1" * 32,
            "project_id": "prj_" + "2" * 32,
            "agent_type": "claude",
            "generation": "1",
            "binding_revision": "1",
            "binding_digest": "a" * 64,
            "state": "RUNNING",
            "reconciliation_state": "authoritative",
            "runtime_epoch": "2",
            "process_state": "RUNNING",
            "exit_code": None,
            "attachment_capacity": {"admitted": "0", "pending": "0", "limit": "32"},
        }
    )
    with pytest.raises(WAWControlClientError, match="attestation"):
        _validate_runtime_status_epoch(status, SimpleNamespace())


def test_lifecycle_response_identity_is_exactly_fenced() -> None:
    row = cast(
        AgentWorkspaceSessionRecord,
        SimpleNamespace(
            id="aws_" + "1" * 32,
            project_id="prj_" + "2" * 32,
            agent_type="codex",
            generation=7,
        ),
    )
    response = {
        "workspace_id": row.id,
        "project_id": row.project_id,
        "agent_type": row.agent_type,
        "generation": "7",
    }
    _validate_lifecycle_response_identity(response, row)
    for field, value in (("project_id", "prj_" + "3" * 32), ("agent_type", "claude")):
        with pytest.raises(WAWControlClientError, match="identity"):
            _validate_lifecycle_response_identity({**response, field: value}, row)


def test_workspace_id_is_bounded_before_persistence_lookup() -> None:
    _workspace_id_or_404("aws_" + "1" * 32)
    with pytest.raises(HTTPException, match="Workspace not found"):
        _workspace_id_or_404("not-a-workspace")


def test_default_workspace_policy_fails_closed_for_unknown_scope() -> None:
    policy = SingleAdminWorkspacePolicy()
    authenticated = cast(
        AuthenticatedSession,
        SimpleNamespace(user_id="adm_" + "1" * 32),
    )
    workspace = cast(
        AgentWorkspaceSessionRecord,
        SimpleNamespace(authorization_scope="unknown"),
    )
    assert not policy.allows(authenticated, workspace)
    workspace.authorization_scope = "admin"
    assert policy.allows(authenticated, workspace)
