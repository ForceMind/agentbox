"""CI-only source readability probe and exact, bounded read-only fixture snapshot.

No dependency, HOME, credential or arbitrary sys.path copying. Only the fixed
AgentBox package directories and these two public test scripts are eligible.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from a3_native_fixture import FixtureChildError

PACKAGE_DIRS = (
    "apps/api/src/agentbox_api",
    "apps/worker/src/agentbox_worker",
    "apps/cli/src/agentbox_cli",
    "packages/agentbox-core/src/agentbox_core",
    "packages/agentbox-protocol/src/agentbox_protocol",
    "packages/agentbox-runtime/src/agentbox_runtime",
    "packages/agentbox-browser-trust/src/agentbox_browser_trust",
    "helper/src/agentbox_helper",
    "installer/src/agentbox_installer",
)
FIXTURE_FILES = ("tests/a3_native_fixture.py", "tests/a3_native_sources.py")
MAX_FILES = 1024
MAX_BYTES = 16 * 1024 * 1024
_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW

_SOURCE_PROBE = r"""
import importlib, json, os, stat, sys
phase = "parent-fence"
try:
    import ctypes
    parent = os.getppid()
    if ctypes.CDLL(None).prctl(1, 15, 0, 0, 0) != 0 or parent == 1 or os.getppid() != parent:
        raise RuntimeError()
    phase = "dependency-access"
    for module in ("cryptography", "fastapi", "sqlalchemy", "pydantic", "uvicorn", "h11", "argon2"):
        importlib.import_module(module)
    phase = "source-access"
    request = sys.stdin.buffer.read(65537)
    if len(request) > 65536:
        raise ValueError()
    paths = json.loads(request)
    if type(paths) is not list or not 1 <= len(paths) <= 1024:
        raise ValueError()
    for path in paths:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError()
            os.read(fd, 1)
        finally:
            os.close(fd)
    print(json.dumps({"readable": True}), flush=True)
except BaseException as error:
    print(json.dumps({"readable": False, "phase": phase, "code": type(error).__name__}), flush=True)
