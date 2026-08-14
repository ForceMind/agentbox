#!/usr/bin/env python3
"""Fail closed when an RC bundle contains secrets or unsafe public files."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path

from agentbox_installer.artifact import scan_wheel_bytes, verify_release_bundle

CANARIES = (
    b"APP-SECRET-CANARY",
    b"SESSION-CANARY",
    b"CSRF-CANARY",
    b"CODEX-PAIR-CANARY",
    b"CLAUDE-OUTPUT-CANARY",
    b"GITHUB-TOKEN-CANARY",
    b"GIT-CREDENTIAL-CANARY",
    b"PROVIDER-KEY-CANARY",
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
    for public_file in (args.artifact, args.checksums, args.manifest, args.sbom):
        payload = public_file.read_bytes()
        if any(canary in payload for canary in CANARIES):
            raise SystemExit(f"release secret scan failed: {public_file.name}")
    with tarfile.open(args.artifact, "r:*") as archive:
        for member in archive:
            checked += 1
            parts = set(Path(member.name).parts)
            if parts & FORBIDDEN_MEMBER_PARTS or member.name.endswith(".map"):
                raise SystemExit(f"release contains a forbidden member: {member.name}")
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise SystemExit("release member could not be scanned")
                with stream:
                    payload = stream.read()
                if any(canary in payload for canary in CANARIES):
                    raise SystemExit(f"release secret scan failed: {member.name}")
                if member.name.endswith(".whl"):
                    wheel_members_checked += scan_wheel_bytes(payload, CANARIES)
    print(
        f"Release artifact scan passed ({checked} members, AgentBox {manifest.version}, "
        f"{wheel_members_checked} nested wheel members, {artifact_size} bytes, "
        "no source maps or canaries)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
