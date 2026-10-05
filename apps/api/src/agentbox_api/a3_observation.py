"""Default-unwired A3 selector metadata boundary; no Runtime imports or plaintext access.

The source is a typed software port, not a production transport. Only isolated
TEST composition may supply it. Public replies contain neither trust pins nor
credential/relative-path authority. The existing metadata v1 route is unchanged.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal, Protocol, cast

from agentbox_core.errors import RuntimeGatewayError
from agentbox_core.services import ControlPlaneServices
from agentbox_protocol.a3_admission import A3CurrentAdmission
from fastapi import APIRouter, Cookie, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from agentbox_api.a3_admission import A3SessionCurrentness
from agentbox_api.auth import SESSION_COOKIE, _validate_origin, authenticate_request

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
_PROJECT = re.compile(r"prj_[0-9a-f]{32}\Z")
Hex32 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class A3StagedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    path: Annotated[str, Field(min_length=1, max_length=4096)]
    kind: Literal["added", "modified", "deleted", "renamed", "copied", "typechanged", "conflicted"]
    side: Literal["staged"] = "staged"
    selection_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{156}$")] | None
    unavailable_code: (
        Literal[
            "PATCH_STALE",
            "PATCH_UNAVAILABLE_KIND",
            "PATCH_UNAVAILABLE_MODE",
            "PATCH_UNAVAILABLE_PATH",
            "PATCH_UNAVAILABLE_SENSITIVE_PATH",
            "PATCH_UNAVAILABLE_STATUS",
        ]
        | None
    )


class A3StagedMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    snapshot_sha256: Hex32
    entries: Annotated[tuple[A3StagedEntry, ...], Field(max_length=10_000)]


class A3ObservationSource(Protocol):
    """Trusted metadata-only port. Implementations must never return patch bytes."""

    def runtime_epoch(self) -> str | None: ...

    async def observe(self, facts: A3CurrentAdmission) -> A3StagedMetadata: ...


def unavailable(code: str = "PATCH_UNAVAILABLE_CONFIG") -> RuntimeGatewayError:
    return RuntimeGatewayError(code=code, category="unavailable", message="A3 read unavailable")


def public_binding(facts: A3CurrentAdmission) -> dict[str, str]:
    """Deliberately exclude the internal relative key and every API credential."""
    return {
        "project_id": facts.project_id,
        "project_revision": facts.project_revision,
        "binding_revision": facts.binding_revision,
        "binding_digest": facts.binding_digest,
        "runtime_host_installation_id": facts.runtime_host_installation_id,
        "runtime_host_installation_revision": facts.runtime_host_installation_revision,
        "runtime_epoch": facts.runtime_epoch,
        "session_scope": facts.session_scope.hex(),
        "auth_epoch": str(facts.auth_epoch),
    }


@router.post("/{project_id}/git/staged-observation")
async def observe_staged(
    project_id: str,
    request: Request,
    agentbox_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> JSONResponse:
    _validate_origin(request)
    authenticated = authenticate_request(request, agentbox_session)
    services = cast(ControlPlaneServices, request.app.state.services)
    services.sessions.validate_csrf(authenticated, csrf_token)
    # A path is display-only: neither path/selector nor arbitrary query/body input
    # is accepted at this observation boundary (even {} is not an empty body).
    if _PROJECT.fullmatch(project_id) is None or request.query_params or await request.body():
        raise unavailable("PATCH_PROTOCOL_INVALID")
    source = cast(A3ObservationSource | None, request.app.state.a3_observation_source)
    if source is None:
        raise unavailable()
    current = A3SessionCurrentness(services, authenticated, runtime_epoch=source.runtime_epoch)
    try:
        facts = current.current(project_id, current.session_scope)
        if facts is None:
            raise unavailable("PATCH_REVOKED")
        try:
            metadata = await source.observe(facts)
        except Exception:
            # A broken port never reflects exception text or metadata.
            raise unavailable() from None
        if current.current(project_id, current.session_scope) != facts:
            raise unavailable("PATCH_REVOKED")
        if type(metadata) is not A3StagedMetadata:
            raise unavailable("PATCH_PROTOCOL_INVALID")
        paths = set()
        for entry in metadata.entries:
            if entry.path in paths:
                raise unavailable("PATCH_PROTOCOL_INVALID")
            paths.add(entry.path)
            if entry.selection_id is not None and entry.kind not in {
                "added",
                "modified",
                "deleted",
            }:
                raise unavailable("PATCH_PROTOCOL_INVALID")
            if (entry.selection_id is None) == (entry.unavailable_code is None):
                raise unavailable("PATCH_PROTOCOL_INVALID")
        body = {
            "api_version": "v1",
            "request_id": str(request.state.request_id),
            "data": {
                "schema_version": "a3-staged-observation/v1",
                "binding": public_binding(facts),
                **metadata.model_dump(mode="json"),
            },
        }
        if len(json.dumps(body, ensure_ascii=True).encode("ascii")) > 2 * 1024 * 1024:
            raise unavailable("PATCH_TOO_LARGE")
        return JSONResponse(
            body,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Cookie, Origin"},
        )
    finally:
        current.close()
