"""Explicit WAW Runtime bootstrap wiring for trusted, injected components.

This module deliberately does not discover files, bind sockets, or choose an
executor.  The Runtime entrypoint must first validate the installer-owned host
manifest and adopt the systemd-provided descriptor set, then pass those
objects here.  The epoch is consumed exactly once before the registry is
created, so a registry can never silently use its ``"1"`` development
default in a Runtime process.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_control_server import WAWControlServer
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_host_manifest import WAWRuntimeHostManifest
from agentbox_runtime.waw_lifecycle import (
    BindingDigestFactory,
    WAWLifecycleExecutor,
    WAWLifecycleRegistry,
)
from agentbox_runtime.waw_workspace_attestation import WAWWorkspaceAttestationStore


def _default_binding_digest(request: dict[str, Any]) -> str:
    """Return a deterministic digest for the closed binding request fields."""

    payload = json.dumps(
        request,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def create_waw_lifecycle_registry(
    *,
    manifest: WAWRuntimeHostManifest,
    epoch_store: WAWRuntimeEpochStore,
    executor: WAWLifecycleExecutor,
    binding_digest_factory: BindingDigestFactory | None = None,
    attestation_store: WAWWorkspaceAttestationStore | None = None,
) -> tuple[WAWLifecycleRegistry, str]:
    """Consume the Runtime epoch and construct a host-manifest-bound registry.

    ``manifest`` and ``epoch_store`` must already have passed their respective
    descriptor/provenance checks.  This helper is intentionally explicit about
    the side effect of consuming the epoch and returns the consumed value for
    startup logging/diagnostics without re-reading mutable state.
    """

    consumed_epoch = str(epoch_store.consume())
    registry = WAWLifecycleRegistry(
        runtime_host_installation_id=manifest.runtime_host_installation_id,
        runtime_host_installation_revision=manifest.runtime_host_installation_revision,
        host_manifest_digest=manifest.host_manifest_digest,
        project_root_manifest_digest=manifest.project_root_manifest_digest,
        enrollment_epoch=manifest.enrollment_epoch,
        enrollment_state=manifest.enrollment_state,
        executor=executor,
        binding_digest_factory=binding_digest_factory or _default_binding_digest,
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
    "create_waw_lifecycle_registry",
]
