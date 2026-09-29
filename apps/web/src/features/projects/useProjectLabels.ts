import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../../lib/api'
import {
  parseNavigationLabelDeleteImpactResponse,
  parseNavigationLabelListResponse,
  parseNavigationLabelResponse,
  parseProjectLabelSetResponse,
  type NavigationLabelColor,
  type NavigationLabelData,
  type NavigationLabelDeleteImpactResponse,
  type NavigationLabelListResponse,
  type NavigationLabelResponse,
  type ProjectLabelSetData,
  type ProjectLabelSetResponse,
} from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'

export type LabelError = Readonly<{ code: string; requestId?: string }>
type LabelState = Readonly<{
  scope: string | null
  projectId: string
  catalog: readonly NavigationLabelData[]
  assignment: ProjectLabelSetData | null
  loading: boolean
  loaded: boolean
  stale: boolean
  pending: boolean
  error: LabelError | null
}>

function initial(scope: string | null, projectId: string): LabelState {
  return {
    scope,
    projectId,
    catalog: [],
    assignment: null,
    loading: false,
    loaded: false,
    stale: false,
    pending: false,
    error: null,
  }
}

function boundedError(value: unknown): LabelError {
  if (value instanceof ApiError && /^[A-Z][A-Z0-9_]{0,79}$/.test(value.code)) {
    return {
      code: value.code,
      ...(value.requestId && /^[A-Za-z0-9._:-]{1,72}$/.test(value.requestId)
        ? { requestId: value.requestId }
        : {}),
    }
  }
  return { code: 'NAVIGATION_LABEL_UNAVAILABLE' }
}

function consistent(
  catalog: readonly NavigationLabelData[],
  assignment: ProjectLabelSetData,
): boolean {
  const byId = new Map(catalog.map((label) => [label.id, label]))
  return assignment.labels.every((assigned) => {
    const current = byId.get(assigned.id)
    return (
      current?.name === assigned.name &&
      current.color === assigned.color &&
      current.revision === assigned.revision
    )
  })
}

