"""Fixed interactive WAW transport over a narrow native process port.

The port receives only trusted, pre-bound records and opaque validated handles.
It cannot accept a caller command, path, argv, environment, PID, signal or
process name. This module includes the held-FD Linux helper adapter and the
process/PTY state machine shared by production and tests.
"""

from __future__ import annotations

import array
import contextlib
import errno
import fcntl
import hashlib
import hmac
import math
import os
import platform
import pty
import select
import signal
import socket
import stat
import struct
import termios
import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from agentbox_core.waw import AgentType

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import validate_project_id as validate_relative_project_key
from agentbox_runtime.waw_auth_probe import WAWPublicAuthEvidence, WAWPublicAuthResult
from agentbox_runtime.waw_executable import (
    WAWExecutableKind,
    WAWExecutableLaunchHandle,
)
from agentbox_runtime.waw_managed_command import (
    WAWManagedCommand,
    managed_command_agent_type,
    validate_managed_command,
)
from agentbox_runtime.waw_manifest_codecs import (
    CgroupDelegationManifest,
    CrossManifestPinV2,
    ProjectRootManifest,
)
from agentbox_runtime.waw_process_inspector import (
    FixedAttachmentPort,
    FixedAttachmentRequest,
    FixedLaunchHandles,
    FixedLaunchRequest,
    FixedProcessBinding,
    FixedProcessIdentity,
    FixedStartProof,
    FixedStartState,
    LinuxNativeProcessPort,
    NativeProcessPort,
    WAWProcessInspector,
    require_linux_native_process_port,
)
from agentbox_runtime.waw_process_protocol import (
    LAUNCH_FD_ROLE_BITMAP,
    WAWLaunchDescriptor,
    WBRResizeStateMachine,
    encode_launch_descriptor,
    encode_wbr_resize,
)
from agentbox_runtime.waw_pty import PtyGeometry, validate_input
from agentbox_runtime.waw_supervisor import (
    RuntimeAttachmentCleanupEvidence,
    RuntimeAttachmentLease,
    RuntimeProbeEvidence,
    RuntimeProbeState,
    RuntimeStartEvidence,
    RuntimeStopEvidence,
    SupervisorState,
)

MAX_NATIVE_OUTPUT_BYTES = 32 * 1024
AUTH_EVIDENCE_MAX_AGE_SECONDS = 30.0
NATIVE_READY = b"AWR1\x01\x01\x00\x00"
NATIVE_READY_DEADLINE_SECONDS = 1.0
NATIVE_LAUNCH_ACCEPT_DEADLINE_SECONDS = 5.0
_NATIVE_RUN_ROOT = "/run/agentbox-waw"
_EXECUTION_AUTHORITY_TOKEN = object()

OutputSink = Callable[[bytes], tuple[int, ...]]


@dataclass(frozen=True, init=False)
class WAWVerifiedExecutionAuthority:
    """Opaque authority issued only after a complete v2 cross-pin verification."""

    _manifest: CrossManifestPinV2

    def __init__(self, token: object, manifest: CrossManifestPinV2) -> None:
        if token is not _EXECUTION_AUTHORITY_TOKEN or type(manifest) is not CrossManifestPinV2:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Verified execution authority is not caller-constructible",
                category="unavailable",
            )
        object.__setattr__(self, "_manifest", manifest)

    @property
    def runtime_host_installation_id(self) -> str:
        return self._manifest.runtime.runtime_host_installation_id

    @property
    def runtime_host_installation_revision(self) -> str:
        return self._manifest.runtime.runtime_host_installation_revision

    @property
    def host_manifest_digest(self) -> str:
        return self._manifest.runtime_manifest_digest

    @property
    def executable_inventory_digest(self) -> str:
        return self._manifest.executable_inventory_digest

    @property
    def interactive_profile_bundle_digest(self) -> str:
        return self._manifest.interactive_profile_bundle_digest

    @property
    def project_root_manifest_digest(self) -> str:
        return self._manifest.project_root_manifest_digest

    @property
    def cgroup_delegation_manifest_digest(self) -> str:
        return self._manifest.cgroup_manifest_digest

    @property
    def tmux_config_digest(self) -> str:
        return self._manifest.tmux_config_digest

    @property
    def sandbox_policy_bundle_digest(self) -> str:
        return self._manifest.sandbox_policy_bundle_digest

    @property
    def socket_policy_digest(self) -> str:
        return self._manifest.socket_policy_digest

    @property
    def claude_managed_policy_digest(self) -> str:
        return self._manifest.claude_managed_policy_digest

    @property
    def codex_managed_policy_digest(self) -> str:
        return self._manifest.codex_managed_policy_digest

    @property
    def codex_requirements_policy_digest(self) -> str:
        return self._manifest.codex_requirements_policy_digest

    @property
    def codex_managed_config_policy_digest(self) -> str:
        return self._manifest.codex_managed_config_policy_digest

    @property
    def policy_digests(self) -> tuple[str, ...]:
        return (
            self.tmux_config_digest,
            self.sandbox_policy_bundle_digest,
            self.socket_policy_digest,
            self.claude_managed_policy_digest,
            self.codex_managed_policy_digest,
            self.codex_requirements_policy_digest,
            self.codex_managed_config_policy_digest,
        )

    def authorizes(self, identity: FixedProcessIdentity) -> bool:
        return (
            type(identity) is FixedProcessIdentity
            and identity.runtime_host_installation_id == self.runtime_host_installation_id
            and identity.runtime_host_installation_revision
            == self.runtime_host_installation_revision
            and identity.profile_digest == self.interactive_profile_bundle_digest
        )

    def vendor_executable_fingerprint(self, agent_type: AgentType) -> str:
        if type(agent_type) is not AgentType:
            raise ValueError("agent_type is invalid")
        expected = agent_type.value
        matches = [
            entry.sha256
            for entry in self._manifest.executable_inventory.executables
            if entry.kind == expected
        ]
        if len(matches) != 1:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Vendor executable authority is unavailable",
                category="unavailable",
            )
        return matches[0]


def _issue_verified_execution_authority(
    manifest: CrossManifestPinV2,
) -> WAWVerifiedExecutionAuthority:
    if type(manifest) is not CrossManifestPinV2:
        raise TypeError("strict verified v2 manifest is required")
    return WAWVerifiedExecutionAuthority(_EXECUTION_AUTHORITY_TOKEN, manifest)


@runtime_checkable
class CgroupControlHandle(Protocol):
    """Authenticated fixed cgroup-v2 actions; no path or PID is exposed."""

    def populated(self) -> int: ...

    def freeze(self) -> None: ...

    def frozen(self) -> int: ...

    def kill(self) -> None: ...

    def wait_empty(self, timeout_seconds: float) -> bool: ...

    def thaw(self) -> None: ...

    def contains_pidfd(self, pidfd: int) -> bool: ...


_CGROUP_HANDLE_TOKEN = object()


class LinuxCgroupControlHandle:
    """Nominal delegated cgroup-v2 directory with fixed file operations."""

    def __init__(
        self,
        token: object,
        *,
        descriptor: int,
        authority: WAWVerifiedExecutionAuthority,
        identity: FixedProcessIdentity,
        mount_identity: tuple[str, str],
    ) -> None:
        if token is not _CGROUP_HANDLE_TOKEN:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Linux cgroup handles are not caller-constructible",
                category="unavailable",
            )
        self._descriptor = descriptor
        self._issuer = _CGROUP_HANDLE_TOKEN
        self._authority = authority
        self._identity = identity
        self._mount_identity = mount_identity
        self._consumed = False
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def from_delegated_fd(
        cls,
        authority: WAWVerifiedExecutionAuthority,
        identity: FixedProcessIdentity,
        delegate_root: int,
    ) -> LinuxCgroupControlHandle:
        if (
            platform.system() != "Linux"
            or type(authority) is not WAWVerifiedExecutionAuthority
            or type(identity) is not FixedProcessIdentity
            or not authority.authorizes(identity)
        ):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Qualified Linux cgroup authority is unavailable",
                category="unavailable",
            )
        _role_fd(delegate_root, "directory")
        mount_identity = _verify_delegate_root(delegate_root, authority)
        workspace_name = f"ws-{identity.workspace_hash}-g{identity.generation}"
        workspace = _open_relative_directory(
            delegate_root,
            workspace_name,
            path_only=False,
            expected_uid=os.geteuid(),
        )
        try:
            descriptor = _open_relative_directory(
                workspace,
                "workload",
                path_only=False,
                expected_uid=os.geteuid(),
            )
        finally:
            _close_fd(workspace)
        try:
            _validate_delegated_workload(descriptor, authority, mount_identity)
        except BaseException:
            _close_fd(descriptor)
            raise
        return cls(
            _CGROUP_HANDLE_TOKEN,
            descriptor=descriptor,
            authority=authority,
            identity=identity,
            mount_identity=mount_identity,
        )

    @property
    def authority(self) -> WAWVerifiedExecutionAuthority:
        return self._authority

    @property
    def identity(self) -> FixedProcessIdentity:
        return self._identity

    @property
    def consumed(self) -> bool:
        with self._lock:
            return self._consumed

    def production_qualified_for(
        self,
        authority: WAWVerifiedExecutionAuthority,
        identity: FixedProcessIdentity,
    ) -> bool:
        with self._lock:
            return (
                self._issuer is _CGROUP_HANDLE_TOKEN
                and self._authority is authority
                and self._identity == identity
                and not self._closed
                and not self._consumed
                and type(self._mount_identity) is tuple
                and len(self._mount_identity) == 2
                and _fd_mount_id(self._descriptor) == self._mount_identity[0]
                and self._mount_identity[1] == authority._manifest.cgroup.cgroup_mount_filesystem_id
            )

    def take_launcher_fd(self, identity: FixedProcessIdentity) -> int:
        with self._lock:
            if self._closed or self._consumed or identity != self._identity:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Cgroup launch authority is consumed or identity-stale",
                    category="conflict",
                )
            if self.populated() != 0 or self.frozen() != 0:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Cgroup became live before prebirth launch",
                    category="conflict",
                )
            descriptor = fcntl.fcntl(self._fd(), fcntl.F_DUPFD_CLOEXEC, 64)
            self._consumed = True
            return descriptor

    def populated(self) -> int:
        return _cgroup_event(self._fd(), "populated")

    def freeze(self) -> None:
        _write_cgroup_file(self._fd(), "cgroup.freeze", b"1\n")

    def frozen(self) -> int:
        return _cgroup_event(self._fd(), "frozen")

    def kill(self) -> None:
        _write_cgroup_file(self._fd(), "cgroup.kill", b"1\n")

    def wait_empty(self, timeout_seconds: float) -> bool:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < float(timeout_seconds) <= 10
        ):
            raise ValueError("cgroup wait timeout is invalid")
        deadline = time.monotonic() + float(timeout_seconds)
        while self.populated() != 0:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return True

    def thaw(self) -> None:
        _write_cgroup_file(self._fd(), "cgroup.freeze", b"0\n")

    def contains_pidfd(self, pidfd: int) -> bool:
        pid = _pid_from_pidfd(pidfd)
        if pid is None:
            return False
        members = _read_cgroup_file(self._fd(), "cgroup.procs").splitlines()
        return str(pid) in members

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                _close_fd(self._descriptor)
                self._closed = True

    def _fd(self) -> int:
        with self._lock:
            if self._closed:
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED", "Cgroup handle is closed", category="conflict"
                )
            descriptor = self._descriptor
            mount_identity = getattr(self, "_mount_identity", None)
            if mount_identity is not None and _fd_mount_id(descriptor) != mount_identity[0]:
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED",
                    "Cgroup mount identity changed",
                    category="conflict",
                )
            return descriptor


