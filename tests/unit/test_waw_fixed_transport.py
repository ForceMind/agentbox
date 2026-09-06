from __future__ import annotations

import hashlib
import os
import platform
import socket
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType, WorkspaceStopOperation, managed_marker, workspace_id
from agentbox_core.waw_tickets import AttachmentTuple
from agentbox_runtime import waw_fixed_transport as fixed_subject
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import inspect_executable
from agentbox_runtime.waw_auth_probe import WAWPublicAuthEvidence, WAWPublicAuthResult
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_fixed_transport import (
    MAX_NATIVE_OUTPUT_BYTES,
    NATIVE_READY,
    LinuxCgroupControlHandle,
    NativeHelperProcessPort,
    NativeWBREndpoint,
    WAWFixedTransport,
    WAWProductionLaunchHandles,
    WAWVerifiedExecutionAuthority,
    WAWVerifiedLaunchHandleFactory,
    receive_native_ready,
)
from agentbox_runtime.waw_process_inspector import (
    FixedAttachmentRequest,
    FixedLaunchHandles,
    FixedLaunchRequest,
    FixedProcessBinding,
    FixedProcessIdentity,
    FixedStartProof,
    FixedStartState,
)
from agentbox_runtime.waw_process_protocol import WBRMessage, WBRMessageType, encode_wbr_message
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_redraw import BoundedRedraw
from agentbox_runtime.waw_supervisor import (
    RuntimeAttachmentCleanupEvidence,
    RuntimeAttachmentLease,
    RuntimeProbeEvidence,
    RuntimeProbeState,
    RuntimeStopEvidence,
    SupervisorState,
    WAWSupervisor,
)

PROJECT = "prj_" + "1" * 32
WORKSPACE = workspace_id(PROJECT, AgentType.CODEX)
HOST = "wri_" + "2" * 32
DIGEST = "a" * 64
PROFILE_DIGEST = "b" * 64
EXECUTABLE_DIGEST = "c" * 64


def fixed_identity(epoch: str = "2") -> FixedProcessIdentity:
    marker = managed_marker(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        project_id=PROJECT,
        agent_type=AgentType.CODEX,
        workspace_id_value=WORKSPACE,
        generation=1,
        binding_revision=1,
        binding_digest=DIGEST,
    )
    return FixedProcessIdentity(
        WORKSPACE,
        PROJECT,
        AgentType.CODEX,
        1,
        "d" * 64,
        marker,
        PROFILE_DIGEST,
        HOST,
        "1",
        epoch,
    )


def launch_handles() -> FixedLaunchHandles:
    return FixedLaunchHandles(*(object() for _ in range(8)))


def command(tmp_path: Path, item: FixedProcessIdentity) -> WAWCodexCommand:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    return WAWCodexCommand(
        WORKSPACE,
        PROJECT,
        project,
        inspect_executable(executable),
        (),
        item.managed_marker,
    )


def lease(item: FixedProcessIdentity) -> RuntimeAttachmentLease:
    claims = AttachmentTuple(
        WORKSPACE,
        PROJECT,
        AgentType.CODEX,
        "att_" + "4" * 32,
        1,
        1,
        1,
        1,
        HOST,
        1,
        1,
        DIGEST,
    )
    return RuntimeAttachmentLease(claims, item.runtime_epoch, 100.0, lambda: True)


@dataclass
class FakeAttachment:
    request: FixedAttachmentRequest
    output: list[bytes | None] = field(default_factory=list)
    writes: list[bytes] = field(default_factory=list)
    resizes: list[PtyGeometry] = field(default_factory=list)
    fail_resize_at: int | None = None
    closed: int = 0
    cleanup_members: list[int] = field(default_factory=lambda: [0])

    def read_output(self, max_bytes: int) -> bytes | None:
        assert max_bytes == MAX_NATIVE_OUTPUT_BYTES
        return self.output.pop(0) if self.output else None

    def write_input(self, data: bytes) -> None:
        self.writes.append(data)

    def resize(self, geometry: PtyGeometry) -> bytes:
        self.resizes.append(geometry)
        if self.fail_resize_at == len(self.resizes):
            raise OSError("synthetic WBR failure")
        return encode_wbr_message(
            WBRMessage(
                WBRMessageType.ACK,
                len(self.resizes),
                self.request.binding.identity.generation,
                geometry.columns,
                geometry.rows,
            )
        )

    def close(self) -> RuntimeAttachmentCleanupEvidence:
        self.closed += 1
        remaining = (
            self.cleanup_members.pop(0)
            if len(self.cleanup_members) > 1
            else self.cleanup_members[0]
        )
        return RuntimeAttachmentCleanupEvidence(self.request.lease, remaining == 0, remaining)


