from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from agentbox_installer.artifact import ArtifactError, extract_verified_tar, verify_release
from agentbox_installer.build import (
    _frontend_package_inventory,
    _python_package_inventory,
    frontend_inventory_from_pnpm,
    npm_version,
    verify_version_consistency,
)


def _minimal_wheel(path: Path, version: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"agentbox-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: agentbox\nVersion: {version}\n",
        )


def _release_candidate(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    release = tmp_path / "release"
    for directory in ("wheelhouse", "web/dist", "migrations/versions"):
        (release / directory).mkdir(parents=True, exist_ok=True)
    version = "0.3.0rc1"
    (release / "VERSION").write_text(f"{version}\n", encoding="ascii")
    (release / "LICENSE").write_text("fixture\n", encoding="utf-8")
    (release / "THIRD_PARTY_NOTICES.md").write_text("fixture\n", encoding="utf-8")
    (release / "install.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (release / "install.sh").chmod(0o755)
    (release / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (release / "web/dist/index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (release / "migrations/versions/0001.py").write_text(
        'revision = "0001_fixture"\ndown_revision = None\n', encoding="utf-8"
    )
    wheel = release / f"wheelhouse/agentbox-{version}-py3-none-any.whl"
    _minimal_wheel(wheel, version)
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"AgentBox {version} SBOM",
        "packages": [],
    }
    (release / "SBOM.spdx.json").write_text(
        json.dumps(sbom, sort_keys=True) + "\n", encoding="utf-8"
    )
    files = {
        path.relative_to(release).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in release.rglob("*")
        if path.is_file()
    }
    manifest: dict[str, object] = {
        "schema_version": 2,
        "version": version,
        "source_commit": "a" * 40,
        "target_platform": "linux",
        "target_architecture": "x86_64",
        "build_mode": "release-candidate",
        "database_revision": "0001_fixture",
        "database_backward_compatible": False,
        "file_allowlist": sorted(files),
        "files": files,
        "required_python": ">=3.11",
        "platform_support": [
            {
                "distribution": "OpenCloudOS",
                "release": "9",
                "architecture": "x86_64",
                "qualification": "real-host validated",
            }
        ],
        "artifact_authenticity": "unsigned; sha256 integrity only",
        "sbom_filename": "SBOM.spdx.json",
        "license_filename": "LICENSE",
        "third_party_notices_filename": "THIRD_PARTY_NOTICES.md",
        "executable_files": ["install.sh"],
    }
    (release / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    return release, manifest


def test_version_metadata_uses_the_core_source_and_npm_rc_form() -> None:
    root = Path(__file__).resolve().parents[2]
    assert verify_version_consistency(root) == "0.3.0rc1"
    assert npm_version("0.3.0rc1") == "0.3.0-rc.1"


def test_internal_agentbox_wheel_is_not_duplicated_as_a_dependency(tmp_path: Path) -> None:
    _minimal_wheel(tmp_path / "agentbox-0.3.0rc1-py3-none-any.whl", "0.3.0rc1")

    assert _python_package_inventory(tmp_path) == []


def test_reviewed_frontend_inventory_matches_normalized_pnpm_shape() -> None:
    root = Path(__file__).resolve().parents[2]
    reviewed = _frontend_package_inventory(root)
    pnpm_value: dict[str, list[dict[str, object]]] = {}
    for item in reviewed:
        pnpm_value.setdefault(item["license"], []).append(
            {
                "name": item["name"],
                "versions": [item["version"]],
                "license": item["license"],
                "homepage": item["download"],
            }
        )

    assert len(reviewed) == 8
    assert frontend_inventory_from_pnpm(pnpm_value) == reviewed


def test_release_candidate_manifest_verifies_complete_contract(tmp_path: Path) -> None:
    release, _manifest = _release_candidate(tmp_path)
    observed = verify_release(release)

    assert observed.schema_version == 2
    assert observed.version == "0.3.0rc1"
    assert observed.source_commit == "a" * 40
    assert observed.artifact_authenticity == "unsigned; sha256 integrity only"


def test_release_candidate_rejects_unexpected_executable_and_migration_mismatch(
    tmp_path: Path,
) -> None:
    release, manifest = _release_candidate(tmp_path)
    index = release / "web/dist/index.html"
    index.chmod(0o755)
    with pytest.raises(ArtifactError, match="executable file set"):
        verify_release(release)

    index.chmod(0o644)
    manifest["database_revision"] = "wrong"
    (release / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="migration head"):
        verify_release(release)


@pytest.mark.parametrize("name", ["e\u0301.txt", "safe\\escape.txt", "control\nname"])
def test_archive_rejects_noncanonical_or_ambiguous_member_names(tmp_path: Path, name: str) -> None:
    artifact = tmp_path / "unsafe.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        member = tarfile.TarInfo(name)
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))

    with pytest.raises(ArtifactError, match="unsafe path"):
        extract_verified_tar(artifact, tmp_path / "release")


def test_archive_rejects_duplicate_paths_and_unsafe_modes(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.tar.gz"
    with tarfile.open(duplicate, "w:gz") as archive:
        for payload in (b"a", b"b"):
            member = tarfile.TarInfo("duplicate.txt")
            member.size = 1
            archive.addfile(member, io.BytesIO(payload))
    with pytest.raises(ArtifactError, match="duplicate or colliding"):
        extract_verified_tar(duplicate, tmp_path / "duplicate-release")

    unsafe_mode = tmp_path / "mode.tar.gz"
    with tarfile.open(unsafe_mode, "w:gz") as archive:
        member = tarfile.TarInfo("unsafe.txt")
        member.mode = 0o4777
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ArtifactError, match="unsafe file mode"):
        extract_verified_tar(unsafe_mode, tmp_path / "mode-release")