@dataclass(frozen=True, repr=False)
class NativeWBREndpoint:
    native: socket.socket
    controller: socket.socket

    def __post_init__(self) -> None:
        if (
            type(self.native) is not socket.socket
            or type(self.controller) is not socket.socket
            or not _is_unix_seqpacket(self.native)
            or not _is_unix_seqpacket(self.controller)
        ):
            raise ValueError("WBR endpoint must be an exact SOCK_SEQPACKET pair")
        try:
            self.native.getpeername()
            self.controller.getpeername()
        except OSError as exc:
            raise ValueError("WBR endpoint must be connected") from exc


_PRODUCTION_LAUNCH_TOKEN = object()


class WAWProductionLaunchHandles:
    """Nominal one-shot fixed launch handles issued by the v2 factory."""

    def __init__(
        self,
        token: object,
        *,
        identity: FixedProcessIdentity,
        handles: FixedLaunchHandles,
        authority: WAWVerifiedExecutionAuthority,
        project_identity: tuple[int, int, int, int, int],
    ) -> None:
        if token is not _PRODUCTION_LAUNCH_TOKEN:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Production launch handles are not caller-constructible",
                category="unavailable",
            )
        self._identity = identity
        self._handles = handles
        self._authority = authority
        self._project_identity = project_identity
        self._consumed = False
        self._finalizer = weakref.finalize(
            self,
            _cleanup_unconsumed_launch_handles,
            handles,
        )

    def take(self, identity: FixedProcessIdentity) -> FixedLaunchHandles:
        if self._consumed or identity != self._identity:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Production launch handles are consumed or identity-stale",
                category="unavailable",
            )
        self._consumed = True
        self._finalizer.detach()
        return self._handles


class WAWVerifiedLaunchHandleFactory:
    """Issue Project/profile/cgroup launch handles from installed descriptors."""

    def __init__(
        self,
        *,
        authority: WAWVerifiedExecutionAuthority,
        project_root: int,
        claude_home: int,
        codex_home: int,
        temp_root: int,
        claude_policy_directory: int,
        codex_policy_directory: int,
        claude_policy_file: int,
        codex_requirements_file: int,
        codex_managed_config_file: int,
    ) -> None:
        if platform.system() != "Linux" or type(authority) is not WAWVerifiedExecutionAuthority:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Verified Linux launch authority is unavailable",
                category="unavailable",
            )
        manifest = authority._manifest.project_root
        _verify_project_root_descriptor(project_root, manifest)
        installed = (
            (claude_home, "/var/lib/agentbox-waw/vendor-homes/claude", os.geteuid(), 0o700),
            (codex_home, "/var/lib/agentbox-waw/vendor-homes/codex", os.geteuid(), 0o700),
            (temp_root, f"{_NATIVE_RUN_ROOT}/tmp", os.geteuid(), 0o755),
            (claude_policy_directory, "/etc/claude-code", 0, 0o755),
            (codex_policy_directory, "/etc/codex", 0, 0o755),
        )
        for descriptor, path, uid, mode in installed:
            _verify_installed_directory(descriptor, path, expected_uid=uid, expected_mode=mode)
        _verify_installed_file(
            claude_policy_file,
            "/etc/claude-code/managed-settings.json",
            authority.claude_managed_policy_digest,
        )
        _verify_installed_file(
            codex_requirements_file,
            "/etc/codex/requirements.toml",
            authority.codex_requirements_policy_digest,
        )
        _verify_installed_file(
            codex_managed_config_file,
            "/etc/codex/managed_config.toml",
            authority.codex_managed_config_policy_digest,
        )
        source = (
            project_root,
            claude_home,
            codex_home,
            temp_root,
            claude_policy_directory,
            codex_policy_directory,
            claude_policy_file,
            codex_requirements_file,
            codex_managed_config_file,
        )
        duplicated: list[int] = []
        try:
            for descriptor in source:
                duplicated.append(fcntl.fcntl(descriptor, fcntl.F_DUPFD_CLOEXEC, 64))
        except BaseException:
            for descriptor in duplicated:
                _close_fd(descriptor)
            raise
        (
            self._project_root,
            self._claude_home,
            self._codex_home,
            self._temp_root,
            self._claude_policy,
            self._codex_policy,
            self._claude_policy_file,
            self._codex_requirements_file,
            self._codex_managed_config_file,
        ) = duplicated
        self._authority = authority
        self._closed = False

    @property
    def authority(self) -> WAWVerifiedExecutionAuthority:
        return self._authority

    def create(
        self,
        *,
        identity: FixedProcessIdentity,
        relative_key: str,
        wbr_endpoint: NativeWBREndpoint,
        cgroup: LinuxCgroupControlHandle,
    ) -> WAWProductionLaunchHandles:
        if self._closed or not self._authority.authorizes(identity):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Launch factory authority is unavailable",
                category="unavailable",
            )
        if (
            type(wbr_endpoint) is not NativeWBREndpoint
            or type(cgroup) is not LinuxCgroupControlHandle
            or not cgroup.production_qualified_for(self._authority, identity)
        ):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Production WBR/cgroup handle is not authority-bound",
                category="unavailable",
            )
        _verify_project_root_descriptor(self._project_root, self._authority._manifest.project_root)
        for descriptor, path, uid, mode in (
            (
                self._claude_home,
                "/var/lib/agentbox-waw/vendor-homes/claude",
                os.geteuid(),
                0o700,
            ),
            (
                self._codex_home,
                "/var/lib/agentbox-waw/vendor-homes/codex",
                os.geteuid(),
                0o700,
            ),
            (self._temp_root, f"{_NATIVE_RUN_ROOT}/tmp", os.geteuid(), 0o755),
            (self._claude_policy, "/etc/claude-code", 0, 0o755),
            (self._codex_policy, "/etc/codex", 0, 0o755),
        ):
            _verify_installed_directory(descriptor, path, expected_uid=uid, expected_mode=mode)
        _verify_installed_file(
            self._claude_policy_file,
            "/etc/claude-code/managed-settings.json",
            self._authority.claude_managed_policy_digest,
        )
        _verify_installed_file(
            self._codex_requirements_file,
            "/etc/codex/requirements.toml",
            self._authority.codex_requirements_policy_digest,
        )
        _verify_installed_file(
            self._codex_managed_config_file,
            "/etc/codex/managed_config.toml",
            self._authority.codex_managed_config_policy_digest,
        )
        project = workspace_temp = temporary = home = policy = -1
        try:
            key = validate_relative_project_key(relative_key)
            project = _open_relative_directory(
                self._project_root, key, path_only=True, expected_uid=os.geteuid()
            )
            workspace_temp = _open_relative_directory(
                self._temp_root,
                identity.workspace_hash,
                path_only=False,
                expected_uid=os.geteuid(),
                expected_mode=0o700,
            )
            temporary = _open_relative_directory(
                workspace_temp,
                "vendor",
                path_only=False,
                expected_uid=os.geteuid(),
                expected_mode=0o700,
            )
            _close_fd(workspace_temp)
            workspace_temp = -1
            home_source = (
                self._claude_home if identity.agent_type is AgentType.CLAUDE else self._codex_home
            )
            policy_source = (
                self._claude_policy
                if identity.agent_type is AgentType.CLAUDE
                else self._codex_policy
            )
            home = fcntl.fcntl(home_source, fcntl.F_DUPFD_CLOEXEC, 64)
            policy = fcntl.fcntl(policy_source, fcntl.F_DUPFD_CLOEXEC, 64)
        except BaseException:
            for descriptor in (project, workspace_temp, temporary, home, policy):
                if descriptor >= 0:
                    _close_fd(descriptor)
            raise
        handles = FixedLaunchHandles(
            project_directory=project,
            selected_home_directory=home,
            temp_directory=temporary,
            bridge_executable=object(),
            vendor_executable=object(),
            policy_directory=policy,
            wbr_endpoint=wbr_endpoint,
            cgroup=cgroup,
            production_authority=self._authority,
        )
        return WAWProductionLaunchHandles(
            _PRODUCTION_LAUNCH_TOKEN,
            identity=identity,
            handles=handles,
            authority=self._authority,
            project_identity=_directory_identity(project),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for descriptor in (
            self._project_root,
            self._claude_home,
            self._codex_home,
            self._temp_root,
            self._claude_policy,
            self._codex_policy,
            self._claude_policy_file,
            self._codex_requirements_file,
            self._codex_managed_config_file,
        ):
            _close_fd(descriptor)


@dataclass(frozen=True)
class NativeHelperHandles:
    """Held helper/tmux descriptors; no filesystem path enters the port."""

    pane_bootstrap: int
    attach_supervisor: int
    tmux_executable: int
    tmux_socket_directory: int
    tmux_config: int


@dataclass
class _NativeProcessResources:
    pid: int
    process_group: int
    pidfd: int
    stdin: int
    stdout: int
    stderr: int
    control: socket.socket
    wbr: socket.socket
    cgroup: CgroupControlHandle
    tmux_socket_identity: tuple[int, int]
    exit_code: int | None = None
    reaped: bool = False


@dataclass(frozen=True, repr=False)
class _NativeProcessGroup:
    value: int


class _NativeAttachment:
    def __init__(
        self,
        *,
        pid: int,
        pidfd: int,
        master: int,
        lease: RuntimeAttachmentLease,
        process: _NativeProcessResources,
        stop_timeout: float,
    ) -> None:
        self._pid = pid
        self._pidfd = pidfd
        self._master = master
        self._lease = lease
        self._process = process
        self._stop_timeout = stop_timeout
        self._sequence = 0
        self._closed = False
        self._closing = False
        self._permanent_failure = False
        os.set_blocking(master, False)

    def _require_usable(self) -> None:
        if self._closed or self._closing or self._permanent_failure:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_STALE",
                "Native attachment is closed or cleanup-fenced",
                category="conflict",
            )

    def read_output(self, max_bytes: int) -> bytes | None:
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_NATIVE_OUTPUT_BYTES:
            raise ValueError("native output read bound is invalid")
        self._require_usable()
        try:
            return os.read(self._master, max_bytes)
        except BlockingIOError:
            return None
        except OSError as exc:
            if exc.errno == errno.EIO:
                return b""
            raise

    def write_input(self, data: bytes) -> None:
        self._require_usable()
        written = os.write(self._master, data)
        if written != len(data):
            raise RuntimeOperationError(
                "WAW_INPUT_UNCERTAIN", "Native PTY write was partial", category="broken"
            )

    def resize(self, geometry: PtyGeometry) -> bytes:
        self._require_usable()
        fcntl.ioctl(
            self._master,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", geometry.rows, geometry.columns, 0, 0),
        )
        self._sequence += 1
        request = encode_wbr_resize(
            sequence=self._sequence,
            generation=self._lease.claims.generation,
            columns=geometry.columns,
            rows=geometry.rows,
        )
        self._process.wbr.send(request)
        readable, _, _ = select.select([self._process.wbr], [], [], 1.0)
        if not readable:
            raise RuntimeOperationError(
                "WAW_RESIZE_FAILED", "Native WBR ACK deadline expired", category="conflict"
            )
        return self._process.wbr.recv(65)

    def close(self) -> RuntimeAttachmentCleanupEvidence:
        if self._closed:
            return RuntimeAttachmentCleanupEvidence(self._lease, True, 0)
        if self._permanent_failure:
            return RuntimeAttachmentCleanupEvidence(self._lease, False, 1)
        self._closing = True
        try:
            _signal_pidfd(self._pidfd, signal.SIGTERM)
            with _suppress_process_lookup():
                os.killpg(self._pid, signal.SIGTERM)
            reaped = _wait_pidfd(self._pidfd, self._stop_timeout) is not None
            if not reaped:
                _signal_pidfd(self._pidfd, signal.SIGKILL)
                with _suppress_process_lookup():
                    os.killpg(self._pid, signal.SIGKILL)
                reaped = _wait_pidfd(self._pidfd, self._stop_timeout) is not None
        except Exception:
            self._permanent_failure = True
            return RuntimeAttachmentCleanupEvidence(self._lease, False, 1)
        if not reaped:
            return RuntimeAttachmentCleanupEvidence(self._lease, False, 1)
        _close_fd(self._master)
        _close_fd(self._pidfd)
        self._closed = True
        return RuntimeAttachmentCleanupEvidence(self._lease, True, 0)


