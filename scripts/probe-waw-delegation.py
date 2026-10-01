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
        directory_fd = os.open("/run", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            facts = os.fstat(directory_fd)
            filesystem_id = os.fstatvfs(directory_fd).f_fsid
            mount_ids = [
                line.split(":", 1)[1].strip()
                for line in Path(f"/proc/self/fdinfo/{directory_fd}").read_text().splitlines()
                if line.startswith("mnt_id:")
            ]
            assert len(mount_ids) == 1 and mount_ids[0].isdigit()
            assert filesystem_id > 0 and facts.st_ino > 0
        finally:
            os.close(directory_fd)
        print(
            json.dumps(
                {
                    "schema_version": "agentbox-waw-delegation-probe.v2",
                    "scoped_write": True,
                    "outside_write_denied": True,
                    "global_mount_read_only": True,
                    "subtree_mount_read_write": True,
                    "filesystem_id": str(filesystem_id),
                    "inode": str(facts.st_ino),
                    "mount_id": mount_ids[0],
                    "mount_namespace": os.readlink("/proc/self/ns/mnt"),
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
            "--property=ProtectSystem=strict",
            "--property=PrivateTmp=yes",
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
            records = []
            for _attempt in range(2):
                result = subprocess.run(
                    command, check=False, timeout=60, capture_output=True, text=True
                )
                if result.returncode != 0:
                    sys.stderr.write(result.stderr[-8192:])
                    return result.returncode
                assert len(result.stdout) <= 4096, "probe output is oversized"
                record = json.loads(result.stdout)
                assert record["schema_version"] == "agentbox-waw-delegation-probe.v2"
                assert all(
                    record[key] is True
                    for key in (
                        "scoped_write",
                        "outside_write_denied",
                        "global_mount_read_only",
                        "subtree_mount_read_write",
                    )
                )
                records.append(record)
                print(json.dumps(record))
            assert (records[0]["filesystem_id"], records[0]["inode"]) == (
                records[1]["filesystem_id"],
                records[1]["inode"],
            ), "physical filesystem identity changed across service instances"
            print(
                json.dumps(
                    {
                        "schema_version": "agentbox-waw-namespace-restart-probe.v1",
                        "physical_identity_stable": True,
                        "mount_id_changed": records[0]["mount_id"] != records[1]["mount_id"],
                        "namespace_changed": records[0]["mount_namespace"]
                        != records[1]["mount_namespace"],
                    }
                )
            )
            return 0
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
