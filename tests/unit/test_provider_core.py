from __future__ import annotations

from dataclasses import fields
from datetime import timedelta

import pytest
from agentbox_core.errors import (
    ProviderInputInvalid,
    ProviderMetadataConflict,
    ProviderMetadataNotFound,
    ProviderRevisionConflict,
)
from agentbox_core.provider_models import (
    CompatibilityDimension,
    CompatibilityEvidenceCode,
    CompatibilityState,
    CredentialKind,
    CredentialLifecycleState,
    Provider,
    ProviderCompatibilityEvidenceSet,
    ProviderCompatibilityObservation,
    ProviderCredential,
    ProviderLifecycleState,
    ProviderType,
    RuntimeBindingState,
    RuntimeInstallation,
    RuntimeProviderBinding,
    RuntimeProviderProfile,
    RuntimeSessionProviderBinding,
    RuntimeType,
    SessionEvidenceClass,
)
from agentbox_core.providers import (
    CompatibilityDimensionResult,
    CompatibilityEvidenceSetCreate,
    CredentialMetadataCreate,
    ProviderCreate,
    RuntimeBindingCreate,
    RuntimeProfileCreate,
    RuntimeProviderManagement,
    SessionBindingCreate,
)
from agentbox_core.services import ControlPlaneServices
from conftest import FakeClock
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError

ACTOR_ID = "adm_00000000000000000000000000000000"
SECRET_REFERENCE = "sec_11111111111111111111111111111111"


def _runtime(
    services: ControlPlaneServices, *, runtime_type: RuntimeType = RuntimeType.CODEX
) -> RuntimeInstallation:
    return services.providers.register_runtime_installation(
        runtime_type=runtime_type,
        display_name=f"{runtime_type.value} fixture",
        actor_id=ACTOR_ID,
    )


def _provider(
    services: ControlPlaneServices,
    *,
    display_name: str = "OpenAI fixture",
    model: str = "gpt-5",
) -> Provider:
    return services.providers.create_provider(
        ProviderCreate(
            display_name=display_name,
            provider_type=ProviderType.OFFICIAL_OPENAI,
            model=model,
        ),
        actor_id=ACTOR_ID,
    )


def _profile(
    services: ControlPlaneServices, runtime_id: str, provider_id: str, revision: int
) -> RuntimeProviderProfile:
    return services.providers.create_runtime_profile(
        RuntimeProfileCreate(
            runtime_installation_id=runtime_id,
            provider_id=provider_id,
            provider_revision=revision,
            adapter_schema_version=1,
        ),
        actor_id=ACTOR_ID,
    )


def _binding(
    services: ControlPlaneServices,
    runtime_id: str,
    profile_id: str,
    revision: int,
    *,
    previous_binding_id: str | None = None,
) -> RuntimeProviderBinding:
    return services.providers.create_runtime_binding(
        RuntimeBindingCreate(
            runtime_installation_id=runtime_id,
            runtime_profile_id=profile_id,
            runtime_profile_revision=revision,
            previous_binding_id=previous_binding_id,
        ),
        actor_id=ACTOR_ID,
    )


def _activate_binding(
    services: ControlPlaneServices, binding: RuntimeProviderBinding
) -> RuntimeProviderBinding:
    with services.database.transaction() as session:
        session.execute(
            update(RuntimeProviderBinding)
            .where(RuntimeProviderBinding.id == binding.id)
            .values(state=RuntimeBindingState.ACTIVE)
        )
    return services.providers.get_runtime_binding(binding.id)


def _configured_credential_metadata(
    services: ControlPlaneServices, provider: Provider
) -> ProviderCredential:
    """Simulate a future Runtime-attested result directly at the persistence boundary."""

    credential = services.providers.create_credential_metadata(
        CredentialMetadataCreate(provider_id=provider.id, kind=CredentialKind.API_KEY),
        actor_id=ACTOR_ID,
    )
    with services.database.transaction() as session:
        session.execute(
            update(ProviderCredential)
            .where(ProviderCredential.id == credential.id)
            .values(
                runtime_secret_ref=SECRET_REFERENCE,
                secret_version=1,
                state=CredentialLifecycleState.CONFIGURED,
                revision=2,
            )
        )
    return services.providers.get_credential_metadata(credential.id)


