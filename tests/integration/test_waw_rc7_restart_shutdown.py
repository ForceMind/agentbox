"""RC7 restart and shutdown fences over the composed WAW owners.

The checkpoints in this module belong only to the test scheduler.  Production
API, Runtime and admission code receives no failure-injection dependency.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from agentbox_api.waw_admission import wire_admission_tuple
from agentbox_api.waw_admission_coordinator import WAWAdmissionCoordinator
from agentbox_api.waw_application import (
    WAWAPIApplication,
    WAWAPIApplicationState,
    WAWAPIComponents,
    WAWAPIProcessLock,
    WAWWorkLedger,
)
from agentbox_api.waw_authorization import SingleAdminWorkspacePolicy
from agentbox_api.waw_binding import RuntimeEpochClassifier, WAWRuntimeBindCoordinator
from agentbox_api.waw_relay import WAWStreamHandler
from agentbox_core.configuration import Settings
from agentbox_core.models import Project
from agentbox_core.services import ControlPlaneServices, build_services
from agentbox_core.waw import AgentType, WorkspaceState
from agentbox_core.waw_models import RuntimeHostInstallation
from agentbox_core.waw_sessions import RuntimeEpochClassification
from agentbox_core.waw_tickets import AttachmentAuthority
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.waw_crypto_context import derive_context
from support.waw_admission import BA, Browser, Harness
from support.waw_failure_injection import (
    ApplicationCheckpoint,
    CheckpointPlan,
    FakeMonotonicClock,
)

_HOST_ID = "wri_" + "2" * 32
_PROJECT_ID = "prj_" + "1" * 32


class _RuntimeTransport:
    """Ephemeral test-only Runtime control port with one connection identity."""

    def __init__(self, runtime_epoch: str) -> None:
        self.runtime_epoch = runtime_epoch
        self.connection = object()
        self.closed = False
        self.calls = 0

    async def request(self, action: str, request: dict[str, object]) -> dict[str, object]:
        assert not self.closed
        self.calls += 1
        if action == "workspace.api_authority.bind":
            return {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "BOUND",
                "api_authority_epoch": request["api_authority_epoch"],
                "runtime_epoch": self.runtime_epoch,
                "runtime_host_installation_id": _HOST_ID,
                "runtime_host_installation_revision": "1",
                "host_manifest_digest": "a" * 64,
                "project_root_manifest_digest": "b" * 64,
                "enrollment_epoch": "1",
                "enrollment_state": "steady",
            }
        if action == "workspace.project_binding.inventory.finalize.v1":
            return {
                "status": "FINALIZED",
                "runtime_epoch": request["runtime_epoch"],
                "binding_count": request["binding_count"],
                "inventory_digest": request["inventory_digest"],
            }
        raise AssertionError(action)

    async def close(self) -> None:
        self.closed = True


def _owner(
    path: Path,
    settings: Settings,
    services: ControlPlaneServices,
    clock: FakeMonotonicClock,
    transports: list[_RuntimeTransport],
    *,
    runtime_epoch: str,
    classifier: RuntimeEpochClassifier | None = None,
) -> WAWAPIApplication:
    def factory(
        authority_epoch: int, authority_nonce: str, ledger: WAWWorkLedger
    ) -> WAWAPIComponents:
        transport = _RuntimeTransport(runtime_epoch)
        coordinator = WAWRuntimeBindCoordinator.test_only(
            transport,
            api_authority_epoch=str(authority_epoch),
            authority_nonce=authority_nonce,
            expected_runtime_host_installation_id=_HOST_ID,
            expected_runtime_host_installation_revision="1",
            expected_host_manifest_digest="a" * 64,
            expected_project_root_manifest_digest="b" * 64,
            expected_runtime_epoch=runtime_epoch,
            request_id_factory=lambda: "wreq_" + "1" * 32,
            runtime_epoch_classifier=classifier,
        )
        authority = AttachmentAuthority(
            clock=clock.seconds,
            authority_epoch=authority_epoch,
        )
        policy = SingleAdminWorkspacePolicy()
        handler = WAWStreamHandler.test_only(
            services=services,
            settings=settings,
            authority=authority,
            control=coordinator,
            policy=policy,
            work_ledger=ledger,
            runtime_factory=lambda _control: (_ for _ in ()).throw(
                AssertionError("rc7 owner test does not open a socket")
            ),
        )
        transports.append(transport)
        return WAWAPIComponents(None, coordinator, authority, policy, handler, ledger)

    return WAWAPIApplication.test_only(
        factory,
        settings=settings,
        services=services,
        process_lock=WAWAPIProcessLock.test_only(path),
    )


async def _close_and_finalize(owner: WAWAPIApplication, services: ControlPlaneServices) -> None:
    await owner.close()
    assert owner.state is WAWAPIApplicationState.DRAINED
    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean


@pytest.mark.anyio
async def test_rc7_api_restart_fences_old_publication_and_uses_fresh_runtime_connection(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    clock = FakeMonotonicClock()
    plan = CheckpointPlan.single(ApplicationCheckpoint.API_RESTART)
    first_transports: list[_RuntimeTransport] = []
    first = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        clock,
        first_transports,
        runtime_epoch="7",
    )
    await first.start()
    assert first.readiness_checks == {
        "waw_api_singleton": True,
        "waw_runtime_bound": True,
        "waw_stream_owner": True,
    }
    original_connection = first_transports[0].connection

    restarted_services: ControlPlaneServices | None = None
    restarted: WAWAPIApplication | None = None
    restarted_transports: list[_RuntimeTransport] = []

    async def restart() -> None:
        nonlocal restarted, restarted_services
        await _close_and_finalize(first, services)
        await plan.arrive(ApplicationCheckpoint.API_RESTART)
        restarted_services = build_services(settings)
        restarted = _owner(
            tmp_path / "api.lock",
            settings,
            restarted_services,
            clock,
            restarted_transports,
            runtime_epoch="7",
        )
        await restarted.start()

    operation = asyncio.create_task(restart())
    await asyncio.wait_for(plan.observe(ApplicationCheckpoint.API_RESTART), timeout=1)
    assert first.state is WAWAPIApplicationState.CLOSED
    assert first.readiness_checks == {
        "waw_api_singleton": False,
        "waw_runtime_bound": False,
        "waw_stream_owner": False,
    }
    assert first_transports[0].closed

    assert plan.release(ApplicationCheckpoint.API_RESTART)
    await asyncio.wait_for(operation, timeout=1)
    plan.assert_complete()
    assert restarted is not None and restarted_services is not None
    assert restarted.readiness_checks["waw_api_singleton"]
    assert restarted_transports[0].connection is not original_connection

    await _close_and_finalize(restarted, restarted_services)


@pytest.mark.anyio
async def test_rc7_api_and_runtime_restart_advances_epoch_and_fences_old_workspace_publication(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
) -> None:
    now = datetime(2026, 9, 6, 0, 0, 0)
    with services.database.transaction() as session:
        session.add(
            Project(
                id=_PROJECT_ID,
                slug="restart-fence",
                display_name="Restart fence",
                relative_path="restart-fence",
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
                id=_HOST_ID,
                revision=1,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
            )
        )
    first_clock = FakeMonotonicClock()
    plan = CheckpointPlan.single(ApplicationCheckpoint.RUNTIME_RESTART)
    first_transports: list[_RuntimeTransport] = []
    first = _owner(
        tmp_path / "api.lock",
        settings,
        services,
        first_clock,
        first_transports,
        runtime_epoch="7",
        classifier=services.workspaces,
    )
    await first.start()
    workspace = services.workspaces.create(
        project_id=_PROJECT_ID,
        agent_type=AgentType.CODEX,
        authorization_scope="admin",
        runtime_host_installation_id=_HOST_ID,
        runtime_host_installation_revision=1,
        binding_revision=1,
        binding_digest="d" * 64,
    )
    running = services.workspaces.transition(
        workspace.id, expected_revision=workspace.revision, state=WorkspaceState.RUNNING
    )
    original_connection = first_transports[0].connection
    first_coordinator = first.bind_coordinator

    second_services: ControlPlaneServices | None = None
    second_transports: list[_RuntimeTransport] = []

    async def restart_runtime() -> WAWAPIApplication:
        nonlocal second_services
        await _close_and_finalize(first, services)
        await plan.arrive(ApplicationCheckpoint.RUNTIME_RESTART)
        second_services = build_services(settings)
        next_owner = _owner(
            tmp_path / "api.lock",
            settings,
            second_services,
            first_clock,
            second_transports,
            runtime_epoch="8",
            classifier=second_services.workspaces,
        )
        await next_owner.start()
        return next_owner

    operation = asyncio.create_task(restart_runtime())
    await asyncio.wait_for(plan.observe(ApplicationCheckpoint.RUNTIME_RESTART), timeout=1)
    assert not first_coordinator.bound
    assert first_transports[0].closed
    assert first.state is WAWAPIApplicationState.CLOSED

    assert plan.release(ApplicationCheckpoint.RUNTIME_RESTART)
    second = await asyncio.wait_for(operation, timeout=1)
    plan.assert_complete()
    assert second_services is not None
    fenced = second_services.workspaces.get(running.id)
    assert (fenced.state, fenced.reconciliation_state, fenced.failure_code) == (
        WorkspaceState.UNKNOWN.value,
        "reconciliation_required",
        "RUNTIME_RESTART",
    )
    assert second_transports[0].connection is not original_connection
    assert (
        second_services.workspaces.classify_runtime_epoch(
            runtime_host_installation_id=_HOST_ID,
            runtime_host_installation_revision=1,
            observed_runtime_epoch="8",
        )
        is RuntimeEpochClassification.API_RESTART
    )

    await _close_and_finalize(second, second_services)


@pytest.mark.anyio
async def test_rc7_shutdown_drain_burns_pending_admission_and_releases_no_writer_record(
    tmp_path: Path,
    settings: Settings,
    services: ControlPlaneServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonicClock()
    plan = CheckpointPlan.single(ApplicationCheckpoint.SHUTDOWN_DRAIN)
    transports: list[_RuntimeTransport] = []
    owner = _owner(
        tmp_path / "shutdown.lock",
        settings,
        services,
        clock,
        transports,
        runtime_epoch="7",
    )
    await owner.start()
    owner_authority = owner.attachment_authority
    owner_handler = owner.stream_handler

    admission = Harness()
    admission.runtime.block = "prepare"
    clock.advance_to(admission.clock.ns)
    previous_claims = admission.ticket.claims
    admission.authority = owner_authority
    admission.ticket = admission.authority.issue(
        workspace_id=previous_claims.workspace_id,
        project_id=previous_claims.project_id,
        agent_type=previous_claims.agent_type,
        attachment_id=previous_claims.attachment_id,
        generation=previous_claims.generation,
        auth_epoch=previous_claims.auth_epoch,
        runtime_host_installation_id=previous_claims.runtime_host_installation_id,
        runtime_host_installation_revision=previous_claims.runtime_host_installation_revision,
        binding_revision=previous_claims.binding_revision,
        binding_digest=previous_claims.binding_digest,
        context=admission.context,
    )
    admission.a = wire_admission_tuple(admission.ticket.claims)
    admission.c = derive_context(admission.a, admission.context.runtime_epoch)
    admission.browser = Browser(admission, admission.input_budget)
    admission.coordinator = WAWAdmissionCoordinator(
        authority=admission.authority,
        claims=admission.ticket.claims,
        context=admission.context,
        runtime=admission.runtime,
        browser=admission.browser,
        audit=admission.audit,
        revalidator=admission.validator,
        budget=admission.budget,
        source="source",
        started_at_ns=admission.clock.ns,
        input_budget=admission.input_budget,
        clock_ns=admission.clock,
    )
    admission.browser.incoming.put_nowait(admission.frame(F.WS_HELLO, BA, 1))
    admission.browser.incoming.put_nowait(admission.frame(F.KEY_INIT, BA, 2))
    original_cleanup = admission.runtime.close_and_cleanup

    async def close_and_cleanup(request):  # type: ignore[no-untyped-def]
        await plan.arrive(ApplicationCheckpoint.SHUTDOWN_DRAIN)
        return await original_cleanup(request)

    monkeypatch.setattr(admission.runtime, "close_and_cleanup", close_and_cleanup)

    async def admit() -> None:
        task = asyncio.current_task()
        assert task is not None and owner_handler._register(task)
        try:
            await admission.coordinator.run()
        finally:
            owner_handler._unregister(task)

    pending = asyncio.create_task(admit())
    await asyncio.wait_for(admission.runtime.entered.wait(), timeout=1)
    operation = asyncio.create_task(owner.close())
    await asyncio.wait_for(plan.observe(ApplicationCheckpoint.SHUTDOWN_DRAIN), timeout=1)
    assert admission.authority.pending_count == 0
    assert admission.authority.active_count == 0
    assert admission.authority.record_count == 1
    assert owner_authority is admission.authority
    assert not owner_authority.shutdown_clean
    assert owner._work_ledger.accepting is False

    assert plan.release(ApplicationCheckpoint.SHUTDOWN_DRAIN)
    await asyncio.wait_for(operation, timeout=1)
    plan.assert_complete()
    assert pending.cancelled()
    assert admission.runtime.aborted
    assert admission.authority.record_count == 0
    assert admission.authority.shutdown_clean
    assert owner.state is WAWAPIApplicationState.DRAINED
    assert transports[0].closed

    services.database.close()
    owner.finalize_after_database_close()
    assert owner.shutdown_clean
