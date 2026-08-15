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
            "(state = 'missing' AND runtime_secret_ref IS NULL AND secret_version IS NULL) OR "
            "(state IN ('configured', 'rotating', 'revoked', 'needs_attention') "
            "AND runtime_secret_ref IS NOT NULL AND secret_version IS NOT NULL "
            "AND secret_version >= 1)",
            name="ck_provider_credentials_state_reference",
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
            _enum("runtime_profile_adapter_type", "codex"),
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
            "(credential_id IS NOT NULL AND credential_revision IS NOT NULL "
            "AND credential_revision >= 1 AND credential_secret_version IS NOT NULL "
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
    op.execute(
        "CREATE TRIGGER trg_runtime_profiles_valid_snapshot "
        "BEFORE INSERT ON runtime_provider_profiles "
        "WHEN NOT EXISTS (SELECT 1 FROM runtime_installations AS runtime "
        "JOIN provider_definitions AS provider ON provider.id = NEW.provider_id "
        "WHERE runtime.id = NEW.runtime_installation_id "
        "AND runtime.runtime_type = 'codex' "
        "AND NEW.adapter_type = 'codex' "
        "AND provider.state <> 'disabled' "
        "AND provider.revision = NEW.provider_revision "
        "AND ((NEW.credential_id IS NULL "
        "AND NEW.credential_revision IS NULL "
        "AND NEW.credential_secret_version IS NULL) "
        "OR EXISTS (SELECT 1 FROM provider_credentials AS credential "
        "WHERE credential.id = NEW.credential_id "
        "AND credential.provider_id = NEW.provider_id "
        "AND credential.revision = NEW.credential_revision "
        "AND credential.secret_version = NEW.credential_secret_version "
        "AND credential.state = 'configured'))) "
        "BEGIN SELECT RAISE(ABORT, 'runtime profile snapshot is not current and eligible'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_runtime_profiles_immutable_snapshot "
        "BEFORE UPDATE ON runtime_provider_profiles "
        "WHEN NEW.id IS NOT OLD.id "
        "OR NEW.runtime_installation_id IS NOT OLD.runtime_installation_id "
        "OR NEW.provider_id IS NOT OLD.provider_id "
        "OR NEW.provider_revision IS NOT OLD.provider_revision "
        "OR NEW.credential_id IS NOT OLD.credential_id "
        "OR NEW.credential_revision IS NOT OLD.credential_revision "
        "OR NEW.credential_secret_version IS NOT OLD.credential_secret_version "
        "OR NEW.adapter_type IS NOT OLD.adapter_type "
        "OR NEW.adapter_schema_version IS NOT OLD.adapter_schema_version "
        "OR NEW.created_at IS NOT OLD.created_at "
        "BEGIN SELECT RAISE(ABORT, 'runtime profile snapshot identity is immutable'); END"
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
        sa.CheckConstraint(
            "previous_binding_id IS NULL OR previous_binding_id <> id",
            name="ck_runtime_bindings_previous_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["runtime_installation_id"],
            ["runtime_installations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_binding_id", "runtime_installation_id"],
            [
                "runtime_provider_bindings.id",
                "runtime_provider_bindings.runtime_installation_id",
            ],
            ondelete="RESTRICT",
            name="fk_runtime_bindings_previous_same_runtime",
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
    op.execute(
        "CREATE TRIGGER trg_runtime_bindings_valid_snapshot "
        "BEFORE INSERT ON runtime_provider_bindings "
        "WHEN NOT EXISTS (SELECT 1 FROM runtime_provider_profiles AS profile "
        "JOIN provider_definitions AS provider ON provider.id = NEW.provider_id "
        "WHERE profile.id = NEW.runtime_profile_id "
        "AND profile.runtime_installation_id = NEW.runtime_installation_id "
        "AND profile.provider_id = NEW.provider_id "
        "AND profile.revision = NEW.runtime_profile_revision "
        "AND profile.provider_revision = NEW.provider_revision "
        "AND provider.state <> 'disabled' "
        "AND provider.revision = profile.provider_revision) "
        "BEGIN SELECT RAISE(ABORT, 'runtime binding snapshot is not current and eligible'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_runtime_bindings_immutable_selection "
        "BEFORE UPDATE ON runtime_provider_bindings "
        "WHEN NEW.id IS NOT OLD.id "
        "OR NEW.runtime_installation_id IS NOT OLD.runtime_installation_id "
        "OR NEW.runtime_profile_id IS NOT OLD.runtime_profile_id "
        "OR NEW.runtime_profile_revision IS NOT OLD.runtime_profile_revision "
        "OR NEW.provider_id IS NOT OLD.provider_id "
        "OR NEW.provider_revision IS NOT OLD.provider_revision "
        "OR NEW.previous_binding_id IS NOT OLD.previous_binding_id "
        "OR NEW.created_at IS NOT OLD.created_at "
        "BEGIN SELECT RAISE(ABORT, 'runtime binding selection is immutable'); END"
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
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("runtime_binding_revision >= 1", name="ck_session_binding_revision"),
        sa.CheckConstraint("runtime_profile_revision >= 1", name="ck_session_profile_revision"),
        sa.CheckConstraint("provider_revision >= 1", name="ck_session_provider_revision"),
        sa.CheckConstraint(
            "length(runtime_session_id) = 36 "
            "AND substr(runtime_session_id, 1, 4) = 'rts_' "
            "AND substr(runtime_session_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="ck_session_binding_runtime_session_id",
        ),
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
        "CREATE TRIGGER trg_session_bindings_valid_snapshot "
        "BEFORE INSERT ON runtime_session_provider_bindings "
        "WHEN NOT EXISTS (SELECT 1 FROM runtime_provider_bindings AS binding "
        "WHERE binding.id = NEW.runtime_binding_id "
        "AND binding.runtime_installation_id = NEW.runtime_installation_id "
        "AND binding.runtime_profile_id = NEW.runtime_profile_id "
        "AND binding.provider_id = NEW.provider_id "
        "AND binding.state = 'active' "
        "AND binding.revision = NEW.runtime_binding_revision "
        "AND binding.runtime_profile_revision = NEW.runtime_profile_revision "
        "AND binding.provider_revision = NEW.provider_revision) "
        "BEGIN SELECT RAISE(ABORT, 'session binding snapshot is not active and exact'); END"
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
        "provider_compatibility_evidence_sets",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("provider_revision", sa.Integer(), nullable=False),
        sa.Column("runtime_installation_id", sa.String(length=40), nullable=True),
        sa.Column("runtime_profile_id", sa.String(length=40), nullable=True),
        sa.Column("runtime_profile_revision", sa.Integer(), nullable=True),
        sa.Column("credential_id", sa.String(length=40), nullable=True),
        sa.Column("credential_revision", sa.Integer(), nullable=True),
        sa.Column("credential_secret_version", sa.Integer(), nullable=True),
        sa.Column("evidence_schema_version", sa.Integer(), nullable=False),
        sa.Column("expected_dimension_mask", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            _enum("compatibility_evidence_set_state", "building", "sealed"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider_revision >= 1", name="ck_compatibility_provider_revision"),
        sa.CheckConstraint("evidence_schema_version >= 1", name="ck_compatibility_evidence_schema"),
        sa.CheckConstraint(
            "expected_dimension_mask >= 1 AND expected_dimension_mask <= 2047",
            name="ck_compatibility_expected_dimension_mask",
        ),
        sa.CheckConstraint(
            "(runtime_installation_id IS NULL AND runtime_profile_id IS NULL "
            "AND runtime_profile_revision IS NULL) OR "
            "(runtime_installation_id IS NOT NULL AND runtime_profile_id IS NOT NULL "
            "AND runtime_profile_revision IS NOT NULL AND runtime_profile_revision >= 1)",
            name="ck_compatibility_runtime_profile_scope",
        ),
        sa.CheckConstraint(
            "(credential_id IS NULL AND credential_revision IS NULL "
            "AND credential_secret_version IS NULL) OR "
            "(credential_id IS NOT NULL AND credential_revision IS NOT NULL "
            "AND credential_revision >= 1 AND credential_secret_version IS NOT NULL "
            "AND credential_secret_version >= 1)",
            name="ck_compatibility_credential_scope",
        ),
        sa.CheckConstraint("expires_at > observed_at", name="ck_compatibility_evidence_expiry"),
        sa.CheckConstraint(
            "(state = 'building' AND sealed_at IS NULL) OR "
            "(state = 'sealed' AND sealed_at IS NOT NULL)",
            name="ck_compatibility_evidence_seal_state",
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
            name="fk_compatibility_evidence_profile_identity",
        ),
        sa.ForeignKeyConstraint(
            ["credential_id", "provider_id"],
            ["provider_credentials.id", "provider_credentials.provider_id"],
            ondelete="RESTRICT",
            name="fk_compatibility_evidence_credential_provider",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "provider_id", name="uq_provider_compatibility_evidence_set_provider"
        ),
    )

    op.create_table(
        "provider_compatibility_observations",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("evidence_set_id", sa.String(length=40), nullable=False),
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
        sa.Column(
            "evidence_code",
            _enum(
                "compatibility_evidence_code",
                "VALIDATION_PASSED",
                "VALIDATION_FAILED",
                "UNSUPPORTED_CONTRACT",
                "EXPERIMENTAL_CONTRACT",
                "UNKNOWN_EVIDENCE",
                "NOT_EXECUTED",
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state = 'pass' AND evidence_code = 'VALIDATION_PASSED') OR "
            "(state = 'fail' AND evidence_code = 'VALIDATION_FAILED') OR "
            "(state = 'unsupported' AND evidence_code = 'UNSUPPORTED_CONTRACT') OR "
            "(state = 'experimental' AND evidence_code = 'EXPERIMENTAL_CONTRACT') OR "
            "(state = 'unknown' AND evidence_code = 'UNKNOWN_EVIDENCE') OR "
            "(state = 'not_tested' AND evidence_code = 'NOT_EXECUTED')",
            name="ck_compatibility_observation_state_code",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_set_id"],
            ["provider_compatibility_evidence_sets.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_set_id", "dimension", name="uq_provider_compatibility_set_dimension"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_evidence_valid_scope "
        "BEFORE INSERT ON provider_compatibility_evidence_sets "
        "WHEN NOT EXISTS (SELECT 1 FROM provider_definitions AS provider "
        "WHERE provider.id = NEW.provider_id "
        "AND provider.revision = NEW.provider_revision "
        "AND provider.state <> 'disabled' "
        "AND (((NEW.runtime_installation_id IS NULL "
        "AND NEW.runtime_profile_id IS NULL "
        "AND NEW.runtime_profile_revision IS NULL) "
        "AND ((NEW.credential_id IS NULL "
        "AND NEW.credential_revision IS NULL "
        "AND NEW.credential_secret_version IS NULL) "
        "OR EXISTS (SELECT 1 FROM provider_credentials AS credential "
        "WHERE credential.id = NEW.credential_id "
        "AND credential.provider_id = NEW.provider_id "
        "AND credential.revision = NEW.credential_revision "
        "AND credential.secret_version = NEW.credential_secret_version "
        "AND credential.state = 'configured'))) "
        "OR EXISTS (SELECT 1 FROM runtime_provider_profiles AS profile "
        "WHERE profile.id = NEW.runtime_profile_id "
        "AND profile.runtime_installation_id = NEW.runtime_installation_id "
        "AND profile.provider_id = NEW.provider_id "
        "AND profile.revision = NEW.runtime_profile_revision "
        "AND profile.provider_revision = NEW.provider_revision "
        "AND ((profile.credential_id IS NULL "
        "AND profile.credential_revision IS NULL "
        "AND profile.credential_secret_version IS NULL "
        "AND NEW.credential_id IS NULL "
        "AND NEW.credential_revision IS NULL "
        "AND NEW.credential_secret_version IS NULL) "
        "OR (profile.credential_id = NEW.credential_id "
        "AND profile.credential_revision = NEW.credential_revision "
        "AND profile.credential_secret_version = NEW.credential_secret_version "
        "AND EXISTS (SELECT 1 FROM provider_credentials AS credential "
        "WHERE credential.id = NEW.credential_id "
        "AND credential.provider_id = NEW.provider_id "
        "AND credential.revision = NEW.credential_revision "
        "AND credential.secret_version = NEW.credential_secret_version "
        "AND credential.state = 'configured')))))) "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence scope is not current and exact'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_evidence_sets_start_building "
        "BEFORE INSERT ON provider_compatibility_evidence_sets "
        "WHEN NEW.state <> 'building' OR NEW.sealed_at IS NOT NULL "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence must start building'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_expected_dimension "
        "BEFORE INSERT ON provider_compatibility_observations "
        "WHEN NOT EXISTS (SELECT 1 FROM provider_compatibility_evidence_sets AS evidence "
        "WHERE evidence.id = NEW.evidence_set_id "
        "AND evidence.state = 'building' "
        "AND (evidence.expected_dimension_mask & CASE NEW.dimension "
        "WHEN 'provider_endpoint' THEN 1 WHEN 'network' THEN 2 "
        "WHEN 'authentication' THEN 4 WHEN 'model' THEN 8 "
        "WHEN 'wire_protocol' THEN 16 WHEN 'provider_api' THEN 32 "
        "WHEN 'codex_runtime' THEN 64 WHEN 'remote' THEN 128 "
        "WHEN 'resume' THEN 256 WHEN 'context' THEN 512 "
        "WHEN 'discovery' THEN 1024 ELSE 0 END) <> 0) "
        "BEGIN SELECT RAISE(ABORT, 'compatibility dimension is not expected or set is sealed'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_runtime_scope "
        "BEFORE INSERT ON provider_compatibility_observations "
        "WHEN NEW.dimension IN ('codex_runtime', 'remote', 'resume', 'context', 'discovery') "
        "AND NOT EXISTS (SELECT 1 FROM provider_compatibility_evidence_sets AS evidence "
        "WHERE evidence.id = NEW.evidence_set_id "
        "AND evidence.runtime_installation_id IS NOT NULL "
        "AND evidence.runtime_profile_id IS NOT NULL "
        "AND evidence.runtime_profile_revision IS NOT NULL) "
        "BEGIN SELECT RAISE(ABORT, 'runtime compatibility dimension requires profile scope'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_auth_scope "
        "BEFORE INSERT ON provider_compatibility_observations "
        "WHEN NEW.dimension = 'authentication' AND NEW.state IN ('pass', 'fail') "
        "AND NOT EXISTS (SELECT 1 FROM provider_compatibility_evidence_sets AS evidence "
        "WHERE evidence.id = NEW.evidence_set_id "
        "AND evidence.credential_id IS NOT NULL "
        "AND evidence.credential_revision IS NOT NULL "
        "AND evidence.credential_secret_version IS NOT NULL) "
        "BEGIN SELECT RAISE(ABORT, 'authentication result requires credential scope'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_evidence_sets_immutable_scope "
        "BEFORE UPDATE ON provider_compatibility_evidence_sets "
        "WHEN NEW.id IS NOT OLD.id "
        "OR NEW.provider_id IS NOT OLD.provider_id "
        "OR NEW.provider_revision IS NOT OLD.provider_revision "
        "OR NEW.runtime_installation_id IS NOT OLD.runtime_installation_id "
        "OR NEW.runtime_profile_id IS NOT OLD.runtime_profile_id "
        "OR NEW.runtime_profile_revision IS NOT OLD.runtime_profile_revision "
        "OR NEW.credential_id IS NOT OLD.credential_id "
        "OR NEW.credential_revision IS NOT OLD.credential_revision "
        "OR NEW.credential_secret_version IS NOT OLD.credential_secret_version "
        "OR NEW.evidence_schema_version IS NOT OLD.evidence_schema_version "
        "OR NEW.expected_dimension_mask IS NOT OLD.expected_dimension_mask "
        "OR NEW.observed_at IS NOT OLD.observed_at "
        "OR NEW.expires_at IS NOT OLD.expires_at "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence scope is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_evidence_sets_seal_transition "
        "BEFORE UPDATE ON provider_compatibility_evidence_sets "
        "WHEN OLD.state <> 'building' OR NEW.state <> 'sealed' "
        "OR OLD.sealed_at IS NOT NULL OR NEW.sealed_at IS NULL "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence may be sealed exactly once'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_compatibility_evidence_sets_complete "
        "BEFORE UPDATE OF state ON provider_compatibility_evidence_sets "
        "WHEN NEW.state = 'sealed' AND COALESCE((SELECT SUM(CASE observation.dimension "
        "WHEN 'provider_endpoint' THEN 1 WHEN 'network' THEN 2 "
        "WHEN 'authentication' THEN 4 WHEN 'model' THEN 8 "
        "WHEN 'wire_protocol' THEN 16 WHEN 'provider_api' THEN 32 "
        "WHEN 'codex_runtime' THEN 64 WHEN 'remote' THEN 128 "
        "WHEN 'resume' THEN 256 WHEN 'context' THEN 512 "
        "WHEN 'discovery' THEN 1024 ELSE 0 END) "
        "FROM provider_compatibility_observations AS observation "
        "WHERE observation.evidence_set_id = OLD.id), 0) <> OLD.expected_dimension_mask "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence set is incomplete'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_provider_compatibility_evidence_sets_immutable_delete "
        "BEFORE DELETE ON provider_compatibility_evidence_sets "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_provider_compatibility_observations_immutable_update "
        "BEFORE UPDATE ON provider_compatibility_observations "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence is immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_provider_compatibility_observations_immutable_delete "
        "BEFORE DELETE ON provider_compatibility_observations "
        "BEGIN SELECT RAISE(ABORT, 'compatibility evidence is immutable'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_provider_compatibility_observations_immutable_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_provider_compatibility_observations_immutable_update")
    op.execute("DROP TRIGGER IF EXISTS trg_provider_compatibility_evidence_sets_immutable_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_evidence_sets_complete")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_evidence_sets_seal_transition")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_evidence_sets_immutable_scope")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_auth_scope")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_runtime_scope")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_expected_dimension")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_evidence_sets_start_building")
    op.execute("DROP TRIGGER IF EXISTS trg_compatibility_evidence_valid_scope")
    op.drop_table("provider_compatibility_observations")
    op.drop_table("provider_compatibility_evidence_sets")
    op.execute("DROP TRIGGER IF EXISTS trg_session_bindings_immutable_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_session_bindings_immutable_update")
    op.execute("DROP TRIGGER IF EXISTS trg_session_bindings_valid_snapshot")
    op.drop_table("runtime_session_provider_bindings")
    op.execute("DROP TRIGGER IF EXISTS trg_runtime_bindings_immutable_selection")
    op.execute("DROP TRIGGER IF EXISTS trg_runtime_bindings_valid_snapshot")
    op.drop_index("uq_runtime_bindings_single_active", table_name="runtime_provider_bindings")
    op.drop_table("runtime_provider_bindings")
    op.execute("DROP TRIGGER IF EXISTS trg_runtime_profiles_immutable_snapshot")
    op.execute("DROP TRIGGER IF EXISTS trg_runtime_profiles_valid_snapshot")
    op.drop_table("runtime_provider_profiles")
    op.drop_table("provider_credentials")
    op.drop_table("provider_definitions")
    op.drop_table("runtime_installations")