class FakeNativePort:
    def __init__(self, states: list[FixedStartState] | None = None) -> None:
        self.states = list(states or [FixedStartState.RUNNING])
        self.starts: list[FixedLaunchRequest] = []
        self.attachments: list[FakeAttachment] = []
        self.stop_calls = 0
        self.stop_members = 0
        self.redraw = BoundedRedraw(b"", False)
        self.redraw_calls: list[tuple[FixedProcessBinding, float]] = []

    def start(self, request: FixedLaunchRequest) -> FixedStartProof:
        self.starts.append(request)
        state = self.states.pop(0)
        process = (
            None
            if state is FixedStartState.LOGIN_REQUIRED
            else FixedProcessBinding(request.identity, object(), object(), object())
        )
        return FixedStartProof(
            request,
            state,
            process,
            0 if process is None else 1,
        )

    def open_attachment(self, request: FixedAttachmentRequest) -> FakeAttachment:
        attachment = FakeAttachment(request)
        self.attachments.append(attachment)
        return attachment

    def probe(self, binding: FixedProcessBinding) -> RuntimeProbeEvidence:
        item = binding.identity
        return RuntimeProbeEvidence(
            item.workspace_id,
            item.generation,
            item.managed_marker,
            RuntimeProbeState.RUNNING,
        )

    def capture_redraw(self, binding: FixedProcessBinding, deadline: float) -> BoundedRedraw:
        self.redraw_calls.append((binding, deadline))
        return self.redraw

    def stop(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        self.stop_calls += 1
        item = binding.identity
        return RuntimeStopEvidence(
            item.workspace_id,
            item.generation,
            item.managed_marker,
            True,
            self.stop_members,
        )

    def destroy_fenced(self, binding: FixedProcessBinding) -> RuntimeStopEvidence:
        self.stop_calls += 1
        item = binding.identity
        return RuntimeStopEvidence(item.workspace_id, item.generation, item.managed_marker, True, 0)


def transport(
    item: FixedProcessIdentity, port: FakeNativePort, *, now: float = 10.0
) -> WAWFixedTransport:
    return WAWFixedTransport.development_only(
        identity=item,
        handles=launch_handles(),
        executable_fingerprint=EXECUTABLE_DIGEST,
        port=port,
        clock=lambda: now,
    )


def supervisor(
    tmp_path: Path, item: FixedProcessIdentity, fixed: WAWFixedTransport
) -> WAWSupervisor:
    return WAWSupervisor(
        workspace_id=WORKSPACE,
        generation=1,
        command=command(tmp_path, item),
        transport=fixed,
        geometry=PtyGeometry(80, 24),
        clock=lambda: 10.0,
        attachment_validator=lambda _value: True,
        stop_binding=WorkspaceStopOperation(
            WORKSPACE, PROJECT, AgentType.CODEX, 1, 1, DIGEST, HOST, 1
        ),
        runtime_epoch=item.runtime_epoch,
    )


def test_commit_opens_exact_attachment_applies_winsize_and_produces_bounded_output(
    tmp_path: Path,
) -> None:
    item = fixed_identity()
    port = FakeNativePort()
    fixed = transport(item, port)
    runtime = supervisor(tmp_path, item, fixed)
    runtime.start()
    active = lease(item)
    runtime.reserve_runtime_attachment(active)
    runtime.commit_runtime_attachment(active)

    native = port.attachments[0]
    assert native.request.lease is active
    assert native.resizes == [PtyGeometry(80, 24)]
    native.output.append(b"x" * MAX_NATIVE_OUTPUT_BYTES)
    assert (
        runtime.replay_output(0, generation=1, runtime_epoch="2", attachment=active)
        .frames[0]
        .payload
        == b"x" * MAX_NATIVE_OUTPUT_BYTES
    )


def test_resize_failure_fences_only_attachment_and_keeps_process_running(tmp_path: Path) -> None:
    item = fixed_identity()
    port = FakeNativePort()
    fixed = transport(item, port)
    runtime = supervisor(tmp_path, item, fixed)
    runtime.start()
    active = lease(item)
    runtime.reserve_runtime_attachment(active)
    runtime.commit_runtime_attachment(active)
    port.attachments[0].fail_resize_at = 2

    with pytest.raises(RuntimeOperationError, match="resize"):
        runtime.resize(active, PtyGeometry(100, 30))
    assert runtime.state is SupervisorState.DETACHED
    assert runtime.probe().state is RuntimeProbeState.RUNNING
    assert port.attachments[0].closed == 1


def test_detach_uses_typed_cleanup_and_never_legacy_boolean(tmp_path: Path) -> None:
    item = fixed_identity()
    port = FakeNativePort()
    fixed = transport(item, port)
    runtime = supervisor(tmp_path, item, fixed)
    runtime.start()
    active = lease(item)
    runtime.reserve_runtime_attachment(active)
    runtime.commit_runtime_attachment(active)
    runtime.detach(active)
    assert runtime.state is SupervisorState.DETACHED
    assert port.attachments[0].closed == 1


def test_login_resume_reuses_exact_request_and_no_process_stop_is_success(tmp_path: Path) -> None:
    item = fixed_identity()
    login_only = FakeNativePort([FixedStartState.LOGIN_REQUIRED])
    fixed = transport(item, login_only)
    runtime = supervisor(tmp_path, item, fixed)
    assert runtime.start().state is SupervisorState.LOGIN_REQUIRED
    runtime.exact_stop(
        WorkspaceStopOperation(WORKSPACE, PROJECT, AgentType.CODEX, 1, 1, DIGEST, HOST, 1)
    )
    assert login_only.stop_calls == 0

    resuming_port = FakeNativePort([FixedStartState.LOGIN_REQUIRED, FixedStartState.RUNNING])
    resuming = transport(item, resuming_port)
    resumed_runtime = supervisor(tmp_path, item, resuming)
    assert resumed_runtime.start().state is SupervisorState.LOGIN_REQUIRED
    evidence = WAWPublicAuthEvidence(
        AgentType.CODEX,
        HOST,
        "1",
        EXECUTABLE_DIGEST,
        9.0,
        WAWPublicAuthResult.AUTHENTICATED,
    )
    assert resumed_runtime.resume_after_login(evidence).state is SupervisorState.RUNNING
    assert len(resuming_port.starts) == 2
    assert resuming_port.starts[0] is resuming_port.starts[1]
    with pytest.raises(RuntimeOperationError, match="not waiting"):
        resumed_runtime.resume_after_login(evidence)


def test_stale_auth_evidence_does_not_leave_login_required_state(tmp_path: Path) -> None:
    item = fixed_identity()
    port = FakeNativePort([FixedStartState.LOGIN_REQUIRED])
    runtime = supervisor(tmp_path, item, transport(item, port, now=40.0))
    runtime.start()
    stale = WAWPublicAuthEvidence(
        AgentType.CODEX,
        HOST,
        "1",
        EXECUTABLE_DIGEST,
        9.0,
        WAWPublicAuthResult.AUTHENTICATED,
    )
    with pytest.raises(RuntimeOperationError, match="Fresh authenticated"):
        runtime.resume_after_login(stale)
    assert runtime.state is SupervisorState.LOGIN_REQUIRED
    assert len(port.starts) == 1


def test_test_fake_cannot_enter_production_constructor() -> None:
    item = fixed_identity()
    with pytest.raises(RuntimeOperationError, match="Linux native helper"):
        WAWFixedTransport(
            identity=item,
            handles=launch_handles(),
            executable_fingerprint=EXECUTABLE_DIGEST,
            port=FakeNativePort(),
            clock=lambda: 0.0,
            production=True,
        )


def test_nominal_production_launch_and_cgroup_handles_are_not_constructible() -> None:
    item = fixed_identity()
    with pytest.raises(RuntimeOperationError, match="not caller-constructible"):
        LinuxCgroupControlHandle(
            object(),
            descriptor=-1,
            authority=cast(Any, object()),
            identity=fixed_identity(),
            mount_identity=("1", "host-cgroup2-1"),
        )
    with pytest.raises(RuntimeOperationError, match="not caller-constructible"):
        WAWProductionLaunchHandles(
            object(),
            identity=item,
            handles=launch_handles(),
            authority=cast(Any, object()),
            project_identity=(1, 2, 3, 4, 5),
        )


def test_production_transport_rejects_ordinary_test_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = fixed_identity()
    port = object.__new__(NativeHelperProcessPort)
    port.production_qualified = True
    port._execution_authority = object.__new__(WAWVerifiedExecutionAuthority)
    monkeypatch.setattr(NativeHelperProcessPort, "authorizes", lambda _self, _identity: True)
    monkeypatch.setattr(
        WAWVerifiedExecutionAuthority,
        "vendor_executable_fingerprint",
        lambda _self, _agent: EXECUTABLE_DIGEST,
    )
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    with pytest.raises(RuntimeOperationError, match="were not issued"):
        WAWFixedTransport(
            identity=item,
            handles=launch_handles(),
            executable_fingerprint=EXECUTABLE_DIGEST,
            port=port,
            clock=lambda: 0.0,
            production=True,
        )


def test_launch_factory_rejects_structural_cgroup_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = object.__new__(WAWVerifiedExecutionAuthority)
    monkeypatch.setattr(WAWVerifiedExecutionAuthority, "authorizes", lambda _self, _identity: True)
    factory = object.__new__(WAWVerifiedLaunchHandleFactory)
    factory._closed = False
    factory._authority = authority
    endpoint = object.__new__(NativeWBREndpoint)
    with pytest.raises(RuntimeOperationError, match="cgroup handle"):
        factory.create(
            identity=fixed_identity(),
            relative_key="project",
            wbr_endpoint=endpoint,
            cgroup=cast(Any, _CgroupControl()),
        )


def test_cgroup_identity_live_and_reuse_reject_before_launch_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    handle = object.__new__(LinuxCgroupControlHandle)
    handle._descriptor = directory_fd
    handle._authority = cast(Any, object())
    handle._identity = fixed_identity()
    handle._closed = False
    handle._consumed = False
    handle._lock = threading.RLock()
    wrong = replace(fixed_identity(), generation=2)
    with pytest.raises(RuntimeOperationError, match="identity-stale"):
        handle.take_launcher_fd(wrong)
    assert not handle.consumed

    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: 1)
    monkeypatch.setattr(LinuxCgroupControlHandle, "frozen", lambda _self: 0)
    with pytest.raises(RuntimeOperationError, match="became live"):
        handle.take_launcher_fd(fixed_identity())
    assert not handle.consumed

    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: 0)
    launcher_fd = handle.take_launcher_fd(fixed_identity())
    os.close(launcher_fd)
    with pytest.raises(RuntimeOperationError, match="consumed"):
        handle.take_launcher_fd(fixed_identity())
    handle.close()


