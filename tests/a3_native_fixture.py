"""CI-only separate-process A3 fixture; no product import or host activation.

Only Runtime imports the A3 reader/key owner. API has its own database and sees
metadata/ciphertext. The optional root supervisor drops both children to distinct
unregistered numeric UIDs, so static-byte and Runtime-file denial is measured,
not inferred from a same-UID chmod. No accounts or system services are created.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ID = "prj_" + "a" * 32
HOST_ID = "wri_" + "c" * 32
BUILD_ID = "d" * 64
# Published public X25519 fixture pin. Private bytes are constructed only in Runtime.
PIN = "8f40c5adb68f25624ae5b214ea767a6ec94d829d3d7b5e1ad1ba6f3e2138285f"
USERNAME = "native-fixture"
PASSWORD = "published synthetic native fixture password"
SYNTHETIC_SECRET = "published-synthetic-test-only-secret-00000000"
REPOSITORY = Path(__file__).resolve().parents[1]
_MAX_CONTROL = 64 * 1024


class _PublicationWitness:
    """Opt-in test evidence: fixed scalar counters, no event or payload export.

    Overflow or a failed invariant latches failure. Saturation must never let
    equal counters stand in for complete coverage after observations were lost.
    """

    LIMIT = 65535
    FIELDS = {
        "runtime": (
            "records_started",
            "publish_checks",
            "precheck_active",
            "checked_matches",
            "published",
            "ack_matches",
        ),
        "api": (
            "ready_received",
            "records_received",
            "complete_received",
            "current_received",
            "current_replied",
            "checked_received",
            "checked_matches",
            "ack_received",
            "ack_matches",
            "live_received",
            "live_matches",
        ),
    }

    def __init__(self, role: str) -> None:
        self._counts = dict.fromkeys(self.FIELDS[role], 0)
        self._failed = False
        self._lock = threading.Lock()

    def add(self, field: str, *, matched: bool = True, sequence: object = None) -> None:
        with self._lock:
            if self._failed or field not in self._counts or matched is not True:
                self._failed = True
                return
            if sequence is not None and (
                type(sequence) is not int or sequence != self._counts[field] + 1
            ):
                self._failed = True
                return
            if self._counts[field] >= self.LIMIT:
                self._failed = True
                return
            self._counts[field] += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            if self._failed:
                raise RuntimeError("fixture publication witness invalid")
            return dict(self._counts)


_CHILD_BOOTSTRAP = r"""
import json, os, stat, sys
stage = "parent-fence"
try:
    import ctypes
    parent = os.getppid()
    if ctypes.CDLL(None).prctl(1, 15, 0, 0, 0) != 0 or parent == 1 or os.getppid() != parent:
        raise RuntimeError()
    stage = "source-access"
    source, role = sys.argv[1:]
    fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
            raise ValueError()
        program = stream.read(131073)
    if len(program) > 131072:
        raise ValueError()
    stage = "source-exec"
    sys.argv = [source, role]
    exec(compile(program, source, "exec"), {"__name__": "__main__", "__file__": source})
except SystemExit:
    raise
except BaseException as error:
    print(json.dumps({"error": type(error).__name__, "phase": stage}), flush=True)
    raise SystemExit(1) from None
"""


def _emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), flush=True)


def _read() -> dict[str, Any]:
    line = sys.stdin.buffer.readline(_MAX_CONTROL + 1)
    if not line or len(line) > _MAX_CONTROL or not line.endswith(b"\n"):
        raise EOFError("fixture control closed")
    value = json.loads(line)
    if type(value) is not dict:
        raise ValueError("fixture control invalid")
    return value


class FixtureChildError(RuntimeError):
    """Value-free child phase/type diagnostic, never exception values or wire data."""

    def __init__(self, role: str, phase: str, code: object, exit_code: object = None) -> None:
        allowed = {
            "AssertionError",
            "AttributeError",
            "BrokenPipeError",
            "ChildProcessError",
            "ChildExited",
            "ConnectionError",
            "ContentError",
            "EOFError",
            "FileNotFoundError",
            "ImportError",
            "KeyError",
            "ModuleNotFoundError",
            "OSError",
            "PermissionError",
            "RuntimeError",
            "TimeoutError",
            "TypeError",
            "ValueError",
        }
        self.role = role if role in {"api", "runtime"} else "child"
        self.phase = (
            phase
            if phase
            in {
                "spawn",
                "control",
                "bootstrap-eof",
                "parent-fence",
                "source-access",
                "source-exec",
                "dependency-access",
                "protocol",
                "source-probe",
            }
            else "control"
        )
        self.exit_code = exit_code if type(exit_code) is int and -255 <= exit_code <= 255 else None
        self.code = code if type(code) is str and code in allowed else "ChildError"
        super().__init__(f"{self.role}:{self.phase}:{self.code}")


def fixture_error_diagnostic(error: BaseException) -> dict[str, object]:
    """Keep a grouped setup failure's primary type without exposing values."""
    diagnostic: dict[str, object] = {"code": type(error).__name__}
    primary = error
    for _ in range(8):
        if not isinstance(primary, BaseExceptionGroup):
            break
        diagnostic["cleanup_failed"] = True
        primary = primary.exceptions[0]
    if primary is not error:
        diagnostic["primary_code"] = type(primary).__name__
    if isinstance(primary, FixtureChildError):
        diagnostic.update(role=primary.role, phase=primary.phase, child_code=primary.code)
        if primary.exit_code is not None:
            diagnostic["exit_code"] = primary.exit_code
    return diagnostic


