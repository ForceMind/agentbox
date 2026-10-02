"""Actual pinned vendor binaries in isolated CI; no login or provider calls."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from agentbox_installer.waw_vendor_bootstrap import VENDOR_DOWNLOADS, decode_vendor_download
from agentbox_runtime.waw_vendor_probe import waw_vendor_probe_output_digest


@pytest.mark.skipif(
    os.environ.get("AGENTBOX_VENDOR_DISTRIBUTION_PROBE") != "1",
    reason="actual official downloads require the isolated Linux CI gate",
)
def test_actual_pinned_vendor_version_and_unauthenticated_probe(tmp_path: Path) -> None:
    gpg_home = tmp_path / "gpg"
    gpg_home.mkdir(mode=0o700)
    base = "https://downloads.claude.ai/claude-code-releases/" + VENDOR_DOWNLOADS[0].version
    for name, url in (
        ("key.asc", "https://downloads.claude.ai/keys/claude-code.asc"),
        ("manifest.json", base + "/manifest.json"),
        ("manifest.json.sig", base + "/manifest.json.sig"),
    ):
        subprocess.run(  # noqa: S603 - fixed public signing metadata only
            ["/usr/bin/curl", "-q", "-fsSL", "--max-time", "30", "-o", str(tmp_path / name), url],
            check=True,
            capture_output=True,
            timeout=35,
        )
    gpg = ["/usr/bin/gpg", "--batch", "--homedir", str(gpg_home)]
    subprocess.run(  # noqa: S603 - public key import in private disposable keyring
        [*gpg, "--import", str(tmp_path / "key.asc")], check=True, capture_output=True, timeout=10
    )
    listing = subprocess.run(  # noqa: S603 - readonly public key fingerprint
        [*gpg, "--with-colons", "--fingerprint"], check=True, capture_output=True, timeout=10
    ).stdout
    assert b"31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE" in listing
    verified = subprocess.run(  # noqa: S603 - detached public release-manifest signature
        [
            *gpg,
            "--status-fd",
            "1",
            "--verify",
            str(tmp_path / "manifest.json.sig"),
            str(tmp_path / "manifest.json"),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    ).stdout
    assert any(
        b"VALIDSIG" in line and b"31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE" in line
        for line in verified.splitlines()
    )
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    assert manifest["platforms"]["linux-x64"]["checksum"] == VENDOR_DOWNLOADS[0].sha256
    for spec in VENDOR_DOWNLOADS:
        artifact = tmp_path / (spec.kind + ".download")
        subprocess.run(  # noqa: S603 - two fixed, pinned HTTPS artifacts
            [
                "/usr/bin/curl",
                "-q",
                "-fsSL",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--max-time",
                "240",
                "--max-filesize",
                "268435456",
                "-o",
                str(artifact),
                spec.url,
            ],
            check=True,
            capture_output=True,
            timeout=250,
        )
        executable = tmp_path / spec.kind
        binary = decode_vendor_download(spec, artifact.read_bytes())
        executable.write_bytes(binary)
        executable.chmod(0o755)
        print(spec.kind, "actual verified native executable SHA256:", hashlib.sha256(binary).hexdigest())
        home = tmp_path / (spec.kind + "-home")
        home.mkdir(mode=0o700)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8"}
        result = subprocess.run(  # noqa: S603 - verified native binary, fixed --version, empty HOME
            [str(executable), "--version"], capture_output=True, timeout=30, env=env, check=False
        )
        assert result.returncode == 0 and spec.version.encode() in result.stdout
        print(spec.kind, "actual verified native version:", result.stdout.decode().strip())
        if spec.kind == "codex":
            result = subprocess.run(  # noqa: S603 - fixed readonly status in empty HOME
                [str(executable), "login", "status"],
                capture_output=True,
                timeout=30,
                env=env,
                check=False,
            )
            assert result.returncode != 0
            assert b"not logged in" in (result.stdout + result.stderr).lower()
            print(
                "codex unauthenticated framed stdout/stderr SHA256:",
                waw_vendor_probe_output_digest(result.stdout, result.stderr),
            )
