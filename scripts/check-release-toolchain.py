#!/usr/bin/env python3
"""Verify the reviewed, hash-locked Release Candidate build environment."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import subprocess
import tomllib
from pathlib import Path

from agentbox_installer.build import release_build_toolchain

LOCK_LINE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([0-9A-Za-z][0-9A-Za-z.+-]*) " r"--hash=sha256:([0-9a-f]{64})"
)
REQUIRED_BUILD_PACKAGES = {
    "black",
    "httpx",
    "mypy",
    "pip",
    "pip-audit",
    "pre-commit",
    "pytest",
    "ruff",
    "setuptools",
    "wheel",
}


def _canonical(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _locked_versions(source: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in (
        (source / "requirements-release-build.lock").read_text(encoding="utf-8").splitlines()
    ):
        if not line or line.startswith("#"):
            continue
        match = LOCK_LINE.fullmatch(line)
        if match is None:
            raise RuntimeError("release build lock contains an unpinned or unhashed entry")
        name = _canonical(match.group(1))
        if name in versions:
            raise RuntimeError("release build lock contains a duplicate package")
        versions[name] = match.group(2)
    if len(versions) < 50 or not REQUIRED_BUILD_PACKAGES.issubset(versions):
        raise RuntimeError("release build lock is incomplete")
    return versions


def _command_version(argv: tuple[str, ...]) -> str:
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    match = re.search(r"[0-9]+(?:\.[0-9]+){1,2}", result.stdout)
    if match is None:
        raise RuntimeError("release build tool version is unavailable")
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--check-installed", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    versions = _locked_versions(source)
    workflow = (source / ".github/workflows/release-candidate.yml").read_text(encoding="utf-8")
    forbidden = ("pip install --upgrade", ".[dev]", "node-version: 22\n", " wheel\n")
    if any(value in workflow for value in forbidden):
        raise RuntimeError("release workflow contains an unpinned tool installation")
    required_workflow = (
        "--require-hashes",
        "--only-binary=:all:",
        "requirements-release-build.lock",
        "--no-deps --no-build-isolation --editable .",
        'node-version: "22.23.2"',
        "version: 11.20.0",
    )
    if not all(value in workflow for value in required_workflow):
        raise RuntimeError("release workflow does not enforce the reviewed toolchain lock")
    pyproject = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    build_requirements = pyproject.get("build-system", {}).get("requires")
    if build_requirements != ["setuptools>=83"] or versions["setuptools"] < "83.0.0":
        raise RuntimeError("pyproject build requirements conflict with the release lock")
    expected = release_build_toolchain(source)
    if args.check_installed:
        for name, version in versions.items():
            if importlib.metadata.version(name) != version:
                raise RuntimeError(f"installed release build tool drifted: {name}")
        observed = {
            "node": _command_version(("node", "--version")),
            "pip": importlib.metadata.version("pip"),
            "pnpm": _command_version(("pnpm", "--version")),
            "setuptools": importlib.metadata.version("setuptools"),
            "wheel": importlib.metadata.version("wheel"),
        }
        if observed != expected:
            raise RuntimeError("installed artifact-affecting toolchain differs from its lock")
    print(f"Release build toolchain lock verified ({len(versions)} packages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
