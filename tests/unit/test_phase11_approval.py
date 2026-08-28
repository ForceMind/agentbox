from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

import pytest
import rfc8785
from agentbox_core.approval_models import (
    ChallengeTerminalResultCode,
    ConfirmationChallenge,
    ConfirmationChallengeState,
    ConfirmationPurpose,
    ProviderSecretProvisioningAttempt,
    ProviderSecretProvisioningAttemptState,
)
from agentbox_core.approvals import (
    ApprovalService,
    ChallengeIssue,
    approval_digest,
    approval_document,
)
from agentbox_core.errors import (
    ApprovalAlreadyFinal,
    ApprovalExpired,
    ApprovalInvalid,
    ApprovalStale,
    ApprovalUnavailable,
    ReauthenticationInvalidCredentials,
    ReauthenticationInvalidSession,
    ReauthenticationUnavailable,
)
from agentbox_core.models import AuditEvent, ControlPlaneSession
from agentbox_core.provider_models import (
    CredentialKind,
    CredentialLifecycleState,
    ProviderLifecycleState,
    ProviderType,
    RuntimeType,
)
from agentbox_core.providers import CredentialMetadataCreate, ProviderCreate
from agentbox_core.services import AuthenticatedSession, ControlPlaneServices
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

PASSWORD = "a sufficiently long passphrase"


class AdvancingClock(Protocol):
    current: datetime

    def advance(self, *, seconds: int) -> None: ...


def _authority(
    services: ControlPlaneServices,
) -> tuple[AuthenticatedSession, ChallengeIssue]:
    issued = services.auth.login(
        username="maintainer",
        password=PASSWORD,
        source_identifier="127.0.0.1",
        request_id="req_login",
    )
    authenticated = services.sessions.authenticate(issued.token)
    runtime = services.providers.register_runtime_installation(
        runtime_type=RuntimeType.CODEX,
        display_name="Codex",
        actor_id=authenticated.user_id,
    )
    provider = services.providers.create_provider(
        ProviderCreate(
            display_name="OpenAI",
            provider_type=ProviderType.OFFICIAL_OPENAI,
            model="gpt-5",
        ),
        actor_id=authenticated.user_id,
    )
    credential = services.providers.create_credential_metadata(
        CredentialMetadataCreate(
            provider_id=provider.id,
            provider_revision=provider.revision,
            provider_state=provider.state,
            runtime_installation_id=runtime.id,
            runtime_installation_revision=runtime.revision,
            runtime_type=runtime.runtime_type,
            kind=CredentialKind.API_KEY,
        ),
        actor_id=authenticated.user_id,
    )
    values = ChallengeIssue(
        runtime_installation_id=runtime.id,
        runtime_installation_revision=runtime.revision,
        runtime_type=runtime.runtime_type,
        provider_id=provider.id,
        provider_revision=provider.revision,
        provider_state=ProviderLifecycleState.CONFIGURED,
        credential_id=credential.id,
        credential_revision=credential.revision,
        credential_kind=CredentialKind.API_KEY,
        credential_state=CredentialLifecycleState.MISSING,
    )
    return authenticated, values


def test_issue_and_consume_atomically_create_only_authorized_attempt(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated,
        values,
        request_id="req_issue",
    )
    assert challenge.state is ConfirmationChallengeState.ISSUED
    assert challenge.approval_digest == approval_digest(challenge)
    assert (challenge.expires_at - challenge.issued_at).total_seconds() == 300

    confirmation = f"PROVISION {values.credential_id}"
    attempt = initialized_services.approvals.consume(
        authenticated,
        challenge.id,
        confirmation=confirmation,
        authorization_request_id="req_consume",
    )
    assert attempt.state is ProviderSecretProvisioningAttemptState.AUTHORIZED
    assert attempt.provisioning_intent_id == challenge.provisioning_intent_id
    assert attempt.authorize_requested_at is None
    assert attempt.authorize_attempt_count == 0
    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.state is ConfirmationChallengeState.CONSUMED
        assert stored.terminal_result_code is ChallengeTerminalResultCode.ATTEMPT_CREATED
        assert session.scalar(
            select(ProviderSecretProvisioningAttempt).where(
                ProviderSecretProvisioningAttempt.challenge_id == challenge.id
            )
        )
        audit_blob = json.dumps(
            [event.metadata_json for event in session.scalars(select(AuditEvent))]
        )
        assert confirmation not in audit_blob


def test_confirmation_mismatch_burns_challenge_without_attempt(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated,
        values,
        request_id="req_issue_mismatch",
    )
    with pytest.raises(ApprovalInvalid):
        initialized_services.approvals.consume(
            authenticated,
            challenge.id,
            confirmation=f"provision {values.credential_id}",
            authorization_request_id="req_consume_mismatch",
        )
    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.state is ConfirmationChallengeState.CANCELLED
        assert stored.terminal_result_code is ChallengeTerminalResultCode.CONFIRMATION_MISMATCH
        assert (
            session.scalar(
                select(ProviderSecretProvisioningAttempt).where(
                    ProviderSecretProvisioningAttempt.challenge_id == challenge.id
                )
            )
            is None
        )
        rejection = session.scalar(
            select(AuditEvent)
            .where(AuditEvent.action == "provider_secret.challenge_rejected")
            .order_by(AuditEvent.created_at.desc())
        )
        assert rejection is not None
        assert rejection.target_id == challenge.id
        assert rejection.metadata_json == {
            "reason_code": "APPROVAL_INVALID",
            "id_well_formed": True,
        }


