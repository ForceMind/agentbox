"""Persist the last verified WAW Runtime epoch.

Revision ID: 0008_waw_runtime_epoch_fence
Revises: 0007_waw_host_identity_fence
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_waw_runtime_epoch_fence"
down_revision = "0007_waw_host_identity_fence"
branch_labels = None
depends_on = None


_CHECK = (
    "last_runtime_epoch IS NULL OR ("
    "length(last_runtime_epoch) BETWEEN 1 AND 20 AND "
    "last_runtime_epoch NOT GLOB '*[^0-9]*' AND "
    "substr(last_runtime_epoch,1,1) BETWEEN '1' AND '9' AND "
    "(length(last_runtime_epoch) < 20 OR "
    "last_runtime_epoch <= '18446744073709551615'))"
)


def upgrade() -> None:
    with op.batch_alter_table("waw_runtime_host_installations", recreate="always") as batch:
        batch.add_column(sa.Column("last_runtime_epoch", sa.String(length=20), nullable=True))
        batch.create_check_constraint("ck_waw_runtime_hosts_last_epoch", _CHECK)


def downgrade() -> None:
    with op.batch_alter_table("waw_runtime_host_installations", recreate="always") as batch:
        batch.drop_constraint("ck_waw_runtime_hosts_last_epoch", type_="check")
        batch.drop_column("last_runtime_epoch")
