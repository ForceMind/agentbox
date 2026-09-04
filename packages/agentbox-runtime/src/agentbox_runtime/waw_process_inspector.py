"""Exact process evidence and restart fences for the fixed WAW transport.

This module deliberately models authenticated OS handles as opaque objects.  It
never accepts a PID, process name, cgroup path, executable path, argv or
environment.  A native port creates the handles and every observation is
checked against the exact workspace generation that received them.
"""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agentbox_core.waw import (
    AgentType,
    validate_positive_u64,
    validate_project_id,
    validate_runtime_host_installation_id,
    validate_workspace_id,
)

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_process_protocol import LaunchGeometry
from agentbox_runtime.waw_pty import PtyGeometry

if TYPE_CHECKING:
    from agentbox_runtime.waw_supervisor import (
        RuntimeAttachmentCleanupEvidence,
        RuntimeAttachmentLease,
        RuntimeProbeEvidence,
        RuntimeStopEvidence,
    )

_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_MARKER = re.compile(r"\Awaw-v1:wri_[0-9a-f]{32}:[0-9a-f]{32}\Z")

NATIVE_HELPER_IDENTITIES = (
    "agentbox-waw-pane-bootstrap",
    "agentbox-waw-bridge",
    "agentbox-waw-attach-supervisor",
)


class FixedStartState(StrEnum):
    RUNNING = "RUNNING"
    NEEDS_INTERACTION = "NEEDS_INTERACTION"
    TRUST_REQUIRED = "TRUST_REQUIRED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"


@dataclass(frozen=True)
class FixedProcessIdentity:
    workspace_id: str
    project_id: str
    agent_type: AgentType
    generation: int
    workspace_hash: str
    managed_marker: str
    profile_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    runtime_epoch: str

    def __post_init__(self) -> None:
        validate_workspace_id(self.workspace_id)
        validate_project_id(self.project_id)
        if type(self.agent_type) is not AgentType:
            raise ValueError("fixed process agent_type is invalid")
        validate_positive_u64(self.generation, field="generation")
        if _DIGEST.fullmatch(self.workspace_hash) is None:
            raise ValueError("fixed process workspace hash is invalid")
        if _MARKER.fullmatch(self.managed_marker) is None:
            raise ValueError("fixed process marker is invalid")
        if _DIGEST.fullmatch(self.profile_digest) is None or self.profile_digest == "0" * 64:
            raise ValueError("fixed process profile digest is invalid")
        validate_runtime_host_installation_id(self.runtime_host_installation_id)
        _positive_decimal(
            self.runtime_host_installation_revision,
            "runtime_host_installation_revision",
        )
        if self.runtime_host_installation_id not in self.managed_marker:
            raise ValueError("fixed process marker does not match Runtime installation")
        _positive_decimal(self.runtime_epoch, "runtime_epoch")


@dataclass(frozen=True, repr=False)
class FixedLaunchHandles:
    """Seven launch roles plus one opaque authenticated cgroup handle."""

    project_directory: object
    selected_home_directory: object
    temp_directory: object
    bridge_executable: object
    vendor_executable: object
    policy_directory: object
    wbr_endpoint: object
    cgroup: object
    production_authority: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        handles = (
            self.project_directory,
            self.selected_home_directory,
            self.temp_directory,
            self.bridge_executable,
            self.vendor_executable,
            self.policy_directory,
            self.wbr_endpoint,
            self.cgroup,
        )
        if (
            any(handle is None for handle in handles)
            or len({id(handle) for handle in handles}) != 8
        ):
            raise ValueError("fixed launch handles are invalid")


@dataclass(frozen=True, repr=False)
class FixedProcessBinding:
    """Authenticated process-group/pidfd/cgroup handles returned by native code."""

    identity: FixedProcessIdentity
    pidfd_handle: object
    process_group_handle: object
    cgroup_handle: object

    def __post_init__(self) -> None:
        if type(self.identity) is not FixedProcessIdentity:
            raise ValueError("fixed process identity is invalid")
        handles = (self.pidfd_handle, self.process_group_handle, self.cgroup_handle)
        if (
            any(handle is None for handle in handles)
            or len({id(handle) for handle in handles}) != 3
        ):
            raise ValueError("fixed process binding handles are invalid")


