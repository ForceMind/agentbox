from __future__ import annotations

import array
import os
import platform
import select
import socket
import struct
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "scripts" / "build-waw-native.py"
HASH = "b" * 64
PROFILE = "c" * 64
GENERATION = 8
CGROUP = Path("/sys/fs/cgroup/agentbox-waw-test") / f"ws-{HASH}-g{GENERATION}" / "workload"
WRONG_CGROUP = Path("/sys/fs/cgroup/agentbox-waw-test") / f"ws-{'a' * 64}-g7" / "workload"
SCRATCH_TARGET = Path("/run/agentbox-waw/auth-probe")
SCRATCH_SOURCE = Path("/run/agentbox-waw/tmp") / HASH / f"auth-probe-g{GENERATION}"
WRONG_SCRATCH_SOURCE = Path("/run/agentbox-waw/tmp") / HASH / "auth-probe-g9"
WRONG_WORKSPACE_SCRATCH_SOURCE = (
    Path("/run/agentbox-waw/tmp") / ("d" * 64) / f"auth-probe-g{GENERATION}"
)
HOST_GATE = os.environ.get("AGENTBOX_WAW_NATIVE_HOST_GATE") == "1"
LINUX = platform.system() == "Linux"

pytestmark = pytest.mark.skipif(
    not LINUX or not HOST_GATE, reason="dedicated Linux native auth helper host gate"
)


_FD_EXEC_SHIM = """
import fcntl
import os
import sys

separator = sys.argv.index("--", 1)
mapping = [tuple(map(int, item.split(":"))) for item in sys.argv[1:separator]]
arguments = sys.argv[separator + 1:]
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


_FAKE_VENDOR = r"""
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

extern char **environ;

#ifndef AUTH_HANG
static int exact_environment(const char *agent) {
    const char *state_name = strcmp(agent, "claude") == 0 ? "CLAUDE_CONFIG_DIR" : "CODEX_HOME";
    const char *state_leaf = strcmp(agent, "claude") == 0 ? ".config/claude" : ".config/codex";
    char expected[11][256];
    size_t index;
    size_t count = 0;
    snprintf(expected[0], sizeof(expected[0]), "HOME=/var/lib/agentbox-waw/vendor-homes/%s", agent);
    snprintf(expected[1], sizeof(expected[1]),
             "XDG_CONFIG_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.config", agent);
    snprintf(expected[2], sizeof(expected[2]),
             "XDG_CACHE_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.cache", agent);
    snprintf(expected[3], sizeof(expected[3]),
             "XDG_DATA_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.local/share", agent);
    snprintf(expected[4], sizeof(expected[4]),
             "XDG_STATE_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.local/state", agent);
    snprintf(expected[5], sizeof(expected[5]), "TMPDIR=/run/agentbox-waw/auth-probe");
    snprintf(expected[6], sizeof(expected[6]), "PATH=/usr/bin:/opt/agentbox/current/libexec");
    snprintf(expected[7], sizeof(expected[7]), "LANG=C.UTF-8");
    snprintf(expected[8], sizeof(expected[8]), "LC_CTYPE=C.UTF-8");
    snprintf(expected[9], sizeof(expected[9]), "TERM=dumb");
    snprintf(expected[10], sizeof(expected[10]), "%s=/var/lib/agentbox-waw/vendor-homes/%s/%s",
             state_name, agent, state_leaf);
    for (char **item = environ; *item != NULL; ++item) {
        int matched = 0;
        ++count;
        for (index = 0; index < 11U; ++index) {
            if (strcmp(*item, expected[index]) == 0) {
                matched = 1;
                break;
            }
        }
        if (!matched) return -1;
    }
    return count == 11U ? 0 : -1;
}

static int file_equals(const char *path, const char *expected) {
    char buffer[32];
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    ssize_t count;
    if (fd < 0) return -1;
    count = read(fd, buffer, sizeof(buffer));
    close(fd);
    return count == (ssize_t)strlen(expected) && memcmp(buffer, expected, (size_t)count) == 0
               ? 0 : -1;
}

