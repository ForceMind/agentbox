#!/usr/bin/env python3
"""Rehearse WAW native-source and Python wheel provenance from one RC artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from agentbox_installer.artifact import (
    ArtifactError,
    ReleaseManifest,
    extract_verified_tar,
    verify_release_bundle,
)

AGENTBOX_MODULES = (
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
NATIVE_BUILD_SCRIPT = "scripts/build-waw-native.py"
NATIVE_CHECK_SCRIPT = "scripts/check-waw-native.py"
SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".m", ".mm", ".s", ".S")
PATH_ARGUMENTS = ("-I", "-iquote", "-isystem", "-idirafter", "-include", "-imacros")
JOINED_PATH_ARGUMENTS = (
    "-isysroot",
    "-iquote",
    "-isystem",
    "-idirafter",
    "-include",
    "-imacros",
    "-I",
)


class RehearsalError(RuntimeError):
    """A fail-closed error whose message names only a reviewed evidence surface."""

    def __init__(self, surface: str) -> None:
        self.surface = surface
        super().__init__(surface)


def _run(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str],
    surface: str,
    timeout: int = 300,
) -> str:
    try:
        completed = subprocess.run(  # noqa: S603 - every caller supplies a fixed rehearsal argv
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=timeout,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RehearsalError(surface) from exc
    if completed.returncode != 0:
        raise RehearsalError(surface)
    return completed.stdout


def _confined(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_argument_path(value: str, cwd: Path) -> Path:
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else cwd / candidate).resolve()


def _compiler_path_arguments(argv: list[str], cwd: Path) -> tuple[set[Path], set[Path], set[Path]]:
    sources: set[Path] = set()
    includes: set[Path] = set()
    outputs: set[Path] = set()
    index = 0
    while index < len(argv):
        value = argv[index]
        if value.startswith("@"):
            raise RehearsalError("native compiler provenance")
        if value in PATH_ARGUMENTS or value in {"-isysroot", "--sysroot", "-o"}:
            index += 1
            if index >= len(argv):
                raise RehearsalError("native compiler provenance")
            path = _resolve_argument_path(argv[index], cwd)
            if value == "-o":
                outputs.add(path)
            else:
                includes.add(path)
        elif value.startswith("--sysroot="):
            includes.add(_resolve_argument_path(value.split("=", 1)[1], cwd))
        else:
            joined = next(
                (
                    prefix
                    for prefix in JOINED_PATH_ARGUMENTS
                    if value.startswith(prefix) and value != prefix
                ),
                None,
            )
            if joined is not None:
                includes.add(_resolve_argument_path(value.removeprefix(joined), cwd))
            elif not value.startswith("-") and value.endswith(SOURCE_SUFFIXES):
                sources.add(_resolve_argument_path(value, cwd))
        index += 1
    return sources, includes, outputs


def verify_compiler_provenance(records: list[list[str]], release: Path) -> None:
    """Require all explicit compiler inputs and outputs to remain in the unpacked release."""

    release_root = release.resolve()
    expected_source_root = (release_root / "native/waw/src").resolve()
    expected_include_roots = {
        (release_root / "native/waw/src").resolve(),
        (release_root / "native/waw/include").resolve(),
    }
    expected_native_sources = {
        path.resolve() for path in (release_root / "native/waw/src").glob("*.c")
    }
    if not records or not expected_native_sources:
        raise RehearsalError("native compiler provenance")

    observed_sources: set[Path] = set()
    observed_includes: set[Path] = set()
    for record in records:
        if not record or not all(isinstance(value, str) and value for value in record):
            raise RehearsalError("native compiler provenance")
        sources, includes, outputs = _compiler_path_arguments(record, release_root)
        if not sources or not outputs:
            raise RehearsalError("native compiler provenance")
        if any(not _confined(path, release_root) for path in sources | includes | outputs):
            raise RehearsalError("native compiler provenance")
        observed_sources.update(sources)
        observed_includes.update(includes)

    observed_native_sources = {
        path for path in observed_sources if _confined(path, expected_source_root)
    }
    if observed_native_sources != expected_native_sources:
        raise RehearsalError("native compiler provenance")
    if not expected_include_roots.issubset(observed_includes):
        raise RehearsalError("native compiler provenance")


def _write_compiler_proxy(work: Path, compiler: Path) -> tuple[Path, Path]:
    log = work / "compiler-argv.jsonl"
    driver = work / "compiler-proxy.py"
    driver.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"LOG = Path({str(log)!r})\n"
        f"COMPILER = {str(compiler)!r}\n"
        "with LOG.open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "os.execv(COMPILER, [COMPILER, *sys.argv[1:]])\n",
        encoding="utf-8",
    )
    proxy = work / "cc"
    proxy.write_text(
        "#!/bin/sh\n" f'exec {shlex.quote(sys.executable)} {shlex.quote(str(driver))} "$@"\n',
        encoding="utf-8",
    )
    proxy.chmod(0o700)
    return proxy, log


def _read_compiler_records(log: Path) -> list[list[str]]:
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
        values: list[Any] = [json.loads(line) for line in lines]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RehearsalError("native compiler provenance") from exc
    if not all(
        isinstance(value, list) and all(isinstance(item, str) for item in value) for value in values
    ):
        raise RehearsalError("native compiler provenance")
    return [[str(item) for item in value] for value in values]


def rehearse_native(release: Path, compiler_name: str) -> None:
    build = release / NATIVE_BUILD_SCRIPT
    check = release / NATIVE_CHECK_SCRIPT
    if any(path.is_symlink() or not path.is_file() for path in (build, check)):
        raise RehearsalError("unpacked native scripts")
    compiler_value = shutil.which(compiler_name)
    if compiler_value is None:
        raise RehearsalError("native compiler")
    compiler = Path(compiler_value).resolve()

    work = release / ".artifact-rehearsal-work"
    try:
        work.mkdir(mode=0o700)
        native_temp = work / "tmp"
        native_temp.mkdir(mode=0o700)
        home = work / "home"
        home.mkdir(mode=0o700)
    except OSError as exc:
        raise RehearsalError("native workspace") from exc
    output = work / "bin"
    proxy, log = _write_compiler_proxy(work, compiler)
    native_env = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "TMPDIR": str(native_temp),
    }
    _run(
        (
            sys.executable,
            str(build),
            "--output",
            str(output),
            "--cc",
            str(proxy),
            "--verbose",
        ),
        cwd=release,
        env=native_env,
        surface="unpacked native build",
    )
    _run(
        (
            sys.executable,
            str(check),
            "--binary-dir",
            str(output),
            "--no-build",
            "--cc",
            str(proxy),
        ),
        cwd=release,
        env=native_env,
        surface="unpacked native check",
    )
    verify_compiler_provenance(_read_compiler_records(log), release)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pip_report(report: Path, release: Path, manifest: ReleaseManifest) -> None:
    """Bind every newly installed distribution to a manifest-hashed artifact wheel."""

    try:
        value: Any = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RehearsalError("wheelhouse install provenance") from exc
    installed = value.get("install") if isinstance(value, dict) else None
    if not isinstance(installed, list) or not installed:
        raise RehearsalError("wheelhouse install provenance")

    release_root = release.resolve()
    wheelhouse = (release_root / "wheelhouse").resolve()
    agentbox_versions: list[str] = []
    observed_wheels: set[Path] = set()
    for item in installed:
        if not isinstance(item, dict):
            raise RehearsalError("wheelhouse install provenance")
        metadata = item.get("metadata")
        download = item.get("download_info")
        if not isinstance(metadata, dict) or not isinstance(download, dict):
            raise RehearsalError("wheelhouse install provenance")
        name = metadata.get("name")
        version = metadata.get("version")
        url = download.get("url")
        archive_info = download.get("archive_info")
        if (
            not isinstance(name, str)
            or not isinstance(version, str)
            or not isinstance(url, str)
            or not isinstance(archive_info, dict)
        ):
            raise RehearsalError("wheelhouse install provenance")
        parsed = urlparse(url)
        if (
            parsed.scheme != "file"
            or parsed.netloc not in {"", "localhost"}
            or parsed.query
            or parsed.fragment
        ):
            raise RehearsalError("wheelhouse install provenance")
        wheel = Path(unquote(parsed.path)).resolve()
        if (
            wheel in observed_wheels
            or not _confined(wheel, wheelhouse)
            or wheel.suffix != ".whl"
            or wheel.is_symlink()
            or not wheel.is_file()
        ):
            raise RehearsalError("wheelhouse install provenance")
        observed_wheels.add(wheel)
        relative = wheel.relative_to(release_root).as_posix()
        expected_digest = manifest.files.get(relative)
        hashes = archive_info.get("hashes")
        if (
            expected_digest is None
            or not isinstance(hashes, dict)
            or hashes.get("sha256") != expected_digest
            or _sha256(wheel) != expected_digest
        ):
            raise RehearsalError("wheelhouse install provenance")
        if re.sub(r"[-_.]+", "-", name).casefold() == "agentbox":
            agentbox_versions.append(version)
    if agentbox_versions != [manifest.version]:
        raise RehearsalError("wheelhouse install provenance")


PROBE = r"""
from __future__ import annotations
import importlib
import importlib.metadata
import json
import sys
from pathlib import Path

