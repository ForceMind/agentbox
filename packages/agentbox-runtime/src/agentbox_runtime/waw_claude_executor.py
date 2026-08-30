"""Bounded Claude adapter for the WAW lifecycle registry.

The adapter deliberately accepts only a formal Project resolver and an
immutable :class:`WAWLifecycleIdentity`.  It never accepts a filesystem path,
command, PID, tmux target, or credential from the WAW request.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from agentbox_core.waw import AgentType, workspace_id

from agentbox_runtime.claude import managed_session_name
from agentbox_runtime.models import (
    ClaudeSession,
    ClaudeSessionActionResult,
    ClaudeSessionState,
    RuntimeOperationError,
)
from agentbox_runtime.waw_control_server import WAWControlDispatchError
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleExecutor,
    WAWLifecycleIdentity,
    WAWLifecycleObservation,
)


@dataclass(frozen=True)
class ClaudeProjectBinding:
    """Resolver output binding a formal Project ID to its manager key."""

    project_id: str
    project_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, str) or not self.project_id:
            raise ValueError("project_id must be non-empty")
        if (
            not isinstance(self.project_key, str)
            or not 1 <= len(self.project_key) <= 80
            or self.project_key != self.project_key.strip()
            or self.project_key in {".", ".."}
            or self.project_key.startswith(".")
            or "/" in self.project_key
            or "\\" in self.project_key
            or any(unicodedata.category(char).startswith("C") for char in self.project_key)
            or any(
                not (char.isalnum() or char in {"-", "_", ".", " "})
                for char in self.project_key
            )
        ):
            raise ValueError("project_key is invalid")


ProjectResolver: TypeAlias = Callable[[str], ClaudeProjectBinding | Awaitable[ClaudeProjectBinding]]
_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")


class ClaudeSessionOperations(Protocol):
    async def start(self, project_id: str) -> ClaudeSessionActionResult: ...

    async def stop(self, project_id: str) -> ClaudeSessionActionResult: ...

    async def session(self, project_id: str) -> ClaudeSession: ...


class WAWClaudeLifecycleExecutor(WAWLifecycleExecutor):
    """Translate one Claude manager into the WAW lifecycle contract."""

    def __init__(
        self,
        manager: ClaudeSessionOperations,
        project_resolver: ProjectResolver,
        *,
        runtime_epoch: str,
    ) -> None:
        if not callable(project_resolver):
            raise TypeError("project_resolver must be callable")
        if not isinstance(runtime_epoch, str) or _POSITIVE_DECIMAL.fullmatch(runtime_epoch) is None:
            raise ValueError("runtime_epoch must be a positive decimal string")
        self._manager = manager
        self._project_resolver = project_resolver
        self._runtime_epoch = runtime_epoch

    async def start(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self._require_claude(identity)
        project = await self._project(identity.project_id)
        try:
            result = await self._manager.start(project.project_key)
        except RuntimeOperationError as exc:
            return self._error_observation(exc)
        return self._observation(result.session, identity.project_id)

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self._require_claude(identity)
        project = await self._project(identity.project_id)
        try:
            result = await self._manager.stop(project.project_key)
        except RuntimeOperationError as exc:
            return self._error_observation(exc)
        return self._observation(result.session, identity.project_id)

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self._require_claude(identity)
        project = await self._project(identity.project_id)
        try:
            session = await self._manager.session(project.project_key)
        except RuntimeOperationError as exc:
            return self._error_observation(exc)
        return self._observation(session, identity.project_id)

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return await self.status(identity)

    @staticmethod
    def _require_claude(identity: WAWLifecycleIdentity) -> None:
        if identity.agent_type != "claude":
            raise WAWControlDispatchError("WAW_AGENT_UNSUPPORTED")
        if workspace_id(identity.project_id, AgentType.CLAUDE) != identity.workspace_id:
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")

    async def _project(self, project_id: str) -> ClaudeProjectBinding:
        project = self._project_resolver(project_id)
        if isinstance(project, Awaitable):
            project = await project
        if not isinstance(project, ClaudeProjectBinding) or project.project_id != project_id:
            if isinstance(project, ClaudeProjectBinding):
                raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
            raise RuntimeOperationError(
                "WAW_PROJECT_UNAVAILABLE",
                "Formal Project is unavailable",
                category="unavailable",
            )
        return project

    def _observation(self, session: ClaudeSession, project_id: str) -> WAWLifecycleObservation:
        if (
            session.project_id != project_id
            or not session.managed
            or session.session_name != managed_session_name(project_id)
        ):
            raise WAWControlDispatchError("PROJECT_IDENTITY_CHANGED")
        state = {
            ClaudeSessionState.RUNNING: "RUNNING",
            ClaudeSessionState.STOPPED: "STOPPED",
            ClaudeSessionState.STARTING: "STARTING",
            ClaudeSessionState.NEEDS_INTERACTION: "NEEDS_INTERACTION",
            ClaudeSessionState.BROKEN: "BROKEN",
            ClaudeSessionState.UNKNOWN: "UNKNOWN",
        }[session.state]
        if state == "STOPPED":
            reconciliation = "authoritative"
            process = "STOPPED"
        elif state == "BROKEN":
            reconciliation = "reconciliation_required"
            process = "UNKNOWN"
        elif state == "UNKNOWN":
            reconciliation = "unknown"
            process = "UNKNOWN"
        else:
            reconciliation = "authoritative"
            process = "RUNNING" if session.tmux_running else "NOT_STARTED"
        return WAWLifecycleObservation(
            state=state,
            reconciliation_state=reconciliation,
            process_state=process,
            runtime_epoch=self._runtime_epoch,
        )

    def _error_observation(self, error: RuntimeOperationError) -> WAWLifecycleObservation:
        if error.code == "CLAUDE_SESSION_COLLISION":
            return WAWLifecycleObservation(
                state="COLLISION",
                reconciliation_state="collision",
                process_state="UNKNOWN",
                runtime_epoch=self._runtime_epoch,
            )
        if error.code == "CLAUDE_UNAUTHENTICATED":
            return WAWLifecycleObservation(
                state="LOGIN_REQUIRED",
                reconciliation_state="authoritative",
                process_state="NOT_STARTED",
                runtime_epoch=self._runtime_epoch,
            )
        if error.retryable or error.category == "unavailable":
            return WAWLifecycleObservation(
                state="UNKNOWN",
                reconciliation_state="reconciliation_required",
                process_state="UNKNOWN",
                runtime_epoch=self._runtime_epoch,
            )
        return WAWLifecycleObservation(
            state="BROKEN",
            reconciliation_state="reconciliation_required",
            process_state="UNKNOWN",
            runtime_epoch=self._runtime_epoch,
        )


__all__ = [
    "ClaudeProjectBinding",
    "ClaudeSessionOperations",
    "ProjectResolver",
    "WAWClaudeLifecycleExecutor",
]
