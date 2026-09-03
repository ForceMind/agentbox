"""Closed command union accepted by the WAW Runtime supervisor seam."""

from __future__ import annotations

from typing import TypeAlias

from agentbox_core.waw import AgentType

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_command import WAWClaudeCommand

WAWManagedCommand: TypeAlias = WAWClaudeCommand | WAWCodexCommand


def validate_managed_command(command: object) -> WAWManagedCommand:
    """Revalidate one of the two concrete fixed commands before Runtime use."""

    if type(command) is WAWClaudeCommand:
        WAWClaudeCommand.__post_init__(command)
        return command
    if type(command) is WAWCodexCommand:
        WAWCodexCommand.__post_init__(command)
        return command
    raise RuntimeOperationError(
        "WAW_COMMAND_INVALID",
        "Runtime command contract is not a supported WAW command",
        category="validation",
    )


def managed_command_agent_type(command: WAWManagedCommand) -> AgentType:
    """Return the fixed AgentType encoded by the concrete command class."""

    if type(command) is WAWClaudeCommand:
        return AgentType.CLAUDE
    if type(command) is WAWCodexCommand:
        return AgentType.CODEX
    raise RuntimeOperationError(
        "WAW_COMMAND_INVALID", "Runtime command type is unsupported", category="validation"
    )


__all__ = [
    "WAWClaudeCommand",
    "WAWCodexCommand",
    "WAWManagedCommand",
    "managed_command_agent_type",
    "validate_managed_command",
]
