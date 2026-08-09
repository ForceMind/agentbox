import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../../lib/api'
import {
  CodexPairResponse,
  CodexRemoteActionResponse,
  CodexStatusResponse,
  parseCodexPairResponse,
  parseCodexRemoteActionResponse,
  parseCodexStatusResponse,
} from '../../lib/contracts'

export type CodexViewState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'loaded'; response: CodexStatusResponse }

// The Runtime RPC budgets the complete sequential Codex probe/action chain at
// 70/100 seconds. Browser deadlines include connection/API overhead so a local
// timeout cannot report failure while the Runtime can still apply the action.
const CODEX_STATUS_TIMEOUT_MS = 85_000
const CODEX_MUTATION_TIMEOUT_MS = 130_000

export function useCodex() {
  const { api, auth } = useAuth()
  const [view, setView] = useState<CodexViewState>({ status: 'loading' })
  const [pending, setPending] = useState<'start' | 'stop' | 'pair' | null>(null)
  const [pair, setPair] = useState<CodexPairResponse['data'] | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)

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
      setView({ status: 'loaded', response })
    } catch (error) {
      setView({
        status: 'error',
        error:
          error instanceof ApiError
            ? error
            : new ApiError({
                code: 'CODEX_STATUS_UNAVAILABLE',
                message: 'Codex status is unavailable',
                status: 0,
              }),
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
      setActionError(
        error instanceof ApiError
          ? error
          : new ApiError({
              code: 'CODEX_ACTION_FAILED',
              message: 'Codex action failed',
              status: 0,
            }),
      )
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
      setPair(response.data)
    } catch (error) {
      setActionError(
        error instanceof ApiError
          ? error
          : new ApiError({
              code: 'CODEX_PAIR_FAILED',
              message: 'A pairing code could not be generated',
              status: 0,
            }),
      )
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
