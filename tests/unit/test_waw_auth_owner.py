from __future__ import annotations

import asyncio
import os
import platform
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_auth_lease import WAWAuthLeaseOwner, WAWSealedAuthLease
from agentbox_runtime.waw_auth_native_port import WAWNativeAuthProbePortFactory
from agentbox_runtime.waw_auth_owner import WAWProductionAuthOwner
from agentbox_runtime.waw_auth_probe import (
    WAWPublicAuthEvidence,
    WAWPublicAuthProbeError,
    WAWPublicAuthResult,
    WAWVendorPublicAuthBinding,
)
from agentbox_runtime.waw_fixed_transport import (
    LinuxCgroupControlHandle,
    NativeHelperProcessPort,
    WAWFixedTransport,
    WAWVerifiedExecutionAuthority,
)
from agentbox_runtime.waw_process_inspector import (
    FixedLaunchHandles,
    FixedLaunchRequest,
    FixedProcessIdentity,
    FixedStartState,
)
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_vendor_probe import (
    WAWIsolatedProbeCompletion,
    WAWProcessIsolationKind,
    WAWProcessIsolationPort,
    WAWVendorProbeEvidence,
    WAWVendorProbeFailure,
    WAWVendorProbeId,
    WAWVendorProbeParserId,
    WAWVendorProbeProfile,
    WAWVendorProbeResult,
    WAWVendorProbeRunner,
)

PROJECT = "prj_" + "1" * 32
WORKSPACE = workspace_id(PROJECT, AgentType.CODEX)
HOST = "wri_" + "2" * 32
DIGEST = "a" * 64
PROFILE_DIGEST = "b" * 64
WORKSPACE_HASH = "d" * 64
SCRATCH_NAME = "auth-probe-g1"
HOST_ID = "wri_" + "1" * 32
REVISION = "2"
FINGERPRINTS = {AgentType.CLAUDE: "a" * 64, AgentType.CODEX: "b" * 64}
VERSIONS = {AgentType.CLAUDE: "2.1.226", AgentType.CODEX: "0.146.1"}
PROBE_IDS = {
    AgentType.CLAUDE: WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1,
    AgentType.CODEX: WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
}
PARSER_IDS = {
    AgentType.CLAUDE: WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
    AgentType.CODEX: WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
}


def fixed_identity(
    workspace: str = WORKSPACE, workspace_hash: str = WORKSPACE_HASH
) -> FixedProcessIdentity:
    marker = managed_marker(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        project_id=PROJECT,
        agent_type=AgentType.CODEX,
        workspace_id_value=workspace,
        generation=1,
        binding_revision=1,
        binding_digest=DIGEST,
    )
    return FixedProcessIdentity(
        workspace,
        PROJECT,
        AgentType.CODEX,
        1,
        workspace_hash,
        marker,
        PROFILE_DIGEST,
        HOST,
        "1",
        "2",
    )


def _authority(
    monkeypatch: pytest.MonkeyPatch, *, authorized: bool = True
) -> WAWVerifiedExecutionAuthority:
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority, "authorizes", lambda _self, _identity: authorized
    )
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority,
        "runtime_host_installation_id",
        property(lambda _self: HOST_ID),
    )
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority,
        "runtime_host_installation_revision",
        property(lambda _self: REVISION),
    )
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority,
        "vendor_executable_fingerprint",
        lambda _self, agent_type: FINGERPRINTS[agent_type],
    )
    return object.__new__(WAWVerifiedExecutionAuthority)


def _bindings(**overrides: str) -> dict[AgentType, WAWVendorPublicAuthBinding]:
    return {
        agent_type: WAWVendorPublicAuthBinding(
            agent_type,
            overrides.get("host", HOST_ID),
            overrides.get("revision", REVISION),
            overrides.get("fingerprint", FINGERPRINTS[agent_type]),
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            VERSIONS[agent_type],
        )
        for agent_type in AgentType
    }


class _RunnerControl:
    def __init__(self) -> None:
        self.calls: list[AgentType] = []
        self.behavior = "authenticated"
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.side_effect: Any = None


