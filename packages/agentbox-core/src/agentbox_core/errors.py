"""Stable service errors mapped to versioned API and CLI envelopes."""

from __future__ import annotations


class AgentBoxError(Exception):
    code = "INTERNAL_ERROR"
    category = "internal"
    message = "The request could not be completed"
    status_code = 500
    retryable = False

    def __init__(self, *, retry_after: int | None = None) -> None:
        super().__init__(self.message)
        self.retry_after = retry_after


class AdminAlreadyInitialized(AgentBoxError):
    code = "ADMIN_ALREADY_INITIALIZED"
    category = "conflict"
    message = "Admin already initialized"
    status_code = 409


class AdminNotInitialized(AgentBoxError):
    code = "ADMIN_NOT_INITIALIZED"
    category = "unavailable"
    message = "Administrator initialization is required"
    status_code = 503


class InvalidCredentials(AgentBoxError):
    code = "AUTH_INVALID_CREDENTIALS"
    category = "unauthenticated"
    message = "Invalid credentials"
    status_code = 401


class InvalidSession(AgentBoxError):
    code = "AUTH_SESSION_INVALID"
    category = "unauthenticated"
    message = "Authentication required"
    status_code = 401


class InvalidCsrfToken(AgentBoxError):
    code = "AUTH_CSRF_INVALID"
    category = "forbidden"
    message = "CSRF validation failed"
    status_code = 403


class InvalidOrigin(AgentBoxError):
    code = "AUTH_ORIGIN_INVALID"
    category = "forbidden"
    message = "Request origin is not allowed"
    status_code = 403


class LoginRateLimited(AgentBoxError):
    code = "AUTH_RATE_LIMITED"
    category = "rate_limited"
    message = "Too many login attempts"
    status_code = 429
    retryable = True


class PasswordPolicyViolation(AgentBoxError):
    code = "AUTH_PASSWORD_POLICY"
    category = "validation"
    message = "Password does not meet the local security policy"
    status_code = 422


class DatabaseNotReady(AgentBoxError):
    code = "CONTROL_PLANE_NOT_READY"
    category = "unavailable"
    message = "Control plane is not ready"
    status_code = 503
    retryable = True
