#!/usr/bin/env python3
"""CI-only real PID-1 probe of the approved systemd 255 delegation model.

No production unit, account, Runtime HOME, key or credential is touched.
The fixed transient probe owns its own service subtree and is stopped in
finally. A passing result is prerequisite evidence, not WAW qualification.
"""

from __future__ import annotations

import errno
import json
import os
import platform
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

UNIT = "agentbox-waw-delegation-probe.service"
ROOT = Path("/sys/fs/cgroup")
SERVICE = ROOT / "system.slice" / UNIT


def child() -> int:
    assert os.geteuid() != 0, "probe must run as the non-root DynamicUser"
    membership = Path("/proc/self/cgroup").read_text().strip()
    assert membership == f"0::/system.slice/{UNIT}/supervisor", membership
    assert SERVICE.stat().st_uid == os.geteuid(), "delegation owner mismatch"
    assert {"cpu", "memory", "pids"} <= set((SERVICE / "cgroup.controllers").read_text().split())
    (SERVICE / "cgroup.subtree_control").write_text("+cpu +memory +pids")
    leaf = SERVICE / "probe-workload"
    leaf.mkdir()
    try:
        (leaf / "pids.max").write_text("16")
        (leaf / "memory.max").write_text("67108864")
        (leaf / "memory.swap.max").write_text("0")
        (leaf / "cpu.max").write_text("100000 100000")
        (leaf / "cgroup.procs").write_text(str(os.getpid()))
        assert (leaf / "cgroup.procs").read_text().strip() == str(os.getpid())
        assert (leaf / "pids.max").read_text().strip() == "16"
        assert (leaf / "memory.max").read_text().strip() == "67108864"
        try:
            fd = os.open(ROOT / "cgroup.procs", os.O_WRONLY | os.O_CLOEXEC)
        except OSError as exc:
            assert exc.errno in {errno.EROFS, errno.EACCES, errno.EPERM}, exc.errno
        else:
            os.close(fd)
            raise AssertionError("outside cgroup opened for write")
        mounts = []
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            before, _, after = line.partition(" - ")
            fields = before.split()
            if len(fields) >= 6 and after.startswith("cgroup2 "):
                mounts.append((fields[4], fields[5].split(",")))
        assert any(path == str(ROOT) and "ro" in flags for path, flags in mounts), mounts
        assert any(path == str(SERVICE) and "rw" in flags for path, flags in mounts), mounts
        print(
            json.dumps(
                {
                    "schema_version": "agentbox-waw-delegation-probe.v1",
                    "scoped_write": True,
                    "outside_write_denied": True,
                    "global_mount_read_only": True,
                    "subtree_mount_read_write": True,
                }
            )
        )
    finally:
        (SERVICE / "supervisor/cgroup.procs").write_text(str(os.getpid()))
        leaf.rmdir()
    return 0


def main() -> int:
    if sys.argv[1:] == ["--child"]:
        return child()
    if sys.argv[1:] or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("this fixed probe is CI-only")
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise SystemExit("isolated Linux root runner required")
    if Path("/proc/1/comm").read_text().strip() != "systemd":
        raise SystemExit("native systemd PID 1 required; no simulated pass")
    query = subprocess.run(
        ["/usr/bin/systemctl", "show", UNIT, "--property=LoadState", "--value"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    if query.stdout.strip() != "not-found":
        raise SystemExit("refusing an existing probe unit")
    marker = "AgentBox-CI-delegation-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="agentbox-waw-probe-", dir="/run") as temporary:
        directory = Path(temporary)
        directory.chmod(0o755)
        script = directory / "probe.py"
        script.write_bytes(Path(__file__).read_bytes())
        script.chmod(0o555)
        command = [
            "/usr/bin/systemd-run",
            "--quiet",
            "--wait",
            "--pipe",
            "--collect",
            f"--unit={UNIT}",
            f"--property=Description={marker}",
            "--property=DynamicUser=yes",
            "--property=Delegate=cpu memory pids",
            "--property=DelegateSubgroup=supervisor",
            "--property=ProtectControlGroups=yes",
            f"--property=ReadWritePaths={SERVICE}",
            "--property=NoNewPrivileges=yes",
            "--property=RuntimeMaxSec=45",
            "--property=TasksMax=256",
            "--property=MemoryMax=512M",
            "--property=MemorySwapMax=0",
            "--property=CPUQuota=400%",
            "/usr/bin/python3",
            "-I",
            str(script),
            "--child",
        ]
        try:
            result = subprocess.run(command, check=False, timeout=60)
            return result.returncode
        finally:
            own = subprocess.run(
                ["/usr/bin/systemctl", "show", UNIT, "--property=Description", "--value"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if own.stdout.strip() == marker:
                subprocess.run(
                    ["/usr/bin/systemctl", "stop", UNIT],
                    check=False,
                    timeout=15,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )


if __name__ == "__main__":
    raise SystemExit(main())
