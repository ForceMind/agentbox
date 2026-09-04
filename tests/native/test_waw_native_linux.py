from __future__ import annotations

import array
import errno
import hashlib
import json
import os
import platform
import pty
import re
import select
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from agentbox_core.waw import AgentType, managed_marker, workspace_id
from agentbox_core.waw_tickets import AttachmentTuple
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_fixed_transport import (
    NativeHelperHandles,
    NativeHelperProcessPort,
)
from agentbox_runtime.waw_process_inspector import (
    FixedAttachmentRequest,
    FixedLaunchHandles,
    FixedLaunchRequest,
    FixedProcessIdentity,
    FixedStartState,
)
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_supervisor import RuntimeAttachmentLease, RuntimeProbeState

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "scripts" / "build-waw-native.py"
HASH = "a" * 64
PROFILE = "b" * 64
PROJECT = "prj_" + "1" * 32
WORKSPACE = workspace_id(PROJECT, AgentType.CLAUDE)
HOST = "wri_" + "2" * 32
LINUX = platform.system() == "Linux"
HOST_GATE = os.environ.get("AGENTBOX_WAW_NATIVE_HOST_GATE") == "1"
O_PATH = getattr(os, "O_PATH", 0)
TMUX_SOCKET = Path("/run/agentbox-waw/tmux") / f"{HASH[:32]}.sock"
TMUX_CONFIG = (
    ROOT
    / "packages"
    / "agentbox-runtime"
    / "src"
    / "agentbox_runtime"
    / "assets"
    / "waw-inert"
    / "tmux.conf"
)
TMUX_ENV = {
    "HOME": "/nonexistent",
    "PATH": "/usr/bin",
    "LANG": "C.UTF-8",
    "LC_CTYPE": "C.UTF-8",
    "TERM": "xterm-256color",
}

pytestmark = pytest.mark.skipif(
    not LINUX or not HOST_GATE, reason="dedicated Linux native helper host gate"
)


@pytest.fixture(scope="session", autouse=True)
def linux_native_host_gate() -> Iterator[object]:
    if not LINUX:
        yield None
        return
    tmux = shutil.which("tmux")
    assert tmux == "/usr/bin/tmux"
    required = (
        Path("/run/agentbox-waw/tmux"),
        Path("/run/agentbox-waw/tmp") / HASH,
        Path("/var/lib/agentbox-waw/vendor-homes/claude"),
        Path("/var/lib/agentbox-waw/vendor-homes/codex"),
        Path("/etc/claude-code"),
        Path("/etc/codex"),
    )
    assert all(path.is_dir() for path in required)
    _kill_tmux_server()
    control_path = Path("/run/agentbox-waw/workspace-control.sock")
    control_path.unlink(missing_ok=True)
    control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    control.bind(str(control_path))
    control.listen(1)
    yield {"tmux": tmux, "control": control}
    _kill_tmux_server()
    control.close()
    control_path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def linux_native_test_cleanup() -> Iterator[None]:
    yield
    if LINUX and HOST_GATE:
        _kill_tmux_server()


@pytest.fixture(scope="session")
def native_binaries(tmp_path_factory: pytest.TempPathFactory) -> Path:
    configured = os.environ.get("AGENTBOX_WAW_NATIVE_BIN_DIR")
    if configured:
        return (ROOT / configured).resolve()
    output = tmp_path_factory.mktemp("waw-native-bin")
    subprocess.run([sys.executable, str(BUILD), "--output", str(output)], check=True, cwd=ROOT)
    return output


@pytest.fixture(scope="session")
def fake_binaries(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    output = tmp_path_factory.mktemp("waw-native-fakes")
    common = [
        os.environ.get("CC", "cc"),
        "-std=c17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wpedantic",
        "-fPIE",
        "-pie",
        "-fstack-protector-strong",
        "-D_FORTIFY_SOURCE=3",
        "-pthread",
    ]
    vendor = output / "fake-vendor"
    attach = output / "fake-attach"
    subprocess.run(
        [*common, str(ROOT / "tests" / "native" / "fake_vendor.c"), "-o", str(vendor)],
        check=True,
    )
    subprocess.run(
        [
            *common,
            str(ROOT / "tests" / "native" / "fake_attach_target.c"),
            "-o",
            str(attach),
        ],
        check=True,
    )
    return vendor, attach


def _launch_record(agent: str = "claude", *, extra: bool = False) -> bytes:
    value: dict[str, object] = {
        "agent": agent,
        "fd_role_bitmap": 127,
        "generation": "7",
        "initial_geometry": {"columns": 80, "rows": 24},
        "profile_digest": PROFILE,
        "runtime_gid": os.getegid(),
        "runtime_uid": os.geteuid(),
        "schema": "agentbox-waw-launch-v1",
        "type": "interactive",
        "workspace_hash": HASH,
    }
    if extra:
        value["command"] = "rejected"
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


_FD_EXEC_SHIM = """
import fcntl
import os
import sys

make_session = sys.argv[1] == "1"
separator = sys.argv.index("--", 2)
mapping = [tuple(map(int, item.split(":"))) for item in sys.argv[2:separator]]
arguments = sys.argv[separator + 1:]
if make_session:
    os.setsid()
duplicated = []
try:
    for source, destination in mapping:
        duplicated.append((fcntl.fcntl(source, fcntl.F_DUPFD_CLOEXEC, 64), destination))
    for source, destination in duplicated:
        os.dup2(source, destination, inheritable=True)
finally:
    for source, _destination in duplicated:
        os.close(source)
os.execv(arguments[0], arguments)
"""


def _popen_with_fd_mapping(
    arguments: list[str],
    mapping: dict[int, int],
    *,
    make_session: bool = False,
    **kwargs: Any,
) -> subprocess.Popen[bytes]:
    mapping_arguments = [f"{source}:{destination}" for source, destination in mapping.items()]
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            _FD_EXEC_SHIM,
            "1" if make_session else "0",
            *mapping_arguments,
            "--",
            *arguments,
        ],
        pass_fds=tuple(mapping),
        **kwargs,
    )