class FixtureDirectory:
    """Supervisor-owned cleanup capability for one existing test directory.

    The only recursive target is its fixed ``processes`` child. Retained directory
    descriptors and shutil's fd-relative symlink-safe removal prevent a changed
    pathname or child symlink from expanding this already authorized cleanup.
    Node continues to own browser/static artifacts and removes those afterwards.
    """

    def __init__(self, root: Path, static: Path) -> None:
        if not root.is_absolute() or root.resolve(strict=True) != root:
            raise ValueError("fixture directory must be an exact absolute path")
        if not root.name.startswith("a3n-") or static != root / "static":
            raise ValueError("fixture directory scope mismatch")
        if not shutil.rmtree.avoids_symlink_attacks:
            raise RuntimeError("fd-relative fixture cleanup unavailable")
        self._fds: list[int] = []
        self._closed = False
        self._failure: BaseException | None = None
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            self._root = os.open(root, flags | os.O_DIRECTORY)
            self._fds.append(self._root)
            self._static = os.open("static", flags | os.O_DIRECTORY, dir_fd=self._root)
            self._fds.append(self._static)
            self._index = os.open("index.html", flags | os.O_NONBLOCK, dir_fd=self._static)
            self._fds.append(self._index)
            self._index_owner = os.fstat(self._index)
            if not stat.S_ISREG(self._index_owner.st_mode) or self._index_owner.st_nlink != 1:
                raise ValueError("fixture index must be a unique regular file")
            self._owner = os.fstat(self._static)
        except BaseException:
            self._release()
            raise

    def isolate_static(self) -> None:
        if os.geteuid() != 0:
            raise PermissionError("CI isolation root missing")
        os.fchown(self._index, 0, 0)
        os.fchown(self._static, 0, 0)

    def _release(self) -> None:
        descriptors, self._fds = self._fds, []
        failures: list[Exception] = []
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except Exception as error:
                failures.append(error)
        self._closed = True
        if failures:
            raise ExceptionGroup("fixture descriptor retirement failed", failures)

    def close(self, fixture: A3NativeFixture | None) -> None:
        if self._closed:
            if self._failure is not None:
                raise self._failure
            return
        errors: list[Exception] = []
        failure: BaseException | None = None
        try:
            if fixture is not None:
                try:
                    fixture.close()
                except Exception as error:
                    errors.append(error)
                if any(
                    child and child.process.poll() is None
                    for child in (fixture.api, fixture.runtime)
                ):
                    raise RuntimeError("fixture children still live; filesystem cleanup refused")
            try:
                shutil.rmtree("processes", dir_fd=self._root)
            except FileNotFoundError:
                pass
            except Exception as error:
                errors.append(error)
            try:
                if os.geteuid() == 0:
                    os.fchown(self._index, self._index_owner.st_uid, self._index_owner.st_gid)
                    os.fchown(self._static, self._owner.st_uid, self._owner.st_gid)
                os.fchmod(self._static, 0o755)
            except Exception as error:
                errors.append(error)
            if errors:
                raise ExceptionGroup("fixture supervisor cleanup failed", errors)
        except BaseException as error:
            failure = error
        try:
            self._release()
        except BaseException as error:
            failure = (
                error
                if failure is None
                else BaseExceptionGroup("fixture cleanup and retirement failed", [failure, error])
            )
        self._failure = failure
        if failure is not None:
            raise failure


