from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import cast

import pytest
from agentbox_api.waw_control_client import WAWControlClientError
from agentbox_api.workspaces import (
    WorkspaceMetadata,
    WorkspaceRuntimeStatus,
    _validate_runtime_status_identity,
)
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
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
