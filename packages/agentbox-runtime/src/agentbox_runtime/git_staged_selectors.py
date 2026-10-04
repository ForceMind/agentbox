"""Runtime-only short-lived staged selectors, not content authorization.

There is deliberately no RPC/API composition, wire codec, storage or logging.
The trusted context resolver must supply the CURRENT formal Project binding,
Runtime epoch and active API session scope. Raw cookies/CSRF are not inputs.
A future encrypted-content admission must provide that resolver separately.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import re
import secrets
import struct
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field

from agentbox_core.waw import (
    WAWDomainError,
    validate_binding_digest,
    validate_positive_u64,
    validate_project_id,
    validate_runtime_host_installation_id,
)
from agentbox_protocol.a3_content import ContentContext, selector_commitment, validate_context

from agentbox_runtime.git_staged_reader import GitStagedPatchReader, StagedPatchObservation
from agentbox_runtime.git_staged_selection import observe_staged_snapshot
from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.project import validate_project_id as validate_relative_key
from agentbox_runtime.waw_lifecycle import WAWProjectBinding

# One closed payload: version, monotonic issuance/expiry, sorted entry index,
# full snapshot digest, opaque context commitment; followed by HMAC-SHA256.
_PAYLOAD = struct.Struct(">BQQI32s32s")
_TOKEN_BYTES = _PAYLOAD.size + 32
_TOKEN_LENGTH = 156
_TOKEN = re.compile(r"[A-Za-z0-9_-]{156}\Z")
_TTL_NS = 30_000_000_000
_MAX_ACTIVE = 4
_MAX_BURNED_NONCES = 128
_HANDLE_SEAL = object()
_DOMAIN = b"agentbox-runtime-staged-selector-v1\0staged\0"


def _stale() -> RuntimeOperationError:
    return RuntimeOperationError("PATCH_STALE", "Staged selection changed", category="conflict")


@dataclass(frozen=True, repr=False)
class StagedSelectorContext:
    """Trusted current inputs, never reconstructed from a caller's token.

    ``session_scope`` is a 32-byte noncredential scope from trusted API session
    admission, not a cookie/CSRF value and not an authorization by itself.
    The resolver returns None for revoked/not-READY/ambiguous/unbound Projects.
    """

    binding: WAWProjectBinding
    runtime_epoch: str
    session_scope: bytes


@dataclass(frozen=True)
class StagedSelectorEntry:
    entry_index: int
    path: str
    kind: str
    selection_id: str | None = field(repr=False)
    unavailable_code: str | None
    side: str = "staged"


@dataclass(frozen=True)
class StagedSelectorObservation:
    entries: tuple[StagedSelectorEntry, ...]
    snapshot_sha256: str
    schema_version: str = "runtime-staged-observation-v2"


ContextResolver = Callable[[str, bytes], StagedSelectorContext | None]


class AdmittedStagedRead:
    """Sealed Runtime-owned handle, valid only inside its owner's admission scope.

    Original authenticated expiry is preserved. No unverified token fields are
    exposed or parsed by the channel. This is in-process custody, not protection
    from code already controlling the Runtime process.
    """

    def __init__(
        self,
        seal: object,
        *,
        context: ContentContext,
        expires_ns: int,
        check: Callable[[], None],
        read: Callable[[], Awaitable[StagedPatchObservation]],
    ) -> None:
        if seal is not _HANDLE_SEAL:
            raise TypeError("Runtime admission is required")
        self.__context = validate_context(context)
        self.__expires_ns = expires_ns
        self.__check = check
        self.__read = read
        self.__closed = False
        self.__started = False

    @property
    def context(self) -> ContentContext:
        self.check()
        return validate_context(self.__context)

    @property
    def expires_ns(self) -> int:
        self.check()
        return self.__expires_ns

    def check(self) -> None:
        if self.__closed:
            raise _stale()
        try:
            self.__check()
        except BaseException:
            self.close()
            raise

    async def read(self) -> StagedPatchObservation:
        try:
            self.check()
            if self.__started:
                raise _stale()
            self.__started = True
            result = await self.__read()
            self.check()
            return result
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        self.__closed = True

    def __repr__(self) -> str:
        return "<AdmittedStagedRead redacted>"


class GitStagedSelectors:
    """Fixed in-process observation/read owner with a fresh ephemeral MAC key.

    The constructor is trusted Runtime composition. No exported sign/verify or
    caller-path read exists. Concurrent operations own independent held views;
    close fences all operations and drops the key (not a zeroization claim).
    """

    def __init__(self, reader: GitStagedPatchReader, *, context: ContextResolver) -> None:
        if type(reader) is not GitStagedPatchReader or not callable(context):
            raise TypeError("fixed staged reader and trusted context resolver are required")
        self._reader = reader
        self._context = context
        self._key: bytes | None = secrets.token_bytes(32)
        self._pid = os.getpid()
        self._lock = threading.RLock()
        self._last_ns = 0
        self._active = 0
        # Lives with the selector key/process owner, never with a channel.
        self._burned_nonces: dict[bytes, int] = {}
        self._handles: set[AdmittedStagedRead] = set()

    def close(self) -> None:
        with self._lock:
            self._key = None
            for handle in self._handles:
                handle.close()

    def _now(self) -> int:
        # All calls are under _lock. A regressing/invalid clock permanently
        # fences this owner, rather than extending already-issued validity.
        now = time.monotonic_ns()
        if (
            self._key is None
            or self._pid != os.getpid()
            or type(now) is not int
            or not self._last_ns <= now <= (2**64 - 1 - _TTL_NS)
        ):
            self._key = None
            raise _stale()
        self._last_ns = now
        return now

    @contextmanager
    def _operation(self) -> Iterator[None]:
        with self._lock:
            self._now()
            if self._active >= _MAX_ACTIVE:
                raise RuntimeOperationError(
                    "PATCH_UNAVAILABLE_BUSY", "Staged reader is busy", category="unavailable"
                )
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1

    def _current(self, project_id: str, session_scope: bytes) -> StagedSelectorContext:
        try:
            validate_project_id(project_id)
            if type(session_scope) is not bytes or len(session_scope) != 32:
                raise _stale()
            current = self._context(project_id, session_scope)
            if (
                type(current) is not StagedSelectorContext
                or type(current.binding) is not WAWProjectBinding
                or current.binding.project_id != project_id
                or type(current.session_scope) is not bytes
                or current.session_scope != session_scope
            ):
                raise _stale()
            binding = current.binding
            validate_relative_key(binding.relative_key)
            validate_binding_digest(binding.binding_digest)
            validate_runtime_host_installation_id(binding.runtime_host_installation_id)
            for value in (
                current.runtime_epoch,
                binding.project_revision,
                binding.binding_revision,
                binding.runtime_host_installation_revision,
            ):
                # Strict canonical bounded decimal, never bool/int coercion.
                if type(value) is not str or re.fullmatch(r"[1-9][0-9]{0,19}", value) is None:
                    raise _stale()
                validate_positive_u64(int(value), field="staged selector context")
        except (RuntimeOperationError, WAWDomainError, ValueError, TypeError):
            raise _stale() from None
        return current

    def _context_digest(self, current: StagedSelectorContext) -> bytes:
        binding = current.binding
        encoded = json.dumps(
            [
                binding.project_id,
                binding.relative_key,
                binding.project_revision,
                binding.binding_revision,
                binding.binding_digest,
                binding.runtime_host_installation_id,
                binding.runtime_host_installation_revision,
                current.runtime_epoch,
                current.session_scope.hex(),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        assert self._key is not None
        return hmac.digest(self._key, _DOMAIN + b"context\0" + encoded, "sha256")

    def _require_current(self, initial: StagedSelectorContext) -> None:
        if self._current(initial.binding.project_id, initial.session_scope) != initial:
            raise _stale()

    async def observe(self, project_id: str, session_scope: bytes) -> StagedSelectorObservation:
        """Issue selectors only from one current complete staged observation."""
        with self._operation():
            current = self._current(project_id, session_scope)
            async with self._reader._observation(current.binding.relative_key) as (_, view, raw):
                observed = observe_staged_snapshot(raw)
                self._reader._revalidate(view)
                with self._lock:
                    self._require_current(current)
                    now = self._now()
                    context_digest = self._context_digest(current)
                    assert self._key is not None
                    entries: list[StagedSelectorEntry] = []
                    for index, entry in enumerate(observed.entries):
                        token = None
                        if entry.selection is not None:
                            payload = _PAYLOAD.pack(
                                1,
                                now,
                                now + _TTL_NS,
                                index,
                                bytes.fromhex(observed.sha256),
                                context_digest,
                            )
                            mac = hmac.digest(self._key, _DOMAIN + payload, "sha256")
                            token = base64.urlsafe_b64encode(payload + mac).decode("ascii")
                        entries.append(
                            StagedSelectorEntry(
                                index, entry.path, entry.kind, token, entry.unavailable_code
                            )
                        )
                    # Key/currentness/clock and held-source checks also fence
                    # issuance work, not just the beginning of observation.
                    self._require_current(current)
                    if self._now() >= now + _TTL_NS:
                        raise _stale()
                    self._reader._revalidate(view)
                    return StagedSelectorObservation(tuple(entries), observed.sha256)

    def _decode(self, selection_id: str) -> tuple[int, int, int, bytes, bytes]:
        # Exact alphabet and size before decoding or authentication; no JSON,
        # generic signer, configurable algorithms or variable payload claims.
        if (
            type(selection_id) is not str
            or len(selection_id) != _TOKEN_LENGTH
            or _TOKEN.fullmatch(selection_id) is None
        ):
            raise _stale()
        raw = base64.urlsafe_b64decode(selection_id)
        if (
            len(raw) != _TOKEN_BYTES
            or base64.urlsafe_b64encode(raw).decode("ascii") != selection_id
        ):
            raise _stale()
        payload, mac = raw[:-32], raw[-32:]
        with self._lock:
            self._now()
            assert self._key is not None
            if not hmac.compare_digest(mac, hmac.digest(self._key, _DOMAIN + payload, "sha256")):
                raise _stale()
        version, issued, expires, index, snapshot, context = _PAYLOAD.unpack(payload)
        if version != 1 or expires - issued != _TTL_NS:
            raise _stale()
        return issued, expires, index, snapshot, context

    async def read(
        self, project_id: str, session_scope: bytes, selection_id: str
    ) -> StagedPatchObservation:
        """Resolve the path only from the same held view used to start the read."""
        with self._operation():
            issued, expires, index, digest, context = self._decode(selection_id)
            current = self._current(project_id, session_scope)

            def check_current() -> None:
                with self._lock:
                    self._require_current(current)
                    now = self._now()
                    if not issued <= now < expires or not hmac.compare_digest(
                        context, self._context_digest(current)
                    ):
                        raise _stale()

            check_current()
            async with self._reader._observation(current.binding.relative_key) as (
                executable,
                view,
                raw,
            ):
                observed = observe_staged_snapshot(raw)
                if not hmac.compare_digest(digest, bytes.fromhex(observed.sha256)) or not (
                    0 <= index < len(observed.entries)
                ):
                    raise _stale()
                selected = observed.entries[index].selection
                if selected is None:
                    raise _stale()
                # This is the actual extraction view, not a validate-and-reopen
                # preflight. _read_observed checks again with no await before
                # each patch child and at result publication.
                return await self._reader._read_observed(
                    executable, view, raw, selected, check_current=check_current
                )

    @asynccontextmanager
    async def admit(
        self, project_id: str, session_scope: bytes, selection_id: str, request_nonce: bytes
    ) -> AsyncIterator[AdmittedStagedRead]:
        """Burn one nonce and hold validation/extraction view until channel closes.

        Four existing operation slots include admitted channels. A failed or
        cancelled channel retains its nonce until ORIGINAL verified expiry.
        Recreating a channel cannot reset this owner's ledger. Recreating the
        owner changes its key, invalidating every previously issued selector.
        """
        handle: AdmittedStagedRead | None = None
        with self._operation():
            issued, expires, index, digest, commitment = self._decode(selection_id)
            current = self._current(project_id, session_scope)

            def check_current() -> None:
                with self._lock:
                    self._require_current(current)
                    now = self._now()
                    if not issued <= now < expires or not hmac.compare_digest(
                        commitment, self._context_digest(current)
                    ):
                        raise _stale()

            with self._lock:
                check_current()
                if type(request_nonce) is not bytes or len(request_nonce) != 32:
                    raise _stale()
                now = self._now()
                self._burned_nonces = {
                    key: end for key, end in self._burned_nonces.items() if now < end
                }
                if request_nonce in self._burned_nonces:
                    raise _stale()
                if len(self._burned_nonces) >= _MAX_BURNED_NONCES:
                    raise RuntimeOperationError(
                        "PATCH_UNAVAILABLE_BUSY", "Staged reader is busy", category="unavailable"
                    )
                self._burned_nonces[request_nonce] = expires
            try:
                async with self._reader._observation(
                    current.binding.relative_key, check_current=check_current
                ) as (
                    executable,
                    view,
                    raw,
                ):
                    check_current()
                    observed = observe_staged_snapshot(raw)
                    if not hmac.compare_digest(digest, bytes.fromhex(observed.sha256)) or not (
                        0 <= index < len(observed.entries)
                    ):
                        raise _stale()
                    selected = observed.entries[index].selection
                    if selected is None:
                        raise _stale()
                    self._reader._revalidate(view)
                    binding = current.binding
                    content: ContentContext = {
                        "protocol_id": "agentbox-a3-content/v1",
                        "protocol_version": 1,
                        "project_id": binding.project_id,
                        "project_revision": binding.project_revision,
                        "binding_revision": binding.binding_revision,
                        "binding_digest": binding.binding_digest,
                        "runtime_host_installation_id": binding.runtime_host_installation_id,
                        "runtime_host_installation_revision": (
                            binding.runtime_host_installation_revision
                        ),
                        "runtime_epoch": current.runtime_epoch,
                        "session_scope": current.session_scope.hex(),
                        "selector_commitment": selector_commitment(selection_id),
                        "side": "staged",
                        "request_nonce": request_nonce.hex(),
                    }

                    async def read() -> StagedPatchObservation:
                        assert handle is not None
                        return await self._reader._read_observed(
                            executable, view, raw, selected, check_current=handle.check
                        )

                    handle = AdmittedStagedRead(
                        _HANDLE_SEAL,
                        context=content,
                        expires_ns=expires,
                        check=check_current,
                        read=read,
                    )
                    with self._lock:
                        self._handles.add(handle)
                        handle.check()
                    yield handle
            finally:
                if handle is not None:
                    handle.close()
                    with self._lock:
                        self._handles.discard(handle)
