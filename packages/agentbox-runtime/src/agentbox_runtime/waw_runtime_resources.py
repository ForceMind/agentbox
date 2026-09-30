"""Authority-deferred, fixed production launch resources for one WAW Runtime.

The filesystem-v2 builder issues its verified authority only after loading the
cross-pinned manifest. Opening launch handles before that point would bind
them to a different authority object. This module receives the builder's exact
authority once and owns every descriptor it opens until a provider takes the
result. It never accepts request-supplied paths or executable selectors.
"""

from __future__ import annotations

import os
import threading

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_executable import (
    WAWExecutableInventory,
    WAWExecutableKind,
    WAWExecutableLaunchHandle,
)
from agentbox_runtime.waw_fixed_transport import (
    WAWVerifiedExecutionAuthority,
    WAWVerifiedLaunchHandleFactory,
    _verify_delegate_root,
)
from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2, cgroup_delegate_root_path

_RESOURCE_TOKEN = object()
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_CLAUDE_HOME = "/var/lib/agentbox-waw/vendor-homes/claude"
_CODEX_HOME = "/var/lib/agentbox-waw/vendor-homes/codex"
_TMP_ROOT = "/run/agentbox-waw/tmp"
_CLAUDE_POLICY_DIRECTORY = "/etc/claude-code"
_CODEX_POLICY_DIRECTORY = "/etc/codex"
_CLAUDE_POLICY_FILE = "/etc/claude-code/managed-settings.json"
_CODEX_REQUIREMENTS_FILE = "/etc/codex/requirements.toml"
_CODEX_MANAGED_CONFIG_FILE = "/etc/codex/managed_config.toml"


class WAWProductionResourceCleanupError(RuntimeOperationError):
    """A partial resource construction cannot prove that every FD closed."""

    def __init__(self) -> None:
        super().__init__(
            "RUNTIME_UNAVAILABLE",
            "Production resource construction cleanup is uncertain",
            category="unavailable",
        )


def _open_role(path: str, *, directory: bool) -> int:
    try:
        return os.open(path, _DIRECTORY_FLAGS if directory else _FILE_FLAGS)
    except OSError as exc:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Installed WAW resource is unavailable", category="unavailable"
        ) from exc


class WAWProductionResources:
    """One-shot owned bundle; close is terminal and reports uncertain cleanup."""

    def __init__(
        self,
        token: object,
        *,
        authority: WAWVerifiedExecutionAuthority,
        handles: tuple[WAWExecutableLaunchHandle, ...],
        launch_factory: WAWVerifiedLaunchHandleFactory,
        cgroup_delegate_root: int,
    ) -> None:
        if token is not _RESOURCE_TOKEN:
            raise RuntimeError("production resources are not caller-constructible")
        if (
            type(authority) is not WAWVerifiedExecutionAuthority
            or type(handles) is not tuple
            or tuple(handle.identity.kind for handle in handles) != tuple(WAWExecutableKind)
            or type(launch_factory) is not WAWVerifiedLaunchHandleFactory
            or launch_factory.authority is not authority
            or type(cgroup_delegate_root) is not int
            or cgroup_delegate_root < 0
        ):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Production launch resources are inconsistent",
                category="unavailable",
            )
        self.authority = authority
        self.handles = handles
        self.launch_factory = launch_factory
        self.cgroup_delegate_root = cgroup_delegate_root
        self._lock = threading.RLock()
        self._closed = False
        self._close_failed = False
        self._transferred = False

    def transfer_to_provider(self) -> None:
        """Retire this temporary owner after a validated provider takes its FDs."""

        with self._lock:
            if self._closed or self._transferred:
                raise RuntimeError("production resource ownership is consumed")
            self._transferred = True

    def close(self) -> bool:
        with self._lock:
            if self._transferred:
                return False
            if self._closed:
                return not self._close_failed
            self._closed = True
            ok = True
            for handle in self.handles:
                try:
                    handle.close()
                except BaseException:
                    ok = False
                if not handle.closed:
                    ok = False
            try:
                self.launch_factory.close()
            except BaseException:
                ok = False
            try:
                os.close(self.cgroup_delegate_root)
            except OSError:
                ok = False
            self.cgroup_delegate_root = -1
            self._close_failed = not ok
            return ok


