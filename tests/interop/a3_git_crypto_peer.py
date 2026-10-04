"""Synthetic Git→admitted Runtime→opaque-pipe peer for the Web interop fixture.

No host keys/accounts/network routes. Bootstrap on stdout is fixture-only trusted
metadata, never an authentication protocol. Data exchange contains only opaque
key/ciphertext envelopes; the final complete plaintext is verified by Web.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parents[2]
for directory in [
    "apps/api/src",
    "packages/agentbox-protocol/src",
    "packages/agentbox-runtime/src",
    "packages/agentbox-core/src",
]:
    sys.path.insert(0, str(ROOT / directory))

from datetime import datetime  # noqa: E402

from agentbox_api.a3_admission import A3SessionCurrentness  # noqa: E402
from agentbox_core.configuration import Environment, Settings  # noqa: E402
from agentbox_core.models import Base, Project  # noqa: E402
from agentbox_core.security import PasswordManager  # noqa: E402
from agentbox_core.services import build_services  # noqa: E402
from agentbox_core.waw_models import RuntimeHostInstallation  # noqa: E402
from agentbox_runtime.a3_admission import A3SyntheticTestKey, A3TestReadOwner  # noqa: E402
from agentbox_runtime.a3_content_session import serve_admitted_staged_read  # noqa: E402
from agentbox_runtime.git import GitAdapter  # noqa: E402
from agentbox_runtime.git_staged_reader import GitStagedPatchReader  # noqa: E402
from agentbox_runtime.process import ControlledProcessRunner, ProcessResult  # noqa: E402
from agentbox_runtime.project import ProjectRegistry  # noqa: E402
from agentbox_runtime.waw_encrypted_stream import RuntimePeer  # noqa: E402
from agentbox_runtime.waw_lifecycle import (  # noqa: E402
    WAWLifecycleRegistry,
    WAWProjectBinding,
)
from agentbox_runtime.waw_pty import PtyGeometry  # noqa: E402
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: E402
from pydantic import SecretStr  # noqa: E402

KEY = bytes(range(32))
PIN = hashlib.sha256(
    X25519PrivateKey.from_private_bytes(KEY).public_key().public_bytes_raw()
).hexdigest()
_PROJECT = "prj_" + "a" * 32
_SCOPE = b"s" * 32


def no_host(*args: Any) -> NoReturn:
    raise AssertionError("synthetic A3 fixture must never activate host")


class NativeCounter(ControlledProcessRunner):
    def __init__(self) -> None:
        super().__init__()
        self.diff_count = 0

    async def run_with_cwd_fd(self, *args: Any, **kwargs: Any) -> ProcessResult:
        result = await super().run_with_cwd_fd(*args, **kwargs)
        if "--patch" in args[1]:
            self.diff_count += 1
        return result


class PipeFixture:
    def __init__(self, reader: asyncio.StreamReader) -> None:
        self.reader = reader
        self.closed = False

    async def receive(self) -> bytes:
        line = await self.reader.readline()
        if self.closed or not 1 <= len(line) <= 49153:
            raise ValueError("invalid opaque fixture input")
        record = bytes.fromhex(line.decode("ascii").strip())
        if len(record) > 24576:
            raise ValueError("oversize opaque fixture input")
        return record

    async def send(self, record: bytes, check_current: Callable[[], None]) -> None:
        if self.closed or not 1 <= len(record) <= 24576:
            raise ValueError("invalid opaque fixture output")
        check_current()
        # No await between final guard and synthetic pipe publication.
        print(json.dumps({"wire": record.hex()}), flush=True)

    def close(self) -> None:
        self.closed = True


async def main() -> None:
    # Fixed Runtime fixture clock; Web uses a distinct local origin.
    time.monotonic_ns = lambda: 100_000_000_000
    stream = asyncio.StreamReader(limit=49154)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(stream), sys.stdin.buffer
    )
    try:
        with tempfile.TemporaryDirectory(prefix="a3-encrypted-git-") as directory:
            root = Path(directory) / "projects"
            project = root / "formal-project"
            project.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
            runner = NativeCounter()
            reader = GitStagedPatchReader(ProjectRegistry(root), GitAdapter(runner=runner))
            # Actual API session/READY DB adapters over an isolated synthetic app.
            settings = Settings(
                env=Environment.TEST,
                data_dir=Path(directory) / "data",
                database_url=f"sqlite+pysqlite:///{directory}/fixture.db",
                secret_key=SecretStr("published-synthetic-test-only-secret-00000000"),
                project_root=root,
                allowed_origins=("http://testserver",),
            )
            services = build_services(
                settings,
                password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
            )
            Base.metadata.create_all(services.database.engine)
            services.admin.initialize("fixture", "published synthetic fixture password")
            issued = services.auth.login(
                username="fixture",
                password="published synthetic fixture password",
                source_identifier="synthetic",
                request_id=None,
            )
            authenticated = services.sessions.authenticate(issued.token)
            host_id = "wri_" + "c" * 32
            now = datetime.now().replace(tzinfo=None)
            with services.database.transaction() as session:
                session.add(
                    Project(
                        id=_PROJECT,
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
                        id=host_id,
                        revision=1,
                        runtime_type="agentbox-runtime-linux-v1",
                        created_at=now,
                        updated_at=now,
                        last_runtime_epoch="1",
                    )
                )
            pending = services.project_bindings.reserve(
                project_id=_PROJECT,
                expected_project_revision=1,
                runtime_host_installation_id=host_id,
                runtime_host_installation_revision=1,
                expected_head_revision=None,
                expected_head_digest=None,
            )
            services.project_bindings.commit(
                project_id=_PROJECT,
                binding_revision=pending.binding_revision,
                expected_project_revision=1,
                binding_digest="b" * 64,
            )
            api = A3SessionCurrentness(services, authenticated, runtime_epoch=lambda: "1")
            scope = api.session_scope
            binding = WAWProjectBinding(
                _PROJECT, "formal-project", "1", "1", "b" * 64, host_id, "1"
            )
            executor = WAWSupervisorExecutor(
                runtime_epoch="1",
                project_registry=ProjectRegistry(root),
                command_factory=no_host,
                transport_factory=no_host,
                geometry=PtyGeometry(80, 24),
                clock=time.monotonic,
                attachment_validator=lambda _: False,
            )
            await executor.register_project_binding(binding)
            lifecycle = WAWLifecycleRegistry(
                runtime_host_installation_id=host_id,
                runtime_host_installation_revision="1",
                host_manifest_digest="a" * 64,
                project_root_manifest_digest="b" * 64,
                runtime_epoch="1",
                executor=executor,
            )
            identity = object()  # Explicit fixture peer, no production pidfd claim.
            lifecycle._authority = ("1", "fixture")
            lifecycle._peer_authority_identity = identity
            lifecycle._bindings[_PROJECT] = binding
            composition = A3TestReadOwner(
                reader,
                lifecycle,
                executor,
                RuntimePeer(identity, "1", lambda: True),
                api.current,
                A3SyntheticTestKey(KEY),
                enabled_for_tests=True,
            )
            owner = composition.selectors
            (project / "modified.txt").write_text(
                "synthetic-staged-canary-" + "x" * 24000 + "\n🌍\n", encoding="utf-8"
            )
            subprocess.run(["git", "-C", str(project), "add", "--", "modified.txt"], check=True)
            # Independent expected fixture diff; never sent as plaintext to relay.
            expected = subprocess.run(
                [
                    "git",
                    "-C",
                    str(project),
                    "diff",
                    "--cached",
                    "--patch",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--no-color",
                    "--no-renames",
                    "--full-index",
                    "--unified=3",
                    "--",
                    "modified.txt",
                ],
                check=True,
                capture_output=True,
            ).stdout
            observation = await owner.observe(_PROJECT, scope)
            selection = observation.entries[0].selection_id
            assert selection is not None
            (project / "modified.txt").write_text("unstaged-exclusion-canary\n")
            async with owner.admit(_PROJECT, scope, selection, b"n" * 32) as admitted:
                print(
                    json.dumps(
                        {
                            "fixture_bootstrap": {
                                "context": admitted.context,
                                "selection": selection,
                                "pin_sha256": PIN,
                                "expected_sha256": hashlib.sha256(expected).hexdigest(),
                            }
                        }
                    ),
                    flush=True,
                )
                port = PipeFixture(stream)
                await serve_admitted_staged_read(admitted, KEY, port)
            assert port.closed and owner._active == 0 and runner.diff_count == 2
            print(
                json.dumps(
                    {
                        "fixture_done": True,
                        "native_double_observations": runner.diff_count,
                        "burned_nonces": len(owner._burned_nonces),
                    }
                ),
                flush=True,
            )
            composition.close()
            services.database.close()
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(main())
