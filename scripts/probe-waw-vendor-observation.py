#!/usr/bin/env python3
"""Disposable native proof for Runtime-only fixed vendor observation."""

from __future__ import annotations

import grp
import json
import os
import platform
import pwd
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from agentbox_installer.host import HostOperations
from agentbox_installer.waw_vendor_bootstrap import VENDOR_DOWNLOADS, decode_vendor_download

VENDOR_PATHS = {
    "claude": Path("/usr/local/bin/claude"),
    "codex": Path("/usr/local/bin/codex"),
}
RUNTIME_USER = "agentbox-runtime"
RUNTIME_GROUP = "agentbox-runtime"


def _run(*argv: str) -> None:
    subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=60,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
    )


def _identity_exists() -> bool:
    try:
        pwd.getpwnam(RUNTIME_USER)
        return True
    except KeyError:
        pass
    try:
        grp.getgrnam(RUNTIME_GROUP)
        return True
    except KeyError:
        return False


def main() -> int:
    if (
        sys.argv[1:]
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or platform.system() != "Linux"
        or os.geteuid() != 0
    ):
        raise SystemExit("isolated Linux root GitHub Actions runner required")
    if Path("/proc/1/comm").read_text(encoding="ascii").strip() != "systemd":
        raise SystemExit("native systemd PID 1 required; no simulated pass")
    if _identity_exists():
        raise SystemExit("pre-existing agentbox-runtime identity makes this runner unsuitable")
    for path in VENDOR_PATHS.values():
        if path.exists() or path.is_symlink():
            raise SystemExit(f"pre-existing vendor path makes this runner unsuitable: {path}")

    host = HostOperations(real_host=True)
    created_identity = False
    created_paths: list[Path] = []
    try:
        _run("/usr/sbin/groupadd", "--system", RUNTIME_GROUP)
        _run(
            "/usr/sbin/useradd",
            "--system",
            "--gid",
            RUNTIME_GROUP,
            "--home-dir",
            "/home/agentbox-runtime",
            "--shell",
            "/usr/sbin/nologin",
            RUNTIME_USER,
        )
        created_identity = True
        for spec in VENDOR_DOWNLOADS:
            raw = decode_vendor_download(spec, host.download_waw_vendor(spec))
            path = VENDOR_PATHS[spec.kind]
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o755,
            )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
            os.chown(path, 0, 0)
            os.chmod(path, 0o755)
            facts = path.lstat()
            if (
                not stat.S_ISREG(facts.st_mode)
                or facts.st_uid != 0
                or facts.st_gid != 0
                or stat.S_IMODE(facts.st_mode) != 0o755
                or facts.st_nlink != 1
            ):
                raise AssertionError("fixed vendor publication provenance is invalid")
            created_paths.append(path)

        observed = host.observe_waw_vendors()
        value = asdict(observed)
        if set(value) != {
            "claude_vendor_version",
            "codex_vendor_version",
            "codex_unauthenticated_output_sha256",
        }:
            raise AssertionError("Runtime vendor observation result is not closed")
        if not value["claude_vendor_version"].startswith("2.1.286"):
            raise AssertionError("unexpected Claude vendor observation")
        if "0.159.3" not in value["codex_vendor_version"]:
            raise AssertionError("unexpected Codex vendor observation")
        if (
            len(value["codex_unauthenticated_output_sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in value["codex_unauthenticated_output_sha256"])
        ):
            raise AssertionError("invalid Codex framed observation digest")
        print(json.dumps(value, sort_keys=True))
        return 0
    finally:
        for path in reversed(created_paths):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if created_identity:
            subprocess.run(
                ("/usr/sbin/userdel", RUNTIME_USER),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
            subprocess.run(
                ("/usr/sbin/groupdel", RUNTIME_GROUP),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
        home = Path("/home/agentbox-runtime")
        if home.exists() and home.is_dir() and not any(home.iterdir()):
            home.rmdir()
        shutil.rmtree("/tmp/agentbox-waw-vendor-observe-orphan", ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
