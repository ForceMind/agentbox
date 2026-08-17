from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from agentbox_installer import artifact as artifact_module
from agentbox_installer.artifact import (
    ArtifactError,
    extract_verified_tar,
    scan_wheel_bytes,
    verify_release,
)
from agentbox_installer.build import (
    _frontend_package_inventory,
    _python_package_inventory,
    frontend_inventory_from_pnpm,
    npm_version,
    release_bootstrap_pip,
    release_build_toolchain,
    verify_version_consistency,
)


def _minimal_wheel(path: Path, version: str, name: str = "agentbox") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{name}-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n",
        )


def _release_candidate(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    release = tmp_path / "release"
    for directory in ("bootstrap", "wheelhouse", "web/dist", "migrations/versions"):
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
    for abi in ("cp311", "cp312", "cp313"):
        _minimal_wheel(
            release / f"wheelhouse/fixture-1.0-{abi}-{abi}-manylinux_2_28_x86_64.whl",
            "1.0",
            "fixture",
        )
    bootstrap_wheel = release / "bootstrap/pip-26.2.1-py3-none-any.whl"
    _minimal_wheel(bootstrap_wheel, "26.2.1", "pip")
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
        "schema_version": 4,
        "version": version,
        "source_commit": "a" * 40,
        "source_ref_kind": "pull_request_head",
        "target_platform": "linux",
        "target_architecture": "x86_64",
        "build_mode": "release-candidate",
        "database_revision": "0001_fixture",
        "database_backward_compatible": False,
        "file_allowlist": sorted(files),
        "files": files,
        "required_python": ">=3.11,<3.14",
        "supported_python_abis": ["cp311", "cp312", "cp313"],
        "build_toolchain": {
            "node": "22.23.2",
            "pip": "26.2.1",
            "pnpm": "11.20.0",
            "setuptools": "83.0.0",
            "wheel": "0.46.2",
        },
        "bootstrap_pip": {
            "filename": "bootstrap/pip-26.2.1-py3-none-any.whl",
            "version": "26.2.1",
            "sha256": files["bootstrap/pip-26.2.1-py3-none-any.whl"],
            "method": "pythonpath-wheel-target",
        },
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


def test_release_build_toolchain_is_read_from_the_reviewed_lock() -> None:
    root = Path(__file__).resolve().parents[2]

    assert release_build_toolchain(root) == {
        "node": "22.23.2",
        "pip": "26.2.1",
        "pnpm": "11.20.0",
        "setuptools": "83.0.0",
        "wheel": "0.46.2",
    }
    assert release_bootstrap_pip(root) == {
        "filename": "bootstrap/pip-26.2.1-py3-none-any.whl",
        "version": "26.2.1",
        "sha256": "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e",
        "method": "pythonpath-wheel-target",
    }


def test_release_packaging_compatibility_lock_and_gate_are_fail_closed() -> None:
    root = Path(__file__).resolve().parents[2]
    packaging_lock = [
        line
        for line in (root / "requirements-release-packaging.lock")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith("#")
    ]
    assert packaging_lock == [
        "pip==26.2.1 "
        "--hash=sha256:71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e",
        "wheel==0.46.2 "
        "--hash=sha256:33ae60725d69eaa249bc1982e739943c23b34b58d51f1cb6253453773aca6e65",
    ]

    workflow = (root / ".github/workflows/release-candidate.yml").read_text(encoding="utf-8")
    assert 'python-version: ["3.11", "3.12", "3.13"]' in workflow
    assert "--requirement requirements-release-packaging.lock" in workflow
    assert "python -m pip_audit --local --skip-editable" in workflow
    assert "needs: [packaging-toolchain, release-candidate]" in workflow
    assert 'test "$PACKAGING_TOOLCHAIN_RESULT" = "success"' in workflow
    assert 'test "$RELEASE_CANDIDATE_RESULT" = "success"' in workflow


def test_internal_agentbox_wheel_is_not_duplicated_as_a_dependency(tmp_path: Path) -> None:
    _minimal_wheel(tmp_path / "agentbox-0.3.0rc1-py3-none-any.whl", "0.3.0rc1")

    assert _python_package_inventory(tmp_path) == []


def test_python_inventory_uses_closed_license_classifier_fallback(tmp_path: Path) -> None:
    wheel = tmp_path / "rfc8785-0.1.4-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "rfc8785-0.1.4.dist-info/METADATA",
            "Metadata-Version: 2.4\n"
            "Name: rfc8785\n"
            "Version: 0.1.4\n"
            "Classifier: License :: OSI Approved :: Apache Software License\n",
        )

    assert _python_package_inventory(tmp_path) == [
        {
            "name": "rfc8785",
            "version": "0.1.4",
            "license": "Apache-2.0",
            "download": "NOASSERTION",
            "manager": "pypi",
        }
    ]


