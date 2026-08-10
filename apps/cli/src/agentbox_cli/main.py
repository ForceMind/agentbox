"""AgentBox local bootstrap, diagnostics, and typed Runtime CLI."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import secrets
import shutil
import sys
from collections.abc import Sequence
from typing import Any

from agentbox_core import __version__
from agentbox_core.configuration import Settings
from agentbox_core.errors import AdminAlreadyInitialized, AgentBoxError
from agentbox_core.projects import repository_name_from_url, validate_repository_url
from agentbox_core.services import build_services
from agentbox_runtime import (
    CodexAdapter,
    RuntimeOperationError,
    UnixClaudeRuntimeClient,
    UnixCodexRuntimeClient,
    UnixProjectRuntimeClient,
    validate_branch_name,
)


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

    codex = subcommands.add_parser("codex")
    codex_commands = codex.add_subparsers(dest="codex_command", required=True)
    codex_status = codex_commands.add_parser("status")
    codex_status.add_argument(
        "--json", dest="json_output", action="store_true", default=argparse.SUPPRESS
    )
    codex_commands.add_parser("start")
    codex_commands.add_parser("stop")
    codex_commands.add_parser("pair")

    claude = subcommands.add_parser("claude")
    claude_commands = claude.add_subparsers(dest="claude_command", required=True)
    for command in ("status", "list"):
        subcommand = claude_commands.add_parser(command)
        subcommand.add_argument(
            "--json",
            dest="json_output",
            action="store_true",
            default=argparse.SUPPRESS,
        )
    for command in ("start", "stop", "attach", "output"):
        subcommand = claude_commands.add_parser(command)
        subcommand.add_argument("project")

    project = subcommands.add_parser("project")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    for command in ("list",):
        subcommand = project_commands.add_parser(command)
        subcommand.add_argument(
            "--json", dest="json_output", action="store_true", default=argparse.SUPPRESS
        )
    create = project_commands.add_parser("create")
    create.add_argument("name")
    create.add_argument("--slug")
    clone = project_commands.add_parser("clone")
    clone.add_argument("url")
    clone.add_argument("--name")
    clone.add_argument("--slug")
    for command in ("status", "pull", "push"):
        subcommand = project_commands.add_parser(command)
        subcommand.add_argument("project")
    branch = project_commands.add_parser("branch")
    branch_commands = branch.add_subparsers(dest="branch_command", required=True)
    branch_list = branch_commands.add_parser("list")
    branch_list.add_argument("project")
    for command in ("create", "switch"):
        subcommand = branch_commands.add_parser(command)
        subcommand.add_argument("project")
        subcommand.add_argument("branch")

    github = subcommands.add_parser("github")
    github_commands = github.add_subparsers(dest="github_command", required=True)
    github_commands.add_parser("status")
    pr = github_commands.add_parser("pr")
    pr_commands = pr.add_subparsers(dest="pr_command", required=True)
    pr_status = pr_commands.add_parser("status")
    pr_status.add_argument("project")
    pr_create = pr_commands.add_parser("create")
    pr_create.add_argument("project")
    pr_create.add_argument("--title", required=True)
    pr_create.add_argument("--body", default="")
    pr_create.add_argument("--base")
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


def _runtime_exit_code(error: RuntimeOperationError) -> int:
    return {
        "unavailable": 10,
        "unsupported": 11,
        "unauthenticated": 12,
        "forbidden": 13,
        "conflict": 14,
        "validation": 15,
        "timeout": 16,
        "broken": 17,
        "rate_limited": 17,
    }.get(error.category, 17)


async def _codex_command(settings: Settings, args: argparse.Namespace) -> int:
    request_id = f"req_cli-{secrets.token_hex(12)}"
    client = UnixCodexRuntimeClient(settings.runtime_socket)
    try:
        if args.codex_command == "status":
            try:
                status = await client.status(request_id)
                execution_mode = "runtime_socket"
            except RuntimeOperationError as exc:
                if exc.code != "CODEX_RUNTIME_UNAVAILABLE":
                    raise
                status = await CodexAdapter().status()
                execution_mode = "local_read_only"
            data = status.to_dict()
            data["execution_mode"] = execution_mode
            result = _envelope("codex.status", ok=True, data=data)
            result["execution_mode"] = execution_mode
            _print_result(result, getattr(args, "json_output", False))
            return 0 if status.installed else 10

        if args.codex_command == "pair" and getattr(args, "json_output", False):
            print(
                "ERROR [CODEX_PAIR_JSON_FORBIDDEN]: Pair Code JSON output is disabled",
                file=sys.stderr,
            )
            return 13
        if args.codex_command == "pair" and not sys.stdout.isatty():
            print(
                "ERROR [CODEX_PAIR_TTY_REQUIRED]: pairing requires an interactive TTY",
                file=sys.stderr,
            )
            return 13
        if args.codex_command == "start":
            action = await client.start_remote(request_id)
            print(f"Codex Remote: {action.outcome}")
            return 0
        if args.codex_command == "stop":
            action = await client.stop_remote(request_id)
            print(f"Codex Remote: {action.outcome}")
            return 0
        pair = await client.generate_pair_code(request_id)
        print("Sensitive temporary code. Do not share or log it.")
        print(pair.code)
        return 0
    except RuntimeOperationError as exc:
        print(f"ERROR [{exc.code}]: {exc.message}", file=sys.stderr)
        return _runtime_exit_code(exc)


async def _claude_command(settings: Settings, args: argparse.Namespace) -> int:
    request_id = f"req_cli-{secrets.token_hex(12)}"
    client = UnixClaudeRuntimeClient(settings.runtime_socket)
    command = str(args.claude_command)
    json_output = bool(getattr(args, "json_output", False))
    try:
        if command == "status":
            status = await client.status(request_id)
            result = _envelope("claude.status", ok=True, data=status.to_dict())
            result["execution_mode"] = "runtime_socket"
            _print_result(result, json_output)
            return 0 if status.installed and status.tmux_installed else 10
        if command == "list":
            sessions = await client.list_sessions(request_id)
            if json_output:
                result = _envelope(
                    "claude.list",
                    ok=True,
                    data={"sessions": [session.to_dict() for session in sessions]},
                )
                result["execution_mode"] = "runtime_socket"
                _print_result(result, True)
            else:
                print(f"{'PROJECT':<24} {'STATE':<20} SESSION")
                for session in sessions:
                    state = session.state.value.replace("_", " ").title()
                    print(f"{session.project_id:<24.24} {state:<20.20} managed")
            return 0

        project_id = str(args.project)
        if command == "start":
            action = await client.start_session(request_id, project_id)
            print(f"Claude session: {action.outcome} ({action.session.state.value})")
            return 0
        if command == "stop":
            action = await client.stop_session(request_id, project_id)
            print(f"Claude session: {action.outcome}")
            return 0
        if json_output:
            print(
                f"ERROR [CLAUDE_{command.upper()}_JSON_FORBIDDEN]: "
                f"Claude {command} JSON output is disabled",
                file=sys.stderr,
            )
            return 13
        if command == "output":
            output = await client.recent_output(request_id, project_id)
            print(
                "Sensitive Claude session output; it may contain project or model data.",
                file=sys.stderr,
            )
            print(output.output)
            return 0

        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print(
                "ERROR [CLAUDE_ATTACH_TTY_REQUIRED]: attach requires a local interactive TTY",
                file=sys.stderr,
            )
            return 13
        session = await client.session(request_id, project_id)
        if not session.tmux_running:
            print(
                "ERROR [CLAUDE_SESSION_NOT_RUNNING]: Claude session is not running",
                file=sys.stderr,
            )
            return 10
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session.session_name):
            print(
                "ERROR [TMUX_SESSION_NAME_INVALID]: Runtime returned an invalid session name",
                file=sys.stderr,
            )
            return 17
        tmux = shutil.which("tmux")
        if tmux is None or not os.path.isabs(tmux):
            print("ERROR [TMUX_NOT_INSTALLED]: tmux is unavailable", file=sys.stderr)
            return 10
        os.execv(tmux, [tmux, "attach-session", "-t", f"={session.session_name}"])
    except RuntimeOperationError as exc:
        print(f"ERROR [{exc.code}]: {exc.message}", file=sys.stderr)
        return _runtime_exit_code(exc)


def _queue_project_job(
    services: Any,
    *,
    job_type: str,
    project: Any,
    payload: dict[str, object],
) -> str:
    job, _created = services.jobs.enqueue(
        job_type=job_type,
        requested_by="local-cli",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        payload={"project_key": project.relative_path, **payload},
        resource_lock_key=f"project:{project.id}",
        idempotency_key=f"cli-{secrets.token_hex(16)}",
        request_id=f"req_cli-{secrets.token_hex(12)}",
    )
    return str(job.id)


async def _project_command(settings: Settings, args: argparse.Namespace) -> int:
    services = build_services(settings)
    runtime = UnixProjectRuntimeClient(settings.runtime_socket)
    request_id = f"req_cli-{secrets.token_hex(12)}"
    try:
        command = str(args.project_command)
        if command == "list":
            projects = services.projects.list()
            data = {
                "projects": [
                    {
                        "id": item.id,
                        "slug": item.slug,
                        "name": item.display_name,
                        "state": item.state,
                    }
                    for item in projects
                ]
            }
            _print_result(_envelope("project.list", ok=True, data=data), args.json_output)
            return 0
        if command in {"create", "clone"}:
            repository_url = None
            name = str(args.name) if args.name else ""
            source_type = "empty"
            if command == "clone":
                repository_url = validate_repository_url(str(args.url))
                name = name or repository_name_from_url(repository_url)
                source_type = "git_clone"
            project = services.projects.reserve(
                name=name,
                slug=args.slug,
                source_type=source_type,
                repository_url=repository_url,
            )
            try:
                job_id = _queue_project_job(
                    services,
                    job_type=f"project.{command}",
                    project=project,
                    payload={"repository_url": repository_url} if repository_url else {},
                )
            except Exception:
                services.projects.discard_reservation(project.id)
                raise
            print(f"Project queued: {project.id} (Job {job_id})")
            return 0

        project = services.projects.resolve(str(args.project), ready=True)
        if command == "status":
            status = await runtime.git_status(request_id, project.relative_path)
            _print_result(
                _envelope("project.status", ok=True, data=status.to_dict()),
                bool(getattr(args, "json_output", False)),
            )
            return 0
        if command in {"pull", "push"}:
            job_id = _queue_project_job(
                services, job_type=f"git.{command}", project=project, payload={}
            )
            print(f"Git {command} queued: {job_id}")
            return 0
        branch_command = str(args.branch_command)
        if branch_command == "list":
            branches = await runtime.branches(request_id, project.relative_path)
            for branch in branches:
                print(f"{'*' if branch.current else ' '} {branch.name}")
            return 0
        branch_name = validate_branch_name(str(args.branch))
        job_id = _queue_project_job(
            services,
            job_type=f"git.branch.{branch_command}",
            project=project,
            payload={"branch": branch_name},
        )
        print(f"Branch operation queued: {job_id}")
        return 0
    except (AgentBoxError, RuntimeOperationError, ValueError) as exc:
        code = (
            exc.code
            if isinstance(exc, (AgentBoxError, RuntimeOperationError))
            else "PROJECT_INPUT_INVALID"
        )
        message = (
            exc.message if isinstance(exc, (AgentBoxError, RuntimeOperationError)) else str(exc)
        )
        print(f"ERROR [{code}]: {message}", file=sys.stderr)
        return 15
    finally:
        services.database.close()


async def _github_command(settings: Settings, args: argparse.Namespace) -> int:
    services = build_services(settings)
    runtime = UnixProjectRuntimeClient(settings.runtime_socket)
    request_id = f"req_cli-{secrets.token_hex(12)}"
    try:
        if args.github_command == "status":
            global_status = await runtime.github_status(request_id)
            _print_result(_envelope("github.status", ok=True, data=global_status.to_dict()), False)
            return 0
        project = services.projects.resolve(str(args.project), ready=True)
        if args.pr_command == "status":
            project_status = await runtime.github_project_status(request_id, project.relative_path)
            _print_result(
                _envelope("github.pr.status", ok=True, data=project_status.to_dict()),
                False,
            )
            return 0
        job_id = _queue_project_job(
            services,
            job_type="github.pr.create",
            project=project,
            payload={"title": args.title, "body": args.body, "base": args.base},
        )
        print(f"Draft pull request queued: {job_id}")
        return 0
    except (AgentBoxError, RuntimeOperationError, ValueError) as exc:
        code = (
            exc.code
            if isinstance(exc, (AgentBoxError, RuntimeOperationError))
            else "GITHUB_INPUT_INVALID"
        )
        message = (
            exc.message if isinstance(exc, (AgentBoxError, RuntimeOperationError)) else str(exc)
        )
        print(f"ERROR [{code}]: {message}", file=sys.stderr)
        return 15
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

    if args.command == "codex":
        return asyncio.run(_codex_command(settings, args))

    if args.command == "claude":
        return asyncio.run(_claude_command(settings, args))

    if args.command == "project":
        return asyncio.run(_project_command(settings, args))

    if args.command == "github":
        return asyncio.run(_github_command(settings, args))

    status = _control_plane_status(settings)
    result = _envelope(args.command, ok=True, data=status)
    _print_result(result, args.json_output)
    return 0
