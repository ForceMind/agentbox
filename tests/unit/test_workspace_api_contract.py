from __future__ import annotations

from datetime import datetime

import pytest
from agentbox_api.workspaces import WorkspaceMetadata
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
        "runtime_host_installation_id": "wri_" + "3" * 32,
        "runtime_host_installation_revision": 1,
        "runtime_type": "agentbox-runtime-linux-v1",
        "binding_revision": 1,
        "binding_digest": "a" * 64,
        "runtime_session_name": "agentbox-waw-claude-demo",
        "executable_fingerprint": "b" * 64,
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
