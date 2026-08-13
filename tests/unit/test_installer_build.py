from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_installer.build import BuildError, _copy_regular_tree, _migration_head


def _migration(path: Path, revision: str, down_revision: str | None) -> None:
    path.write_text(
        f"revision = {revision!r}\ndown_revision = {down_revision!r}\n",
        encoding="utf-8",
    )


def test_release_builder_derives_current_unique_migration_head(tmp_path: Path) -> None:
    _migration(tmp_path / "0001.py", "0001_initial", None)
    _migration(tmp_path / "0002.py", "0002_jobs", "0001_initial")
    _migration(tmp_path / "0003.py", "0003_hardening", "0002_jobs")

    assert _migration_head(tmp_path) == "0003_hardening"


def test_release_builder_rejects_branches_and_dynamic_migration_identity(
    tmp_path: Path,
) -> None:
    _migration(tmp_path / "0001.py", "0001_initial", None)
    _migration(tmp_path / "0002_a.py", "0002_a", "0001_initial")
    _migration(tmp_path / "0002_b.py", "0002_b", "0001_initial")
    with pytest.raises(BuildError, match="exactly one head"):
        _migration_head(tmp_path)

    (tmp_path / "0002_b.py").write_text(
        'revision = get_revision()\ndown_revision = "0001_initial"\n', encoding="utf-8"
    )
    with pytest.raises(BuildError, match="literal"):
        _migration_head(tmp_path)


def test_release_tree_excludes_interpreter_cache_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    cache = source / "__pycache__"
    cache.mkdir(parents=True)
    (source / "migration.py").write_text("revision = 'fixture'\n", encoding="utf-8")
    (cache / "migration.cpython-311.pyc").write_bytes(b"host-specific-cache")

    _copy_regular_tree(source, destination)

    assert (destination / "migration.py").is_file()
    assert not (destination / "__pycache__").exists()
