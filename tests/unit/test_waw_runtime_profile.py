from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from agentbox_runtime import waw_runtime_profile as subject
from agentbox_runtime.waw_runtime_profile import (
    DISABLED_PROFILE_BYTES,
    FILESYSTEM_V2_PROFILE_BYTES,
    WAWRuntimeMode,
    WAWRuntimeProfileError,
    _load_profile_at,
)


def _fixture(tmp_path: Path, content: bytes | None) -> tuple[Path, Path]:
    root = tmp_path / "trusted-root"
    parent = root / "var/lib/agentbox-waw"
    parent.mkdir(parents=True)
    root.chmod(0o700)
    (root / "var").chmod(0o755)
    (root / "var/lib").chmod(0o755)
    parent.chmod(0o750)
    path = parent / "runtime-profile.v1.json"
    if content is not None:
        path.write_bytes(content)
        path.chmod(0o440)
    return root, path


def _load(root: Path, path: Path) -> subject.WAWRuntimeProfileObservation:
    return _load_profile_at(
        path, root=root, root_uid=os.geteuid(), runtime_gid=path.parent.stat().st_gid
    )


@pytest.mark.parametrize(
    ("content", "mode"),
    [
        (DISABLED_PROFILE_BYTES, WAWRuntimeMode.DISABLED),
        (FILESYSTEM_V2_PROFILE_BYTES, WAWRuntimeMode.FILESYSTEM_V2),
    ],
)
def test_runtime_profile_accepts_only_canonical_installed_bytes(
    tmp_path: Path, content: bytes, mode: WAWRuntimeMode
) -> None:
    root, path = _fixture(tmp_path, content)
    observed = _load(root, path)
    assert observed.mode is mode
    assert observed.source == "installed_profile"
    assert observed.raw_sha256 is not None and len(observed.raw_sha256) == 64
    assert observed.file_identity is not None

    path.chmod(0o600)
    path.write_bytes(b'{"mode":"enabled","schema_version":"agentbox-waw-runtime-profile.v1"}\n')
    path.chmod(0o440)
    with pytest.raises(WAWRuntimeProfileError, match="content"):
        _load(root, path)


def test_runtime_profile_absence_is_disabled_only_under_a_trusted_parent(tmp_path: Path) -> None:
    root, path = _fixture(tmp_path, None)
    observed = _load(root, path)
    assert observed.mode is WAWRuntimeMode.DISABLED
    assert observed.source == "missing_default"
    assert observed.file_identity is None

    path.parent.chmod(0o770)
    with pytest.raises(WAWRuntimeProfileError, match="parent"):
        _load(root, path)


@pytest.mark.parametrize("bad_content", [b"", b"x" * 257, b"{}\n"])
def test_runtime_profile_rejects_empty_oversized_and_unknown_content(
    tmp_path: Path, bad_content: bytes
) -> None:
    root, path = _fixture(tmp_path, bad_content)
    with pytest.raises(WAWRuntimeProfileError):
        _load(root, path)


def test_runtime_profile_rejects_symlink_hardlink_fifo_and_wrong_mode(tmp_path: Path) -> None:
    root, path = _fixture(tmp_path, DISABLED_PROFILE_BYTES)
    path.chmod(0o640)
    with pytest.raises(WAWRuntimeProfileError, match="provenance"):
        _load(root, path)
    path.chmod(0o440)

    second = path.with_name("second-link")
    second.hardlink_to(path)
    with pytest.raises(WAWRuntimeProfileError, match="provenance"):
        _load(root, path)
    second.unlink()

    path.unlink()
    path.symlink_to(second)
    with pytest.raises(OSError):
        _load(root, path)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(WAWRuntimeProfileError, match="provenance"):
        _load(root, path)


def test_runtime_profile_identity_changes_when_leaf_is_replaced(tmp_path: Path) -> None:
    root, path = _fixture(tmp_path, DISABLED_PROFILE_BYTES)
    old = _load(root, path)
    path.unlink()
    path.write_bytes(DISABLED_PROFILE_BYTES)
    path.chmod(0o440)
    assert _load(root, path) != old


def test_runtime_profile_rejects_symlinked_ancestor_and_path_escape(tmp_path: Path) -> None:
    root, path = _fixture(tmp_path, DISABLED_PROFILE_BYTES)
    library = root / "var/lib"
    moved = root / "var/real-lib"
    library.rename(moved)
    library.symlink_to(moved, target_is_directory=True)
    with pytest.raises(WAWRuntimeProfileError, match="parent"):
        _load(root, path)
    with pytest.raises(ValueError, match="fixture boundary"):
        _load_profile_at(
            root / "var/../runtime-profile.v1.json",
            root=root,
            root_uid=os.geteuid(),
            runtime_gid=os.getegid(),
        )


def test_runtime_profile_rejects_in_place_drift_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path = _fixture(tmp_path, DISABLED_PROFILE_BYTES)
    original_read = os.read
    changed = False

    def drift(descriptor: int, length: int) -> bytes:
        nonlocal changed
        content = original_read(descriptor, length)
        if content and not changed:
            changed = True
            path.chmod(0o600)
            path.write_bytes(b"X" + DISABLED_PROFILE_BYTES[1:])
            path.chmod(0o440)
        return content

    monkeypatch.setattr("agentbox_runtime.waw_runtime_profile.os.read", drift)
    with pytest.raises(WAWRuntimeProfileError, match="changed"):
        _load(root, path)


def test_runtime_profile_public_loader_fails_closed_without_runtime_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_name: str) -> None:
        raise KeyError("missing")

    monkeypatch.setattr("agentbox_runtime.waw_runtime_profile.grp.getgrnam", missing)
    with pytest.raises(WAWRuntimeProfileError, match="unavailable"):
        subject.load_waw_runtime_profile()


def test_runtime_profile_revalidation_rejects_changed_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path = _fixture(tmp_path, DISABLED_PROFILE_BYTES)
    observed = _load(root, path)
    monkeypatch.setattr(subject, "load_waw_runtime_profile", lambda: observed)
    subject.revalidate_waw_runtime_profile(observed)
    monkeypatch.setattr(
        subject,
        "load_waw_runtime_profile",
        lambda: replace(observed, raw_sha256="b" * 64),
    )
    with pytest.raises(WAWRuntimeProfileError, match="changed"):
        subject.revalidate_waw_runtime_profile(observed)