static int denied(const char *path) {
    int fd;
    errno = 0;
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd >= 0) {
        close(fd);
        return -1;
    }
    return errno == EACCES || errno == ENOENT || errno == ENOTDIR ? 0 : -1;
}

static int exact_fds(void) {
    int fd;
    for (fd = 3; fd < 64; ++fd) {
        errno = 0;
        if (fcntl(fd, F_GETFD) >= 0 || errno != EBADF) return -1;
    }
    errno = 0;
    return fcntl(128, F_GETFD) >= 0 || errno != EBADF ? -1 : 0;
}
#endif

int main(int argc, char **argv) {
    const char *agent;
    if (argc != 3) return 90;
    agent = argv[0];
    if (!((strcmp(agent, "claude") == 0 && strcmp(argv[1], "auth") == 0) ||
          (strcmp(agent, "codex") == 0 && strcmp(argv[1], "login") == 0)) ||
        strcmp(argv[2], "status") != 0) return 91;
#ifdef EXPECT_CODEX
    if (strcmp(agent, "codex") != 0) return 89;
#endif
#ifdef AUTH_HANG
    {
        pid_t child = fork();
        if (child < 0) return 92;
        if (child == 0) {
            puts("DESCENDANT-OPEN");
            fflush(stdout);
            for (;;) pause();
        }
        signal(SIGTERM, SIG_IGN);
        for (;;) pause();
    }
#else
    const char *home_marker;
    char cwd[256];
    char cgroup[512];
    int fd;
    ssize_t count;
    home_marker = strcmp(agent, "claude") == 0
                      ? "/var/lib/agentbox-waw/vendor-homes/claude/.auth-home-canary"
                      : "/var/lib/agentbox-waw/vendor-homes/codex/.auth-home-canary";
    int tty_fd;
    if (isatty(0) || isatty(1) || isatty(2) || read(0, cgroup, 1U) != 0 ||
        exact_environment(agent) != 0 || getcwd(cwd, sizeof(cwd)) == NULL ||
        strcmp(cwd, "/run/agentbox-waw/auth-probe") != 0 || exact_fds() != 0 ||
        file_equals(home_marker, "home\n") != 0 ||
        file_equals("/run/agentbox-waw/auth-probe/.auth-scratch-canary", "scratch\n") != 0 ||
        denied("/var/lib/agentbox-waw/keys-v1") != 0 ||
        denied("/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1") != 0 ||
        denied("/run/agentbox-waw/tmp") != 0 ||
        denied("/srv/agentbox/projects") != 0) return 93;
    tty_fd = open("/dev/tty", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (tty_fd >= 0) {
        close(tty_fd);
        return 93;
    }
    fd = open("/run/agentbox-waw/auth-probe/vendor-residue",
              O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0 || write(fd, "residue\n", 8U) != 8 || close(fd) != 0) return 99;
#ifdef AUTH_EARLY_EXIT
    return 42;
#endif
    errno = 0;
    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd >= 0 || errno != EPERM) return 94;
    errno = 0;
    if (unshare(CLONE_NEWNET) == 0 || errno != EPERM) return 95;
    fd = open("/proc/self/cgroup", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 96;
    count = read(fd, cgroup, sizeof(cgroup) - 1U);
    close(fd);
    if (count <= 0) return 97;
    cgroup[(size_t)count] = '\0';
    if (strstr(cgroup, "/ws-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                       "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-g8/workload") == NULL)
        return 98;
    puts("AUTH-OK");
    fputs("AUTH-ERR-OK\n", stderr);
    return 23;
#endif
}
"""


@pytest.fixture(scope="session")
def native_binaries(tmp_path_factory: pytest.TempPathFactory) -> Path:
    configured = os.environ.get("AGENTBOX_WAW_NATIVE_BIN_DIR")
    if configured:
        return (ROOT / configured).resolve()
    output = tmp_path_factory.mktemp("waw-auth-native-bin")
    subprocess.run([sys.executable, str(BUILD), "--output", str(output)], check=True, cwd=ROOT)
    return output


@pytest.fixture(scope="session")
def auth_fake_vendors(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, Path, Path]:
    output = tmp_path_factory.mktemp("waw-auth-native-fakes")
    source = output / "fake_auth_vendor.c"
    source.write_text(_FAKE_VENDOR)
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
    ]
    normal = output / "fake-auth-vendor"
    hanging = output / "fake-auth-vendor-hang"
    early = output / "fake-auth-vendor-early"
    codex_only = output / "fake-auth-vendor-codex-only"
    subprocess.run([*common, str(source), "-o", str(normal)], check=True)
    subprocess.run([*common, "-DAUTH_HANG=1", str(source), "-o", str(hanging)], check=True)
    subprocess.run([*common, "-DAUTH_EARLY_EXIT=1", str(source), "-o", str(early)], check=True)
    subprocess.run([*common, "-DEXPECT_CODEX=1", str(source), "-o", str(codex_only)], check=True)
    return normal, hanging, early, codex_only


def _cgroup_members(path: Path = CGROUP) -> tuple[int, ...]:
    return tuple(int(value) for value in (path / "cgroup.procs").read_text().split())


def _cgroup_populated(path: Path = CGROUP) -> int:
    values = {
        key: int(value)
        for key, value in (
            line.split() for line in (path / "cgroup.events").read_text().splitlines()
        )
    }
    return values["populated"]


def _wait_cgroup_empty(timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while _cgroup_populated() != 0 or _cgroup_members():
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"auth cgroup did not empty: populated={_cgroup_populated()} "
                f"members={_cgroup_members()}"
            )
        time.sleep(0.01)
    assert _cgroup_populated() == 0
    assert _cgroup_members() == ()


@pytest.fixture(autouse=True)
def auth_mount_canaries() -> Iterator[None]:
    if not LINUX or not HOST_GATE:
        yield
        return
    assert os.geteuid() != 0
    assert CGROUP.is_dir()
    assert WRONG_CGROUP.is_dir()
    assert _cgroup_populated() == 0
    assert _cgroup_members() == ()
    parent_cgroup = Path("/proc/self/cgroup").read_text()
    assert f"/ws-{'a' * 64}-g7/workload" in parent_cgroup
    assert f"/ws-{HASH}-g{GENERATION}/workload" not in parent_cgroup
    assert os.getpid() not in _cgroup_members()
    assert SCRATCH_TARGET.is_dir()
    target_status = SCRATCH_TARGET.stat()
    assert target_status.st_uid == 0
    assert target_status.st_mode & 0o777 == 0o755
    SCRATCH_SOURCE.mkdir(mode=0o700, exist_ok=True)
    SCRATCH_SOURCE.chmod(0o700)
    WRONG_SCRATCH_SOURCE.mkdir(mode=0o700, exist_ok=True)
    WRONG_SCRATCH_SOURCE.chmod(0o700)
    WRONG_WORKSPACE_SCRATCH_SOURCE.parent.mkdir(mode=0o700, exist_ok=True)
    WRONG_WORKSPACE_SCRATCH_SOURCE.mkdir(mode=0o700, exist_ok=True)
    WRONG_WORKSPACE_SCRATCH_SOURCE.chmod(0o700)
    home_markers = [
        Path("/var/lib/agentbox-waw/vendor-homes/claude/.auth-home-canary"),
        Path("/var/lib/agentbox-waw/vendor-homes/codex/.auth-home-canary"),
    ]
    for home in (marker.parent for marker in home_markers):
        status = home.stat()
        assert status.st_uid == os.geteuid()
        assert status.st_mode & 0o777 == 0o700
    for policy in (Path("/etc/claude-code"), Path("/etc/codex")):
        status = policy.stat()
        assert status.st_uid == 0
        assert status.st_mode & 0o777 == 0o755
    scratch_marker = SCRATCH_SOURCE / ".auth-scratch-canary"
    residue = SCRATCH_SOURCE / "vendor-residue"
    assert not residue.exists(), "previous auth-probe residue was not cleaned by its owner"
    for marker in home_markers:
        marker.write_text("home\n")
    scratch_marker.write_text("scratch\n")
    yield
    masked_directory = SCRATCH_SOURCE / ".masked"
    masked_file = SCRATCH_SOURCE / ".masked-file"
    if masked_directory.exists():
        masked_directory.chmod(0o700)
    for marker in [*home_markers, scratch_marker]:
        marker.unlink(missing_ok=True)
    masked_file.unlink(missing_ok=True)
    assert not residue.exists(), "auth-probe scratch owner cleanup was not proven"
    if masked_directory.exists():
        masked_directory.rmdir()
    SCRATCH_SOURCE.rmdir()
    WRONG_SCRATCH_SOURCE.rmdir()
    WRONG_WORKSPACE_SCRATCH_SOURCE.rmdir()
    WRONG_WORKSPACE_SCRATCH_SOURCE.parent.rmdir()
    _wait_cgroup_empty()


def _auth_record(
    agent: int = 1,
    *,
    magic: bytes = b"AWP1",
    version: int = 1,
    flags: int = 0,
    runtime_pid: int | None = None,
    runtime_uid: int | None = None,
    generation: int = GENERATION,
    profile: bytes | None = None,
    reserved: bytes = b"\0" * 4,
) -> bytes:
    return struct.pack(
        "!4sBBHIIIQ64s64s4s",
        magic,
        version,
        agent,
        flags,
        os.getpid() if runtime_pid is None else runtime_pid,
        os.geteuid() if runtime_uid is None else runtime_uid,
        os.getegid(),
        generation,
        HASH.encode(),
        PROFILE.encode() if profile is None else profile,
        reserved,
    )


def _mapped_process(
    native_binaries: Path,
    vendor: Path,
    agent: int = 1,
    *,
    initial_packets: tuple[bytes, ...] = (),
    ancillary: bool = False,
    role_fault: str | None = None,
) -> tuple[subprocess.Popen[bytes], socket.socket, int, int, list[int]]:
    stdin_path = "/dev/zero" if role_fault == "stdin" else "/dev/null"
    devnull = os.open(stdin_path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    stdout_read, stdout_write = os.pipe2(os.O_CLOEXEC)
    stderr_read, stderr_write = os.pipe2(os.O_CLOEXEC)
    control_parent, control_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    if ancillary:
        extra = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        try:
            control_parent.sendmsg(
                [initial_packets[0]],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [extra]))],
            )
        finally:
            os.close(extra)
    else:
        for packet in initial_packets:
            control_parent.send(packet)
    if initial_packets:
        control_parent.shutdown(socket.SHUT_WR)
    home = (
        "/var/lib/agentbox-waw/vendor-homes/claude"
        if agent == 1
        else "/var/lib/agentbox-waw/vendor-homes/codex"
    )
    policy = "/etc/claude-code" if agent == 1 else "/etc/codex"
    if role_fault == "home":
        home = (
            "/var/lib/agentbox-waw/vendor-homes/codex"
            if agent == 1
            else "/var/lib/agentbox-waw/vendor-homes/claude"
        )
    if role_fault == "policy":
        policy = "/etc/codex" if agent == 1 else "/etc/claude-code"
    cgroup_path = WRONG_CGROUP if role_fault == "cgroup" else CGROUP
    cgroup_source = Path("/dev/null") if role_fault == "cgroup-file" else cgroup_path
    cgroup_flags = os.O_RDONLY | os.O_CLOEXEC
    if role_fault != "cgroup-file":
        cgroup_flags |= os.O_DIRECTORY
    vendor_source = Path("/dev/null") if role_fault == "vendor" else vendor
    home_source = Path("/dev/null") if role_fault == "home-file" else Path(home)
    scratch_path = SCRATCH_SOURCE
    if role_fault == "scratch-generation":
        scratch_path = WRONG_SCRATCH_SOURCE
    elif role_fault == "scratch-workspace":
        scratch_path = WRONG_WORKSPACE_SCRATCH_SOURCE
    scratch_source = Path("/dev/null") if role_fault == "scratch-file" else scratch_path
    policy_source = Path("/dev/null") if role_fault == "policy-file" else Path(policy)
    opened = [
        os.open(cgroup_source, cgroup_flags),
        os.open(vendor_source, os.O_RDONLY | os.O_CLOEXEC),
        os.open(
            home_source,
            os.O_RDONLY | os.O_CLOEXEC | (0 if role_fault == "home-file" else os.O_DIRECTORY),
        ),
        os.open(
            scratch_source,
            os.O_RDONLY | os.O_CLOEXEC | (0 if role_fault == "scratch-file" else os.O_DIRECTORY),
        ),
        os.open(
            policy_source,
            os.O_RDONLY | os.O_CLOEXEC | (0 if role_fault == "policy-file" else os.O_DIRECTORY),
        ),
    ]
    if role_fault == "extra":
        opened.append(os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC))
    sentinel = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
    mapping = [
        (devnull, 0),
        (stdout_write, 1),
        (stdout_write if role_fault == "pipes" else stderr_write, 2),
        (devnull if role_fault == "control" else control_child.fileno(), 3),
        (opened[0], 4),
        (opened[1], 5),
        (opened[2], 6),
        (opened[3], 7),
        (opened[4], 8),
    ]
    if role_fault == "extra":
        mapping.append((opened[5], 9))
    mapping.append((sentinel, 128))
    mapping_arguments = [f"{source}:{destination}" for source, destination in mapping]
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _FD_EXEC_SHIM,
            *mapping_arguments,
            "--",
            str(native_binaries / "agentbox-waw-pane-bootstrap"),
            "--auth-probe",
        ],
        pass_fds=tuple({source for source, _destination in mapping}),
    )
    control_child.close()
    for descriptor in [devnull, stdout_write, stderr_write, sentinel, *opened]:
        os.close(descriptor)
    return process, control_parent, stdout_read, stderr_read, [stdout_read, stderr_read]


def _send_record_and_close(control: socket.socket, payload: bytes) -> None:
    assert _cgroup_populated() == 0
    assert _cgroup_members() == ()
    control.send(payload)
    control.shutdown(socket.SHUT_WR)


def _cleanup_auth_scratch_owner() -> None:
    residue = SCRATCH_SOURCE / "vendor-residue"
    residue.unlink(missing_ok=True)
    assert not residue.exists()


def _read_until_marker(descriptor: int, marker: bytes, timeout: float = 5.0) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while marker not in output:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"pipe did not emit marker: {bytes(output)!r}")
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            continue
        chunk = os.read(descriptor, 4096)
        if not chunk:
            raise AssertionError(f"pipe closed before marker: {bytes(output)!r}")
        output.extend(chunk)
    return bytes(output)


def _read_to_eof(descriptor: int, timeout: float = 5.0) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"pipe did not reach EOF: {bytes(output)!r}")
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            continue
        chunk = os.read(descriptor, 4096)
        if not chunk:
            return bytes(output)
        output.extend(chunk)


@pytest.mark.parametrize("agent", [1, 2])
def test_auth_probe_fixed_record_fds_environment_offline_and_exit_status(
    native_binaries: Path, auth_fake_vendors: tuple[Path, ...], agent: int
) -> None:
    process, control, stdout_fd, stderr_fd, descriptors = _mapped_process(
        native_binaries, auth_fake_vendors[0], agent
    )
    try:
        _send_record_and_close(control, _auth_record(agent))
        control.settimeout(5.0)
        assert control.recv(8) == b"AWRP\x01\x01\x00\x00"
        assert process.wait(timeout=5.0) == 23
        assert _read_to_eof(stdout_fd) == b"AUTH-OK\n"
        assert _read_to_eof(stderr_fd) == b"AUTH-ERR-OK\n"
        _wait_cgroup_empty()
        assert (SCRATCH_SOURCE / "vendor-residue").read_text() == "residue\n"
        _cleanup_auth_scratch_owner()
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)


@pytest.mark.parametrize(
    "payload",
    [
        b"short",
        _auth_record() + b"oversize",
        _auth_record(magic=b"AWP2"),
        _auth_record(version=2),
        _auth_record(agent=3),
        _auth_record(flags=1),
        _auth_record(runtime_uid=0),
        _auth_record(generation=0),
        _auth_record(profile=b"B" * 64),
        _auth_record(reserved=b"\0\0\0\x01"),
        _auth_record(runtime_pid=1),
    ],
)
def test_auth_probe_rejects_malformed_or_wrong_parent_record(
    native_binaries: Path, auth_fake_vendors: tuple[Path, ...], payload: bytes
) -> None:
    process, control, _stdout, _stderr, descriptors = _mapped_process(
        native_binaries, auth_fake_vendors[0]
    )
    try:
        _send_record_and_close(control, payload)
        assert process.wait(timeout=5.0) == 65
        _wait_cgroup_empty()
        control.settimeout(1.0)
        assert control.recv(8) == b""
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)


def test_auth_probe_rejects_delayed_second_record_before_placement(
    native_binaries: Path, auth_fake_vendors: tuple[Path, ...]
) -> None:
    process, control, stdout_fd, stderr_fd, descriptors = _mapped_process(
        native_binaries, auth_fake_vendors[0]
    )
    try:
        assert _cgroup_populated() == 0
        assert _cgroup_members() == ()
        control.send(_auth_record())
        time.sleep(0.05)
        control.send(_auth_record())
        control.shutdown(socket.SHUT_WR)
        assert process.wait(timeout=5.0) == 65
        assert _read_to_eof(stdout_fd) == b""
        assert _read_to_eof(stderr_fd) == b""
        assert _cgroup_populated() == 0
        assert _cgroup_members() == ()
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)


def test_auth_probe_rejects_ancillary_or_second_record(
    native_binaries: Path, auth_fake_vendors: tuple[Path, ...]
) -> None:
    for ancillary in (True, False):
        process, control, _stdout, _stderr, descriptors = _mapped_process(
            native_binaries,
            auth_fake_vendors[0],
            initial_packets=(_auth_record(),) if ancillary else (_auth_record(), _auth_record()),
            ancillary=ancillary,
        )
        try:
            assert process.wait(timeout=5.0) == 65
            _wait_cgroup_empty()
        finally:
            control.close()
            for descriptor in descriptors:
                os.close(descriptor)


@pytest.mark.parametrize(
    "role_fault",
    [
        "stdin",
        "pipes",
        "control",
        "cgroup-file",
        "vendor",
        "home",
        "home-file",
        "policy",
        "policy-file",
        "scratch-generation",
        "scratch-workspace",
        "scratch-file",
    ],
)
def test_auth_probe_rejects_wrong_fixed_fd_role_or_identity(
    native_binaries: Path,
    auth_fake_vendors: tuple[Path, ...],
    role_fault: str,
) -> None:
    process, control, _stdout, _stderr, descriptors = _mapped_process(
        native_binaries,
        auth_fake_vendors[0],
        initial_packets=(_auth_record(),),
        role_fault=role_fault,
    )
    try:
        assert process.wait(timeout=5.0) == 65
        _wait_cgroup_empty()
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)


def test_auth_probe_wrong_generation_cgroup_never_emits_placed_ready(
    native_binaries: Path,
    auth_fake_vendors: tuple[Path, ...],
) -> None:
    process, control, _stdout, _stderr, descriptors = _mapped_process(
        native_binaries,
        auth_fake_vendors[0],
        role_fault="cgroup",
    )
    wrong_before = _cgroup_members(WRONG_CGROUP)
    try:
        _send_record_and_close(control, _auth_record())
        assert process.wait(timeout=5.0) == 71
        control.settimeout(1.0)
        assert control.recv(8) == b""
        _wait_cgroup_empty()
        assert _cgroup_populated(WRONG_CGROUP) == (1 if wrong_before else 0)
        assert _cgroup_members(WRONG_CGROUP) == wrong_before
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)


def test_auth_probe_wrong_agent_vendor_propagates_failure_and_empties_cgroup(
    native_binaries: Path,
    auth_fake_vendors: tuple[Path, ...],
) -> None:
    process, control, stdout_fd, stderr_fd, descriptors = _mapped_process(
        native_binaries, auth_fake_vendors[3]
    )
    try:
        _send_record_and_close(control, _auth_record(agent=1))
        control.settimeout(5.0)
        assert control.recv(8) == b"AWRP\x01\x01\x00\x00"
        assert process.wait(timeout=5.0) == 89
        assert _read_to_eof(stdout_fd) == b""
        assert _read_to_eof(stderr_fd) == b""
        _wait_cgroup_empty()
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)


def test_auth_probe_early_vendor_exit_leaves_scratch_for_owner_and_empties_cgroup(
    native_binaries: Path,
    auth_fake_vendors: tuple[Path, ...],
) -> None:
    process, control, stdout_fd, stderr_fd, descriptors = _mapped_process(
        native_binaries, auth_fake_vendors[2]
    )
    try:
        _send_record_and_close(control, _auth_record())
        control.settimeout(5.0)
        assert control.recv(8) == b"AWRP\x01\x01\x00\x00"
        assert process.wait(timeout=5.0) == 42
        assert _read_to_eof(stdout_fd) == b""
        assert _read_to_eof(stderr_fd) == b""
        _wait_cgroup_empty()
        assert (SCRATCH_SOURCE / "vendor-residue").read_text() == "residue\n"
        _cleanup_auth_scratch_owner()
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)


def test_auth_probe_closes_unexpected_inherited_fd_before_vendor_exec(
    native_binaries: Path,
    auth_fake_vendors: tuple[Path, ...],
) -> None:
    process, control, stdout_fd, stderr_fd, descriptors = _mapped_process(
        native_binaries, auth_fake_vendors[0], role_fault="extra"
    )
    try:
        _send_record_and_close(control, _auth_record())
        control.settimeout(5.0)
        assert control.recv(8) == b"AWRP\x01\x01\x00\x00"
        assert process.wait(timeout=5.0) == 23
        assert _read_to_eof(stdout_fd) == b"AUTH-OK\n"
        assert _read_to_eof(stderr_fd) == b"AUTH-ERR-OK\n"
        _wait_cgroup_empty()
        assert (SCRATCH_SOURCE / "vendor-residue").read_text() == "residue\n"
        _cleanup_auth_scratch_owner()
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)


def test_auth_probe_helper_death_reaps_hanging_namespace_descendants_and_closes_pipes(
    native_binaries: Path, auth_fake_vendors: tuple[Path, ...]
) -> None:
    process, control, stdout_fd, stderr_fd, descriptors = _mapped_process(
        native_binaries, auth_fake_vendors[1]
    )
    try:
        _send_record_and_close(control, _auth_record())
        control.settimeout(5.0)
        assert control.recv(8) == b"AWRP\x01\x01\x00\x00"
        assert _read_until_marker(stdout_fd, b"DESCENDANT-OPEN\n")
        assert _cgroup_populated() == 1
        assert len(_cgroup_members()) >= 2
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.1)
        process.terminate()
        assert process.wait(timeout=1.0) == -15
        assert _read_to_eof(stdout_fd, timeout=1.0) == b""
        assert _read_to_eof(stderr_fd, timeout=1.0) == b""
        _wait_cgroup_empty()
    finally:
        control.close()
        for descriptor in descriptors:
            os.close(descriptor)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)


def test_auth_protocol_layout_and_portable_mode_are_separate_from_interactive_ready(
    native_binaries: Path,
) -> None:
    assert struct.calcsize("!4sBBHIIIQ64s64s4s") == 160
    header = (ROOT / "native/waw/include/agentbox_waw_protocol.h").read_text()
    assert '#define AGENTBOX_WAW_AUTH_READY_MAGIC "AWRP"' in header
    assert '#define AGENTBOX_WAW_READY_MAGIC "AWR1"' in header
    assert "AGENTBOX_WAW_FD_COUNT = 7" in header
    completed = subprocess.run(
        [str(native_binaries / "agentbox-waw-pane-bootstrap"), "--auth-probe"],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 65
    assert completed.stdout == b"" and completed.stderr == b""
