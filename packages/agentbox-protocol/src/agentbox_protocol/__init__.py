"""Minimal versioned public protocol types for the control plane."""

from agentbox_protocol.auth import (
    AdminView,
    AuthData,
    AuthResponse,
    AuthSessionView,
    ErrorBody,
    ErrorResponse,
    LoginRequest,
    ReadinessResponse,
)
from agentbox_protocol.metadata import HealthResponse, MetaResponse

__all__ = [
    "AdminView",
    "AuthData",
    "AuthResponse",
    "AuthSessionView",
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "LoginRequest",
    "MetaResponse",
    "ReadinessResponse",
]