class NativeHelperProcessPort(LinuxNativeProcessPort):
    """Linux adapter for the fixed native helper ABI using held descriptors.

    The direct raw-FD constructor is development evidence and deliberately
    leaves ``production_qualified`` false. Production composition must use
    :meth:`from_verified_execution_authority`. The adapter performs no
    executable discovery and accepts no path, argv, environment, PID, signal
    or tmux target from a request. Helper arguments, descriptor numbers and
    environment are fixed here and in the native ABI.
    """

    def __init__(
        self,
        helpers: NativeHelperHandles,
        *,
        authenticated: Callable[[FixedProcessIdentity], bool],
        stop_timeout_seconds: float = 1.0,
    ) -> None:
        if platform.system() != "Linux":
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Native WAW helpers require Linux",
                category="unavailable",
            )
        if type(helpers) is not NativeHelperHandles or not callable(authenticated):
            raise TypeError("qualified native helper handles are required")
        if (
            isinstance(stop_timeout_seconds, bool)
            or not isinstance(stop_timeout_seconds, (int, float))
            or not math.isfinite(float(stop_timeout_seconds))
            or not 0 < float(stop_timeout_seconds) <= 10
        ):
            raise ValueError("native stop timeout is invalid")
        duplicated: list[int] = []
        try:
            for descriptor, role in (
                (helpers.pane_bootstrap, "executable"),
                (helpers.attach_supervisor, "executable"),
                (helpers.tmux_executable, "executable"),
                (helpers.tmux_socket_directory, "directory"),
                (helpers.tmux_config, "regular"),
            ):
                duplicated.append(_duplicate_role_fd(descriptor, role))
        except BaseException:
            for descriptor in duplicated:
                _close_fd(descriptor)
            raise
        self._helpers = NativeHelperHandles(*duplicated)
        self._authenticated = authenticated
        self._stop_timeout = float(stop_timeout_seconds)
        self._bindings: dict[int, _NativeProcessResources] = {}
        self._attachments: dict[int, _NativeAttachment] = {}
        self._qualified_executables: dict[WAWExecutableKind, int] = {}
        self._execution_authority: WAWVerifiedExecutionAuthority | None = None
        self.production_qualified = False
        self._closed = False

    @classmethod
    def from_verified_execution_authority(
        cls,
        authority: WAWVerifiedExecutionAuthority,
        executable_handles: tuple[WAWExecutableLaunchHandle, ...],
        *,
        tmux_socket_directory: int,
        tmux_config: int,
        authenticated: Callable[[FixedProcessIdentity], bool],
        stop_timeout_seconds: float = 1.0,
    ) -> NativeHelperProcessPort:
        """Consume exact-six one-shot handles bound to one issued v2 authority."""

        if platform.system() != "Linux":
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE", "Native WAW helpers require Linux", category="unavailable"
            )
        if type(authority) is not WAWVerifiedExecutionAuthority:
            raise TypeError("verified execution authority is required")
        manifest = authority._manifest
        expected_kinds = tuple(WAWExecutableKind)
        if type(executable_handles) is not tuple or len(executable_handles) != len(expected_kinds):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Exact-six executable launch handles are required",
                category="unavailable",
            )
        inventory = manifest.executable_inventory.executables
        if len(inventory) != len(expected_kinds):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE", "Executable inventory is incomplete", category="unavailable"
            )
        for handle, kind, entry in zip(executable_handles, expected_kinds, inventory, strict=True):
            if (
                type(handle) is not WAWExecutableLaunchHandle
                or handle.identity.kind is not kind
                or entry.kind != kind.value
                or handle.identity.sha256 != entry.sha256
                or handle.inventory_digest != authority.executable_inventory_digest
                or handle.version_identity != entry.version_identity
                or handle.version_probe_id != entry.version_probe_id
                or handle.profile_digest != authority.interactive_profile_bundle_digest
            ):
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Executable launch handle is not bound to the v2 authority",
                    category="unavailable",
                )
        _verify_fd_digest(tmux_config, authority.tmux_config_digest)
        consumed: dict[WAWExecutableKind, int] = {}
        qualified: dict[WAWExecutableKind, int] = {}
        result: NativeHelperProcessPort | None = None
        try:
            for handle, kind in zip(executable_handles, expected_kinds, strict=True):
                consumed[kind] = handle.take(kind)
            result = cls(
                NativeHelperHandles(
                    consumed[WAWExecutableKind.PANE_BOOTSTRAP],
                    consumed[WAWExecutableKind.ATTACH_SUPERVISOR],
                    consumed[WAWExecutableKind.TMUX],
                    tmux_socket_directory,
                    tmux_config,
                ),
                authenticated=authenticated,
                stop_timeout_seconds=stop_timeout_seconds,
            )
            for kind in (
                WAWExecutableKind.BRIDGE,
                WAWExecutableKind.CLAUDE,
                WAWExecutableKind.CODEX,
            ):
                qualified[kind] = _duplicate_role_fd(consumed[kind], "executable")
            result._qualified_executables = qualified
        except BaseException:
            for descriptor in consumed.values():
                _close_fd(descriptor)
            for descriptor in qualified.values():
                _close_fd(descriptor)
            if result is not None:
                result._qualified_executables = {}
                result.close()
            raise
        for descriptor in consumed.values():
            _close_fd(descriptor)
        result._execution_authority = authority
        result.production_qualified = True
        return result

    @property
    def execution_authority(self) -> WAWVerifiedExecutionAuthority | None:
        return self._execution_authority

    def authorizes(self, identity: FixedProcessIdentity) -> bool:
        authority = self._execution_authority
        return authority is not None and authority.authorizes(identity)

    @staticmethod
    def create_wbr_endpoint() -> NativeWBREndpoint:
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        return NativeWBREndpoint(left, right)

    def _start_tmux_session(
        self, identity: FixedProcessIdentity, cgroup: CgroupControlHandle
    ) -> tuple[int, int]:
        tmux_directory = f"{_NATIVE_RUN_ROOT}/tmux"
        _verify_fixed_directory_handle(self._helpers.tmux_socket_directory, tmux_directory)
        tmux_socket = f"{tmux_directory}/{identity.workspace_hash[:32]}.sock"
        try:
            os.lstat(tmux_socket)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeOperationError(
                "WAW_START_UNCONFIRMED",
                "Fixed tmux socket collision cannot be inspected",
                category="conflict",
            ) from exc
        else:
            raise RuntimeOperationError(
                "WAW_START_UNCONFIRMED",
                "Fixed tmux socket already exists",
                category="conflict",
            )
        session = f"agentbox-waw-{identity.agent_type.value}-{identity.workspace_hash[:32]}"
        bootstrap = f"/proc/{os.getpid()}/fd/{self._helpers.pane_bootstrap}"
        config_fd = 7
        config = f"/proc/self/fd/{config_fd}"
        devnull = os.open("/dev/null", os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            arguments = (
                "tmux",
                "-S",
                tmux_socket,
                "-f",
                config,
                "new-session",
                "-d",
                "-s",
                session,
                bootstrap,
                "--workspace-hash",
                identity.workspace_hash,
                "--agent-type",
                identity.agent_type.value,
            )
            environment = {
                "HOME": "/nonexistent",
                "PATH": "/usr/bin",
                "LANG": "C.UTF-8",
                "LC_CTYPE": "C.UTF-8",
                "TERM": "xterm-256color",
            }
            descriptor_map = (
                (devnull, 0),
                (devnull, 1),
                (devnull, 2),
                (self._helpers.tmux_config, config_fd),
            )
            if type(cgroup) is LinuxCgroupControlHandle:
                cgroup_fd = cgroup.take_launcher_fd(identity)
                ready_parent, ready_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                pid: int | None = None
                pidfd: int | None = None
                try:
                    pid = _spawn_fixed(
                        self._helpers.pane_bootstrap,
                        (
                            "agentbox-waw-pane-bootstrap",
                            "--launch-tmux",
                            "--workspace-hash",
                            identity.workspace_hash,
                            "--agent-type",
                            identity.agent_type.value,
                            "--runtime-pid",
                            str(os.getpid()),
                            "--bootstrap-fd",
                            str(self._helpers.pane_bootstrap),
                        ),
                        {},
                        (
                            (devnull, 0),
                            (devnull, 1),
                            (devnull, 2),
                            (cgroup_fd, 3),
                            (self._helpers.tmux_executable, 4),
                            (self._helpers.tmux_config, 5),
                            (ready_child.fileno(), 6),
                        ),
                    )
                    pidfd = os.pidfd_open(pid, 0)
                    ready_child.close()
                    receive_native_ready(ready_parent)
                    return pid, pidfd
                except BaseException:
                    if pidfd is not None and pid is not None:
                        _terminate_spawned(pid, pidfd, 1.0, process_group=pid)
                    elif pid is not None:
                        _terminate_without_pidfd(pid)
                    raise
                finally:
                    _close_fd(cgroup_fd)
                    ready_parent.close()
                    ready_child.close()
            direct_pid = _spawn_fixed(
                self._helpers.tmux_executable,
                arguments,
                environment,
                descriptor_map,
            )
            try:
                return direct_pid, os.pidfd_open(direct_pid, 0)
            except BaseException:
                _terminate_without_pidfd(direct_pid)
                raise
        finally:
            _close_fd(devnull)

    def start(self, request: FixedLaunchRequest) -> FixedStartProof:
        self._require_open()
        if type(request) is not FixedLaunchRequest:
            raise TypeError("fixed launch request is required")
        if not self._authenticated(request.identity):
            return FixedStartProof(request, FixedStartState.LOGIN_REQUIRED, None, 0)
        role_fds, endpoint, cgroup = self._launch_roles(request)
        listener, launch_path, listener_identity = _bind_fixed_launch_listener(request.identity)
        tmux_pid: int | None = None
        tmux_pidfd: int | None = None
        control: socket.socket | None = None
        process_pid: int | None = None
        process_pidfd: int | None = None
        process_group: int | None = None
        tmux_socket_identity: tuple[int, int] | None = None
        try:
            tmux_pid, tmux_pidfd = self._start_tmux_session(request.identity, cgroup)
            control, tmux_exited = _accept_fixed_launch(listener, tmux_pidfd)
            tmux_exit = _wait_pidfd(tmux_pidfd, 0) if tmux_exited else None
            if tmux_exited:
                if tmux_exit != 0:
                    raise RuntimeOperationError(
                        "WAW_START_UNCONFIRMED",
                        "Fixed tmux session creation failed",
                        category="conflict",
                    )
                _close_fd(tmux_pidfd)
                tmux_pidfd = None
            process_pid, process_uid, process_gid = _peer_credentials(control)
            if process_uid != os.geteuid() or process_gid != os.getegid():
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Native pane peer credentials are invalid",
                    category="conflict",
                )
            process_pidfd = os.pidfd_open(process_pid, 0)
            process_group = os.getpgid(process_pid)
            if cgroup.contains_pidfd(process_pidfd) is not True:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Native pane is outside the authenticated cgroup",
                    category="conflict",
                )
            launch_descriptor = WAWLaunchDescriptor(
                agent=request.identity.agent_type.value,
                workspace_hash=request.identity.workspace_hash,
                generation=str(request.identity.generation),
                profile_digest=request.identity.profile_digest,
                initial_geometry=request.launch_geometry,
                runtime_uid=os.geteuid(),
                runtime_gid=os.getegid(),
                fd_role_bitmap=LAUNCH_FD_ROLE_BITMAP,
            )
            control.sendmsg(
                [encode_launch_descriptor(launch_descriptor)],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", role_fds))],
            )
            receive_native_ready(control)
            tmux_socket_identity = _verify_fixed_tmux_socket(request.identity)
            if tmux_exit is None:
                assert tmux_pidfd is not None
                tmux_exit = _wait_pidfd(tmux_pidfd, NATIVE_LAUNCH_ACCEPT_DEADLINE_SECONDS)
            if tmux_exit is None:
                assert tmux_pidfd is not None
                _terminate_spawned(tmux_pid, tmux_pidfd, self._stop_timeout, process_group=tmux_pid)
                tmux_pidfd = None
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Fixed tmux client did not exit after session creation",
                    category="conflict",
                )
            if tmux_pidfd is not None:
                _close_fd(tmux_pidfd)
                tmux_pidfd = None
            if tmux_exit != 0:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Fixed tmux session creation was not confirmed",
                    category="conflict",
                )
            populated = cgroup.populated()
            if type(populated) is not int or populated != 1:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Native cgroup did not prove the started process tree",
                    category="conflict",
                )
            listener.close()
            _unlink_fixed_launch_listener(launch_path, listener_identity)
        except BaseException:
            if process_pidfd is not None and process_pid is not None:
                _terminate_spawned(
                    process_pid,
                    process_pidfd,
                    self._stop_timeout,
                    process_group=process_group,
                )
                process_pidfd = None
            elif process_pid is not None:
                _terminate_without_pidfd(process_pid)
            if tmux_pidfd is not None:
                if _wait_pidfd(tmux_pidfd, 0) is None and tmux_pid is not None:
                    _terminate_spawned(tmux_pid, tmux_pidfd, self._stop_timeout)
                else:
                    _close_fd(tmux_pidfd)
                tmux_pidfd = None
            _force_cgroup_empty(cgroup, self._stop_timeout)
            if type(cgroup) is LinuxCgroupControlHandle:
                cgroup.close()
            if control is not None:
                control.close()
            endpoint.native.close()
            endpoint.controller.close()
            raise
        finally:
            listener.close()
            _unlink_fixed_launch_listener(launch_path, listener_identity)
        assert control is not None
        assert process_pid is not None and process_pidfd is not None
        assert process_group is not None
        assert tmux_socket_identity is not None
        control.close()
        resources = _NativeProcessResources(
            process_pid,
            process_group,
            process_pidfd,
            -1,
            -1,
            -1,
            control,
            endpoint.controller,
            cgroup,
            tmux_socket_identity,
        )
        binding = FixedProcessBinding(
            request.identity,
            resources,
            _NativeProcessGroup(process_group),
            cgroup,
        )
        self._bindings[id(binding)] = resources
        # The child endpoint is now held by the bridge after SCM_RIGHTS.
        endpoint.native.close()
        return FixedStartProof(request, FixedStartState.RUNNING, binding, 1)

    def open_attachment(self, request: FixedAttachmentRequest) -> FixedAttachmentPort:
        self._require_open()
        resources = self._resources(request.binding)
        existing = self._attachments.get(id(request.binding))
        if existing is not None and existing._closed:
            self._attachments.pop(id(request.binding), None)
            existing = None
        if existing is not None:
            raise RuntimeOperationError(
                "WORKSPACE_WRITER_BUSY", "Native attachment already exists", category="conflict"
            )
        master, slave = pty.openpty()
        ready_parent, ready_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            pid = _spawn_fixed(
                self._helpers.attach_supervisor,
                (
                    "agentbox-waw-attach-supervisor",
                    "--workspace-hash",
                    request.binding.identity.workspace_hash,
                    "--agent-type",
                    request.binding.identity.agent_type.value,
                ),
                {},
                (
                    (slave, 0),
                    (slave, 1),
                    (slave, 2),
                    (self._helpers.tmux_executable, 3),
                    (self._helpers.tmux_socket_directory, 4),
                    (self._helpers.tmux_config, 5),
                    (ready_child.fileno(), 6),
                ),
            )
            pidfd = os.pidfd_open(pid, 0)
            ready_child.close()
            receive_native_ready(ready_parent)
        except BaseException:
            if "pidfd" in locals():
                _terminate_spawned(pid, pidfd, self._stop_timeout)
            elif "pid" in locals():
                _terminate_without_pidfd(pid)
            _close_fd(master)
            _close_fd(slave)
            ready_parent.close()
            ready_child.close()
            raise
        _close_fd(slave)
        ready_parent.close()
        attachment = _NativeAttachment(
            pid=pid,
            pidfd=pidfd,
            master=master,
            lease=request.lease,
            process=resources,
            stop_timeout=self._stop_timeout,
        )
        self._attachments[id(request.binding)] = attachment
        return attachment

    def probe(self, binding: FixedProcessBinding) -> RuntimeProbeEvidence:
        resources = self._resources(binding)
        exit_code = _poll_pidfd(resources)
        state = RuntimeProbeState.RUNNING if exit_code is None else RuntimeProbeState.EXITED
        return RuntimeProbeEvidence(
            binding.identity.workspace_id,
            binding.identity.generation,
            binding.identity.managed_marker,
            state,
            exit_code,
        )

    def stop(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        resources = self._resources(binding)
        attachment = self._attachments.get(id(binding))
        if attachment is not None:
            cleanup = attachment.close()
            if not cleanup.closed or cleanup.remaining_members != 0:
                return self._stop_evidence(binding, False, 1)
            self._attachments.pop(id(binding), None)
        _force_cgroup_empty(resources.cgroup, self._stop_timeout)
        exit_code = _poll_pidfd(resources)
        if exit_code is None:
            _signal_pidfd(resources.pidfd, signal.SIGKILL)
            with _suppress_process_lookup():
                os.killpg(resources.process_group, signal.SIGKILL)
            exit_code = _wait_resources(resources, self._stop_timeout)
        group_empty = not _process_group_exists(resources.process_group)
        populated = resources.cgroup.populated()
        if type(populated) is not int or populated not in {0, 1}:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Native cgroup populated evidence is invalid",
                category="conflict",
            )
        frozen = resources.cgroup.frozen()
        if type(frozen) is not int or frozen != 0:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Native cgroup thaw read-back is invalid",
                category="conflict",
            )
        confirmed = exit_code is not None and group_empty and populated == 0
        tmux_gone = _wait_fixed_tmux_socket_gone(
            binding.identity, resources.tmux_socket_identity, self._stop_timeout
        )
        confirmed = confirmed and tmux_gone
        if confirmed:
            self._close_resources(resources)
            self._bindings.pop(id(binding), None)
        return self._stop_evidence(binding, confirmed, 0 if confirmed else max(1, populated))

    def destroy_fenced(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        # Only a binding already authenticated by this port can enter Stop.
        return self.stop(binding)

    def close(self) -> None:
        if self._closed:
            return
        if self._bindings:
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED",
                "Native process bindings remain live",
                category="conflict",
            )
        self._closed = True
        for descriptor in (
            *self._helpers.__dict__.values(),
            *self._qualified_executables.values(),
        ):
            _close_fd(descriptor)

    def _launch_roles(
        self, request: FixedLaunchRequest
    ) -> tuple[tuple[int, ...], NativeWBREndpoint, CgroupControlHandle]:
        handles = request.handles
        endpoint = handles.wbr_endpoint
        cgroup = handles.cgroup
        if type(endpoint) is not NativeWBREndpoint or not isinstance(cgroup, CgroupControlHandle):
            raise RuntimeOperationError(
                "WAW_START_UNCONFIRMED",
                "Native WBR/cgroup handles are not qualified",
                category="conflict",
            )
        bridge = handles.bridge_executable
        vendor = handles.vendor_executable
        if self.production_qualified:
            authority = self._execution_authority
            if (
                type(authority) is not WAWVerifiedExecutionAuthority
                or not self.authorizes(request.identity)
                or handles.production_authority is not authority
                or type(cgroup) is not LinuxCgroupControlHandle
                or not cgroup.production_qualified_for(authority, request.identity)
            ):
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Process launch handles are not bound to the execution authority",
                    category="unavailable",
                )
            bridge = self._qualified_executables[WAWExecutableKind.BRIDGE]
            vendor = self._qualified_executables[
                (
                    WAWExecutableKind.CLAUDE
                    if request.identity.agent_type is AgentType.CLAUDE
                    else WAWExecutableKind.CODEX
                )
            ]
        roles = (
            _role_fd(handles.project_directory, "path_directory"),
            _role_fd(handles.selected_home_directory, "directory"),
            _role_fd(handles.temp_directory, "directory"),
            _role_fd(bridge, "executable"),
            _role_fd(vendor, "executable"),
            _role_fd(handles.policy_directory, "directory"),
            _role_fd(endpoint.native.fileno(), "seqpacket"),
        )
        return roles, endpoint, cgroup

    def _resources(self, binding: FixedProcessBinding) -> _NativeProcessResources:
        if type(binding) is not FixedProcessBinding:
            raise TypeError("fixed process binding is required")
        resources = self._bindings.get(id(binding))
        if resources is None or binding.pidfd_handle is not resources:
            raise RuntimeOperationError(
                "WAW_PROCESS_IDENTITY_UNCONFIRMED",
                "Native process binding is not authenticated",
                category="conflict",
            )
        return resources

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE", "Native process port is closed", category="unavailable"
            )

    @staticmethod
    def _stop_evidence(
        binding: FixedProcessBinding, closed: bool, members: int
    ) -> RuntimeStopEvidence:
        return RuntimeStopEvidence(
            binding.identity.workspace_id,
            binding.identity.generation,
            binding.identity.managed_marker,
            closed,
            members,
        )

    @staticmethod
    def _close_resources(resources: _NativeProcessResources) -> None:
        for descriptor in (
            resources.stdin,
            resources.stdout,
            resources.stderr,
            resources.pidfd,
        ):
            _close_fd(descriptor)
        resources.control.close()
        resources.wbr.close()
        if type(resources.cgroup) is LinuxCgroupControlHandle:
            resources.cgroup.close()


