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
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for directory in [
    "packages/agentbox-protocol/src",
    "packages/agentbox-runtime/src",
    "packages/agentbox-core/src",
]:
    sys.path.insert(0, str(ROOT / directory))

from agentbox_runtime.a3_content_session import serve_admitted_staged_read  # noqa: E402
from agentbox_runtime.git import GitAdapter  # noqa: E402
from agentbox_runtime.git_staged_reader import GitStagedPatchReader  # noqa: E402
from agentbox_runtime.git_staged_selectors import (  # noqa: E402
    GitStagedSelectors,
    StagedSelectorContext,
)
from agentbox_runtime.process import ControlledProcessRunner, ProcessResult  # noqa: E402
from agentbox_runtime.project import ProjectRegistry  # noqa: E402
from agentbox_runtime.waw_lifecycle import WAWProjectBinding  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: E402

KEY = bytes(range(32))
PIN = hashlib.sha256(
    X25519PrivateKey.from_private_bytes(KEY).public_key().public_bytes_raw()
).hexdigest()
_PROJECT = "prj_" + "a" * 32
_SCOPE = b"s" * 32


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
    # Shared fixed monotonic fixture clock; no cross-machine time-origin claim.
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
            binding = WAWProjectBinding(
                _PROJECT, "formal-project", "1", "1", "b" * 64, "wri_" + "c" * 32, "1"
            )
            # Explicit synthetic READY/scope source; not production authentication.
            current = StagedSelectorContext(binding, "1", _SCOPE)
            owner = GitStagedSelectors(
                reader,
                context=lambda project, scope: (
                    current if project == _PROJECT and scope == _SCOPE else None
                ),
            )
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
            observation = await owner.observe(_PROJECT, _SCOPE)
            selection = observation.entries[0].selection_id
            assert selection is not None
            (project / "modified.txt").write_text("unstaged-exclusion-canary\n")
            async with owner.admit(_PROJECT, _SCOPE, selection, b"n" * 32) as admitted:
                print(
                    json.dumps(
                        {
                            "fixture_bootstrap": {
                                "context": admitted.context,
                                "selection": selection,
                                "pin_sha256": PIN,
                                "now_ms": 100000,
                                "expires_ms": admitted.expires_ns // 1_000_000,
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
            owner.close()
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(main())