def test_malformed_challenge_id_is_rejected_without_audit_target(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, _values = _authority(initialized_services)
    with pytest.raises(ApprovalInvalid):
        initialized_services.approvals.consume(
            authenticated,
            "not-a-challenge-id",
            confirmation="PROVISION crd_00000000000000000000000000000000",
            authorization_request_id="req_malformed",
        )
    with initialized_services.database.transaction() as session:
        rejection = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "provider_secret.challenge_rejected")
        )
        assert rejection is not None
        assert rejection.target_type is None
        assert rejection.target_id is None
        assert rejection.metadata_json["id_well_formed"] is False


def test_authorized_attempt_expires_instead_of_cancelling_after_deadline(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated,
        values,
        request_id="req_issue_expiry",
    )
    attempt = initialized_services.approvals.consume(
        authenticated,
        challenge.id,
        confirmation=f"PROVISION {values.credential_id}",
        authorization_request_id="req_consume_expiry",
    )
    clock.advance(seconds=300)
    with pytest.raises(ApprovalAlreadyFinal):
        initialized_services.approvals.cancel_authorized_attempt(
            authenticated,
            attempt.id,
            request_id="req_cancel_expired",
        )
    with initialized_services.database.transaction() as session:
        stored = session.get(ProviderSecretProvisioningAttempt, attempt.id)
        assert stored is not None
        assert stored.state is ProviderSecretProvisioningAttemptState.EXPIRED
        assert stored.terminal_result_code is not None
        assert stored.terminal_result_code.value == "INTENT_EXPIRED_UNSENT"


