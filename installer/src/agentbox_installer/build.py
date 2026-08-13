"""Build a checksummed offline release payload from a reviewed checkout."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from agentbox_installer.artifact import VERSION_PATTERN, sha256_file


class BuildError(RuntimeError):
    pass


def _copy_regular_tree(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise BuildError(f"required release input is unavailable: {source.name}")
    destination.mkdir(mode=0o755, parents=True)
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        if "__pycache__" in relative.parts or item.suffix in {".pyc", ".pyo"}:
            continue
        target = destination / relative
        if item.is_symlink():
            raise BuildError("release input contains a symbolic link")
        if item.is_dir():
            target.mkdir(mode=0o755, parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            shutil.copyfile(item, target)
            os.chmod(target, 0o644)
        else:
            raise BuildError("release input contains a special file")


def build_release_artifact(source: Path, output: Path, *, version: str, python: Path) -> str:
    if not VERSION_PATTERN.fullmatch(version):
        raise BuildError("release version must follow semantic version syntax")
    source = source.resolve()
    if not (source / "pyproject.toml").is_file() or not (source / "alembic.ini").is_file():
        raise BuildError("source is not an AgentBox checkout")
    if output.exists() or output.is_symlink():
        raise BuildError("artifact output already exists")
    web_dist = source / "apps/web/dist"
    if not (web_dist / "index.html").is_file():
        raise BuildError("frontend production artifact is missing; run pnpm build first")
    with tempfile.TemporaryDirectory(prefix="agentbox-release-") as temporary:
        release = Path(temporary) / "release"
        wheelhouse = release / "wheelhouse"
        wheelhouse.mkdir(mode=0o755, parents=True)
        try:
            result = subprocess.run(  # noqa: S603 - local reviewed build input
                (
                    str(python),
                    "-m",
                    "pip",
                    "wheel",
                    "--wheel-dir",
                    str(wheelhouse),
                    str(source),
                ),
                cwd=source,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=600,
                check=False,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BuildError("Python wheel build failed") from exc
        if result.returncode != 0:
            raise BuildError("Python wheel build failed")
        agentbox_wheels = sorted(wheelhouse.glob("agentbox-*.whl"))
        if len(agentbox_wheels) != 1 or _wheel_version(agentbox_wheels[0]) != version:
            raise BuildError("AgentBox package version does not match release version")
        _copy_regular_tree(web_dist, release / "web/dist")
        _copy_regular_tree(source / "migrations", release / "migrations")
        shutil.copyfile(source / "alembic.ini", release / "alembic.ini")
        os.chmod(release / "alembic.ini", 0o644)
        files = {
            path.relative_to(release).as_posix(): sha256_file(path)
            for path in sorted(release.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema_version": 1,
            "version": version,
            "database_revision": _migration_head(source / "migrations/versions"),
            "database_backward_compatible": False,
            "files": files,
        }
        (release / "manifest.json").write_text(
            json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(release.rglob("*")):
                archive.add(path, arcname=path.relative_to(release), recursive=False)
        return sha256_file(output)


def _wheel_version(wheel: Path) -> str:
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_names = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise BuildError("AgentBox wheel metadata is invalid")
            metadata = archive.read(metadata_names[0]).decode("utf-8")
    except (OSError, UnicodeError, zipfile.BadZipFile, KeyError) as exc:
        raise BuildError("AgentBox wheel metadata is invalid") from exc
    versions = [
        line.removeprefix("Version: ")
        for line in metadata.splitlines()
        if line.startswith("Version: ")
    ]
    if len(versions) != 1:
        raise BuildError("AgentBox wheel version is unavailable")
    return versions[0]


def _migration_head(versions_directory: Path) -> str:
    """Read the unique Alembic head without importing migration code."""
    if versions_directory.is_symlink() or not versions_directory.is_dir():
        raise BuildError("migration versions directory is unavailable")
    revisions: set[str] = set()
    predecessors: set[str] = set()
    for path in sorted(versions_directory.glob("*.py")):
        if path.is_symlink() or not path.is_file():
            raise BuildError("migration source contains an unsafe object")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise BuildError("migration source is invalid") from exc
        values: dict[str, object] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError) as exc:
                    raise BuildError("migration identity must be a literal") from exc
        revision = values.get("revision")
        down_revision = values.get("down_revision")
        if not isinstance(revision, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", revision) is None:
            raise BuildError("migration revision is invalid")
        if revision in revisions:
            raise BuildError("migration revision is duplicated")
        revisions.add(revision)
        if down_revision is not None:
            if (
                not isinstance(down_revision, str)
                or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", down_revision) is None
            ):
                raise BuildError("branched migration graphs are unsupported")
            predecessors.add(down_revision)
    if not revisions or not predecessors.issubset(revisions):
        raise BuildError("migration graph is incomplete")
    heads = revisions - predecessors
    if len(heads) != 1:
        raise BuildError("migration graph must have exactly one head")
    return heads.pop()
