"""Exercise the actual bootstrap body with local transport/platform fixtures."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "installer/bootstrap.sh"


def _run(
    tmp_path: Path,
    *,
    extra: tarfile.TarInfo | None = None,
    wrong_digest: bool = False,
    verify_failure: bool = False,
    apply: bool = False,
    resume: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    remote = tmp_path / "remote"
    remote.mkdir()
    log = tmp_path / "calls"
    archive = remote / "agentbox-0.3.0rc30-linux-x86_64.tar.gz"
    script = f"#!/bin/bash\nprintf '%s\\n' \"$1\" >> '{log}'\n"
    if verify_failure:
        script += 'if [[ "$1" == "verify-artifact" ]]; then exit 16; fi\n'
    raw = script.encode()
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo("install.sh")
        member.size = len(raw)
        member.mode = 0o755
        bundle.addfile(member, io.BytesIO(raw))
        if extra is not None:
            bundle.addfile(extra, io.BytesIO(b"x") if extra.isfile() else None)
    for name in ("SHA256SUMS", "RELEASE_MANIFEST.json", "SBOM.spdx.json"):
        (remote / name).write_text("fixture", encoding="utf-8")
    curl = tmp_path / "curl"
    curl.write_text(
        f"#!{sys.executable}\nimport pathlib, shutil, sys\n"
        "args = sys.argv[1:]\n"
        "assert args[0] == '-q'\n"
        "assert '--proto-redir' in args and '=https' in args\n"
        "assert args[-1].startswith('https://github.com/ForceMind/agentbox/releases/download/v0.3.0rc30/')\n"
        f"source = pathlib.Path({str(remote)!r}) / args[-1].rsplit('/', 1)[-1]\n"
        "shutil.copyfile(source, args[args.index('--output') + 1])\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    body = _SCRIPT.read_text(encoding="utf-8").split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    # Only this copied test body changes host and transport. Production exposes
    # neither an arbitrary URL nor a platform/interpreter bypass.
    body = body.replace('platform.system() != "Linux" or platform.machine() != "x86_64"', "False")
    body = body.replace("(apply or resume) and os.geteuid() != 0", "False")
    body = body.replace('"/usr/bin/curl"', repr(str(curl)))
    digest = "0" * 64 if wrong_digest else hashlib.sha256(archive.read_bytes()).hexdigest()
    arguments = [sys.executable, "-I", "-", "0.3.0rc30", digest]
    if apply:
        arguments.append("--apply")
    elif resume:
        arguments.append("--resume")
    result = subprocess.run(
        arguments, input=body, text=True, capture_output=True, check=False, timeout=20
    )
    return result, log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("apply,resume", [(False, False), (True, False), (False, True)])
def test_download_verifies_and_plans_before_optional_apply(
    tmp_path: Path,
    apply: bool,
    resume: bool,
) -> None:
    result, calls = _run(tmp_path, apply=apply, resume=resume)
    assert result.returncode == 0, result.stderr
    assert calls == ["verify-artifact", "plan"] + (
        ["resume-install"] if resume else ["apply"] if apply else []
    )


def test_download_pinned_digest_failure_never_executes_payload(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, wrong_digest=True, apply=True)
    assert result.returncode == 18
    assert "pinned artifact checksum mismatch" in result.stderr
    assert calls == []


def test_download_failed_manifest_verification_never_plans_or_applies(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, verify_failure=True, apply=True)
    assert result.returncode == 18
    assert calls == ["verify-artifact"]


@pytest.mark.parametrize("kind", ["traversal", "symlink", "collision", "oversized"])
def test_download_unsafe_archive_never_executes_payload(tmp_path: Path, kind: str) -> None:
    member = tarfile.TarInfo("../outside" if kind == "traversal" else "INSTALL.SH")
    member.size = 1
    if kind == "symlink":
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/shadow"
    elif kind == "oversized":
        member.type = tarfile.DIRTYPE
        member.size = 513 * 1024 * 1024
    result, calls = _run(tmp_path, extra=member)
    assert result.returncode == 18, result.stderr
    assert calls == []


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["main", "0" * 64],
        ["0.3.0rc30", "invalid"],
        ["0.3.0rc30", "0" * 64, "--force"],
    ],
)
def test_download_shell_rejects_unpinned_or_unknown_inputs(arguments: list[str]) -> None:
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), *arguments], capture_output=True, check=False, timeout=5
    )
    assert result.returncode == 18
