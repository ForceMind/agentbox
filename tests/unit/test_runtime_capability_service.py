from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, timedelta
from pathlib import Path

import pytest
from agentbox_core.configuration import Settings
from agentbox_core.errors import (
    ProviderMetadataNotFound,
    RuntimeCapabilityEvidenceExpired,
    RuntimeCapabilityReportInvalid,
    RuntimeInstallationRevisionConflict,
)
from agentbox_core.models import AuditEvent
from agentbox_core.provider_models import (
    Provider,
    ProviderCompatibilityEvidenceSet,
    ProviderCompatibilityObservation,
    ProviderCredential,
    RuntimeInstallation,
    RuntimeProviderBinding,
    RuntimeProviderProfile,
    RuntimeSessionProviderBinding,
    RuntimeType,
)
from agentbox_core.runtime_capabilities import RuntimeCapabilityClient, RuntimeCapabilityService
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.runtime_capabilities import (
    CLAUDE_CAPABILITY_NAMES,
    CODEX_CAPABILITY_NAMES,
    RuntimeAdapterID,
    RuntimeAuthenticationState,
    RuntimeCapabilityCollectionState,
    RuntimeCapabilityFindingCode,
    RuntimeCapabilityName,
    RuntimeCapabilityObservation,
    RuntimeCapabilityOutcome,
    RuntimeCapabilityReport,
    RuntimeCapabilitySet,
    RuntimeConfigOwnershipState,
    RuntimeEvidenceClass,
    RuntimeEvidenceLifecycle,
    RuntimeInstallationType,
    RuntimeRemoteState,
)
from agentbox_protocol.runtime_capabilities import (
    RuntimeType as WireRuntimeType,
)
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.rpc import UnixRuntimeCapabilityClient
from conftest import FakeClock
from sqlalchemy import func, inspect, select, update
from sqlalchemy.engine import make_url

ACTOR_ID = "adm_00000000000000000000000000000000"
RAW_CANARY = "RUNTIME-RAW-SECRET-CANARY-DO-NOT-PERSIST"


def make_report(
    *,
    runtime_id: str,
    revision: int,
    runtime_type: WireRuntimeType,
    clock: FakeClock,
) -> RuntimeCapabilityReport:
    observed_at = clock.now().replace(tzinfo=UTC)
    names = (
        CODEX_CAPABILITY_NAMES if runtime_type is WireRuntimeType.CODEX else CLAUDE_CAPABILITY_NAMES
    )
    observations = tuple(
        RuntimeCapabilityObservation(
            name=name,
            outcome=RuntimeCapabilityOutcome.UNKNOWN,
            lifecycle=RuntimeEvidenceLifecycle.VALIDATED,
            evidence_class=RuntimeEvidenceClass.QUALIFIED_PUBLIC_CONTRACT,
            finding_code=RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,
            dependencies=(
                (
                    RuntimeCapabilityName.CLAUDE_INSTALLED,
                    RuntimeCapabilityName.TMUX_AVAILABLE,
                )
                if name is RuntimeCapabilityName.CLAUDE_SESSION_INSPECT_MANAGED
                else ()
            ),
            observed_at=observed_at,
            expires_at=observed_at + timedelta(seconds=60),
        )
        for name in names
    )
    return RuntimeCapabilityReport(
        runtime_installation_id=runtime_id,
        runtime_installation_revision=revision,
        runtime_type=runtime_type,
        capability_set=(
            RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1
            if runtime_type is WireRuntimeType.CODEX
            else RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1
        ),
        adapter_id=(
            RuntimeAdapterID.CODEX_RUNTIME_ADAPTER_V1
            if runtime_type is WireRuntimeType.CODEX
            else RuntimeAdapterID.CLAUDE_RUNTIME_ADAPTER_V1
        ),
        collection_state=RuntimeCapabilityCollectionState.COMPLETE,
        runtime_version="0.146.1",
        installation_type=(
            RuntimeInstallationType.STANDALONE
            if runtime_type is WireRuntimeType.CODEX
            else RuntimeInstallationType.NOT_APPLICABLE
        ),
        authentication_state=RuntimeAuthenticationState.UNKNOWN,
        remote_state=RuntimeRemoteState.UNKNOWN,
        config_ownership_state=(
            RuntimeConfigOwnershipState.UNKNOWN
            if runtime_type is WireRuntimeType.CODEX
            else RuntimeConfigOwnershipState.NOT_APPLICABLE
        ),
        managed_session_count=None,
        observed_at=observed_at,
        expires_at=observed_at + timedelta(seconds=60),
        observations=observations,
        findings=(RuntimeCapabilityFindingCode.PUBLIC_CONTRACT_UNQUALIFIED,),
    )