def _runner(monkeypatch: pytest.MonkeyPatch, control: _RunnerControl) -> WAWVendorProbeRunner:
    async def fake_probe(
        _self: WAWVendorProbeRunner, *, agent_type: AgentType, observed_vendor_version: str
    ) -> WAWVendorProbeEvidence:
        control.calls.append(agent_type)
        control.entered.set()
        if control.side_effect is not None:
            control.side_effect()
        if control.behavior == "raise":
            raise RuntimeError("probe boom")
        if control.behavior == "cancel":
            raise asyncio.CancelledError
        if control.behavior == "block":
            await control.release.wait()
        result = (
            WAWVendorProbeResult.UNAUTHENTICATED
            if control.behavior == "unauthenticated"
            else WAWVendorProbeResult.AUTHENTICATED
        )
        return WAWVendorProbeEvidence(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            agent_type,
            observed_vendor_version,
            PROBE_IDS[agent_type],
            PARSER_IDS[agent_type],
            result,
            WAWVendorProbeFailure.NONE,
            0 if result is WAWVendorProbeResult.AUTHENTICATED else 1,
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


def _transport(
    identity: FixedProcessIdentity,
    authority: WAWVerifiedExecutionAuthority,
    handle: LinuxCgroupControlHandle,
) -> WAWFixedTransport:
    transport = object.__new__(WAWFixedTransport)
    transport._identity = identity
    transport._production = True
    transport._handles = cast(Any, SimpleNamespace(cgroup=handle))
    transport._port = SimpleNamespace(execution_authority=authority)
    transport._start_attempted = False
    transport._closed = False
    transport._aborted_unstarted = False
    transport._auth_lease = None
    transport._auth_poisoned = False
    return transport


class _Rig:
    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, authorized: bool = True
    ) -> None:
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        self.authority = _authority(monkeypatch, authorized=authorized)
        self.control = _RunnerControl()
        self.runner = _runner(monkeypatch, self.control)
        self.now = [1000.0]
        root = tmp_path / "scratch"
        root.mkdir(parents=True)
        root.chmod(0o700)
        self.workspace = root / WORKSPACE_HASH
        self.workspace.mkdir()
        self.workspace.chmod(0o700)
        scratch_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        self.lease_owner = WAWAuthLeaseOwner(self.authority, scratch_root=scratch_fd)
        os.close(scratch_fd)
        self.identity = fixed_identity()
        self.cgroup_state = {"populated": 0, "frozen": 0}
        self.handle = _cgroup_handle(
            tmp_path, monkeypatch, self.identity, self.authority, self.cgroup_state
        )
        self.transport = _transport(self.identity, self.authority, self.handle)
        self.owner = WAWProductionAuthOwner(
            self.authority,
            runner=self.runner,
            bindings=_bindings(),
            lease_owner=self.lease_owner,
            clock=lambda: self.now[0],
            max_age_seconds=30.0,
        )

    @property
    def scratch(self) -> Path:
        return self.workspace / SCRATCH_NAME

    def probe_kwargs(self) -> dict[str, Any]:
        return {
            "agent_type": AgentType.CODEX,
            "runtime_host_installation_id": HOST_ID,
            "runtime_host_installation_revision": REVISION,
            "executable_fingerprint": FINGERPRINTS[AgentType.CODEX],
            "checked_at_monotonic": self.now[0],
        }


def _evidence(
    agent_type: AgentType, result: WAWPublicAuthResult, checked_at: float
) -> WAWPublicAuthEvidence:
    return WAWPublicAuthEvidence(
        agent_type, HOST_ID, REVISION, FINGERPRINTS[agent_type], checked_at, result
    )


def _error_code(exc: BaseException) -> str:
    assert isinstance(exc, RuntimeOperationError)
    return exc.code


def test_constructor_rejects_type_and_authority_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        WAWProductionAuthOwner(
            cast(Any, object()),
            runner=rig.runner,
            bindings=_bindings(),
            lease_owner=rig.lease_owner,
            clock=lambda: 0.0,
        )
    with pytest.raises(TypeError):
        WAWProductionAuthOwner(
            rig.authority,
            runner=cast(Any, object()),
            bindings=_bindings(),
            lease_owner=rig.lease_owner,
            clock=lambda: 0.0,
        )
    with pytest.raises(TypeError):
        WAWProductionAuthOwner(
            rig.authority,
            runner=rig.runner,
            bindings=_bindings(),
            lease_owner=cast(Any, object()),
            clock=lambda: 0.0,
        )
    foreign = object.__new__(WAWVerifiedExecutionAuthority)
    foreign_fd = os.open(tmp_path / "scratch", os.O_RDONLY | os.O_DIRECTORY)
    foreign_lease_owner = WAWAuthLeaseOwner(foreign, scratch_root=foreign_fd)
    os.close(foreign_fd)
    with pytest.raises(WAWPublicAuthProbeError, match="not bound"):
        WAWProductionAuthOwner(
            rig.authority,
            runner=rig.runner,
            bindings=_bindings(),
            lease_owner=foreign_lease_owner,
            clock=lambda: 0.0,
        )