def _duplicate_role_fd(descriptor: int, role: str) -> int:
    validated = _role_fd(descriptor, role)
    return fcntl.fcntl(validated, fcntl.F_DUPFD_CLOEXEC, 64)


def receive_native_ready(
    connection: socket.socket,
    *,
    timeout_seconds: float = NATIVE_READY_DEADLINE_SECONDS,
) -> None:
    """Accept one exact native READY packet with no ancillary data or tail."""

    if not _is_unix_seqpacket(connection):
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "Native READY endpoint is invalid", category="conflict"
        )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or not 0 < float(timeout_seconds) <= NATIVE_READY_DEADLINE_SECONDS
    ):
        raise ValueError("native READY deadline is invalid")
    readable, _, _ = select.select([connection], [], [], float(timeout_seconds))
    if not readable:
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "Native READY deadline expired", category="conflict"
        )
    payload, ancillary, flags, _address = connection.recvmsg(9, socket.CMSG_SPACE(1))
    if payload != NATIVE_READY or ancillary or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "Native READY proof is invalid", category="conflict"
        )


def _bind_fixed_launch_listener(
    identity: FixedProcessIdentity,
) -> tuple[socket.socket, str, tuple[int, int]]:
    directory = f"{_NATIVE_RUN_ROOT}/tmp/{identity.workspace_hash}"
    path = f"{directory}/launch.v1.sock"
    opened_identity: tuple[int, int] | None = None
    try:
        directory_stat = os.lstat(directory)
        if (
            not stat.S_ISDIR(directory_stat.st_mode)
            or directory_stat.st_uid != os.geteuid()
            or directory_stat.st_mode & 0o022
        ):
            raise OSError(errno.EPERM, "unsafe launch directory")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        listener.bind(path)
        os.chmod(path, 0o600)
        listener.listen(1)
        opened = os.lstat(path)
        opened_identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISSOCK(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
        ):
            raise OSError(errno.EPERM, "unsafe launch listener")
        return listener, path, (opened.st_dev, opened.st_ino)
    except OSError as exc:
        if "listener" in locals():
            listener.close()
        if opened_identity is not None:
            with contextlib.suppress(RuntimeOperationError):
                _unlink_fixed_launch_listener(path, opened_identity)
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED",
            "Fixed launch listener could not be created",
            category="conflict",
        ) from exc


