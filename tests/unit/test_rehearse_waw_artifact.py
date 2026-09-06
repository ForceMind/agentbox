from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
import virtualenv
from agentbox_installer.artifact import extract_verified_tar, verify_release

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/rehearse-waw-artifact.py"
OPERATIONS_SCRIPT = ROOT / "scripts/rehearse-release-operations.py"
VERSION = "0.3.0rc8"
SOURCE_COMMIT = "a" * 40
MODULES = (
    "agentbox_api",
    "agentbox_browser_trust",
    "agentbox_cli",
    "agentbox_core",
    "agentbox_helper",
    "agentbox_installer",
    "agentbox_protocol",
    "agentbox_runtime",
    "agentbox_worker",
)
NATIVE_FILES = (
    "native/waw/include/agentbox_waw_protocol.h",
    "native/waw/src/attach_supervisor.c",
    "native/waw/src/bridge.c",
    "native/waw/src/pane_bootstrap.c",
    "native/waw/src/waw_isolation.c",
    "native/waw/src/waw_isolation.h",
    "native/waw/src/waw_native.c",
    "native/waw/src/waw_native.h",
)


def _script_module() -> Any:
    spec = importlib.util.spec_from_file_location("rehearse_waw_artifact", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture could not load rehearsal script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operations_module() -> Any:
    spec = importlib.util.spec_from_file_location("rehearse_release_operations", OPERATIONS_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture could not load operations rehearsal script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_wheel(path: Path, name: str, version: str, packages: tuple[str, ...] = ()) -> None:
    normalized = name.replace("-", "_")
    dist_info = f"{normalized}-{version}.dist-info"
    records = [f"{package}/__init__.py" for package in packages]
    if "agentbox_installer" in packages:
        records.append("agentbox_installer/lifecycle.py")
    records.extend(
        [
            f"{dist_info}/METADATA",
            f"{dist_info}/WHEEL",
            f"{dist_info}/RECORD",
        ]
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for package in packages:
            archive.writestr(f"{package}/__init__.py", "")
        if "agentbox_installer" in packages:
            archive.writestr("agentbox_installer/lifecycle.py", "class AgentBoxInstaller: pass\n")
        archive.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: AgentBox fixture\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{dist_info}/RECORD", "".join(f"{item},,\n" for item in records))


BUILD_SCRIPT = r"""
from __future__ import annotations
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/waw/src"
INCLUDE = ROOT / "native/waw/include"
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--cc", required=True)
parser.add_argument("--verbose", action="store_true")
args = parser.parse_args()
args.output.mkdir(parents=True)
for name, source in (
    ("agentbox-waw-pane-bootstrap", SOURCE / "pane_bootstrap.c"),
    ("agentbox-waw-bridge", SOURCE / "bridge.c"),
    ("agentbox-waw-attach-supervisor", SOURCE / "attach_supervisor.c"),
):
    command = [
        args.cc,
        f"-I{INCLUDE}",
        f"-I{SOURCE}",
        str(source),
        str(SOURCE / "waw_native.c"),
        str(SOURCE / "waw_isolation.c"),
        "-o",
        str(args.output / name),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
""".lstrip()

CHECK_SCRIPT = r"""
from __future__ import annotations
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ROOT / "native/waw/include"
parser = argparse.ArgumentParser()
parser.add_argument("--binary-dir", type=Path, required=True)
parser.add_argument("--no-build", action="store_true")
parser.add_argument("--cc", required=True)
args = parser.parse_args()
with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as temporary:
    probe = Path(temporary) / "header-probe.c"
    binary = Path(temporary) / "header-probe"
    probe.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    subprocess.run(
        [args.cc, f"-I{INCLUDE}", str(probe), "-o", str(binary)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(binary)], cwd=ROOT, check=True)
for name in (
    "agentbox-waw-pane-bootstrap",
    "agentbox-waw-bridge",
    "agentbox-waw-attach-supervisor",
):
    if not (args.binary_dir / name).is_file():
        raise RuntimeError("missing fixture binary")
""".lstrip()


def _build_bundle(tmp_path: Path) -> dict[str, Path]:
    release = tmp_path / "release"
    for directory in (
        "bootstrap",
        "migrations/versions",
        "native/waw/include",
        "native/waw/src",
        "scripts",
        "web/dist",
        "wheelhouse",
    ):
        (release / directory).mkdir(parents=True, exist_ok=True)
    (release / "VERSION").write_text(f"{VERSION}\n", encoding="ascii")
    (release / "LICENSE").write_text("fixture\n", encoding="utf-8")
    (release / "THIRD_PARTY_NOTICES.md").write_text("fixture\n", encoding="utf-8")
    (release / "install.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (release / "install.sh").chmod(0o755)
    (release / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (release / "web/dist/index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (release / "migrations/versions/0001.py").write_text(
        'revision = "0001_fixture"\ndown_revision = None\n', encoding="utf-8"
    )
    (release / "scripts/build-waw-native.py").write_text(BUILD_SCRIPT, encoding="utf-8")
    (release / "scripts/check-waw-native.py").write_text(CHECK_SCRIPT, encoding="utf-8")
    for name in NATIVE_FILES:
        path = release / name
        if path.suffix == ".c" and path.name in {
            "attach_supervisor.c",
            "bridge.c",
            "pane_bootstrap.c",
        }:
            content = "int main(void) { return 0; }\n"
        else:
            content = "/* synthetic closed native source */\n"
        path.write_text(content, encoding="utf-8")

    agentbox_wheel = release / f"wheelhouse/agentbox-{VERSION}-py3-none-any.whl"
    _write_wheel(agentbox_wheel, "agentbox", VERSION, MODULES)
    for abi in ("cp311", "cp312", "cp313"):
        _write_wheel(
            release / f"wheelhouse/fixture-1.0-{abi}-{abi}-manylinux_2_28_x86_64.whl",
            "fixture",
            "1.0",
        )
    bootstrap_wheel = release / "bootstrap/pip-26.2.1-py3-none-any.whl"
    embedded_pip = (
        Path(virtualenv.__file__).resolve().parent / "seed/wheels/embed/pip-26.2.1-py3-none-any.whl"
    )
    assert embedded_pip.is_file()
    shutil.copyfile(embedded_pip, bootstrap_wheel)
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"AgentBox {VERSION} SBOM",
        "packages": [
            {
                "name": "agentbox",
                "versionInfo": VERSION,
                "downloadLocation": f"https://github.com/ForceMind/agentbox/tree/{SOURCE_COMMIT}",
            }
        ],
    }
    (release / "SBOM.spdx.json").write_text(
        json.dumps(sbom, sort_keys=True) + "\n", encoding="utf-8"
    )
    files = {
        path.relative_to(release).as_posix(): _sha256(path)
        for path in release.rglob("*")
        if path.is_file()
    }
    manifest = {
        "schema_version": 4,
        "version": VERSION,
        "source_commit": SOURCE_COMMIT,
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
                "distribution": "Linux",
                "release": "fixture",
                "architecture": "x86_64",
                "qualification": "synthetic",
            }
        ],
        "artifact_authenticity": "unsigned; sha256 integrity only",
        "sbom_filename": "SBOM.spdx.json",
        "license_filename": "LICENSE",
        "third_party_notices_filename": "THIRD_PARTY_NOTICES.md",
        "executable_files": ["install.sh"],
    }
    manifest_path = release / "RELEASE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")

    public = tmp_path / "public"
    public.mkdir()
    artifact = public / f"agentbox-{VERSION}-linux-x86_64.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        for path in sorted(release.rglob("*")):
            archive.add(path, arcname=path.relative_to(release).as_posix(), recursive=False)
    external_manifest = public / "RELEASE_MANIFEST.json"
    external_sbom = public / "SBOM.spdx.json"
    external_manifest.write_bytes(manifest_path.read_bytes())
    external_sbom.write_bytes((release / "SBOM.spdx.json").read_bytes())
    checksums = public / "SHA256SUMS"
    checksums.write_text(
        "".join(
            f"{_sha256(path)}  {path.name}\n"
            for path in (artifact, external_manifest, external_sbom)
        ),
        encoding="ascii",
    )
    return {
        "artifact": artifact,
        "checksums": checksums,
        "manifest": external_manifest,
        "sbom": external_sbom,
    }


def _command(bundle: dict[str, Path], source_commit: str = SOURCE_COMMIT) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--artifact",
        str(bundle["artifact"]),
        "--checksums",
        str(bundle["checksums"]),
        "--manifest",
        str(bundle["manifest"]),
        "--sbom",
        str(bundle["sbom"]),
        "--expected-source-commit",
        source_commit,
        "--expected-source-ref-kind",
        "pull_request_head",
    ]


