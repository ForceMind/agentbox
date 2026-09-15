from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import os
import platform
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_runtime import waw_auth_native_port as subject
from agentbox_runtime import waw_fixed_transport as fixed_transport_subject
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_auth_lease import WAWAuthLeaseOwner, WAWSealedAuthLease
from agentbox_runtime.waw_auth_native_port import (
    WAWNativeAuthProbePort,
    WAWNativeAuthProbePortFactory,
    receive_auth_placed,
)
from agentbox_runtime.waw_auth_owner import WAWProductionAuthOwner
from agentbox_runtime.waw_auth_probe import (
    WAWPublicAuthEvidence,
    WAWPublicAuthProbeError,
    WAWPublicAuthResult,
    WAWVendorPublicAuthBinding,
)
from agentbox_runtime.waw_executable import WAWExecutableKind
from agentbox_runtime.waw_fixed_transport import (
    LinuxCgroupControlHandle,
    NativeHelperHandles,
    NativeHelperProcessPort,
    WAWFixedTransport,
    WAWVerifiedExecutionAuthority,
)
from agentbox_runtime.waw_process_inspector import FixedProcessIdentity
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1
from agentbox_runtime.waw_vendor_probe import (
    WAWIsolatedProbeCompletion,
    WAWProcessIsolationKind,
    WAWVendorProbeFailure,
    WAWVendorProbeId,
    WAWVendorProbeParserId,
    WAWVendorProbeProfile,
    WAWVendorProbeRunner,
    waw_vendor_probe_output_digest,
)

PROJECT = "prj_" + "1" * 32
HOST = "wri_" + "2" * 32
DIGEST = "a" * 64
PROFILE_DIGEST = "b" * 64
WORKSPACE_HASH = "d" * 64
HOST_ID = "wri_" + "1" * 32
REVISION = "2"
VERSIONS = {AgentType.CLAUDE: "2.1.226", AgentType.CODEX: "0.146.1"}
PROBE_IDS = {
    AgentType.CLAUDE: WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1,
    AgentType.CODEX: WAWVendorProbeId.CODEX_LOGIN_STATUS_V1,
}
PARSER_IDS = {
    AgentType.CLAUDE: WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
    AgentType.CODEX: WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
}
ARGUMENTS = {AgentType.CLAUDE: ("auth", "status"), AgentType.CODEX: ("login", "status")}

# Real protocol peer for the fixed helper ABI: reads the 160-byte AWP1 record
# from fd3, waits for the sealed write side, answers AWRP, then plays the
# scripted stdout/stderr/exit behaviour.  It performs no namespace or cgroup
# work; that remains native-host evidence.
_HELPER_SCRIPT = r"""
import array
import os
import signal
import socket
import sys
import time


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


mode = os.environ.get("FAKE_HELPER_MODE", "happy")
dump_path = os.environ.get("FAKE_HELPER_RECORD", "")
started_path = os.environ.get("FAKE_HELPER_STARTED", "")
exit_code = int(os.environ.get("FAKE_HELPER_EXIT", "0"))
out = bytes.fromhex(os.environ.get("FAKE_HELPER_STDOUT", ""))
err = bytes.fromhex(os.environ.get("FAKE_HELPER_STDERR", ""))

control = socket.socket(fileno=3)
record, _ancillary, _flags, _address = control.recvmsg(160, socket.CMSG_SPACE(4))
if dump_path:
    with open(dump_path, "wb") as handle:
        handle.write(record)

if mode == "no-awrp":
    sys.exit(0)
if mode == "bad-magic":
    control.sendall(b"BXRP\x01\x01\x00\x00")
    sys.exit(0)
if mode == "oversize":
    control.sendall(b"AWRP\x01\x01\x00\x00X")
    sys.exit(0)
if mode == "ancillary":
    control.sendmsg(
        [b"AWRP\x01\x01\x00\x00"],
        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [0]))],
    )
    sys.exit(0)
if mode == "silent-hang":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1)
control.sendall(b"AWRP\x01\x01\x00\x00")
if started_path:
    with open(started_path, "wb") as handle:
        handle.write(b"1")
if mode == "hang":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1)
if mode == "escaped-writer":
    if os.fork() == 0:
        time.sleep(1.5)
        os._exit(0)
    sys.exit(0)
if out:
    _write_all(1, out)
if err:
    _write_all(2, err)
sys.exit(exit_code)
"""


def fixed_identity(agent_type: AgentType = AgentType.CODEX) -> FixedProcessIdentity:
    workspace = workspace_id(PROJECT, agent_type)
    marker = managed_marker(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        project_id=PROJECT,
        agent_type=agent_type,
        workspace_id_value=workspace,
        generation=1,
        binding_revision=1,
        binding_digest=DIGEST,
    )
    return FixedProcessIdentity(
        workspace,
        PROJECT,
        agent_type,
        1,
        WORKSPACE_HASH,
        marker,
        PROFILE_DIGEST,
        HOST,
        "1",
        "2",
    )


def _profile(agent_type: AgentType, *, codex_digest: str = "0" * 64) -> WAWVendorProbeProfile:
    return WAWVendorProbeProfile(
        str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
        agent_type,
        VERSIONS[agent_type],
        PROBE_IDS[agent_type],
        PARSER_IDS[agent_type],
        Path("/usr/bin/fake-vendor"),
        Path("/tmp"),
        (("PATH", "/usr/bin:/bin"),),
        codex_unauthenticated_output_sha256=(
            codex_digest if agent_type is AgentType.CODEX else None
        ),
    )


