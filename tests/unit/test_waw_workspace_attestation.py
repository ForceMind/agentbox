from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from agentbox_runtime.waw_cgroup_attestation import WAWCgroupAttestation, WAWCgroupLimits
from agentbox_runtime.waw_workspace_attestation import (
    WAWWorkspaceAttestation,
    WAWWorkspaceAttestationError,
    WAWWorkspaceAttestationStore,
)


def _store(tmp_path: Path) -> WAWWorkspaceAttestationStore:
    directory = tmp_path / "attestations"
    directory.mkdir(mode=0o700)
    return WAWWorkspaceAttestationStore(
        directory, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )


def _kwargs(generation: int) -> dict[str, Any]:
    return {
        "workspace_id": "aws_" + "1" * 32,
        "generation": generation,
        "binding_revision": "1",
        "binding_digest": "a" * 64,
        "runtime_host_installation_id": "wri_" + "2" * 32,
        "runtime_host_installation_revision": "1",
        "runtime_epoch": "1",
    }


def test_generation_accepts_uint64_max(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.advance(**_kwargs(1))
    record = store.advance(**_kwargs(2**64 - 1))
    assert record.min_generation == 2**64 - 1


@pytest.mark.parametrize("generation", (0, -1, 2**64))
def test_generation_rejects_out_of_range_values(tmp_path: Path, generation: int) -> None:
    with pytest.raises(WAWWorkspaceAttestationError):
        _store(tmp_path).advance(**_kwargs(generation))


def _empty() -> WAWCgroupAttestation:
    limits = WAWCgroupLimits(536870912, 0, 400000, 100000, 256)
    return WAWCgroupAttestation(
        workspace_id="aws_" + "1" * 32,
        project_id="prj_" + "3" * 32,
        agent_type="claude",
        generation=1,
        runtime_epoch="2",
        service_unit="agentbox-runtime.service",
        service_invocation_id="2" * 32,
        service_cgroup_device="0:31",
        service_cgroup_inode="10",
        service_cgroup_mount_id="11",
        delegated_subgroup="agentbox-runtime-workspaces",
        delegate_subgroup_device="0:31",
        delegate_subgroup_inode="12",
        delegate_subgroup_mount_id="11",
        cgroup_mount_id="11",
        cgroup_filesystem_id="scoped-runtime-cgroup2-v1",
        workspace_relative_path="ws-111-g1",
        workspace_device="0:31",
        workspace_inode="13",
        workload_relative_path="ws-111-g1/workload",
        workload_device="0:31",
        workload_inode="14",
        attachment_leaves=(),
        controller_configuration_digest="a" * 64,
        workspace_limits=limits,
        workload_limits=limits,
        attachment_limits=limits,
        last_frozen="0",
        last_populated="0",
        cleanup_state="EMPTY_DURABLE",
    )


def test_epoch_recovery_preserves_floor_and_allows_next_generation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    old = store.advance(**_kwargs(1))
    recovered = store.recover_epoch(expected=old, empty=_empty())
    assert recovered == replace(old, runtime_epoch="2")
    assert store.read(old.workspace_id) == recovered
    assert store.recover_epoch(expected=old, empty=_empty()) == recovered
    new = _kwargs(2) | {"runtime_epoch": "2"}
    assert store.advance(**new).min_generation == 2
    with pytest.raises(WAWWorkspaceAttestationError):
        store.recover_epoch(expected=old, empty=_empty())


@pytest.mark.parametrize(
    "change",
    [
        {"runtime_epoch": "1"},
        {"generation": 2},
        {"workspace_id": "aws_" + "9" * 32},
        {"cleanup_state": "FENCED"},
        {"cleanup_state": "LIVE", "last_populated": "1"},
    ],
)
def test_epoch_recovery_rejects_nonmatching_evidence(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    store = _store(tmp_path)
    old = store.advance(**_kwargs(1))
    with pytest.raises(WAWWorkspaceAttestationError):
        store.recover_epoch(expected=old, empty=replace(_empty(), **change))
    assert store.read(old.workspace_id) == old


@pytest.mark.parametrize(
    "change",
    [
        {"binding_revision": "2"},
        {"binding_digest": "b" * 64},
        {"runtime_host_installation_id": "wri_" + "9" * 32},
        {"runtime_host_installation_revision": "2"},
    ],
)
def test_epoch_recovery_compare_and_swap_rejects_provenance_change(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    store = _store(tmp_path)
    old = store.advance(**_kwargs(1))
    with pytest.raises(WAWWorkspaceAttestationError, match="floor changed"):
        store.recover_epoch(expected=replace(old, **change), empty=_empty())
    assert store.read(old.workspace_id) == old


def test_epoch_recovery_requires_existing_floor(tmp_path: Path) -> None:
    store = _store(tmp_path)
    values = _kwargs(1)
    values["min_generation"] = values.pop("generation")
    with pytest.raises(WAWWorkspaceAttestationError, match="floor changed"):
        store.recover_epoch(expected=WAWWorkspaceAttestation(**values), empty=_empty())
