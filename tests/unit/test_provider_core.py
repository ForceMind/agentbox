from __future__ import annotations

from dataclasses import fields

import pytest
from agentbox_core.errors import ProviderInputInvalid, ProviderRevisionConflict
from agentbox_core.provider_models import (
    CompatibilityDimension,
    CompatibilityState,
    CredentialKind,
    CredentialLifecycleState,
    Provider,
    ProviderLifecycleState,
    ProviderType,
    RuntimeBindingState,
    RuntimeInstallation,
    RuntimeProviderBinding,
    RuntimeProviderProfile,
    RuntimeType,
    SessionBindingState,
    SessionEvidenceClass,
)
from agentbox_core.providers import (
    CompatibilityObservationCreate,
    CredentialMetadataCreate,
    ProviderCreate,
    RuntimeBindingCreate,
    RuntimeProfileCreate,
    RuntimeProviderManagement,
    SessionBindingCreate,
)
from agentbox_core.services import ControlPlaneServices
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


def _provider(services: ControlPlaneServices) -> Provider:
    return services.providers.create_provider(
        ProviderCreate(
            display_name="OpenAI fixture",
            provider_type=ProviderType.OFFICIAL_OPENAI,
            model="gpt-5",
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
    services: ControlPlaneServices, runtime_id: str, profile_id: str, revision: int
) -> RuntimeProviderBinding:
    return services.providers.create_runtime_binding(
        RuntimeBindingCreate(
            runtime_installation_id=runtime_id,
            runtime_profile_id=profile_id,
            runtime_profile_revision=revision,
        ),
        actor_id=ACTOR_ID,
    )


def test_provider_identities_relationships_and_unmanaged_read_model(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)

    unmanaged = services.providers.runtime_management(runtime.id)
    assert unmanaged == RuntimeProviderManagement(
        runtime_installation_id=runtime.id,
        state=RuntimeBindingState.UNMANAGED,
        runtime_binding_id=None,
        binding_revision=None,
    )

    credential = services.providers.create_credential_metadata(
        CredentialMetadataCreate(
            provider_id=provider.id,
            kind=CredentialKind.API_KEY,
            runtime_secret_ref=SECRET_REFERENCE,
            secret_version=1,
        ),
        actor_id=ACTOR_ID,
    )
    profile = services.providers.create_runtime_profile(
        RuntimeProfileCreate(
            runtime_installation_id=runtime.id,
            provider_id=provider.id,
            provider_revision=provider.revision,
            adapter_schema_version=1,
            credential_id=credential.id,
            credential_revision=credential.revision,
            credential_secret_version=credential.secret_version,
        ),
        actor_id=ACTOR_ID,
    )
    binding = _binding(services, runtime.id, profile.id, profile.revision)

    assert len({runtime.id, provider.id, credential.id, profile.id, binding.id}) == 5
    assert credential.provider_id == provider.id
    assert profile.runtime_installation_id == runtime.id
    assert profile.provider_id == provider.id
    assert profile.credential_id == credential.id
    assert binding.runtime_profile_id == profile.id
    assert binding.state is RuntimeBindingState.PENDING
    assert services.providers.runtime_management(runtime.id).state is RuntimeBindingState.PENDING


def test_provider_and_lifecycle_enums_are_closed_contracts() -> None:
    assert {item.value for item in ProviderType} == {
        "official_openai",
        "openai_compatible",
    }
    assert {item.value for item in ProviderLifecycleState} == {
        "configured",
        "validated",
        "needs_attention",
        "disabled",
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


def test_credential_is_metadata_only_and_revision_checked(
    services: ControlPlaneServices,
) -> None:
    provider = _provider(services)
    credential = services.providers.create_credential_metadata(
        CredentialMetadataCreate(provider_id=provider.id, kind=CredentialKind.API_KEY),
        actor_id=ACTOR_ID,
    )
    assert credential.runtime_secret_ref is None
    assert credential.secret_version is None
    assert credential.state is CredentialLifecycleState.MISSING

    changed = services.providers.update_credential_state(
        credential.id,
        state=CredentialLifecycleState.REVOKED,
        expected_revision=1,
        actor_id=ACTOR_ID,
    )
    assert changed.revision == 2
    with pytest.raises(ProviderRevisionConflict):
        services.providers.update_credential_state(
            credential.id,
            state=CredentialLifecycleState.NEEDS_ATTENTION,
            expected_revision=1,
            actor_id=ACTOR_ID,
        )
    with pytest.raises(ProviderInputInvalid):
        services.providers.update_credential_state(
            credential.id,
            state=CredentialLifecycleState.CONFIGURED,
            expected_revision=2,
            actor_id=ACTOR_ID,
        )


def test_claude_runtime_does_not_gain_provider_profile(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services, runtime_type=RuntimeType.CLAUDE)
    provider = _provider(services)
    with pytest.raises(ProviderInputInvalid):
        _profile(services, runtime.id, provider.id, provider.revision)


def test_database_allows_pending_history_but_only_one_active_binding(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)
    profile = _profile(services, runtime.id, provider.id, provider.revision)
    first = _binding(services, runtime.id, profile.id, profile.revision)
    second = _binding(services, runtime.id, profile.id, profile.revision)

    with services.database.transaction() as session:
        session.execute(
            update(RuntimeProviderBinding)
            .where(RuntimeProviderBinding.id == first.id)
            .values(state=RuntimeBindingState.ACTIVE)
        )
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.execute(
            update(RuntimeProviderBinding)
            .where(RuntimeProviderBinding.id == second.id)
            .values(state=RuntimeBindingState.ACTIVE)
        )

    assert services.providers.get_runtime_binding(first.id).state is RuntimeBindingState.ACTIVE
    assert services.providers.get_runtime_binding(second.id).state is RuntimeBindingState.PENDING
    with pytest.raises(IntegrityError), services.database.transaction() as session:
        session.execute(
            update(RuntimeProviderBinding)
            .where(RuntimeProviderBinding.id == second.id)
            .values(state=RuntimeBindingState.UNMANAGED)
        )


def test_session_binding_is_immutable_historical_evidence(
    services: ControlPlaneServices,
) -> None:
    runtime = _runtime(services)
    provider = _provider(services)
    profile = _profile(services, runtime.id, provider.id, provider.revision)
    binding = _binding(services, runtime.id, profile.id, profile.revision)
    with services.database.transaction() as session:
        session.execute(
            update(RuntimeProviderBinding)
            .where(RuntimeProviderBinding.id == binding.id)
            .values(state=RuntimeBindingState.ACTIVE)
        )

    session_binding = services.providers.create_session_binding(
        SessionBindingCreate(
            runtime_session_id="ses_22222222222222222222222222222222",
            runtime_binding_id=binding.id,
            runtime_binding_revision=binding.revision,
            evidence_class=SessionEvidenceClass.AGENTBOX_CREATED,
        ),
        actor_id=ACTOR_ID,
    )
    assert session_binding.state is SessionBindingState.BOUND
    assert session_binding.runtime_binding_id == binding.id

    with (
        pytest.raises(IntegrityError, match="session bindings are immutable"),
        services.database.transaction() as session,
    ):
        session.execute(
            update(type(session_binding))
            .where(type(session_binding).id == session_binding.id)
            .values(state=SessionBindingState.RETIRED)
        )
    with (
        pytest.raises(IntegrityError, match="session bindings are immutable"),
        services.database.transaction() as session,
    ):
        session.execute(
            delete(type(session_binding)).where(type(session_binding).id == session_binding.id)
        )
    assert (
        services.providers.get_session_binding(session_binding.id).state
        is SessionBindingState.BOUND
    )


def test_compatibility_observations_are_typed_dimensions(
    services: ControlPlaneServices,
) -> None:
    provider = _provider(services)
    states = {
        CompatibilityDimension.NETWORK: CompatibilityState.PASS,
        CompatibilityDimension.AUTHENTICATION: CompatibilityState.NOT_TESTED,
        CompatibilityDimension.REMOTE: CompatibilityState.UNKNOWN,
    }
    for dimension, state in states.items():
        observation = services.providers.record_compatibility_observation(
            CompatibilityObservationCreate(
                observation_set_id="obs_33333333333333333333333333333333",
                provider_id=provider.id,
                dimension=dimension,
                state=state,
                evidence_schema_version=1,
                evidence_code="SLICE_ONE_METADATA_ONLY",
            ),
            actor_id=ACTOR_ID,
        )
        assert observation.dimension is dimension
        assert observation.state is state


def test_management_read_model_fields_are_bounded_and_non_generic() -> None:
    assert {field.name for field in fields(RuntimeProviderManagement)} == {
        "runtime_installation_id",
        "state",
        "runtime_binding_id",
        "binding_revision",
    }
