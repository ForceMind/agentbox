from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from agentbox_protocol.runtime_capabilities import (
    CLAUDE_CAPABILITY_NAMES,
    CODEX_CAPABILITY_NAMES,
    RUNTIME_CAPABILITY_TTL_SECONDS,
    RuntimeAdapterID,
    RuntimeAuthenticationState,
    RuntimeCapabilityCollectionState,
    RuntimeCapabilityFindingCode,
    RuntimeCapabilityName,
    RuntimeCapabilityObservation,
    RuntimeCapabilityOutcome,
    RuntimeCapabilityQuery,
    RuntimeCapabilityRefreshPolicy,
    RuntimeCapabilityReport,
    RuntimeCapabilitySet,
    RuntimeConfigOwnershipState,
    RuntimeEvidenceClass,
    RuntimeEvidenceLifecycle,
    RuntimeInstallationType,
    RuntimeRemoteState,
    RuntimeType,
)
from pydantic import ValidationError

RUNTIME_ID = "rti_0123456789abcdef0123456789abcdef"
NOW = datetime(2026, 8, 16, 1, 2, 3, tzinfo=UTC)


def query(
    *,
    runtime_type: RuntimeType = RuntimeType.CODEX,
    capability_set: RuntimeCapabilitySet = RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1,
) -> RuntimeCapabilityQuery:
    return RuntimeCapabilityQuery(
        request_id="req_capability_contract",
        runtime_installation_id=RUNTIME_ID,
        runtime_installation_revision=3,
        runtime_type=runtime_type,
        capability_set=capability_set,
        refresh_policy=RuntimeCapabilityRefreshPolicy.FORCE_FRESH_READ_ONLY,
    )


def report(
    *,
    runtime_type: RuntimeType = RuntimeType.CODEX,
    capability_set: RuntimeCapabilitySet = RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1,
) -> RuntimeCapabilityReport:
    names = CODEX_CAPABILITY_NAMES if runtime_type is RuntimeType.CODEX else CLAUDE_CAPABILITY_NAMES
    observations = tuple(
        RuntimeCapabilityObservation(
            name=name,
            outcome=RuntimeCapabilityOutcome.UNKNOWN,
            lifecycle=RuntimeEvidenceLifecycle.VALIDATED,
            evidence_class=RuntimeEvidenceClass.NO_ACCEPTABLE_EVIDENCE,
            finding_code=RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,
            dependencies=(
                (
                    RuntimeCapabilityName.CLAUDE_INSTALLED,
                    RuntimeCapabilityName.TMUX_AVAILABLE,
                )
                if name is RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED
                else ()
            ),
            observed_at=NOW,
            expires_at=NOW + timedelta(seconds=RUNTIME_CAPABILITY_TTL_SECONDS),
        )
        for name in names
    )
    return RuntimeCapabilityReport(
        runtime_installation_id=RUNTIME_ID,
        runtime_installation_revision=3,
        runtime_type=runtime_type,
        capability_set=capability_set,
        adapter_id=(
            RuntimeAdapterID.CODEX_RUNTIME_ADAPTER_V1
            if runtime_type is RuntimeType.CODEX
            else RuntimeAdapterID.CLAUDE_RUNTIME_ADAPTER_V1
        ),
        collection_state=RuntimeCapabilityCollectionState.COMPLETE,
        runtime_version="0.146.1",
        installation_type=(
            RuntimeInstallationType.STANDALONE
            if runtime_type is RuntimeType.CODEX
            else RuntimeInstallationType.NOT_APPLICABLE
        ),
        authentication_state=RuntimeAuthenticationState.UNKNOWN,
        remote_state=RuntimeRemoteState.UNKNOWN,
        config_ownership_state=(
            RuntimeConfigOwnershipState.UNKNOWN
            if runtime_type is RuntimeType.CODEX
            else RuntimeConfigOwnershipState.NOT_APPLICABLE
        ),
        managed_session_count=None,
        observed_at=NOW,
        expires_at=NOW + timedelta(seconds=RUNTIME_CAPABILITY_TTL_SECONDS),
        observations=observations,
        findings=(RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,),
    )


