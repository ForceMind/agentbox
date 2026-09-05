"""Add the expand-stage WAW Project binding ledger.

Revision ID: 0009_waw_project_binding_ledger
Revises: 0008_waw_runtime_epoch_fence
"""

# ruff: noqa: E501 -- SQL checks and triggers remain auditable literals.

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_waw_project_binding_ledger"
down_revision = "0008_waw_runtime_epoch_fence"
branch_labels = None
depends_on = None


_EVIDENCE_EPOCH_CHECK = (
    "executable_evidence_runtime_epoch IS NULL OR ("
    "length(executable_evidence_runtime_epoch) BETWEEN 1 AND 20 AND "
    "executable_evidence_runtime_epoch NOT GLOB '*[^0-9]*' AND "
    "substr(executable_evidence_runtime_epoch,1,1) BETWEEN '1' AND '9' AND "
    "(length(executable_evidence_runtime_epoch) < 20 OR "
    "executable_evidence_runtime_epoch <= '18446744073709551615'))"
)

_EVIDENCE_CONSISTENCY_CHECK = (
    "(executable_evidence_state = 'UNOBSERVED' AND executable_fingerprint IS NULL "
    "AND executable_evidence_generation IS NULL "
    "AND executable_evidence_runtime_epoch IS NULL) OR "
    "(executable_evidence_state = 'VERIFIED' AND executable_fingerprint IS NOT NULL "
    "AND executable_evidence_generation = generation "
    "AND executable_evidence_runtime_epoch IS NOT NULL) OR "
    "(executable_evidence_state = 'STALE' AND ("
    "(executable_evidence_generation IS NULL AND executable_evidence_runtime_epoch IS NULL) OR "
    "(executable_fingerprint IS NOT NULL AND executable_evidence_generation IS NOT NULL "
    "AND executable_evidence_runtime_epoch IS NOT NULL)))"
)


