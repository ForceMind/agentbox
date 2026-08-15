from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from pathlib import Path

from agentbox_core.models import Base
from agentbox_core.provider_models import (
    Provider,
    ProviderCompatibilityEvidenceSet,
    ProviderCompatibilityObservation,
    ProviderCredential,
    RuntimeInstallation,
    RuntimeProviderBinding,
    RuntimeProviderProfile,
    RuntimeSessionProviderBinding,
)
from agentbox_core.providers import (
    CompatibilityDimensionResult,
    CompatibilityEvidenceSetCreate,
    CredentialMetadataCreate,
    ProviderCreate,
    RuntimeBindingCreate,
    RuntimeProfileCreate,
    RuntimeProviderManagement,
    SessionBindingCreate,
)
from sqlalchemy import JSON

NEW_TABLE_COLUMNS = {
    "runtime_installations": {
        "id",
        "runtime_type",
        "display_name",
        "revision",
        "created_at",
        "updated_at",
    },
    "provider_definitions": {
        "id",
        "identity_schema_version",
        "display_name",
        "provider_type",
        "endpoint",
        "wire_protocol",
        "model",
        "state",
        "revision",
        "created_at",
        "updated_at",
    },
    "provider_credentials": {
        "id",
        "provider_id",
        "kind",
        "runtime_secret_ref",
        "secret_version",
        "state",
        "revision",
        "created_at",
        "updated_at",
    },
    "runtime_provider_profiles": {
        "id",
        "runtime_installation_id",
        "provider_id",
        "provider_revision",
        "credential_id",
        "credential_revision",
        "credential_secret_version",
        "adapter_type",
        "adapter_schema_version",
        "state",
        "revision",
        "created_at",
        "updated_at",
    },
    "runtime_provider_bindings": {
        "id",
        "runtime_installation_id",
        "runtime_profile_id",
        "runtime_profile_revision",
        "provider_id",
        "provider_revision",
        "state",
        "previous_binding_id",
        "revision",
        "created_at",
        "updated_at",
    },
    "runtime_session_provider_bindings": {
        "id",
        "runtime_session_id",
        "runtime_installation_id",
        "runtime_binding_id",
        "runtime_binding_revision",
        "runtime_profile_id",
        "runtime_profile_revision",
        "provider_id",
        "provider_revision",
        "evidence_class",
        "effective_at",
        "created_at",
    },
    "provider_compatibility_evidence_sets": {
        "id",
        "provider_id",
        "provider_revision",
        "runtime_installation_id",
        "runtime_profile_id",
        "runtime_profile_revision",
        "credential_id",
        "credential_revision",
        "credential_secret_version",
        "evidence_schema_version",
        "expected_dimension_mask",
        "state",
        "observed_at",
        "expires_at",
        "sealed_at",
    },
    "provider_compatibility_observations": {
        "id",
        "evidence_set_id",
        "dimension",
        "state",
        "evidence_code",
    },
}

SAFE_OPAQUE_REFERENCE_COLUMNS = {
    "runtime_secret_ref",
    "secret_version",
    "credential_secret_version",
}

FORBIDDEN_STORAGE_NAMES = {
    "api_key",
    "secret",
    "secret_value",
    "token",
    "bearer",
    "authorization",
    "password",
    "ciphertext",
    "nonce",
    "tag",
    "dek",
    "kek",
    "master_key",
    "private_key",
    "raw_config",
    "toml",
    "command",
    "argv",
    "environment",
    "headers",
}


def test_new_schema_is_exact_typed_and_contains_no_generic_payload_column() -> None:
    assert set(NEW_TABLE_COLUMNS).issubset(Base.metadata.tables)
    assert "provider_config_transactions" not in Base.metadata.tables
    for table_name, expected_columns in NEW_TABLE_COLUMNS.items():
        table = Base.metadata.tables[table_name]
        actual_columns = {column.name for column in table.columns}
        assert actual_columns == expected_columns
        assert all(not isinstance(column.type, JSON) for column in table.columns)
        for column_name in actual_columns - SAFE_OPAQUE_REFERENCE_COLUMNS:
            assert column_name not in FORBIDDEN_STORAGE_NAMES


def test_credential_table_reserves_only_opaque_references_not_secret_material() -> None:
    columns = NEW_TABLE_COLUMNS["provider_credentials"]
    assert SAFE_OPAQUE_REFERENCE_COLUMNS & columns == {
        "runtime_secret_ref",
        "secret_version",
    }
    assert not (
        {
            "secret_value",
            "ciphertext",
            "nonce",
            "tag",
            "dek",
            "kek",
            "master_key",
        }
        & columns
    )


def test_slice_one_inputs_have_no_generic_or_secret_bearing_field() -> None:
    input_types = (
        ProviderCreate,
        CredentialMetadataCreate,
        RuntimeProfileCreate,
        RuntimeBindingCreate,
        SessionBindingCreate,
        CompatibilityDimensionResult,
        CompatibilityEvidenceSetCreate,
        RuntimeProviderManagement,
    )
    allowed = SAFE_OPAQUE_REFERENCE_COLUMNS | {"credential_secret_version"}
    for input_type in input_types:
        assert is_dataclass(input_type)
        names = {field.name for field in fields(input_type)}
        assert not ((names - allowed) & FORBIDDEN_STORAGE_NAMES)
        assert not ({"options", "metadata", "payload", "config", "parameters"} & names)
    assert {field.name for field in fields(CredentialMetadataCreate)} == {
        "provider_id",
        "kind",
    }
    assert "id" not in {field.name for field in fields(CompatibilityEvidenceSetCreate)}
    assert "observation_set_id" not in {
        field.name for field in fields(CompatibilityEvidenceSetCreate)
    }


def test_compatibility_child_cannot_mix_provider_or_runtime_scope() -> None:
    columns = NEW_TABLE_COLUMNS["provider_compatibility_observations"]
    assert (
        not {
            "provider_id",
            "provider_revision",
            "runtime_installation_id",
            "runtime_profile_id",
            "runtime_profile_revision",
            "credential_id",
            "credential_revision",
            "credential_secret_version",
        }
        & columns
    )


def test_session_binding_contains_no_credential_secret_or_runtime_private_state() -> None:
    columns = NEW_TABLE_COLUMNS["runtime_session_provider_bindings"]
    assert "state" not in columns
    assert (
        not {
            "credential_id",
            "runtime_secret_ref",
            "secret_version",
            "conversation",
            "jsonl",
            "rollout",
            "runtime_data",
        }
        & columns
    )


def test_provider_repository_has_no_runtime_network_or_privilege_dependency() -> None:
    source_path = Path("packages/agentbox-core/src/agentbox_core/providers.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)} | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    forbidden_roots = {
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "pathlib",
        "agentbox_runtime",
        "agentbox_helper",
        "cryptography",
    }
    assert not {name.split(".", maxsplit=1)[0] for name in imports} & forbidden_roots


def test_slice_one_exposes_no_provider_disable_transition() -> None:
    from agentbox_core.providers import ProviderRepository

    assert not hasattr(ProviderRepository, "disable_provider")


def test_entity_identities_are_not_collapsed_in_the_orm() -> None:
    primary_keys = {
        model.__name__: tuple(column.name for column in model.__table__.primary_key)
        for model in (
            Provider,
            ProviderCredential,
            RuntimeInstallation,
            RuntimeProviderProfile,
            RuntimeProviderBinding,
            RuntimeSessionProviderBinding,
            ProviderCompatibilityEvidenceSet,
            ProviderCompatibilityObservation,
        )
    }
    assert all(value == ("id",) for value in primary_keys.values())