def test_constructor_rejects_binding_drift_and_bad_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    with pytest.raises(WAWPublicAuthProbeError, match="does not match"):
        WAWProductionAuthOwner(
            rig.authority,
            runner=rig.runner,
            bindings=_bindings(fingerprint="f" * 64),
            lease_owner=rig.lease_owner,
            clock=lambda: 0.0,
        )
    with pytest.raises(WAWPublicAuthProbeError, match="does not match"):
        WAWProductionAuthOwner(
            rig.authority,
            runner=rig.runner,
            bindings=_bindings(host="wri_" + "9" * 32),
            lease_owner=rig.lease_owner,
            clock=lambda: 0.0,
        )
    incomplete = {AgentType.CODEX: _bindings()[AgentType.CODEX]}
    with pytest.raises(WAWPublicAuthProbeError):
        WAWProductionAuthOwner(
            rig.authority,
            runner=rig.runner,
            bindings=cast(Any, incomplete),
            lease_owner=rig.lease_owner,
            clock=lambda: 0.0,
        )
    samples = iter((10.0, 5.0))
    with pytest.raises(WAWPublicAuthProbeError, match="monotonic"):
        WAWProductionAuthOwner(
            rig.authority,
            runner=rig.runner,
            bindings=_bindings(),
            lease_owner=rig.lease_owner,
            clock=lambda: next(samples),
        )
    closed_fd = os.open(tmp_path / "scratch", os.O_RDONLY | os.O_DIRECTORY)
    closed_lease_owner = WAWAuthLeaseOwner(rig.authority, scratch_root=closed_fd)
    os.close(closed_fd)
    closed_lease_owner.close()
    with pytest.raises(WAWPublicAuthProbeError, match="terminal"):
        WAWProductionAuthOwner(
            rig.authority,
            runner=rig.runner,
            bindings=_bindings(),
            lease_owner=closed_lease_owner,
            clock=lambda: 0.0,
        )


def test_authenticated_gate_cache_outcomes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    identity = rig.identity
    assert rig.owner.authenticated(identity) is False
    rig.owner._cache.record(_evidence(AgentType.CODEX, WAWPublicAuthResult.AUTHENTICATED, 1000.0))
    assert rig.owner.authenticated(identity) is True
    rig.now[0] = 1031.0
    assert rig.owner.authenticated(identity) is False
    rig.now[0] = 1000.0
    rig.owner._cache.clear()
    rig.owner._cache.record(_evidence(AgentType.CODEX, WAWPublicAuthResult.UNAUTHENTICATED, 1000.0))
    assert rig.owner.authenticated(identity) is False
    assert rig.owner.authenticated(cast(Any, object())) is False


def test_authenticated_gate_identity_drift_and_poison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drifted = _Rig(tmp_path, monkeypatch, authorized=False)
    drifted.owner._cache.record(
        _evidence(AgentType.CODEX, WAWPublicAuthResult.AUTHENTICATED, 1000.0)
    )
    assert drifted.owner.authenticated(drifted.identity) is False
    rig = _Rig(tmp_path / "poison", monkeypatch)
    rig.owner._cache.record(_evidence(AgentType.CODEX, WAWPublicAuthResult.AUTHENTICATED, 1000.0))
    rig.owner._poison()
    assert rig.owner.poisoned
    assert rig.lease_owner.poisoned
    assert rig.owner.authenticated(rig.identity) is False


@pytest.mark.anyio
async def test_probe_is_always_live_and_echoes_checked_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.owner._cache.record(_evidence(AgentType.CODEX, WAWPublicAuthResult.AUTHENTICATED, 1000.0))
    evidence = await rig.owner.probe(
        agent_type=AgentType.CODEX,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=REVISION,
        executable_fingerprint=FINGERPRINTS[AgentType.CODEX],
        checked_at_monotonic=1005.0,
    )
    assert rig.control.calls == [AgentType.CODEX]
    assert evidence.checked_at_monotonic == 1005.0
    assert evidence.result is WAWPublicAuthResult.AUTHENTICATED
    rig.owner._poison()
    with pytest.raises(RuntimeOperationError) as poisoned:
        await rig.owner.probe(
            agent_type=AgentType.CODEX,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision=REVISION,
            executable_fingerprint=FINGERPRINTS[AgentType.CODEX],
            checked_at_monotonic=1006.0,
        )
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"