"""


def tracked_manifest(checkout: Path) -> tuple[str, ...]:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={checkout}",
            "-c",
            "core.fsmonitor=false",
            "ls-files",
            "-z",
            "--",
            *PACKAGE_DIRS,
            *FIXTURE_FILES,
        ],
        cwd=checkout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=5,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        },
    )
    if len(result.stdout) > 65536:
        raise ValueError("fixture source manifest exceeds bound")
    paths = tuple(
        sorted(
            path.decode("utf-8")
            for path in result.stdout.split(b"\0")
            if path and path.endswith(b".py")
        )
    )
    if not 1 <= len(paths) <= MAX_FILES or not set(FIXTURE_FILES).issubset(paths):
        raise ValueError("fixture tracked source manifest incomplete")
    return paths


def source_inventory(checkout: Path, paths: tuple[str, ...] | None = None) -> dict[str, bytes]:
    """Read the tracked Python whitelist through exact no-follow descriptors."""
    selected = tracked_manifest(checkout) if paths is None else paths
    result: dict[str, bytes] = {}
    total = 0
    root = os.open(checkout, _FLAGS | os.O_DIRECTORY)
    try:
        for relative in selected:
            if (
                not relative.endswith(".py")
                or any(part in {"", ".", ".."} for part in relative.split("/"))
                or not (
                    relative in FIXTURE_FILES
                    or any(relative.startswith(package + "/") for package in PACKAGE_DIRS)
                )
            ):
                raise ValueError("fixture source manifest scope mismatch")
            parts = relative.split("/")
            fd = os.dup(root)
            try:
                for part in parts[:-1]:
                    child = os.open(part, _FLAGS | os.O_DIRECTORY, dir_fd=fd)
                    os.close(fd)
                    fd = child
                opened = os.open(parts[-1], _FLAGS | os.O_NONBLOCK, dir_fd=fd)
                with os.fdopen(opened, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    if (
                        not stat.S_ISREG(before.st_mode)
                        or before.st_nlink != 1
                        or before.st_size > MAX_BYTES
                    ):
                        raise ValueError("fixture source must be bounded regular files")
                    data = stream.read(MAX_BYTES + 1)
                    after = os.fstat(stream.fileno())
                if len(data) != before.st_size or (before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                ):
                    raise ValueError("fixture source changed during read")
                total += len(data)
                if len(result) >= MAX_FILES or total > MAX_BYTES:
                    raise ValueError("fixture source snapshot exceeds bound")
                result[relative] = data
            finally:
                os.close(fd)
    finally:
        os.close(root)
    return result


def inventory_digest(inventory: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path, data in sorted(inventory.items()):
        digest.update(path.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()


def probe_sources(
    checkout: Path,
    inventory: dict[str, bytes],
    uid: int,
    gid: int,
    role: str,
    environment: dict[str, str],
) -> bool:
    payload = json.dumps([str(checkout / path) for path in sorted(inventory)]).encode()
    if len(payload) > 65536:
        raise ValueError("fixture source probe exceeds bound")
    try:
        result = subprocess.run(
            [sys.executable, "-c", _SOURCE_PROBE],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd="/",
            env=environment,
            user=uid,
            group=gid,
            extra_groups=[],
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise FixtureChildError(role, "source-probe", "TimeoutError") from None
    except OSError as error:
        raise FixtureChildError(role, "source-probe", type(error).__name__) from None
    if result.returncode != 0 or not result.stdout or len(result.stdout) > 512:
        raise FixtureChildError(role, "source-probe", "ChildExited", result.returncode)
    try:
        reply = json.loads(result.stdout)
    except ValueError:
        raise FixtureChildError(role, "source-probe", "ValueError") from None
    if reply == {"readable": True}:
        return True
    if reply == {"readable": False, "phase": "source-access", "code": "PermissionError"}:
        return False
    if type(reply) is not dict:
        raise FixtureChildError(role, "source-probe", "TypeError")
    phase = reply.get("phase")
    raise FixtureChildError(
        role, phase if type(phase) is str else "source-probe", reply.get("code")
    )


def copy_sources(checkout: Path, destination: Path, inventory: dict[str, bytes]) -> str:
    destination.mkdir(mode=0o700)
    for relative, data in inventory.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(data)
        target.chmod(0o444)
    # Both destination bytes and the still-current source bytes must match.
    digest = inventory_digest(inventory)
    if (
        inventory_digest(source_inventory(destination, tuple(inventory))) != digest
        or inventory_digest(source_inventory(checkout, tuple(inventory))) != digest
    ):
        raise ValueError("fixture source snapshot digest mismatch")
    for directory, _, _ in os.walk(destination, topdown=False):
        os.chmod(directory, 0o555)
    return digest


def verify_root_snapshot(destination: Path, paths: tuple[str, ...]) -> None:
    """Measure root ownership and nonwritable mode before exposing the snapshot."""

    def check(fd: int, directory: bool) -> None:
        details = os.fstat(fd)
        expected = stat.S_ISDIR(details.st_mode) if directory else stat.S_ISREG(details.st_mode)
        if not expected or details.st_uid != 0 or details.st_mode & 0o222:
            raise PermissionError("fixture snapshot owner or mode is not root read-only")

    root = os.open(destination, _FLAGS | os.O_DIRECTORY)
    try:
        check(root, True)
        for relative in paths:
            fd = os.dup(root)
            try:
                components = relative.split("/")
                if any(part in {"", ".", ".."} for part in components):
                    raise ValueError("fixture snapshot path invalid")
                for part in components[:-1]:
                    child = os.open(part, _FLAGS | os.O_DIRECTORY, dir_fd=fd)
                    os.close(fd)
                    fd = child
                    check(fd, True)
                leaf = os.open(components[-1], _FLAGS | os.O_NONBLOCK, dir_fd=fd)
                try:
                    check(leaf, False)
                finally:
                    os.close(leaf)
            finally:
                os.close(fd)
    finally:
        os.close(root)


def prepare_sources(
    checkout: Path, process_root: Path, environment: dict[str, str]
) -> tuple[Path, dict[str, Any]]:
    if os.geteuid() != 0:
        raise PermissionError("numeric UID source preparation is CI root-only")
    inventory = source_inventory(checkout)
    access = [
        probe_sources(checkout, inventory, uid, uid, role, environment)
        for uid, role in ((61131, "api"), (61132, "runtime"))
    ]
    digest = inventory_digest(inventory)
    target = checkout
    if not all(access):
        target = process_root / "source"
        digest = copy_sources(checkout, target, inventory)
        verify_root_snapshot(target, tuple(inventory))
        if not all(
            probe_sources(target, inventory, uid, uid, role, environment)
            for uid, role in ((61131, "api"), (61132, "runtime"))
        ):
            raise PermissionError("numeric UID cannot read bounded source snapshot")
    return target, {
        "source_staged": target != checkout,
        "source_files": len(inventory),
        "source_digest": digest,
    }
