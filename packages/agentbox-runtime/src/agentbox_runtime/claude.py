"""Public-CLI Claude detection and project-scoped tmux session lifecycle."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path

from agentbox_core.waw import validate_project_id as validate_waw_project_id

from agentbox_runtime.models import (
    AuthenticationState,
    CapabilityState,
    ClaudeCapabilities,
    ClaudeCapabilityStatus,
    ClaudeSession,
    ClaudeSessionActionResult,
    ClaudeSessionOutput,
    ClaudeSessionState,
    ClaudeStatus,
    DiagnosticFinding,
    RuntimeOperationError,
    WorkspaceState,
)
from agentbox_runtime.process import (
    ControlledProcessRunner,
    ExecutableIdentity,
    ProcessResult,
    inspect_executable,
    minimal_runtime_environment,
)
from agentbox_runtime.project import ConfiguredProject, ProjectRegistry
from agentbox_runtime.tmux import TmuxAdapter
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWConflictError,
    WAWConflictLease,
)

_ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_VERSION_FIRST = re.compile(
    r"\A\s*(?P<version>[0-9][0-9A-Za-z.+_-]{0,63})\s+\(Claude(?:\s+Code)?\)\s*\Z",
    re.I,
)
_VERSION_PREFIXED = re.compile(
    r"\A\s*Claude(?:\s+Code)?(?:\s+version)?\s+"
    r"(?P<version>[0-9][0-9A-Za-z.+_-]{0,63})(?:\s|\Z)",
    re.I,
)
_TRUST = re.compile(
    r"(?:workspace\s+trust|trust\s+this\s+(?:folder|project|workspace)|"
    r"do\s+you\s+trust|security\s+confirmation)",
    re.I,
)
_LOGIN = re.compile(
    r"(?:authentication\s+required|not\s+logged\s+in|please\s+(?:log|sign)\s+in)", re.I
)
_READY = re.compile(
    r"(?:remote\s+control.{0,80}(?:ready|active|started)|"
    r"(?:ready|active|started).{0,80}remote\s+control)",
    re.I | re.S,
)
_FATAL = re.compile(r"(?:fatal\s+error|failed\s+to\s+start|command\s+not\s+found)", re.I)
_AUTHENTICATED = re.compile(r"\b(?:authenticated|logged\s+in)\b", re.I)
_UNAUTHENTICATED = re.compile(r"\b(?:unauthenticated|not\s+logged\s+in)\b", re.I)


def managed_session_name(project_id: str) -> str:
    """Return one bounded ASCII name; caller text never becomes tmux syntax."""
    digest = hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:12]
    ascii_name = unicodedata.normalize("NFKD", project_id).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_name).strip("-_").lower()
    slug = slug[:28].rstrip("-_") or "project"
    return f"agentbox-claude-{slug}-{digest}"


def managed_session_marker(project_id: str) -> str:
    digest = hashlib.sha256(("agentbox-claude-v1\0" + project_id).encode()).hexdigest()[:16]
    return f"v1:{digest}"


def attach_command(session_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session_name):
        raise RuntimeOperationError(
            "TMUX_SESSION_NAME_INVALID", "tmux session name is invalid", category="validation"
        )
    return f"tmux attach-session -t ={session_name}"


def sanitize_pane_output(
    raw: bytes, *, line_limit: int = 200, byte_limit: int = 24 * 1024
) -> tuple[str, bool]:
    """Remove terminal controls and bound sensitive pane text without claiming redaction."""
    if not 1 <= line_limit <= 200 or not 1 <= byte_limit <= 24 * 1024:
        raise ValueError("output limits are invalid")
    text = raw.decode("utf-8", errors="replace")
    text = _ANSI_OSC.sub("", _ANSI_CSI.sub("", text))
    text = "".join(
        character
        for character in text
        if character in {"\n", "\t"} or (ord(character) >= 32 and ord(character) != 127)
    )
    lines = text.splitlines()
    truncated = len(lines) > line_limit
    text = "\n".join(lines[-line_limit:])
    encoded = text.encode("utf-8")
    if len(encoded) > byte_limit:
        truncated = True
        text = encoded[-byte_limit:].decode("utf-8", errors="ignore")
    return text, truncated


def classify_startup_output(output: str) -> ClaudeSessionState:
    """Conservative hints only; unknown UI text never becomes a readiness claim."""
    if _TRUST.search(output) or _LOGIN.search(output):
        return ClaudeSessionState.NEEDS_INTERACTION
    if _FATAL.search(output):
        return ClaudeSessionState.BROKEN
    if _READY.search(output):
        return ClaudeSessionState.RUNNING
    return ClaudeSessionState.UNKNOWN


class ClaudeAdapter:
    """Detect Claude behavior using only public CLI help and status commands."""

    runtime_name = "claude"

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        runner: ControlledProcessRunner | None = None,
    ) -> None:
        self._environment = minimal_runtime_environment(environment or os.environ)
        self._runner = runner or ControlledProcessRunner()

    def executable(self) -> ExecutableIdentity | None:
        selected = shutil.which("claude", path=self._environment.get("PATH", ""))
        if selected is None:
            return None
        try:
            return inspect_executable(Path(selected).absolute(), error_prefix="CLAUDE")
        except RuntimeOperationError:
            return None

    async def inspect(
        self,
    ) -> tuple[
        bool,
        str | None,
        AuthenticationState,
        ClaudeCapabilities,
        tuple[DiagnosticFinding, ...],
    ]:
        identity = self.executable()
        if identity is None:
            return (
                False,
                None,
                AuthenticationState.UNKNOWN,
                ClaudeCapabilities(),
                (
                    DiagnosticFinding(
                        code="CLAUDE_NOT_INSTALLED",
                        severity="warning",
                        summary="Claude is not available on the Runtime PATH.",
                        remediation="Install and authenticate Claude manually.",
                    ),
                ),
            )
        diagnostics: list[DiagnosticFinding] = []
        version: str | None = None
        try:
            version_result = await self._invoke(identity, ("--version",), allow_nonzero=True)
            version = self._parse_version(version_result)
        except RuntimeOperationError:
            diagnostics.append(
                DiagnosticFinding(
                    code="CLAUDE_VERSION_UNKNOWN",
                    severity="warning",
                    summary="Claude version could not be read safely.",
                )
            )
        try:
            main_help = await self._invoke(identity, ("--help",), allow_nonzero=True)
        except RuntimeOperationError:
            main_help = None
        capabilities = await self._capabilities(identity, main_help)
        authentication = await self._authentication(identity, main_help)
        if capabilities.remote_control is CapabilityState.UNKNOWN:
            diagnostics.append(
                DiagnosticFinding(
                    code="CLAUDE_REMOTE_CAPABILITY_UNKNOWN",
                    severity="warning",
                    summary="Claude Remote capability could not be confirmed from public help.",
                )
            )
        return True, version, authentication, capabilities, tuple(diagnostics)

    async def _capabilities(
        self, identity: ExecutableIdentity, main_help: ProcessResult | None
    ) -> ClaudeCapabilities:
        if main_help is None or main_help.exit_code != 0:
            return ClaudeCapabilities(version=CapabilityState.SUPPORTED)
        help_text = self._text(main_help)
        if not re.search(r"\bremote-control\b", help_text, re.I):
            return ClaudeCapabilities(
                remote_control=CapabilityState.UNSUPPORTED,
                remote_start=CapabilityState.UNSUPPORTED,
                version=CapabilityState.SUPPORTED,
            )
        try:
            remote_help = await self._invoke(
                identity, ("remote-control", "--help"), allow_nonzero=True
            )
        except RuntimeOperationError:
            return ClaudeCapabilities(
                remote_control=CapabilityState.UNKNOWN,
                remote_start=CapabilityState.UNKNOWN,
                version=CapabilityState.SUPPORTED,
            )
        state = CapabilityState.SUPPORTED if remote_help.exit_code == 0 else CapabilityState.UNKNOWN
        return ClaudeCapabilities(
            remote_control=state,
            remote_start=state,
            version=CapabilityState.SUPPORTED,
        )

    async def _authentication(
        self, identity: ExecutableIdentity, main_help: ProcessResult | None
    ) -> AuthenticationState:
        if main_help is None or main_help.exit_code != 0:
            return AuthenticationState.UNKNOWN
        if not re.search(r"(?:^|\s)auth(?:\s|$)", self._text(main_help), re.I):
            return AuthenticationState.UNKNOWN
        try:
            result = await self._invoke(identity, ("auth", "status"), allow_nonzero=True)
        except RuntimeOperationError:
            return AuthenticationState.UNKNOWN
        output = self._text(result)
        if _UNAUTHENTICATED.search(output):
            return AuthenticationState.UNAUTHENTICATED
        if result.exit_code == 0 and _AUTHENTICATED.search(output):
            return AuthenticationState.AUTHENTICATED
        return AuthenticationState.UNKNOWN

    async def _invoke(
        self,
        identity: ExecutableIdentity,
        arguments: tuple[str, ...],
        *,
        allow_nonzero: bool,
    ) -> ProcessResult:
        result = await self._runner.run(
            identity,
            arguments,
            environment=self._environment,
            cwd=Path(self._environment.get("HOME", "/")),
            timeout_seconds=8,
            stdout_limit=64 * 1024,
            stderr_limit=16 * 1024,
            error_prefix="CLAUDE",
        )
        if result.exit_code != 0 and not allow_nonzero:
            raise RuntimeOperationError("CLAUDE_COMMAND_FAILED", "Claude command failed")
        return result

    @staticmethod
    def _parse_version(result: ProcessResult) -> str | None:
        text = ClaudeAdapter._text(result).strip()
        first_line = text.splitlines()[0].strip() if text else ""
        for pattern in (_VERSION_FIRST, _VERSION_PREFIXED):
            match = pattern.search(first_line)
            if match:
                return match.group("version")[:64]
        return first_line[:64] if result.exit_code == 0 and first_line else None

    @staticmethod
    def _text(result: ProcessResult) -> str:
        return (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")


class ClaudeSessionManager:
    """Own one marked tmux-backed Claude Remote session per configured project."""

    def __init__(
        self,
        adapter: ClaudeAdapter,
        tmux: TmuxAdapter,
        projects: ProjectRegistry,
        *,
        observe_delay_seconds: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_concurrent_tmux_operations: int = 4,
        conflict_coordinator: WAWConflictCoordinator | None = None,
        formal_project_id_for_legacy: Callable[[str], str | None] | None = None,
    ) -> None:
        self._adapter = adapter
        self._tmux = tmux
        self._projects = projects
        self._observe_delay_seconds = observe_delay_seconds
        self._sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._tmux_limiter = asyncio.Semaphore(max_concurrent_tmux_operations)
        self._initialized: set[str] = set()
        if (
            conflict_coordinator is not None
            and type(conflict_coordinator) is not WAWConflictCoordinator
        ):
            raise TypeError("conflict_coordinator must be WAWConflictCoordinator")
        if (conflict_coordinator is None) != (formal_project_id_for_legacy is None):
            raise ValueError("conflict coordinator and Project identity mapper must be paired")
        if formal_project_id_for_legacy is not None and not callable(formal_project_id_for_legacy):
            raise TypeError("formal_project_id_for_legacy must be callable")
        self._conflicts = conflict_coordinator
        self._formal_project_id_for_legacy = formal_project_id_for_legacy

    @property
    def conflict_coordinator(self) -> WAWConflictCoordinator | None:
        return self._conflicts

    def bind_conflict_coordinator(
        self,
        coordinator: WAWConflictCoordinator,
        *,
        formal_project_id_for_legacy: Callable[[str], str | None],
    ) -> None:
        """Install the host coordinator once when fixed WAW composition is enabled."""

        if type(coordinator) is not WAWConflictCoordinator:
            raise TypeError("coordinator must be WAWConflictCoordinator")
        if not callable(formal_project_id_for_legacy):
            raise TypeError("formal_project_id_for_legacy must be callable")
        if self._conflicts is not None:
            raise RuntimeOperationError(
                "WAW_CONFLICT_COORDINATOR_BOUND",
                "Claude conflict coordinator is already bound",
                category="conflict",
            )
        self._conflicts = coordinator
        self._formal_project_id_for_legacy = formal_project_id_for_legacy

    async def status(self) -> ClaudeStatus:
        installed, version, authentication, capabilities, diagnostics = (
            await self._adapter.inspect()
        )
        tmux_identity = self._tmux.executable()
        tmux_version = await self._tmux.version() if tmux_identity is not None else None
        sessions = await self.list_sessions()
        actual_names = await self._tmux.list_sessions() if tmux_identity is not None else ()
        expected = {session.session_name for session in sessions if session.managed}
        return ClaudeStatus(
            installed=installed,
            version=version,
            authentication=authentication,
            capabilities=capabilities,
            tmux_installed=tmux_identity is not None,
            tmux_version=tmux_version,
            managed_sessions=sum(session.managed and session.tmux_running for session in sessions),
            unmanaged_sessions=sum(name not in expected for name in actual_names),
            workspace_interaction_warnings=sum(
                session.state is ClaudeSessionState.NEEDS_INTERACTION for session in sessions
            ),
            diagnostics=diagnostics,
        )

    async def capability_status(self) -> ClaudeCapabilityStatus:
        """Collect only bounded public and exact AgentBox-managed session evidence."""
        installed, version, authentication, capabilities, _diagnostics = (
            await self._adapter.inspect()
        )
        tmux_installed = self._tmux.executable() is not None
        if not installed or not tmux_installed:
            return ClaudeCapabilityStatus(
                installed=installed,
                version=version,
                authentication=authentication,
                capabilities=capabilities,
                tmux_installed=tmux_installed,
                managed_session_count=None,
                managed_session_evidence_available=False,
            )

        projects = self._projects.list_projects()
        if len(projects) > 64:
            return ClaudeCapabilityStatus(
                installed=installed,
                version=version,
                authentication=authentication,
                capabilities=capabilities,
                tmux_installed=True,
                managed_session_count=None,
                managed_session_evidence_available=False,
            )
        managed_session_count = 0
        try:
            for project in projects:
                session_name = managed_session_name(project.project_id)
                if await self._tmux.has_session(session_name) and await self._tmux.is_managed(
                    session_name, managed_session_marker(project.project_id)
                ):
                    managed_session_count += 1
        except RuntimeOperationError:
            return ClaudeCapabilityStatus(
                installed=installed,
                version=version,
                authentication=authentication,
                capabilities=capabilities,
                tmux_installed=True,
                managed_session_count=None,
                managed_session_evidence_available=False,
            )
        return ClaudeCapabilityStatus(
            installed=installed,
            version=version,
            authentication=authentication,
            capabilities=capabilities,
            tmux_installed=True,
            managed_session_count=managed_session_count,
            managed_session_evidence_available=True,
        )

    async def list_sessions(self) -> tuple[ClaudeSession, ...]:
        projects = self._projects.list_projects()
        if self._tmux.executable() is None:
            return tuple(self._stopped(project) for project in projects)
        return tuple([await self.session(project.project_id) for project in projects])

    async def session(self, project_id: str) -> ClaudeSession:
        project = self._projects.resolve(project_id)
        name = managed_session_name(project.project_id)
        marker = managed_session_marker(project.project_id)
        if self._tmux.executable() is None or not await self._tmux.has_session(name):
            return self._stopped(project)
        if not await self._tmux.is_managed(name, marker):
            raise RuntimeOperationError(
                "CLAUDE_SESSION_COLLISION",
                "A non-AgentBox tmux session uses the managed session name",
                category="conflict",
            )
        return await self._observe(project, name)

    async def start(self, project_id: str) -> ClaudeSessionActionResult:
        project = self._projects.resolve(project_id)
        formal_project_id = self._mapped_waw_project_id(project.project_id)
        async with self._project_lock(project.project_id), self._tmux_limiter:
            lease = await self._acquire_conflict_lease(formal_project_id)
            try:
                name = managed_session_name(project.project_id)
                marker = managed_session_marker(project.project_id)
                if await self._tmux.has_session(name):
                    if not await self._tmux.is_managed(name, marker):
                        raise RuntimeOperationError(
                            "CLAUDE_SESSION_COLLISION",
                            "A non-AgentBox tmux session uses the managed session name",
                            category="conflict",
                        )
                    return ClaudeSessionActionResult(
                        "already_running", await self._observe(project, name)
                    )
                installed, _version, authentication, capabilities, _diagnostics = (
                    await self._adapter.inspect()
                )
                if not installed or self._adapter.executable() is None:
                    raise RuntimeOperationError(
                        "CLAUDE_NOT_INSTALLED", "Claude is unavailable", category="unavailable"
                    )
                if authentication is AuthenticationState.UNAUTHENTICATED:
                    raise RuntimeOperationError(
                        "CLAUDE_UNAUTHENTICATED",
                        "Claude authentication is required",
                        category="unauthenticated",
                    )
                if capabilities.remote_start is not CapabilityState.SUPPORTED:
                    raise RuntimeOperationError(
                        "CLAUDE_REMOTE_UNSUPPORTED",
                        "Claude Remote capability is unsupported or unknown",
                        category="unsupported",
                    )
                executable = self._adapter.executable()
                if executable is None:
                    raise RuntimeOperationError(
                        "CLAUDE_NOT_INSTALLED", "Claude is unavailable", category="unavailable"
                    )
                await self._tmux.create_session(
                    name,
                    cwd=project.path,
                    command=executable,
                    managed_marker=marker,
                )
                self._initialized.add(project.project_id)
                await self._sleep(self._observe_delay_seconds)
                if not await self._tmux.has_session(name):
                    session = self._session_view(
                        project, name, ClaudeSessionState.BROKEN, tmux_running=False
                    )
                else:
                    session = await self._observe(project, name)
                    interaction_prepared = False
                    if (
                        session.workspace_state is WorkspaceState.REQUIRES_USER_CONFIRMATION
                        and await self._tmux.pane_dead(name)
                    ):
                        if not await self._tmux.is_managed(name, marker):
                            raise RuntimeOperationError(
                                "CLAUDE_SESSION_UNMANAGED",
                                "The tmux session is not managed by AgentBox",
                                category="forbidden",
                            )
                        await self._tmux.prepare_workspace_interaction(
                            name,
                            cwd=project.path,
                            command=executable,
                        )
                        interaction_prepared = True
                        await self._sleep(self._observe_delay_seconds)
                        session = await self._observe(project, name)
                        if session.state is not ClaudeSessionState.NEEDS_INTERACTION:
                            session = replace(
                                session,
                                state=ClaudeSessionState.NEEDS_INTERACTION,
                                workspace_state=WorkspaceState.REQUIRES_USER_CONFIRMATION,
                                remote_readiness="unknown",
                            )
                    if session.state is ClaudeSessionState.UNKNOWN and not interaction_prepared:
                        session = replace(session, state=ClaudeSessionState.STARTING)
                return ClaudeSessionActionResult("started", session)
            finally:
                if lease is not None:
                    lease.release()

    async def stop(self, project_id: str) -> ClaudeSessionActionResult:
        project = self._projects.resolve(project_id)
        async with self._project_lock(project.project_id), self._tmux_limiter:
            name = managed_session_name(project.project_id)
            marker = managed_session_marker(project.project_id)
            if not await self._tmux.has_session(name):
                return ClaudeSessionActionResult("already_stopped", self._stopped(project))
            if not await self._tmux.is_managed(name, marker):
                raise RuntimeOperationError(
                    "CLAUDE_SESSION_UNMANAGED",
                    "The tmux session is not managed by AgentBox",
                    category="forbidden",
                )
            await self._tmux.kill_session(name)
            return ClaudeSessionActionResult("stopped", self._stopped(project))

    async def recent_output(self, project_id: str) -> ClaudeSessionOutput:
        project = self._projects.resolve(project_id)
        name = managed_session_name(project.project_id)
        marker = managed_session_marker(project.project_id)
        async with self._tmux_limiter:
            if not await self._tmux.has_session(name) or not await self._tmux.is_managed(
                name, marker
            ):
                raise RuntimeOperationError(
                    "CLAUDE_SESSION_OUTPUT_UNAVAILABLE",
                    "Claude session output is unavailable",
                    category="unavailable",
                )
            output, truncated = sanitize_pane_output(await self._tmux.capture_pane(name))
        return ClaudeSessionOutput(project.project_id, name, output, truncated)

    async def _observe(self, project: ConfiguredProject, name: str) -> ClaudeSession:
        output = ""
        try:
            output, _truncated = sanitize_pane_output(await self._tmux.capture_pane(name))
            state = classify_startup_output(output)
        except RuntimeOperationError:
            state = ClaudeSessionState.UNKNOWN
        workspace = (
            WorkspaceState.REQUIRES_USER_CONFIRMATION
            if state is ClaudeSessionState.NEEDS_INTERACTION and _TRUST.search(output)
            else (
                WorkspaceState.INITIALIZED_BY_AGENTBOX
                if project.project_id in self._initialized
                else WorkspaceState.UNKNOWN
            )
        )
        readiness = "ready" if state is ClaudeSessionState.RUNNING else "unknown"
        return self._session_view(
            project,
            name,
            state,
            tmux_running=True,
            workspace=workspace,
            remote_readiness=readiness,
        )

    @staticmethod
    def _session_view(
        project: ConfiguredProject,
        name: str,
        state: ClaudeSessionState,
        *,
        tmux_running: bool,
        workspace: WorkspaceState = WorkspaceState.UNKNOWN,
        remote_readiness: str = "unknown",
    ) -> ClaudeSession:
        return ClaudeSession(
            project_id=project.project_id,
            display_name=project.display_name,
            state=state,
            managed=True,
            session_name=name,
            attach_command=attach_command(name),
            workspace_state=workspace,
            tmux_running=tmux_running,
            remote_readiness=remote_readiness,
        )

    def _stopped(self, project: ConfiguredProject) -> ClaudeSession:
        return self._session_view(
            project,
            managed_session_name(project.project_id),
            ClaudeSessionState.STOPPED,
            tmux_running=False,
        )

    def _project_lock(self, project_id: str) -> asyncio.Lock:
        lock = self._locks.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[project_id] = lock
        return lock

    def _mapped_waw_project_id(self, relative_key: str) -> str:
        if self._conflicts is None:
            return relative_key
        mapper = self._formal_project_id_for_legacy
        if mapper is None:  # pragma: no cover - constructor/binder invariant
            raise RuntimeOperationError(
                "PROJECT_RUNTIME_ACTIVE",
                "WAW Project identity mapping is unavailable",
                category="conflict",
            )
        try:
            formal_project_id = mapper(relative_key)
            if formal_project_id is None:
                raise ValueError("WAW Project identity mapping is unavailable")
            validate_waw_project_id(formal_project_id)
        except Exception as exc:
            raise RuntimeOperationError(
                "PROJECT_RUNTIME_ACTIVE",
                "WAW Project identity mapping is unavailable",
                category="conflict",
            ) from exc
        return formal_project_id

    async def _acquire_conflict_lease(self, project_id: str) -> WAWConflictLease | None:
        if self._conflicts is None:
            return None
        task = asyncio.create_task(
            asyncio.to_thread(
                self._conflicts.acquire_legacy_claude_start,
                project_id=project_id,
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            lease: WAWConflictLease | None = None
            while True:
                try:
                    lease = await asyncio.shield(task)
                    break
                except asyncio.CancelledError:
                    if task.done():
                        break
                    continue
                except WAWConflictError:
                    break
            if lease is not None:
                lease.release()
            raise
        except WAWConflictError as exc:
            raise RuntimeOperationError(
                exc.code,
                "WAW Runtime conflicts with legacy Claude start",
                category="conflict",
            ) from exc