def _fixture_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "PYTHONPATH", "PYTHONHOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ"}
    }
    environment.update(
        {"HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    )
    return environment


class _Child:
    def __init__(
        self, role: str, uid: int | None, gid: int | None, *, source_root: Path | None = None
    ) -> None:
        environment = _fixture_environment()
        checkout = source_root or REPOSITORY
        if source_root is not None:
            from a3_native_sources import PACKAGE_DIRS

            environment["PYTHONPATH"] = os.pathsep.join(
                str(source_root / Path(path).parent) for path in PACKAGE_DIRS
            )
        self.role = role
        self._lock = threading.Lock()
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _CHILD_BOOTSTRAP,
                    str(checkout / "tests/a3_native_fixture.py"),
                    role,
                ],
                cwd=checkout,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                user=uid,
                group=gid,
                extra_groups=[] if uid is not None else None,
            )
        except OSError as error:
            raise FixtureChildError(role, "spawn", type(error).__name__) from None

    def call(
        self, value: dict[str, Any], timeout: float = 10, *, deadline: float | None = None
    ) -> Any:
        lock_timeout = -1 if deadline is None else max(0, deadline - time.monotonic())
        if not self._lock.acquire(timeout=lock_timeout):
            raise TimeoutError("fixture child control timed out")
        try:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("fixture child control timed out")
            assert self.process.stdin is not None and self.process.stdout is not None
            raw = json.dumps(value).encode() + b"\n"
            if len(raw) > _MAX_CONTROL:
                raise ValueError("fixture control exceeded limit")
            self.process.stdin.write(raw)
            self.process.stdin.flush()
            if deadline is not None:
                timeout = min(timeout, deadline - time.monotonic())
                if timeout <= 0:
                    raise TimeoutError("fixture child control timed out")
            line: bytes | bytearray
            if deadline is None:
                # Preserve the legacy fixture control path unless opted in by a caller.
                if not select.select([self.process.stdout], [], [], timeout)[0]:
                    raise TimeoutError("fixture child control timed out")
                line = self.process.stdout.readline(_MAX_CONTROL + 1)
            else:
                end = min(time.monotonic() + timeout, deadline)
                line = bytearray()
                # One request is outstanding; consume only its bounded line.
                # Readability of a partial line cannot renew the caller's budget.
                while not line.endswith(b"\n") and len(line) <= _MAX_CONTROL:
                    remaining = end - time.monotonic()
                    if (
                        remaining <= 0
                        or not select.select([self.process.stdout], [], [], remaining)[0]
                    ):
                        raise TimeoutError("fixture child control timed out")
                    part = os.read(
                        self.process.stdout.fileno(), min(4096, _MAX_CONTROL + 1 - len(line))
                    )
                    if not part:
                        break
                    line.extend(part)
            if not line:
                try:
                    exit_code = self.process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    exit_code = None
                raise FixtureChildError(self.role, "bootstrap-eof", "ChildExited", exit_code)
            if len(line) > _MAX_CONTROL or (deadline is not None and not line.endswith(b"\n")):
                raise FixtureChildError(self.role, "protocol", "ValueError")
            try:
                result = json.loads(line)
            except ValueError:
                raise FixtureChildError(self.role, "protocol", "ValueError") from None
            if type(result) is not dict:
                raise FixtureChildError(self.role, "protocol", "TypeError")
            # A readable pipe or successful decode after expiry is not success.
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("fixture child control timed out")
            if "error" in result:
                phase = result.get("phase", "control")
                raise FixtureChildError(
                    self.role, phase if type(phase) is str else "control", result["error"]
                )
            return result
        finally:
            self._lock.release()

    def close(self) -> None:
        failure: RuntimeError | None = None
        if self.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.send_signal(signal.SIGCONT)
            with contextlib.suppress(Exception):
                self.call({"op": "close"}, timeout=2)
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
                failure = RuntimeError("fixture child did not complete bounded graceful cleanup")
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe is not None:
                pipe.close()
        if failure is not None:
            raise failure


class A3NativeFixture:
    """Supervisor only; never imported into either product API or Runtime."""

    def __init__(
        self,
        root: Path,
        *,
        origin: str,
        static_root: Path,
        isolated: bool = False,
        retain: Callable[[A3NativeFixture], None] | None = None,
        publication_witnesses: bool = False,
    ) -> None:
        if isolated and os.geteuid() != 0:
            raise PermissionError("numeric UID isolation requires the CI root supervisor")
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o755)
        self.root, self.isolated = root, isolated
        self.publication_witnesses = publication_witnesses
        self.api: _Child | None = None
        self.runtime: _Child | None = None
        # The supervisor retains this exact owner BEFORE any child is spawned.
        # A raising constructor must not hide a partially initialized live child.
        if retain is not None:
            retain(self)
        uid_api, uid_runtime = (61131, 61132) if isolated else (os.getuid(), os.getuid())
        gid_api, gid_runtime = (61131, 61132) if isolated else (os.getgid(), os.getgid())
        for name, uid, gid, mode in (
            ("api", uid_api, gid_api, 0o700),
            ("runtime", uid_runtime, gid_runtime, 0o700),
            ("transport", uid_runtime, gid_runtime, 0o711),
        ):
            path = root / name
            path.mkdir(mode=mode)
            if isolated:
                os.chown(path, uid, gid)
        source_root: Path | None = None
        source_proof: dict[str, Any] = {"source_staged": False}
        if isolated:
            from a3_native_sources import prepare_sources

            source_root, source_proof = prepare_sources(REPOSITORY, root, _fixture_environment())
        # Socket pathname stays below Linux's 108-byte sun_path limit.
        socket_path = root / "transport" / "a3.sock"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        self.api_origin = f"http://127.0.0.1:{port}"
        try:
            # Both process identities exist BEFORE any connected stream is created.
            self.api = _Child(
                "api",
                uid_api if isolated else None,
                gid_api if isolated else None,
                source_root=source_root,
            )
            self.runtime = _Child(
                "runtime",
                uid_runtime if isolated else None,
                gid_runtime if isolated else None,
                source_root=source_root,
            )
            runtime = self.runtime.call(
                {
                    "op": "init",
                    "root": str(root / "runtime"),
                    "socket": str(socket_path),
                    "api_pid": self.api.process.pid,
                    "api_uid": uid_api,
                    "api_gid": gid_api,
                    "publication_witnesses": publication_witnesses,
                }
            )
            api = self.api.call(
                {
                    "op": "init",
                    "root": str(root / "api"),
                    "socket": str(socket_path),
                    "runtime_root": str(root / "runtime"),
                    "runtime_pid": self.runtime.process.pid,
                    "runtime_uid": uid_runtime,
                    "runtime_gid": gid_runtime,
                    "origin": origin,
                    "api_origin": self.api_origin,
                    "port": port,
                    "metadata": runtime["metadata"],
                    "static_root": str(static_root),
                    "isolated": isolated,
                    "publication_witnesses": publication_witnesses,
                }
            )
            self.proof = {
                "api_pid": self.api.process.pid,
                "runtime_pid": self.runtime.process.pid,
                "supervisor_pid": os.getpid(),
                "isolated": isolated,
                **source_proof,
                **api,
            }
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup:
                raise BaseExceptionGroup(
                    "fixture setup and cleanup failed", [primary, cleanup]
                ) from None
            raise

    def call(
        self, op: str, payload: dict[str, Any] | None = None, *, deadline: float | None = None
    ) -> Any:
        value = {"op": op, **(payload or {})}
        if op == "runtime-status":
            assert self.runtime
            return self.runtime.call({"op": "status"}, deadline=deadline)
        if op == "status":
            assert self.runtime and self.api
            return {
                **self.runtime.call(value, deadline=deadline),
                **self.api.call(value, deadline=deadline),
                **self.proof,
            }
        if op == "publication-status":
            if not self.publication_witnesses:
                raise ValueError("fixture publication witnesses disabled")
            assert self.runtime and self.api
            return {
                "runtime": self.runtime.call(value, deadline=deadline),
                "api": self.api.call(value, deadline=deadline),
            }
        if op in {"revoke", "auth-epoch", "project", "epoch", "peer"}:
            assert self.api
            return self.api.call(value, deadline=deadline)
        if op in {"pause-api", "resume-api", "exit-api", "exit-runtime"}:
            target = self.runtime if op == "exit-runtime" else self.api
            assert target
            target.process.send_signal(
                signal.SIGSTOP
                if op == "pause-api"
                else signal.SIGCONT if op == "resume-api" else signal.SIGTERM
            )
            return {"ok": True}
        assert self.runtime
        return self.runtime.call(value, deadline=deadline)

    def close(self) -> None:
        failures: list[Exception] = []
        for child in (self.api, self.runtime):
            if child:
                try:
                    child.close()
                except Exception as error:
                    failures.append(error)
        if failures:
            raise ExceptionGroup("fixture process cleanup failed", failures)


