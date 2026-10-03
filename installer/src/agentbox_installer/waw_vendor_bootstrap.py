"""Fixed, digest-pinned native vendor installation; no vendor script execution."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import tarfile
from collections.abc import Callable
from dataclasses import dataclass

from agentbox_runtime.waw_executable import _validate_elf_header
from agentbox_runtime.waw_process_profile import ExecutableInventoryV1

from agentbox_installer.waw_manifest_install import WAWManifestInstallError, WAWManifestIssuer


@dataclass(frozen=True)
class VendorDownload:
    kind: str
    version: str
    url: str
    sha256: str
    archive_member: str | None


@dataclass(frozen=True)
class VendorQualification:
    kind: str
    version: str
    version_output: str
    executable_sha256: str
    codex_unauthenticated_output_sha256: str | None = None


VENDOR_DOWNLOADS = (
    VendorDownload(
        "claude",
        "2.1.286",
        "https://downloads.claude.ai/claude-code-releases/2.1.286/linux-x64/claude",
        "fe503f65c6289d59c23e5b21ae44f03583f997dd33a2cbfc75ab4f96fb8fc73f",
        None,
    ),
    VendorDownload(
        "codex",
        "0.159.3",
        "https://releases.openai.com/codex/releases/0.159.3/codex-x86_64-unknown-linux-musl.tar.gz",
        "b48ca1b2d6b1bf42b944e02c3d937c898e24651916684cdc35fdedf31b291bcb",
        "codex-x86_64-unknown-linux-musl",
    ),
)

QUALIFIED_VENDOR_FACTS = (
    VendorQualification(
        "claude",
        "2.1.286",
        "2.1.286 (Claude Code)",
        "fe503f65c6289d59c23e5b21ae44f03583f997dd33a2cbfc75ab4f96fb8fc73f",
    ),
    VendorQualification(
        "codex",
        "0.159.3",
        "codex-cli 0.159.3",
        "8bf204b36a2f6dd0dab73aa2f639892e67ef9ac8befccb4a05b1496ebf25c479",
        "76522c70a3df95fdd59bc4851200017bf42947a49d47e216c95bb0dea1579d9c",
    ),
)
_MAXIMUM = 256 * 1024 * 1024


def decode_vendor_download(spec: VendorDownload, raw: bytes) -> bytes:
    binary_maximum = (384 if spec.kind == "codex" else 256) * 1024 * 1024
    if len(raw) > _MAXIMUM or hashlib.sha256(raw).hexdigest() != spec.sha256:
        raise WAWManifestInstallError("vendor download checksum or size is invalid")
    if spec.archive_member is not None:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            entries = archive.getmembers()
            if (
                len(entries) != 1
                or entries[0].name != spec.archive_member
                or not entries[0].isfile()
                or not 64 <= entries[0].size <= binary_maximum
            ):
                raise WAWManifestInstallError("vendor archive has unexpected entries")
            stream = archive.extractfile(entries[0])
            if stream is None:
                raise WAWManifestInstallError("vendor archive binary is missing")
            with stream:
                raw = stream.read(binary_maximum + 1)
    if not 64 <= len(raw) <= binary_maximum:
        raise WAWManifestInstallError("vendor binary size is invalid")
    _validate_elf_header(raw[:64])
    return raw


class WAWVendorBootstrap:
    def __init__(self, issuer: WAWManifestIssuer) -> None:
        self.issuer = issuer

    def qualified_enrollment_values(
        self, inventory: ExecutableInventoryV1
    ) -> dict[str, str]:
        """Verify installed AgentBox-owned vendor ELFs against qualified release facts."""

        if type(inventory) is not ExecutableInventoryV1:
            raise TypeError("qualified vendor inventory is invalid")
        downloads = {spec.kind: spec for spec in VENDOR_DOWNLOADS}
        qualifications = {item.kind: item for item in QUALIFIED_VENDOR_FACTS}
        if set(downloads) != {"claude", "codex"} or set(qualifications) != set(downloads):
            raise WAWManifestInstallError("qualified vendor set is invalid")
        entries = {entry.kind: entry for entry in inventory.executables}
        if not set(qualifications).issubset(entries):
            raise WAWManifestInstallError("qualified vendor inventory is incomplete")

        for kind, qualification in qualifications.items():
            spec = downloads[kind]
            entry = entries[kind]
            if (
                spec.version != qualification.version
                or entry.path != f"/usr/local/bin/{kind}"
                or entry.sha256 != qualification.executable_sha256
            ):
                raise WAWManifestInstallError(
                    "installed vendor does not match the qualified release"
                )
            raw = self.issuer._read(entry.path, entry.max_bytes, executable=True)
            if hashlib.sha256(raw).hexdigest() != qualification.executable_sha256:
                raise WAWManifestInstallError(
                    "installed vendor bytes do not match the qualified release"
                )
        self.issuer.revalidate()

        codex = qualifications["codex"]
        if codex.codex_unauthenticated_output_sha256 is None:
            raise WAWManifestInstallError("qualified Codex unauthenticated digest is missing")
        return {
            "claude_vendor_version": qualifications["claude"].version,
            "codex_vendor_version": codex.version,
            "codex_unauthenticated_output_sha256": codex.codex_unauthenticated_output_sha256,
        }

    def install(
        self, *, plan: bool, recover: bool, download: Callable[[VendorDownload], bytes]
    ) -> dict[str, object]:
        for spec in VENDOR_DOWNLOADS:
            alternate = self.issuer.root / f"usr/bin/{spec.kind}"
            if alternate.exists() or alternate.is_symlink():
                raise WAWManifestInstallError(
                    "existing distro vendor CLI requires explicit enrollment"
                )
        result: dict[str, object] = {
            "status": "planned" if plan else "installed",
            "vendors": [
                {"kind": spec.kind, "version": spec.version, "url": spec.url, "sha256": spec.sha256}
                for spec in VENDOR_DOWNLOADS
            ],
            "services_started": False,
            "credentials_read": False,
        }
        if plan:
            return result
        # Decode and check both payloads before creating either executable.
        payloads = {
            spec.kind: decode_vendor_download(spec, download(spec)) for spec in VENDOR_DOWNLOADS
        }
        with self.issuer._directory("/usr/local/bin") as parent:
            for kind, raw in payloads.items():
                target = self.issuer.root / f"usr/local/bin/{kind}"
                if target.exists() or target.is_symlink():
                    pending = "." + kind + ".agentbox-" + hashlib.sha256(raw).hexdigest()[:16]
                    facts = os.stat(kind, dir_fd=parent, follow_symlinks=False)
                    if recover and facts.st_nlink == 2:
                        staged = os.stat(pending, dir_fd=parent, follow_symlinks=False)
                        if (
                            not stat.S_ISREG(facts.st_mode)
                            or facts.st_uid != self.issuer.owner_uid
                            or facts.st_gid != self.issuer.root_gid
                            or stat.S_IMODE(facts.st_mode) != 0o755
                            or (facts.st_dev, facts.st_ino) != (staged.st_dev, staged.st_ino)
                        ):
                            raise WAWManifestInstallError("vendor publication links are unsafe")
                        fd = os.open(
                            kind, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
                        )
                        try:
                            if os.fstat(fd) != facts or os.read(fd, len(raw) + 1) != raw:
                                raise WAWManifestInstallError("vendor publication bytes changed")
                        finally:
                            os.close(fd)
                        os.unlink(pending, dir_fd=parent)
                        os.fsync(parent)
                    self.issuer._require_bytes(parent, kind, raw, 0o755, self.issuer.root_gid)
            for kind, raw in payloads.items():
                target = self.issuer.root / f"usr/local/bin/{kind}"
                if target.exists():
                    continue
                pending = "." + kind + ".agentbox-" + hashlib.sha256(raw).hexdigest()[:16]
                self.issuer._create_file(
                    parent,
                    pending,
                    raw,
                    0o755,
                    self.issuer.root_gid,
                    allow_existing=recover,
                    repair_prefix=recover,
                )
                os.link(pending, kind, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)
                os.unlink(pending, dir_fd=parent)
                os.fsync(parent)
        return result
