"""Capability-aware Runtime adapter interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentbox_runtime.models import CodexStatus, PairCodeResult, RemoteActionResult


@runtime_checkable
class RuntimeAdapter(Protocol):
    @property
    def runtime_name(self) -> str: ...


@runtime_checkable
class CodexRuntime(Protocol):
    async def status(self) -> CodexStatus: ...

    async def start_remote(self) -> RemoteActionResult: ...

    async def stop_remote(self) -> RemoteActionResult: ...

    async def generate_pair_code(self) -> PairCodeResult: ...
