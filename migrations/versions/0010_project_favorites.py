"""Add per-admin Project favorite metadata with revision/CAS storage.

Revision ID: 0010_project_favorites
Revises: 0009_waw_project_binding_ledger
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_project_favorites"
down_revision = "0009_waw_project_binding_ledger"
branch_labels = None
depends_on = None

_UTC6_GLOB = (
    "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] "
    "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
    "[0-9][0-9][0-9][0-9][0-9][0-9]"
)


def _utc6(column: str) -> str:
    year = f"CAST(substr({column},1,4) AS INTEGER)"
    month = f"CAST(substr({column},6,2) AS INTEGER)"
    day = f"CAST(substr({column},9,2) AS INTEGER)"
    max_day = (
        f"CASE WHEN {month} IN (1,3,5,7,8,10,12) THEN 31 "
        f"WHEN {month} IN (4,6,9,11) THEN 30 WHEN {month}=2 THEN "
        f"CASE WHEN ({year}%4=0 AND ({year}%100<>0 OR {year}%400=0)) "
        "THEN 29 ELSE 28 END ELSE 0 END"
    )
    return (
        f"length({column})=26 AND {column} GLOB '{_UTC6_GLOB}' "
        f"AND {year} BETWEEN 1 AND 9999 AND {month} BETWEEN 1 AND 12 "
        f"AND {day} BETWEEN 1 AND ({max_day}) "
        f"AND CAST(substr({column},12,2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND CAST(substr({column},15,2) AS INTEGER) BETWEEN 0 AND 59 "
        f"AND CAST(substr({column},18,2) AS INTEGER) BETWEEN 0 AND 59"
    )


def upgrade() -> None:
    op.create_table(
        "project_favorites",
        sa.Column("admin_user_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("favorite IN (0,1)", name="ck_project_favorites_boolean"),
        sa.CheckConstraint("revision >= 1", name="ck_project_favorites_revision"),
        sa.CheckConstraint(_utc6("updated_at"), name="ck_project_favorites_updated_at"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("admin_user_id", "project_id"),
    )


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM project_favorites")).scalar_one()
    if count:
        raise RuntimeError("Project favorite rows must be preserved before downgrade")
    op.drop_table("project_favorites")