def upgrade() -> None:
    with op.batch_alter_table("projects", recreate="always") as batch:
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch.create_check_constraint("ck_projects_revision", "revision >= 1")

    with op.batch_alter_table("waw_agent_workspace_sessions", recreate="always") as batch:
        batch.drop_constraint("ck_waw_sessions_executable_fingerprint", type_="check")
        batch.alter_column(
            "executable_fingerprint",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        # STALE is the only truthful expand default for a pre-0009 fingerprint:
        # the old schema stored no Runtime epoch/generation proof.
        batch.add_column(
            sa.Column(
                "executable_evidence_state",
                sa.String(length=16),
                nullable=False,
                server_default="STALE",
            )
        )
        batch.add_column(sa.Column("executable_evidence_generation", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("executable_evidence_runtime_epoch", sa.String(length=20), nullable=True)
        )
        batch.create_check_constraint(
            "ck_waw_sessions_executable_fingerprint",
            "executable_fingerprint IS NULL OR (length(executable_fingerprint)=64 "
            "AND executable_fingerprint NOT GLOB '*[^0-9a-f]*')",
        )
        batch.create_check_constraint(
            "ck_waw_sessions_executable_evidence_state",
            "executable_evidence_state IN ('UNOBSERVED','VERIFIED','STALE')",
        )
        batch.create_check_constraint(
            "ck_waw_sessions_executable_evidence_generation",
            "executable_evidence_generation IS NULL OR executable_evidence_generation >= 1",
        )
        batch.create_check_constraint(
            "ck_waw_sessions_executable_evidence_epoch", _EVIDENCE_EPOCH_CHECK
        )
        batch.create_check_constraint(
            "ck_waw_sessions_executable_evidence_consistency",
            _EVIDENCE_CONSISTENCY_CHECK,
        )

    # Existing non-terminal rows have neither a Project-binding ledger nor
    # executable proof.  Fence them and their durable pending Stop intent in the
    # same migration transaction.  EXITED/STOPPED lifecycle evidence remains
    # terminal; its old executable fingerprint is merely STALE metadata.
    op.execute(
        "UPDATE waw_workspace_stop_operations SET "
        "result='RECONCILIATION_REQUIRED', "
        "failure_code='SCHEMA_MIGRATION_REQUIRED', "
        "updated_at=strftime('%Y-%m-%d %H:%M:%f000','now') "
        "WHERE result='PENDING' AND workspace_id IN ("
        "SELECT id FROM waw_agent_workspace_sessions "
        "WHERE state NOT IN ('EXITED','STOPPED'))"
    )
    op.execute(
        "UPDATE waw_agent_workspace_sessions SET "
        "state='UNKNOWN', reconciliation_state='reconciliation_required', "
        "failure_code='SCHEMA_MIGRATION_REQUIRED', "
        "executable_evidence_state='STALE', "
        "executable_evidence_generation=NULL, "
        "executable_evidence_runtime_epoch=NULL, revision=revision+1 "
        "WHERE state NOT IN ('EXITED','STOPPED')"
    )

    op.create_table(
        "waw_project_bindings",
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("binding_revision", sa.Integer(), nullable=False),
        sa.Column("relative_key", sa.String(length=80), nullable=False),
        sa.Column("project_revision", sa.Integer(), nullable=False),
        sa.Column("binding_digest", sa.String(length=64), nullable=True),
        sa.Column("previous_binding_revision", sa.Integer(), nullable=True),
        sa.Column("previous_binding_digest", sa.String(length=64), nullable=True),
        sa.Column("runtime_host_installation_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_host_installation_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(project_id)=36 AND substr(project_id,1,4)='prj_' "
            "AND substr(project_id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_project_bindings_project_id",
        ),
        sa.CheckConstraint(
            "length(relative_key) BETWEEN 1 AND 80 AND relative_key = trim(relative_key) "
            "AND relative_key NOT IN ('.','..') AND instr(relative_key,'/')=0 "
            "AND instr(relative_key, char(92))=0",
            name="ck_waw_project_bindings_relative_key",
        ),
        sa.CheckConstraint(
            "project_revision >= 1", name="ck_waw_project_bindings_project_revision"
        ),
        sa.CheckConstraint(
            "binding_revision >= 1", name="ck_waw_project_bindings_binding_revision"
        ),
        sa.CheckConstraint(
            "binding_digest IS NULL OR (length(binding_digest)=64 "
            "AND binding_digest NOT GLOB '*[^0-9a-f]*')",
            name="ck_waw_project_bindings_digest",
        ),
        sa.CheckConstraint(
            "(binding_revision=1 AND previous_binding_revision IS NULL "
            "AND previous_binding_digest IS NULL) OR "
            "(binding_revision>1 AND previous_binding_revision=binding_revision-1 "
            "AND length(previous_binding_digest)=64 "
            "AND previous_binding_digest NOT GLOB '*[^0-9a-f]*')",
            name="ck_waw_project_bindings_predecessor",
        ),
        sa.CheckConstraint(
            "length(runtime_host_installation_id)=36 "
            "AND substr(runtime_host_installation_id,1,4)='wri_' "
            "AND substr(runtime_host_installation_id,5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_waw_project_bindings_host_id",
        ),
        sa.CheckConstraint(
            "runtime_host_installation_revision >= 1",
            name="ck_waw_project_bindings_host_revision",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','CURRENT','RECONCILIATION_REQUIRED','SUPERSEDED')",
            name="ck_waw_project_bindings_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('CURRENT','SUPERSEDED') OR binding_digest IS NOT NULL",
            name="ck_waw_project_bindings_attested_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="RESTRICT",
            name="fk_waw_project_bindings_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "previous_binding_revision", "previous_binding_digest"],
            [
                "waw_project_bindings.project_id",
                "waw_project_bindings.binding_revision",
                "waw_project_bindings.binding_digest",
            ],
            ondelete="RESTRICT",
            name="fk_waw_project_bindings_predecessor",
        ),
        sa.ForeignKeyConstraint(
            ["runtime_host_installation_id", "runtime_host_installation_revision"],
            [
                "waw_runtime_host_installations.id",
                "waw_runtime_host_installations.revision",
            ],
            ondelete="RESTRICT",
            name="fk_waw_project_bindings_runtime_host_identity",
        ),
        sa.PrimaryKeyConstraint("project_id", "binding_revision"),
        sa.UniqueConstraint(
            "project_id",
            "binding_revision",
            "binding_digest",
            name="uq_waw_project_bindings_attested_identity",
        ),
    )
    op.create_index(
        "uq_waw_project_bindings_open_attempt",
        "waw_project_bindings",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(
            "status='PENDING' OR (status='RECONCILIATION_REQUIRED' AND binding_digest IS NULL)"
        ),
    )
    op.create_index(
        "uq_waw_project_bindings_head",
        "waw_project_bindings",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(
            "status='CURRENT' OR (status='RECONCILIATION_REQUIRED' AND binding_digest IS NOT NULL)"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_waw_project_bindings_immutable_identity "
        "BEFORE UPDATE ON waw_project_bindings WHEN "
        "NEW.project_id IS NOT OLD.project_id OR "
        "NEW.binding_revision IS NOT OLD.binding_revision OR "
        "NEW.relative_key IS NOT OLD.relative_key OR "
        "NEW.project_revision IS NOT OLD.project_revision OR "
        "NEW.previous_binding_revision IS NOT OLD.previous_binding_revision OR "
        "NEW.previous_binding_digest IS NOT OLD.previous_binding_digest OR "
        "NEW.runtime_host_installation_id IS NOT OLD.runtime_host_installation_id OR "
        "NEW.runtime_host_installation_revision IS NOT OLD.runtime_host_installation_revision OR "
        "NEW.created_at IS NOT OLD.created_at OR "
        "(OLD.binding_digest IS NOT NULL AND NEW.binding_digest IS NOT OLD.binding_digest) "
        "BEGIN SELECT RAISE(ABORT, 'WAW Project binding identity is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_waw_project_bindings_legal_transition "
        "BEFORE UPDATE ON waw_project_bindings WHEN NOT ("
        "(OLD.status='PENDING' AND NEW.status IN ('PENDING','CURRENT','RECONCILIATION_REQUIRED')) OR "
        "(OLD.status='CURRENT' AND NEW.status IN ('CURRENT','RECONCILIATION_REQUIRED','SUPERSEDED')) OR "
        "(OLD.status='RECONCILIATION_REQUIRED' AND NEW.status IN "
        "('RECONCILIATION_REQUIRED','CURRENT','SUPERSEDED')) OR "
        "(OLD.status='SUPERSEDED' AND NEW.status='SUPERSEDED')) "
        "BEGIN SELECT RAISE(ABORT, 'WAW Project binding transition is invalid'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_waw_project_bindings_immutable_delete "
        "BEFORE DELETE ON waw_project_bindings "
        "BEGIN SELECT RAISE(ABORT, 'WAW Project binding history is immutable'); END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    binding_count = connection.execute(
        sa.text("SELECT count(*) FROM waw_project_bindings")
    ).scalar_one()
    workspace_count = connection.execute(
        sa.text("SELECT count(*) FROM waw_agent_workspace_sessions")
    ).scalar_one()
    if binding_count or workspace_count:
        raise RuntimeError("WAW_0009_DOWNGRADE_UNSAFE")

    op.execute("DROP TRIGGER trg_waw_project_bindings_immutable_delete")
    op.execute("DROP TRIGGER trg_waw_project_bindings_legal_transition")
    op.execute("DROP TRIGGER trg_waw_project_bindings_immutable_identity")
    op.drop_index("uq_waw_project_bindings_head", table_name="waw_project_bindings")
    op.drop_index("uq_waw_project_bindings_open_attempt", table_name="waw_project_bindings")
    op.drop_table("waw_project_bindings")

    with op.batch_alter_table("waw_agent_workspace_sessions", recreate="always") as batch:
        batch.drop_constraint("ck_waw_sessions_executable_evidence_consistency", type_="check")
        batch.drop_constraint("ck_waw_sessions_executable_evidence_epoch", type_="check")
        batch.drop_constraint("ck_waw_sessions_executable_evidence_generation", type_="check")
        batch.drop_constraint("ck_waw_sessions_executable_evidence_state", type_="check")
        batch.drop_constraint("ck_waw_sessions_executable_fingerprint", type_="check")
        batch.drop_column("executable_evidence_runtime_epoch")
        batch.drop_column("executable_evidence_generation")
        batch.drop_column("executable_evidence_state")
        batch.alter_column(
            "executable_fingerprint",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_waw_sessions_executable_fingerprint",
            "length(executable_fingerprint)=64 "
            "AND executable_fingerprint NOT GLOB '*[^0-9a-f]*'",
        )

    with op.batch_alter_table("projects", recreate="always") as batch:
        batch.drop_constraint("ck_projects_revision", type_="check")
        batch.drop_column("revision")
