"""Verified AgentBox release artifact handling."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any

VERSION_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)" r"(?:[-+][0-9A-Za-z.-]+)?"
)
MAX_ARCHIVE_MEMBERS = 20_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024


class ArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    database_revision: str
    database_backward_compatible: bool
    files: dict[str, str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact_digest(path: Path, expected_sha256: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ArtifactError("artifact checksum must be lowercase SHA-256")
    if sha256_file(path) != expected_sha256:
        raise ArtifactError("artifact checksum mismatch")


def _safe_member_path(name: str) -> PurePosixPath:
    value = PurePosixPath(name)
    if not name or value.is_absolute() or ".." in value.parts or "" in value.parts:
        raise ArtifactError("archive contains an unsafe path")
    if len(value.parts) > 32 or len(name.encode("utf-8")) > 4096:
        raise ArtifactError("archive path exceeds its limit")
    return value


def _copy_member(source: IO[bytes], destination: Path, size: int, mode: int) -> None:
    remaining = size
    with destination.open("xb") as output:
        os.chmod(destination, 0o755 if mode & 0o111 else 0o644)
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ArtifactError("archive member ended unexpectedly")
            output.write(chunk)
            remaining -= len(chunk)


def extract_verified_tar(artifact: Path, destination: Path) -> None:
    """Extract regular files/directories only; links and special nodes fail closed."""
    if destination.exists() or destination.is_symlink():
        raise ArtifactError("release staging destination already exists")
    destination.mkdir(mode=0o755, parents=False)
    member_count = 0
    expanded_bytes = 0
    try:
        with tarfile.open(artifact, mode="r:*") as archive:
            for member in archive:
                member_count += 1
                expanded_bytes += max(0, member.size)
                if member_count > MAX_ARCHIVE_MEMBERS or expanded_bytes > MAX_EXPANDED_BYTES:
                    raise ArtifactError("archive exceeds extraction limits")
                relative = _safe_member_path(member.name)
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(mode=0o755, parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ArtifactError("archive links and special files are forbidden")
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    raise ArtifactError("archive contains a duplicate path")
                source = archive.extractfile(member)
                if source is None:
                    raise ArtifactError("archive member cannot be read")
                with source:
                    _copy_member(source, target, member.size, member.mode)
    except Exception:
        remove_verified_tree(destination)
        raise


def remove_verified_tree(root: Path) -> None:
    """Remove only a fresh, verified staging directory without following links."""
    if not root.exists() or root.is_symlink() or not root.is_dir():
        return
    for child in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        details = child.lstat()
        if stat.S_ISDIR(details.st_mode):
            child.rmdir()
        else:
            child.unlink()
    root.rmdir()


def load_manifest(release: Path) -> ReleaseManifest:
    manifest_path = release / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ArtifactError("release manifest is missing")
    try:
        value: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError("release manifest is invalid") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "version",
        "database_revision",
        "database_backward_compatible",
        "files",
    }:
        raise ArtifactError("release manifest schema is invalid")
    version = value["version"]
    revision = value["database_revision"]
    compatible = value["database_backward_compatible"]
    files = value["files"]
    if (
        value["schema_version"] != 1
        or not isinstance(version, str)
        or not VERSION_PATTERN.fullmatch(version)
        or not isinstance(revision, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", revision)
        or not isinstance(compatible, bool)
        or not isinstance(files, dict)
        or len(files) > MAX_ARCHIVE_MEMBERS
    ):
        raise ArtifactError("release manifest values are invalid")
    normalized: dict[str, str] = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ArtifactError("release file manifest is invalid")
        _safe_member_path(name)
        if name == "manifest.json" or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ArtifactError("release file manifest is invalid")
        normalized[name] = digest
    return ReleaseManifest(version, revision, compatible, normalized)


def verify_release(
    release: Path,
    manifest: ReleaseManifest | None = None,
    *,
    allow_generated_venv: bool = False,
) -> ReleaseManifest:
    try:
        root_details = release.lstat()
    except OSError as exc:
        raise ArtifactError("release root is unavailable") from exc
    if stat.S_ISLNK(root_details.st_mode) or not stat.S_ISDIR(root_details.st_mode):
        raise ArtifactError("release root is unsafe")
    actual = manifest or load_manifest(release)
    observed: set[str] = set()
    for path in release.rglob("*"):
        relative = path.relative_to(release).as_posix()
        if allow_generated_venv and (relative == "venv" or relative.startswith("venv/")):
            continue
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not (
            stat.S_ISDIR(details.st_mode) or stat.S_ISREG(details.st_mode)
        ):
            raise ArtifactError("release contains an unsafe filesystem object")
        if stat.S_ISREG(details.st_mode) and relative != "manifest.json":
            observed.add(relative)
            if actual.files.get(relative) != sha256_file(path):
                raise ArtifactError("release file digest mismatch")
    if observed != set(actual.files):
        raise ArtifactError("release file set does not match its manifest")
    return actual
