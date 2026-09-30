"""R12-C2 C3-b production executor provider.

This module owns the production :class:`WAWRuntimeExecutorProvider`: the one
sealed owner of every production resource below the application layer (six
one-shot executable launch handles, the verified launch-handle factory, the
sealed auth lease owner, the production auth owner, the native process port,
the native auth-probe port factory and the conflict coordinator).

Construction order inside :meth:`create_executor` is fixed by the
``WAW_R12_RUNTIME_AUTH_PROBE.md`` C3-a closure contract:

lease owner -> production auth owner -> NativeHelperProcessPort ->
WAWNativeAuthProbePortFactory -> owner.bind_native_probe_path -> executor.

The exported deferred port returns a distinct application owner from
``take()``. Only that owner can create the executor, after the filesystem-v2
builder issues its unique authority. The inner provider receives the exact
resources then owns them once; ``close()`` is terminal with sticky failure
on uncertain descriptor cleanup.
Production profiles require the externally enrolled ``vendor_version`` and
``codex_unauthenticated_output_sha256`` values; composition fails closed
without them and never synthesizes versions or digests.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from agentbox_core.waw import AgentType, managed_marker
from agentbox_core.waw_tickets import ActiveAttachment

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import inspect_executable
from agentbox_runtime.project import ConfiguredProject, ProjectRegistry
from agentbox_runtime.waw_auth_lease import WAWAuthLeaseOwner
from agentbox_runtime.waw_auth_owner import WAWProductionAuthOwner
from agentbox_runtime.waw_auth_probe import WAWVendorPublicAuthBinding
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_conflicts import WAWConflictCoordinator, WAWConflictProbe
from agentbox_runtime.waw_executable import WAWExecutableKind, WAWExecutableLaunchHandle
from agentbox_runtime.waw_fixed_transport import (
    LinuxCgroupControlHandle,
    NativeHelperProcessPort,
    WAWFixedTransport,
    WAWVerifiedExecutionAuthority,
    WAWVerifiedLaunchHandleFactory,
)
from agentbox_runtime.waw_lifecycle import WAWLifecycleIdentity
from agentbox_runtime.waw_managed_command import WAWManagedCommand
from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2
from agentbox_runtime.waw_process_inspector import FixedProcessIdentity
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_application import WAWRuntimeExecutorProvider
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from agentbox_runtime.waw_runtime_resources import (
    WAWProductionResourceCleanupError,
    WAWProductionResources,
    build_waw_production_resources,
)
from agentbox_runtime.waw_vendor_enrollment import (
    WAWVendorEnrollmentRecord,
    revalidate_waw_vendor_enrollment,
)
from agentbox_runtime.waw_vendor_probe import (
    WAWVendorProbeId,
    WAWVendorProbeParserId,
    WAWVendorProbeProfile,
)

__all__ = [
    "WAWProductionExecutorProvider",
    "WAWProductionExecutorProviderError",
    "WAWVendorEnrollmentInput",
    "build_waw_production_executor_provider",
    "WAWDeferredProductionExecutorProvider",
    "build_waw_deferred_production_executor_provider",
]

if TYPE_CHECKING:
    from agentbox_runtime.waw_auth_native_port import WAWNativeAuthProbePortFactory

_RUN_ROOT = "/run/agentbox-waw"
_AUTH_SCRATCH_ROOT_NAME = "tmp"
_VENDOR_HOME_ROOT = "/var/lib/agentbox-waw/vendor-homes"
_POLICY_PATHS = MappingProxyType(
    {
        AgentType.CLAUDE: "/etc/claude-code",
        AgentType.CODEX: "/etc/codex",
    }
)
_PROBE_IDS = MappingProxyType(
    {
        AgentType.CLAUDE: WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1,
        AgentType.CODEX: WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
    }
)
_PARSER_IDS = MappingProxyType(
    {
        AgentType.CLAUDE: WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
        AgentType.CODEX: WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
    }
)
_EXPECTED_HANDLE_KINDS = tuple(WAWExecutableKind)
_VENDOR_KINDS = MappingProxyType(
    {
        AgentType.CLAUDE: WAWExecutableKind.CLAUDE,
        AgentType.CODEX: WAWExecutableKind.CODEX,
    }
)


class WAWProductionExecutorProviderError(RuntimeError):
    """Production executor provider construction or ownership failure."""


class WAWVendorEnrollmentInput(Mapping[str, str]):
    """Fail-closed external enrollment input: exact vendor versions/digests.

    The value is a frozen, exact-key mapping with one ``vendor_version`` per
    AgentType plus the Codex ``codex_unauthenticated_output_sha256``.  These
    are D/G/H enrollment facts; they are never derived, guessed or padded.
    """

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, str]) -> None:
        if not isinstance(values, Mapping):
            raise TypeError("enrollment input must be a mapping")
        copied = dict(values)
        expected = {
            "claude_vendor_version",
            "codex_vendor_version",
            "codex_unauthenticated_output_sha256",
        }
        if set(copied) != expected:
            raise WAWProductionExecutorProviderError(
                "vendor enrollment input must contain exactly the three enrolled values"
            )
        for key, value in copied.items():
            if type(value) is not str or not value:
                raise WAWProductionExecutorProviderError(
                    f"vendor enrollment value {key!r} is invalid"
                )
        self._values = MappingProxyType(copied)

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return "WAWVendorEnrollmentInput(<enrolled>)"


def _import_native_probe_factory() -> type[WAWNativeAuthProbePortFactory]:
    """Deferred import to avoid a circular import at module load time."""

    from agentbox_runtime.waw_auth_native_port import WAWNativeAuthProbePortFactory

    return WAWNativeAuthProbePortFactory


def _require_owned_directory(descriptor: int, path: str, *, mode: int) -> int:
    """Re-dup one caller-owned directory FD after exact provenance checks."""

    if type(descriptor) is not int or descriptor < 0:
        raise TypeError(f"{path} must be a directory descriptor")
    try:
        details = os.fstat(descriptor)
    except OSError as exc:
        raise WAWProductionExecutorProviderError(f"{path} descriptor is unavailable") from exc
    import stat as _stat

    if (
        not _stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.geteuid()
        or _stat.S_IMODE(details.st_mode) != mode
    ):
        raise WAWProductionExecutorProviderError(f"{path} provenance is invalid")
    try:
        linked = os.readlink(f"/proc/self/fd/{descriptor}")
    except OSError as exc:
        raise WAWProductionExecutorProviderError(f"{path} path cannot be verified") from exc
    if linked != path:
        raise WAWProductionExecutorProviderError(f"{path} path does not match")
    try:
        return os.dup(descriptor)
    except OSError as exc:
        raise WAWProductionExecutorProviderError(f"{path} cannot be held") from exc


def _open_owned_directory(path: str, *, mode: int) -> int:
    """Open one fixed directory with O_NOFOLLOW and verify exact provenance."""

    try:
        raw = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise WAWProductionExecutorProviderError(f"{path} anchor is unavailable") from exc
    try:
        return _require_owned_directory(raw, path, mode=mode)
    finally:
        _close_quiet(raw)


def _close_quiet(descriptor: int) -> None:
    with contextlib.suppress(OSError):
        os.close(descriptor)


class WAWProductionExecutorProvider(WAWRuntimeExecutorProvider):
    """Single-use sealed owner of the production executor composition."""

    def __init__(
        self,
        token: object,
        *,
        executable_handles: tuple[WAWExecutableLaunchHandle, ...],
        launch_handle_factory: WAWVerifiedLaunchHandleFactory,
        cgroup_delegate_root: int,
        project_registry: ProjectRegistry,
        enrollment: WAWVendorEnrollmentInput,
        conflict_coordinator: WAWConflictCoordinator,
        geometry: PtyGeometry,
        clock: Callable[[], float],
        attachment_validator: Callable[[ActiveAttachment], bool],
    ) -> None:
        if token is not _PROVIDER_TOKEN:
            raise WAWProductionExecutorProviderError(
                "production executor provider is not caller-constructible"
            )
        self._validate_construction(
            executable_handles=executable_handles,
            launch_handle_factory=launch_handle_factory,
            cgroup_delegate_root=cgroup_delegate_root,
            project_registry=project_registry,
            enrollment=enrollment,
            conflict_coordinator=conflict_coordinator,
            geometry=geometry,
            clock=clock,
            attachment_validator=attachment_validator,
        )
        self._handles = executable_handles
        self._factory = launch_handle_factory
        self._delegate_root = cgroup_delegate_root
        self._projects = project_registry
        self._enrollment = enrollment
        self._conflicts = conflict_coordinator
        self._geometry = geometry
        self._clock = clock
        self._attachment_validator = attachment_validator
        self._taken = False
        self._created = False
        self._closed = False
        self._close_failed = False
        self._lock = threading.RLock()
        self._executor_epoch: str | None = None
        self._composed_process_port: NativeHelperProcessPort | None = None
        self._lease_owner: WAWAuthLeaseOwner | None = None

    @staticmethod
    def _validate_construction(
        *,
        executable_handles: tuple[WAWExecutableLaunchHandle, ...],
        launch_handle_factory: WAWVerifiedLaunchHandleFactory,
        cgroup_delegate_root: int,
        project_registry: ProjectRegistry,
        enrollment: WAWVendorEnrollmentInput,
        conflict_coordinator: WAWConflictCoordinator,
        geometry: PtyGeometry,
        clock: Callable[[], float],
        attachment_validator: Callable[[ActiveAttachment], bool],
    ) -> None:
        if type(executable_handles) is not tuple or len(executable_handles) != len(
            _EXPECTED_HANDLE_KINDS
        ):
            raise WAWProductionExecutorProviderError(
                "exact-six executable launch handles are required"
            )
        for handle, kind in zip(executable_handles, _EXPECTED_HANDLE_KINDS, strict=True):
            if type(handle) is not WAWExecutableLaunchHandle or handle.identity.kind is not kind:
                raise WAWProductionExecutorProviderError(
                    "executable launch handles do not match the fixed inventory order"
                )
        if type(launch_handle_factory) is not WAWVerifiedLaunchHandleFactory:
            raise TypeError("verified launch handle factory is required")
        if type(cgroup_delegate_root) is not int or cgroup_delegate_root < 0:
            raise TypeError("cgroup delegate root must be a directory descriptor")
        if type(project_registry) is not ProjectRegistry:
            raise TypeError("project_registry must be ProjectRegistry")
        if type(enrollment) is not WAWVendorEnrollmentInput:
            raise TypeError("enrollment must be WAWVendorEnrollmentInput")
        if type(conflict_coordinator) is not WAWConflictCoordinator:
            raise TypeError("conflict_coordinator must be WAWConflictCoordinator")
        if type(geometry) is not PtyGeometry:
            raise TypeError("geometry must be PtyGeometry")
        if not callable(clock):
            raise TypeError("clock must be callable")
        first = clock()
        second = clock()
        import math as _math

        for sample in (first, second):
            if (
                isinstance(sample, bool)
                or not isinstance(sample, (int, float))
                or not _math.isfinite(float(sample))
                or sample < 0
            ):
                raise WAWProductionExecutorProviderError("provider clock is invalid")
        if float(second) < float(first):
            raise WAWProductionExecutorProviderError("provider clock is not monotonic")
        if not callable(attachment_validator):
            raise TypeError("attachment_validator must be callable")

    def take(self) -> WAWRuntimeExecutorProvider:
        """Transfer this single-use provider to the application owner."""

        with self._lock:
            if self._closed or self._taken:
                raise WAWProductionExecutorProviderError(
                    "production executor provider ownership is consumed"
                )
            self._taken = True
            return self

    def create_executor(
        self,
        runtime_epoch: str,
        authority: WAWVerifiedExecutionAuthority,
    ) -> WAWSupervisorExecutor:
        """Compose the one production executor bound to the verified authority."""

        with self._lock:
            if not self._taken:
                raise WAWProductionExecutorProviderError(
                    "production executor provider is not yet taken"
                )
            if self._closed or self._created:
                raise WAWProductionExecutorProviderError("production executor was already created")
            if type(authority) is not WAWVerifiedExecutionAuthority:
                raise TypeError("verified execution authority is required")
            if self._factory.authority is not authority:
                raise WAWProductionExecutorProviderError(
                    "launch handle factory is not bound to this authority"
                )
            self._created = True
            self._executor_epoch = runtime_epoch
        try:
            return self._compose(runtime_epoch, authority)
        except BaseException:
            with self._lock:
                self._close_failed = True
            self.close()
            raise

    def _compose(
        self,
        runtime_epoch: str,
        authority: WAWVerifiedExecutionAuthority,
    ) -> WAWSupervisorExecutor:
        # Runtime-owned scratch sources live below tmp; the root-owned
        # auth-probe path is only the native namespace's mount anchor.
        scratch_root = _open_owned_directory(f"{_RUN_ROOT}/{_AUTH_SCRATCH_ROOT_NAME}", mode=0o755)
        try:
            lease_owner = WAWAuthLeaseOwner(authority, scratch_root=scratch_root)
        finally:
            _close_quiet(scratch_root)
        self._lease_owner = lease_owner
        owner = WAWProductionAuthOwner(
            authority,
            runner=None,
            bindings=self._public_auth_bindings(authority),
            lease_owner=lease_owner,
            clock=self._clock,
            native_unbound=True,
        )
        tmux_directory = self._open_tmux_socket_directory()
        try:
            tmux_config = self._open_tmux_config()
            try:
                process_port = NativeHelperProcessPort.from_verified_execution_authority(
                    authority,
                    self._handles,
                    tmux_socket_directory=tmux_directory,
                    tmux_config=tmux_config,
                    auth_owner=owner,
                )
            finally:
                _close_quiet(tmux_config)
        finally:
            _close_quiet(tmux_directory)
        self._composed_process_port = process_port
        factory = _import_native_probe_factory()(authority, process_port=process_port)
        owner.bind_native_probe_path(factory, self._native_profiles())
        return WAWSupervisorExecutor(
            runtime_epoch=runtime_epoch,
            project_registry=self._projects,
            command_factory=self._command_factory,
            transport_factory=self._transport_factory,
            geometry=self._geometry,
            clock=self._clock,
            attachment_validator=self._attachment_validator,
            conflict_coordinator=self._conflicts,
            execution_authority=authority,
            auth_probe=owner,
        )

    def _open_tmux_socket_directory(self) -> int:
        try:
            raw = os.open(f"{_RUN_ROOT}/tmux", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise WAWProductionExecutorProviderError(
                "tmux socket directory is unavailable"
            ) from exc
        try:
            return _require_owned_directory(raw, f"{_RUN_ROOT}/tmux", mode=0o700)
        finally:
            _close_quiet(raw)

    def _open_tmux_config(self) -> int:
        try:
            raw = os.open("/usr/share/agentbox/waw/tmux.conf", os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise WAWProductionExecutorProviderError("tmux configuration is unavailable") from exc
        try:
            details = os.fstat(raw)
        except OSError as exc:
            _close_quiet(raw)
            raise WAWProductionExecutorProviderError("tmux configuration is unavailable") from exc
        import stat as _stat

        if (
            not _stat.S_ISREG(details.st_mode)
            or details.st_uid != 0
            or _stat.S_IMODE(details.st_mode) & 0o022
        ):
            _close_quiet(raw)
            raise WAWProductionExecutorProviderError("tmux configuration provenance is invalid")
        try:
            linked = os.readlink(f"/proc/self/fd/{raw}")
        except OSError as exc:
            _close_quiet(raw)
            raise WAWProductionExecutorProviderError(
                "tmux configuration path cannot be verified"
            ) from exc
        if linked != "/usr/share/agentbox/waw/tmux.conf":
            _close_quiet(raw)
            raise WAWProductionExecutorProviderError("tmux configuration path does not match")
        try:
            return os.dup(raw)
        except OSError as exc:
            raise WAWProductionExecutorProviderError("tmux configuration cannot be held") from exc
        finally:
            _close_quiet(raw)

    def _executable_path(self, agent_type: AgentType) -> Path:
        kind = _VENDOR_KINDS[agent_type]
        matches = [
            entry.path
            for entry in self._factory.authority._manifest.executable_inventory.executables
            if entry.kind == kind.value
        ]
        if len(matches) != 1:
            raise WAWProductionExecutorProviderError(
                "vendor executable inventory entry is unavailable"
            )
        return Path(matches[0])

    def _public_auth_bindings(
        self, authority: WAWVerifiedExecutionAuthority
    ) -> dict[AgentType, WAWVendorPublicAuthBinding]:
        return {
            agent_type: WAWVendorPublicAuthBinding(
                agent_type=agent_type,
                runtime_host_installation_id=authority.runtime_host_installation_id,
                runtime_host_installation_revision=(authority.runtime_host_installation_revision),
                executable_fingerprint=authority.vendor_executable_fingerprint(agent_type),
                profile_id=cast(
                    str, INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]
                ),
                vendor_version=self._enrollment[f"{agent_type.value}_vendor_version"],
            )
            for agent_type in AgentType
        }

    def _native_profiles(self) -> dict[AgentType, WAWVendorProbeProfile]:
        profiles: dict[AgentType, WAWVendorProbeProfile] = {}
        for agent_type in AgentType:
            executable = self._executable_path(agent_type)
            digest = (
                self._enrollment["codex_unauthenticated_output_sha256"]
                if agent_type is AgentType.CODEX
                else None
            )
            profiles[agent_type] = WAWVendorProbeProfile(
                profile_id=cast(
                    str, INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]
                ),
                agent_type=agent_type,
                vendor_version=self._enrollment[f"{agent_type.value}_vendor_version"],
                probe_id=_PROBE_IDS[agent_type],
                parser_id=_PARSER_IDS[agent_type],
                executable=executable,
                cwd=Path(f"{_VENDOR_HOME_ROOT}/{agent_type.value}"),
                environment=(
                    ("HOME", f"{_VENDOR_HOME_ROOT}/{agent_type.value}"),
                    ("TERM", "dumb"),
                ),
                codex_unauthenticated_output_sha256=digest,
            )
        return profiles

    def _derive_process_identity(self, identity: WAWLifecycleIdentity) -> FixedProcessIdentity:
        agent_type = AgentType(identity.agent_type)
        if self._executor_epoch is None:
            raise WAWProductionExecutorProviderError("production executor epoch is not bound")
        return FixedProcessIdentity(
            workspace_id=identity.workspace_id,
            project_id=identity.project_id,
            agent_type=agent_type,
            generation=int(identity.generation),
            workspace_hash=hashlib.sha256(identity.workspace_id.encode("ascii")).hexdigest(),
            managed_marker=managed_marker(
                runtime_host_installation_id=identity.runtime_host_installation_id,
                runtime_host_installation_revision=int(identity.runtime_host_installation_revision),
                project_id=identity.project_id,
                agent_type=agent_type,
                workspace_id_value=identity.workspace_id,
                generation=int(identity.generation),
                binding_revision=int(identity.binding_revision),
                binding_digest=identity.binding_digest,
            ),
            profile_digest=self._factory.authority.interactive_profile_bundle_digest,
            runtime_host_installation_id=identity.runtime_host_installation_id,
            runtime_host_installation_revision=str(identity.runtime_host_installation_revision),
            runtime_epoch=self._executor_epoch,
        )

    def _command_factory(
        self, identity: WAWLifecycleIdentity, configured: ConfiguredProject
    ) -> WAWManagedCommand:
        agent_type = AgentType(identity.agent_type)
        if (
            type(configured) is not ConfiguredProject
            or configured.project_id != configured.path.name
        ):
            raise RuntimeOperationError(
                "WAW_PROJECT_INVALID", "Resolved Project path is invalid", category="validation"
            )
        configured_path = configured.path
        executable_path = self._executable_path(agent_type)
        executable = inspect_executable(executable_path, error_prefix=agent_type.name)
        marker = self._derive_process_identity(identity).managed_marker
        if agent_type is AgentType.CLAUDE:
            return WAWClaudeCommand(
                identity.workspace_id,
                identity.project_id,
                configured_path,
                executable,
                ("remote-control",),
                marker,
            )
        return WAWCodexCommand(
            identity.workspace_id,
            identity.project_id,
            configured_path,
            executable,
            (),
            marker,
        )

    def _transport_factory(
        self, identity: WAWLifecycleIdentity, command: WAWManagedCommand
    ) -> WAWFixedTransport:
        agent_type = AgentType(identity.agent_type)
        relative_key = command.cwd.name
        if (
            command.project_id != identity.project_id
            or command.workspace_id != identity.workspace_id
            or self._projects.resolve(relative_key).path != command.cwd
        ):
            raise RuntimeOperationError(
                "WAW_BINDING_INVALID",
                "Production command is not bound to the registered Project",
                category="conflict",
            )
        process_identity = self._derive_process_identity(identity)
        cgroup = LinuxCgroupControlHandle.from_delegated_fd(
            self._factory.authority,
            process_identity,
            self._delegate_root,
            create_workload=True,
        )
        endpoint = NativeHelperProcessPort.create_wbr_endpoint()
        handles = self._factory.create(
            identity=process_identity,
            relative_key=relative_key,
            wbr_endpoint=endpoint,
            cgroup=cgroup,
        )
        return WAWFixedTransport.production(
            identity=process_identity,
            handles=handles,
            executable_fingerprint=self._factory.authority.vendor_executable_fingerprint(
                agent_type
            ),
            port=self._process_port,
            clock=self._clock,
        )

    @property
    def _process_port(self) -> NativeHelperProcessPort:
        port = self.__dict__.get("_composed_process_port")
        if type(port) is not NativeHelperProcessPort:
            raise WAWProductionExecutorProviderError("production process port is not composed")
        return port

    def close(self) -> bool:
        """Idempotently release held descriptors; sticky failure on uncertainty."""

        with self._lock:
            if self._closed:
                return not self._close_failed
            self._closed = True
        ok = True
        if self._composed_process_port is not None:
            try:
                self._composed_process_port.close()
            except BaseException:
                # A live or uncertain native binding retains the lower owners.
                with self._lock:
                    self._close_failed = True
                return False
        if self._lease_owner is not None:
            try:
                self._lease_owner.close()
            except BaseException:
                with self._lock:
                    self._close_failed = True
                return False
        for handle in self._handles:
            try:
                handle.close()
            except BaseException:
                ok = False
            if not handle.closed:
                ok = False
        try:
            self._factory.close()
        except BaseException:
            ok = False
        try:
            os.close(self._delegate_root)
        except OSError:
            ok = False
        self._delegate_root = -1
        with self._lock:
            self._close_failed = self._close_failed or not ok
        return not self._close_failed


_PROVIDER_TOKEN = object()


def build_waw_production_executor_provider(
    *,
    executable_handles: tuple[WAWExecutableLaunchHandle, ...],
    launch_handle_factory: WAWVerifiedLaunchHandleFactory,
    cgroup_delegate_root: int,
    project_registry: ProjectRegistry,
    enrollment: WAWVendorEnrollmentInput,
    conflict_probe: WAWConflictProbe,
    geometry: PtyGeometry,
    clock: Callable[[], float],
    attachment_validator: Callable[[ActiveAttachment], bool],
) -> WAWProductionExecutorProvider:
    """Build the sealed production executor provider from owned resources."""

    if not isinstance(conflict_probe, WAWConflictProbe):  # pragma: no cover - nominal
        raise TypeError("conflict_probe must implement WAWConflictProbe")
    return WAWProductionExecutorProvider(
        _PROVIDER_TOKEN,
        executable_handles=executable_handles,
        launch_handle_factory=launch_handle_factory,
        cgroup_delegate_root=cgroup_delegate_root,
        project_registry=project_registry,
        enrollment=enrollment,
        conflict_coordinator=WAWConflictCoordinator(conflict_probe),
        geometry=geometry,
        clock=clock,
        attachment_validator=attachment_validator,
    )


_DEFERRED_PROVIDER_TOKEN = object()


class _OwnedDeferredProvider(WAWRuntimeExecutorProvider):
    """Distinct application owner; the original port cannot close its resources."""

    def __init__(self, provider: WAWDeferredProductionExecutorProvider) -> None:
        self._provider = provider

    def take(self) -> WAWRuntimeExecutorProvider:
        raise WAWProductionExecutorProviderError("production ownership is consumed")

    def create_executor(
        self, runtime_epoch: str, authority: WAWVerifiedExecutionAuthority
    ) -> WAWSupervisorExecutor:
        return self._provider._create_executor(runtime_epoch, authority)

    def close(self) -> bool:
        return self._provider._close_owned()


class WAWDeferredProductionExecutorProvider(WAWRuntimeExecutorProvider):
    """Defer fixed resource opening until the builder issues one authority."""

    def __init__(
        self,
        token: object,
        *,
        project_registry: ProjectRegistry,
        enrollment: WAWVendorEnrollmentRecord,
        conflict_probe: WAWConflictProbe,
        geometry: PtyGeometry,
        clock: Callable[[], float],
        attachment_validator: Callable[[ActiveAttachment], bool],
    ) -> None:
        if token is not _DEFERRED_PROVIDER_TOKEN:
            raise WAWProductionExecutorProviderError(
                "deferred provider is not caller-constructible"
            )
        if (
            type(project_registry) is not ProjectRegistry
            or type(enrollment) is not WAWVendorEnrollmentRecord
            or not isinstance(conflict_probe, WAWConflictProbe)
            or type(geometry) is not PtyGeometry
            or not callable(clock)
            or not callable(attachment_validator)
        ):
            raise TypeError("fixed production provider inputs are required")
        self._projects = project_registry
        self._enrollment = enrollment
        self._conflict_probe = conflict_probe
        self._geometry = geometry
        self._clock = clock
        self._attachment_validator = attachment_validator
        self._lock = threading.RLock()
        self._taken = False
        self._created = False
        self._closed = False
        self._close_failed = False
        self._inner: WAWProductionExecutorProvider | None = None

    def take(self) -> WAWRuntimeExecutorProvider:
        with self._lock:
            if self._taken or self._closed:
                raise WAWProductionExecutorProviderError("production ownership is consumed")
            self._taken = True
            return _OwnedDeferredProvider(self)

    def create_executor(
        self, runtime_epoch: str, authority: WAWVerifiedExecutionAuthority
    ) -> WAWSupervisorExecutor:
        raise WAWProductionExecutorProviderError("application owner must create the executor")

    def close(self) -> bool:
        with self._lock:
            if self._taken:
                return False
            self._closed = True
            return True

    def _create_executor(
        self, runtime_epoch: str, authority: WAWVerifiedExecutionAuthority
    ) -> WAWSupervisorExecutor:
        with self._lock:
            if not self._taken or self._closed or self._created:
                raise WAWProductionExecutorProviderError(
                    "production executor ownership is consumed"
                )
            if type(authority) is not WAWVerifiedExecutionAuthority:
                raise TypeError("verified execution authority is required")
            manifest = authority._manifest
            if (
                type(manifest) is not CrossManifestPinV2
                or str(self._projects.root) != manifest.project_root.configured_root
            ):
                raise WAWProductionExecutorProviderError(
                    "Project registry root does not match the verified authority"
                )
            self._created = True
            resources: WAWProductionResources | None = None
            inner: WAWProductionExecutorProvider | None = None
            try:
                self._enrollment.require_authority(authority)
                revalidate_waw_vendor_enrollment(self._enrollment)
                resources = build_waw_production_resources(authority)
                if resources.authority is not authority:
                    raise WAWProductionExecutorProviderError(
                        "production resources are bound to a different authority"
                    )
                inner = build_waw_production_executor_provider(
                    executable_handles=resources.handles,
                    launch_handle_factory=resources.launch_factory,
                    cgroup_delegate_root=resources.cgroup_delegate_root,
                    project_registry=self._projects,
                    enrollment=WAWVendorEnrollmentInput(self._enrollment.values),
                    conflict_probe=self._conflict_probe,
                    geometry=self._geometry,
                    clock=self._clock,
                    attachment_validator=self._attachment_validator,
                )
                resources.transfer_to_provider()
                self._inner = inner
                return inner.take().create_executor(runtime_epoch, authority)
            except BaseException as failure:
                clean = not isinstance(failure, WAWProductionResourceCleanupError)
                try:
                    if inner is not None:
                        clean = inner.close() is True and clean
                    elif resources is not None:
                        clean = resources.close() is True and clean
                except BaseException:
                    clean = False
                self._closed = True
                self._close_failed = not clean
                if not clean:
                    if isinstance(failure, WAWProductionResourceCleanupError):
                        raise
                    raise RuntimeOperationError(
                        "RUNTIME_UNAVAILABLE",
                        "Production executor construction cleanup is uncertain",
                        category="unavailable",
                    ) from failure
                raise

    def _close_owned(self) -> bool:
        with self._lock:
            if self._closed:
                return not self._close_failed
            self._closed = True
            if self._inner is None:
                return not self._close_failed
            try:
                clean = self._inner.close()
            except BaseException:
                clean = False
            self._close_failed = self._close_failed or not clean
            return not self._close_failed


def build_waw_deferred_production_executor_provider(
    *,
    project_registry: ProjectRegistry,
    enrollment: WAWVendorEnrollmentRecord,
    conflict_probe: WAWConflictProbe,
    geometry: PtyGeometry,
    clock: Callable[[], float],
    attachment_validator: Callable[[ActiveAttachment], bool],
) -> WAWDeferredProductionExecutorProvider:
    """Create the production port before, and resources after, authority issue."""

    return WAWDeferredProductionExecutorProvider(
        _DEFERRED_PROVIDER_TOKEN,
        project_registry=project_registry,
        enrollment=enrollment,
        conflict_probe=conflict_probe,
        geometry=geometry,
        clock=clock,
        attachment_validator=attachment_validator,
    )
