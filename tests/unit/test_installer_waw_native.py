from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from agentbox_installer.artifact import ArtifactError, verify_release
from agentbox_installer.build import RELEASE_NATIVE_BUILD_SCRIPTS, RELEASE_NATIVE_SOURCE_FILES
from agentbox_installer.waw_native_install import (
    NATIVE_HELPERS,
    WAWNativeInstallError,
    _run_command,
    prepare_waw_helpers,
    verify_installed_waw_helpers,
)
from pytest import MonkeyPatch

_ROOT = Path(__file__).resolve().parents[2]
_LINUX_ROOT = platform.system() == "Linux" and os.geteuid() == 0


def _release(tmp_path: Path) -> Path:
    release = tmp_path / "release"
    release.mkdir(mode=0o755)
    files = {}
    for name in (*RELEASE_NATIVE_SOURCE_FILES, *RELEASE_NATIVE_BUILD_SCRIPTS):
        target = release / name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(_ROOT / name, target)
        target.chmod(0o644)
        files[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "0.3.0rc30",
                "database_revision": "fixture",
                "database_backward_compatible": False,
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return release


def _generated_fixture(release: Path) -> dict[str, object]:
    """Synthetic ELF headers test ledger validation only, never native behavior."""
    manifest = verify_release(release)
    output = release / "libexec"
    output.mkdir(mode=0o755)
    binaries = {}
    for name in NATIVE_HELPERS:
        raw = bytearray(64)
        raw[:6] = b"\x7fELF\x02\x01"
        raw[16:20] = b"\x03\x00\x3e\x00"
        path = output / name
        path.write_bytes(raw)
        path.chmod(0o755)
        binaries[name] = hashlib.sha256(raw).hexdigest()
    record: dict[str, object] = {
        "schema_version": "agentbox-waw-native-build.v1",
        "source_files": manifest.files,
        "binaries": binaries,
    }
    _write_record(release, record)
    return record


def _write_record(release: Path, record: dict[str, object]) -> None:
    path = release / "libexec/build-record.v1.json"
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii"
    )
    path.chmod(0o644)


def test_generated_native_is_explicit_and_exact(tmp_path: Path) -> None:
    release = _release(tmp_path)
    _generated_fixture(release)
    with pytest.raises(ArtifactError, match="release file digest mismatch"):
        verify_release(release)
    manifest = verify_release(release, allow_generated_native=True)
    assert len(verify_installed_waw_helpers(release, manifest.files)) == 5
    (release / "libexec/unknown").write_bytes(b"preserve")
    with pytest.raises(ArtifactError, match="native helpers"):
        verify_release(release, allow_generated_native=True)
    assert (release / "libexec/unknown").read_bytes() == b"preserve"


@pytest.mark.parametrize(
    "change", ["binary", "mode", "hardlink", "symlink", "ledger", "source", "elf"]
)
def test_generated_native_rejects_tampering(tmp_path: Path, change: str) -> None:
    release = _release(tmp_path)
    record = _generated_fixture(release)
    binary = release / "libexec" / NATIVE_HELPERS[0]
    if change == "binary":
        binary.write_bytes(b"different")
    elif change == "mode":
        binary.chmod(0o775)
    elif change == "hardlink":
        os.link(binary, tmp_path / "other-link")
    elif change == "symlink":
        raw = binary.read_bytes()
        binary.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(raw)
        binary.symlink_to(outside)
    elif change == "ledger":
        record["unknown"] = "field"
        _write_record(release, record)
    elif change == "source":
        record["source_files"] = {}
        _write_record(release, record)
    else:
        arm_payload = bytearray(binary.read_bytes())
        arm_payload[18:20] = b"\xb7\x00"  # AArch64 is not the declared x86_64 target.
        binary.write_bytes(arm_payload)
        binaries = record["binaries"]
        assert isinstance(binaries, dict)
        binaries[NATIVE_HELPERS[0]] = hashlib.sha256(arm_payload).hexdigest()
        _write_record(release, record)
    with pytest.raises(ArtifactError, match="native helpers"):
        verify_release(release, allow_generated_native=True)


def test_generated_directory_symlink_is_never_followed(tmp_path: Path) -> None:
    release = _release(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"preserve")
    (release / "libexec").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactError, match="native helpers"):
        verify_release(release, allow_generated_native=True)
    assert (outside / "sentinel").read_bytes() == b"preserve"


def test_native_build_timeout_kills_the_child_process_group(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    marker = tmp_path / "child-started"
    completed = tmp_path / "child-completed"
    child = (
        "import pathlib,time; "
        f"pathlib.Path({str(marker)!r}).write_text('started'); "
        "time.sleep(0.5); "
        f"pathlib.Path({str(completed)!r}).write_text('leaked')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-I','-c',{child!r}]); time.sleep(30)"
    )
    original = subprocess.Popen

    def spawn(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process: subprocess.Popen[bytes] = original(*args, **kwargs)  # type: ignore[call-overload]
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not marker.exists():
            os.killpg(process.pid, 9)
            process.wait()
            pytest.fail("child did not start")
        wait = process.wait
        first = True

        def bounded_wait(timeout: float | None = None) -> int:
            nonlocal first
            if first:
                first = False
                return wait(timeout=0.05)
            return wait(timeout=timeout)

        monkeypatch.setattr(process, "wait", bounded_wait)
        return process

    monkeypatch.setattr("agentbox_installer.waw_native_install.subprocess.Popen", spawn)
    with pytest.raises(subprocess.TimeoutExpired):
        _run_command((sys.executable, "-I", "-c", parent), tmp_path, {"LANG": "C.UTF-8"})
    time.sleep(0.6)
    assert not completed.exists(), "compiler child survived cancellation"


@pytest.mark.skipif(not _LINUX_ROOT, reason="requires isolated Linux root CI fixture")
def test_linux_installer_compiles_verifies_and_reuses_actual_helpers(tmp_path: Path) -> None:
    release = _release(tmp_path)
    prepare_waw_helpers(release)
    manifest = verify_release(release, allow_generated_native=True)
    before = {name: (release / "libexec" / name).stat().st_ino for name in NATIVE_HELPERS}
    prepare_waw_helpers(release)
    assert before == {name: (release / "libexec" / name).stat().st_ino for name in NATIVE_HELPERS}
    for name in NATIVE_HELPERS:
        result = subprocess.run(
            [str(release / "libexec" / name), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        assert result.stdout == f"{name} 1\n"
    assert verify_installed_waw_helpers(release, manifest.files)


@pytest.mark.skipif(not _LINUX_ROOT, reason="requires isolated Linux root CI fixture")
def test_linux_failed_native_build_can_retry_without_partial_publication(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    release = _release(tmp_path)
    with monkeypatch.context() as scoped:

        def fail(*_args: object, **_kwargs: object) -> None:
            raise subprocess.CalledProcessError(1, "fixed compiler")

        scoped.setattr("agentbox_installer.waw_native_install._run_command", fail)
        with pytest.raises(WAWNativeInstallError, match="before activation"):
            prepare_waw_helpers(release)
    assert not (release / "libexec").exists()
    assert list(tmp_path.glob(".agentbox-waw-build-*")) == []
    verify_release(release)
    prepare_waw_helpers(release)
    verify_release(release, allow_generated_native=True)
