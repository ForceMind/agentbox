"""R12-C2 M4: sealed owner lease integration and per-action control envelopes.

The executor drives ``WAWProductionAuthOwner.probe_with_lease`` for start and
awaiting-login resume while non-owner probes keep the exact echo path, and the
control server widens only the start dispatch envelope around the probe-owned
five-second budget.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import socket
import threading
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_protocol.waw_control import decode_control_response
from agentbox_runtime import waw_bootstrap as bootstrap_subject
from agentbox_runtime import waw_control_server as control_subject
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import inspect_executable
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_activation import WAWActivatedSockets
from agentbox_runtime.waw_auth_lease import WAWAuthLeaseOwner
from agentbox_runtime.waw_auth_owner import WAWProductionAuthOwner
from agentbox_runtime.waw_auth_probe import (
    WAWPublicAuthEvidence,
    WAWPublicAuthResult,
    WAWVendorPublicAuthBinding,
)
from agentbox_runtime.waw_bootstrap import (
    build_waw_control_server,
    create_waw_lifecycle_registry_development_only,
)
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_control_server import WAWControlServer
from agentbox_runtime.waw_epoch import WAWRuntimeEpochStore
from agentbox_runtime.waw_fixed_transport import (
    LinuxCgroupControlHandle,
    WAWFixedTransport,
    WAWVerifiedExecutionAuthority,
)
from agentbox_runtime.waw_host_manifest import WAWRuntimeHostManifestDevelopmentOnly
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleIdentity,
    WAWLifecycleObservation,
    WAWProjectBinding,
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
    WAWProcessInspector,
)
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_executor import (
    WAW_START_OPERATION_TIMEOUT_SECONDS,
    WAWSupervisorExecutor,
)
from agentbox_runtime.waw_supervisor import (
    RuntimeProbeEvidence,
    RuntimeStopEvidence,
    SupervisorState,
    WAWSupervisor,
)
from agentbox_runtime.waw_vendor_probe import (
    WAWVendorProbeEvidence,
    WAWVendorProbeFailure,
    WAWVendorProbeId,
    WAWVendorProbeParserId,
    WAWVendorProbeResult,
    WAWVendorProbeRunner,
)

PROJECT = "prj_" + "1" * 32
HOST = "wri_" + "2" * 32
REVISION = "2"
DIGEST = "a" * 64
WORKSPACE_HASH = "d" * 64
PROFILE_DIGEST = "b" * 64
FINGERPRINT = "c" * 64
SCRATCH_NAME = "auth-probe-g1"
VERSIONS = {AgentType.CLAUDE: "2.1.226", AgentType.CODEX: "0.146.1"}
PROBE_IDS = {
    AgentType.CLAUDE: WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1,
    AgentType.CODEX: WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
}
PARSER_IDS = {
    AgentType.CLAUDE: WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
    AgentType.CODEX: WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
}


def _authority(monkeypatch: pytest.MonkeyPatch) -> WAWVerifiedExecutionAuthority:
    monkeypatch.setattr(WAWVerifiedExecutionAuthority, "authorizes", lambda _self, _identity: True)
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority,
        "runtime_host_installation_id",
        property(lambda _self: HOST),
    )
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority,
        "runtime_host_installation_revision",
        property(lambda _self: REVISION),
    )
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority,
        "vendor_executable_fingerprint",
        lambda _self, _agent_type: FINGERPRINT,
    )
    return object.__new__(WAWVerifiedExecutionAuthority)


def _bindings() -> dict[AgentType, WAWVendorPublicAuthBinding]:
    return {
        agent_type: WAWVendorPublicAuthBinding(
            agent_type,
            HOST,
            REVISION,
            FINGERPRINT,
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            VERSIONS[agent_type],
        )
        for agent_type in AgentType
    }


class _RunnerControl:
    def __init__(self) -> None:
        self.calls: list[AgentType] = []
        self.result = WAWVendorProbeResult.AUTHENTICATED


def _runner(monkeypatch: pytest.MonkeyPatch, control: _RunnerControl) -> WAWVendorProbeRunner:
    async def fake_probe(
        _self: WAWVendorProbeRunner, *, agent_type: AgentType, observed_vendor_version: str
    ) -> WAWVendorProbeEvidence:
        control.calls.append(agent_type)
        unsupported = control.result is WAWVendorProbeResult.UNSUPPORTED
        exit_code = 0 if control.result is WAWVendorProbeResult.AUTHENTICATED else 1
        return WAWVendorProbeEvidence(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            agent_type,
            observed_vendor_version,
            PROBE_IDS[agent_type],
            PARSER_IDS[agent_type],
            control.result,
            WAWVendorProbeFailure.VERSION_MISMATCH if unsupported else WAWVendorProbeFailure.NONE,
            None if unsupported else exit_code,
        )

    monkeypatch.setattr(WAWVendorProbeRunner, "probe", fake_probe)
    return object.__new__(WAWVendorProbeRunner)


def _cgroup_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity: FixedProcessIdentity,
    authority: WAWVerifiedExecutionAuthority,
    state: dict[str, int],
) -> LinuxCgroupControlHandle:
    cgroup_dir = tmp_path / f"workload-{identity.workspace_hash[:8]}"
    cgroup_dir.mkdir(exist_ok=True)
    descriptor = os.open(cgroup_dir, os.O_RDONLY | os.O_DIRECTORY)
    handle = object.__new__(LinuxCgroupControlHandle)
    handle._descriptor = descriptor
    handle._authority = authority
    handle._identity = identity
    handle._closed = False
    handle._consumed = False
    handle._auth_borrowed = False
    handle._lock = threading.RLock()
    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: state["populated"])
    monkeypatch.setattr(LinuxCgroupControlHandle, "frozen", lambda _self: state["frozen"])
    monkeypatch.setattr(
        LinuxCgroupControlHandle,
        "production_qualified_for",
        lambda _self, _authority, _identity: True,
    )
    return handle


class _LeasePort:
    """Synthetic native port: exact authority plus a counted spawn."""

    def __init__(self, authority: WAWVerifiedExecutionAuthority) -> None:
        self.execution_authority = authority
        self.starts = 0

    def start(self, request: FixedLaunchRequest) -> FixedStartProof:
        self.starts += 1
        return FixedStartProof(
            request,
            FixedStartState.RUNNING,
            FixedProcessBinding(request.identity, object(), object(), object()),
            1,
        )

    def open_attachment(self, request: FixedAttachmentRequest) -> FixedAttachmentPort:
        raise AssertionError("attachment is outside the M4 scope")

    def probe(self, binding: FixedProcessBinding) -> RuntimeProbeEvidence:
        raise AssertionError("process probe is outside the M4 scope")

    def stop(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        raise AssertionError("process stop is outside the M4 scope")

    def destroy_fenced(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        raise AssertionError("fenced destroy is outside the M4 scope")


class _LeaseRig:
    """One executor wired to a sealed production owner over a borrowable transport."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        self.agent = AgentType.CODEX
        self.now = [1000.0]
        self.owner_now = [1000.0]
        root = tmp_path / "projects"
        project = root / "project-a"
        project.mkdir(parents=True)
        executable_path = tmp_path / "codex"
        executable_path.write_text("#!/bin/sh\n")
        executable_path.chmod(0o755)
        executable = inspect_executable(executable_path)
        self.workspace = workspace_id(PROJECT, self.agent)
        self.identity = WAWLifecycleIdentity(
            self.workspace, PROJECT, self.agent.value, "1", "1", DIGEST, HOST, REVISION
        )
        self.marker = managed_marker(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision=int(REVISION),
            project_id=PROJECT,
            agent_type=self.agent,
            workspace_id_value=self.workspace,
            generation=1,
            binding_revision=1,
            binding_digest=DIGEST,
        )

        def command_factory(item: WAWLifecycleIdentity, configured: Any) -> WAWCodexCommand:
            return WAWCodexCommand(
                item.workspace_id, item.project_id, configured.path, executable, (), self.marker
            )

        self.authority = _authority(monkeypatch)
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        scratch.chmod(0o700)
        workspace_dir = scratch / WORKSPACE_HASH
        workspace_dir.mkdir()
        workspace_dir.chmod(0o700)
        self.scratch = workspace_dir / SCRATCH_NAME
        scratch_fd = os.open(scratch, os.O_RDONLY | os.O_DIRECTORY)
        self.lease_owner = WAWAuthLeaseOwner(self.authority, scratch_root=scratch_fd)
        os.close(scratch_fd)
        self.control = _RunnerControl()
        self.runner = _runner(monkeypatch, self.control)
        self.owner = WAWProductionAuthOwner(
            self.authority,
            runner=self.runner,
            bindings=_bindings(),
            lease_owner=self.lease_owner,
            clock=lambda: self.owner_now[0],
            max_age_seconds=30.0,
        )
        self.cgroup_state = {"populated": 0, "frozen": 0}
        self.monkeypatch = monkeypatch
        self.tmp_path = tmp_path
        self.transports: list[WAWFixedTransport] = []
        self.ports: list[_LeasePort] = []
        self.handles: list[LinuxCgroupControlHandle] = []

        def transport_factory(_item: WAWLifecycleIdentity, _command: Any) -> WAWFixedTransport:
            transport, port, handle = self._new_transport()
            self.transports.append(transport)
            self.ports.append(port)
            self.handles.append(handle)
            return transport

        self.executor = WAWSupervisorExecutor(
            runtime_epoch="2",
            project_registry=ProjectRegistry(root),
            command_factory=command_factory,
            transport_factory=transport_factory,
            geometry=PtyGeometry(80, 24),
            clock=lambda: self.now[0],
            attachment_validator=lambda attachment: attachment.active_at(0.0),
            auth_probe=self.owner,
        )

    def _new_transport(self) -> tuple[WAWFixedTransport, _LeasePort, LinuxCgroupControlHandle]:
        identity = FixedProcessIdentity(
            self.workspace,
            PROJECT,
            self.agent,
            1,
            WORKSPACE_HASH,
            self.marker,
            PROFILE_DIGEST,
            HOST,
            REVISION,
            "2",
        )
        handle = _cgroup_handle(
            self.tmp_path, self.monkeypatch, identity, self.authority, self.cgroup_state
        )
        port = _LeasePort(self.authority)
        transport = object.__new__(WAWFixedTransport)
        transport._identity = identity
        transport._production = True
        transport._production_project_identity = None
        transport._handles = FixedLaunchHandles(
            project_directory=object(),
            selected_home_directory=object(),
            temp_directory=object(),
            bridge_executable=object(),
            vendor_executable=object(),
            policy_directory=object(),
            wbr_endpoint=object(),
            cgroup=handle,
        )
        transport._owned_launch_descriptors = ()
        transport._executable_fingerprint = FINGERPRINT
        transport._port = port
        transport._clock = lambda: self.now[0]
        transport._inspector = WAWProcessInspector(identity, port)
        transport._request = None
        transport._attachment = None
        transport._attachment_lease = None
        transport._wbr = None
        transport._last_cleanup = None
        transport._output_sink = None
        transport._initial_auth_evidence = None
        transport._auth_lease = None
        transport._auth_poisoned = False
        transport._start_attempted = False
        transport._closed = False
        transport._aborted_unstarted = False
        return transport, port, handle

    def binding(self) -> WAWProjectBinding:
        return WAWProjectBinding(PROJECT, "project-a", "1", "1", DIGEST, HOST, REVISION)

    def assert_lease_released(self) -> None:
        for transport in self.transports:
            assert transport._auth_lease is None
        for handle in self.handles:
            assert handle.auth_borrowed is False
        assert not self.scratch.exists()


