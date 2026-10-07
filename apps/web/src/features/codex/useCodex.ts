import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

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
  const { api, auth, status } = useAuth()
  const userId = auth?.user.id
  const sessionId = auth?.session.id
  const csrfToken = auth?.csrf_token
  const owner = useMemo(
    () => ({ api, userId, sessionId, csrfToken, status }),
    [api, userId, sessionId, csrfToken, status],
  )
  const currentOwner = useRef(owner)
  currentOwner.current = owner
  type State = {
    view: CodexViewState
    pending: 'start' | 'stop' | 'pair' | null
    pair: CodexPairView | null
    actionError: CodexDisplayError | null
  }
  const [state, setState] = useState<State & { owner: typeof owner }>({
    owner,
    view: { status: 'loading' },
    pending: null,
    pair: null,
    actionError: null,
  })
  const control = useRef<{
    owner: typeof owner
    refresh: () => Promise<void>
    remoteAction: (operation: 'start' | 'stop') => Promise<void>
    generatePairCode: () => Promise<void>
    clearPair: () => void
  } | null>(null)

  useEffect(() => {
    let disposed = false
    let mutation: AbortController | null = null
    let pairTimer: number | undefined
    const requests = new Set<AbortController>()
    const authenticated =
      owner.status === 'authenticated' &&
      Boolean(owner.userId && owner.sessionId)
    function owns() {
      return !disposed && authenticated && currentOwner.current === owner
    }
    function commit(next: Partial<State>) {
      if (!owns()) return
      setState((current) =>
        owns() && current.owner === owner ? { ...current, ...next } : current,
      )
    }
    function clearPair() {
      if (!owns()) return
      window.clearTimeout(pairTimer)
      pairTimer = undefined
      commit({ pair: null })
    }
    async function refresh() {
      if (!owns()) return
      const request = new AbortController()
      requests.add(request)
      commit({ view: { status: 'loading' } })
      try {
        const response = await owner.api.get<CodexStatusResponse>(
          '/api/v1/codex/status',
          {
            signal: request.signal,
            timeoutMs: CODEX_STATUS_TIMEOUT_MS,
            validate: parseCodexStatusResponse,
          },
        )
        if (!owns() || request.signal.aborted) return
        commit({
          view: {
            status: 'loaded',
            response: projectCodexStatusResponse(response),
          },
        })
      } catch (error) {
        if (!owns() || request.signal.aborted) return
        commit({
          view: {
            status: 'error',
            error: projectCodexError(error, 'CODEX_STATUS_UNAVAILABLE'),
          },
        })
      } finally {
        requests.delete(request)
      }
    }
    async function remoteAction(operation: 'start' | 'stop') {
      if (!owns() || mutation !== null || !owner.csrfToken) return
      const request = new AbortController()
      mutation = request
      requests.add(request)
      commit({ pending: operation, actionError: null })
      try {
        await owner.api.post<CodexRemoteActionResponse>(
          `/api/v1/codex/remote/${operation}`,
          {
            signal: request.signal,
            csrfToken: owner.csrfToken,
            timeoutMs: CODEX_MUTATION_TIMEOUT_MS,
            validate: parseCodexRemoteActionResponse,
          },
        )
        if (!owns() || request.signal.aborted) return
        await refresh()
      } catch (error) {
        if (!owns() || request.signal.aborted) return
        commit({ actionError: projectCodexError(error, 'CODEX_ACTION_FAILED') })
      } finally {
        requests.delete(request)
        if (owns() && mutation === request) {
          mutation = null
          commit({ pending: null })
        }
      }
    }
    async function generatePairCode() {
      if (!owns() || mutation !== null || !owner.csrfToken) return
      const request = new AbortController()
      mutation = request
      requests.add(request)
      clearPair()
      commit({ pending: 'pair', actionError: null })
      try {
        const response = await owner.api.post<CodexPairResponse>(
          '/api/v1/codex/pair-codes',
          {
            signal: request.signal,
            csrfToken: owner.csrfToken,
            timeoutMs: CODEX_MUTATION_TIMEOUT_MS,
            validate: parseCodexPairResponse,
          },
        )
        if (!owns() || request.signal.aborted) return
        const pair = projectCodexPair(response.data)
        if (pair === null) {
          commit({
            actionError: {
              code: 'CODEX_PAIR_OUTPUT_UNRECOGNIZED',
              requestId: response.request_id,
            },
          })
          return
        }
        commit({ pair })
        // A display lifetime only; this does not assert vendor code expiry.
        pairTimer = window.setTimeout(clearPair, 90_000)
      } catch (error) {
        if (!owns() || request.signal.aborted) return
        commit({ actionError: projectCodexError(error, 'CODEX_PAIR_FAILED') })
      } finally {
        requests.delete(request)
        if (owns() && mutation === request) {
          mutation = null
          commit({ pending: null })
        }
      }
    }
    setState({
      owner,
      view: { status: 'loading' },
      pending: null,
      pair: null,
      actionError: null,
    })
    const controls = {
      owner,
      refresh,
      remoteAction,
      generatePairCode,
      clearPair,
    }
    control.current = controls
    void refresh()
    return () => {
      disposed = true
      window.clearTimeout(pairTimer)
      // Cancel browser work; an already submitted Runtime action may still run.
      for (const request of requests) request.abort()
      requests.clear()
      if (control.current === controls) control.current = null
    }
  }, [owner])

  const isCurrent = useCallback(
    () => currentOwner.current === owner && control.current?.owner === owner,
    [owner],
  )
  const refresh = useCallback(async () => {
    if (isCurrent()) await control.current?.refresh()
  }, [isCurrent])
  async function remoteAction(operation: 'start' | 'stop') {
    if (isCurrent()) await control.current?.remoteAction(operation)
  }
  async function generatePairCode() {
    if (isCurrent()) await control.current?.generatePairCode()
  }
  function clearPair() {
    if (isCurrent()) control.current?.clearPair()
  }
  // Do not expose an old owner's state even before effect cleanup/setup runs.
  const owned = state.owner === owner && owner.status === 'authenticated'
  return {
    actionError: owned ? state.actionError : null,
    clearPair,
    generatePairCode,
    isCurrent,
    pair: owned ? state.pair : null,
    pending: owned ? state.pending : null,
    refresh,
    remoteAction,
    view: owned ? state.view : ({ status: 'loading' } as const),
  }
}
