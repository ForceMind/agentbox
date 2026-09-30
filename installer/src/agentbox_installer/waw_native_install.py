"""Build the three fixed WAW helpers from an already verified release.

Host compilation avoids shipping a newer build host's glibc requirement to
OpenCloudOS. The generated directory is published atomically, with an exact
source/output ledger; it never changes the checksummed release manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import signal
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

NATIVE_HELPERS = (
    "agentbox-waw-pane-bootstrap",
    "agentbox-waw-bridge",
    "agentbox-waw-attach-supervisor",
)
_LEDGER = "build-record.v1.json"
_SCHEMA = "agentbox-waw-native-build.v1"
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class WAWNativeInstallError(RuntimeError):
    pass


def _run_command(argv: tuple[str, ...], release: Path, environment: dict[str, str]) -> None:
    # Killing only the Python build-script parent would leave a root compiler
    # writing into a staging directory being removed after timeout/cancel.
    with subprocess.Popen(
        argv,
        cwd=release,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    ) as process:
        try:
            code = process.wait(timeout=180)
        except BaseException:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            raise
        if code != 0:
            raise subprocess.CalledProcessError(code, argv[0])


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _identity(item: os.stat_result) -> tuple[int, ...]:
    return (
        item.st_dev,
        item.st_ino,
        item.st_uid,
        item.st_gid,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _read(path: Path, *, owner: int, mode: int, limit: int) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != owner
                or stat.S_IMODE(before.st_mode) != mode
                or before.st_nlink != 1
                or not 0 < before.st_size <= limit
            ):
                raise WAWNativeInstallError("generated WAW helper provenance is invalid")
            raw = bytearray()
            while len(raw) <= limit:
                chunk = os.read(fd, min(1024 * 1024, limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            if (
                len(raw) != before.st_size
                or len(raw) > limit
                or _identity(os.fstat(fd)) != _identity(before)
                or _identity(path.lstat()) != _identity(before)
            ):
                raise WAWNativeInstallError("generated WAW helper changed during read")
            return bytes(raw)
        finally:
            os.close(fd)
    except OSError as exc:
        raise WAWNativeInstallError("generated WAW helper cannot be read safely") from exc


def _sources(files: Mapping[str, str]) -> dict[str, str]:
    from agentbox_installer.build import RELEASE_NATIVE_BUILD_SCRIPTS, RELEASE_NATIVE_SOURCE_FILES

    names = (*RELEASE_NATIVE_SOURCE_FILES, *RELEASE_NATIVE_BUILD_SCRIPTS)
    if any(name not in files for name in names):
        raise WAWNativeInstallError("release is missing reviewed WAW native build inputs")
    return {name: files[name] for name in names}


def verify_installed_waw_helpers(release: Path, files: Mapping[str, str]) -> set[str]:
    """Verify only the exact generated subtree; absence retains legacy releases."""
    directory = release / "libexec"
    if not directory.exists() and not directory.is_symlink():
        return set()
    owner = release.lstat().st_uid
    try:
        before = directory.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or before.st_uid != owner
            or stat.S_IMODE(before.st_mode) != 0o755
            or {path.name for path in directory.iterdir()} != {*NATIVE_HELPERS, _LEDGER}
        ):
            raise WAWNativeInstallError("generated WAW helper directory is invalid")
        raw = _read(directory / _LEDGER, owner=owner, mode=0o644, limit=8192)
        record = json.loads(raw)
        if (
            not isinstance(record, dict)
            or set(record) != {"schema_version", "source_files", "binaries"}
            or record["schema_version"] != _SCHEMA
            or record["source_files"] != _sources(files)
            or not isinstance(record["binaries"], dict)
            or set(record["binaries"]) != set(NATIVE_HELPERS)
            or _canonical(record) != raw
        ):
            raise WAWNativeInstallError("generated WAW helper ledger is invalid")
        for name in NATIVE_HELPERS:
            payload = _read(directory / name, owner=owner, mode=0o755, limit=16 * 1024 * 1024)
            if (
                len(payload) < 64
                or payload[:6] != b"\x7fELF\x02\x01"
                or payload[16:20] != b"\x03\x00\x3e\x00"
                or hashlib.sha256(payload).hexdigest() != record["binaries"][name]
            ):
                raise WAWNativeInstallError("generated WAW helper digest or ELF target is invalid")
        if _identity(directory.lstat()) != _identity(before):
            raise WAWNativeInstallError("generated WAW helper directory changed")
        return {"libexec", *(f"libexec/{name}" for name in (*NATIVE_HELPERS, _LEDGER))}
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise WAWNativeInstallError("generated WAW helper ledger cannot be verified") from exc


def prepare_waw_helpers(release: Path) -> None:
    """Compile fixed sources and commit one complete directory before activation."""
    from agentbox_installer.artifact import verify_release

    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise WAWNativeInstallError("WAW helper installation requires Linux x86_64")
    if os.geteuid() != 0:
        raise WAWNativeInstallError("WAW helper installation requires root")
    for directory in (release, release.parent):
        facts = directory.lstat()
        if not stat.S_ISDIR(facts.st_mode) or facts.st_uid != 0 or facts.st_mode & 0o022:
            raise WAWNativeInstallError("WAW helper release directories must be root-owned")
    manifest = verify_release(release, allow_generated_venv=True, allow_generated_native=True)
    if verify_installed_waw_helpers(release, manifest.files):
        return
    source_files = _sources(manifest.files)
    for name, expected in source_files.items():
        raw = _read(release / name, owner=0, mode=0o644, limit=2 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise WAWNativeInstallError("WAW native build source changed")
    for tool in ("/usr/bin/cc", "/usr/bin/readelf"):
        try:
            resolved = Path(tool).resolve(strict=True)
            facts = resolved.stat()
            if (
                not resolved.is_relative_to("/usr/bin")
                or not stat.S_ISREG(facts.st_mode)
                or facts.st_uid != 0
                or facts.st_mode & 0o022
                or not os.access(resolved, os.X_OK)
            ):
                raise WAWNativeInstallError("fixed native compiler tools are untrusted")
        except OSError as exc:
            raise WAWNativeInstallError(
                "install the fixed gcc/binutils dependencies first"
            ) from exc
    environment = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}
    try:
        with tempfile.TemporaryDirectory(prefix=".agentbox-waw-build-", dir=release.parent) as temp:
            output = Path(temp) / "libexec"
            for argv in (
                (
                    sys.executable,
                    "-I",
                    str(release / "scripts/build-waw-native.py"),
                    "--cc",
                    "/usr/bin/cc",
                    "--output",
                    str(output),
                ),
                (
                    sys.executable,
                    "-I",
                    str(release / "scripts/check-waw-native.py"),
                    "--cc",
                    "/usr/bin/cc",
                    "--no-build",
                    "--binary-dir",
                    str(output),
                ),
            ):
                _run_command(argv, release, environment)
            if {path.name for path in output.iterdir()} != set(NATIVE_HELPERS):
                raise WAWNativeInstallError("native compiler output is not exact")
            binaries = {}
            for name in NATIVE_HELPERS:
                path = output / name
                path.chmod(0o755)
                raw = _read(path, owner=0, mode=0o755, limit=16 * 1024 * 1024)
                binaries[name] = hashlib.sha256(raw).hexdigest()
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
            ledger = output / _LEDGER
            with ledger.open("xb") as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(
                    _canonical(
                        {
                            "schema_version": _SCHEMA,
                            "source_files": source_files,
                            "binaries": binaries,
                        }
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
            output.chmod(0o755)
            temporary_root = Path(temp)
            # Verify the complete prepared subtree using the same readback as
            # installed state; it has the same root owner as the release.
            verify_installed_waw_helpers(temporary_root, manifest.files)
            directory_fd = os.open(output, _DIRECTORY_FLAGS)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            verify_release(release, allow_generated_venv=True)
            os.rename(output, release / "libexec")
            parent_fd = os.open(release, _DIRECTORY_FLAGS)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            verify_release(release, allow_generated_venv=True, allow_generated_native=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WAWNativeInstallError(
            "WAW helper build/publication failed before activation"
        ) from exc