@dataclass(frozen=True, repr=False)
class FixedLaunchRequest:
    identity: FixedProcessIdentity
    handles: FixedLaunchHandles
    initial_geometry: PtyGeometry

    def __post_init__(self) -> None:
        if type(self.identity) is not FixedProcessIdentity:
            raise ValueError("fixed launch identity is invalid")
        if type(self.handles) is not FixedLaunchHandles:
            raise ValueError("fixed launch handles are invalid")
        if type(self.initial_geometry) is not PtyGeometry:
            raise ValueError("fixed launch geometry is invalid")

    @property
    def launch_geometry(self) -> LaunchGeometry:
        return LaunchGeometry(self.initial_geometry.columns, self.initial_geometry.rows)


@dataclass(frozen=True)
class FixedStartProof:
    request: FixedLaunchRequest
    state: FixedStartState
    binding: FixedProcessBinding | None
    cgroup_populated: int

    def __post_init__(self) -> None:
        if type(self.request) is not FixedLaunchRequest or type(self.state) is not FixedStartState:
            raise ValueError("fixed start proof is invalid")
        if type(self.cgroup_populated) is not int or self.cgroup_populated not in {0, 1}:
            raise ValueError("fixed start cgroup evidence is invalid")
        if self.state is FixedStartState.LOGIN_REQUIRED:
            if self.binding is not None or self.cgroup_populated != 0:
                raise ValueError("LOGIN_REQUIRED must prove that no process was spawned")
        elif (
            type(self.binding) is not FixedProcessBinding
            or self.binding.identity != self.request.identity
            or self.cgroup_populated != 1
        ):
            raise ValueError("running start proof lacks the exact process binding")


@dataclass(frozen=True, repr=False)
class FixedAttachmentRequest:
    binding: FixedProcessBinding
    lease: RuntimeAttachmentLease
    geometry: PtyGeometry

    def __post_init__(self) -> None:
        if type(self.binding) is not FixedProcessBinding:
            raise ValueError("fixed attachment binding is invalid")
        if type(self.geometry) is not PtyGeometry:
            raise ValueError("fixed attachment geometry is invalid")
        claims = self.lease.claims
        identity = self.binding.identity
        if (
            claims.workspace_id != identity.workspace_id
            or claims.project_id != identity.project_id
            or claims.agent_type is not identity.agent_type
            or claims.generation != identity.generation
            or self.lease.runtime_epoch != identity.runtime_epoch
        ):
            raise ValueError("fixed attachment lease does not match the process binding")


@runtime_checkable
class FixedAttachmentPort(Protocol):
    """One exact attach child and client PTY; reads must be nonblocking."""

    def read_output(self, max_bytes: int) -> bytes | None: ...

    def write_input(self, data: bytes) -> None: ...

    def resize(self, geometry: PtyGeometry) -> bytes: ...

    def close(self) -> RuntimeAttachmentCleanupEvidence: ...


@runtime_checkable
class NativeProcessPort(Protocol):
    """Closed OS seam implemented by native fixed-action helpers or test fakes."""

    def start(self, request: FixedLaunchRequest) -> FixedStartProof: ...

    def open_attachment(self, request: FixedAttachmentRequest) -> FixedAttachmentPort: ...

    def probe(self, binding: FixedProcessBinding) -> RuntimeProbeEvidence: ...

    def stop(self, binding: FixedProcessBinding) -> RuntimeStopEvidence: ...

    def destroy_fenced(self, binding: FixedProcessBinding) -> RuntimeStopEvidence: ...


