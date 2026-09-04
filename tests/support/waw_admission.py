"""Shared synthetic Runtime/browser/Audit fixtures for R6/R8 software tests."""

from __future__ import annotations

import asyncio
import gc
from dataclasses import replace
from typing import Any

from agentbox_api.waw_admission import wire_admission_tuple
from agentbox_api.waw_admission_coordinator import (
    AdmissionAuditAction as A,
)
from agentbox_api.waw_admission_coordinator import (
    AdmissionAuditEvent,
    BoundedAdmissionQueue,
    PendingAdmissionBudget,
    RuntimeCleanupProof,
    RuntimeCleanupRequest,
    RuntimePrepared,
    RuntimePrepareRequest,
    WAWAdmissionCoordinator,
)
from agentbox_api.waw_input_budget import (
    BrowserDelivery,
    InputBudget,
    InputBudgetOwner,
    is_encoded_input,
)
from agentbox_core.waw import workspace_id
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
)
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.awce import encode_awce_header
from agentbox_protocol.waw_crypto_context import derive_context
from agentbox_protocol.waw_wire import Leg, decode_wire_frame, encode_wire_frame

BA, AB, AR, RA = tuple(Leg)


class Clock:
    def __init__(self) -> None:
        self.ns = 100_000_000_000

    def __call__(self) -> int:
        return self.ns


class Validator:
    valid = True

    def current(self, claims: AttachmentTuple, context: AuthenticatedAttachmentContext) -> bool:
        return self.valid


class Audit:
    def __init__(self) -> None:
        self.events: list[AdmissionAuditEvent] = []
        self.block: A | None = None
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.fail: A | None = None

    async def persist(self, event: AdmissionAuditEvent) -> None:
        if event.action == self.block:
            self.entered.set()
            await self.resume.wait()
        if event.action == self.fail:
            raise RuntimeError("AUDIT-PRIVATE-CANARY")
        self.events.append(event)
        await asyncio.sleep(0)


class Browser:
    def __init__(self, harness: Harness, input_budget: InputBudget) -> None:
        self.h = harness
        self.input_budget = input_budget
        self.incoming: asyncio.Queue[bytes | BrowserDelivery] = asyncio.Queue(maxsize=8)
        self.sent: list[bytes] = []
        self.closed: int | None = None

    def delivery(self, raw: bytes) -> BrowserDelivery:
        token = self.input_budget.reserve_native(len(raw)) if is_encoded_input(raw) else None
        if token is not None:
            self.input_budget.transfer(
                token,
                source=InputBudgetOwner.NATIVE_READY,
                target=InputBudgetOwner.BROWSER_DELIVERY,
            )
        return BrowserDelivery(raw, token)

    async def receive(self) -> BrowserDelivery:
        incoming = await self.incoming.get()
        if isinstance(incoming, bytes):
            return self.delivery(incoming)
        assert isinstance(incoming, BrowserDelivery)
        token = incoming.input_token
        if token is not None and token.owner == InputBudgetOwner.NATIVE_READY:
            self.input_budget.transfer(
                token,
                source=InputBudgetOwner.NATIVE_READY,
                target=InputBudgetOwner.BROWSER_DELIVERY,
            )
        return incoming

    async def send_key_frame(self, frame: bytes) -> None:
        self.sent.append(frame)
        kind = decode_wire_frame(frame, AB).frame_type
        if kind == F.KEY_ATTEST:
            self.incoming.put_nowait(self.h.frame(F.KEY_CONFIRM, BA, 3))
        await asyncio.sleep(0)

    def close(self, code: int) -> None:
        self.closed = code
        self.input_budget.close()

    def abort(self, code: int) -> None:
        self.close(code)


class Runtime:
    def __init__(self, harness: Harness) -> None:
        self.h = harness
        self.connection_id = object()
        self.incoming: asyncio.Queue[bytes] = asyncio.Queue(maxsize=8)
        self.sent: list[bytes] = []
        self.prepares = 0
        self.commits = 0
        self.cleanup_requests: list[RuntimeCleanupRequest] = []
        self.cleanup_positive = True
        self.cleanup_wrong_tuple = False
        self.cleanup_wrong_connection = False
        self.aborted = False
        self.drop_commits = 0
        self.reject_commit = False
        self.extra_outputs = 0
        self.output_size = 1
        self.block: F | str | None = None
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.mutate_response: F | None = None

    async def _barrier(self, action: F | str) -> None:
        if action == self.block:
            self.entered.set()
            await self.resume.wait()
        await asyncio.sleep(0)

    async def prepare(self, request: RuntimePrepareRequest) -> RuntimePrepared:
        self.prepares += 1
        await self._barrier("prepare")
        return RuntimePrepared(request.claims, request.runtime_epoch, self.connection_id, "c" * 64)

    async def send(self, frame: bytes) -> None:
        decoded = decode_wire_frame(frame, AR)
        self.sent.append(frame)
        await self._barrier(decoded.frame_type)
        if decoded.frame_type == F.KEY_INIT:
            self._reply(F.HELLO_ACK, 1)
            self._reply(F.KEY_ATTEST, 2)
        elif decoded.frame_type == F.KEY_CONFIRM:
            self._reply(F.KEY_CONFIRM_ACK, 3)
        elif decoded.frame_type == F.STREAM_READY:
            self._reply(F.STREAM_READY_ACK, 4)
        elif decoded.frame_type == F.ADMISSION_COMMIT:
            self.commits += 1
            if self.drop_commits > 0:
                self.drop_commits -= 1
                return
            payload = self.h.payload(F.ADMISSION_COMMIT_ACK)
            if self.reject_commit:
                payload.update(result="rejected", reason_code="ATTACHMENT_STALE")
            self.incoming.put_nowait(encode_wire_frame(F.ADMISSION_COMMIT_ACK, RA, payload, 5))
            for number in range(self.extra_outputs):
                raw = encode_awce_header(
                    crypto_envelope_version=1,
                    direction_id=2,
                    flags=0,
                    crypto_sequence=number + 1,
                    stream_cursor=number + 1,
                    context_id=bytes.fromhex("e" * 32),
                    ciphertext_length=self.output_size + 16,
                ) + b"x" * (self.output_size + 16)
                self.incoming.put_nowait(encode_wire_frame(F.OUTPUT, RA, raw, 6 + number))

    def _reply(self, kind: F, seq: int) -> None:
        payload = self.h.payload(kind)
        if kind == self.mutate_response:
            payload["runtime_epoch"] = "999"
        self.incoming.put_nowait(encode_wire_frame(kind, RA, payload, seq))

    async def receive(self) -> bytes:
        return await self.incoming.get()

    async def close_and_cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupProof:
        self.cleanup_requests.append(request)
        await asyncio.sleep(0)
        return RuntimeCleanupProof(
            replace(request.claims, generation=9) if self.cleanup_wrong_tuple else request.claims,
            request.runtime_epoch,
            object() if self.cleanup_wrong_connection else request.connection_id,
            "detached" if self.cleanup_positive else "rejected",
            "ATTACH_PTY_CLOSED" if self.cleanup_positive else "UNKNOWN",
        )

    def abort(self) -> None:
        self.aborted = True