def test_python_inventory_rejects_ambiguous_license_classifier_fallback(tmp_path: Path) -> None:
    wheel = tmp_path / "fixture-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "fixture-1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\n"
            "Name: fixture\n"
            "Version: 1.0\n"
            "Classifier: License :: OSI Approved :: Apache Software License\n"
            "Classifier: License :: OSI Approved :: MIT License\n",
        )

    assert _python_package_inventory(tmp_path)[0]["license"] == "NOASSERTION"


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
    release, manifest = _release_candidate(tmp_path)
    observed = verify_release(release)
    expected_files = manifest["files"]
    assert isinstance(expected_files, dict)
    expected_bootstrap_digest = expected_files["bootstrap/pip-26.2.1-py3-none-any.whl"]
    assert isinstance(expected_bootstrap_digest, str)

    assert observed.schema_version == 4
    assert observed.version == "0.3.0rc1"
    assert observed.source_commit == "a" * 40
    assert observed.source_ref_kind == "pull_request_head"
    assert observed.required_python == ">=3.11,<3.14"
    assert observed.supported_python_abis == ("cp311", "cp312", "cp313")
    assert observed.bootstrap_pip == {
        "filename": "bootstrap/pip-26.2.1-py3-none-any.whl",
        "version": "26.2.1",
        "sha256": expected_bootstrap_digest,
        "method": "pythonpath-wheel-target",
    }
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


def test_release_candidate_rejects_overbroad_python_or_incomplete_abi_contract(
    tmp_path: Path,
) -> None:
    release, manifest = _release_candidate(tmp_path)
    manifest["required_python"] = ">=3.11"
    (release / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="manifest values"):
        verify_release(release)

    manifest["required_python"] = ">=3.11,<3.14"
    manifest["supported_python_abis"] = ["cp311", "cp312"]
    (release / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="compatibility metadata"):
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


def test_nested_wheel_secret_scan_detects_only_decompressed_canary() -> None:
    canary = b"CODEX-PAIR-CANARY"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("agentbox/runtime.py", canary * 32)
    wheel = payload.getvalue()

    assert canary not in wheel
    with pytest.raises(ArtifactError, match="contains a release canary"):
        scan_wheel_bytes(wheel, (canary,))


@pytest.mark.parametrize(
    "names",
    [
        ("../escape.py",),
        ("agentbox/module.py", "agentbox/module.py"),
        ("agentbox/e\u0301.py",),
    ],
)
def test_nested_wheel_scan_rejects_unsafe_or_duplicate_members(names: tuple[str, ...]) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for name in names:
            archive.writestr(name, b"safe")

    with pytest.raises(ArtifactError):
        scan_wheel_bytes(payload.getvalue(), (b"CANARY",))


def test_nested_wheel_scan_rejects_malformed_zip() -> None:
    with pytest.raises(ArtifactError, match="malformed"):
        scan_wheel_bytes(b"not-a-wheel", (b"CANARY",))


def test_nested_wheel_scan_enforces_member_and_expanded_size_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("agentbox/a.py", b"a" * 8)
        archive.writestr("agentbox/b.py", b"b" * 8)
    wheel = payload.getvalue()

    monkeypatch.setattr(artifact_module, "MAX_WHEEL_MEMBERS", 1)
    with pytest.raises(ArtifactError, match="member count"):
        scan_wheel_bytes(wheel, (b"CANARY",))
    monkeypatch.setattr(artifact_module, "MAX_WHEEL_MEMBERS", 10)
    monkeypatch.setattr(artifact_module, "MAX_WHEEL_MEMBER_BYTES", 4)
    with pytest.raises(ArtifactError, match="member exceeds"):
        scan_wheel_bytes(wheel, (b"CANARY",))
    monkeypatch.setattr(artifact_module, "MAX_WHEEL_MEMBER_BYTES", 16)
    monkeypatch.setattr(artifact_module, "MAX_WHEEL_EXPANDED_BYTES", 12)
    with pytest.raises(ArtifactError, match="wheel exceeds"):
        scan_wheel_bytes(wheel, (b"CANARY",))
