"""Root-only apply and read-only planning CLI for AgentBox deployment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from agentbox_installer.artifact import verify_release_bundle
from agentbox_installer.build import (
    build_release_artifact,
    build_release_bundle,
    release_version,
    verify_version_consistency,
)
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller, InstallError


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbox-install")
    parser.add_argument("--fixture-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply", "update", "resume-install"):
        command = commands.add_parser(name)
        command.add_argument("--artifact", type=Path, required=True)
        command.add_argument("--sha256", required=True)
        command.add_argument("--json", action="store_true")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--to")
    rollback.add_argument("--json", action="store_true")
    commands.add_parser("recover").add_argument("--json", action="store_true")
    uninstall = commands.add_parser("uninstall")
    uninstall.add_argument("--json", action="store_true")
    uninstall.add_argument(
        "--purge",
        action="store_true",
        help="reserved; destructive purge is intentionally unavailable",
    )
    commands.add_parser("doctor").add_argument("--json", action="store_true")
    preparation = commands.add_parser("prepare-waw-manifests")
    preparation.add_argument("--plan", action="store_true")
    preparation.add_argument("--recover", action="store_true")
    preparation.add_argument("--json", action="store_true")
    policy = commands.add_parser("prepare-waw-policies")
    policy.add_argument("--plan", action="store_true")
    policy.add_argument("--recover", action="store_true")
    policy.add_argument("--json", action="store_true")
    activation = commands.add_parser("activate-waw")
    activation.add_argument("--plan", action="store_true")
    activation.add_argument("--recover", action="store_true")
    activation.add_argument("--json", action="store_true")
    web = commands.add_parser("publish-waw-web")
    web.add_argument("--origin", required=True)
    web.add_argument("--valid-from", required=True)
    web.add_argument("--valid-until", required=True)
    web.add_argument("--plan", action="store_true")
    web.add_argument("--recover", action="store_true")
    web.add_argument("--json", action="store_true")
    for name in ("configure-waw-web", "activate-waw-web"):
        web_configuration = commands.add_parser(name)
        web_configuration.add_argument("--origin", required=True)
        web_configuration.add_argument("--plan", action="store_true")
        web_configuration.add_argument("--recover", action="store_true")
        web_configuration.add_argument("--json", action="store_true")
    certificate = commands.add_parser("provision-waw-web-certificate")
    certificate.add_argument("--origin", required=True)
    certificate.add_argument("--email", required=True)
    certificate.add_argument("--agree-acme-terms", action="store_true")
    certificate.add_argument("--plan", action="store_true")
    certificate.add_argument("--recover", action="store_true")
    certificate.add_argument("--json", action="store_true")
    maintenance = commands.add_parser("maintain-waw-web")
    maintenance.add_argument("--recover", action="store_true")
    maintenance.add_argument("--json", action="store_true")
    setup_web = commands.add_parser("setup-waw-web")
    setup_web.add_argument("--origin", required=True)
    setup_web.add_argument("--email", required=True)
    setup_web.add_argument("--agree-acme-terms", action="store_true")
    setup_web.add_argument("--plan", action="store_true")
    setup_web.add_argument("--recover", action="store_true")
    setup_web.add_argument("--json", action="store_true")
    vendors = commands.add_parser("install-waw-vendors")
    vendors.add_argument("--plan", action="store_true")
    vendors.add_argument("--recover", action="store_true")
    vendors.add_argument("--json", action="store_true")
    enrollment = commands.add_parser("enroll-waw-vendors")
    enrollment.add_argument("--claude-version", required=True)
    enrollment.add_argument("--codex-version", required=True)
    enrollment.add_argument("--codex-unauthenticated-output-sha256", required=True)
    enrollment.add_argument("--plan", action="store_true")
    enrollment.add_argument("--recover", action="store_true")
    enrollment.add_argument("--json", action="store_true")
    build = commands.add_parser("build-artifact")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--version")
    build.add_argument("--python", type=Path, default=Path(sys.executable))
    candidate = commands.add_parser("build-release-candidate")
    candidate.add_argument("--source", type=Path, required=True)
    candidate.add_argument("--output-dir", type=Path, required=True)
    candidate.add_argument("--python", type=Path, default=Path(sys.executable))
    candidate.add_argument(
        "--source-ref-kind",
        choices=("pull_request_head", "main", "tag", "other"),
        default="other",
    )
    verify = commands.add_parser("verify-artifact")
    verify.add_argument("--artifact", type=Path, required=True)
    verify.add_argument("--checksums", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--sbom", type=Path, required=True)
    version = commands.add_parser("verify-version")
    version.add_argument("--source", type=Path, required=True)
    return parser


def _layout(fixture_root: Path | None) -> tuple[InstallLayout, HostOperations]:
    if fixture_root is None:
        return InstallLayout(), HostOperations(real_host=True)
    if os.environ.get("AGENTBOX_INSTALLER_TEST_MODE") != "1":
        raise InstallError("fixture root is available only in explicit test mode")
    root = fixture_root.resolve()
    if root == Path("/") or len(root.parts) < 3:
        raise InstallError("fixture root is unsafe")
    return InstallLayout(root), HostOperations(real_host=False)


def _print(value: object, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(value, separators=(",", ":"), sort_keys=True, default=str))
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key.replace('_', ' ').title()}: {item}")
    else:
        print(value)


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build-artifact":
            version = args.version or release_version(args.source)
            digest = build_release_artifact(
                args.source, args.output, version=version, python=args.python
            )
            print(f"Artifact: {args.output}")
            print(f"SHA256: {digest}")
            return 0
        if args.command == "build-release-candidate":
            bundle = build_release_bundle(
                args.source,
                args.output_dir,
                python=args.python,
                source_ref_kind=args.source_ref_kind,
            )
            print(f"Version: {bundle.version}")
            print(f"Source commit: {bundle.source_commit}")
            print(f"Source ref kind: {bundle.source_ref_kind}")
            print(f"Artifact: {bundle.artifact}")
            print(f"SHA256: {bundle.artifact_sha256}")
            print(f"Manifest: {bundle.manifest}")
            print(f"SBOM: {bundle.sbom}")
            print(f"Checksums: {bundle.checksums}")
            return 0
        if args.command == "verify-artifact":
            manifest = verify_release_bundle(
                args.artifact, args.checksums, args.manifest, args.sbom
            )
            print(f"Artifact verified: AgentBox {manifest.version} linux x86_64")
            print("Integrity: SHA-256 verified")
            print("Artifact signature: not available")
            return 0
        if args.command == "verify-version":
            print(verify_version_consistency(args.source))
            return 0
        layout, host = _layout(args.fixture_root)
        installer = AgentBoxInstaller(layout, host)
        json_output = bool(getattr(args, "json", False))
        if args.command == "prepare-waw-manifests":
            _print(
                asdict(installer.prepare_waw_manifests(recover=args.recover, plan=args.plan)),
                json_output=json_output,
            )
            return 0
        if args.command == "prepare-waw-policies":
            _print(
                installer.prepare_waw_policies(plan=args.plan, recover=args.recover),
                json_output=json_output,
            )
            return 0
        if args.command == "publish-waw-web":
            _print(
                installer.publish_waw_web(
                    origin=args.origin,
                    valid_from=datetime.fromisoformat(args.valid_from),
                    valid_until=datetime.fromisoformat(args.valid_until),
                    plan=args.plan,
                    recover=args.recover,
                ),
                json_output=json_output,
            )
            return 0
        if args.command in {"configure-waw-web", "activate-waw-web"}:
            _print(
                installer.configure_waw_web(
                    origin=args.origin,
                    plan=args.plan,
                    recover=args.recover,
                    activate=args.command == "activate-waw-web",
                ),
                json_output=json_output,
            )
            return 0
        if args.command == "provision-waw-web-certificate":
            _print(
                installer.provision_waw_web_certificate(
                    origin=args.origin,
                    email=args.email,
                    agree_terms=args.agree_acme_terms,
                    plan=args.plan,
                    recover=args.recover,
                ),
                json_output=json_output,
            )
            return 0
        if args.command == "maintain-waw-web":
            _print(installer.maintain_waw_web(recover=args.recover), json_output=json_output)
            return 0
        if args.command == "setup-waw-web":
            _print(
                installer.setup_waw_web(
                    origin=args.origin,
                    email=args.email,
                    agree_terms=args.agree_acme_terms,
                    plan=args.plan,
                    recover=args.recover,
                ),
                json_output=json_output,
            )
            return 0
        if args.command == "install-waw-vendors":
            _print(
                installer.install_waw_vendors(plan=args.plan, recover=args.recover),
                json_output=json_output,
            )
            return 0
        if args.command == "activate-waw":
            _print(
                installer.activate_waw(plan=args.plan, recover=args.recover),
                json_output=json_output,
            )
            return 0
        if args.command == "enroll-waw-vendors":
            enrollment_result = installer.enroll_waw_vendors(
                claude_version=args.claude_version,
                codex_version=args.codex_version,
                codex_unauthenticated_output_sha256=args.codex_unauthenticated_output_sha256,
                recover=args.recover,
                plan=args.plan,
            )
            _print(asdict(enrollment_result), json_output=json_output)
            return 0
        if args.command == "plan":
            _print(installer.plan(args.artifact, args.sha256).to_dict(), json_output=json_output)
            return 0
        if args.command in {"apply", "update", "resume-install"}:
            result = (
                installer.resume_install(args.artifact, args.sha256)
                if args.command == "resume-install"
                else installer.apply(args.artifact, args.sha256)
            )
            _print(result.__dict__, json_output=json_output)
            return 0
        if args.command == "rollback":
            result = installer.rollback(args.to)
            _print(result.__dict__, json_output=json_output)
            return 0
        if args.command == "recover":
            result = installer.recover()
            _print(result.__dict__, json_output=json_output)
            return 0
        if args.command == "uninstall":
            if args.purge:
                raise InstallError("--purge is not implemented; persistent data is preserved")
            _print(installer.uninstall(), json_output=json_output)
            return 0
        _print(
            {
                "installation": installer.installation_state(),
                "version": installer.current_version() or "unavailable",
                "health": "ready" if installer.health_check() else "not_ready",
            },
            json_output=json_output,
        )
        return 0
    except (InstallError, RuntimeError, ValueError) as exc:
        print(f"ERROR [INSTALLATION_FAILED]: {exc}", file=sys.stderr)
        return 17


if __name__ == "__main__":
    raise SystemExit(main())
