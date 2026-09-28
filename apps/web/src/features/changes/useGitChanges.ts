import { useCallback, useEffect, useRef, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../../lib/api'
import {
  parseGitChangePageResponse,
  type GitChangeEntryData,
  type GitChangePageResponse,
} from '../../lib/contracts'

type ChangesError = Readonly<{ code: string; requestId?: string }>

type ChangesState = Readonly<{
  scope: string | null
  files: GitChangeEntryData[]
  totalCount: number
  nextCursor: string | null
  isRepository: boolean
  loading: boolean
  loadingMore: boolean
  stale: boolean
  error: ChangesError | null
}>

const EMPTY: ChangesState = {
  scope: null,
  files: [],
  totalCount: 0,
  nextCursor: null,
  isRepository: true,
  loading: false,
  loadingMore: false,
  stale: false,
  error: null,
}
const INITIAL: ChangesState = { ...EMPTY, loading: true }

function boundedError(value: unknown): ChangesError {
  if (value instanceof ApiError && /^[A-Z][A-Z0-9_]{0,79}$/.test(value.code)) {
    return {
      code: value.code,
      ...(value.requestId && /^[A-Za-z0-9._:-]{1,96}$/.test(value.requestId)
        ? { requestId: value.requestId }
        : {}),
    }
  }
  return { code: 'GIT_CHANGES_UNAVAILABLE' }
}

export function useGitChanges(projectId: string | undefined) {
  const { api, auth } = useAuth()
  const sessionId = auth?.session.id
  const scope =
    projectId && sessionId ? JSON.stringify([sessionId, projectId]) : null
  const [state, setState] = useState<ChangesState>(INITIAL)
  const generation = useRef(0)
  const pending = useRef<AbortController | null>(null)
  const loadingMore = useRef(false)

  const refresh = useCallback(async () => {
    const token = ++generation.current
    pending.current?.abort()
    loadingMore.current = false
    if (!projectId || !sessionId || document.hidden) {
      setState({ ...EMPTY, stale: document.hidden })
      return
    }
    const controller = new AbortController()
    pending.current = controller
    setState({ ...EMPTY, scope, loading: true })
    try {
      const response = await api.get<GitChangePageResponse>(
        `/api/v1/projects/${encodeURIComponent(projectId)}/git/changes`,
        {
          signal: controller.signal,
          timeoutMs: 15_000,
          validate: parseGitChangePageResponse,
        },
      )
      if (token !== generation.current || controller.signal.aborted) return
      setState({
        scope,
        files: response.data.files,
        totalCount: response.data.total_count,
        nextCursor: response.data.next_cursor,
        isRepository: response.data.is_repository,
        loading: false,
        loadingMore: false,
        stale: false,
        error: null,
      })
    } catch (value) {
      if (token !== generation.current || controller.signal.aborted) return
      setState({ ...EMPTY, scope, error: boundedError(value) })
    }
  }, [api, projectId, sessionId, scope])

  useEffect(() => {
    void refresh()
    return () => {
      generation.current += 1
      pending.current?.abort()
      loadingMore.current = false
    }
  }, [refresh, scope])

  useEffect(() => {
    const visibilityChanged = () => {
      if (document.hidden) {
        generation.current += 1
        pending.current?.abort()
        loadingMore.current = false
        setState({ ...EMPTY, scope, stale: true })
      } else {
        void refresh()
      }
    }
    document.addEventListener('visibilitychange', visibilityChanged)
    return () =>
      document.removeEventListener('visibilitychange', visibilityChanged)
  }, [refresh, scope])

  const loadMore = useCallback(async () => {
    if (
      !projectId ||
      !sessionId ||
      state.scope !== scope ||
      !state.nextCursor ||
      state.stale ||
      state.loading ||
      loadingMore.current ||
      document.hidden
    ) {
      return
    }
    const token = generation.current
    const cursor = state.nextCursor
    const controller = new AbortController()
    pending.current = controller
    loadingMore.current = true
    setState((current) => ({ ...current, loadingMore: true, error: null }))
    try {
      const response = await api.get<GitChangePageResponse>(
        `/api/v1/projects/${encodeURIComponent(projectId)}/git/changes?cursor=${encodeURIComponent(cursor)}`,
        {
          signal: controller.signal,
          timeoutMs: 15_000,
          validate: parseGitChangePageResponse,
        },
      )
      if (token !== generation.current || controller.signal.aborted) return
      setState((current) => {
        if (
          current.nextCursor !== cursor ||
          current.totalCount !== response.data.total_count ||
          current.isRepository !== response.data.is_repository ||
          response.data.files.some((item) =>
            current.files.some((known) => known.path === item.path),
          )
        ) {
          return {
            ...EMPTY,
            scope,
            stale: true,
            error: { code: 'GIT_CHANGES_STALE' },
          }
        }
        return {
          ...current,
          files: [...current.files, ...response.data.files],
          nextCursor: response.data.next_cursor,
          loadingMore: false,
        }
      })
    } catch (value) {
      if (token !== generation.current || controller.signal.aborted) return
      setState({ ...EMPTY, scope, stale: true, error: boundedError(value) })
    } finally {
      loadingMore.current = false
    }
  }, [
    api,
    projectId,
    sessionId,
    scope,
    state.loading,
    state.nextCursor,
    state.scope,
    state.stale,
  ])

  const visibleState =
    state.scope === scope ? state : { ...EMPTY, loading: Boolean(scope) }
  return {
    files: visibleState.files,
    totalCount: visibleState.totalCount,
    nextCursor: visibleState.nextCursor,
    isRepository: visibleState.isRepository,
    loading: visibleState.loading,
    loadingMore: visibleState.loadingMore,
    stale: visibleState.stale,
    error: visibleState.error,
    loadMore,
    refresh,
  }
}
