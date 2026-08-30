from __future__ import annotations

import asyncio

import pytest
from agentbox_protocol import ABWSError, ABWSFramedStreamPump, ABWSFrameType, encode_frame


class FakeReader:
    def __init__(self, chunks: list[bytes], *, error: BaseException | None = None) -> None:
        self.chunks = list(chunks)
        self.error = error
        self.read_sizes: list[int] = []

    async def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        if self.error is not None:
            raise self.error
        await asyncio.sleep(0)
        return self.chunks.pop(0) if self.chunks else b""


class FakeWriter:
    def __init__(self, *, error: BaseException | None = None) -> None:
        self.writes: list[bytes] = []
        self.error = error
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.error is not None:
            raise self.error
        self.writes.append(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error

    def close(self) -> None:
        self.closed = True


def _control(request_id: str) -> dict[str, object]:
    return {"protocol_version": 1, "request_id": request_id}


async def _collect(pump: ABWSFramedStreamPump) -> list[object]:
    return [frame async for frame in pump.receive()]


def test_receive_handles_fragmented_and_coalesced_frames_with_bounded_reads() -> None:
    first = encode_frame(ABWSFrameType.PING, _control("one"), 1)
    second = encode_frame(ABWSFrameType.PONG, _control("two"), 2)
    reader = FakeReader([first[:3], first[3:] + second])
    writer = FakeWriter()
    pump = ABWSFramedStreamPump(reader, writer, read_chunk_size=17)

    frames = asyncio.run(_collect(pump))

    assert [frame.frame_type for frame in frames] == [ABWSFrameType.PING, ABWSFrameType.PONG]
    assert reader.read_sizes == [17, 17, 17]
    assert writer.closed
    assert pump.closed


def test_send_has_independent_contiguous_sequence_and_serializes_frames() -> None:
    reader = FakeReader([])
    writer = FakeWriter()
    pump = ABWSFramedStreamPump(reader, writer, first_outbound_sequence=9)

    first = asyncio.run(pump.send(ABWSFrameType.PING, _control("one")))
    second = asyncio.run(pump.send(ABWSFrameType.PONG, _control("two")))

    assert (first, second) == (9, 10)
    assert writer.writes
    assert int.from_bytes(writer.writes[0][12:20], "big") == 9
    assert int.from_bytes(writer.writes[1][12:20], "big") == 10


def test_partial_eof_fails_closed() -> None:
    frame = encode_frame(ABWSFrameType.PING, _control("one"), 1)
    reader = FakeReader([frame[:-1]])
    writer = FakeWriter()
    pump = ABWSFramedStreamPump(reader, writer)

    with pytest.raises(ABWSError, match="ended before a complete frame"):
        asyncio.run(_collect(pump))
    assert pump.closed
    assert writer.closed


def test_read_timeout_fails_closed() -> None:
    class SlowReader:
        async def read(self, size: int) -> bytes:
            await asyncio.sleep(0.05)
            return b""

    writer = FakeWriter()
    pump = ABWSFramedStreamPump(SlowReader(), writer, read_timeout=0.001)

    with pytest.raises(ABWSError, match="stream read failed"):
        asyncio.run(_collect(pump))
    assert pump.closed
    assert writer.closed


def test_receive_cancellation_fails_closed() -> None:
    async def scenario() -> None:
        class BlockingReader:
            async def read(self, size: int) -> bytes:
                await asyncio.Future()

        writer = FakeWriter()
        pump = ABWSFramedStreamPump(BlockingReader(), writer)
        task = asyncio.create_task(_collect(pump))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pump.closed
        assert writer.closed

    asyncio.run(scenario())
