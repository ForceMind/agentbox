"""Fail-closed authorization policy for Web Agent Workspace metadata."""

from __future__ import annotations

from typing import Protocol

from agentbox_core.services import AuthenticatedSession
from agentbox_core.waw_models import AgentWorkspaceSessionRecord


class WorkspaceAuthorizationPolicy(Protocol):
    """Application-supplied policy for a workspace's opaque scope."""

    def allows(
        self,
        authenticated: AuthenticatedSession,
        workspace: AgentWorkspaceSessionRecord,
    ) -> bool: ...


class SingleAdminWorkspacePolicy:
    """Default policy while AgentBox has one administrator authority domain.

    The persisted scope is intentionally not copied into Runtime requests. Any
    future multi-user scope must provide an explicit policy instead of relying
    on an inferred user-to-project mapping.
    """

    def allows(
        self,
        authenticated: AuthenticatedSession,
        workspace: AgentWorkspaceSessionRecord,
    ) -> bool:
        del authenticated
        return workspace.authorization_scope == "admin"


__all__ = ["SingleAdminWorkspacePolicy", "WorkspaceAuthorizationPolicy"]
