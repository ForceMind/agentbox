"""Minimal, non-mutating AgentBox command-line interface."""

import argparse
import json
from collections.abc import Sequence
from typing import Any

from agentbox_core import __version__


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbox", description="AgentBox engineering skeleton")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--json", dest="json_output", action="store_true")

    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "doctor"):
        subcommand = subcommands.add_parser(command)
        subcommand.add_argument(
            "--json",
            dest="json_output",
            action="store_true",
            default=argparse.SUPPRESS,
        )

    return parser


def placeholder_result(command: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "command": command,
        "ok": True,
        "data": {
            "status": "not_implemented",
            "message": "Not implemented in Phase 2",
        },
        "error": None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    result = placeholder_result(args.command)

    if args.json_output:
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    else:
        print(f"AgentBox {args.command}: Not implemented in Phase 2")
    return 0
