"""Add the non-secret Phase 11 Provider core.

Revision ID: 0004_phase11_provider_core
Revises: 0003_security_hardening
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_phase11_provider_core"
down_revision = "0003_security_hardening"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "runtime_installations",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("runtime_type", _enum("runtime_type", "codex", "claude"), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_runtime_installations_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "runtime_type", name="uq_runtime_installations_id_type"),
    )

    op.create_table(
        "provider_definitions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("identity_schema_version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column(
            "provider_type",
            _enum("provider_type", "official_openai", "openai_compatible"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("wire_protocol", _enum("provider_wire_protocol", "responses"), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "state",
            _enum(
                "provider_lifecycle_state",
                "configured",
                "validated",
                "needs_attention",
                "disabled",
            ),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("identity_schema_version >= 1", name="ck_providers_identity_schema"),
        sa.CheckConstraint("revision >= 1", name="ck_providers_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_type",
            "endpoint",
            "wire_protocol",
            "model",
            name="uq_provider_definitions_identity",
        ),
    )

    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("kind", _enum("provider_credential_kind", "api_key"), nullable=False),
        sa.Column("runtime_secret_ref", sa.String(length=40), nullable=True),
        sa.Column("secret_version", sa.Integer(), nullable=True),
        sa.Column(
            "state",
            _enum(
                "provider_credential_state",
                "missing",
                "configured",
                "rotating",
                "revoked",
                "needs_attention",
            ),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_provider_credentials_revision"),
        sa.CheckConstraint(
            "(runtime_secret_ref IS NULL AND secret_version IS NULL) OR "
            "(runtime_secret_ref IS NOT NULL AND secret_version >= 1)",
            name="ck_provider_credentials_secret_reference_pair",
        ),
        sa.CheckConstraint(
            "runtime_secret_ref IS NULL OR "
            "(length(runtime_secret_ref) = 36 AND substr(runtime_secret_ref, 1, 4) = 'sec_' "
            "AND substr(runtime_secret_ref, 5) NOT GLOB '*[^0-9a-f]*')",
            name="ck_provider_credentials_secret_reference_format",
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definitions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "provider_id", name="uq_provider_credentials_id_provider"),
        sa.UniqueConstraint("provider_id", name="uq_provider_credentials_provider"),
    )

    op.create_table(
        "runtime_provider_profiles",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("runtime_installation_id", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("provider_revision", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.String(length=40), nullable=True),
        sa.Column("credential_revision", sa.Integer(), nullable=True),
        sa.Column("credential_secret_version", sa.Integer(), nullable=True),
        sa.Column(
            "adapter_type",
            _enum("runtime_profile_adapter_type", "codex", "claude"),
            nullable=False,
        ),
        sa.Column("adapter_schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            _enum(
                "runtime_profile_state",
                "draft",
                "valid",
                "superseded",
                "incompatible",
                "needs_attention",
            ),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider_revision >= 1", name="ck_runtime_profiles_provider_revision"),
        sa.CheckConstraint(
            "adapter_schema_version >= 1", name="ck_runtime_profiles_adapter_schema"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_runtime_profiles_revision"),
        sa.CheckConstraint(
            "(credential_id IS NULL AND credential_revision IS NULL "
            "AND credential_secret_version IS NULL) OR "
            "(credential_id IS NOT NULL AND credential_revision >= 1 "
            "AND credential_secret_version >= 1)",
            name="ck_runtime_profiles_credential_reference",
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["runtime_installation_id", "adapter_type"],
            ["runtime_installations.id", "runtime_installations.runtime_type"],
            ondelete="RESTRICT",
            name="fk_runtime_profiles_installation_adapter",
        ),
        sa.ForeignKeyConstraint(
            ["credential_id", "provider_id"],
            ["provider_credentials.id", "provider_credentials.provider_id"],
            ondelete="RESTRICT",
            name="fk_runtime_profiles_credential_provider",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "runtime_installation_id",
            "provider_id",
            name="uq_runtime_provider_profiles_identity",
        ),
    )

    op.create_table(
        "runtime_provider_bindings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("runtime_installation_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_profile_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_profile_revision", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("provider_revision", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            _enum(
                "runtime_binding_state",
                "unmanaged",
                "pending",
                "activating",
                "commit_pending",
                "active",
                "activation_failed",
                "rollback_pending",
                "rolling_back",
                "rollback_verified",
                "superseded",
                "needs_attention",
                "unknown",
            ),
            nullable=False,
        ),
        sa.Column("previous_binding_id", sa.String(length=40), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "runtime_profile_revision >= 1", name="ck_runtime_bindings_profile_revision"
        ),
        sa.CheckConstraint("provider_revision >= 1", name="ck_runtime_bindings_provider_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_runtime_bindings_revision"),
        sa.CheckConstraint("state <> 'unmanaged'", name="ck_runtime_bindings_managed_rows_only"),
        sa.ForeignKeyConstraint(
            ["runtime_installation_id"],
            ["runtime_installations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_binding_id"],
            ["runtime_provider_bindings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["runtime_profile_id", "runtime_installation_id", "provider_id"],
            [
                "runtime_provider_profiles.id",
                "runtime_provider_profiles.runtime_installation_id",
                "runtime_provider_profiles.provider_id",
            ],
            ondelete="RESTRICT",
            name="fk_runtime_bindings_profile_identity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "runtime_installation_id", name="uq_runtime_bindings_runtime"),
        sa.UniqueConstraint(
            "id",
            "runtime_installation_id",
            "runtime_profile_id",
            "provider_id",
            name="uq_runtime_bindings_effective_identity",
        ),
    )
    op.create_index(
        "uq_runtime_bindings_single_active",
        "runtime_provider_bindings",
        ["runtime_installation_id"],
        unique=True,
        sqlite_where=sa.text("state = 'active'"),
    )

    op.create_table(
        "runtime_session_provider_bindings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("runtime_session_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_installation_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_binding_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_binding_revision", sa.Integer(), nullable=False),
        sa.Column("runtime_profile_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_profile_revision", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("provider_revision", sa.Integer(), nullable=False),
        sa.Column(
            "evidence_class",
            _enum("session_binding_evidence_class", "agentbox_created", "public_runtime"),
            nullable=False,
        ),
        sa.Column(
            "state",
            _enum(
                "session_binding_state",
                "bound",
                "legacy_unbound",
                "rebind_required",
                "continuity_unknown",
                "retired",
            ),
            nullable=False,
        ),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("runtime_binding_revision >= 1", name="ck_session_binding_revision"),
        sa.CheckConstraint("runtime_profile_revision >= 1", name="ck_session_profile_revision"),
        sa.CheckConstraint("provider_revision >= 1", name="ck_session_provider_revision"),
        sa.ForeignKeyConstraint(
            ["runtime_installation_id"],
            ["runtime_installations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "runtime_binding_id",
                "runtime_installation_id",
                "runtime_profile_id",
                "provider_id",
            ],
            [
                "runtime_provider_bindings.id",
                "runtime_provider_bindings.runtime_installation_id",
                "runtime_provider_bindings.runtime_profile_id",
                "runtime_provider_bindings.provider_id",
            ],
            ondelete="RESTRICT",
            name="fk_session_bindings_effective_binding",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("runtime_session_id", name="uq_session_bindings_runtime_session"),
    )
    op.execute(
        "CREATE TRIGGER trg_session_bindings_immutable_update "
        "BEFORE UPDATE ON runtime_session_provider_bindings "
        "BEGIN SELECT RAISE(ABORT, 'session bindings are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_session_bindings_immutable_delete "
        "BEFORE DELETE ON runtime_session_provider_bindings "
        "BEGIN SELECT RAISE(ABORT, 'session bindings are immutable'); END"
    )

    op.create_table(
        "provider_compatibility_observations",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("observation_set_id", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_installation_id", sa.String(length=40), nullable=True),
        sa.Column("runtime_profile_id", sa.String(length=40), nullable=True),
        sa.Column(
            "dimension",
            _enum(
                "compatibility_dimension",
                "provider_endpoint",
                "network",
                "authentication",
                "model",
                "wire_protocol",
                "provider_api",
                "codex_runtime",
                "remote",
                "resume",
                "context",
                "discovery",
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            _enum(
                "compatibility_state",
                "pass",
                "fail",
                "unsupported",
                "experimental",
                "unknown",
                "not_tested",
            ),
            nullable=False,
        ),
        sa.Column("evidence_schema_version", sa.Integer(), nullable=False),
        sa.Column("evidence_code", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("evidence_schema_version >= 1", name="ck_compatibility_evidence_schema"),
        sa.CheckConstraint(
            "(runtime_profile_id IS NULL AND runtime_installation_id IS NULL) OR "
            "(runtime_profile_id IS NOT NULL AND runtime_installation_id IS NOT NULL)",
            name="ck_compatibility_runtime_profile_pair",
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["runtime_profile_id", "runtime_installation_id", "provider_id"],
            [
                "runtime_provider_profiles.id",
                "runtime_provider_profiles.runtime_installation_id",
                "runtime_provider_profiles.provider_id",
            ],
            ondelete="RESTRICT",
            name="fk_compatibility_observation_profile_identity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "observation_set_id",
            "dimension",
            name="uq_provider_compatibility_set_dimension",
        ),
    )

    op.create_table(
        "provider_config_transactions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("runtime_installation_id", sa.String(length=40), nullable=False),
        sa.Column("runtime_binding_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=True),
        sa.Column(
            "state",
            _enum(
                "provider_config_transaction_state",
                "created",
                "planning",
                "prepared",
                "validated",
                "snapshot_creating",
                "snapshot_created",
                "applying",
                "applied",
                "candidate_verification_authorized",
                "verifying",
                "commit_pending",
                "committed",
                "failed_no_change",
                "rollback_required",
                "rolling_back",
                "rollback_verifying",
                "recovered",
                "interrupted",
                "reconciling",
                "needs_attention",
            ),
            nullable=False,
        ),
        sa.Column("expected_binding_revision", sa.Integer(), nullable=False),
        sa.Column("expected_profile_revision", sa.Integer(), nullable=False),
        sa.Column("expected_provider_revision", sa.Integer(), nullable=False),
        sa.Column("expected_credential_revision", sa.Integer(), nullable=True),
        sa.Column("plan_digest", sa.String(length=64), nullable=True),
        sa.Column("runtime_snapshot_ref", sa.String(length=40), nullable=True),
        sa.Column("outcome_code", sa.String(length=80), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expected_binding_revision >= 1", name="ck_tx_binding_revision"),
        sa.CheckConstraint("expected_profile_revision >= 1", name="ck_tx_profile_revision"),
        sa.CheckConstraint("expected_provider_revision >= 1", name="ck_tx_provider_revision"),
        sa.CheckConstraint(
            "expected_credential_revision IS NULL OR expected_credential_revision >= 1",
            name="ck_tx_credential_revision",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_provider_transactions_revision"),
        sa.CheckConstraint(
            "runtime_snapshot_ref IS NULL OR "
            "(length(runtime_snapshot_ref) = 36 "
            "AND substr(runtime_snapshot_ref, 1, 4) = 'snp_' "
            "AND substr(runtime_snapshot_ref, 5) NOT GLOB '*[^0-9a-f]*')",
            name="ck_provider_transactions_snapshot_reference_format",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["runtime_binding_id", "runtime_installation_id"],
            ["runtime_provider_bindings.id", "runtime_provider_bindings.runtime_installation_id"],
            ondelete="RESTRICT",
            name="fk_provider_transactions_binding_runtime",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_provider_config_transactions_job"),
    )


def downgrade() -> None:
    op.drop_table("provider_config_transactions")
    op.drop_table("provider_compatibility_observations")
    op.execute("DROP TRIGGER IF EXISTS trg_session_bindings_immutable_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_session_bindings_immutable_update")
    op.drop_table("runtime_session_provider_bindings")
    op.drop_index("uq_runtime_bindings_single_active", table_name="runtime_provider_bindings")
    op.drop_table("runtime_provider_bindings")
    op.drop_table("runtime_provider_profiles")
    op.drop_table("provider_credentials")
    op.drop_table("provider_definitions")
    op.drop_table("runtime_installations")
