"""Fixed offline binary S03 peer; stdout is exclusively length-prefixed frames.

The only result is the seven-field, bounded metadata object on inherited fd 3.
No wire command, bootstrap, body, key, payload hash or arbitrary exception is a
process argument or diagnostic. This file is a test harness, never an endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

MAX_FRAME = 22_031
METADATA_LIMIT = 4_096
SCENARIOS = (
    "minimum",
    "ascii_16k",
    "nul_16k",
    "utf8_4byte_16k",
    "bom",
    "quotes_backslashes",
    "crlf",
    "lf",
    "decomposed",
    "composed",
    "mixed_canary",
    "corrupt_tag",
    "prefix_max",
    "truncated_prefix",
    "truncated_body",
    "missing_attest",
    "missing_confirm",
    "missing_ready",
    "missing_submit",
    "held_writable",
    "held_readiness",
    "cancel_waiter",
    "revoke_readiness",
    "remote_expiry",
    "slow_reader",
    "lost_ack_recovery",
    "response_prefix_max",
    "truncated_response_prefix",
    "truncated_response_body",
)
FIXTURE = Path(__file__).parents[1] / "fixtures/kebui_s03_submit/v1.json"


class PipeFailure(Exception):
    def __init__(self) -> None:
        super().__init__("s03_invalid")


class BinaryPipe:
    """Exactly one pending read or write; all fd waits unregister on cancellation."""

    def __init__(self, *, slow: bool = False) -> None:
        self.pending_read = False
        self.pending_write = False
        self.allocated_max = 0
        self.closed = False
        self.slow = slow
        self.read_count = 0
        os.set_blocking(0, False)
        os.set_blocking(1, False)

    async def _ready(self, fd: int, *, write: bool = False) -> None:
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[None] = loop.create_future()

        def resolve() -> None:
            if not ready.done():
                ready.set_result(None)

        if write:
            loop.add_writer(fd, resolve)
        else:
            loop.add_reader(fd, resolve)
        try:
            await ready
        finally:
            if write:
                loop.remove_writer(fd)
            else:
                loop.remove_reader(fd)

    async def _exact(self, target: bytearray) -> None:
        position = 0
        while position < len(target):
            if self.closed:
                raise PipeFailure()
            failed = False
            chunk: bytes | None = None
            try:
                count = min(len(target) - position, 1024 if self.slow else MAX_FRAME)
                chunk = os.read(0, count)
            except BlockingIOError:
                pass
            except OSError:
                failed = True
            if failed:
                raise PipeFailure()
            if chunk is None:
                await self._ready(0)
                continue
            if not chunk:
                raise PipeFailure()
            target[position : position + len(chunk)] = chunk
            position += len(chunk)
            chunk = None
            if self.slow:
                await asyncio.sleep(0.005)

    async def read(self) -> bytes:
        if self.pending_read or self.closed:
            raise PipeFailure()
        self.pending_read = True
        prefix: bytearray | None = bytearray(4)
        payload: bytearray | None = None
        try:
            assert prefix is not None
            await self._exact(prefix)
            length = int.from_bytes(prefix, "big")
            # This check precedes payload allocation and any text/Base64 decode.
            if not 1 <= length <= MAX_FRAME:
                raise PipeFailure()
            payload = bytearray(length)
            self.allocated_max = max(self.allocated_max, length)
            await self._exact(payload)
            self.read_count += 1
            return bytes(payload)
        finally:
            prefix = payload = None
            self.pending_read = False

    async def write(self, raw: bytes) -> None:
        if (
            self.pending_write
            or self.closed
            or type(raw) is not bytes
            or not 1 <= len(raw) <= MAX_FRAME
        ):
            raise PipeFailure()
        self.pending_write = True
        packet: bytes | None = len(raw).to_bytes(4, "big") + raw
        raw = b""
        offset = 0
        try:
            while packet is not None and offset < len(packet):
                failed = False
                count = 0
                try:
                    count = os.write(1, memoryview(packet)[offset:])
                except BlockingIOError:
                    pass
                except OSError:
                    failed = True
                if failed:
                    raise PipeFailure()
                if count:
                    offset += count
                else:
                    await self._ready(1, write=True)
        finally:
            packet = None
            self.pending_write = False

    def close(self) -> None:
        self.closed = True


def context_for(fixture: dict[str, Any], name: str) -> dict[str, str]:
    suffix = f"{SCENARIOS.index(name) + 1:032x}"
    return {
        **fixture["context"],
        "request_id": "kreq_" + suffix,
        "channel_id": "ks03c_" + suffix,
        "source_lease_id": "ks03l_" + suffix,
    }


def _safe_error(error: BaseException) -> bool:
    """Inspect only fixed errors without rendering arbitrary private exceptions."""
    allowed = {"s03_unavailable", "s03_invalid", "s03_busy", "s03_revoked"}
    if isinstance(error, asyncio.CancelledError):
        return True
    return (
        len(error.args) == 1
        and error.args[0] in allowed
        and error.__cause__ is None
        and error.__context__ is None
    )


def _result(
    name: str,
    phase: str,
    effects: int = 0,
    count: int = 0,
    identity: bool = False,
    drained: bool = True,
    safe: bool = True,
) -> dict[str, Any]:
    return {
        "scenario": name,
        "phase": phase,
        "effects": effects,
        "bytes": count,
        "original_identity_match": identity,
        "pool_drained": drained,
        "safe_errors": safe,
    }


def _write_metadata(result: dict[str, Any]) -> None:
    encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(encoded) > METADATA_LIMIT:
        raise PipeFailure()
    offset = 0
    while offset < len(encoded):
        written = os.write(3, memoryview(encoded)[offset:])
        if written <= 0:
            raise PipeFailure()
        offset += written


async def _run(name: str, directory: Path, *, catalog_path: Path | None = None) -> dict[str, Any]:
    from agentbox_runtime.kebui_s03_submit import SyntheticS03TestRoot, s03_usage

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    context = context_for(fixture, name)
    origin = time.monotonic_ns()

    def clock() -> int:
        return 100_000_000_000 + time.monotonic_ns() - origin

    directory.mkdir(mode=0o700)
    pipe = BinaryPipe(slow=name == "slow_reader")
    endpoint = object()
    root = SyntheticS03TestRoot.create_for_test(
        directory=directory,
        endpoint=endpoint,
        context=context,
        clock=clock,
        deadline_ns=112_000_000_000,
        enabled=True,
    )
    phase = "REJECTED"
    safe = True
    raw: bytes | None = None
    response: bytes | None = None
    handle = None
    try:
        if name == "remote_expiry":
            # Source is minted now, then opened with only 100 ms of its ORIGINAL
            # 12-second lease. The advancing clock is not reset at channel open.
            await asyncio.sleep(11.9)
        root.open(endpoint)
        for step in range(2):
            raw = await root.deadlines.wait_io(pipe.read())
            response = root.receive_handshake(raw, endpoint)
            raw = None
            omit = (name == "missing_attest" and step == 0) or (
                name == "missing_ready" and step == 1
            )
            if step == 0 and name in {
                "response_prefix_max",
                "truncated_response_prefix",
                "truncated_response_body",
            }:
                if name == "response_prefix_max":
                    broken = (MAX_FRAME + 1).to_bytes(4, "big")
                elif name == "truncated_response_prefix":
                    broken = len(response).to_bytes(4, "big")[:3]
                else:
                    broken = len(response).to_bytes(4, "big") + response[:5]
                if os.write(1, broken) != len(broken):
                    raise PipeFailure()
                broken = b""
                if name != "response_prefix_max":
                    os.close(1)
            elif not omit:
                await root.deadlines.wait_io(pipe.write(response))
            response = None
        raw = await root.deadlines.wait_io(pipe.read())
        handle = root.receive_submit_and_prepare(
            raw,
            endpoint,
            oracle_case=(
                "ascii_16k"
                if name == "slow_reader"
                else name if name in SCENARIOS[:11] else "mixed_canary"
            ),
        )
        raw = None
        if name in {"held_readiness", "cancel_waiter", "revoke_readiness"}:
            root.readiness.hold()
        pending = asyncio.create_task(root.submit_prepared(handle))
        if name in {"held_readiness", "cancel_waiter", "revoke_readiness"}:
            await root.readiness.entered.wait()
            if name == "cancel_waiter":
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
                root.readiness.release()
                await root.owner.wait_for_idle()
            elif name == "revoke_readiness":
                root.revoke_source()
        if name != "cancel_waiter":
            await pending
        await root.owner.wait_for_idle()
        observed = root.owner.read(handle.request)
        if observed is None:
            raise PipeFailure()
        phase = observed.phase.value.upper()
        if root.consumer.calls == 1 and (
            not root.original_identity_match
            or root.consumer.last_body_identity != root.decrypted_identity
        ):
            raise PipeFailure()
        if name == "lost_ack_recovery":
            # This is the only success exit of the fixed crash child: actual
            # original consumer identity/effect and durable ACK are established
            # before losing the independent result. The parent can therefore
            # attribute effect=1 to this checked exit, never to a scenario name.
            if (
                catalog_path is None
                or phase != "ACKNOWLEDGED"
                or root.consumer.calls != 1
                or root.consumer.byte_count != 16
                or not root.original_identity_match
                or root.consumer.last_body_identity != root.decrypted_identity
            ):
                raise PipeFailure()
            catalog = root.recovery_catalog(name, handle.request)
            encoded = json.dumps(catalog, separators=(",", ":"), ensure_ascii=True).encode("ascii")
            if len(encoded) > METADATA_LIMIT:
                raise PipeFailure()
            catalog_path.write_bytes(encoded)
            # Exit-crash, not SIGKILL, user Stop or source cancellation. Neither
            # aclose nor finally can publish a result or rewrite the journal.
            os._exit(0)
        # Metadata receipts remain readable with body authority gone.
        root.revoke_source()
        if root.owner.read(handle.request) != observed:
            raise PipeFailure()
    except (Exception, asyncio.CancelledError) as error:
        safe = _safe_error(error)
        if name in {
            "missing_attest",
            "missing_confirm",
            "missing_ready",
            "missing_submit",
            "held_writable",
            "remote_expiry",
        }:
            phase = "EXPIRED"
            safe = safe and root.deadlines.expired.done() and root.state == "CLOSED"
        else:
            phase = "REJECTED"
    finally:
        raw = response = None
        safe = safe and s03_usage().channel_reserved_bytes == 1_048_576
        await root.aclose()
        pipe.close()
        if name == "remote_expiry":
            # Keep only the OS relay endpoint alive briefly. Application IO has
            # retired; Web has received no remote-expiry signal and may publish
            # once into the opaque pipe. No frame is read/decrypted/prepared.
            await asyncio.sleep(0.3)
    if name == "prefix_max" and pipe.allocated_max != 0:
        safe = False
    usage = s03_usage()
    drained = (
        root.pool_drained
        and not pipe.pending_read
        and not pipe.pending_write
        and usage.channel_reserved_bytes == 0
        and usage.active_waiters == 0
        and usage.active_timers == 0
    )
    return _result(
        name,
        phase,
        root.consumer.calls,
        root.consumer.byte_count,
        root.original_identity_match,
        drained,
        safe,
    )


def _recover_after_process_loss(name: str, directory: Path, catalog_path: Path) -> dict[str, Any]:
    """Fixed parent catalog; the child is this known peer, never a wire command."""
    child = os.fork()
    if child == 0:
        try:
            asyncio.run(_run(name, directory, catalog_path=catalog_path))
        except BaseException:
            os._exit(1)
        os._exit(1)
    _, status = os.waitpid(child, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise PipeFailure()
    if not catalog_path.is_file() or catalog_path.stat().st_size > METADATA_LIMIT:
        raise PipeFailure()
    catalog = json.loads(catalog_path.read_text(encoding="ascii"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    from agentbox_runtime.kebui_s03_submit import SyntheticS03Recovery

    recovery = SyntheticS03Recovery.open(
        catalog, directory=directory, context=context_for(fixture, name), scenario=name
    )
    try:
        observed = recovery.read()
        if observed is None or observed.phase.value.upper() != "UNKNOWN":
            raise PipeFailure()
        if hasattr(recovery, "submit") or hasattr(recovery, "issuer"):
            raise PipeFailure()
        # Child exit 0 is reachable only after the exact effect=1/byte_count=16
        # and original-object assertions above. Recovery never owns a consumer.
        return _result(name, "UNKNOWN", effects=1, count=16, identity=True)
    finally:
        recovery.close()


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        return 2
    name = sys.argv[1]
    safe = False
    result: dict[str, Any] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="agentbox-s03-peer-") as temporary:
            directory = Path(temporary) / "journal"
            if name == "lost_ack_recovery":
                result = _recover_after_process_loss(
                    name, directory, Path(temporary) / "catalog.json"
                )
            else:
                result = asyncio.run(_run(name, directory))
            # The child and original journal are gone before the result claims
            # retirement. Only the fixed scalar result leaves this process.
        safe = True
    except BaseException:
        pass
    if not safe or result is None:
        os.write(2, b"s03_invalid")
        return 1
    _write_metadata(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
