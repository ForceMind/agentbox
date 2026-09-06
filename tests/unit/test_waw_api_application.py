from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from agentbox_api.main import create_app
from agentbox_api.waw_admission_coordinator import (
    AdmissionAuditAction,
    AdmissionAuditEvent,
)
from agentbox_api.waw_application import (
    WAWAPIApplication,
    WAWAPIApplicationError,
    WAWAPIApplicationState,
    WAWAPIComponents,
    WAWAPIProcessLock,
    WAWMode,
    WAWWorkLedger,
)
from agentbox_api.waw_authorization import SingleAdminWorkspacePolicy
from agentbox_api.waw_binding import WAWRuntimeBindCoordinator
from agentbox_api.waw_control_client import WAWControlClientError
from agentbox_api.waw_relay import DurableAdmissionAudit, WAWStreamHandler
from agentbox_core.configuration import Environment, Settings
from agentbox_core.models import Project
from agentbox_core.services import ControlPlaneServices
from agentbox_core.waw_models import RuntimeHostInstallation
from agentbox_core.waw_tickets import AttachmentAuthority

PROJECT_ID = "prj_" + "1" * 32
HOST_ID = "wri_" + "2" * 32
REPLAY_DIGEST = "d" * 64


class BindTransport:
    def __init__(self, authority_epoch: int) -> None:
        self.authority_epoch = authority_epoch
        self.calls = 0
        self.closes = 0
        self.actions: list[dict[str, Any]] = []

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.actions.append({"action": action, **request})
        if action == "workspace.api_authority.bind":
            assert request["api_authority_epoch"] == str(self.authority_epoch)
            self.calls += 1
            return {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "BOUND",
                "api_authority_epoch": str(self.authority_epoch),
                "runtime_epoch": "9",
                "runtime_host_installation_id": HOST_ID,
                "runtime_host_installation_revision": "3",
                "host_manifest_digest": "a" * 64,
                "project_root_manifest_digest": "b" * 64,
                "enrollment_epoch": "1",
                "enrollment_state": "steady",
            }
        if action == "workspace.project_binding.inventory.finalize.v1":
            return {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "FINALIZED",
                "runtime_epoch": request["runtime_epoch"],
                "binding_count": request["binding_count"],
                "inventory_digest": request["inventory_digest"],
            }
        raise AssertionError(action)

    async def close(self) -> None:
        self.closes += 1


class PausedBindTransport(BindTransport):
    def __init__(self, authority_epoch: int) -> None:
        super().__init__(authority_epoch)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        self.entered.set()
        await self.release.wait()
        return await super().request(action, request)


class ReplayTransport(BindTransport):
    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        if action == "workspace.project_binding.register":
            self.actions.append({"action": action, **request})
            return {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "REGISTERED",
                "project_id": request["project_id"],
                "binding_revision": request["binding_revision"],
                "binding_digest": REPLAY_DIGEST,
                "runtime_host_installation_id": request["runtime_host_installation_id"],
                "runtime_host_installation_revision": request["runtime_host_installation_revision"],
            }
        return await super().request(action, request)


class MismatchedFinalizeTransport(ReplayTransport):
    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        response = await super().request(action, request)
        if action == "workspace.project_binding.inventory.finalize.v1":
            response["inventory_digest"] = "f" * 64
        return response


class LostRegisterTransport(ReplayTransport):
    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        if action == "workspace.project_binding.register":
            self.actions.append({"action": action, **request})
            raise WAWControlClientError("RUNTIME_UNAVAILABLE", "synthetic response loss")
        return await super().request(action, request)


class RuntimeRegistrationState:
    def __init__(self) -> None:
        self.persisted = False


class ResponseLossAfterRuntimePersistTransport(ReplayTransport):
    def __init__(self, authority_epoch: int, state: RuntimeRegistrationState) -> None:
        super().__init__(authority_epoch)
        self.state = state

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        if action == "workspace.project_binding.register":
            self.actions.append({"action": action, **request})
            self.state.persisted = True
            raise WAWControlClientError("RUNTIME_UNAVAILABLE", "synthetic response loss")
        return await super().request(action, request)


class RecoveredRuntimeRegistrationTransport(ReplayTransport):
    def __init__(self, authority_epoch: int, state: RuntimeRegistrationState) -> None:
        super().__init__(authority_epoch)
        self.state = state

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        if action == "workspace.project_binding.register":
            assert self.state.persisted
            self.actions.append({"action": action, **request})
            return {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "ALREADY_CURRENT",
                "project_id": request["project_id"],
                "binding_revision": request["binding_revision"],
                "binding_digest": REPLAY_DIGEST,
                "runtime_host_installation_id": request["runtime_host_installation_id"],
                "runtime_host_installation_revision": request["runtime_host_installation_revision"],
            }
        return await super().request(action, request)


