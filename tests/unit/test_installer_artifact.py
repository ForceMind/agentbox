from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from agentbox_installer.artifact import ArtifactError, extract_verified_tar, verify_release


def _tar_with_member(path: Path, name: str, content: bytes, *, kind: bytes | None = None) -> None:
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo(name)
        member.size = len(content)
        if kind is not None:
            member.type = kind
        archive.addfile(member, io.BytesIO(content))


@pytest.mark.parametrize("name", ["../escape", "/absolute", "safe/../../escape"])
def test_archive_rejects_traversal_and_absolute_paths(tmp_path: Path, name: str) -> None:
    artifact = tmp_path / "bad.tar.gz"
    _tar_with_member(artifact, name, b"bad")

    with pytest.raises(ArtifactError, match="unsafe path"):
        extract_verified_tar(artifact, tmp_path / "release")

    assert not (tmp_path / "release").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE])
def test_archive_rejects_links_and_special_files(tmp_path: Path, kind: bytes) -> None:
    artifact = tmp_path / "bad.tar.gz"
    _tar_with_member(artifact, "unsafe", b"", kind=kind)

    with pytest.raises(ArtifactError, match="special files"):
        extract_verified_tar(artifact, tmp_path / "release")


def test_release_manifest_detects_file_tampering(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    payload = release / "payload.txt"
    payload.write_text("expected", encoding="utf-8")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "0.2.0+dev.8",
                "database_revision": "0002_project_jobs",
                "database_backward_compatible": False,
                "files": {"payload.txt": digest},
            }
        ),
        encoding="utf-8",
    )
    verify_release(release)
    payload.write_text("changed", encoding="utf-8")

    with pytest.raises(ArtifactError, match="digest mismatch"):
        verify_release(release)