def test_cgroup_launcher_fd_is_consumed_once_across_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    handle = object.__new__(LinuxCgroupControlHandle)
    handle._descriptor = directory_fd
    handle._authority = cast(Any, object())
    handle._identity = fixed_identity()
    handle._closed = False
    handle._consumed = False
    handle._lock = threading.RLock()
    monkeypatch.setattr(LinuxCgroupControlHandle, "populated", lambda _self: 0)
    monkeypatch.setattr(LinuxCgroupControlHandle, "frozen", lambda _self: 0)

    def consume() -> int | None:
        try:
            return handle.take_launcher_fd(fixed_identity())
        except RuntimeOperationError:
            return None

    with ThreadPoolExecutor(max_workers=16) as workers:
        results = tuple(workers.map(lambda _index: consume(), range(100)))
    issued = tuple(descriptor for descriptor in results if descriptor is not None)
    assert len(issued) == 1
    os.close(issued[0])
    assert handle.consumed
    handle.close()


def test_installed_directory_and_policy_forgery_are_rejected(tmp_path: Path) -> None:
    expected = tmp_path / "expected"
    forged = tmp_path / "forged"
    expected.mkdir(mode=0o700)
    forged.mkdir(mode=0o700)
    expected_fd = os.open(expected, os.O_RDONLY | os.O_DIRECTORY)
    forged_fd = os.open(forged, os.O_RDONLY | os.O_DIRECTORY)
    policy = tmp_path / "policy.json"
    policy.write_bytes(b"{}")
    policy.chmod(0o444)
    policy_fd = os.open(policy, os.O_RDONLY)
    try:
        fixed_subject._verify_installed_directory(
            expected_fd,
            str(expected),
            expected_uid=os.geteuid(),
            expected_mode=0o700,
        )
        with pytest.raises(RuntimeOperationError, match="identity"):
            fixed_subject._verify_installed_directory(
                forged_fd,
                str(expected),
                expected_uid=os.geteuid(),
                expected_mode=0o700,
            )
        expected.chmod(0o755)
        with pytest.raises(RuntimeOperationError, match="identity"):
            fixed_subject._verify_installed_directory(
                expected_fd,
                str(expected),
                expected_uid=os.geteuid(),
                expected_mode=0o700,
            )
        with pytest.raises(RuntimeOperationError, match="policy file identity"):
            fixed_subject._verify_installed_file(
                policy_fd, str(policy), hashlib.sha256(b"{}").hexdigest()
            )
    finally:
        for descriptor in (expected_fd, forged_fd, policy_fd):
            os.close(descriptor)


