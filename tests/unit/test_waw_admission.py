from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from agentbox_api.waw_admission import (
    WAWAdmissionError,
    WAWRuntimeReadiness,
    prepare_attachment,
)
from agentbox_api.waw_authorization import SingleAdminWorkspacePolicy
from agentbox_core.services import AuthenticatedSession
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from agentbox_core.waw_tickets import AttachmentAuthority

PROJECT_ID = "prj_" + "0" * 32
WORKSPACE_ID = "aws_" + "1" * 32
HOST_ID = "wri_" + "2" * 32
BINDING_DIGEST = "a" * 64


class RecentAuth:
    def __init__(self, value: bool = True) -> None:
        self.value = value

    def is_recently_authenticated(self, authenticated: AuthenticatedSession) -> bool:
        return self.value


def _auth(*, epoch: int = 4) -> AuthenticatedSession:
    now = datetime.now(UTC)
    return AuthenticatedSession(
        session_id="ses_" + "3" * 32,
        user_id="adm_" + "4" * 32,
        username="maintainer",
        expires_at=now + timedelta(hours=1),
        authenticated_at=now,
        auth_epoch=epoch,
        csrf_token="csrf-test",
    )


def _row(**changes: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "authorization_scope": "admin",
        "agent_type": "claude",
        "generation": 2,
        "binding_revision": 3,
        "binding_digest": BINDING_DIGEST,
        "runtime_host_installation_id": HOST_ID,
        "runtime_host_installation_revision": 5,
        "state": "RUNNING",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _authority() -> AttachmentAuthority:
    return AttachmentAuthority(clock=lambda: 100.0, authority_epoch=7, lease_seed=9)


def _runtime(**changes: object) -> WAWRuntimeReadiness:
    return WAWRuntimeReadiness(
        runtime_host_installation_id=cast(
            str, changes.get("runtime_host_installation_id", HOST_ID)
        ),
        runtime_host_installation_revision=cast(
            int, changes.get("runtime_host_installation_revision", 5)
        ),
        runtime_epoch=cast(str, changes.get("runtime_epoch", "12")),
        ready=cast(bool, changes.get("ready", True)),
    )


def test_prepare_attachment_issues_transient_bearer_with_exact_tuple() -> None:
    issued = prepare_attachment(
        authenticated=_auth(),
        row=cast(AgentWorkspaceSessionRecord, _row()),
        policy=SingleAdminWorkspacePolicy(),
        recent_authenticator=RecentAuth(),
        runtime=_runtime(),
        bound_runtime_epoch="12",
        authority=_authority(),
    )

    assert issued.ticket.startswith("wat_")
    assert issued.claims.workspace_id == WORKSPACE_ID
    assert issued.claims.project_id == PROJECT_ID
    assert issued.claims.generation == 2
    assert issued.claims.auth_epoch == 4
    assert issued.claims.runtime_host_installation_revision == 5


@pytest.mark.parametrize(
    "changes, recent, runtime, code",
    [
        ({"authorization_scope": "other"}, True, _runtime(), "WORKSPACE_NOT_FOUND"),
        ({}, False, _runtime(), "RECENT_AUTH_REQUIRED"),
        ({"state": "STOPPED"}, True, _runtime(), "WORKSPACE_NOT_RUNNING"),
        ({}, True, None, "RUNTIME_UNAVAILABLE"),
        ({}, True, _runtime(runtime_epoch="13"), "RUNTIME_INSTALLATION_MISMATCH"),
        ({}, True, _runtime(runtime_host_installation_revision=6), "RUNTIME_INSTALLATION_MISMATCH"),
    ],
)
def test_preflight_rejects_before_authority_write(
    changes: dict[str, object],
    recent: bool,
    runtime: WAWRuntimeReadiness | None,
    code: str,
) -> None:
    authority = _authority()
    with pytest.raises(WAWAdmissionError) as error:
        prepare_attachment(
            authenticated=_auth(),
            row=cast(AgentWorkspaceSessionRecord, _row(**changes)),
            policy=SingleAdminWorkspacePolicy(),
            recent_authenticator=RecentAuth(recent),
            runtime=runtime,
            bound_runtime_epoch="12",
            authority=authority,
        )
    assert error.value.code == code
    assert authority.pending_count == 0


def test_invalid_runtime_epoch_is_rejected_before_issue() -> None:
    with pytest.raises(ValueError):
        _runtime(runtime_epoch="0")
