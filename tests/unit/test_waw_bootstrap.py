from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from agentbox_runtime.waw_bootstrap import (
    create_waw_lifecycle_registry_development_only,
    create_waw_lifecycle_registry_from_filesystem_bundle,
    create_waw_lifecycle_registry_from_loaded_manifest_bundle,
    create_waw_lifecycle_registry_from_manifest_bundle,
    create_waw_lifecycle_registry_from_manifest_bytes,
)
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_host_manifest import (
    WAWCanonicalManifestBundle,
    WAWRuntimeHostManifestDevelopmentOnly,
    WAWRuntimeHostManifestError,
)
from agentbox_runtime.waw_lifecycle import WAWLifecycleIdentity, WAWLifecycleObservation
from agentbox_runtime.waw_manifest_codecs import (
    APIHostAnchor,
    CgroupDelegationManifest,
    ProjectRootManifest,
    RuntimeHostManifest,
    WAWManifestCodecError,
    decode_runtime_host_manifest,
    encode_api_host_anchor,
    encode_cgroup_delegation_manifest,
    encode_project_root_manifest,
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
            codex_fingerprint="9" * 64,
            attach_supervisor_fingerprint="1" * 64,
            cgroup_delegation_policy_digest="4" * 64,
            project_root_manifest_path="/var/lib/agentbox-waw/project-root.json",
            project_root_manifest_digest="b" * 64,
            socket_digest="2" * 64,
            config_digest="3" * 64,
            enrollment_epoch="4",
            enrollment_state="steady",
        )
    )


def _strict_project_root_bytes() -> bytes:
    return encode_project_root_manifest(
        ProjectRootManifest(
            manifest_revision="1",
            configured_root="/srv/agentbox/projects",
            root_device="2049",
            root_mount_id="42",
            root_filesystem_id="host-filesystem-1",
            root_uid="0",
            root_gid="0",
            root_mode="755",
            relative_key_grammar_version="one-component-v1",
            binding_digest_algorithm="sha256-rfc8785",
            no_shell_executable_path="/bin/false",
            no_shell_executable_digest="a" * 64,
        )
    )


def _strict_cgroup_bytes() -> bytes:
    return encode_cgroup_delegation_manifest(
        CgroupDelegationManifest(
            service_unit="agentbox-runtime.service",
            cgroup_mount_type="cgroup2",
            cgroup_mount_device="0:31",
            cgroup_mount_filesystem_id="host-cgroup2-1",
            cgroup_schema_identity="cgroup-v2",
            delegate=True,
            delegate_subgroup="agentbox-runtime-supervisor",
            protect_control_groups="private",
            kill_mode="process",
            controllers=("cpu", "memory", "pids"),
            tasks_max=256,
            memory_max=536870912,
            memory_swap_max=0,
            cpu_quota_percent=400,
            cpu_quota_period_usec=100000,
            policy_template_digest="a" * 64,
        )
    )


def _strict_manifest_bundle() -> tuple[bytes, bytes, bytes, bytes]:
    project_raw = _strict_project_root_bytes()
    cgroup_raw = _strict_cgroup_bytes()
    runtime = decode_runtime_host_manifest(_strict_manifest_bytes())
    runtime = replace(
        runtime,
        project_root_manifest_digest=manifest_sha256(project_raw),
        cgroup_delegation_policy_digest=manifest_sha256(cgroup_raw),
    )
    runtime_raw = encode_runtime_host_manifest(runtime)
    anchor_raw = encode_api_host_anchor(
        APIHostAnchor(
            runtime_host_installation_id=runtime.runtime_host_installation_id,
            runtime_host_installation_revision=runtime.runtime_host_installation_revision,
            runtime_attestation_x25519_fingerprint=runtime.runtime_attestation_x25519_fingerprint,
            host_manifest_digest=manifest_sha256(runtime_raw),
            project_root_manifest_digest=manifest_sha256(project_raw),
            enrollment_epoch=runtime.enrollment_epoch,
            enrollment_state=runtime.enrollment_state,
        )
    )
    return anchor_raw, runtime_raw, project_raw, cgroup_raw


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


def test_bootstrap_factory_failure_burns_epoch_and_requires_fresh_startup(
    tmp_path: Path,
) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1

    def failing_factory(_epoch: str) -> FakeExecutor:
        raise RuntimeError("synthetic executor construction failure")

    with pytest.raises(RuntimeError, match="synthetic executor construction failure"):
        create_waw_lifecycle_registry_development_only(
            manifest=_manifest(),
            epoch_store=store,
            executor_factory=failing_factory,
            binding_digest_factory=lambda _request: "a" * 64,
        )

    # Epoch 2 was durably consumed before factory invocation.  A recovery
    # startup must advance to 3 and must never retry with the burned value.
    assert store.consume() == 3


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