def test_query_is_exact_typed_and_runtime_set_matched() -> None:
    value = query()
    assert value.protocol_version == 1
    assert value.action == "runtime.capabilities.query"
    assert value.capability_contract_version == 1
    assert value.refresh_policy is RuntimeCapabilityRefreshPolicy.FORCE_FRESH_READ_ONLY

    invalid_changes: tuple[dict[str, object], ...] = (
        {"runtime_installation_id": "prv_0123456789abcdef0123456789abcdef"},
        {"runtime_installation_revision": 0},
        {"runtime_installation_revision": True},
        {"refresh_policy": "cached"},
        {"capability_contract_version": 2},
        {"command": "codex status"},
        {"path": "/root/.codex"},
        {"environment": {}},
        {"capabilities": ["arbitrary"]},
    )
    for changes in invalid_changes:
        with pytest.raises(ValidationError):
            RuntimeCapabilityQuery.model_validate({**value.model_dump(), **changes})

    with pytest.raises(ValidationError):
        query(
            runtime_type=RuntimeType.CLAUDE,
            capability_set=RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1,
        )


def test_query_json_accepts_only_the_two_exact_capability_sets() -> None:
    claude = query(
        runtime_type=RuntimeType.CLAUDE,
        capability_set=RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1,
    )
    assert RuntimeCapabilityQuery.model_validate_json(claude.model_dump_json()) == claude
    invalid = claude.model_dump_json().replace("claude_runtime_session_v1", "claude_provider_v1")
    with pytest.raises(ValidationError):
        RuntimeCapabilityQuery.model_validate_json(invalid)


def test_report_requires_complete_ordered_exact_capability_set() -> None:
    value = report()
    assert tuple(item.name for item in value.observations) == CODEX_CAPABILITY_NAMES

    base = value.model_dump()
    for observations in (
        value.observations[:-1],
        value.observations + (value.observations[-1],),
        (value.observations[1], value.observations[0], *value.observations[2:]),
    ):
        with pytest.raises(ValidationError):
            RuntimeCapabilityReport.model_validate({**base, "observations": observations})


def test_report_has_fixed_utc_ttl_and_one_timestamp_domain() -> None:
    value = report()
    invalid_expiry = NOW + timedelta(seconds=RUNTIME_CAPABILITY_TTL_SECONDS + 1)
    with pytest.raises(ValidationError):
        RuntimeCapabilityReport.model_validate({**value.model_dump(), "expires_at": invalid_expiry})
    changed = list(value.observations)
    changed[0] = changed[0].model_copy(update={"observed_at": NOW + timedelta(seconds=1)})
    with pytest.raises(ValidationError):
        RuntimeCapabilityReport.model_validate({**value.model_dump(), "observations": changed})
    with pytest.raises(ValidationError):
        RuntimeCapabilityReport.model_validate(
            {**value.model_dump(), "observed_at": NOW.replace(tzinfo=None)}
        )


def test_outcome_and_evidence_lifecycle_are_independent() -> None:
    unsupported = RuntimeCapabilityObservation(
        name=RuntimeCapabilityName.CODEX_REMOTE_PAIR,
        outcome=RuntimeCapabilityOutcome.UNSUPPORTED,
        lifecycle=RuntimeEvidenceLifecycle.VALIDATED,
        evidence_class=RuntimeEvidenceClass.PUBLIC_HELP,
        observed_at=NOW,
        expires_at=NOW + timedelta(seconds=60),
    )
    expired = unsupported.model_copy(
        update={
            "outcome": RuntimeCapabilityOutcome.SUPPORTED,
            "lifecycle": RuntimeEvidenceLifecycle.EXPIRED,
        }
    )
    assert unsupported.outcome is RuntimeCapabilityOutcome.UNSUPPORTED
    assert unsupported.lifecycle is RuntimeEvidenceLifecycle.VALIDATED
    assert expired.outcome is RuntimeCapabilityOutcome.SUPPORTED
    assert expired.lifecycle is RuntimeEvidenceLifecycle.EXPIRED


