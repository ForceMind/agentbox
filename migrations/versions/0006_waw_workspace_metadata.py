"""Add durable non-secret Web Agent Workspace metadata.

Revision ID: 0006_waw_workspace_metadata
Revises: 0005_phase11_control_plane_ownership_approval
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_waw_workspace_metadata"
down_revision = "0005_phase11_control_plane_ownership_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waw_runtime_host_installations",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("runtime_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(id)=36 AND substr(id,1,4)='wri_' AND substr(id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_runtime_hosts_id",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_waw_runtime_hosts_revision"),
        sa.CheckConstraint(
            "runtime_type = 'agentbox-runtime-linux-v1'", name="ck_waw_runtime_hosts_type"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "revision", name="uq_waw_runtime_hosts_identity"),
    )
    op.create_table(
        "waw_agent_workspace_sessions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("authorization_scope", sa.String(length=128), nullable=False),
        sa.Column("runtime_host_installation_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_host_installation_revision", sa.Integer(), nullable=False),
        sa.Column("runtime_type", sa.String(length=32), nullable=False),
        sa.Column("agent_type", sa.String(length=8), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("runtime_session_name", sa.String(length=80), nullable=False),
        sa.Column("runtime_marker", sa.String(length=192), nullable=False),
        sa.Column("executable_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("binding_revision", sa.Integer(), nullable=False),
        sa.Column("binding_digest", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("reconciliation_state", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "length(id)=36 AND substr(id,1,4)='aws_' AND substr(id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_id",
        ),
        sa.CheckConstraint(
            "length(project_id)=36 AND substr(project_id,1,4)='prj_' AND substr(project_id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_project_id",
        ),
        sa.CheckConstraint(
            "authorization_scope <> '' AND length(authorization_scope) <= 128",
            name="ck_waw_sessions_scope",
        ),
        sa.CheckConstraint(
            "length(runtime_host_installation_id)=36 AND substr(runtime_host_installation_id,1,4)='wri_' AND substr(runtime_host_installation_id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_host_id",
        ),
        sa.CheckConstraint("runtime_host_installation_revision >= 1", name="ck_waw_sessions_host_revision"),
        sa.CheckConstraint(
            "runtime_type = 'agentbox-runtime-linux-v1'", name="ck_waw_sessions_runtime_type"
        ),
        sa.CheckConstraint("agent_type IN ('claude','codex')", name="ck_waw_sessions_agent_type"),
        sa.CheckConstraint(
            "state IN ('STARTING','RUNNING','NEEDS_INTERACTION','TRUST_REQUIRED','LOGIN_REQUIRED','STOPPING','EXITED','STOPPED','MISSING','COLLISION','BROKEN','UNKNOWN')",
            name="ck_waw_sessions_state",
        ),
        sa.CheckConstraint("generation >= 1", name="ck_waw_sessions_generation"),
        sa.CheckConstraint("revision >= 1", name="ck_waw_sessions_revision"),
        sa.CheckConstraint("binding_revision >= 1", name="ck_waw_sessions_binding_revision"),
        sa.CheckConstraint(
            "length(binding_digest)=64 AND binding_digest NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_binding_digest",
        ),
        sa.CheckConstraint(
            "length(runtime_session_name) BETWEEN 1 AND 80", name="ck_waw_sessions_session_name"
        ),
        sa.CheckConstraint("length(runtime_marker) BETWEEN 1 AND 192", name="ck_waw_sessions_marker"),
        sa.CheckConstraint(
            "length(executable_fingerprint)=64 AND executable_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_sessions_executable_fingerprint",
        ),
        sa.CheckConstraint(
            "exit_code IS NULL OR exit_code BETWEEN -128 AND 255", name="ck_waw_sessions_exit_code"
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (length(failure_code) BETWEEN 1 AND 64)",
            name="ck_waw_sessions_failure_code",
        ),
        sa.CheckConstraint(
            "reconciliation_state IN ('authoritative','stopping','missing','collision','exited','reconciliation_required','unknown')",
            name="ck_waw_sessions_reconciliation_state",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT", name="fk_waw_sessions_project"
        ),
        sa.ForeignKeyConstraint(
            ["runtime_host_installation_id"],
            ["waw_runtime_host_installations.id"],
            ondelete="RESTRICT",
            name="fk_waw_sessions_runtime_host",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "agent_type", name="uq_waw_sessions_project_agent"),
        sa.UniqueConstraint(
            "runtime_session_name", name="uq_waw_sessions_runtime_session_name"
        ),
    )
    op.create_index("ix_waw_sessions_state", "waw_agent_workspace_sessions", ["state"])


def downgrade() -> None:
    op.drop_index("ix_waw_sessions_state", table_name="waw_agent_workspace_sessions")
    op.drop_table("waw_agent_workspace_sessions")
    op.drop_table("waw_runtime_host_installations")
