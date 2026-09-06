import { KNOWN_API_ERROR_CODES, type KnownApiErrorCode } from './apiErrorCodes'
import {
  formatMessage,
  parameterFreeMessage,
  type ParameterFreeMessageKey,
} from './catalog'
import type { Locale } from './locale'
import { technicalValue, type TechnicalValue } from './technical'

const MAX_RETRY_AFTER_SECONDS = 86_400

export interface ApiErrorDisplaySource {
  readonly code: unknown
  readonly requestId?: unknown
  readonly retryAfter?: unknown
}

export interface LocalizedApiErrorData {
  readonly text: string
  readonly code: TechnicalValue | null
  readonly requestId: TechnicalValue | null
  readonly retryAfter?: number
}

type ErrorMessageKey = Extract<ParameterFreeMessageKey, `error.${string}`>

/**
 * This table is the only supported mapping from an API error code to display
 * copy. Callers must never render ApiError.message, which is server prose.
 */
export const KNOWN_API_ERROR_MESSAGES = Object.freeze({
  AUTH_CSRF_INVALID: 'error.authCsrfInvalid',
  AUTH_INVALID_CREDENTIALS: 'error.authInvalidCredentials',
  AUTH_RATE_LIMITED: 'error.authRateLimited',
  AUTH_RECENT_REQUIRED: 'error.authRecentRequired',
  AUTH_SESSION_INVALID: 'error.authSessionInvalid',
  CLAUDE_ACTION_FAILED: 'error.claudeActionFailed',
  CLAUDE_RUNTIME_UNAVAILABLE: 'error.claudeRuntimeUnavailable',
  CODEX_ACTION_FAILED: 'error.codexActionFailed',
  CODEX_COMMAND_TIMEOUT: 'error.codexCommandTimeout',
  CODEX_EXECUTABLE_CHANGED: 'error.codexExecutableChanged',
  CODEX_EXECUTABLE_INVALID: 'error.codexExecutableInvalid',
  CODEX_NOT_INSTALLED: 'error.codexNotInstalled',
  CODEX_OUTPUT_LIMIT_EXCEEDED: 'error.codexOutputLimitExceeded',
  CODEX_PAIR_FAILED: 'error.codexPairFailed',
  CODEX_PAIR_OUTPUT_UNRECOGNIZED: 'error.codexPairOutputUnrecognized',
  CODEX_PAIR_RATE_LIMITED: 'error.codexPairRateLimited',
  CODEX_PAIR_TIMEOUT: 'error.codexPairTimeout',
  CODEX_PAIR_UNSUPPORTED: 'error.codexPairUnsupported',
  CODEX_REMOTE_START_FAILED: 'error.codexRemoteStartFailed',
  CODEX_REMOTE_STATUS_UNSUPPORTED: 'error.codexRemoteStatusUnsupported',
  CODEX_REMOTE_STOP_FAILED: 'error.codexRemoteStopFailed',
  CODEX_REMOTE_UNSUPPORTED: 'error.codexRemoteUnsupported',
  CODEX_STATUS_UNAVAILABLE: 'error.codexStatusUnavailable',
  CODEX_UNAUTHENTICATED: 'error.codexUnauthenticated',
  CONTROL_PLANE_UNAVAILABLE: 'error.controlPlaneUnavailable',
  DOCTOR_UNAVAILABLE: 'error.doctorUnavailable',
  PROJECT_IDENTITY_CHANGED: 'error.projectIdentityChanged',
  PROJECT_NOT_FOUND: 'error.projectNotFound',
  PROJECT_NOT_READY: 'error.projectNotReady',
  RECONCILIATION_REQUIRED: 'error.reconciliationRequired',
  REQUEST_TIMEOUT: 'error.requestTimeout',
  WAW_ACTION_BUSY: 'error.wawActionBusy',
  WAW_ACTION_FAILED: 'error.wawActionFailed',
  WAW_ACTION_STALE: 'error.wawActionStale',
  WAW_INVALID_AGENT: 'error.wawInvalidAgent',
  WAW_METADATA_INVALID: 'error.wawMetadataInvalid',
  WAW_SESSION_REQUIRED: 'error.wawSessionRequired',
  WAW_STATUS_UNAVAILABLE: 'error.wawStatusUnavailable',
  WORKSPACE_NOT_FOUND: 'error.workspaceNotFound',
} as const satisfies Readonly<Record<KnownApiErrorCode, ErrorMessageKey>>)

export function isKnownApiErrorCode(code: string): code is KnownApiErrorCode {
  return (KNOWN_API_ERROR_CODES as readonly string[]).includes(code)
}

export function localizeApiError(locale: Locale, code: string): string {
  const key = isKnownApiErrorCode(code)
    ? KNOWN_API_ERROR_MESSAGES[code]
    : 'error.unknown'
  return formatMessage(locale, ...parameterFreeMessage(key))
}

function safeRetryAfter(value: unknown): number | undefined {
  return typeof value === 'number' &&
    Number.isInteger(value) &&
    value > 0 &&
    value <= MAX_RETRY_AFTER_SECONDS
    ? value
    : undefined
}

/**
 * Projects only bounded display-safe fields. In particular, an ApiError
 * `message` property is neither declared nor read.
 */
export function localizeApiErrorData(
  locale: Locale,
  error: ApiErrorDisplaySource,
): LocalizedApiErrorData {
  const rawCode = typeof error.code === 'string' ? error.code : ''
  const base = {
    text: localizeApiError(locale, rawCode),
    code: technicalApiIdentifier(rawCode),
    requestId: technicalApiIdentifier(error.requestId),
  }
  const retryAfter = safeRetryAfter(error.retryAfter)

  return Object.freeze(
    retryAfter === undefined ? base : { ...base, retryAfter },
  )
}

/**
 * Codes and request IDs are supporting technical evidence, not translated UI
 * copy. Invalid externally supplied strings are omitted rather than rendered.
 */
export function technicalApiIdentifier(value: unknown): TechnicalValue | null {
  if (typeof value !== 'string') return null
  try {
    return technicalValue(value)
  } catch {
    return null
  }
}