class FakeClient:
    def __init__(
        self,
        factory: Callable[
            [str, int, WireRuntimeType, RuntimeCapabilitySet], RuntimeCapabilityReport
        ],
    ) -> None:
        self._factory = factory
        self.calls: list[tuple[str, str, int, WireRuntimeType, RuntimeCapabilitySet]] = []

    async def collect_capabilities(
        self,
        request_id: str,
        runtime_installation_id: str,
        runtime_installation_revision: int,
        runtime_type: WireRuntimeType,
        capability_set: RuntimeCapabilitySet,
    ) -> RuntimeCapabilityReport:
        self.calls.append(
            (
                request_id,
                runtime_installation_id,
                runtime_installation_revision,
                runtime_type,
                capability_set,
            )
        )
        return self._factory(
            runtime_installation_id,
            runtime_installation_revision,
            runtime_type,
            capability_set,
        )


def runtime(
    services: ControlPlaneServices, runtime_type: RuntimeType = RuntimeType.CODEX
) -> RuntimeInstallation:
    return services.providers.register_runtime_installation(
        runtime_type=runtime_type,
        display_name=f"{runtime_type.value} capability fixture",
        actor_id=ACTOR_ID,
    )


def service(
    services: ControlPlaneServices,
    clock: FakeClock,
    codex: RuntimeCapabilityClient,
    claude: RuntimeCapabilityClient | None = None,
) -> RuntimeCapabilityService:
    return RuntimeCapabilityService(
        services.database,
        clock,
        services.audit,
        codex_client=codex,
        claude_client=claude or codex,
    )


@pytest.mark.anyio
async def test_service_requires_registered_runtime_and_exact_revision(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    client = FakeClient(
        lambda runtime_id, revision, runtime_type, _set: make_report(
            runtime_id=runtime_id,
            revision=revision,
            runtime_type=runtime_type,
            clock=clock,
        )
    )
    subject = service(services, clock, client)
    with pytest.raises(ProviderMetadataNotFound):
        await subject.collect(
            request_id="req_unknown_runtime",
            runtime_installation_id="rti_ffffffffffffffffffffffffffffffff",
            runtime_installation_revision=1,
        )
    assert client.calls == []

    registered = runtime(services)
    with pytest.raises(RuntimeInstallationRevisionConflict):
        await subject.collect(
            request_id="req_stale_runtime",
            runtime_installation_id=registered.id,
            runtime_installation_revision=registered.revision + 1,
        )
    assert client.calls == []


@pytest.mark.anyio
async def test_service_selects_type_and_capability_set_server_side_and_audits_safely(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    codex = FakeClient(
        lambda runtime_id, revision, runtime_type, _set: make_report(
            runtime_id=runtime_id,
            revision=revision,
            runtime_type=runtime_type,
            clock=clock,
        )
    )
    claude = FakeClient(codex._factory)
    subject = service(services, clock, codex, claude)
    codex_runtime = runtime(services)
    claude_runtime = runtime(services, RuntimeType.CLAUDE)

    codex_report = await subject.collect(
        request_id="req_codex_capabilities",
        runtime_installation_id=codex_runtime.id,
        runtime_installation_revision=codex_runtime.revision,
        actor_id=ACTOR_ID,
    )
    claude_report = await subject.collect(
        request_id="req_claude_capabilities",
        runtime_installation_id=claude_runtime.id,
        runtime_installation_revision=claude_runtime.revision,
        actor_id=ACTOR_ID,
    )

    assert codex_report.capability_set is RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1
    assert claude_report.capability_set is RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1
    assert codex.calls[0][3:] == (
        WireRuntimeType.CODEX,
        RuntimeCapabilitySet.CODEX_PROVIDER_RUNTIME_V1,
    )
    assert claude.calls[0][3:] == (
        WireRuntimeType.CLAUDE,
        RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1,
    )
    with services.database.transaction() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "runtime_capabilities.collected")
        ).all()
    assert len(events) == 2
    for event in events:
        assert set(event.metadata_json) == {
            "runtime_type",
            "runtime_revision",
            "capability_set",
            "contract_version",
            "adapter_schema_version",
            "collection_state",
            "capability_count",
            "supported_count",
            "unknown_count",
            "expired",
        }
        assert RAW_CANARY not in str(event.metadata_json)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "field",
    (
        "runtime_installation_id",
        "runtime_installation_revision",
        "runtime_type",
        "capability_set",
        "capability_contract_version",
    ),
)
async def test_service_rejects_response_identity_or_contract_mismatch(
    services: ControlPlaneServices, clock: FakeClock, field: str
) -> None:
    registered = runtime(services)
    valid = make_report(
        runtime_id=registered.id,
        revision=registered.revision,
        runtime_type=WireRuntimeType.CODEX,
        clock=clock,
    )
    replacements = {
        "runtime_installation_id": "rti_ffffffffffffffffffffffffffffffff",
        "runtime_installation_revision": 99,
        "runtime_type": WireRuntimeType.CLAUDE,
        "capability_set": RuntimeCapabilitySet.CLAUDE_RUNTIME_SESSION_V1,
        "capability_contract_version": 2,
    }
    client = FakeClient(lambda *_args: valid.model_copy(update={field: replacements[field]}))
    with pytest.raises(RuntimeCapabilityReportInvalid):
        await service(services, clock, client).collect(
            request_id="req_mismatched_report",
            runtime_installation_id=registered.id,
            runtime_installation_revision=registered.revision,
        )