venv = Path(sys.argv[1]).resolve()
manifest = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
modules = json.loads(sys.argv[3])
observed = {}
for name in modules:
    module = importlib.import_module(name)
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None)
    if not isinstance(origin, str):
        raise RuntimeError("module origin unavailable")
    path = Path(origin).resolve()
    if not path.is_relative_to(venv):
        raise RuntimeError("module origin escaped venv")
    observed[name] = str(path)
distribution = importlib.metadata.distribution("agentbox")
distribution_root = Path(distribution.locate_file("")).resolve()
if not distribution_root.is_relative_to(venv):
    raise RuntimeError("distribution escaped venv")
print(json.dumps({
    "distribution_root": str(distribution_root),
    "distribution_version": distribution.version,
    "manifest_source_commit": manifest.get("source_commit"),
    "manifest_source_ref_kind": manifest.get("source_ref_kind"),
    "manifest_version": manifest.get("version"),
    "modules": observed,
}, sort_keys=True))
""".strip()


def verify_isolated_imports(output: str, venv: Path, manifest: ReleaseManifest) -> None:
    try:
        value: Any = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RehearsalError("isolated import provenance") from exc
    if not isinstance(value, dict):
        raise RehearsalError("isolated import provenance")
    modules = value.get("modules")
    if not isinstance(modules, dict) or set(modules) != set(AGENTBOX_MODULES):
        raise RehearsalError("isolated import provenance")
    venv_root = venv.resolve()
    paths = [value.get("distribution_root"), *modules.values()]
    if any(
        not isinstance(path, str) or not _confined(Path(path).resolve(), venv_root)
        for path in paths
    ):
        raise RehearsalError("isolated import provenance")
    if (
        value.get("distribution_version") != manifest.version
        or value.get("manifest_version") != manifest.version
        or value.get("manifest_source_commit") != manifest.source_commit
        or value.get("manifest_source_ref_kind") != manifest.source_ref_kind
    ):
        raise RehearsalError("isolated import provenance")


def rehearse_wheelhouse(release: Path, root: Path, manifest: ReleaseManifest) -> None:
    wheelhouse = release / "wheelhouse"
    if wheelhouse.is_symlink() or not wheelhouse.is_dir():
        raise RehearsalError("artifact wheelhouse")
    venv = root / "venv"
    home = root / "home"
    home.mkdir(mode=0o700)
    neutral_config = root / "empty-pip.conf"
    neutral_config.write_text("", encoding="ascii")
    base_env = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONNOUSERSITE": "1",
    }
    _run(
        (sys.executable, "-I", "-m", "venv", str(venv)),
        cwd=root,
        env=base_env,
        surface="fresh virtual environment",
    )
    python = venv / "bin/python"
    if not python.exists():
        raise RehearsalError("fresh virtual environment")
    report = root / "pip-report.json"
    pip_env = {
        **base_env,
        "PATH": f"{venv / 'bin'}{os.pathsep}{os.defpath}",
        "PIP_CONFIG_FILE": str(neutral_config),
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INDEX": "1",
    }
    _run(
        (
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--isolated",
            "--no-index",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--find-links",
            str(wheelhouse),
            "--report",
            str(report),
            f"agentbox=={manifest.version}",
        ),
        cwd=root,
        env=pip_env,
        surface="artifact wheelhouse install",
    )
    verify_pip_report(report, release, manifest)
    probe_output = _run(
        (
            str(python),
            "-I",
            "-c",
            PROBE,
            str(venv),
            str(release / "RELEASE_MANIFEST.json"),
            json.dumps(AGENTBOX_MODULES),
        ),
        cwd=root,
        env=pip_env,
        surface="isolated agentbox imports",
    )
    verify_isolated_imports(probe_output, venv, manifest)


def verify_release_provenance(
    release: Path,
    manifest: ReleaseManifest,
    expected_source_commit: str,
    expected_source_ref_kind: str,
) -> None:
    if (
        re.fullmatch(r"[0-9a-f]{40}", expected_source_commit) is None
        or manifest.source_commit != expected_source_commit
        or manifest.source_ref_kind != expected_source_ref_kind
    ):
        raise RehearsalError("release source provenance")
    try:
        sbom: Any = json.loads((release / "SBOM.spdx.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RehearsalError("release source provenance") from exc
    packages = sbom.get("packages") if isinstance(sbom, dict) else None
    if not isinstance(packages, list):
        raise RehearsalError("release source provenance")
    agentbox = [
        item for item in packages if isinstance(item, dict) and item.get("name") == "agentbox"
    ]
    if len(agentbox) != 1 or (
        agentbox[0].get("versionInfo") != manifest.version
        or agentbox[0].get("downloadLocation")
        != f"https://github.com/ForceMind/agentbox/tree/{expected_source_commit}"
    ):
        raise RehearsalError("release source provenance")


def rehearse(arguments: argparse.Namespace) -> ReleaseManifest:
    try:
        manifest = verify_release_bundle(
            arguments.artifact,
            arguments.checksums,
            arguments.manifest,
            arguments.sbom,
        )
    except (ArtifactError, OSError) as exc:
        raise RehearsalError("public artifact verification") from exc
    with tempfile.TemporaryDirectory(prefix="agentbox-waw-artifact-") as temporary:
        root = Path(temporary)
        release = root / "release"
        try:
            extract_verified_tar(arguments.artifact, release)
        except (ArtifactError, OSError) as exc:
            raise RehearsalError("safe artifact unpack") from exc
        verify_release_provenance(
            release,
            manifest,
            arguments.expected_source_commit,
            arguments.expected_source_ref_kind,
        )
        if not arguments.skip_native:
            rehearse_native(release, arguments.cc)
        rehearse_wheelhouse(release, root, manifest)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument(
        "--expected-source-ref-kind",
        choices=("pull_request_head", "main", "tag", "other"),
        required=True,
    )
    parser.add_argument("--cc", default="cc")
    parser.add_argument(
        "--skip-native",
        action="store_true",
        help="run the wheelhouse-only import matrix; native provenance remains required elsewhere",
    )
    return parser


def main() -> int:
    parser = _parser()
    arguments = parser.parse_args()
    try:
        manifest = rehearse(arguments)
    except RehearsalError as exc:
        parser.exit(1, f"artifact rehearsal failed: {exc.surface}\n")
    except Exception:
        parser.exit(1, "artifact rehearsal failed: internal execution\n")
    print(
        f"Artifact WAW provenance passed (AgentBox {manifest.version}, "
        f"{len(AGENTBOX_MODULES)} isolated package modules)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