def _record_authenticated(rig: _LeaseRig, checked_at: float) -> None:
    rig.owner._cache.record(
        WAWPublicAuthEvidence(
            AgentType.CODEX,
            HOST,
            REVISION,
            FINGERPRINT,
            checked_at,
            WAWPublicAuthResult.AUTHENTICATED,
        )
    )


def _error_code(exc: BaseException) -> str:
    assert isinstance(exc, RuntimeOperationError)
    return exc.code


@pytest.mark.anyio
async def test_start_live_probe_miss_releases_lease_and_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    await rig.executor.register_project_binding(rig.binding())
    started = await rig.executor.start(rig.identity)
    assert started.state == "RUNNING"
    assert rig.control.calls == [AgentType.CODEX]
    assert rig.ports[0].starts == 1
    transport = rig.transports[0]
    assert transport._initial_auth_evidence is not None
    assert transport._initial_auth_evidence.checked_at_monotonic == 1000.0
    rig.assert_lease_released()


@pytest.mark.anyio
async def test_start_commit_failure_aborts_transport_after_lease_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    await rig.executor.register_project_binding(rig.binding())

    def failing_commit(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeOperationError(
            "WAW_OPERATION_BUSY", "synthetic commit conflict", category="conflict"
        )

    monkeypatch.setattr(rig.executor, "_commit_start", failing_commit)
    with pytest.raises(RuntimeOperationError) as raised:
        await rig.executor.start(rig.identity)
    assert raised.value.code == "WAW_OPERATION_BUSY"
    assert rig.control.calls == [AgentType.CODEX]
    transport = rig.transports[0]
    assert transport._aborted_unstarted is True
    assert transport._closed is True
    assert rig.handles[0]._closed is True
    rig.assert_lease_released()


@pytest.mark.anyio
async def test_start_uses_fresh_cache_hit_without_rerunning_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    await rig.executor.register_project_binding(rig.binding())
    _record_authenticated(rig, 995.0)
    rig.owner_now[0] = 1024.0
    rig.now[0] = 1024.0
    started = await rig.executor.start(rig.identity)
    assert started.state == "RUNNING"
    assert rig.control.calls == []
    transport = rig.transports[0]
    assert transport._initial_auth_evidence is not None
    assert transport._initial_auth_evidence.checked_at_monotonic == 995.0
    rig.assert_lease_released()


@pytest.mark.anyio
async def test_start_rejects_cache_hit_aged_past_the_sealed_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    await rig.executor.register_project_binding(rig.binding())
    _record_authenticated(rig, 995.0)
    rig.owner_now[0] = 1024.0
    rig.now[0] = 1025.0
    with pytest.raises(RuntimeOperationError) as raised:
        await rig.executor.start(rig.identity)
    assert raised.value.code == "WAW_AUTH_UNKNOWN"
    assert rig.control.calls == []
    assert rig.ports[0].starts == 0
    assert rig.transports[0]._aborted_unstarted is True
    rig.assert_lease_released()


@pytest.mark.anyio
async def test_start_rejects_cache_hit_sampled_in_the_future(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    await rig.executor.register_project_binding(rig.binding())
    _record_authenticated(rig, 1001.0)
    rig.owner_now[0] = 1030.0
    rig.now[0] = 1000.5
    with pytest.raises(RuntimeOperationError) as raised:
        await rig.executor.start(rig.identity)
    assert raised.value.code == "WAW_AUTH_UNKNOWN"
    assert rig.control.calls == []
    assert rig.ports[0].starts == 0
    rig.assert_lease_released()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "code"),
    [
        (WAWVendorProbeResult.UNKNOWN, "WAW_AUTH_UNKNOWN"),
        (WAWVendorProbeResult.UNSUPPORTED, "WAW_PROFILE_UNSUPPORTED"),
    ],
)
async def test_unknown_or_unsupported_results_fail_closed_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: WAWVendorProbeResult,
    code: str,
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    rig.control.result = result
    await rig.executor.register_project_binding(rig.binding())
    with pytest.raises(RuntimeOperationError) as raised:
        await rig.executor.start(rig.identity)
    assert raised.value.code == code
    assert rig.control.calls == [AgentType.CODEX]
    assert rig.ports[0].starts == 0
    assert rig.transports[0]._aborted_unstarted is True
    rig.assert_lease_released()


