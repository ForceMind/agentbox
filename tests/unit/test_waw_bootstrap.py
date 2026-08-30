from __future__ import annotations

import os
from pathlib import Path

import pytest
from agentbox_runtime.waw_bootstrap import (
    create_waw_lifecycle_registry_development_only,
    create_waw_lifecycle_registry_from_manifest_bytes,
)
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_host_manifest import (
    WAWRuntimeHostManifestDevelopmentOnly,
    WAWRuntimeHostManifestError,
)
from agentbox_runtime.waw_lifecycle import WAWLifecycleIdentity, WAWLifecycleObservation
from agentbox_runtime.waw_manifest_codecs import (
    RuntimeHostManifest,
    encode_runtime_host_manifest,
    manifest_sha256,
)

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


def _manifest() -> WAWRuntimeHostManifestDevelopmentOnly:
    return WAWRuntimeHostManifestDevelopmentOnly(
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


def _strict_manifest_bytes() -> bytes:
    return encode_runtime_host_manifest(
        RuntimeHostManifest(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision="3",
            runtime_attestation_x25519_fingerprint="c" * 64,
            tmux_fingerprint="d" * 64,
            bridge_fingerprint="e" * 64,
            claude_fingerprint="f" * 64,
            codex_fingerprint="0" * 64,
            attach_supervisor_fingerprint="1" * 64,
            project_root_manifest_path="/var/lib/agentbox-waw/project-root.json",
            project_root_manifest_digest="b" * 64,
            socket_digest="2" * 64,
            config_digest="3" * 64,
            enrollment_epoch="4",
            enrollment_state="steady",
        )
    )


@pytest.mark.anyio
async def test_bootstrap_consumes_epoch_and_binds_manifest(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    registry, epoch = create_waw_lifecycle_registry_development_only(
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


@pytest.mark.anyio
async def test_bootstrap_factory_receives_consumed_epoch(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    observed: list[str] = []

    def factory(epoch: str) -> FakeExecutor:
        observed.append(epoch)
        return FakeExecutor()

    _registry, epoch = create_waw_lifecycle_registry_development_only(
        manifest=_manifest(),
        epoch_store=store,
        executor_factory=factory,
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert epoch == "2"
    assert observed == ["2"]


def test_bootstrap_advances_epoch_counter_without_reuse(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    _registry, first_epoch = create_waw_lifecycle_registry_development_only(
        manifest=_manifest(),
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    _registry, second_epoch = create_waw_lifecycle_registry_development_only(
        manifest=_manifest(),
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert first_epoch == "2"
    assert second_epoch == "3"


@pytest.mark.anyio
async def test_production_bootstrap_decodes_strict_manifest_bytes(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    raw_manifest = _strict_manifest_bytes()
    registry, epoch = create_waw_lifecycle_registry_from_manifest_bytes(
        raw_manifest=raw_manifest,
        expected_host_manifest_digest=manifest_sha256(raw_manifest),
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert epoch == "2"
    response = await registry.dispatch(
        {
            "protocol_version": 1,
            "request_id": "wreq_" + "1" * 32,
            "action": "workspace.api_authority.bind",
            "api_authority_epoch": "5",
            "authority_nonce": "c" * 32,
        }
    )
    assert response["runtime_host_installation_id"] == HOST
    assert response["project_root_manifest_digest"] == "b" * 64


@pytest.mark.parametrize("raw", [b"{}", b'{"schema_version":"waw-runtime-host-installation-v1"}'])
def test_production_bootstrap_rejects_unverified_manifest_bytes(tmp_path: Path, raw: bytes) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    with pytest.raises(WAWRuntimeHostManifestError):
        create_waw_lifecycle_registry_from_manifest_bytes(
            raw_manifest=raw,
            expected_host_manifest_digest="a" * 64,
            epoch_store=store,
            executor=FakeExecutor(),
            binding_digest_factory=lambda _request: "a" * 64,
        )


def test_production_bootstrap_rejects_digest_mismatch_without_consuming_epoch(
    tmp_path: Path,
) -> None:
    from agentbox_runtime.waw_manifest_codecs import WAWManifestCodecError

    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    raw_manifest = _strict_manifest_bytes()
    with pytest.raises(WAWManifestCodecError, match="digest mismatch"):
        create_waw_lifecycle_registry_from_manifest_bytes(
            raw_manifest=raw_manifest,
            expected_host_manifest_digest="a" * 64,
            epoch_store=store,
            executor=FakeExecutor(),
            binding_digest_factory=lambda _request: "a" * 64,
        )
    # The failed attempt must not consume the first Runtime epoch.
    assert store.consume() == 2


def test_production_bootstrap_rejects_replayed_manifest_against_new_anchor(
    tmp_path: Path,
) -> None:
    from agentbox_runtime.waw_manifest_codecs import WAWManifestCodecError

    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    raw_manifest = _strict_manifest_bytes()
    expected_digest = manifest_sha256(raw_manifest)
    # A later anchor is intentionally different: replaying the old bytes is
    # rejected before the epoch trust root is touched.
    with pytest.raises(WAWManifestCodecError, match="digest mismatch"):
        create_waw_lifecycle_registry_from_manifest_bytes(
            raw_manifest=raw_manifest,
            expected_host_manifest_digest="b" * 64,
            epoch_store=store,
            executor=FakeExecutor(),
            binding_digest_factory=lambda _request: "a" * 64,
        )
    assert expected_digest != "b" * 64
    assert store.consume() == 2


def test_production_bootstrap_rejects_invalid_expected_digest_without_consuming_epoch(
    tmp_path: Path,
) -> None:
    from agentbox_runtime.waw_manifest_codecs import WAWManifestCodecError

    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    raw_manifest = _strict_manifest_bytes()
    with pytest.raises(WAWManifestCodecError, match="expected host manifest digest"):
        create_waw_lifecycle_registry_from_manifest_bytes(
            raw_manifest=raw_manifest,
            expected_host_manifest_digest="A" * 64,
            epoch_store=store,
            executor=FakeExecutor(),
            binding_digest_factory=lambda _request: "a" * 64,
        )
    assert store.consume() == 2