export function useProjectLabels(projectId: string) {
  const { api, auth } = useAuth()
  const scope = auth?.session.id ?? null
  const [state, setState] = useState<LabelState>(() =>
    initial(scope, projectId),
  )
  const [notice, setNotice] = useState<LabelError | null>(null)
  const generation = useRef(0)
  const read = useRef<AbortController | null>(null)
  const operation = useRef<AbortController | null>(null)

  const abortAll = useCallback(() => {
    generation.current += 1
    read.current?.abort()
    read.current = null
    operation.current?.abort()
    operation.current = null
  }, [])

  const refresh = useCallback(async (): Promise<boolean> => {
    if (operation.current) return false
    const token = ++generation.current
    read.current?.abort()
    if (!scope || !/^prj_[0-9a-f]{32}$/.test(projectId) || document.hidden) {
      setState({ ...initial(scope, projectId), stale: true })
      return false
    }
    const controller = new AbortController()
    read.current = controller
    setState({ ...initial(scope, projectId), loading: true })
    try {
      const [catalog, assigned] = await Promise.all([
        api.get<NavigationLabelListResponse>('/api/v1/project-labels', {
          signal: controller.signal,
          timeoutMs: 15_000,
          validate: parseNavigationLabelListResponse,
        }),
        api.get<ProjectLabelSetResponse>(
          `/api/v1/project-labels/projects/${encodeURIComponent(projectId)}`,
          {
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: parseProjectLabelSetResponse,
          },
        ),
      ])
      if (token !== generation.current || controller.signal.aborted)
        return false
      if (
        assigned.data.project_id !== projectId ||
        !consistent(catalog.data.labels, assigned.data)
      ) {
        throw new Error('Project label observations disagree')
      }
      setState({
        ...initial(scope, projectId),
        catalog: catalog.data.labels,
        assignment: assigned.data,
        loaded: true,
      })
      return true
    } catch (value) {
      if (token !== generation.current || controller.signal.aborted)
        return false
      setState({
        ...initial(scope, projectId),
        stale: true,
        error: boundedError(value),
      })
      return false
    } finally {
      if (read.current === controller) read.current = null
    }
  }, [api, projectId, scope])

  useEffect(() => {
    setNotice(null)
    void refresh()
    return abortAll
  }, [refresh, abortAll])

  useEffect(() => {
    const visibilityChanged = () => {
      if (document.hidden) {
        abortAll()
        setState({ ...initial(scope, projectId), stale: true })
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
  }, [abortAll, projectId, refresh, scope])

  const ready =
    Boolean(auth && scope && state.scope === scope) &&
    state.projectId === projectId &&
    state.loaded &&
    !state.stale &&
    !state.loading &&
    !state.pending &&
    state.assignment !== null &&
    !document.hidden

  const perform = useCallback(
    async <T>(
      send: (signal: AbortSignal) => Promise<T>,
      acknowledge: (value: T) => boolean,
    ): Promise<boolean> => {
      if (!ready || operation.current) return false
      const token = generation.current
      const controller = new AbortController()
      operation.current = controller
      read.current?.abort()
      setNotice(null)
      setState((current) => ({ ...current, pending: true }))
      let accepted = false
      try {
        const response = await send(controller.signal)
        if (token !== generation.current || controller.signal.aborted)
          return false
        if (!acknowledge(response))
          throw new Error('Label acknowledgment changed')
        accepted = true
      } catch (value) {
        if (token !== generation.current || controller.signal.aborted)
          return false
        setNotice(boundedError(value))
      } finally {
        if (operation.current === controller) operation.current = null
      }
      if (token !== generation.current || controller.signal.aborted)
        return false
      const fresh = await refresh()
      return accepted && fresh
    },
    [ready, refresh],
  )

  const setAssignment = useCallback(
    async (labelId: string): Promise<boolean> => {
      if (
        !auth ||
        !state.assignment ||
        !state.catalog.some((item) => item.id === labelId)
      ) {
        return false
      }
      const expected = state.assignment.revision
      const desired = !state.assignment.labels.some(
        (item) => item.id === labelId,
      )
      return perform(
        (signal) =>
          api.request<ProjectLabelSetResponse>(
            `/api/v1/project-labels/projects/${encodeURIComponent(projectId)}/${encodeURIComponent(labelId)}`,
            {
              method: 'PUT',
              body: { assigned: desired, expected_revision: expected },
              csrfToken: auth.csrf_token,
              signal,
              timeoutMs: 15_000,
              validate: parseProjectLabelSetResponse,
            },
          ),
        (response) =>
          response.data.project_id === projectId &&
          response.data.revision === expected + 1 &&
          response.data.labels.some((item) => item.id === labelId) === desired,
      )
    },
    [api, auth, perform, projectId, state.assignment, state.catalog],
  )

  const create = useCallback(
    async (name: string, color: NavigationLabelColor): Promise<boolean> => {
      if (!auth) return false
      const normalized = name.replace(/\s+/gu, ' ').trim()
      return perform(
        (signal) =>
          api.request<NavigationLabelResponse>('/api/v1/project-labels', {
            method: 'POST',
            body: { name, color },
            csrfToken: auth.csrf_token,
            signal,
            timeoutMs: 15_000,
            validate: parseNavigationLabelResponse,
          }),
        (response) =>
          response.data.name === normalized &&
          response.data.color === color &&
          response.data.revision === 1 &&
          !state.catalog.some((item) => item.id === response.data.id),
      )
    },
    [api, auth, perform, state.catalog],
  )

  const update = useCallback(
    async (
      label: NavigationLabelData,
      name: string,
      color: NavigationLabelColor,
    ): Promise<boolean> => {
      if (!auth) return false
      const current = state.catalog.find((item) => item.id === label.id)
      if (!current || current.revision !== label.revision) {
        setNotice({ code: 'NAVIGATION_LABEL_CONFLICT' })
        return false
      }
      const normalized = name.replace(/\s+/gu, ' ').trim()
      return perform(
        (signal) =>
          api.request<NavigationLabelResponse>(
            `/api/v1/project-labels/${encodeURIComponent(label.id)}`,
            {
              method: 'PUT',
              body: { name, color, expected_revision: label.revision },
              csrfToken: auth.csrf_token,
              signal,
              timeoutMs: 15_000,
              validate: parseNavigationLabelResponse,
            },
          ),
        (response) =>
          response.data.id === label.id &&
          response.data.name === normalized &&
          response.data.color === color &&
          response.data.revision === label.revision + 1,
      )
    },
    [api, auth, perform, state.catalog],
  )

  const inspectDelete = useCallback(
    async (labelId: string): Promise<number | null> => {
      if (
        !ready ||
        operation.current ||
        !state.catalog.some((item) => item.id === labelId)
      ) {
        return null
      }
      const token = generation.current
      const controller = new AbortController()
      operation.current = controller
      setState((current) => ({ ...current, pending: true }))
      try {
        const response = await api.get<NavigationLabelDeleteImpactResponse>(
          `/api/v1/project-labels/${encodeURIComponent(labelId)}/delete-impact`,
          {
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: parseNavigationLabelDeleteImpactResponse,
          },
        )
        if (token !== generation.current || controller.signal.aborted)
          return null
        if (response.data.label_id !== labelId)
          throw new Error('Delete impact changed')
        return response.data.affected_project_count
      } catch (value) {
        if (token === generation.current && !controller.signal.aborted) {
          setNotice(boundedError(value))
        }
        return null
      } finally {
        if (operation.current === controller) operation.current = null
        if (token === generation.current && !controller.signal.aborted) {
          setState((current) => ({ ...current, pending: false }))
        }
      }
    },
    [api, ready, state.catalog],
  )

  const remove = useCallback(
    async (
      label: NavigationLabelData,
      expectedImpact: number,
    ): Promise<boolean> => {
      if (!auth) return false
      const current = state.catalog.find((item) => item.id === label.id)
      if (!current || current.revision !== label.revision) {
        setNotice({ code: 'NAVIGATION_LABEL_CONFLICT' })
        return false
      }
      return perform(
        (signal) =>
          api.request<NavigationLabelDeleteImpactResponse>(
            `/api/v1/project-labels/${encodeURIComponent(label.id)}/delete`,
            {
              method: 'POST',
              body: {
                expected_revision: label.revision,
                expected_affected_project_count: expectedImpact,
              },
              csrfToken: auth.csrf_token,
              signal,
              timeoutMs: 15_000,
              validate: parseNavigationLabelDeleteImpactResponse,
            },
          ),
        (response) =>
          response.data.label_id === label.id &&
          response.data.affected_project_count === expectedImpact,
      )
    },
    [api, auth, perform, state.catalog],
  )

  const visible =
    state.scope === scope && state.projectId === projectId
      ? state
      : { ...initial(scope, projectId), loading: Boolean(scope) }
  return {
    catalog: visible.catalog,
    assignment: visible.assignment,
    loading: visible.loading,
    loaded: visible.loaded,
    stale: visible.stale,
    pending: visible.pending,
    error: visible.error,
    notice:
      state.scope === scope && state.projectId === projectId ? notice : null,
    refresh,
    setAssignment,
    create,
    update,
    inspectDelete,
    remove,
  }
}
