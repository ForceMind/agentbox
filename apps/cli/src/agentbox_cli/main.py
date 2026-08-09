"""Local bootstrap and read-only control-plane CLI for Phase 3."""

from __future__ import annotations

import argparse
import getpass
import json
import secrets
import sys
from collections.abc import Sequence
from typing import Any

from agentbox_core import __version__
from agentbox_core.configuration import Settings
from agentbox_core.errors import AdminAlreadyInitialized, AgentBoxError
from agentbox_core.services import build_services


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentbox", description="AgentBox control-plane CLI")
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

    admin = subcommands.add_parser("admin")
    admin_commands = admin.add_subparsers(dest="admin_command", required=True)
    admin_init = admin_commands.add_parser("init")
    admin_init.add_argument("--username")
    admin_status = admin_commands.add_parser("status")
    admin_status.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=argparse.SUPPRESS,
    )

    secret = subcommands.add_parser("secret")
    secret_commands = secret.add_subparsers(dest="secret_command", required=True)
    secret_commands.add_parser("generate")
    return parser


def _envelope(command: str, *, ok: bool, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "command": command,
        "execution_mode": "local_read_only" if command in {"status", "doctor"} else "local",
        "ok": ok,
        "data": data,
        "error": None,
    }


def _print_result(result: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return
    data = result["data"]
    for key, value in data.items():
        print(f"{key.replace('_', ' ').title()}: {value}")


def _control_plane_status(settings: Settings) -> dict[str, Any]:
    services = build_services(settings)
    try:
        database_reachable = services.database.check_connection()
        migrations_current = services.database.migrations_current()
        admin_initialized = False
        if database_reachable and migrations_current:
            admin_initialized, _username = services.admin.status()
        return {
            "configuration": "valid",
            "environment": settings.env.value,
            "database": "reachable" if database_reachable else "unavailable",
            "migrations": "current" if migrations_current else "required",
            "admin": "initialized" if admin_initialized else "not_initialized",
        }
    finally:
        services.database.close()


def _admin_init(settings: Settings, username_argument: str | None) -> int:
    if not sys.stdin.isatty():
        print(
            "ERROR [ADMIN_INIT_TTY_REQUIRED]: admin initialization requires a local TTY",
            file=sys.stderr,
        )
        return 13

    services = build_services(settings)
    try:
        if not services.database.migrations_current():
            print(
                "ERROR [DATABASE_MIGRATION_REQUIRED]: run alembic upgrade head first",
                file=sys.stderr,
            )
            return 10
        username = username_argument or input("Administrator username: ").strip()
        password = getpass.getpass("Administrator password: ")
        confirmation = getpass.getpass("Confirm administrator password: ")
        if password != confirmation:
            print("ERROR [AUTH_PASSWORD_MISMATCH]: passwords do not match", file=sys.stderr)
            return 15
        admin = services.admin.initialize(username, password)
        print(f"AgentBox administrator initialized: {admin.username}")
        return 0
    except AdminAlreadyInitialized as exc:
        print(f"ERROR [{exc.code}]: {exc.message}", file=sys.stderr)
        return 14
    except (AgentBoxError, ValueError) as exc:
        code = exc.code if isinstance(exc, AgentBoxError) else "ADMIN_INPUT_INVALID"
        message = exc.message if isinstance(exc, AgentBoxError) else str(exc)
        print(f"ERROR [{code}]: {message}", file=sys.stderr)
        return 15
    finally:
        services.database.close()


def _admin_status(settings: Settings, json_output: bool) -> int:
    services = build_services(settings)
    try:
        if not services.database.migrations_current():
            initialized, username = False, None
        else:
            initialized, username = services.admin.status()
        result = _envelope(
            "admin.status",
            ok=True,
            data={"initialized": initialized, "username": username},
        )
        _print_result(result, json_output)
        return 0
    finally:
        services.database.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)

    if args.command == "secret":
        if getattr(args, "json_output", False):
            print(
                "ERROR [SECRET_JSON_FORBIDDEN]: secret generation is TTY/plain output only",
                file=sys.stderr,
            )
            return 13
        print(secrets.token_urlsafe(48))
        return 0

    try:
        settings = Settings()
    except Exception:
        print("ERROR [CONFIGURATION_INVALID]: AgentBox configuration is invalid", file=sys.stderr)
        return 15

    if args.command == "admin":
        if args.admin_command == "init":
            return _admin_init(settings, args.username)
        return _admin_status(settings, getattr(args, "json_output", False))

    status = _control_plane_status(settings)
    result = _envelope(args.command, ok=True, data=status)
    _print_result(result, args.json_output)
    return 0
