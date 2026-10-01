from __future__ import annotations

import hashlib
import io
import os
import tarfile
from pathlib import Path

import agentbox_installer.waw_vendor_bootstrap as module
import pytest
from agentbox_installer.waw_manifest_install import WAWManifestInstallError
from agentbox_runtime.waw_executable import WAWExecutableError, WAWExecutableKind, WAWExecutablePin
from test_installer_waw_manifests import _fixture


def _downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[module.WAWVendorBootstrap, Path, dict[str, bytes]]:
    issuer, root = _fixture(tmp_path)
    raw = (root / "usr/local/bin/claude").read_bytes()
    for kind in ("claude", "codex"):
        (root / f"usr/local/bin/{kind}").unlink()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        entry = tarfile.TarInfo("codex-x86_64-unknown-linux-musl")
        entry.size = len(raw)
        archive.addfile(entry, io.BytesIO(raw))
    compressed = output.getvalue()
    specs = (
        module.VendorDownload(
            "claude",
            "fixture",
            "https://fixture.test/claude",
            hashlib.sha256(raw).hexdigest(),
            None,
        ),
        module.VendorDownload(
            "codex",
            "fixture",
            "https://fixture.test/codex",
            hashlib.sha256(compressed).hexdigest(),
            "codex-x86_64-unknown-linux-musl",
        ),
    )
    monkeypatch.setattr(module, "VENDOR_DOWNLOADS", specs)
    payloads = {"claude": raw, "codex": compressed}
    return module.WAWVendorBootstrap(issuer), root, payloads


def test_vendor_plan_and_atomic_install_never_execute_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap, root, payloads = _downloads(tmp_path, monkeypatch)
    calls: list[str] = []

    def download(spec: module.VendorDownload) -> bytes:
        calls.append(spec.kind)
        return payloads[spec.kind]

    bootstrap.install(plan=True, recover=False, download=download)
    assert calls == [] and not (root / "usr/local/bin/claude").exists()
    result = bootstrap.install(plan=False, recover=False, download=download)
    assert result["credentials_read"] is False and result["services_started"] is False
    assert calls == ["claude", "codex"]
    for kind in calls:
        assert (root / f"usr/local/bin/{kind}").stat().st_mode & 0o777 == 0o755
    inode = (root / "usr/local/bin/codex").stat().st_ino
    bootstrap.install(plan=False, recover=False, download=download)
    assert (root / "usr/local/bin/codex").stat().st_ino == inode


def test_invalid_second_payload_does_not_publish_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap, root, payloads = _downloads(tmp_path, monkeypatch)
    payloads["codex"] = b"bad archive"
    with pytest.raises(WAWManifestInstallError, match="checksum"):
        bootstrap.install(plan=False, recover=False, download=lambda spec: payloads[spec.kind])
    assert not (root / "usr/local/bin/claude").exists()


def test_existing_vendor_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap, root, payloads = _downloads(tmp_path, monkeypatch)
    path = root / "usr/local/bin/codex"
    path.write_bytes(b"foreign vendor")
    path.chmod(0o755)
    with pytest.raises(WAWManifestInstallError):
        bootstrap.install(plan=False, recover=True, download=lambda spec: payloads[spec.kind])
    assert path.read_bytes() == b"foreign vendor"
    assert not (root / "usr/local/bin/claude").exists()


def test_only_fixed_codex_pin_admits_larger_executable() -> None:
    size = 384 * 1024 * 1024
    WAWExecutablePin(Path("/usr/local/bin/codex"), "a" * 64, size, WAWExecutableKind.CODEX)
    for kind, path in (
        (None, "/usr/local/bin/codex"),
        (WAWExecutableKind.CLAUDE, "/usr/local/bin/claude"),
        (WAWExecutableKind.CODEX, "/opt/other/native"),
    ):
        with pytest.raises(WAWExecutableError, match="limit"):
            WAWExecutablePin(Path(path), "a" * 64, size, kind)


def test_vendor_link_publication_interruption_has_exact_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap, root, payloads = _downloads(tmp_path, monkeypatch)
    original = os.unlink

    def interrupted(path: str, *, dir_fd: int | None = None) -> None:
        if path.startswith(".claude.agentbox-"):
            raise OSError("synthetic interrupted vendor publication")
        original(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", interrupted)
    with pytest.raises(OSError):
        bootstrap.install(plan=False, recover=False, download=lambda spec: payloads[spec.kind])
    monkeypatch.setattr(os, "unlink", original)
    assert (root / "usr/local/bin/claude").stat().st_nlink == 2
    bootstrap.install(plan=False, recover=True, download=lambda spec: payloads[spec.kind])
    assert (root / "usr/local/bin/claude").stat().st_nlink == 1
