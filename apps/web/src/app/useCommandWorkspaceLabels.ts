import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../lib/api'
import {
  parseNavigationLabelListResponse,
  parseWorkspaceLabelSetResponse,
  type NavigationLabelData,
  type NavigationLabelListResponse,
  type WorkspaceLabelSetData,
  type WorkspaceLabelSetResponse,
} from '../lib/contracts'
import { useAuth } from '../features/auth/AuthContext'
import { NAVIGATION_LABELS_CHANGED_EVENT } from '../features/projects/labelEvents'
import {
  isWorkspaceId,
  parseWorkspaceMetadata,
  type WorkspaceMetadata,
} from '../features/workspace/workspaceMetadata'

type Notice = 'conflict' | 'invalid' | 'uncertain' | 'unavailable' | null
type View = {
  target: string
  catalog: readonly NavigationLabelData[]
  assignment: WorkspaceLabelSetData | null
  loading: boolean
  pending: boolean
  notice: Notice
}

function empty(target: string): View {
  return {
    target,
    catalog: [],
    assignment: null,
    loading: false,
    pending: false,
    notice: null,
  }
}

function consistent(
  catalog: readonly NavigationLabelData[],
  assignment: WorkspaceLabelSetData,
): boolean {
  const definitions = new Map(catalog.map((label) => [label.id, label]))
  return assignment.labels.every((assigned) => {
    const current = definitions.get(assigned.id)
    return (
      current?.name === assigned.name &&
      current.color === assigned.color &&
      current.revision === assigned.revision
    )
  })
}

function rejectedNotice(error: unknown): Notice {
  if (error instanceof ApiError) {
    if (
      error.code === 'WORKSPACE_LABEL_CONFLICT' ||
      error.code === 'NAVIGATION_LABEL_CONFLICT' ||
      error.code === 'NAVIGATION_LABEL_NOT_FOUND'
    )
      return 'conflict'
    if (
      error.code === 'NAVIGATION_LABEL_INVALID' ||
      error.code === 'NAVIGATION_LABEL_LIMIT_EXCEEDED'
    )
      return 'invalid'
  }
  return 'uncertain'
}