@pytest.mark.anyio
async def test_unauthenticated_start_reaches_login_required_without_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    rig.control.result = WAWVendorProbeResult.UNAUTHENTICATED
    await rig.executor.register_project_binding(rig.binding())
    login = await rig.executor.start(rig.identity)
    assert login.state == "LOGIN_REQUIRED"
    assert login.process_state == "NOT_STARTED"
    assert rig.ports[0].starts == 0
    transport = rig.transports[0]
    assert transport._start_attempted is True
    assert transport._inspector.login_required is True
    rig.assert_lease_released()


class _EchoProbe:
    """Non-owner probe: exact echo, with a tripwire on the lease entrypoint."""

    def __init__(self, result: WAWPublicAuthResult) -> None:
        self.result = result
        self.calls: list[tuple[AgentType, str, str, str, float]] = []

    async def probe(
        self,
        *,
        agent_type: AgentType,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: str,
        executable_fingerprint: str,
        checked_at_monotonic: float,
    ) -> WAWPublicAuthEvidence:
        self.calls.append(
            (
                agent_type,
                runtime_host_installation_id,
                runtime_host_installation_revision,
                executable_fingerprint,
                checked_at_monotonic,
            )
        )
        return WAWPublicAuthEvidence(
            agent_type,
            runtime_host_installation_id,
            runtime_host_installation_revision,
            executable_fingerprint,
            checked_at_monotonic,
            self.result,
        )

    async def probe_with_lease(self, *_args: Any, **_kwargs: Any) -> WAWPublicAuthEvidence:
        raise AssertionError("non-owner probes must stay on the echo path")