def test_active_attempt_delete_and_inconsistent_terminal_transition_fail_closed(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated,
        values,
        request_id="req_issue_direct_sql",
    )
    attempt = initialized_services.approvals.consume(
        authenticated,
        challenge.id,
        confirmation=f"PROVISION {values.credential_id}",
        authorization_request_id="req_consume_direct_sql",
    )
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.execute(
            text("DELETE FROM provider_secret_provisioning_attempts WHERE id=:attempt_id"),
            {"attempt_id": attempt.id},
        )
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.execute(
            text(
                "UPDATE provider_secret_provisioning_attempts "
                "SET state='cancelled',updated_at=created_at WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.execute(
            text(
                "UPDATE provider_secret_provisioning_attempts "
                "SET updated_at=agentbox_now_utc6() WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )


def test_needs_attention_is_unresolved_nonprunable_and_immutable(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_needs_attention_issue"
    )
    attempt = initialized_services.approvals.consume(
        authenticated,
        challenge.id,
        confirmation=f"PROVISION {values.credential_id}",
        authorization_request_id="req_needs_attention_consume",
    )
    with initialized_services.database.transaction() as session:
        session.execute(
            text(
                "UPDATE provider_secret_provisioning_attempts SET "
                "state='needs_attention',updated_at=agentbox_now_utc6(),"
                "terminal_at=agentbox_now_utc6(),terminal_result_code='BOUND_ENTITY_STALE' "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
    clock.advance(seconds=9_999 * 24 * 60 * 60)
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.execute(
            text("DELETE FROM provider_secret_provisioning_attempts WHERE id=:attempt_id"),
            {"attempt_id": attempt.id},
        )
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.execute(
            text(
                "UPDATE provider_secret_provisioning_attempts SET "
                "updated_at=agentbox_now_utc6(),terminal_at=agentbox_now_utc6(),"
                "terminal_result_code='RUNTIME_OPERATION_UNCERTAIN' WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )


def test_backward_clock_burns_challenge_without_granting_authority(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated,
        values,
        request_id="req_issue_clock_rollback",
    )
    clock.current -= timedelta(microseconds=1)
    with pytest.raises(ApprovalUnavailable):
        initialized_services.approvals.consume(
            authenticated,
            challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_consume_clock_rollback",
        )
    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.state is ConfirmationChallengeState.CANCELLED
        assert stored.terminal_result_code is ChallengeTerminalResultCode.CLOCK_ROLLBACK_DETECTED
        assert (
            session.scalar(select(func.count()).select_from(ProviderSecretProvisioningAttempt)) == 0
        )


def test_reauthentication_rotates_exact_session_and_old_epoch_authority(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated,
        values,
        request_id="req_issue_reauth",
    )
    old_hash: str
    with initialized_services.database.transaction() as session:
        stored = session.get(ControlPlaneSession, authenticated.session_id)
        assert stored is not None
        old_hash = stored.token_hash

    replacement = initialized_services.auth.reauthenticate(
        authenticated,
        password=PASSWORD,
        source_identifier="127.0.0.1",
        request_id="req_reauth",
    )
    assert replacement.session_id == authenticated.session_id
    assert replacement.auth_epoch == authenticated.auth_epoch + 1
    assert (
        initialized_services.sessions.authenticate(replacement.token).auth_epoch
        == replacement.auth_epoch
    )
    with initialized_services.database.transaction() as session:
        stored_session = session.get(ControlPlaneSession, authenticated.session_id)
        stored_challenge = session.get(ConfirmationChallenge, challenge.id)
        assert stored_session is not None
        assert stored_session.token_hash != old_hash
        assert stored_challenge is not None
        assert stored_challenge.state is ConfirmationChallengeState.CANCELLED
        assert (
            stored_challenge.terminal_result_code is ChallengeTerminalResultCode.AUTH_EPOCH_ROTATED
        )


def test_database_rejects_cross_runtime_owner_and_identity_mutation(
    initialized_services: ControlPlaneServices,
) -> None:
    _authenticated, values = _authority(initialized_services)
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.execute(
            text(
                "UPDATE provider_credentials SET runtime_installation_id="
                "'rti_ffffffffffffffffffffffffffffffff' WHERE id=:credential_id"
            ),
            {"credential_id": values.credential_id},
        )


def test_transaction_clock_is_pinned_at_begin(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    with initialized_services.database.transaction() as session:
        session.execute(text("BEGIN IMMEDIATE"))
        first = session.execute(text("SELECT agentbox_now_utc6()")).scalar_one()
        clock.advance(seconds=30)
        second = session.execute(text("SELECT agentbox_now_utc6()")).scalar_one()
    with initialized_services.database.transaction() as session:
        third = session.execute(text("SELECT agentbox_now_utc6()")).scalar_one()

    assert first == second == "2026-08-09 00:00:00.000000"
    assert third == "2026-08-09 00:00:30.000000"


def test_database_rejects_noncanonical_calendar_utc6(
    initialized_services: ControlPlaneServices,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password=PASSWORD,
        source_identifier="192.0.2.12",
        request_id="req_invalid_calendar_login",
    )
    with pytest.raises(IntegrityError), initialized_services.database.transaction() as session:
        session.execute(
            text("UPDATE sessions SET last_seen_at='2026-02-30 00:00:00.000000' WHERE id=:id"),
            {"id": issued.session_id},
        )


def test_slice32a_audit_envelope_and_values_are_closed(
    initialized_services: ControlPlaneServices,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password=PASSWORD,
        source_identifier="192.0.2.13",
        request_id="req_audit_allowlist_login",
    )
    authenticated = initialized_services.sessions.authenticate(issued.token)
    valid_metadata: dict[str, object] = {
        "auth_context_fingerprint": "a" * 24,
        "source_fingerprint": "b" * 24,
        "reason": "credentials_rotated",
    }
    with (
        pytest.raises(ValueError, match="target"),
        initialized_services.database.transaction() as session,
    ):
        initialized_services.audit.record(
            session,
            actor_type="admin_user",
            actor_id=authenticated.user_id,
            action="reauth_succeeded",
            result="succeeded",
            request_id="req_bad_audit_target",
            target_type="auth_context",
            target_id=authenticated.session_id,
            metadata=valid_metadata,
        )
    with (
        pytest.raises(ValueError, match="reason"),
        initialized_services.database.transaction() as session,
    ):
        initialized_services.audit.record(
            session,
            actor_type="admin_user",
            actor_id=authenticated.user_id,
            action="reauth_succeeded",
            result="succeeded",
            request_id="req_bad_audit_reason",
            target_type="auth_context",
            target_id=None,
            metadata={**valid_metadata, "reason": "caller_selected"},
        )


def test_exact_expiry_boundary_burns_challenge_without_attempt(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_exact_expiry"
    )
    clock.advance(seconds=300)

    with pytest.raises(ApprovalExpired) as captured:
        initialized_services.approvals.consume(
            authenticated,
            challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_exact_expiry_consume",
        )
    assert getattr(captured.value, "code", None) == "APPROVAL_EXPIRED"
    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.state is ConfirmationChallengeState.EXPIRED
        assert (
            session.scalar(select(func.count()).select_from(ProviderSecretProvisioningAttempt)) == 0
        )


def test_challenge_is_exact_session_bound(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_session_bound"
    )
    second = initialized_services.auth.login(
        username="maintainer",
        password=PASSWORD,
        source_identifier="127.0.0.2",
        request_id="req_second_login",
    )
    other_session = initialized_services.sessions.authenticate(second.token)

    with pytest.raises(ApprovalInvalid):
        initialized_services.approvals.consume(
            other_session,
            challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_wrong_session",
        )
    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.state is ConfirmationChallengeState.ISSUED


def test_digest_binds_every_mutated_authority_field_and_pregenerated_intent(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_digest_binding"
    )
    baseline = approval_digest(challenge)
    assert challenge.provisioning_intent_id.startswith("psi_")
    assert len(challenge.provisioning_intent_id) == 36

    challenge.provider_revision += 1
    assert approval_digest(challenge) != baseline
    challenge.provider_revision -= 1
    challenge.provisioning_intent_id = "psi_" + ("f" * 32)
    assert approval_digest(challenge) != baseline


def test_consume_rollback_preserves_the_only_two_durable_outcomes(
    initialized_services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_failure_injection"
    )
    original_record = initialized_services.audit.record

    def fail_after_handshake(*args: object, **kwargs: object) -> object:
        if kwargs.get("action") == "provider_secret.attempt_created":
            raise RuntimeError("injected audit failure")
        return original_record(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(initialized_services.audit, "record", fail_after_handshake)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        initialized_services.approvals.consume(
            authenticated,
            challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_failure_injection_consume",
        )

    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.state is ConfirmationChallengeState.ISSUED
        assert (
            session.scalar(select(func.count()).select_from(ProviderSecretProvisioningAttempt)) == 0
        )


def test_two_connections_can_consume_a_challenge_only_once(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_concurrent_issue"
    )
    barrier = threading.Barrier(2)

    def consume(request_id: str) -> str:
        barrier.wait(timeout=5)
        try:
            initialized_services.approvals.consume(
                authenticated,
                challenge.id,
                confirmation=f"PROVISION {values.credential_id}",
                authorization_request_id=request_id,
            )
            return "authorized"
        except (ApprovalAlreadyFinal, ApprovalUnavailable) as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(consume, ("req_race_a", "req_race_b")))

    assert outcomes.count("authorized") == 1
    assert len(outcomes) == 2
    with initialized_services.database.transaction() as session:
        assert (
            session.scalar(select(func.count()).select_from(ProviderSecretProvisioningAttempt)) == 1
        )
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.state is ConfirmationChallengeState.CONSUMED


def test_concurrent_reauthentication_rotates_only_once(
    initialized_services: ControlPlaneServices,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password=PASSWORD,
        source_identifier="192.0.2.10",
        request_id="req_reauth_race_login",
    )
    authenticated = initialized_services.sessions.authenticate(issued.token)
    barrier = threading.Barrier(2)

    def reauthenticate(request_id: str) -> str:
        barrier.wait(timeout=5)
        try:
            replacement = initialized_services.auth.reauthenticate(
                authenticated,
                password=PASSWORD,
                source_identifier="192.0.2.10",
                request_id=request_id,
            )
            return replacement.token
        except (ReauthenticationInvalidCredentials, ReauthenticationInvalidSession) as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(reauthenticate, ("req_reauth_a", "req_reauth_b")))

    replacements = [
        value for value in outcomes if value not in {"INVALID_CREDENTIALS", "INVALID_SESSION"}
    ]
    assert len(replacements) == 1
    assert initialized_services.sessions.authenticate(replacements[0]).auth_epoch == 2


def test_consume_materializes_exact_admin_and_auth_epoch_invalidation_codes(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    admin_challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_admin_invalidation"
    )
    with initialized_services.database.transaction() as session:
        session.execute(
            text("UPDATE admin_users SET is_active=0 WHERE id=:id"),
            {"id": authenticated.user_id},
        )
    with pytest.raises(ApprovalInvalid):
        initialized_services.approvals.consume(
            authenticated,
            admin_challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_admin_invalidation_consume",
        )
    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, admin_challenge.id)
        assert stored is not None
        assert stored.terminal_result_code is ChallengeTerminalResultCode.ADMIN_DEACTIVATED


def test_consume_rejects_authenticated_context_epoch_substitution(
    initialized_services: ControlPlaneServices,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_epoch_substitution"
    )
    substituted = replace(authenticated, auth_epoch=authenticated.auth_epoch + 1)

    with pytest.raises(ApprovalStale):
        initialized_services.approvals.consume(
            substituted,
            challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_epoch_substitution_consume",
        )
    with initialized_services.database.transaction() as session:
        stored = session.get(ConfirmationChallenge, challenge.id)
        assert stored is not None
        assert stored.terminal_result_code is ChallengeTerminalResultCode.AUTH_EPOCH_ROTATED


def test_reauthentication_clock_rollback_after_password_proof_fails_closed(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = initialized_services.auth.login(
        username="maintainer",
        password=PASSWORD,
        source_identifier="192.0.2.11",
        request_id="req_reauth_clock_login",
    )
    authenticated = initialized_services.sessions.authenticate(issued.token)
    original_verify = initialized_services.auth._password_manager.verify

    def verify_then_rewind(encoded_hash: str, password: str) -> bool:
        verified = original_verify(encoded_hash, password)
        clock.current -= timedelta(microseconds=1)
        return verified

    monkeypatch.setattr(initialized_services.auth._password_manager, "verify", verify_then_rewind)
    with pytest.raises(ReauthenticationUnavailable):
        initialized_services.auth.reauthenticate(
            authenticated,
            password=PASSWORD,
            source_identifier="192.0.2.11",
            request_id="req_reauth_clock",
        )

    clock.current += timedelta(microseconds=1)
    assert initialized_services.sessions.authenticate(issued.token).auth_epoch == 1


def test_maintenance_has_one_global_hundred_row_bound(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    authenticated, values = _authority(initialized_services)
    for index in range(101):
        challenge = initialized_services.approvals.issue(
            authenticated, values, request_id=f"req_bound_issue_{index}"
        )
        initialized_services.approvals.cancel_challenge(
            authenticated, challenge.id, request_id=f"req_bound_cancel_{index}"
        )
    clock.advance(seconds=30 * 24 * 60 * 60)

    first = initialized_services.approvals.maintenance()
    assert sum(first.__dict__.values()) == 100
    with initialized_services.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationChallenge)) == 1

    second = initialized_services.approvals.maintenance()
    assert sum(second.__dict__.values()) <= 100
    with initialized_services.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationChallenge)) == 0


def test_malformed_clock_function_fails_closed_at_retention_delete(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_bad_clock_issue"
    )
    attempt = initialized_services.approvals.consume(
        authenticated,
        challenge.id,
        confirmation=f"PROVISION {values.credential_id}",
        authorization_request_id="req_bad_clock_consume",
    )
    initialized_services.approvals.cancel_authorized_attempt(
        authenticated, attempt.id, request_id="req_bad_clock_cancel"
    )
    clock.advance(seconds=30 * 24 * 60 * 60)

    with initialized_services.database.engine.connect() as connection:
        driver_connection = connection.connection.driver_connection
        assert driver_connection is not None
        driver_connection.create_function(
            "agentbox_now_utc6", 0, lambda: "2026-02-30 00:00:00.000000"
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                text("DELETE FROM provider_secret_provisioning_attempts WHERE id=:id"),
                {"id": attempt.id},
            )
    initialized_services.database.engine.dispose()
    with initialized_services.database.transaction() as session:
        assert session.get(ProviderSecretProvisioningAttempt, attempt.id) is not None


def test_missing_clock_function_fails_closed_at_retention_delete(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
) -> None:
    authenticated, values = _authority(initialized_services)
    challenge = initialized_services.approvals.issue(
        authenticated, values, request_id="req_missing_clock_issue"
    )
    attempt = initialized_services.approvals.consume(
        authenticated,
        challenge.id,
        confirmation=f"PROVISION {values.credential_id}",
        authorization_request_id="req_missing_clock_consume",
    )
    initialized_services.approvals.cancel_authorized_attempt(
        authenticated, attempt.id, request_id="req_missing_clock_cancel"
    )
    clock.advance(seconds=30 * 24 * 60 * 60)
    initialized_services.database.engine.dispose()
    path = make_url(initialized_services.database.settings.database_url).database
    assert path is not None
    raw = sqlite3.connect(path)
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.OperationalError, match="agentbox_now_utc6"):
            raw.execute(
                "DELETE FROM provider_secret_provisioning_attempts WHERE id=?",
                (attempt.id,),
            )
    finally:
        raw.close()

    with initialized_services.database.transaction() as session:
        assert session.get(ProviderSecretProvisioningAttempt, attempt.id) is not None


def _cancel_rollback_combination(
    services: ControlPlaneServices, clock: AdvancingClock, invalidation: str
) -> None:
    authenticated, values = _authority(services)
    challenge = services.approvals.issue(authenticated, values, request_id="req_rollback_issue")
    with services.database.transaction() as session:
        if invalidation == "admin":
            session.execute(
                text("UPDATE admin_users SET is_active=0 WHERE id=:id"),
                {"id": authenticated.user_id},
            )
        else:
            session.execute(
                text("UPDATE sessions SET revoked_at=created_at WHERE id=:id"),
                {"id": authenticated.session_id},
            )
    clock.current -= timedelta(microseconds=1)
    with pytest.raises(ApprovalUnavailable) as caught:
        services.approvals.cancel_challenge(authenticated, challenge.id, request_id="req_cancel")
    assert caught.value.code == "APPROVAL_UNAVAILABLE"
    # A new driver connection proves committed state, not an ORM identity-map view.
    with sqlite3.connect(str(services.database.engine.url.database)) as connection:
        row = connection.execute(
            "SELECT state,terminal_result_code,cancellation_epoch,terminal_at,"
            "retention_eligible_at,consumed_at,consumed_request_id,last_observed_at,"
            "provisioning_intent_id FROM confirmation_challenges WHERE id=?",
            (challenge.id,),
        ).fetchone()
        terminal = challenge.issued_at.strftime("%Y-%m-%d %H:%M:%S.%f")
        retention = (challenge.issued_at + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S.%f")
        assert row == (
            "cancelled",
            "CLOCK_ROLLBACK_DETECTED",
            1,
            terminal,
            retention,
            None,
            None,
            terminal,
            challenge.provisioning_intent_id,
        )
        assert connection.execute(
            "SELECT count(*) FROM provider_secret_provisioning_attempts"
        ).fetchone() == (0,)
        dump = "\n".join(connection.iterdump())
        assert f"PROVISION {values.credential_id}" not in dump
        assert PASSWORD not in dump
        assert services.approvals._secret not in dump
    with pytest.raises(ApprovalAlreadyFinal):
        services.approvals.consume(
            authenticated,
            challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_burned_intent",
        )


def test_cancel_challenge_clock_rollback_precedes_admin_deactivation(
    initialized_services: ControlPlaneServices, clock: AdvancingClock
) -> None:
    _cancel_rollback_combination(initialized_services, clock, "admin")


def test_cancel_challenge_clock_rollback_precedes_session_revocation(
    initialized_services: ControlPlaneServices, clock: AdvancingClock
) -> None:
    _cancel_rollback_combination(initialized_services, clock, "session")


@pytest.mark.parametrize("iteration", range(5))
def test_consume_cancel_concurrency_has_one_durable_winner(
    initialized_services: ControlPlaneServices, iteration: int
) -> None:
    services = initialized_services
    authenticated, values = _authority(services)
    challenge = services.approvals.issue(authenticated, values, request_id="req_race_issue")
    barrier = threading.Barrier(2)

    def race(consume: bool) -> str:
        barrier.wait(timeout=10)
        try:
            if consume:
                services.approvals.consume(
                    authenticated,
                    challenge.id,
                    confirmation=f"PROVISION {values.credential_id}",
                    authorization_request_id="req_race_consume",
                )
                return "consumed"
            services.approvals.cancel_challenge(
                authenticated, challenge.id, request_id="req_race_cancel"
            )
            return "cancelled"
        except ApprovalAlreadyFinal as exc:
            assert exc.code == "APPROVAL_ALREADY_FINAL"
            return "final"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(race, [True, False]))
    assert outcomes in (["consumed", "final"], ["final", "cancelled"])
    with sqlite3.connect(str(services.database.engine.url.database)) as connection:
        state, code = connection.execute(
            "SELECT state,terminal_result_code FROM confirmation_challenges WHERE id=?",
            (challenge.id,),
        ).fetchone()
        attempts = connection.execute(
            "SELECT state,challenge_id FROM provider_secret_provisioning_attempts"
        ).fetchall()
        if state == "consumed":
            assert code == "ATTEMPT_CREATED"
            assert attempts == [("authorized", challenge.id)]
        else:
            assert (state, code, attempts) == ("cancelled", "CANCELLED_BY_ISSUER", [])


@pytest.mark.parametrize(
    "checkpoint",
    [
        "after_validation",
        "before_attempt_construct",
        "before_attempt_insert",
        "after_attempt_insert",
        "before_challenge_audit",
        "after_challenge_audit",
        "before_attempt_audit",
        "after_attempt_audit",
        "before_final_flush",
        "after_final_flush",
        "before_commit",
        "after_commit",
    ],
)
def test_consume_statement_fault_matrix_is_durable(
    initialized_services: ControlPlaneServices, monkeypatch: pytest.MonkeyPatch, checkpoint: str
) -> None:
    services = initialized_services
    authenticated, values = _authority(services)
    challenge = services.approvals.issue(authenticated, values, request_id="req_fault_issue")
    reached: list[str] = []

    def fail(self: ApprovalService, stage: str) -> None:
        reached.append(stage)
        if stage == checkpoint:
            raise ValueError(
                "injected response loss" if stage == "after_commit" else "injected fault"
            )

    monkeypatch.setattr(ApprovalService, "_consume_checkpoint", fail)
    with pytest.raises(ApprovalUnavailable):
        services.approvals.consume(
            authenticated,
            challenge.id,
            confirmation=f"PROVISION {values.credential_id}",
            authorization_request_id="req_fault_consume",
        )
    assert checkpoint in reached
    with sqlite3.connect(str(services.database.engine.url.database)) as connection:
        state = connection.execute(
            "SELECT state FROM confirmation_challenges WHERE id=?", (challenge.id,)
        ).fetchone()[0]
        attempts = connection.execute(
            "SELECT "
            "id,state,challenge_id,provisioning_intent_id,authorization_request_id,"
            "authorize_attempt_count,authorize_requested_at "
            "FROM provider_secret_provisioning_attempts"
        ).fetchall()
        audits = connection.execute(
            "SELECT action FROM audit_events WHERE action IN "
            "('provider_secret.challenge_consumed','provider_secret.attempt_created')"
        ).fetchall()
        if checkpoint == "after_commit":
            assert state == "consumed"
            assert len(attempts) == 1
            assert attempts[0][1:] == (
                "authorized",
                challenge.id,
                challenge.provisioning_intent_id,
                "req_fault_consume",
                0,
                None,
            )
            assert sorted(audits) == [
                ("provider_secret.attempt_created",),
                ("provider_secret.challenge_consumed",),
            ]
        else:
            assert (state, attempts, audits) == ("issued", [], [])
    if checkpoint == "after_commit":
        monkeypatch.undo()
        with pytest.raises(ApprovalAlreadyFinal):
            services.approvals.consume(
                authenticated,
                challenge.id,
                confirmation=f"PROVISION {values.credential_id}",
                authorization_request_id="req_fault_consume",
            )
        with sqlite3.connect(str(services.database.engine.url.database)) as connection:
            assert connection.execute(
                "SELECT id FROM provider_secret_provisioning_attempts"
            ).fetchall() == [(attempts[0][0],)]


# Section 18 literals transcribed independently; for this no-float, ASCII-key
# document json.dumps(sort_keys=True,separators=(",",":"),ensure_ascii=False)
# is equivalent to RFC8785. One-time hashlib result was independently checked
# with `openssl dgst -sha256` over domain NUL bytes + the literal UTF-8 bytes.
_GOLDEN_CANONICAL = (
    b'{"admin_user_id":"adm_22222222222222222222222222222222",'
    b'"auth_epoch":3,'
    b'"cancellation_epoch":0,'
    b'"challenge_id":"cch_11111111111111111111111111111111",'
    b'"confirmation_verifier":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
    b'"control_plane_session_id":"ses_33333333333333333333333333333333",'
    b'"credential_id":"crd_77777777777777777777777777777777",'
    b'"credential_kind":"api_key",'
    b'"credential_revision":13,'
    b'"credential_runtime_installation_id":"rti_55555555555555555555555555555555",'
    b'"credential_state":"missing",'
    b'"expected_runtime_secret_ref":null,'
    b'"expected_secret_version":null,'
    b'"expires_at":"2026-08-24T00:05:01.999999Z",'
    b'"initial_cancellation_epoch":0,'
    b'"intended_secret_version":1,'
    b'"intended_state":"configured",'
    b'"intent_contract_version":1,'
    b'"intent_expires_at":"2026-08-24T00:05:01.999999Z",'
    b'"intent_issued_at":"2026-08-24T00:00:01.999999Z",'
    b'"issue_request_id":"req_golden",'
    b'"issued_at":"2026-08-24T00:00:01.999999Z",'
    b'"provider_id":"prv_66666666666666666666666666666666",'
    b'"provider_revision":11,'
    b'"provider_state":"configured",'
    b'"provisioning_intent_id":"psi_44444444444444444444444444444444",'
    b'"purpose":"provider_secret_provision",'
    b'"recent_authenticated_at":"2026-08-24T00:00:00.000000Z",'
    b'"runtime_installation_id":"rti_55555555555555555555555555555555",'
    b'"runtime_installation_revision":7,'
    b'"runtime_type":"codex",'
    b'"schema":"agentbox.provider-secret-provision-approval.v1"}'
)
_GOLDEN_DIGEST = "32d35b12f4d8adf824f711b7ad3726e3adeab5ac8ce5bdb482830ae98ad92613"


def test_approval_digest_fixed_rfc8785_golden_vector() -> None:
    issued = datetime(2026, 8, 24, 0, 0, 1, 999999, tzinfo=UTC)
    challenge = ConfirmationChallenge(
        id="cch_" + "1" * 32,
        schema_version=1,
        intent_contract_version=1,
        purpose=ConfirmationPurpose.PROVIDER_SECRET_PROVISION,
        state=ConfirmationChallengeState.ISSUED,
        admin_user_id="adm_" + "2" * 32,
        control_plane_session_id="ses_" + "3" * 32,
        auth_epoch=3,
        recent_authenticated_at=datetime(2026, 8, 24, tzinfo=UTC),
        issue_request_id="req_golden",
        provisioning_intent_id="psi_" + "4" * 32,
        runtime_installation_id="rti_" + "5" * 32,
        runtime_installation_revision=7,
        runtime_type=RuntimeType.CODEX,
        provider_id="prv_" + "6" * 32,
        provider_revision=11,
        provider_state=ProviderLifecycleState.CONFIGURED,
        credential_id="crd_" + "7" * 32,
        credential_revision=13,
        credential_kind=CredentialKind.API_KEY,
        credential_state=CredentialLifecycleState.MISSING,
        expected_runtime_secret_ref=None,
        expected_secret_version=None,
        credential_runtime_installation_id="rti_" + "5" * 32,
        intended_state=CredentialLifecycleState.CONFIGURED,
        intended_secret_version=1,
        confirmation_verifier="a" * 64,
        approval_digest=_GOLDEN_DIGEST,
        issued_at=issued,
        created_at=issued,
        expires_at=issued + timedelta(seconds=300),
        intent_issued_at=issued,
        intent_expires_at=issued + timedelta(seconds=300),
        initial_cancellation_epoch=0,
        cancellation_epoch=0,
        last_observed_at=issued,
        terminal_at=None,
        consumed_at=None,
        consumed_request_id=None,
        terminal_result_code=None,
        retention_eligible_at=None,
    )
    document = approval_document(challenge)
    assert rfc8785.dumps(cast(Any, document)) == _GOLDEN_CANONICAL
    assert rfc8785.dumps(cast(Any, dict(reversed(list(document.items()))))) == _GOLDEN_CANONICAL
    assert approval_digest(challenge) == _GOLDEN_DIGEST
    # Display-only Unicode cannot enter the closed authority document.
    challenge.__dict__["display_name"] = "审批 café 😀"
    assert approval_document(challenge) == document
    assert approval_digest(challenge) == _GOLDEN_DIGEST
    challenge.cancellation_epoch = 1
    assert approval_digest(challenge) != _GOLDEN_DIGEST
    challenge.cancellation_epoch = 0
    challenge.provisioning_intent_id = "psi_" + "8" * 32
    assert approval_digest(challenge) != _GOLDEN_DIGEST


def test_rfc8785_unicode_golden_bytes() -> None:
    # UTF-16 key ordering, literal UTF-8 (not ASCII escaping), no normalization.
    assert rfc8785.dumps({"\ue000": "café", "😀": "审批", "null": None, "integer": 7}) == (
        '{"integer":7,"null":null,"😀":"审批","\ue000":"café"}'.encode("utf-8")
    )


@pytest.mark.parametrize("operation", ["logout", "revoke", "password"])
def test_session_invalidation_clock_rollback_is_durable(
    initialized_services: ControlPlaneServices, clock: AdvancingClock, operation: str
) -> None:
    services = initialized_services
    authenticated, values = _authority(services)
    challenge = services.approvals.issue(authenticated, values, request_id="req_invalidation")
    clock.current -= timedelta(microseconds=1)
    if operation == "logout":
        services.sessions.revoke(authenticated, request_id="req_logout")
    elif operation == "revoke":
        services.admin.revoke_sessions(PASSWORD, request_id="req_revoke")
    else:
        services.admin.change_password(
            PASSWORD, "a different long test passphrase", request_id="req_password"
        )
    with sqlite3.connect(str(services.database.engine.url.database)) as connection:
        assert connection.execute(
            "SELECT state,terminal_result_code,cancellation_epoch "
            "FROM confirmation_challenges WHERE id=?",
            (challenge.id,),
        ).fetchone() == ("cancelled", "CLOCK_ROLLBACK_DETECTED", 1)
        assert connection.execute(
            "SELECT count(*) FROM provider_secret_provisioning_attempts"
        ).fetchone() == (0,)


@pytest.mark.parametrize("expiry_column", ["expires_at", "idle_expires_at"])
def test_cancel_rollback_precedes_expired_session(
    initialized_services: ControlPlaneServices, clock: AdvancingClock, expiry_column: str
) -> None:
    services = initialized_services
    authenticated, values = _authority(services)
    clock.advance(seconds=10)
    challenge = services.approvals.issue(authenticated, values, request_id="req_expired_session")
    with services.database.transaction() as session:
        session.execute(
            text(f"UPDATE sessions SET {expiry_column}=created_at WHERE id=:id"),
            {"id": authenticated.session_id},
        )
    clock.current -= timedelta(microseconds=1)
    with pytest.raises(ApprovalUnavailable):
        services.approvals.cancel_challenge(
            authenticated, challenge.id, request_id="req_cancel_expired"
        )
    with sqlite3.connect(str(services.database.engine.url.database)) as connection:
        assert connection.execute(
            "SELECT state,terminal_result_code,cancellation_epoch "
            "FROM confirmation_challenges WHERE id=?",
            (challenge.id,),
        ).fetchone() == ("cancelled", "CLOCK_ROLLBACK_DETECTED", 1)
        assert connection.execute(
            "SELECT count(*) FROM provider_secret_provisioning_attempts"
        ).fetchone() == (0,)


def test_maintenance_clock_rollback_precedes_expiry(
    initialized_services: ControlPlaneServices,
    clock: AdvancingClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = initialized_services
    authenticated, values = _authority(services)
    original = services.audit.record

    def insert_future_observation(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("action") == "provider_secret.challenge_issued":
            for pending in args[0].new:
                if isinstance(pending, ConfirmationChallenge):
                    # Adversarial initial row, admitted by unchanged SQL constraints.
                    pending.last_observed_at = pending.expires_at + timedelta(microseconds=1)
        return original(*args, **kwargs)

    monkeypatch.setattr(services.audit, "record", insert_future_observation)
    challenge = services.approvals.issue(authenticated, values, request_id="req_maintenance_clock")
    monkeypatch.undo()
    clock.advance(seconds=300)
    result = services.approvals.maintenance()
    assert result.approval_expired_count == 0
    with sqlite3.connect(str(services.database.engine.url.database)) as connection:
        assert connection.execute(
            "SELECT state,terminal_result_code,cancellation_epoch,terminal_at "
            "FROM confirmation_challenges WHERE id=?",
            (challenge.id,),
        ).fetchone() == (
            "cancelled",
            "CLOCK_ROLLBACK_DETECTED",
            1,
            challenge.last_observed_at.strftime("%Y-%m-%d %H:%M:%S.%f"),
        )
        assert connection.execute(
            "SELECT count(*) FROM provider_secret_provisioning_attempts"
        ).fetchone() == (0,)