def test_native_output_over_bound_is_rejected_before_ring_append(tmp_path: Path) -> None:
    item = fixed_identity()
    port = FakeNativePort()
    runtime = supervisor(tmp_path, item, transport(item, port))
    runtime.start()
    active = lease(item)
    runtime.reserve_runtime_attachment(active)
    runtime.commit_runtime_attachment(active)
    port.attachments[0].output.append(b"x" * (MAX_NATIVE_OUTPUT_BYTES + 1))
    with pytest.raises(RuntimeOperationError, match="read bound"):
        runtime.produce_output()
    assert runtime.snapshot().buffered_bytes == 0


def test_fixed_tmux_socket_cleanup_unlinks_exact_stale_identity() -> None:
    with tempfile.TemporaryDirectory(prefix="agentbox-sock-", dir="/tmp") as temporary:
        identity = fixed_identity()
        path = Path(temporary) / f"{identity.workspace_hash[:32]}.sock"
        directory_fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(path))
            details = os.lstat(path)
            listener.close()
            assert fixed_subject._remove_fixed_tmux_socket(
                identity, (details.st_dev, details.st_ino), directory_fd
            )
            assert not path.exists()
            assert fixed_subject._remove_fixed_tmux_socket(
                identity, (details.st_dev, details.st_ino), directory_fd
            )
        finally:
            listener.close()
            os.close(directory_fd)


