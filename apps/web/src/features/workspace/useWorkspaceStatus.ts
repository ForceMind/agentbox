import { useCallback, useEffect, useRef, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../../lib/api'
import {
  parseWorkspaceRuntimeStatusResponse,
  WorkspaceRuntimeStatusResponse,
} from '../../lib/contracts'

export type WorkspaceStatusView =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; response: WorkspaceRuntimeStatusResponse }
  | { status: 'error'; error: ApiError }

function normalizedError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({
        code: 'WAW_STATUS_UNAVAILABLE',
        message: 'Workspace status is unavailable',
        status: 0,
      })
}

/** Fetches bounded metadata only; it never creates an admission or terminal transport. */
export function useWorkspaceStatus(
  workspaceId: string | undefined,
  refreshKey = '',
) {
  const { api, auth } = useAuth()
  const scope = `${auth?.session.id ?? ''}:${auth?.csrf_token ?? ''}:${workspaceId ?? ''}:${refreshKey}`
  const [snapshot, setSnapshot] = useState<{
    scope: string
    view: WorkspaceStatusView
  }>({ scope: '', view: { status: 'idle' } })
  const requestGeneration = useRef(0)

  const refresh = useCallback(async () => {
    const generation = ++requestGeneration.current
    if (!workspaceId) {
      setSnapshot({ scope, view: { status: 'idle' } })
      return
    }
    setSnapshot({ scope, view: { status: 'loading' } })
    try {
      const response = await api.get<WorkspaceRuntimeStatusResponse>(
        `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/status`,
        {
          timeoutMs: 10_000,
          validate: (value) => {
            const result = parseWorkspaceRuntimeStatusResponse(value)
            if (result.data.workspace_id !== workspaceId)
              throw new Error('Workspace status identity mismatch')
            return result
          },
        },
      )
      if (requestGeneration.current === generation) {
        setSnapshot({ scope, view: { status: 'loaded', response } })
      }
    } catch (error) {
      if (requestGeneration.current === generation) {
        setSnapshot({
          scope,
          view: { status: 'error', error: normalizedError(error) },
        })
      }
    }
  }, [api, scope, workspaceId])

  useEffect(() => {
    void refresh()
    return () => {
      requestGeneration.current += 1
    }
  }, [refresh])

  const view: WorkspaceStatusView =
    snapshot.scope === scope
      ? snapshot.view
      : { status: workspaceId ? 'loading' : 'idle' }
  return { refresh, view }
}
