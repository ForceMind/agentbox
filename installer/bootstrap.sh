#!/usr/bin/env bash
set -euo pipefail
umask 077

# Publication supplies an immutable version and independently pinned archive
# digest. No latest/main URL or downloaded checksum is a trust anchor.
if [[ $# -lt 2 || $# -gt 3 || ! "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+(rc[1-9][0-9]*)?$ || ! "$2" =~ ^[0-9a-f]{64}$ ]]; then
  printf 'Usage: bash bootstrap.sh VERSION SHA256 [--apply|--resume]\n' >&2
  exit 18
fi
if [[ $# -eq 3 && "$3" != "--apply" && "$3" != "--resume" ]]; then
  printf 'Installation options are --apply or explicit --resume; default is a read-only plan.\n' >&2
  exit 18
fi
bootstrap_python=""
for candidate in /usr/bin/python3 /usr/bin/python3.13 /usr/bin/python3.12 /usr/bin/python3.11; do
  if [[ -x "${candidate}" ]] && "${candidate}" -I -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)' >/dev/null 2>&1; then
    bootstrap_python="${candidate}"
    break
  fi
done
if [[ -z "${bootstrap_python}" ]]; then
  printf 'AgentBox requires Python 3.11, 3.12 or 3.13 in /usr/bin.\n' >&2
  exit 18
fi
"${bootstrap_python}" -I - "$@" <<'PY'
import hashlib
import os
import pathlib
import platform
import stat
import subprocess
import sys
import tarfile
import tempfile
import unicodedata

def fail(message):
    print("AgentBox: " + message, file=sys.stderr)
    raise SystemExit(18)

version, expected = sys.argv[1:3]
apply = sys.argv[3:] == ["--apply"]
resume = sys.argv[3:] == ["--resume"]
if platform.system() != "Linux" or platform.machine() != "x86_64":
    fail("this artifact requires Linux x86_64")
if (apply or resume) and os.geteuid() != 0:
    fail("installation/resume requires root; run the published command in a root shell")
archive_name = f"agentbox-{version}-linux-x86_64.tar.gz"
base = f"https://github.com/ForceMind/agentbox/releases/download/v{version}/"
environment = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}

try:
    with tempfile.TemporaryDirectory(prefix="agentbox-download-", dir="/tmp") as temporary:
        stage = pathlib.Path(temporary)
        os.chmod(stage, 0o700)
        for name in (archive_name, "SHA256SUMS", "RELEASE_MANIFEST.json", "SBOM.spdx.json"):
            subprocess.run(
                ("/usr/bin/curl", "-q", "--fail", "--silent", "--show-error",
                 "--location", "--proto", "=https", "--proto-redir", "=https",
                 "--connect-timeout", "15", "--max-time", "300", "--max-filesize",
                 str(64 * 1024 * 1024 if name == archive_name else 8 * 1024 * 1024),
                 "--output", str(stage / name), base + name),
                env=environment, stdin=subprocess.DEVNULL, check=True, timeout=310,
            )
            if (stage / name).stat().st_size > (64 * 1024 * 1024 if name == archive_name else 8 * 1024 * 1024):
                fail("download exceeds release size limit")
        artifact = stage / archive_name
        with artifact.open("rb") as stream:
            observed = hashlib.file_digest(stream, "sha256").hexdigest()
        if observed != expected:
            fail("pinned artifact checksum mismatch; nothing installed")
        release = stage / "release"
        release.mkdir(mode=0o700)
        paths = set()
        total = 0
        with tarfile.open(artifact, "r:gz") as archive:
            for member in archive:
                total += max(0, member.size)
                parts = member.name.split("/")
                normalized = unicodedata.normalize("NFKC", member.name)
                if (len(paths) >= 20000 or total > 512 * 1024 * 1024
                    or len(parts) > 32 or len(member.name.encode()) > 4096
                    or normalized != member.name or normalized.casefold() in paths
                    or any(part in ("", ".", "..") for part in parts)
                    or "\\" in member.name
                    or any(ord(char) < 32 or ord(char) == 127 for char in member.name)
                    or not (member.isfile() or member.isdir())
                    or member.mode & (stat.S_ISUID | stat.S_ISGID | stat.S_IWOTH)):
                    fail("unsafe or oversized release archive; nothing installed")
                paths.add(normalized.casefold())
                target = release.joinpath(*parts)
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    fail("incomplete release archive")
                with source, target.open("xb") as output:
                    remaining = member.size
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            fail("truncated release archive")
                        output.write(chunk)
                        remaining -= len(chunk)
        entry = release / "install.sh"
        if not entry.is_file():
            fail("release installation entry is missing")
        def install(*arguments):
            subprocess.run(("/bin/bash", str(entry), *arguments), env=environment, check=True)
        install("verify-artifact", "--artifact", str(artifact),
                "--checksums", str(stage / "SHA256SUMS"),
                "--manifest", str(stage / "RELEASE_MANIFEST.json"),
                "--sbom", str(stage / "SBOM.spdx.json"))
        install("plan", "--artifact", str(artifact), "--sha256", expected)
        if apply or resume:
            install("resume-install" if resume else "apply",
                    "--artifact", str(artifact), "--sha256", expected)
        else:
            print("AgentBox: plan only; add --apply to install this exact version")
except (OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
    fail(f"download/install failed ({type(exc).__name__}); inspect installer status before retrying")
PY