def test_fixed_tmux_socket_cleanup_rejects_mismatched_inode() -> None:
    with tempfile.TemporaryDirectory(prefix="agentbox-sock-", dir="/tmp") as temporary:
        identity = fixed_identity()
        path = Path(temporary) / f"{identity.workspace_hash[:32]}.sock"
        directory_fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(path))
            details = os.lstat(path)
            with pytest.raises(RuntimeOperationError, match="identity changed"):
                fixed_subject._remove_fixed_tmux_socket(
                    identity, (details.st_dev, details.st_ino + 1), directory_fd
                )
            assert path.exists()
        finally:
            listener.close()
            path.unlink(missing_ok=True)
            os.close(directory_fd)


def _missing_tmux_socket(*_args: object) -> tuple[int, int]:
    try:
        raise FileNotFoundError("not created")
    except FileNotFoundError as exc:
        raise RuntimeOperationError(
            "WAW_START_UNCONFIRMED", "not created", category="conflict"
        ) from exc


def test_tmux_socket_wait_retries_only_missing_then_records_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations: list[tuple[int, int] | None] = [None, (11, 12)]

    def verify(*_args: object) -> tuple[int, int]:
        observed = observations.pop(0)
        if observed is None:
            return _missing_tmux_socket()
        return observed

    monkeypatch.setattr(fixed_subject, "_verify_fixed_tmux_socket", verify)
    monkeypatch.setattr(fixed_subject, "_peek_pidfd", lambda _fd: None)
    assert fixed_subject._wait_for_fixed_tmux_socket(fixed_identity(), -1, -1, 1.0) == (11, 12)


def test_tmux_socket_wait_fails_when_launcher_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fixed_subject, "_verify_fixed_tmux_socket", _missing_tmux_socket)
    monkeypatch.setattr(fixed_subject, "_peek_pidfd", lambda _fd: 7)
    with pytest.raises(RuntimeOperationError, match="exited before socket identity"):
        fixed_subject._wait_for_fixed_tmux_socket(fixed_identity(), -1, -1, 1.0)


def test_tmux_socket_wait_deadline_and_identity_errors_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fixed_subject, "_verify_fixed_tmux_socket", _missing_tmux_socket)
    monkeypatch.setattr(fixed_subject, "_peek_pidfd", lambda _fd: None)
    with pytest.raises(RuntimeOperationError, match="deadline expired"):
        fixed_subject._wait_for_fixed_tmux_socket(fixed_identity(), -1, -1, 0.0)

    invalid = RuntimeOperationError(
        "WAW_START_UNCONFIRMED", "identity is invalid", category="conflict"
    )

    def reject(*_args: object) -> tuple[int, int]:
        raise invalid

    monkeypatch.setattr(fixed_subject, "_verify_fixed_tmux_socket", reject)
    with pytest.raises(RuntimeOperationError, match="identity is invalid"):
        fixed_subject._wait_for_fixed_tmux_socket(fixed_identity(), -1, -1, 1.0)


def test_observed_nonchild_termination_closes_pidfd_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    monkeypatch.setattr(fixed_subject, "_signal_pidfd", lambda _fd, _signal: None)
    monkeypatch.setattr(fixed_subject, "_pidfd_exit_observed", lambda _fd, _timeout: True)
    monkeypatch.setattr(fixed_subject, "_close_fd", closed.append)
    monkeypatch.setattr(os, "killpg", lambda _group, _signal: None)
    fixed_subject._terminate_observed(41, 1.0, process_group=42)
    assert closed == [41]


def test_process_group_empty_waits_for_tmux_zombie_reap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = iter((True, True, False))
    monkeypatch.setattr(fixed_subject, "_process_group_exists", lambda _group: next(observations))
    assert fixed_subject._wait_process_group_empty(42, 1.0)


def test_process_group_empty_rejects_evidence_after_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fixed_subject, "_process_group_exists", lambda _group: True)
    assert not fixed_subject._wait_process_group_empty(42, 0.0)