@pytest.mark.anyio
async def test_non_owner_probe_keeps_the_exact_echo_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    probe = _EchoProbe(WAWPublicAuthResult.AUTHENTICATED)
    rig.executor._auth_probe = probe
    await rig.executor.register_project_binding(rig.binding())
    started = await rig.executor.start(rig.identity)
    assert started.state == "RUNNING"
    assert probe.calls == [(AgentType.CODEX, HOST, REVISION, FINGERPRINT, 1000.0)]
    assert rig.control.calls == []
    assert rig.ports[0].starts == 1
    transport = rig.transports[0]
    assert transport._auth_lease is None
    assert not rig.scratch.exists()


@pytest.mark.anyio
async def test_resume_with_exact_owner_uses_the_awaiting_login_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    rig.control.result = WAWVendorProbeResult.UNAUTHENTICATED
    await rig.executor.register_project_binding(rig.binding())
    login = await rig.executor.start(rig.identity)
    assert login.state == "LOGIN_REQUIRED"
    assert rig.ports[0].starts == 0
    rig.control.result = WAWVendorProbeResult.AUTHENTICATED
    resumed = await rig.executor.resume_after_login(rig.identity)
    assert resumed.state == "RUNNING"
    assert resumed.process_state == "RUNNING"
    assert rig.ports[0].starts == 1
    assert rig.control.calls == [AgentType.CODEX, AgentType.CODEX]
    rig.assert_lease_released()