def _close_fd_quiet(descriptor: int) -> None:
    with contextlib.suppress(OSError):
        os.close(descriptor)


def _directory_fd(path: Path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)


def _executable_fd(tmp_path: Path, name: str, content: bytes) -> int:
    path = tmp_path / name
    path.write_bytes(content)
    path.chmod(0o755)
    return os.open(path, os.O_RDONLY | os.O_CLOEXEC)


def _write_helper_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_waw_auth_helper.py"
    script.write_text(_HELPER_SCRIPT, encoding="utf-8")
    return script


def _patch_platform_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """macOS has no AF_UNIX SOCK_SEQPACKET; substitute packet-real datagrams.

    The Linux production path is unchanged: this only swaps the host socket
    kind so the exact same AWP1/AWRP byte contract runs in unit tests.  The
    seqpacket role check keeps rejecting stream sockets and accepts the
    datagram stand-in.
    """

    if platform.system() == "Linux":
        return
    real_check = fixed_transport_subject._is_unix_seqpacket

    def datagram_aware(connection: object) -> bool:
        getsockopt = getattr(connection, "getsockopt", None)
        if callable(getsockopt):
            try:
                if getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_DGRAM:
                    return True
            except OSError:
                return False
        return real_check(connection)

    monkeypatch.setattr(subject, "_is_unix_seqpacket", datagram_aware)
    monkeypatch.setattr(
        subject,
        "_control_socketpair",
        lambda: socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM),
    )


def _control_pair() -> tuple[socket.socket, socket.socket]:
    kind = socket.SOCK_SEQPACKET if platform.system() == "Linux" else socket.SOCK_DGRAM
    return socket.socketpair(socket.AF_UNIX, kind)


def _sha256_fd_check(descriptor: int, expected: str, *, max_bytes: int = 64 * 1024) -> None:
    """Test stand-in for the host-qualified digest read-back (no uid-0 gate)."""

    del max_bytes
    digest = hashlib.sha256()
    offset = 0
    while True:
        block = os.pread(descriptor, 8192, offset)
        if not block:
            break
        offset += len(block)
        digest.update(block)
    if not hmac.compare_digest(digest.hexdigest(), expected):
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "held descriptor does not match the execution authority",
            category="unavailable",
        )