def _native_redraw_port() -> tuple[
    NativeHelperProcessPort,
    FixedProcessBinding,
    Any,
]:
    identity = fixed_identity()
    resources = fixed_subject._NativeProcessResources(
        321,
        321,
        91,
        -1,
        -1,
        -1,
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, object()),
        (11, 12),
    )
    binding = FixedProcessBinding(identity, resources, object(), object())
    port = object.__new__(NativeHelperProcessPort)
    port._closed = False
    port._bindings = {id(binding): resources}
    port._helpers = cast(
        Any,
        SimpleNamespace(
            tmux_executable=7,
            tmux_socket_directory=8,
            tmux_config=9,
        ),
    )
    port._stop_timeout = 0.1
    return port, binding, resources


def test_native_redraw_uses_exact_identity_and_discards_row_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, binding, resources = _native_redraw_port()
    identity = binding.identity
    expected_identity = (
        "\t".join(
            (
                fixed_subject._fixed_tmux_session(identity),
                "$0",
                "1",
                "0",
                "@0",
                "1",
                "0",
                "%0",
                str(resources.pid),
                "0",
            )
        ).encode()
        + b"\n"
    )
    calls: list[tuple[tuple[str, ...], float, int]] = []

    def run(
        _identity: FixedProcessIdentity,
        operation: tuple[str, ...],
        deadline: float,
        limit: int,
    ) -> bytes:
        calls.append((operation, deadline, limit))
        return b"row\n" * 25 if operation[0] == "capture-pane" else expected_identity

    port._run_redraw_tmux = run  # type: ignore[method-assign,assignment]
    monkeypatch.setattr(fixed_subject, "_redraw_remaining", lambda _deadline: 1.0)
    monkeypatch.setattr(fixed_subject, "_verify_fixed_tmux_socket", lambda *_: (11, 12))
    monkeypatch.setattr(fixed_subject, "_pidfd_exit_observed", lambda *_: False)

    redraw = port.capture_redraw(binding, 42.0)

    assert redraw.payload == b"row\n" * 24 and redraw.has_more
    assert [call[0][0] for call in calls] == [
        "display-message",
        "capture-pane",
        "display-message",
    ]
    capture = calls[1][0]
    assert capture == (
        "capture-pane",
        "-p",
        "-t",
        fixed_subject._fixed_tmux_pane_target(identity),
        "-S",
        "0",
        "-E",
        "24",
    )
    assert all(deadline == 42.0 for _operation, deadline, _limit in calls)


def test_native_redraw_rejects_socket_or_pane_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, binding, _resources = _native_redraw_port()
    monkeypatch.setattr(fixed_subject, "_redraw_remaining", lambda _deadline: 1.0)
    monkeypatch.setattr(fixed_subject, "_verify_fixed_tmux_socket", lambda *_: (99, 100))
    monkeypatch.setattr(fixed_subject, "_pidfd_exit_observed", lambda *_: False)
    with pytest.raises(RuntimeOperationError, match="identity is unavailable"):
        port.capture_redraw(binding, 42.0)

    monkeypatch.setattr(fixed_subject, "_verify_fixed_tmux_socket", lambda *_: (11, 12))
    port._run_redraw_tmux = lambda *_args: b"wrong\n"  # type: ignore[method-assign]
    with pytest.raises(RuntimeOperationError, match="pane identity"):
        port.capture_redraw(binding, 42.0)


def test_fixed_tmux_client_uses_only_held_descriptor_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[int, tuple[str, ...], dict[str, str], tuple[tuple[int, int], ...]]] = []
    closed: list[int] = []
    real_close = os.close

    def spawn(
        executable: int,
        arguments: tuple[str, ...],
        environment: dict[str, str],
        descriptor_map: tuple[tuple[int, int], ...],
    ) -> int:
        observed.append((executable, arguments, environment, descriptor_map))
        stdout = next(source for source, destination in descriptor_map if destination == 1)
        os.write(stdout, b"bounded")
        return 321

    def close(descriptor: int) -> None:
        closed.append(descriptor)
        if descriptor != 91:
            real_close(descriptor)

    monkeypatch.setattr(fixed_subject, "_spawn_fixed", spawn)
    monkeypatch.setattr(os, "pidfd_open", lambda *_: 91, raising=False)
    monkeypatch.setattr(fixed_subject, "_wait_spawned_child", lambda *_: 0)
    monkeypatch.setattr(fixed_subject, "_redraw_remaining", lambda _deadline: 1.0)
    monkeypatch.setattr(fixed_subject, "_close_fd", close)

    result = fixed_subject._run_fixed_tmux_client(
        7,
        8,
        9,
        ("tmux", "-S", "/proc/self/fd/4/fixed.sock", "display-message"),
        42.0,
        32,
    )

    assert result == b"bounded"
    executable, arguments, environment, descriptor_map = observed[0]
    assert executable == 7 and arguments[0] == "tmux"
    assert environment["PATH"] == "/usr/bin"
    held = {
        (source, destination) for source, destination in descriptor_map if destination in {4, 5}
    }
    assert held == {
        (8, 4),
        (9, 5),
    }
    assert closed.count(91) == 1


