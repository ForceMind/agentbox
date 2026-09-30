"""R12-C2 C3-b: production executor provider unit coverage.

Covers construction-time validation, one-shot ownership semantics, the
fail-closed vendor enrollment input, derived process-identity fields and
idempotent close with sticky failure.  Host anchors (auth scratch, tmux,
cgroup delegation) and the native process port are Linux host resources and
are covered by host evidence, not by these portable unit tests.
"""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast
from unittest import mock

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWLegacyClaudeState,
    WAWLegacyCodexState,
    WAWManagedConflictState,
)
from agentbox_runtime.waw_executable import (
    WAWExecutableIdentity,
    WAWExecutableKind,
    WAWExecutableLaunchHandle,
)
from agentbox_runtime.waw_fixed_transport import (
    LinuxCgroupControlHandle,
    NativeHelperProcessPort,
    WAWVerifiedExecutionAuthority,
    WAWVerifiedLaunchHandleFactory,
)
from agentbox_runtime.waw_lifecycle import WAWLifecycleIdentity
from agentbox_runtime.waw_managed_command import WAWManagedCommand
from agentbox_runtime.waw_manifest_codecs import CrossManifestPinV2
from agentbox_runtime.waw_process_inspector import FixedProcessIdentity
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_application import WAWRuntimeExecutorProvider
from agentbox_runtime.waw_runtime_provider import (
    WAWDeferredProductionExecutorProvider,
    WAWProductionExecutorProvider,
    WAWProductionExecutorProviderError,
    WAWVendorEnrollmentInput,
    build_waw_deferred_production_executor_provider,
    build_waw_production_executor_provider,
)
from agentbox_runtime.waw_runtime_resources import (
    WAWProductionResourceCleanupError,
    WAWProductionResources,
)
from agentbox_runtime.waw_vendor_enrollment import (
    WAWVendorEnrollmentError,
    WAWVendorEnrollmentRecord,
)

PROJECT = "prj_" + "1" * 32
HOST = "wri_" + "2" * 32
REVISION = "2"
BINDING_DIGEST = "a" * 64
PROFILE_DIGEST = "b" * 64
ENROLLMENT_VALUES = {
    "claude_vendor_version": "2.1.226",
    "codex_vendor_version": "0.146.1",
    "codex_unauthenticated_output_sha256": "f" * 64,
}


class _ConflictProbe:
    def legacy_claude(self, project_id: str) -> WAWLegacyClaudeState:
        return WAWLegacyClaudeState.ABSENT

    def legacy_codex_remote(self) -> WAWLegacyCodexState:
        return WAWLegacyCodexState.ABSENT

    def waw_for_project(self, project_id: str) -> tuple[WAWManagedConflictState, ...]:
        return ()

    def waw_for_host(self) -> tuple[WAWManagedConflictState, ...]:
        return ()


def _launch_handles() -> tuple[WAWExecutableLaunchHandle, ...]:
    handles: list[WAWExecutableLaunchHandle] = []
    for kind in WAWExecutableKind:
        handle = object.__new__(WAWExecutableLaunchHandle)
        object.__setattr__(
            handle,
            "_identity",
            WAWExecutableIdentity(
                kind=kind,
                path=Path(f"/usr/lib/agentbox/waw/{kind.value}"),
                device=1,
                inode=1,
                uid=os.geteuid(),
                gid=os.getegid(),
                mode=0o755,
                size=1,
                modified_ns=1,
                changed_ns=1,
                links=1,
                sha256="c" * 64,
            ),
        )
        object.__setattr__(handle, "_descriptor", -1)
        object.__setattr__(handle, "_lock", threading.Lock())
        object.__setattr__(handle, "_finalizer", mock.Mock())
        handles.append(handle)
    return tuple(handles)


def _factory(authority: object) -> WAWVerifiedLaunchHandleFactory:
    factory = object.__new__(WAWVerifiedLaunchHandleFactory)
    object.__setattr__(factory, "_authority", authority)
    return factory


def _enrollment() -> WAWVendorEnrollmentInput:
    return WAWVendorEnrollmentInput(dict(ENROLLMENT_VALUES))