def build_waw_production_resources(
    authority: WAWVerifiedExecutionAuthority,
) -> WAWProductionResources:
    """Open exact-six pinned executables and fixed installed descriptors once.

    All paths except the Project root and delegated cgroup subtree are fixed
    constants. Those two values come only from the authority's already
    cross-verified v2 manifest. The launch factory and cgroup verifier compare
    held descriptors to that same authority before anything is returned.
    """

    if type(authority) is not WAWVerifiedExecutionAuthority:
        raise TypeError("verified execution authority is required")
    manifest = authority._manifest
    if type(manifest) is not CrossManifestPinV2:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE", "Verified v2 manifest is unavailable", category="unavailable"
        )
    opened: list[int] = []
    handles: list[WAWExecutableLaunchHandle] = []
    launch_factory: WAWVerifiedLaunchHandleFactory | None = None
    delegate_root = -1
    cleanup_uncertain = False
    try:
        inventory = WAWExecutableInventory.from_manifest(manifest.executable_inventory)
        for kind in WAWExecutableKind:
            with inventory.open(kind) as verified:
                handles.append(
                    verified.create_launch_handle(
                        expected_kind=kind,
                        profile_digest=authority.interactive_profile_bundle_digest,
                    )
                )
        if tuple(handle.identity.kind for handle in handles) != tuple(WAWExecutableKind):
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE", "Executable inventory order changed", category="unavailable"
            )
        roles = (
            (manifest.project_root.configured_root, True),
            (_CLAUDE_HOME, True),
            (_CODEX_HOME, True),
            (_TMP_ROOT, True),
            (_CLAUDE_POLICY_DIRECTORY, True),
            (_CODEX_POLICY_DIRECTORY, True),
            (_CLAUDE_POLICY_FILE, False),
            (_CODEX_REQUIREMENTS_FILE, False),
            (_CODEX_MANAGED_CONFIG_FILE, False),
        )
        for path, directory in roles:
            opened.append(_open_role(path, directory=directory))
        launch_factory = WAWVerifiedLaunchHandleFactory(
            authority=authority,
            project_root=opened[0],
            claude_home=opened[1],
            codex_home=opened[2],
            temp_root=opened[3],
            claude_policy_directory=opened[4],
            codex_policy_directory=opened[5],
            claude_policy_file=opened[6],
            codex_requirements_file=opened[7],
            codex_managed_config_file=opened[8],
        )
        # The factory duplicates verified roles; release the temporary inputs
        # before it can be published to the provider.
        while opened:
            descriptor = opened.pop()
            try:
                os.close(descriptor)
            except OSError:
                cleanup_uncertain = True
                raise
        delegate_root = _open_role(cgroup_delegate_root_path(manifest.cgroup), directory=True)
        _verify_delegate_root(delegate_root, authority)
        return WAWProductionResources(
            _RESOURCE_TOKEN,
            authority=authority,
            handles=tuple(handles),
            launch_factory=launch_factory,
            cgroup_delegate_root=delegate_root,
        )
    except BaseException as failure:
        if delegate_root >= 0:
            try:
                os.close(delegate_root)
            except OSError:
                cleanup_uncertain = True
        while opened:
            descriptor = opened.pop()
            try:
                os.close(descriptor)
            except OSError:
                cleanup_uncertain = True
        if launch_factory is not None:
            try:
                launch_factory.close()
            except BaseException:
                cleanup_uncertain = True
        for handle in handles:
            try:
                handle.close()
            except BaseException:
                cleanup_uncertain = True
            if not handle.closed:
                cleanup_uncertain = True
        if cleanup_uncertain:
            raise WAWProductionResourceCleanupError() from failure
        raise


__all__ = [
    "WAWProductionResourceCleanupError",
    "WAWProductionResources",
    "build_waw_production_resources",
]