/** Metadata-only command choices for the exact current Workspace route. */
export function useCommandWorkspaceLabels(workspaceId: string | null) {
  const { api, auth } = useAuth()
  const scope = auth?.session.id ?? null
  const target = `${scope ?? ''}:${workspaceId ?? ''}`
  const [view, setView] = useState<View>(() => empty(target))
  const generation = useRef(0)
  const read = useRef<AbortController | null>(null)
  const write = useRef<AbortController | null>(null)
  const refreshOnWriteSettle = useRef(false)

  const refresh =
    useCallback(async (): Promise<WorkspaceLabelSetData | null> => {
      if (write.current) return null
      const token = ++generation.current
      read.current?.abort()
      if (
        !scope ||
        !workspaceId ||
        !isWorkspaceId(workspaceId) ||
        document.hidden
      ) {
        setView(empty(target))
        return null
      }
      const controller = new AbortController()
      read.current = controller
      setView({ ...empty(target), loading: true })
      try {
        const metadata = await api.get<WorkspaceMetadata>(
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}`,
          {
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: (value) => parseWorkspaceMetadata(value, workspaceId),
          },
        )
        if (token !== generation.current || controller.signal.aborted)
          return null
        if (metadata.id !== workspaceId)
          throw new Error('Workspace identity changed')
        const [catalog, assignment] = await Promise.all([
          api.get<NavigationLabelListResponse>('/api/v1/project-labels', {
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: parseNavigationLabelListResponse,
          }),
          api.get<WorkspaceLabelSetResponse>(
            `/api/v1/project-labels/workspaces/${encodeURIComponent(metadata.project_id)}/${metadata.agent_type}`,
            {
              signal: controller.signal,
              timeoutMs: 15_000,
              validate: parseWorkspaceLabelSetResponse,
            },
          ),
        ])
        if (token !== generation.current || controller.signal.aborted)
          return null
        if (
          assignment.data.workspace_id !== workspaceId ||
          assignment.data.project_id !== metadata.project_id ||
          assignment.data.agent_type !== metadata.agent_type ||
          !consistent(catalog.data.labels, assignment.data)
        ) {
          throw new Error('Workspace label observations disagree')
        }
        setView({
          target,
          catalog: catalog.data.labels,
          assignment: assignment.data,
          loading: false,
          pending: false,
          notice: null,
        })
        return assignment.data
      } catch {
        if (token === generation.current && !controller.signal.aborted) {
          setView({ ...empty(target), notice: 'unavailable' })
        }
        return null
      } finally {
        if (read.current === controller) read.current = null
      }
    }, [api, scope, target, workspaceId])

  useEffect(() => {
    void refresh()
    const onVisibility = () => {
      if (document.hidden) {
        refreshOnWriteSettle.current = false
        generation.current += 1
        read.current?.abort()
        write.current?.abort()
        setView(empty(target))
      } else if (write.current) refreshOnWriteSettle.current = true
      else void refresh()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      refreshOnWriteSettle.current = false
      generation.current += 1
      read.current?.abort()
      write.current?.abort()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [refresh, target])

  const visible = view.target === target ? view : empty(target)
  const ready = Boolean(
    scope &&
    workspaceId &&
    visible.assignment &&
    !visible.loading &&
    !visible.pending &&
    !document.hidden,
  )

  const toggle = useCallback(
    async (labelId: string): Promise<boolean> => {
      if (
        !auth ||
        !ready ||
        write.current ||
        !visible.assignment ||
        !visible.catalog.some((label) => label.id === labelId)
      )
        return false
      const assignment = visible.assignment
      const desired = !assignment.labels.some((label) => label.id === labelId)
      const expected = assignment.revision
      const token = generation.current
      const controller = new AbortController()
      read.current?.abort()
      write.current = controller
      setView((current) => ({ ...current, pending: true, notice: null }))
      let accepted = false
      let rejection: Notice = 'uncertain'
      try {
        const response = await api.request<WorkspaceLabelSetResponse>(
          `/api/v1/project-labels/workspaces/${encodeURIComponent(assignment.project_id)}/${assignment.agent_type}/${encodeURIComponent(labelId)}`,
          {
            method: 'PUT',
            body: { assigned: desired, expected_revision: expected },
            csrfToken: auth.csrf_token,
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: parseWorkspaceLabelSetResponse,
          },
        )
        accepted =
          response.data.workspace_id === assignment.workspace_id &&
          response.data.project_id === assignment.project_id &&
          response.data.agent_type === assignment.agent_type &&
          response.data.revision === expected + 1 &&
          response.data.labels.some((label) => label.id === labelId) === desired
      } catch (error) {
        rejection = rejectedNotice(error)
      } finally {
        if (write.current === controller) write.current = null
        if (refreshOnWriteSettle.current && !document.hidden) {
          refreshOnWriteSettle.current = false
          void refresh()
        }
      }
      if (token !== generation.current || controller.signal.aborted)
        return false
      const fresh = await refresh()
      const confirmed =
        accepted &&
        fresh?.workspace_id === assignment.workspace_id &&
        fresh.revision === expected + 1 &&
        fresh.labels.some((label) => label.id === labelId) === desired
      if (!confirmed) {
        setView((current) =>
          current.target === target
            ? { ...current, notice: accepted ? 'uncertain' : rejection }
            : current,
        )
      }
      if (confirmed)
        window.dispatchEvent(new Event(NAVIGATION_LABELS_CHANGED_EVENT))
      return Boolean(confirmed)
    },
    [api, auth, ready, refresh, target, visible.assignment, visible.catalog],
  )

  return {
    catalog: visible.catalog,
    assignment: visible.assignment,
    loading: visible.loading,
    pending: visible.pending,
    notice: visible.notice,
    ready,
    refresh,
    toggle,
  }
}
