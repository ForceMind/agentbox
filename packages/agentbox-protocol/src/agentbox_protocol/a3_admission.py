"""Noncredential A3 admission facts; no routes, tokens or Runtime authority."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, repr=False)
class A3CurrentAdmission:
    project_id: str
    relative_key: str
    project_revision: str
    binding_revision: str
    binding_digest: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    runtime_epoch: str
    session_scope: bytes
    auth_epoch: int
