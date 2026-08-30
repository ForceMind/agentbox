"""Fixed command contract for the WAW Claude managed process.

This module builds an immutable command specification only.  It never starts a
process and accepts no caller-controlled executable, argv, environment, PID or
shell string.  Runtime adapters must perform the actual launch through their
existing controlled process/tmux boundary.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from agentbox_core.waw import AgentType, validate_project_id, validate_workspace_id, workspace_id

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.process import ExecutableIdentity, inspect_executable
from agentbox_runtime.project import ProjectRegistry

_MAX_MARKER_LENGTH = 192
_MARKER = re.compile(r"\Awaw-v1:wri_[0-9a-f]{32}:[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class WAWClaudeCommand:
    """Exact immutable command and identity supplied to a Runtime adapter."""

    workspace_id: str
    project_id: str
    cwd: Path
    executable: ExecutableIdentity
    argv: tuple[str, ...]
    managed_marker: str

    def __post_init__(self) -> None:
        validate_workspace_id(self.workspace_id)
        validate_project_id(self.project_id)
        if workspace_id(self.project_id, AgentType.CLAUDE) != self.workspace_id:
            raise RuntimeOperationError(
                "WAW_WORKSPACE_MISMATCH",
                "Workspace identity is not bound to the Claude Project",
                category="validation",
            )
        if self.argv != ("remote-control",):
            raise RuntimeOperationError(
                "WAW_COMMAND_INVALID", "Claude command arguments are fixed", category="validation"
            )
        if (
            not self.cwd.is_absolute()
            or not self.cwd.is_dir()
            or self.cwd.is_symlink()
            or self.cwd.stat().st_uid != os.geteuid()
            or self.cwd.stat().st_mode & 0o022
        ):
            raise RuntimeOperationError(
                "WAW_PROJECT_INVALID", "Project working directory is invalid", category="validation"
            )
        if (
            not self.managed_marker
            or len(self.managed_marker) > _MAX_MARKER_LENGTH
            or not _MARKER.fullmatch(self.managed_marker)
        ):
            raise RuntimeOperationError(
                "WAW_MARKER_INVALID", "Managed session marker is invalid", category="validation"
            )
        try:
            current = inspect_executable(self.executable.path, error_prefix="CLAUDE")
        except RuntimeOperationError:
            raise
        if current != self.executable or self.executable.path.name != "claude":
            raise RuntimeOperationError(
                "WAW_EXECUTABLE_INVALID",
                "Claude executable provenance is invalid",
                category="validation",
            )


def build_claude_command(
    *,
    registry: ProjectRegistry,
    project_id: str,
    workspace_id: str,
    executable: ExecutableIdentity,
    managed_marker: str,
) -> WAWClaudeCommand:
    """Resolve one formal Project and return the fixed Claude command contract."""

    if AgentType.CLAUDE.value != "claude":  # defensive closed-contract assertion
        raise RuntimeOperationError(
            "WAW_AGENT_TYPE_INVALID", "Claude agent contract is unavailable", category="broken"
        )
    project = registry.resolve(project_id)
    return WAWClaudeCommand(
        workspace_id=workspace_id,
        project_id=project.project_id,
        cwd=project.path,
        executable=executable,
        argv=("remote-control",),
        managed_marker=managed_marker,
    )


__all__ = ["WAWClaudeCommand", "build_claude_command"]
