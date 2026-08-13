"""Conservative retention for verified AgentBox backups and releases."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agentbox_installer.artifact import (
    VERSION_PATTERN,
    ArtifactError,
    remove_verified_tree,
    verify_release,
)
from agentbox_installer.backup import BackupResult, verify_sqlite_backup

DEFAULT_BACKUP_RETENTION = 5
DEFAULT_RELEASE_RETENTION = 4
BACKUP_ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,80}")


@dataclass(frozen=True)
class RetentionResult:
    removed_backups: tuple[str, ...]
    removed_releases: tuple[str, ...]


@dataclass(frozen=True)
class _VerifiedBackup:
    identifier: str
    created_at: datetime
    result: BackupResult


def enforce_retention(
    *,
    backups_root: Path,
    releases_root: Path,
    protected_backup_ids: frozenset[str],
    protected_release_versions: frozenset[str],
    backup_limit: int = DEFAULT_BACKUP_RETENTION,
    release_limit: int = DEFAULT_RELEASE_RETENTION,
) -> RetentionResult:
    """Delete only verified AgentBox objects outside the protected keep set.

    Unknown files, invalid manifests, symlinks, and corrupt objects are retained
    for explicit operator review. Limits count verified objects only; protected
    rollback identities are never removed even when they exceed a limit.
    """
    if backup_limit < 1 or release_limit < 2:
        raise ValueError("retention limits are unsafe")
    _validate_root(backups_root)
    _validate_root(releases_root)

    backups = tuple(
        candidate
        for entry in backups_root.iterdir()
        if (candidate := _verified_backup(entry)) is not None
    )
    ordered_backups = tuple(
        sorted(backups, key=lambda item: (item.created_at, item.identifier), reverse=True)
    )
    kept_backup_ids = set(protected_backup_ids)
    for candidate in ordered_backups:
        if len(kept_backup_ids) >= backup_limit:
            break
        kept_backup_ids.add(candidate.identifier)
    removed_backups: list[str] = []
    for candidate in ordered_backups:
        if candidate.identifier in kept_backup_ids:
            continue
        remove_verified_tree(candidate.result.path)
        if candidate.result.path.exists() or candidate.result.path.is_symlink():
            raise RuntimeError("verified backup retention deletion failed")
        removed_backups.append(candidate.identifier)

    releases = tuple(entry.name for entry in releases_root.iterdir() if _verified_release(entry))
    ordered_releases = tuple(sorted(releases, key=_version_key, reverse=True))
    kept_releases = set(protected_release_versions)
    current_release = _current_release_version(releases_root)
    if current_release is not None:
        kept_releases.add(current_release)
    for version in ordered_releases:
        if len(kept_releases) >= release_limit:
            break
        kept_releases.add(version)
    removed_releases: list[str] = []
    for version in ordered_releases:
        if version in kept_releases:
            continue
        release = releases_root / version
        # Revalidate at the deletion boundary; a changed object is retained.
        if not _verified_release(release):
            continue
        remove_verified_tree(release)
        if release.exists() or release.is_symlink():
            raise RuntimeError("verified release retention deletion failed")
        removed_releases.append(version)

    return RetentionResult(tuple(removed_backups), tuple(removed_releases))


def _validate_root(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("retention root is unavailable or unsafe")


def _verified_backup(path: Path) -> _VerifiedBackup | None:
    if not BACKUP_ID_PATTERN.fullmatch(path.name) or path.is_symlink() or not path.is_dir():
        return None
    manifest_path = path / "manifest.json"
    try:
        value: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    expected_keys = {
        "schema_version",
        "backup_id",
        "created_at",
        "application_version",
        "migration_revision",
        "database_sha256",
        "file_sha256",
        "contents",
        "units",
        "tmpfiles",
        "excluded",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        return None
    digest = value.get("database_sha256")
    if (
        value.get("schema_version") != 1
        or value.get("backup_id") != path.name
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        return None
    try:
        created_at = datetime.fromisoformat(str(value["created_at"]))
    except (TypeError, ValueError):
        return None
    result = BackupResult(path.name, path, digest)
    if not verify_sqlite_backup(result):
        return None
    return _VerifiedBackup(path.name, created_at, result)


def _verified_release(path: Path) -> bool:
    if not VERSION_PATTERN.fullmatch(path.name) or path.is_symlink() or not path.is_dir():
        return False
    try:
        manifest = verify_release(path, allow_generated_venv=True)
    except (ArtifactError, OSError):
        return False
    return manifest.version == path.name


def _current_release_version(releases_root: Path) -> str | None:
    """Fail closed and protect the verified target of the managed current link."""
    current = releases_root.parent / "current"
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise RuntimeError("current release identity is unsafe")
    try:
        raw_target = os.readlink(current)
        candidate = Path(raw_target)
        if not candidate.is_absolute():
            candidate = current.parent / candidate
        target = candidate.resolve(strict=True)
        trusted_releases = releases_root.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("current release target is unavailable") from exc
    if target.parent != trusted_releases or not _verified_release(target):
        raise RuntimeError("current release target is unsafe")
    return target.name


def _version_key(version: str) -> tuple[int, int, int, str]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+](.*))?", version)
    if match is None:
        raise ValueError("verified release version is invalid")
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), suffix or ""
