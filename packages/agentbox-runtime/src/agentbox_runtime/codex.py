"""Codex CLI integration based only on public command behavior and safe OS evidence."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from agentbox_runtime.models import (
    AuthenticationState,
    CapabilityState,
    CodexCapabilities,
    CodexStatus,
    DiagnosticFinding,
    InstallationType,
    PairCodeResult,
    RemoteActionResult,
    RemoteState,
    RuntimeOperationError,
)
from agentbox_runtime.process import (
    ControlledProcessRunner,
    ExecutableIdentity,
    ProcessResult,
    inspect_executable,
    minimal_runtime_environment,
)
from agentbox_runtime.waw_conflicts import (
    WAWConflictCoordinator,
    WAWConflictError,
    WAWConflictLease,
)

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_SUBCOMMAND = re.compile(r"^\s{0,8}([a-z][a-z0-9-]*)\s{2,}", re.MULTILINE)
_PAIR_LINE = re.compile(
    r"^\s*(?:temporary\s+)?pair(?:ing)?\s+code\s*(?:is|:)?\s*" r"([A-Z0-9][A-Z0-9-]{3,63})\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_VERSION = re.compile(r"\bcodex(?:-cli)?\s+([^\s]+)", re.IGNORECASE)
_AUTHENTICATED = re.compile(r"\b(?:logged\s+in|authenticated)\b", re.IGNORECASE)
_UNAUTHENTICATED = re.compile(
    r"\b(?:not\s+logged\s+in|unauthenticated|authentication\s+required)\b",
    re.IGNORECASE,
)


def _text(value: bytes) -> str:
    return _ANSI.sub("", value.decode("utf-8", errors="replace")).replace("\x00", "")


def _commands(help_text: str) -> set[str]:
    return {match.group(1) for match in _SUBCOMMAND.finditer(help_text)}


def parse_pair_code(stdout: bytes, stderr: bytes) -> PairCodeResult:
    """Extract one labelled code and return no raw output on failure."""
    combined = f"{_text(stdout)}\n{_text(stderr)}"
    matches = {match.group(1) for match in _PAIR_LINE.finditer(combined)}
    if len(matches) != 1:
        raise RuntimeOperationError(
            "CODEX_PAIR_OUTPUT_UNRECOGNIZED",
            "Codex did not return a recognizable pairing code",
            category="broken",
        )
    code = matches.pop()
    if len(code) > 64:
        raise RuntimeOperationError(
            "CODEX_PAIR_OUTPUT_UNRECOGNIZED",
            "Codex did not return a recognizable pairing code",
            category="broken",
        )
    return PairCodeResult(code=code)


class CurrentUserProcessInspector:
    """Return only a boolean for a strict current-UID Codex Remote argv match."""

    def __init__(
        self,
        *,
        proc_root: Path = Path("/proc"),
        effective_uid: Callable[[], int] = os.geteuid,
    ) -> None:
        self._proc_root = proc_root
        self._effective_uid = effective_uid

    def is_remote_running(self, executable: Path) -> bool:
        proc = self._proc_root
        if not proc.is_dir():
            return False
        expected_uid = self._effective_uid()
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != expected_uid:
                    continue
                process_executable = (entry / "exe").resolve(strict=True)
                if process_executable != executable:
                    continue
                argv = (entry / "cmdline").read_bytes().split(b"\0")
            except (OSError, RuntimeError):
                continue
            decoded = [item.decode("utf-8", errors="replace") for item in argv if item]
            if "remote-control" in decoded and "start" in decoded:
                return True
        return False


class CodexAdapter:
    """Translate a fixed AgentBox action set into capability-checked Codex argv."""

    runtime_name = "codex"

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        runner: ControlledProcessRunner | None = None,
        process_inspector: CurrentUserProcessInspector | None = None,
    ) -> None:
        self._environment = minimal_runtime_environment(environment or os.environ)
        self._runner = runner or ControlledProcessRunner()
        self._process_inspector = process_inspector or CurrentUserProcessInspector()

    async def status(self) -> CodexStatus:
        selected, alternatives, diagnostics = self._resolve_installations()
        if selected is None:
            return CodexStatus(
                installed=False,
                version=None,
                selected_executable=None,
                diagnostics=(
                    *diagnostics,
                    DiagnosticFinding(
                        code="CODEX_NOT_INSTALLED",
                        severity="warning",
                        summary="Codex is not available on the Runtime PATH.",
                        remediation="Install Codex manually; installation management is deferred.",
                    ),
                ),
            )

        identity = inspect_executable(selected)
        owner_uid = identity.path.stat().st_uid
        if owner_uid not in {0, os.geteuid()}:
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_EXECUTABLE_OWNER_MISMATCH",
                    severity="warning",
                    summary="The selected Codex executable has an unexpected owner.",
                    remediation="Review ownership manually before production adoption.",
                )
            )
        try:
            version_result = await self._invoke(
                identity, ("--version",), timeout=8, allow_nonzero=True
            )
            version = self._parse_version(version_result)
        except RuntimeOperationError:
            version = None
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_VERSION_UNAVAILABLE",
                    severity="warning",
                    summary="The Codex version probe did not complete safely.",
                )
            )
        try:
            main_help: ProcessResult | None = await self._invoke(
                identity, ("--help",), timeout=8, allow_nonzero=True
            )
        except RuntimeOperationError:
            main_help = None
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_CAPABILITY_PROBE_FAILED",
                    severity="warning",
                    summary="Codex capability help could not be inspected.",
                )
            )
        capabilities = await self._capabilities(identity, main_help)
        authentication = await self._authentication(identity, main_help)
        installation_type, conflict, npm_diagnostics = await self._installation_type(
            selected, alternatives
        )
        remote_state, confidence = await self._remote_status(identity, capabilities)
        if Path("/etc/systemd/system/codex.service").exists():
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_LEGACY_UNIT_PRESENT",
                    severity="warning",
                    summary="A legacy codex.service exists and is not managed by AgentBox.",
                    remediation="Review the unit manually before host deployment.",
                )
            )
        if capabilities.status is CapabilityState.UNSUPPORTED:
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_REMOTE_STATUS_UNSUPPORTED",
                    severity="info",
                    summary="This Codex CLI does not advertise a Remote status command.",
                )
            )
        return CodexStatus(
            installed=True,
            version=version,
            selected_executable=str(selected),
            alternatives=tuple(str(path) for path in alternatives),
            installation_type=installation_type,
            conflict_detected=conflict,
            authentication=authentication,
            capabilities=capabilities,
            remote_state=remote_state,
            remote_confidence=confidence,
            diagnostics=tuple((*diagnostics, *npm_diagnostics)),
        )

    async def start_remote(self) -> RemoteActionResult:
        status = await self.status()
        identity = self._require_action(status, "start")
        if status.remote_state is RemoteState.RUNNING:
            return RemoteActionResult("already_running", RemoteState.RUNNING)
        result = await self._invoke(
            identity, ("remote-control", "start"), timeout=30, allow_nonzero=True
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "CODEX_REMOTE_START_FAILED", "Codex Remote could not be started"
            )
        return RemoteActionResult("started", RemoteState.RUNNING)

    async def stop_remote(self) -> RemoteActionResult:
        status = await self.status()
        identity = self._require_action(status, "stop")
        if status.remote_state is RemoteState.STOPPED:
            return RemoteActionResult("already_stopped", RemoteState.STOPPED)
        result = await self._invoke(
            identity, ("remote-control", "stop"), timeout=30, allow_nonzero=True
        )
        if result.exit_code != 0:
            raise RuntimeOperationError(
                "CODEX_REMOTE_STOP_FAILED", "Codex Remote could not be stopped"
            )
        return RemoteActionResult("stopped", RemoteState.STOPPED)

    async def generate_pair_code(self) -> PairCodeResult:
        status = await self.status()
        identity = self._require_action(status, "pair")
        if status.authentication is AuthenticationState.UNAUTHENTICATED:
            raise RuntimeOperationError(
                "CODEX_UNAUTHENTICATED",
                "Codex authentication is required",
                category="unauthenticated",
            )
        try:
            result = await self._invoke(
                identity,
                ("remote-control", "pair"),
                timeout=30,
                stdout_limit=4096,
                stderr_limit=4096,
                allow_nonzero=True,
                sensitive_output=True,
            )
        except RuntimeOperationError as exc:
            if exc.code == "CODEX_COMMAND_TIMEOUT":
                raise RuntimeOperationError(
                    "CODEX_PAIR_TIMEOUT",
                    "Codex pairing timed out",
                    category="timeout",
                    retryable=True,
                ) from exc
            raise
        if result.exit_code != 0:
            raise RuntimeOperationError("CODEX_PAIR_FAILED", "Codex pairing failed")
        return parse_pair_code(result.stdout, result.stderr)

    def _resolve_installations(
        self,
    ) -> tuple[Path | None, tuple[Path, ...], list[DiagnosticFinding]]:
        path_value = self._environment.get("PATH", "")
        selected_raw = shutil.which("codex", path=path_value)
        candidates: list[Path] = []
        diagnostics: list[DiagnosticFinding] = []
        for directory in path_value.split(os.pathsep):
            if not directory:
                continue
            candidate = Path(directory) / "codex"
            if candidate.exists() or candidate.is_symlink():
                absolute = candidate.absolute()
                if absolute not in candidates:
                    candidates.append(absolute)
        valid_candidates: list[Path] = []
        identities: set[Path] = set()
        for candidate in candidates:
            try:
                resolved = inspect_executable(candidate).path
            except RuntimeOperationError:
                diagnostics.append(
                    DiagnosticFinding(
                        code="CODEX_ALTERNATIVE_INVALID",
                        severity="warning",
                        summary="A Codex PATH candidate is not a safe executable.",
                    )
                )
                continue
            if resolved not in identities:
                identities.add(resolved)
                valid_candidates.append(candidate)
        if selected_raw is None:
            return None, tuple(valid_candidates), diagnostics
        selected = Path(selected_raw).absolute()
        try:
            selected_identity = inspect_executable(selected).path
        except RuntimeOperationError:
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_EXECUTABLE_INVALID",
                    severity="warning",
                    summary="The selected Codex command is not a safe executable.",
                )
            )
            return None, tuple(valid_candidates), diagnostics
        alternatives = tuple(
            candidate
            for candidate in valid_candidates
            if inspect_executable(candidate).path != selected_identity
        )
        if alternatives:
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_MULTIPLE_EXECUTABLES",
                    severity="warning",
                    summary="Multiple distinct Codex executables were found on PATH.",
                    remediation="Select one Runtime installation explicitly in a later phase.",
                )
            )
        return selected, alternatives, diagnostics

    async def _capabilities(
        self, identity: ExecutableIdentity, main_help: ProcessResult | None
    ) -> CodexCapabilities:
        if main_help is None or main_help.exit_code != 0:
            return CodexCapabilities()
        combined_main_help = _text(main_help.stdout) + "\n" + _text(main_help.stderr)
        main_commands = _commands(combined_main_help)
        if not main_commands or "commands:" not in combined_main_help.lower():
            return CodexCapabilities()
        if "remote-control" not in main_commands:
            return CodexCapabilities(
                remote_control=CapabilityState.UNSUPPORTED,
                start=CapabilityState.UNSUPPORTED,
                stop=CapabilityState.UNSUPPORTED,
                pair=CapabilityState.UNSUPPORTED,
                status=CapabilityState.UNSUPPORTED,
            )
        try:
            remote_help = await self._invoke(
                identity, ("remote-control", "--help"), timeout=8, allow_nonzero=True
            )
        except RuntimeOperationError:
            return CodexCapabilities(remote_control=CapabilityState.SUPPORTED)
        if remote_help.exit_code != 0:
            return CodexCapabilities(remote_control=CapabilityState.UNKNOWN)
        remote_commands = _commands(_text(remote_help.stdout) + "\n" + _text(remote_help.stderr))
        if not remote_commands:
            return CodexCapabilities(remote_control=CapabilityState.UNKNOWN)

        def state(command: str) -> CapabilityState:
            return (
                CapabilityState.SUPPORTED
                if command in remote_commands
                else CapabilityState.UNSUPPORTED
            )

        return CodexCapabilities(
            remote_control=CapabilityState.SUPPORTED,
            start=state("start"),
            stop=state("stop"),
            pair=state("pair"),
            status=state("status"),
        )

    async def _authentication(
        self, identity: ExecutableIdentity, main_help: ProcessResult | None
    ) -> AuthenticationState:
        if main_help is None or main_help.exit_code != 0:
            return AuthenticationState.UNKNOWN
        main_commands = _commands(_text(main_help.stdout) + "\n" + _text(main_help.stderr))
        if "login" not in main_commands:
            return AuthenticationState.UNKNOWN
        try:
            login_help = await self._invoke(
                identity, ("login", "--help"), timeout=8, allow_nonzero=True
            )
        except RuntimeOperationError:
            return AuthenticationState.UNKNOWN
        if login_help.exit_code != 0 or "status" not in _commands(
            _text(login_help.stdout) + "\n" + _text(login_help.stderr)
        ):
            return AuthenticationState.UNKNOWN
        try:
            result = await self._invoke(
                identity, ("login", "status"), timeout=8, allow_nonzero=True
            )
        except RuntimeOperationError:
            return AuthenticationState.UNKNOWN
        output = f"{_text(result.stdout)}\n{_text(result.stderr)}"
        if _UNAUTHENTICATED.search(output):
            return AuthenticationState.UNAUTHENTICATED
        if result.exit_code == 0 and _AUTHENTICATED.search(output):
            return AuthenticationState.AUTHENTICATED
        return AuthenticationState.UNKNOWN

    async def _installation_type(
        self, selected: Path, alternatives: tuple[Path, ...]
    ) -> tuple[InstallationType, bool, tuple[DiagnosticFinding, ...]]:
        npm_path = shutil.which("npm", path=self._environment.get("PATH", ""))
        home = Path(self._environment.get("HOME", "/nonexistent"))
        standalone_hint = selected == home / ".local" / "bin" / "codex"
        npm_detected = False
        diagnostics: list[DiagnosticFinding] = []
        if npm_path:
            try:
                npm_identity = inspect_executable(Path(npm_path).absolute())
                result = await self._runner.run(
                    npm_identity,
                    ("list", "-g", "--depth=0", "--json"),
                    environment=self._environment,
                    cwd=self._runtime_home(),
                    timeout_seconds=10,
                    stdout_limit=64 * 1024,
                    stderr_limit=8192,
                )
                if result.exit_code in (0, 1):
                    payload = json.loads(_text(result.stdout) or "{}")
                    dependencies = payload.get("dependencies", {})
                    if isinstance(dependencies, dict):
                        npm_detected = any(
                            name.lower() in {"@openai/codex", "codex"} for name in dependencies
                        )
            except (RuntimeOperationError, json.JSONDecodeError, OSError):
                diagnostics.append(
                    DiagnosticFinding(
                        code="CODEX_NPM_DETECTION_UNKNOWN",
                        severity="info",
                        summary="npm Codex package detection was inconclusive.",
                    )
                )
        conflict = bool(alternatives) or (standalone_hint and npm_detected)
        if conflict:
            diagnostics.append(
                DiagnosticFinding(
                    code="CODEX_INSTALLATION_CONFLICT",
                    severity="warning",
                    summary="Standalone and npm Codex evidence conflict.",
                    remediation=(
                        "Keep one explicit Runtime selection; do not uninstall automatically."
                    ),
                )
            )
            return InstallationType.CONFLICT, True, tuple(diagnostics)
        if npm_detected:
            return InstallationType.NPM, False, tuple(diagnostics)
        if standalone_hint:
            return InstallationType.STANDALONE, False, tuple(diagnostics)
        return InstallationType.UNKNOWN, False, tuple(diagnostics)

    async def _remote_status(
        self, identity: ExecutableIdentity, capabilities: CodexCapabilities
    ) -> tuple[RemoteState, str]:
        if capabilities.status is CapabilityState.SUPPORTED:
            try:
                result = await self._invoke(
                    identity,
                    ("remote-control", "status"),
                    timeout=8,
                    allow_nonzero=True,
                )
            except RuntimeOperationError:
                return RemoteState.BROKEN, "reported"
            output = f"{_text(result.stdout)}\n{_text(result.stderr)}".lower()
            if re.search(r"\b(stopped|inactive|not running)\b", output):
                return RemoteState.STOPPED, "reported"
            if result.exit_code == 0 and re.search(r"\b(running|active)\b", output):
                return RemoteState.RUNNING, "reported"
            if result.exit_code != 0:
                return RemoteState.BROKEN, "reported"
        if self._process_inspector.is_remote_running(identity.path):
            return RemoteState.RUNNING, "inferred"
        return RemoteState.UNKNOWN, "unknown"

    def _require_action(self, status: CodexStatus, action: str) -> ExecutableIdentity:
        if not status.installed or status.selected_executable is None:
            raise RuntimeOperationError(
                "CODEX_NOT_INSTALLED", "Codex is not installed", category="unavailable"
            )
        capability = getattr(status.capabilities, action)
        if capability is not CapabilityState.SUPPORTED:
            code = "CODEX_PAIR_UNSUPPORTED" if action == "pair" else "CODEX_REMOTE_UNSUPPORTED"
            raise RuntimeOperationError(
                code,
                "The installed Codex CLI does not advertise this action",
                category="unsupported",
            )
        return inspect_executable(Path(status.selected_executable))

    async def _invoke(
        self,
        identity: ExecutableIdentity,
        arguments: tuple[str, ...],
        *,
        timeout: float,
        stdout_limit: int = 64 * 1024,
        stderr_limit: int = 16 * 1024,
        allow_nonzero: bool = False,
        sensitive_output: bool = False,
    ) -> ProcessResult:
        cwd = self._runtime_home()
        result = await self._runner.run(
            identity,
            arguments,
            environment=self._environment,
            cwd=cwd,
            timeout_seconds=timeout,
            stdout_limit=stdout_limit,
            stderr_limit=stderr_limit,
            sensitive_output=sensitive_output,
        )
        if result.exit_code != 0 and not allow_nonzero:
            raise RuntimeOperationError("CODEX_COMMAND_FAILED", "Codex command failed")
        return result

    def _runtime_home(self) -> Path:
        home = Path(self._environment.get("HOME", ""))
        if not home.is_absolute() or not home.is_dir():
            raise RuntimeOperationError(
                "CODEX_WORKING_DIRECTORY_INVALID",
                "Codex Runtime HOME is unavailable",
                category="unavailable",
            )
        return home

    @staticmethod
    def _parse_version(result: ProcessResult) -> str | None:
        if result.exit_code != 0:
            return None
        match = _VERSION.search(f"{_text(result.stdout)}\n{_text(result.stderr)}")
        return match.group(1)[:64] if match else None


class CodexManager:
    """Serialize Runtime actions and rate-limit Pair generation in process."""

    def __init__(
        self,
        adapter: CodexAdapter,
        *,
        pair_cooldown_seconds: int = 10,
        monotonic: Callable[[], float] = time.monotonic,
        conflict_coordinator: WAWConflictCoordinator | None = None,
    ) -> None:
        self._adapter = adapter
        self._lock = asyncio.Lock()
        self._pair_cooldown_seconds = pair_cooldown_seconds
        self._monotonic = monotonic
        self._last_pair_request: float | None = None
        if (
            conflict_coordinator is not None
            and type(conflict_coordinator) is not WAWConflictCoordinator
        ):
            raise TypeError("conflict_coordinator must be WAWConflictCoordinator")
        self._conflicts = conflict_coordinator

    @property
    def conflict_coordinator(self) -> WAWConflictCoordinator | None:
        return self._conflicts

    def bind_conflict_coordinator(self, coordinator: WAWConflictCoordinator) -> None:
        """Install the host coordinator once when fixed WAW composition is enabled."""

        if type(coordinator) is not WAWConflictCoordinator:
            raise TypeError("coordinator must be WAWConflictCoordinator")
        if self._conflicts is not None:
            raise RuntimeOperationError(
                "WAW_CONFLICT_COORDINATOR_BOUND",
                "Codex conflict coordinator is already bound",
                category="conflict",
            )
        self._conflicts = coordinator

    async def status(self) -> CodexStatus:
        return await self._adapter.status()

    async def start_remote(self) -> RemoteActionResult:
        async with self._lock:
            lease = await self._acquire_conflict_lease()
            try:
                return await self._adapter.start_remote()
            finally:
                if lease is not None:
                    lease.release()

    async def stop_remote(self) -> RemoteActionResult:
        async with self._lock:
            return await self._adapter.stop_remote()

    async def generate_pair_code(self) -> PairCodeResult:
        async with self._lock:
            now = self._monotonic()
            if self._last_pair_request is not None:
                remaining = self._pair_cooldown_seconds - (now - self._last_pair_request)
                if remaining > 0:
                    raise RuntimeOperationError(
                        "CODEX_PAIR_RATE_LIMITED",
                        "A new pairing code was requested too recently",
                        category="rate_limited",
                        retryable=True,
                        retry_after=max(1, int(remaining + 0.999)),
                    )
            self._last_pair_request = now
            return await self._adapter.generate_pair_code()

    async def _acquire_conflict_lease(self) -> WAWConflictLease | None:
        if self._conflicts is None:
            return None
        task = asyncio.create_task(asyncio.to_thread(self._conflicts.acquire_legacy_codex_start))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            lease: WAWConflictLease | None = None
            while True:
                try:
                    lease = await asyncio.shield(task)
                    break
                except asyncio.CancelledError:
                    if task.done():
                        break
                    continue
                except WAWConflictError:
                    break
            if lease is not None:
                lease.release()
            raise
        except WAWConflictError as exc:
            raise RuntimeOperationError(
                exc.code,
                "WAW Runtime conflicts with legacy Codex Remote start",
                category="conflict",
            ) from exc
