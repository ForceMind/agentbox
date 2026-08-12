"""Consistent SQLite and non-secret deployment backup primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class BackupResult:
    backup_id: str
    path: Path
    database_sha256: str


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def create_sqlite_backup(
    source: Path,
    backups_root: Path,
    *,
    application_version: str,
    migration_revision: str,
    config_path: Path | None = None,
    unit_paths: tuple[Path, ...] = (),
    tmpfiles_path: Path | None = None,
    backup_id: str | None = None,
) -> BackupResult:
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("live SQLite database is unavailable or unsafe")
    identifier = backup_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", identifier):
        raise ValueError("backup identifier is invalid")
    if backups_root.is_symlink() or not backups_root.is_dir():
        raise RuntimeError("backup root is unavailable or unsafe")
    destination = backups_root / identifier
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    database_copy = destination / "agentbox.db"
    try:
        with (
            sqlite3.connect(f"file:{source}?mode=ro", uri=True) as live,
            sqlite3.connect(database_copy) as backup,
        ):
            live.backup(backup)
            backup.execute("PRAGMA journal_mode=DELETE")
            integrity = backup.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise RuntimeError("SQLite backup integrity check failed")
        os.chmod(database_copy, 0o600)
        database_digest = _digest(database_copy)
        if config_path is not None and config_path.is_file() and not config_path.is_symlink():
            config_copy = destination / "agentbox.toml"
            content = config_path.read_bytes()
            try:
                parsed_config = tomllib.loads(content.decode("utf-8"))
            except (UnicodeError, tomllib.TOMLDecodeError) as exc:
                raise RuntimeError("non-secret config is invalid") from exc
            if _contains_secret_key(parsed_config):
                raise RuntimeError("non-secret config unexpectedly contains a secret field")
            config_copy.write_bytes(content)
            os.chmod(config_copy, 0o600)
        copied_units: list[str] = []
        if unit_paths:
            units_directory = destination / "units"
            units_directory.mkdir(mode=0o700)
            for unit_path in unit_paths:
                if unit_path.is_symlink() or not unit_path.is_file():
                    raise RuntimeError("managed unit backup source is unsafe")
                unit_copy = units_directory / unit_path.name
                unit_copy.write_bytes(unit_path.read_bytes())
                os.chmod(unit_copy, 0o600)
                copied_units.append(unit_path.name)
        copied_tmpfiles: list[str] = []
        if tmpfiles_path is not None:
            if tmpfiles_path.is_symlink() or not tmpfiles_path.is_file():
                raise RuntimeError("managed tmpfiles backup source is unsafe")
            tmpfiles_directory = destination / "tmpfiles"
            tmpfiles_directory.mkdir(mode=0o700)
            tmpfiles_copy = tmpfiles_directory / "agentbox.conf"
            tmpfiles_copy.write_bytes(tmpfiles_path.read_bytes())
            os.chmod(tmpfiles_copy, 0o600)
            copied_tmpfiles.append("agentbox.conf")
        file_digests = {
            path.relative_to(destination).as_posix(): _digest(path)
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema_version": 1,
            "backup_id": identifier,
            "created_at": datetime.now(UTC).isoformat(),
            "application_version": application_version,
            "migration_revision": migration_revision,
            "database_sha256": database_digest,
            "file_sha256": file_digests,
            "contents": [
                "database",
                *(["config"] if (destination / "agentbox.toml").exists() else []),
                *(["units"] if copied_units else []),
                *(["tmpfiles"] if copied_tmpfiles else []),
            ],
            "units": copied_units,
            "tmpfiles": copied_tmpfiles,
            "excluded": ["runtime_credentials", "projects", "provider_secrets"],
        }
        manifest_path = destination / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(manifest_path, 0o600)
        return BackupResult(identifier, destination, database_digest)
    except Exception:
        for child in sorted(destination.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if child.is_dir() and not child.is_symlink():
                child.rmdir()
            else:
                child.unlink()
        destination.rmdir()
        raise


def verify_sqlite_backup(result: BackupResult) -> bool:
    database = result.path / "agentbox.db"
    if (
        database.is_symlink()
        or not database.is_file()
        or _digest(database) != result.database_sha256
    ):
        return False
    try:
        manifest_path = result.path / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        file_digests = manifest.get("file_sha256")
        if not isinstance(file_digests, dict):
            return False
        observed = {
            path.relative_to(result.path).as_posix()
            for path in result.path.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        if observed != set(file_digests):
            return False
        for relative, expected in file_digests.items():
            if (
                not isinstance(relative, str)
                or not isinstance(expected, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected)
                or relative.startswith("/")
                or ".." in Path(relative).parts
            ):
                return False
            candidate = result.path / relative
            if candidate.is_symlink() or not candidate.is_file() or _digest(candidate) != expected:
                return False
        if manifest.get("database_sha256") != result.database_sha256:
            return False
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(row == ("ok",))
    except (OSError, json.JSONDecodeError, sqlite3.Error):
        return False


def _contains_secret_key(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    forbidden = {"secret", "secret_key", "token", "password", "api_key", "authorization"}
    for key, nested in value.items():
        normalized = str(key).lower().replace("-", "_")
        if normalized in forbidden or _contains_secret_key(nested):
            return True
    return False
