import { formatMessage, type MessageKey } from './catalog'
import type { Locale } from './locale'
import { technicalValue, type TechnicalValue } from './technical'

type ErrorMessageKey = Extract<MessageKey, `error.${string}`>

/**
 * This table is the only supported mapping from an API error code to display
 * copy. Callers must never render ApiError.message, which is server prose.
 */
export const KNOWN_API_ERROR_MESSAGES = Object.freeze({
  CLAUDE_ACTION_FAILED: 'error.claudeActionFailed',
  CODEX_ACTION_FAILED: 'error.codexActionFailed',
  CODEX_PAIR_FAILED: 'error.codexPairFailed',
  CODEX_STATUS_UNAVAILABLE: 'error.codexStatusUnavailable',
  CONTROL_PLANE_UNAVAILABLE: 'error.controlPlaneUnavailable',
  DOCTOR_UNAVAILABLE: 'error.doctorUnavailable',
  PROJECT_IDENTITY_CHANGED: 'error.projectIdentityChanged',
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
} as const satisfies Readonly<Record<string, ErrorMessageKey>>)

export type KnownApiErrorCode = keyof typeof KNOWN_API_ERROR_MESSAGES

export function isKnownApiErrorCode(code: string): code is KnownApiErrorCode {
  return Object.hasOwn(KNOWN_API_ERROR_MESSAGES, code)
}

export function localizeApiError(locale: Locale, code: string): string {
  const key = isKnownApiErrorCode(code)
    ? KNOWN_API_ERROR_MESSAGES[code]
    : 'error.unknown'
  return formatMessage(locale, key, {})
}

/**
 * Codes and request IDs are supporting technical evidence, not translated UI
 * copy. Invalid externally supplied strings are omitted rather than rendered.
 */
export function technicalApiIdentifier(
  value: string | undefined,
): TechnicalValue | null {
  if (value === undefined) return null
  try {
    return technicalValue(value)
  } catch {
    return null
  }
}