def _no_host(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("native A3 fixture must not activate host resources")


def _populate_patch_project(project: Path, *, publication_witnesses: bool = False) -> None:
    """Create real staged Git changes; only synthetic fixture bytes are committed."""
    project.mkdir(parents=True)

    def git(*arguments: str) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(project),
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.hooksPath=/dev/null",
                *arguments,
            ],
            check=True,
            capture_output=True,
            env=_fixture_environment(),
        )

    git("init", "-q", "--template=")
    for name, raw in {
        "modify.txt": "上下文 α\nold value\n尾部 Ω\n".encode(),
        "delete.txt": "removed first\n删除第二行 🌍\n".encode(),
        "multiple-hunks.txt": "".join(
            f"context {number:02d}\n" for number in range(1, 31)
        ).encode(),
        "crlf.txt": b"CRLF context\r\nold CRLF\r\nCRLF tail\r\n",
        "no-final-newline.txt": b"line one\nold tail",
    }.items():
        (project / name).write_bytes(raw)
    if publication_witnesses:
        (project / "modified.txt").write_text("original synthetic content\n", encoding="utf-8")
    git("add", "--", ".")
    # Identity is limited to this synthetic commit command, never global config.
    git(
        "-c",
        "user.name=AgentBox synthetic fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--no-gpg-sign",
        "-qm",
        "Synthetic native diff baseline",
    )
    lines = [f"context {number:02d}\n" for number in range(1, 31)]
    lines[1] = "first changed 🌍\n"
    lines[28] = "last changed 中文\n"
    for name, raw in {
        "success.txt": (
            "A3 native complete diff\n<img src=x onerror=window.a3Executed=true>\n"
            '<a href="https://example.invalid/a3">inert link</a>\n'
            "<script>window.a3Executed=true</script>\n" + ("x" * 6000 + "\n") * 4 + "🌍\n"
        ).encode(),
        "modify.txt": "上下文 α\nnew value 🌍\n尾部 Ω\n".encode(),
        "multiple-hunks.txt": "".join(lines).encode(),
        "crlf.txt": b"CRLF context\r\nnew CRLF\r\nCRLF tail\r\n",
        "no-final-newline.txt": "line one\n新尾 🌍".encode(),
        "long-line.txt": ("long-line raw fallback\n" + "L" * 9000 + "\n完整末尾 🌍\n").encode(),
        "binary.bin": b"synthetic\0binary\n",
        "large.txt": b"L" * 210000 + b"\n",
        ".env": b"synthetic denied path only\n",
    }.items():
        (project / name).write_bytes(raw)
    (project / "delete.txt").unlink()
    if publication_witnesses:
        (project / "modified.txt").write_text("staged secret-canary content\n", encoding="utf-8")
    git("add", "--", ".")
    if publication_witnesses:
        (project / "modified.txt").write_text("unstaged-exclusion-canary\n", encoding="utf-8")
    (project / "success.txt").write_text("unstaged-exclusion-canary\n")
    (project / "unstaged-only.txt").write_text("untracked fixture only\n")


