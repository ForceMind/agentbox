"""Fixed command contract for a WAW Codex managed process.

The command is intentionally narrower than the existing Codex Remote adapter:
an interactive WAW Codex process is scoped by the Runtime-resolved Project cwd
and has no caller-provided arguments.  The managed marker is metadata consumed
by the Runtime lifecycle/transport boundary; it is never a shell fragment or
an environment value.
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
class WAWCodexCommand:
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
        if workspace_id(self.project_id, AgentType.CODEX) != self.workspace_id:
            raise RuntimeOperationError(
                "WAW_WORKSPACE_MISMATCH",
                "Workspace identity is not bound to the Codex Project",
                category="validation",
            )
        # Codex interactive mode is selected by the executable itself.  Project
        # scope comes exclusively from the validated cwd; no flags or caller
        # arguments may widen the workspace boundary.
        if self.argv != ():
            raise RuntimeOperationError(
                "WAW_COMMAND_INVALID", "Codex command arguments are fixed", category="validation"
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
            current = inspect_executable(self.executable.path, error_prefix="CODEX")
        except RuntimeOperationError:
            raise
        if current != self.executable or self.executable.path.name != "codex":
            raise RuntimeOperationError(
                "WAW_EXECUTABLE_INVALID",
                "Codex executable provenance is invalid",
                category="validation",
            )


def build_codex_command(
    *,
    registry: ProjectRegistry,
    project_id: str,
    workspace_id: str,
    executable: ExecutableIdentity,
    managed_marker: str,
) -> WAWCodexCommand:
    """Resolve one formal Project and return the fixed Codex command contract."""

    if AgentType.CODEX.value != "codex":  # defensive closed-contract assertion
        raise RuntimeOperationError(
            "WAW_AGENT_TYPE_INVALID", "Codex agent contract is unavailable", category="broken"
        )
    project = registry.resolve(project_id)
    return WAWCodexCommand(
        workspace_id=workspace_id,
        project_id=project.project_id,
        cwd=project.path,
        executable=executable,
        argv=(),
        managed_marker=managed_marker,
    )


__all__ = ["WAWCodexCommand", "build_codex_command"]