class PausedRegisterTransport(ReplayTransport):
    def __init__(self, authority_epoch: int) -> None:
        super().__init__(authority_epoch)
        self.register_entered = asyncio.Event()
        self.register_release = asyncio.Event()

    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        if action == "workspace.project_binding.register":
            self.register_entered.set()
            await self.register_release.wait()
        return await super().request(action, request)


def _seed_current_binding(services: ControlPlaneServices) -> None:
    now = datetime(2026, 9, 5, 0, 0, 0)
    with services.database.transaction() as session:
        session.add(
            Project(
                id=PROJECT_ID,
                slug="replay-project",
                display_name="Replay project",
                relative_path="replay-project",
                source_type="empty",
                repository_url=None,
                default_branch=None,
                state="ready",
                archived_at=None,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            RuntimeHostInstallation(
                id=HOST_ID,
                revision=3,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
            )
        )
    attempt = services.project_bindings.reserve(
        project_id=PROJECT_ID,
        expected_project_revision=1,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=3,
        expected_head_revision=None,
        expected_head_digest=None,
    )
    services.project_bindings.commit(
        project_id=PROJECT_ID,
        binding_revision=attempt.binding_revision,
        expected_project_revision=1,
        binding_digest=REPLAY_DIGEST,
    )


def _seed_pending_binding(services: ControlPlaneServices) -> None:
    now = datetime(2026, 9, 5, 0, 0, 0)
    with services.database.transaction() as session:
        session.add(
            Project(
                id=PROJECT_ID,
                slug="replay-pending",
                display_name="Replay pending",
                relative_path="replay-pending",
                source_type="empty",
                repository_url=None,
                default_branch=None,
                state="ready",
                archived_at=None,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            RuntimeHostInstallation(
                id=HOST_ID,
                revision=3,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
            )
        )
    services.project_bindings.reserve(
        project_id=PROJECT_ID,
        expected_project_revision=1,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=3,
        expected_head_revision=None,
        expected_head_digest=None,
    )


def _assert_state(owner: WAWAPIApplication, expected: WAWAPIApplicationState) -> None:
    assert owner.state is expected


def _assert_fork_fenced(owner: WAWAPIApplication) -> None:
    assert owner._state is WAWAPIApplicationState.POISONED
    assert not owner._process_lock.has_owned_fd
    assert owner._process_lock.poisoned
    assert owner._components is not None
    assert owner._components.bind_coordinator.shutdown_clean is False


def _owner(
    path: Path,
    settings: Settings,
    services: ControlPlaneServices,
    created: list[tuple[int, str, BindTransport]],
    transport_factory: Callable[[int], BindTransport] = BindTransport,
) -> WAWAPIApplication:
    def factory(
        authority_epoch: int, authority_nonce: str, ledger: WAWWorkLedger
    ) -> WAWAPIComponents:
        transport = transport_factory(authority_epoch)
        coordinator = WAWRuntimeBindCoordinator.test_only(
            transport,
            api_authority_epoch=str(authority_epoch),
            authority_nonce=authority_nonce,
            expected_runtime_host_installation_id="wri_" + "2" * 32,
            expected_runtime_host_installation_revision="3",
            expected_host_manifest_digest="a" * 64,
            expected_project_root_manifest_digest="b" * 64,
            expected_runtime_epoch="9",
            request_id_factory=lambda: "wreq_" + "1" * 32,
        )
        authority = AttachmentAuthority(clock=time.monotonic, authority_epoch=authority_epoch)
        policy = SingleAdminWorkspacePolicy()
        handler = WAWStreamHandler.test_only(
            services=services,
            settings=settings,
            authority=authority,
            control=coordinator,
            policy=policy,
            work_ledger=ledger,
            runtime_factory=lambda _control: (_ for _ in ()).throw(
                AssertionError("test does not open a Runtime stream")
            ),
        )
        created.append((authority_epoch, authority_nonce, transport))
        return WAWAPIComponents(None, coordinator, authority, policy, handler, ledger)

    owner = WAWAPIApplication.test_only(
        factory,
        settings=settings,
        services=services,
        process_lock=WAWAPIProcessLock.test_only(path),
    )
    return owner


@pytest.mark.anyio
async def test_owner_constructs_only_after_lock_and_closes_in_order(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    assert created == []
    _assert_state(owner, WAWAPIApplicationState.NEW)

    await asyncio.gather(owner.start(), owner.start())
    _assert_state(owner, WAWAPIApplicationState.RUNNING)
    assert len(created) == 1
    epoch, nonce, transport = created[0]
    assert 1 <= epoch < 1 << 64
    assert len(nonce) == 32
    assert transport.calls == 1
    assert all(owner.readiness_checks.values())

    await asyncio.gather(owner.close(), owner.close())
    _assert_state(owner, WAWAPIApplicationState.DRAINED)
    services.database.close()
    owner.finalize_after_database_close()
    _assert_state(owner, WAWAPIApplicationState.CLOSED)
    assert owner.shutdown_clean is True
    assert transport.closes == 1
    assert (tmp_path / "api.lock").exists()


@pytest.mark.anyio
async def test_owner_replays_and_finalizes_current_binding_before_running(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    _seed_current_binding(services)
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        created,
        transport_factory=ReplayTransport,
    )

    await owner.start()

    transport = created[0][2]
    assert [call["action"] for call in transport.actions] == [
        "workspace.api_authority.bind",
        "workspace.project_binding.register",
        "workspace.project_binding.inventory.finalize.v1",
    ]
    assert transport.actions[-1]["binding_count"] == "1"
    inventory_digest = transport.actions[-1]["inventory_digest"]
    assert isinstance(inventory_digest, str) and len(inventory_digest) == 64
    assert owner.state is WAWAPIApplicationState.RUNNING

    await owner.close()
    services.database.close()
    owner.finalize_after_database_close()


@pytest.mark.anyio
async def test_owner_does_not_publish_when_inventory_finalize_is_mismatched(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    _seed_current_binding(services)
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        created,
        transport_factory=MismatchedFinalizeTransport,
    )

    with pytest.raises(WAWAPIApplicationError) as raised:
        await owner.start()
    assert raised.value.code == "WAW_API_COMPOSITION_UNAVAILABLE"
    assert owner.state is WAWAPIApplicationState.POISONED
    assert not owner.readiness_checks["waw_api_singleton"]


@pytest.mark.anyio
async def test_owner_reconciles_pending_binding_after_runtime_registration_response_loss(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    _seed_pending_binding(services)
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        created,
        transport_factory=LostRegisterTransport,
    )

    with pytest.raises(WAWAPIApplicationError) as raised:
        await owner.start()

    assert raised.value.code == "WAW_API_COMPOSITION_UNAVAILABLE"
    assert services.project_bindings.get(PROJECT_ID, 1).status == "RECONCILIATION_REQUIRED"


@pytest.mark.anyio
async def test_replay_recovers_runtime_persisted_binding_after_response_loss(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    _seed_pending_binding(services)
    state = RuntimeRegistrationState()
    first_created: list[tuple[int, str, BindTransport]] = []
    first = _owner(
        tmp_path / "first.lock",
        settings,
        services,
        first_created,
        transport_factory=lambda authority_epoch: ResponseLossAfterRuntimePersistTransport(
            authority_epoch, state
        ),
    )

    with pytest.raises(WAWAPIApplicationError):
        await first.start()
    assert state.persisted
    assert services.project_bindings.get(PROJECT_ID, 1).status == "RECONCILIATION_REQUIRED"

    recovered_created: list[tuple[int, str, BindTransport]] = []
    recovered = _owner(
        tmp_path / "recovered.lock",
        settings,
        services,
        recovered_created,
        transport_factory=lambda authority_epoch: RecoveredRuntimeRegistrationTransport(
            authority_epoch, state
        ),
    )
    await recovered.start()

    binding = services.project_bindings.get(PROJECT_ID, 1)
    assert (binding.status, binding.binding_digest) == ("CURRENT", REPLAY_DIGEST)
    assert [call["action"] for call in recovered_created[0][2].actions] == [
        "workspace.api_authority.bind",
        "workspace.project_binding.register",
        "workspace.project_binding.inventory.finalize.v1",
    ]

    await recovered.close()
    services.database.close()
    recovered.finalize_after_database_close()


@pytest.mark.anyio
async def test_owner_fences_project_drift_between_replay_register_and_finalize(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    _seed_current_binding(services)
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        created,
        transport_factory=PausedRegisterTransport,
    )
    starting = asyncio.create_task(owner.start())
    while not created:
        await asyncio.sleep(0)
    transport = created[0][2]
    assert isinstance(transport, PausedRegisterTransport)
    await transport.register_entered.wait()
    services.projects.mark_error(PROJECT_ID, expected_revision=1)
    transport.register_release.set()

    with pytest.raises(WAWAPIApplicationError) as raised:
        await starting
    assert raised.value.code == "WAW_API_COMPOSITION_UNAVAILABLE"
    assert owner.state is WAWAPIApplicationState.POISONED
    assert [call["action"] for call in transport.actions] == [
        "workspace.api_authority.bind",
        "workspace.project_binding.register",
    ]


@pytest.mark.anyio
async def test_fastapi_lifespan_publishes_one_owner_and_reports_readiness(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    application = create_app(
        settings,
        services,
        waw_mode=WAWMode.FILESYSTEM_V2,
        waw_application=owner,
    )

    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/readyz")
        assert response.status_code == 200
        assert response.json()["checks"] == {
            "database": True,
            "migrations": True,
            "waw_api_singleton": True,
            "waw_runtime_bound": True,
            "waw_stream_owner": True,
        }
        assert application.state.waw_bind_coordinator is None
        assert application.state.waw_attachment_authority is None
        assert application.state.waw_stream_handler is None

    assert owner.shutdown_clean is True


@pytest.mark.anyio
async def test_stream_handler_shutdown_gate_cancels_registered_work(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    handler = owner.stream_handler
    started = asyncio.Event()

    async def active() -> None:
        task = asyncio.current_task()
        assert task is not None and handler._register(task)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            handler._unregister(task)

    task = asyncio.create_task(active())
    await started.wait()
    assert handler.active_count == 1
    await owner.close()
    services.database.close()
    owner.finalize_after_database_close()
    assert task.cancelled()
    assert handler.accepting is False
    assert handler.shutdown_clean is True


@pytest.mark.anyio
async def test_owner_waits_for_background_work_before_database_and_lock(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    release = asyncio.Event()
    started = asyncio.Event()

    async def background() -> None:
        started.set()
        await release.wait()

    work = asyncio.create_task(background())
    owner.stream_handler.track_background(work)
    await started.wait()
    closing = asyncio.create_task(owner.close())
    await asyncio.sleep(0)
    assert not closing.done()
    _assert_state(owner, WAWAPIApplicationState.QUIESCING)

    release.set()
    await closing
    _assert_state(owner, WAWAPIApplicationState.DRAINED)
    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean


@pytest.mark.anyio
async def test_completed_failed_background_work_is_sticky_before_close(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    failed = asyncio.get_running_loop().create_future()
    owner.stream_handler.track_background(failed)

    failed.set_exception(RuntimeError("synthetic completed background failure"))
    await asyncio.sleep(0)
    assert owner._work_ledger.background_count == 0

    with pytest.raises(WAWAPIApplicationError) as raised:
        await owner.close()
    assert raised.value.code == "WAW_API_SHUTDOWN_INCOMPLETE"
    assert owner.state is WAWAPIApplicationState.POISONED
    assert not owner.shutdown_clean
    assert owner._process_lock.has_owned_fd


@pytest.mark.anyio
async def test_detach_operations_are_owned_and_retired_with_application(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    key: tuple[object, ...] = ("workspace", "attachment", "1")
    operation_id, detached = owner.detach_operation(key)
    assert not detached and owner.detach_operation(key) == (operation_id, False)
    owner.mark_detached(key, operation_id)
    assert owner.detach_operation(key) == (operation_id, True)

    await owner.close()
    assert owner._work_ledger._detach_operations == {}
    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean


@pytest.mark.anyio
async def test_pending_detach_poison_retains_operation_and_process_lock(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    key: tuple[object, ...] = ("workspace", "attachment", "uncertain")
    operation_id, detached = owner.detach_operation(key)
    assert not detached

    with pytest.raises(WAWAPIApplicationError) as raised:
        await owner.close()
    assert raised.value.code == "WAW_API_SHUTDOWN_INCOMPLETE"
    assert owner._work_ledger._detach_operations == {key: (operation_id, False)}
    assert owner.state is WAWAPIApplicationState.POISONED
    assert not owner.shutdown_clean
    assert owner._process_lock.has_owned_fd


@pytest.mark.anyio
async def test_cancelled_close_waiter_does_not_cancel_shared_shutdown(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    release = asyncio.Event()
    work = asyncio.create_task(release.wait())
    owner.stream_handler.track_background(work)

    waiter = asyncio.create_task(owner.close())
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.sleep(0)
    assert not waiter.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await owner.close()
    _assert_state(owner, WAWAPIApplicationState.DRAINED)
    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean


@pytest.mark.anyio
async def test_cancelled_audit_waiter_keeps_database_work_owned_until_shutdown(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    entered = threading.Event()
    release = threading.Event()
    audit = DurableAdmissionAudit(services, "usr_synthetic", owner.stream_handler)

    def blocking_persist(_event: AdmissionAuditEvent) -> None:
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(audit, "_persist", blocking_persist)
    pending = asyncio.create_task(
        audit.persist(
            AdmissionAuditEvent(
                AdmissionAuditAction.PREPARED,
                "aws_" + "1" * 32,
                "att_" + "2" * 32,
                1,
                "1",
                1,
                None,
            )
        )
    )
    assert await asyncio.to_thread(entered.wait, 5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    closing = asyncio.create_task(owner.close())
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    await closing
    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean


@pytest.mark.anyio
async def test_close_during_start_fences_publication_and_drains_once(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        created,
        transport_factory=PausedBindTransport,
    )
    starting = asyncio.create_task(owner.start())
    while not created:
        await asyncio.sleep(0)
    transport = created[0][2]
    assert isinstance(transport, PausedBindTransport)
    await transport.entered.wait()
    closing = asyncio.create_task(owner.close())
    await asyncio.sleep(0)
    _assert_state(owner, WAWAPIApplicationState.QUIESCING)

    transport.release.set()
    with pytest.raises(WAWAPIApplicationError):
        await starting
    await closing
    _assert_state(owner, WAWAPIApplicationState.DRAINED)
    assert transport.closes == 1
    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean


@pytest.mark.anyio
async def test_cancelled_start_waiter_cannot_publish_partial_graph(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        created,
        transport_factory=PausedBindTransport,
    )
    waiter = asyncio.create_task(owner.start())
    while not created:
        await asyncio.sleep(0)
    transport = created[0][2]
    assert isinstance(transport, PausedBindTransport)
    await transport.entered.wait()
    waiter.cancel()
    await asyncio.sleep(0)
    assert not waiter.done()
    transport.release.set()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    _assert_state(owner, WAWAPIApplicationState.RUNNING)

    await owner.close()
    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean


def test_production_rejects_fragmented_waw_injection(
    settings: Settings, services: ControlPlaneServices
) -> None:
    production = settings.model_copy(update={"env": Environment.PRODUCTION})
    with pytest.raises(ValueError, match="cannot be injected"):
        create_app(production, services, waw_stream_handler=object())


def test_production_rejects_injected_owner(
    tmp_path: Path, settings: Settings, services: ControlPlaneServices
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    production = settings.model_copy(update={"env": Environment.PRODUCTION})
    with pytest.raises(ValueError, match="cannot be injected"):
        create_app(
            production,
            services,
            waw_mode=WAWMode.FILESYSTEM_V2,
            waw_application=owner,
        )


@pytest.mark.anyio
async def test_filesystem_v2_production_is_lazy_and_missing_fixed_lock_fails_closed(
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = settings.model_copy(update={"env": Environment.PRODUCTION})

    def unavailable(_lock: WAWAPIProcessLock) -> None:
        raise WAWAPIApplicationError(
            "WAW_API_SINGLETON_UNAVAILABLE", "synthetic fixed lock is unavailable"
        )

    monkeypatch.setattr(WAWAPIProcessLock, "acquire", unavailable)
    application = create_app(production, services, waw_mode=WAWMode.FILESYSTEM_V2)
    with pytest.raises(WAWAPIApplicationError) as raised:
        async with application.router.lifespan_context(application):
            raise AssertionError("filesystem-v2 startup must fail without its fixed lock")
    assert raised.value.code == "WAW_API_SINGLETON_UNAVAILABLE"


@pytest.mark.anyio
async def test_post_start_fork_fences_graph_and_closes_inherited_lock(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[int, str, BindTransport]] = []
    owner = _owner(tmp_path / "api.lock", settings, services, created)
    await owner.start()
    parent_pid = owner._lifespan_pid
    assert parent_pid is not None and owner._process_lock.has_owned_fd

    with monkeypatch.context() as patch:
        patch.setattr(os, "getpid", lambda: parent_pid + 1)
        owner.fence_after_fork()
        with pytest.raises(WAWAPIApplicationError) as raised:
            _ = owner.bind_coordinator
        assert raised.value.code == "WAW_API_SINGLETON_UNSAFE"

    _assert_fork_fenced(owner)
