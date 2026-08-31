from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
import rfc8785
from agentbox_runtime.waw_cgroup_attestation import (
    WAWCgroupAttachmentLeaf,
    WAWCgroupAttestation,
    WAWCgroupAttestationError,
    WAWCgroupLimits,
    decode_waw_cgroup_attestation,
    encode_waw_cgroup_attestation,
    waw_cgroup_attestation_sha256,
)


def _limits() -> WAWCgroupLimits:
    return WAWCgroupLimits(
        memory_max=128 * 1024 * 1024,
        memory_swap_max=0,
        cpu_quota_usec=200_000,
        cpu_period_usec=100_000,
        pids_max=20,
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
        workspace_limits=_limits(),
        workload_limits=WAWCgroupLimits(120 * 1024 * 1024, 0, 190_000, 100_000, 16),
        attachment_limits=WAWCgroupLimits(8 * 1024 * 1024, 0, 10_000, 100_000, 4),
        last_frozen="0",
        last_populated="1",
        cleanup_state="LIVE",
    )


def test_cgroup_attestation_round_trip_is_canonical() -> None:
    raw = encode_waw_cgroup_attestation(_record())
    assert decode_waw_cgroup_attestation(raw) == _record()
    assert waw_cgroup_attestation_sha256(raw) == hashlib.sha256(raw).hexdigest()
    assert raw == rfc8785.dumps(json.loads(raw))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_id", "prj_" + "1" * 32),
        ("project_id", "aws_" + "2" * 32),
        ("agent_type", "provider"),
        ("generation", 0),
        ("runtime_epoch", "0"),
        ("service_unit", "other.service"),
        ("service_cgroup_device", "/dev/cgroup"),
        ("service_cgroup_device", "00:31"),
        ("workspace_device", "0:031"),
        ("workspace_relative_path", "/escape"),
        ("workspace_relative_path", "."),
        ("workload_relative_path", "waw/../escape"),
        ("last_frozen", "2"),
        ("cleanup_state", "UNKNOWN"),
    ],
)
def test_cgroup_attestation_rejects_unsafe_fields(field: str, value: object) -> None:
    values: dict[str, Any] = dict(_record().__dict__)
    values[field] = value
    with pytest.raises(WAWCgroupAttestationError):
        encode_waw_cgroup_attestation(values)


def test_cgroup_attestation_rejects_more_than_one_attachment_leaf() -> None:
    values: dict[str, Any] = dict(_record().__dict__)
    values["attachment_leaves"] = [
        {
            "attachment_id": "att_" + "3" * 32,
            "relative_path": "att-333",
            "device": "0:31",
            "inode": "15",
            "lease_number": 1,
            "cleanup_state": "LIVE",
        },
        {
            "attachment_id": "att_" + "4" * 32,
            "relative_path": "att-444",
            "device": "0:31",
            "inode": "16",
            "lease_number": 2,
            "cleanup_state": "FENCED",
        },
    ]
    with pytest.raises(WAWCgroupAttestationError, match="at most one"):
        encode_waw_cgroup_attestation(values)


def test_cgroup_attestation_enforces_cleanup_and_limit_invariants() -> None:
    values: dict[str, Any] = dict(_record().__dict__)
    values["cleanup_state"] = "EMPTY_DURABLE"
    with pytest.raises(WAWCgroupAttestationError, match="EMPTY_DURABLE"):
        encode_waw_cgroup_attestation(values)

    values = dict(_record().__dict__)
    values["workspace_limits"] = {
        "memory_max": 1,
        "memory_swap_max": 0,
        "cpu_quota_usec": 1,
        "cpu_period_usec": 1,
        "pids_max": 1,
    }
    with pytest.raises(WAWCgroupAttestationError, match="hierarchy"):
        encode_waw_cgroup_attestation(values)


def test_cgroup_attestation_decoder_rejects_duplicate_unknown_and_noncanonical() -> None:
    raw = encode_waw_cgroup_attestation(_record())
    duplicate = raw.replace(
        b'"workspace_id":"aws_' + b"1" * 32 + b'"',
        b'"workspace_id":"aws_' + b"1" * 32 + b'","workspace_id":"aws_' + b"1" * 32 + b'"',
        1,
    )
    with pytest.raises(WAWCgroupAttestationError, match="duplicate"):
        decode_waw_cgroup_attestation(duplicate)
    value = json.loads(raw)
    value["extra"] = "rejected"
    with pytest.raises(WAWCgroupAttestationError, match="closed"):
        decode_waw_cgroup_attestation(rfc8785.dumps(value))
    with pytest.raises(WAWCgroupAttestationError, match="canonical"):
        decode_waw_cgroup_attestation(raw + b" ")
