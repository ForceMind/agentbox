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


class RecentAuthenticationRequired(AgentBoxError):
    code = "AUTH_RECENT_REQUIRED"
    category = "forbidden"
    message = "Recent authentication is required"
    status_code = 403


class RuntimeGatewayError(AgentBoxError):
    """Safe projection of a normalized Runtime Executor error."""

    def __init__(
        self,
        *,
        code: str,
        category: str,
        message: str,
        retryable: bool = False,
        retry_after: int | None = None,
    ) -> None:
        self.code = code[:80]
        self.category = category[:32]
        self.message = message[:256]
        self.retryable = retryable
        self.status_code = {
            "validation": 422,
            "unauthenticated": 503,
            "forbidden": 403,
            "conflict": 409,
            "rate_limited": 429,
            "unsupported": 501,
            "unavailable": 503,
            "timeout": 504,
            "broken": 503,
        }.get(category, 503)
        super().__init__(retry_after=retry_after)


class ProjectNotFound(AgentBoxError):
    code = "PROJECT_NOT_FOUND"
    category = "unavailable"
    message = "Project was not found"
    status_code = 404


class ProjectNotReady(AgentBoxError):
    code = "PROJECT_NOT_READY"
    category = "conflict"
    message = "Project is not ready"
    status_code = 409


class ProjectConflict(AgentBoxError):
    code = "PROJECT_CONFLICT"
    category = "conflict"
    message = "Project conflicts with an existing workspace"
    status_code = 409


class ProjectValidationError(AgentBoxError):
    code = "PROJECT_INPUT_INVALID"
    category = "validation"
    message = "Project input is invalid"
    status_code = 422


class JobNotFound(AgentBoxError):
    code = "JOB_NOT_FOUND"
    category = "unavailable"
    message = "Job was not found"
    status_code = 404


class ProviderMetadataNotFound(AgentBoxError):
    code = "PROVIDER_METADATA_NOT_FOUND"
    category = "unavailable"
    message = "Provider metadata was not found"
    status_code = 404


class ProviderMetadataConflict(AgentBoxError):
    code = "PROVIDER_METADATA_CONFLICT"
    category = "conflict"
    message = "Provider metadata conflicts with existing state"
    status_code = 409


class ProviderRevisionConflict(AgentBoxError):
    code = "PROVIDER_REVISION_CONFLICT"
    category = "conflict"
    message = "Provider metadata revision is stale"
    status_code = 409


class ProviderInputInvalid(AgentBoxError):
    code = "PROVIDER_INPUT_INVALID"
    category = "validation"
    message = "Provider metadata is invalid"
    status_code = 422


class RuntimeCapabilityReportInvalid(AgentBoxError):
    code = "RUNTIME_CAPABILITY_REPORT_INVALID"
    category = "broken"
    message = "Runtime capability report is invalid"
    status_code = 503


class RuntimeInstallationRevisionConflict(AgentBoxError):
    code = "RUNTIME_INSTALLATION_REVISION_CONFLICT"
    category = "conflict"
    message = "Runtime installation revision is stale"
    status_code = 409


class RuntimeCapabilityEvidenceExpired(AgentBoxError):
    code = "RUNTIME_CAPABILITY_EVIDENCE_EXPIRED"
    category = "conflict"
    message = "Runtime capability evidence is expired"
    status_code = 409