class LinuxNativeProcessPort:
    """Nominal marker for a qualified Linux/native-helper adapter.

    Production composition requires this nominal base class in addition to the
    structural protocol.  Synthetic ports can implement ``NativeProcessPort``
    for tests, but cannot be passed through the production constructor merely
    by returning a truthy flag. Concrete syscall/helper wiring is implemented
    by ``NativeHelperProcessPort``; real-host qualification remains separate.
    """

    native_helper_identities = NATIVE_HELPER_IDENTITIES
    production_qualified = False


class WAWProcessInspector:
    """Validate every native observation against one exact process binding."""

    def __init__(self, identity: FixedProcessIdentity, port: NativeProcessPort) -> None:
        if type(identity) is not FixedProcessIdentity:
            raise ValueError("fixed process identity is invalid")
        if not isinstance(port, NativeProcessPort):
            raise TypeError("port must implement NativeProcessPort")
        self._identity = identity
        self._port = port
        self._binding: FixedProcessBinding | None = None
        self._login_required = False
        self._fenced = False

    @property
    def binding(self) -> FixedProcessBinding | None:
        return self._binding

    @property
    def login_required(self) -> bool:
        return self._login_required

    @property
    def fenced(self) -> bool:
        return self._fenced

    def accept_start(self, proof: FixedStartProof, request: FixedLaunchRequest) -> FixedStartProof:
        if type(proof) is not FixedStartProof or proof.request is not request:
            raise RuntimeOperationError(
                "WAW_START_UNCONFIRMED", "Native start proof is not exact", category="conflict"
            )
        if proof.request.identity != self._identity:
            raise RuntimeOperationError(
                "WAW_START_UNCONFIRMED", "Native start identity is stale", category="conflict"
            )
        proof.__post_init__()
        self._binding = proof.binding
        self._login_required = proof.state is FixedStartState.LOGIN_REQUIRED
        self._fenced = False
        return proof

    def probe(self) -> RuntimeProbeEvidence:
        from agentbox_runtime.waw_supervisor import RuntimeProbeEvidence, RuntimeProbeState

        if self._fenced:
            return RuntimeProbeEvidence(
                self._identity.workspace_id,
                self._identity.generation,
                self._identity.managed_marker,
                RuntimeProbeState.UNKNOWN,
            )
        binding = self._binding
        if binding is None:
            if not self._login_required:
                raise RuntimeOperationError(
                    "WAW_PROBE_UNCONFIRMED", "No exact process binding exists", category="conflict"
                )
            return RuntimeProbeEvidence(
                self._identity.workspace_id,
                self._identity.generation,
                self._identity.managed_marker,
                RuntimeProbeState.LOGIN_REQUIRED,
            )
        evidence = self._port.probe(binding)
        return self._validate_probe(evidence)

    def stop(self) -> RuntimeStopEvidence:
        from agentbox_runtime.waw_supervisor import RuntimeStopEvidence

        if self._fenced:
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED",
                "Restart quarantine requires exact fenced destroy",
                category="conflict",
            )
        binding = self._binding
        if binding is None:
            if not self._login_required:
                raise RuntimeOperationError(
                    "WAW_STOP_UNCONFIRMED", "No exact process binding exists", category="conflict"
                )
            self._login_required = False
            return RuntimeStopEvidence(
                self._identity.workspace_id,
                self._identity.generation,
                self._identity.managed_marker,
                True,
                0,
            )
        evidence = self._validate_stop(self._port.stop(binding))
        self._binding = None
        self._login_required = False
        return evidence

    def quarantine_restart(self, binding: FixedProcessBinding | None) -> None:
        """Fence restart state without adopting or probing a prior epoch."""

        if binding is not None:
            if type(binding) is not FixedProcessBinding or not _same_process_except_epoch(
                binding.identity, self._identity
            ):
                raise ValueError("restart binding does not match the exact identity")
            if binding.identity.runtime_epoch == self._identity.runtime_epoch:
                raise ValueError("restart binding must belong to a prior Runtime epoch")
        self._binding = binding
        self._login_required = False
        self._fenced = True

    def destroy_fenced(self) -> RuntimeStopEvidence:
        binding = self._binding
        if not self._fenced or binding is None:
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED",
                "Fenced process has no authenticated native handle",
                category="conflict",
            )
        evidence = self._validate_stop(self._port.destroy_fenced(binding))
        self._binding = None
        self._fenced = False
        return evidence

    def _validate_probe(self, evidence: RuntimeProbeEvidence) -> RuntimeProbeEvidence:
        from agentbox_runtime.waw_supervisor import RuntimeProbeEvidence, RuntimeProbeState

        if (
            type(evidence) is not RuntimeProbeEvidence
            or evidence.workspace_id != self._identity.workspace_id
            or evidence.generation != self._identity.generation
            or evidence.managed_marker != self._identity.managed_marker
            or type(evidence.state) is not RuntimeProbeState
            or (
                evidence.state is RuntimeProbeState.EXITED
                and evidence.exit_code is not None
                and (type(evidence.exit_code) is not int or not -128 <= evidence.exit_code <= 255)
            )
            or (evidence.state is not RuntimeProbeState.EXITED and evidence.exit_code is not None)
        ):
            raise RuntimeOperationError(
                "WAW_PROBE_UNCONFIRMED", "Native process evidence is not exact", category="conflict"
            )
        return evidence

    def _validate_stop(self, evidence: RuntimeStopEvidence) -> RuntimeStopEvidence:
        from agentbox_runtime.waw_supervisor import RuntimeStopEvidence

        if (
            type(evidence) is not RuntimeStopEvidence
            or evidence.workspace_id != self._identity.workspace_id
            or evidence.generation != self._identity.generation
            or evidence.managed_marker != self._identity.managed_marker
            or evidence.closed is not True
            or type(evidence.remaining_members) is not int
            or evidence.remaining_members != 0
        ):
            self._fenced = True
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Native stop did not prove pidfd/process-group closure and populated=0",
                category="conflict",
            )
        return evidence


