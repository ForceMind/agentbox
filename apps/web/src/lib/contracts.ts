export type AdminView = {
  id: string
  username: string
}

export type AuthData = {
  user: AdminView
  session: { id: string; expires_at: string }
  csrf_token: string
}

export type AuthEnvelope = {
  api_version: 'v1'
  request_id: string
  data: AuthData
}

export type HealthResponse = { status: 'ok' }

export type ReadinessResponse = {
  status: 'ready' | 'not_ready'
  checks: { database: boolean; migrations: boolean }
}

export type MetaResponse = {
  name: 'AgentBox'
  version: string
  api_version: 'v1'
  environment: 'development' | 'test' | 'production'
}

export type DoctorResponse = {
  api_version: 'v1'
  request_id: string
  data: {
    status: 'ready' | 'not_ready'
    checks: {
      configuration_valid: boolean
      database_reachable: boolean
      migrations_current: boolean
      admin_initialized: boolean
      control_plane_ready: boolean
    }
    policy: {
      environment: 'development' | 'test' | 'production'
      bind_host: string
      bind_port: number
      session_ttl_seconds: number
      session_idle_ttl_seconds: number
      login_rate_limit: number
      login_rate_window_seconds: number
      login_lock_duration_seconds: number
    }
  }
}

type JsonObject = Record<string, unknown>

function object(value: unknown, context: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`Invalid ${context} response`)
  }
  return value as JsonObject
}

function string(value: unknown, context: string): string {
  if (typeof value !== 'string') throw new Error(`Invalid ${context} response`)
  return value
}

function boolean(value: unknown, context: string): boolean {
  if (typeof value !== 'boolean') throw new Error(`Invalid ${context} response`)
  return value
}

function number(value: unknown, context: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Invalid ${context} response`)
  }
  return value
}

function literal<T extends string>(
  value: unknown,
  values: readonly T[],
  context: string,
): T {
  if (typeof value !== 'string' || !values.includes(value as T)) {
    throw new Error(`Invalid ${context} response`)
  }
  return value as T
}

export function parseAuthEnvelope(value: unknown): AuthEnvelope {
  const envelope = object(value, 'authentication')
  const data = object(envelope.data, 'authentication data')
  const user = object(data.user, 'administrator')
  const session = object(data.session, 'session')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      user: {
        id: string(user.id, 'administrator ID'),
        username: string(user.username, 'administrator username'),
      },
      session: {
        id: string(session.id, 'session ID'),
        expires_at: string(session.expires_at, 'session expiry'),
      },
      csrf_token: string(data.csrf_token, 'CSRF token'),
    },
  }
}

export function parseHealthResponse(value: unknown): HealthResponse {
  const response = object(value, 'health')
  return { status: literal(response.status, ['ok'], 'health status') }
}

export function parseReadinessResponse(value: unknown): ReadinessResponse {
  const response = object(value, 'readiness')
  const checks = object(response.checks, 'readiness checks')
  return {
    status: literal(
      response.status,
      ['ready', 'not_ready'],
      'readiness status',
    ),
    checks: {
      database: boolean(checks.database, 'database readiness'),
      migrations: boolean(checks.migrations, 'migration readiness'),
    },
  }
}

export function parseMetaResponse(value: unknown): MetaResponse {
  const response = object(value, 'metadata')
  return {
    name: literal(response.name, ['AgentBox'], 'application name'),
    version: string(response.version, 'application version'),
    api_version: literal(response.api_version, ['v1'], 'API version'),
    environment: literal(
      response.environment,
      ['development', 'test', 'production'],
      'environment',
    ),
  }
}

export function parseDoctorResponse(value: unknown): DoctorResponse {
  const response = object(value, 'Doctor')
  const data = object(response.data, 'Doctor data')
  const checks = object(data.checks, 'Doctor checks')
  const policy = object(data.policy, 'Doctor policy')
  return {
    api_version: literal(response.api_version, ['v1'], 'API version'),
    request_id: string(response.request_id, 'request ID'),
    data: {
      status: literal(data.status, ['ready', 'not_ready'], 'Doctor status'),
      checks: {
        configuration_valid: boolean(
          checks.configuration_valid,
          'configuration check',
        ),
        database_reachable: boolean(
          checks.database_reachable,
          'database check',
        ),
        migrations_current: boolean(
          checks.migrations_current,
          'migration check',
        ),
        admin_initialized: boolean(
          checks.admin_initialized,
          'administrator check',
        ),
        control_plane_ready: boolean(
          checks.control_plane_ready,
          'control-plane check',
        ),
      },
      policy: {
        environment: literal(
          policy.environment,
          ['development', 'test', 'production'],
          'environment',
        ),
        bind_host: string(policy.bind_host, 'bind host'),
        bind_port: number(policy.bind_port, 'bind port'),
        session_ttl_seconds: number(
          policy.session_ttl_seconds,
          'session lifetime',
        ),
        session_idle_ttl_seconds: number(
          policy.session_idle_ttl_seconds,
          'idle session lifetime',
        ),
        login_rate_limit: number(policy.login_rate_limit, 'login rate limit'),
        login_rate_window_seconds: number(
          policy.login_rate_window_seconds,
          'login rate window',
        ),
        login_lock_duration_seconds: number(
          policy.login_lock_duration_seconds,
          'login lock duration',
        ),
      },
    },
  }
}