def _read_fd_until(descriptor: int, needle: bytes, timeout: float = 5.0) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while needle not in output:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"timed out waiting for {needle!r}: {bytes(output)!r}")
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            continue
        try:
            chunk = os.read(descriptor, 4096)
        except BlockingIOError:
            continue
        if not chunk:
            break
        output.extend(chunk)
    return bytes(output)


def _read_attachment_until(attachment: Any, needle: bytes, timeout: float = 5.0) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while needle not in output:
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out waiting for {needle!r}: {bytes(output)!r}")
        chunk = attachment.read_output(32768)
        if chunk:
            output.extend(chunk)
        else:
            time.sleep(0.01)
    return bytes(output)


def _write_host_namespace_record(project: Path) -> None:
    values = [os.stat(f"/proc/self/ns/{name}").st_ino for name in ("user", "mnt", "pid", "ipc")]
    (project / ".host-namespaces").write_text(" ".join(str(value) for value in values) + "\n")


def _write_mount_canaries(home: Path, temporary: Path, policy: Path) -> None:
    (home / ".home-mount-canary").write_text("home\n")
    (temporary / ".temp-mount-canary").write_text("temp\n")
    (policy / "policy-mount-canary").write_text("policy\n")


def _spawn_real_attach(
    native_binaries: Path, agent: str, *, expect_ready: bool = True
) -> tuple[subprocess.Popen[bytes], int]:
    executable_fd = os.open("/usr/bin/tmux", os.O_RDONLY | os.O_CLOEXEC)
    directory_fd = os.open(TMUX_SOCKET.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    config_fd = os.open(TMUX_CONFIG, os.O_RDONLY | os.O_CLOEXEC)
    ready_parent, ready_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    master, slave = pty.openpty()
    process = _popen_with_fd_mapping(
        [
            str(native_binaries / "agentbox-waw-attach-supervisor"),
            "--workspace-hash",
            HASH,
            "--agent-type",
            agent,
        ],
        {
            executable_fd: 3,
            directory_fd: 4,
            config_fd: 5,
            ready_child.fileno(): 6,
        },
        make_session=True,
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    os.close(slave)
    os.close(executable_fd)
    os.close(directory_fd)
    os.close(config_fd)
    ready_child.close()
    ready_parent.settimeout(5.0)
    ready = ready_parent.recv(9)
    expected_ready = b"AWR1\x01\x01\x00\x00" if expect_ready else b""
    if ready != expected_ready:
        status = process.wait(timeout=5)
        os.close(master)
        pytest.fail(f"attach READY failed with status {status}")
    ready_parent.close()
    return process, master


class _CgroupSequence:
    def __init__(self, values: list[int]) -> None:
        self._values = values
        self._frozen = 0

    def populated(self) -> int:
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]

    def freeze(self) -> None:
        self._frozen = 1

    def frozen(self) -> int:
        return self._frozen

    def kill(self) -> None:
        self._values = [0]

    def wait_empty(self, timeout_seconds: float) -> bool:
        return 0 < timeout_seconds <= 10 and self.populated() == 0

    def thaw(self) -> None:
        self._frozen = 0

    def contains_pidfd(self, pidfd: int) -> bool:
        return pidfd >= 0


def _fixed_identity() -> FixedProcessIdentity:
    marker = managed_marker(
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        project_id=PROJECT,
        agent_type=AgentType.CLAUDE,
        workspace_id_value=WORKSPACE,
        generation=7,
        binding_revision=1,
        binding_digest="d" * 64,
    )
    return FixedProcessIdentity(
        WORKSPACE,
        PROJECT,
        AgentType.CLAUDE,
        7,
        HASH,
        marker,
        PROFILE,
        HOST,
        "1",
        "9",
    )


def _kill_tmux_server() -> None:
    expected = _tmux_socket_identity()
    if expected is None:
        return
    subprocess.run(
        ["/usr/bin/tmux", "-S", str(TMUX_SOCKET), "kill-server"],
        capture_output=True,
        check=False,
        timeout=5,
    )
    deadline = time.monotonic() + 5.0
    while _tmux_server_responds():
        if time.monotonic() >= deadline:
            raise AssertionError("dedicated tmux server did not exit")
        time.sleep(0.02)
    if expected is not None:
        _unlink_stale_tmux_socket(expected)


def _tmux_socket_identity() -> tuple[int, int, int] | None:
    try:
        details = TMUX_SOCKET.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.geteuid():
        raise AssertionError("dedicated tmux socket identity is invalid")
    return details.st_dev, details.st_ino, details.st_uid


def _tmux_server_responds() -> bool:
    return (
        subprocess.run(
            ["/usr/bin/tmux", "-S", str(TMUX_SOCKET), "show-options", "-s", "-v", "exit-empty"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _unlink_stale_tmux_socket(expected: tuple[int, int, int]) -> None:
    observed = _tmux_socket_identity()
    if observed is None:
        return
    if observed != expected:
        raise AssertionError("dedicated tmux socket identity changed")
    TMUX_SOCKET.unlink()
    if _tmux_socket_identity() is not None:
        raise AssertionError("dedicated tmux socket unlink was not observed")


def _begin_real_workspace(
    native_binaries: Path,
    vendor: Path,
    tmp_path: Path,
    *,
    agent: str = "claude",
    launch: bytes | None = None,
    delete_policy_after_open: bool = False,
    tmux_config: Path = TMUX_CONFIG,
) -> tuple[str, socket.socket, socket.socket]:
    _kill_tmux_server()
    launch_path = Path("/run/agentbox-waw/tmp") / HASH / "launch.v1.sock"
    launch_path.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    listener.bind(str(launch_path))
    listener.listen(1)
    listener.settimeout(5.0)
    project = tmp_path / "project"
    home = tmp_path / "home"
    temporary = tmp_path / "temp"
    policy = tmp_path / "policy"
    for directory in (project, home, temporary, policy):
        directory.mkdir()
    _write_host_namespace_record(project)
    _write_mount_canaries(home, temporary, policy)
    wbr_parent, wbr_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    role_fds = [
        os.open(project, O_PATH | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(native_binaries / "agentbox-waw-bridge", os.O_RDONLY | os.O_CLOEXEC),
        os.open(vendor, os.O_RDONLY | os.O_CLOEXEC),
        os.open(policy, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        wbr_child.fileno(),
    ]
    if delete_policy_after_open:
        (policy / "policy-mount-canary").unlink()
        policy.rmdir()
    session = f"agentbox-waw-{agent}-{HASH[:32]}"
    subprocess.run(
        [
            "/usr/bin/tmux",
            "-S",
            str(TMUX_SOCKET),
            "-f",
            str(tmux_config),
            "new-session",
            "-d",
            "-s",
            session,
            str(native_binaries / "agentbox-waw-pane-bootstrap"),
            "--workspace-hash",
            HASH,
            "--agent-type",
            agent,
        ],
        check=True,
        env=TMUX_ENV,
    )
    control, _address = listener.accept()
    control.settimeout(5.0)
    listener.close()
    server_pid = int(
        subprocess.run(
            ["/usr/bin/tmux", "-S", str(TMUX_SOCKET), "display-message", "-p", "#{pid}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    pane_pid = int(
        subprocess.run(
            [
                "/usr/bin/tmux",
                "-S",
                str(TMUX_SOCKET),
                "list-panes",
                "-t",
                f"={session}:0",
                "-F",
                "#{pane_pid}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    expected_cgroup = f"/ws-{HASH}-g7/workload"
    assert expected_cgroup in Path("/proc/self/cgroup").read_text()
    assert expected_cgroup in Path(f"/proc/{server_pid}/cgroup").read_text()
    assert expected_cgroup in Path(f"/proc/{pane_pid}/cgroup").read_text()
    control.sendmsg(
        [launch or _launch_record(agent)],
        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", role_fds))],
    )
    wbr_child.close()
    for descriptor in role_fds[:-1]:
        os.close(descriptor)
    launch_path.unlink(missing_ok=True)
    return session, control, wbr_parent


def _wait_session_gone(session: str, timeout: float = 10.0) -> None:
    expected = _tmux_socket_identity()
    if expected is None:
        raise AssertionError("dedicated tmux socket disappeared before session cleanup")
    deadline = time.monotonic() + timeout
    while (
        subprocess.run(
            ["/usr/bin/tmux", "-S", str(TMUX_SOCKET), "has-session", "-t", f"={session}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    ):
        if time.monotonic() >= deadline:
            raise AssertionError("dedicated tmux session did not exit")
        time.sleep(0.02)
    deadline = time.monotonic() + timeout
    while _tmux_server_responds():
        if time.monotonic() >= deadline:
            raise AssertionError("dedicated tmux server did not exit")
        time.sleep(0.02)
    _unlink_stale_tmux_socket(expected)


def _wbr_resize(sequence: int, columns: int, rows: int) -> bytes:
    return struct.pack(
        "!4sBBHQQHHB35s", b"WBR1", 1, 1, 0, sequence, 7, columns, rows, 0, b"\x00" * 35
    )


def test_bootstrap_bridge_execveat_pty_resize_relay_and_reap(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    session, control, wbr = _begin_real_workspace(native_binaries, fake_binaries[0], tmp_path)
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    attached, master = _spawn_real_attach(native_binaries, "claude")
    startup = _read_fd_until(master, b"SIZE 80 24")
    assert b"READY claude" in startup

    resize = _wbr_resize(1, 100, 40)
    wbr.send(resize)
    acknowledgment = wbr.recv(128)
    assert len(acknowledgment) == 64
    assert acknowledgment[5] == 2
    assert acknowledgment[28] == 1
    assert struct.unpack("!Q", acknowledgment[8:16])[0] == 1

    os.write(master, b"size\nhello\nexit7\n")
    output = _read_fd_until(master, b"ECHO hello")
    assert b"SIZE 100 40" in output
    assert attached.wait(timeout=10) in {0, 1, 7, 143, -signal.SIGTERM}
    os.close(master)
    _wait_session_gone(session)
    control.close()
    wbr.close()


def test_codex_fixed_profile_uses_same_isolated_native_path(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    session, control, wbr = _begin_real_workspace(
        native_binaries, fake_binaries[0], tmp_path, agent="codex"
    )
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    attached, master = _spawn_real_attach(native_binaries, "codex")
    startup = _read_fd_until(master, b"READY codex")
    assert b"SIZE 80 24" in startup
    os.write(master, b"exit7\n")
    assert attached.wait(timeout=10) in {0, 1, 7, 143, -signal.SIGTERM}
    os.close(master)
    _wait_session_gone(session)
    control.close()
    wbr.close()


def test_bridge_vendor_exec_failure_never_emits_ready_and_reaps(
    native_binaries: Path, tmp_path: Path
) -> None:
    invalid_vendor = tmp_path / "invalid-vendor"
    invalid_vendor.write_text("#!/definitely/missing/interpreter\n")
    invalid_vendor.chmod(0o755)
    session, control, wbr = _begin_real_workspace(native_binaries, invalid_vendor, tmp_path)
    assert control.recv(9) == b""
    _wait_session_gone(session)
    control.close()
    wbr.close()


def test_deleted_held_directory_hint_fails_before_ready_and_vendor(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    session, control, wbr = _begin_real_workspace(
        native_binaries,
        fake_binaries[0],
        tmp_path,
        delete_policy_after_open=True,
    )
    assert control.recv(9) == b""
    _wait_session_gone(session)
    control.close()
    wbr.close()


def test_bootstrap_rejects_forged_tmux_environment(native_binaries: Path) -> None:
    control_parent, control_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    process = _popen_with_fd_mapping(
        [
            str(native_binaries / "agentbox-waw-pane-bootstrap"),
            "--workspace-hash",
            HASH,
            "--agent-type",
            "claude",
        ],
        {control_child.fileno(): 3},
        env={"TMUX": "/run/forged,1,0", "TMUX_PANE": "%1"},
    )
    control_child.close()
    control_parent.close()
    assert process.wait(timeout=5) == 65


def test_bootstrap_rejects_correct_socket_from_non_tmux_parent(native_binaries: Path) -> None:
    _kill_tmux_server()
    subprocess.run(
        [
            "/usr/bin/tmux",
            "-S",
            str(TMUX_SOCKET),
            "-f",
            str(TMUX_CONFIG),
            "new-session",
            "-d",
            "-s",
            "parent-gate",
            "/usr/bin/sleep",
            "3600",
        ],
        check=True,
        env=TMUX_ENV,
    )
    process = subprocess.run(
        [
            str(native_binaries / "agentbox-waw-pane-bootstrap"),
            "--workspace-hash",
            HASH,
            "--agent-type",
            "claude",
        ],
        env={"TMUX": f"{TMUX_SOCKET},1,0", "TMUX_PANE": "%1"},
        check=False,
    )
    assert process.returncode == 65
    _kill_tmux_server()


def test_real_tmux_server_has_exact_inert_options_and_no_key_tables() -> None:
    _kill_tmux_server()
    subprocess.run(
        [
            "/usr/bin/tmux",
            "-S",
            str(TMUX_SOCKET),
            "-f",
            str(TMUX_CONFIG),
            "new-session",
            "-d",
            "-s",
            "native-config-gate",
            "/usr/bin/sleep",
            "3600",
        ],
        check=True,
        env=TMUX_ENV,
    )
    expected = {
        ("-g", "prefix"): "None",
        ("-g", "allow-passthrough"): "off",
        ("-s", "set-clipboard"): "off",
        ("-s", "exit-empty"): "on",
        ("-g", "update-environment"): "",
        ("-g", "status"): "off",
        ("-g", "default-shell"): "/bin/false",
        ("-g", "default-command"): "/bin/false",
        ("-g", "history-limit"): "25",
        ("-g", "remain-on-exit"): "off",
        ("-g", "allow-rename"): "off",
        ("-g", "set-titles"): "off",
    }
    for (scope, option), value in expected.items():
        observed = subprocess.run(
            [
                "/usr/bin/tmux",
                "-S",
                str(TMUX_SOCKET),
                "show-options",
                scope,
                "-v",
                option,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.rstrip("\n")
        assert observed == value
    for table in ("prefix", "root", "copy-mode", "copy-mode-vi"):
        listed = subprocess.run(
            ["/usr/bin/tmux", "-S", str(TMUX_SOCKET), "list-keys", "-T", table],
            check=False,
            capture_output=True,
            text=True,
        )
        assert listed.stdout == ""
    _kill_tmux_server()


def test_bootstrap_rejects_noncanonical_or_open_ended_launch_before_vendor(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    session, control, wbr = _begin_real_workspace(
        native_binaries, fake_binaries[0], tmp_path, launch=_launch_record(extra=True)
    )
    assert control.recv(9) == b""
    _wait_session_gone(session)
    control.close()
    wbr.close()


def test_bridge_rejects_oversized_wbr_and_reaps_vendor(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    session, control, wbr = _begin_real_workspace(native_binaries, fake_binaries[0], tmp_path)
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    wbr.send(_wbr_resize(1, 80, 24) + b"x")
    _wait_session_gone(session)
    control.close()
    wbr.close()


def test_bridge_wbr_hup_cleans_vendor_without_busy_loop(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    session, control, wbr = _begin_real_workspace(native_binaries, fake_binaries[0], tmp_path)
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    wbr.close()
    _wait_session_gone(session)
    control.close()


def test_bridge_tmux_parent_death_cleans_vendor_without_spin(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    _session, control, wbr = _begin_real_workspace(native_binaries, fake_binaries[0], tmp_path)
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    attached, master = _spawn_real_attach(native_binaries, "claude")
    _read_fd_until(master, b"READY claude")
    _kill_tmux_server()
    assert attached.wait(timeout=5) in {0, 1, 143, -signal.SIGTERM}
    os.close(master)
    control.close()
    wbr.close()


def test_bridge_flushes_large_vendor_tail_after_child_exit(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    capture_config = tmp_path / "capture-tmux.conf"
    capture_config.write_bytes(
        TMUX_CONFIG.read_bytes()
        + b"\nset-option -g history-limit 4096\nset-option -g remain-on-exit on\n"
    )
    session, control, wbr = _begin_real_workspace(
        native_binaries, fake_binaries[0], tmp_path, tmux_config=capture_config
    )
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    attached, master = _spawn_real_attach(native_binaries, "claude")
    _read_fd_until(master, b"READY claude")
    drain_errors: list[OSError] = []

    def drain_attach_output() -> None:
        while True:
            try:
                chunk = os.read(master, 65536)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    drain_errors.append(exc)
                return
            if not chunk:
                return

    drainer = threading.Thread(target=drain_attach_output, daemon=True)
    drainer.start()
    os.write(master, b"tail\n")
    deadline = time.monotonic() + 5.0
    pane_status = ""
    while pane_status != "1:7":
        pane_status = subprocess.run(
            [
                "/usr/bin/tmux",
                "-S",
                str(TMUX_SOCKET),
                "list-panes",
                "-t",
                f"={session}:0.0",
                "-F",
                "#{pane_dead}:#{pane_dead_status}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if time.monotonic() >= deadline:
            raise AssertionError(f"tail pane did not exit cleanly: {pane_status}")
        time.sleep(0.01)
    attached.send_signal(signal.SIGTERM)
    assert attached.wait(timeout=5) in {0, 1, 143, -signal.SIGTERM}
    drainer.join(timeout=5)
    assert not drainer.is_alive() and not drain_errors
    os.close(master)
    pane_metrics = subprocess.run(
        [
            "/usr/bin/tmux",
            "-S",
            str(TMUX_SOCKET),
            "list-panes",
            "-t",
            f"={session}:0.0",
            "-F",
            "#{pane_width}:#{pane_height}:#{history_size}",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    history_limit = subprocess.run(
        [
            "/usr/bin/tmux",
            "-S",
            str(TMUX_SOCKET),
            "show-options",
            "-w",
            "-v",
            "-t",
            f"={session}:0",
            "history-limit",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    captured = subprocess.run(
        [
            "/usr/bin/tmux",
            "-S",
            str(TMUX_SOCKET),
            "capture-pane",
            "-p",
            "-S",
            "-",
            "-E",
            "-",
            "-t",
            f"={session}:0.0",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    control.close()
    wbr.close()
    _kill_tmux_server()
    payload = "0123456789abcdef0123456789abcdef"
    expected = [f"TAIL {index:04d} {payload}" for index in range(2048)]
    observed = [line for line in captured if re.fullmatch(r"TAIL [0-9]{4} [0-9a-f]{32}", line)]
    assert sum(len(line) + 1 for line in observed) > 65536
    if observed != expected:
        indices = [int(line[5:9]) for line in observed]
        counts = Counter(indices)
        discontinuity = next(
            (
                (position, position, value)
                for position, value in enumerate(indices)
                if value != position
            ),
            None,
        )
        missing = sorted(set(range(2048)) - set(indices))[:5]
        duplicates = [value for value, count in sorted(counts.items()) if count > 1][:5]
        mismatch = next(
            (
                index
                for index, pair in enumerate(zip(observed, expected, strict=False))
                if pair[0] != pair[1]
            ),
            min(len(observed), len(expected)),
        )
        observed_value = observed[mismatch] if mismatch < len(observed) else "<missing>"
        expected_value = expected[mismatch] if mismatch < len(expected) else "<none>"
        pytest.fail(
            f"tail history mismatch matched={len(observed)} captured={len(captured)} "
            f"bytes={sum(len(line) + 1 for line in observed)} metrics={pane_metrics} "
            f"limit={history_limit} first={indices[0] if indices else None} "
            f"last={indices[-1] if indices else None} unique={len(counts)} "
            f"discontinuity={discontinuity} missing={missing} duplicates={duplicates} "
            f"index={mismatch} expected={expected_value!r} observed={observed_value!r}"
        )
    assert (
        hashlib.sha256("\n".join(observed).encode()).digest()
        == hashlib.sha256("\n".join(expected).encode()).digest()
    )
    assert any(line.strip() == "TAIL-END" for line in captured)
    assert any("TAIL-NOISE-END" in line for line in captured)


def test_real_tmux_detach_reattach_preserves_vendor_pid_and_reaps_descendants(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    _kill_tmux_server()
    launch_path = Path("/run/agentbox-waw/tmp") / HASH / "launch.v1.sock"
    launch_path.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    listener.bind(str(launch_path))
    listener.listen(1)
    project = tmp_path / "tmux-project"
    home = tmp_path / "tmux-home"
    temporary = tmp_path / "tmux-temp"
    policy = tmp_path / "tmux-policy"
    for directory in (project, home, temporary, policy):
        directory.mkdir()
    _write_host_namespace_record(project)
    _write_mount_canaries(home, temporary, policy)
    wbr_parent, wbr_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    role_fds = [
        os.open(project, O_PATH | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(native_binaries / "agentbox-waw-bridge", os.O_RDONLY | os.O_CLOEXEC),
        os.open(fake_binaries[0], os.O_RDONLY | os.O_CLOEXEC),
        os.open(policy, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        wbr_child.fileno(),
    ]
    session = f"agentbox-waw-claude-{HASH[:32]}"
    subprocess.run(
        [
            "/usr/bin/tmux",
            "-S",
            str(TMUX_SOCKET),
            "-f",
            str(TMUX_CONFIG),
            "new-session",
            "-d",
            "-s",
            session,
            str(native_binaries / "agentbox-waw-pane-bootstrap"),
            "--workspace-hash",
            HASH,
            "--agent-type",
            "claude",
        ],
        check=True,
        env=TMUX_ENV,
    )
    listener.settimeout(5.0)
    launch, _address = listener.accept()
    launch.settimeout(5.0)
    launch.sendmsg(
        [_launch_record()],
        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", role_fds))],
    )
    assert launch.recv(9) == b"AWR1\x01\x01\x00\x00"
    wbr_child.close()
    for descriptor in role_fds[:-1]:
        os.close(descriptor)

    first, first_master = _spawn_real_attach(native_binaries, "claude")
    _read_fd_until(first_master, b"READY claude")
    os.write(first_master, b"pid\n")
    first_output = _read_fd_until(first_master, b"PID ")
    first_matches = re.findall(rb"PID ([0-9]+)", first_output)
    assert first_matches
    first_pid = first_matches[-1]
    os.write(first_master, b"\x02c\ntmux new-window\nrespawn-pane\nset-option\ncontrols\n")
    controls = _read_fd_until(first_master, b"CONTROL-DONE")
    assert b"FORBIDDEN-CLIPBOARD" not in controls
    assert b"FORBIDDEN-PASSTHROUGH" not in controls
    windows = subprocess.run(
        ["/usr/bin/tmux", "-S", str(TMUX_SOCKET), "list-windows", "-t", f"={session}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert len(windows) == 1
    first.send_signal(signal.SIGTERM)
    assert first.wait(timeout=5) in {0, 1, 143, -signal.SIGTERM}
    os.close(first_master)
    assert (
        subprocess.run(
            ["/usr/bin/tmux", "-S", str(TMUX_SOCKET), "has-session", "-t", f"={session}"],
            check=False,
        ).returncode
        == 0
    )

    second, second_master = _spawn_real_attach(native_binaries, "claude")
    os.write(second_master, b"pid\n")
    second_output = _read_fd_until(second_master, b"PID ")
    second_matches = re.findall(rb"PID ([0-9]+)", second_output)
    assert second_matches and second_matches[-1] == first_pid
    resize = _wbr_resize(1, 100, 40)
    wbr_parent.send(resize)
    assert wbr_parent.recv(128)[5] == 2
    os.write(second_master, b"size\nspawn\nexit7\n")
    terminal = _read_fd_until(second_master, b"SPAWNED", timeout=5.0)
    assert b"SIZE 100 40" in terminal
    assert second.wait(timeout=10) in {0, 1, 7, 143, -signal.SIGTERM}
    os.close(second_master)
    _wait_session_gone(session, timeout=5.0)
    launch.close()
    listener.close()
    launch_path.unlink(missing_ok=True)
    wbr_parent.close()


def test_incomplete_vendor_dcs_fails_closed_before_pane_success(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    dcs_config = tmp_path / "dcs-tmux.conf"
    dcs_config.write_bytes(TMUX_CONFIG.read_bytes() + b"\nset-option -g remain-on-exit on\n")
    session, control, wbr = _begin_real_workspace(
        native_binaries, fake_binaries[0], tmp_path, tmux_config=dcs_config
    )
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    attached, master = _spawn_real_attach(native_binaries, "claude")
    _read_fd_until(master, b"READY claude")
    os.write(master, b"dcs-exit\n")
    deadline = time.monotonic() + 5.0
    pane_status = ""
    while pane_status != "1:74":
        pane_status = subprocess.run(
            [
                "/usr/bin/tmux",
                "-S",
                str(TMUX_SOCKET),
                "list-panes",
                "-t",
                f"={session}:0.0",
                "-F",
                "#{pane_dead}:#{pane_dead_status}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if time.monotonic() >= deadline:
            raise AssertionError(f"incomplete DCS did not fail closed: {pane_status}")
        time.sleep(0.01)
    attached.send_signal(signal.SIGTERM)
    assert attached.wait(timeout=5) in {0, 1, 143, -signal.SIGTERM}
    os.close(master)
    control.close()
    wbr.close()
    _kill_tmux_server()


def test_closed_stdio_descendant_is_reaped_before_successful_drain_ack(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    descendant_config = tmp_path / "descendant-tmux.conf"
    descendant_config.write_bytes(TMUX_CONFIG.read_bytes() + b"\nset-option -g remain-on-exit on\n")
    session, control, wbr = _begin_real_workspace(
        native_binaries, fake_binaries[0], tmp_path, tmux_config=descendant_config
    )
    assert control.recv(9) == b"AWR1\x01\x01\x00\x00"
    attached, master = _spawn_real_attach(native_binaries, "claude")
    _read_fd_until(master, b"READY claude")
    os.write(master, b"closed-descendant\n")
    assert b"CLOSED-SPAWNED" in _read_fd_until(master, b"CLOSED-SPAWNED")
    deadline = time.monotonic() + 5.0
    pane_status = ""
    while pane_status != "1:7":
        pane_status = subprocess.run(
            [
                "/usr/bin/tmux",
                "-S",
                str(TMUX_SOCKET),
                "list-panes",
                "-t",
                f"={session}:0.0",
                "-F",
                "#{pane_dead}:#{pane_dead_status}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if time.monotonic() >= deadline:
            raise AssertionError(f"closed-stdio descendant was not reaped: {pane_status}")
        time.sleep(0.01)
    assert (tmp_path / "temp" / ".descendant-term-canary").read_bytes() == b"\x01"
    attached.send_signal(signal.SIGTERM)
    assert attached.wait(timeout=5) in {0, 1, 143, -signal.SIGTERM}
    os.close(master)
    control.close()
    wbr.close()
    _kill_tmux_server()


def test_attach_supervisor_rejects_missing_tmux_session(native_binaries: Path) -> None:
    _kill_tmux_server()
    process, master = _spawn_real_attach(native_binaries, "claude", expect_ready=False)
    os.close(master)
    assert process.wait(timeout=5) == 71


def test_attach_supervisor_rejects_fake_elf_that_does_not_attach(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    socket_dir = tmp_path / "tmux"
    socket_dir.mkdir()
    config = tmp_path / "tmux.conf"
    config.write_text("set -g status off\n")
    executable_fd = os.open(fake_binaries[1], os.O_RDONLY)
    directory_fd = os.open(socket_dir, os.O_RDONLY | os.O_DIRECTORY)
    config_fd = os.open(config, os.O_RDONLY)
    ready_parent, ready_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    master, slave = pty.openpty()
    process = _popen_with_fd_mapping(
        [
            str(native_binaries / "agentbox-waw-attach-supervisor"),
            "--workspace-hash",
            HASH,
            "--agent-type",
            "codex",
        ],
        {
            executable_fd: 3,
            directory_fd: 4,
            config_fd: 5,
            ready_child.fileno(): 6,
        },
        make_session=True,
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    os.close(slave)
    os.close(executable_fd)
    os.close(directory_fd)
    os.close(config_fd)
    ready_child.close()
    ready_parent.settimeout(5.0)
    assert ready_parent.recv(9) == b""
    ready_parent.close()
    os.close(master)
    assert process.wait(timeout=5) == 71


def test_attach_supervisor_exec_failure_never_emits_ready_and_reaps(
    native_binaries: Path, tmp_path: Path
) -> None:
    socket_dir = tmp_path / "invalid-attach-tmux"
    socket_dir.mkdir()
    config = tmp_path / "invalid-attach.conf"
    config.write_text("set -g status off\n")
    invalid_target = tmp_path / "invalid-attach-target"
    invalid_target.write_text("#!/definitely/missing/interpreter\n")
    invalid_target.chmod(0o755)
    executable_fd = os.open(invalid_target, os.O_RDONLY)
    directory_fd = os.open(socket_dir, os.O_RDONLY | os.O_DIRECTORY)
    config_fd = os.open(config, os.O_RDONLY)
    ready_parent, ready_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    master, slave = pty.openpty()
    process = _popen_with_fd_mapping(
        [
            str(native_binaries / "agentbox-waw-attach-supervisor"),
            "--workspace-hash",
            HASH,
            "--agent-type",
            "claude",
        ],
        {
            executable_fd: 3,
            directory_fd: 4,
            config_fd: 5,
            ready_child.fileno(): 6,
        },
        make_session=True,
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    os.close(slave)
    os.close(executable_fd)
    os.close(directory_fd)
    os.close(config_fd)
    ready_child.close()
    ready_parent.settimeout(5.0)
    assert ready_parent.recv(9) == b""
    ready_parent.close()
    os.close(master)
    assert process.wait(timeout=5) == 71


def test_native_launcher_places_itself_before_held_tmux_exec(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    cgroup = tmp_path / "launcher-cgroup"
    cgroup.mkdir()
    (cgroup / "cgroup.procs").write_text("")
    config = tmp_path / "launcher-tmux.conf"
    config.write_text("set -g status off\n")
    bootstrap_fd = os.open(
        native_binaries / "agentbox-waw-pane-bootstrap", os.O_RDONLY | os.O_CLOEXEC
    )
    cgroup_fd = os.open(cgroup, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    tmux_fd = os.open(fake_binaries[1], os.O_RDONLY | os.O_CLOEXEC)
    config_fd = os.open(config, os.O_RDONLY | os.O_CLOEXEC)
    ready_parent, ready_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    process = _popen_with_fd_mapping(
        [
            str(native_binaries / "agentbox-waw-pane-bootstrap"),
            "--launch-tmux",
            "--workspace-hash",
            HASH,
            "--agent-type",
            "claude",
            "--runtime-pid",
            str(os.getpid()),
            "--bootstrap-fd",
            str(bootstrap_fd),
        ],
        {
            cgroup_fd: 3,
            tmux_fd: 4,
            config_fd: 5,
            ready_child.fileno(): 6,
        },
        make_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ready_child.close()
    ready_parent.settimeout(5)
    assert ready_parent.recv(9) == b"AWR1\x01\x01\x00\x00"
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 23 and stderr == b""
    assert b"ARG1=-S" in stdout and b"ARG5=new-session" in stdout
    assert (cgroup / "cgroup.procs").read_text().strip() == str(process.pid)
    ready_parent.close()
    for descriptor in (bootstrap_fd, cgroup_fd, tmux_fd, config_fd):
        os.close(descriptor)


def test_python_native_port_reaches_built_helpers_fake_vendor_pty_wbr_and_reap(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    project = tmp_path / "adapter-project"
    home = tmp_path / "adapter-home"
    temporary = tmp_path / "adapter-temp"
    policy = tmp_path / "adapter-policy"
    for directory in (project, home, temporary, policy):
        directory.mkdir()
    _write_host_namespace_record(project)
    _write_mount_canaries(home, temporary, policy)

    helper_sources = [
        os.open(native_binaries / "agentbox-waw-pane-bootstrap", os.O_RDONLY | os.O_CLOEXEC),
        os.open(native_binaries / "agentbox-waw-attach-supervisor", os.O_RDONLY | os.O_CLOEXEC),
        os.open("/usr/bin/tmux", os.O_RDONLY | os.O_CLOEXEC),
        os.open(TMUX_SOCKET.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(TMUX_CONFIG, os.O_RDONLY | os.O_CLOEXEC),
    ]
    port = NativeHelperProcessPort(
        NativeHelperHandles(*helper_sources), authenticated=lambda _identity: True
    )
    for descriptor in helper_sources:
        os.close(descriptor)

    endpoint = port.create_wbr_endpoint()
    role_fds = [
        os.open(project, O_PATH | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(native_binaries / "agentbox-waw-bridge", os.O_RDONLY | os.O_CLOEXEC),
        os.open(fake_binaries[0], os.O_RDONLY | os.O_CLOEXEC),
        os.open(policy, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
    ]
    identity = _fixed_identity()
    cgroup = _CgroupSequence([1, 0])
    handles = FixedLaunchHandles(
        project_directory=role_fds[0],
        selected_home_directory=role_fds[1],
        temp_directory=role_fds[2],
        bridge_executable=role_fds[3],
        vendor_executable=role_fds[4],
        policy_directory=role_fds[5],
        wbr_endpoint=endpoint,
        cgroup=cgroup,
    )
    request = FixedLaunchRequest(identity, handles, PtyGeometry(80, 24))
    proof = port.start(request)
    assert proof.state is FixedStartState.RUNNING
    assert proof.binding is not None

    claims = AttachmentTuple(
        workspace_id=WORKSPACE,
        project_id=PROJECT,
        agent_type=AgentType.CLAUDE,
        attachment_id="att_" + "4" * 32,
        lease_number=1,
        generation=7,
        auth_epoch=1,
        api_authority_epoch=1,
        runtime_host_installation_id=HOST,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="d" * 64,
    )
    lease = RuntimeAttachmentLease(claims, "9", 100.0, lambda: True)
    attachment = port.open_attachment(
        FixedAttachmentRequest(proof.binding, lease, PtyGeometry(80, 24))
    )
    acknowledgment = attachment.resize(PtyGeometry(100, 40))
    assert len(acknowledgment) == 64
    assert acknowledgment[5] == 2

    attachment.write_input(b"size\nexit7\n")
    observed = _read_attachment_until(attachment, b"SIZE 100 40")
    assert b"READY claude" in observed
    cleanup = attachment.close()
    assert cleanup.closed
    deadline = time.monotonic() + 5.0
    while True:
        probe = port.probe(proof.binding)
        if probe.state is RuntimeProbeState.EXITED:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("native adapter did not reap the fake vendor")
        time.sleep(0.01)
    assert probe.exit_code is None
    stopped = port.stop(proof.binding)
    assert stopped.closed and stopped.remaining_members == 0
    port.close()
    for descriptor in role_fds:
        os.close(descriptor)


def test_python_native_port_exec_failure_closes_ready_and_wbr_without_binding(
    native_binaries: Path, fake_binaries: tuple[Path, Path], tmp_path: Path
) -> None:
    directories = [
        tmp_path / name for name in ("fail-project", "fail-home", "fail-temp", "fail-policy")
    ]
    for directory in directories:
        directory.mkdir()
    invalid_vendor = tmp_path / "fail-vendor"
    invalid_vendor.write_text("#!/definitely/missing/interpreter\n")
    invalid_vendor.chmod(0o755)

    helper_sources = [
        os.open(native_binaries / "agentbox-waw-pane-bootstrap", os.O_RDONLY | os.O_CLOEXEC),
        os.open(native_binaries / "agentbox-waw-attach-supervisor", os.O_RDONLY | os.O_CLOEXEC),
        os.open("/usr/bin/tmux", os.O_RDONLY | os.O_CLOEXEC),
        os.open(TMUX_SOCKET.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(TMUX_CONFIG, os.O_RDONLY | os.O_CLOEXEC),
    ]
    port = NativeHelperProcessPort(
        NativeHelperHandles(*helper_sources), authenticated=lambda _identity: True
    )
    for descriptor in helper_sources:
        os.close(descriptor)
    endpoint = port.create_wbr_endpoint()
    role_fds = [
        os.open(directories[0], O_PATH | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(directories[1], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(directories[2], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
        os.open(native_binaries / "agentbox-waw-bridge", os.O_RDONLY | os.O_CLOEXEC),
        os.open(invalid_vendor, os.O_RDONLY | os.O_CLOEXEC),
        os.open(directories[3], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC),
    ]
    handles = FixedLaunchHandles(
        project_directory=role_fds[0],
        selected_home_directory=role_fds[1],
        temp_directory=role_fds[2],
        bridge_executable=role_fds[3],
        vendor_executable=role_fds[4],
        policy_directory=role_fds[5],
        wbr_endpoint=endpoint,
        cgroup=_CgroupSequence([1, 0]),
    )
    with pytest.raises(RuntimeOperationError, match="READY"):
        port.start(FixedLaunchRequest(_fixed_identity(), handles, PtyGeometry(80, 24)))
    assert endpoint.native.fileno() == -1
    assert endpoint.controller.fileno() == -1
    port.close()
    for descriptor in role_fds:
        os.close(descriptor)


@pytest.mark.parametrize(
    "program",
    [
        "agentbox-waw-pane-bootstrap",
        "agentbox-waw-bridge",
        "agentbox-waw-attach-supervisor",
    ],
)
def test_native_helpers_reject_caller_command_surface(native_binaries: Path, program: str) -> None:
    completed = subprocess.run(
        [str(native_binaries / program), "--command", "id"], capture_output=True, check=False
    )
    assert completed.returncode == 64
    assert completed.stdout == b""
    assert completed.stderr == b""
