"""Default-off A3 test composition using the existing lifecycle/Project owners.

No listener, RPC, production key acquisition or alternate Project registry exists.
The API port returns only copied noncredential facts; no API session object enters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agentbox_protocol.a3_admission import A3CurrentAdmission
from agentbox_protocol.a3_content import ContentError

from agentbox_runtime.a3_content_session import OpaqueContentPort, serve_admitted_staged_read
from agentbox_runtime.git_staged_reader import GitStagedPatchReader
from agentbox_runtime.git_staged_selectors import GitStagedSelectors, StagedSelectorContext
from agentbox_runtime.waw_encrypted_stream import RuntimePeer
from agentbox_runtime.waw_lifecycle import WAWLifecycleRegistry, WAWProjectBinding
from agentbox_runtime.waw_runtime_executor import WAWSupervisorExecutor


@dataclass(frozen=True, slots=True, repr=False)
class A3SyntheticTestKey:
    """Published synthetic A3-only fixture material; never a WAW production key port."""

    private_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.private_bytes) is not bytes or len(self.private_bytes) != 32:
            raise ValueError("synthetic A3 key must be 32 bytes")


class A3TestReadOwner:
    def __init__(
        self,
        reader: GitStagedPatchReader,
        lifecycle: WAWLifecycleRegistry,
        executor: WAWSupervisorExecutor,
        peer: RuntimePeer,
        current: Callable[[str, bytes], A3CurrentAdmission | None],
        key: A3SyntheticTestKey,
        *,
        enabled_for_tests: bool = False,
    ) -> None:
        if enabled_for_tests is not True or type(key) is not A3SyntheticTestKey:
            raise ContentError("PATCH_REVOKED")
        if (
            type(lifecycle) is not WAWLifecycleRegistry
            or type(executor) is not WAWSupervisorExecutor
        ):
            raise TypeError("existing fixed Runtime owners required")
        self._lifecycle, self._executor, self._peer = lifecycle, executor, peer
        self._current, self._key = current, key
        self._closed = False
        self.selectors = GitStagedSelectors(reader, context=self._resolve)
        lifecycle.replace_content_selector_owner(self.selectors)

    def close(self) -> None:
        self._closed = True
        self.selectors.close()

    def _resolve(self, project_id: str, scope: bytes) -> StagedSelectorContext | None:
        if self._closed:
            return None
        try:
            facts = self._current(project_id, scope)
            binding = self._executor.content_project_binding(project_id)
            if (
                type(facts) is not A3CurrentAdmission
                or binding is None
                or facts.project_id != project_id
                or facts.session_scope != scope
                or type(facts.auth_epoch) is not int
                or facts.auth_epoch < 1
                or facts.runtime_epoch != self._executor.runtime_epoch
            ):
                return None
            expected = WAWProjectBinding(
                facts.project_id,
                facts.relative_key,
                facts.project_revision,
                facts.binding_revision,
                facts.binding_digest,
                facts.runtime_host_installation_id,
                facts.runtime_host_installation_revision,
            )
            if binding != expected or not self._lifecycle.content_project_current(
                binding, facts.runtime_epoch, self._peer, self.selectors
            ):
                return None
            return StagedSelectorContext(binding, facts.runtime_epoch, scope)
        except Exception:
            return None

    async def serve(
        self,
        project_id: str,
        session_scope: bytes,
        selection_id: str,
        request_nonce: bytes,
        port: OpaqueContentPort,
    ) -> None:
        try:
            async with self.selectors.admit(
                project_id, session_scope, selection_id, request_nonce
            ) as admitted:
                await serve_admitted_staged_read(admitted, self._key.private_bytes, port)
        finally:
            port.close()
