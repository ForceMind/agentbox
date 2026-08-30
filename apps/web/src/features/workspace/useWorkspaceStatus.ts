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
export function useWorkspaceStatus(workspaceId: string | undefined) {
  const { api } = useAuth()
  const [view, setView] = useState<WorkspaceStatusView>({ status: 'idle' })
  const requestGeneration = useRef(0)

  const refresh = useCallback(async () => {
    const generation = ++requestGeneration.current
    if (!workspaceId) {
      setView({ status: 'idle' })
      return
    }
    setView({ status: 'loading' })
    try {
      const response = await api.get<WorkspaceRuntimeStatusResponse>(
        `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/status`,
        {
          timeoutMs: 10_000,
          validate: parseWorkspaceRuntimeStatusResponse,
        },
      )
      if (requestGeneration.current === generation) {
        setView({ status: 'loaded', response })
      }
    } catch (error) {
      if (requestGeneration.current === generation) {
        setView({ status: 'error', error: normalizedError(error) })
      }
    }
  }, [api, workspaceId])

  useEffect(() => {
    void refresh()
    return () => {
      requestGeneration.current += 1
    }
  }, [refresh])

  return { refresh, view }
}