def test_report_schema_has_no_generic_or_sensitive_fields() -> None:
    field_names = {
        *RuntimeCapabilityQuery.model_fields,
        *RuntimeCapabilityReport.model_fields,
        *RuntimeCapabilityObservation.model_fields,
    }
    forbidden = {
        "command",
        "argv",
        "path",
        "environment",
        "metadata",
        "details",
        "payload",
        "value",
        "stdout",
        "stderr",
        "config",
        "headers",
        "token",
        "secret",
        "authorization",
    }
    assert field_names.isdisjoint(forbidden)


def test_claude_report_is_runtime_only_and_rejects_config_ownership() -> None:
    value = report(
        runtime_type=RuntimeType.CLAUDE,
        capability_set=RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1,
    )
    assert tuple(item.name for item in value.observations) == CLAUDE_CAPABILITY_NAMES
    assert all("provider" not in item.name.value for item in value.observations)
    with pytest.raises(ValidationError):
        RuntimeCapabilityReport.model_validate(
            {
                **value.model_dump(),
                "config_ownership_state": RuntimeConfigOwnershipState.UNKNOWN,
            }
        )


def test_claude_managed_session_evidence_requires_exact_supported_dependencies() -> None:
    value = report(
        runtime_type=RuntimeType.CLAUDE,
        capability_set=RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1,
    )
    data = value.model_dump()
    observations = list(data["observations"])
    by_name = {item["name"]: item for item in observations}
    by_name[RuntimeCapabilityName.CLAUDE_INSTALLED]["outcome"] = RuntimeCapabilityOutcome.SUPPORTED
    by_name[RuntimeCapabilityName.TMUX_AVAILABLE]["outcome"] = RuntimeCapabilityOutcome.SUPPORTED
    session = by_name[RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED]
    session.update(
        outcome=RuntimeCapabilityOutcome.SUPPORTED,
        lifecycle=RuntimeEvidenceLifecycle.VALIDATED,
        evidence_class=RuntimeEvidenceClass.AGENTBOX_MANAGED_STATE,
        finding_code=None,
    )
    data.update(
        observations=tuple(observations),
        managed_session_count=0,
        findings=(RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,),
    )
    valid = RuntimeCapabilityReport.model_validate(data)
    assert valid.managed_session_count == 0

    for name, field, replacement in (
        (RuntimeCapabilityName.CLAUDE_INSTALLED, "outcome", RuntimeCapabilityOutcome.UNAVAILABLE),
        (RuntimeCapabilityName.TMUX_AVAILABLE, "outcome", RuntimeCapabilityOutcome.UNAVAILABLE),
        (
            RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED,
            "lifecycle",
            RuntimeEvidenceLifecycle.DETECTED,
        ),
        (
            RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED,
            "evidence_class",
            RuntimeEvidenceClass.NO_ACCEPTABLE_EVIDENCE,
        ),
    ):
        changed = valid.model_dump()
        changed_observations = list(changed["observations"])
        changed_by_name = {item["name"]: item for item in changed_observations}
        changed_by_name[name][field] = replacement
        changed["observations"] = tuple(changed_observations)
        with pytest.raises(ValidationError):
            RuntimeCapabilityReport.model_validate(changed)


def test_claude_session_count_and_dependency_contradictions_fail_closed() -> None:
    value = report(
        runtime_type=RuntimeType.CLAUDE,
        capability_set=RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1,
    )
    with pytest.raises(ValidationError):
        RuntimeCapabilityReport.model_validate({**value.model_dump(), "managed_session_count": 1})

    data = value.model_dump()
    observations = list(data["observations"])
    session = next(
        item
        for item in observations
        if item["name"] is RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED
    )
    session["dependencies"] = (RuntimeCapabilityName.TMUX_AVAILABLE,)
    with pytest.raises(ValidationError):
        RuntimeCapabilityReport.model_validate({**data, "observations": tuple(observations)})