def _unlink_fixed_launch_listener(path: str, identity: tuple[int, int]) -> None:
    try:
        current = os.lstat(path)
        if (
            not stat.S_ISSOCK(current.st_mode)
            or (current.st_dev, current.st_ino) != identity
            or current.st_uid != os.geteuid()
        ):
            raise OSError(errno.EPERM, "launch listener identity changed")
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeOperationError(
            "RECONCILIATION_REQUIRED",
            "Fixed launch listener cleanup is unconfirmed",
            category="conflict",
        ) from exc


def _accept_fixed_launch(listener: socket.socket, tmux_pidfd: int) -> tuple[socket.socket, bool]:
    deadline = time.monotonic() + NATIVE_LAUNCH_ACCEPT_DEADLINE_SECONDS
    tmux_exited = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeOperationError(
                "WAW_START_UNCONFIRMED",
                "Fixed tmux pane did not connect to the launch listener",
                category="conflict",
            )
        watched: list[object] = [listener]
        if not tmux_exited:
            watched.append(tmux_pidfd)
        readable, _, _ = select.select(watched, [], [], remaining)
        if not tmux_exited and tmux_pidfd in readable:
            tmux_exit = _peek_pidfd(tmux_pidfd)
            if tmux_exit is None:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Fixed tmux pidfd readiness was inconsistent",
                    category="conflict",
                )
            if tmux_exit != 0:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Fixed tmux session creation failed",
                    category="conflict",
                )
            tmux_exited = True
        if listener in readable:
            connection, _address = listener.accept()
            if not _is_unix_seqpacket(connection):
                connection.close()
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Native pane control type is invalid",
                    category="conflict",
                )
            return connection, tmux_exited


def _peer_credentials(connection: socket.socket) -> tuple[int, int, int]:
    option = getattr(socket, "SO_PEERCRED", None)
    if type(option) is not int:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "SO_PEERCRED is unavailable", category="unavailable"
        )
    try:
        raw = connection.getsockopt(socket.SOL_SOCKET, option, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", raw)
    except (OSError, struct.error) as exc:
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "Native pane peer is unverified", category="conflict"
        ) from exc
    if pid <= 1 or uid < 0 or gid < 0:
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "Native pane peer is invalid", category="conflict"
        )
    return pid, uid, gid


def _verify_fixed_directory_handle(descriptor: int, path: str) -> None:
    _role_fd(descriptor, "directory")
    try:
        held = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Fixed directory handle is unavailable", category="unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
        or current.st_mode & 0o022
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Fixed directory handle identity changed", category="unavailable"
        )


def _verify_fixed_tmux_socket(identity: FixedProcessIdentity) -> tuple[int, int]:
    path = f"{_NATIVE_RUN_ROOT}/tmux/{identity.workspace_hash[:32]}.sock"
    try:
        details = os.lstat(path)
    except OSError as exc:
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "Fixed tmux socket is unavailable", category="conflict"
        ) from exc
    if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.geteuid():
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "Fixed tmux socket identity is invalid", category="conflict"
        )
    return details.st_dev, details.st_ino


def _verify_delegate_root(
    descriptor: int, authority: WAWVerifiedExecutionAuthority
) -> tuple[str, str]:
    details = os.fstat(descriptor)
    manifest = authority._manifest.cgroup
    try:
        path = os.readlink(f"/proc/self/fd/{descriptor}")
    except OSError as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Delegated cgroup path is unavailable", category="unavailable"
        ) from exc
    device = f"{os.major(details.st_dev)}:{os.minor(details.st_dev)}"
    expected_path = f"/sys/fs/cgroup/{manifest.delegate_subgroup}"
    mount_id = _fd_mount_id(descriptor)
    if (
        path != expected_path
        or path.endswith(" (deleted)")
        or device != manifest.cgroup_mount_device
        or not _mountinfo_matches_cgroup(mount_id, manifest)
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Delegated cgroup root does not match the manifest",
            category="unavailable",
        )
    return mount_id, manifest.cgroup_mount_filesystem_id


def _validate_delegated_workload(
    descriptor: int,
    authority: WAWVerifiedExecutionAuthority,
    mount_identity: tuple[str, str],
) -> None:
    details = os.fstat(descriptor)
    cgroup_manifest = authority._manifest.cgroup
    actual_device = f"{os.major(details.st_dev)}:{os.minor(details.st_dev)}"
    if (
        actual_device != cgroup_manifest.cgroup_mount_device
        or _fd_mount_id(descriptor) != mount_identity[0]
        or mount_identity[1] != cgroup_manifest.cgroup_mount_filesystem_id
        or details.st_uid != os.geteuid()
        or details.st_mode & 0o022
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Delegated cgroup descriptor provenance is invalid",
            category="unavailable",
        )
    controllers = set(_read_cgroup_file(descriptor, "cgroup.controllers").split())
    cpu_quota = cgroup_manifest.cpu_quota_percent * cgroup_manifest.cpu_quota_period_usec // 100
    fixed_values = {
        "cgroup.type": "domain",
        "pids.max": str(cgroup_manifest.tasks_max),
        "memory.max": str(cgroup_manifest.memory_max),
        "memory.swap.max": str(cgroup_manifest.memory_swap_max),
        "cpu.max": f"{cpu_quota} {cgroup_manifest.cpu_quota_period_usec}",
    }
    if not set(cgroup_manifest.controllers).issubset(controllers) or any(
        _read_cgroup_file(descriptor, name).strip() != expected
        for name, expected in fixed_values.items()
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Delegated cgroup controllers or limits are invalid",
            category="unavailable",
        )
    if _cgroup_event(descriptor, "populated") != 0 or _cgroup_event(descriptor, "frozen") != 0:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Delegated workload cgroup is already live",
            category="unavailable",
        )