@pytest.mark.anyio
async def test_resume_without_authentication_keeps_cgroup_unconsumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    rig.control.result = WAWVendorProbeResult.UNAUTHENTICATED
    await rig.executor.register_project_binding(rig.binding())
    login = await rig.executor.start(rig.identity)
    assert login.state == "LOGIN_REQUIRED"
    with pytest.raises(RuntimeOperationError) as raised:
        await rig.executor.resume_after_login(rig.identity)
    assert raised.value.code == "WORKSPACE_AUTH_REQUIRED"
    assert rig.handles[0]._consumed is False
    assert rig.ports[0].starts == 0
    rig.assert_lease_released()
    rig.control.result = WAWVendorProbeResult.AUTHENTICATED
    resumed = await rig.executor.resume_after_login(rig.identity)
    assert resumed.state == "RUNNING"


def _bare_supervisor(state: SupervisorState, transport: Any) -> WAWSupervisor:
    supervisor = object.__new__(WAWSupervisor)
    supervisor._state = state
    supervisor._transport = transport
    supervisor._lock = threading.RLock()
    return supervisor


def test_fixed_auth_probe_transport_requires_login_required_state() -> None:
    supervisor = _bare_supervisor(SupervisorState.RUNNING, object())
    with pytest.raises(RuntimeOperationError) as raised:
        supervisor.fixed_auth_probe_transport()
    assert raised.value.code == "WAW_RESUME_INVALID"