@pytest.mark.anyio
async def test_probe_with_lease_live_miss_echoes_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    evidence = await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
    assert rig.control.calls == [AgentType.CODEX]
    assert evidence.checked_at_monotonic == 1000.0
    assert evidence.result is WAWPublicAuthResult.AUTHENTICATED
    assert rig.transport._auth_lease is None
    assert not rig.handle.auth_borrowed
    assert not rig.scratch.exists()
    assert rig.owner.authenticated(rig.identity) is True


@pytest.mark.anyio
async def test_probe_with_lease_cache_hit_releases_unused_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.owner._cache.record(_evidence(AgentType.CODEX, WAWPublicAuthResult.AUTHENTICATED, 1000.0))
    evidence = await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
    assert rig.control.calls == []
    assert evidence.checked_at_monotonic == 1000.0
    assert rig.transport._auth_lease is None
    assert not rig.handle.auth_borrowed
    assert not rig.scratch.exists()


@pytest.mark.anyio
async def test_probe_with_lease_serializes_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.control.behavior = "block"
    first = asyncio.create_task(rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs()))
    await asyncio.wait_for(rig.control.entered.wait(), timeout=5.0)
    other_handle = _cgroup_handle(
        tmp_path, monkeypatch, rig.identity, rig.authority, rig.cgroup_state
    )
    other_transport = _transport(rig.identity, rig.authority, other_handle)
    with pytest.raises(RuntimeOperationError) as busy:
        await rig.owner.probe_with_lease(other_transport, **rig.probe_kwargs())
    assert _error_code(busy.value) == "WAW_AUTH_PROBE_BUSY"
    rig.control.release.set()
    evidence = await first
    assert evidence.result is WAWPublicAuthResult.AUTHENTICATED
    assert rig.transport._auth_lease is None
    assert other_transport._auth_lease is None


@pytest.mark.anyio
async def test_probe_with_lease_cancellation_releases_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.control.behavior = "cancel"
    with pytest.raises(asyncio.CancelledError):
        await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
    assert rig.transport._auth_lease is None
    assert not rig.handle.auth_borrowed
    assert not rig.scratch.exists()
    assert not rig.owner.poisoned
    assert not rig.lease_owner.poisoned
    assert rig.owner.authenticated(rig.identity) is False


@pytest.mark.anyio
async def test_probe_with_lease_runner_error_releases_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.control.behavior = "raise"
    with pytest.raises(RuntimeError, match="probe boom"):
        await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
    assert rig.transport._auth_lease is None
    assert not rig.handle.auth_borrowed
    assert not rig.scratch.exists()
    assert not rig.lease_owner.poisoned


@pytest.mark.anyio
async def test_probe_with_lease_release_failure_poisons_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.control.side_effect = lambda: rig.cgroup_state.__setitem__("populated", 1)
    with pytest.raises(RuntimeOperationError) as poisoned:
        await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"
    assert rig.lease_owner.poisoned
    assert rig.transport._auth_poisoned
    assert rig.owner.authenticated(rig.identity) is False
    with pytest.raises(RuntimeOperationError) as again:
        await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
    assert _error_code(again.value) == "WAW_AUTH_LEASE_POISONED"


@pytest.mark.anyio
async def test_probe_with_lease_rejects_request_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    drifted_fingerprint = rig.probe_kwargs() | {"executable_fingerprint": "f" * 64}
    with pytest.raises(WAWPublicAuthProbeError, match="execution authority"):
        await rig.owner.probe_with_lease(rig.transport, **drifted_fingerprint)
    drifted_host = rig.probe_kwargs() | {"runtime_host_installation_id": "wri_" + "9" * 32}
    with pytest.raises(WAWPublicAuthProbeError, match="execution authority"):
        await rig.owner.probe_with_lease(rig.transport, **drifted_host)
    wrong_agent = rig.probe_kwargs() | {
        "agent_type": AgentType.CLAUDE,
        "executable_fingerprint": FINGERPRINTS[AgentType.CLAUDE],
    }
    with pytest.raises(WAWPublicAuthProbeError, match="transport identity"):
        await rig.owner.probe_with_lease(rig.transport, **wrong_agent)
    malformed = rig.probe_kwargs() | {"executable_fingerprint": "not-a-digest"}
    with pytest.raises(WAWPublicAuthProbeError):
        await rig.owner.probe_with_lease(rig.transport, **malformed)
    assert rig.transport._auth_lease is None
    assert rig.control.calls == []


