"""Bounded asyncio transport adapter for the ABWS outer framing.

This module intentionally starts below WebSocket/Noise admission.  It only
consumes an already-admitted byte stream, parses ABWS frames, and serializes
one ordered outbound leg.  It does not decrypt terminal payloads or perform
any Runtime/API side effects.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any, Protocol

from agentbox_protocol.abws import ABWSError, ABWSFrame, ABWSFrameType, ABWSParser, encode_frame

DEFAULT_READ_CHUNK_SIZE = 64 * 1024
MAX_READ_CHUNK_SIZE = 64 * 1024


class _AsyncReader(Protocol):
    async def read(self, n: int = -1) -> bytes: ...


class _AsyncWriter(Protocol):
    def write(self, data: bytes) -> Any: ...

    async def drain(self) -> None: ...

    def close(self) -> Any: ...


class ABWSFramedStreamPump:
    """Read and write bounded, independently sequenced ABWS frame legs.

    ``reader`` and ``writer`` must already represent an admitted transport.
    A malformed frame, partial EOF, read timeout, I/O error, or cancellation
    closes the writer immediately and leaves the pump unusable.  Outbound
    writes are serialized so a caller cannot interleave frame bytes or reuse a
    sequence number.
    """

    def __init__(
        self,
        reader: _AsyncReader,
        writer: _AsyncWriter,
        *,
        first_inbound_sequence: int = 1,
        first_outbound_sequence: int = 1,
        read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
        read_timeout: float | None = None,
    ) -> None:
        if not 1 <= first_inbound_sequence <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("first_inbound_sequence must be a non-zero uint64")
        if not 1 <= first_outbound_sequence <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("first_outbound_sequence must be a non-zero uint64")
        if not 1 <= read_chunk_size <= MAX_READ_CHUNK_SIZE:
            raise ValueError("read_chunk_size must be between 1 and 65536")
        if read_timeout is not None and read_timeout <= 0:
            raise ValueError("read_timeout must be positive")
        self._reader = reader
        self._writer = writer
        self._parser = ABWSParser(first_sequence=first_inbound_sequence)
        self._next_outbound_sequence = first_outbound_sequence
        self._read_chunk_size = read_chunk_size
        self._read_timeout = read_timeout
        self._write_lock = asyncio.Lock()
        self._receive_started = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def next_outbound_sequence(self) -> int:
        return self._next_outbound_sequence

    async def receive(self) -> AsyncIterator[ABWSFrame]:
        """Yield inbound frames until clean EOF, failing closed on any error."""

        if self._receive_started:
            raise RuntimeError("ABWS receive may only be started once")
        if self._closed:
            raise ABWSError("ABWS stream pump is closed")
        self._receive_started = True
        try:
            while True:
                chunk = await self._read()
                if not chunk:
                    self._parser.finish()
                    self._close()
                    return
                for frame in self._parser.feed(chunk):
                    yield frame
        except asyncio.CancelledError:
            self._close()
            raise
        except (ABWSError, OSError, TimeoutError) as exc:
            self._close()
            if isinstance(exc, ABWSError):
                raise
            raise ABWSError("ABWS stream read failed") from exc

    async def send(
        self,
        frame_type: ABWSFrameType | int,
        payload: bytes | bytearray | memoryview | dict[str, Any],
    ) -> int:
        """Encode and write one outbound frame, returning its sequence."""

        if self._closed:
            raise ABWSError("ABWS stream pump is closed")
        async with self._write_lock:
            if self._closed:
                raise ABWSError("ABWS stream pump is closed")
            sequence = self._next_outbound_sequence
            try:
                encoded = encode_frame(frame_type, payload, sequence)
                self._writer.write(encoded)
                await self._writer.drain()
            except asyncio.CancelledError:
                self._close()
                raise
            except (ABWSError, OSError, TimeoutError) as exc:
                self._close()
                if isinstance(exc, ABWSError):
                    raise
                raise ABWSError("ABWS stream write failed") from exc
            if sequence == 0xFFFFFFFFFFFFFFFF:
                self._close()
            else:
                self._next_outbound_sequence += 1
            return sequence

    async def _read(self) -> bytes:
        if self._read_timeout is None:
            return await self._reader.read(self._read_chunk_size)
        return await asyncio.wait_for(
            self._reader.read(self._read_chunk_size), timeout=self._read_timeout
        )

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with suppress(Exception):
            self._writer.close()


__all__ = ["ABWSFramedStreamPump"]
