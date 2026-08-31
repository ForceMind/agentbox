from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from agentbox_runtime.waw_cleanup_recovery import (
    CleanupEvidenceSource,
    CleanupRecoveryDecision,
    WAWCleanupActiveIdentity,
    WAWCleanupDurableSnapshot,
    WAWCleanupEvidence,
    WAWCleanupRecoveryError,
    cleanup_attestation_digest,
    reduce_cleanup_recovery,
)

WORKSPACE = "aws_" + "1" * 32
PROJECT = "prj_" + "2" * 32
HOST = "wri_" + "3" * 32
BINDING_DIGEST = "a" * 64
CGROUP_IDENTITY_DIGEST = "b" * 64


def replace_evidence(value: WAWCleanupEvidence, **changes: object) -> WAWCleanupEvidence:
    return cast(WAWCleanupEvidence, replace(cast(Any, value), **changes))


def active(*, generation: int = 3, host: str = HOST) -> WAWCleanupActiveIdentity:
    return WAWCleanupActiveIdentity(
        workspace_id=WORKSPACE,
        project_id=PROJECT,
        agent_type="claude",
        generation=generation,
        runtime_epoch="7",
        binding_revision="2",
        binding_digest=BINDING_DIGEST,
        runtime_host_installation_id=host,
        runtime_host_installation_revision="4",
    )


def snapshot(
    *,
    state: str = "FENCED",
    populated: str = "1",
    generation: int = 3,
    latest_generation: int = 3,
    unresolved_generations: tuple[int, ...] = (3,),
    host: str = HOST,
    cgroup_identity_digest: str = CGROUP_IDENTITY_DIGEST,
    leaves: tuple[str, ...] | None = None,
) -> WAWCleanupDurableSnapshot:
    value = WAWCleanupDurableSnapshot(
        workspace_id=WORKSPACE,
        project_id=PROJECT,
        agent_type="claude",
        generation=generation,
        runtime_epoch="7",
        binding_revision="2",
        binding_digest=BINDING_DIGEST,
        runtime_host_installation_id=host,
        runtime_host_installation_revision="4",
        cgroup_identity_digest=cgroup_identity_digest,
        attestation_digest="f" * 64,
        cleanup_state=state,
        last_populated=populated,
        attachment_leaves=(
            ("att_" + "3" * 32,) if leaves is None and populated == "1" else (leaves or ())
        ),
        latest_generation=latest_generation,
        unresolved_generations=unresolved_generations,
    )
    return replace(value, attestation_digest=cleanup_attestation_digest(value))


def evidence(
    *,
    state: str = "FENCED",
    populated: str = "1",
    generation: int = 3,
    host: str = HOST,
    cgroup_identity_digest: str = CGROUP_IDENTITY_DIGEST,
    leaves: tuple[str, ...] | None = None,
) -> WAWCleanupEvidence:
    value = WAWCleanupEvidence(
        workspace_id=WORKSPACE,
        project_id=PROJECT,
        agent_type="claude",
        generation=generation,
        runtime_epoch="7",
        binding_revision="2",
        binding_digest=BINDING_DIGEST,
        runtime_host_installation_id=host,
        runtime_host_installation_revision="4",
        cgroup_identity_digest=cgroup_identity_digest,
        attestation_digest="f" * 64,
        cleanup_state=state,
        last_populated=populated,
        attachment_leaves=(
            ("att_" + "3" * 32,) if leaves is None and populated == "1" else (leaves or ())
        ),
        evidence_source=CleanupEvidenceSource.SYNTHETIC,
    )
    return replace(value, attestation_digest=cleanup_attestation_digest(value))


def test_populated_or_fenced_evidence_keeps_quarantine() -> None:
    assert (
        reduce_cleanup_recovery(active(), snapshot(), evidence())
        == CleanupRecoveryDecision.KEEP_QUARANTINED
    )


