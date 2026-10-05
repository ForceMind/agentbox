"""Bounded multiplexed stdin bridge used only by Changes DOM/CI fixtures."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for directory in [
    "tests",
    "apps/api/src",
    "packages/agentbox-protocol/src",
    "packages/agentbox-runtime/src",
    "packages/agentbox-core/src",
]:
    sys.path.insert(0, str(ROOT / directory))

from a3_changes_fixture import A3ChangesFixture  # noqa: E402


async def main() -> None:
    stream = asyncio.StreamReader(limit=50176)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(stream),
        sys.stdin.buffer,
    )
    with tempfile.TemporaryDirectory(prefix="a3-changes-dom-") as directory:
        fixture = await A3ChangesFixture.create(Path(directory))
        tasks: set[asyncio.Task[None]] = set()

        async def handle(raw: bytes) -> None:
            value = json.loads(raw)
            identifier = value["id"]
            try:
                result = await fixture.command(value["op"], value.get("payload", {}))
                response = {"id": identifier, "ok": True, "result": result}
            except Exception as exc:
                code = str(exc)
                if re.fullmatch(r"(?:PATCH_|AUTH_|SESSION_)[A-Z_]{1,64}", code) is None:
                    code = "PATCH_PROTOCOL_INVALID"
                response = {"id": identifier, "ok": False, "code": code}
            print(json.dumps(response, separators=(",", ":")), flush=True)

        try:
            print('{"ready":true}', flush=True)
            while raw := await stream.readline():
                if len(raw) > 50176 or len(tasks) >= 8:
                    raise ValueError("fixture request bound exceeded")
                task = asyncio.create_task(handle(raw))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        finally:
            await fixture.close()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            transport.close()


if __name__ == "__main__":
    asyncio.run(main())
