"""Bind WAW rows to the exact host installation revision.

Revision ID: 0007_waw_host_identity_fence
Revises: 0006_waw_workspace_metadata
"""

from __future__ import annotations

from alembic import op

revision = "0007_waw_host_identity_fence"
down_revision = "0006_waw_workspace_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite requires table recreation for foreign-key shape changes.  The
    # existing columns and constraints are preserved while replacing the
    # id-only host FK with an immutable (id, revision) identity fence.
    with op.batch_alter_table("waw_agent_workspace_sessions", recreate="always") as batch:
        batch.drop_constraint("fk_waw_sessions_runtime_host", type_="foreignkey")
        batch.create_foreign_key(
            "fk_waw_sessions_runtime_host_identity",
            "waw_runtime_host_installations",
            ["runtime_host_installation_id", "runtime_host_installation_revision"],
            ["id", "revision"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("waw_workspace_stop_operations", recreate="always") as batch:
        batch.create_foreign_key(
            "fk_waw_stops_runtime_host_identity",
            "waw_runtime_host_installations",
            ["runtime_host_installation_id", "runtime_host_installation_revision"],
            ["id", "revision"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("waw_workspace_stop_operations", recreate="always") as batch:
        batch.drop_constraint("fk_waw_stops_runtime_host_identity", type_="foreignkey")
    with op.batch_alter_table("waw_agent_workspace_sessions", recreate="always") as batch:
        batch.drop_constraint("fk_waw_sessions_runtime_host_identity", type_="foreignkey")
        batch.create_foreign_key(
            "fk_waw_sessions_runtime_host",
            "waw_runtime_host_installations",
            ["runtime_host_installation_id"],
            ["id"],
            ondelete="RESTRICT",
        )