@pytest.mark.anyio
async def test_service_rejects_expired_and_incomplete_typed_reports(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    registered = runtime(services)
    valid = make_report(
        runtime_id=registered.id,
        revision=registered.revision,
        runtime_type=WireRuntimeType.CODEX,
        clock=clock,
    )
    expired = valid.model_copy(
        update={
            "observed_at": valid.observed_at - timedelta(seconds=120),
            "expires_at": valid.expires_at - timedelta(seconds=120),
            "observations": tuple(
                item.model_copy(
                    update={
                        "observed_at": item.observed_at - timedelta(seconds=120),
                        "expires_at": item.expires_at - timedelta(seconds=120),
                    }
                )
                for item in valid.observations
            ),
        }
    )
    with pytest.raises(RuntimeCapabilityEvidenceExpired):
        await service(services, clock, FakeClient(lambda *_args: expired)).collect(
            request_id="req_expired_report",
            runtime_installation_id=registered.id,
            runtime_installation_revision=registered.revision,
        )

    incomplete = valid.model_copy(update={"observations": valid.observations[:-1]})
    with pytest.raises(RuntimeCapabilityReportInvalid):
        await service(services, clock, FakeClient(lambda *_args: incomplete)).collect(
            request_id="req_incomplete_report",
            runtime_installation_id=registered.id,
            runtime_installation_revision=registered.revision,
        )

    future = valid.model_copy(
        update={
            "observed_at": valid.observed_at + timedelta(seconds=1),
            "expires_at": valid.expires_at + timedelta(seconds=1),
            "observations": tuple(
                item.model_copy(
                    update={
                        "observed_at": item.observed_at + timedelta(seconds=1),
                        "expires_at": item.expires_at + timedelta(seconds=1),
                    }
                )
                for item in valid.observations
            ),
        }
    )
    with pytest.raises(RuntimeCapabilityReportInvalid):
        await service(services, clock, FakeClient(lambda *_args: future)).collect(
            request_id="req_future_report",
            runtime_installation_id=registered.id,
            runtime_installation_revision=registered.revision,
        )


@pytest.mark.anyio
async def test_service_rechecks_runtime_revision_after_ipc(
    services: ControlPlaneServices, clock: FakeClock
) -> None:
    registered = runtime(services)

    def mutate_then_report(
        runtime_id: str,
        revision: int,
        runtime_type: WireRuntimeType,
        _set: RuntimeCapabilitySet,
    ) -> RuntimeCapabilityReport:
        with services.database.transaction() as session:
            session.execute(
                update(RuntimeInstallation)
                .where(RuntimeInstallation.id == runtime_id)
                .values(revision=revision + 1)
            )
        return make_report(
            runtime_id=runtime_id,
            revision=revision,
            runtime_type=runtime_type,
            clock=clock,
        )

    with pytest.raises(RuntimeInstallationRevisionConflict):
        await service(services, clock, FakeClient(mutate_then_report)).collect(
            request_id="req_runtime_changed",
            runtime_installation_id=registered.id,
            runtime_installation_revision=registered.revision,
        )


@pytest.mark.anyio
async def test_collection_creates_no_capability_persistence_or_provider_adoption(
    services: ControlPlaneServices, clock: FakeClock, settings: Settings
) -> None:
    registered = runtime(services)
    client = FakeClient(
        lambda runtime_id, revision, runtime_type, _set: make_report(
            runtime_id=runtime_id,
            revision=revision,
            runtime_type=runtime_type,
            clock=clock,
        )
    )
    await service(services, clock, client).collect(
        request_id="req_no_persistence",
        runtime_installation_id=registered.id,
        runtime_installation_revision=registered.revision,
    )
    tables = set(inspect(services.database.engine).get_table_names())
    assert not any("capabilit" in table for table in tables)
    assert "provider_config_transactions" not in tables
    assert services.providers.runtime_management(registered.id).state.value == "unmanaged"
    with services.database.transaction() as session:
        assert [
            item.id for item in session.execute(select(RuntimeInstallation)).scalars().all()
        ] == [registered.id]
        for model in (
            Provider,
            ProviderCredential,
            RuntimeProviderProfile,
            RuntimeProviderBinding,
            RuntimeSessionProviderBinding,
            ProviderCompatibilityEvidenceSet,
            ProviderCompatibilityObservation,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0

    database_name = make_url(settings.database_url).database
    assert database_name is not None
    database_path = Path(database_name)
    for suffix in ("", "-wal", "-shm"):
        file_path = Path(f"{database_path}{suffix}")
        if file_path.exists():
            assert RAW_CANARY.encode() not in file_path.read_bytes()


@pytest.mark.anyio
async def test_remote_error_canary_is_normalized_before_service_audit_or_persistence(
    services: ControlPlaneServices,
    clock: FakeClock,
    settings: Settings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    code_canary = "SECRET_CANARY_EXFILTRATION_123"
    message_canary = "REMOTE-SECRET-MESSAGE-CANARY"
    socket_path = tmp_path / "runtime-error.sock"

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = json.loads(await reader.readline())
        writer.write(
            json.dumps(
                {
                    "protocol_version": 1,
                    "request_id": request["request_id"],
                    "data": None,
                    "error": {
                        "code": code_canary,
                        "category": "conflict",
                        "message": message_canary,
                        "retryable": True,
                        "retry_after": 5,
                    },
                }
            ).encode()
            + b"\n"
        )
        await writer.drain()
        writer.close()
        with contextlib.suppress(ConnectionError):
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handler, path=socket_path)
    registered = runtime(services)
    client = UnixRuntimeCapabilityClient(socket_path)
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeOperationError) as raised:
            await service(services, clock, client).collect(
                request_id="req_remote_error_canary",
                runtime_installation_id=registered.id,
                runtime_installation_revision=registered.revision,
            )
        assert raised.value.code == "RUNTIME_CAPABILITY_REMOTE_ERROR"
        serialized = json.dumps(
            {"code": raised.value.code, "message": raised.value.message},
            separators=(",", ":"),
        )
        with services.database.transaction() as session:
            events = session.scalars(
                select(AuditEvent).where(AuditEvent.action == "runtime_capabilities.collected")
            ).all()
        assert events == []
        database_name = make_url(settings.database_url).database
        assert database_name is not None
        for suffix in ("", "-wal", "-shm"):
            file_path = Path(f"{database_name}{suffix}")
            if file_path.exists():
                contents = file_path.read_bytes()
                assert code_canary.encode() not in contents
                assert message_canary.encode() not in contents
        for canary in (code_canary, message_canary):
            assert canary not in raised.value.code
            assert canary not in raised.value.message
            assert canary not in serialized
            assert canary not in caplog.text
    finally:
        server.close()
        await server.wait_closed()
