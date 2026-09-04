#!/usr/bin/env python3
"""Fail closed when an RC bundle contains secrets or unsafe public files."""

from __future__ import annotations

import argparse
import io
import tarfile
import zipfile
from pathlib import Path

from agentbox_installer.artifact import scan_wheel_bytes, verify_release_bundle
from agentbox_installer.build import RELEASE_NATIVE_BUILD_SCRIPTS, RELEASE_NATIVE_SOURCE_FILES

CANARIES = (
    b"APP-SECRET-CANARY",
    b"SESSION-CANARY",
    b"CSRF-CANARY",
    b"CODEX-PAIR-CANARY",
    b"CLAUDE-OUTPUT-CANARY",
    b"GITHUB-TOKEN-CANARY",
    b"GIT-CREDENTIAL-CANARY",
    b"PROVIDER-KEY-CANARY",
    b"PROVIDER-SECRET-FOUNDATION-CANARY",
    b"SSH-KEY-CANARY",
)
FORBIDDEN_MEMBER_PARTS = {
    ".git",
    ".agentbox-dev",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "playwright-report",
    "test-results",
    "venv",
    ".venv",
}
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
WAW_INERT_WHEEL_ASSETS = {
    "agentbox_runtime/assets/waw-inert/README.md",
    "agentbox_runtime/assets/waw-inert/tmux.conf",
    "agentbox_runtime/assets/waw-inert/sandbox-policies.v1.json",
    "agentbox_runtime/assets/waw-inert/claude/managed-settings.json",
    "agentbox_runtime/assets/waw-inert/codex/requirements.toml",
    "agentbox_runtime/assets/waw-inert/codex/managed_config.toml",
    "agentbox_runtime/assets/waw-inert/codex/policy-bundle.v1.json",
}


def verify_waw_release_inventory(
    native_members: set[str], native_scripts: set[str], wheel_assets: set[str]
) -> None:
    """Require the release's WAW review inputs to be one exact closed set."""

    if native_members != set(RELEASE_NATIVE_SOURCE_FILES):
        raise ValueError("release native WAW source inventory mismatch")
    if native_scripts != set(RELEASE_NATIVE_BUILD_SCRIPTS):
        raise ValueError("release native WAW build-script inventory mismatch")
    if wheel_assets != WAW_INERT_WHEEL_ASSETS:
        raise ValueError("release wheel WAW inert-asset inventory mismatch")


def collect_waw_release_source_inventory(
    members: list[tarfile.TarInfo],
) -> tuple[set[str], set[str]]:
    """Collect every regular native/script member through the real tar path."""

    native_members: set[str] = set()
    native_scripts: set[str] = set()
    for member in members:
        if not member.isfile():
            continue
        relative_name = member.name.removeprefix("./")
        if relative_name.startswith("native/waw/"):
            native_members.add(relative_name)
        if relative_name.startswith("scripts/"):
            native_scripts.add(relative_name)
    return native_members, native_scripts


def collect_agentbox_waw_assets(
    member_name: str,
    payload: bytes,
    *,
    agentbox_wheel_member: str,
    wheel_assets: set[str],
) -> None:
    """Collect inert assets only from the manifest-identified AgentBox wheel."""

    if member_name != agentbox_wheel_member:
        return
    with zipfile.ZipFile(io.BytesIO(payload)) as wheel:
        wheel_assets.update(
            name
            for name in wheel.namelist()
            if name.startswith("agentbox_runtime/assets/waw-inert/") and not name.endswith("/")
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-source-ref-kind")
    args = parser.parse_args()

    artifact_size = args.artifact.stat().st_size
    if artifact_size > MAX_ARTIFACT_BYTES:
        raise SystemExit(
            f"release artifact exceeds the {MAX_ARTIFACT_BYTES // (1024 * 1024)} MiB limit"
        )
    manifest = verify_release_bundle(args.artifact, args.checksums, args.manifest, args.sbom)
    if args.expected_source_commit is not None and (
        manifest.source_commit != args.expected_source_commit
    ):
        raise SystemExit("release provenance source commit mismatch")
    if args.expected_source_ref_kind is not None and (
        manifest.source_ref_kind != args.expected_source_ref_kind
    ):
        raise SystemExit("release provenance ref kind mismatch")
    checked = 0
    wheel_members_checked = 0
    wheel_assets: set[str] = set()
    agentbox_wheel_members = {
        name
        for name in manifest.files
        if Path(name).parent.as_posix() == "wheelhouse"
        and Path(name).name.startswith("agentbox-")
        and name.endswith(".whl")
    }
    if len(agentbox_wheel_members) != 1:
        raise SystemExit("release AgentBox wheel inventory is ambiguous")
    agentbox_wheel_member = agentbox_wheel_members.pop()
    for public_file in (args.artifact, args.checksums, args.manifest, args.sbom):
        payload = public_file.read_bytes()
        if any(canary in payload for canary in CANARIES):
            raise SystemExit(f"release secret scan failed: {public_file.name}")
    with tarfile.open(args.artifact, "r:*") as archive:
        members = archive.getmembers()
        native_members, native_scripts = collect_waw_release_source_inventory(members)
        for member in members:
            checked += 1
            parts = set(Path(member.name).parts)
            if parts & FORBIDDEN_MEMBER_PARTS or member.name.endswith(".map"):
                raise SystemExit(f"release contains a forbidden member: {member.name}")
            if member.isfile():
                relative_name = member.name.removeprefix("./")
                stream = archive.extractfile(member)
                if stream is None:
                    raise SystemExit("release member could not be scanned")
                with stream:
                    payload = stream.read()
                if any(canary in payload for canary in CANARIES):
                    raise SystemExit(f"release secret scan failed: {member.name}")
                if member.name.endswith(".whl"):
                    wheel_members_checked += scan_wheel_bytes(payload, CANARIES)
                    collect_agentbox_waw_assets(
                        relative_name,
                        payload,
                        agentbox_wheel_member=agentbox_wheel_member,
                        wheel_assets=wheel_assets,
                    )
    try:
        verify_waw_release_inventory(native_members, native_scripts, wheel_assets)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"Release artifact scan passed ({checked} members, AgentBox {manifest.version}, "
        f"{wheel_members_checked} nested wheel members, {artifact_size} bytes, "
        "no source maps or canaries)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