def _provider(
    *,
    handles: tuple[WAWExecutableLaunchHandle, ...] | None = None,
    authority: object | None = None,
    cgroup_delegate_root: int = 0,
    project_registry: ProjectRegistry | None = None,
) -> WAWProductionExecutorProvider:
    actual_authority = authority if authority is not None else mock.sentinel.authority
    return build_waw_production_executor_provider(
        executable_handles=handles if handles is not None else _launch_handles(),
        launch_handle_factory=_factory(actual_authority),
        cgroup_delegate_root=cgroup_delegate_root,
        project_registry=project_registry or ProjectRegistry(Path.cwd()),
        enrollment=_enrollment(),
        conflict_probe=_ConflictProbe(),
        geometry=PtyGeometry(80, 24),
        clock=lambda: 1.0,
        attachment_validator=lambda _attachment: True,
    )


def _deferred_record() -> WAWVendorEnrollmentRecord:
    return WAWVendorEnrollmentRecord(
        HOST,
        REVISION,
        "a" * 64,
        "3",
        "steady",
        MappingProxyType(dict(ENROLLMENT_VALUES)),
        "d" * 64,
        (1, 2, 3, 4, 5),
        (1, 2, 3, 4, 5, 1, 100, 1, 1),
    )


def _deferred_provider(
    enrollment: WAWVendorEnrollmentRecord | None = None,
) -> WAWDeferredProductionExecutorProvider:
    return build_waw_deferred_production_executor_provider(
        project_registry=ProjectRegistry(Path.cwd()),
        enrollment=enrollment or _deferred_record(),
        conflict_probe=_ConflictProbe(),
        geometry=PtyGeometry(80, 24),
        clock=lambda: 1.0,
        attachment_validator=lambda _attachment: True,
    )


def _deferred_authority(project_root: Path | None = None) -> WAWVerifiedExecutionAuthority:
    manifest = object.__new__(CrossManifestPinV2)
    object.__setattr__(
        manifest,
        "project_root",
        SimpleNamespace(
            configured_root=str(project_root if project_root is not None else Path.cwd())
        ),
    )
    object.__setattr__(
        manifest,
        "runtime",
        SimpleNamespace(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision=REVISION,
            enrollment_epoch="3",
            enrollment_state="steady",
        ),
    )
    object.__setattr__(manifest, "runtime_manifest_digest", "a" * 64)
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    object.__setattr__(authority, "_manifest", manifest)
    return authority