def test_synthetic_artifact_builds_native_and_imports_only_from_wheelhouse(
    tmp_path: Path,
) -> None:
    bundle = _build_bundle(tmp_path)
    ambient = tmp_path / "ambient"
    (ambient / "agentbox_core").mkdir(parents=True)
    (ambient / "agentbox_core/__init__.py").write_text(
        "raise RuntimeError('ambient package imported')\n", encoding="utf-8"
    )
    environment = {
        **os.environ,
        "PIP_INDEX_URL": "http://127.0.0.1:9/forbidden",
        "PIP_TRUSTED_HOST": "127.0.0.1",
        "PYTHONPATH": str(ambient),
    }
    completed = subprocess.run(
        _command(bundle),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (
        completed.stdout
        == "Artifact WAW provenance passed (AgentBox 0.3.0rc8, 9 isolated package modules).\n"
    )
    assert completed.stderr == ""


def test_unsafe_artifact_fails_with_only_the_fixed_surface(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    artifact = bundle["artifact"]
    with tarfile.open(artifact, "w:gz") as archive:
        member = tarfile.TarInfo("../../do-not-disclose-this-path")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    bundle["checksums"].write_text(
        "".join(
            f"{_sha256(path)}  {path.name}\n"
            for path in (artifact, bundle["manifest"], bundle["sbom"])
        ),
        encoding="ascii",
    )
    completed = subprocess.run(
        _command(bundle),
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "artifact rehearsal failed: public artifact verification\n"
    assert "do-not-disclose" not in completed.stderr


def test_expected_source_is_bound_before_native_or_install_work(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    completed = subprocess.run(
        _command(bundle, source_commit="b" * 40),
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stderr == "artifact rehearsal failed: release source provenance\n"


def test_retained_workspace_emits_an_artifact_bound_environment_proof(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    workspace = tmp_path / "retained-workspace"
    completed = subprocess.run(
        [*_command(bundle), "--skip-native", "--workspace-root", str(workspace)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    proof = json.loads((workspace / "environment-proof.json").read_text(encoding="utf-8"))
    environment = workspace / "environment"
    site_packages = Path(proof["site_packages"])
    wheel_path = f"wheelhouse/agentbox-{VERSION}-py3-none-any.whl"
    wheel_sha256 = _sha256(workspace / "unpacked" / wheel_path)
    assert proof == {
        "schema_version": 2,
        "artifact_sha256": _sha256(bundle["artifact"]),
        "source_sha": SOURCE_COMMIT,
        "source_ref_kind": "pull_request_head",
        "version": VERSION,
        "environment_prefix": str(environment.resolve()),
        "python_entry": str(environment / "bin/python"),
        "python_realpath": str((environment / "bin/python").resolve()),
        "site_packages": str(site_packages),
        "agentbox_wheel": {"path": wheel_path, "sha256": wheel_sha256},
        "pip_report": {
            "path": str((workspace / "pip-report.json").resolve()),
            "sha256": _sha256(workspace / "pip-report.json"),
        },
        "installed_distributions": [
            {
                "name": "agentbox",
                "version": VERSION,
                "wheel_path": wheel_path,
                "wheel_sha256": wheel_sha256,
            }
        ],
        "module_origins": {name: str(site_packages / name / "__init__.py") for name in MODULES},
        "include_system_site_packages": False,
        "pth_files": [],
        "installer_module": str(site_packages / "agentbox_installer/lifecycle.py"),
    }
    assert (workspace / "unpacked/RELEASE_MANIFEST.json").is_file()
    assert (workspace / "pip-report.json").is_file()
    assert not list(site_packages.glob("*.pth"))
    assert (workspace / "environment-proof.json").stat().st_mode & 0o777 == 0o600


def test_retained_proof_round_trips_into_operations_environment_validation(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    workspace = tmp_path / "operations-workspace"
    completed = subprocess.run(
        [*_command(bundle), "--skip-native", "--workspace-root", str(workspace)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    operations = _operations_module()
    with tempfile.TemporaryDirectory(dir=tmp_path) as temporary:
        release = Path(temporary) / "release"
        extract_verified_tar(bundle["artifact"], release)
        manifest = verify_release(release)
        artifact = operations.ArtifactInput(
            artifact=bundle["artifact"],
            sha256=_sha256(bundle["artifact"]),
            version=VERSION,
            source_sha=SOURCE_COMMIT,
            python=workspace / "environment/bin/python",
            environment_root=workspace / "environment",
            environment_proof=workspace / "environment-proof.json",
        )
        wheel_sha256, installer_module = operations._validate_environment_binding(
            artifact,
            manifest,
            release,
            "candidate",
        )
    assert wheel_sha256 == _sha256(
        workspace / "unpacked/wheelhouse/agentbox-0.3.0rc8-py3-none-any.whl"
    )
    assert installer_module.endswith("agentbox_installer/lifecycle.py")


def test_artifact_synthetic_requires_a_manifest_hashed_runner(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    completed = subprocess.run(
        [*_command(bundle), "--skip-native", "--run-synthetic"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "artifact rehearsal failed: artifact synthetic runner\n"


def test_compiler_provenance_rejects_an_external_include(tmp_path: Path) -> None:
    module = _script_module()
    release = tmp_path / "release"
    source = release / "native/waw/src"
    include = release / "native/waw/include"
    source.mkdir(parents=True)
    include.mkdir(parents=True)
    native = source / "fixture.c"
    native.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    output = release / "bin/fixture"
    records = [
        [
            f"-I{include}",
            f"-I{source}",
            "-include",
            str(tmp_path / "outside.h"),
            str(native),
            "-o",
            str(output),
        ]
    ]
    with pytest.raises(module.RehearsalError, match="native compiler provenance"):
        module.verify_compiler_provenance(records, release)


def test_pip_report_rejects_a_wheel_outside_the_artifact(tmp_path: Path) -> None:
    module = _script_module()
    release = tmp_path / "release"
    (release / "wheelhouse").mkdir(parents=True)
    outside = tmp_path / "agentbox.whl"
    outside.write_bytes(b"fixture")
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "install": [
                    {
                        "metadata": {"name": "agentbox", "version": VERSION},
                        "download_info": {
                            "url": outside.as_uri(),
                            "archive_info": {"hashes": {"sha256": _sha256(outside)}},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = module.ReleaseManifest(
        VERSION,
        "0001_fixture",
        False,
        {"wheelhouse/agentbox.whl": _sha256(outside)},
    )
    with pytest.raises(module.RehearsalError, match="wheelhouse install provenance"):
        module.verify_pip_report(report, release, manifest)
