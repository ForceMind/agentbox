"""Repository boundary for the non-secret Phase 11 Provider core.

This module intentionally exposes metadata operations only. It contains no
Runtime client, filesystem access, Provider HTTP client, configuration adapter,
credential provisioning, or activation operation.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentbox_core.clock import Clock
from agentbox_core.database import Database
from agentbox_core.errors import (
    ProviderInputInvalid,
    ProviderMetadataConflict,
    ProviderMetadataNotFound,
    ProviderRevisionConflict,
)
from agentbox_core.provider_models import (
    CompatibilityDimension,
    CompatibilityState,
    CredentialKind,
    CredentialLifecycleState,
    Provider,
    ProviderCompatibilityObservation,
    ProviderCredential,
    ProviderLifecycleState,
    ProviderType,
    RuntimeBindingState,
    RuntimeInstallation,
    RuntimeProfileState,
    RuntimeProviderBinding,
    RuntimeProviderProfile,
    RuntimeSessionProviderBinding,
    RuntimeType,
    SessionBindingState,
    SessionEvidenceClass,
    WireProtocol,
)
from agentbox_core.security import new_identifier

OFFICIAL_OPENAI_ENDPOINT = "https://api.openai.com/v1"

_MODEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,126}[A-Za-z0-9])?")
_OPAQUE_ID = re.compile(r"[a-z]{3}_[0-9a-f]{32}")
_SECRET_REFERENCE = re.compile(r"sec_[0-9a-f]{32}")
_EVIDENCE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,79}")


class AuditRecorder(Protocol):
    def record(
        self,
        session: Session,
        *,
        actor_type: str,
        actor_id: str | None,
        action: str,
        result: str,
        request_id: str | None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object: ...


@dataclass(frozen=True)
class ProviderCreate:
    display_name: str
    provider_type: ProviderType
    model: str
    endpoint: str | None = None
    wire_protocol: WireProtocol = WireProtocol.RESPONSES


@dataclass(frozen=True)
class CredentialMetadataCreate:
    provider_id: str
    kind: CredentialKind
    runtime_secret_ref: str | None = None
    secret_version: int | None = None


@dataclass(frozen=True)
class RuntimeProfileCreate:
    runtime_installation_id: str
    provider_id: str
    provider_revision: int
    adapter_schema_version: int
    credential_id: str | None = None
    credential_revision: int | None = None
    credential_secret_version: int | None = None


@dataclass(frozen=True)
class RuntimeBindingCreate:
    runtime_installation_id: str
    runtime_profile_id: str
    runtime_profile_revision: int
    previous_binding_id: str | None = None


@dataclass(frozen=True)
class SessionBindingCreate:
    runtime_session_id: str
    runtime_binding_id: str
    runtime_binding_revision: int
    evidence_class: SessionEvidenceClass


@dataclass(frozen=True)
class CompatibilityObservationCreate:
    observation_set_id: str
    provider_id: str
    dimension: CompatibilityDimension
    state: CompatibilityState
    evidence_schema_version: int
    evidence_code: str | None = None
    runtime_installation_id: str | None = None
    runtime_profile_id: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class RuntimeProviderManagement:
    runtime_installation_id: str
    state: RuntimeBindingState
    runtime_binding_id: str | None
    binding_revision: int | None


class ProviderRepository:
    """Typed control-plane repository with optimistic revision checks."""

    def __init__(self, database: Database, clock: Clock, audit: AuditRecorder) -> None:
        self._database = database
        self._clock = clock
        self._audit = audit

    def register_runtime_installation(
        self,
        *,
        runtime_type: RuntimeType,
        display_name: str,
        actor_id: str,
        request_id: str | None = None,
    ) -> RuntimeInstallation:
        now = self._clock.now()
        runtime = RuntimeInstallation(
            id=new_identifier("rti"),
            runtime_type=runtime_type,
            display_name=_safe_label(display_name),
            revision=1,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._database.transaction() as session:
                session.add(runtime)
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=actor_id,
                    action="runtime_installation.registered",
                    result="succeeded",
                    request_id=request_id,
                    target_type="runtime_installation",
                    target_id=runtime.id,
                    metadata={"runtime_type": runtime_type.value, "revision": 1},
                )
                session.flush()
                return runtime
        except IntegrityError as exc:
            raise ProviderMetadataConflict() from exc

    def create_provider(
        self,
        values: ProviderCreate,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> Provider:
        endpoint = _provider_endpoint(values.provider_type, values.endpoint)
        now = self._clock.now()
        provider = Provider(
            id=new_identifier("prv"),
            identity_schema_version=1,
            display_name=_safe_label(values.display_name),
            provider_type=values.provider_type,
            endpoint=endpoint,
            wire_protocol=values.wire_protocol,
            model=_safe_model(values.model),
            state=ProviderLifecycleState.CONFIGURED,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._database.transaction() as session:
                session.add(provider)
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=actor_id,
                    action="provider.created",
                    result="succeeded",
                    request_id=request_id,
                    target_type="provider",
                    target_id=provider.id,
                    metadata={"provider_type": values.provider_type.value, "revision": 1},
                )
                session.flush()
                return provider
        except IntegrityError as exc:
            raise ProviderMetadataConflict() from exc

    def get_provider(self, provider_id: str) -> Provider:
        _require_id(provider_id)
        with self._database.transaction() as session:
            provider = session.get(Provider, provider_id)
            if provider is None:
                raise ProviderMetadataNotFound()
            return provider

    def list_providers(self, *, include_disabled: bool = False) -> tuple[Provider, ...]:
        with self._database.transaction() as session:
            query = select(Provider)
            if not include_disabled:
                query = query.where(Provider.state != ProviderLifecycleState.DISABLED)
            return tuple(session.scalars(query.order_by(Provider.created_at, Provider.id)))

    def update_provider_display_name(
        self,
        provider_id: str,
        *,
        display_name: str,
        expected_revision: int,
        actor_id: str,
        request_id: str | None = None,
    ) -> Provider:
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            provider = _provider_for_update(session, provider_id, expected_revision)
            provider.display_name = _safe_label(display_name)
            provider.revision += 1
            provider.updated_at = self._clock.now()
            self._audit.record(
                session,
                actor_type="admin_user",
                actor_id=actor_id,
                action="provider.updated",
                result="succeeded",
                request_id=request_id,
                target_type="provider",
                target_id=provider.id,
                metadata={"revision": provider.revision},
            )
            session.flush()
            return provider

    def disable_provider(
        self,
        provider_id: str,
        *,
        expected_revision: int,
        actor_id: str,
        request_id: str | None = None,
    ) -> Provider:
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            provider = _provider_for_update(session, provider_id, expected_revision)
            if session.scalar(
                select(RuntimeProviderBinding.id).where(
                    RuntimeProviderBinding.provider_id == provider.id,
                    RuntimeProviderBinding.state == RuntimeBindingState.ACTIVE,
                )
            ):
                raise ProviderMetadataConflict()
            provider.state = ProviderLifecycleState.DISABLED
            provider.revision += 1
            provider.updated_at = self._clock.now()
            self._audit.record(
                session,
                actor_type="admin_user",
                actor_id=actor_id,
                action="provider.disabled",
                result="succeeded",
                request_id=request_id,
                target_type="provider",
                target_id=provider.id,
                metadata={"revision": provider.revision},
            )
            session.flush()
            return provider

    def create_credential_metadata(
        self,
        values: CredentialMetadataCreate,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> ProviderCredential:
        reference, version, state = _credential_reference(
            values.runtime_secret_ref, values.secret_version
        )
        now = self._clock.now()
        credential = ProviderCredential(
            id=new_identifier("crd"),
            provider_id=_require_id(values.provider_id),
            kind=values.kind,
            runtime_secret_ref=reference,
            secret_version=version,
            state=state,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._database.transaction() as session:
                if session.get(Provider, credential.provider_id) is None:
                    raise ProviderMetadataNotFound()
                session.add(credential)
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=actor_id,
                    action="provider_credential.created",
                    result="succeeded",
                    request_id=request_id,
                    target_type="provider_credential",
                    target_id=credential.id,
                    metadata={"configured": reference is not None, "revision": 1},
                )
                session.flush()
                return credential
        except IntegrityError as exc:
            raise ProviderMetadataConflict() from exc

    def get_credential_metadata(self, credential_id: str) -> ProviderCredential:
        _require_id(credential_id)
        with self._database.transaction() as session:
            credential = session.get(ProviderCredential, credential_id)
            if credential is None:
                raise ProviderMetadataNotFound()
            return credential

    def update_credential_state(
        self,
        credential_id: str,
        *,
        state: CredentialLifecycleState,
        expected_revision: int,
        actor_id: str,
        request_id: str | None = None,
    ) -> ProviderCredential:
        if state is CredentialLifecycleState.CONFIGURED:
            raise ProviderInputInvalid()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            credential = session.get(ProviderCredential, _require_id(credential_id))
            if credential is None:
                raise ProviderMetadataNotFound()
            _require_revision(credential.revision, expected_revision)
            credential.state = state
            credential.revision += 1
            credential.updated_at = self._clock.now()
            self._audit.record(
                session,
                actor_type="admin_user",
                actor_id=actor_id,
                action="provider_credential.state_changed",
                result="succeeded",
                request_id=request_id,
                target_type="provider_credential",
                target_id=credential.id,
                metadata={"state": state.value, "revision": credential.revision},
            )
            session.flush()
            return credential

    def create_runtime_profile(
        self,
        values: RuntimeProfileCreate,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> RuntimeProviderProfile:
        if values.provider_revision < 1 or values.adapter_schema_version < 1:
            raise ProviderInputInvalid()
        now = self._clock.now()
        with self._database.transaction() as session:
            runtime = session.get(RuntimeInstallation, _require_id(values.runtime_installation_id))
            provider = session.get(Provider, _require_id(values.provider_id))
            if runtime is None or provider is None:
                raise ProviderMetadataNotFound()
            if runtime.runtime_type is not RuntimeType.CODEX:
                raise ProviderInputInvalid()
            _require_revision(provider.revision, values.provider_revision)
            credential = self._profile_credential(session, values)
            profile = RuntimeProviderProfile(
                id=new_identifier("rpf"),
                runtime_installation_id=runtime.id,
                provider_id=provider.id,
                provider_revision=provider.revision,
                credential_id=credential.id if credential else None,
                credential_revision=credential.revision if credential else None,
                credential_secret_version=credential.secret_version if credential else None,
                adapter_type=RuntimeType.CODEX,
                adapter_schema_version=values.adapter_schema_version,
                state=RuntimeProfileState.DRAFT,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
            self._audit.record(
                session,
                actor_type="admin_user",
                actor_id=actor_id,
                action="runtime_profile.created",
                result="succeeded",
                request_id=request_id,
                target_type="runtime_profile",
                target_id=profile.id,
                metadata={"adapter_type": RuntimeType.CODEX.value, "revision": 1},
            )
            session.flush()
            return profile

    def get_runtime_profile(self, profile_id: str) -> RuntimeProviderProfile:
        _require_id(profile_id)
        with self._database.transaction() as session:
            profile = session.get(RuntimeProviderProfile, profile_id)
            if profile is None:
                raise ProviderMetadataNotFound()
            return profile

    def create_runtime_binding(
        self,
        values: RuntimeBindingCreate,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> RuntimeProviderBinding:
        if values.runtime_profile_revision < 1:
            raise ProviderInputInvalid()
        now = self._clock.now()
        with self._database.transaction() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            profile = session.get(RuntimeProviderProfile, _require_id(values.runtime_profile_id))
            if profile is None or profile.runtime_installation_id != values.runtime_installation_id:
                raise ProviderMetadataNotFound()
            _require_revision(profile.revision, values.runtime_profile_revision)
            previous = None
            if values.previous_binding_id is not None:
                previous = session.get(
                    RuntimeProviderBinding, _require_id(values.previous_binding_id)
                )
                if (
                    previous is None
                    or previous.runtime_installation_id != profile.runtime_installation_id
                ):
                    raise ProviderMetadataConflict()
            binding = RuntimeProviderBinding(
                id=new_identifier("rbd"),
                runtime_installation_id=profile.runtime_installation_id,
                runtime_profile_id=profile.id,
                runtime_profile_revision=profile.revision,
                provider_id=profile.provider_id,
                provider_revision=profile.provider_revision,
                state=RuntimeBindingState.PENDING,
                previous_binding_id=previous.id if previous else None,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            session.add(binding)
            self._audit.record(
                session,
                actor_type="admin_user",
                actor_id=actor_id,
                action="runtime_binding.created",
                result="succeeded",
                request_id=request_id,
                target_type="runtime_binding",
                target_id=binding.id,
                metadata={"state": RuntimeBindingState.PENDING.value, "revision": 1},
            )
            session.flush()
            return binding

    def get_runtime_binding(self, binding_id: str) -> RuntimeProviderBinding:
        _require_id(binding_id)
        with self._database.transaction() as session:
            binding = session.get(RuntimeProviderBinding, binding_id)
            if binding is None:
                raise ProviderMetadataNotFound()
            return binding

    def runtime_management(self, runtime_installation_id: str) -> RuntimeProviderManagement:
        _require_id(runtime_installation_id)
        with self._database.transaction() as session:
            active = session.scalar(
                select(RuntimeProviderBinding).where(
                    RuntimeProviderBinding.runtime_installation_id == runtime_installation_id,
                    RuntimeProviderBinding.state == RuntimeBindingState.ACTIVE,
                )
            )
            binding = active or session.scalar(
                select(RuntimeProviderBinding)
                .where(RuntimeProviderBinding.runtime_installation_id == runtime_installation_id)
                .order_by(
                    RuntimeProviderBinding.created_at.desc(),
                    RuntimeProviderBinding.id.desc(),
                )
                .limit(1)
            )
            if binding is None:
                return RuntimeProviderManagement(
                    runtime_installation_id=runtime_installation_id,
                    state=RuntimeBindingState.UNMANAGED,
                    runtime_binding_id=None,
                    binding_revision=None,
                )
            return RuntimeProviderManagement(
                runtime_installation_id=runtime_installation_id,
                state=binding.state,
                runtime_binding_id=binding.id,
                binding_revision=binding.revision,
            )

    def create_session_binding(
        self,
        values: SessionBindingCreate,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> RuntimeSessionProviderBinding:
        if values.runtime_binding_revision < 1:
            raise ProviderInputInvalid()
        now = self._clock.now()
        try:
            with self._database.transaction() as session:
                binding = session.get(
                    RuntimeProviderBinding, _require_id(values.runtime_binding_id)
                )
                if binding is None or binding.state is not RuntimeBindingState.ACTIVE:
                    raise ProviderMetadataConflict()
                _require_revision(binding.revision, values.runtime_binding_revision)
                session_binding = RuntimeSessionProviderBinding(
                    id=new_identifier("sbd"),
                    runtime_session_id=_require_id(values.runtime_session_id),
                    runtime_installation_id=binding.runtime_installation_id,
                    runtime_binding_id=binding.id,
                    runtime_binding_revision=binding.revision,
                    runtime_profile_id=binding.runtime_profile_id,
                    runtime_profile_revision=binding.runtime_profile_revision,
                    provider_id=binding.provider_id,
                    provider_revision=binding.provider_revision,
                    evidence_class=values.evidence_class,
                    state=SessionBindingState.BOUND,
                    effective_at=now,
                    created_at=now,
                )
                session.add(session_binding)
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=actor_id,
                    action="session_binding.recorded",
                    result="succeeded",
                    request_id=request_id,
                    target_type="session_binding",
                    target_id=session_binding.id,
                    metadata={"state": SessionBindingState.BOUND.value},
                )
                session.flush()
                return session_binding
        except IntegrityError as exc:
            raise ProviderMetadataConflict() from exc

    def get_session_binding(self, session_binding_id: str) -> RuntimeSessionProviderBinding:
        _require_id(session_binding_id)
        with self._database.transaction() as session:
            value = session.get(RuntimeSessionProviderBinding, session_binding_id)
            if value is None:
                raise ProviderMetadataNotFound()
            return value

    def record_compatibility_observation(
        self,
        values: CompatibilityObservationCreate,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> ProviderCompatibilityObservation:
        if values.evidence_schema_version < 1:
            raise ProviderInputInvalid()
        _require_id(values.observation_set_id)
        evidence_code = _safe_evidence_code(values.evidence_code)
        try:
            with self._database.transaction() as session:
                provider = session.get(Provider, _require_id(values.provider_id))
                if provider is None:
                    raise ProviderMetadataNotFound()
                profile = None
                if (values.runtime_installation_id is None) != (values.runtime_profile_id is None):
                    raise ProviderInputInvalid()
                if values.runtime_profile_id is not None:
                    profile = session.get(
                        RuntimeProviderProfile, _require_id(values.runtime_profile_id)
                    )
                    if (
                        profile is None
                        or profile.runtime_installation_id != values.runtime_installation_id
                        or profile.provider_id != provider.id
                    ):
                        raise ProviderMetadataConflict()
                observation = ProviderCompatibilityObservation(
                    id=new_identifier("pco"),
                    observation_set_id=values.observation_set_id,
                    provider_id=provider.id,
                    runtime_installation_id=(profile.runtime_installation_id if profile else None),
                    runtime_profile_id=profile.id if profile else None,
                    dimension=values.dimension,
                    state=values.state,
                    evidence_schema_version=values.evidence_schema_version,
                    evidence_code=evidence_code,
                    observed_at=self._clock.now(),
                    expires_at=values.expires_at,
                )
                session.add(observation)
                self._audit.record(
                    session,
                    actor_type="admin_user",
                    actor_id=actor_id,
                    action="compatibility_observation.recorded",
                    result="succeeded",
                    request_id=request_id,
                    target_type="compatibility_observation",
                    target_id=observation.id,
                    metadata={
                        "dimension": values.dimension.value,
                        "state": values.state.value,
                    },
                )
                session.flush()
                return observation
        except IntegrityError as exc:
            raise ProviderMetadataConflict() from exc

    @staticmethod
    def _profile_credential(
        session: Session, values: RuntimeProfileCreate
    ) -> ProviderCredential | None:
        supplied = (
            values.credential_id,
            values.credential_revision,
            values.credential_secret_version,
        )
        if supplied == (None, None, None):
            return None
        if any(item is None for item in supplied):
            raise ProviderInputInvalid()
        credential = session.get(ProviderCredential, _require_id(values.credential_id or ""))
        if credential is None or credential.provider_id != values.provider_id:
            raise ProviderMetadataConflict()
        _require_revision(credential.revision, values.credential_revision or 0)
        if credential.secret_version != values.credential_secret_version:
            raise ProviderRevisionConflict()
        if credential.state is not CredentialLifecycleState.CONFIGURED:
            raise ProviderMetadataConflict()
        return credential


def _provider_for_update(session: Session, provider_id: str, expected_revision: int) -> Provider:
    provider = session.get(Provider, _require_id(provider_id))
    if provider is None:
        raise ProviderMetadataNotFound()
    _require_revision(provider.revision, expected_revision)
    return provider


def _require_revision(current: int, expected: int) -> None:
    if expected < 1:
        raise ProviderInputInvalid()
    if current != expected:
        raise ProviderRevisionConflict()


def _require_id(value: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value):
        raise ProviderInputInvalid()
    return value


def _safe_label(value: str) -> str:
    if not isinstance(value, str):
        raise ProviderInputInvalid()
    normalized = unicodedata.normalize("NFC", value).strip()
    if (
        normalized != value.strip()
        or not 1 <= len(normalized) <= 128
        or any(unicodedata.category(character).startswith("C") for character in normalized)
    ):
        raise ProviderInputInvalid()
    return normalized


def _safe_model(value: str) -> str:
    if not isinstance(value, str) or not _MODEL.fullmatch(value):
        raise ProviderInputInvalid()
    return value


def _provider_endpoint(provider_type: ProviderType, endpoint: str | None) -> str:
    if provider_type is ProviderType.OFFICIAL_OPENAI:
        if endpoint is not None and endpoint != OFFICIAL_OPENAI_ENDPOINT:
            raise ProviderInputInvalid()
        return OFFICIAL_OPENAI_ENDPOINT
    if provider_type is not ProviderType.OPENAI_COMPATIBLE or endpoint is None:
        raise ProviderInputInvalid()
    return _normalize_https_endpoint(endpoint)


def _normalize_https_endpoint(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 512
        or value != value.strip()
        or "%" in value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        raise ProviderInputInvalid()
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ProviderInputInvalid() from exc
    if (
        parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderInputInvalid()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ProviderInputInvalid()
    try:
        normalized_host = hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise ProviderInputInvalid() from exc
    if (
        not normalized_host
        or len(normalized_host) > 253
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not re.fullmatch(r"[a-z0-9-]+", label)
            for label in normalized_host.split(".")
        )
    ):
        raise ProviderInputInvalid()
    path = parsed.path.rstrip("/")
    if "//" in path or any(part in {".", ".."} for part in path.split("/")):
        raise ProviderInputInvalid()
    return urlunsplit(("https", normalized_host, path, "", ""))


def _credential_reference(
    reference: str | None, version: int | None
) -> tuple[str | None, int | None, CredentialLifecycleState]:
    if reference is None and version is None:
        return None, None, CredentialLifecycleState.MISSING
    if (
        reference is None
        or version is None
        or version < 1
        or not _SECRET_REFERENCE.fullmatch(reference)
    ):
        raise ProviderInputInvalid()
    return reference, version, CredentialLifecycleState.CONFIGURED


def _safe_evidence_code(value: str | None) -> str | None:
    if value is None:
        return None
    if not _EVIDENCE_CODE.fullmatch(value):
        raise ProviderInputInvalid()
    return value
