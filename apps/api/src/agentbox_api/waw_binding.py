"""Single-authority API bootstrap for the WAW Runtime control endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from agentbox_api.waw_control_client import (
    WAWControlClient,
    WAWControlClientError,
    validate_runtime_bind_attestation,
)

_ALLOWED_LIFECYCLE_REQUESTS = frozenset(
    {
        "workspace.project_binding.register",
        "workspace.workspace.start",
        "workspace.workspace.stop",
        "workspace.workspace.status",
        "workspace.workspace.reconcile",
        "workspace.attach.prepare",
        "workspace.attach.detach",
    }
)


class WAWBindTransport(Protocol):
    async def request(self, action: str, request: dict[str, Any]) -> dict[str, Any]: ...


class RuntimeEpochClassifier(Protocol):
    def classify_runtime_epoch(
        self,
        *,
        runtime_host_installation_id: str,
        runtime_host_installation_revision: int,
        observed_runtime_epoch: str,
    ) -> object: ...


RequestIdFactory = Callable[[], str | Awaitable[str]]


class WAWRuntimeBindCoordinator:
    """Perform exactly one serialized API-authority bind per process epoch."""

    def __init__(
        self,
        client: WAWBindTransport | WAWControlClient,
        *,
        api_authority_epoch: str,
        authority_nonce: str,
        expected_runtime_host_installation_id: str,
        expected_runtime_host_installation_revision: str,
        expected_host_manifest_digest: str,
        expected_project_root_manifest_digest: str,
        request_id_factory: RequestIdFactory,
        expected_runtime_epoch: str | None = None,
        runtime_epoch_classifier: RuntimeEpochClassifier | None = None,
    ) -> None:
        if not isinstance(api_authority_epoch, str) or not api_authority_epoch:
            raise ValueError("api_authority_epoch must be non-empty")
        if not isinstance(authority_nonce, str) or not authority_nonce:
            raise ValueError("authority_nonce must be non-empty")
        self._client = client
        self._epoch = api_authority_epoch
        self._nonce = authority_nonce
        self._expected_host_id = expected_runtime_host_installation_id
        self._expected_host_revision = expected_runtime_host_installation_revision
        self._expected_host_manifest = expected_host_manifest_digest
        self._expected_project_root_manifest = expected_project_root_manifest_digest
        self._expected_runtime_epoch = expected_runtime_epoch
        self._runtime_epoch_classifier = runtime_epoch_classifier
        self._request_id_factory = request_id_factory
        self._bound_response: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    def _invalidate(self) -> None:
        """Forget Runtime state after a restart or lost bootstrap."""

        self._bound_response = None

    async def _reconnect(self) -> None:
        reconnect = getattr(self._client, "reconnect", None)
        if callable(reconnect):
            result = reconnect()
            if isinstance(result, Awaitable):
                await result

    async def _bind_locked(self) -> dict[str, Any]:
        if self._bound_response is not None:
            return dict(self._bound_response)
        request_id = self._request_id_factory()
        if isinstance(request_id, Awaitable):
            request_id = await request_id
        if not isinstance(request_id, str):
            raise WAWControlClientError("PROTOCOL_INVALID", "bind request ID is invalid")
        request = {
            "protocol_version": 1,
            "request_id": request_id,
            "action": "workspace.api_authority.bind",
            "api_authority_epoch": self._epoch,
            "authority_nonce": self._nonce,
        }
        try:
            response = await self._client.request("workspace.api_authority.bind", request)
        except WAWControlClientError as exc:
            if exc.code == "RUNTIME_UNAVAILABLE":
                # Never retain an attestation across a transport poison or
                # reconnect attempt.  The next call must bind afresh.
                self._invalidate()
                await self._reconnect()
            raise
        if response.get("status") == "ERROR":
            code = response.get("error_code")
            if code in {"BINDING_BOOTSTRAP_REQUIRED", "RUNTIME_INSTALLATION_MISMATCH"}:
                self._invalidate()
                await self._reconnect()
            raise WAWControlClientError(code or "PROTOCOL_INVALID", "Runtime bind failed")
        try:
            verified = validate_runtime_bind_attestation(
                response,
                expected_runtime_host_installation_id=self._expected_host_id,
                expected_runtime_host_installation_revision=self._expected_host_revision,
                expected_host_manifest_digest=self._expected_host_manifest,
                expected_project_root_manifest_digest=self._expected_project_root_manifest,
                expected_runtime_epoch=self._expected_runtime_epoch,
            )
        except WAWControlClientError as exc:
            if exc.code == "RUNTIME_INSTALLATION_MISMATCH":
                self._invalidate()
                await self._reconnect()
            raise
        runtime_epoch = verified.get("runtime_epoch")
        if not isinstance(runtime_epoch, str):
            self._invalidate()
            raise WAWControlClientError(
                "RUNTIME_INSTALLATION_MISMATCH", "Runtime bind epoch is unavailable"
            )
        if self._runtime_epoch_classifier is not None:
            self._runtime_epoch_classifier.classify_runtime_epoch(
                runtime_host_installation_id=self._expected_host_id,
                runtime_host_installation_revision=int(self._expected_host_revision),
                observed_runtime_epoch=runtime_epoch,
            )
        self._bound_response = dict(verified)
        return dict(verified)

    @property
    def bound(self) -> bool:
        return self._bound_response is not None

    @property
    def attestation(self) -> dict[str, Any] | None:
        return None if self._bound_response is None else dict(self._bound_response)

    async def bind(self) -> dict[str, Any]:
        """Bind the current API epoch, returning the verified Runtime attestation."""

        async with self._lock:
            return await self._bind_locked()

    async def request_lifecycle(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        """Issue one bound lifecycle request through the closed client.

        The caller still supplies only typed, identity-bound payloads.  This
        coordinator deliberately has no generic Runtime action escape hatch;
        the allowlist mirrors the WAW control codec's closed action set.
        """

        if action not in _ALLOWED_LIFECYCLE_REQUESTS:
            raise WAWControlClientError("PROTOCOL_INVALID", "WAW lifecycle action is not enabled")
        async with self._lock:
            await self._bind_locked()
            try:
                response = await self._client.request(action, request)
            except WAWControlClientError as exc:
                if exc.code == "RUNTIME_UNAVAILABLE":
                    self._invalidate()
                    await self._reconnect()
                raise
            if response.get("status") == "ERROR":
                code = response.get("error_code")
                if code in {"BINDING_BOOTSTRAP_REQUIRED", "RUNTIME_INSTALLATION_MISMATCH"}:
                    self._invalidate()
                    await self._reconnect()
                raise WAWControlClientError(
                    code or "PROTOCOL_INVALID", "Runtime lifecycle request failed"
                )
            expected_epoch = (
                self._bound_response.get("runtime_epoch") if self._bound_response else None
            )
            if isinstance(expected_epoch, str) and response.get("runtime_epoch") != expected_epoch:
                self._invalidate()
                await self._reconnect()
                raise WAWControlClientError(
                    "RUNTIME_INSTALLATION_MISMATCH", "WAW lifecycle response epoch is stale"
                )
            return response


__all__ = ["RuntimeEpochClassifier", "WAWBindTransport", "WAWRuntimeBindCoordinator"]
