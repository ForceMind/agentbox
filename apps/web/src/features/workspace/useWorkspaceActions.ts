import { useCallback, useEffect, useRef, useState } from 'react'

import {
  parseWorkspaceAttachmentTicketResponse,
  parseWorkspaceDetachResponse,
  parseWorkspaceStartResponse,
  parseWorkspaceStopResponse,
  WorkspaceAttachmentTicketResponse,
} from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'
import {
  workspaceApiError,
  workspaceError,
  type WorkspaceApiErrorView,
} from './workspaceView'

export type WorkspaceAction =
  'start' | 'connect' | 'reconnect' | 'detach' | 'stop'

/** Metadata/control-plane mutations only. Ticket material is returned to the caller and never persisted. */
export function useWorkspaceActions() {
  const { api, auth } = useAuth()
  const authScope = auth ? `${auth.session.id}:${auth.csrf_token}` : null
  const [pendingState, setPending] = useState<{
    action: WorkspaceAction
    scope: string
  } | null>(null)
  const [errorState, setError] = useState<{
    error: WorkspaceApiErrorView
    scope: string
  } | null>(null)
  const active = useRef<symbol | null>(null)
  const liveScope = useRef(authScope)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    liveScope.current = authScope
    active.current = null
    return () => {
      mounted.current = false
      active.current = null
    }
  }, [authScope])

  const run = useCallback(
    async <T>(
      action: WorkspaceAction,
      task: () => Promise<T>,
      signal?: AbortSignal,
    ) => {
      const scope = authScope
      if (signal?.aborted) {
        throw workspaceError('WAW_ACTION_STALE')
      }
      if (!scope || !mounted.current || liveScope.current !== scope) {
        throw workspaceError('WAW_SESSION_REQUIRED')
      }
      if (active.current !== null) {
        throw workspaceError('WAW_ACTION_BUSY')
      }
      const operation = Symbol('workspace-action')
      active.current = operation
      const current = () =>
        mounted.current &&
        liveScope.current === scope &&
        active.current === operation &&
        !signal?.aborted
      setPending({ action, scope })
      setError(null)
      try {
        const result = await task()
        if (!current()) {
          throw workspaceError('WAW_ACTION_STALE')
        }
        return result
      } catch (cause) {
        if (signal?.aborted) {
          throw workspaceError('WAW_ACTION_STALE')
        }
        const failure = workspaceApiError(cause, 'WAW_ACTION_FAILED')
        if (current()) setError({ error: failure, scope })
        throw failure
      } finally {
        const ownsOperation =
          mounted.current &&
          liveScope.current === scope &&
          active.current === operation
        if (ownsOperation) {
          active.current = null
          setPending(null)
        }
      }
    },
    [authScope],
  )

  const start = useCallback(
    (
      projectId: string,
      agentType: 'claude' | 'codex' = 'claude',
      signal?: AbortSignal,
    ) => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(workspaceError('WAW_INVALID_AGENT'))
      return run(
        'start',
        () =>
          api.post(
            `/api/v1/projects/${encodeURIComponent(projectId)}/workspaces/${agentType}/start`,
            {
              body: {},
              csrfToken: auth?.csrf_token,
              signal,
              validate: (value) =>
                parseWorkspaceStartResponse(value, { projectId, agentType }),
            },
          ),
        signal,
      )
    },
    [api, auth, run],
  )
  const connect = useCallback(
    (
      workspaceId: string,
      agentType: 'claude' | 'codex' = 'claude',
      signal?: AbortSignal,
    ) => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(workspaceError('WAW_INVALID_AGENT'))
      return run<WorkspaceAttachmentTicketResponse>(
        'connect',
        () =>
          api.post(
            `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/attachments`,
            {
              body: { mode: 'writer' },
              csrfToken: auth?.csrf_token,
              signal,
              validate: (value) =>
                parseWorkspaceAttachmentTicketResponse(value, {
                  workspaceId,
                  agentType,
                }),
            },
          ),
        signal,
      )
    },
    [api, auth, run],
  )
  const reconnect = useCallback(
    (
      workspaceId: string,
      agentType: 'claude' | 'codex' = 'claude',
      signal?: AbortSignal,
    ) => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(workspaceError('WAW_INVALID_AGENT'))
      return run<WorkspaceAttachmentTicketResponse>(
        'reconnect',
        () =>
          api.post(
            `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reconnect`,
            {
              body: {},
              csrfToken: auth?.csrf_token,
              signal,
              validate: (value) =>
                parseWorkspaceAttachmentTicketResponse(value, {
                  workspaceId,
                  agentType,
                }),
            },
          ),
        signal,
      )
    },
    [api, auth, run],
  )
  const detach = useCallback(
    (
      workspaceId: string,
      attachmentId: string,
      generation: string,
      leaseNumber: string,
      agentType: 'claude' | 'codex' = 'claude',
      signal?: AbortSignal,
    ) => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(workspaceError('WAW_INVALID_AGENT'))
      return run(
        'detach',
        () =>
          api.post(
            `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/detach`,
            {
              body: {
                attachment_id: attachmentId,
                generation,
                lease_number: leaseNumber,
              },
              csrfToken: auth?.csrf_token,
              signal,
              validate: (value) =>
                parseWorkspaceDetachResponse(value, {
                  workspaceId,
                  attachmentId,
                  generation,
                  leaseNumber,
                  agentType,
                }),
            },
          ),
        signal,
      )
    },
    [api, auth, run],
  )
  const stop = useCallback(
    (
      workspaceId: string,
      generation: string,
      agentType: 'claude' | 'codex' = 'claude',
      signal?: AbortSignal,
    ) => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(workspaceError('WAW_INVALID_AGENT'))
      return run(
        'stop',
        () =>
          api.post(
            `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/stop`,
            {
              body: { generation },
              csrfToken: auth?.csrf_token,
              signal,
              validate: (value) =>
                parseWorkspaceStopResponse(value, {
                  workspaceId,
                  generation,
                  agentType,
                }),
            },
          ),
        signal,
      )
    },
    [api, auth, run],
  )

  return {
    pending: pendingState?.scope === authScope ? pendingState.action : null,
    error: errorState?.scope === authScope ? errorState.error : null,
    start,
    connect,
    reconnect,
    detach,
    stop,
  }
}