class TestDeferredOwner:
    @pytest.fixture(autouse=True)
    def fixed_enrollment_fixture(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.revalidate_waw_vendor_enrollment",
            lambda _record: None,
        )

    def test_enrollment_pin_drift_precedes_resource_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resources = mock.Mock()
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources",
            resources,
        )
        owner = _deferred_provider(replace(_deferred_record(), enrollment_epoch="4")).take()
        with pytest.raises(WAWVendorEnrollmentError):
            owner.create_executor("7", _deferred_authority())
        resources.assert_not_called()
        assert owner.close() is True

    def test_enrollment_file_drift_precedes_resource_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resources = mock.Mock()
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources",
            resources,
        )

        def drift(_record: WAWVendorEnrollmentRecord) -> None:
            raise WAWVendorEnrollmentError("installed enrollment changed")

        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.revalidate_waw_vendor_enrollment",
            drift,
        )
        owner = _deferred_provider().take()
        with pytest.raises(WAWVendorEnrollmentError):
            owner.create_executor("7", _deferred_authority())
        resources.assert_not_called()
        assert owner.close() is True

    def test_take_moves_authority_to_distinct_application_owner(self) -> None:
        provider = _deferred_provider()
        assert isinstance(provider, WAWRuntimeExecutorProvider)
        owner = provider.take()
        assert owner is not provider
        assert isinstance(owner, WAWRuntimeExecutorProvider)
        with pytest.raises(WAWProductionExecutorProviderError, match="consumed"):
            provider.take()
        with pytest.raises(WAWProductionExecutorProviderError, match="owner"):
            provider.create_executor("7", cast(Any, object()))
        assert provider.close() is False
        assert owner.close() is True

    def test_uses_only_the_builder_issued_authority_and_closes_owned_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        authority = _deferred_authority()
        resources = mock.Mock(spec=WAWProductionResources)
        resources.authority = authority
        resources.handles = _launch_handles()
        resources.launch_factory = _factory(authority)
        resources.cgroup_delegate_root = 42
        inner = mock.Mock(spec=WAWProductionExecutorProvider)
        inner.close.return_value = True
        expected = mock.sentinel.executor
        inner.take.return_value.create_executor.return_value = expected
        build_resources = mock.Mock(return_value=resources)
        build_inner = mock.Mock(return_value=inner)
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources",
            build_resources,
        )
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_executor_provider",
            build_inner,
        )

        owner = _deferred_provider().take()
        assert owner.create_executor("7", authority) is expected
        build_resources.assert_called_once_with(authority)
        assert build_inner.call_args.kwargs["launch_handle_factory"] is resources.launch_factory
        resources.transfer_to_provider.assert_called_once_with()
        inner.take.return_value.create_executor.assert_called_once_with("7", authority)
        assert owner.close() is True
        inner.close.assert_called_once_with()

    def test_mismatched_resource_authority_is_closed_before_executor_creation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        authority = _deferred_authority()
        resources = mock.Mock(spec=WAWProductionResources)
        resources.authority = object.__new__(WAWVerifiedExecutionAuthority)
        resources.close.return_value = True
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources",
            lambda _authority: resources,
        )
        owner = _deferred_provider().take()
        with pytest.raises(WAWProductionExecutorProviderError, match="different authority"):
            owner.create_executor("7", authority)
        resources.close.assert_called_once_with()
        assert owner.close() is True

    def test_uncertain_inner_close_is_sticky(self, monkeypatch: pytest.MonkeyPatch) -> None:
        authority = _deferred_authority()
        resources = mock.Mock(spec=WAWProductionResources)
        resources.authority = authority
        resources.handles = _launch_handles()
        resources.launch_factory = _factory(authority)
        resources.cgroup_delegate_root = 42
        inner = mock.Mock(spec=WAWProductionExecutorProvider)
        inner.take.return_value.create_executor.return_value = mock.sentinel.executor
        inner.close.return_value = False
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources",
            lambda _authority: resources,
        )
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_executor_provider",
            lambda **_kwargs: inner,
        )

        owner = _deferred_provider().take()
        owner.create_executor("7", authority)
        assert owner.close() is False
        assert owner.close() is False
        inner.close.assert_called_once_with()

    def test_uncertain_resource_construction_cannot_report_clean(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        authority = _deferred_authority()
        issue = mock.Mock(side_effect=WAWProductionResourceCleanupError())
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources", issue
        )
        owner = _deferred_provider().take()
        with pytest.raises(WAWProductionResourceCleanupError):
            owner.create_executor("7", authority)
        assert owner.close() is False
        issue.assert_called_once_with(authority)

    def test_failed_inner_close_is_not_retried_after_fd_uncertainty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        authority = _deferred_authority()
        resources = mock.Mock(spec=WAWProductionResources)
        resources.authority = authority
        resources.handles = _launch_handles()
        resources.launch_factory = _factory(authority)
        resources.cgroup_delegate_root = 42
        inner = mock.Mock(spec=WAWProductionExecutorProvider)
        inner.take.return_value.create_executor.side_effect = RuntimeError("partial start")
        inner.close.side_effect = RuntimeError("close uncertainty")
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources",
            lambda _authority: resources,
        )
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_executor_provider",
            lambda **_kwargs: inner,
        )

        owner = _deferred_provider().take()
        with pytest.raises(RuntimeOperationError, match="cleanup is uncertain"):
            owner.create_executor("7", authority)
        assert owner.close() is False
        inner.close.assert_called_once_with()

    def test_rejects_registry_root_drift_before_opening_any_resource(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        authority = _deferred_authority(Path("/srv/unrelated-projects"))
        build_resources = mock.Mock()
        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider.build_waw_production_resources",
            build_resources,
        )
        owner = _deferred_provider().take()
        with pytest.raises(WAWProductionExecutorProviderError, match="Project registry root"):
            owner.create_executor("7", authority)
        build_resources.assert_not_called()
        assert owner.close() is True


def _identity(
    project_id: str = PROJECT, agent_type: AgentType = AgentType.CLAUDE
) -> WAWLifecycleIdentity:
    return WAWLifecycleIdentity(
        workspace_id=workspace_id(project_id, agent_type),
        project_id=project_id,
        agent_type=agent_type.value,
        generation="1",
        binding_revision="1",
        binding_digest=BINDING_DIGEST,
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=REVISION,
    )


