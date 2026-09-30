#!/usr/bin/env python3
"""CI-only actual Runtime helper cgroupfs test; no production account/key use."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

UNIT = "agentbox-runtime.service"


def child() -> int:
    # The copied, root-owned package sources are the current checkout. The
    # authority here is explicitly a metadata fixture, not a cryptographic
    # Runtime admission claim. Actual filesystem and production helpers run.
    sys.path.insert(0, str(Path(__file__).parent / "packages"))
    from agentbox_runtime.waw_cgroup_attestation_store import WAWCgroupAttestationStore
    from agentbox_runtime.waw_cgroup_observation import WAWCgroupObservationFactory
    from agentbox_runtime.waw_fixed_transport import (
        _create_bound_workload_cgroup,
        _open_scoped_workspace_root,
        _read_cgroup_file,
        _verify_delegate_root,
    )
    from agentbox_runtime.waw_manifest_codecs import (
        RUNTIME_NAMESPACE_BINDING_V1,
        SCOPED_CGROUP_FILESYSTEM_V1,
        SCOPED_CGROUP_PROTECTION_V1,
        SCOPED_CGROUP_TEMPLATE_SHA256_V1,
        SCOPED_CGROUP_WORKSPACES_V1,
        CgroupDelegationManifest,
    )

    assert os.geteuid() != 0
    manifest = CgroupDelegationManifest(
        UNIT,
        "cgroup2",
        RUNTIME_NAMESPACE_BINDING_V1,
        SCOPED_CGROUP_FILESYSTEM_V1,
        "cgroup-v2",
        True,
        SCOPED_CGROUP_WORKSPACES_V1,
        SCOPED_CGROUP_PROTECTION_V1,
        "process",
        ("cpu", "memory", "pids"),
        256,
        536870912,
        0,
        400,
        100000,
        SCOPED_CGROUP_TEMPLATE_SHA256_V1,
    )
    authority = SimpleNamespace(_manifest=SimpleNamespace(cgroup=manifest))
    root = _open_scoped_workspace_root(authority)
    workspace_id = "aws_" + "2" * 32
    name = "ws-" + hashlib.sha256(workspace_id.encode("ascii")).hexdigest() + "-g1"
    try:
        _create_bound_workload_cgroup(root, name, authority)
        workspace = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            workload = os.open(
                "workload", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=workspace
            )
            try:
                assert _read_cgroup_file(workload, "pids.max").strip() == "256"
                assert _read_cgroup_file(workload, "memory.max").strip() == "536870912"
                assert _read_cgroup_file(workload, "memory.swap.max").strip() == "0"
                assert _read_cgroup_file(workload, "cpu.max").strip() == "400000 100000"
                with tempfile.TemporaryDirectory(prefix="agentbox-attestation-") as record_path:
                    record_dir = Path(record_path)
                    record_dir.chmod(0o700)
                    store = WAWCgroupAttestationStore(
                        record_dir, expected_uid=os.geteuid(), expected_gid=os.getegid()
                    )
                    factory = WAWCgroupObservationFactory(
                        lambda: authority,
                        store,
                        invocation_id=os.environ["INVOCATION_ID"],
                        runtime_epoch=lambda: "1",
                    )
                    identity = SimpleNamespace(
                        workspace_id=workspace_id,
                        project_id="prj_" + "3" * 32,
                        agent_type="claude",
                        generation="1",
                    )
                    record = factory(identity, SimpleNamespace(state="STOPPED"))
                    assert record.cleanup_state == "EMPTY_DURABLE" and record.last_populated == "0"
                    assert store.read(workspace_id=workspace_id, generation=1) == record
                mount = _verify_delegate_root(root, authority)
                try:
                    _create_bound_workload_cgroup(root, name, authority)
                except Exception as error:
                    assert getattr(error, "code", None) == "RECONCILIATION_REQUIRED"
                else:
                    raise AssertionError("existing generation was adopted")
                print(
                    json.dumps(
                        {
                            "schema_version": "agentbox-cgroup-setup-probe.v1",
                            "production_helpers_executed": True,
                            "limits_read_back": True,
                            "existing_generation_rejected": True,
                            "fd_observation_persisted": True,
                            "mount_id": mount[0],
                        }
                    )
                )
            finally:
                os.close(workload)
            os.rmdir("workload", dir_fd=workspace)
        finally:
            os.close(workspace)
        os.rmdir(name, dir_fd=root)
    finally:
        os.close(root)
    return 0


def main() -> int:
    if sys.argv[1:] == ["--child"]:
        return child()
    if (
        sys.argv[1:]
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or platform.system() != "Linux"
        or os.geteuid() != 0
    ):
        raise SystemExit("isolated Linux root CI only")
    if Path("/proc/1/comm").read_text().strip() != "systemd":
        raise SystemExit("native systemd PID 1 required")
    query = subprocess.run(
        ["/usr/bin/systemctl", "show", UNIT, "--property=LoadState", "--value"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    if query.stdout.strip() != "not-found":
        raise SystemExit("refusing existing Runtime unit")
    marker = "AgentBox-CI-cgroup-setup-" + uuid.uuid4().hex
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="agentbox-cgroup-setup-", dir="/run") as temporary:
        directory = Path(temporary)
        directory.chmod(0o755)
        script = directory / "probe.py"
        script.write_bytes(Path(__file__).read_bytes())
        script.chmod(0o555)
        for package, folder in (
            ("agentbox_runtime", "agentbox-runtime"),
            ("agentbox_core", "agentbox-core"),
            ("agentbox_protocol", "agentbox-protocol"),
            ("agentbox_browser_trust", "agentbox-browser-trust"),
        ):
            shutil.copytree(
                source / "packages" / folder / "src" / package,
                directory / "packages" / package,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
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
            "--property=DelegateSubgroup=agentbox-runtime-supervisor",
            "--property=ProtectControlGroups=yes",
            "--property=ProtectSystem=strict",
            "--property=PrivateTmp=yes",
            "--property=ReadWritePaths=/sys/fs/cgroup/system.slice/agentbox-runtime.service",
            "--property=NoNewPrivileges=yes",
            "--property=TasksMax=256",
            "--property=MemoryMax=512M",
            "--property=MemorySwapMax=0",
            "--property=CPUQuota=400%",
            "--property=RuntimeMaxSec=45",
            sys.executable,
            "-I",
            str(script),
            "--child",
        ]
        try:
            return subprocess.run(command, check=False, timeout=60).returncode
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