def test_fixed_tmux_client_transfers_unreaped_pidfd_without_closing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    real_close = os.close

    def spawn(
        _executable: int,
        _arguments: tuple[str, ...],
        _environment: dict[str, str],
        descriptor_map: tuple[tuple[int, int], ...],
    ) -> int:
        stdout = next(source for source, destination in descriptor_map if destination == 1)
        os.write(stdout, b"partial")
        return 321

    def close(descriptor: int) -> None:
        closed.append(descriptor)
        if descriptor != 91:
            real_close(descriptor)

    monkeypatch.setattr(fixed_subject, "_spawn_fixed", spawn)
    monkeypatch.setattr(os, "pidfd_open", lambda *_: 91, raising=False)
    monkeypatch.setattr(fixed_subject, "_wait_spawned_child", lambda *_: None)
    monkeypatch.setattr(fixed_subject, "_kill_and_reap_redraw_child", lambda *_: False)
    monkeypatch.setattr(fixed_subject, "_redraw_remaining", lambda _deadline: 1.0)
    monkeypatch.setattr(fixed_subject, "_close_fd", close)

    with pytest.raises(fixed_subject._WAWRedrawChildUnreaped) as raised:
        fixed_subject._run_fixed_tmux_client(
            7,
            8,
            9,
            ("tmux", "display-message"),
            42.0,
            32,
        )
    assert raised.value.pidfd == 91
    assert 91 not in closed


def test_native_redraw_poison_retains_unreaped_child_until_stop_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, binding, _resources = _native_redraw_port()

    def unreaped(*_args: object) -> bytes:
        raise fixed_subject._WAWRedrawChildUnreaped(321, 91)

    monkeypatch.setattr(fixed_subject, "_run_fixed_tmux_client", unreaped)
    with pytest.raises(RuntimeOperationError, match="cleanup is incomplete"):
        port._run_redraw_tmux(binding.identity, ("capture-pane",), 42.0, 32)
    assert port._redraw_poisoned and port._redraw_children == [(321, 91)]
    with pytest.raises(RuntimeOperationError, match="unavailable"):
        port.capture_redraw(binding, 42.0)

    monkeypatch.setattr(fixed_subject, "_kill_and_reap_redraw_child", lambda *_: False)
    assert not port._cleanup_redraw_children(42.0)
    assert port._redraw_children == [(321, 91)]


def test_fixed_transport_passes_opaque_binding_to_redraw_port(tmp_path: Path) -> None:
    item = fixed_identity()
    port = FakeNativePort()
    fixed = transport(item, port)
    fixed.start(command(tmp_path, item), PtyGeometry(80, 24))
    port.redraw = BoundedRedraw(b"screen", False)

    assert fixed.capture_redraw(42.0) == port.redraw
    assert port.redraw_calls == [(fixed._inspector.binding, 42.0)]


def test_unpopulated_stop_remains_fenced_for_exact_destroy_retry(tmp_path: Path) -> None:
    item = fixed_identity()
    port = FakeNativePort()
    fixed = transport(item, port)
    fixed.start(command(tmp_path, item), PtyGeometry(80, 24))
    port.stop_members = 1
    with pytest.raises(RuntimeOperationError, match="populated=0"):
        fixed.stop()
    assert fixed.stop().remaining_members == 0
    assert port.stop_calls == 2


def test_stop_never_reports_zero_until_attachment_reap_is_confirmed(tmp_path: Path) -> None:
    item = fixed_identity()
    port = FakeNativePort()
    runtime = supervisor(tmp_path, item, transport(item, port))
    runtime.start()
    active = lease(item)
    runtime.reserve_runtime_attachment(active)
    runtime.commit_runtime_attachment(active)
    port.attachments[0].cleanup_members = [1, 0]
    operation = WorkspaceStopOperation(WORKSPACE, PROJECT, AgentType.CODEX, 1, 1, DIGEST, HOST, 1)
    with pytest.raises(RuntimeOperationError):
        runtime.exact_stop(operation)
    assert runtime.state is not SupervisorState.STOPPED
    assert runtime.exact_stop(operation).state is SupervisorState.STOPPED


class _CgroupControl:
    def __init__(self, *, wait_empty: bool = True) -> None:
        self.calls: list[str] = []
        self._frozen = 0
        self._populated = 1
        self._wait_empty = wait_empty

    def populated(self) -> int:
        self.calls.append("populated")
        return self._populated

    def freeze(self) -> None:
        self.calls.append("freeze")
        self._frozen = 1

    def frozen(self) -> int:
        self.calls.append("frozen")
        return self._frozen

    def kill(self) -> None:
        self.calls.append("kill")
        if self._wait_empty:
            self._populated = 0

    def wait_empty(self, timeout_seconds: float) -> bool:
        self.calls.append(f"wait:{timeout_seconds}")
        return self._wait_empty

    def thaw(self) -> None:
        self.calls.append("thaw")
        self._frozen = 0

    def contains_pidfd(self, pidfd: int) -> bool:
        return pidfd >= 0


