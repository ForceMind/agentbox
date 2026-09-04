"""Version-bound, bounded public vendor probe execution for WAW.

Only trusted Runtime composition constructs probe profiles.  Callers select an
``AgentType`` and report the already-observed vendor version; they cannot supply
an executable, argv, environment, parser, timeout, signal, or output limit.
Probe output exists only long enough to run the exact version-bound parser and
is never retained in returned evidence or exception text.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import math
import os
import re
import signal
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from agentbox_core.waw import AgentType

from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1

WAW_VENDOR_PROBE_OUTPUT_LIMIT = 4 * 1024
WAW_VENDOR_PROBE_TIMEOUT_SECONDS = 5.0
WAW_VENDOR_PROBE_TERMINATE_GRACE_SECONDS = 0.25

_VERSION = re.compile(r"\A[!-~]{1,96}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_ENVIRONMENT_KEY = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z")

_create_subprocess_exec = asyncio.create_subprocess_exec
_killpg = os.killpg
_SYNTHETIC_PORT_TOKEN = object()


class WAWVendorProbeError(ValueError):
    """A trusted probe profile or execution request is malformed."""


class WAWVendorProbeId(StrEnum):
    CLAUDE_AUTH_STATUS_V1 = "claude.auth_status.v1"
    CODEX_LOGIN_STATUS_V1 = "codex.login_status.v1"


class WAWVendorProbeParserId(StrEnum):
    CLAUDE_EXIT_STATUS_V1 = "claude-auth-status-v1"
    CODEX_EXACT_STATUS_V1 = "codex-login-status-v1"


class WAWVendorProbeResult(StrEnum):
    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class WAWVendorProbeFailure(StrEnum):
    NONE = "NONE"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    SPAWN_ERROR = "SPAWN_ERROR"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    TIMEOUT = "TIMEOUT"
    SIGNALLED = "SIGNALLED"
    NON_UTF8 = "NON_UTF8"
    PROCESS_GROUP = "PROCESS_GROUP"
    CLEANUP_UNPROVEN = "CLEANUP_UNPROVEN"
    UNQUALIFIED_ISOLATION = "UNQUALIFIED_ISOLATION"


class WAWProcessIsolationKind(StrEnum):
    SYNTHETIC_SUBPROCESS = "SYNTHETIC_SUBPROCESS"
    PREBIRTH_CGROUP = "PREBIRTH_CGROUP"
    PID_NAMESPACE = "PID_NAMESPACE"
    QUALIFIED_EQUIVALENT = "QUALIFIED_EQUIVALENT"


_PROBE_ARGUMENTS: dict[WAWVendorProbeId, tuple[str, ...]] = {
    WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1: ("auth", "status"),
    WAWVendorProbeId.CODEX_LOGIN_STATUS_V1: ("login", "status"),
}
_PROBE_CONTRACT: dict[WAWVendorProbeId, tuple[AgentType, WAWVendorProbeParserId]] = {
    WAWVendorProbeId.CLAUDE_AUTH_STATUS_V1: (
        AgentType.CLAUDE,
        WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1,
    ),
    WAWVendorProbeId.CODEX_LOGIN_STATUS_V1: (
        AgentType.CODEX,
        WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1,
    ),
}


def waw_vendor_probe_output_digest(stdout: bytes, stderr: bytes) -> str:
    """Hash an exact stdout/stderr tuple without ambiguous concatenation."""

    if type(stdout) is not bytes or type(stderr) is not bytes:
        raise TypeError("probe output must be bytes")
    framed = len(stdout).to_bytes(8, "big") + stdout + len(stderr).to_bytes(8, "big") + stderr
    return hashlib.sha256(framed).hexdigest()


@dataclass(frozen=True)
class WAWVendorProbeProfile:
    """Trusted installation binding for one exact supported vendor build."""

    profile_id: str
    agent_type: AgentType
    vendor_version: str
    probe_id: WAWVendorProbeId
    parser_id: WAWVendorProbeParserId
    executable: Path
    cwd: Path
    environment: tuple[tuple[str, str], ...]
    codex_unauthenticated_output_sha256: str | None = None
    synthetic_test_only: bool = False

    def __post_init__(self) -> None:
        if type(self.agent_type) is not AgentType:
            raise WAWVendorProbeError("probe agent_type is invalid")
        expected_profile = INTERACTIVE_PROFILE_CONSTANTS_V1[self.agent_type.value]
        if self.profile_id != expected_profile["profile_id"]:
            raise WAWVendorProbeError("probe profile_id does not match interactive profile")
        if type(self.vendor_version) is not str or _VERSION.fullmatch(self.vendor_version) is None:
            raise WAWVendorProbeError("probe vendor_version is invalid")
        if type(self.probe_id) is not WAWVendorProbeId:
            raise WAWVendorProbeError("probe_id is invalid")
        if type(self.parser_id) is not WAWVendorProbeParserId:
            raise WAWVendorProbeError("parser_id is invalid")
        if _PROBE_CONTRACT[self.probe_id] != (self.agent_type, self.parser_id):
            raise WAWVendorProbeError("probe and parser are not valid for AgentType")
        if (
            self.parser_id.value != expected_profile["auth_parser_id"]
            or _PROBE_ARGUMENTS[self.probe_id] != expected_profile["auth_probe_argv"]
        ):
            raise WAWVendorProbeError("probe does not match interactive profile")
        _validate_absolute_path(self.executable, field="executable")
        _validate_absolute_path(self.cwd, field="cwd")
        if type(self.environment) is not tuple or len(self.environment) > 32:
            raise WAWVendorProbeError("probe environment is invalid")
        seen: set[str] = set()
        for entry in self.environment:
            if type(entry) is not tuple or len(entry) != 2:
                raise WAWVendorProbeError("probe environment is invalid")
            key, value = entry
            if (
                type(key) is not str
                or _ENVIRONMENT_KEY.fullmatch(key) is None
                or key in seen
                or type(value) is not str
                or "\x00" in value
                or len(value.encode("utf-8")) > 4096
            ):
                raise WAWVendorProbeError("probe environment is invalid")
            seen.add(key)
        digest = self.codex_unauthenticated_output_sha256
        if self.agent_type is AgentType.CODEX:
            if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
                raise WAWVendorProbeError("Codex unauthenticated fixture digest is invalid")
        elif digest is not None:
            raise WAWVendorProbeError("Claude probe cannot configure a Codex fixture digest")
        if type(self.synthetic_test_only) is not bool:
            raise WAWVendorProbeError("synthetic_test_only is invalid")


@dataclass(frozen=True)
class WAWVendorProbeEvidence:
    """Metadata-only outcome.  Raw or decoded process output is never retained."""

    profile_id: str
    agent_type: AgentType
    vendor_version: str
    probe_id: WAWVendorProbeId
    parser_id: WAWVendorProbeParserId
    result: WAWVendorProbeResult
    failure: WAWVendorProbeFailure
    exit_code: int | None

    def __post_init__(self) -> None:
        if type(self.agent_type) is not AgentType:
            raise WAWVendorProbeError("probe evidence agent_type is invalid")
        if self.profile_id != INTERACTIVE_PROFILE_CONSTANTS_V1[self.agent_type.value]["profile_id"]:
            raise WAWVendorProbeError("probe evidence profile_id is invalid")
        if type(self.vendor_version) is not str or _VERSION.fullmatch(self.vendor_version) is None:
            raise WAWVendorProbeError("probe evidence vendor_version is invalid")
        if (
            type(self.probe_id) is not WAWVendorProbeId
            or type(self.parser_id) is not WAWVendorProbeParserId
        ):
            raise WAWVendorProbeError("probe evidence IDs are invalid")
        if (
            type(self.result) is not WAWVendorProbeResult
            or type(self.failure) is not WAWVendorProbeFailure
        ):
            raise WAWVendorProbeError("probe evidence outcome is invalid")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise WAWVendorProbeError("probe evidence exit_code is invalid")
        if self.result is WAWVendorProbeResult.UNSUPPORTED:
            if (
                self.failure is not WAWVendorProbeFailure.VERSION_MISMATCH
                or self.exit_code is not None
            ):
                raise WAWVendorProbeError("unsupported evidence is inconsistent")
        elif self.failure is WAWVendorProbeFailure.VERSION_MISMATCH:
            raise WAWVendorProbeError("version mismatch must be unsupported")
        elif (
            self.failure is not WAWVendorProbeFailure.NONE
            and self.result is not WAWVendorProbeResult.UNKNOWN
        ):
            raise WAWVendorProbeError("probe failure must be unknown")


def _validate_absolute_path(value: Path, *, field: str) -> None:
    if (
        not isinstance(value, Path)
        or not value.is_absolute()
        or value.anchor != "/"
        or ".." in value.parts
        or "\x00" in str(value)
        or len(os.fsencode(value)) > 4096
    ):
        raise WAWVendorProbeError(f"probe {field} is invalid")


class _OutputLimitExceeded(Exception):
    pass


@dataclass(frozen=True)
class WAWProcessCleanupProof:
    """Nominal proof issued by one isolation port after cleanup/read-back."""

    isolation_kind: WAWProcessIsolationKind
    leader_reaped: bool
    descendants_remaining: int
    _issuer: object = field(repr=False, compare=False)

    @property
    def complete(self) -> bool:
        return self.leader_reaped and self.descendants_remaining == 0


@dataclass(frozen=True)
class WAWIsolatedProbeCompletion:
    """Ephemeral port result consumed immediately by the metadata-only runner."""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    failure: WAWVendorProbeFailure
    cleanup_proof: WAWProcessCleanupProof


class WAWProcessIsolationPort(ABC):
    """Nominal pre-birth containment port for a complete probe process tree."""

    def __init__(
        self, *, isolation_kind: WAWProcessIsolationKind, production_qualified: bool
    ) -> None:
        if type(isolation_kind) is not WAWProcessIsolationKind:
            raise TypeError("isolation_kind is invalid")
        if type(production_qualified) is not bool:
            raise TypeError("production_qualified is invalid")
        if production_qualified and isolation_kind is WAWProcessIsolationKind.SYNTHETIC_SUBPROCESS:
            raise ValueError("synthetic subprocess isolation cannot be production qualified")
        self._isolation_kind = isolation_kind
        self._production_qualified = production_qualified
        self.__proof_issuer = object()

    @property
    def isolation_kind(self) -> WAWProcessIsolationKind:
        return self._isolation_kind

    @property
    def production_qualified(self) -> bool:
        return self._production_qualified

    def cleanup_proof(
        self, *, leader_reaped: bool, descendants_remaining: int
    ) -> WAWProcessCleanupProof:
        if type(leader_reaped) is not bool:
            raise TypeError("leader_reaped is invalid")
        if type(descendants_remaining) is not int or descendants_remaining < 0:
            raise ValueError("descendants_remaining is invalid")
        return WAWProcessCleanupProof(
            self._isolation_kind,
            leader_reaped,
            descendants_remaining,
            self.__proof_issuer,
        )

    def validates(self, proof: WAWProcessCleanupProof) -> bool:
        return (
            type(proof) is WAWProcessCleanupProof
            and proof._issuer is self.__proof_issuer
            and proof.isolation_kind is self._isolation_kind
        )

    @abstractmethod
    async def execute(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> WAWIsolatedProbeCompletion:
        """Run in pre-birth containment and return proof after all descendants empty."""


async def _await_cleanup_uninterruptibly(
    cleanup_task: asyncio.Task[WAWProcessCleanupProof],
) -> WAWProcessCleanupProof:
    """Observe one cleanup task to completion despite repeated caller cancellation."""

    cancelled = False
    while True:
        try:
            proof = await asyncio.shield(cleanup_task)
            break
        except asyncio.CancelledError:
            if cleanup_task.done():
                proof = cleanup_task.result()
                cancelled = True
                break
            cancelled = True
            continue
    if cancelled:
        raise asyncio.CancelledError
    return proof


class _SyntheticSubprocessIsolationPort(WAWProcessIsolationPort):
    """Unqualified subprocess harness for tests; never authorizes a probe result.

    A process group cannot contain a descendant that calls ``setsid``.  This
    adapter therefore always identifies itself as synthetic and the runner
    converts every otherwise successful parse to ``UNKNOWN``.
    """

    def __init__(self, token: object) -> None:
        if token is not _SYNTHETIC_PORT_TOKEN:
            raise TypeError("synthetic subprocess isolation is test-only")
        super().__init__(
            isolation_kind=WAWProcessIsolationKind.SYNTHETIC_SUBPROCESS,
            production_qualified=False,
        )

    async def execute(
        self,
        profile: WAWVendorProbeProfile,
        arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        output_limit: int,
        terminate_grace_seconds: float,
    ) -> WAWIsolatedProbeCompletion:
        if not profile.synthetic_test_only or arguments != _PROBE_ARGUMENTS[profile.probe_id]:
            raise WAWVendorProbeError("synthetic subprocess isolation is test-only")
        try:
            process = await _create_subprocess_exec(
                str(profile.executable),
                *arguments,
                cwd=str(profile.cwd),
                env=dict(profile.environment),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                limit=output_limit + 1,
            )
        except (OSError, ValueError):
            return WAWIsolatedProbeCompletion(
                None,
                b"",
                b"",
                WAWVendorProbeFailure.SPAWN_ERROR,
                self.cleanup_proof(leader_reaped=True, descendants_remaining=0),
            )

        assert process.stdout is not None
        assert process.stderr is not None
        remaining = [output_limit]
        stdout_task = asyncio.create_task(self._read_bounded(process.stdout, remaining))
        stderr_task = asyncio.create_task(self._read_bounded(process.stderr, remaining))
        wait_task = asyncio.create_task(process.wait())
        failure = WAWVendorProbeFailure.NONE
        stdout = stderr = b""
        exit_code: int | None = None
        try:
            stdout, stderr, exit_code = await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task, wait_task), timeout=timeout_seconds
            )
        except asyncio.CancelledError:
            cleanup = asyncio.create_task(
                self._cleanup(
                    process,
                    stdout_task,
                    stderr_task,
                    wait_task,
                    terminate_grace_seconds,
                )
            )
            await _await_cleanup_uninterruptibly(cleanup)
            raise AssertionError("unreachable after cancellation") from None
        except TimeoutError:
            failure = WAWVendorProbeFailure.TIMEOUT
        except _OutputLimitExceeded:
            failure = WAWVendorProbeFailure.OUTPUT_LIMIT

        if failure is not WAWVendorProbeFailure.NONE:
            cleanup = asyncio.create_task(
                self._cleanup(
                    process,
                    stdout_task,
                    stderr_task,
                    wait_task,
                    terminate_grace_seconds,
                )
            )
            proof = await _await_cleanup_uninterruptibly(cleanup)
            return WAWIsolatedProbeCompletion(process.returncode, b"", b"", failure, proof)

        assert exit_code is not None
        group_remaining = 1 if self._process_group_exists(process.pid) else 0
        if group_remaining:
            cleanup = asyncio.create_task(
                self._cleanup(
                    process,
                    stdout_task,
                    stderr_task,
                    wait_task,
                    terminate_grace_seconds,
                )
            )
            proof = await _await_cleanup_uninterruptibly(cleanup)
            return WAWIsolatedProbeCompletion(
                exit_code, b"", b"", WAWVendorProbeFailure.PROCESS_GROUP, proof
            )
        proof = self.cleanup_proof(leader_reaped=True, descendants_remaining=0)
        if exit_code < 0:
            return WAWIsolatedProbeCompletion(
                exit_code, b"", b"", WAWVendorProbeFailure.SIGNALLED, proof
            )
        return WAWIsolatedProbeCompletion(exit_code, stdout, stderr, failure, proof)

    async def _cleanup(
        self,
        process: asyncio.subprocess.Process,
        stdout_task: asyncio.Task[bytes],
        stderr_task: asyncio.Task[bytes],
        wait_task: asyncio.Task[int],
        terminate_grace_seconds: float,
    ) -> WAWProcessCleanupProof:
        for task in (stdout_task, stderr_task, wait_task):
            if not task.done():
                task.cancel()
        with contextlib.suppress(ProcessLookupError, PermissionError):
            _killpg(process.pid, signal.SIGTERM)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=terminate_grace_seconds)
        if self._process_group_exists(process.pid):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                _killpg(process.pid, signal.SIGKILL)
        await process.wait()
        await asyncio.gather(stdout_task, stderr_task, wait_task, return_exceptions=True)
        remaining = 1 if self._process_group_exists(process.pid) else 0
        return self.cleanup_proof(leader_reaped=True, descendants_remaining=remaining)

    @staticmethod
    async def _read_bounded(stream: asyncio.StreamReader, remaining: list[int]) -> bytes:
        result = bytearray()
        while True:
            chunk = await stream.read(min(1024, remaining[0] + 1))
            if not chunk:
                return bytes(result)
            if len(chunk) > remaining[0]:
                raise _OutputLimitExceeded
            remaining[0] -= len(chunk)
            result.extend(chunk)

    @staticmethod
    def _process_group_exists(process_group: int) -> bool:
        try:
            _killpg(process_group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def _synthetic_subprocess_port_for_tests() -> WAWProcessIsolationPort:
    """Return the private fixed-argv subprocess harness for repository tests."""

    return _SyntheticSubprocessIsolationPort(_SYNTHETIC_PORT_TOKEN)


class WAWVendorProbeRunner:
    """Parse only cleanup-proven results from a nominal qualified isolation port."""

    def __init__(
        self,
        profiles: Mapping[AgentType, WAWVendorProbeProfile],
        isolation_port: WAWProcessIsolationPort,
        *,
        timeout_seconds: float = WAW_VENDOR_PROBE_TIMEOUT_SECONDS,
        terminate_grace_seconds: float = WAW_VENDOR_PROBE_TERMINATE_GRACE_SECONDS,
    ) -> None:
        if not isinstance(profiles, Mapping):
            raise WAWVendorProbeError("probe profiles are invalid")
        copied = dict(profiles)
        if set(copied) != set(AgentType):
            raise WAWVendorProbeError("one probe profile per AgentType is required")
        for agent_type, profile in copied.items():
            if type(agent_type) is not AgentType or type(profile) is not WAWVendorProbeProfile:
                raise WAWVendorProbeError("probe profile entry is invalid")
            profile.__post_init__()
            if profile.agent_type is not agent_type:
                raise WAWVendorProbeError("probe profile key does not match AgentType")
        for value, field_name, maximum in (
            (timeout_seconds, "timeout_seconds", 30.0),
            (terminate_grace_seconds, "terminate_grace_seconds", 5.0),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 < value <= maximum
            ):
                raise WAWVendorProbeError(f"{field_name} is invalid")
        self._profiles = copied
        if not isinstance(isolation_port, WAWProcessIsolationPort):
            raise TypeError("isolation_port must be a WAWProcessIsolationPort")
        self._isolation_port = isolation_port
        self._timeout = float(timeout_seconds)
        self._terminate_grace = float(terminate_grace_seconds)

    async def probe(
        self, *, agent_type: AgentType, observed_vendor_version: str
    ) -> WAWVendorProbeEvidence:
        if type(agent_type) is not AgentType:
            raise WAWVendorProbeError("probe agent_type is invalid")
        if (
            type(observed_vendor_version) is not str
            or _VERSION.fullmatch(observed_vendor_version) is None
        ):
            raise WAWVendorProbeError("observed vendor version is invalid")
        profile = self._profiles[agent_type]
        if observed_vendor_version != profile.vendor_version:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNSUPPORTED,
                WAWVendorProbeFailure.VERSION_MISMATCH,
                None,
            )

        try:
            completion = await self._isolation_port.execute(
                profile,
                _PROBE_ARGUMENTS[profile.probe_id],
                timeout_seconds=self._timeout,
                output_limit=WAW_VENDOR_PROBE_OUTPUT_LIMIT,
                terminate_grace_seconds=self._terminate_grace,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.SPAWN_ERROR,
                None,
            )

        if type(completion) is not WAWIsolatedProbeCompletion:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.CLEANUP_UNPROVEN,
                None,
            )
        proof = completion.cleanup_proof
        if not self._isolation_port.validates(proof):
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.CLEANUP_UNPROVEN,
                completion.exit_code,
            )
        if type(completion.failure) is not WAWVendorProbeFailure:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.CLEANUP_UNPROVEN,
                completion.exit_code,
            )
        if completion.failure is not WAWVendorProbeFailure.NONE:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                completion.failure,
                completion.exit_code,
            )
        if not proof.complete:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.CLEANUP_UNPROVEN,
                completion.exit_code,
            )
        if (
            type(completion.exit_code) is not int
            or type(completion.stdout) is not bytes
            or type(completion.stderr) is not bytes
        ):
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.CLEANUP_UNPROVEN,
                completion.exit_code,
            )
        if len(completion.stdout) + len(completion.stderr) > WAW_VENDOR_PROBE_OUTPUT_LIMIT:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.OUTPUT_LIMIT,
                completion.exit_code,
            )
        try:
            completion.stdout.decode("utf-8", errors="strict")
            completion.stderr.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.NON_UTF8,
                completion.exit_code,
            )
        if profile.synthetic_test_only or not self._isolation_port.production_qualified:
            return self._evidence(
                profile,
                observed_vendor_version,
                WAWVendorProbeResult.UNKNOWN,
                WAWVendorProbeFailure.UNQUALIFIED_ISOLATION,
                completion.exit_code,
            )
        result = _parse(
            profile,
            exit_code=completion.exit_code,
            stdout=completion.stdout,
            stderr=completion.stderr,
        )
        return self._evidence(
            profile,
            observed_vendor_version,
            result,
            WAWVendorProbeFailure.NONE,
            completion.exit_code,
        )

    @staticmethod
    def _evidence(
        profile: WAWVendorProbeProfile,
        observed_vendor_version: str,
        result: WAWVendorProbeResult,
        failure: WAWVendorProbeFailure,
        exit_code: int | None,
    ) -> WAWVendorProbeEvidence:
        return WAWVendorProbeEvidence(
            profile.profile_id,
            profile.agent_type,
            observed_vendor_version,
            profile.probe_id,
            profile.parser_id,
            result,
            failure,
            exit_code,
        )


def _parse(
    profile: WAWVendorProbeProfile, *, exit_code: int, stdout: bytes, stderr: bytes
) -> WAWVendorProbeResult:
    if profile.parser_id is WAWVendorProbeParserId.CLAUDE_EXIT_STATUS_V1:
        if exit_code == 0:
            return WAWVendorProbeResult.AUTHENTICATED
        if exit_code == 1:
            return WAWVendorProbeResult.UNAUTHENTICATED
        return WAWVendorProbeResult.UNKNOWN
    if profile.parser_id is WAWVendorProbeParserId.CODEX_EXACT_STATUS_V1:
        if exit_code == 0:
            return WAWVendorProbeResult.AUTHENTICATED
        if (
            exit_code == 1
            and waw_vendor_probe_output_digest(stdout, stderr)
            == profile.codex_unauthenticated_output_sha256
        ):
            return WAWVendorProbeResult.UNAUTHENTICATED
        # No arbitrary non-zero Codex exit can be promoted to unauthenticated.
        return WAWVendorProbeResult.UNKNOWN
    raise AssertionError("closed parser ID was not handled")


__all__ = [
    "WAW_VENDOR_PROBE_OUTPUT_LIMIT",
    "WAW_VENDOR_PROBE_TERMINATE_GRACE_SECONDS",
    "WAW_VENDOR_PROBE_TIMEOUT_SECONDS",
    "WAWIsolatedProbeCompletion",
    "WAWProcessCleanupProof",
    "WAWProcessIsolationKind",
    "WAWProcessIsolationPort",
    "WAWVendorProbeError",
    "WAWVendorProbeEvidence",
    "WAWVendorProbeFailure",
    "WAWVendorProbeId",
    "WAWVendorProbeParserId",
    "WAWVendorProbeProfile",
    "WAWVendorProbeResult",
    "WAWVendorProbeRunner",
    "waw_vendor_probe_output_digest",
]