def _verify_project_root_descriptor(descriptor: int, manifest: ProjectRootManifest) -> None:
    _verify_installed_directory(
        descriptor,
        manifest.configured_root,
        expected_uid=int(manifest.root_uid),
        expected_mode=int(manifest.root_mode, 8),
    )
    details = os.fstat(descriptor)
    if (
        str(details.st_dev) != manifest.root_device
        or str(details.st_gid) != manifest.root_gid
        or format(stat.S_IMODE(details.st_mode), "o") != manifest.root_mode
        or _fd_mount_id(descriptor) != manifest.root_mount_id
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "ProjectRoot descriptor does not match its manifest",
            category="unavailable",
        )


def _verify_installed_directory(
    descriptor: int, path: str, *, expected_uid: int, expected_mode: int
) -> None:
    _role_fd(descriptor, "directory")
    try:
        held = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Installed directory is unavailable", category="unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
        or held.st_uid != expected_uid
        or stat.S_IMODE(held.st_mode) != expected_mode
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Installed directory identity is invalid", category="unavailable"
        )


def _verify_installed_file(descriptor: int, path: str, digest: str) -> None:
    _role_fd(descriptor, "regular")
    try:
        held = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Installed policy file is unavailable", category="unavailable"
        ) from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
        or held.st_uid != 0
        or held.st_mode & 0o022
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Installed policy file identity is invalid",
            category="unavailable",
        )
    _verify_fd_digest(descriptor, digest)


def _open_relative_directory(
    parent: int,
    name: str,
    *,
    path_only: bool,
    expected_uid: int,
    expected_mode: int | None = None,
) -> int:
    if (
        type(name) is not str
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Installed directory key is invalid", category="unavailable"
        )
    flags = os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    flags |= os.O_PATH if path_only else os.O_RDONLY
    descriptor = os.open(name, flags, dir_fd=parent)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != expected_uid
            or details.st_mode & 0o022
            or (expected_mode is not None and stat.S_IMODE(details.st_mode) != expected_mode)
        ):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Installed directory entry is invalid",
                category="unavailable",
            )
        return descriptor
    except BaseException:
        _close_fd(descriptor)
        raise


def _directory_identity(descriptor: int) -> tuple[int, int, int, int, int]:
    details = os.fstat(descriptor)
    return (
        details.st_dev,
        details.st_ino,
        details.st_uid,
        details.st_gid,
        details.st_mode,
    )


def _fd_mount_id(descriptor: int) -> str:
    try:
        raw = Path(f"/proc/self/fdinfo/{descriptor}").read_text(encoding="ascii", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Descriptor mount identity is unavailable",
            category="unavailable",
        ) from exc
    matches = [line[7:] for line in raw.splitlines() if line.startswith("mnt_id:\t")]
    if len(matches) != 1 or not matches[0].isdecimal():
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Descriptor mount identity is invalid", category="unavailable"
        )
    return matches[0]


def _mountinfo_matches_cgroup(mount_id: str, manifest: CgroupDelegationManifest) -> bool:
    try:
        raw = Path("/proc/self/mountinfo").read_text(encoding="ascii", errors="strict")
    except (OSError, UnicodeError):
        return False
    matches = []
    for line in raw.splitlines():
        before, separator, after = line.partition(" - ")
        fields = before.split()
        filesystem = after.split()
        if separator and len(fields) >= 6 and len(filesystem) >= 3 and fields[0] == mount_id:
            matches.append((fields, filesystem))
    return len(matches) == 1 and (
        matches[0][0][2] == manifest.cgroup_mount_device
        and matches[0][0][3] == "/"
        and matches[0][0][4] == "/sys/fs/cgroup"
        and matches[0][1][0] == manifest.cgroup_mount_type
    )


def _wait_fixed_tmux_socket_gone(
    identity: FixedProcessIdentity,
    expected: tuple[int, int],
    timeout: float,
) -> bool:
    path = f"{_NATIVE_RUN_ROOT}/tmux/{identity.workspace_hash[:32]}.sock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            details = os.lstat(path)
        except FileNotFoundError:
            return True
        except OSError as exc:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Fixed tmux socket cleanup is unobservable",
                category="conflict",
            ) from exc
        if (details.st_dev, details.st_ino) != expected or not stat.S_ISSOCK(details.st_mode):
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Fixed tmux socket identity changed during Stop",
                category="conflict",
            )
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


def _role_fd(value: object, role: str) -> int:
    if type(value) is not int or value < 0:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Native held descriptor is invalid", category="unavailable"
        )
    try:
        details = os.fstat(value)
        flags = fcntl.fcntl(value, fcntl.F_GETFL)
        if role in {"directory", "path_directory"} and not stat.S_ISDIR(details.st_mode):
            raise ValueError
        if role == "path_directory" and (
            not hasattr(os, "O_PATH") or flags & os.O_PATH != os.O_PATH
        ):
            raise ValueError
        if role == "directory" and flags & os.O_ACCMODE != os.O_RDONLY:
            raise ValueError
        if role in {"regular", "executable"} and not stat.S_ISREG(details.st_mode):
            raise ValueError
        if role == "executable" and (details.st_mode & 0o111 == 0 or details.st_mode & 0o022 != 0):
            raise ValueError
        if role == "seqpacket":
            duplicate = socket.socket(fileno=os.dup(value))
            try:
                if not _is_unix_seqpacket(duplicate):
                    raise ValueError
            finally:
                duplicate.close()
    except (OSError, ValueError) as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Native held descriptor role is invalid", category="unavailable"
        ) from exc
    return value


def _read_cgroup_file(directory_fd: int, name: str) -> str:
    if name not in {
        "cgroup.controllers",
        "cgroup.events",
        "cgroup.procs",
        "cgroup.type",
        "pids.max",
        "memory.max",
        "memory.swap.max",
        "cpu.max",
    }:
        raise ValueError("unsupported cgroup read")
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        dir_fd=directory_fd,
    )
    try:
        raw = os.read(descriptor, 4097)
        if len(raw) > 4096:
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED", "Cgroup read-back is oversized", category="conflict"
            )
        return raw.decode("ascii", errors="strict")
    finally:
        _close_fd(descriptor)


def _write_cgroup_file(directory_fd: int, name: str, payload: bytes) -> None:
    if name not in {"cgroup.freeze", "cgroup.kill", "cgroup.procs"}:
        raise ValueError("unsupported cgroup write")
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        dir_fd=directory_fd,
    )
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError(errno.EIO, "short cgroup write")
    finally:
        _close_fd(descriptor)


def _cgroup_event(directory_fd: int, field: str) -> int:
    values: dict[str, str] = {}
    for line in _read_cgroup_file(directory_fd, "cgroup.events").splitlines():
        parts = line.split(" ")
        if len(parts) != 2 or parts[0] in values:
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED", "Cgroup events are invalid", category="conflict"
            )
        values[parts[0]] = parts[1]
    value = values.get(field)
    if value not in {"0", "1"}:
        raise RuntimeOperationError(
            "RECONCILIATION_REQUIRED", "Cgroup event is unavailable", category="conflict"
        )
    return int(value)


def _pid_from_pidfd(pidfd: int) -> int | None:
    if type(pidfd) is not int or pidfd < 0:
        return None
    try:
        descriptor = os.open(
            f"/proc/self/fdinfo/{pidfd}",
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            raw = os.read(descriptor, 4097)
        finally:
            _close_fd(descriptor)
        if len(raw) > 4096:
            return None
        matches = [
            line[5:] for line in raw.decode("ascii").splitlines() if line.startswith("Pid:\t")
        ]
        if len(matches) != 1 or not matches[0].isascii() or not matches[0].isdecimal():
            return None
        value = int(matches[0])
        return value if value > 1 else None
    except (OSError, UnicodeError, ValueError):
        return None


def _is_unix_seqpacket(connection: object) -> bool:
    domain_option = getattr(socket, "SO_DOMAIN", None)
    if type(domain_option) is not int:
        return False
    try:
        getsockopt = getattr(connection, "getsockopt", None)
        if not callable(getsockopt):
            return False
        return bool(
            getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_SEQPACKET
            and getsockopt(socket.SOL_SOCKET, domain_option) == socket.AF_UNIX
        )
    except (AttributeError, OSError, TypeError):
        return False


def _verify_fd_digest(descriptor: int, expected: str, *, max_bytes: int = 64 * 1024) -> None:
    _role_fd(descriptor, "regular")
    before = os.fstat(descriptor)
    if (
        before.st_uid != 0
        or before.st_mode & 0o022
        or before.st_nlink != 1
        or before.st_size > max_bytes
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Policy descriptor provenance is invalid",
            category="unavailable",
        )
    digest = hashlib.sha256()
    offset = 0
    while True:
        block = os.pread(descriptor, min(8192, max_bytes - offset + 1), offset)
        if not block:
            break
        offset += len(block)
        if offset > max_bytes:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE", "Policy descriptor is oversized", category="unavailable"
            )
        digest.update(block)
    if not hmac.compare_digest(digest.hexdigest(), expected):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Policy descriptor does not match execution authority",
            category="unavailable",
        )
    after = os.fstat(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_uid,
        before.st_gid,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_uid,
        after.st_gid,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
    ):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Policy descriptor changed during handoff",
            category="unavailable",
        )


def _spawn_fixed(
    executable: int,
    argv: tuple[str, ...],
    environment: dict[str, str],
    descriptor_map: tuple[tuple[int, int], ...],
) -> int:
    actions: list[tuple[int, int, int]] = []
    for source, destination in descriptor_map:
        actions.append((os.POSIX_SPAWN_DUP2, source, destination))
    try:
        return os.posix_spawn(
            f"/proc/self/fd/{executable}",
            argv,
            environment,
            file_actions=actions,
            setsid=True,
        )
    except (AttributeError, OSError, TypeError) as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Fixed native helper spawn failed", category="unavailable"
        ) from exc


def _poll_pidfd(resources: _NativeProcessResources) -> int | None:
    if resources.reaped:
        return resources.exit_code
    return _wait_resources(resources, 0.0)


def _wait_resources(resources: _NativeProcessResources, timeout: float) -> int | None:
    if resources.reaped:
        return resources.exit_code
    result = _wait_pidfd(resources.pidfd, timeout)
    if result is not None:
        resources.exit_code = result
        resources.reaped = True
    return result


def _wait_pidfd(pidfd: int, timeout: float) -> int | None:
    poller = select.poll()
    poller.register(pidfd, select.POLLIN)
    if not poller.poll(max(0, math.ceil(timeout * 1000))):
        return None
    result = os.waitid(os.P_PIDFD, pidfd, os.WEXITED)
    if result is None:
        return None
    return result.si_status if result.si_code == os.CLD_EXITED else -result.si_status