@pytest.mark.anyio
async def test_bundle_bootstrap_verifies_cross_manifest_pin_before_epoch_consume(
    tmp_path: Path,
) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _strict_manifest_bundle()
    registry, epoch = create_waw_lifecycle_registry_from_manifest_bundle(
        raw_api_host_anchor=anchor_raw,
        raw_runtime_host_manifest=runtime_raw,
        raw_project_root_manifest=project_raw,
        raw_cgroup_delegation_manifest=cgroup_raw,
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
    assert response["runtime_epoch"] == "2"
    assert response["host_manifest_digest"] == manifest_sha256(runtime_raw)
    assert response["project_root_manifest_digest"] == manifest_sha256(project_raw)


def test_loaded_bundle_bootstrap_preserves_single_bundle_boundary(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _strict_manifest_bundle()
    bundle = WAWCanonicalManifestBundle(
        api_host_anchor=anchor_raw,
        runtime_host_installation=runtime_raw,
        project_root=project_raw,
        cgroup_delegation=cgroup_raw,
    )
    _registry, epoch = create_waw_lifecycle_registry_from_loaded_manifest_bundle(
        bundle=bundle,
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert epoch == "2"


def test_filesystem_bundle_bootstrap_loads_and_pins_before_epoch(tmp_path: Path) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _strict_manifest_bundle()
    directory = tmp_path / "bundle"
    directory.mkdir()
    directory.chmod(0o750)
    for filename, raw in (
        ("api-host-anchor.v1", anchor_raw),
        ("runtime-host-installation.v1", runtime_raw),
        ("project-root.v1", project_raw),
        ("cgroup-delegation.v1", cgroup_raw),
    ):
        path = directory / filename
        path.write_bytes(raw)
        path.chmod(0o440)

    _registry, epoch = create_waw_lifecycle_registry_from_filesystem_bundle(
        directory=directory,
        expected_api_host_anchor_digest=manifest_sha256(anchor_raw),
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
        epoch_store=store,
        executor=FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    assert epoch == "2"


def test_filesystem_bundle_bootstrap_rejects_external_anchor_mismatch_without_epoch(
    tmp_path: Path,
) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _strict_manifest_bundle()
    directory = tmp_path / "bundle"
    directory.mkdir()
    directory.chmod(0o750)
    for filename, raw in (
        ("api-host-anchor.v1", anchor_raw),
        ("runtime-host-installation.v1", runtime_raw),
        ("project-root.v1", project_raw),
        ("cgroup-delegation.v1", cgroup_raw),
    ):
        path = directory / filename
        path.write_bytes(raw)
        path.chmod(0o440)

    with pytest.raises(WAWManifestCodecError, match="anchor digest mismatch"):
        create_waw_lifecycle_registry_from_filesystem_bundle(
            directory=directory,
            expected_api_host_anchor_digest="f" * 64,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            epoch_store=store,
            executor=FakeExecutor(),
            binding_digest_factory=lambda _request: "a" * 64,
        )
    assert store.consume() == 2


def test_bundle_bootstrap_rejects_cross_manifest_mismatch_without_epoch_consume(
    tmp_path: Path,
) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    anchor_raw, runtime_raw, project_raw, cgroup_raw = _strict_manifest_bundle()
    anchor = APIHostAnchor(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision="3",
        runtime_attestation_x25519_fingerprint="c" * 64,
        host_manifest_digest="b" * 64,
        project_root_manifest_digest=manifest_sha256(project_raw),
        enrollment_epoch="4",
        enrollment_state="steady",
    )
    with pytest.raises(WAWManifestCodecError, match="does not pin"):
        create_waw_lifecycle_registry_from_manifest_bundle(
            raw_api_host_anchor=encode_api_host_anchor(anchor),
            raw_runtime_host_manifest=runtime_raw,
            raw_project_root_manifest=project_raw,
            raw_cgroup_delegation_manifest=cgroup_raw,
            epoch_store=store,
            executor=FakeExecutor(),
            binding_digest_factory=lambda _request: "a" * 64,
        )
    # Cross-manifest verification happens before the registry consumes epoch 2.
    assert store.consume() == 2
    assert anchor_raw != encode_api_host_anchor(anchor)


@pytest.mark.parametrize("manifest_index", range(4))
def test_bundle_bootstrap_rejects_each_manifest_mutation_before_epoch_consume(
    tmp_path: Path, manifest_index: int
) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    bundle = list(_strict_manifest_bundle())
    raw = bundle[manifest_index]
    # Mutating the canonical closing byte makes each individual record
    # malformed.  The bundle boundary must reject it before consuming epoch 2.
    bundle[manifest_index] = raw[:-1] + b" "
    with pytest.raises(WAWManifestCodecError):
        create_waw_lifecycle_registry_from_manifest_bundle(
            raw_api_host_anchor=bundle[0],
            raw_runtime_host_manifest=bundle[1],
            raw_project_root_manifest=bundle[2],
            raw_cgroup_delegation_manifest=bundle[3],
            epoch_store=store,
            executor=FakeExecutor(),
            binding_digest_factory=lambda _request: "a" * 64,
        )
    assert store.consume() == 2


def test_bundle_bootstrap_is_exported_from_runtime_package() -> None:
    from agentbox_runtime import (
        CrossManifestPin,
        create_waw_lifecycle_registry_from_manifest_bundle,
    )

    assert create_waw_lifecycle_registry_from_manifest_bundle is not None
    assert CrossManifestPin is not None
