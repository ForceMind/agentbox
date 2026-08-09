import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../../lib/api'
import {
  ClaudeSessionActionResponse,
  ClaudeSessionData,
  ClaudeSessionListResponse,
  ClaudeSessionOutputResponse,
  ClaudeStatusResponse,
  parseClaudeSessionActionResponse,
  parseClaudeSessionListResponse,
  parseClaudeSessionOutputResponse,
  parseClaudeStatusResponse,
} from '../../lib/contracts'

type LoadedClaude = {
  status: ClaudeStatusResponse['data']
  sessions: ClaudeSessionData[]
}

export type ClaudeViewState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'loaded'; data: LoadedClaude }

const CLAUDE_STATUS_TIMEOUT_MS = 45_000
const CLAUDE_MUTATION_TIMEOUT_MS = 45_000

function normalizedError(error: unknown, fallback: string): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({
        code: 'CLAUDE_ACTION_FAILED',
        message: fallback,
        status: 0,
      })
}

export function useClaude() {
  const { api, auth } = useAuth()
  const [view, setView] = useState<ClaudeViewState>({ status: 'loading' })
  const [pending, setPending] = useState<string | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [outputs, setOutputs] = useState<
    Record<string, ClaudeSessionOutputResponse['data']>
  >({})

  const refresh = useCallback(async () => {
    setView({ status: 'loading' })
    try {
      const [status, sessions] = await Promise.all([
        api.get<ClaudeStatusResponse>('/api/v1/claude', {
          timeoutMs: CLAUDE_STATUS_TIMEOUT_MS,
          validate: parseClaudeStatusResponse,
        }),
        api.get<ClaudeSessionListResponse>('/api/v1/claude/sessions', {
          timeoutMs: CLAUDE_STATUS_TIMEOUT_MS,
          validate: parseClaudeSessionListResponse,
        }),
      ])
      setView({
        status: 'loaded',
        data: { status: status.data, sessions: sessions.data.sessions },
      })
    } catch (error) {
      setView({
        status: 'error',
        error: normalizedError(error, 'Claude session status is unavailable'),
      })
    }
  }, [api])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function sessionAction(projectId: string, operation: 'start' | 'stop') {
    if (!auth) return
    setPending(`${operation}:${projectId}`)
    setActionError(null)
    setOutputs((current) => {
      const next = { ...current }
      delete next[projectId]
      return next
    })
    try {
      const response = await api.post<ClaudeSessionActionResponse>(
        `/api/v1/claude/sessions/${encodeURIComponent(projectId)}/${operation}`,
        {
          csrfToken: auth.csrf_token,
          timeoutMs: CLAUDE_MUTATION_TIMEOUT_MS,
          validate: parseClaudeSessionActionResponse,
        },
      )
      setView((current) =>
        current.status === 'loaded'
          ? {
              status: 'loaded',
              data: {
                ...current.data,
                sessions: current.data.sessions.map((session) =>
                  session.project_id === projectId
                    ? response.data.session
                    : session,
                ),
              },
            }
          : current,
      )
    } catch (error) {
      setActionError(
        error instanceof ApiError
          ? error
          : normalizedError(error, 'Claude session action failed'),
      )
    } finally {
      setPending(null)
    }
  }

  async function revealOutput(projectId: string) {
    setPending(`output:${projectId}`)
    setActionError(null)
    try {
      const response = await api.get<ClaudeSessionOutputResponse>(
        `/api/v1/claude/sessions/${encodeURIComponent(projectId)}/output`,
        {
          timeoutMs: CLAUDE_STATUS_TIMEOUT_MS,
          validate: parseClaudeSessionOutputResponse,
        },
      )
      setOutputs((current) => ({ ...current, [projectId]: response.data }))
    } catch (error) {
      setActionError(
        error instanceof ApiError
          ? error
          : normalizedError(error, 'Claude output is unavailable'),
      )
    } finally {
      setPending(null)
    }
  }

  function hideOutput(projectId: string) {
    setOutputs((current) => {
      const next = { ...current }
      delete next[projectId]
      return next
    })
  }

  return {
    actionError,
    hideOutput,
    outputs,
    pending,
    refresh,
    revealOutput,
    sessionAction,
    view,
  }
}
