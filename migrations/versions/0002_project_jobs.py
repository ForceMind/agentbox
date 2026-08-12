"""Add formal Projects and durable Jobs.

Revision ID: 0002_project_jobs
Revises: 0001_control_plane_foundation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_project_jobs"
down_revision = "0001_control_plane_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("relative_path", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("repository_url", sa.String(length=512), nullable=True),
        sa.Column("default_branch", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_archived_at", "projects", ["archived_at"])
    op.create_index("ix_projects_state", "projects", ["state"])
    op.create_index("uq_projects_relative_path", "projects", ["relative_path"], unique=True)
    op.create_index("uq_projects_slug_active", "projects", ["slug"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=80), nullable=True),
        sa.Column("project_id", sa.String(length=40), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(length=48), nullable=True),
        sa.Column("result_summary", sa.String(length=512), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_summary", sa.String(length=512), nullable=True),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key_digest", sa.String(length=64), nullable=False),
        sa.Column("resource_lock_key", sa.String(length=96), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=80), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_id", sa.String(length=72), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key_digest"),
    )
    for name, columns in (
        ("ix_jobs_lease_expires_at", ["lease_expires_at"]),
        ("ix_jobs_project_id", ["project_id"]),
        ("ix_jobs_request_id", ["request_id"]),
        ("ix_jobs_resource_lock_key", ["resource_lock_key"]),
        ("ix_jobs_status", ["status"]),
        ("ix_jobs_target_id", ["target_id"]),
        ("ix_jobs_type", ["type"]),
    ):
        op.create_index(name, "jobs", columns)

    op.create_table(
        "job_events",
        sa.Column("sequence", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(length=48), nullable=True),
        sa.Column("summary", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sequence"),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_events_job_id", table_name="job_events")
    op.drop_table("job_events")
    for name in (
        "ix_jobs_type",
        "ix_jobs_target_id",
        "ix_jobs_status",
        "ix_jobs_resource_lock_key",
        "ix_jobs_request_id",
        "ix_jobs_project_id",
        "ix_jobs_lease_expires_at",
    ):
        op.drop_index(name, table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("uq_projects_slug_active", table_name="projects")
    op.drop_index("uq_projects_relative_path", table_name="projects")
    op.drop_index("ix_projects_state", table_name="projects")
    op.drop_index("ix_projects_archived_at", table_name="projects")
    op.drop_table("projects")
