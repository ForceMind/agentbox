import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../../lib/api'
import {
  parseWorkspaceAttachmentTicketResponse,
  parseWorkspaceDetachResponse,
  parseWorkspaceStartResponse,
  parseWorkspaceStopResponse,
  WorkspaceAttachmentTicketResponse,
} from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'

export type WorkspaceAction =
  'start' | 'connect' | 'reconnect' | 'detach' | 'stop'

function actionError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({
        code: 'WAW_ACTION_FAILED',
        message: 'Workspace 操作失败',
        status: 0,
      })
}

/** Metadata/control-plane mutations only. Ticket material is returned to the caller and never persisted. */
export function useWorkspaceActions() {
  const { api, auth } = useAuth()
  const authScope = auth ? `${auth.session.id}:${auth.csrf_token}` : null
  const [pendingState, setPending] = useState<{
    action: WorkspaceAction
    scope: string
  } | null>(null)
  const [errorState, setError] = useState<{
    error: ApiError
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
    async <T>(action: WorkspaceAction, task: () => Promise<T>) => {
      const scope = authScope
      if (!scope || !mounted.current || liveScope.current !== scope) {
        throw new ApiError({
          code: 'WAW_SESSION_REQUIRED',
          message: '请重新登录后操作',
          status: 401,
        })
      }
      if (active.current !== null) {
        throw new ApiError({
          code: 'WAW_ACTION_BUSY',
          message: 'Workspace 操作正在进行中',
          status: 409,
        })
      }
      const operation = Symbol('workspace-action')
      active.current = operation
      const current = () =>
        mounted.current &&
        liveScope.current === scope &&
        active.current === operation
      setPending({ action, scope })
      setError(null)
      try {
        const result = await task()
        if (!current()) {
          throw new ApiError({
            code: 'WAW_ACTION_STALE',
            message: '会话已变化，请重新读取工作区状态',
            status: 0,
          })
        }
        return result
      } catch (cause) {
        const failure = actionError(cause)
        if (current()) setError({ error: failure, scope })
        throw failure
      } finally {
        if (current()) {
          active.current = null
          setPending(null)
        }
      }
    },
    [authScope],
  )

  const start = useCallback(
    (projectId: string, agentType: 'claude' | 'codex' = 'claude') => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(
          new ApiError({
            code: 'WAW_INVALID_AGENT',
            message: 'AgentType 无效',
            status: 400,
          }),
        )
      return run('start', () =>
        api.post(
          `/api/v1/projects/${encodeURIComponent(projectId)}/workspaces/${agentType}/start`,
          {
            body: {},
            csrfToken: auth?.csrf_token,
            validate: (value) =>
              parseWorkspaceStartResponse(value, { projectId, agentType }),
          },
        ),
      )
    },
    [api, auth, run],
  )
  const connect = useCallback(
    (workspaceId: string, agentType: 'claude' | 'codex' = 'claude') => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(
          new ApiError({
            code: 'WAW_INVALID_AGENT',
            message: 'AgentType 无效',
            status: 400,
          }),
        )
      return run<WorkspaceAttachmentTicketResponse>('connect', () =>
        api.post(
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/attachments`,
          {
            body: { mode: 'writer' },
            csrfToken: auth?.csrf_token,
            validate: (value) =>
              parseWorkspaceAttachmentTicketResponse(value, {
                workspaceId,
                agentType,
              }),
          },
        ),
      )
    },
    [api, auth, run],
  )
  const reconnect = useCallback(
    (workspaceId: string, agentType: 'claude' | 'codex' = 'claude') => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(
          new ApiError({
            code: 'WAW_INVALID_AGENT',
            message: 'AgentType 无效',
            status: 400,
          }),
        )
      return run<WorkspaceAttachmentTicketResponse>('reconnect', () =>
        api.post(
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reconnect`,
          {
            body: {},
            csrfToken: auth?.csrf_token,
            validate: (value) =>
              parseWorkspaceAttachmentTicketResponse(value, {
                workspaceId,
                agentType,
              }),
          },
        ),
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
    ) => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(
          new ApiError({
            code: 'WAW_INVALID_AGENT',
            message: 'AgentType 无效',
            status: 400,
          }),
        )
      return run('detach', () =>
        api.post(
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/detach`,
          {
            body: {
              attachment_id: attachmentId,
              generation,
              lease_number: leaseNumber,
            },
            csrfToken: auth?.csrf_token,
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
      )
    },
    [api, auth, run],
  )
  const stop = useCallback(
    (
      workspaceId: string,
      generation: string,
      agentType: 'claude' | 'codex' = 'claude',
    ) => {
      if (agentType !== 'claude' && agentType !== 'codex')
        return Promise.reject(
          new ApiError({
            code: 'WAW_INVALID_AGENT',
            message: 'AgentType 无效',
            status: 400,
          }),
        )
      return run('stop', () =>
        api.post(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/stop`, {
          body: { generation },
          csrfToken: auth?.csrf_token,
          validate: (value) =>
            parseWorkspaceStopResponse(value, {
              workspaceId,
              generation,
              agentType,
            }),
        }),
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