async def _runtime(config: dict[str, Any]) -> None:
    # No Runtime authority, patch reader or key imports occur in the API child.
    from agentbox_protocol.a3_crypto import A3Runtime
    from agentbox_protocol.a3_transport import NativeFrame, NativeKind
    from agentbox_runtime.a3_native_transport import (
        A3NativeReadOwner,
        A3NativeReservation,
        _NativeOpaquePort,
    )
    from agentbox_runtime.git import GitAdapter
    from agentbox_runtime.git_changes import parse_git_change_page
    from agentbox_runtime.git_staged_reader import GitStagedPatchReader
    from agentbox_runtime.process import ControlledProcessRunner, ProcessResult
    from agentbox_runtime.project import ProjectRegistry
    from agentbox_runtime.waw_lifecycle import WAWLifecycleRegistry, WAWProjectBinding
    from agentbox_runtime.waw_peer_authority import WAWPeerAuthority
    from agentbox_runtime.waw_pty import PtyGeometry
    from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor

    # Runtime-only fault injection; no plaintext, crypto key or record crosses
    # the supervisor control pipe. Product classes remain unmodified on disk.
    fault: dict[str, Any] = {"mode": "normal", "held": False, "end": None}
    release = asyncio.Event()
    original_encrypt = A3Runtime.encrypt_record
    original_send = _NativeOpaquePort.send
    witness = _PublicationWitness("runtime") if config.get("publication_witnesses") else None

    if witness is not None:
        original_execute = A3NativeReservation._execute

        async def execute(
            self: A3NativeReservation, frame: NativeFrame, deadline: int
        ) -> tuple[NativeKind, dict[str, object]]:
            assert witness is not None
            if frame.kind is NativeKind.PUBLISH_CHECK:
                witness.add("publish_checks")
                # Same Runtime loop and original owner, before the real check.
                witness.add("precheck_active", matched=self._owner.selectors._active == 1)
            result = await original_execute(self, frame, deadline)
            if frame.kind in {NativeKind.PUBLISH_CHECK, NativeKind.PUBLISHED}:
                port = self._port
                expected = (
                    NativeKind.CHECKED if frame.kind is NativeKind.PUBLISH_CHECK else NativeKind.ACK
                )
                field = "checked_matches" if expected is NativeKind.CHECKED else "ack_matches"
                witness.add(
                    field,
                    matched=(
                        port is not None
                        and isinstance(frame.payload, dict)
                        and frame.payload == port.pending == result[1]
                        and result[0] is expected
                    ),
                    sequence=(
                        frame.payload.get("record_sequence")
                        if isinstance(frame.payload, dict)
                        else 0
                    ),
                )
                if frame.kind is NativeKind.PUBLISHED:
                    witness.add("published")
            return result

        A3NativeReservation._execute = execute  # type: ignore[method-assign]

    def encrypt(profile: A3Runtime, raw: bytes) -> bytes:
        record = original_encrypt(profile, raw)
        if json.loads(raw)["kind"] == "PATCH_END":
            fault["end"] = record
        return record

    async def send(
        self: _NativeOpaquePort, record: bytes, check_current: Callable[[], None]
    ) -> None:
        if witness is not None:
            witness.add("records_started")
        if record == fault["end"]:
            if fault["mode"] == "hold-end":
                fault["held"] = True
                await release.wait()
                check_current()
            elif fault["mode"] == "tamper-end":
                record = record[:-1] + bytes([record[-1] ^ 1])
        await original_send(self, record, check_current)

    A3Runtime.encrypt_record = encrypt  # type: ignore[method-assign]
    _NativeOpaquePort.send = send  # type: ignore[method-assign]
    root = Path(config["root"])
    projects = root / "projects"
    project = projects / "formal-project"
    _populate_patch_project(project, publication_witnesses=witness is not None)
    metadata = parse_git_change_page(
        subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain=v2", "-z"],
            check=True,
            capture_output=True,
        ).stdout,
        None,
    ).to_dict()

    class Counter(ControlledProcessRunner):
        diff_count = 0

        async def run_with_cwd_fd(self, *args: Any, **kwargs: Any) -> ProcessResult:
            result = await super().run_with_cwd_fd(*args, **kwargs)
            if "--patch" in args[1]:
                self.diff_count += 1
            return result

    class PublishedSyntheticKey:
        @contextlib.contextmanager
        def borrow(self, facts: Any) -> Iterator[bytes]:
            assert facts.runtime_host_installation_id == HOST_ID
            yield bytes(range(32))

    runner = Counter()
    reader = GitStagedPatchReader(ProjectRegistry(projects), GitAdapter(runner=runner))
    executor = WAWSupervisorExecutor(
        runtime_epoch="1",
        project_registry=ProjectRegistry(projects),
        command_factory=_no_host,
        transport_factory=_no_host,
        geometry=PtyGeometry(80, 24),
        clock=time.monotonic,
        attachment_validator=lambda _: False,
    )
    binding = WAWProjectBinding(PROJECT_ID, "formal-project", "1", "1", "b" * 64, HOST_ID, "1")
    await executor.register_project_binding(binding)
    authority = WAWPeerAuthority(expected_uid=config["api_uid"], expected_gid=config["api_gid"])
    pidfd = os.pidfd_open(config["api_pid"])
    try:
        observed = authority.observe_control(
            config["api_pid"], config["api_uid"], config["api_gid"], pidfd
        )
        assert observed is not None
        plan = authority.prepare_bind(observed, api_authority_epoch="1", nonce_digest=b"n" * 32)
        authority.commit_bind(plan)
    finally:
        os.close(pidfd)
    lease = authority.borrow()
    assert lease is not None
    lifecycle = WAWLifecycleRegistry(
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="1",
        host_manifest_digest="a" * 64,
        project_root_manifest_digest="b" * 64,
        runtime_epoch="1",
        executor=executor,
        peer_authority=authority,
    )
    # Synthetic inventory admission, but exact real process/pidfd authority.
    lifecycle._authority = ("1", "fixture")
    lifecycle._peer_authority_identity = lease.runtime_peer.identity
    lifecycle._bindings[PROJECT_ID] = binding
    owner = A3NativeReadOwner(reader, lifecycle, executor, PublishedSyntheticKey())
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(config["socket"])
    os.chmod(config["socket"], 0o666)
    listener.listen(12)
    listener.setblocking(False)
    loop = asyncio.get_running_loop()
    observed_pids: set[int] = set()
    bundle_count = 0

    async def accept() -> None:
        nonlocal bundle_count
        while True:
            reservation = None
            sockets: list[socket.socket] = []
            try:
                ready = loop.create_future()

                def readable(future: asyncio.Future[None] = ready) -> None:
                    if not future.done():
                        future.set_result(None)

                loop.add_reader(listener.fileno(), readable)
                try:
                    await ready
                finally:
                    loop.remove_reader(listener.fileno())
                # Count the bundle BEFORE accepting even its first descriptor.
                reservation = owner.reserve()
                first, _ = await loop.sock_accept(listener)
                sockets.append(first)
                async with asyncio.timeout(1):
                    for _ in range(2):
                        stream, _ = await loop.sock_accept(listener)
                        sockets.append(stream)
                for stream in sockets:
                    import struct

                    pid, _, _ = struct.unpack(
                        "3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                    )
                    observed_pids.add(pid)
                    assert pid == config["api_pid"] and pid != os.getpid()
                reservation.accept(*sockets)
                bundle_count += 1
            except asyncio.CancelledError:
                for stream in sockets:
                    stream.close()
                if reservation:
                    reservation.close()
                raise
            except Exception:
                for stream in sockets:
                    stream.close()
                if reservation:
                    reservation.close()

    accepting = asyncio.create_task(accept())
    _emit({"metadata": metadata})
    try:
        while True:
            command = await asyncio.to_thread(_read)
            op = command["op"]
            if op == "status":
                _emit(
                    {
                        "diff_count": runner.diff_count,
                        "held": fault["held"],
                        "active": owner.selectors._active,
                        "active_bundles": owner.active_bundles,
                        "burned_nonces": len(owner.selectors._burned_nonces),
                        "bundles": bundle_count,
                        "observed_api_pids": sorted(observed_pids),
                        "runtime_uid": os.geteuid(),
                    }
                )
            elif op == "publication-status" and witness is not None:
                _emit(witness.snapshot())
            elif op == "mode":
                assert command["value"] in {"normal", "hold-end", "tamper-end"}
                fault["mode"] = command["value"]
                release.clear()
                _emit({"ok": True})
            elif op == "release":
                release.set()
                _emit({"ok": True})
            elif op == "lifecycle":
                lifecycle._shutting_down = True
                _emit({"ok": True})
            elif op == "close":
                _emit({"ok": True})
                break
            else:
                _emit({"error": "unsupported-control"})
    finally:
        accepting.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await accepting
        listener.close()
        owner.close()
        await owner.wait_closed()
        lease.close()
        authority.close()


def _revoke_fixture_sessions(services: Any) -> None:
    from agentbox_core.models import ControlPlaneSession
    from sqlalchemy import select as db_select

    with services.database.transaction() as session:
        now = services.database.transaction_now(session)
        for row in session.scalars(db_select(ControlPlaneSession)):
            row.revoked_at = now


def _configure_api_import_environment(config: dict[str, Any]) -> None:
    """Bind even main.py's import-time default app to this API child's TEST root."""
    root = Path(config["root"])
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("fixture API root must already exist")
    toml = root / "fixture-import.toml"
    # This fresh per-child file prevents local checkout TOML or an outer harness
    # from supplying a default setting before the explicit factory is invoked.
    with toml.open("x", encoding="ascii"):
        pass
    for name in tuple(os.environ):
        if name.upper().startswith("AGENTBOX_"):
            del os.environ[name]
    os.environ.update(
        {
            "AGENTBOX_ENV": "test",
            "AGENTBOX_DATA_DIR": str(root),
            "AGENTBOX_DATABASE_URL": f"sqlite+pysqlite:///{root}/fixture.db",
            "AGENTBOX_PROJECT_ROOT": str(root / "empty-projects"),
            "AGENTBOX_RUNTIME_SOCKET": str(root / "unavailable-runtime.sock"),
            "AGENTBOX_TOML_FILE": str(toml),
            "AGENTBOX_SECRET_KEY": SYNTHETIC_SECRET,
            "AGENTBOX_ALLOWED_ORIGINS": json.dumps([config["origin"], config["api_origin"]]),
        }
    )


async def _api(config: dict[str, Any]) -> None:
    _configure_api_import_environment(config)

    import uvicorn
    from agentbox_api.a3_native_transport import A3NativeBundle, A3NativeSource
    from agentbox_api.main import create_app
    from agentbox_api.waw_control_client import (
        BoundRuntimePeer,
        WAWSocketPathIdentity,
        _RuntimePeerObservation,
    )
    from agentbox_api.waw_websocket_protocol import WAWWebSocketProtocol
    from agentbox_core.a3_native_io import NativeChannel
    from agentbox_core.configuration import Environment, Settings
    from agentbox_core.models import Base, ControlPlaneSession, Project
    from agentbox_core.security import PasswordManager
    from agentbox_core.services import build_services
    from agentbox_core.waw_models import RuntimeHostInstallation
    from agentbox_protocol.a3_transport import NativeFrame, NativeKind
    from pydantic import SecretStr
    from sqlalchemy import select as db_select

    witness = _PublicationWitness("api") if config.get("publication_witnesses") else None
    if witness is not None:
        original_areceive = NativeChannel.areceive
        original_receive = NativeChannel.receive
        original_send = NativeChannel.send
        original_rpc = A3NativeBundle._rpc
        original_request = A3NativeBundle.request

        async def areceive(
            self: NativeChannel,
            expected: frozenset[NativeKind],
            *,
            deadline_ns: int,
            guard: Callable[[], None] | None = None,
        ) -> NativeFrame:
            frame = await original_areceive(self, expected, deadline_ns=deadline_ns, guard=guard)
            assert witness is not None
            if frame.kind is NativeKind.READY:
                witness.add("ready_received")
            elif frame.kind is NativeKind.RECORD:
                witness.add("records_received")
            elif frame.kind is NativeKind.COMPLETE:
                witness.add("complete_received")
            elif frame.kind is NativeKind.ACK:
                witness.add("ack_received")
            return frame

        def receive(
            self: NativeChannel,
            expected: frozenset[NativeKind],
            *,
            deadline_ns: int,
            guard: Callable[[], None] | None = None,
        ) -> NativeFrame:
            frame = original_receive(self, expected, deadline_ns=deadline_ns, guard=guard)
            assert witness is not None
            if frame.kind is NativeKind.CURRENT:
                witness.add("current_received")
            elif frame.kind is NativeKind.CHECKED:
                witness.add("checked_received")
            elif frame.kind is NativeKind.LIVE_REPLY:
                witness.add("live_received")
            return frame

        def native_send(
            self: NativeChannel,
            kind: NativeKind,
            payload: dict[str, object] | bytes,
            *,
            deadline_ns: int,
            guard: Callable[[], None] | None = None,
        ) -> None:
            original_send(self, kind, payload, deadline_ns=deadline_ns, guard=guard)
            if kind is NativeKind.CURRENT_REPLY:
                assert witness is not None
                witness.add("current_replied")

        def rpc(
            self: A3NativeBundle,
            kind: NativeKind,
            payload: dict[str, object],
            expected: NativeKind,
        ) -> None:
            # The unmodified _rpc returns only after exact reply-payload equality,
            # including SHA/challenge and sequence, and its final authority check.
            original_rpc(self, kind, payload, expected)
            assert witness is not None
            if kind is NativeKind.PUBLISH_CHECK:
                witness.add(
                    "checked_matches",
                    matched=expected is NativeKind.CHECKED,
                    sequence=payload["record_sequence"],
                )
            elif kind is NativeKind.LIVE:
                witness.add("live_matches", matched=expected is NativeKind.LIVE_REPLY)

        async def request(
            self: A3NativeBundle,
            kind: NativeKind,
            payload: dict[str, object],
            expected: NativeKind,
            seconds: float,
        ) -> Any:
            reply = await original_request(self, kind, payload, expected, seconds)
            if kind is NativeKind.PUBLISHED:
                assert witness is not None
                witness.add(
                    "ack_matches",
                    matched=expected is NativeKind.ACK and reply == payload,
                    sequence=payload["record_sequence"],
                )
            return reply

        NativeChannel.areceive = areceive  # type: ignore[method-assign]
        NativeChannel.receive = receive  # type: ignore[method-assign]
        NativeChannel.send = native_send  # type: ignore[method-assign]
        A3NativeBundle._rpc = rpc  # type: ignore[method-assign]
        A3NativeBundle.request = request  # type: ignore[method-assign]

    root = Path(config["root"])
    settings = Settings(
        env=Environment.TEST,
        data_dir=root,
        database_url=f"sqlite+pysqlite:///{root}/fixture.db",
        secret_key=SecretStr(SYNTHETIC_SECRET),
        project_root=root / "empty-projects",
        allowed_origins=(config["origin"], config["api_origin"]),
    )
    services = build_services(
        settings,
        password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
    )
    Base.metadata.create_all(services.database.engine)
    services.admin.initialize(USERNAME, PASSWORD)
    now = datetime.now(UTC).replace(tzinfo=None)
    with services.database.transaction() as session:
        session.add(
            Project(
                id=PROJECT_ID,
                slug="formal-project",
                display_name="独立进程 A3 测试项目",
                relative_path="formal-project",
                source_type="empty",
                state="ready",
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            RuntimeHostInstallation(
                id=HOST_ID,
                revision=1,
                runtime_type="agentbox-runtime-linux-v1",
                created_at=now,
                updated_at=now,
                last_runtime_epoch="1",
            )
        )
    pending = services.project_bindings.reserve(
        project_id=PROJECT_ID,
        expected_project_revision=1,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision=1,
        expected_head_revision=None,
        expected_head_digest=None,
    )
    services.project_bindings.commit(
        project_id=PROJECT_ID,
        binding_revision=pending.binding_revision,
        expected_project_revision=1,
        binding_digest="b" * 64,
    )
    inode = os.stat(config["socket"])
    peer = BoundRuntimePeer(
        _RuntimePeerObservation(
            config["runtime_pid"],
            config["runtime_uid"],
            config["runtime_gid"],
            os.pidfd_open(config["runtime_pid"]),
        ),
        WAWSocketPathIdentity(inode.st_dev, inode.st_ino),
    )
    peer._publish(
        generation=1, owner_current=lambda owner, generation: owner is peer and generation == 1
    )
    connections = 0

    async def connector(facts: Any) -> tuple[socket.socket, socket.socket, socket.socket]:
        nonlocal connections
        streams: list[socket.socket] = []
        try:
            async with asyncio.timeout(1):
                for _ in range(3):
                    stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    streams.append(stream)
                    stream.setblocking(False)
                    await asyncio.get_running_loop().sock_connect(stream, config["socket"])
            connections += 1
            return streams[0], streams[1], streams[2]
        except BaseException:
            for stream in streams:
                stream.close()
            raise

    source = A3NativeSource(
        services, runtime_epoch=lambda: "1", connector=connector, runtime_peer=lambda: peer
    )

    class MetadataOnlyProjectPort:
        async def git_changes(self, *args: Any) -> Any:
            return SimpleNamespace(to_dict=lambda: config["metadata"])

    app = create_app(
        settings,
        services,
        project_runtime=MetadataOnlyProjectPort(),  # type: ignore[arg-type]
        a3_native_source=source,
    )
    denied: dict[str, bool] = {}
    for name, path, flags in (
        ("api_cannot_write_static", Path(config["static_root"]) / "index.html", os.O_WRONLY),
        (
            "api_cannot_read_patch",
            Path(config["runtime_root"]) / "projects/formal-project/success.txt",
            os.O_RDONLY,
        ),
    ):
        try:
            fd = os.open(path, flags)
        except PermissionError:
            denied[name] = True
        else:
            os.close(fd)
            denied[name] = False
    if config["isolated"] and not all(denied.values()):
        raise AssertionError("fixture isolation proof failed")
    forbidden = [
        name
        for name in sys.modules
        if name.startswith(("agentbox_runtime.a3_", "agentbox_runtime.git_staged"))
    ]
    if forbidden:
        raise AssertionError("API imported A3 Runtime authority")
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=config["port"],
            ws=WAWWebSocketProtocol,
            access_log=False,
            log_level="critical",
            lifespan="on",
        )
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            await task
            raise RuntimeError("API startup failed")
        await asyncio.sleep(0.01)
    _emit(
        {
            **denied,
            "api_a3_runtime_imports": len(forbidden),
            "api_uid": os.geteuid(),
            "static_owner_uid": Path(config["static_root"]).stat().st_uid,
        }
    )
    try:
        while True:
            command = await asyncio.to_thread(_read)
            op = command["op"]
            if op == "status":
                _emit({"connections": connections, "api_a3_runtime_imports": len(forbidden)})
                continue
            if op == "publication-status" and witness is not None:
                if not 0 <= len(source._bundles) <= 4:
                    raise RuntimeError("fixture publication witness invalid")
                _emit(
                    {
                        **witness.snapshot(),
                        "open_bundles": len(source._bundles),
                        "a3_runtime_imports_absent": not any(
                            name.startswith(("agentbox_runtime.a3_", "agentbox_runtime.git_staged"))
                            for name in sys.modules
                        ),
                    }
                )
                continue
            if op == "close":
                _emit({"ok": True})
                break
            if op == "peer":
                peer.poison()
            elif op == "revoke":
                _revoke_fixture_sessions(services)
            else:
                with services.database.transaction() as session:
                    if op == "auth-epoch":
                        for row in session.scalars(db_select(ControlPlaneSession)):
                            row.auth_epoch += 1
                    elif op == "project":
                        project = session.get(Project, PROJECT_ID)
                        assert project
                        project.revision += 1
                    elif op == "epoch":
                        host = session.get(RuntimeHostInstallation, HOST_ID)
                        assert host
                        host.last_runtime_epoch = "2"
                    else:
                        raise ValueError("unsupported fixture control")
            _emit({"ok": True})
    finally:
        server.should_exit = True
        await task
        await source.close()
        peer.close()
        services.database.close()


if __name__ == "__main__":
    try:
        # Both exec children die if the CI supervisor disappears; no orphan
        # listener can survive a canceled browser job or failed control pipe.
        import ctypes

        parent_pid = os.getppid()
        if ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            raise RuntimeError("fixture parent-death fence unavailable")
        if parent_pid == 1 or os.getppid() != parent_pid:
            raise RuntimeError("fixture supervisor already exited")
        initial = _read()
        asyncio.run(_runtime(initial) if sys.argv[1] == "runtime" else _api(initial))
    except BaseException as error:
        # No exception values, paths, DB params, patch bytes or records in diagnostics.
        _emit({"error": type(error).__name__})
        raise SystemExit(1) from None