def test_fixed_auth_probe_transport_requires_the_exact_fixed_transport() -> None:
    supervisor = _bare_supervisor(SupervisorState.LOGIN_REQUIRED, object())
    with pytest.raises(RuntimeOperationError) as raised:
        supervisor.fixed_auth_probe_transport()
    assert raised.value.code == "RUNTIME_UNAVAILABLE"


def test_borrow_precheck_allows_only_the_awaiting_login_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _LeaseRig(tmp_path, monkeypatch)
    transport, _port, _handle = rig._new_transport()
    transport._auth_borrow_precheck()
    transport._start_attempted = True
    with pytest.raises(RuntimeOperationError) as raised:
        transport._auth_borrow_precheck()
    assert raised.value.code == "WAW_AUTH_LEASE_BUSY"
    transport._inspector._login_required = True
    transport._auth_borrow_precheck()
    transport._closed = True
    with pytest.raises(RuntimeOperationError) as raised:
        transport._auth_borrow_precheck()
    assert raised.value.code == "WAW_AUTH_LEASE_BUSY"


class _FakeListenSocket:
    family = socket.AF_UNIX
    type = socket.SOCK_STREAM

    def getsockopt(self, _level: int, option: int) -> int:
        assert option == socket.SO_ACCEPTCONN
        return 1

    def get_inheritable(self) -> bool:
        return False


def _control_server(**overrides: Any) -> WAWControlServer:
    async def default_dispatch(_request: dict[str, Any]) -> dict[str, Any]:
        return {}

    dispatch = cast(Any, overrides.pop("dispatch", default_dispatch))
    kwargs: dict[str, Any] = {
        "expected_peer_uid": os.geteuid(),
        "expected_peer_gid": os.getegid(),
    }
    kwargs.update(overrides)
    return WAWControlServer(cast(Any, _FakeListenSocket()), dispatch, **kwargs)


def test_operation_timeout_overrides_default_to_empty() -> None:
    server = _control_server()
    assert server._operation_timeouts == {}


@pytest.mark.parametrize(
    "overrides",
    [
        [("workspace.workspace.start", 1.0)],
        {"": 1.0},
        {1: 1.0},
        {"workspace.workspace.start": True},
        {"workspace.workspace.start": "1.0"},
        {"workspace.workspace.start": 0.0},
        {"workspace.workspace.start": -1.0},
        {"workspace.workspace.start": 30.1},
        {"workspace.workspace.start": float("inf")},
        {"workspace.workspace.start": float("nan")},
    ],
)
def test_operation_timeout_overrides_reject_invalid_entries(overrides: Any) -> None:
    with pytest.raises(ValueError):
        _control_server(operation_timeout_overrides=overrides)


def test_operation_timeout_overrides_accept_int_and_boundary_floats() -> None:
    server = _control_server(
        operation_timeout_overrides={
            "workspace.workspace.start": 8,
            "workspace.workspace.stop": 30.0,
        }
    )
    assert server._operation_timeouts == {
        "workspace.workspace.start": 8.0,
        "workspace.workspace.stop": 30.0,
    }


def _control_request(action: str) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "wreq_" + "1" * 32,
        "action": action,
        "workspace_id": "aws_" + "2" * 32,
        "project_id": PROJECT,
        "agent_type": "codex",
        "generation": "1",
        "binding_revision": "1",
        "binding_digest": DIGEST,
        "runtime_host_installation_id": HOST,
        "runtime_host_installation_revision": "1",
    }


def _start_response(request_id: str) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": request_id,
        "status": "STARTED",
        "workspace_id": "aws_" + "2" * 32,
        "project_id": PROJECT,
        "agent_type": "codex",
        "generation": "1",
        "state": "RUNNING",
        "runtime_host_installation_id": HOST,
        "runtime_host_installation_revision": "1",
    }


class _MemoryWriter:
    def __init__(self) -> None:
        self.output = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.output.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    def get_extra_info(self, _name: str) -> None:
        return None


