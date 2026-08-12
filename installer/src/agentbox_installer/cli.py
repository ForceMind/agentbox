"""Root-only apply and read-only planning CLI for AgentBox deployment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from agentbox_installer.build import build_release_artifact
from agentbox_installer.host import HostOperations
from agentbox_installer.layout import InstallLayout
from agentbox_installer.lifecycle import AgentBoxInstaller, InstallError


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbox-install")
    parser.add_argument("--fixture-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply", "update"):
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
    build = commands.add_parser("build-artifact")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--python", type=Path, default=Path(sys.executable))
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
            digest = build_release_artifact(
                args.source, args.output, version=args.version, python=args.python
            )
            print(f"Artifact: {args.output}")
            print(f"SHA256: {digest}")
            return 0
        layout, host = _layout(args.fixture_root)
        installer = AgentBoxInstaller(layout, host)
        json_output = bool(getattr(args, "json", False))
        if args.command == "plan":
            _print(installer.plan(args.artifact, args.sha256).to_dict(), json_output=json_output)
            return 0
        if args.command in {"apply", "update"}:
            result = installer.apply(args.artifact, args.sha256)
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
