"""Production native auth-probe port: AWP1 record, AWRP placement, sealed factory.

One :class:`WAWNativeAuthProbePort` runs exactly one fixed auth observation
through the native ``agentbox-waw-pane-bootstrap --auth-probe`` helper.  The
port sends one exact 160-byte AWP1 record on a SOCK_SEQPACKET control channel,
waits for the independent 8-byte AWRP placed-ready proof, drains both output
pipes concurrently under one shared byte budget, and always ends with a
cleanup proof: the helper leader is reaped, termination escalates
SIGTERM -> SIGKILL plus a cgroup kill for descendants, and the cgroup
populated read-back decides descendant certainty.  The sealed factory binds
the held helper/vendor executable descriptors to one verified execution
authority before any record is sent (contract: FD5 + AgentType + digest are
pinned by the same manifest/authority).  The module retains metadata only;
raw probe output exists only inside the ephemeral completion handed to the
metadata-only runner, and nothing here logs or audits probe content.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import select
import signal
import socket
import struct
import threading
import time
import weakref
from typing import cast

from agentbox_core.waw import AgentType

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_auth_lease import WAWSealedAuthLease
from agentbox_runtime.waw_executable import WAWExecutableKind
from agentbox_runtime.waw_fixed_transport import (
    CgroupControlHandle,
    NativeHelperProcessPort,
    WAWVerifiedExecutionAuthority,
    _close_fd,
    _duplicate_role_fd,
    _is_unix_seqpacket,
    _role_fd,
    _spawn_fixed,
    _verify_fd_digest,
)
from agentbox_runtime.waw_process_inspector import FixedProcessIdentity
from agentbox_runtime.waw_vendor_probe import (
    WAWIsolatedProbeCompletion,
    WAWProcessIsolationKind,
    WAWProcessIsolationPort,
    WAWVendorProbeFailure,
    WAWVendorProbeProfile,
)

_AUTH_RECORD = struct.Struct("!4sBBHIIIQ64s64s4s")
AUTH_RECORD_BYTES = _AUTH_RECORD.size
_AUTH_PLACED = b"AWRP\x01\x01\x00\x00"
_AUTH_PLACED_DEADLINE_SECONDS = 5.0
_AUTH_NATIVE_PORT_TOKEN = object()
_AGENT_CODES: dict[AgentType, int] = {AgentType.CLAUDE: 1, AgentType.CODEX: 2}
_AUTH_PROBE_ARGUMENTS: dict[AgentType, tuple[str, ...]] = {
    AgentType.CLAUDE: ("auth", "status"),
    AgentType.CODEX: ("login", "status"),
}
_HELPER_FAILURE_EXIT_CODES = frozenset({65, 71})
_MONITOR_SLICE_SECONDS = 0.05
_DRAIN_MARGIN_SECONDS = 1.0

# Tests substitute a posix_spawn adapter for this alias on non-Linux hosts.
_spawn = _spawn_fixed


def _unconfirmed(message: str) -> RuntimeOperationError:
    return RuntimeOperationError("WAW_AUTH_PLACEMENT_UNCONFIRMED", message, category="conflict")


def _encode_auth_record(identity: FixedProcessIdentity) -> bytes:
    """Encode the exact 160-byte AWP1 record for one fixed process identity."""

    if type(identity) is not FixedProcessIdentity:
        raise TypeError("fixed process identity is required")
    agent_code = _AGENT_CODES.get(identity.agent_type)
    if agent_code is None:
        raise RuntimeOperationError(
            "RUNTIME_UNAVAILABLE",
            "Auth probe agent type is outside the closed map",
            category="unavailable",
        )
    return _AUTH_RECORD.pack(
        b"AWP1",
        1,
        agent_code,
        0,
        os.getpid(),
        os.geteuid(),
        os.getegid(),
        identity.generation,
        identity.workspace_hash.encode("ascii"),
        identity.profile_digest.encode("ascii"),
        b"\0" * 4,
    )


def receive_auth_placed(connection: socket.socket, *, timeout_seconds: float) -> None:
    """Accept one exact 8-byte AWRP placed packet: no ancillary data, no tail.

    This is deliberately separate from ``receive_native_ready``: the auth
    helper proves cgroup placement with an independent ``AWRP`` record, never
    with the interactive 9-byte ``AWR1`` running identity.
    """

    if not _is_unix_seqpacket(connection):
        raise _unconfirmed("Auth placed endpoint is invalid")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or not 0 < float(timeout_seconds) <= _AUTH_PLACED_DEADLINE_SECONDS
    ):
        raise ValueError("auth placed deadline is invalid")
    readable, _, _ = select.select([connection], [], [], float(timeout_seconds))
    if not readable:
        raise _unconfirmed("Auth placed deadline expired")
    try:
        payload, ancillary, flags, _address = connection.recvmsg(8, socket.CMSG_SPACE(1))
    except OSError as exc:
        raise _unconfirmed("Auth placed channel failed") from exc
    if payload != _AUTH_PLACED or ancillary or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
        raise _unconfirmed("Auth placed proof is invalid")


def _control_socketpair() -> tuple[socket.socket, socket.socket]:
    """Return the AWP1/AWRP control channel; tests may patch for the host."""

    return socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)


def _pipe_cloexec() -> tuple[int, int]:
    """Return one CLOEXEC pipe; ``os.pipe2`` on Linux, a fallback elsewhere."""

    pipe2 = getattr(os, "pipe2", None)
    if pipe2 is not None:
        return cast(tuple[int, int], pipe2(os.O_CLOEXEC))
    read_fd, write_fd = os.pipe()
    os.set_inheritable(read_fd, False)
    os.set_inheritable(write_fd, False)
    return read_fd, write_fd


def _open_pidfd(pid: int) -> int | None:
    """Open a pidfd when the platform offers one; tests may patch this."""

    opener = getattr(os, "pidfd_open", None)
    if not callable(opener):
        return None
    try:
        return cast(int, opener(pid, 0))
    except OSError:
        return None


def _signal_child(pid: int, pidfd: int | None, signal_number: int) -> None:
    if pidfd is not None:
        sender = getattr(signal, "pidfd_send_signal", None)
        if callable(sender):
            with contextlib.suppress(ProcessLookupError):
                sender(pidfd, signal_number)
            return
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal_number)


def _poll_child(pid: int) -> int | None:
    """Return the raw wait status once the exact child exited, else None."""

    waited, status = os.waitpid(pid, os.WNOHANG)
    if waited == 0:
        return None
    return status


def _wait_child(pid: int, timeout_seconds: float) -> int | None:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        status = _poll_child(pid)
        if status is not None:
            return status
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(0.01, remaining))


def _reap_child(pid: int) -> int:
    while True:
        try:
            _waited, status = os.waitpid(pid, 0)
            return status
        except InterruptedError:
            continue


def _terminate_and_reap(pid: int, pidfd: int | None, grace_seconds: float) -> tuple[int, bool]:
    """SIGTERM, grace, then SIGKILL and a blocking reap of the exact child.

    Returns the raw wait status and whether termination escalated to SIGKILL.
    Kept small and module-level so platform tests can patch it.
    """

    _signal_child(pid, pidfd, signal.SIGTERM)
    status = _wait_child(pid, grace_seconds)
    if status is not None:
        return status, False
    _signal_child(pid, pidfd, signal.SIGKILL)
    return _reap_child(pid), True


def _terminate_helper(
    pid: int,
    pidfd: int | None,
    grace_seconds: float,
    cgroup: CgroupControlHandle,
) -> tuple[int, bool]:
    """Terminate the helper and, on escalation, cgroup-kill the descendants.

    Returns the raw wait status and whether cleanup stayed certain.  The
    ``lease._cgroup.kill()`` idiom is the same-package private capability the
    sealed auth lease lends to exactly this port.
    """

    status, escalated = _terminate_and_reap(pid, pidfd, grace_seconds)
    certain = True
    if escalated:
        try:
            cgroup.kill()
        except Exception:
            certain = False
    return status, certain


def _place_helper(
    control_parent: socket.socket,
    record: bytes,
    deadline: float,
    cancel_event: threading.Event,
) -> bool:
    """Send the one AWP1 record, seal the channel, and await the exact AWRP."""

    if cancel_event.is_set():
        return False
    try:
        if control_parent.send(record) != len(record):
            return False
        control_parent.shutdown(socket.SHUT_WR)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        receive_auth_placed(
            control_parent,
            timeout_seconds=min(remaining, _AUTH_PLACED_DEADLINE_SECONDS),
        )
    except Exception:
        return False
    return not cancel_event.is_set()


class _PipeDrain:
    """Concurrent non-blocking drain of the two helper output pipes.

    One shared byte budget covers stdout and stderr together; reaching the
    budget (``output_limit + 1``) means the first overflowing byte arrived.
    """

    def __init__(self, stdout_fd: int, stderr_fd: int, budget: int) -> None:
        self._stdout_fd = stdout_fd
        self._stderr_fd = stderr_fd
        self._buffers: dict[int, bytearray] = {stdout_fd: bytearray(), stderr_fd: bytearray()}
        self._budget = budget
        self._received = 0
        self._retain = True
        self.overflow = False
        self._open: set[int] = {stdout_fd, stderr_fd}
        self._poller = select.poll()
        for descriptor in (stdout_fd, stderr_fd):
            os.set_blocking(descriptor, False)
            self._poller.register(descriptor, select.POLLIN | select.POLLHUP | select.POLLERR)

    @property
    def drained(self) -> bool:
        return not self._open

    @property
    def stdout(self) -> bytes:
        return bytes(self._buffers[self._stdout_fd])

    @property
    def stderr(self) -> bytes:
        return bytes(self._buffers[self._stderr_fd])

    def discard(self) -> None:
        self._retain = False
        self._buffers[self._stdout_fd].clear()
        self._buffers[self._stderr_fd].clear()

    def pump(self, timeout_ms: int) -> None:
        events = self._poller.poll(max(0, timeout_ms))
        for descriptor, _event in events:
            try:
                chunk = os.read(descriptor, 65536)
            except BlockingIOError:
                continue
            except OSError:
                chunk = b""
            if not chunk:
                if descriptor in self._open:
                    with contextlib.suppress(KeyError):
                        self._poller.unregister(descriptor)
                    self._open.discard(descriptor)
                continue
            self._received += len(chunk)
            if self._received >= self._budget:
                self.overflow = True
                self.discard()
            elif self._retain:
                self._buffers[descriptor].extend(chunk)


class WAWNativeAuthProbePort(WAWProcessIsolationPort):
    """Single-use pre-birth auth-probe port over the fixed native helper ABI.

    Construction is token-gated: only :class:`WAWNativeAuthProbePortFactory`
    may issue ports.  Every held descriptor is role-validated and re-duped
    ``F_DUPFD_CLOEXEC`` at construction so caller-side closes cannot swap the
    assets underneath one in-flight probe.
    """

    def __init__(
        self,
        token: object,
        *,
        lease: WAWSealedAuthLease,
        identity: FixedProcessIdentity,
        helper_executable: int,
        vendor_executable: int,
        home_directory: int,
        policy_directory: int,
    ) -> None:
        if token is not _AUTH_NATIVE_PORT_TOKEN:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Native auth probe ports are not caller-constructible",
                category="unavailable",
            )
        if type(lease) is not WAWSealedAuthLease:
            raise TypeError("exact sealed auth lease is required")
        if type(identity) is not FixedProcessIdentity:
            raise TypeError("fixed process identity is required")
        super().__init__(
            isolation_kind=WAWProcessIsolationKind.PREBIRTH_CGROUP,
            production_qualified=True,
        )
        duplicated: list[int] = []
        try:
            for descriptor, role in (
                (helper_executable, "executable"),
                (vendor_executable, "executable"),
                (home_directory, "directory"),
                (policy_directory, "directory"),
            ):
                duplicated.append(_duplicate_role_fd(descriptor, role))
        except BaseException:
            for held in reversed(duplicated):
                _close_fd(held)
            raise
        self._lease = lease
        self._identity = identity
        self._helper_executable = duplicated[0]
        self._vendor_executable = duplicated[1]
        self._home_directory = duplicated[2]
        self._policy_directory = duplicated[3]
        self._executed = False
        self._closed = False

    def close(self) -> None:
        """Idempotently release every descriptor this port holds."""

        if self._closed:
            return
        self._closed = True
        for descriptor in (
            self._helper_executable,
            self._vendor_executable,
            self._home_directory,
            self._policy_directory,
        ):
            _close_fd(descriptor)
        self._helper_executable = -1
        self._vendor_executable = -1
        self._home_directory = -1
        self._policy_directory = -1

    async def execute(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> WAWIsolatedProbeCompletion:
        """Run the one fixed auth observation this port exists for."""

        if self._closed or self._executed:
            raise RuntimeOperationError(
                "WAW_AUTH_PROBE_BUSY",
                "Native auth probe port is single-use",
                category="conflict",
            )
        self._executed = True
        if not self._request_matches(
            profile, arguments, timeout_seconds, output_limit, terminate_grace_seconds
        ):
            # Fail closed inside the spawn-error domain without spawning.
            return WAWIsolatedProbeCompletion(
                None,
                b"",
                b"",
                WAWVendorProbeFailure.SPAWN_ERROR,
                self.cleanup_proof(leader_reaped=True, descendants_remaining=0),
            )
        record = _encode_auth_record(self._identity)
        stdout_read = stdout_write = stderr_read = stderr_write = -1
        devnull = cgroup_fd = scratch_fd = -1
        control_parent: socket.socket | None = None
        control_child: socket.socket | None = None
        try:
            stdout_read, stdout_write = _pipe_cloexec()
            stderr_read, stderr_write = _pipe_cloexec()
            control_parent, control_child = _control_socketpair()
            devnull = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            cgroup_fd = self._lease.cgroup_fd()
            scratch_fd = self._lease.scratch_fd()
        except BaseException:
            for descriptor in (
                stdout_read,
                stdout_write,
                stderr_read,
                stderr_write,
                devnull,
                cgroup_fd,
                scratch_fd,
            ):
                if descriptor >= 0:
                    _close_fd(descriptor)
            for endpoint in (control_parent, control_child):
                if endpoint is not None:
                    endpoint.close()
            raise
        descriptor_map = (
            (devnull, 0),
            (stdout_write, 1),
            (stderr_write, 2),
            (control_child.fileno(), 3),
            (cgroup_fd, 4),
            (self._vendor_executable, 5),
            (self._home_directory, 6),
            (scratch_fd, 7),
            (self._policy_directory, 8),
        )
        try:
            pid = _spawn(
                self._helper_executable,
                ("agentbox-waw-pane-bootstrap", "--auth-probe"),
                {},
                descriptor_map,
            )
        except BaseException:
            for descriptor in (
                stdout_read,
                stdout_write,
                stderr_read,
                stderr_write,
                devnull,
                cgroup_fd,
                scratch_fd,
            ):
                _close_fd(descriptor)
            control_parent.close()
            control_child.close()
            raise
        # The child owns its dup2 copies; drop every child-side descriptor.
        _close_fd(stdout_write)
        _close_fd(stderr_write)
        control_child.close()
        _close_fd(devnull)
        _close_fd(cgroup_fd)
        _close_fd(scratch_fd)
        deadline = time.monotonic() + float(timeout_seconds)
        cancel_event = threading.Event()
        try:
            worker = asyncio.create_task(
                asyncio.to_thread(
                    self._run_isolated_probe,
                    record=record,
                    pid=pid,
                    control_parent=control_parent,
                    stdout_read=stdout_read,
                    stderr_read=stderr_read,
                    deadline=deadline,
                    output_limit=output_limit,
                    terminate_grace_seconds=float(terminate_grace_seconds),
                    cancel_event=cancel_event,
                )
            )
        except BaseException:
            control_parent.close()
            _close_fd(stdout_read)
            _close_fd(stderr_read)
            with contextlib.suppress(Exception):
                _terminate_and_reap(pid, None, 0.1)
            raise
        cancelled = False
        completion: WAWIsolatedProbeCompletion | None = None
        while completion is None:
            try:
                completion = await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancelled = True
                cancel_event.set()
                if worker.done():
                    completion = worker.result()
        if cancelled:
            # Cleanup (terminate, reap, drain, proof) finished before this
            # propagation; the caller never sees a half-cleaned probe.
            raise asyncio.CancelledError
        return completion

    def _request_matches(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> bool:
        if type(profile) is not WAWVendorProbeProfile:
            return False
        if profile.agent_type is not self._identity.agent_type:
            return False
        expected = _AUTH_PROBE_ARGUMENTS.get(self._identity.agent_type)
        if expected is None or type(arguments) is not tuple or arguments != expected:
            return False
        for value in (timeout_seconds, terminate_grace_seconds):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                return False
        return type(output_limit) is int and output_limit >= 1

    def _run_isolated_probe(
        self,
        *,
        record: bytes,
        pid: int,
        control_parent: socket.socket,
        stdout_read: int,
        stderr_read: int,
        deadline: float,
        output_limit: int,
        terminate_grace_seconds: float,
        cancel_event: threading.Event,
    ) -> WAWIsolatedProbeCompletion:
        """Drive placement, bounded drain, termination, and the cleanup proof.

        Runs on a worker thread; cancellation reaches it only through
        ``cancel_event`` so the terminate/reap/proof sequence always finishes.
        """

        cgroup = self._lease._cgroup
        drain = _PipeDrain(stdout_read, stderr_read, output_limit + 1)
        pidfd: int | None = None
        status: int | None = None
        exit_code: int | None = None
        failure = WAWVendorProbeFailure.NONE
        uncertain = False
        try:
            pidfd = _open_pidfd(pid)
            if not _place_helper(control_parent, record, deadline, cancel_event):
                failure = WAWVendorProbeFailure.SPAWN_ERROR
                drain.discard()
                status, certain = _terminate_helper(pid, pidfd, terminate_grace_seconds, cgroup)
                uncertain = uncertain or not certain
                exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else None
            else:
                while status is None:
                    now = time.monotonic()
                    if cancel_event.is_set() or drain.overflow or now >= deadline:
                        failure = (
                            WAWVendorProbeFailure.OUTPUT_LIMIT
                            if drain.overflow and not cancel_event.is_set()
                            else WAWVendorProbeFailure.TIMEOUT
                        )
                        drain.discard()
                        status, certain = _terminate_helper(
                            pid, pidfd, terminate_grace_seconds, cgroup
                        )
                        uncertain = uncertain or not certain
                        exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else None
                        break
                    status = _poll_child(pid)
                    if status is not None:
                        break
                    slice_ms = max(1, math.ceil(min(_MONITOR_SLICE_SECONDS, deadline - now) * 1000))
                    if drain.drained:
                        time.sleep(slice_ms / 1000)
                    else:
                        drain.pump(slice_ms)
                if failure is WAWVendorProbeFailure.NONE:
                    assert status is not None
                    if os.WIFEXITED(status):
                        exit_code = os.WEXITSTATUS(status)
                        if exit_code in _HELPER_FAILURE_EXIT_CODES:
                            # Helper-domain setup/placement failure (65/71).
                            failure = WAWVendorProbeFailure.SPAWN_ERROR
                            drain.discard()
                    else:
                        failure = WAWVendorProbeFailure.SIGNALLED
                        drain.discard()
            # Continue draining to EOF after exit or termination; bounded so
            # an escaped writer can only degrade the proof, never hang it.
            drain_deadline = time.monotonic() + _DRAIN_MARGIN_SECONDS
            while not drain.drained:
                remaining_ms = math.ceil((drain_deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    uncertain = True
                    break
                drain.pump(remaining_ms)
        except Exception:
            failure = WAWVendorProbeFailure.SPAWN_ERROR
            exit_code = None
            uncertain = True
            if status is None:
                with contextlib.suppress(Exception):
                    _signal_child(pid, pidfd, signal.SIGKILL)
                with contextlib.suppress(Exception):
                    _waited, status = os.waitpid(pid, 0)
        finally:
            control_parent.close()
            _close_fd(stdout_read)
            _close_fd(stderr_read)
            if pidfd is not None:
                _close_fd(pidfd)
        if uncertain or status is None:
            descendants = 1
        else:
            try:
                descendants = 0 if cgroup.populated() == 0 else 1
            except Exception:
                descendants = 1
        if failure is WAWVendorProbeFailure.NONE and drain.overflow:
            # A burst that raced the monitor loop still triggers the fixed
            # output budget; the overflowing bytes were already discarded.
            failure = WAWVendorProbeFailure.OUTPUT_LIMIT
        proof = self.cleanup_proof(
            leader_reaped=status is not None,
            descendants_remaining=descendants,
        )
        if failure is not WAWVendorProbeFailure.NONE:
            return WAWIsolatedProbeCompletion(exit_code, b"", b"", failure, proof)
        return WAWIsolatedProbeCompletion(exit_code, drain.stdout, drain.stderr, failure, proof)


class WAWNativeAuthProbePortFactory:
    """Issue sealed single-use auth probe ports bound to one authority.

    The factory dups and digest-pins the held ``pane_bootstrap`` helper and
    both vendor executables out of one production :class:`NativeHelperProcessPort`;
    per contract the FD5 vendor descriptor, the AgentType, and the executable
    digest are all verified against the same verified execution authority
    before any lease can receive a port.
    """

    def __init__(
        self,
        authority: WAWVerifiedExecutionAuthority,
        *,
        process_port: NativeHelperProcessPort,
    ) -> None:
        if type(authority) is not WAWVerifiedExecutionAuthority:
            raise TypeError("verified execution authority is required")
        if type(process_port) is not NativeHelperProcessPort:
            raise TypeError("exact native helper process port is required")
        if process_port.production_qualified is not True:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Native auth probe factory requires a production process port",
                category="unavailable",
            )
        if process_port.execution_authority is not authority:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Native process port is not bound to this execution authority",
                category="unavailable",
            )
        inventory = authority._manifest.executable_inventory.executables
        held: list[int] = []
        vendors: dict[AgentType, int] = {}
        try:
            helper = _duplicate_role_fd(process_port._helpers.pane_bootstrap, "executable")
            held.append(helper)
            helper_entries = [
                entry for entry in inventory if entry.kind == WAWExecutableKind.PANE_BOOTSTRAP.value
            ]
            if len(helper_entries) != 1:
                raise RuntimeOperationError(
                    "RUNTIME_UNAVAILABLE",
                    "Helper executable authority is unavailable",
                    category="unavailable",
                )
            _verify_fd_digest(
                helper, helper_entries[0].sha256, max_bytes=helper_entries[0].max_bytes
            )
            for agent_type, kind in (
                (AgentType.CLAUDE, WAWExecutableKind.CLAUDE),
                (AgentType.CODEX, WAWExecutableKind.CODEX),
            ):
                vendor = _duplicate_role_fd(process_port._qualified_executables[kind], "executable")
                held.append(vendor)
                # Contract (WAW_R12_RUNTIME_AUTH_PROBE.md): FD5, AgentType and
                # the executable digest are bound to the same authority here.
                _verify_fd_digest(vendor, authority.vendor_executable_fingerprint(agent_type))
                vendors[agent_type] = vendor
        except BaseException:
            for descriptor in reversed(held):
                _close_fd(descriptor)
            raise
        self._authority = authority
        self._helper_executable = helper
        self._vendor_executables = vendors
        self._issued_leases: weakref.WeakSet[WAWSealedAuthLease] = weakref.WeakSet()
        self._closed = False

    @property
    def authority(self) -> WAWVerifiedExecutionAuthority:
        return self._authority

    def close(self) -> None:
        """Idempotently release the held executable descriptors; terminal."""

        if self._closed:
            return
        self._closed = True
        _close_fd(self._helper_executable)
        for descriptor in self._vendor_executables.values():
            _close_fd(descriptor)
        self._helper_executable = -1
        self._vendor_executables = {}

    def port_for_lease(self, lease: WAWSealedAuthLease) -> WAWNativeAuthProbePort:
        """Issue the single-use port for one OWNED, authority-bound lease."""

        if self._closed:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "Native auth probe port factory is closed",
                category="unavailable",
            )
        if type(lease) is not WAWSealedAuthLease:
            raise TypeError("exact sealed auth lease is required")
        if lease._state != "OWNED":
            raise RuntimeOperationError(
                "WAW_AUTH_LEASE_STALE",
                "Sealed auth lease is not owned",
                category="conflict",
            )
        identity = lease.identity
        if type(identity) is not FixedProcessIdentity or not self._authority.authorizes(identity):
            raise RuntimeOperationError(
                "WAW_AUTH_LEASE_STALE",
                "Sealed auth lease identity is not authorized",
                category="conflict",
            )
        vendor = self._vendor_executables.get(identity.agent_type)
        if vendor is None:
            raise RuntimeOperationError(
                "WAW_AUTH_LEASE_STALE",
                "Sealed auth lease agent type is outside the closed map",
                category="conflict",
            )
        if lease in self._issued_leases:
            raise RuntimeOperationError(
                "WAW_AUTH_PROBE_BUSY",
                "Sealed auth lease already issued its single probe port",
                category="conflict",
            )
        try:
            handles = lease._transport._handles
            home = _role_fd(handles.selected_home_directory, "directory")
            policy = _role_fd(handles.policy_directory, "directory")
        except AttributeError as exc:
            raise RuntimeOperationError(
                "WAW_AUTH_LEASE_STALE",
                "Sealed auth lease transport handles are unavailable",
                category="conflict",
            ) from exc
        self._issued_leases.add(lease)
        return WAWNativeAuthProbePort(
            _AUTH_NATIVE_PORT_TOKEN,
            lease=lease,
            identity=identity,
            helper_executable=self._helper_executable,
            vendor_executable=vendor,
            home_directory=home,
            policy_directory=policy,
        )


__all__ = [
    "AUTH_RECORD_BYTES",
    "WAWNativeAuthProbePort",
    "WAWNativeAuthProbePortFactory",
    "receive_auth_placed",
]
