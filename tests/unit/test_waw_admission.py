from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from agentbox_api.waw_admission import (
    WAWAdmissionError,
    WAWAttachmentTicketRequest,
    WAWAttachmentTicketResponse,
    WAWRuntimeReadiness,
    prepare_attachment,
)
from agentbox_api.waw_authorization import SingleAdminWorkspacePolicy
from agentbox_core.services import AuthenticatedSession
from agentbox_core.waw import AgentType, workspace_id
from agentbox_core.waw_models import AgentWorkspaceSessionRecord
from agentbox_core.waw_tickets import AttachmentAuthority

PROJECT_ID = "prj_" + "0" * 32
WORKSPACE_ID = workspace_id(PROJECT_ID, AgentType.CLAUDE)
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
    response = WAWAttachmentTicketResponse.from_issued(
        "wreq_" + "1" * 32, issued, runtime_epoch="12"
    )
    assert response.model_dump(mode="json")["lease_number"] == "9"
    assert response.model_dump(mode="json")["protocol_version"] == 1
    assert response.model_dump(mode="json")["expires_at"].endswith("Z")
    assert response.expires_at > datetime.now(UTC)


def test_attachment_ticket_request_is_closed_to_writer_mode() -> None:
    assert WAWAttachmentTicketRequest(mode="writer").mode == "writer"
    with pytest.raises(ValueError):
        WAWAttachmentTicketRequest.model_validate({"mode": "reader"})
    with pytest.raises(ValueError):
        WAWAttachmentTicketRequest.model_validate({"mode": "writer", "path": "/tmp"})


def test_attachment_ticket_response_rejects_zero_or_extra_fields() -> None:
    with pytest.raises(ValueError):
        WAWAttachmentTicketResponse.model_validate(
            {
                "request_id": "wreq_" + "1" * 32,
                "ticket": "wat_" + "2" * 32,
                "workspace_id": WORKSPACE_ID,
                "project_id": PROJECT_ID,
                "agent_type": "claude",
                "attachment_id": "att_" + "3" * 32,
                "mode": "writer",
                "lease_number": "0",
                "generation": "1",
                "binding_revision": "1",
                "binding_digest": BINDING_DIGEST,
                "auth_epoch": "1",
                "api_authority_epoch": "1",
                "runtime_host_installation_id": HOST_ID,
                "runtime_host_installation_revision": "1",
                "runtime_epoch": "1",
                "expires_at": datetime.now(UTC),
                "terminal": "forbidden",
            }
        )


@pytest.mark.parametrize(
    "origin",
    ["https://evil.invalid", "http://agentbox.invalid", "https://agentbox.invalid/path"],
)
def test_prepare_attachment_rejects_noncanonical_or_unallowlisted_origin(origin: str) -> None:
    with pytest.raises(WAWAdmissionError) as rejected:
        prepare_attachment(
            authenticated=_auth(),
            row=cast(AgentWorkspaceSessionRecord, _row()),
            policy=SingleAdminWorkspacePolicy(),
            recent_authenticator=RecentAuth(),
            runtime=_runtime(),
            bound_runtime_epoch="12",
            authority=_authority(),
            origin=origin,
            allowed_origins={"https://agentbox.invalid"},
        )
    assert rejected.value.code == "ORIGIN_INVALID"


@pytest.mark.parametrize(
    "changes",
    [
        {"runtime_host_installation_id": "host-invalid"},
        {"runtime_host_installation_revision": 0},
        {"runtime_host_installation_revision": 2**64},
        {"ready": 1},
    ],
)
def test_runtime_readiness_rejects_untrusted_identity_values(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _runtime(**changes)


def test_attachment_randomness_failure_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_count: int) -> str:
        raise RuntimeError("entropy unavailable")

    monkeypatch.setattr("agentbox_api.waw_admission.secrets.token_hex", fail)
    with pytest.raises(WAWAdmissionError) as unavailable:
        prepare_attachment(
            authenticated=_auth(),
            row=cast(AgentWorkspaceSessionRecord, _row()),
            policy=SingleAdminWorkspacePolicy(),
            recent_authenticator=RecentAuth(),
            runtime=_runtime(),
            bound_runtime_epoch="12",
            authority=_authority(),
        )
    assert unavailable.value.code == "RANDOMNESS_UNAVAILABLE"


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
