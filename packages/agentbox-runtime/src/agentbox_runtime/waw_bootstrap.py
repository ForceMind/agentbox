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

from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_control_server import WAWControlServer
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_host_manifest import (
    WAWRuntimeHostManifestDevelopmentOnly,
    decode_canonical_waw_runtime_host_manifest,
)
from agentbox_runtime.waw_lifecycle import (
    BindingDigestFactory,
    WAWLifecycleExecutor,
    WAWLifecycleRegistry,
)
from agentbox_runtime.waw_manifest_codecs import (
    RuntimeHostManifest,
    WAWManifestCodecError,
    manifest_sha256,
    verify_api_host_anchor_cross_manifest,
)
from agentbox_runtime.waw_workspace_attestation import WAWWorkspaceAttestationStore


def create_waw_lifecycle_registry_development_only(
    *,
    manifest: WAWRuntimeHostManifestDevelopmentOnly,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Development/test-only compatibility bootstrap for the legacy record.

    Production entrypoints must call
    :func:`create_waw_lifecycle_registry_from_manifest_bytes`, which performs
    strict ``runtime-host-installation.v1`` decoding first.  Keeping this
    helper available avoids breaking synthetic fixtures while making its
    non-production status explicit.

    ``manifest`` and ``epoch_store`` must already have passed their respective
    descriptor/provenance checks.  This helper is intentionally explicit about
    the side effect of consuming the epoch and returns the consumed value for
    startup logging/diagnostics without re-reading mutable state.  When using
    ``executor_factory``, the factory receives that consumed epoch so its
    observations can be bound to the same Runtime trust root.
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
    )
    return registry, consumed_epoch


def create_waw_lifecycle_registry_from_manifest_bytes(
    *,
    raw_manifest: bytes,
    expected_host_manifest_digest: str,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Bootstrap from a strict, canonical ``runtime-host-installation.v1``.

    This is the production-facing data boundary.  Raw bytes are decoded and
    codec-validated before any Runtime registry is created; malformed,
    noncanonical, or legacy seven-field records are rejected closed.  The
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
    )


def create_waw_lifecycle_registry_from_manifest_bundle(
    *,
    raw_api_host_anchor: bytes,
    raw_runtime_host_manifest: bytes,
    raw_project_root_manifest: bytes,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Bootstrap from a strictly cross-pinned manifest bundle.

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
    """

    pin = verify_api_host_anchor_cross_manifest(
        raw_api_host_anchor,
        raw_runtime_host_manifest,
        raw_project_root_manifest,
    )
    return _create_registry_from_verified_manifest(
        manifest=pin.runtime,
        host_manifest_digest=pin.runtime_manifest_digest,
        epoch_store=epoch_store,
        executor=executor,
        executor_factory=executor_factory,
        binding_digest_factory=binding_digest_factory,
        attestation_store=attestation_store,
    )


def _create_registry_from_verified_manifest(
    *,
    manifest: RuntimeHostManifest,
    host_manifest_digest: str,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor | None = None,
    executor_factory: Callable[[str], WAWLifecycleExecutor] | None = None,
    binding_digest_factory: BindingDigestFactory,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
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
) -> tuple[WAWLifecycleRegistry, str]:
    """Shared construction after either compatibility or strict validation."""

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
    )
    return registry, consumed_epoch


def build_waw_control_server(
    *,
    sockets: WAWActivatedSockets,
    registry: WAWLifecycleRegistry,
    expected_peer_uid: int,
    expected_peer_gid: int,
    timeout_seconds: float = 2.0,
) -> WAWControlServer:
    """Bind the registry dispatcher to an already-validated control socket."""

    return WAWControlServer(
        sockets.control,
        registry.dispatch,
        expected_peer_uid=expected_peer_uid,
        expected_peer_gid=expected_peer_gid,
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "build_waw_control_server",
    "create_waw_lifecycle_registry_from_manifest_bundle",
    "create_waw_lifecycle_registry_from_manifest_bytes",
]
