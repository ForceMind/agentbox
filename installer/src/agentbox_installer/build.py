"""Build a checksummed offline release payload from a reviewed checkout."""

from __future__ import annotations

import ast
import email.policy
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from agentbox_installer.artifact import (
    RELEASE_MANIFEST_NAME,
    VERSION_PATTERN,
    sha256_file,
    verify_release_bundle,
)


class BuildError(RuntimeError):
    pass


RELEASE_DOCUMENTS = (
    "docs/QUICKSTART.md",
    "docs/INSTALLATION.md",
    "docs/DEPLOYMENT.md",
    "docs/UPGRADE.md",
    "docs/ROLLBACK.md",
    "docs/UNINSTALL.md",
    "docs/PLATFORM_SUPPORT.md",
    "docs/KNOWN_LIMITATIONS.md",
    "docs/MVP_ACCEPTANCE.md",
    "docs/RELEASE_CHECKLIST.md",
)
PLATFORM_SUPPORT = (
    {
        "distribution": "OpenCloudOS",
        "release": "9",
        "architecture": "x86_64",
        "qualification": "real-host validated",
    },
    {
        "distribution": "Ubuntu",
        "release": "24.04",
        "architecture": "x86_64",
        "qualification": "CI validated",
    },
    {
        "distribution": "Ubuntu",
        "release": "22.04",
        "architecture": "x86_64",
        "qualification": "unsupported",
    },
    {
        "distribution": "Rocky Linux",
        "release": "9",
        "architecture": "x86_64",
        "qualification": "fixture validated",
    },
    {
        "distribution": "Debian",
        "release": "12",
        "architecture": "x86_64",
        "qualification": "fixture validated",
    },
    {
        "distribution": "Linux",
        "release": "any",
        "architecture": "aarch64",
        "qualification": "unsupported",
    },
)


@dataclass(frozen=True)
class ReleaseBundle:
    version: str
    source_commit: str
    artifact: Path
    artifact_sha256: str
    manifest: Path
    sbom: Path
    checksums: Path


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


def release_version(source: Path) -> str:
    version_file = source / "packages/agentbox-core/src/agentbox_core/version.py"
    try:
        tree = ast.parse(version_file.read_text(encoding="utf-8"), filename=str(version_file))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise BuildError("AgentBox version source is unavailable") from exc
    values: list[str] = []
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__version__"
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError) as exc:
                raise BuildError("AgentBox version source is invalid") from exc
            if isinstance(value, str):
                values.append(value)
    if len(values) != 1 or VERSION_PATTERN.fullmatch(values[0]) is None:
        raise BuildError("AgentBox version source is invalid")
    return values[0]


def npm_version(version: str) -> str:
    match = re.fullmatch(r"([0-9]+\.[0-9]+\.[0-9]+)rc([0-9]+)", version)
    return (
        f"{match.group(1)}-rc.{match.group(2)}" if match is not None else version.replace("+", "-")
    )