def test_exact_empty_evidence_returns_ack_with_distinct_record_digest() -> None:
    unresolved = snapshot()
    observed = evidence(state="EMPTY_DURABLE", populated="0", leaves=())
    assert unresolved.attestation_digest != observed.attestation_digest
    assert (
        reduce_cleanup_recovery(active(), unresolved, observed) == CleanupRecoveryDecision.ACK_EMPTY
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", "aws_" + "9" * 32),
        ("project_id", "prj_" + "9" * 32),
        ("generation", 4),
        ("runtime_epoch", "8"),
        ("binding_revision", "3"),
        ("binding_digest", "c" * 64),
        ("runtime_host_installation_id", "wri_" + "9" * 32),
        ("runtime_host_installation_revision", "5"),
        ("cgroup_identity_digest", "c" * 64),
    ],
)
def test_identity_mismatch_requires_reconciliation(field: str, value: object) -> None:
    observed = replace_evidence(evidence(), **{field: value})
    assert (
        reduce_cleanup_recovery(active(), snapshot(), observed)
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


def test_old_unresolved_generation_cannot_ack_when_newer_unresolved_exists() -> None:
    old = active(generation=2)
    old_snapshot = snapshot(
        generation=2,
        latest_generation=3,
        unresolved_generations=(2, 3),
    )
    old_evidence = evidence(generation=2, state="EMPTY_DURABLE", populated="0", leaves=())
    assert (
        reduce_cleanup_recovery(old, old_snapshot, old_evidence)
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


def test_snapshot_generation_must_be_latest_unresolved() -> None:
    value = snapshot(latest_generation=4, unresolved_generations=(3, 4))
    assert (
        reduce_cleanup_recovery(active(), value, evidence())
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


def test_snapshot_digest_covers_latest_generation_metadata() -> None:
    original = snapshot()
    mutated = replace(original, latest_generation=4, unresolved_generations=(3, 4))
    assert cleanup_attestation_digest(mutated) != original.attestation_digest


def test_attestation_digest_mismatch_requires_reconciliation() -> None:
    observed = replace_evidence(evidence(), attestation_digest="b" * 64)
    assert (
        reduce_cleanup_recovery(active(), snapshot(), observed)
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


def test_cgroup_identity_digest_mismatch_requires_reconciliation() -> None:
    observed = evidence(cgroup_identity_digest="c" * 64)
    assert (
        reduce_cleanup_recovery(active(), snapshot(), observed)
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


def test_state_conflict_requires_reconciliation() -> None:
    observed = evidence(state="LIVE")
    assert (
        reduce_cleanup_recovery(active(), snapshot(), observed)
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


def test_replayed_empty_snapshot_requires_reconciliation() -> None:
    empty = snapshot(state="EMPTY_DURABLE", populated="0", leaves=())
    observed = evidence(state="EMPTY_DURABLE", populated="0", leaves=())
    assert (
        reduce_cleanup_recovery(active(), empty, observed)
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


def test_missing_snapshot_requires_reconciliation() -> None:
    assert (
        reduce_cleanup_recovery(active(), None, evidence())
        == CleanupRecoveryDecision.RECONCILIATION_REQUIRED
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", "not-an-id"),
        ("generation", 0),
        ("runtime_epoch", "01"),
        ("binding_digest", "0" * 64),
        ("runtime_host_installation_id", "host"),
        ("cleanup_state", "UNKNOWN"),
        ("last_populated", "2"),
        ("attachment_leaves", ("att_1",)),
        ("evidence_source", "HOST_READBACK"),
    ],
)
def test_malformed_evidence_is_rejected(field: str, value: object) -> None:
    with pytest.raises(WAWCleanupRecoveryError):
        reduce_cleanup_recovery(
            active(), snapshot(), replace_evidence(evidence(), **{field: value})
        )


def test_closed_mapping_rejects_arbitrary_fields() -> None:
    data = {**active().__dict__, "unexpected": "forbidden"}
    with pytest.raises(WAWCleanupRecoveryError):
        reduce_cleanup_recovery(data, snapshot(), evidence())


def test_mapping_input_is_normalized_without_side_effects() -> None:
    evidence_mapping = {
        **evidence().__dict__,
        "evidence_source": "SYNTHETIC",
    }
    assert (
        reduce_cleanup_recovery(active().__dict__, snapshot().__dict__, evidence_mapping)
        == CleanupRecoveryDecision.KEEP_QUARANTINED
    )


def test_mapping_constructor_errors_are_normalized() -> None:
    malformed = {**evidence().__dict__, "attachment_leaves": 1}
    with pytest.raises(WAWCleanupRecoveryError):
        reduce_cleanup_recovery(active(), snapshot(), malformed)


def test_typed_subclass_is_not_accepted_as_closed_record() -> None:
    class DerivedEvidence(WAWCleanupEvidence):
        pass

    with pytest.raises(WAWCleanupRecoveryError):
        reduce_cleanup_recovery(active(), snapshot(), DerivedEvidence(**evidence().__dict__))
