from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from agentbox_runtime.waw_cgroup_attestation import (
    WAWCgroupAttachmentLeaf,
    WAWCgroupAttestation,
    WAWCgroupLimits,
)
from agentbox_runtime.waw_cgroup_attestation_store import (
    WAWCgroupAttestationStore,
    WAWCgroupAttestationStoreError,
)


def _record() -> WAWCgroupAttestation:
    return WAWCgroupAttestation(
        workspace_id="aws_" + "1" * 32,
        project_id="prj_" + "2" * 32,
        agent_type="claude",
        generation=1,
        runtime_epoch="3",
        service_unit="agentbox-runtime.service",
        service_invocation_id="invocation-1",
        service_cgroup_device="0:31",
        service_cgroup_inode="10",
        service_cgroup_mount_id="11",
        delegated_subgroup="agentbox-runtime-supervisor",
        delegate_subgroup_device="0:31",
        delegate_subgroup_inode="12",
        delegate_subgroup_mount_id="11",
        cgroup_mount_id="11",
        cgroup_filesystem_id="host-cgroup2-1",
        workspace_relative_path="waw/ws-111-g1",
        workspace_device="0:31",
        workspace_inode="13",
        workload_relative_path="waw/ws-111-g1/workload",
        workload_device="0:31",
        workload_inode="14",
        attachment_leaves=(
            WAWCgroupAttachmentLeaf(
                attachment_id="att_" + "3" * 32,
                relative_path="waw/ws-111-g1/attachments/att-333",
                device="0:31",
                inode="15",
                lease_number=1,
                cleanup_state="LIVE",
            ),
        ),
        controller_configuration_digest="a" * 64,
        workspace_limits=WAWCgroupLimits(128 * 1024 * 1024, 0, 200_000, 100_000, 20),
        workload_limits=WAWCgroupLimits(120 * 1024 * 1024, 0, 190_000, 100_000, 16),
        attachment_limits=WAWCgroupLimits(8 * 1024 * 1024, 0, 10_000, 100_000, 4),
        last_frozen="0",
        last_populated="1",
        cleanup_state="LIVE",
    )


def _store(tmp_path: Path) -> tuple[WAWCgroupAttestationStore, Path]:
    directory = tmp_path / "cgroup-attestations"
    directory.mkdir()
    directory.chmod(0o700)
    return (
        WAWCgroupAttestationStore(
            directory,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        ),
        directory,
    )


def test_store_writes_and_reads_validated_record(tmp_path: Path) -> None:
    store, directory = _store(tmp_path)
    record = _record()
    assert store.write(record) == record
    assert store.read(workspace_id=record.workspace_id, generation=record.generation) == record
    files = list(directory.glob("*.json"))
    assert len(files) == 1
    assert files[0].stat().st_mode & 0o777 == 0o600


def test_store_requires_first_generation_and_rejects_cross_generation_copy(
    tmp_path: Path,
) -> None:
    store, directory = _store(tmp_path)
    record = _record()
    with pytest.raises(WAWCgroupAttestationStoreError, match="first-generation"):
        store.write(replace(record, generation=2))

    store.write(record)
    source = next(directory.glob("*.json"))
    wrong_generation = directory / (source.stem[:-2] + "g2.json")
    wrong_generation.write_bytes(source.read_bytes())
    wrong_generation.chmod(0o600)
    with pytest.raises(WAWCgroupAttestationStoreError, match="key mismatch"):
        store.read(workspace_id=record.workspace_id, generation=2)


def test_store_write_is_idempotent_for_exact_record(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    record = _record()
    assert store.write(record) == record
    assert store.write(record) == record


def test_store_allows_only_forward_cleanup_transitions(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    record = _record()
    fenced = replace(record, attachment_leaves=(), cleanup_state="FENCED")
    empty = replace(fenced, last_populated="0", cleanup_state="EMPTY_DURABLE")
    assert store.write(record) == record
    assert store.write(fenced) == fenced
    assert store.write(empty) == empty
    assert store.read(workspace_id=record.workspace_id, generation=1) == empty
    with pytest.raises(WAWCgroupAttestationStoreError, match="cannot be changed"):
        store.write(replace(empty, last_frozen="1"))


def test_store_rejects_immutable_identity_or_backward_state_changes(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    record = _record()
    store.write(record)
    with pytest.raises(WAWCgroupAttestationStoreError, match="immutable"):
        store.write(replace(record, runtime_epoch="4"))
    fenced = replace(record, attachment_leaves=(), cleanup_state="FENCED")
    empty = replace(fenced, last_populated="0", cleanup_state="EMPTY_DURABLE")
    store.write(fenced)
    store.write(empty)
    with pytest.raises(WAWCgroupAttestationStoreError, match="backwards"):
        store.write(fenced)


def test_store_rejects_symlink_and_malformed_records(tmp_path: Path) -> None:
    store, directory = _store(tmp_path)
    record = _record()
    store.write(record)
    path = next(directory.glob("*.json"))
    raw = path.read_bytes()
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_bytes(raw)
    outside.chmod(0o600)
    path.symlink_to(outside)
    with pytest.raises(WAWCgroupAttestationStoreError):
        store.read(workspace_id=record.workspace_id, generation=record.generation)
    path.unlink()
    path.write_bytes(b"{}")
    path.chmod(0o600)
    with pytest.raises(WAWCgroupAttestationStoreError, match="invalid"):
        store.read(workspace_id=record.workspace_id, generation=record.generation)
