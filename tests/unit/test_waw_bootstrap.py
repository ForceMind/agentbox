from __future__ import annotations

import os
from pathlib import Path

import pytest
from agentbox_runtime.waw_bootstrap import create_waw_lifecycle_registry
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_host_manifest import WAWRuntimeHostManifest
from agentbox_runtime.waw_lifecycle import WAWLifecycleIdentity, WAWLifecycleObservation

HOST = "wri_" + "1" * 32
PROJECT = "prj_" + "2" * 32


class FakeExecutor:
    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch="2")

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="STOPPED", process_state="STOPPED", runtime_epoch="2")

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch="2")

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch="2")


def _manifest() -> WAWRuntimeHostManifest:
    return WAWRuntimeHostManifest(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision="3",
        host_manifest_digest="a" * 64,
        project_root_manifest_digest="b" * 64,
        enrollment_epoch="4",
        enrollment_state="steady",
    )


def _epoch_store(tmp_path: Path) -> WAWRuntimeEpochStore:
    directory = tmp_path / "epoch"
    directory.mkdir()
    directory.chmod(0o700)
    return WAWRuntimeEpochStore(
        directory,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )


@pytest.mark.anyio
async def test_bootstrap_consumes_epoch_and_binds_manifest(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    registry, epoch = create_waw_lifecycle_registry(
        manifest=_manifest(),
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert epoch == "2"
    # A bind response proves the registry received every manifest field and
    # the consumed epoch rather than its development default.
    response = await registry.dispatch(
        {
            "protocol_version": 1,
            "request_id": "wreq_" + "1" * 32,
            "action": "workspace.api_authority.bind",
            "api_authority_epoch": "5",
            "authority_nonce": "c" * 32,
        }
    )
    assert response["runtime_epoch"] == "2"
    assert response["runtime_host_installation_id"] == HOST
    assert response["runtime_host_installation_revision"] == "3"
    assert response["host_manifest_digest"] == "a" * 64
    assert response["project_root_manifest_digest"] == "b" * 64
    assert response["enrollment_epoch"] == "4"
    assert response["enrollment_state"] == "steady"


def test_bootstrap_advances_epoch_counter_without_reuse(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    _registry, first_epoch = create_waw_lifecycle_registry(
        manifest=_manifest(),
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    _registry, second_epoch = create_waw_lifecycle_registry(
        manifest=_manifest(),
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert first_epoch == "2"
    assert second_epoch == "3"
