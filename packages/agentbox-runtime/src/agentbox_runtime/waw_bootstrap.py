"""Explicit WAW Runtime bootstrap wiring for trusted, injected components.

This module deliberately does not discover files, bind sockets, or choose an
executor.  The Runtime entrypoint must first validate the installer-owned host
manifest and adopt the systemd-provided descriptor set, then pass those
objects here.  The epoch is consumed exactly once before the registry is
created, so a registry can never silently use its ``"1"`` development
default in a Runtime process.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_auth_probe import WAWCachedPublicAuthProbe
from agentbox_runtime.waw_cgroup_attestation_store import WAWCgroupAttestationStore
from agentbox_runtime.waw_control_server import WAWControlServer
from agentbox_runtime.waw_encrypted_server import WAWEncryptedServer
from agentbox_runtime.waw_encrypted_stream import (
    RuntimePeer,
    WAWEncryptedAttachmentService,
    WAWEncryptedRegistry,
)
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_fixed_transport import (
    WAWVerifiedExecutionAuthority,
    _issue_verified_execution_authority,
)
from agentbox_runtime.waw_host_manifest import (
    WAWCanonicalManifestBundle,
    WAWRuntimeHostManifestDevelopmentOnly,
    decode_canonical_waw_runtime_host_manifest,
    load_canonical_waw_manifest_bundle,
    load_verified_canonical_waw_manifest_bundle_v2,
)
from agentbox_runtime.waw_lifecycle import (
    BindingDigestFactory,
    CgroupAttestationFactory,
    WAWLifecycleExecutor,
    WAWLifecycleRegistry,
)
from agentbox_runtime.waw_manifest_codecs import (
    CrossManifestPinV2,
    RuntimeHostManifest,
    RuntimeHostManifestV2,
    WAWManifestCodecError,
    manifest_sha256,
    verify_api_host_anchor_cross_manifest,
    verify_api_host_anchor_v2_cross_manifest,
)
from agentbox_runtime.waw_peer_authority import WAWPeerAuthority, WAWPeerAuthorityError
from agentbox_runtime.waw_project_binding_store import (
    WAWProjectBindingStore,
    WAWProjectBindingStoreError,
    WAWProjectBindingVerifier,
    WAWProjectBindingVerifierError,
)
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.waw_workspace_attestation import WAWWorkspaceAttestationStore

_FILESYSTEM_V2_BINDING_STORE = Path("/var/lib/agentbox-waw/bindings-v1")


def create_waw_lifecycle_registry_development_only(
    *,
    manifest: WAWRuntimeHostManifestDevelopmentOnly,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Development/test-only compatibility bootstrap for the legacy record.

    Production entrypoints must call the full-v2 bundle or filesystem
    composition below.  Keeping this helper available avoids breaking
    synthetic fixtures while making its non-production status explicit.

    ``manifest`` and ``epoch_store`` must already have passed their respective
    descriptor/provenance checks.  This helper is intentionally explicit about
    the side effect of consuming the epoch and returns the consumed value for
    startup logging/diagnostics without re-reading mutable state.  When using
    ``executor_factory``, the factory receives that consumed epoch so its
    observations can be bound to the same Runtime trust root.  Consumption is
    durable and intentionally occurs before factory/registry construction; a
    factory or constructor failure therefore burns that epoch and requires a
    fresh Runtime startup with the next epoch rather than retrying with a
    reused trust root.
    """

    if (executor is None) == (executor_factory is None):
        raise ValueError("provide exactly one of executor or executor_factory")
    consumed_epoch = str(epoch_store.consume())
    actual_executor = executor_factory(consumed_epoch) if executor_factory is not None else executor
    if actual_executor is None:  # pragma: no cover - guarded by the exclusivity check
        raise RuntimeError("WAW executor factory returned no executor")
    registry = WAWLifecycleRegistry(
        runtime_host_installation_id=manifest.runtime_host_installation_id,
        runtime_host_installation_revision=manifest.runtime_host_installation_revision,
        host_manifest_digest=manifest.host_manifest_digest,
        project_root_manifest_digest=manifest.project_root_manifest_digest,
        enrollment_epoch=manifest.enrollment_epoch,
        enrollment_state=manifest.enrollment_state,
        executor=actual_executor,
        binding_digest_factory=binding_digest_factory,
        runtime_epoch=consumed_epoch,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )
    return registry, consumed_epoch


