"""Minimal non-root Runtime Executor for allowlisted Codex and Claude actions."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import os
import socket
import stat
import struct
from pathlib import Path
from typing import Any

from agentbox_protocol.runtime_capabilities import (
    RUNTIME_CAPABILITY_ACTION,
    RuntimeCapabilityQuery,
)

from agentbox_runtime.capabilities import RuntimeCapabilityCollector
from agentbox_runtime.claude import ClaudeAdapter, ClaudeSessionManager
from agentbox_runtime.codex import CodexAdapter, CodexManager
from agentbox_runtime.git import GitAdapter, validate_branch_name, validate_git_repository_url
from agentbox_runtime.github import GitHubAdapter, validate_pr_body, validate_pr_title
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import ProjectRegistry, validate_project_id
from agentbox_runtime.rpc import (
    MAX_RUNTIME_FRAME,
    RUNTIME_PROTOCOL_VERSION,
    strict_json_loads,
    validate_request_id,
)
from agentbox_runtime.tmux import TmuxAdapter
from agentbox_runtime.workspace import ProjectWorkspaceManager, validate_operation_id

_CODEX_ACTIONS = frozenset(
    {"codex.status", "codex.remote.start", "codex.remote.stop", "codex.pair"}
)
_CLAUDE_GLOBAL_ACTIONS = frozenset({"claude.status", "claude.sessions.list"})
_CLAUDE_PROJECT_ACTIONS = frozenset(
    {
        "claude.session.status",
        "claude.session.start",
        "claude.session.stop",
        "claude.session.output",
    }
)
_ACTIONS = _CODEX_ACTIONS | _CLAUDE_GLOBAL_ACTIONS | _CLAUDE_PROJECT_ACTIONS
_ACTIONS |= frozenset({RUNTIME_CAPABILITY_ACTION})
_PROJECT_ACTION_KEYS: dict[str, frozenset[str]] = {
    "project.list": frozenset(),
    "project.create": frozenset({"project_key", "operation_id"}),
    "project.clone": frozenset({"project_key", "operation_id", "repository_url"}),
    "project.finalize": frozenset({"project_key", "operation_id"}),
    "project.rollback": frozenset({"project_key", "operation_id"}),
    "git.status": frozenset({"project_key"}),
    "git.global.status": frozenset(),
    "git.branches.list": frozenset({"project_key"}),
    "git.branch.create": frozenset({"project_key", "branch"}),
    "git.branch.switch": frozenset({"project_key", "branch"}),
    "git.pull": frozenset({"project_key"}),
    "git.push": frozenset({"project_key"}),
    "github.status": frozenset(),
    "github.project.status": frozenset({"project_key"}),
    "github.pr.create": frozenset({"project_key", "title", "body", "base"}),
}
_ACTIONS |= frozenset(_PROJECT_ACTION_KEYS)


class RuntimeExecutorServer:
    def __init__(
        self,
        socket_path: Path,
        manager: CodexManager,
        *,
        allowed_peer_uids: frozenset[int],
        allowed_peer_gids: frozenset[int] | None = None,
        claude_manager: ClaudeSessionManager | None = None,
        project_manager: ProjectWorkspaceManager | None = None,
        capability_collector: RuntimeCapabilityCollector | None = None,
        read_timeout_seconds: float = 5.0,
        write_timeout_seconds: float = 5.0,
        trailing_timeout_seconds: float = 0.01,
    ) -> None:
        if read_timeout_seconds <= 0 or write_timeout_seconds <= 0 or trailing_timeout_seconds <= 0:
            raise ValueError("Runtime socket timeouts must be positive")
        self._socket_path = socket_path
        self._manager = manager
        self._claude_manager = claude_manager
        self._project_manager = project_manager
        self._capability_collector = capability_collector
        self._allowed_peer_uids = allowed_peer_uids
        self._allowed_peer_gids = allowed_peer_gids or frozenset({os.getegid()})
        self._read_timeout_seconds = read_timeout_seconds
        self._write_timeout_seconds = write_timeout_seconds
        self._trailing_timeout_seconds = trailing_timeout_seconds
        self._server: asyncio.AbstractServer | None = None

    async def start(self, *, create_development_parent: bool = False) -> None:
        parent = self._socket_path.parent
        if create_development_parent:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not parent.is_dir():
            raise RuntimeError("Runtime socket parent does not exist")
        if self._socket_path.exists() or self._socket_path.is_symlink():
            details = self._socket_path.lstat()
            if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.geteuid():
                raise RuntimeError("refusing to replace an unexpected Runtime socket path")
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(0.2)
            try:
                probe.connect(str(self._socket_path))
            except OSError as exc:
                if exc.errno not in {errno.ECONNREFUSED, errno.ENOENT}:
                    raise RuntimeError("Runtime socket state cannot be verified") from exc
                try:
                    current = self._socket_path.lstat()
                except FileNotFoundError:
                    current = None
                if current is not None:
                    if (
                        not stat.S_ISSOCK(current.st_mode)
                        or current.st_uid != os.geteuid()
                        or (current.st_dev, current.st_ino) != (details.st_dev, details.st_ino)
                    ):
                        raise RuntimeError(
                            "Runtime socket changed during stale-state check"
                        ) from exc
                    self._socket_path.unlink()
            else:
                raise RuntimeError("Runtime socket already has an active server")
            finally:
                probe.close()
        self._server = await asyncio.start_unix_server(
            self._handle,
            path=self._socket_path,
            start_serving=False,
            limit=MAX_RUNTIME_FRAME + 1,
        )
        try:
            configured_gid = os.environ.get("AGENTBOX_RUNTIME_SOCKET_GID")
            if configured_gid:
                try:
                    socket_gid = int(configured_gid)
                except ValueError as exc:
                    raise RuntimeError("AGENTBOX_RUNTIME_SOCKET_GID must be an integer") from exc
                if socket_gid not in os.getgroups() and socket_gid != os.getegid():
                    raise RuntimeError("Runtime socket group is not assigned to this process")
                os.chown(self._socket_path, -1, socket_gid)
            self._socket_path.chmod(0o660)
            await self._server.start_serving()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            details = self._socket_path.lstat()
            if stat.S_ISSOCK(details.st_mode) and details.st_uid == os.geteuid():
                self._socket_path.unlink()
        except FileNotFoundError:
            pass

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("Runtime server is not started")
        async with self._server:
            await self._server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_id: str | None = None
        try:
            if not self._peer_allowed(writer):
                await self._write_error(
                    writer, "RUNTIME_PEER_FORBIDDEN", "Runtime peer is forbidden"
                )
                return
            raw = await asyncio.wait_for(reader.readline(), timeout=self._read_timeout_seconds)
            if not raw or len(raw) > MAX_RUNTIME_FRAME or not raw.endswith(b"\n"):
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            request = strict_json_loads(raw)
            if (
                not isinstance(request, dict)
                or type(request.get("protocol_version")) is not int
                or request["protocol_version"] != RUNTIME_PROTOCOL_VERSION
                or not isinstance(request.get("action"), str)
                or request["action"] not in _ACTIONS
                or not isinstance(request.get("request_id"), str)
            ):
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            try:
                validate_request_id(request["request_id"])
            except RuntimeOperationError:
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            try:
                trailing = await asyncio.wait_for(
                    reader.read(1), timeout=self._trailing_timeout_seconds
                )
            except TimeoutError:
                trailing = b""
            if trailing:
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            action = request["action"]
            expected_keys = {"protocol_version", "action", "request_id"}
            if action == RUNTIME_CAPABILITY_ACTION:
                expected_keys = set(RuntimeCapabilityQuery.model_fields)
            if action in _CLAUDE_PROJECT_ACTIONS:
                expected_keys.add("project_id")
            expected_keys.update(_PROJECT_ACTION_KEYS.get(action, ()))
            if set(request) != expected_keys:
                await self._write_error(
                    writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                )
                return
            if action in _CLAUDE_PROJECT_ACTIONS:
                try:
                    raw_project_id = request.get("project_id")
                    if not isinstance(raw_project_id, str):
                        raise RuntimeOperationError(
                            "CLAUDE_PROJECT_INVALID",
                            "Project identifier is invalid",
                            category="validation",
                        )
                    validate_project_id(raw_project_id)
                except RuntimeOperationError:
                    await self._write_error(
                        writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                    )
                    return
            if action in _PROJECT_ACTION_KEYS:
                try:
                    self._validate_project_action(action, request)
                except RuntimeOperationError:
                    await self._write_error(
                        writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
                    )
                    return
            request_id = request["request_id"]
            data = await self._dispatch(request)
            await self._write(
                writer,
                {
                    "protocol_version": 1,
                    "request_id": request_id,
                    "data": data,
                    "error": None,
                },
            )
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeError,
            ValueError,
            RecursionError,
        ):
            await self._write_error(
                writer, "RUNTIME_PROTOCOL_INVALID", "Runtime request is invalid"
            )
        except RuntimeOperationError as exc:
            await self._write(
                writer,
                {
                    "protocol_version": 1,
                    "request_id": request_id,
                    "data": None,
                    "error": {
                        "code": exc.code,
                        "category": exc.category,
                        "message": exc.message,
                        "retryable": exc.retryable,
                        "retry_after": exc.retry_after,
                    },
                },
            )
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    def _peer_allowed(self, writer: asyncio.StreamWriter) -> bool:
        transport_socket = writer.get_extra_info("socket")
        if transport_socket is None or not hasattr(socket, "SO_PEERCRED"):
            return False
        try:
            credentials = transport_socket.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
            _pid, uid, gid = struct.unpack("3i", credentials)
        except (OSError, struct.error):
            return False
        return uid in self._allowed_peer_uids and gid in self._allowed_peer_gids

    async def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        action = str(request["action"])
        if action == RUNTIME_CAPABILITY_ACTION:
            if self._capability_collector is None:
                raise RuntimeOperationError(
                    "RUNTIME_MANAGER_UNAVAILABLE",
                    "Runtime capability manager is unavailable",
                    category="unavailable",
                    retryable=True,
                )
            query = RuntimeCapabilityQuery.model_validate_json(
                json.dumps(request, separators=(",", ":"), ensure_ascii=False)
            )
            return (await self._capability_collector.collect(query)).model_dump(mode="json")
        if action == "codex.status":
            return (await self._manager.status()).to_dict()
        if action == "codex.remote.start":
            return (await self._manager.start_remote()).to_dict()
        if action == "codex.remote.stop":
            return (await self._manager.stop_remote()).to_dict()
        if action == "codex.pair":
            return (await self._manager.generate_pair_code()).to_dict()
        if action.startswith("claude.") and self._claude_manager is None:
            raise RuntimeOperationError(
                "CLAUDE_RUNTIME_UNAVAILABLE",
                "Claude Runtime manager is unavailable",
                category="unavailable",
            )
        if self._claude_manager is not None:
            if action == "claude.status":
                return (await self._claude_manager.status()).to_dict()
            if action == "claude.sessions.list":
                return {
                    "sessions": [
                        session.to_dict() for session in await self._claude_manager.list_sessions()
                    ]
                }
            project_id = str(request.get("project_id", ""))
            if action == "claude.session.status":
                return (await self._claude_manager.session(project_id)).to_dict()
            if action == "claude.session.start":
                return (await self._claude_manager.start(project_id)).to_dict()
            if action == "claude.session.stop":
                return (await self._claude_manager.stop(project_id)).to_dict()
            if action == "claude.session.output":
                return (await self._claude_manager.recent_output(project_id)).to_dict()
        if action in _PROJECT_ACTION_KEYS and self._project_manager is None:
            raise RuntimeOperationError(
                "PROJECT_RUNTIME_UNAVAILABLE",
                "Project Runtime manager is unavailable",
                category="unavailable",
            )
        if self._project_manager is not None:
            project_key = str(request.get("project_key", ""))
            operation_id = str(request.get("operation_id", ""))
            if action == "project.list":
                return {
                    "projects": [item.to_dict() for item in self._project_manager.list_workspaces()]
                }
            if action == "project.create":
                return (await self._project_manager.create(project_key, operation_id)).to_dict()
            if action == "project.clone":
                return (
                    await self._project_manager.clone(
                        project_key, operation_id, str(request["repository_url"])
                    )
                ).to_dict()
            if action == "project.finalize":
                return self._project_manager.finalize(project_key, operation_id).to_dict()
            if action == "project.rollback":
                return self._project_manager.rollback(project_key, operation_id).to_dict()
            if action == "git.status":
                return (await self._project_manager.git_status(project_key)).to_dict()
            if action == "git.global.status":
                return (await self._project_manager.git_global_status()).to_dict()
            if action == "git.branches.list":
                return {
                    "branches": [
                        branch.to_dict()
                        for branch in await self._project_manager.branches(project_key)
                    ]
                }
            if action == "git.branch.create":
                return (
                    await self._project_manager.create_branch(project_key, str(request["branch"]))
                ).to_dict()
            if action in {"git.branch.switch", "git.pull"}:
                await self._require_inactive_claude(project_key)
            if action == "git.branch.switch":
                return (
                    await self._project_manager.switch_branch(project_key, str(request["branch"]))
                ).to_dict()
            if action == "git.pull":
                return (await self._project_manager.pull(project_key)).to_dict()
            if action == "git.push":
                return (await self._project_manager.push(project_key)).to_dict()
            if action == "github.status":
                return (await self._project_manager.github_global_status()).to_dict()
            if action == "github.project.status":
                return (await self._project_manager.github_status(project_key)).to_dict()
            if action == "github.pr.create":
                return (
                    await self._project_manager.create_draft_pr(
                        project_key,
                        title=str(request["title"]),
                        body=str(request["body"]),
                        base=(str(request["base"]) if request["base"] is not None else None),
                    )
                ).to_dict()
        raise RuntimeOperationError(
            "RUNTIME_ACTION_UNSUPPORTED", "Runtime action is unsupported", category="unsupported"
        )

    async def _require_inactive_claude(self, project_key: str) -> None:
        if self._claude_manager is None:
            return
        session = await self._claude_manager.session(project_key)
        if session.tmux_running:
            raise RuntimeOperationError(
                "PROJECT_RUNTIME_ACTIVE",
                "Stop the managed Claude session before changing the workspace",
                category="conflict",
            )

    @staticmethod
    def _validate_project_action(action: str, request: dict[str, Any]) -> None:
        if "project_key" in _PROJECT_ACTION_KEYS[action]:
            value = request.get("project_key")
            if not isinstance(value, str):
                raise RuntimeOperationError("PROJECT_INPUT_INVALID", "Project input is invalid")
            validate_project_id(value)
        if "operation_id" in _PROJECT_ACTION_KEYS[action]:
            value = request.get("operation_id")
            if not isinstance(value, str):
                raise RuntimeOperationError(
                    "PROJECT_OPERATION_INVALID", "Project operation is invalid"
                )
            validate_operation_id(value)
        if action == "project.clone":
            value = request.get("repository_url")
            if not isinstance(value, str):
                raise RuntimeOperationError(
                    "GIT_REPOSITORY_URL_INVALID", "Repository URL is invalid"
                )
            validate_git_repository_url(value)
        if "branch" in _PROJECT_ACTION_KEYS[action]:
            value = request.get("branch")
            if not isinstance(value, str):
                raise RuntimeOperationError("GIT_BRANCH_INVALID", "Branch name is invalid")
            validate_branch_name(value)
        if action == "github.pr.create":
            title, body, base = request.get("title"), request.get("body"), request.get("base")
            if (
                not isinstance(title, str)
                or not isinstance(body, str)
                or not (base is None or isinstance(base, str))
            ):
                raise RuntimeOperationError(
                    "GITHUB_PR_INPUT_INVALID", "Pull request input is invalid"
                )
            validate_pr_title(title)
            validate_pr_body(body)
            if base is not None:
                validate_branch_name(base)

    async def _write_error(self, writer: asyncio.StreamWriter, code: str, message: str) -> None:
        await self._write(
            writer,
            {
                "protocol_version": 1,
                "request_id": None,
                "data": None,
                "error": {
                    "code": code,
                    "category": "forbidden" if code.endswith("FORBIDDEN") else "validation",
                    "message": message,
                    "retryable": False,
                    "retry_after": None,
                },
            },
        )

    async def _write(self, writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        # UTF-8 avoids the six-byte \uXXXX expansion for bounded Unicode pane
        # output. The payload cap leaves room for worst-case JSON quoting inside
        # the unchanged 64 KiB Runtime frame.
        encoded = (
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        )
        if len(encoded) > MAX_RUNTIME_FRAME:
            encoded = (
                b'{"protocol_version":1,"request_id":null,"data":null,'
                b'"error":{"code":"RUNTIME_RESPONSE_TOO_LARGE",'
                b'"category":"broken","message":"Runtime response exceeded its limit",'
                b'"retryable":false,"retry_after":null}}\n'
            )
        writer.write(encoded)
        await asyncio.wait_for(writer.drain(), timeout=self._write_timeout_seconds)


async def _main() -> None:
    environment = os.environ.get("AGENTBOX_ENV", "development")
    socket_path = Path(os.environ.get("AGENTBOX_RUNTIME_SOCKET", ".agentbox-dev/runtime.sock"))
    if environment == "production" and (
        not socket_path.is_absolute() or socket_path.parent != Path("/run/agentbox")
    ):
        raise RuntimeError("production Runtime socket must be beneath /run/agentbox")
    configured_uids = os.environ.get("AGENTBOX_RUNTIME_ALLOWED_UIDS")
    configured_gids = os.environ.get("AGENTBOX_RUNTIME_ALLOWED_GIDS")
    if environment == "production" and (not configured_uids or not configured_gids):
        raise RuntimeError("Runtime peer UID and GID allowlists are required in production")
    allowed = (
        frozenset(int(value) for value in configured_uids.split(","))
        if configured_uids
        else frozenset({os.geteuid()})
    )
    allowed_gids = (
        frozenset(int(value) for value in configured_gids.split(","))
        if configured_gids
        else frozenset({os.getegid()})
    )
    try:
        pair_cooldown = int(os.environ.get("AGENTBOX_CODEX_PAIR_COOLDOWN", "10"))
    except ValueError as exc:
        raise RuntimeError("AGENTBOX_CODEX_PAIR_COOLDOWN must be an integer") from exc
    if not 5 <= pair_cooldown <= 300:
        raise RuntimeError("AGENTBOX_CODEX_PAIR_COOLDOWN must be between 5 and 300 seconds")
    project_registry = ProjectRegistry(
        Path(
            os.environ.get(
                "AGENTBOX_PROJECT_ROOT",
                (
                    "/srv/agentbox/projects"
                    if environment == "production"
                    else ".agentbox-dev/projects"
                ),
            )
        )
    )
    git = GitAdapter()
    github = GitHubAdapter(git)
    claude_manager = ClaudeSessionManager(ClaudeAdapter(), TmuxAdapter(), project_registry)
    codex_manager = CodexManager(CodexAdapter(), pair_cooldown_seconds=pair_cooldown)
    server = RuntimeExecutorServer(
        socket_path,
        codex_manager,
        allowed_peer_uids=allowed,
        allowed_peer_gids=allowed_gids,
        claude_manager=claude_manager,
        project_manager=ProjectWorkspaceManager(project_registry, git, github),
        capability_collector=RuntimeCapabilityCollector(codex_manager, claude_manager),
    )
    await server.start(create_development_parent=environment != "production")
    try:
        await server.serve_forever()
    finally:
        await server.close()


def main() -> None:
    asyncio.run(_main())