def _authority(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authorized: bool = True,
    fingerprints: dict[AgentType, str] | None = None,
    manifest: object | None = None,
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
    if fingerprints is not None:
        monkeypatch.setattr(
            WAWVerifiedExecutionAuthority,
            "vendor_executable_fingerprint",
            lambda _self, agent_type: fingerprints[agent_type],
        )
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    if manifest is not None:
        object.__setattr__(authority, "_manifest", cast(Any, manifest))
    return authority


class _CgroupFake:
    def __init__(self) -> None:
        self.populated_value = 0
        self.kill_calls = 0

    def populated(self) -> int:
        return self.populated_value

    def kill(self) -> None:
        self.kill_calls += 1


def _fake_lease(
    identity: FixedProcessIdentity,
    cgroup: _CgroupFake,
    cgroup_dir: Path,
    scratch_dir: Path,
    home_dir: Path,
    policy_dir: Path,
) -> WAWSealedAuthLease:
    lease = object.__new__(WAWSealedAuthLease)
    lease._identity = identity
    lease._state = "OWNED"
    lease._lock = threading.RLock()
    lease._cgroup_fd = _directory_fd(cgroup_dir)
    lease._scratch_fd = _directory_fd(scratch_dir)
    lease._cgroup = cast(Any, cgroup)
    lease._transport = cast(
        Any,
        SimpleNamespace(
            _handles=SimpleNamespace(
                selected_home_directory=_directory_fd(home_dir),
                policy_directory=_directory_fd(policy_dir),
            )
        ),
    )
    return lease


def _close_fake_lease(lease: WAWSealedAuthLease) -> None:
    _close_fd_quiet(lease._cgroup_fd)
    _close_fd_quiet(lease._scratch_fd)
    handles = cast(Any, cast(Any, lease._transport)._handles)
    _close_fd_quiet(cast(int, handles.selected_home_directory))
    _close_fd_quiet(cast(int, handles.policy_directory))


class _SpawnRig:
    """Patch ``subject._spawn`` with a real posix_spawn of the fake helper."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, script: Path) -> None:
        self.script = script
        self.argv: tuple[str, ...] | None = None
        self.environment: dict[str, str] | None = None
        self.descriptor_map: tuple[tuple[int, int], ...] | None = None
        self.pid: int | None = None
        self.mode = "happy"
        self.exit_code = 0
        self.stdout = b""
        self.stderr = b""
        self.record_dump: Path | None = None
        self.started: Path | None = None
        monkeypatch.setattr(subject, "_spawn", self.spawn)

    def spawn(
        self,
        executable: int,
        argv: tuple[str, ...],
        environment: dict[str, str],
        descriptor_map: tuple[tuple[int, int], ...],
    ) -> int:
        del executable
        self.argv = argv
        self.environment = environment
        self.descriptor_map = descriptor_map
        actions = [
            (os.POSIX_SPAWN_DUP2, source, destination) for source, destination in descriptor_map
        ]
        helper_environment = {
            "PATH": "/usr/bin:/bin",
            "FAKE_HELPER_MODE": self.mode,
            "FAKE_HELPER_EXIT": str(self.exit_code),
            "FAKE_HELPER_STDOUT": self.stdout.hex(),
            "FAKE_HELPER_STDERR": self.stderr.hex(),
        }
        if self.record_dump is not None:
            helper_environment["FAKE_HELPER_RECORD"] = str(self.record_dump)
        if self.started is not None:
            helper_environment["FAKE_HELPER_STARTED"] = str(self.started)
        self.pid = os.posix_spawn(
            sys.executable,
            [sys.executable, str(self.script)],
            helper_environment,
            file_actions=actions,
        )
        return self.pid


class _ExecuteRig:
    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        agent_type: AgentType = AgentType.CODEX,
    ) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        _patch_platform_sockets(monkeypatch)
        self.identity = fixed_identity(agent_type)
        self.cgroup = _CgroupFake()
        cgroup_dir = tmp_path / "cgroup"
        scratch_dir = tmp_path / "scratch"
        home_dir = tmp_path / "home"
        policy_dir = tmp_path / "policy"
        for directory in (cgroup_dir, scratch_dir, home_dir, policy_dir):
            directory.mkdir()
        self.lease = _fake_lease(
            self.identity, self.cgroup, cgroup_dir, scratch_dir, home_dir, policy_dir
        )
        self.script = _write_helper_script(tmp_path)
        self.spawn = _SpawnRig(monkeypatch, self.script)
        helper_fd = _executable_fd(tmp_path, "pane-bootstrap-held", b"helper-held-bytes")
        vendor_fd = _executable_fd(tmp_path, "vendor-held", b"vendor-held-bytes")
        home_fd = _directory_fd(home_dir)
        policy_fd = _directory_fd(policy_dir)
        try:
            self.port = WAWNativeAuthProbePort(
                subject._AUTH_NATIVE_PORT_TOKEN,
                lease=self.lease,
                identity=self.identity,
                helper_executable=helper_fd,
                vendor_executable=vendor_fd,
                home_directory=home_fd,
                policy_directory=policy_fd,
            )
        finally:
            for descriptor in (helper_fd, vendor_fd, home_fd, policy_fd):
                _close_fd_quiet(descriptor)
        self.profile = _profile(agent_type)

    @property
    def arguments(self) -> tuple[str, ...]:
        return ARGUMENTS[self.identity.agent_type]

    async def execute(
        self,
        *,
        timeout_seconds: float = 5.0,
        output_limit: int = 4096,
        terminate_grace_seconds: float = 0.25,
    ) -> WAWIsolatedProbeCompletion:
        return await self.port.execute(
            self.profile,
            self.arguments,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            terminate_grace_seconds=terminate_grace_seconds,
        )

    def close(self) -> None:
        self.port.close()
        _close_fake_lease(self.lease)


def _error_code(exc: BaseException) -> str:
    assert isinstance(exc, RuntimeOperationError)
    return exc.code


def test_receive_auth_placed_accepts_exact_packet(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform_sockets(monkeypatch)
    parent, child = _control_pair()
    try:
        child.sendall(b"AWRP\x01\x01\x00\x00")
        receive_auth_placed(parent, timeout_seconds=1.0)
    finally:
        parent.close()
        child.close()


def test_receive_auth_placed_rejects_endpoint_eof_and_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_platform_sockets(monkeypatch)
    stream_parent, stream_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeOperationError, match="endpoint is invalid"):
            receive_auth_placed(stream_parent, timeout_seconds=1.0)
    finally:
        stream_parent.close()
        stream_child.close()
    eof_parent, eof_child = _control_pair()
    try:
        eof_child.close()
        with pytest.raises(RuntimeOperationError, match="Auth placed"):
            receive_auth_placed(eof_parent, timeout_seconds=1.0)
    finally:
        eof_parent.close()
    idle_parent, idle_child = _control_pair()
    try:
        with pytest.raises(RuntimeOperationError, match="deadline expired"):
            receive_auth_placed(idle_parent, timeout_seconds=0.05)
        with pytest.raises(ValueError, match="deadline is invalid"):
            receive_auth_placed(idle_parent, timeout_seconds=6.0)
    finally:
        idle_parent.close()
        idle_child.close()


@pytest.mark.anyio
async def test_execute_sends_exact_awp1_record_and_fixed_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.record_dump = tmp_path / "record.bin"
        completion = await rig.execute()
        assert completion.failure is WAWVendorProbeFailure.NONE
        raw = rig.spawn.record_dump.read_bytes()
        assert len(raw) == 160
        fields = struct.unpack("!4sBBHIIIQ64s64s4s", raw)
        (
            magic,
            version,
            agent,
            flags,
            runtime_pid,
            runtime_uid,
            runtime_gid,
            generation,
            workspace_hash_raw,
            profile_digest_raw,
            reserved,
        ) = fields
        assert magic == b"AWP1"
        assert version == 1
        assert agent == 2
        assert flags == 0
        assert runtime_pid == os.getpid()
        assert runtime_uid == os.geteuid()
        assert runtime_gid == os.getegid()
        assert generation == rig.identity.generation
        assert workspace_hash_raw == rig.identity.workspace_hash.encode("ascii")
        assert profile_digest_raw == rig.identity.profile_digest.encode("ascii")
        assert reserved == b"\0" * 4
        assert rig.spawn.argv == ("agentbox-waw-pane-bootstrap", "--auth-probe")
        assert rig.spawn.environment == {}
        assert rig.spawn.descriptor_map is not None
        assert [destination for _source, destination in rig.spawn.descriptor_map] == list(range(9))
    finally:
        rig.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("agent_type", "agent_code"),
    [(AgentType.CODEX, 2), (AgentType.CLAUDE, 1)],
)
async def test_execute_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_type: AgentType,
    agent_code: int,
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch, agent_type=agent_type)
    try:
        rig.spawn.record_dump = tmp_path / "record.bin"
        rig.spawn.stdout = b"vendor stdout\n"
        rig.spawn.stderr = b"vendor stderr\n"
        completion = await rig.execute()
        assert completion.exit_code == 0
        assert completion.stdout == b"vendor stdout\n"
        assert completion.stderr == b"vendor stderr\n"
        assert completion.failure is WAWVendorProbeFailure.NONE
        assert rig.port.validates(completion.cleanup_proof)
        assert completion.cleanup_proof.complete
        record_fields = struct.unpack("!4sBBHIIIQ64s64s4s", rig.spawn.record_dump.read_bytes())
        assert record_fields[2] == agent_code
    finally:
        rig.close()


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["no-awrp", "bad-magic", "oversize", "ancillary"])
async def test_execute_rejects_missing_or_invalid_awrp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.mode = mode
        completion = await rig.execute()
        assert completion.failure is WAWVendorProbeFailure.SPAWN_ERROR
        assert rig.port.validates(completion.cleanup_proof)
    finally:
        rig.close()


@pytest.mark.anyio
@pytest.mark.parametrize("exit_code", [65, 71])
async def test_execute_maps_helper_domain_exits_to_spawn_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.exit_code = exit_code
        completion = await rig.execute()
        assert completion.failure is WAWVendorProbeFailure.SPAWN_ERROR
        assert completion.exit_code == exit_code
        assert completion.cleanup_proof.complete
    finally:
        rig.close()


@pytest.mark.anyio
@pytest.mark.parametrize("exit_code", [23, 42, 89])
async def test_execute_passes_vendor_exit_codes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.exit_code = exit_code
        completion = await rig.execute()
        assert completion.failure is WAWVendorProbeFailure.NONE
        assert completion.exit_code == exit_code
        assert completion.cleanup_proof.complete
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_timeout_terminates_and_kills_cgroup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.mode = "hang"
        started = time.monotonic()
        completion = await rig.execute(timeout_seconds=0.4, terminate_grace_seconds=0.1)
        elapsed = time.monotonic() - started
        assert completion.failure is WAWVendorProbeFailure.TIMEOUT
        assert completion.exit_code is None
        assert rig.cgroup.kill_calls == 1
        assert rig.port.validates(completion.cleanup_proof)
        assert completion.cleanup_proof.complete
        assert elapsed < 4.0
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_output_overflow_terminates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.stdout = b"x" * 4097
        completion = await rig.execute(output_limit=4096)
        assert completion.failure is WAWVendorProbeFailure.OUTPUT_LIMIT
        assert completion.stdout == b""
        assert rig.port.validates(completion.cleanup_proof)
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_cancellation_completes_cleanup_before_propagating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.mode = "hang"
        rig.spawn.started = tmp_path / "started.marker"
        task = asyncio.create_task(rig.execute(terminate_grace_seconds=0.1))
        deadline = time.monotonic() + 5.0
        while not rig.spawn.started.exists():
            assert time.monotonic() < deadline, "fake helper did not start"
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert rig.cgroup.kill_calls == 1
        assert rig.spawn.pid is not None
        with pytest.raises(ChildProcessError):
            os.waitpid(rig.spawn.pid, os.WNOHANG)
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_reports_descendants_when_cgroup_stays_populated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.cgroup.populated_value = 1
        completion = await rig.execute()
        assert completion.failure is WAWVendorProbeFailure.NONE
        assert rig.port.validates(completion.cleanup_proof)
        assert completion.cleanup_proof.descendants_remaining == 1
        assert not completion.cleanup_proof.complete
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_output_boundary_burst_is_never_masked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.stdout = b"x" * 4096
        within = await rig.execute(output_limit=4096)
        assert within.failure is WAWVendorProbeFailure.NONE
        assert within.stdout == b"x" * 4096
        assert within.exit_code == 0
        assert rig.port.validates(within.cleanup_proof)
        assert within.cleanup_proof.complete
    finally:
        rig.close()

    rig = _ExecuteRig(tmp_path / "overflow", monkeypatch)
    try:
        rig.spawn.stdout = b"x" * 4097
        burst = await rig.execute(output_limit=4096)
        assert burst.failure is WAWVendorProbeFailure.OUTPUT_LIMIT
        assert burst.stdout == b""
        assert burst.stderr == b""
        assert rig.port.validates(burst.cleanup_proof)
        assert burst.cleanup_proof.complete
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_kill_failure_degrades_cleanup_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.mode = "hang"

        def _boom() -> None:
            raise OSError("cgroup kill failed")

        monkeypatch.setattr(rig.cgroup, "kill", _boom)
        completion = await rig.execute(timeout_seconds=0.3, terminate_grace_seconds=0.05)
        assert completion.failure is WAWVendorProbeFailure.TIMEOUT
        assert rig.port.validates(completion.cleanup_proof)
        assert completion.cleanup_proof.leader_reaped
        assert completion.cleanup_proof.descendants_remaining == 1
        assert not completion.cleanup_proof.complete
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_cancellation_during_placement_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.mode = "silent-hang"
        started = time.monotonic()
        task = asyncio.create_task(rig.execute(timeout_seconds=0.4, terminate_grace_seconds=0.05))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - started < 4.0
        assert rig.cgroup.kill_calls == 1
        assert rig.spawn.pid is not None
        with pytest.raises(ChildProcessError):
            os.waitpid(rig.spawn.pid, os.WNOHANG)
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_escaped_writer_degrades_cleanup_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.spawn.mode = "escaped-writer"
        started = time.monotonic()
        completion = await rig.execute(timeout_seconds=5.0)
        assert completion.failure is WAWVendorProbeFailure.NONE
        assert completion.exit_code == 0
        assert rig.port.validates(completion.cleanup_proof)
        assert completion.cleanup_proof.leader_reaped
        assert completion.cleanup_proof.descendants_remaining == 1
        assert not completion.cleanup_proof.complete
        assert time.monotonic() - started < 4.0
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_is_single_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        completion = await rig.execute()
        assert completion.failure is WAWVendorProbeFailure.NONE
        with pytest.raises(RuntimeOperationError) as busy:
            await rig.execute()
        assert _error_code(busy.value) == "WAW_AUTH_PROBE_BUSY"
    finally:
        rig.close()


@pytest.mark.anyio
async def test_execute_rejects_mismatched_profile_and_arguments_without_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        wrong_profile = _profile(AgentType.CLAUDE)
        completion = await rig.port.execute(
            wrong_profile,
            ("auth", "status"),
            timeout_seconds=5.0,
            output_limit=4096,
            terminate_grace_seconds=0.25,
        )
        assert completion.failure is WAWVendorProbeFailure.SPAWN_ERROR
        assert rig.spawn.pid is None
        rig2 = _ExecuteRig(tmp_path / "second", monkeypatch)
        try:
            completion = await rig2.port.execute(
                rig2.profile,
                ("auth", "status"),
                timeout_seconds=5.0,
                output_limit=4096,
                terminate_grace_seconds=0.25,
            )
            assert completion.failure is WAWVendorProbeFailure.SPAWN_ERROR
            assert rig2.spawn.pid is None
        finally:
            rig2.close()
    finally:
        rig.close()


def test_port_constructor_rejects_wrong_token_and_fd_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        helper_fd = _executable_fd(tmp_path, "helper-two", b"helper-two")
        vendor_fd = _executable_fd(tmp_path, "vendor-two", b"vendor-two")
        home_fd = _directory_fd(tmp_path / "home")
        policy_fd = _directory_fd(tmp_path / "policy")
        try:
            with pytest.raises(RuntimeOperationError, match="not caller-constructible"):
                WAWNativeAuthProbePort(
                    object(),
                    lease=rig.lease,
                    identity=rig.identity,
                    helper_executable=helper_fd,
                    vendor_executable=vendor_fd,
                    home_directory=home_fd,
                    policy_directory=policy_fd,
                )
            regular_fd = _executable_fd(tmp_path, "not-a-directory", b"x")
            try:
                with pytest.raises(RuntimeOperationError, match="role is invalid"):
                    WAWNativeAuthProbePort(
                        subject._AUTH_NATIVE_PORT_TOKEN,
                        lease=rig.lease,
                        identity=rig.identity,
                        helper_executable=helper_fd,
                        vendor_executable=vendor_fd,
                        home_directory=regular_fd,
                        policy_directory=policy_fd,
                    )
            finally:
                _close_fd_quiet(regular_fd)
        finally:
            for descriptor in (helper_fd, vendor_fd, home_fd, policy_fd):
                _close_fd_quiet(descriptor)
    finally:
        rig.close()


def test_port_close_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _ExecuteRig(tmp_path, monkeypatch)
    try:
        rig.port.close()
        rig.port.close()
        with pytest.raises(OSError):
            os.fstat(rig.port._helper_executable)
    finally:
        _close_fake_lease(rig.lease)


_HELD_CONTENT = {
    "helper": b"helper-held-bytes",
    "claude": b"claude-held-bytes",
    "codex": b"codex-held-bytes",
}


class _FactoryRig:
    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        authorized: bool = True,
        tamper_asset: str | None = None,
        production: bool = True,
        drift: bool = False,
    ) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        _patch_platform_sockets(monkeypatch)
        monkeypatch.setattr(subject, "_verify_fd_digest", _sha256_fd_check)
        self.helper_path = tmp_path / "pane-bootstrap-held"
        self.claude_path = tmp_path / "claude-held"
        self.codex_path = tmp_path / "codex-held"
        paths = {"helper": self.helper_path, "claude": self.claude_path, "codex": self.codex_path}
        for asset, path in paths.items():
            path.write_bytes(_HELD_CONTENT[asset])
            path.chmod(0o755)
        # Manifest digests always describe the pristine held bytes; tampering
        # the file afterwards must therefore fail closed at construction.
        if tamper_asset is not None:
            paths[tamper_asset].write_bytes(b"tampered-held-bytes")
        self.helper_digest = hashlib.sha256(_HELD_CONTENT["helper"]).hexdigest()
        self.fingerprints = {
            AgentType.CLAUDE: hashlib.sha256(_HELD_CONTENT["claude"]).hexdigest(),
            AgentType.CODEX: hashlib.sha256(_HELD_CONTENT["codex"]).hexdigest(),
        }
        manifest = SimpleNamespace(
            executable_inventory=SimpleNamespace(
                executables=(
                    SimpleNamespace(
                        kind="pane_bootstrap", sha256=self.helper_digest, max_bytes=4096
                    ),
                    SimpleNamespace(
                        kind="claude",
                        sha256=self.fingerprints[AgentType.CLAUDE],
                        max_bytes=4096,
                    ),
                    SimpleNamespace(
                        kind="codex",
                        sha256=self.fingerprints[AgentType.CODEX],
                        max_bytes=4096,
                    ),
                )
            )
        )
        self.authority = _authority(
            monkeypatch,
            authorized=authorized,
            fingerprints=self.fingerprints,
            manifest=manifest,
        )
        self.other_authority = object.__new__(WAWVerifiedExecutionAuthority)
        helper_fd = os.open(self.helper_path, os.O_RDONLY | os.O_CLOEXEC)
        claude_fd = os.open(self.claude_path, os.O_RDONLY | os.O_CLOEXEC)
        codex_fd = os.open(self.codex_path, os.O_RDONLY | os.O_CLOEXEC)
        self.process_port = object.__new__(NativeHelperProcessPort)
        self.process_port._helpers = NativeHelperHandles(
            helper_fd, helper_fd, helper_fd, helper_fd, helper_fd
        )
        self.process_port._qualified_executables = {
            WAWExecutableKind.CLAUDE: claude_fd,
            WAWExecutableKind.CODEX: codex_fd,
        }
        self.process_port.production_qualified = production
        self.process_port._execution_authority = self.other_authority if drift else self.authority
        self._source_fds: tuple[int, ...] = (helper_fd, claude_fd, codex_fd)
        self.factory: WAWNativeAuthProbePortFactory | None = None

    def build(self) -> WAWNativeAuthProbePortFactory:
        self.factory = WAWNativeAuthProbePortFactory(self.authority, process_port=self.process_port)
        for descriptor in self._source_fds:
            _close_fd_quiet(descriptor)
        self._source_fds = ()
        return self.factory

    def close(self) -> None:
        if self.factory is not None:
            self.factory.close()
        for descriptor in self._source_fds:
            _close_fd_quiet(descriptor)
        self._source_fds = ()


def test_factory_constructs_and_pins_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _FactoryRig(tmp_path, monkeypatch)
    try:
        factory = rig.build()
        assert factory.authority is rig.authority
        factory.close()
        factory.close()
        with pytest.raises(RuntimeOperationError, match="factory is closed"):
            factory.port_for_lease(cast(Any, object()))
    finally:
        rig.close()


def test_factory_rejects_type_production_and_authority_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _FactoryRig(tmp_path, monkeypatch)
    try:
        with pytest.raises(TypeError):
            WAWNativeAuthProbePortFactory(cast(Any, object()), process_port=rig.process_port)
        with pytest.raises(TypeError):
            WAWNativeAuthProbePortFactory(rig.authority, process_port=cast(Any, object()))
    finally:
        rig.close()
    synthetic = _FactoryRig(tmp_path / "synthetic", monkeypatch, production=False)
    try:
        with pytest.raises(RuntimeOperationError, match="production process port"):
            synthetic.build()
    finally:
        synthetic.close()
    drifted = _FactoryRig(tmp_path / "drifted", monkeypatch, drift=True)
    try:
        with pytest.raises(RuntimeOperationError, match="not bound"):
            drifted.build()
    finally:
        drifted.close()


@pytest.mark.parametrize("asset", ["helper", "claude", "codex"])
def test_factory_rejects_digest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asset: str
) -> None:
    rig = _FactoryRig(tmp_path, monkeypatch, tamper_asset=asset)
    try:
        with pytest.raises(RuntimeOperationError, match="does not match"):
            rig.build()
    finally:
        rig.close()


@pytest.mark.anyio
async def test_factory_port_for_lease_executes_happy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _FactoryRig(tmp_path, monkeypatch)
    lease: WAWSealedAuthLease | None = None
    try:
        factory = rig.build()
        identity = fixed_identity(AgentType.CODEX)
        cgroup = _CgroupFake()
        home_dir = tmp_path / "home"
        policy_dir = tmp_path / "policy"
        cgroup_dir = tmp_path / "cgroup"
        scratch_dir = tmp_path / "scratch"
        for directory in (home_dir, policy_dir, cgroup_dir, scratch_dir):
            directory.mkdir()
        lease = _fake_lease(identity, cgroup, cgroup_dir, scratch_dir, home_dir, policy_dir)
        spawn = _SpawnRig(monkeypatch, _write_helper_script(tmp_path))
        spawn.stdout = b"factory wired\n"
        port = factory.port_for_lease(lease)
        assert port.isolation_kind is WAWProcessIsolationKind.PREBIRTH_CGROUP
        assert port.production_qualified is True
        completion = await port.execute(
            _profile(AgentType.CODEX),
            ("login", "status"),
            timeout_seconds=5.0,
            output_limit=4096,
            terminate_grace_seconds=0.25,
        )
        assert completion.exit_code == 0
        assert completion.stdout == b"factory wired\n"
        assert completion.failure is WAWVendorProbeFailure.NONE
        assert port.validates(completion.cleanup_proof)
        assert completion.cleanup_proof.complete
        port.close()
    finally:
        if lease is not None:
            _close_fake_lease(lease)
        rig.close()


def test_factory_issues_single_port_per_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _FactoryRig(tmp_path, monkeypatch)
    lease: WAWSealedAuthLease | None = None
    try:
        factory = rig.build()
        identity = fixed_identity(AgentType.CODEX)
        cgroup = _CgroupFake()
        home_dir = tmp_path / "home"
        policy_dir = tmp_path / "policy"
        cgroup_dir = tmp_path / "cgroup"
        scratch_dir = tmp_path / "scratch"
        for directory in (home_dir, policy_dir, cgroup_dir, scratch_dir):
            directory.mkdir()
        lease = _fake_lease(identity, cgroup, cgroup_dir, scratch_dir, home_dir, policy_dir)
        port = factory.port_for_lease(lease)
        port.close()
        with pytest.raises(RuntimeOperationError) as busy:
            factory.port_for_lease(lease)
        assert _error_code(busy.value) == "WAW_AUTH_PROBE_BUSY"
    finally:
        if lease is not None:
            _close_fake_lease(lease)
        rig.close()


def test_factory_port_for_lease_rejects_stale_and_unauthorized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _FactoryRig(tmp_path, monkeypatch)
    lease: WAWSealedAuthLease | None = None
    try:
        factory = rig.build()
        identity = fixed_identity(AgentType.CODEX)
        cgroup = _CgroupFake()
        home_dir = tmp_path / "home"
        policy_dir = tmp_path / "policy"
        cgroup_dir = tmp_path / "cgroup"
        scratch_dir = tmp_path / "scratch"
        for directory in (home_dir, policy_dir, cgroup_dir, scratch_dir):
            directory.mkdir()
        lease = _fake_lease(identity, cgroup, cgroup_dir, scratch_dir, home_dir, policy_dir)
        lease._state = "RELEASED"
        with pytest.raises(RuntimeOperationError) as stale:
            factory.port_for_lease(lease)
        assert _error_code(stale.value) == "WAW_AUTH_LEASE_STALE"
        lease._state = "OWNED"
        with pytest.raises(TypeError):
            factory.port_for_lease(cast(Any, object()))
    finally:
        if lease is not None:
            _close_fake_lease(lease)
        rig.close()
    unauthorized = _FactoryRig(tmp_path / "unauthorized", monkeypatch, authorized=False)
    lease = None
    try:
        factory = unauthorized.build()
        identity = fixed_identity(AgentType.CODEX)
        cgroup = _CgroupFake()
        for name in ("home", "policy", "cgroup", "scratch"):
            (tmp_path / "unauthorized" / name).mkdir()
        lease = _fake_lease(
            identity,
            cgroup,
            tmp_path / "unauthorized" / "cgroup",
            tmp_path / "unauthorized" / "scratch",
            tmp_path / "unauthorized" / "home",
            tmp_path / "unauthorized" / "policy",
        )
        with pytest.raises(RuntimeOperationError) as stale:
            factory.port_for_lease(lease)
        assert _error_code(stale.value) == "WAW_AUTH_LEASE_STALE"
    finally:
        if lease is not None:
            _close_fake_lease(lease)
        unauthorized.close()


def _bindings(fingerprints: dict[AgentType, str]) -> dict[AgentType, WAWVendorPublicAuthBinding]:
    return {
        agent_type: WAWVendorPublicAuthBinding(
            agent_type,
            HOST_ID,
            REVISION,
            fingerprints[agent_type],
            str(INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]["profile_id"]),
            VERSIONS[agent_type],
        )
        for agent_type in AgentType
    }


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
    home_dir: Path,
    policy_dir: Path,
) -> WAWFixedTransport:
    transport = object.__new__(WAWFixedTransport)
    transport._identity = identity
    transport._production = True
    transport._handles = cast(
        Any,
        SimpleNamespace(
            cgroup=handle,
            selected_home_directory=os.open(home_dir, os.O_RDONLY | os.O_DIRECTORY),
            policy_directory=os.open(policy_dir, os.O_RDONLY | os.O_DIRECTORY),
        ),
    )
    transport._port = cast(Any, SimpleNamespace(execution_authority=authority))
    transport._start_attempted = False
    transport._closed = False
    transport._aborted_unstarted = False
    transport._auth_lease = None
    transport._auth_poisoned = False
    return transport


class _OwnerNativeRig:
    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        exit_code: int = 0,
        out: bytes = b"",
        err: bytes = b"",
        codex_digest: str = "0" * 64,
    ) -> None:
        self.factory_rig = _FactoryRig(tmp_path, monkeypatch)
        self.factory = self.factory_rig.build()
        self.authority = self.factory_rig.authority
        self.runner = object.__new__(WAWVendorProbeRunner)
        self.profiles = {
            AgentType.CLAUDE: _profile(AgentType.CLAUDE),
            AgentType.CODEX: _profile(AgentType.CODEX, codex_digest=codex_digest),
        }
        self.now = [1000.0]
        root = tmp_path / "scratch-root"
        root.mkdir()
        root.chmod(0o700)
        workspace = root / WORKSPACE_HASH
        workspace.mkdir()
        workspace.chmod(0o700)
        scratch_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        self.lease_owner = WAWAuthLeaseOwner(self.authority, scratch_root=scratch_fd)
        os.close(scratch_fd)
        self.identity = fixed_identity(AgentType.CODEX)
        self.cgroup_state = {"populated": 0, "frozen": 0}
        self.handle = _cgroup_handle(
            tmp_path, monkeypatch, self.identity, self.authority, self.cgroup_state
        )
        home_dir = tmp_path / "vendor-home"
        policy_dir = tmp_path / "vendor-policy"
        home_dir.mkdir()
        policy_dir.mkdir()
        self.transport = _transport(
            self.identity, self.authority, self.handle, home_dir, policy_dir
        )
        self.spawn = _SpawnRig(monkeypatch, _write_helper_script(tmp_path))
        self.spawn.exit_code = exit_code
        self.spawn.stdout = out
        self.spawn.stderr = err
        self.ports_created: list[WAWNativeAuthProbePort] = []
        original_port_for_lease = WAWNativeAuthProbePortFactory.port_for_lease

        def port_spy(
            factory: WAWNativeAuthProbePortFactory, lease: WAWSealedAuthLease
        ) -> WAWNativeAuthProbePort:
            port = original_port_for_lease(factory, lease)
            self.ports_created.append(port)
            return port

        monkeypatch.setattr(WAWNativeAuthProbePortFactory, "port_for_lease", port_spy)
        original_close = WAWNativeAuthProbePort.close
        self.closed_ports: list[WAWNativeAuthProbePort] = []

        def close_spy(port: WAWNativeAuthProbePort) -> None:
            self.closed_ports.append(port)
            original_close(port)

        monkeypatch.setattr(WAWNativeAuthProbePort, "close", close_spy)
        self.owner = WAWProductionAuthOwner(
            self.authority,
            runner=self.runner,
            bindings=_bindings(self.factory_rig.fingerprints),
            lease_owner=self.lease_owner,
            clock=lambda: self.now[0],
            max_age_seconds=30.0,
            native_port_factory=self.factory,
            profiles=self.profiles,
        )

    def probe_kwargs(self) -> dict[str, Any]:
        return {
            "agent_type": AgentType.CODEX,
            "runtime_host_installation_id": HOST_ID,
            "runtime_host_installation_revision": REVISION,
            "executable_fingerprint": self.factory_rig.fingerprints[AgentType.CODEX],
            "checked_at_monotonic": self.now[0],
        }

    def close(self) -> None:
        self.factory_rig.close()
        self.lease_owner.close()
        _close_fd_quiet(self.handle._descriptor)
        handles = cast(Any, self.transport._handles)
        _close_fd_quiet(cast(int, handles.selected_home_directory))
        _close_fd_quiet(cast(int, handles.policy_directory))


def test_owner_native_configuration_requires_pairing_and_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _OwnerNativeRig(tmp_path, monkeypatch)
    try:
        base: dict[str, Any] = {
            "runner": rig.runner,
            "bindings": _bindings(rig.factory_rig.fingerprints),
            "lease_owner": rig.lease_owner,
            "clock": lambda: 0.0,
        }
        with pytest.raises(WAWPublicAuthProbeError, match="together"):
            WAWProductionAuthOwner(rig.authority, native_port_factory=rig.factory, **base)
        with pytest.raises(WAWPublicAuthProbeError, match="together"):
            WAWProductionAuthOwner(rig.authority, profiles=rig.profiles, **base)
        with pytest.raises(TypeError):
            WAWProductionAuthOwner(
                rig.authority,
                native_port_factory=cast(Any, object()),
                profiles=rig.profiles,
                **base,
            )
        foreign = _FactoryRig(tmp_path / "foreign", monkeypatch)
        try:
            foreign_factory = foreign.build()
            with pytest.raises(WAWPublicAuthProbeError, match="not bound"):
                WAWProductionAuthOwner(
                    rig.authority,
                    native_port_factory=foreign_factory,
                    profiles=rig.profiles,
                    **base,
                )
        finally:
            foreign.close()
        incomplete = {AgentType.CODEX: rig.profiles[AgentType.CODEX]}
        with pytest.raises(WAWPublicAuthProbeError, match="per AgentType"):
            WAWProductionAuthOwner(
                rig.authority,
                native_port_factory=rig.factory,
                profiles=cast(Any, incomplete),
                **base,
            )
        mismatched = dict(rig.profiles)
        mismatched[AgentType.CLAUDE] = _profile(AgentType.CODEX)
        with pytest.raises(WAWPublicAuthProbeError, match="does not match"):
            WAWProductionAuthOwner(
                rig.authority,
                native_port_factory=rig.factory,
                profiles=mismatched,
                **base,
            )
    finally:
        rig.close()


@pytest.mark.anyio
async def test_owner_native_probe_with_lease_authenticated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _OwnerNativeRig(tmp_path, monkeypatch)
    try:
        evidence = await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
        assert evidence.result is WAWPublicAuthResult.AUTHENTICATED
        assert evidence.checked_at_monotonic == 1000.0
        assert len(rig.ports_created) == 1
        assert rig.closed_ports == rig.ports_created
        assert rig.transport._auth_lease is None
        assert not rig.handle.auth_borrowed
        assert rig.owner.authenticated(rig.identity) is True
        # Second call is a cache hit: no new port, lease still fully released.
        cached = await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
        assert cached is evidence
        assert len(rig.ports_created) == 1
        assert rig.transport._auth_lease is None
    finally:
        rig.close()


@pytest.mark.anyio
async def test_owner_native_probe_with_lease_unauthenticated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = b"Not logged in\n"
    digest = waw_vendor_probe_output_digest(out, b"")
    rig = _OwnerNativeRig(tmp_path, monkeypatch, exit_code=1, out=out, codex_digest=digest)
    try:
        evidence = await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
        assert evidence.result is WAWPublicAuthResult.UNAUTHENTICATED
        assert evidence.checked_at_monotonic == 1000.0
        assert len(rig.ports_created) == 1
        assert rig.closed_ports == rig.ports_created
        assert rig.transport._auth_lease is None
        assert not rig.handle.auth_borrowed
        assert rig.owner.authenticated(rig.identity) is False
    finally:
        rig.close()


@pytest.mark.anyio
async def test_owner_native_cache_hit_skips_port_and_releases_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = _OwnerNativeRig(tmp_path, monkeypatch)
    try:
        rig.owner._cache.record(
            WAWPublicAuthEvidence(
                AgentType.CODEX,
                HOST_ID,
                REVISION,
                rig.factory_rig.fingerprints[AgentType.CODEX],
                1000.0,
                WAWPublicAuthResult.AUTHENTICATED,
            )
        )
        evidence = await rig.owner.probe_with_lease(rig.transport, **rig.probe_kwargs())
        assert evidence.result is WAWPublicAuthResult.AUTHENTICATED
        assert rig.ports_created == []
        assert rig.transport._auth_lease is None
        assert not rig.handle.auth_borrowed
    finally:
        rig.close()
