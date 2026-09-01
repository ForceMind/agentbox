import { useCallback, useState } from 'react'

import { ApiError } from '../../lib/api'
import {
  parseWorkspaceAttachmentTicketResponse,
  parseWorkspaceDetachResponse,
  parseWorkspaceStartResponse,
  parseWorkspaceStopResponse,
  WorkspaceAttachmentTicketResponse,
} from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'

export type WorkspaceAction = 'start' | 'connect' | 'reconnect' | 'detach' | 'stop'

function actionError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({ code: 'WAW_ACTION_FAILED', message: 'Workspace 操作失败', status: 0 })
}

/** Metadata/control-plane mutations only. Ticket material is returned to the caller and never persisted. */
export function useWorkspaceActions() {
  const { api, auth } = useAuth()
  const [pending, setPending] = useState<WorkspaceAction | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const run = useCallback(async <T,>(action: WorkspaceAction, task: () => Promise<T>) => {
    if (!auth) return undefined
    setPending(action)
    setError(null)
    try {
      return await task()
    } catch (cause) {
      const failure = actionError(cause)
      setError(failure)
      throw failure
    } finally {
      setPending(null)
    }
  }, [auth])

  const start = useCallback((projectId: string) => run('start', () => api.post(`/api/v1/projects/${encodeURIComponent(projectId)}/workspaces/claude/start`, {
    body: {}, csrfToken: auth?.csrf_token, validate: parseWorkspaceStartResponse,
  })), [api, auth, run])
  const connect = useCallback((workspaceId: string) => run<WorkspaceAttachmentTicketResponse>('connect', () => api.post(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/attachments`, {
    body: { mode: 'writer' }, csrfToken: auth?.csrf_token, validate: parseWorkspaceAttachmentTicketResponse,
  })), [api, auth, run])
  const reconnect = useCallback((workspaceId: string) => run<WorkspaceAttachmentTicketResponse>('reconnect', () => api.post(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reconnect`, {
    body: {}, csrfToken: auth?.csrf_token, validate: parseWorkspaceAttachmentTicketResponse,
  })), [api, auth, run])
  const detach = useCallback((workspaceId: string, attachmentId: string, generation: string, leaseNumber: string) => run('detach', () => api.post(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/detach`, {
    body: { attachment_id: attachmentId, generation, lease_number: leaseNumber }, csrfToken: auth?.csrf_token, validate: parseWorkspaceDetachResponse,
  })), [api, auth, run])
  const stop = useCallback((workspaceId: string, generation: string) => run('stop', () => api.post(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/stop`, {
    body: { generation }, csrfToken: auth?.csrf_token, validate: parseWorkspaceStopResponse,
  })), [api, auth, run])

  return { pending, error, start, connect, reconnect, detach, stop }
}
