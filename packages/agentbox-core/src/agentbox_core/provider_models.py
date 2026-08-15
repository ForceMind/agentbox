"""Non-secret Phase 11 Provider-domain persistence models.

These control-plane models contain typed metadata and opaque identities only.
Secret material, Runtime configuration, and Runtime execution state belong to
separate trust boundaries and are intentionally not representable here.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentbox_core.models import Base


def _values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


class ProviderType(StrEnum):
    OFFICIAL_OPENAI = "official_openai"
    OPENAI_COMPATIBLE = "openai_compatible"


class WireProtocol(StrEnum):
    RESPONSES = "responses"


class ProviderLifecycleState(StrEnum):
    CONFIGURED = "configured"
    VALIDATED = "validated"
    NEEDS_ATTENTION = "needs_attention"
    DISABLED = "disabled"


class CredentialKind(StrEnum):
    API_KEY = "api_key"


class CredentialLifecycleState(StrEnum):
    MISSING = "missing"
    CONFIGURED = "configured"
    ROTATING = "rotating"
    REVOKED = "revoked"
    NEEDS_ATTENTION = "needs_attention"


class RuntimeType(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class RuntimeProfileState(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    SUPERSEDED = "superseded"
    INCOMPATIBLE = "incompatible"
    NEEDS_ATTENTION = "needs_attention"


class RuntimeBindingState(StrEnum):
    UNMANAGED = "unmanaged"
    PENDING = "pending"
    ACTIVATING = "activating"
    COMMIT_PENDING = "commit_pending"
    ACTIVE = "active"
    ACTIVATION_FAILED = "activation_failed"
    ROLLBACK_PENDING = "rollback_pending"
    ROLLING_BACK = "rolling_back"
    ROLLBACK_VERIFIED = "rollback_verified"
    SUPERSEDED = "superseded"
    NEEDS_ATTENTION = "needs_attention"
    UNKNOWN = "unknown"


class SessionBindingState(StrEnum):
    BOUND = "bound"
    LEGACY_UNBOUND = "legacy_unbound"
    REBIND_REQUIRED = "rebind_required"
    CONTINUITY_UNKNOWN = "continuity_unknown"
    RETIRED = "retired"


class SessionEvidenceClass(StrEnum):
    AGENTBOX_CREATED = "agentbox_created"
    PUBLIC_RUNTIME = "public_runtime"


class CompatibilityDimension(StrEnum):
    PROVIDER_ENDPOINT = "provider_endpoint"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    MODEL = "model"
    WIRE_PROTOCOL = "wire_protocol"
    PROVIDER_API = "provider_api"
    CODEX_RUNTIME = "codex_runtime"
    REMOTE = "remote"
    RESUME = "resume"
    CONTEXT = "context"
    DISCOVERY = "discovery"


class CompatibilityState(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNSUPPORTED = "unsupported"
    EXPERIMENTAL = "experimental"
    UNKNOWN = "unknown"
    NOT_TESTED = "not_tested"


class ConfigTransactionState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    PREPARED = "prepared"
    VALIDATED = "validated"
    SNAPSHOT_CREATING = "snapshot_creating"
    SNAPSHOT_CREATED = "snapshot_created"
    APPLYING = "applying"
    APPLIED = "applied"
    CANDIDATE_VERIFICATION_AUTHORIZED = "candidate_verification_authorized"
    VERIFYING = "verifying"
    COMMIT_PENDING = "commit_pending"
    COMMITTED = "committed"
    FAILED_NO_CHANGE = "failed_no_change"
    ROLLBACK_REQUIRED = "rollback_required"
    ROLLING_BACK = "rolling_back"
    ROLLBACK_VERIFYING = "rollback_verifying"
    RECOVERED = "recovered"
    INTERRUPTED = "interrupted"
    RECONCILING = "reconciling"
    NEEDS_ATTENTION = "needs_attention"


class RuntimeInstallation(Base):
    """Control-plane identity for one Runtime installation, without local paths."""

    __tablename__ = "runtime_installations"
    __table_args__ = (
        UniqueConstraint("id", "runtime_type", name="uq_runtime_installations_id_type"),
        CheckConstraint("revision >= 1", name="ck_runtime_installations_revision"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    runtime_type: Mapped[RuntimeType] = mapped_column(
        Enum(
            RuntimeType,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="runtime_type",
        ),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    profiles: Mapped[list[RuntimeProviderProfile]] = relationship(
        back_populates="runtime", viewonly=True
    )
    bindings: Mapped[list[RuntimeProviderBinding]] = relationship(
        back_populates="runtime", viewonly=True
    )


class Provider(Base):
    """A typed, non-secret AI execution backend definition."""

    __tablename__ = "provider_definitions"
    __table_args__ = (
        UniqueConstraint(
            "provider_type",
            "endpoint",
            "wire_protocol",
            "model",
            name="uq_provider_definitions_identity",
        ),
        CheckConstraint("identity_schema_version >= 1", name="ck_providers_identity_schema"),
        CheckConstraint("revision >= 1", name="ck_providers_revision"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    identity_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[ProviderType] = mapped_column(
        Enum(
            ProviderType,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="provider_type",
        ),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    wire_protocol: Mapped[WireProtocol] = mapped_column(
        Enum(
            WireProtocol,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="provider_wire_protocol",
        ),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[ProviderLifecycleState] = mapped_column(
        Enum(
            ProviderLifecycleState,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="provider_lifecycle_state",
        ),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    credentials: Mapped[list[ProviderCredential]] = relationship(
        back_populates="provider", viewonly=True
    )
    profiles: Mapped[list[RuntimeProviderProfile]] = relationship(
        back_populates="provider", viewonly=True
    )
    observations: Mapped[list[ProviderCompatibilityObservation]] = relationship(
        back_populates="provider", viewonly=True
    )


class ProviderCredential(Base):
    """Credential lifecycle metadata; never Provider authentication material."""

    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_provider_credentials_provider"),
        UniqueConstraint("id", "provider_id", name="uq_provider_credentials_id_provider"),
        CheckConstraint("revision >= 1", name="ck_provider_credentials_revision"),
        CheckConstraint(
            "(runtime_secret_ref IS NULL AND secret_version IS NULL) OR "
            "(runtime_secret_ref IS NOT NULL AND secret_version >= 1)",
            name="ck_provider_credentials_secret_reference_pair",
        ),
        CheckConstraint(
            "runtime_secret_ref IS NULL OR "
            "(length(runtime_secret_ref) = 36 AND substr(runtime_secret_ref, 1, 4) = 'sec_' "
            "AND substr(runtime_secret_ref, 5) NOT GLOB '*[^0-9a-f]*')",
            name="ck_provider_credentials_secret_reference_format",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    provider_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("provider_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[CredentialKind] = mapped_column(
        Enum(
            CredentialKind,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="provider_credential_kind",
        ),
        nullable=False,
    )
    runtime_secret_ref: Mapped[str | None] = mapped_column(String(40))
    secret_version: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[CredentialLifecycleState] = mapped_column(
        Enum(
            CredentialLifecycleState,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="provider_credential_state",
        ),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    provider: Mapped[Provider] = relationship(back_populates="credentials", viewonly=True)
    profiles: Mapped[list[RuntimeProviderProfile]] = relationship(
        back_populates="credential", viewonly=True
    )


class RuntimeProviderProfile(Base):
    """Typed, non-secret Provider configuration intent for one Runtime."""

    __tablename__ = "runtime_provider_profiles"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "runtime_installation_id",
            "provider_id",
            name="uq_runtime_provider_profiles_identity",
        ),
        ForeignKeyConstraint(
            ["runtime_installation_id", "adapter_type"],
            ["runtime_installations.id", "runtime_installations.runtime_type"],
            ondelete="RESTRICT",
            name="fk_runtime_profiles_installation_adapter",
        ),
        ForeignKeyConstraint(
            ["credential_id", "provider_id"],
            ["provider_credentials.id", "provider_credentials.provider_id"],
            ondelete="RESTRICT",
            name="fk_runtime_profiles_credential_provider",
        ),
        CheckConstraint("provider_revision >= 1", name="ck_runtime_profiles_provider_revision"),
        CheckConstraint("adapter_schema_version >= 1", name="ck_runtime_profiles_adapter_schema"),
        CheckConstraint("revision >= 1", name="ck_runtime_profiles_revision"),
        CheckConstraint(
            "(credential_id IS NULL AND credential_revision IS NULL "
            "AND credential_secret_version IS NULL) OR "
            "(credential_id IS NOT NULL AND credential_revision >= 1 "
            "AND credential_secret_version >= 1)",
            name="ck_runtime_profiles_credential_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    runtime_installation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("provider_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    provider_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    credential_id: Mapped[str | None] = mapped_column(String(40))
    credential_revision: Mapped[int | None] = mapped_column(Integer)
    credential_secret_version: Mapped[int | None] = mapped_column(Integer)
    adapter_type: Mapped[RuntimeType] = mapped_column(
        Enum(
            RuntimeType,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="runtime_profile_adapter_type",
        ),
        nullable=False,
    )
    adapter_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[RuntimeProfileState] = mapped_column(
        Enum(
            RuntimeProfileState,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="runtime_profile_state",
        ),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    runtime: Mapped[RuntimeInstallation] = relationship(back_populates="profiles", viewonly=True)
    provider: Mapped[Provider] = relationship(back_populates="profiles", viewonly=True)
    credential: Mapped[ProviderCredential | None] = relationship(
        back_populates="profiles", viewonly=True
    )
    bindings: Mapped[list[RuntimeProviderBinding]] = relationship(
        back_populates="profile", viewonly=True
    )
    observations: Mapped[list[ProviderCompatibilityObservation]] = relationship(
        back_populates="profile", viewonly=True
    )


class RuntimeProviderBinding(Base):
    """Provider selection intent; creation never implies activation."""

    __tablename__ = "runtime_provider_bindings"
    __table_args__ = (
        UniqueConstraint("id", "runtime_installation_id", name="uq_runtime_bindings_runtime"),
        UniqueConstraint(
            "id",
            "runtime_installation_id",
            "runtime_profile_id",
            "provider_id",
            name="uq_runtime_bindings_effective_identity",
        ),
        ForeignKeyConstraint(
            ["runtime_profile_id", "runtime_installation_id", "provider_id"],
            [
                "runtime_provider_profiles.id",
                "runtime_provider_profiles.runtime_installation_id",
                "runtime_provider_profiles.provider_id",
            ],
            ondelete="RESTRICT",
            name="fk_runtime_bindings_profile_identity",
        ),
        CheckConstraint(
            "runtime_profile_revision >= 1", name="ck_runtime_bindings_profile_revision"
        ),
        CheckConstraint("provider_revision >= 1", name="ck_runtime_bindings_provider_revision"),
        CheckConstraint("revision >= 1", name="ck_runtime_bindings_revision"),
        CheckConstraint("state <> 'unmanaged'", name="ck_runtime_bindings_managed_rows_only"),
        Index(
            "uq_runtime_bindings_single_active",
            "runtime_installation_id",
            unique=True,
            sqlite_where=text("state = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    runtime_installation_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("runtime_installations.id", ondelete="RESTRICT"), nullable=False
    )
    runtime_profile_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_id: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[RuntimeBindingState] = mapped_column(
        Enum(
            RuntimeBindingState,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="runtime_binding_state",
        ),
        nullable=False,
    )
    previous_binding_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("runtime_provider_bindings.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    runtime: Mapped[RuntimeInstallation] = relationship(back_populates="bindings", viewonly=True)
    profile: Mapped[RuntimeProviderProfile] = relationship(back_populates="bindings", viewonly=True)
    previous_binding: Mapped[RuntimeProviderBinding | None] = relationship(
        remote_side="RuntimeProviderBinding.id", viewonly=True
    )
    session_bindings: Mapped[list[RuntimeSessionProviderBinding]] = relationship(
        back_populates="runtime_binding", viewonly=True
    )
    transactions: Mapped[list[ProviderConfigTransaction]] = relationship(
        back_populates="runtime_binding", viewonly=True
    )


class RuntimeSessionProviderBinding(Base):
    """Immutable effective-binding evidence for one AgentBox Runtime session."""

    __tablename__ = "runtime_session_provider_bindings"
    __table_args__ = (
        UniqueConstraint("runtime_session_id", name="uq_session_bindings_runtime_session"),
        ForeignKeyConstraint(
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
        CheckConstraint("runtime_binding_revision >= 1", name="ck_session_binding_revision"),
        CheckConstraint("runtime_profile_revision >= 1", name="ck_session_profile_revision"),
        CheckConstraint("provider_revision >= 1", name="ck_session_provider_revision"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    runtime_session_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_installation_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("runtime_installations.id", ondelete="RESTRICT"), nullable=False
    )
    runtime_binding_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_binding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_profile_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_id: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_class: Mapped[SessionEvidenceClass] = mapped_column(
        Enum(
            SessionEvidenceClass,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="session_binding_evidence_class",
        ),
        nullable=False,
    )
    state: Mapped[SessionBindingState] = mapped_column(
        Enum(
            SessionBindingState,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="session_binding_state",
        ),
        nullable=False,
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    runtime_binding: Mapped[RuntimeProviderBinding] = relationship(
        back_populates="session_bindings", viewonly=True
    )


class ProviderCompatibilityObservation(Base):
    """One typed dimension in a bounded compatibility evidence set."""

    __tablename__ = "provider_compatibility_observations"
    __table_args__ = (
        UniqueConstraint(
            "observation_set_id",
            "dimension",
            name="uq_provider_compatibility_set_dimension",
        ),
        ForeignKeyConstraint(
            ["runtime_profile_id", "runtime_installation_id", "provider_id"],
            [
                "runtime_provider_profiles.id",
                "runtime_provider_profiles.runtime_installation_id",
                "runtime_provider_profiles.provider_id",
            ],
            ondelete="RESTRICT",
            name="fk_compatibility_observation_profile_identity",
        ),
        CheckConstraint("evidence_schema_version >= 1", name="ck_compatibility_evidence_schema"),
        CheckConstraint(
            "(runtime_profile_id IS NULL AND runtime_installation_id IS NULL) OR "
            "(runtime_profile_id IS NOT NULL AND runtime_installation_id IS NOT NULL)",
            name="ck_compatibility_runtime_profile_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    observation_set_id: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("provider_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    runtime_installation_id: Mapped[str | None] = mapped_column(String(40))
    runtime_profile_id: Mapped[str | None] = mapped_column(String(40))
    dimension: Mapped[CompatibilityDimension] = mapped_column(
        Enum(
            CompatibilityDimension,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="compatibility_dimension",
        ),
        nullable=False,
    )
    state: Mapped[CompatibilityState] = mapped_column(
        Enum(
            CompatibilityState,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="compatibility_state",
        ),
        nullable=False,
    )
    evidence_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_code: Mapped[str | None] = mapped_column(String(80))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    provider: Mapped[Provider] = relationship(back_populates="observations", viewonly=True)
    profile: Mapped[RuntimeProviderProfile | None] = relationship(
        back_populates="observations", viewonly=True
    )


class ProviderConfigTransaction(Base):
    """Non-secret control-plane orchestration metadata for a future transaction."""

    __tablename__ = "provider_config_transactions"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_provider_config_transactions_job"),
        ForeignKeyConstraint(
            ["runtime_binding_id", "runtime_installation_id"],
            ["runtime_provider_bindings.id", "runtime_provider_bindings.runtime_installation_id"],
            ondelete="RESTRICT",
            name="fk_provider_transactions_binding_runtime",
        ),
        CheckConstraint("expected_binding_revision >= 1", name="ck_tx_binding_revision"),
        CheckConstraint("expected_profile_revision >= 1", name="ck_tx_profile_revision"),
        CheckConstraint("expected_provider_revision >= 1", name="ck_tx_provider_revision"),
        CheckConstraint(
            "expected_credential_revision IS NULL OR expected_credential_revision >= 1",
            name="ck_tx_credential_revision",
        ),
        CheckConstraint("revision >= 1", name="ck_provider_transactions_revision"),
        CheckConstraint(
            "runtime_snapshot_ref IS NULL OR "
            "(length(runtime_snapshot_ref) = 36 "
            "AND substr(runtime_snapshot_ref, 1, 4) = 'snp_' "
            "AND substr(runtime_snapshot_ref, 5) NOT GLOB '*[^0-9a-f]*')",
            name="ck_provider_transactions_snapshot_reference_format",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    runtime_installation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    runtime_binding_id: Mapped[str] = mapped_column(String(40), nullable=False)
    job_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    state: Mapped[ConfigTransactionState] = mapped_column(
        Enum(
            ConfigTransactionState,
            values_callable=_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="provider_config_transaction_state",
        ),
        nullable=False,
    )
    expected_binding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_provider_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_credential_revision: Mapped[int | None] = mapped_column(Integer)
    plan_digest: Mapped[str | None] = mapped_column(String(64))
    runtime_snapshot_ref: Mapped[str | None] = mapped_column(String(40))
    outcome_code: Mapped[str | None] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    runtime_binding: Mapped[RuntimeProviderBinding] = relationship(
        back_populates="transactions", viewonly=True
    )
