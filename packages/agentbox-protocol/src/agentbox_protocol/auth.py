"""Versioned Phase 3 authentication request and response contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class AdminView(StrictModel):
    id: str
    username: str


class AuthSessionView(StrictModel):
    id: str
    expires_at: datetime

    @field_serializer("expires_at")
    def serialize_expires_at(self, value: datetime) -> str:
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.isoformat().replace("+00:00", "Z")


class AuthData(StrictModel):
    user: AdminView
    session: AuthSessionView
    csrf_token: str


class AuthResponse(StrictModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    data: AuthData


class ErrorBody(StrictModel):
    code: str
    category: str
    message: str
    retryable: bool = False
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(StrictModel):
    api_version: Literal["v1"] = "v1"
    request_id: str
    error: ErrorBody


class ReadinessResponse(StrictModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, bool]