def _peek_pidfd(pidfd: int) -> int | None:
    result = os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if result is None:
        return None
    return result.si_status if result.si_code == os.CLD_EXITED else -result.si_status


def _signal_pidfd(pidfd: int, signal_number: int) -> None:
    sender = getattr(signal, "pidfd_send_signal", None)
    if not callable(sender):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "pidfd_send_signal is unavailable", category="unavailable"
        )
    with contextlib.suppress(ProcessLookupError):
        sender(pidfd, signal_number)


def _terminate_spawned(
    pid: int,
    pidfd: int,
    timeout: float,
    *,
    process_group: int | None = None,
) -> None:
    _signal_pidfd(pidfd, signal.SIGKILL)
    with _suppress_process_lookup():
        os.killpg(pid if process_group is None else process_group, signal.SIGKILL)
    _wait_pidfd(pidfd, timeout)
    _close_fd(pidfd)


def _terminate_without_pidfd(pid: int) -> None:
    """Reap only the exact child returned by this failed spawn."""

    with _suppress_process_lookup():
        os.killpg(pid, signal.SIGKILL)
    with contextlib.suppress(ChildProcessError, ProcessLookupError):
        os.waitpid(pid, 0)


def _force_cgroup_empty(cgroup: CgroupControlHandle, timeout: float) -> None:
    try:
        cgroup.freeze()
        if cgroup.frozen() != 1:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Native cgroup freeze read-back is invalid",
                category="conflict",
            )
        cgroup.kill()
        if cgroup.wait_empty(timeout) is not True:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Native cgroup kill did not reach populated=0",
                category="conflict",
            )
        if cgroup.populated() != 0:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Native cgroup populated read-back is invalid",
                category="conflict",
            )
        cgroup.thaw()
        if cgroup.frozen() != 0:
            raise RuntimeOperationError(
                "WAW_STOP_UNCONFIRMED",
                "Native cgroup thaw read-back is invalid",
                category="conflict",
            )
    except RuntimeOperationError:
        raise
    except Exception as exc:
        raise RuntimeOperationError(
            "WAW_STOP_UNCONFIRMED",
            "Native cgroup fixed cleanup failed",
            category="conflict",
        ) from exc


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class _suppress_process_lookup:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exception: type[BaseException] | None, *_args: object) -> bool:
        return exception is not None and issubclass(exception, ProcessLookupError)


def _close_fd(descriptor: int) -> None:
    with contextlib.suppress(OSError):
        os.close(descriptor)


def _close_fd_tuple(descriptors: tuple[int, ...]) -> None:
    for descriptor in descriptors:
        _close_fd(descriptor)


def _cleanup_unconsumed_launch_handles(handles: FixedLaunchHandles) -> None:
    _close_fd_tuple(
        (
            cast(int, handles.project_directory),
            cast(int, handles.selected_home_directory),
            cast(int, handles.temp_directory),
            cast(int, handles.policy_directory),
        )
    )
    endpoint = handles.wbr_endpoint
    if type(endpoint) is NativeWBREndpoint:
        endpoint.native.close()
        endpoint.controller.close()
    cgroup = handles.cgroup
    if type(cgroup) is LinuxCgroupControlHandle:
        cgroup.close()


