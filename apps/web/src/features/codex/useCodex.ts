import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { technicalValue } from '../../i18n'
import { ApiError } from '../../lib/api'
import {
  CodexPairResponse,
  CodexRemoteActionResponse,
  CodexStatusData,
  CodexStatusResponse,
  parseCodexPairResponse,
  parseCodexRemoteActionResponse,
  parseCodexStatusResponse,
} from '../../lib/contracts'

export type CodexDisplayError = Readonly<{
  code: string
  requestId?: string
}>

export type CodexStatusViewData = Omit<CodexStatusData, 'diagnostics'> & {
  diagnostics: Array<
    Pick<CodexStatusData['diagnostics'][number], 'code' | 'severity'>
  >
}

export type CodexStatusViewResponse = Omit<CodexStatusResponse, 'data'> & {
  data: CodexStatusViewData
}

export type CodexPairView = Readonly<{
  pair_code: string
}>

export type CodexViewState =
  | { status: 'loading' }
  | { status: 'error'; error: CodexDisplayError }
  | { status: 'loaded'; response: CodexStatusViewResponse }

// The Runtime RPC budgets the complete sequential Codex probe/action chain at
// 70/100 seconds. Browser deadlines include connection/API overhead so a local
// timeout cannot report failure while the Runtime can still apply the action.
const CODEX_STATUS_TIMEOUT_MS = 85_000
const CODEX_MUTATION_TIMEOUT_MS = 130_000
const PAIR_CODE = /^[A-Za-z0-9][A-Za-z0-9-]{3,63}$/

/** Invalid or non-ASCII versions are external prose and become local Unknown. */
export function projectCodexVersion(version: string | null): string | null {
  if (version === null) return null
  try {
    return technicalValue(version).value
  } catch {
    return null
  }
}

/**
 * Pair codes are sensitive but must also be safe terminal-style technical text.
 * This mirrors the Runtime parser's 4–64 character alphanumeric/hyphen shape;
 * malformed transport data becomes a local error rather than React state.
 */
export function projectCodexPair(
  data: CodexPairResponse['data'],
): CodexPairView | null {
  return PAIR_CODE.test(data.pair_code)
    ? Object.freeze({ pair_code: data.pair_code })
    : null
}

/** Keep only stable machine evidence. ApiError.message is server prose. */
export function projectCodexError(
  error: unknown,
  fallbackCode: string,
): CodexDisplayError {
  if (!(error instanceof ApiError)) return { code: fallbackCode }
  return error.requestId
    ? { code: error.code, requestId: error.requestId }
    : { code: error.code }
}

/**
 * Builds the page model from an explicit allowlist. Diagnostic prose is parsed
 * at the transport boundary for contract compatibility, then discarded before
 * any React state can retain or render it.
 */
export function projectCodexStatusResponse(
  response: CodexStatusResponse,
): CodexStatusViewResponse {
  const data = response.data
  return {
    api_version: response.api_version,
    request_id: response.request_id,
    data: {
      installed: data.installed,
      version: projectCodexVersion(data.version),
      selected_executable: data.selected_executable,
      alternatives: [...data.alternatives],
      installation_type: data.installation_type,
      conflict_detected: data.conflict_detected,
      authentication: data.authentication,
      capabilities: { ...data.capabilities },
      remote_state: data.remote_state,
      remote_confidence: data.remote_confidence,
      diagnostics: data.diagnostics.map(({ code, severity }) => ({
        code,
        severity,
      })),
    },
  }
}

export function useCodex() {
  const { api, auth } = useAuth()
  const [view, setView] = useState<CodexViewState>({ status: 'loading' })
  const [pending, setPending] = useState<'start' | 'stop' | 'pair' | null>(null)
  const [pair, setPair] = useState<CodexPairView | null>(null)
  const [actionError, setActionError] = useState<CodexDisplayError | null>(null)

  const refresh = useCallback(async () => {
    setView({ status: 'loading' })
    try {
      const response = await api.get<CodexStatusResponse>(
        '/api/v1/codex/status',
        {
          timeoutMs: CODEX_STATUS_TIMEOUT_MS,
          validate: parseCodexStatusResponse,
        },
      )
      setView({
        status: 'loaded',
        response: projectCodexStatusResponse(response),
      })
    } catch (error) {
      setView({
        status: 'error',
        error: projectCodexError(error, 'CODEX_STATUS_UNAVAILABLE'),
      })
    }
  }, [api])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!pair) return
    const timer = window.setTimeout(() => setPair(null), 90_000)
    return () => window.clearTimeout(timer)
  }, [pair])

  async function remoteAction(operation: 'start' | 'stop') {
    if (!auth) return
    setPending(operation)
    setActionError(null)
    try {
      await api.post<CodexRemoteActionResponse>(
        `/api/v1/codex/remote/${operation}`,
        {
          csrfToken: auth.csrf_token,
          timeoutMs: CODEX_MUTATION_TIMEOUT_MS,
          validate: parseCodexRemoteActionResponse,
        },
      )
      await refresh()
    } catch (error) {
      setActionError(projectCodexError(error, 'CODEX_ACTION_FAILED'))
    } finally {
      setPending(null)
    }
  }

  async function generatePairCode() {
    if (!auth) return
    setPending('pair')
    setActionError(null)
    setPair(null)
    try {
      const response = await api.post<CodexPairResponse>(
        '/api/v1/codex/pair-codes',
        {
          csrfToken: auth.csrf_token,
          timeoutMs: CODEX_MUTATION_TIMEOUT_MS,
          validate: parseCodexPairResponse,
        },
      )
      const pair = projectCodexPair(response.data)
      if (pair === null) {
        setActionError({
          code: 'CODEX_PAIR_OUTPUT_UNRECOGNIZED',
          requestId: response.request_id,
        })
        return
      }
      setPair(pair)
    } catch (error) {
      setActionError(projectCodexError(error, 'CODEX_PAIR_FAILED'))
    } finally {
      setPending(null)
    }
  }

  return {
    actionError,
    clearPair: () => setPair(null),
    generatePairCode,
    pair,
    pending,
    refresh,
    remoteAction,
    view,
  }
}