def test_cgroup_stop_freezes_kills_waits_empty_then_thaws() -> None:
    cgroup = _CgroupControl()
    fixed_subject._force_cgroup_empty(cgroup, 1.0)
    assert cgroup.calls == [
        "freeze",
        "frozen",
        "kill",
        "wait:1.0",
        "populated",
        "thaw",
        "frozen",
    ]


def test_cgroup_stop_timeout_keeps_frozen_quarantine() -> None:
    cgroup = _CgroupControl(wait_empty=False)
    with pytest.raises(RuntimeOperationError, match="populated=0"):
        fixed_subject._force_cgroup_empty(cgroup, 1.0)
    assert cgroup._frozen == 1
    assert "thaw" not in cgroup.calls


def test_attachment_cleanup_timeout_retains_fds_and_later_reap_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master_read, master_write = os.pipe()
    pidfd_read, pidfd_write = os.pipe()
    outcomes = iter([None, None, 0])
    monkeypatch.setattr(fixed_subject, "_signal_pidfd", lambda *_args: None)
    monkeypatch.setattr(os, "killpg", lambda *_args: None)
    monkeypatch.setattr(fixed_subject, "_wait_pidfd", lambda *_args: next(outcomes))
    attachment = fixed_subject._NativeAttachment(
        pid=123,
        pidfd=pidfd_read,
        master=master_read,
        lease=lease(fixed_identity()),
        process=cast(Any, object()),
        stop_timeout=0.01,
    )
    first = attachment.close()
    assert not first.closed and first.remaining_members == 1
    os.fstat(master_read)
    os.fstat(pidfd_read)
    with pytest.raises(RuntimeOperationError, match="cleanup-fenced"):
        attachment.write_input(b"blocked")
    second = attachment.close()
    assert second.closed and second.remaining_members == 0
    with pytest.raises(OSError):
        os.fstat(master_read)
    with pytest.raises(OSError):
        os.fstat(pidfd_read)
    os.close(master_write)
    os.close(pidfd_write)


def test_attachment_unretryable_failure_never_later_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master_read, master_write = os.pipe()
    pidfd_read, pidfd_write = os.pipe()
    monkeypatch.setattr(
        fixed_subject,
        "_signal_pidfd",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("uncertain pidfd")),
    )
    attachment = fixed_subject._NativeAttachment(
        pid=123,
        pidfd=pidfd_read,
        master=master_read,
        lease=lease(fixed_identity()),
        process=cast(Any, object()),
        stop_timeout=0.01,
    )
    assert not attachment.close().closed
    assert not attachment.close().closed
    os.fstat(master_read)
    os.fstat(pidfd_read)
    for descriptor in (master_read, master_write, pidfd_read, pidfd_write):
        os.close(descriptor)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        NATIVE_READY[:7],
        b"BWR1\x01\x01\x00\x00",
        b"AWR1\x02\x01\x00\x00",
        b"AWR1\x01\x02\x00\x00",
        b"AWR1\x01\x01\x00\x01",
        NATIVE_READY + b"x",
        NATIVE_READY + b"xy",
    ],
)
@pytest.mark.skipif(platform.system() != "Linux", reason="Linux SOCK_SEQPACKET READY gate")
def test_native_ready_rejects_eof_partial_wrong_and_oversized(payload: bytes) -> None:
    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        if payload:
            sender.send(payload)
        else:
            sender.close()
        with pytest.raises(RuntimeOperationError, match="READY"):
            receive_native_ready(receiver, timeout_seconds=0.1)
    finally:
        receiver.close()
        sender.close()


@pytest.mark.skipif(platform.system() != "Linux", reason="Linux SOCK_SEQPACKET READY gate")
def test_native_ready_accepts_exact_packet_and_rejects_timeout() -> None:
    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        sender.send(NATIVE_READY)
        receive_native_ready(receiver)
    finally:
        receiver.close()
        sender.close()

    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        with pytest.raises(RuntimeOperationError, match="deadline"):
            receive_native_ready(receiver, timeout_seconds=0.01)
    finally:
        receiver.close()
        sender.close()


def test_native_ready_rejects_non_unix_domain_before_read() -> None:
    class WrongDomain:
        def getsockopt(self, _level: int, option: int, *_args: int) -> int:
            return socket.SOCK_SEQPACKET if option == socket.SO_TYPE else socket.AF_INET

    with pytest.raises(RuntimeOperationError, match="endpoint is invalid"):
        receive_native_ready(WrongDomain())  # type: ignore[arg-type]