class WAWFixedTransport:
    """One exact generation's fixed process and commit-time PTY attachment."""

    requires_commit_attachment = True

    def __init__(
        self,
        *,
        identity: FixedProcessIdentity,
        handles: FixedLaunchHandles | WAWProductionLaunchHandles,
        executable_fingerprint: str,
        port: NativeProcessPort,
        clock: Callable[[], float],
        production: bool,
    ) -> None:
        if type(identity) is not FixedProcessIdentity:
            raise ValueError("fixed transport construction records are invalid")
        if (
            type(executable_fingerprint) is not str
            or len(executable_fingerprint) != 64
            or any(char not in "0123456789abcdef" for char in executable_fingerprint)
        ):
            raise ValueError("executable fingerprint is invalid")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if production:
            qualified = require_linux_native_process_port(port)
            if type(qualified) is not NativeHelperProcessPort:
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Production transport requires the fixed native helper adapter",
                    category="unavailable",
                )
            authorizes = getattr(qualified, "authorizes", None)
            if not callable(authorizes) or authorizes(identity) is not True:
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Fixed process identity is not bound to the execution authority",
                    category="unavailable",
                )
            execution_authority = qualified.execution_authority
            if (
                execution_authority is None
                or executable_fingerprint
                != execution_authority.vendor_executable_fingerprint(identity.agent_type)
            ):
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Vendor fingerprint is not bound to the execution authority",
                    category="unavailable",
                )
            if (
                type(handles) is not WAWProductionLaunchHandles
                or handles._authority is not execution_authority
            ):
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Production launch handles were not issued by the execution authority",
                    category="unavailable",
                )
            fixed_handles = handles.take(identity)
        elif isinstance(port, LinuxNativeProcessPort):
            # A nominal production adapter must always use the production path,
            # keeping test-only construction explicit in evidence.
            raise ValueError("Linux native port requires production construction")
        elif type(handles) is FixedLaunchHandles and handles.production_authority is None:
            fixed_handles = handles
        else:
            raise ValueError("Development transport requires test-only launch handles")
        self._identity = identity
        self._production_project_identity = (
            handles._project_identity if type(handles) is WAWProductionLaunchHandles else None
        )
        self._handles = fixed_handles
        launch_descriptors = (
            fixed_handles.project_directory,
            fixed_handles.selected_home_directory,
            fixed_handles.temp_directory,
            fixed_handles.policy_directory,
        )
        self._owned_launch_descriptors = (
            cast(tuple[int, ...], launch_descriptors)
            if all(type(value) is int for value in launch_descriptors)
            else ()
        )
        self._executable_fingerprint = executable_fingerprint
        self._port = port
        self._clock = clock
        self._production = production
        self._inspector = WAWProcessInspector(identity, port)
        self._request: FixedLaunchRequest | None = None
        self._attachment: FixedAttachmentPort | None = None
        self._attachment_lease: RuntimeAttachmentLease | None = None
        self._wbr: WBRResizeStateMachine | None = None
        self._last_cleanup: (
            tuple[RuntimeAttachmentLease, RuntimeAttachmentCleanupEvidence] | None
        ) = None
        self._output_sink: OutputSink | None = None
        self._initial_auth_evidence: WAWPublicAuthEvidence | None = None
        self._start_attempted = False
        self._closed = False
        self._aborted_unstarted = False

    @classmethod
    def production(
        cls,
        *,
        identity: FixedProcessIdentity,
        handles: WAWProductionLaunchHandles,
        executable_fingerprint: str,
        port: LinuxNativeProcessPort,
        clock: Callable[[], float],
    ) -> WAWFixedTransport:
        return cls(
            identity=identity,
            handles=handles,
            executable_fingerprint=executable_fingerprint,
            port=cast(NativeProcessPort, port),
            clock=clock,
            production=True,
        )

    @classmethod
    def development_only(
        cls,
        *,
        identity: FixedProcessIdentity,
        handles: FixedLaunchHandles,
        executable_fingerprint: str,
        port: NativeProcessPort,
        clock: Callable[[], float],
    ) -> WAWFixedTransport:
        return cls(
            identity=identity,
            handles=handles,
            executable_fingerprint=executable_fingerprint,
            port=port,
            clock=clock,
            production=False,
        )

    @property
    def production_qualified(self) -> bool:
        return self._production

    @property
    def process_identity(self) -> FixedProcessIdentity:
        return self._identity

    @property
    def execution_authority(self) -> WAWVerifiedExecutionAuthority | None:
        authority = getattr(self._port, "execution_authority", None)
        return authority if type(authority) is WAWVerifiedExecutionAuthority else None

    @property
    def executable_fingerprint(self) -> str:
        return self._executable_fingerprint

    def set_initial_auth_evidence(self, evidence: WAWPublicAuthEvidence) -> None:
        if self._start_attempted or self._initial_auth_evidence is not None:
            raise RuntimeOperationError(
                "WAW_AUTH_EVIDENCE_STALE",
                "Initial auth evidence is already consumed",
                category="conflict",
            )
        self._validate_auth_evidence(evidence, require_authenticated=False)
        if evidence.result not in {
            WAWPublicAuthResult.AUTHENTICATED,
            WAWPublicAuthResult.UNAUTHENTICATED,
        }:
            raise RuntimeOperationError(
                "WAW_AUTH_EVIDENCE_STALE",
                "Definitive public auth evidence is required",
                category="conflict",
            )
        self._initial_auth_evidence = evidence

    def abort_unstarted(self) -> bool:
        """Close every launch-owned resource before the first process effect."""

        if self._start_attempted:
            return False
        if self._aborted_unstarted:
            return True
        try:
            self._close_owned_launch_descriptors()
            endpoint = self._handles.wbr_endpoint
            if type(endpoint) is NativeWBREndpoint:
                endpoint.native.close()
                endpoint.controller.close()
            cgroup = self._handles.cgroup
            if type(cgroup) is LinuxCgroupControlHandle:
                if cgroup.consumed:
                    return False
                cgroup.close()
        except Exception:
            return False
        self._aborted_unstarted = True
        self._closed = True
        return True

    def bind_output_sink(self, sink: OutputSink) -> None:
        if self._output_sink is not None or not callable(sink):
            raise RuntimeOperationError(
                "WAW_OUTPUT_INVALID", "Fixed output sink cannot be installed", category="conflict"
            )
        self._output_sink = sink

    def start(self, command: WAWManagedCommand, geometry: PtyGeometry) -> RuntimeStartEvidence:
        if self._start_attempted or self._closed:
            raise RuntimeOperationError(
                "WAW_START_INVALID", "Fixed process start is not reusable", category="conflict"
            )
        validated = validate_managed_command(command)
        self._check_command(validated)
        request = FixedLaunchRequest(self._identity, self._handles, geometry)
        self._request = request
        self._start_attempted = True
        initial_auth = self._initial_auth_evidence
        if initial_auth is not None and (
            initial_auth.result is WAWPublicAuthResult.UNAUTHENTICATED
        ):
            proof = self._inspector.accept_start(
                FixedStartProof(request, FixedStartState.LOGIN_REQUIRED, None, 0), request
            )
        else:
            try:
                proof = self._inspector.accept_start(self._port.start(request), request)
            finally:
                self._close_owned_launch_descriptors()
            if initial_auth is not None and proof.state is FixedStartState.LOGIN_REQUIRED:
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Authenticated native start did not spawn a process",
                    category="conflict",
                )
        return self._start_evidence(proof)

    def resume_after_login(self, evidence: WAWPublicAuthEvidence) -> RuntimeStartEvidence:
        request = self._request
        if request is None or not self._start_attempted or not self._inspector.login_required:
            raise RuntimeOperationError(
                "WAW_RESUME_INVALID", "Workspace is not waiting for login", category="conflict"
            )
        self.validate_resume_evidence(evidence)
        try:
            proof = self._inspector.accept_start(self._port.start(request), request)
        finally:
            self._close_owned_launch_descriptors()
        if proof.state is FixedStartState.LOGIN_REQUIRED or proof.binding is None:
            raise RuntimeOperationError(
                "WAW_RESUME_UNCONFIRMED",
                "Authenticated resume did not start the exact process",
                category="conflict",
            )
        return self._start_evidence(proof)

    def validate_resume_evidence(self, evidence: WAWPublicAuthEvidence) -> None:
        """Validate freshness before the supervisor changes its CAS state."""

        self._validate_auth_evidence(evidence)

    def open_attachment(
        self, lease: RuntimeAttachmentLease, geometry: PtyGeometry
    ) -> RuntimeStartEvidence:
        if self._closed or self._attachment is not None:
            raise RuntimeOperationError(
                "WORKSPACE_WRITER_BUSY", "Fixed PTY attachment is unavailable", category="conflict"
            )
        binding = self._inspector.binding
        if binding is None:
            raise RuntimeOperationError(
                "WORKSPACE_NOT_RUNNING", "Fixed process is not running", category="conflict"
            )
        request = FixedAttachmentRequest(binding, lease, geometry)
        attachment = self._port.open_attachment(request)
        if not isinstance(attachment, FixedAttachmentPort):
            raise RuntimeOperationError(
                "WAW_ATTACH_UNCONFIRMED", "Native attachment port is invalid", category="conflict"
            )
        wbr = WBRResizeStateMachine(generation=self._identity.generation)
        try:
            self._accept_resize(attachment, wbr, geometry)
        except BaseException as exc:
            cleanup = self._close_uncommitted(attachment, lease)
            self._last_cleanup = (lease, cleanup)
            raise RuntimeOperationError(
                "WAW_ATTACH_UNCONFIRMED",
                "Native attachment winsize was not acknowledged",
                category="conflict",
            ) from exc
        self._attachment = attachment
        self._attachment_lease = lease
        self._wbr = wbr
        return RuntimeStartEvidence(
            self._identity.workspace_id,
            self._identity.generation,
            self._identity.managed_marker,
            SupervisorState.RUNNING,
            True,
        )

    def write(self, data: bytes) -> None:
        attachment = self._require_attachment()
        attachment.write_input(validate_input(data))

    def resize(self, geometry: PtyGeometry) -> None:
        attachment = self._require_attachment()
        wbr = self._wbr
        if wbr is None:
            raise RuntimeOperationError(
                "WAW_RESIZE_FAILED", "WBR state is unavailable", category="conflict"
            )
        self._accept_resize(attachment, wbr, geometry)

    def produce_output(self) -> int:
        """Perform one nonblocking, at-most-32KiB producer read into the ring."""

        attachment = self._require_attachment()
        sink = self._output_sink
        if sink is None:
            raise RuntimeOperationError(
                "WAW_OUTPUT_INVALID", "Fixed output sink is unavailable", category="conflict"
            )
        payload = attachment.read_output(MAX_NATIVE_OUTPUT_BYTES)
        if payload is None or payload == b"":
            return 0
        if type(payload) is not bytes or len(payload) > MAX_NATIVE_OUTPUT_BYTES:
            raise RuntimeOperationError(
                "WAW_OUTPUT_INVALID",
                "Native output exceeded the fixed read bound",
                category="broken",
            )
        sink(payload)
        return len(payload)

    def close_attachment(self, lease: RuntimeAttachmentLease) -> RuntimeAttachmentCleanupEvidence:
        if self._last_cleanup is not None and self._last_cleanup[0] is lease:
            return self._last_cleanup[1]
        if self._attachment_lease is not lease:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_STALE", "Fixed PTY lease is stale", category="conflict"
            )
        attachment = self._require_attachment()
        evidence = attachment.close()
        self._validate_cleanup(evidence, lease)
        self._clear_attachment()
        self._last_cleanup = (lease, evidence)
        return evidence

    def detach(self) -> bool:
        raise RuntimeOperationError(
            "WAW_DETACH_UNCONFIRMED",
            "Fixed transport requires typed attachment cleanup evidence",
            category="conflict",
        )

    def probe(self) -> RuntimeProbeEvidence:
        return self._inspector.probe()

    def stop(self) -> RuntimeStopEvidence:
        had_process = self._inspector.binding is not None
        if self._attachment is not None:
            lease = self._attachment_lease
            if lease is None:
                raise RuntimeOperationError(
                    "WAW_STOP_UNCONFIRMED", "Fixed PTY lease is unavailable", category="conflict"
                )
            self.close_attachment(lease)
        evidence = (
            self._inspector.destroy_fenced() if self._inspector.fenced else self._inspector.stop()
        )
        if self._production and not had_process:
            self._close_owned_launch_descriptors()
            endpoint = self._handles.wbr_endpoint
            if type(endpoint) is NativeWBREndpoint:
                endpoint.native.close()
                endpoint.controller.close()
            cgroup = self._handles.cgroup
            if type(cgroup) is LinuxCgroupControlHandle:
                cgroup.close()
        self._closed = True
        return evidence

    def quarantine_restart(self, binding: object | None) -> None:
        """Enter restart quarantine; no prior process is adopted or probed."""

        from agentbox_runtime.waw_process_inspector import FixedProcessBinding

        if binding is not None and type(binding) is not FixedProcessBinding:
            raise TypeError("restart binding must be an authenticated FixedProcessBinding")
        self._inspector.quarantine_restart(binding)

    def destroy_fenced(self) -> RuntimeStopEvidence:
        evidence = self._inspector.destroy_fenced()
        self._closed = True
        return evidence

    def _check_command(self, command: WAWManagedCommand) -> None:
        if (
            command.workspace_id != self._identity.workspace_id
            or command.project_id != self._identity.project_id
            or managed_command_agent_type(command) is not self._identity.agent_type
            or command.managed_marker != self._identity.managed_marker
        ):
            raise RuntimeOperationError(
                "WAW_COMMAND_IDENTITY_MISMATCH",
                "Fixed launch request does not match the Runtime command binding",
                category="validation",
            )
        if self._production_project_identity is not None:
            details = command.cwd.stat()
            if (
                details.st_dev,
                details.st_ino,
                details.st_uid,
                details.st_gid,
                details.st_mode,
            ) != self._production_project_identity:
                raise RuntimeOperationError(
                    "WAW_PROJECT_CHANGED",
                    "Production Project descriptor does not match the command binding",
                    category="conflict",
                )

    def _validate_auth_evidence(
        self, evidence: WAWPublicAuthEvidence, *, require_authenticated: bool = True
    ) -> None:
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(float(now))
            or now < 0
            or type(evidence) is not WAWPublicAuthEvidence
            or evidence.agent_type is not self._identity.agent_type
            or evidence.runtime_host_installation_id != self._identity.runtime_host_installation_id
            or evidence.runtime_host_installation_revision
            != self._identity.runtime_host_installation_revision
            or evidence.executable_fingerprint != self._executable_fingerprint
            or (require_authenticated and evidence.result is not WAWPublicAuthResult.AUTHENTICATED)
            or float(now) < evidence.checked_at_monotonic
            or float(now) - evidence.checked_at_monotonic >= AUTH_EVIDENCE_MAX_AGE_SECONDS
        ):
            raise RuntimeOperationError(
                "WAW_AUTH_EVIDENCE_STALE",
                "Fresh authenticated evidence is required for resume",
                category="conflict",
            )

    def _accept_resize(
        self,
        attachment: FixedAttachmentPort,
        wbr: WBRResizeStateMachine,
        geometry: PtyGeometry,
    ) -> None:
        wbr.begin_resize(geometry.columns, geometry.rows)
        acknowledgment = attachment.resize(geometry)
        wbr.accept_ack(acknowledgment)

    @staticmethod
    def _validate_cleanup(
        evidence: RuntimeAttachmentCleanupEvidence, lease: RuntimeAttachmentLease
    ) -> None:
        if (
            type(evidence) is not RuntimeAttachmentCleanupEvidence
            or evidence.lease is not lease
            or evidence.closed is not True
            or type(evidence.remaining_members) is not int
            or evidence.remaining_members != 0
        ):
            raise RuntimeOperationError(
                "WAW_DETACH_UNCONFIRMED",
                "Native attach child/PTY cleanup was not proven",
                category="conflict",
            )

    def _close_uncommitted(
        self, attachment: FixedAttachmentPort, lease: RuntimeAttachmentLease
    ) -> RuntimeAttachmentCleanupEvidence:
        try:
            evidence = attachment.close()
            self._validate_cleanup(evidence, lease)
            return evidence
        except BaseException as exc:
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED",
                "Failed attachment could not be positively fenced",
                category="conflict",
            ) from exc

    def _require_attachment(self) -> FixedAttachmentPort:
        if self._attachment is None:
            raise RuntimeOperationError(
                "WAW_ATTACHMENT_REQUIRED", "No exact fixed PTY is attached", category="conflict"
            )
        return self._attachment

    def _clear_attachment(self) -> None:
        if self._wbr is not None:
            self._wbr.close()
        self._wbr = None
        self._attachment = None
        self._attachment_lease = None

    def _close_owned_launch_descriptors(self) -> None:
        for descriptor in self._owned_launch_descriptors:
            _close_fd(descriptor)
        self._owned_launch_descriptors = ()

    @staticmethod
    def _start_evidence(proof: FixedStartProof) -> RuntimeStartEvidence:
        return RuntimeStartEvidence(
            proof.request.identity.workspace_id,
            proof.request.identity.generation,
            proof.request.identity.managed_marker,
            SupervisorState(proof.state.value),
            True,
        )


__all__ = [
    "AUTH_EVIDENCE_MAX_AGE_SECONDS",
    "CgroupControlHandle",
    "LinuxCgroupControlHandle",
    "MAX_NATIVE_OUTPUT_BYTES",
    "NATIVE_READY",
    "NATIVE_READY_DEADLINE_SECONDS",
    "NativeHelperHandles",
    "NativeHelperProcessPort",
    "NativeWBREndpoint",
    "OutputSink",
    "WAWFixedTransport",
    "WAWProductionLaunchHandles",
    "WAWVerifiedExecutionAuthority",
    "WAWVerifiedLaunchHandleFactory",
    "receive_native_ready",
]
