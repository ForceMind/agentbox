import { useCallback, useEffect, useRef, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import {
  parseWorkspaceRuntimeStatusResponse,
  WorkspaceRuntimeStatusResponse,
} from '../../lib/contracts'
import { workspaceApiError, type WorkspaceApiErrorView } from './workspaceView'

export type WorkspaceStatusView =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; response: WorkspaceRuntimeStatusResponse }
  | { status: 'error'; error: WorkspaceApiErrorView }

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
          // The controller compares all Runtime identity fields against the
          // selected metadata row and emits the specific fenced identity error.
          // Keeping the parsed response here lets that higher-level guard
          // distinguish an identity mismatch from transport unavailability.
          validate: parseWorkspaceRuntimeStatusResponse,
        },
      )
      if (requestGeneration.current === generation) {
        setSnapshot({ scope, view: { status: 'loaded', response } })
      }
    } catch (error) {
      if (requestGeneration.current === generation) {
        setSnapshot({
          scope,
          view: {
            status: 'error',
            error: workspaceApiError(error, 'WAW_STATUS_UNAVAILABLE'),
          },
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
