"""Ciphertext-only WAW API relay, fixed UDS adapter and authenticated WS handler.

Deployment must inject a bound Runtime coordinator and explicitly enable this
handler. The default API has neither. This module imports opaque wire/context
code only: no Runtime process code, Noise profile, keys or decryption authority.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import secrets
import select
import socket
import stat
import struct
import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from agentbox_core.configuration import Settings
from agentbox_core.models import AdminUser, ControlPlaneSession
from agentbox_core.security import keyed_digest
from agentbox_core.services import AuthenticatedSession, ControlPlaneServices
from agentbox_core.waw_lease import LeaseCleanupFence, LeaseCleanupState, LeaseOwner
from agentbox_core.waw_recovery import RecoveryIdentity
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
)
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.abws import decode_frame
from agentbox_protocol.awce import decode_awce
from agentbox_protocol.waw_wire import (
    Leg,
    WireFrame,
    decode_wire_frame,
    encode_wire_frame,
    forward_wire_frame,
)
from fastapi import WebSocket
from sqlalchemy import select as sql_select

from agentbox_api.waw_admission import wire_admission_tuple
from agentbox_api.waw_admission_coordinator import (
    AdmissionAuditAction,
    AdmissionAuditEvent,
    AdmissionAuditPort,
    AdmissionBrowserPort,
    AdmissionFailure,
    AdmissionRevalidator,
    AdmissionRuntimePort,
    PendingAdmissionBudget,
    RuntimeCleanupProof,
    RuntimeCleanupRequest,
    RuntimePrepared,
    RuntimePrepareRequest,
    WAWAdmissionCoordinator,
)
from agentbox_api.waw_authorization import WorkspaceAuthorizationPolicy
from agentbox_api.waw_input_budget import (
    BrowserDelivery,
    InputBudget,
    InputBudgetError,
    InputBudgetOwner,
    InputBudgetToken,
    is_encoded_input,
)
from agentbox_api.waw_websocket_protocol import NATIVE_SCOPE_KEY, WAWWebSocketProtocol

BA, AB, AR, RA = tuple(Leg)
_STREAM_PATH = Path("/run/agentbox-waw/workspace-stream.sock")


class RelayFailure(RuntimeError):
    def __init__(self, code: str = "PROTOCOL_INVALID", close_code: int = 4400) -> None:
        self.code, self.close_code = code, close_code
        super().__init__("WAW attachment closed")


def _canonical_origin(origin: str) -> None:
    parsed = urlsplit(origin)
    host = parsed.hostname
    if (
        not origin.isascii()
        or parsed.scheme not in ("https", "http")
        or not host
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or origin != origin.lower()
        or host.endswith(".")
        or "%" in origin
    ):
        raise RelayFailure("ATTACHMENT_STALE", 4403)
    port = parsed.port
    if port == (443 if parsed.scheme == "https" else 80):
        raise RelayFailure("ATTACHMENT_STALE", 4403)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if (
            re.fullmatch(r"[0-9.]+", host)
            or len(host) > 253
            or any(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None
                for label in host.split(".")
            )
        ):
            raise RelayFailure("ATTACHMENT_STALE", 4403) from None
        if parsed.scheme == "http" and host != "localhost":
            raise RelayFailure("ATTACHMENT_STALE", 4403) from None
        authority = host
    else:
        if host != address.compressed or (parsed.scheme == "http" and not address.is_loopback):
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        authority = "[" + host + "]" if address.version == 6 else host
    if parsed.netloc != authority + (":" + str(port) if port else ""):
        raise RelayFailure("ATTACHMENT_STALE", 4403)


class RuntimeControl(Protocol):
    @property
    def attestation(self) -> dict[str, Any] | None: ...

    async def request_lifecycle(self, action: str, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RuntimeSocketTrust:
    """Locally provisioned, non-secret DAC/peer expectations; no caller path."""

    socket_gid: int
    runtime_uid: int
    runtime_gid: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (self.socket_gid, self.runtime_uid, self.runtime_gid)
        ):
            raise ValueError("invalid Runtime socket trust")


class UnixRuntimePort:
    """One fixed provenance-checked UDS stream and fixed control actions.

    Control cleanup serializes after any prepare task. A cancelled/lost prepare
    therefore cannot install a later orphan after a purported cleanup success.
    API proof construction requires the exact authenticated response tuple.
    """

    def __init__(self, control: RuntimeControl, trust: RuntimeSocketTrust) -> None:
        self._control, self._trust = control, trust
        self._connection = object()
        self._socket: socket.socket | None = None
        self._receive_task: asyncio.Task[bytes] | None = None
        self._pidfd: int | None = None
        self._request: RuntimePrepareRequest | None = None
        self._prepare_task: asyncio.Task[dict[str, Any]] | None = None
        self._aborted = False
        self._cleanup_id = "wreq_" + secrets.token_hex(16)
        self._send_guard: Callable[[bytes], None] | None = None
        self._write_waiter: asyncio.Future[None] | None = None
        self._write_loop: asyncio.AbstractEventLoop | None = None
        self._write_fd: int | None = None

    @property
    def connection_id(self) -> object:
        return self._connection

    def _path_identity(self) -> tuple[int, int]:
        parent, details = os.lstat(_STREAM_PATH.parent), os.lstat(_STREAM_PATH)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != 0
            or parent.st_mode & 0o022
            or not stat.S_ISSOCK(details.st_mode)
            or details.st_uid != 0
            or details.st_gid != self._trust.socket_gid
            or stat.S_IMODE(details.st_mode) != 0o660
        ):
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        return details.st_dev, details.st_ino

    async def _connect(self) -> None:
        before = self._path_identity()
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        peer.setblocking(False)
        for option in (socket.SO_RCVBUF, socket.SO_SNDBUF):
            peer.setsockopt(socket.SOL_SOCKET, option, 32768)
            if peer.getsockopt(socket.SOL_SOCKET, option) > 65536:
                peer.close()
                raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        self._socket = peer
        await asyncio.get_running_loop().sock_connect(peer, str(_STREAM_PATH))
        if self._aborted or self._path_identity() != before:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        pid, uid, gid = struct.unpack(
            "3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
        if uid != self._trust.runtime_uid or gid != self._trust.runtime_gid:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        self._pidfd = os.pidfd_open(pid, 0)
        self._current()

    def _current(self) -> None:
        if self._aborted or self._pidfd is None or select.select([self._pidfd], [], [], 0)[0]:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        attestation = self._control.attestation
        if self._request is not None and (
            attestation is None or attestation.get("runtime_epoch") != self._request.runtime_epoch
        ):
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)

    @staticmethod
    def _body(request: RuntimePrepareRequest | RuntimeCleanupRequest) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            **wire_admission_tuple(request.claims),
            "runtime_epoch": request.runtime_epoch,
        }

    @staticmethod
    def _validate_response(
        response: dict[str, Any], request: RuntimePrepareRequest | RuntimeCleanupRequest
    ) -> None:
        expected = UnixRuntimePort._body(request)
        if any(response.get(name) != value for name, value in expected.items()):
            raise RelayFailure("ATTACHMENT_STALE", 4403)

    async def prepare(self, request: RuntimePrepareRequest) -> RuntimePrepared:
        if (
            self._request is not None
            or self._aborted
            or request.connection_id is not self._connection
        ):
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        self._request = request
        action = "workspace.attach.prepare"
        body = {
            **self._body(request),
            "action": action,
            "request_id": "wreq_" + secrets.token_hex(16),
            "resume_cursor": request.resume_cursor,
            "previous_runtime_epoch": request.previous_runtime_epoch,
        }
        self._prepare_task = asyncio.create_task(self._control.request_lifecycle(action, body))
        self._prepare_task.add_done_callback(_consume_result)
        response = await asyncio.shield(self._prepare_task)
        self._validate_response(response, request)
        if (
            response.get("status") != "PREPARED"
            or response.get("resume_cursor") != request.resume_cursor
            or response.get("previous_runtime_epoch") != request.previous_runtime_epoch
        ):
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        await self._connect()
        capability = response.get("capability")
        if type(capability) is not str:
            raise RelayFailure()
        self._prepare_task = None
        return RuntimePrepared(request.claims, request.runtime_epoch, self._connection, capability)

    async def send(self, frame: bytes) -> None:
        decode_wire_frame(frame, AR)
        if self._socket is None:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        offset = 0
        attempts = 0
        while offset < len(frame):
            if attempts == 16:
                await asyncio.sleep(0)
                attempts = 0
            attempts += 1
            self._current()
            if self._send_guard is not None:
                self._send_guard(frame)
            # No await separates the final permit from each kernel write.
            try:
                sent = self._socket.send(memoryview(frame)[offset:])
            except BlockingIOError:
                await self._wait_writable()
                continue
            if not sent:
                raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
            offset += sent

    def install_send_guard(self, guard: Callable[[bytes], None]) -> None:
        if self._send_guard is not None:
            raise RelayFailure()
        self._send_guard = guard

    async def _wait_writable(self) -> None:
        if self._socket is None or self._write_waiter is not None:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[None] = loop.create_future()
        waiter.add_done_callback(_consume_result)
        fd = self._socket.fileno()
        self._write_waiter, self._write_loop, self._write_fd = waiter, loop, fd

        def ready() -> None:
            if not waiter.done():
                waiter.set_result(None)

        try:
            loop.add_writer(fd, ready)
            await waiter
        finally:
            if self._write_waiter is waiter:
                loop.remove_writer(fd)
                self._write_waiter = self._write_loop = self._write_fd = None

    async def _read_exact(self, size: int) -> bytes:
        if self._socket is None:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        result = bytearray()
        while len(result) < size:
            part = await asyncio.get_running_loop().sock_recv(self._socket, size - len(result))
            if not part:
                raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
            result.extend(part)
        return bytes(result)

    async def _read_frame(self) -> bytes:
        header = await self._read_exact(24)
        magic, version, kind, flags, size, sequence, reserved = struct.unpack("!4sBBHIQI", header)
        if (
            magic != b"ABWS"
            or version != 1
            or flags
            or reserved
            or not sequence
            or (kind != F.OUTPUT and size > 4096)
        ):
            raise RelayFailure()
        if kind == F.OUTPUT and size > 32828:
            raise RelayFailure("PROTOCOL_INVALID", 1009)
        payload = await self._read_exact(size)
        self._current()
        return header + payload

    async def receive(self) -> bytes:
        self._current()
        # One bounded read task survives coordinator reader cancellation, even
        # when its header has already been consumed. The next reader takes the
        # same result; there is never a second socket reader or lost frame.
        if self._receive_task is None:
            self._receive_task = asyncio.create_task(self._read_frame())
            self._receive_task.add_done_callback(_consume_result)
        raw = await asyncio.shield(self._receive_task)
        self._receive_task = None
        return raw

    async def close_and_cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupProof:
        if (
            self._request is None
            or request.claims != self._request.claims
            or request.runtime_epoch != self._request.runtime_epoch
            or request.connection_id is not self._connection
        ):
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        if self._prepare_task is not None:
            # An unknown prepare result is not positive cleanup evidence.
            await asyncio.shield(self._prepare_task)
        if request.close_frame is not None and not self._aborted:
            with suppress(Exception):
                await self.send(request.close_frame)
        action = "workspace.attach.detach"
        response = await self._control.request_lifecycle(
            action, {**self._body(request), "action": action, "request_id": self._cleanup_id}
        )
        self._validate_response(response, request)
        if (
            response.get("status") not in ("DETACHED", "ALREADY_DETACHED")
            or response.get("cleanup_state") != "ATTACH_PTY_CLOSED"
            or response.get("reason_code") is not None
        ):
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        self.abort()
        return RuntimeCleanupProof(
            request.claims,
            request.runtime_epoch,
            self._connection,
            str(response["status"]).lower(),
            "ATTACH_PTY_CLOSED",
        )

    def abort(self) -> None:
        self._aborted = True
        if self._write_loop is not None and self._write_fd is not None:
            # Remove the exact registration before closing/reusing the FD.
            self._write_loop.remove_writer(self._write_fd)
        if self._write_waiter is not None and not self._write_waiter.done():
            self._write_waiter.set_exception(RelayFailure("RUNTIME_UNAVAILABLE", 1013))
        self._write_waiter = self._write_loop = self._write_fd = None
        if self._socket is not None:
            self._socket.close()
        if self._receive_task is not None:
            self._receive_task.cancel()
        if self._pidfd is not None:
            os.close(self._pidfd)
            self._pidfd = None


def _consume_result(task: asyncio.Future[Any]) -> None:
    if not task.cancelled():
        task.exception()


@dataclass
class _Bucket:
    rate: float
    burst: float
    at: float
    tokens: float = -1

    def take(self, now: float, cost: int = 1) -> bool:
        if now < self.at:
            raise RelayFailure()
        if self.tokens < 0:
            self.tokens = self.burst
        self.tokens = min(self.burst, self.tokens + (now - self.at) * self.rate)
        self.at = now
        if cost > self.tokens:
            return False
        self.tokens -= cost
        return True


class _LaneQueue:
    """Encoded-byte ceilings include the frame currently being sent."""

    def __init__(self, data_limit: int, control_limit: int) -> None:
        self.limits = (data_limit, control_limit)
        self.sizes = [0, 0]
        self.items: asyncio.Queue[tuple[bytes, int, InputBudgetToken | None]] = asyncio.Queue(
            maxsize=256
        )

    def put(self, raw: bytes, *, data: bool, input_token: InputBudgetToken | None = None) -> None:
        lane = 0 if data else 1
        if self.items.full() or self.sizes[lane] + len(raw) > self.limits[lane]:
            raise RelayFailure("OUTPUT_BACKPRESSURE" if data else "INTERNAL_BOUNDED", 1013)
        self.sizes[lane] += len(raw)
        self.items.put_nowait((raw, lane, input_token))

    def done(self, item: tuple[bytes, int, InputBudgetToken | None]) -> None:
        self.sizes[item[1]] -= len(item[0])

    def clear(self) -> tuple[InputBudgetToken, ...]:
        tokens: list[InputBudgetToken] = []
        while not self.items.empty():
            token = self.items.get_nowait()[2]
            if token is not None:
                tokens.append(token)
        self.sizes[:] = [0, 0]
        return tuple(tokens)


@dataclass(repr=False)
class _InputReference:
    browser_hop: int
    crypto_sequence: int
    deadline: float
    result: str | None = None
    terminal_body: dict[str, Any] | None = None
    replayed: bool = False


class WAWCiphertextRelay:
    """ACTIVE relay over R6's real authority transaction and exact wire trace."""

    def __init__(
        self,
        coordinator: WAWAdmissionCoordinator,
        *,
        authority: AttachmentAuthority,
        claims: AttachmentTuple,
        context: AuthenticatedAttachmentContext,
        browser: AdmissionBrowserPort,
        runtime: AdmissionRuntimePort,
        audit: AdmissionAuditPort,
        revalidator: AdmissionRevalidator,
        input_budget: InputBudget,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.coordinator, self.authority, self.claims, self.context = (
            coordinator,
            authority,
            claims,
            context,
        )
        self.browser, self.runtime, self.audit, self.validator = (
            browser,
            runtime,
            audit,
            revalidator,
        )
        self.clock, self.wire = clock, coordinator.wire_session
        self.connection = runtime.connection_id
        self.input_budget = input_budget
        self.input_budget.assert_identity(
            connection_id=self.connection,
            attachment_id=claims.attachment_id,
            runtime_epoch=context.runtime_epoch,
        )
        self.input_budget.install_overflow_fence(
            lambda: self._fence_io(RelayFailure("INPUT_RATE_LIMITED", 4429))
        )
        self.started = self.last_activity = self.last_runtime_heartbeat = self.last_health_sent = (
            clock()
        )
        self._last = self.started
        self.state = "RUNNING"
        self._closed = self._detaching = self._exited = False
        self._terminal_at: float | None = None
        self._publication_fenced = False
        self._failure: RelayFailure | None = None
        self._browser_published_next = 3  # R6 completed KEY_ATTEST/KEY_CONFIRM_ACK.
        self._browser_inflight: F | None = None
        self._publication_uncertain = False
        self._last_revocation_check = self.started
        self._inputs: dict[int, _InputReference] = {}
        self.input_uncertain: tuple[tuple[int, int, int], ...] = ()
        self._resize: tuple[int, int, dict[str, Any]] | None = None
        self._detach: tuple[int, int] | None = None
        self._browser_queue = _LaneQueue(192 * 1024, 64 * 1024)
        self._runtime_queue = _LaneQueue(64 * 1024, 16 * 1024)
        self._input_rate = _Bucket(8192, 16384, self.started)
        self._resize_rate = _Bucket(5, 5, self.started)
        self._control_rate = _Bucket(10, 10, self.started)
        self._heartbeat_rate = _Bucket(0.2, 2, self.started)
        self._ping_rates = {BA: _Bucket(2, 2, self.started), RA: _Bucket(2, 2, self.started)}
        self._violations: dict[str, tuple[int, int]] = {}
        self._runtime_ping: dict[str, tuple[str, float]] = {}
        self._browser_ping: dict[str, tuple[str, float]] = {}
        self._runtime_responses: dict[str, tuple[str, float]] = {}
        self._last_probe = self.started
        self._runtime_heartbeat_window = -1
        self._tasks: list[asyncio.Task[Any]] = []
        self._cleanup_tasks: set[asyncio.Task[Any]] = set()
        self._close_task: asyncio.Task[None] | None = None
        self._authority_fence_error: BaseException | None = None
        self.lease = LeaseCleanupFence(clock=clock)
        identity = RecoveryIdentity(
            workspace_id=claims.workspace_id,
            project_id=claims.project_id,
            agent_type=str(claims.agent_type),
            generation=claims.generation,
            binding_revision=claims.binding_revision,
            binding_digest=claims.binding_digest,
            runtime_host_installation_id=claims.runtime_host_installation_id,
            runtime_host_installation_revision=claims.runtime_host_installation_revision,
            runtime_epoch=int(context.runtime_epoch),
            api_authority_epoch=claims.api_authority_epoch,
            attachment_id=claims.attachment_id,
            lease_number=claims.lease_number,
            session_id=context.session_id,
            auth_epoch=claims.auth_epoch,
        )
        self.owner = LeaseOwner(identity)

    def _now(self) -> float:
        now = self.clock()
        if now < self._last or self.runtime.connection_id is not self.connection:
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        self._last = now
        return now

    def _fence_io(self, failure: RelayFailure) -> None:
        if self._failure is None:
            self._failure = failure
        self._publication_fenced = True
        handle = self.coordinator.reservation
        try:
            if handle is not None:
                self.authority.fence(handle)
        except BaseException as error:
            if self._authority_fence_error is None:
                self._authority_fence_error = error
            raise
        finally:
            # Transport destruction cannot turn an authority failure into
            # successful isolation or cleanup; the original error propagates.
            if self._browser_inflight is not None:
                self._publication_uncertain = True
                with suppress(BaseException):
                    self._abort_browser(failure.close_code)
            with suppress(BaseException):
                self.runtime.abort()

    def _check_deadlines(self, now: float) -> None:
        failure: RelayFailure | None = None
        if now - self.last_runtime_heartbeat >= 10 or any(
            now >= entry[1]
            for table in (self._runtime_ping, self._runtime_responses)
            for entry in table.values()
        ):
            failure = RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        elif any(now >= entry[1] for entry in self._browser_ping.values()):
            failure = RelayFailure("ATTACHMENT_STALE", 4403)
        if failure is not None:
            self._fence_io(failure)
            raise failure

    def _permit(self, *, authorization: bool = True) -> float:
        now = self._now()
        self._check_deadlines(now)
        if (
            self._closed
            or getattr(self.browser, "transport_open", True) is not True
            or self._publication_fenced
            or self._detaching
            or self._exited
            or self.lease.tick(now=now).state != LeaseCleanupState.ACTIVE
            or now - self.last_activity >= 900
            or now - self.started >= 28800
        ):
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        if (
            authorization and self.validator.current(self.claims, self.context) is not True
        ) or not self.authority.is_active(self.claims, context=self.context, now=now):
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        return now

    def _publication_authorized(self) -> bool:
        try:
            checker = getattr(self.validator, "publication_current", self.validator.current)
            return checker(self.claims, self.context) is True
        except Exception:
            return False

    def _publication_permit(self) -> None:
        now = self._now()
        self._check_deadlines(now)
        if (
            self._closed
            or getattr(self.browser, "transport_open", True) is not True
            or self._publication_fenced
            or now - self.last_activity >= 900
            or now - self.started >= 28800
            or self.lease.tick(now=now).state
            not in (LeaseCleanupState.ACTIVE, LeaseCleanupState.DETACHING)
            or not self.authority.is_active(self.claims, context=self.context, now=now)
            or not self._publication_authorized()
        ):
            raise RelayFailure("ATTACHMENT_STALE", 4403)

    def _abort_browser(self, code: int) -> None:
        abort = getattr(self.browser, "abort", None)
        if callable(abort):
            abort(code)
        else:
            self.browser.close(code)

    def _discard_output_at_fence(self) -> None:
        if self._browser_queue.sizes[0] or self._browser_inflight == F.OUTPUT:
            # The wire trace already allocated those outer hops. Do not send
            # later metadata across the hole or continue the old CipherState.
            self._publication_fenced = True
            self._browser_queue.clear()
            if self._browser_inflight is not None:
                self._publication_uncertain = True
                self._abort_browser(4403)
            raise RelayFailure("ATTACHMENT_STALE", 4403)

    def _before_browser_write(self, raw: bytes) -> None:
        try:
            self._check_deadlines(self._now())
            frame = decode_wire_frame(raw, AB)
            if self._closed:
                body = frame.json_payload
                if (
                    frame.frame_type != F.ERROR
                    or body is None
                    or body["code"] != "INPUT_RATE_LIMITED"
                    or body["retryable"] is not False
                    or not self._publication_authorized()
                ):
                    raise RelayFailure("ATTACHMENT_STALE", 4403)
            else:
                self._publication_permit()
                if frame.frame_type in (F.ADMITTED, F.OUTPUT):
                    self._permit()
        except Exception as error:
            failure = error if isinstance(error, RelayFailure) else RelayFailure()
            self._fence_io(failure)
            raise failure from None

    def _before_runtime_write(self, raw: bytes) -> None:
        frame = decode_wire_frame(raw, AR)
        if frame.frame_type == F.CLOSE:
            return  # The exact internal cleanup fence remains legal after revoke.
        try:
            self._check_deadlines(self._now())
            if frame.frame_type == F.DETACH:
                self._publication_permit()
            else:
                self._permit()
        except Exception as error:
            failure = error if isinstance(error, RelayFailure) else RelayFailure()
            self._fence_io(failure)
            raise failure from None

    async def _publish_browser(self, raw: bytes, *, closing: bool = False) -> None:
        frame = decode_wire_frame(raw, AB)
        if self._publication_uncertain or frame.hop_sequence != self._browser_published_next:
            self._publication_fenced = True
            raise RelayFailure()
        if closing and not self._closed:
            raise RelayFailure()
        self._before_browser_write(raw)
        self._browser_inflight = frame.frame_type
        try:
            await self.browser.send_key_frame(raw)
        except BaseException:
            self._publication_uncertain = True
            raise
        else:
            self._browser_published_next += 1
            if self._publication_fenced or (self._closed and not closing):
                raise RelayFailure("ATTACHMENT_STALE", 4403)
        finally:
            self._browser_inflight = None

    def _accept(self, leg: Leg, raw: bytes) -> WireFrame:
        return self.wire.accept(leg, raw, stream_id=self.connection, now=int(self._now() * 1e9))

    def _emit(self, kind: F, leg: Leg, body: dict[str, Any]) -> bytes:
        return encode_wire_frame(kind, leg, body, self.wire.expected_sequence(leg))

    def _queue_browser(self, raw: bytes, *, observed: bool = False) -> None:
        frame = decode_wire_frame(raw, AB)
        self._browser_queue.put(raw, data=frame.frame_type == F.OUTPUT)
        if not observed:
            self._accept(AB, raw)

    def _queue_runtime(
        self,
        raw: bytes,
        *,
        data: bool = False,
        input_token: InputBudgetToken | None = None,
    ) -> None:
        if data:
            if input_token is None:
                raise RelayFailure()
            self.input_budget.transfer(
                input_token,
                source=InputBudgetOwner.BROWSER_DELIVERY,
                target=InputBudgetOwner.RELAY_RUNTIME_PENDING,
            )
        elif input_token is not None:
            raise RelayFailure()
        try:
            self._runtime_queue.put(raw, data=data, input_token=input_token)
            self._accept(AR, raw)
        except BaseException:
            if data and input_token is not None:
                with suppress(InputBudgetError):
                    self.input_budget.transfer(
                        input_token,
                        source=InputBudgetOwner.RELAY_RUNTIME_PENDING,
                        target=InputBudgetOwner.BROWSER_DELIVERY,
                    )
            raise

    def _limit(self, name: str, *, interval: int = 1) -> None:
        now = self._now()
        window = int((now - self.started) // interval)
        previous, count = self._violations.get(name, (-2, 0))
        count = count if previous == window else count + 1 if previous == window - 1 else 1
        self._violations[name] = (window, count)
        if count >= 3:
            raise RelayFailure("CONTROL_RATE_LIMITED", 4429)
        self._queue_browser(
            self._emit(
                F.ERROR,
                AB,
                {
                    "protocol_version": 1,
                    "code": "CONTROL_RATE_LIMITED",
                    "retryable": True,
                    "request_id": "wreq_" + secrets.token_hex(16),
                },
            )
        )

    @staticmethod
    def _size_check(raw: bytes, *, output: bool) -> None:
        if type(raw) is bytes and len(raw) >= 24 and raw[5] == (F.OUTPUT if output else F.INPUT):
            frame = decode_frame(raw)
            if len(decode_awce(frame.payload).ciphertext) > (32784 if output else 16400):
                raise RelayFailure("PROTOCOL_INVALID", 1009)

    def browser_frame(self, delivery: BrowserDelivery) -> None:
        token: InputBudgetToken | None = None
        try:
            if type(delivery) is not BrowserDelivery:
                raise RelayFailure()
            raw, token = delivery.wire_bytes, delivery.input_token
            if type(raw) is not bytes:
                raise RelayFailure()
            if self._publication_fenced:
                raise self._failure or RelayFailure("ATTACHMENT_STALE", 4403)
            self._browser_frame(raw, token)
            token = None  # A valid INPUT token now belongs to the Runtime queue.
        except Exception as error:
            if token is not None:
                self.input_budget.release(token, owner=InputBudgetOwner.BROWSER_DELIVERY)
            failure = error if isinstance(error, RelayFailure) else RelayFailure()
            self._fence_io(failure)
            raise failure from None

    def _browser_frame(self, raw: bytes, input_token: InputBudgetToken | None) -> None:
        """One complete message; all decisions happen before Runtime allocation."""
        now = self._permit(authorization=False)
        self._size_check(raw, output=False)
        encoded_input = is_encoded_input(raw)
        if encoded_input:
            if (
                type(input_token) is not InputBudgetToken
                or not input_token.live
                or input_token.owner != InputBudgetOwner.BROWSER_DELIVERY
                or input_token.size != len(raw)
            ):
                raise RelayFailure()
        elif input_token is not None:
            raise RelayFailure()
        frame = self._accept(BA, raw)
        kind, body = frame.frame_type, frame.json_payload
        if kind == F.INPUT:
            assert input_token is not None
            envelope = decode_awce(frame.payload)
            size = len(envelope.ciphertext) - 16
            if size > 16384:
                raise RelayFailure("PROTOCOL_INVALID", 1009)
            if (
                not self._input_rate.take(now, size)
                or len(self._inputs) >= 256
                or self._runtime_queue.sizes[0] + len(raw) > 65536
                or self._runtime_queue.items.full()
            ):
                raise RelayFailure("INPUT_RATE_LIMITED", 4429)
            self._permit()
            hop = self.wire.expected_sequence(AR)
            self._inputs[hop] = _InputReference(
                frame.hop_sequence, envelope.crypto_sequence, now + 5
            )
            # The immutable forwarded copy is built and queued without an await;
            # one token transfers with it instead of charging another 64 KiB.
            forwarded = forward_wire_frame(frame, AR, hop)
            self._queue_runtime(forwarded, data=True, input_token=input_token)
            self.last_activity = now
            return
        assert body is not None
        if kind == F.HEARTBEAT:
            if not self._heartbeat_rate.take(now):
                self._limit("heartbeat", interval=5)
                return
            self._permit()
            self.lease.heartbeat(now=now)
            self.authority.heartbeat(self.claims, context=self.context, now=now)
        elif kind == F.PING:
            if not self._ping_rates[BA].take(now):
                self._limit("ping")
                return
            self._permit()
            if body["nonce"] in self._browser_ping or len(self._browser_ping) >= 2:
                raise RelayFailure()
            self._browser_ping[body["nonce"]] = (body["sent_at_monotonic_tick"], now + 5)
            self._queue_browser(
                self._emit(
                    F.PONG,
                    AB,
                    {
                        "protocol_version": 1,
                        "nonce": body["nonce"],
                        "echoed_sent_at_monotonic_tick": body["sent_at_monotonic_tick"],
                    },
                )
            )
        elif kind == F.RESIZE:
            if not self._resize_rate.take(now) or self._resize is not None:
                self._limit("resize")
                return
            hop = self.wire.expected_sequence(AR)
            self._permit()
            self._resize = frame.hop_sequence, hop, body
            self._queue_runtime(self._emit(kind, AR, body))
            self.last_activity = now
        elif kind == F.DETACH:
            self._discard_output_at_fence()
            if not self._control_rate.take(now):
                self._limit("control")
                return
            hop = self.wire.expected_sequence(AR)
            self._permit()
            self._detach = frame.hop_sequence, hop
            self._queue_runtime(self._emit(kind, AR, body))
            self._detaching = True
            self.lease.request_detach(now=now)
        else:
            raise RelayFailure()

    def runtime_frame(self, raw: bytes) -> None:
        try:
            if self._publication_fenced:
                raise self._failure or RelayFailure("ATTACHMENT_STALE", 4403)
            self._runtime_frame(raw)
        except Exception as error:
            failure = error if isinstance(error, RelayFailure) else RelayFailure()
            self._fence_io(failure)
            raise failure from None

    def _runtime_frame(self, raw: bytes) -> None:
        now = self._now()
        self._check_deadlines(now)
        self._size_check(raw, output=True)
        frame = self._accept(RA, raw)
        kind, body = frame.frame_type, frame.json_payload
        if kind == F.OUTPUT:
            if len(decode_awce(frame.payload).ciphertext) - 16 > 32768:
                raise RelayFailure("PROTOCOL_INVALID", 1009)
            self._queue_browser(forward_wire_frame(frame, AB, self.wire.expected_sequence(AB)))
            return
        assert body is not None
        if kind == F.ACK:
            if self._exited:
                raise RelayFailure()
            reference = self._inputs.get(int(body["runtime_input_hop_sequence"]))
            if (
                reference is None
                or reference.crypto_sequence != int(body["crypto_sequence"])
                or now >= reference.deadline
            ):
                raise RelayFailure()
            result = body["result"]
            if reference.terminal_body is not None:
                if reference.replayed or body != reference.terminal_body:
                    raise RelayFailure()
                reference.replayed = True
            else:
                if (reference.result is None and result not in ("accepted", "rejected")) or (
                    reference.result == "accepted"
                    and result not in ("written_to_pty", "write_uncertain")
                ):
                    raise RelayFailure()
                reference.result = result
                if result != "accepted":
                    reference.terminal_body = body
            self._queue_browser(
                self._emit(
                    kind, AB, {**body, "browser_input_hop_sequence": str(reference.browser_hop)}
                )
            )
        elif kind == F.RESIZE_ACK:
            if self._resize is None:
                raise RelayFailure()
            browser_hop, runtime_hop, requested = self._resize
            if (
                body["acknowledged_hop_sequence"] != str(runtime_hop)
                or body["requested_columns"] != requested["columns"]
                or body["requested_rows"] != requested["rows"]
            ):
                raise RelayFailure()
            self._queue_browser(
                self._emit(kind, AB, {**body, "acknowledged_hop_sequence": str(browser_hop)})
            )
            self._resize = None
        elif kind == F.DETACH_ACK:
            if self._detach is None or body["acknowledged_hop_sequence"] != str(self._detach[1]):
                raise RelayFailure()
            translated = {
                key: body[key]
                for key in (
                    "protocol_version",
                    "attachment_id",
                    "lease_number",
                    "result",
                    "cleanup_state",
                    "reason_code",
                )
            }
            translated["acknowledged_hop_sequence"] = str(self._detach[0])
            self._queue_browser(self._emit(kind, AB, translated))
            positive = (
                body["result"] in ("detached", "already_detached")
                and body["cleanup_state"] == "ATTACH_PTY_CLOSED"
            )
            self._queue_browser(
                self._emit(
                    F.CLOSE,
                    AB,
                    {
                        "protocol_version": 1,
                        "code": "DETACHED" if positive else "ATTACHMENT_STALE",
                        "workspace_state_at_close": self.state,
                    },
                )
            )
            self._exited = True
            self._terminal_at = now
        elif kind == F.HEARTBEAT:
            window = int((now - self.started) // 5)
            if window == self._runtime_heartbeat_window:
                raise RelayFailure("CONTROL_RATE_LIMITED", 4429)
            self._runtime_heartbeat_window, self.last_runtime_heartbeat = window, now
        elif kind == F.PING:
            if not self._ping_rates[RA].take(now):
                raise RelayFailure("CONTROL_RATE_LIMITED", 4429)
            if body["nonce"] in self._runtime_responses or len(self._runtime_responses) >= 2:
                raise RelayFailure()
            self._runtime_responses[body["nonce"]] = (body["sent_at_monotonic_tick"], now + 5)
            self._queue_runtime(
                self._emit(
                    F.PONG,
                    AR,
                    {
                        "protocol_version": 1,
                        "nonce": body["nonce"],
                        "echoed_sent_at_monotonic_tick": body["sent_at_monotonic_tick"],
                    },
                )
            )
        elif kind == F.PONG:
            if not self._ping_rates[RA].take(now):
                raise RelayFailure("CONTROL_RATE_LIMITED", 4429)
            pending = self._runtime_ping.pop(body["nonce"], None)
            if (
                pending is None
                or pending[0] != body["echoed_sent_at_monotonic_tick"]
                or now >= pending[1]
            ):
                raise RelayFailure()
        elif kind in (F.EXIT, F.CLOSE):
            if kind == F.EXIT and any(
                value.terminal_body is None for value in self._inputs.values()
            ):
                raise RelayFailure()
            self._exited = True
            if kind == F.CLOSE:
                self._terminal_at = now
            self.state = body["state"] if kind == F.EXIT else body["workspace_state_at_close"]
            self._discard_output_at_fence()
            self._queue_browser(self._emit(kind, AB, body))
        elif kind in (F.GAP, F.STATE, F.ERROR):
            if kind == F.ERROR or (kind == F.STATE and body["state"] != "RUNNING"):
                self._discard_output_at_fence()
            if kind == F.ERROR:
                body = {**body, "request_id": "wreq_" + secrets.token_hex(16)}
            if kind == F.STATE:
                self.state = body["state"]
                body = {name: value for name, value in body.items() if name != "runtime_epoch"}
            self._queue_browser(self._emit(kind, AB, body))
        else:
            raise RelayFailure()

    async def _browser_reader(self) -> None:
        while True:
            self.browser_frame(await self.browser.receive())
            await asyncio.sleep(0)

    async def _runtime_reader(self) -> None:
        while True:
            self.runtime_frame(await self.runtime.receive())
            if self._terminal_at is not None:
                # Let the bounded browser writer drain ACK/EXIT/CLOSE in order.
                # A normal Runtime EOF must not race and discard this batch.
                await asyncio.Future()
            await asyncio.sleep(0)

    async def _writer(self, queue: _LaneQueue, *, browser: bool) -> None:
        while True:
            item = await queue.items.get()
            raw, _lane, input_token = item
            if browser:
                if input_token is not None:
                    raise RelayFailure()
                await self._publish_browser(raw)
            else:
                self._before_runtime_write(raw)
                if input_token is not None:
                    self.input_budget.transfer(
                        input_token,
                        source=InputBudgetOwner.RELAY_RUNTIME_PENDING,
                        target=InputBudgetOwner.RUNTIME_SEND_INFLIGHT,
                    )
                    try:
                        await self.runtime.send(raw)
                    except BaseException:
                        # A cancelled or partial Runtime write destroys the
                        # channel before its credit can become reusable.
                        self._fence_io(RelayFailure("ATTACHMENT_STALE", 4403))
                        raise
                    finally:
                        # A completed/cancelled send no longer retains its queue
                        # item or local frame bytes before the exact token release.
                        queue.done(item)
                        del raw, item
                        self.input_budget.release(
                            input_token, owner=InputBudgetOwner.RUNTIME_SEND_INFLIGHT
                        )
                    if self._closed:
                        return
                    continue
                await self.runtime.send(raw)
            if self._closed:
                return
            queue.done(item)
            sent = decode_wire_frame(raw, AB if browser else AR)
            if sent.frame_type == F.PONG and sent.json_payload is not None:
                (self._browser_ping if browser else self._runtime_responses).pop(
                    sent.json_payload["nonce"], None
                )
            if browser and sent.frame_type == F.CLOSE:
                assert sent.json_payload is not None
                code = sent.json_payload["code"]
                number = {
                    "DETACHED": 1000,
                    "WORKSPACE_EXITED": 1000,
                    "WORKSPACE_STOPPED": 1000,
                    "PROTOCOL_INVALID": 4400,
                    "SEQUENCE_EXHAUSTED": 4400,
                    "ADMISSION_TIMEOUT": 4408,
                    "CONTROL_RATE_LIMITED": 4429,
                    "OUTPUT_BACKPRESSURE": 1013,
                    "RUNTIME_UNAVAILABLE": 1013,
                    "RUNTIME_RESTART": 1013,
                    "SERVICE_SHUTDOWN": 1012,
                }.get(code, 4403)
                raise RelayFailure(code, number)

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            now = self._now()
            self._check_deadlines(now)
            if self._terminal_at is not None and now - self._terminal_at >= 1:
                raise RelayFailure("ATTACHMENT_STALE", 4403)
            if not self._exited and not self._detaching:
                if self.lease.tick(now=now).state != LeaseCleanupState.ACTIVE:
                    raise RelayFailure("ATTACHMENT_STALE", 4403)
                if now - self._last_revocation_check >= 5:
                    self._permit()
                    self._last_revocation_check = now
            if (
                self._detaching
                and self.lease.tick(now=now).state == LeaseCleanupState.RECONCILIATION_REQUIRED
            ):
                raise RelayFailure("ATTACHMENT_STALE", 4403)
            if now - self.last_runtime_heartbeat >= 10:
                raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
            if now - self.last_health_sent >= 5 and not self._detaching and not self._exited:
                self._queue_runtime(
                    self._emit(
                        F.HEARTBEAT,
                        AR,
                        {
                            "protocol_version": 1,
                            "attachment_id": self.claims.attachment_id,
                            "lease_number": str(self.claims.lease_number),
                            "sent_at_monotonic_tick": str(max(1, int(now * 1e9))),
                        },
                    )
                )
                self.last_health_sent = now
            if now - self._last_probe >= 20 and not self._detaching and not self._exited:
                nonce = secrets.token_hex(8)
                tick = str(max(1, int(now * 1e9)))
                if len(self._runtime_ping) >= 2:
                    raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
                self._runtime_ping[nonce] = (tick, now + 5)
                self._queue_runtime(
                    self._emit(
                        F.PING,
                        AR,
                        {"protocol_version": 1, "nonce": nonce, "sent_at_monotonic_tick": tick},
                    )
                )
                self._last_probe = now
            if any(
                now >= entry[1]
                for table in (self._browser_ping, self._runtime_responses)
                for entry in table.values()
            ):
                raise RelayFailure("ATTACHMENT_STALE", 4403)
            for hop, reference in tuple(self._inputs.items()):
                if now >= reference.deadline:
                    if reference.terminal_body is None:
                        raise RelayFailure("ATTACHMENT_STALE", 4403)
                    del self._inputs[hop]
            if any(now >= pending[1] for pending in self._runtime_ping.values()):
                raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)

    async def run(self) -> None:
        await self.coordinator.run()
        self.started = self.last_activity = self.last_runtime_heartbeat = self.last_health_sent = (
            self.clock()
        )
        self.lease.begin(
            attachment_id=self.claims.attachment_id,
            generation=self.claims.generation,
            lease_number=self.claims.lease_number,
            owner=self.owner,
        )
        self.lease.commit_admission()
        try:
            browser_guard = getattr(self.browser, "install_publication_guard", None)
            if callable(browser_guard):
                browser_guard(self._before_browser_write)
            runtime_guard = getattr(self.runtime, "install_send_guard", None)
            if callable(runtime_guard):
                runtime_guard(self._before_runtime_write)
            self._permit()
            while (raw := self.coordinator.queue.read()) is not None:
                self._permit()
                self._queue_browser(raw, observed=True)
            self._tasks = [
                asyncio.create_task(operation)
                for operation in (
                    self._browser_reader(),
                    self._runtime_reader(),
                    self._writer(self._browser_queue, browser=True),
                    self._writer(self._runtime_queue, browser=False),
                    self._watch(),
                )
            ]
            done, _ = await asyncio.wait(self._tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            raise RelayFailure()
        except asyncio.CancelledError:
            await self.close(self._failure or RelayFailure("ATTACHMENT_STALE", 4403))
            current = asyncio.current_task()
            if self._failure is None or (current is not None and current.cancelling()):
                raise
        except BaseException as exc:
            await self.close(
                self._failure or (exc if isinstance(exc, RelayFailure) else RelayFailure())
            )

    async def close(self, failure: RelayFailure) -> None:
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._close_once(failure))
            self._close_task.add_done_callback(_consume_result)
        task = self._close_task
        interrupted = False
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.cancelled():
                    raise
                interrupted = True
        if interrupted:
            raise asyncio.CancelledError

    async def _close_once(self, failure: RelayFailure) -> None:
        can_notify_limit = (
            failure.code == "INPUT_RATE_LIMITED"
            and not any(self._browser_queue.sizes)
            and self.wire.admitted
            and not self._publication_uncertain
            and self._browser_inflight is None
            and self.wire.expected_sequence(AB) == self._browser_published_next
            and self._publication_authorized()
        )
        handle = self.coordinator.reservation
        if handle is not None:
            try:
                self.authority.fence(handle)
            except BaseException as error:
                if self._authority_fence_error is None:
                    self._authority_fence_error = error
        self.input_uncertain = tuple(
            (item.browser_hop, hop, item.crypto_sequence)
            for hop, item in self._inputs.items()
            if item.terminal_body is None
        )
        self._inputs.clear()
        self._browser_ping.clear()
        self._runtime_ping.clear()
        self._runtime_responses.clear()
        if self._browser_inflight is not None:
            self._publication_uncertain = True
            with suppress(BaseException):
                self._abort_browser(failure.close_code)
        for task in self._tasks:
            with suppress(BaseException):
                task.cancel()
        with suppress(BaseException):
            self.coordinator.queue.discard()
        with suppress(BaseException):
            self._browser_queue.clear()
        pending_tokens: tuple[InputBudgetToken, ...] = ()
        with suppress(BaseException):
            pending_tokens = self._runtime_queue.clear()
        for token in pending_tokens:
            with suppress(BaseException):
                self.input_budget.release(token, owner=InputBudgetOwner.RELAY_RUNTIME_PENDING)
        proof: RuntimeCleanupProof | None = None
        audited = False
        deadline = asyncio.get_running_loop().time() + 1.0
        if self._tasks:
            with suppress(BaseException):
                await asyncio.wait(self._tasks, timeout=0.05)
        if can_notify_limit and self._publication_authorized():
            with suppress(BaseException):
                raw = self._emit(
                    F.ERROR,
                    AB,
                    {
                        "protocol_version": 1,
                        "code": "INPUT_RATE_LIMITED",
                        "retryable": False,
                        "request_id": "wreq_" + secrets.token_hex(16),
                    },
                )
                self._accept(AB, raw)
                notify = asyncio.create_task(self._publish_browser(raw, closing=True))
                self._track_cleanup(notify)
                completed, _ = await asyncio.wait([notify], timeout=0.05)
                if notify not in completed:
                    self._publication_uncertain = True
                    notify.cancel()
                else:
                    notify.result()
        code = "CONTROL_RATE_LIMITED" if failure.code == "INPUT_RATE_LIMITED" else failure.code
        if code not in {
            "DETACHED",
            "ATTACHMENT_STALE",
            "RUNTIME_UNAVAILABLE",
            "PROTOCOL_INVALID",
            "OUTPUT_BACKPRESSURE",
            "CONTROL_RATE_LIMITED",
        }:
            code = "ATTACHMENT_STALE"
        cleanup_task: asyncio.Task[RuntimeCleanupProof] | None = None
        close: bytes | None = None
        with suppress(BaseException):
            close = self._emit(
                F.CLOSE,
                AR,
                {"protocol_version": 1, "code": code, "workspace_state_at_close": self.state},
            )
        with suppress(BaseException):
            cleanup_task = asyncio.create_task(
                self.runtime.close_and_cleanup(
                    RuntimeCleanupRequest(
                        self.claims, self.context.runtime_epoch, self.connection, close
                    )
                )
            )
            self._track_cleanup(cleanup_task)
        if cleanup_task is not None:
            with suppress(BaseException):
                cleanup_done, _ = await asyncio.wait(
                    [cleanup_task],
                    timeout=max(0, deadline - asyncio.get_running_loop().time() - 0.2),
                )
                if cleanup_task in cleanup_done:
                    proof = cleanup_task.result()
                else:
                    cleanup_task.cancel()
        audit_task: asyncio.Task[None] | None = None
        with suppress(BaseException):
            audit_task = asyncio.create_task(
                self.audit.persist(
                    AdmissionAuditEvent(
                        AdmissionAuditAction.DETACHED,
                        self.claims.workspace_id,
                        self.claims.attachment_id,
                        self.claims.generation,
                        self.context.runtime_epoch,
                        self.claims.api_authority_epoch,
                        failure.code,
                    )
                )
            )
            self._track_cleanup(audit_task)
        if audit_task is not None:
            with suppress(BaseException):
                audit_done, _ = await asyncio.wait(
                    [audit_task], timeout=max(0, deadline - asyncio.get_running_loop().time())
                )
                if audit_task in audit_done:
                    audit_task.result()
                    audited = True
                else:
                    audit_task.cancel()
        with suppress(BaseException):
            self.runtime.abort()
        with suppress(BaseException):
            if self._publication_uncertain:
                self._abort_browser(failure.close_code)
            else:
                self.browser.close(failure.close_code)
        with suppress(BaseException):
            self.input_budget.close()
        with suppress(BaseException):
            self.wire.close()
        if (
            handle is not None
            and self._authority_fence_error is None
            and audited
            and all(task.done() for task in self._tasks)
            and not self._cleanup_tasks
            and type(proof) is RuntimeCleanupProof
            and proof.claims == self.claims
            and proof.runtime_epoch == self.context.runtime_epoch
            and proof.connection_id is self.connection
            and proof.result in ("detached", "already_detached")
            and proof.cleanup_state == "ATTACH_PTY_CLOSED"
        ):
            self.lease.request_detach()
            self.lease.acknowledge_cleanup(cleanup_state="ATTACH_PTY_CLOSED", owner=self.owner)
            self.authority.acknowledge_staged_cleanup(
                handle,
                connection_id=self.connection,
                cleanup_state="ATTACH_PTY_CLOSED",
                failure_audited=True,
            )
        if self._authority_fence_error is not None:
            raise self._authority_fence_error

    def _track_cleanup(self, task: asyncio.Task[Any]) -> None:
        self._cleanup_tasks.add(task)

        def completed(value: asyncio.Task[Any]) -> None:
            self._cleanup_tasks.discard(value)
            _consume_result(value)

        task.add_done_callback(completed)


class DurableAdmissionAudit:
    """Persist only R6's closed metadata in the actual database transaction."""

    _capacity = threading.BoundedSemaphore(32)

    def __init__(self, services: ControlPlaneServices, user_id: str) -> None:
        self.services, self.user_id = services, user_id

    async def persist(self, event: AdmissionAuditEvent) -> None:
        if not self._capacity.acquire(blocking=False):
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)

        def operation() -> None:
            try:
                self._persist(event)
            finally:
                self._capacity.release()

        try:
            future = asyncio.get_running_loop().run_in_executor(None, operation)
        except BaseException:
            self._capacity.release()
            raise
        future.add_done_callback(_consume_result)
        await asyncio.shield(future)

    def _persist(self, event: AdmissionAuditEvent) -> None:
        with self.services.database.transaction() as session:
            self.services.audit.record(
                session,
                actor_type="admin",
                actor_id=self.user_id,
                action=event.action.value,
                result="success",
                request_id=None,
                target_type="workspace",
                target_id=event.workspace_id,
                metadata={
                    "attachment_id": event.attachment_id,
                    "generation": str(event.generation),
                    "runtime_epoch": event.runtime_epoch,
                    "api_authority_epoch": str(event.api_authority_epoch),
                    "reason_code": event.reason_code,
                },
            )


class ReadOnlySessionValidator:
    """No authenticate()/last_seen update and no Runtime HOME/Secret access."""

    def __init__(
        self,
        services: ControlPlaneServices,
        settings: Settings,
        control: RuntimeControl,
        policy: WorkspaceAuthorizationPolicy,
        authenticated: AuthenticatedSession,
    ) -> None:
        self.services, self.settings, self.control, self.policy, self.authenticated = (
            services,
            settings,
            control,
            policy,
            authenticated,
        )

    def current(self, claims: AttachmentTuple, context: AuthenticatedAttachmentContext) -> bool:
        return self._current(claims, context, require_running=True)

    def publication_current(
        self, claims: AttachmentTuple, context: AuthenticatedAttachmentContext
    ) -> bool:
        return self._current(claims, context, require_running=False)

    def _current(
        self,
        claims: AttachmentTuple,
        context: AuthenticatedAttachmentContext,
        *,
        require_running: bool,
    ) -> bool:
        try:
            with self.services.database.transaction() as session:
                row = session.get(ControlPlaneSession, context.session_id)
                user = session.get(AdminUser, context.user_id)
                now = self.services.database.transaction_now(session)
                if (
                    row is None
                    or user is None
                    or not user.is_active
                    or row.user_id != context.user_id
                    or row.auth_epoch != context.auth_epoch
                    or row.revoked_at is not None
                    or now
                    >= min(
                        row.expires_at,
                        row.created_at + timedelta(hours=8),
                        row.idle_expires_at,
                        row.last_seen_at + timedelta(minutes=15),
                    )
                    or now < row.last_seen_at
                ):
                    return False
            workspace = self.services.workspaces.get(claims.workspace_id)
            attestation = self.control.attestation
            return bool(
                (not require_running or workspace.state in ("RUNNING", "NEEDS_INTERACTION"))
                and workspace.authorization_scope == context.authorization_scope
                and self.policy.allows(self.authenticated, workspace)
                and attestation is not None
                and attestation.get("runtime_epoch") == context.runtime_epoch
                and all(
                    getattr(workspace, key if key != "workspace_id" else "id") == value
                    for key, value in (
                        ("workspace_id", claims.workspace_id),
                        ("project_id", claims.project_id),
                        ("agent_type", str(claims.agent_type)),
                        ("generation", claims.generation),
                        ("binding_revision", claims.binding_revision),
                        ("binding_digest", claims.binding_digest),
                        ("runtime_host_installation_id", claims.runtime_host_installation_id),
                        (
                            "runtime_host_installation_revision",
                            claims.runtime_host_installation_revision,
                        ),
                    )
                )
            )
        except Exception:
            return False


class WebSocketBrowserPort:
    def __init__(
        self,
        websocket: WebSocket,
        native: WAWWebSocketProtocol,
        first: bytes,
        input_budget: InputBudget,
    ) -> None:
        self.websocket, self.native = websocket, native
        self.first = BrowserDelivery(first)
        self.input_budget = input_budget

    @property
    def transport_open(self) -> bool:
        return self.native.is_open

    async def receive(self) -> BrowserDelivery:
        if self.first.wire_bytes:
            first, self.first = self.first, BrowserDelivery(b"")
            return first
        message = await self.websocket.receive()
        if message["type"] != "websocket.receive":
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        return self.native.claim_received(message)

    async def send_key_frame(self, raw: bytes) -> None:
        if decode_wire_frame(raw, AB).frame_type == F.ADMITTED:
            self.native.message_limit = 65536
        await self.websocket.send_bytes(raw)

    def close(self, code: int) -> None:
        self.native.close(code)

    def abort(self, code: int) -> None:
        self.native.abort(code)

    def install_publication_guard(self, guard: Callable[[bytes], None]) -> None:
        self.native.install_publication_guard(guard)


class FailedAdmissionBudget:
    """Bounded source/Session failure histories; no ticket or cookie keys."""

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = {}

    def check(self, key: str, now: float, *, failed: bool = False) -> None:
        for expired in tuple(self._failures):
            values = self._failures[expired]
            while values and values[0] <= now - 60:
                values.popleft()
            if not values:
                del self._failures[expired]
        if key not in self._failures and len(self._failures) >= 1024:
            raise RelayFailure("CONTROL_RATE_LIMITED", 4429)
        values = self._failures.get(key, deque())
        if len(values) >= 5:
            raise RelayFailure("CONTROL_RATE_LIMITED", 4429)
        if failed:
            values.append(now)
            self._failures[key] = values


class WAWStreamHandler:
    """Explicit opt-in composition. Missing real ports/trust never auto-enable."""

    def __init__(
        self,
        *,
        services: ControlPlaneServices,
        settings: Settings,
        authority: AttachmentAuthority,
        control: RuntimeControl,
        policy: WorkspaceAuthorizationPolicy,
        runtime_factory: Callable[[], AdmissionRuntimePort],
    ) -> None:
        (
            self.services,
            self.settings,
            self.authority,
            self.control,
            self.policy,
            self.runtime_factory,
        ) = (services, settings, authority, control, policy, runtime_factory)
        self.pending = PendingAdmissionBudget()
        self.failures = FailedAdmissionBudget()

    def _authenticate(self, raw: str) -> AuthenticatedSession:
        digest = keyed_digest(self.settings.secret_key.get_secret_value(), "session-token", raw)
        with self.services.database.transaction() as session:
            stored = session.scalar(
                sql_select(ControlPlaneSession).where(ControlPlaneSession.token_hash == digest)
            )
            now = self.services.database.transaction_now(session)
            if (
                stored is None
                or stored.revoked_at is not None
                or not stored.user.is_active
                or now
                >= min(
                    stored.expires_at,
                    stored.idle_expires_at,
                    stored.last_seen_at + timedelta(minutes=15),
                    stored.created_at + timedelta(hours=8),
                )
                or now < stored.last_seen_at
                or not timedelta(0)
                <= now - stored.recent_authenticated_at
                <= timedelta(seconds=self.settings.recent_auth_ttl)
            ):
                raise RelayFailure("ATTACHMENT_STALE", 4401)
            return AuthenticatedSession(
                stored.id,
                stored.user_id,
                stored.user.username,
                stored.expires_at,
                stored.recent_authenticated_at,
                stored.auth_epoch,
                "",
            )

    async def __call__(self, websocket: WebSocket) -> None:
        native = websocket.scope.get("extensions", {}).get(NATIVE_SCOPE_KEY)
        if type(native) is not WAWWebSocketProtocol:
            await websocket.close(code=1013)
            return
        started = time.monotonic_ns()
        source = ""
        session_key = ""
        permit = None
        try:
            peer = ipaddress.ip_address(
                native.peer_address[0] if native.peer_address is not None else "invalid"
            )
            source = peer.compressed
            headers = dict(websocket.scope["headers"])
            origin, host = headers[b"origin"].decode("ascii"), headers[b"host"].decode("ascii")
            _canonical_origin(origin)
            if origin not in self.settings.allowed_origins or urlsplit(origin).netloc != host:
                raise RelayFailure("ATTACHMENT_STALE", 4403)
            peer = ipaddress.ip_address(
                native.peer_address[0] if native.peer_address is not None else "invalid"
            )
            source = peer.compressed
            if (
                (origin.startswith("http:") or not native.tls)
                and not peer.is_loopback
                and not (
                    headers.get(b"x-forwarded-proto") == b"https"
                    and any(
                        peer in ipaddress.ip_network(network)
                        for network in self.settings.trusted_proxies
                    )
                )
            ):
                raise RelayFailure("ATTACHMENT_STALE", 4403)
            # Forwarded identity is accepted only from a configured trusted peer,
            # as one canonical address. Lists and ambiguous forwarding fail.
            forwarded = headers.get(b"x-forwarded-for")
            if forwarded is not None:
                if not any(
                    peer in ipaddress.ip_network(network)
                    for network in self.settings.trusted_proxies
                ):
                    raise RelayFailure("ATTACHMENT_STALE", 4403)
                source = ipaddress.ip_address(forwarded.decode("ascii")).compressed
            self.failures.check("source:" + source, time.monotonic())
            cookies = headers.get(b"cookie", b"").decode("ascii").split(";")
            values = [
                piece.strip().partition("=")[2]
                for piece in cookies
                if piece.strip().partition("=")[0] == "agentbox_session"
            ]
            if len(values) != 1 or not values[0] or len(values[0]) > 128:
                raise RelayFailure("ATTACHMENT_STALE", 4401)
            authenticated = self._authenticate(values[0])
            session_key = "session:" + authenticated.session_id
            self.failures.check(session_key, time.monotonic())
            permit = self.pending.acquire(source)
            await websocket.accept(subprotocol="agentbox-waw-v1")
            async with asyncio.timeout(max(0, 5 - (time.monotonic_ns() - started) / 1e9)):
                first = await websocket.receive_bytes()
            if len(first) > 4120:
                raise RelayFailure("PROTOCOL_INVALID", 1009)
            hello = decode_wire_frame(first, BA, trusted_context=False)
            body = hello.json_payload
            if hello.frame_type != F.WS_HELLO or body is None or hello.hop_sequence != 1:
                raise RelayFailure()
            workspace = self.services.workspaces.get(websocket.path_params["workspace_id"])
            attestation = self.control.attestation
            if attestation is None or not self.policy.allows(authenticated, workspace):
                raise RelayFailure("ATTACHMENT_STALE", 4403)
            claims = AttachmentTuple(
                workspace.id,
                workspace.project_id,
                workspace.agent_type,
                body["attachment_id"],
                int(body["lease_number"]),
                workspace.generation,
                authenticated.auth_epoch,
                self.authority.authority_epoch,
                workspace.runtime_host_installation_id,
                workspace.runtime_host_installation_revision,
                workspace.binding_revision,
                workspace.binding_digest,
            )
            context = AuthenticatedAttachmentContext(
                authenticated.session_id,
                authenticated.user_id,
                workspace.authorization_scope,
                origin,
                str(attestation["runtime_epoch"]),
                authenticated.auth_epoch,
            )
            validator = ReadOnlySessionValidator(
                self.services, self.settings, self.control, self.policy, authenticated
            )
            runtime = self.runtime_factory()
            input_budget = InputBudget(
                connection_id=runtime.connection_id,
                attachment_id=claims.attachment_id,
                runtime_epoch=context.runtime_epoch,
            )
            native.install_input_budget(input_budget)
            browser = WebSocketBrowserPort(websocket, native, first, input_budget)
            audit = DurableAdmissionAudit(self.services, authenticated.user_id)
            # Transfer the already-held pre-upgrade permit without double count.
            self.pending.release(permit)
            permit = None
            coordinator = WAWAdmissionCoordinator(
                authority=self.authority,
                claims=claims,
                context=context,
                runtime=runtime,
                browser=browser,
                audit=audit,
                revalidator=validator,
                budget=self.pending,
                source=source,
                started_at_ns=started,
                input_budget=input_budget,
            )
            await WAWCiphertextRelay(
                coordinator,
                authority=self.authority,
                claims=claims,
                context=context,
                browser=browser,
                runtime=runtime,
                audit=audit,
                revalidator=validator,
                input_budget=input_budget,
            ).run()
        except BaseException as exc:
            for key in ("source:" + source if source else "", session_key):
                if key:
                    with suppress(RelayFailure):
                        self.failures.check(key, time.monotonic(), failed=True)
            native.close(
                exc.close_code
                if isinstance(exc, (RelayFailure, AdmissionFailure))
                else 4408 if isinstance(exc, TimeoutError) else 4400
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            if permit is not None:
                self.pending.release(permit)