def require_linux_native_process_port(port: NativeProcessPort) -> LinuxNativeProcessPort:
    if (
        platform.system() != "Linux"
        or not isinstance(port, NativeProcessPort)
        or not isinstance(port, LinuxNativeProcessPort)
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Production fixed transport requires the Linux native helper port",
            category="unavailable",
        )
    if tuple(port.native_helper_identities) != NATIVE_HELPER_IDENTITIES:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Native helper identity set is invalid", category="unavailable"
        )
    if port.production_qualified is not True:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Native helper port lacks a verified executable handoff",
            category="unavailable",
        )
    return port


def _positive_decimal(value: str, field: str) -> None:
    if (
        type(value) is not str
        or not value.isascii()
        or not value.isdecimal()
        or value.startswith("0")
    ):
        raise ValueError(f"{field} is invalid")
    validate_positive_u64(int(value), field=field)


def _same_process_except_epoch(left: FixedProcessIdentity, right: FixedProcessIdentity) -> bool:
    return (
        left.workspace_id == right.workspace_id
        and left.project_id == right.project_id
        and left.agent_type is right.agent_type
        and left.generation == right.generation
        and left.workspace_hash == right.workspace_hash
        and left.managed_marker == right.managed_marker
        and left.profile_digest == right.profile_digest
        and left.runtime_host_installation_id == right.runtime_host_installation_id
        and left.runtime_host_installation_revision == right.runtime_host_installation_revision
    )


__all__ = [
    "NATIVE_HELPER_IDENTITIES",
    "FixedAttachmentPort",
    "FixedAttachmentRequest",
    "FixedLaunchHandles",
    "FixedLaunchRequest",
    "FixedProcessBinding",
    "FixedProcessIdentity",
    "FixedStartProof",
    "FixedStartState",
    "LinuxNativeProcessPort",
    "NativeProcessPort",
    "WAWProcessInspector",
    "require_linux_native_process_port",
]
