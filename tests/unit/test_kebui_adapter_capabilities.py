"""Pinned-source descriptor negatives; no vendor, authenticated source, or host execution."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest
from agentbox_runtime.kebui_adapter_capabilities import (
    AckMeaning,
    AdapterOperation,
    AdapterProfile,
    AdapterSelection,
    CapabilityContractError,
    CapabilityState,
    EvidenceDomain,
    FindingCode,
    RecoveryRule,
    TerminalRule,
    assess_capability,
    fixed_profiles,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "packages/agentbox-runtime/src/agentbox_runtime/kebui_adapter_capabilities.py"


def selection(profile: AdapterProfile) -> AdapterSelection:
    return AdapterSelection(
        agent=profile.agent,
        profile_id=profile.profile_id,
        executable_version=profile.executable_version,
        source_revision=profile.source_revision,
        sdk_version=profile.sdk_version,
    )


@pytest.mark.parametrize("profile", fixed_profiles(), ids=lambda item: item.agent)
@pytest.mark.parametrize("operation", tuple(AdapterOperation))
def test_source_match_never_becomes_software_host_or_execution_qualification(
    profile: AdapterProfile, operation: AdapterOperation
) -> None:
    report = assess_capability(selection(profile), operation)
    assert report.identity_state is CapabilityState.SUPPORTED
    assert report.source_research.domain is EvidenceDomain.SOURCE_RESEARCH
    assert report.software_qualification.domain is EvidenceDomain.SOFTWARE_QUALIFICATION
    assert report.host_qualification.domain is EvidenceDomain.HOST_QUALIFICATION
    assert report.software_qualification.state is not CapabilityState.SUPPORTED
    assert report.host_qualification.state is CapabilityState.UNKNOWN
    assert report.state in {CapabilityState.UNKNOWN, CapabilityState.UNSUPPORTED}
    assert report.execution_allowed is False
    assert FindingCode.HOST_NOT_QUALIFIED in report.blockers
    assert report.contract is not None
    assert report.contract.acknowledgment_proves_terminal is False


@pytest.mark.parametrize("profile", fixed_profiles(), ids=lambda item: item.agent)
@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("profile_id", "some-other-profile-v1"),
        ("executable_version", "999.0.0"),
        ("source_revision", "f" * 40),
        ("sdk_version", "999.0.0"),
    ],
)
def test_each_identity_contradiction_is_stale_without_automatic_upgrade(
    profile: AdapterProfile, field: str, changed: str
) -> None:
    report = assess_capability(replace(selection(profile), **{field: changed}), "start_turn")
    assert report.state is CapabilityState.STALE
    assert report.identity_state is CapabilityState.STALE
    assert report.source_research.state is CapabilityState.SUPPORTED
    assert report.software_qualification.state is CapabilityState.UNKNOWN
    assert report.host_qualification.state is CapabilityState.UNKNOWN
    assert FindingCode.IDENTITY_MISMATCH in report.blockers
    assert report.execution_allowed is False


@pytest.mark.parametrize("profile", fixed_profiles(), ids=lambda item: item.agent)
@pytest.mark.parametrize("field", ["profile_id", "executable_version", "source_revision"])
def test_missing_pin_stays_unknown_without_inheriting_known_agent_capabilities(
    profile: AdapterProfile, field: str
) -> None:
    missing: dict[str, Any] = {field: None}
    report = assess_capability(replace(selection(profile), **missing), "start_turn")
    assert report.identity_state is CapabilityState.UNKNOWN
    assert report.state is CapabilityState.UNKNOWN
    assert FindingCode.MISSING_IDENTITY in report.blockers
    assert report.execution_allowed is False


def test_claude_cli_version_without_sdk_pin_does_not_qualify_sdk_contract() -> None:
    profile = next(item for item in fixed_profiles() if item.agent == "claude")
    report = assess_capability(replace(selection(profile), sdk_version=None), "interrupt_turn")
    assert report.identity_state is CapabilityState.UNKNOWN
    assert report.execution_allowed is False


def test_known_drift_is_not_hidden_by_another_missing_field() -> None:
    profile = fixed_profiles()[0]
    hint = replace(selection(profile), executable_version="0.159.4", source_revision=None)
    report = assess_capability(hint, "start_turn")
    assert report.identity_state is CapabilityState.STALE
    assert FindingCode.IDENTITY_MISMATCH in report.blockers
    assert FindingCode.MISSING_IDENTITY not in report.blockers


def test_unknown_agent_is_not_reported_as_vendor_unsupported() -> None:
    report = assess_capability(AdapterSelection(agent="another-agent"), "start_turn")
    assert report.state is CapabilityState.UNKNOWN
    assert report.profile is None
    assert report.contract is None
    assert report.source_research.state is CapabilityState.UNKNOWN
    assert FindingCode.UNKNOWN_AGENT in report.blockers
    assert report.execution_allowed is False


@pytest.mark.parametrize("operation", ["shell", "execute", "parallel_turn", "provider_login"])
def test_unregistered_operations_never_fall_back_to_native_commands(operation: str) -> None:
    report = assess_capability(selection(fixed_profiles()[0]), operation)
    assert report.state is CapabilityState.UNSUPPORTED
    assert report.contract is None
    assert FindingCode.UNKNOWN_OPERATION in report.blockers
    assert report.execution_allowed is False


@pytest.mark.parametrize("profile", fixed_profiles(), ids=lambda item: item.agent)
@pytest.mark.parametrize(
    "operation", ["respond_question", "steer_turn", "fork_thread", "rollback_thread", "queue_turn"]
)
def test_future_features_remain_profile_unsupported_despite_upstream_methods(
    profile: AdapterProfile, operation: str
) -> None:
    report = assess_capability(selection(profile), operation)
    assert report.state is CapabilityState.UNSUPPORTED
    assert report.software_qualification.state is CapabilityState.UNSUPPORTED
    assert FindingCode.OUT_OF_PROFILE in report.blockers
    assert report.execution_allowed is False


def test_native_steer_does_not_make_initial_k2_steer_available() -> None:
    codex = next(item for item in fixed_profiles() if item.agent == "codex")
    report = assess_capability(selection(codex), "steer_turn")
    assert report.source_research.state is CapabilityState.SUPPORTED
    assert report.state is CapabilityState.UNSUPPORTED


def test_rollback_is_not_inferred_from_other_versions_or_file_rewind() -> None:
    for profile in fixed_profiles():
        report = assess_capability(selection(profile), "rollback_thread")
        assert report.source_research.state is CapabilityState.UNKNOWN
        assert report.software_qualification.state is CapabilityState.UNSUPPORTED
        assert report.execution_allowed is False


def test_ack_and_terminal_semantics_cannot_be_flattened_across_vendors() -> None:
    profiles = {item.agent: item for item in fixed_profiles()}
    codex = assess_capability(selection(profiles["codex"]), "start_turn").contract
    claude = assess_capability(selection(profiles["claude"]), "start_turn").contract
    assert codex is not None and claude is not None
    assert codex.acknowledgment is AckMeaning.PROTOCOL_REPLY_ONLY
    assert claude.acknowledgment is AckMeaning.LOCAL_WRITE_ONLY
    assert codex.terminal is TerminalRule.MATCHED_TURN_EVENT_REQUIRED
    assert claude.terminal is TerminalRule.CORRELATED_RESULT_REQUIRED
    assert "runtime_proven_no_active_turn" in codex.input_requirements
    assert "busy_must_not_become_steer" in codex.unresolved_requirements
    assert "vendor_ack_not_established" in claude.unresolved_requirements


def test_claude_interrupt_does_not_claim_a_native_exact_turn_selector() -> None:
    profile = next(item for item in fixed_profiles() if item.agent == "claude")
    contract = assess_capability(selection(profile), "interrupt_turn").contract
    assert contract is not None
    assert "native_control_has_no_turn_id" in contract.unresolved_requirements
    assert "background_task_lifetime_separate" in contract.unresolved_requirements
    assert contract.acknowledgment_proves_terminal is False


@pytest.mark.parametrize("profile", fixed_profiles(), ids=lambda item: item.agent)
def test_approval_deadline_and_recovery_remain_unqualified(profile: AdapterProfile) -> None:
    report = assess_capability(selection(profile), "respond_approval")
    assert report.contract is not None
    assert "qualified_source_deadline_capped_at_60_seconds" in (
        report.contract.unresolved_requirements
    )
    assert report.contract.recovery is RecoveryRule.NEVER_REPLAY_RESPONSE
    assert report.contract.terminal is TerminalRule.NOT_TURN_TERMINAL
    assert report.software_qualification.state is CapabilityState.UNKNOWN
    assert report.state is CapabilityState.UNSUPPORTED
    assert FindingCode.APPROVAL_DEADLINE_UNQUALIFIED in report.blockers
    assert report.execution_allowed is False


@pytest.mark.parametrize("profile", fixed_profiles(), ids=lambda item: item.agent)
def test_reconnect_and_history_cannot_resolve_unknown_dispatch(profile: AdapterProfile) -> None:
    resumed = assess_capability(selection(profile), "resume_session").contract
    history = assess_capability(selection(profile), "read_history").contract
    assert resumed is not None and history is not None
    assert resumed.recovery is RecoveryRule.NO_AUTOMATIC_REPLAY
    assert "unknown_delivery_never_resubmits_prompt" in resumed.unresolved_requirements
    assert history.recovery is RecoveryRule.FRESH_AUTHORIZED_READ
    assert history.terminal is TerminalRule.NOT_TURN_TERMINAL


@pytest.mark.parametrize("value", [None, True, 1, [], {}, b"codex", "/tmp/agent", "secret\nvalue"])
def test_identity_hints_reject_content_paths_and_wrong_types_without_echo(value: Any) -> None:
    with pytest.raises(CapabilityContractError, match="^invalid_adapter_selection$"):
        AdapterSelection(agent=value)


@pytest.mark.parametrize("value", [True, 1, [], {}, "/bin/sh", "token=value", "x" * 81])
def test_operation_rejects_arbitrary_payloads_without_echo(value: Any) -> None:
    with pytest.raises(CapabilityContractError, match="^invalid_adapter_operation$"):
        assess_capability(selection(fixed_profiles()[0]), value)


def test_qualification_claims_and_executable_paths_are_not_accepted_inputs() -> None:
    extras: dict[str, Any] = {"host_qualified": True, "executable_path": "/tmp/cli"}
    with pytest.raises(TypeError):
        AdapterSelection(agent="codex", **extras)
    with pytest.raises(CapabilityContractError, match="^invalid_adapter_selection$"):
        assess_capability({"agent": "codex", "qualified": True}, "start_turn")  # type: ignore[arg-type]


def test_readers_cannot_mutate_the_catalog_or_enable_execution() -> None:
    profile = fixed_profiles()[0]
    report = assess_capability(selection(profile), "start_turn")
    with pytest.raises(FrozenInstanceError):
        profile.executable_version = "999.0.0"  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, TypeError, AttributeError)):
        report.execution_allowed = True  # type: ignore[misc,assignment]
    additions: dict[str, Any] = {"execution_allowed": True}
    with pytest.raises(TypeError):
        replace(report, **additions)
    assert fixed_profiles()[0] == profile
    assert assess_capability(selection(profile), "start_turn").execution_allowed is False


def test_catalog_is_pure_and_has_no_production_consumer() -> None:
    """Guard the architectural risk: installing this file must not wire dispatch."""
    tree = ast.parse(MODULE.read_text())
    imports = {
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports == {"__future__", "re", "dataclasses", "enum", "typing"}
    for directory in ("apps", "packages", "helper", "installer"):
        for source in (ROOT / directory).rglob("*.py"):
            if source == MODULE or "node_modules" in source.parts:
                continue
            assert "kebui_adapter_capabilities" not in source.read_text(), source
