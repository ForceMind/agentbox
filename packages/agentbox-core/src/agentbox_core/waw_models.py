"""Durable, non-secret Control Plane metadata for Web Agent Workspace.

The ORM records in this module intentionally contain identity, lifecycle and
fencing metadata only.  Terminal bytes, tickets, credentials and process
details remain outside the database row.
"""

# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentbox_core.models import Base

_AGENT_TYPES = "('claude','codex')"
_WORKSPACE_STATES = "('STARTING','RUNNING','NEEDS_INTERACTION','TRUST_REQUIRED','LOGIN_REQUIRED','STOPPING','EXITED','STOPPED','MISSING','COLLISION','BROKEN','UNKNOWN')"
_RECONCILIATION_STATES = "('authoritative','stopping','missing','collision','exited','reconciliation_required','unknown')"


class RuntimeHostInstallation(Base):
    """WAW-only public host identity; never a Provider runtime row."""

    __tablename__ = "waw_runtime_host_installations"
    __table_args__ = (
        CheckConstraint(
            "length(id)=36 AND substr(id,1,4)='wri_' AND substr(id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_runtime_hosts_id",
        ),
        CheckConstraint("revision >= 1", name="ck_waw_runtime_hosts_revision"),
        CheckConstraint(
            "runtime_type = 'agentbox-runtime-linux-v1'", name="ck_waw_runtime_hosts_type"
        ),
        UniqueConstraint("id", "revision", name="uq_waw_runtime_hosts_identity"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentWorkspaceSessionRecord(Base):
    """One durable Project/AgentType workspace identity and lifecycle row."""

    __tablename__ = "waw_agent_workspace_sessions"
    __table_args__ = (
        CheckConstraint(
            "length(id)=36 AND substr(id,1,4)='aws_' AND substr(id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_id",
        ),
        CheckConstraint(
            "length(project_id)=36 AND substr(project_id,1,4)='prj_' AND substr(project_id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_project_id",
        ),
        CheckConstraint(
            "authorization_scope <> '' AND length(authorization_scope) <= 128",
            name="ck_waw_sessions_scope",
        ),
        CheckConstraint(
            "length(runtime_host_installation_id)=36 AND substr(runtime_host_installation_id,1,4)='wri_' AND substr(runtime_host_installation_id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_host_id",
        ),
        CheckConstraint(
            "runtime_host_installation_revision >= 1", name="ck_waw_sessions_host_revision"
        ),
        CheckConstraint(
            "runtime_type = 'agentbox-runtime-linux-v1'", name="ck_waw_sessions_runtime_type"
        ),
        CheckConstraint(f"agent_type IN {_AGENT_TYPES}", name="ck_waw_sessions_agent_type"),
        CheckConstraint(f"state IN {_WORKSPACE_STATES}", name="ck_waw_sessions_state"),
        CheckConstraint("generation >= 1", name="ck_waw_sessions_generation"),
        CheckConstraint("revision >= 1", name="ck_waw_sessions_revision"),
        CheckConstraint("binding_revision >= 1", name="ck_waw_sessions_binding_revision"),
        CheckConstraint(
            "length(binding_digest)=64 AND binding_digest NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_binding_digest",
        ),
        CheckConstraint(
            "length(runtime_session_name) BETWEEN 1 AND 80", name="ck_waw_sessions_session_name"
        ),
        CheckConstraint("length(runtime_marker) BETWEEN 1 AND 192", name="ck_waw_sessions_marker"),
        CheckConstraint(
            "length(executable_fingerprint)=64 AND executable_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_executable_fingerprint",
        ),
        CheckConstraint(
            "exit_code IS NULL OR exit_code BETWEEN -128 AND 255", name="ck_waw_sessions_exit_code"
        ),
        CheckConstraint(
            "failure_code IS NULL OR (length(failure_code) BETWEEN 1 AND 64 AND failure_code NOT GLOB '*[^[:cntrl:]]*')",
            name="ck_waw_sessions_failure_code",
        ),
        CheckConstraint(
            f"reconciliation_state IN {_RECONCILIATION_STATES}",
            name="ck_waw_sessions_reconciliation_state",
        ),
        UniqueConstraint("project_id", "agent_type", name="uq_waw_sessions_project_agent"),
        ForeignKeyConstraint(
            ["runtime_host_installation_id", "runtime_host_installation_revision"],
            [
                "waw_runtime_host_installations.id",
                "waw_runtime_host_installations.revision",
            ],
            ondelete="RESTRICT",
            name="fk_waw_sessions_runtime_host_identity",
        ),
        Index("ix_waw_sessions_state", "state"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    runtime_host_installation_id: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    runtime_host_installation_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(8), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    runtime_session_name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    runtime_marker: Mapped[str] = mapped_column(String(192), nullable=False)
    executable_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    reconciliation_state: Mapped[str] = mapped_column(String(32), nullable=False)


class WorkspaceStopOperationRecord(Base):
    """Durable exact-Stop intent; contains no PID, path, command, or secret."""

    __tablename__ = "waw_workspace_stop_operations"
    __table_args__ = (
        CheckConstraint(
            "length(id)=36 AND substr(id,1,4)='wso_' AND substr(id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_stops_id",
        ),
        CheckConstraint(
            "length(workspace_id)=36 AND substr(workspace_id,1,4)='aws_' AND substr(workspace_id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_stops_workspace_id",
        ),
        CheckConstraint("generation >= 1", name="ck_waw_stops_generation"),
        CheckConstraint("binding_revision >= 1", name="ck_waw_stops_binding_revision"),
        CheckConstraint(
            "length(binding_digest)=64 AND binding_digest NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_stops_binding_digest",
        ),
        CheckConstraint(
            "result IN ('PENDING','STOPPED','RECONCILIATION_REQUIRED','TIMEOUT')",
            name="ck_waw_stops_result",
        ),
        CheckConstraint("length(failure_code) <= 64", name="ck_waw_stops_failure_code"),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["waw_agent_workspace_sessions.id"],
            ondelete="RESTRICT",
            name="fk_waw_stops_workspace",
        ),
        ForeignKeyConstraint(
            ["runtime_host_installation_id", "runtime_host_installation_revision"],
            [
                "waw_runtime_host_installations.id",
                "waw_runtime_host_installations.revision",
            ],
            ondelete="RESTRICT",
            name="fk_waw_stops_runtime_host_identity",
        ),
        UniqueConstraint(
            "workspace_id", "generation", "binding_revision", name="uq_waw_stops_generation"
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), nullable=False)
    project_id: Mapped[str] = mapped_column(String(40), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(8), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_host_installation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_host_installation_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "AgentWorkspaceSessionRecord",
    "RuntimeHostInstallation",
    "WorkspaceStopOperationRecord",
]