def _result(
    dimension: CompatibilityDimension,
    state: CompatibilityState,
) -> CompatibilityDimensionResult:
    codes = {
        CompatibilityState.PASS: CompatibilityEvidenceCode.VALIDATION_PASSED,
        CompatibilityState.FAIL: CompatibilityEvidenceCode.VALIDATION_FAILED,
        CompatibilityState.UNSUPPORTED: CompatibilityEvidenceCode.UNSUPPORTED_CONTRACT,
        CompatibilityState.EXPERIMENTAL: CompatibilityEvidenceCode.EXPERIMENTAL_CONTRACT,
        CompatibilityState.UNKNOWN: CompatibilityEvidenceCode.UNKNOWN_EVIDENCE,
        CompatibilityState.NOT_TESTED: CompatibilityEvidenceCode.NOT_EXECUTED,
    }
    return CompatibilityDimensionResult(
        dimension=dimension, state=state, evidence_code=codes[state]
    )


def test_registered_runtime_without_binding_is_unmanaged_but_unknown_runtime_is_not_found(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services)

    assert services.providers.runtime_management(runtime.id) == RuntimeProviderManagement(
        runtime_installation_id=runtime.id,
        state=RuntimeBindingState.UNMANAGED,
        runtime_binding_id=None,
        binding_revision=None,
    )
    with pytest.raises(ProviderMetadataNotFound):
        services.providers.runtime_management("rti_ffffffffffffffffffffffffffffffff")


def test_provider_identities_and_relationships_remain_independent(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)
    credential = services.providers.create_credential_metadata(
        CredentialMetadataCreate(provider_id=provider.id, kind=CredentialKind.API_KEY),
        actor_id=ACTOR_ID,
    )
    profile = _profile(services, runtime.id, provider.id, provider.revision)
    binding = _binding(services, runtime.id, profile.id, profile.revision)

    assert len({runtime.id, provider.id, credential.id, profile.id, binding.id}) == 5
    assert credential.provider_id == provider.id
    assert profile.runtime_installation_id == runtime.id
    assert profile.provider_id == provider.id
    assert profile.credential_id is None
    assert binding.runtime_profile_id == profile.id
    assert binding.state is RuntimeBindingState.PENDING


@pytest.mark.parametrize(
    ("operation", "wrong_id"),
    [
        ("provider", "rti_11111111111111111111111111111111"),
        ("credential", "prv_11111111111111111111111111111111"),
        ("profile", "crd_11111111111111111111111111111111"),
        ("binding", "rpf_11111111111111111111111111111111"),
        ("session_binding", "ses_11111111111111111111111111111111"),
        ("runtime", "prv_11111111111111111111111111111111"),
    ],
)
def test_repository_rejects_wrong_typed_identity_prefix(
    services: ControlPlaneServices, operation: str, wrong_id: str
) -> None:
    calls = {
        "provider": services.providers.get_provider,
        "credential": services.providers.get_credential_metadata,
        "profile": services.providers.get_runtime_profile,
        "binding": services.providers.get_runtime_binding,
        "session_binding": services.providers.get_session_binding,
        "runtime": services.providers.runtime_management,
    }
    with pytest.raises(ProviderInputInvalid):
        calls[operation](wrong_id)


def test_provider_and_lifecycle_enums_are_closed_contracts() -> None:
    assert {item.value for item in ProviderType} == {
        "official_openai",
        "openai_compatible",
    }
    assert RuntimeBindingState.UNMANAGED.value == "unmanaged"
    assert RuntimeBindingState.ACTIVE.value == "active"
    assert CompatibilityState.UNKNOWN.value == "unknown"
    assert CompatibilityState.NOT_TESTED.value == "not_tested"
    with pytest.raises(ValueError):
        ProviderType("local")
    with pytest.raises(ValueError):
        ProviderType("claude")


