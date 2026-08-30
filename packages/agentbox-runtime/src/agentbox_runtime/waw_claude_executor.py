"""Bounded Claude adapter for the WAW lifecycle registry.

The adapter deliberately accepts only a formal Project resolver and an
immutable :class:`WAWLifecycleIdentity`.  It never accepts a filesystem path,
command, PID, tmux target, or credential from the WAW request.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import TypeAlias

from agentbox_runtime.claude import ClaudeSessionManager
from agentbox_runtime.models import ClaudeSession, ClaudeSessionState, RuntimeOperationError
from agentbox_runtime.waw_control_server import WAWControlDispatchError
from agentbox_runtime.waw_lifecycle import (
    WAWLifecycleExecutor,
    WAWLifecycleIdentity,
    WAWLifecycleObservation,
)

ProjectResolver: TypeAlias = Callable[[str], str | Awaitable[str]]
_POSITIVE_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")


class WAWClaudeLifecycleExecutor(WAWLifecycleExecutor):
    """Translate one Claude manager into the WAW lifecycle contract."""

    def __init__(
        self,
        manager: ClaudeSessionManager,
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
            result = await self._manager.start(project)
        except RuntimeOperationError as exc:
            return self._error_observation(exc)
        return self._observation(result.session)

    async def stop(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self._require_claude(identity)
        project = await self._project(identity.project_id)
        try:
            result = await self._manager.stop(project)
        except RuntimeOperationError as exc:
            return self._error_observation(exc)
        return self._observation(result.session)

    async def status(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        self._require_claude(identity)
        project = await self._project(identity.project_id)
        try:
            session = await self._manager.session(project)
        except RuntimeOperationError as exc:
            return self._error_observation(exc)
        return self._observation(session)

    async def reconcile(self, identity: WAWLifecycleIdentity) -> WAWLifecycleObservation:
        return await self.status(identity)

    @staticmethod
    def _require_claude(identity: WAWLifecycleIdentity) -> None:
        if identity.agent_type != "claude":
            raise WAWControlDispatchError("WAW_AGENT_UNSUPPORTED")

    async def _project(self, project_id: str) -> str:
        project = self._project_resolver(project_id)
        if isinstance(project, Awaitable):
            project = await project
        if not isinstance(project, str) or not project:
            raise RuntimeOperationError(
                "WAW_PROJECT_UNAVAILABLE",
                "Formal Project is unavailable",
                category="unavailable",
            )
        return project

    def _observation(self, session: ClaudeSession) -> WAWLifecycleObservation:
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
        return WAWLifecycleObservation(
            state="BROKEN",
            reconciliation_state="reconciliation_required",
            process_state="UNKNOWN",
            runtime_epoch=self._runtime_epoch,
        )


__all__ = ["ProjectResolver", "WAWClaudeLifecycleExecutor"]
