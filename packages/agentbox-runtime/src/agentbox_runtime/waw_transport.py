"""Bounded Claude Web Agent Workspace transport over the Runtime tmux adapter.

This adapter is intentionally narrower than :class:`ClaudeSessionManager`.
Its caller supplies only a previously validated :class:`WAWClaudeCommand` and
bounded PTY geometry/bytes.  The adapter derives the tmux target from the
formal Project identity, never accepts a shell string, executable, path, or
argv, and returns typed lifecycle evidence that the supervisor can fence.

The methods are synchronous because ``WAWSupervisor`` is a synchronous state
machine.  ``TmuxAdapter`` itself is asynchronous; :func:`_resolve` bridges the
two without changing the existing adapter or supervisor contracts.  If a
caller is already running an event loop, the bounded tmux call is run on a
short-lived worker thread rather than nesting an event loop in that thread.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from agentbox_core.waw import AgentType, validate_positive_u64, validate_workspace_id

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity
from agentbox_runtime.tmux import TmuxAdapter
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_pty import PtyGeometry, validate_input
from agentbox_runtime.waw_supervisor import (
    RuntimeStartEvidence,
    RuntimeStopEvidence,
    SupervisorState,
)

_T = TypeVar("_T")


class _TmuxOperations(Protocol):
    """The fixed subset of TmuxAdapter used by this transport."""

    async def has_session(self, session_name: str) -> bool: ...

    async def is_managed(self, session_name: str, managed_marker: str) -> bool: ...

    async def pane_dead(self, session_name: str) -> bool: ...

    async def create_session(
        self,
        session_name: str,
        *,
        cwd: Path,
        command: ExecutableIdentity,
        managed_marker: str,
    ) -> None: ...

    async def kill_session(self, session_name: str) -> bool: ...

    async def write_input(self, session_name: str, data: bytes) -> None: ...

    async def resize_window(self, session_name: str, *, columns: int, rows: int) -> None: ...


@dataclass(frozen=True)
class _TransportBinding:
    workspace_id: str
    project_id: str
    generation: int
    managed_marker: str
    session_name: str


class WAWTmuxTransport:
    """One fixed Claude Runtime transport for one workspace generation.

    ``workspace_id`` and ``generation`` are constructor-bound by the Runtime
    lifecycle record.  The first start binds the command marker; a caller may
    also pass ``managed_marker`` to require an exact marker before any tmux
    mutation.  A transport cannot be rebound to another Project, workspace,
    generation, or marker after it starts.
    """

    def __init__(
        self,
        *,
        workspace_id: str,
        generation: int,
        tmux: _TmuxOperations | None = None,
        managed_marker: str | None = None,
    ) -> None:
        validate_workspace_id(workspace_id)
        validate_positive_u64(generation, field="generation")
        if managed_marker is not None and not _valid_waw_marker(managed_marker):
            raise RuntimeOperationError(
                "WAW_MARKER_INVALID", "Runtime marker is invalid", category="validation"
            )
        self._workspace_id = workspace_id
        self._generation = generation
        self._expected_marker = managed_marker
        self._tmux: _TmuxOperations = tmux or TmuxAdapter()
        self._binding: _TransportBinding | None = None
        self._geometry: PtyGeometry | None = None
        self._started = False
        self._attached = False
        self._closed = False

    @property
    def session_name(self) -> str | None:
        """Return the derived managed target after start, never caller input."""

        return self._binding.session_name if self._binding is not None else None

    @property
    def attached(self) -> bool:
        return self._attached

    def start(self, command: WAWClaudeCommand, geometry: PtyGeometry) -> RuntimeStartEvidence:
        """Create/adopt the exact marked tmux session and return evidence."""

        if self._started or self._closed:
            raise RuntimeOperationError(
                "WAW_START_INVALID",
                "Runtime transport has already started or closed",
                category="conflict",
            )
        self._validate_command(command)
        session_name = _managed_session_name(command.project_id)
        marker = command.managed_marker
        if self._expected_marker is not None and marker != self._expected_marker:
            raise RuntimeOperationError(
                "WAW_MARKER_MISMATCH",
                "Runtime marker does not match the generation binding",
                category="conflict",
            )
        binding = _TransportBinding(
            workspace_id=command.workspace_id,
            project_id=command.project_id,
            generation=self._generation,
            managed_marker=marker,
            session_name=session_name,
        )
        try:
            exists = _resolve(self._tmux.has_session(session_name))
            if exists:
                self._require_managed(binding)
            else:
                _resolve(
                    self._tmux.create_session(
                        session_name,
                        cwd=command.cwd,
                        command=command.executable,
                        managed_marker=marker,
                    )
                )
                if not _resolve(self._tmux.has_session(session_name)):
                    raise RuntimeOperationError(
                        "WAW_START_UNCONFIRMED",
                        "Runtime session was not observable after creation",
                        category="conflict",
                    )
                self._require_managed(binding)
            if _resolve(self._tmux.pane_dead(session_name)):
                raise RuntimeOperationError(
                    "WAW_START_UNCONFIRMED",
                    "Managed Runtime pane exited before readiness was observed",
                    category="conflict",
                )
            _resolve(
                self._tmux.resize_window(session_name, columns=geometry.columns, rows=geometry.rows)
            )
        except RuntimeOperationError:
            raise
        except Exception as exc:
            raise RuntimeOperationError(
                "WAW_START_FAILED", "Runtime tmux transport could not start", category="unavailable"
            ) from exc
        self._binding = binding
        self._geometry = geometry
        self._started = True
        # The supervisor performs the authoritative attachment check before
        # invoking write/resize/detach.  The transport's local flag therefore
        # represents an available PTY binding immediately after start; it is
        # cleared only after the positive detach acknowledgement or stop.
        self._attached = True
        return RuntimeStartEvidence(
            workspace_id=binding.workspace_id,
            generation=binding.generation,
            managed_marker=binding.managed_marker,
            state=SupervisorState.RUNNING,
            ready=True,
        )

    def write(self, data: bytes) -> None:
        """Paste bounded opaque bytes to the exact managed pane."""

        self._require_started()
        payload = validate_input(data)
        binding = self._require_binding()
        try:
            self._require_managed(binding)
            _resolve(self._tmux.write_input(binding.session_name, payload))
        except RuntimeOperationError:
            raise
        except Exception as exc:
            raise RuntimeOperationError(
                "WAW_INPUT_UNCERTAIN",
                "Runtime could not confirm PTY input delivery",
                category="broken",
            ) from exc

    def detach(self) -> bool:
        """Release the local attachment only after positive managed-session ACK."""

        self._require_started()
        if not self._attached:
            return False
        binding = self._require_binding()
        try:
            if not _resolve(self._tmux.has_session(binding.session_name)):
                return False
            if not _resolve(self._tmux.is_managed(binding.session_name, binding.managed_marker)):
                return False
        except Exception:
            return False
        # tmux session persistence is the detach primitive: do not detach all
        # tmux clients globally.  The positive observation above is the ACK
        # that this WAW attachment was released while the Runtime survives.
        self._attached = False
        return True

    def resize(self, geometry: PtyGeometry) -> None:
        self._require_started()
        binding = self._require_binding()
        try:
            self._require_managed(binding)
            _resolve(
                self._tmux.resize_window(
                    binding.session_name, columns=geometry.columns, rows=geometry.rows
                )
            )
        except RuntimeOperationError:
            raise
        except Exception as exc:
            raise RuntimeOperationError(
                "WAW_RESIZE_FAILED", "Runtime could not confirm PTY resize", category="broken"
            ) from exc
        self._geometry = geometry

    def stop(self) -> RuntimeStopEvidence:
        """Kill only the exact managed session and prove zero remaining members."""

        self._require_started()
        binding = self._require_binding()
        try:
            if not _resolve(self._tmux.has_session(binding.session_name)):
                raise RuntimeOperationError(
                    "WAW_STOP_UNCONFIRMED",
                    "Managed Runtime session disappeared before stop",
                    category="conflict",
                )
            self._require_managed(binding)
            killed = _resolve(self._tmux.kill_session(binding.session_name))
            closed = bool(killed) and not _resolve(self._tmux.has_session(binding.session_name))
        except RuntimeOperationError:
            raise
        except Exception as exc:
            raise RuntimeOperationError(
                "WAW_STOP_FAILED", "Runtime tmux transport could not stop", category="broken"
            ) from exc
        if closed:
            self._attached = False
            self._closed = True
            self._started = False
        return RuntimeStopEvidence(
            workspace_id=binding.workspace_id,
            generation=binding.generation,
            managed_marker=binding.managed_marker,
            closed=closed,
            remaining_members=0 if closed else 1,
        )

    def _validate_command(self, command: WAWClaudeCommand) -> None:
        if not isinstance(command, WAWClaudeCommand):
            raise RuntimeOperationError(
                "WAW_COMMAND_INVALID", "Runtime command contract is invalid", category="validation"
            )
        if command.workspace_id != self._workspace_id:
            raise RuntimeOperationError(
                "WAW_WORKSPACE_MISMATCH",
                "Runtime command workspace does not match",
                category="validation",
            )
        if command.argv != ("remote-control",):
            raise RuntimeOperationError(
                "WAW_COMMAND_INVALID", "Claude command arguments are fixed", category="validation"
            )
        if not _valid_waw_marker(command.managed_marker):
            raise RuntimeOperationError(
                "WAW_MARKER_INVALID", "Runtime marker is invalid", category="validation"
            )

    def _require_managed(self, binding: _TransportBinding) -> None:
        if not _resolve(self._tmux.is_managed(binding.session_name, binding.managed_marker)):
            raise RuntimeOperationError(
                "WAW_SESSION_UNMANAGED",
                "Runtime session marker does not match",
                category="forbidden",
            )

    def _require_started(self) -> None:
        if not self._started or self._closed or self._binding is None:
            raise RuntimeOperationError(
                "WAW_TRANSPORT_INVALID", "Runtime transport is not running", category="conflict"
            )

    def _require_binding(self) -> _TransportBinding:
        binding = self._binding
        if binding is None:
            raise RuntimeOperationError(
                "WAW_TRANSPORT_INVALID", "Runtime transport has no binding", category="conflict"
            )
        return binding


def _managed_session_name(project_id: str) -> str:
    """Derive the closed WAW Claude target from Project identity."""

    # Importing the domain helper lazily keeps this module's public import
    # surface independent from legacy Claude session naming.
    from agentbox_core.waw import managed_session_name

    return managed_session_name(project_id, AgentType.CLAUDE)


def _valid_waw_marker(marker: str) -> bool:
    import re

    return bool(re.fullmatch(r"waw-v1:wri_[0-9a-f]{32}:[0-9a-f]{32}", marker))


async def _await(value: Awaitable[_T]) -> _T:
    return await value


def _resolve(value: Awaitable[_T]) -> _T:
    """Resolve an async TmuxAdapter method for the sync supervisor boundary."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await(value))

    result: list[_T] = []
    failure: list[BaseException] = []

    def run() -> None:
        try:
            result.append(asyncio.run(_await(value)))
        except BaseException as exc:  # re-raise on the caller thread
            failure.append(exc)

    thread = threading.Thread(target=run, name="agentbox-waw-tmux", daemon=True)
    thread.start()
    thread.join(timeout=15)
    if thread.is_alive():
        raise RuntimeOperationError(
            "WAW_TRANSPORT_TIMEOUT", "Runtime tmux operation timed out", category="timeout"
        )
    if failure:
        raise failure[0]
    if not result:
        raise RuntimeOperationError(
            "WAW_TRANSPORT_FAILED", "Runtime tmux operation returned no result", category="broken"
        )
    return result[0]


# Naming aliases make the bounded role explicit to callers while retaining one
# implementation and one custom-agent discoverable class name.
TmuxWAWTransport = WAWTmuxTransport

__all__ = ["TmuxWAWTransport", "WAWTmuxTransport"]