def test_production_port_factory_requires_sealed_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    object.__setattr__(authority, "_manifest", cast(Any, object()))
    with pytest.raises(TypeError):
        NativeHelperProcessPort.from_verified_execution_authority(
            authority,
            (),
            tmux_socket_directory=0,
            tmux_config=0,
            authenticated=cast(Any, lambda _identity: True),  # type: ignore[call-arg]
        )
    with pytest.raises(TypeError, match="sealed production auth owner"):
        NativeHelperProcessPort.from_verified_execution_authority(
            authority,
            (),
            tmux_socket_directory=0,
            tmux_config=0,
            auth_owner=cast(Any, object()),
        )
    mismatched = object.__new__(WAWProductionAuthOwner)
    mismatched._authority = object.__new__(WAWVerifiedExecutionAuthority)
    with pytest.raises(RuntimeOperationError, match="not bound"):
        NativeHelperProcessPort.from_verified_execution_authority(
            authority,
            (),
            tmux_socket_directory=0,
            tmux_config=0,
            auth_owner=mismatched,
        )
    bound = object.__new__(WAWProductionAuthOwner)
    bound._authority = authority
    with pytest.raises(RuntimeOperationError, match="Exact-six"):
        NativeHelperProcessPort.from_verified_execution_authority(
            authority,
            (),
            tmux_socket_directory=0,
            tmux_config=0,
            auth_owner=bound,
        )


def test_production_port_start_gates_on_auth_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    request = FixedLaunchRequest(
        rig.identity,
        FixedLaunchHandles(*(object() for _ in range(8))),
        PtyGeometry(80, 24),
    )
    dev_calls: list[FixedProcessIdentity] = []

    def dev_callback(identity: FixedProcessIdentity) -> bool:
        dev_calls.append(identity)
        return True

    port = object.__new__(NativeHelperProcessPort)
    port._closed = False
    port._auth_owner = rig.owner
    port._authenticated = dev_callback
    proof = port.start(request)
    assert proof.state is FixedStartState.LOGIN_REQUIRED
    assert dev_calls == []

    rig.owner._cache.record(_evidence(AgentType.CODEX, WAWPublicAuthResult.AUTHENTICATED, 1000.0))
    assert rig.owner.authenticated(rig.identity) is True

    development = object.__new__(NativeHelperProcessPort)
    development._closed = False
    development._auth_owner = None
    development._authenticated = lambda _identity: False
    dev_proof = development.start(request)
    assert dev_proof.state is FixedStartState.LOGIN_REQUIRED


def test_production_port_factory_rejects_poisoned_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    object.__setattr__(authority, "_manifest", cast(Any, object()))
    poisoned = object.__new__(WAWProductionAuthOwner)
    poisoned._authority = authority
    poisoned._poisoned = True
    with pytest.raises(RuntimeOperationError, match="poisoned"):
        NativeHelperProcessPort.from_verified_execution_authority(
            authority,
            (),
            tmux_socket_directory=0,
            tmux_config=0,
            auth_owner=poisoned,
        )


def test_authenticated_is_false_when_lease_owner_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.owner._cache.record(
        _evidence(AgentType.CODEX, WAWPublicAuthResult.AUTHENTICATED, rig.now[0])
    )
    assert rig.owner.authenticated(rig.identity) is True
    rig.lease_owner.close()
    assert rig.owner.authenticated(rig.identity) is False


def _native_profiles() -> dict[AgentType, WAWVendorProbeProfile]:
    return {
        agent_type: WAWVendorProbeProfile(
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            agent_type,
            VERSIONS[agent_type],
            PROBE_IDS[agent_type],
            PARSER_IDS[agent_type],
            Path("/usr/bin/fake-vendor"),
            Path("/tmp"),
            (("PATH", "/usr/bin:/bin"),),
            codex_unauthenticated_output_sha256=(
                "0" * 64 if agent_type is AgentType.CODEX else None
            ),
        )
        for agent_type in AgentType
    }