class Harness:
    def __init__(self, *, queue: BoundedAdmissionQueue | None = None) -> None:
        # Collect prior cyclic fake ports before entering the 5 ms wire CPU budget.
        gc.collect()
        self.clock = Clock()
        self.authority = AttachmentAuthority(
            clock=lambda: self.clock.ns / 1_000_000_000, authority_epoch=4
        )
        self.context = AuthenticatedAttachmentContext(
            "private-session", "admin", "scope", "https://agentbox.invalid", "2", 3
        )
        project = "prj_" + "1" * 32
        self.ticket = self.authority.issue(
            workspace_id=workspace_id(project, "codex"),
            project_id=project,
            agent_type="codex",
            attachment_id="att_" + "2" * 32,
            generation=1,
            auth_epoch=3,
            runtime_host_installation_id="wri_" + "a" * 32,
            runtime_host_installation_revision=1,
            binding_revision=1,
            binding_digest="b" * 64,
            context=self.context,
        )
        self.a = wire_admission_tuple(self.ticket.claims)
        self.c = derive_context(self.a, "2")
        self.runtime, self.audit = Runtime(self), Audit()
        self.input_budget = InputBudget(
            connection_id=self.runtime.connection_id,
            attachment_id=self.ticket.claims.attachment_id,
            runtime_epoch=self.context.runtime_epoch,
        )
        self.browser = Browser(self, self.input_budget)
        self.validator = Validator()
        self.budget = PendingAdmissionBudget()
        self.coordinator = WAWAdmissionCoordinator(
            authority=self.authority,
            claims=self.ticket.claims,
            context=self.context,
            runtime=self.runtime,
            browser=self.browser,
            audit=self.audit,
            revalidator=self.validator,
            budget=self.budget,
            source="source",
            started_at_ns=self.clock.ns,
            input_budget=self.input_budget,
            clock_ns=self.clock,
            queue=queue,
        )
        self.browser.incoming.put_nowait(self.frame(F.WS_HELLO, BA, 1))
        self.browser.incoming.put_nowait(self.frame(F.KEY_INIT, BA, 2))

    def payload(self, kind: F) -> dict[str, Any]:
        base: dict[str, Any] = {"protocol_version": 1}
        common = {**base, **self.a, "runtime_epoch": "2"}
        if kind == F.WS_HELLO:
            return {
                **common,
                "ticket": self.ticket.ticket,
                "resume_cursor": None,
                "previous_runtime_epoch": None,
            }
        if kind in (F.KEY_INIT, F.KEY_ATTEST):
            extra = (
                {"browser_ephemeral_public_key": "A" * 43, "noise_message_1": "A" * 43}
                if kind == F.KEY_INIT
                else {
                    "runtime_attestation_x25519_fingerprint": "d" * 64,
                    "runtime_ephemeral_public_key": "A" * 43,
                    "noise_message_2": "A" * 171,
                }
            )
            return {
                **common,
                "noise_protocol": "Noise_NX_25519_AESGCM_SHA256",
                "crypto_envelope_version": 1,
                **extra,
            }
        if kind in (F.KEY_CONFIRM, F.KEY_CONFIRM_ACK):
            return {
                **base,
                **self.c,
                "noise_protocol": "Noise_NX_25519_AESGCM_SHA256",
                "ciphertext": "A" * 64,
                **(
                    {"status": "verified", "transcript_context_hash": "e" * 64}
                    if kind == F.KEY_CONFIRM_ACK
                    else {}
                ),
            }
        if kind in (F.HELLO_ACK, F.STREAM_READY_ACK):
            return {
                **common,
                "state": "RUNNING",
                "output_cursor": "0",
                **(
                    {"input_limit": 16384, "output_limit": 32768}
                    if kind == F.HELLO_ACK
                    else {"admission_fence": "f" * 64}
                ),
            }
        if kind == F.ADMISSION_COMMIT_ACK:
            return {**common, "result": "committed", "reason_code": None}
        raise AssertionError(kind)

    def frame(self, kind: F, leg: Leg, seq: int) -> bytes:
        return encode_wire_frame(kind, leg, self.payload(kind), seq)

    def active(self) -> bool:
        return self.authority.is_active(self.ticket.claims, context=self.context)