async def _serve_one(
    server: WAWControlServer, monkeypatch: pytest.MonkeyPatch, request: dict[str, object]
) -> bytes:
    pidfd, write_fd = os.pipe()
    credentials = control_subject._ControlPeerCredentials(
        os.getpid(), os.geteuid(), os.getegid(), pidfd
    )
    monkeypatch.setattr(server, "_peer_credentials", lambda _writer: credentials)
    reader = asyncio.StreamReader()
    reader.feed_data(json.dumps(request, separators=(",", ":")).encode() + b"\n")
    reader.feed_eof()
    writer = _MemoryWriter()
    try:
        await server._handle(reader, cast(Any, writer))
    finally:
        os.close(write_fd)
        await server.close()
    return bytes(writer.output)


@pytest.mark.anyio
async def test_start_action_receives_the_widened_dispatch_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def dispatch(request: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.5)
        return _start_response(cast(str, request["request_id"]))

    server = _control_server(
        dispatch=cast(Any, dispatch),
        timeout_seconds=0.2,
        cancellation_grace_seconds=0.05,
        operation_timeout_overrides={"workspace.workspace.start": 2.0},
    )
    raw = await _serve_one(server, monkeypatch, _control_request("workspace.workspace.start"))
    response = decode_control_response(
        raw, "workspace.workspace.start", expected_request_id="wreq_" + "1" * 32
    )
    assert response == _start_response("wreq_" + "1" * 32)


@pytest.mark.anyio
async def test_unlisted_action_keeps_the_default_dispatch_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def dispatch(request: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.5)
        return _start_response(cast(str, request["request_id"]))

    server = _control_server(
        dispatch=cast(Any, dispatch),
        timeout_seconds=0.2,
        cancellation_grace_seconds=0.05,
        operation_timeout_overrides={"workspace.workspace.start": 2.0},
    )
    raw = await _serve_one(server, monkeypatch, _control_request("workspace.workspace.status"))
    assert b'"error_code":"INTERNAL_BOUNDED"' in raw


class _FakeExecutor:
    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch="2")

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="STOPPED", process_state="STOPPED", runtime_epoch="2")

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch="2")

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return WAWLifecycleObservation(state="RUNNING", runtime_epoch="2")


def _epoch_store(tmp_path: Path) -> WAWRuntimeEpochStore:
    directory = tmp_path / "epoch"
    directory.mkdir()
    directory.chmod(0o700)
    return WAWRuntimeEpochStore(directory, expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_control_builder_defaults_start_envelope_and_prefers_explicit_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _epoch_store(tmp_path)
    assert store.bootstrap() == 1
    registry, _ = create_waw_lifecycle_registry_development_only(
        manifest=WAWRuntimeHostManifestDevelopmentOnly(
            runtime_host_installation_id=HOST,
            runtime_host_installation_revision="3",
            host_manifest_digest="a" * 64,
            project_root_manifest_digest="b" * 64,
            enrollment_epoch="4",
            enrollment_state="steady",
        ),
        epoch_store=store,
        executor=_FakeExecutor(),
        binding_digest_factory=lambda _request: "a" * 64,
    )
    sockets = WAWActivatedSockets(cast(Any, object()), cast(Any, object()))
    calls: list[dict[str, Any]] = []

    class FakeControlServer:
        def __init__(self, *_args: Any, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(bootstrap_subject, "WAWControlServer", FakeControlServer)
    build_waw_control_server(
        sockets=sockets,
        registry=registry,
        expected_peer_uid=1001,
        expected_peer_gid=1002,
    )
    assert calls[-1]["operation_timeout_overrides"] == {
        "workspace.workspace.start": WAW_START_OPERATION_TIMEOUT_SECONDS
    }
    explicit = {"workspace.workspace.stop": 3.0}
    build_waw_control_server(
        sockets=sockets,
        registry=registry,
        expected_peer_uid=1001,
        expected_peer_gid=1002,
        operation_timeout_overrides=explicit,
    )
    assert calls[-1]["operation_timeout_overrides"] is explicit
