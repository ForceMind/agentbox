from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from agentbox_runtime.waw_workspace_attestation import (
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
    record = _store(tmp_path).advance(**_kwargs(2**64 - 1))
    assert record.min_generation == 2**64 - 1


@pytest.mark.parametrize("generation", (0, -1, 2**64))
def test_generation_rejects_out_of_range_values(tmp_path: Path, generation: int) -> None:
    with pytest.raises(WAWWorkspaceAttestationError):
        _store(tmp_path).advance(**_kwargs(generation))