def test_provider_validation_revision_and_audit_metadata(
    services: ControlPlaneServices,
) -> None:
    provider = services.providers.create_provider(
        ProviderCreate(
            display_name="Compatible fixture",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            endpoint="https://EXAMPLE.com/v1/",
            model="example-model",
        ),
        actor_id=ACTOR_ID,
        request_id="req-provider-create",
    )
    assert provider.endpoint == "https://example.com/v1"
    assert provider.state is ProviderLifecycleState.CONFIGURED
    assert provider.revision == 1

    updated = services.providers.update_provider_display_name(
        provider.id,
        display_name="Renamed fixture",
        expected_revision=1,
        actor_id=ACTOR_ID,
    )
    assert updated.revision == 2
    with pytest.raises(ProviderRevisionConflict):
        services.providers.update_provider_display_name(
            provider.id,
            display_name="Stale update",
            expected_revision=1,
            actor_id=ACTOR_ID,
        )

    with services.database.transaction() as session:
        rows = session.execute(
            text(
                "SELECT action, metadata_json FROM audit_events "
                "WHERE target_id = :target ORDER BY created_at"
            ),
            {"target": provider.id},
        ).all()
    assert [row[0] for row in rows] == ["provider.created", "provider.updated"]
    assert SECRET_REFERENCE not in repr(rows)
    assert "example-model" not in repr(rows)
    assert "example.com" not in repr(rows)


@pytest.mark.parametrize(
    ("provider_type", "endpoint"),
    [
        (ProviderType.OFFICIAL_OPENAI, "https://example.com/v1"),
        (ProviderType.OPENAI_COMPATIBLE, None),
        (ProviderType.OPENAI_COMPATIBLE, "http://example.com/v1"),
        (ProviderType.OPENAI_COMPATIBLE, "https://127.0.0.1/v1"),
        (ProviderType.OPENAI_COMPATIBLE, "https://user@example.com/v1"),
        (ProviderType.OPENAI_COMPATIBLE, "https://example.com/v1?key=value"),
    ],
)
def test_provider_endpoint_policy_rejects_unsafe_identity_metadata(
    services: ControlPlaneServices,
    provider_type: ProviderType,
    endpoint: str | None,
) -> None:
    with pytest.raises(ProviderInputInvalid):
        services.providers.create_provider(
            ProviderCreate(
                display_name="Rejected fixture",
                provider_type=provider_type,
                endpoint=endpoint,
                model="fixture",
            ),
            actor_id=ACTOR_ID,
        )


def test_slice_one_credential_creation_is_missing_metadata_only(
    services: ControlPlaneServices,
) -> None:
    provider = _provider(services)
    assert {field.name for field in fields(CredentialMetadataCreate)} == {
        "provider_id",
        "kind",
    }

    credential = services.providers.create_credential_metadata(
        CredentialMetadataCreate(provider_id=provider.id, kind=CredentialKind.API_KEY),
        actor_id=ACTOR_ID,
    )
    assert credential.runtime_secret_ref is None
    assert credential.secret_version is None
    assert credential.state is CredentialLifecycleState.MISSING
    assert credential.revision == 1
    assert not hasattr(services.providers, "update_credential_state")


@pytest.mark.parametrize(
    ("state", "runtime_secret_ref", "secret_version"),
    [
        (CredentialLifecycleState.MISSING, SECRET_REFERENCE, 1),
        (CredentialLifecycleState.CONFIGURED, None, None),
        (CredentialLifecycleState.ROTATING, SECRET_REFERENCE, None),
        (CredentialLifecycleState.REVOKED, None, 1),
    ],
)
def test_database_enforces_credential_state_reference_consistency(
    services: ControlPlaneServices,
    state: CredentialLifecycleState,
    runtime_secret_ref: str | None,
    secret_version: int | None,
) -> None:
    provider = _provider(services)
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(
            ProviderCredential(
                id="crd_22222222222222222222222222222222",
                provider_id=provider.id,
                kind=CredentialKind.API_KEY,
                runtime_secret_ref=runtime_secret_ref,
                secret_version=secret_version,
                state=state,
                revision=1,
                created_at=services.providers._clock.now(),
                updated_at=services.providers._clock.now(),
            )
        )
        session.flush()


def test_claude_runtime_profile_is_rejected_by_repository_and_database(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services, runtime_type=RuntimeType.CLAUDE)
    provider = _provider(services)
    with pytest.raises(ProviderInputInvalid):
        _profile(services, runtime.id, provider.id, provider.revision)

    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.execute(
            text(
                "INSERT INTO runtime_provider_profiles "
                "(id, runtime_installation_id, provider_id, provider_revision, credential_id, "
                "credential_revision, credential_secret_version, adapter_type, "
                "adapter_schema_version, state, revision, created_at, updated_at) VALUES "
                "(:id, :runtime, :provider, 1, NULL, NULL, NULL, 'claude', 1, 'draft', 1, "
                ":created, :updated)"
            ),
            {
                "id": "rpf_22222222222222222222222222222222",
                "runtime": runtime.id,
                "provider": provider.id,
                "created": services.providers._clock.now(),
                "updated": services.providers._clock.now(),
            },
        )


