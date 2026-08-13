from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_installer.build import (
    WHEEL_SOURCE_DIRECTORIES,
    WHEEL_SOURCE_FILES,
    BuildError,
    _build_command_label,
    _copy_regular_tree,
    _migration_head,
    _prepare_wheel_source,
)


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


def test_wheel_build_uses_an_isolated_allowlisted_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "wheel-source"
    source.mkdir()
    for name in WHEEL_SOURCE_DIRECTORIES:
        package = source / name
        package.mkdir(parents=True)
        (package / "tracked.py").write_text("value = True\n", encoding="utf-8")
    for name in WHEEL_SOURCE_FILES:
        (source / name).write_text("fixture\n", encoding="utf-8")
    generated = source / "build/untracked.py"
    generated.parent.mkdir()
    generated.write_text("must_not_be_copied = True\n", encoding="utf-8")

    _prepare_wheel_source(source, destination)

    assert all((destination / name).exists() for name in WHEEL_SOURCE_DIRECTORIES)
    assert all((destination / name).is_file() for name in WHEEL_SOURCE_FILES)
    assert not (destination / "build").exists()


def test_build_failure_labels_are_bounded_and_do_not_include_paths() -> None:
    assert _build_command_label(("/secret/python", "-m", "pip", "download")) == "pip download"
    assert _build_command_label(("/secret/pnpm", "licenses", "list", "--prod", "--json")) == (
        "pnpm licenses"
    )
    assert _build_command_label(("/secret/custom-tool", "--token", "canary")) == (
        "reviewed build subprocess"
    )
