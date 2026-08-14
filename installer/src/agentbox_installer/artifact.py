"""Verified AgentBox release artifact handling."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import stat
import tarfile
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any

from agentbox_installer.versioning import valid_version

MAX_ARCHIVE_MEMBERS = 20_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_WHEEL_MEMBERS = 10_000
MAX_WHEEL_MEMBER_BYTES = 32 * 1024 * 1024
MAX_WHEEL_EXPANDED_BYTES = 256 * 1024 * 1024
RELEASE_MANIFEST_NAME = "RELEASE_MANIFEST.json"
LEGACY_MANIFEST_NAME = "manifest.json"
REQUIRED_RELEASE_PATHS = frozenset(
    {
        "VERSION",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "SBOM.spdx.json",
        "install.sh",
        "alembic.ini",
        "web/dist/index.html",
    }
)


class ArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    database_revision: str
    database_backward_compatible: bool
    files: dict[str, str]
    schema_version: int = 1
    source_commit: str | None = None
    source_ref_kind: str | None = None
    target_platform: str | None = None
    target_architecture: str | None = None
    build_mode: str | None = None
    required_python: str | None = None
    supported_python_abis: tuple[str, ...] = ()
    build_toolchain: dict[str, str] | None = None
    bootstrap_pip: dict[str, str] | None = None
    platform_support: tuple[dict[str, str], ...] = ()
    artifact_authenticity: str | None = None
    sbom_filename: str | None = None
    license_filename: str | None = None
    third_party_notices_filename: str | None = None
    executable_files: tuple[str, ...] = ()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact_digest(path: Path, expected_sha256: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ArtifactError("artifact checksum must be lowercase SHA-256")
    if sha256_file(path) != expected_sha256:
        raise ArtifactError("artifact checksum mismatch")


def _safe_member_path(name: str) -> PurePosixPath:
    value = PurePosixPath(name)
    raw_parts = name.split("/")
    if (
        not name
        or value.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or "\\" in name
        or unicodedata.normalize("NFKC", name) != name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ArtifactError("archive contains an unsafe path")
    if len(value.parts) > 32 or len(name.encode("utf-8")) > 4096:
        raise ArtifactError("archive path exceeds its limit")
    return value


def _copy_member(source: IO[bytes], destination: Path, size: int, mode: int) -> None:
    remaining = size
    with destination.open("xb") as output:
        os.chmod(destination, 0o755 if mode & 0o111 else 0o644)
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ArtifactError("archive member ended unexpectedly")
            output.write(chunk)
            remaining -= len(chunk)


def extract_verified_tar(artifact: Path, destination: Path) -> None:
    """Extract regular files/directories only; links and special nodes fail closed."""
    if destination.exists() or destination.is_symlink():
        raise ArtifactError("release staging destination already exists")
    destination.mkdir(mode=0o755, parents=False)
    member_count = 0
    expanded_bytes = 0
    observed_paths: set[str] = set()
    normalized_paths: set[str] = set()
    try:
        with tarfile.open(artifact, mode="r:*") as archive:
            for member in archive:
                member_count += 1
                expanded_bytes += max(0, member.size)
                if member_count > MAX_ARCHIVE_MEMBERS or expanded_bytes > MAX_EXPANDED_BYTES:
                    raise ArtifactError("archive exceeds extraction limits")
                relative = _safe_member_path(member.name)
                normalized = unicodedata.normalize("NFKC", member.name).casefold()
                if member.name in observed_paths or normalized in normalized_paths:
                    raise ArtifactError("archive contains a duplicate or colliding path")
                observed_paths.add(member.name)
                normalized_paths.add(normalized)
                if member.mode & (stat.S_ISUID | stat.S_ISGID | stat.S_IWOTH):
                    raise ArtifactError("archive contains an unsafe file mode")
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(mode=0o755, parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ArtifactError("archive links and special files are forbidden")
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    raise ArtifactError("archive contains a duplicate path")
                source = archive.extractfile(member)
                if source is None:
                    raise ArtifactError("archive member cannot be read")
                with source:
                    _copy_member(source, target, member.size, member.mode)
    except Exception:
        remove_verified_tree(destination)
        raise


def remove_verified_tree(root: Path) -> None:
    """Remove only a fresh, verified staging directory without following links."""
    if not root.exists() or root.is_symlink() or not root.is_dir():
        return
    for child in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        details = child.lstat()
        if stat.S_ISDIR(details.st_mode):
            child.rmdir()
        else:
            child.unlink()
    root.rmdir()


def load_manifest(release: Path) -> ReleaseManifest:
    canonical = release / RELEASE_MANIFEST_NAME
    legacy = release / LEGACY_MANIFEST_NAME
    if canonical.exists() and legacy.exists():
        raise ArtifactError("release contains conflicting manifests")
    manifest_path = canonical if canonical.exists() else legacy
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ArtifactError("release manifest is missing")
    try:
        value: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError("release manifest is invalid") from exc
    if not isinstance(value, dict):
        raise ArtifactError("release manifest schema is invalid")
    schema_version = value.get("schema_version")
    legacy_keys = {
        "schema_version",
        "version",
        "database_revision",
        "database_backward_compatible",
        "files",
    }
    version_two_keys = legacy_keys | {
        "source_commit",
        "target_platform",
        "target_architecture",
        "build_mode",
        "file_allowlist",
        "required_python",
        "platform_support",
        "artifact_authenticity",
        "sbom_filename",
        "license_filename",
        "third_party_notices_filename",
        "executable_files",
    }
    version_three_keys = version_two_keys | {
        "source_ref_kind",
        "supported_python_abis",
        "build_toolchain",
    }
    current_keys = version_three_keys | {"bootstrap_pip"}
    if (
        (schema_version == 1 and set(value) != legacy_keys)
        or (schema_version == 2 and set(value) != version_two_keys)
        or (schema_version == 3 and set(value) != version_three_keys)
        or (schema_version == 4 and set(value) != current_keys)
    ):
        raise ArtifactError("release manifest schema is invalid")
    if schema_version not in {1, 2, 3, 4}:
        raise ArtifactError("release manifest schema is invalid")
    version = value["version"]
    revision = value["database_revision"]
    compatible = value["database_backward_compatible"]
    files = value["files"]
    if (
        not valid_version(version)
        or not isinstance(revision, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", revision)
        or not isinstance(compatible, bool)
        or not isinstance(files, dict)
        or len(files) > MAX_ARCHIVE_MEMBERS
    ):
        raise ArtifactError("release manifest values are invalid")
    normalized: dict[str, str] = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ArtifactError("release file manifest is invalid")
        _safe_member_path(name)
        if name in {RELEASE_MANIFEST_NAME, LEGACY_MANIFEST_NAME} or not re.fullmatch(
            r"[0-9a-f]{64}", digest
        ):
            raise ArtifactError("release file manifest is invalid")
        normalized[name] = digest
    if schema_version == 1:
        return ReleaseManifest(version, revision, compatible, normalized)

    source_commit = value["source_commit"]
    source_ref_kind = value.get("source_ref_kind")
    target_platform = value["target_platform"]
    target_architecture = value["target_architecture"]
    build_mode = value["build_mode"]
    required_python = value["required_python"]
    supported_python_abis = value.get("supported_python_abis", [])
    build_toolchain = value.get("build_toolchain")
    bootstrap_pip = value.get("bootstrap_pip")
    platform_support = value["platform_support"]
    authenticity = value["artifact_authenticity"]
    sbom_filename = value["sbom_filename"]
    license_filename = value["license_filename"]
    notices_filename = value["third_party_notices_filename"]
    allowlist = value["file_allowlist"]
    executable_files = value["executable_files"]
    if (
        not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
        or target_platform != "linux"
        or target_architecture != "x86_64"
        or build_mode != "release-candidate"
        or required_python != (">=3.11" if schema_version == 2 else ">=3.11,<3.14")
        or authenticity != "unsigned; sha256 integrity only"
        or sbom_filename != "SBOM.spdx.json"
        or license_filename != "LICENSE"
        or notices_filename != "THIRD_PARTY_NOTICES.md"
        or not isinstance(allowlist, list)
        or allowlist != sorted(normalized)
        or not isinstance(executable_files, list)
        or executable_files != ["install.sh"]
        or not isinstance(platform_support, list)
        or not platform_support
    ):
        raise ArtifactError("release manifest values are invalid")
    if schema_version in {3, 4} and (
        source_ref_kind not in {"pull_request_head", "main", "tag", "other"}
        or supported_python_abis != ["cp311", "cp312", "cp313"]
        or not isinstance(build_toolchain, dict)
        or set(build_toolchain) != {"node", "pip", "pnpm", "setuptools", "wheel"}
        or not all(
            isinstance(name, str)
            and isinstance(version, str)
            and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", version)
            for name, version in build_toolchain.items()
        )
    ):
        raise ArtifactError("release build compatibility metadata is invalid")
    if schema_version == 4 and (
        not isinstance(bootstrap_pip, dict)
        or not isinstance(build_toolchain, dict)
        or set(bootstrap_pip) != {"filename", "version", "sha256", "method"}
        or bootstrap_pip.get("method") != "pythonpath-wheel-target"
        or bootstrap_pip.get("version") != build_toolchain.get("pip")
        or not isinstance(bootstrap_pip.get("filename"), str)
        or re.fullmatch(
            r"bootstrap/pip-[0-9]+(?:\.[0-9]+){1,2}-py3-none-any\.whl",
            bootstrap_pip["filename"],
        )
        is None
        or not isinstance(bootstrap_pip.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", bootstrap_pip["sha256"]) is None
        or normalized.get(bootstrap_pip["filename"]) != bootstrap_pip["sha256"]
    ):
        raise ArtifactError("release bootstrap pip metadata is invalid")
    expected_platform_keys = {"distribution", "release", "architecture", "qualification"}
    normalized_platforms: list[dict[str, str]] = []
    for entry in platform_support:
        if (
            not isinstance(entry, dict)
            or set(entry) != expected_platform_keys
            or not all(isinstance(item, str) and item for item in entry.values())
        ):
            raise ArtifactError("release platform support metadata is invalid")
        normalized_platforms.append(dict(entry))
    if not REQUIRED_RELEASE_PATHS.issubset(normalized):
        raise ArtifactError("release required files are missing from the manifest")
    return ReleaseManifest(
        version,
        revision,
        compatible,
        normalized,
        schema_version=schema_version,
        source_commit=source_commit,
        source_ref_kind=source_ref_kind,
        target_platform=target_platform,
        target_architecture=target_architecture,
        build_mode=build_mode,
        required_python=required_python,
        supported_python_abis=tuple(supported_python_abis),
        build_toolchain=dict(build_toolchain) if build_toolchain is not None else None,
        bootstrap_pip=dict(bootstrap_pip) if bootstrap_pip is not None else None,
        platform_support=tuple(normalized_platforms),
        artifact_authenticity=authenticity,
        sbom_filename=sbom_filename,
        license_filename=license_filename,
        third_party_notices_filename=notices_filename,
        executable_files=tuple(executable_files),
    )


def verify_release(
    release: Path,
    manifest: ReleaseManifest | None = None,
    *,
    allow_generated_venv: bool = False,
) -> ReleaseManifest:
    try:
        root_details = release.lstat()
    except OSError as exc:
        raise ArtifactError("release root is unavailable") from exc
    if stat.S_ISLNK(root_details.st_mode) or not stat.S_ISDIR(root_details.st_mode):
        raise ArtifactError("release root is unsafe")
    actual = manifest or load_manifest(release)
    observed: set[str] = set()
    observed_executables: set[str] = set()
    for path in release.rglob("*"):
        relative = path.relative_to(release).as_posix()
        if allow_generated_venv and (relative == "venv" or relative.startswith("venv/")):
            continue
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not (
            stat.S_ISDIR(details.st_mode) or stat.S_ISREG(details.st_mode)
        ):
            raise ArtifactError("release contains an unsafe filesystem object")
        if details.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_IWOTH):
            raise ArtifactError("release contains an unsafe file mode")
        if stat.S_ISREG(details.st_mode) and relative not in {
            RELEASE_MANIFEST_NAME,
            LEGACY_MANIFEST_NAME,
        }:
            observed.add(relative)
            if details.st_mode & 0o111:
                observed_executables.add(relative)
            if actual.files.get(relative) != sha256_file(path):
                raise ArtifactError("release file digest mismatch")
    if observed != set(actual.files):
        raise ArtifactError("release file set does not match its manifest")
    if actual.schema_version in {2, 3, 4}:
        if observed_executables != set(actual.executable_files):
            raise ArtifactError("release executable file set does not match its manifest")
        _verify_release_candidate_contract(release, actual)
    return actual


def _verify_release_candidate_contract(release: Path, manifest: ReleaseManifest) -> None:
    try:
        version = (release / "VERSION").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise ArtifactError("release VERSION is unavailable") from exc
    if version != manifest.version:
        raise ArtifactError("release VERSION does not match its manifest")
    wheels = sorted((release / "wheelhouse").glob("agentbox-*.whl"))
    if len(wheels) != 1 or _wheel_version(wheels[0]) != manifest.version:
        raise ArtifactError("release wheel version does not match its manifest")
    if manifest.schema_version in {3, 4}:
        observed_abis = {
            match.group(1)
            for wheel in (release / "wheelhouse").glob("*.whl")
            if (match := re.search(r"-(cp3(?:11|12|13))-", wheel.name)) is not None
        }
        if observed_abis != set(manifest.supported_python_abis):
            raise ArtifactError("release wheelhouse ABI inventory does not match its manifest")
    if manifest.schema_version == 4:
        assert manifest.bootstrap_pip is not None
        bootstrap_wheel = release / manifest.bootstrap_pip["filename"]
        if (
            bootstrap_wheel.is_symlink()
            or not bootstrap_wheel.is_file()
            or _wheel_version(bootstrap_wheel) != manifest.bootstrap_pip["version"]
        ):
            raise ArtifactError("release bootstrap pip wheel does not match its manifest")
    try:
        sbom: Any = json.loads((release / "SBOM.spdx.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError("release SBOM is invalid") from exc
    if (
        not isinstance(sbom, dict)
        or sbom.get("spdxVersion") != "SPDX-2.3"
        or sbom.get("dataLicense") != "CC0-1.0"
        or sbom.get("name") != f"AgentBox {manifest.version} SBOM"
    ):
        raise ArtifactError("release SBOM schema is invalid")
    if _migration_head(release / "migrations/versions") != manifest.database_revision:
        raise ArtifactError("release migration head does not match its manifest")


def _migration_head(versions_directory: Path) -> str:
    revisions: set[str] = set()
    predecessors: set[str] = set()
    if versions_directory.is_symlink() or not versions_directory.is_dir():
        raise ArtifactError("release migration directory is unavailable")
    for path in sorted(versions_directory.glob("*.py")):
        if path.is_symlink() or not path.is_file():
            raise ArtifactError("release migration source is unsafe")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise ArtifactError("release migration source is invalid") from exc
        values: dict[str, object] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError) as exc:
                    raise ArtifactError("release migration identity is invalid") from exc
        revision = values.get("revision")
        down_revision = values.get("down_revision")
        if not isinstance(revision, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", revision) is None:
            raise ArtifactError("release migration identity is invalid")
        revisions.add(revision)
        if down_revision is not None:
            if not isinstance(down_revision, str):
                raise ArtifactError("release migration graph is invalid")
            predecessors.add(down_revision)
    heads = revisions - predecessors
    if not revisions or not predecessors.issubset(revisions) or len(heads) != 1:
        raise ArtifactError("release migration graph is invalid")
    return heads.pop()


def _wheel_version(wheel: Path) -> str:
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ArtifactError("release wheel metadata is invalid")
            metadata = archive.read(names[0]).decode("utf-8")
    except (OSError, UnicodeError, zipfile.BadZipFile, KeyError) as exc:
        raise ArtifactError("release wheel metadata is invalid") from exc
    versions = [
        line.removeprefix("Version: ")
        for line in metadata.splitlines()
        if line.startswith("Version: ")
    ]
    if len(versions) != 1:
        raise ArtifactError("release wheel metadata is invalid")
    return versions[0]


def scan_wheel_bytes(payload: bytes, canaries: tuple[bytes, ...]) -> int:
    """Scan a nested wheel without extracting it; malformed or ambiguous ZIPs fail closed."""
    member_count = 0
    expanded_bytes = 0
    observed_paths: set[str] = set()
    normalized_paths: set[str] = set()
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.infolist():
                member_count += 1
                if member_count > MAX_WHEEL_MEMBERS:
                    raise ArtifactError("wheel exceeds its member count limit")
                canonical_name = member.filename.rstrip("/")
                _safe_member_path(canonical_name)
                normalized = unicodedata.normalize("NFKC", canonical_name).casefold()
                if canonical_name in observed_paths or normalized in normalized_paths:
                    raise ArtifactError("wheel contains a duplicate or colliding path")
                parents = PurePosixPath(canonical_name).parents
                if any(parent.as_posix() in observed_files for parent in parents):
                    raise ArtifactError("wheel contains a file/directory path collision")
                if not member.is_dir() and canonical_name in observed_directories:
                    raise ArtifactError("wheel contains a file/directory path collision")
                observed_paths.add(canonical_name)
                normalized_paths.add(normalized)
                if member.is_dir():
                    observed_directories.add(canonical_name)
                else:
                    observed_files.add(canonical_name)
                if any(canary in member.filename.encode("utf-8") for canary in canaries):
                    raise ArtifactError("wheel member name contains a release canary")
                if member.flag_bits & 0x1:
                    raise ArtifactError("encrypted wheel members are forbidden")
                if member.file_size > MAX_WHEEL_MEMBER_BYTES:
                    raise ArtifactError("wheel member exceeds its expanded size limit")
                expanded_bytes += member.file_size
                if expanded_bytes > MAX_WHEEL_EXPANDED_BYTES:
                    raise ArtifactError("wheel exceeds its expanded size limit")
                unix_mode = member.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                if file_type and not (stat.S_ISREG(unix_mode) or stat.S_ISDIR(unix_mode)):
                    raise ArtifactError("wheel links and special files are forbidden")
                if member.is_dir():
                    continue
                tail = b""
                observed_size = 0
                with archive.open(member, "r") as stream:
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        observed_size += len(chunk)
                        scan = tail + chunk
                        if any(canary in scan for canary in canaries):
                            raise ArtifactError("wheel member contains a release canary")
                        longest = max((len(canary) for canary in canaries), default=1)
                        retained = max(0, longest - 1)
                        tail = scan[-retained:] if retained else b""
                if observed_size != member.file_size:
                    raise ArtifactError("wheel member expanded size is inconsistent")
    except ArtifactError:
        raise
    except (OSError, UnicodeError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ArtifactError("wheel archive is malformed") from exc
    return member_count


def verify_release_bundle(
    artifact: Path,
    checksums: Path,
    external_manifest: Path,
    external_sbom: Path,
) -> ReleaseManifest:
    """Verify the independently published RC files and the complete archive contract."""
    expected_names = {artifact.name, external_manifest.name, external_sbom.name}
    observed: dict[str, str] = {}
    try:
        lines = checksums.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ArtifactError("SHA256SUMS is unavailable") from exc
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]{0,255})", line)
        if match is None or match.group(2) in observed:
            raise ArtifactError("SHA256SUMS format is invalid")
        observed[match.group(2)] = match.group(1)
    if set(observed) != expected_names:
        raise ArtifactError("SHA256SUMS file set is invalid")
    for path in (artifact, external_manifest, external_sbom):
        verify_artifact_digest(path, observed[path.name])
    with tempfile.TemporaryDirectory(prefix="agentbox-verify-") as temporary:
        release = Path(temporary) / "release"
        extract_verified_tar(artifact, release)
        internal_manifest = release / RELEASE_MANIFEST_NAME
        internal_sbom = release / "SBOM.spdx.json"
        if (
            internal_manifest.read_bytes() != external_manifest.read_bytes()
            or internal_sbom.read_bytes() != external_sbom.read_bytes()
        ):
            raise ArtifactError("published release metadata does not match the archive")
        manifest = verify_release(release)
        if artifact.name != f"agentbox-{manifest.version}-linux-x86_64.tar.gz":
            raise ArtifactError("release artifact filename does not match its manifest")
        return manifest
