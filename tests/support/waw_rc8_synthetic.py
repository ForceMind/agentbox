"""Software-only rc8 WAW path over real process, socket, and PTY boundaries.

This module is a closed test fixture.  It deliberately does not emulate host
activation: the production Runtime stream client has a fixed ``/run`` path and
pidfd-backed control authority, so an artifact rehearsal needs this temporary
socket adapter until it can run under the artifact-installed host layout.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import fcntl
import hashlib
import importlib
import importlib.metadata
import json
import multiprocessing
import os
import pty
import re
import secrets
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, cast

from agentbox_api.waw_admission import wire_admission_tuple
from agentbox_api.waw_admission_coordinator import (
    AdmissionAuditEvent,
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
from agentbox_api.waw_relay import RelayFailure, WAWCiphertextRelay
from agentbox_core.waw import AgentType, WorkspaceStopOperation, managed_marker, workspace_id
from agentbox_core.waw_tickets import (
    AttachmentAuthority,
    AttachmentTuple,
    AuthenticatedAttachmentContext,
    TicketAuthorityError,
)
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.awce import decode_awce
from agentbox_protocol.waw_crypto_profile import BrowserCryptoProfile
from agentbox_protocol.waw_wire import Leg, decode_wire_frame, encode_wire_frame
from agentbox_runtime.process import ExecutableIdentity
from agentbox_runtime.waw_codex_command import WAWCodexCommand
from agentbox_runtime.waw_command import WAWClaudeCommand
from agentbox_runtime.waw_encrypted_server import WAWEncryptedServer
from agentbox_runtime.waw_encrypted_stream import (
    RuntimePeer,
    WAWEncryptedAttachmentService,
    WAWEncryptedRegistry,
)
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_redraw import BoundedRedraw
from agentbox_runtime.waw_supervisor import (
    RuntimeAttachmentCleanupEvidence,
    RuntimeAttachmentLease,
    RuntimeProbeEvidence,
    RuntimeProbeState,
    RuntimeStartEvidence,
    RuntimeStopEvidence,
    SupervisorState,
    WAWSupervisor,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

BA, AB, AR, RA = tuple(Leg)
PROJECT_ID = "prj_" + "1" * 32
WORKSPACE_ID = workspace_id(PROJECT_ID, AgentType.CLAUDE)
HOST_ID = "wri_" + "3" * 32
BINDING_DIGEST = "a" * 64
RUNTIME_EPOCH = "1"
AUTHORITY_EPOCH = 1
AUTH_EPOCH = 1
GENERATION = 1
ORIGIN = "http://localhost"
_TRUST_DOMAIN = b"agentbox-rc8-synthetic-trust/v1\0"
_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_PUBLIC_FINGERPRINT_PREFIX = b"WAFP"
_PUBLIC_FINGERPRINT_SIZE = 64
_ABWS_HEADER = struct.Struct("!4sBBHIQI")
_CONTROL_HEADER = struct.Struct("!I")
_WINSIZE = struct.Struct("HHHH")
_ARTIFACT_VENV_ENV = "AGENTBOX_RC8_EXPECTED_VENV_ROOT"
_ARTIFACT_VERSION_ENV = "AGENTBOX_RC8_EXPECTED_ARTIFACT_VERSION"
_ARTIFACT_MODULES = (
    "agentbox_api",
    "agentbox_browser_trust",
    "agentbox_cli",
    "agentbox_core",
    "agentbox_helper",
    "agentbox_installer",
    "agentbox_protocol",
    "agentbox_runtime",
    "agentbox_worker",
)
_ECHO_CHILD = """
import os
while True:
    value = os.read(0, 16384)
    if not value:
        break
    os.write(1, b\"PTY:\" + value)
"""


def _verify_artifact_import_origins() -> None:
    """Require every AgentBox import to originate in the artifact venv when requested.

    The source-test invocation leaves the environment variables unset.  The
    artifact rehearsal sets both values before the parent, API child and Runtime
    child have a chance to open a socket, create a key or start a PTY.
    """

    root_value = os.environ.get(_ARTIFACT_VENV_ENV)
    if root_value is None:
        return
    version = os.environ.get(_ARTIFACT_VERSION_ENV)
    root = Path(root_value)
    if (
        not root.is_absolute()
        or not root.exists()
        or root.is_symlink()
        or not root.is_dir()
        or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}(?:rc[0-9]+)?", version or "") is None
    ):
        raise RuntimeError("artifact synthetic import provenance is invalid")
    root = root.resolve()
    if Path(sys.prefix).resolve() != root:
        raise RuntimeError("artifact synthetic import provenance is invalid")
    for name in _ARTIFACT_MODULES:
        module = importlib.import_module(name)
        origin = getattr(getattr(module, "__spec__", None), "origin", None)
        if not isinstance(origin, str) or not Path(origin).resolve().is_relative_to(root):
            raise RuntimeError("artifact synthetic import provenance is invalid")
    distribution = importlib.metadata.distribution("agentbox")
    distribution_root = Path(str(distribution.locate_file(""))).resolve()
    if distribution.version != version or not distribution_root.is_relative_to(root):
        raise RuntimeError("artifact synthetic import provenance is invalid")


def _canonical_trust_record(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: object, *, size: int) -> bytes:
    if type(value) is not str or not value or len(value) > 256:
        raise ValueError("synthetic trust record is invalid")
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("synthetic trust record is invalid") from exc
    if len(decoded) != size:
        raise ValueError("synthetic trust record is invalid")
    return decoded


def _signed_trust_record(key: Ed25519PrivateKey, fingerprint: str) -> dict[str, str | int]:
    body: dict[str, str | int] = {
        "schema_version": 1,
        "origin": ORIGIN,
        "runtime_host_installation_id": HOST_ID,
        "runtime_epoch": RUNTIME_EPOCH,
        "runtime_fingerprint": fingerprint,
        "signature_algorithm": "Ed25519",
    }
    return {**body, "signature": _b64url(key.sign(_TRUST_DOMAIN + _canonical_trust_record(body)))}


def verify_synthetic_trust_record(record: Mapping[str, object], anchor: bytes) -> str:
    expected = {
        "schema_version": 1,
        "origin": ORIGIN,
        "runtime_host_installation_id": HOST_ID,
        "runtime_epoch": RUNTIME_EPOCH,
        "signature_algorithm": "Ed25519",
    }
    if type(record) is not dict or any(
        record.get(name) != value for name, value in expected.items()
    ):
        raise ValueError("synthetic trust record is invalid")
    fingerprint = record.get("runtime_fingerprint")
    if (
        type(fingerprint) is not str
        or len(fingerprint) != 64
        or any(value not in "0123456789abcdef" for value in fingerprint)
    ):
        raise ValueError("synthetic trust record is invalid")
    unsigned = {name: value for name, value in record.items() if name != "signature"}
    try:
        Ed25519PublicKey.from_public_bytes(anchor).verify(
            _b64url_decode(record.get("signature"), size=64),
            _TRUST_DOMAIN + _canonical_trust_record(unsigned),
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("synthetic trust record is invalid") from exc
    return fingerprint


def claims_from_admission(value: Mapping[str, object]) -> AttachmentTuple:
    """Build the exact typed tuple from its canonical wire representation."""

    return AttachmentTuple(
        workspace_id=cast(str, value["workspace_id"]),
        project_id=cast(str, value["project_id"]),
        agent_type=cast(str, value["agent_type"]),
        attachment_id=cast(str, value["attachment_id"]),
        lease_number=int(cast(str, value["lease_number"])),
        generation=int(cast(str, value["generation"])),
        auth_epoch=int(cast(str, value["auth_epoch"])),
        api_authority_epoch=int(cast(str, value["api_authority_epoch"])),
        runtime_host_installation_id=cast(str, value["runtime_host_installation_id"]),
        runtime_host_installation_revision=int(
            cast(str, value["runtime_host_installation_revision"])
        ),
        binding_revision=int(cast(str, value["binding_revision"])),
        binding_digest=cast(str, value["binding_digest"]),
    )


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


async def _read_exact(reader: asyncio.StreamReader, size: int) -> bytes:
    return await reader.readexactly(size)


async def _read_control(reader: asyncio.StreamReader) -> dict[str, Any]:
    (size,) = _CONTROL_HEADER.unpack(await _read_exact(reader, _CONTROL_HEADER.size))
    if not 1 <= size <= 16 * 1024:
        raise ValueError("invalid synthetic control record")
    value = json.loads((await _read_exact(reader, size)).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid synthetic control record")
    return cast(dict[str, Any], value)


async def _write_control(writer: asyncio.StreamWriter, value: Mapping[str, object]) -> None:
    raw = _json_bytes(value)
    writer.write(_CONTROL_HEADER.pack(len(raw)) + raw)
    await writer.drain()


class _ListeningSocket(socket.socket):
    """Use real UDS I/O while supplying Darwin's absent accept-state probe."""

    def getsockopt(self, *args: Any, **kwargs: Any) -> Any:
        if sys.platform == "darwin" and len(args) > 1 and args[1] == socket.SO_ACCEPTCONN:
            return 1
        return super().getsockopt(*args, **kwargs)


class _RealPtyTransport:
    """A fixed echo process with a kernel PTY and a separate attachment fd."""

    def __init__(self, marker: str) -> None:
        self._marker = marker
        self._master = -1
        self._attachment = -1
        self._process: subprocess.Popen[bytes] | None = None
        self._sink: Callable[[bytes], tuple[int, ...]] | None = None
        self._reader: threading.Thread | None = None
        self._reader_stop = threading.Event()
        self._geometry = PtyGeometry(80, 24)
        self._input_count = 0
        self._lock = threading.RLock()

    @property
    def input_count(self) -> int:
        with self._lock:
            return self._input_count

    @property
    def child_pid(self) -> int:
        process = self._process
        return -1 if process is None else process.pid

    def start(
        self, command: WAWClaudeCommand | WAWCodexCommand, geometry: PtyGeometry
    ) -> RuntimeStartEvidence:
        if self._process is not None:
            raise RuntimeError("synthetic PTY already started")
        master, slave = pty.openpty()
        tty.setraw(slave)
        fcntl.ioctl(
            master, termios.TIOCSWINSZ, _WINSIZE.pack(geometry.rows, geometry.columns, 0, 0)
        )
        os.set_blocking(master, False)
        try:
            process = subprocess.Popen(
                (sys.executable, "-u", "-c", _ECHO_CHILD),
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            os.close(slave)
        self._master = master
        self._attachment = os.dup(master)
        os.set_blocking(self._attachment, False)
        self._process = process
        self._geometry = geometry
        return RuntimeStartEvidence(
            command.workspace_id,
            GENERATION,
            command.managed_marker,
            SupervisorState.RUNNING,
            True,
        )

    def bind_output_sink(self, sink: Callable[[bytes], tuple[int, ...]]) -> None:
        if self._sink is not None or self._master < 0:
            raise RuntimeError("synthetic output sink is unavailable")
        self._sink = sink
        self._reader = threading.Thread(target=self._produce, name="waw-rc8-pty", daemon=True)
        self._reader.start()

    def _produce(self) -> None:
        while not self._reader_stop.is_set():
            master = self._master
            if master < 0:
                return
            try:
                readable, _, _ = select.select((master,), (), (), 0.05)
                if not readable:
                    continue
                payload = os.read(master, 64 * 1024)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                return
            if not payload:
                return
            sink = self._sink
            if sink is not None:
                sink(payload)

    def write(self, data: bytes) -> None:
        with self._lock:
            if self._attachment < 0:
                raise OSError("synthetic attachment PTY is closed")
            offset = 0
            while offset < len(data):
                try:
                    written = os.write(self._attachment, data[offset:])
                except BlockingIOError:
                    select.select((), (self._attachment,), (), 0.5)
                    continue
                if written <= 0:
                    raise OSError("synthetic PTY write did not progress")
                offset += written
            self._input_count += 1

    def resize(self, geometry: PtyGeometry) -> None:
        with self._lock:
            if self._attachment < 0:
                raise OSError("synthetic attachment PTY is closed")
            fcntl.ioctl(
                self._attachment,
                termios.TIOCSWINSZ,
                _WINSIZE.pack(geometry.rows, geometry.columns, 0, 0),
            )
            rows, columns, _, _ = _WINSIZE.unpack(
                fcntl.ioctl(self._attachment, termios.TIOCGWINSZ, _WINSIZE.pack(0, 0, 0, 0))
            )
            if (columns, rows) != (geometry.columns, geometry.rows):
                raise OSError("synthetic PTY resize read-back differs")
            self._geometry = PtyGeometry(columns, rows)

    def geometry(self) -> PtyGeometry:
        with self._lock:
            fd = self._attachment if self._attachment >= 0 else self._master
            if fd >= 0:
                rows, columns, _, _ = _WINSIZE.unpack(
                    fcntl.ioctl(fd, termios.TIOCGWINSZ, _WINSIZE.pack(0, 0, 0, 0))
                )
                self._geometry = PtyGeometry(columns, rows)
            return self._geometry

    def capture_redraw(self, _deadline: float) -> BoundedRedraw:
        return BoundedRedraw(b"", False)

    def close_attachment(self, lease: RuntimeAttachmentLease) -> RuntimeAttachmentCleanupEvidence:
        with self._lock:
            closed = self._attachment < 0
            if not closed:
                os.close(self._attachment)
                self._attachment = -1
                closed = True
            return RuntimeAttachmentCleanupEvidence(lease, closed, 0 if closed else 1)

    def detach(self) -> bool:
        with self._lock:
            if self._attachment >= 0:
                os.close(self._attachment)
                self._attachment = -1
            return True

    def probe(self) -> RuntimeProbeEvidence:
        process = self._process
        stopped = process is None or process.poll() is not None
        return RuntimeProbeEvidence(
            WORKSPACE_ID,
            GENERATION,
            self._marker,
            RuntimeProbeState.STOPPED if stopped else RuntimeProbeState.RUNNING,
        )

    def stop(self) -> RuntimeStopEvidence:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        self._reader_stop.set()
        reader = self._reader
        if reader is not None:
            reader.join(timeout=1)
        with self._lock:
            for name in ("_attachment", "_master"):
                fd = cast(int, getattr(self, name))
                if fd >= 0:
                    with contextlib.suppress(OSError):
                        os.close(fd)
                    setattr(self, name, -1)
        closed = process is None or process.poll() is not None
        return RuntimeStopEvidence(
            WORKSPACE_ID,
            GENERATION,
            self._marker,
            closed,
            0 if closed else 1,
        )


def _runtime_objects(root: Path) -> tuple[WAWSupervisor, _RealPtyTransport, WorkspaceStopOperation]:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    executable = root / "claude"
    executable.write_bytes(b"#!/bin/sh\nexit 127\n")
    executable.chmod(0o755)
    details = executable.stat()
    stop = WorkspaceStopOperation(
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        generation=GENERATION,
        binding_revision=1,
        binding_digest=BINDING_DIGEST,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
    )
    marker = managed_marker(
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        project_id=PROJECT_ID,
        agent_type=AgentType.CLAUDE,
        workspace_id_value=WORKSPACE_ID,
        generation=GENERATION,
        binding_revision=1,
        binding_digest=BINDING_DIGEST,
    )
    command = WAWClaudeCommand(
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        cwd=root,
        executable=ExecutableIdentity(
            executable,
            details.st_dev,
            details.st_ino,
            details.st_mode,
            details.st_size,
            details.st_mtime_ns,
        ),
        argv=("remote-control",),
        managed_marker=marker,
    )
    transport = _RealPtyTransport(marker)
    supervisor = WAWSupervisor(
        workspace_id=WORKSPACE_ID,
        generation=GENERATION,
        command=command,
        transport=transport,
        geometry=PtyGeometry(80, 24),
        clock=time.monotonic,
        attachment_validator=lambda _attachment: True,
        stop_binding=stop,
        runtime_epoch=RUNTIME_EPOCH,
    )
    supervisor.start()
    return supervisor, transport, stop


@dataclass
class _RuntimeState:
    supervisor: WAWSupervisor
    transport: _RealPtyTransport
    stop_binding: WorkspaceStopOperation
    registry: WAWEncryptedRegistry
    service: WAWEncryptedAttachmentService
    peer: RuntimePeer
    stop_event: asyncio.Event
    api_connected: bool = False
    prepare_count: int = 0
    detach_count: int = 0


def _request_payload(request: RuntimePrepareRequest | RuntimeCleanupRequest) -> dict[str, object]:
    return {
        "claims": wire_admission_tuple(request.claims),
        "runtime_epoch": request.runtime_epoch,
        "resume_cursor": getattr(request, "resume_cursor", None),
        "previous_runtime_epoch": getattr(request, "previous_runtime_epoch", None),
    }


async def _runtime_control_request(state: _RuntimeState, request: dict[str, Any]) -> dict[str, Any]:
    operation = request.get("operation")
    if operation in {"prepare", "detach"}:
        claims = claims_from_admission(cast(Mapping[str, object], request["claims"]))
        common: dict[str, Any] = {
            "protocol_version": 1,
            **wire_admission_tuple(claims),
            "runtime_epoch": request["runtime_epoch"],
            "request_id": request["request_id"],
        }
        if operation == "prepare":
            state.prepare_count += 1
            common.update(
                action="workspace.attach.prepare",
                resume_cursor=request.get("resume_cursor"),
                previous_runtime_epoch=request.get("previous_runtime_epoch"),
            )
            return state.service.prepare(common, state.peer)
        state.detach_count += 1
        common["action"] = "workspace.attach.detach"
        return state.service.detach(common, state.peer)
    if operation == "status":
        geometry = state.transport.geometry()
        return {
            "status": "OK",
            "runtime_pid": os.getpid(),
            "child_pid": state.transport.child_pid,
            "geometry": [geometry.columns, geometry.rows],
            "input_count": state.transport.input_count,
            "registry_count": state.registry.count,
            "prepare_count": state.prepare_count,
            "detach_count": state.detach_count,
            "state": state.supervisor.state.value,
        }
    if operation == "stop":
        if request.get("generation") != GENERATION:
            raise ValueError("stale synthetic Stop generation")
        before = await _runtime_control_request(state, {"operation": "status"})
        snapshot = state.supervisor.exact_stop(state.stop_binding)
        return {
            **before,
            "status": "STOPPED",
            "state": snapshot.state.value,
            "child_stopped": state.transport.probe().state is RuntimeProbeState.STOPPED,
            "registry_count": state.registry.count,
        }
    if operation == "shutdown":
        state.registry.invalidate()
        if state.supervisor.state is not SupervisorState.STOPPED:
            state.supervisor.exact_stop(state.stop_binding)
        evidence = await _runtime_control_request(state, {"operation": "status"})
        state.stop_event.set()
        return {**evidence, "status": "SHUTDOWN"}
    raise ValueError("unsupported synthetic control operation")


async def _runtime_main(
    root: Path,
    control_path: Path,
    stream_path: Path,
    static_private_key: bytes,
) -> None:
    supervisor, transport, stop_binding = _runtime_objects(root)
    registry = WAWEncryptedRegistry(
        runtime_epoch=RUNTIME_EPOCH,
        static_key=lambda: static_private_key,
    )
    stop_event = asyncio.Event()
    identity = object()
    # Construction is an internal Runtime composition step.  The flag becomes
    # the actual control-connection lifetime before any prepare/open request.
    connected = [True]
    peer = RuntimePeer(identity, str(AUTHORITY_EPOCH), lambda: connected[0])
    service = WAWEncryptedAttachmentService(
        registry,
        peer=lambda: peer,
        supervisor=lambda _claims: supervisor,
        current=lambda _claims: (
            supervisor.state in {SupervisorState.RUNNING, SupervisorState.DETACHED}
        ),
    )
    service.bind_authority(
        {"api_authority_epoch": str(AUTHORITY_EPOCH), "authority_nonce": "d" * 32}, peer
    )
    connected[0] = False
    state = _RuntimeState(supervisor, transport, stop_binding, registry, service, peer, stop_event)

    async def control_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if state.api_connected:
            writer.close()
            return
        state.api_connected = True
        connected[0] = True
        try:
            while not reader.at_eof():
                request = await _read_control(reader)
                try:
                    response = await _runtime_control_request(state, request)
                except Exception as exc:
                    response = {"status": "ERROR", "error_type": type(exc).__name__}
                await _write_control(writer, response)
                if request.get("operation") == "shutdown":
                    break
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            state.api_connected = False
            connected[0] = False
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    for path in (control_path, stream_path):
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    control = await asyncio.start_unix_server(control_client, path=str(control_path))
    stream_socket = _ListeningSocket(socket.AF_UNIX, socket.SOCK_STREAM)
    stream_socket.set_inheritable(False)
    stream_socket.bind(str(stream_path))
    stream_socket.listen(64)
    encrypted = WAWEncryptedServer(stream_socket, registry, peer_verifier=lambda _socket: peer)
    await encrypted.start()
    try:
        await stop_event.wait()
    finally:
        control.close()
        await control.wait_closed()
        await encrypted.close()
        if supervisor.state is not SupervisorState.STOPPED:
            with contextlib.suppress(Exception):
                supervisor.exact_stop(stop_binding)
        for path in (control_path, stream_path):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


def _record_child_failure(root: Path, role: str, exc: BaseException) -> None:
    (root / f"{role}.error").write_text(
        json.dumps({"type": type(exc).__name__, "message": str(exc)}), encoding="utf-8"
    )


def _runtime_entry(
    root_raw: str,
    control_raw: str,
    stream_raw: str,
    public_channel: socket.socket,
) -> None:
    _verify_artifact_import_origins()
    root, control, stream = Path(root_raw), Path(control_raw), Path(stream_raw)
    try:
        private_key = X25519PrivateKey.generate()
        static_private_key = private_key.private_bytes_raw()
        fingerprint = hashlib.sha256(private_key.public_key().public_bytes_raw()).hexdigest()
        del private_key
        public_channel.sendall(_PUBLIC_FINGERPRINT_PREFIX + fingerprint.encode("ascii"))
        public_channel.shutdown(socket.SHUT_WR)
        asyncio.run(_runtime_main(root, control, stream, static_private_key))
    except BaseException as exc:
        _record_child_failure(root, "runtime", exc)
        raise
    finally:
        public_channel.close()


class _ControlChannel:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(str(self._path))

    async def request(self, operation: str, **fields: object) -> dict[str, Any]:
        async with self._lock:
            if self._reader is None or self._writer is None:
                raise RuntimeError("synthetic Runtime control is not connected")
            await _write_control(self._writer, {"operation": operation, **fields})
            response = await _read_control(self._reader)
            if response.get("status") == "ERROR":
                raise RuntimeError("synthetic Runtime control rejected the fixed operation")
            return response

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()


class _UnixRuntimePort:
    """Temporary-path equivalent of the production closed UnixRuntimePort."""

    def __init__(self, control: _ControlChannel, stream_path: Path) -> None:
        self._control = control
        self._stream_path = stream_path
        self._connection = object()
        self._socket: socket.socket | None = None
        self._request: RuntimePrepareRequest | None = None
        self._aborted = False
        self._send_guard: Callable[[bytes], None] | None = None

    @property
    def connection_id(self) -> object:
        return self._connection

    async def prepare(self, request: RuntimePrepareRequest) -> RuntimePrepared:
        if self._request is not None or request.connection_id is not self._connection:
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        self._request = request
        response = await self._control.request(
            "prepare",
            **_request_payload(request),
            request_id="wreq_" + secrets.token_hex(16),
        )
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        peer.setblocking(False)
        await asyncio.get_running_loop().sock_connect(peer, str(self._stream_path))
        self._socket = peer
        capability = response.get("capability")
        if response.get("status") != "PREPARED" or not isinstance(capability, str):
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        return RuntimePrepared(request.claims, request.runtime_epoch, self._connection, capability)

    def install_send_guard(self, guard: Callable[[bytes], None]) -> None:
        self._send_guard = guard

    async def send(self, frame: bytes) -> None:
        decode_wire_frame(frame, AR)
        peer = self._socket
        if peer is None or self._aborted:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        offset = 0
        while offset < len(frame):
            if self._send_guard is not None:
                self._send_guard(frame)
            try:
                sent = peer.send(memoryview(frame)[offset:])
            except BlockingIOError:
                await asyncio.sleep(0)
                continue
            if sent <= 0:
                raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
            offset += sent

    async def _socket_exact(self, size: int) -> bytes:
        peer = self._socket
        if peer is None:
            raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
        result = bytearray()
        while len(result) < size:
            part = await asyncio.get_running_loop().sock_recv(peer, size - len(result))
            if not part:
                raise RelayFailure("RUNTIME_UNAVAILABLE", 1013)
            result.extend(part)
        return bytes(result)

    async def receive(self) -> bytes:
        header = await self._socket_exact(_ABWS_HEADER.size)
        magic, version, _kind, flags, size, sequence, reserved = _ABWS_HEADER.unpack(header)
        if magic != b"ABWS" or version != 1 or flags or not sequence or reserved or size > 65536:
            raise RelayFailure()
        return header + await self._socket_exact(size)

    async def close_and_cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupProof:
        if self._request is None or request.connection_id is not self._connection:
            raise RelayFailure("ATTACHMENT_STALE", 4403)
        response = await self._control.request(
            "detach",
            **_request_payload(request),
            request_id="wreq_" + secrets.token_hex(16),
        )
        self.abort()
        return RuntimeCleanupProof(
            request.claims,
            request.runtime_epoch,
            self._connection,
            str(response["status"]).lower(),
            cast(str, response["cleanup_state"]),
        )

    def abort(self) -> None:
        self._aborted = True
        if self._socket is not None:
            self._socket.close()
            self._socket = None


class _SocketBrowserPort:
    """RFC6455 server-side peer used by the production admission and relay code."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader, self._writer = reader, writer
        self._budget: InputBudget | None = None
        self._open = True
        self._guard: Callable[[bytes], None] | None = None

    @property
    def transport_open(self) -> bool:
        return self._open and not self._writer.is_closing()

    def install_input_budget(self, budget: InputBudget) -> None:
        self._budget = budget

    def install_publication_guard(self, guard: Callable[[bytes], None]) -> None:
        self._guard = guard

    async def receive(self) -> BrowserDelivery:
        opcode, raw = await _read_ws_frame(self._reader, client=True)
        if opcode != 2:
            raise RelayFailure()
        token = None
        if is_encoded_input(raw):
            if self._budget is None:
                raise RelayFailure()
            token = self._budget.reserve_native(len(raw))
            self._budget.transfer(
                token,
                source=InputBudgetOwner.NATIVE_READY,
                target=InputBudgetOwner.BROWSER_DELIVERY,
            )
        return BrowserDelivery(raw, token)

    async def send_key_frame(self, raw: bytes) -> None:
        if self._guard is not None:
            self._guard(raw)
        self._writer.write(_ws_frame(raw, opcode=2, masked=False))
        await self._writer.drain()

    def close(self, code: int) -> None:
        if self._open:
            self._writer.write(_ws_frame(code.to_bytes(2, "big"), opcode=8, masked=False))
        self._open = False
        self._writer.close()

    def abort(self, code: int) -> None:
        self.close(code)


class _Audit:
    def __init__(self) -> None:
        self.prepared = 0
        self.admitted = 0
        self.detached = 0

    async def persist(self, event: AdmissionAuditEvent) -> None:
        name = event.action.value
        if name.endswith("prepared"):
            self.prepared += 1
        elif name.endswith("admitted"):
            self.admitted += 1
        elif name.endswith("detached"):
            self.detached += 1
        await asyncio.sleep(0)


class _Validator:
    current_value = True

    def current(self, _claims: AttachmentTuple, _context: AuthenticatedAttachmentContext) -> bool:
        return self.current_value

    publication_current = current


def _ws_frame(payload: bytes, *, opcode: int, masked: bool) -> bytes:
    first = 0x80 | opcode
    size = len(payload)
    mask_flag = 0x80 if masked else 0
    if size < 126:
        header = bytes((first, mask_flag | size))
    elif size <= 0xFFFF:
        header = bytes((first, mask_flag | 126)) + size.to_bytes(2, "big")
    else:
        header = bytes((first, mask_flag | 127)) + size.to_bytes(8, "big")
    if not masked:
        return header + payload
    mask = secrets.token_bytes(4)
    encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return header + mask + encoded


async def _read_ws_frame(reader: asyncio.StreamReader, *, client: bool) -> tuple[int, bytes]:
    first, second = await _read_exact(reader, 2)
    if not first & 0x80:
        raise ValueError("fragmented synthetic RFC6455 frame")
    masked = bool(second & 0x80)
    if masked is not client:
        raise ValueError("invalid synthetic RFC6455 masking")
    size = second & 0x7F
    if size == 126:
        size = int.from_bytes(await _read_exact(reader, 2), "big")
    elif size == 127:
        size = int.from_bytes(await _read_exact(reader, 8), "big")
    if size > 65536:
        raise ValueError("oversized synthetic RFC6455 frame")
    mask = await _read_exact(reader, 4) if masked else b""
    payload = await _read_exact(reader, size)
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return first & 0x0F, payload


async def _read_http_request(
    reader: asyncio.StreamReader,
) -> tuple[str, str, dict[str, str], bytes]:
    header = await reader.readuntil(b"\r\n\r\n")
    if len(header) > 8192:
        raise ValueError("oversized synthetic HTTP request")
    lines = header[:-4].split(b"\r\n")
    method_raw, path_raw, version = lines[0].split(b" ")
    if version != b"HTTP/1.1":
        raise ValueError("invalid synthetic HTTP version")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator:
            raise ValueError("invalid synthetic HTTP header")
        headers[name.decode("ascii").lower()] = value.strip().decode("ascii")
    size = int(headers.get("content-length", "0"))
    if not 0 <= size <= 4096:
        raise ValueError("invalid synthetic HTTP body")
    return (
        method_raw.decode("ascii"),
        path_raw.decode("ascii"),
        headers,
        await _read_exact(reader, size),
    )


async def _http_response(
    writer: asyncio.StreamWriter, status: int, value: Mapping[str, object]
) -> None:
    raw = _json_bytes(value)
    reason = {200: "OK", 409: "Conflict"}.get(status, "Bad Request")
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(raw)}\r\nConnection: close\r\n\r\n".encode("ascii")
        + raw
    )
    await writer.drain()


@dataclass
class _ApiState:
    authority: AttachmentAuthority
    context: AuthenticatedAttachmentContext
    control: _ControlChannel
    stream_path: Path
    stop_event: asyncio.Event
    audit: _Audit
    runtime_fingerprint: str
    trust_record: dict[str, str | int]
    issued: Any = None

    def issue(self) -> Any:
        if self.issued is not None:
            raise RuntimeError("synthetic Start already issued its one ticket")
        self.issued = self.authority.issue(
            workspace_id=WORKSPACE_ID,
            project_id=PROJECT_ID,
            agent_type=AgentType.CLAUDE,
            attachment_id="att_" + "2" * 32,
            generation=GENERATION,
            auth_epoch=AUTH_EPOCH,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision=1,
            binding_revision=1,
            binding_digest=BINDING_DIGEST,
            origin=ORIGIN,
            context=self.context,
        )
        return self.issued


async def _accept_websocket(
    state: _ApiState,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    headers: Mapping[str, str],
) -> None:
    key = headers.get("sec-websocket-key")
    if (
        headers.get("upgrade", "").lower() != "websocket"
        or "upgrade" not in headers.get("connection", "").lower()
        or headers.get("sec-websocket-version") != "13"
        or headers.get("sec-websocket-protocol") != "agentbox-waw-v1"
        or key is None
    ):
        await _http_response(writer, 400, {"error": "invalid websocket upgrade"})
        return
    accept = base64.b64encode(hashlib.sha1(key.encode("ascii") + _WS_GUID).digest()).decode("ascii")
    writer.write(
        (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "Sec-WebSocket-Protocol: agentbox-waw-v1\r\n\r\n"
        ).encode("ascii")
    )
    await writer.drain()
    if state.issued is None:
        writer.close()
        return
    claims = state.issued.claims
    runtime = _UnixRuntimePort(state.control, state.stream_path)
    browser = _SocketBrowserPort(reader, writer)
    budget = InputBudget(
        connection_id=runtime.connection_id,
        attachment_id=claims.attachment_id,
        runtime_epoch=RUNTIME_EPOCH,
    )
    browser.install_input_budget(budget)
    audit, validator = state.audit, _Validator()
    coordinator = WAWAdmissionCoordinator(
        authority=state.authority,
        claims=claims,
        context=state.context,
        runtime=runtime,
        browser=browser,
        audit=audit,
        revalidator=validator,
        budget=PendingAdmissionBudget(),
        source="127.0.0.1",
        started_at_ns=time.monotonic_ns(),
        input_budget=budget,
    )
    relay = WAWCiphertextRelay(
        coordinator,
        authority=state.authority,
        claims=claims,
        context=state.context,
        browser=browser,
        runtime=runtime,
        audit=audit,
        revalidator=validator,
        input_budget=budget,
    )
    await relay.run()


async def _api_main(
    listener: socket.socket,
    root: Path,
    control_path: Path,
    stream_path: Path,
    runtime_fingerprint: str,
    trust_record: dict[str, str | int],
) -> None:
    control = _ControlChannel(control_path)
    deadline = time.monotonic() + 5
    while True:
        try:
            await control.connect()
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.01)
    authority = AttachmentAuthority(
        clock=time.monotonic,
        authority_epoch=AUTHORITY_EPOCH,
        lease_seed=1,
    )
    context = AuthenticatedAttachmentContext(
        "synthetic-session", "synthetic-admin", "waw", ORIGIN, RUNTIME_EPOCH, AUTH_EPOCH
    )
    stop_event = asyncio.Event()
    state = _ApiState(
        authority,
        context,
        control,
        stream_path,
        stop_event,
        audit=_Audit(),
        runtime_fingerprint=runtime_fingerprint,
        trust_record=trust_record,
    )

    async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            method, path, headers, body = await _read_http_request(reader)
            if method == "GET" and path == "/v1/workspaces/synthetic/stream":
                await _accept_websocket(state, reader, writer, headers)
                return
            if method == "GET" and path == "/synthetic/ready":
                await _http_response(writer, 200, {"ready": True})
                return
            if method == "POST" and path == "/v1/workspaces/synthetic/start":
                try:
                    issued = state.issue()
                except (RuntimeError, TicketAuthorityError):
                    await _http_response(writer, 409, {"error": "ATTACHMENT_STALE"})
                    return
                await _http_response(
                    writer,
                    200,
                    {
                        "ticket": issued.ticket,
                        "admission": wire_admission_tuple(issued.claims),
                        "runtime_epoch": RUNTIME_EPOCH,
                        "runtime_fingerprint": state.runtime_fingerprint,
                        "trust_record": state.trust_record,
                        "api_pid": os.getpid(),
                    },
                )
                return
            if method == "POST" and path == "/v1/workspaces/synthetic/stop":
                request = json.loads(body or b"{}")
                response = await control.request("stop", generation=request.get("generation"))
                response["api_pid"] = os.getpid()
                await _http_response(writer, 200, response)
                return
            if method == "POST" and path == "/synthetic/shutdown":
                authority.begin_shutdown()
                issuance_fenced = False
                try:
                    authority.issue(
                        workspace_id=WORKSPACE_ID,
                        project_id=PROJECT_ID,
                        agent_type=AgentType.CLAUDE,
                        attachment_id="att_" + "9" * 32,
                        generation=2,
                        auth_epoch=AUTH_EPOCH,
                        runtime_host_installation_id=HOST_ID,
                        runtime_host_installation_revision=1,
                        binding_revision=1,
                        binding_digest=BINDING_DIGEST,
                        context=context,
                    )
                except TicketAuthorityError:
                    issuance_fenced = True
                runtime = await control.request("shutdown")
                await _http_response(
                    writer,
                    200,
                    {
                        "issuance_fenced": issuance_fenced,
                        "authority_clean": authority.shutdown_clean,
                        "runtime": runtime,
                        "audit": {
                            "prepared": state.audit.prepared,
                            "admitted": state.audit.admitted,
                            "detached": state.audit.detached,
                        },
                    },
                )
                stop_event.set()
                return
            await _http_response(writer, 400, {"error": "unsupported synthetic request"})
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except Exception as exc:
            _record_child_failure(root, "api-client", exc)
            with contextlib.suppress(Exception):
                await _http_response(writer, 400, {"error_type": type(exc).__name__})
        finally:
            if not writer.is_closing():
                writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    listener.setblocking(False)
    server = await asyncio.start_server(client, sock=listener)
    try:
        await stop_event.wait()
    finally:
        server.close()
        await server.wait_closed()
        await control.close()


def _receive_runtime_fingerprint(public_channel: socket.socket) -> str:
    public_channel.settimeout(5)
    expected = len(_PUBLIC_FINGERPRINT_PREFIX) + _PUBLIC_FINGERPRINT_SIZE
    raw = bytearray()
    while len(raw) < expected:
        chunk = public_channel.recv(expected - len(raw))
        if not chunk:
            raise RuntimeError("Runtime public startup channel ended early")
        raw.extend(chunk)
    if public_channel.recv(1) != b"":
        raise RuntimeError("Runtime public startup channel exceeded its fixed record")
    prefix, fingerprint_raw = bytes(raw[:4]), bytes(raw[4:])
    if prefix != _PUBLIC_FINGERPRINT_PREFIX:
        raise RuntimeError("Runtime public startup record has the wrong type")
    fingerprint = fingerprint_raw.decode("ascii")
    if len(fingerprint) != 64 or any(value not in "0123456789abcdef" for value in fingerprint):
        raise RuntimeError("Runtime public fingerprint is malformed")
    return fingerprint


def _api_entry(
    listener: socket.socket,
    root_raw: str,
    control_raw: str,
    stream_raw: str,
    runtime_fingerprint: str,
    trust_record: dict[str, str | int],
) -> None:
    _verify_artifact_import_origins()
    root, control, stream = Path(root_raw), Path(control_raw), Path(stream_raw)
    try:
        asyncio.run(_api_main(listener, root, control, stream, runtime_fingerprint, trust_record))
    except BaseException as exc:
        _record_child_failure(root, "api", exc)
        raise


def _socket_http_json(
    host: str, port: int, method: str, path: str, value: Mapping[str, object] | None = None
) -> tuple[int, dict[str, Any]]:
    body = b"" if value is None else _json_bytes(value)
    request = (
        f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode("ascii") + body
    with socket.create_connection((host, port), timeout=5) as peer:
        peer.sendall(request)
        stream = peer.makefile("rb")
        status = int(stream.readline().split()[1])
        headers: dict[bytes, bytes] = {}
        while (line := stream.readline()) != b"\r\n":
            name, _, item = line.partition(b":")
            headers[name.lower()] = item.strip()
        payload = stream.read(int(headers[b"content-length"]))
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("invalid synthetic HTTP response")
    return status, cast(dict[str, Any], result)


class RawRFC6455Peer:
    """A raw TCP browser peer; all client frames are RFC6455-masked."""

    def __init__(self, host: str, port: int) -> None:
        self._socket = socket.create_connection((host, port), timeout=5)
        self._stream = self._socket.makefile("rb")
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        self._socket.sendall(
            (
                "GET /v1/workspaces/synthetic/stream HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Protocol: agentbox-waw-v1\r\n\r\n"
            ).encode("ascii")
        )
        response = self._stream.readline()
        if b" 101 " not in response:
            raise RuntimeError(f"synthetic WebSocket upgrade failed: {response!r}")
        headers: dict[bytes, bytes] = {}
        while (line := self._stream.readline()) != b"\r\n":
            name, separator, value = line.partition(b":")
            if not separator or name.lower() in headers:
                raise RuntimeError("synthetic WebSocket upgrade headers are invalid")
            headers[name.lower()] = value.strip()
        expected_accept = base64.b64encode(
            hashlib.sha1(  # noqa: S324 - RFC6455 mandates SHA-1 for this handshake.
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        )
        if (
            headers.get(b"sec-websocket-accept") != expected_accept
            or headers.get(b"sec-websocket-protocol") != b"agentbox-waw-v1"
        ):
            raise RuntimeError("synthetic WebSocket upgrade negotiation is invalid")

    def send(self, raw: bytes) -> None:
        self._socket.sendall(_ws_frame(raw, opcode=2, masked=True))

    def receive(self) -> tuple[int, bytes]:
        first = self._stream.read(2)
        if len(first) != 2:
            raise EOFError("synthetic WebSocket closed")
        first_byte, second = first
        if second & 0x80:
            raise ValueError("server RFC6455 frame was masked")
        size = second & 0x7F
        if size == 126:
            size = int.from_bytes(self._stream.read(2), "big")
        elif size == 127:
            size = int.from_bytes(self._stream.read(8), "big")
        return first_byte & 0x0F, self._stream.read(size)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._socket.sendall(_ws_frame((1000).to_bytes(2, "big"), opcode=8, masked=True))
        self._stream.close()
        self._socket.close()

    def __enter__(self) -> RawRFC6455Peer:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@dataclass
class SyntheticWAWCluster:
    root: Path
    host: str
    port: int
    runtime: BaseProcess
    api: BaseProcess
    trust_anchor: bytes

    def http(
        self, method: str, path: str, value: Mapping[str, object] | None = None
    ) -> tuple[int, dict[str, Any]]:
        return _socket_http_json(self.host, self.port, method, path, value)

    def browser(self) -> RawRFC6455Peer:
        return RawRFC6455Peer(self.host, self.port)

    def assert_children_clean(self) -> None:
        self.api.join(timeout=5)
        self.runtime.join(timeout=5)
        if self.api.is_alive() or self.runtime.is_alive():
            raise AssertionError("synthetic WAW child did not stop cleanly")
        if self.api.exitcode != 0 or self.runtime.exitcode != 0:
            errors = {
                path.name: path.read_text(encoding="utf-8") for path in self.root.glob("*.error")
            }
            raise AssertionError(
                f"synthetic WAW child failed: api={self.api.exitcode}, "
                f"runtime={self.runtime.exitcode}, errors={errors}"
            )


def loopback_bind_permitted() -> bool:
    """Whether this test host permits the real TCP prerequisite for the fixture."""

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
    except PermissionError:
        return False
    finally:
        listener.close()
    return True


@contextmanager
def synthetic_waw_cluster(tmp_path: Path) -> Iterator[SyntheticWAWCluster]:
    """Start separate API/Runtime processes without queues or shared-memory outcomes."""

    del tmp_path
    root = Path(tempfile.mkdtemp(prefix=".waw-rc8-", dir=Path.cwd()))
    root.chmod(0o700)
    control_path, stream_path = root / "c.sock", root / "s.sock"
    context = multiprocessing.get_context("spawn")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    host, port = cast(tuple[str, int], listener.getsockname())
    signer = Ed25519PrivateKey.generate()
    trust_anchor = signer.public_key().public_bytes_raw()
    runtime_public, parent_public = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    runtime = context.Process(
        target=_runtime_entry,
        args=(str(root), str(control_path), str(stream_path), runtime_public),
        name="waw-rc8-runtime",
    )
    runtime.start()
    runtime_public.close()
    runtime_fingerprint = _receive_runtime_fingerprint(parent_public)
    parent_public.close()
    trust_record = _signed_trust_record(signer, runtime_fingerprint)
    api = context.Process(
        target=_api_entry,
        args=(
            listener,
            str(root),
            str(control_path),
            str(stream_path),
            runtime_fingerprint,
            trust_record,
        ),
        name="waw-rc8-api",
    )
    deadline = time.monotonic() + 5
    while not control_path.exists() or not stream_path.exists():
        if not runtime.is_alive():
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    api.start()
    listener.close()
    cluster = SyntheticWAWCluster(root, host, port, runtime, api, trust_anchor)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                status, ready = cluster.http("GET", "/synthetic/ready")
                if status != 200 or ready != {"ready": True}:
                    raise RuntimeError("synthetic API readiness response is invalid")
                break
            except OSError as exc:
                if time.monotonic() >= deadline or not api.is_alive():
                    raise RuntimeError("synthetic API did not become ready") from exc
                time.sleep(0.01)
        yield cluster
    finally:
        if api.is_alive():
            with contextlib.suppress(Exception):
                cluster.http("POST", "/synthetic/shutdown")
        for child in (api, runtime):
            child.join(timeout=5)
            if child.is_alive():
                child.terminate()
                child.join(timeout=2)
        shutil.rmtree(root, ignore_errors=True)


def run_synthetic_path(
    tmp_path: Path,
    *,
    plaintext: bytes = b"synthetic-rc8-input\n",
    browser_ephemeral_private_key: bytes | None = None,
) -> str:
    """Exercise the closed API/Runtime/browser/PTY path without pytest.

    The callable is shared by the source test and the manifest-hashed artifact
    rehearsal runner.  Caller-provided values are test-only inputs: the normal
    source test keeps its stable payload, while the rc8 workflow later supplies
    per-run canaries without adding a production switch.
    """

    _verify_artifact_import_origins()
    if not loopback_bind_permitted():
        raise RuntimeError("required rc8 loopback socket bind is unavailable")
    if type(plaintext) is not bytes or not 1 <= len(plaintext) <= 16_384:
        raise ValueError("synthetic plaintext is invalid")
    if browser_ephemeral_private_key is not None and (
        type(browser_ephemeral_private_key) is not bytes or len(browser_ephemeral_private_key) != 32
    ):
        raise ValueError("synthetic browser private key is invalid")
    expected_output = b"PTY:" + plaintext

    with synthetic_waw_cluster(tmp_path) as cluster:
        status, started = cluster.http("POST", "/v1/workspaces/synthetic/start")
        if status != 200:
            raise RuntimeError("synthetic Start did not succeed")
        admission = started["admission"]
        if not isinstance(admission, dict):
            raise RuntimeError("synthetic admission is invalid")
        claims = claims_from_admission(admission)
        if wire_admission_tuple(claims) != admission:
            raise RuntimeError("synthetic admission tuple changed")
        ticket = started.get("ticket")
        if not isinstance(ticket, str) or not ticket.startswith("wat_"):
            raise RuntimeError("synthetic ticket is invalid")
        trust_record = started.get("trust_record")
        if not isinstance(trust_record, dict):
            raise RuntimeError("synthetic trust record is invalid")
        trusted_fingerprint = verify_synthetic_trust_record(trust_record, cluster.trust_anchor)
        tampered_trust = {**trust_record, "runtime_fingerprint": "0" * 64}
        try:
            verify_synthetic_trust_record(tampered_trust, cluster.trust_anchor)
        except ValueError:
            pass
        else:
            raise RuntimeError("synthetic trust tampering was accepted")
        if trusted_fingerprint != started.get("runtime_fingerprint"):
            raise RuntimeError("synthetic trust fingerprint differs")

        crypto = BrowserCryptoProfile(
            admission,
            RUNTIME_EPOCH,
            trusted_fingerprint,
            ephemeral_private_key=browser_ephemeral_private_key,
        )
        with cluster.browser() as browser:
            browser.send(
                browser_frame(
                    F.WS_HELLO,
                    {
                        "protocol_version": 1,
                        **admission,
                        "runtime_epoch": RUNTIME_EPOCH,
                        "ticket": ticket,
                        "resume_cursor": None,
                        "previous_runtime_epoch": None,
                    },
                    1,
                )
            )
            browser.send(browser_frame(F.KEY_INIT, crypto.start(), 2))

            opcode, raw = browser.receive()
            attest = decode_wire_frame(raw, AB)
            if opcode != 2 or attest.frame_type is not F.KEY_ATTEST or attest.json_payload is None:
                raise RuntimeError("synthetic key attest is invalid")
            if (
                attest.json_payload["runtime_attestation_x25519_fingerprint"]
                != started["runtime_fingerprint"]
            ):
                raise RuntimeError("synthetic key attest differs")
            browser.send(
                browser_frame(F.KEY_CONFIRM, crypto.receive_attest(attest.json_payload), 3)
            )
            opcode, raw = browser.receive()
            confirmed = decode_wire_frame(raw, AB)
            if opcode != 2 or confirmed.frame_type is not F.KEY_CONFIRM_ACK:
                raise RuntimeError("synthetic key confirmation is invalid")
            crypto.receive_ack(confirmed.json_payload)

            opcode, raw = browser.receive()
            admitted = decode_wire_frame(raw, AB)
            if (
                opcode != 2
                or admitted.frame_type is not F.ADMITTED
                or admitted.json_payload is None
                or admitted.json_payload.get("state") != "RUNNING"
            ):
                raise RuntimeError("synthetic admission was not published")

            browser.send(browser_frame(F.INPUT, crypto.encrypt_input(plaintext), 4))
            accepted = False
            written = False
            output = bytearray()
            while not (accepted and written and expected_output in output):
                opcode, raw = browser.receive()
                if opcode != 2:
                    raise RuntimeError("synthetic browser frame is invalid")
                frame = decode_wire_frame(raw, AB)
                if frame.frame_type is F.ACK:
                    if frame.json_payload is None:
                        raise RuntimeError("synthetic input ACK is invalid")
                    accepted |= frame.json_payload["result"] == "accepted"
                    written |= frame.json_payload["result"] == "written_to_pty"
                elif frame.frame_type is F.OUTPUT:
                    envelope = decode_awce(frame.payload)
                    output.extend(
                        crypto.decrypt_output(
                            frame.payload,
                            expected_cursor=envelope.stream_cursor,
                        )
                    )
            if output.count(expected_output) != 1:
                raise RuntimeError("synthetic PTY output is not exact")

            browser.send(
                browser_frame(
                    F.RESIZE,
                    {
                        "protocol_version": 1,
                        "attachment_id": claims.attachment_id,
                        "lease_number": str(claims.lease_number),
                        "columns": 100,
                        "rows": 40,
                    },
                    5,
                )
            )
            opcode, raw = browser.receive()
            resized = decode_wire_frame(raw, AB)
            if (
                opcode != 2
                or resized.frame_type is not F.RESIZE_ACK
                or resized.json_payload is None
                or resized.json_payload.get("result") != "applied"
                or (
                    resized.json_payload.get("effective_columns"),
                    resized.json_payload.get("effective_rows"),
                )
                != (100, 40)
            ):
                raise RuntimeError("synthetic resize read-back is invalid")

            browser.send(
                browser_frame(
                    F.DETACH,
                    {
                        "protocol_version": 1,
                        "attachment_id": claims.attachment_id,
                        "lease_number": str(claims.lease_number),
                    },
                    6,
                )
            )
            detached: dict[str, Any] | None = None
            closed = False
            while detached is None or not closed:
                opcode, raw = browser.receive()
                if opcode != 2:
                    raise RuntimeError("synthetic detach frame is invalid")
                frame = decode_wire_frame(raw, AB)
                if frame.frame_type is F.DETACH_ACK:
                    detached = frame.json_payload
                elif frame.frame_type is F.CLOSE:
                    closed = True
            if (
                detached is None
                or detached.get("result") != "detached"
                or detached.get("cleanup_state") != "ATTACH_PTY_CLOSED"
                or detached.get("reason_code") is not None
            ):
                raise RuntimeError("synthetic detach evidence is invalid")

        status, stopped = cluster.http(
            "POST", "/v1/workspaces/synthetic/stop", {"generation": GENERATION}
        )
        if (
            status != 200
            or started["api_pid"] == stopped["runtime_pid"]
            or stopped["child_pid"] in {started["api_pid"], stopped["runtime_pid"]}
            or stopped["state"] != "STOPPED"
            or stopped["child_stopped"] is not True
            or stopped["geometry"] != [100, 40]
            or stopped["input_count"] != 1
            or stopped["detach_count"] != 1
            or stopped["registry_count"] != 0
        ):
            raise RuntimeError("synthetic Stop evidence is invalid")

        with cluster.browser() as replay:
            replay.send(
                browser_frame(
                    F.WS_HELLO,
                    {
                        "protocol_version": 1,
                        **admission,
                        "runtime_epoch": RUNTIME_EPOCH,
                        "ticket": ticket,
                        "resume_cursor": None,
                        "previous_runtime_epoch": None,
                    },
                    1,
                )
            )
            opcode, raw = replay.receive()
            if opcode != 8 or int.from_bytes(raw[:2], "big") != 4403:
                raise RuntimeError("synthetic ticket replay was accepted")

        status, shutdown = cluster.http("POST", "/synthetic/shutdown")
        if (
            status != 200
            or shutdown.get("issuance_fenced") is not True
            or shutdown.get("authority_clean") is not True
            or shutdown.get("runtime", {}).get("registry_count") != 0
            or shutdown.get("runtime", {}).get("prepare_count") != 1
            or shutdown.get("audit") != {"prepared": 1, "admitted": 1, "detached": 1}
        ):
            raise RuntimeError("synthetic shutdown evidence is invalid")
        cluster.assert_children_clean()
    return ticket


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-loopback", action="store_true")
    args = parser.parse_args(argv)
    if args.require_loopback and not loopback_bind_permitted():
        return 1
    try:
        run_synthetic_path(Path.cwd())
    except Exception:
        return 1
    print("rc8 artifact synthetic path passed.")
    return 0


def browser_frame(kind: F, payload: dict[str, Any] | bytes, sequence: int) -> bytes:
    return encode_wire_frame(kind, BA, payload, sequence)


def browser_body(raw: bytes) -> tuple[F, dict[str, Any] | None]:
    frame = decode_wire_frame(raw, AB)
    return frame.frame_type, frame.json_payload


__all__ = [
    "AB",
    "AUTHORITY_EPOCH",
    "GENERATION",
    "ORIGIN",
    "RUNTIME_EPOCH",
    "RawRFC6455Peer",
    "SyntheticWAWCluster",
    "browser_body",
    "browser_frame",
    "claims_from_admission",
    "loopback_bind_permitted",
    "run_synthetic_path",
    "synthetic_waw_cluster",
    "verify_synthetic_trust_record",
]


if __name__ == "__main__":
    raise SystemExit(_main())