def verify_version_consistency(source: Path) -> str:
    version = release_version(source)
    try:
        pyproject = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
        root_package = json.loads((source / "package.json").read_text(encoding="utf-8"))
        web_package = json.loads((source / "apps/web/package.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        raise BuildError("version metadata is unavailable") from exc
    if (
        pyproject.get("project", {}).get("dynamic") != ["version"]
        or pyproject.get("tool", {}).get("setuptools", {}).get("dynamic", {}).get("version")
        != {"attr": "agentbox_core.version.__version__"}
        or root_package.get("version") != npm_version(version)
        or web_package.get("version") != npm_version(version)
    ):
        raise BuildError("AgentBox version metadata is inconsistent")
    return version


def _git_metadata(source: Path) -> tuple[str, int]:
    if not (source / ".git").exists():
        raise BuildError("release build requires a Git checkout")
    status = _run_build_command(
        ("/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"), source, timeout=30
    ).stdout.decode("utf-8", "strict")
    if status:
        raise BuildError("release build requires a clean tracked checkout")
    commit = _run_build_command(
        ("/usr/bin/git", "rev-parse", "HEAD"), source, timeout=30
    ).stdout.decode("ascii", "strict")
    timestamp = _run_build_command(
        ("/usr/bin/git", "show", "-s", "--format=%ct", "HEAD"), source, timeout=30
    ).stdout.decode("ascii", "strict")
    if re.fullmatch(r"[0-9a-f]{40}\n?", commit) is None or not timestamp.strip().isdigit():
        raise BuildError("release source commit metadata is invalid")
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", timestamp.strip()))
    if epoch < 315532800:
        raise BuildError("SOURCE_DATE_EPOCH is invalid")
    return commit.strip(), epoch


def _run_build_command(
    argv: tuple[str, ...], cwd: Path, *, timeout: int, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    environment = {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
    }
    if extra_env:
        environment.update(extra_env)
    try:
        result = subprocess.run(  # noqa: S603 - reviewed local build tools and fixed argv
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BuildError("release build command failed") from exc
    if result.returncode != 0:
        raise BuildError("release build command failed")
    return result


def build_release_artifact(
    source: Path,
    output: Path,
    *,
    version: str,
    python: Path,
    source_commit: str | None = None,
    source_date_epoch: int | None = None,
    pnpm: Path | None = None,
) -> str:
    if not VERSION_PATTERN.fullmatch(version):
        raise BuildError("release version must follow semantic version syntax")
    source = source.resolve()
    if not (source / "pyproject.toml").is_file() or not (source / "alembic.ini").is_file():
        raise BuildError("source is not an AgentBox checkout")
    if output.exists() or output.is_symlink():
        raise BuildError("artifact output already exists")
    actual_version = verify_version_consistency(source)
    if version != actual_version:
        raise BuildError("requested release version does not match the source version")
    web_dist = source / "apps/web/dist"
    if not (web_dist / "index.html").is_file():
        raise BuildError("frontend production artifact is missing; run pnpm build first")
    if source_commit is None or source_date_epoch is None:
        observed_commit, observed_epoch = _git_metadata(source)
        source_commit = source_commit or observed_commit
        source_date_epoch = source_date_epoch or observed_epoch
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None or source_date_epoch < 315532800:
        raise BuildError("release source metadata is invalid")
    pnpm = pnpm or Path(shutil.which("pnpm") or "")
    if not pnpm.is_absolute() or not pnpm.is_file():
        raise BuildError("pnpm is required to inventory frontend production dependencies")
    with tempfile.TemporaryDirectory(prefix="agentbox-release-") as temporary:
        release = Path(temporary) / "release"
        wheelhouse = release / "wheelhouse"
        wheelhouse.mkdir(mode=0o755, parents=True)
        build_environment = {"SOURCE_DATE_EPOCH": str(source_date_epoch)}
        _run_build_command(
            (
                str(python),
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--dest",
                str(wheelhouse),
                "--requirement",
                str(source / "requirements-release.lock"),
            ),
            source,
            timeout=600,
            extra_env=build_environment,
        )
        for python_abi in ("312", "313"):
            _run_build_command(
                (
                    str(python),
                    "-m",
                    "pip",
                    "download",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "--platform",
                    "manylinux_2_28_x86_64",
                    "--platform",
                    "manylinux2014_x86_64",
                    "--implementation",
                    "cp",
                    "--python-version",
                    python_abi,
                    "--abi",
                    f"cp{python_abi}",
                    "--dest",
                    str(wheelhouse),
                    "--requirement",
                    str(source / "requirements-release.lock"),
                ),
                source,
                timeout=600,
                extra_env=build_environment,
            )
        _run_build_command(
            (
                str(python),
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheelhouse),
                str(source),
            ),
            source,
            timeout=600,
            extra_env=build_environment,
        )
        agentbox_wheels = sorted(wheelhouse.glob("agentbox-*.whl"))
        if len(agentbox_wheels) != 1 or _wheel_version(agentbox_wheels[0]) != version:
            raise BuildError("AgentBox package version does not match release version")
        _copy_regular_tree(web_dist, release / "web/dist")
        _copy_regular_tree(source / "migrations", release / "migrations")
        shutil.copyfile(source / "alembic.ini", release / "alembic.ini")
        os.chmod(release / "alembic.ini", 0o644)
        for source_name, target_name, mode in (
            ("LICENSE", "LICENSE", 0o644),
            ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md", 0o644),
            ("installer/release-install.sh", "install.sh", 0o755),
        ):
            source_path = source / source_name
            if source_path.is_symlink() or not source_path.is_file():
                raise BuildError(f"required release input is unavailable: {source_name}")
            shutil.copyfile(source_path, release / target_name)
            os.chmod(release / target_name, mode)
        (release / "VERSION").write_text(f"{version}\n", encoding="ascii")
        os.chmod(release / "VERSION", 0o644)
        release_docs = release / "docs"
        release_docs.mkdir(mode=0o755)
        for name in RELEASE_DOCUMENTS:
            source_path = source / name
            if source_path.is_symlink() or not source_path.is_file():
                raise BuildError(f"required release input is unavailable: {name}")
            shutil.copyfile(source_path, release_docs / source_path.name)
            os.chmod(release_docs / source_path.name, 0o644)
        release_notes = source / f"docs/releases/{version}.md"
        if release_notes.is_symlink() or not release_notes.is_file():
            raise BuildError("candidate release notes are unavailable")
        (release_docs / "releases").mkdir(mode=0o755)
        shutil.copyfile(release_notes, release_docs / "releases" / release_notes.name)
        os.chmod(release_docs / "releases" / release_notes.name, 0o644)

        python_packages = _python_package_inventory(wheelhouse)
        frontend_packages = _frontend_package_inventory(source, pnpm)
        _verify_license_inventory(python_packages + frontend_packages)
        sbom = _spdx_sbom(
            version,
            source_commit,
            source_date_epoch,
            python_packages,
            frontend_packages,
        )
        (release / "SBOM.spdx.json").write_text(
            json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(release / "SBOM.spdx.json", 0o644)
        if any(path.suffix == ".map" for path in (release / "web/dist").rglob("*")):
            raise BuildError("production Web source maps are not release files")
        files = {
            path.relative_to(release).as_posix(): sha256_file(path)
            for path in sorted(release.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema_version": 2,
            "version": version,
            "source_commit": source_commit,
            "target_platform": "linux",
            "target_architecture": "x86_64",
            "build_mode": "release-candidate",
            "database_revision": _migration_head(source / "migrations/versions"),
            "database_backward_compatible": False,
            "file_allowlist": sorted(files),
            "files": files,
            "required_python": ">=3.11",
            "platform_support": PLATFORM_SUPPORT,
            "artifact_authenticity": "unsigned; sha256 integrity only",
            "sbom_filename": "SBOM.spdx.json",
            "license_filename": "LICENSE",
            "third_party_notices_filename": "THIRD_PARTY_NOTICES.md",
            "executable_files": ["install.sh"],
        }
        (release / RELEASE_MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(release / RELEASE_MANIFEST_NAME, 0o644)
        output.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        _write_reproducible_tar(release, output, source_date_epoch)
        return sha256_file(output)


def build_release_bundle(source: Path, output_directory: Path, *, python: Path) -> ReleaseBundle:
    source = source.resolve()
    version = verify_version_consistency(source)
    commit, epoch = _git_metadata(source)
    if output_directory.exists() and any(output_directory.iterdir()):
        raise BuildError("release output directory must be empty")
    output_directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    artifact = output_directory / f"agentbox-{version}-linux-x86_64.tar.gz"
    digest = build_release_artifact(
        source,
        artifact,
        version=version,
        python=python,
        source_commit=commit,
        source_date_epoch=epoch,
    )
    with tempfile.TemporaryDirectory(prefix="agentbox-metadata-") as temporary:
        from agentbox_installer.artifact import extract_verified_tar

        release = Path(temporary) / "release"
        extract_verified_tar(artifact, release)
        manifest = output_directory / RELEASE_MANIFEST_NAME
        sbom = output_directory / "SBOM.spdx.json"
        shutil.copyfile(release / RELEASE_MANIFEST_NAME, manifest)
        shutil.copyfile(release / "SBOM.spdx.json", sbom)
    checksums = output_directory / "SHA256SUMS"
    public_files = (artifact, manifest, sbom)
    checksums.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in public_files),
        encoding="ascii",
    )
    verify_release_bundle(artifact, checksums, manifest, sbom)
    return ReleaseBundle(version, commit, artifact, digest, manifest, sbom, checksums)


def _write_reproducible_tar(source: Path, output: Path, epoch: int) -> None:
    with (
        output.open("xb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=epoch) as zipped,
        tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            relative = path.relative_to(source).as_posix()
            details = path.lstat()
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise BuildError("release payload contains an unsafe object")
            info = tarfile.TarInfo(relative)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = epoch
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
            else:
                info.mode = 0o755 if relative == "install.sh" else 0o644
                info.size = details.st_size
                with path.open("rb") as stream:
                    archive.addfile(info, stream)


def _python_package_inventory(wheelhouse: Path) -> list[dict[str, str]]:
    packages: dict[tuple[str, str], dict[str, str]] = {}
    for wheel in sorted(wheelhouse.glob("*.whl")):
        try:
            with zipfile.ZipFile(wheel) as archive:
                names = [
                    name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
                ]
                if len(names) != 1:
                    raise BuildError("Python dependency wheel metadata is invalid")
                message = BytesParser(policy=email.policy.default).parsebytes(
                    archive.read(names[0])
                )
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            raise BuildError("Python dependency wheel metadata is invalid") from exc
        name = message.get("Name")
        version = message.get("Version")
        license_value = message.get("License-Expression") or message.get("License") or "NOASSERTION"
        homepage = message.get("Home-page") or "NOASSERTION"
        if not name or not version:
            raise BuildError("Python dependency wheel metadata is incomplete")
        item = {
            "name": str(name),
            "version": str(version),
            "license": _normalize_license(str(license_value)),
            "download": str(homepage),
            "manager": "pypi",
        }
        key = (item["name"].casefold(), item["version"])
        previous = packages.get(key)
        if previous is not None and previous != item:
            raise BuildError("Python dependency wheel metadata is inconsistent across ABIs")
        packages[key] = item
    return [packages[key] for key in sorted(packages)]


def _frontend_package_inventory(source: Path, pnpm: Path) -> list[dict[str, str]]:
    environment = {"PATH": f"{pnpm.parent}:/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
    result = _run_build_command(
        (str(pnpm), "licenses", "list", "--prod", "--json"),
        source,
        timeout=120,
        extra_env=environment,
    )
    try:
        value: Any = json.loads(result.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError("frontend license inventory is invalid") from exc
    if not isinstance(value, dict):
        raise BuildError("frontend license inventory is invalid")
    packages: dict[tuple[str, str], dict[str, str]] = {}
    for license_name, entries in value.items():
        if not isinstance(license_name, str) or not isinstance(entries, list):
            raise BuildError("frontend license inventory is invalid")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                raise BuildError("frontend license inventory is invalid")
            versions = entry.get("versions")
            if not isinstance(versions, list) or not all(
                isinstance(item, str) for item in versions
            ):
                raise BuildError("frontend license inventory is invalid")
            for version in versions:
                key = (entry["name"], version)
                packages[key] = {
                    "name": entry["name"],
                    "version": version,
                    "license": _normalize_license(str(entry.get("license") or license_name)),
                    "download": str(entry.get("homepage") or "NOASSERTION"),
                    "manager": "npm",
                }
    return [
        packages[key] for key in sorted(packages, key=lambda item: (item[0].casefold(), item[1]))
    ]


def _normalize_license(value: str) -> str:
    stripped = " ".join(value.strip().split())
    aliases = {
        "Apache Software License": "Apache-2.0",
        "BSD License": "BSD-3-Clause",
        "MIT License": "MIT",
        "ISC License (ISCL)": "ISC",
    }
    return aliases.get(stripped, stripped if stripped else "NOASSERTION")


def _verify_license_inventory(packages: list[dict[str, str]]) -> None:
    forbidden = re.compile(r"(?:^|[^A-Za-z])(AGPL|GPL)(?:[^A-Za-z]|$)", re.IGNORECASE)
    if not packages or any(item["license"] == "NOASSERTION" for item in packages):
        raise BuildError("dependency license inventory contains an unknown license")
    if any(forbidden.search(item["license"]) for item in packages):
        raise BuildError("dependency license inventory contains a distribution blocker")


def _spdx_id(manager: str, name: str, version: str) -> str:
    digest = hashlib.sha256(f"{manager}:{name}:{version}".encode()).hexdigest()[:20]
    return f"SPDXRef-Package-{digest}"


def _spdx_sbom(
    version: str,
    commit: str,
    epoch: int,
    python_packages: list[dict[str, str]],
    frontend_packages: list[dict[str, str]],
) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    agentbox_id = _spdx_id("agentbox", "agentbox", version)
    packages.append(
        {
            "SPDXID": agentbox_id,
            "name": "agentbox",
            "versionInfo": version,
            "downloadLocation": f"https://github.com/ForceMind/agentbox/tree/{commit}",
            "filesAnalyzed": False,
            "licenseConcluded": "Apache-2.0",
            "licenseDeclared": "Apache-2.0",
            "supplier": "Organization: AgentBox contributors",
        }
    )
    relationships.append(
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": agentbox_id,
        }
    )
    for item in python_packages + frontend_packages:
        package_id = _spdx_id(item["manager"], item["name"], item["version"])
        packages.append(
            {
                "SPDXID": package_id,
                "name": item["name"],
                "versionInfo": item["version"],
                "downloadLocation": item["download"],
                "filesAnalyzed": False,
                "licenseConcluded": item["license"],
                "licenseDeclared": item["license"],
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": (
                            f"pkg:{item['manager']}/{item['name']}@{item['version']}"
                        ),
                    }
                ],
            }
        )
        if item["name"].casefold() != "agentbox":
            relationships.append(
                {
                    "spdxElementId": agentbox_id,
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": package_id,
                }
            )
    created = (
        datetime.fromtimestamp(epoch, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"AgentBox {version} SBOM",
        "documentNamespace": f"https://github.com/ForceMind/agentbox/sbom/{commit}/{version}",
        "creationInfo": {"created": created, "creators": ["Tool: AgentBox release builder"]},
        "packages": sorted(packages, key=lambda item: item["SPDXID"]),
        "relationships": sorted(
            relationships,
            key=lambda item: (
                item["spdxElementId"],
                item["relationshipType"],
                item["relatedSpdxElement"],
            ),
        ),
    }


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