class _FakeNativePort(WAWProcessIsolationPort):
    """Issued-port stand-in; the monkeypatched runner never executes it."""

    def __init__(self) -> None:
        super().__init__(
            isolation_kind=WAWProcessIsolationKind.PREBIRTH_CGROUP,
            production_qualified=True,
        )
        self.closed = 0

    async def execute(self, *_args: Any, **_kwargs: Any) -> WAWIsolatedProbeCompletion:
        raise AssertionError("bind tests never execute the issued native port")

    def close(self) -> None:
        self.closed += 1


def _fake_factory(authority: WAWVerifiedExecutionAuthority) -> WAWNativeAuthProbePortFactory:
    factory = object.__new__(WAWNativeAuthProbePortFactory)
    factory._authority = authority
    return factory


@pytest.mark.anyio
async def test_bind_native_probe_path_binds_once_and_enables_native_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    factory = _fake_factory(rig.authority)
    port = _FakeNativePort()
    issued: list[WAWSealedAuthLease] = []

    def fake_port_for_lease(
        _factory: WAWNativeAuthProbePortFactory, lease: WAWSealedAuthLease
    ) -> _FakeNativePort:
        issued.append(lease)
        return port

    monkeypatch.setattr(WAWNativeAuthProbePortFactory, "port_for_lease", fake_port_for_lease)
    profiles = _native_profiles()
    rig.owner.bind_native_probe_path(factory, profiles)
    assert rig.owner._native_port_factory is factory
    assert rig.owner._profiles == profiles

    evidence = await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())

    assert len(issued) == 1
    assert port.closed == 1
    assert rig.control.calls == [AgentType.CODEX]
    assert evidence.result is WAWPublicAuthResult.AUTHENTICATED
    assert evidence.checked_at_monotonic == 1000.0
    assert rig.transport._auth_lease is None
    assert not rig.handle.auth_borrowed
    assert rig.owner.authenticated(rig.identity) is True


def test_bind_native_probe_path_rejects_second_bind_and_constructor_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    factory = _fake_factory(rig.authority)
    profiles = _native_profiles()
    rig.owner.bind_native_probe_path(factory, profiles)
    with pytest.raises(RuntimeOperationError) as busy:
        rig.owner.bind_native_probe_path(factory, profiles)
    assert _error_code(busy.value) == "WAW_AUTH_PROBE_BUSY"

    given = WAWProductionAuthOwner(
        rig.authority,
        runner=rig.runner,
        bindings=_bindings(),
        lease_owner=rig.lease_owner,
        clock=lambda: 0.0,
        native_port_factory=factory,
        profiles=profiles,
    )
    with pytest.raises(RuntimeOperationError) as given_busy:
        given.bind_native_probe_path(factory, profiles)
    assert _error_code(given_busy.value) == "WAW_AUTH_PROBE_BUSY"


def test_bind_native_probe_path_rejects_poisoned_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.owner._poison()
    with pytest.raises(RuntimeOperationError) as poisoned:
        rig.owner.bind_native_probe_path(_fake_factory(rig.authority), _native_profiles())
    assert _error_code(poisoned.value) == "WAW_AUTH_LEASE_POISONED"


def test_bind_native_probe_path_replays_constructor_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    profiles = _native_profiles()
    with pytest.raises(TypeError):
        rig.owner.bind_native_probe_path(cast(Any, object()), profiles)
    foreign = _fake_factory(object.__new__(WAWVerifiedExecutionAuthority))
    with pytest.raises(WAWPublicAuthProbeError, match="not bound"):
        rig.owner.bind_native_probe_path(foreign, profiles)
    factory = _fake_factory(rig.authority)
    with pytest.raises(TypeError):
        rig.owner.bind_native_probe_path(factory, cast(Any, object()))
    incomplete = {AgentType.CODEX: profiles[AgentType.CODEX]}
    with pytest.raises(WAWPublicAuthProbeError, match="per AgentType"):
        rig.owner.bind_native_probe_path(factory, cast(Any, incomplete))
    mismatched = dict(profiles)
    mismatched[AgentType.CLAUDE] = profiles[AgentType.CODEX]
    with pytest.raises(WAWPublicAuthProbeError, match="does not match"):
        rig.owner.bind_native_probe_path(factory, mismatched)
    # Every rejection left the owner unbound; a valid bind still succeeds.
    rig.owner.bind_native_probe_path(factory, profiles)
    assert rig.owner._native_port_factory is factory
    assert rig.owner._profiles == profiles


def test_cache_property_exposes_the_internal_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    assert rig.owner.cache is rig.owner._cache
