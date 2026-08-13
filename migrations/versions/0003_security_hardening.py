"""Persist bounded login throttling state.

Revision ID: 0003_security_hardening
Revises: 0002_project_jobs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_security_hardening"
down_revision = "0002_project_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limit_buckets",
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("failure_timestamps", sa.JSON(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key_digest"),
    )
    op.create_index(
        "ix_login_rate_limit_buckets_locked_until",
        "login_rate_limit_buckets",
        ["locked_until"],
    )
    op.create_index(
        "ix_login_rate_limit_buckets_updated_at",
        "login_rate_limit_buckets",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_login_rate_limit_buckets_updated_at",
        table_name="login_rate_limit_buckets",
    )
    op.drop_index(
        "ix_login_rate_limit_buckets_locked_until",
        table_name="login_rate_limit_buckets",
    )
    op.drop_table("login_rate_limit_buckets")
