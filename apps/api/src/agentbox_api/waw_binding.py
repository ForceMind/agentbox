"""Single-authority API bootstrap for the WAW Runtime control endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Protocol, cast

from agentbox_api.waw_control_client import (
    BoundRuntimePeer,
    RuntimePeerBorrow,
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
_TEST_ONLY_TRANSPORT_TOKEN = object()


class WAWTestBindTransport(Protocol):
    """Explicit test-only compatibility port without process identity authority."""

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
        client: WAWControlClient | WAWTestBindTransport,
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
        _test_only_token: object | None = None,
    ) -> None:
        if not isinstance(api_authority_epoch, str) or not api_authority_epoch:
            raise ValueError("api_authority_epoch must be non-empty")
        if not isinstance(authority_nonce, str) or not authority_nonce:
            raise ValueError("authority_nonce must be non-empty")
        test_only = _test_only_token is _TEST_ONLY_TRANSPORT_TOKEN
        if type(client) is not WAWControlClient and not test_only:
            raise TypeError("production WAW binding requires WAWControlClient")
        self._client = client if type(client) is WAWControlClient else None
        self._test_transport: WAWTestBindTransport | None = (
            cast(WAWTestBindTransport, client) if test_only else None
        )
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
        self._bound_peer: BoundRuntimePeer | None = None
        self._peer_generation = 0
        self._client_replacement_required = False
        self._closing = False
        self._closed = False
        self._lock = asyncio.Lock()
        self._close_operation: asyncio.Task[None] | None = None

    @classmethod
    def test_only(
        cls,
        client: WAWTestBindTransport,
        **kwargs: Any,
    ) -> WAWRuntimeBindCoordinator:
        """Construct a metadata-only coordinator for unit fixtures."""

        return cls(client, _test_only_token=_TEST_ONLY_TRANSPORT_TOKEN, **kwargs)

    def _invalidate(self) -> None:
        """Irreversibly fence the published Runtime peer and attestation."""

        peer, self._bound_peer = self._bound_peer, None
        self._bound_response = None
        self._peer_generation += 1
        if self._client is not None:
            self._client_replacement_required = True
        if peer is not None:
            peer.poison()

    async def _replace_client_locked(self) -> None:
        if self._client is None or not self._client_replacement_required:
            return
        retired = self._client
        await retired.close()
        self._client = retired.replacement_after_close()
        self._client_replacement_required = False

    def _peer_is_current(self, peer: BoundRuntimePeer, generation: int) -> bool:
        return (
            not self._closing
            and not self._closed
            and self._bound_peer is peer
            and self._peer_generation == generation
            and self._bound_response is not None
        )

    def _require_open(self) -> None:
        if self._closing or self._closed:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime binding coordinator is closed"
            )

    async def _bind_locked(self) -> dict[str, Any]:
        self._require_open()
        if self._bound_response is not None and (
            self._bound_peer is None or self._bound_peer.current()
        ):
            return dict(self._bound_response)
        if self._bound_peer is not None:
            self._invalidate()
        await self._replace_client_locked()
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
        exchange = None
        try:
            if self._client is not None:
                exchange = await self._client.bind_exchange("workspace.api_authority.bind", request)
                response = exchange.response
            else:
                assert self._test_transport is not None
                response = await self._test_transport.request(
                    "workspace.api_authority.bind", request
                )
        except WAWControlClientError:
            self._invalidate()
            raise
        if response.get("status") == "ERROR":
            code = response.get("error_code")
            self._invalidate()
            if exchange is not None:
                exchange.invalidate()
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
            if verified.get("api_authority_epoch") != self._epoch:
                raise WAWControlClientError(
                    "RUNTIME_INSTALLATION_MISMATCH",
                    "Runtime bind response authority epoch is stale",
                )
        except WAWControlClientError:
            self._invalidate()
            if exchange is not None:
                exchange.invalidate()
            raise
        runtime_epoch = verified.get("runtime_epoch")
        if not isinstance(runtime_epoch, str):
            self._invalidate()
            if exchange is not None:
                exchange.invalidate()
            raise WAWControlClientError(
                "RUNTIME_INSTALLATION_MISMATCH", "Runtime bind epoch is unavailable"
            )
        try:
            if self._runtime_epoch_classifier is not None:
                self._runtime_epoch_classifier.classify_runtime_epoch(
                    runtime_host_installation_id=self._expected_host_id,
                    runtime_host_installation_revision=int(self._expected_host_revision),
                    observed_runtime_epoch=runtime_epoch,
                )
        except BaseException:
            self._invalidate()
            if exchange is not None:
                exchange.invalidate()
            raise
        if exchange is not None:
            self._require_open()
            generation = self._peer_generation + 1
            try:
                peer = exchange.publish(
                    generation=generation,
                    owner_current=self._peer_is_current,
                )
            except BaseException:
                self._invalidate()
                raise
            self._peer_generation = generation
            self._bound_peer = peer
        self._bound_response = dict(verified)
        return dict(verified)

    @property
    def bound(self) -> bool:
        if self._bound_response is None:
            return False
        peer = self._bound_peer
        if peer is not None and not peer.current():
            self._invalidate()
            return False
        return True

    @property
    def attestation(self) -> dict[str, Any] | None:
        return (
            dict(self._bound_response) if self.bound and self._bound_response is not None else None
        )

    def borrow_runtime_peer(self, peer_socket: Any) -> RuntimePeerBorrow:
        """Borrow the exact published Runtime pidfd for one stream connection."""

        self._require_open()
        peer = self._bound_peer
        if peer is None or self._bound_response is None:
            raise WAWControlClientError(
                "RUNTIME_UNAVAILABLE", "WAW Runtime binding is unavailable", retryable=True
            )
        try:
            borrow = peer.borrow(peer_socket)
        except WAWControlClientError:
            self._invalidate()
            raise
        if self._bound_peer is not peer or not borrow.current():
            borrow.close()
            self._invalidate()
            raise WAWControlClientError(
                "RUNTIME_PEER_FORBIDDEN", "WAW Runtime stream peer is stale"
            )
        return borrow

    async def bind(self) -> dict[str, Any]:
        """Bind the current API epoch, returning the verified Runtime attestation."""

        self._require_open()
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
        self._require_open()
        async with self._lock:
            await self._bind_locked()
            try:
                if self._client is not None:
                    peer = self._bound_peer
                    if peer is None:
                        raise WAWControlClientError(
                            "RUNTIME_UNAVAILABLE", "WAW Runtime peer is unavailable"
                        )
                    response = await self._client.request_bound(action, request, peer)
                else:
                    assert self._test_transport is not None
                    response = await self._test_transport.request(action, request)
            except WAWControlClientError:
                self._invalidate()
                raise
            if response.get("status") == "ERROR":
                code = response.get("error_code")
                if code in {"BINDING_BOOTSTRAP_REQUIRED", "RUNTIME_INSTALLATION_MISMATCH"}:
                    self._invalidate()
                raise WAWControlClientError(
                    code or "PROTOCOL_INVALID", "Runtime lifecycle request failed"
                )
            expected_epoch = (
                self._bound_response.get("runtime_epoch") if self._bound_response else None
            )
            observed_epoch = response.get("runtime_epoch")
            if (
                isinstance(expected_epoch, str)
                and observed_epoch is not None
                and observed_epoch != expected_epoch
            ):
                self._invalidate()
                raise WAWControlClientError(
                    "RUNTIME_INSTALLATION_MISMATCH", "WAW lifecycle response epoch is stale"
                )
            return response

    def close(self) -> Coroutine[Any, Any, None]:
        """Close the sole peer/client owner exactly once."""

        self._closing = True
        operation = self._close_operation
        if operation is None:
            operation = asyncio.create_task(self._perform_close())
            self._close_operation = operation
        return self._await_close(operation)

    async def _await_close(self, operation: asyncio.Task[None]) -> None:
        await asyncio.shield(operation)

    async def _perform_close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            peer, self._bound_peer = self._bound_peer, None
            self._bound_response = None
            self._peer_generation += 1
            if peer is not None:
                peer.close()
            if self._client is not None:
                await self._client.close()
            else:
                close = getattr(self._test_transport, "close", None)
                if callable(close):
                    result = close()
                    if isinstance(result, Awaitable):
                        await result


__all__ = [
    "RuntimeEpochClassifier",
    "WAWRuntimeBindCoordinator",
    "WAWTestBindTransport",
]
