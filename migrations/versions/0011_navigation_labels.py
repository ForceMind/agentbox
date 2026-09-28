"""Add per-admin navigation labels and ordered formal Project assignments.

Revision ID: 0011_navigation_labels
Revises: 0010_project_favorites
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_navigation_labels"
down_revision = "0010_project_favorites"
branch_labels = None
depends_on = None

_UTC6_GLOB = (
    "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] "
    "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
    "[0-9][0-9][0-9][0-9][0-9][0-9]"
)
_COLOR_CHECK = (
    "color IN ('violet','sky','emerald','orange','pink'," "'indigo','teal','red','amber','blue')"
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
        "navigation_labels",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("admin_user_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("name_key", sa.String(length=128), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 64", name="ck_navigation_labels_name"),
        sa.CheckConstraint("length(name_key) BETWEEN 1 AND 128", name="ck_navigation_labels_key"),
        sa.CheckConstraint(_COLOR_CHECK, name="ck_navigation_labels_color"),
        sa.CheckConstraint(
            "revision BETWEEN 1 AND 9007199254740991", name="ck_navigation_labels_revision"
        ),
        sa.CheckConstraint(_utc6("created_at"), name="ck_navigation_labels_created_at"),
        sa.CheckConstraint(_utc6("updated_at"), name="ck_navigation_labels_updated_at"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("admin_user_id", "id", name="uq_navigation_labels_owner_id"),
        sa.UniqueConstraint("admin_user_id", "name_key", name="uq_navigation_labels_name_key"),
    )
    op.create_table(
        "project_label_sets",
        sa.Column("admin_user_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision BETWEEN 1 AND 9007199254740991", name="ck_project_label_sets_revision"
        ),
        sa.CheckConstraint(_utc6("updated_at"), name="ck_project_label_sets_updated_at"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("admin_user_id", "project_id"),
    )
    op.create_table(
        "project_label_assignments",
        sa.Column("admin_user_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("label_id", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_project_label_assignments_position"),
        sa.ForeignKeyConstraint(
            ["admin_user_id", "project_id"],
            ["project_label_sets.admin_user_id", "project_label_sets.project_id"],
            ondelete="CASCADE",
            name="fk_project_label_assignments_set",
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id", "label_id"],
            ["navigation_labels.admin_user_id", "navigation_labels.id"],
            ondelete="CASCADE",
            name="fk_project_label_assignments_label",
        ),
        sa.PrimaryKeyConstraint("admin_user_id", "project_id", "label_id"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("project_label_assignments", "project_label_sets", "navigation_labels"):
        count = connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError("Navigation label rows must be preserved before downgrade")
    op.drop_table("project_label_assignments")
    op.drop_table("project_label_sets")
    op.drop_table("navigation_labels")