class TestVendorEnrollmentInput:
    def test_exact_three_values_required(self) -> None:
        with pytest.raises(WAWProductionExecutorProviderError, match="exactly the three"):
            WAWVendorEnrollmentInput({"claude_vendor_version": "1"})
        with pytest.raises(WAWProductionExecutorProviderError, match="exactly the three"):
            WAWVendorEnrollmentInput({**ENROLLMENT_VALUES, "extra": "1"})

    def test_empty_or_non_string_value_rejected(self) -> None:
        with pytest.raises(WAWProductionExecutorProviderError, match="invalid"):
            WAWVendorEnrollmentInput({**ENROLLMENT_VALUES, "claude_vendor_version": ""})
        with pytest.raises(WAWProductionExecutorProviderError, match="invalid"):
            WAWVendorEnrollmentInput(cast(Any, {**ENROLLMENT_VALUES, "codex_vendor_version": 1}))

    def test_repr_never_echoes_values(self) -> None:
        enrollment = _enrollment()
        assert repr(enrollment) == "WAWVendorEnrollmentInput(<enrolled>)"
        assert "2.1.226" not in repr(enrollment)

    def test_mapping_protocol(self) -> None:
        enrollment = _enrollment()
        assert len(enrollment) == 3
        assert set(enrollment) == set(ENROLLMENT_VALUES)
        assert enrollment["codex_vendor_version"] == ENROLLMENT_VALUES["codex_vendor_version"]


class TestConstruction:
    def test_not_caller_constructible(self) -> None:
        with pytest.raises(WAWProductionExecutorProviderError, match="caller-constructible"):
            WAWProductionExecutorProvider(
                object(),
                executable_handles=_launch_handles(),
                launch_handle_factory=_factory(mock.sentinel.authority),
                cgroup_delegate_root=0,
                project_registry=ProjectRegistry(Path.cwd()),
                enrollment=_enrollment(),
                conflict_coordinator=WAWConflictCoordinator(_ConflictProbe()),
                geometry=PtyGeometry(80, 24),
                clock=lambda: 1.0,
                attachment_validator=lambda _attachment: True,
            )

    def test_exact_six_handles_in_fixed_order(self) -> None:
        handles = list(_launch_handles())
        handles[0], handles[1] = handles[1], handles[0]
        with pytest.raises(WAWProductionExecutorProviderError, match="fixed inventory order"):
            _provider(handles=tuple(handles))
        with pytest.raises(WAWProductionExecutorProviderError, match="exact-six"):
            _provider(handles=_launch_handles()[:5])

    def test_transport_rejects_formal_project_mismatch_before_launch(self) -> None:
        provider = _provider()
        command = mock.Mock(spec=WAWManagedCommand)
        command.project_id = "prj_" + "f" * 32
        command.workspace_id = workspace_id(PROJECT, AgentType.CLAUDE)
        command.cwd = Path.cwd() / "relative-key-1"
        with pytest.raises(RuntimeOperationError) as invalid:
            provider._transport_factory(_identity(), command)
        assert invalid.value.code == "WAW_BINDING_INVALID"

    def test_transport_resolves_project_registered_after_provider_creation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "projects"
        root.mkdir()
        authority = mock.Mock(spec=WAWVerifiedExecutionAuthority)
        authority.interactive_profile_bundle_digest = PROFILE_DIGEST
        provider = _provider(
            authority=authority,
            project_registry=ProjectRegistry(root),
        )
        project = root / "relative-key-1"
        project.mkdir()
        provider._executor_epoch = "7"
        command = mock.Mock(spec=WAWManagedCommand)
        command.project_id = PROJECT
        command.workspace_id = workspace_id(PROJECT, AgentType.CLAUDE)
        command.cwd = project.resolve()

        def stop_before_cgroup(
            _cls: type[LinuxCgroupControlHandle],
            _authority: WAWVerifiedExecutionAuthority,
            _identity: FixedProcessIdentity,
            _delegate_root: int,
            *,
            create_workload: bool = False,
        ) -> LinuxCgroupControlHandle:
            assert create_workload is True
            raise RuntimeError("registered Project reached fixed cgroup boundary")

        monkeypatch.setattr(
            LinuxCgroupControlHandle,
            "from_delegated_fd",
            classmethod(stop_before_cgroup),
        )
        with pytest.raises(RuntimeError, match="registered Project reached fixed cgroup"):
            provider._transport_factory(_identity(), command)

    def test_clock_must_be_monotonic_finite(self) -> None:
        with pytest.raises(WAWProductionExecutorProviderError, match="monotonic"):
            build_waw_production_executor_provider(
                executable_handles=_launch_handles(),
                launch_handle_factory=_factory(mock.sentinel.authority),
                cgroup_delegate_root=0,
                project_registry=ProjectRegistry(Path.cwd()),
                enrollment=_enrollment(),
                conflict_probe=_ConflictProbe(),
                geometry=PtyGeometry(80, 24),
                clock=iter([2.0, 1.0]).__next__,
                attachment_validator=lambda _attachment: True,
            )

    def test_is_runtime_executor_provider(self) -> None:
        provider = _provider()
        assert isinstance(provider, WAWRuntimeExecutorProvider)


