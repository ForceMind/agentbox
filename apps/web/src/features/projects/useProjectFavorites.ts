import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../../lib/api'
import {
  parseProjectFavoriteListResponse,
  parseProjectFavoriteResponse,
  type ProjectFavoriteData,
  type ProjectFavoriteListResponse,
  type ProjectFavoriteResponse,
} from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'

type FavoriteError = Readonly<{ code: string; requestId?: string }>
type FavoriteNotice = Readonly<{ code: string; projectId: string }>
type FavoriteState = Readonly<{
  scope: string | null
  byProject: Readonly<Record<string, ProjectFavoriteData>>
  loaded: boolean
  loading: boolean
  stale: boolean
  error: FavoriteError | null
  pending: ReadonlySet<string>
}>

const EMPTY: FavoriteState = {
  scope: null,
  byProject: {},
  loaded: false,
  loading: false,
  stale: false,
  error: null,
  pending: new Set(),
}

function boundedError(value: unknown): FavoriteError {
  if (value instanceof ApiError && /^[A-Z][A-Z0-9_]{0,79}$/.test(value.code)) {
    return {
      code: value.code,
      ...(value.requestId && /^[A-Za-z0-9._:-]{1,72}$/.test(value.requestId)
        ? { requestId: value.requestId }
        : {}),
    }
  }
  return { code: 'PROJECT_FAVORITE_UNAVAILABLE' }
}

export function useProjectFavorites() {
  const { api, auth } = useAuth()
  const scope = auth?.session.id ?? null
  const [state, setState] = useState<FavoriteState>(EMPTY)
  const [notice, setNotice] = useState<FavoriteNotice | null>(null)
  const generation = useRef(0)
  const read = useRef<AbortController | null>(null)
  const writes = useRef(new Map<string, AbortController>())
  const refreshNeeded = useRef(false)

  const abortAll = useCallback(() => {
    generation.current += 1
    read.current?.abort()
    read.current = null
    for (const controller of writes.current.values()) controller.abort()
    writes.current.clear()
    refreshNeeded.current = false
  }, [])

  const refresh = useCallback(async () => {
    if (writes.current.size > 0) {
      refreshNeeded.current = true
      return
    }
    const token = ++generation.current
    read.current?.abort()
    if (!scope || document.hidden) {
      setState({ ...EMPTY, scope, stale: document.hidden })
      return
    }
    const controller = new AbortController()
    read.current = controller
    setState({ ...EMPTY, scope, loading: true })
    try {
      const response = await api.get<ProjectFavoriteListResponse>(
        '/api/v1/project-favorites',
        {
          signal: controller.signal,
          timeoutMs: 15_000,
          validate: parseProjectFavoriteListResponse,
        },
      )
      if (token !== generation.current || controller.signal.aborted) return
      const byProject: Record<string, ProjectFavoriteData> = {}
      for (const value of response.data.favorites)
        byProject[value.project_id] = value
      setState({ ...EMPTY, scope, byProject, loaded: true })
    } catch (value) {
      if (token !== generation.current || controller.signal.aborted) return
      setState({ ...EMPTY, scope, stale: true, error: boundedError(value) })
    }
  }, [api, scope])

  useEffect(() => {
    setNotice(null)
    void refresh()
    return abortAll
  }, [refresh, abortAll])

  useEffect(() => {
    const visibilityChanged = () => {
      if (document.hidden) {
        abortAll()
        setState({ ...EMPTY, scope, stale: true })
        setNotice(null)
      } else {
        void refresh()
      }
    }
    const focused = () => {
      if (!document.hidden) void refresh()
    }
    document.addEventListener('visibilitychange', visibilityChanged)
    window.addEventListener('focus', focused)
    return () => {
      document.removeEventListener('visibilitychange', visibilityChanged)
      window.removeEventListener('focus', focused)
    }
  }, [abortAll, refresh, scope])

  const setFavorite = useCallback(
    async (projectId: string) => {
      if (
        !auth ||
        !scope ||
        state.scope !== scope ||
        !state.loaded ||
        state.stale ||
        state.loading ||
        writes.current.has(projectId) ||
        document.hidden
      ) {
        return
      }
      const current = state.byProject[projectId]
      const desired = !(current?.favorite ?? false)
      const expectedRevision = current?.revision ?? 0
      const token = generation.current
      const controller = new AbortController()
      writes.current.set(projectId, controller)
      setNotice(null)
      setState((previous) => ({
        ...previous,
        pending: new Set([...previous.pending, projectId]),
      }))
      try {
        const response = await api.request<ProjectFavoriteResponse>(
          `/api/v1/project-favorites/${encodeURIComponent(projectId)}`,
          {
            method: 'PUT',
            body: { favorite: desired, expected_revision: expectedRevision },
            csrfToken: auth.csrf_token,
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: parseProjectFavoriteResponse,
          },
        )
        if (token !== generation.current || controller.signal.aborted) return
        if (
          response.data.project_id !== projectId ||
          response.data.favorite !== desired ||
          response.data.revision !== expectedRevision + 1
        ) {
          throw new Error('Favorite acknowledgment does not match the request')
        }
        setState((previous) => ({
          ...previous,
          byProject: { ...previous.byProject, [projectId]: response.data },
        }))
      } catch (value) {
        if (token !== generation.current || controller.signal.aborted) return
        const error = boundedError(value)
        setNotice({
          code:
            error.code === 'PROJECT_FAVORITE_CONFLICT'
              ? 'PROJECT_FAVORITE_CONFLICT'
              : 'PROJECT_FAVORITE_UNCERTAIN',
          projectId,
        })
        refreshNeeded.current = true
      } finally {
        writes.current.delete(projectId)
        if (token === generation.current && !controller.signal.aborted) {
          setState((previous) => {
            const pending = new Set(previous.pending)
            pending.delete(projectId)
            return { ...previous, pending }
          })
          if (refreshNeeded.current && writes.current.size === 0) {
            refreshNeeded.current = false
            void refresh()
          }
        }
      }
    },
    [api, auth, refresh, scope, state],
  )

  const visible =
    state.scope === scope ? state : { ...EMPTY, loading: Boolean(scope) }
  return {
    byProject: visible.byProject,
    loaded: visible.loaded,
    loading: visible.loading,
    stale: visible.stale,
    error: visible.error,
    pending: visible.pending,
    notice: visible.scope === scope ? notice : null,
    refresh,
    setFavorite,
  }
}