def test_binding_history_and_same_runtime_previous_binding_integrity(
    services: ControlPlaneServices,
) -> None:
    first_runtime = _runtime(services)
    first_provider = _provider(services, model="gpt-5-first")
    first_profile = _profile(services, first_runtime.id, first_provider.id, first_provider.revision)
    first = _binding(services, first_runtime.id, first_profile.id, first_profile.revision)
    second = _binding(
        services,
        first_runtime.id,
        first_profile.id,
        first_profile.revision,
        previous_binding_id=first.id,
    )
    assert second.previous_binding_id == first.id
    assert second.state is RuntimeBindingState.PENDING

    other_runtime = _runtime(services)
    other_provider = _provider(services, display_name="Other", model="gpt-5-other")
    other_profile = _profile(services, other_runtime.id, other_provider.id, other_provider.revision)
    with pytest.raises(ProviderMetadataConflict):
        _binding(
            services,
            other_runtime.id,
            other_profile.id,
            other_profile.revision,
            previous_binding_id=first.id,
        )
    now = services.providers._clock.now()
    cross_runtime = RuntimeProviderBinding(
        id="rbd_33333333333333333333333333333333",
        runtime_installation_id=other_runtime.id,
        runtime_profile_id=other_profile.id,
        runtime_profile_revision=other_profile.revision,
        provider_id=other_provider.id,
        provider_revision=other_provider.revision,
        state=RuntimeBindingState.PENDING,
        previous_binding_id=first.id,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(cross_runtime)
        session.flush()

    self_id = "rbd_44444444444444444444444444444444"
    self_referencing = RuntimeProviderBinding(
        id=self_id,
        runtime_installation_id=other_runtime.id,
        runtime_profile_id=other_profile.id,
        runtime_profile_revision=other_profile.revision,
        provider_id=other_provider.id,
        provider_revision=other_provider.revision,
        state=RuntimeBindingState.PENDING,
        previous_binding_id=self_id,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(self_referencing)
        session.flush()


def test_database_allows_pending_history_but_only_one_active_binding(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)
    profile = _profile(services, runtime.id, provider.id, provider.revision)
    first = _binding(services, runtime.id, profile.id, profile.revision)
    second = _binding(services, runtime.id, profile.id, profile.revision)

    _activate_binding(services, first)
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.execute(
            update(RuntimeProviderBinding)
            .where(RuntimeProviderBinding.id == second.id)
            .values(state=RuntimeBindingState.ACTIVE)
        )

    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.execute(
            update(RuntimeProviderBinding)
            .where(RuntimeProviderBinding.id == second.id)
            .values(state=RuntimeBindingState.UNMANAGED)
        )


def test_session_binding_requires_an_active_exact_snapshot_and_is_immutable(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)
    profile = _profile(services, runtime.id, provider.id, provider.revision)
    pending = _binding(services, runtime.id, profile.id, profile.revision)
    with pytest.raises(ProviderMetadataConflict):
        services.providers.create_session_binding(
            SessionBindingCreate(
                runtime_session_id="ses_11111111111111111111111111111111",
                runtime_binding_id=pending.id,
                runtime_binding_revision=pending.revision,
                evidence_class=SessionEvidenceClass.AGENTBOX_CREATED,
            ),
            actor_id=ACTOR_ID,
        )
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(
            RuntimeSessionProviderBinding(
                id="sbd_11111111111111111111111111111111",
                runtime_session_id="ses_11111111111111111111111111111111",
                runtime_installation_id=pending.runtime_installation_id,
                runtime_binding_id=pending.id,
                runtime_binding_revision=pending.revision,
                runtime_profile_id=pending.runtime_profile_id,
                runtime_profile_revision=pending.runtime_profile_revision,
                provider_id=pending.provider_id,
                provider_revision=pending.provider_revision,
                evidence_class=SessionEvidenceClass.AGENTBOX_CREATED,
                effective_at=services.providers._clock.now(),
                created_at=services.providers._clock.now(),
            )
        )
        session.flush()

    active = _activate_binding(services, pending)
    session_binding = services.providers.create_session_binding(
        SessionBindingCreate(
            runtime_session_id="ses_22222222222222222222222222222222",
            runtime_binding_id=active.id,
            runtime_binding_revision=active.revision,
            evidence_class=SessionEvidenceClass.AGENTBOX_CREATED,
        ),
        actor_id=ACTOR_ID,
    )
    assert session_binding.runtime_binding_id == active.id
    assert not hasattr(session_binding, "state")

    with (
        pytest.raises(IntegrityError, match="session bindings are immutable"),
        services.database.transaction() as session,
    ):
        session.execute(
            update(RuntimeSessionProviderBinding)
            .where(RuntimeSessionProviderBinding.id == session_binding.id)
            .values(provider_revision=99)
        )
    with (
        pytest.raises(IntegrityError, match="session bindings are immutable"),
        services.database.transaction() as session,
    ):
        session.execute(
            delete(RuntimeSessionProviderBinding).where(
                RuntimeSessionProviderBinding.id == session_binding.id
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("runtime_binding_revision", 2),
        ("runtime_profile_revision", 2),
        ("provider_revision", 2),
        ("runtime_installation_id", "rti_ffffffffffffffffffffffffffffffff"),
        ("runtime_profile_id", "rpf_ffffffffffffffffffffffffffffffff"),
        ("provider_id", "prv_ffffffffffffffffffffffffffffffff"),
    ],
)
def test_database_rejects_inexact_session_binding_snapshot(
    services: ControlPlaneServices, field: str, value: object
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)
    profile = _profile(services, runtime.id, provider.id, provider.revision)
    active = _activate_binding(
        services, _binding(services, runtime.id, profile.id, profile.revision)
    )
    values: dict[str, object] = {
        "id": "sbd_33333333333333333333333333333333",
        "runtime_session_id": "ses_33333333333333333333333333333333",
        "runtime_installation_id": active.runtime_installation_id,
        "runtime_binding_id": active.id,
        "runtime_binding_revision": active.revision,
        "runtime_profile_id": active.runtime_profile_id,
        "runtime_profile_revision": active.runtime_profile_revision,
        "provider_id": active.provider_id,
        "provider_revision": active.provider_revision,
        "evidence_class": SessionEvidenceClass.PUBLIC_RUNTIME,
        "effective_at": services.providers._clock.now(),
        "created_at": services.providers._clock.now(),
    }
    values[field] = value
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(RuntimeSessionProviderBinding(**values))
        session.flush()


def test_provider_only_compatibility_evidence_is_atomic_scoped_and_server_identified(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    provider = _provider(services)
    recorded = services.providers.record_compatibility_evidence_set(
        CompatibilityEvidenceSetCreate(
            provider_id=provider.id,
            provider_revision=provider.revision,
            evidence_schema_version=1,
            expires_at=clock.now() + timedelta(minutes=10),
            results=(
                _result(CompatibilityDimension.NETWORK, CompatibilityState.UNKNOWN),
                _result(CompatibilityDimension.AUTHENTICATION, CompatibilityState.NOT_TESTED),
            ),
        ),
        actor_id=ACTOR_ID,
    )
    assert recorded.evidence_set.id.startswith("ces_")
    assert recorded.evidence_set.provider_id == provider.id
    assert recorded.evidence_set.provider_revision == provider.revision
    assert recorded.evidence_set.runtime_profile_id is None
    assert recorded.evidence_set.credential_id is None
    assert {item.dimension for item in recorded.observations} == {
        CompatibilityDimension.NETWORK,
        CompatibilityDimension.AUTHENTICATION,
    }
    assert all(item.evidence_set_id == recorded.evidence_set.id for item in recorded.observations)
    with services.database.transaction() as session:
        audit_rows = session.execute(
            text("SELECT action, metadata_json FROM audit_events " "WHERE target_id = :target"),
            {"target": recorded.evidence_set.id},
        ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == "compatibility_evidence_set.recorded"
    assert SECRET_REFERENCE not in repr(audit_rows)

    other = _provider(services, display_name="Other", model="gpt-5-other")
    other_recorded = services.providers.record_compatibility_evidence_set(
        CompatibilityEvidenceSetCreate(
            provider_id=other.id,
            provider_revision=other.revision,
            evidence_schema_version=1,
            expires_at=clock.now() + timedelta(minutes=10),
            results=(_result(CompatibilityDimension.NETWORK, CompatibilityState.NOT_TESTED),),
        ),
        actor_id=ACTOR_ID,
    )
    assert other_recorded.evidence_set.id != recorded.evidence_set.id
    assert other_recorded.evidence_set.provider_id == other.id


def test_runtime_and_credential_scoped_compatibility_evidence_keeps_exact_revisions(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)
    profile = _profile(services, runtime.id, provider.id, provider.revision)
    credential = _configured_credential_metadata(services, provider)

    recorded = services.providers.record_compatibility_evidence_set(
        CompatibilityEvidenceSetCreate(
            provider_id=provider.id,
            provider_revision=provider.revision,
            runtime_installation_id=runtime.id,
            runtime_profile_id=profile.id,
            runtime_profile_revision=profile.revision,
            credential_id=credential.id,
            credential_revision=credential.revision,
            credential_secret_version=credential.secret_version,
            evidence_schema_version=1,
            expires_at=clock.now() + timedelta(minutes=10),
            results=(
                _result(CompatibilityDimension.CODEX_RUNTIME, CompatibilityState.UNKNOWN),
                _result(CompatibilityDimension.AUTHENTICATION, CompatibilityState.PASS),
            ),
        ),
        actor_id=ACTOR_ID,
    )
    evidence = recorded.evidence_set
    assert evidence.runtime_installation_id == runtime.id
    assert evidence.runtime_profile_id == profile.id
    assert evidence.runtime_profile_revision == profile.revision
    assert evidence.credential_id == credential.id
    assert evidence.credential_revision == credential.revision
    assert evidence.credential_secret_version == credential.secret_version


def test_compatibility_evidence_cannot_mix_provider_or_profile_scope(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    first_runtime = _runtime(services)
    second_runtime = _runtime(services)
    first_provider = _provider(services, model="gpt-5-first")
    second_provider = _provider(services, display_name="Second", model="gpt-5-second")
    first_profile = _profile(services, first_runtime.id, first_provider.id, first_provider.revision)
    second_profile = _profile(
        services, second_runtime.id, second_provider.id, second_provider.revision
    )
    with pytest.raises(ProviderMetadataConflict):
        services.providers.record_compatibility_evidence_set(
            CompatibilityEvidenceSetCreate(
                provider_id=first_provider.id,
                provider_revision=first_provider.revision,
                runtime_installation_id=second_runtime.id,
                runtime_profile_id=first_profile.id,
                runtime_profile_revision=first_profile.revision,
                evidence_schema_version=1,
                expires_at=clock.now() + timedelta(minutes=10),
                results=(
                    _result(CompatibilityDimension.CODEX_RUNTIME, CompatibilityState.UNKNOWN),
                ),
            ),
            actor_id=ACTOR_ID,
        )
    with pytest.raises(ProviderMetadataConflict):
        services.providers.record_compatibility_evidence_set(
            CompatibilityEvidenceSetCreate(
                provider_id=first_provider.id,
                provider_revision=first_provider.revision,
                runtime_installation_id=second_runtime.id,
                runtime_profile_id=second_profile.id,
                runtime_profile_revision=second_profile.revision,
                evidence_schema_version=1,
                expires_at=clock.now() + timedelta(minutes=10),
                results=(
                    _result(CompatibilityDimension.CODEX_RUNTIME, CompatibilityState.UNKNOWN),
                ),
            ),
            actor_id=ACTOR_ID,
        )


@pytest.mark.parametrize(
    "values",
    [
        (CompatibilityDimension.CODEX_RUNTIME, CompatibilityState.UNKNOWN, False),
        (CompatibilityDimension.REMOTE, CompatibilityState.NOT_TESTED, False),
        (CompatibilityDimension.AUTHENTICATION, CompatibilityState.PASS, False),
        (CompatibilityDimension.AUTHENTICATION, CompatibilityState.FAIL, False),
    ],
)
def test_compatibility_scope_rules_fail_closed(
    services: ControlPlaneServices,
    clock: FakeClock,
    values: tuple[CompatibilityDimension, CompatibilityState, bool],
) -> None:
    provider = _provider(services)
    dimension, state, _ = values
    with pytest.raises(ProviderInputInvalid):
        services.providers.record_compatibility_evidence_set(
            CompatibilityEvidenceSetCreate(
                provider_id=provider.id,
                provider_revision=provider.revision,
                evidence_schema_version=1,
                expires_at=clock.now() + timedelta(minutes=10),
                results=(_result(dimension, state),),
            ),
            actor_id=ACTOR_ID,
        )


def test_compatibility_rejects_duplicates_invalid_expiry_and_state_code_mismatch(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    provider = _provider(services)
    with pytest.raises(ProviderInputInvalid):
        services.providers.record_compatibility_evidence_set(
            CompatibilityEvidenceSetCreate(
                provider_id=provider.id,
                provider_revision=provider.revision,
                evidence_schema_version=1,
                expires_at=clock.now() + timedelta(minutes=10),
                results=(
                    _result(CompatibilityDimension.NETWORK, CompatibilityState.UNKNOWN),
                    _result(CompatibilityDimension.NETWORK, CompatibilityState.NOT_TESTED),
                ),
            ),
            actor_id=ACTOR_ID,
        )
    with pytest.raises(ProviderInputInvalid):
        services.providers.record_compatibility_evidence_set(
            CompatibilityEvidenceSetCreate(
                provider_id=provider.id,
                provider_revision=provider.revision,
                evidence_schema_version=1,
                expires_at=clock.now(),
                results=(_result(CompatibilityDimension.NETWORK, CompatibilityState.UNKNOWN),),
            ),
            actor_id=ACTOR_ID,
        )
    with pytest.raises(ProviderInputInvalid):
        services.providers.record_compatibility_evidence_set(
            CompatibilityEvidenceSetCreate(
                provider_id=provider.id,
                provider_revision=provider.revision,
                evidence_schema_version=1,
                expires_at=clock.now() + timedelta(minutes=10),
                results=(
                    CompatibilityDimensionResult(
                        dimension=CompatibilityDimension.NETWORK,
                        state=CompatibilityState.PASS,
                        evidence_code=CompatibilityEvidenceCode.NOT_EXECUTED,
                    ),
                ),
            ),
            actor_id=ACTOR_ID,
        )


def test_database_compatibility_scope_and_immutability_rules_fail_closed(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    provider = _provider(services)
    recorded = services.providers.record_compatibility_evidence_set(
        CompatibilityEvidenceSetCreate(
            provider_id=provider.id,
            provider_revision=provider.revision,
            evidence_schema_version=1,
            expires_at=clock.now() + timedelta(minutes=10),
            results=(_result(CompatibilityDimension.NETWORK, CompatibilityState.UNKNOWN),),
        ),
        actor_id=ACTOR_ID,
    )
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(
            ProviderCompatibilityObservation(
                id="pco_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                evidence_set_id=recorded.evidence_set.id,
                dimension=CompatibilityDimension.CODEX_RUNTIME,
                state=CompatibilityState.UNKNOWN,
                evidence_code=CompatibilityEvidenceCode.UNKNOWN_EVIDENCE,
            )
        )
        session.flush()
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(
            ProviderCompatibilityObservation(
                id="pco_cccccccccccccccccccccccccccccccc",
                evidence_set_id=recorded.evidence_set.id,
                dimension=CompatibilityDimension.MODEL,
                state=CompatibilityState.PASS,
                evidence_code=CompatibilityEvidenceCode.NOT_EXECUTED,
            )
        )
        session.flush()
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.add(
            ProviderCompatibilityObservation(
                id="pco_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                evidence_set_id=recorded.evidence_set.id,
                dimension=CompatibilityDimension.AUTHENTICATION,
                state=CompatibilityState.FAIL,
                evidence_code=CompatibilityEvidenceCode.VALIDATION_FAILED,
            )
        )
        session.flush()
    with (
        pytest.raises(IntegrityError, match="compatibility evidence is immutable"),
        services.database.transaction() as session,
    ):
        session.execute(
            update(ProviderCompatibilityEvidenceSet)
            .where(ProviderCompatibilityEvidenceSet.id == recorded.evidence_set.id)
            .values(provider_revision=2)
        )
    with (
        pytest.raises(IntegrityError, match="compatibility evidence is immutable"),
        services.database.transaction() as session,
    ):
        session.execute(
            delete(ProviderCompatibilityObservation).where(
                ProviderCompatibilityObservation.id == recorded.observations[0].id
            )
        )


def test_management_read_model_fields_are_bounded_and_non_generic() -> None:
    assert {field.name for field in fields(RuntimeProviderManagement)} == {
        "runtime_installation_id",
        "state",
        "runtime_binding_id",
        "binding_revision",
    }
