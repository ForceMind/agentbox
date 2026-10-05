"""Isolated native Git/API/admission/opaque fixture. Never imported by product code."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

import httpx
from agentbox_api.a3_admission import A3SessionCurrentness
from agentbox_api.a3_observation import A3StagedEntry, A3StagedMetadata, public_binding
from agentbox_api.a3_relay import A3OpaqueTestRelay
from agentbox_api.main import create_app
from agentbox_core.configuration import Environment, Settings
from agentbox_core.models import Base, ControlPlaneSession, Project
from agentbox_core.security import PasswordManager
from agentbox_core.services import (
    AuthenticatedSession,
    ControlPlaneServices,
    IssuedSession,
    build_services,
)
from agentbox_core.waw_models import RuntimeHostInstallation
from agentbox_protocol.a3_admission import A3CurrentAdmission
from agentbox_protocol.a3_content import ERROR_CODES, ContentError
from agentbox_runtime.a3_admission import A3SyntheticTestKey, A3TestReadOwner
from agentbox_runtime.git import GitAdapter
from agentbox_runtime.git_staged_reader import GitStagedPatchReader
from agentbox_runtime.process import ControlledProcessRunner, ProcessResult
from agentbox_runtime.project import ProjectRegistry
from agentbox_runtime.waw_encrypted_stream import RuntimePeer
from agentbox_runtime.waw_lifecycle import WAWLifecycleRegistry, WAWProjectBinding
from agentbox_runtime.waw_pty import PtyGeometry
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from fastapi import FastAPI
from pydantic import SecretStr

PROJECT_ID = "prj_" + "a" * 32
HOST_ID = "wri_" + "c" * 32
# Public deterministic TEST fixture only; not a loader, enrollment or real key.
KEY = bytes(range(32))
PIN = X25519PrivateKey.from_private_bytes(KEY).public_key().public_bytes_raw().hex()


def no_host(*args: Any) -> NoReturn:
    raise AssertionError("A3 fixture must never activate host resources")


class NativeCounter(ControlledProcessRunner):
    def __init__(self) -> None:
        super().__init__()
        self.diff_count = 0

    async def run_with_cwd_fd(self, *args: Any, **kwargs: Any) -> ProcessResult:
        result = await super().run_with_cwd_fd(*args, **kwargs)
        if "--patch" in args[1]:
            self.diff_count += 1
        return result


class A3ChangesFixture:
    root: Path
    project: Path
    runner: NativeCounter
    git: GitAdapter
    reader: GitStagedPatchReader
    settings: Settings
    services: ControlPlaneServices
    issued: IssuedSession
    authenticated: AuthenticatedSession
    api: A3SessionCurrentness
    executor: WAWSupervisorExecutor
    lifecycle: WAWLifecycleRegistry
    owner: A3TestReadOwner
    app: FastAPI
    relay: A3OpaqueTestRelay | None
    task: asyncio.Task[None] | None
    failure: str | None
    mode: str
    held: bool
    release: asyncio.Event
    observations: int
    dropped: bool
    handle: str
    generation: int

    @classmethod
    async def create(cls, directory: Path) -> A3ChangesFixture:
        self = cls()
        self.root = directory / "projects"
        self.project = self.root / "formal-project"
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        for name, raw in {
            "success.txt": (
                "A3 synthetic complete diff\n<img src=x onerror=window.a3Executed=true>\n"
                + "x" * 24000
                + "\n🌍\n"
            ).encode(),
            "binary.bin": b"synthetic\0binary\n",
            "large.txt": b"L" * 210000 + b"\n",
            ".env": b"synthetic denied path only\n",
        }.items():
            (self.project / name).write_bytes(raw)
        subprocess.run(["git", "-C", str(self.project), "add", "--", "."], check=True)
        (self.project / "success.txt").write_text("unstaged-exclusion-canary\n")
        (self.project / "unstaged-only.txt").write_text("untracked fixture only\n")
        self.runner = NativeCounter()
        self.git = GitAdapter(runner=self.runner)
        self.reader = GitStagedPatchReader(ProjectRegistry(self.root), self.git)
        self.settings = Settings(
            env=Environment.TEST,
            data_dir=directory / "data",
            database_url=f"sqlite+pysqlite:///{directory}/fixture.db",
            secret_key=SecretStr("published-synthetic-test-only-secret-00000000"),
            project_root=self.root,
            allowed_origins=("http://testserver",),
        )
        self.services = build_services(
            self.settings,
            password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
        )
        Base.metadata.create_all(self.services.database.engine)
        self.services.admin.initialize("fixture", "published synthetic fixture password")
        self.issued = self.services.auth.login(
            username="fixture",
            password="published synthetic fixture password",
            source_identifier="synthetic",
            request_id=None,
        )
        self.authenticated = self.services.sessions.authenticate(self.issued.token)
        now = datetime.now().replace(tzinfo=None)
        with self.services.database.transaction() as session:
            session.add(
                Project(
                    id=PROJECT_ID,
                    slug="formal-project",
                    display_name="Fixture",
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
        pending = self.services.project_bindings.reserve(
            project_id=PROJECT_ID,
            expected_project_revision=1,
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision=1,
            expected_head_revision=None,
            expected_head_digest=None,
        )
        self.services.project_bindings.commit(
            project_id=PROJECT_ID,
            binding_revision=pending.binding_revision,
            expected_project_revision=1,
            binding_digest="b" * 64,
        )
        self.api = A3SessionCurrentness(
            self.services,
            self.authenticated,
            runtime_epoch=self.runtime_epoch,
        )
        binding = WAWProjectBinding(PROJECT_ID, "formal-project", "1", "1", "b" * 64, HOST_ID, "1")
        self.executor = WAWSupervisorExecutor(
            runtime_epoch="1",
            project_registry=ProjectRegistry(self.root),
            command_factory=no_host,
            transport_factory=no_host,
            geometry=PtyGeometry(80, 24),
            clock=time.monotonic,
            attachment_validator=lambda _: False,
        )
        await self.executor.register_project_binding(binding)
        self.lifecycle = WAWLifecycleRegistry(
            runtime_host_installation_id=HOST_ID,
            runtime_host_installation_revision="1",
            host_manifest_digest="a" * 64,
            project_root_manifest_digest="b" * 64,
            runtime_epoch="1",
            executor=self.executor,
        )
        identity = object()  # Synthetic peer authority, never a real pidfd assertion.
        self.lifecycle._authority = ("1", "fixture")
        self.lifecycle._peer_authority_identity = identity
        self.lifecycle._bindings[PROJECT_ID] = binding
        self.owner = A3TestReadOwner(
            self.reader,
            self.lifecycle,
            self.executor,
            RuntimePeer(identity, "1", lambda: True),
            self.api.current,
            A3SyntheticTestKey(KEY),
            enabled_for_tests=True,
        )
        self.app = create_app(self.settings, self.services, a3_observation_source=self)
        self.relay = None
        self.task = None
        self.failure = None
        self.mode = "normal"
        self.held = False
        self.release = asyncio.Event()
        self.observations = 0
        self.dropped = False
        self.generation = 0
        self.handle = ""
        return self

    def runtime_epoch(self) -> str:
        return "1"

    async def observe(self, facts: A3CurrentAdmission) -> A3StagedMetadata:
        assert facts == self.api.current(PROJECT_ID, self.api.session_scope)
        result = await self.owner.selectors.observe(facts.project_id, facts.session_scope)
        self.observations += 1
        return A3StagedMetadata(
            snapshot_sha256=result.snapshot_sha256,
            entries=tuple(
                A3StagedEntry.model_validate(
                    {
                        "path": e.path,
                        "kind": e.kind,
                        "side": e.side,
                        "selection_id": e.selection_id,
                        "unavailable_code": e.unavailable_code,
                    }
                )
                for e in result.entries
            ),
        )

    async def bootstrap(self) -> dict[str, Any]:
        # The actual HTTP route performs Origin/session/CSRF/READY and post-await
        # currentness checks. Credentials never leave this isolated fixture.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
            headers={"Origin": "http://testserver", "X-CSRF-Token": self.issued.csrf_token},
            cookies={"agentbox_session": self.issued.token},
        ) as client:
            response = await client.post(f"/api/v1/projects/{PROJECT_ID}/git/staged-observation")
        body = response.json()
        if response.status_code != 200:
            raise ValueError(body["error"]["code"])
        assert response.headers["cache-control"] == "no-store"
        return dict(body["data"])

    def check_current(self) -> None:
        if self.api.current(PROJECT_ID, self.api.session_scope) is None:
            raise ValueError("PATCH_REVOKED")

    async def serve(
        self, selection: str, nonce: bytes, relay: A3OpaqueTestRelay, handle: str
    ) -> None:
        try:
            await self.owner.serve(PROJECT_ID, self.api.session_scope, selection, nonce, relay)
        except asyncio.CancelledError:
            if self.handle == handle:
                self.failure = "PATCH_REVOKED"
        except Exception as exc:
            code = str(exc) if isinstance(exc, ContentError) else getattr(exc, "code", "")
            if self.handle == handle:
                self.failure = code if code in ERROR_CODES else "PATCH_PROTOCOL_INVALID"
        finally:
            relay.close()

    async def cancel(self, handle: str | None = None) -> None:
        if handle is not None and handle != self.handle:
            return
        relay, task = self.relay, self.task
        # Release the exact slot synchronously. An old task/close cannot clear a
        # newer generation during cleanup's await.
        self.relay, self.task = None, None
        if relay is not None:
            relay.close()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def command(self, op: str, payload: dict[str, Any]) -> Any:
        if op == "bootstrap":
            return await self.bootstrap()
        if op == "trust":
            facts = self.api.current(PROJECT_ID, self.api.session_scope)
            if facts is None:
                raise ValueError("PATCH_REVOKED")
            return {
                "purpose": "agentbox-a3-content/crypto/v2",
                "binding": public_binding(facts),
                "pin": PIN,
            }
        if op == "metadata":
            page = await self.git.changes(self.project, None)
            return {"api_version": "v1", "request_id": "req_a3_fixture", "data": page.to_dict()}
        if op == "open":
            if self.relay is not None:
                raise ValueError("PATCH_UNAVAILABLE_BUSY")
            if payload.get("projectId") != PROJECT_ID:
                raise ValueError("PATCH_REVOKED")
            self.check_current()
            nonce = bytes.fromhex(payload["requestNonce"])
            if len(nonce) != 32:
                raise ValueError("PATCH_PROTOCOL_INVALID")
            self.failure = None
            self.dropped = False
            self.held = False
            self.release.clear()
            self.generation += 1
            self.handle = str(self.generation)
            self.relay = A3OpaqueTestRelay(enabled_for_tests=True)
            self.task = asyncio.create_task(
                self.serve(payload["selectionId"], nonce, self.relay, self.handle)
            )
            return {"handle": self.handle}
        if op in {"send", "receive"} and payload.get("handle") != self.handle:
            raise ValueError("PATCH_REVOKED")
        if op == "send":
            if self.relay is None:
                raise ValueError(self.failure or "PATCH_REVOKED")
            raw = bytes.fromhex(payload["wire"])
            task, handle = self.task, self.handle
            try:
                await self.relay.browser_send(raw, self.check_current)
            except Exception:
                if task is not None:
                    await task
                failure = self.failure if self.handle == handle else "PATCH_REVOKED"
                raise ValueError(failure or "PATCH_PROTOCOL_INVALID") from None
            return None
        if op == "receive":
            relay = self.relay
            task, handle = self.task, self.handle
            if relay is None:
                raise ValueError(self.failure or "PATCH_REVOKED")
            try:
                raw = await relay.browser_receive()
                kind = json.loads(raw)["kind"]  # Outer opaque kind only; never decrypt.
                if self.mode == "drop-page" and kind == "PATCH_PAGE" and not self.dropped:
                    self.dropped = True
                    raw = await relay.browser_receive()
                if self.mode == "tamper" and kind == "PATCH_PAGE":
                    raw = raw[:-1] + b"!"
                if self.mode == "hold-end" and kind == "PATCH_END":
                    self.held = True
                    await self.release.wait()
                    # Deliberately broken TEST transport: return old bytes after
                    # cancellation, proving the Web generation publication fence.
                return {"wire": raw.hex()}
            except Exception:
                if task is not None:
                    await task
                failure = self.failure if self.handle == handle else "PATCH_REVOKED"
                raise ValueError(failure or "PATCH_PROTOCOL_INVALID") from None
        if op == "close":
            await self.cancel(payload.get("handle"))
            return None
        if op == "release":
            self.release.set()
            return None
        if op == "mode":
            mode = payload.get("value")
            if mode not in {"normal", "hold-end", "tamper", "drop-page", "permission"}:
                raise ValueError("PATCH_PROTOCOL_INVALID")
            self.mode = mode
            if mode == "permission":
                with self.services.database.transaction() as session:
                    row = session.get(ControlPlaneSession, self.authenticated.session_id)
                    assert row is not None
                    row.revoked_at = self.services.database.transaction_now(session)
            return None
        if op == "status":
            return {
                "diff_count": self.runner.diff_count,
                "active": self.owner.selectors._active,
                "burned_nonces": len(self.owner.selectors._burned_nonces),
                "held": self.held,
                "observations": self.observations,
            }
        raise ValueError("PATCH_PROTOCOL_INVALID")

    async def close(self) -> None:
        self.release.set()
        await self.cancel()
        self.owner.close()
        self.api.close()
        self.services.database.close()