class TestOwnership:
    def test_take_is_one_shot(self) -> None:
        provider = _provider()
        taken = provider.take()
        assert taken is provider
        with pytest.raises(WAWProductionExecutorProviderError, match="consumed"):
            provider.take()

    def test_create_executor_requires_taken(self) -> None:
        provider = _provider()
        with pytest.raises(WAWProductionExecutorProviderError, match="not yet taken"):
            provider.create_executor("1", mock.sentinel.authority)

    def test_create_executor_requires_exact_authority_type(self) -> None:
        provider = _provider()
        provider.take()
        with pytest.raises(TypeError, match="verified execution authority"):
            provider.create_executor("1", mock.sentinel.authority)

    def test_create_executor_rejects_mismatched_factory_authority(self) -> None:
        provider = _provider(authority=mock.sentinel.factory_authority)
        provider.take()
        authority = object.__new__(WAWVerifiedExecutionAuthority)
        with pytest.raises(WAWProductionExecutorProviderError, match="not bound"):
            provider.create_executor("1", authority)

    def test_close_is_idempotent_and_sticky(self, tmp_path: Path) -> None:
        delegate = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        provider = _provider(cgroup_delegate_root=delegate)
        # Handles are pre-consumed (descriptor -1) and the factory has no
        # production close, so close reports sticky failure deterministically
        # and releases the delegate root descriptor.
        assert provider.close() is False
        assert provider.close() is False
        with pytest.raises(OSError):
            os.fstat(delegate)
        with pytest.raises(WAWProductionExecutorProviderError, match="consumed"):
            provider.take()

    def test_close_retains_lower_owners_if_native_port_is_uncertain(self, tmp_path: Path) -> None:
        delegate = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        provider = _provider(cgroup_delegate_root=delegate)
        port = mock.Mock(spec=NativeHelperProcessPort)
        port.close.side_effect = RuntimeError("live native binding")
        provider._composed_process_port = cast(NativeHelperProcessPort, port)
        try:
            assert provider.close() is False
            os.fstat(delegate)
            assert provider.close() is False
            port.close.assert_called_once_with()
        finally:
            os.close(delegate)

    def test_compose_uses_runtime_tmp_source_not_native_mount_anchor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        authority = object.__new__(WAWVerifiedExecutionAuthority)
        delegate = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        provider = _provider(authority=authority, cgroup_delegate_root=delegate)
        provider.take()
        observed: list[tuple[str, int]] = []

        def reject_after_path(path: str, *, mode: int) -> int:
            observed.append((path, mode))
            raise RuntimeError("scratch path checked")

        monkeypatch.setattr(
            "agentbox_runtime.waw_runtime_provider._open_owned_directory",
            reject_after_path,
        )
        with pytest.raises(RuntimeError, match="scratch path checked"):
            provider.create_executor("7", authority)
        assert observed == [("/run/agentbox-waw/tmp", 0o755)]
        with pytest.raises(OSError):
            os.fstat(delegate)


class TestDerivedFields:
    def test_workspace_hash_and_marker_and_digest(self) -> None:
        authority = mock.Mock(spec=WAWVerifiedExecutionAuthority)
        authority.interactive_profile_bundle_digest = PROFILE_DIGEST
        provider = _provider(authority=authority)
        provider.take()
        provider._executor_epoch = "7"
        identity = _identity()
        process_identity = provider._derive_process_identity(identity)
        assert (
            process_identity.workspace_hash
            == hashlib.sha256(identity.workspace_id.encode("ascii")).hexdigest()
        )
        assert process_identity.managed_marker == managed_marker(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision=int(REVISION),
            project_id=PROJECT,
            agent_type=AgentType.CLAUDE,
            workspace_id_value=identity.workspace_id,
            generation=1,
            binding_revision=1,
            binding_digest=BINDING_DIGEST,
        )
        assert process_identity.profile_digest == PROFILE_DIGEST
        assert process_identity.runtime_epoch == "7"

    def test_epoch_must_be_bound_before_derivation(self) -> None:
        provider = _provider()
        with pytest.raises(WAWProductionExecutorProviderError, match="epoch is not bound"):
            provider._derive_process_identity(_identity())