def create_waw_lifecycle_registry_from_manifest_bytes_v1_compat(
    *,
    raw_manifest: bytes,
    expected_host_manifest_digest: str,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Compatibility bootstrap from ``runtime-host-installation.v1``.

    This historical test seam is not a production-facing data boundary.  Raw
    bytes are decoded and codec-validated before any Runtime registry is
    created; malformed or noncanonical records are rejected closed.  The
    caller must supply the expected digest from an external, already-validated
    host anchor.  The digest is checked against the canonical bytes before the
    epoch is consumed, so malformed input, stale/replayed input, and digest
    mismatch cannot advance the Runtime trust root.  Codec validation and this
    comparison alone are not host provenance/attestation and do not authorize
    a real host; those gates remain the caller's responsibility.  The record is
    then reduced to the lifecycle identity fields consumed by the current
    registry.  Host file discovery, sockets, and credentials remain outside
    this pure wiring function.
    """

    manifest = decode_canonical_waw_runtime_host_manifest(raw_manifest)
    if (
        not isinstance(expected_host_manifest_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_host_manifest_digest) is None
    ):
        raise WAWManifestCodecError("expected host manifest digest is invalid")
    actual_digest = manifest_sha256(raw_manifest)
    if not hmac.compare_digest(actual_digest, expected_host_manifest_digest):
        raise WAWManifestCodecError("host manifest digest mismatch")
    return _create_registry_from_verified_manifest(
        manifest=manifest,
        host_manifest_digest=actual_digest,
        epoch_store=epoch_store,
        executor=executor,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )


def create_waw_lifecycle_registry_from_manifest_bundle_v1_compat(
    *,
    raw_api_host_anchor: bytes,
    raw_runtime_host_manifest: bytes,
    raw_project_root_manifest: bytes,
    raw_cgroup_delegation_manifest: bytes,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Internal/test-only bootstrap from a strictly cross-pinned byte bundle.

    This is a data-only strict boundary.  The API host anchor, Runtime host
    manifest, and Project Root manifest are decoded and cross-verified before
    the Runtime epoch is consumed.  The verified Runtime record and the exact
    digest of its supplied canonical bytes are then passed to the shared
    registry constructor, preventing a second decode or an independently
    selected digest from diverging from the bytes that were checked.

    The caller remains responsible for installer/host provenance and for
    supplying an executor that is already bound to the same trust root.  This
    helper performs no file discovery, socket binding, process execution, or
    credential handling.

    Production callers must use
    :func:`create_waw_lifecycle_registry_from_filesystem_bundle`, which keeps
    the loader provenance boundary intact.  This raw-byte adapter is retained
    only for synthetic fixtures and compatibility tests.
    """

    pin = verify_api_host_anchor_cross_manifest(
        raw_api_host_anchor,
        raw_runtime_host_manifest,
        raw_project_root_manifest,
        raw_cgroup_delegation_manifest,
    )
    return _create_registry_from_verified_manifest(
        manifest=pin.runtime,
        host_manifest_digest=pin.runtime_manifest_digest,
        epoch_store=epoch_store,
        executor=executor,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )


def create_waw_lifecycle_registry_from_loaded_manifest_bundle_v1_compat(
    *,
    bundle: WAWCanonicalManifestBundle,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Bootstrap from the exact raw bytes returned by the filesystem loader.

    Historical test callers should pass the value returned by
    :func:`load_canonical_waw_manifest_bundle` as one object, rather than
    independently selecting four byte strings.  This preserves the loader's
    bundle boundary through cross-pin verification.  The operation remains a
    data-only bootstrap helper: installer enrollment, host attestation, and
    Runtime service activation are still explicit caller/host gates.
    """

    if not isinstance(bundle, WAWCanonicalManifestBundle):
        raise TypeError("bundle must be a WAWCanonicalManifestBundle")
    return create_waw_lifecycle_registry_from_manifest_bundle_v1_compat(
        raw_api_host_anchor=bundle.api_host_anchor,
        raw_runtime_host_manifest=bundle.runtime_host_installation,
        raw_project_root_manifest=bundle.project_root,
        raw_cgroup_delegation_manifest=bundle.cgroup_delegation,
        epoch_store=epoch_store,
        executor=executor,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )


def create_waw_lifecycle_registry_from_filesystem_bundle_v1_compat(
    *,
    directory: Path,
    expected_api_host_anchor_digest: str,
    expected_uid: int,
    expected_gid: int,
    epoch_store: WAWRuntimeEpochStore,
    expected_ancestor_mode: int | None = None,
    expected_directory_mode: int = 0o750,
    expected_file_mode: int = 0o440,
    expected_max_bytes: int = 64 * 1024,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Load and bootstrap one historical installer-owned v1 test bundle.

    The loader establishes descriptor-relative filesystem provenance, then the
    external API-anchor digest is checked before strict cross-manifest decode
    and durable Runtime epoch consumption.  This is still a non-activating
    compatibility boundary and cannot be used by the top-level production API.
    """

    if (
        not isinstance(expected_api_host_anchor_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_api_host_anchor_digest) is None
        or expected_api_host_anchor_digest == "0" * 64
    ):
        raise WAWManifestCodecError("expected API host anchor digest is invalid")
    bundle = load_canonical_waw_manifest_bundle(
        directory,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_ancestor_mode=expected_ancestor_mode,
        expected_directory_mode=expected_directory_mode,
        expected_file_mode=expected_file_mode,
        expected_max_bytes=expected_max_bytes,
    )
    actual_anchor_digest = manifest_sha256(bundle.api_host_anchor)
    if not hmac.compare_digest(actual_anchor_digest, expected_api_host_anchor_digest):
        raise WAWManifestCodecError("API host anchor digest mismatch")
    return create_waw_lifecycle_registry_from_loaded_manifest_bundle_v1_compat(
        bundle=bundle,
        epoch_store=epoch_store,
        executor=executor,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )


@dataclass(frozen=True)
class WAWFixedRuntimeComposition:
    """One v2 manifest trust root, epoch, executor and lifecycle registry."""

    registry: WAWLifecycleRegistry
    executor: WAWSupervisorExecutor
    runtime_epoch: str
    execution_authority: WAWVerifiedExecutionAuthority


def create_waw_lifecycle_registry_from_manifest_bundle_test_only(
    *,
    raw_api_host_anchor: bytes,
    raw_runtime_host_manifest: bytes,
    raw_project_root_manifest: bytes,
    raw_cgroup_delegation_manifest: bytes,
    raw_executable_inventory: bytes,
    raw_interactive_profiles: bytes,
    raw_tmux_config: bytes,
    raw_sandbox_policy_bundle: bytes,
    raw_socket_policy: bytes,
    raw_claude_managed_policy: bytes,
    raw_codex_managed_policy: bytes,
    raw_codex_requirements_policy: bytes,
    raw_codex_managed_config_policy: bytes,
    epoch_store: WAWRuntimeEpochStore,
    executor_factory: Callable[[str, WAWVerifiedExecutionAuthority], WAWSupervisorExecutor],
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> WAWFixedRuntimeComposition:
    """Verify the complete production v2 byte bundle before consuming an epoch."""

    pin = verify_api_host_anchor_v2_cross_manifest(
        raw_api_host_anchor,
        raw_runtime_host_manifest,
        raw_project_root_manifest,
        raw_cgroup_delegation_manifest,
        raw_executable_inventory,
        raw_interactive_profiles,
        raw_tmux_config,
        raw_sandbox_policy_bundle,
        raw_socket_policy,
        raw_claude_managed_policy,
        raw_codex_managed_policy,
        raw_codex_requirements_policy,
        raw_codex_managed_config_policy,
    )
    return create_waw_lifecycle_registry_from_loaded_manifest_bundle_test_only(
        manifest=pin,
        epoch_store=epoch_store,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )


def create_waw_lifecycle_registry_from_loaded_manifest_bundle_test_only(
    *,
    manifest: CrossManifestPinV2,
    epoch_store: WAWRuntimeEpochStore,
    executor_factory: Callable[[str, WAWVerifiedExecutionAuthority], WAWSupervisorExecutor],
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> WAWFixedRuntimeComposition:
    """Compose from one already verified v2 bundle without selecting it again."""

    if type(manifest) is not CrossManifestPinV2:
        raise TypeError("manifest must be a verified CrossManifestPinV2")
    authority = _issue_verified_execution_authority(manifest)
    return _compose_verified_v2(
        manifest=manifest,
        authority=authority,
        epoch_store=epoch_store,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )


def create_waw_lifecycle_registry_from_filesystem_bundle(
    *,
    runtime_manifest_path: Path,
    public_directory: Path,
    expected_runtime_gid: int,
    epoch_store: WAWRuntimeEpochStore,
    executor_factory: Callable[[str, WAWVerifiedExecutionAuthority], WAWSupervisorExecutor],
    binding_digest_factory: BindingDigestFactory | None = None,
    expected_runtime_uid: int = 0,
    expected_public_uid: int = 0,
    expected_public_gid: int = 0,
    runtime_trusted_root: Path | None = None,
    expected_runtime_parent_mode: int = 0o750,
    expected_runtime_file_mode: int = 0o440,
    expected_public_directory_mode: int = 0o755,
    expected_public_file_mode: int = 0o444,
    expected_max_bytes: int = 64 * 1024,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> WAWFixedRuntimeComposition:
    """Load the full v2 production bundle and compose one exact Runtime epoch."""

    manifest = load_verified_canonical_waw_manifest_bundle_v2(
        runtime_manifest_path,
        public_directory,
        expected_runtime_uid=expected_runtime_uid,
        expected_runtime_gid=expected_runtime_gid,
        expected_public_uid=expected_public_uid,
        expected_public_gid=expected_public_gid,
        runtime_trusted_root=runtime_trusted_root,
        expected_runtime_parent_mode=expected_runtime_parent_mode,
        expected_runtime_file_mode=expected_runtime_file_mode,
        expected_public_directory_mode=expected_public_directory_mode,
        expected_public_file_mode=expected_public_file_mode,
        expected_max_bytes=expected_max_bytes,
    )
    authority = _issue_verified_execution_authority(manifest)
    verifier: WAWProjectBindingVerifier | None = None
    store: WAWProjectBindingStore | None = None
    try:
        if binding_digest_factory is None:
            verifier, store = _filesystem_v2_binding_resources(manifest)
        return _compose_verified_v2(
            manifest=manifest,
            authority=authority,
            epoch_store=epoch_store,
            executor_factory=executor_factory,
            binding_digest_factory=binding_digest_factory,
            binding_verifier=verifier,
            binding_store=store,
            attestation_store=attestation_store,
            cgroup_attestation_store=cgroup_attestation_store,
            cgroup_attestation_factory=cgroup_attestation_factory,
        )
    except BaseException:
        if verifier is not None:
            with suppress(WAWProjectBindingVerifierError):
                verifier.close()
        if store is not None:
            with suppress(WAWProjectBindingStoreError):
                store.close()
        raise


def _compose_verified_v2(
    *,
    manifest: CrossManifestPinV2,
    authority: WAWVerifiedExecutionAuthority,
    epoch_store: WAWRuntimeEpochStore,
    executor_factory: Callable[[str, WAWVerifiedExecutionAuthority], WAWSupervisorExecutor],
    binding_digest_factory: BindingDigestFactory | None,
    binding_verifier: WAWProjectBindingVerifier | None = None,
    binding_store: WAWProjectBindingStore | None = None,
    attestation_store: WAWWorkspaceAttestationStore | None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None,
    cgroup_attestation_factory: CgroupAttestationFactory | None,
) -> WAWFixedRuntimeComposition:
    """Prepare and validate exact authority binding before epoch commit."""

    if not callable(executor_factory):
        raise TypeError("executor_factory must be callable")

    def prepare(runtime_epoch: str) -> WAWSupervisorExecutor:
        return executor_factory(runtime_epoch, authority)

    def validate(executor: WAWSupervisorExecutor, runtime_epoch: str) -> None:
        if (
            type(executor) is not WAWSupervisorExecutor
            or executor.runtime_epoch != runtime_epoch
            or executor.conflict_coordinator is None
            or executor.execution_authority is not authority
            or type(executor.auth_probe) is not WAWCachedPublicAuthProbe
        ):
            raise RuntimeOperationError(
                "WAW_RUNTIME_EPOCH_INVALID",
                "Fixed executor is not bound to the exact execution authority",
                category="validation",
            )

    consumed, executor = epoch_store.consume_prepared(prepare, validate)
    runtime_epoch = str(consumed)
    registry = WAWLifecycleRegistry(
        runtime_host_installation_id=manifest.runtime.runtime_host_installation_id,
        runtime_host_installation_revision=manifest.runtime.runtime_host_installation_revision,
        host_manifest_digest=manifest.runtime_manifest_digest,
        project_root_manifest_digest=manifest.runtime.project_root_manifest_digest,
        enrollment_epoch=manifest.runtime.enrollment_epoch,
        enrollment_state=manifest.runtime.enrollment_state,
        executor=executor,
        binding_digest_factory=binding_digest_factory,
        binding_verifier=binding_verifier,
        binding_store=binding_store,
        runtime_epoch=runtime_epoch,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )
    return WAWFixedRuntimeComposition(registry, executor, runtime_epoch, authority)


def _filesystem_v2_binding_resources(
    manifest: CrossManifestPinV2,
) -> tuple[WAWProjectBindingVerifier, WAWProjectBindingStore]:
    """Open only the manifest-pinned Project root and fixed Runtime store."""

    try:
        root_uid = int(manifest.project_root.root_uid)
        root_gid = int(manifest.project_root.root_gid)
        if root_uid < 0 or root_gid < 0:
            raise ValueError
        verifier = WAWProjectBindingVerifier(
            Path(manifest.project_root.configured_root),
            expected_uid=root_uid,
            expected_gid=root_gid,
        )
        try:
            store = WAWProjectBindingStore(
                _FILESYSTEM_V2_BINDING_STORE,
                expected_uid=root_uid,
                expected_gid=root_gid,
            )
        except BaseException:
            verifier.close()
            raise
        return verifier, store
    except (
        OSError,
        ValueError,
        WAWProjectBindingStoreError,
        WAWProjectBindingVerifierError,
    ) as exc:
        raise RuntimeOperationError(
            "WAW_BINDING_STORE_UNAVAILABLE",
            "Runtime Project binding evidence is unavailable",
            category="unavailable",
        ) from exc


def _create_registry_from_verified_manifest(
    *,
    manifest: RuntimeHostManifest | RuntimeHostManifestV2,
    host_manifest_digest: str,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None = None,
    cgroup_attestation_factory: CgroupAttestationFactory | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Internal adapter from the strict codec record to lifecycle state."""

    return _create_registry(
        runtime_host_installation_id=manifest.runtime_host_installation_id,
        runtime_host_installation_revision=manifest.runtime_host_installation_revision,
        host_manifest_digest=host_manifest_digest,
        project_root_manifest_digest=manifest.project_root_manifest_digest,
        enrollment_epoch=manifest.enrollment_epoch,
        enrollment_state=manifest.enrollment_state,
        epoch_store=epoch_store,
        executor=executor,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )


def _create_registry(
    *,
    runtime_host_installation_id: str,
    runtime_host_installation_revision: str,
    host_manifest_digest: str,
    project_root_manifest_digest: str,
    enrollment_epoch: str,
    enrollment_state: str,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None,
    cgroup_attestation_store: WAWCgroupAttestationStore | None,
    cgroup_attestation_factory: CgroupAttestationFactory | None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Shared construction after either compatibility or strict validation.

    Epoch consumption is a durable one-way fence.  It deliberately precedes
    executor and registry construction so every injected component observes
    the exact epoch persisted for this startup.  If construction fails,
    callers must treat the attempt as failed and restart using the next epoch;
    the consumed value must never be reused.
    """

    if (executor is None) == (executor_factory is None):
        raise ValueError("provide exactly one of executor or executor_factory")
    consumed_epoch = str(epoch_store.consume())
    actual_executor = executor_factory(consumed_epoch) if executor_factory is not None else executor
    if actual_executor is None:  # pragma: no cover - guarded by the exclusivity check
        raise RuntimeError("WAW executor factory returned no executor")
    registry = WAWLifecycleRegistry(
        runtime_host_installation_id=runtime_host_installation_id,
        runtime_host_installation_revision=runtime_host_installation_revision,
        host_manifest_digest=host_manifest_digest,
        project_root_manifest_digest=project_root_manifest_digest,
        enrollment_epoch=enrollment_epoch,
        enrollment_state=enrollment_state,
        executor=actual_executor,
        binding_digest_factory=binding_digest_factory,
        runtime_epoch=consumed_epoch,
        attestation_store=attestation_store,
        cgroup_attestation_store=cgroup_attestation_store,
        cgroup_attestation_factory=cgroup_attestation_factory,
    )
    return registry, consumed_epoch


def build_waw_control_server(
    *,
    sockets: WAWActivatedSockets,
    registry: WAWLifecycleRegistry,
    expected_peer_uid: int,
    expected_peer_gid: int,
    timeout_seconds: float = 2.0,
    max_active_connections: int = 64,
    max_active_dispatches: int = 16,
) -> WAWControlServer:
    """Bind control traffic to the registry's sole API process authority."""

    authority = registry.peer_authority
    if authority is None:
        authority = WAWPeerAuthority(
            expected_uid=expected_peer_uid,
            expected_gid=expected_peer_gid,
        )
        registry.configure_peer_authority(authority)
    elif (
        type(authority) is not WAWPeerAuthority
        or authority.expected_uid != expected_peer_uid
        or authority.expected_gid != expected_peer_gid
    ):
        raise ValueError("registry peer authority does not match the control peer identity")

    return WAWControlServer(
        sockets.control,
        registry.dispatch,
        expected_peer_uid=expected_peer_uid,
        expected_peer_gid=expected_peer_gid,
        timeout_seconds=timeout_seconds,
        max_active_connections=max_active_connections,
        max_active_dispatches=max_active_dispatches,
        peer_authorizer=authority.observe_control,
    )


def _create_waw_encrypted_servers_test_only(
    *,
    sockets: WAWActivatedSockets,
    registry: WAWLifecycleRegistry,
    executor: WAWSupervisorExecutor,
    runtime_epoch: str,
    static_key: Callable[[], bytes],
    peer_authority: WAWPeerAuthority,
    expected_peer_uid: int,
    expected_peer_gid: int,
    clock: Callable[[], float],
) -> tuple[WAWControlServer, WAWEncryptedServer, WAWEncryptedRegistry]:
    """Non-activating composition of qualified fixed Runtime endpoints.

    No key file is read. Missing fixed redraw, process peer/unit, pidfd, named socket
    or key custody evidence cannot be supplied by this helper; the deployment
    caller must provide qualified ports. Test keys/ports are software evidence.
    """
    stream_server, streams = _build_waw_encrypted_stream_server(
        sockets=sockets,
        registry=registry,
        executor=executor,
        runtime_epoch=runtime_epoch,
        static_key=static_key,
        peer_authority=peer_authority,
        expected_peer_uid=expected_peer_uid,
        expected_peer_gid=expected_peer_gid,
        clock=clock,
    )
    control_server = build_waw_control_server(
        sockets=sockets,
        registry=registry,
        expected_peer_uid=expected_peer_uid,
        expected_peer_gid=expected_peer_gid,
        max_active_connections=16,
        max_active_dispatches=8,
    )
    return control_server, stream_server, streams


def _build_waw_encrypted_stream_server(
    *,
    sockets: WAWActivatedSockets,
    registry: WAWLifecycleRegistry,
    executor: WAWSupervisorExecutor,
    runtime_epoch: str,
    static_key: Callable[[], bytes],
    peer_authority: WAWPeerAuthority,
    expected_peer_uid: int,
    expected_peer_gid: int,
    clock: Callable[[], float],
) -> tuple[WAWEncryptedServer, WAWEncryptedRegistry]:
    """Attach the one stream endpoint to an already composed control registry."""

    if not callable(static_key):
        raise ValueError("trusted encrypted Runtime providers are required")
    if (
        type(peer_authority) is not WAWPeerAuthority
        or registry.peer_authority is not peer_authority
        or peer_authority.expected_uid != expected_peer_uid
        or peer_authority.expected_gid != expected_peer_gid
        or executor.runtime_epoch != runtime_epoch
    ):
        raise ValueError("encrypted Runtime requires the registry's exact peer authority")

    def borrow_runtime_peer() -> RuntimePeer:
        try:
            lease = peer_authority.borrow()
        except WAWPeerAuthorityError:
            raise RuntimeOperationError(
                "RUNTIME_PEER_FORBIDDEN",
                "Runtime peer authority is unavailable",
                category="conflict",
            ) from None
        if lease is None:
            raise RuntimeOperationError(
                "RUNTIME_PEER_FORBIDDEN",
                "Runtime peer authority is unavailable",
                category="conflict",
            )
        try:
            return lease.runtime_peer
        finally:
            lease.close()

    def verify_stream(peer_socket: object) -> RuntimePeer | None:
        lease = peer_authority.observe_stream_socket(peer_socket)
        if lease is None:
            return None
        try:
            return lease.runtime_peer
        finally:
            lease.close()

    streams = WAWEncryptedRegistry(runtime_epoch=runtime_epoch, static_key=static_key, clock=clock)
    stream_server = WAWEncryptedServer.from_activated(
        sockets,
        streams,
        peer_verifier=verify_stream,
    )
    service = WAWEncryptedAttachmentService(
        streams,
        peer=borrow_runtime_peer,
        supervisor=executor.encrypted_supervisor,
        current=executor.encrypted_binding_current,
    )
    registry.configure_encrypted_attachments(service)
    return stream_server, streams


__all__ = [
    "WAWFixedRuntimeComposition",
    "build_waw_control_server",
    "create_waw_lifecycle_registry_from_filesystem_bundle",
    "create_waw_lifecycle_registry_from_filesystem_bundle_v1_compat",
    "create_waw_lifecycle_registry_from_loaded_manifest_bundle_test_only",
    "create_waw_lifecycle_registry_from_loaded_manifest_bundle_v1_compat",
    "create_waw_lifecycle_registry_from_manifest_bundle_test_only",
    "create_waw_lifecycle_registry_from_manifest_bundle_v1_compat",
    "create_waw_lifecycle_registry_from_manifest_bytes_v1_compat",
]
