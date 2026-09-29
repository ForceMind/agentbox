import { useCallback, useEffect, useRef, useState } from 'react'

import { OpaqueUserValue } from '../../components/i18n'
import { ApiError } from '../../lib/api'
import {
  formatMessage,
  type Locale,
  type MessageArguments,
  type ParameterFreeMessageKey,
} from '../../i18n'
import {
  parseNavigationLabelListResponse,
  parseWorkspaceLabelSetResponse,
  type NavigationLabelData,
  type NavigationLabelListResponse,
  type WorkspaceLabelSetData,
  type WorkspaceLabelSetResponse,
} from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'
import { NAVIGATION_LABELS_CHANGED_EVENT } from '../projects/labelEvents'

import '../projects/ProjectLabelsPanel.css'

type LabelKey = Extract<ParameterFreeMessageKey, `workspace.labels${string}`>

function copy(locale: Locale, key: LabelKey): string {
  return formatMessage(locale, ...([key, {}] as MessageArguments))
}

type LabelView = {
  target: string
  catalog: NavigationLabelData[]
  assignment: WorkspaceLabelSetData | null
  loading: boolean
  stale: boolean
  pending: boolean
  notice: 'none' | 'conflict' | 'invalid' | 'uncertain'
}

const empty = (target: string): LabelView => ({
  target,
  catalog: [],
  assignment: null,
  loading: false,
  stale: true,
  pending: false,
  notice: 'none',
})

export function WorkspaceLabelsPanel({
  projectId,
  agentType,
  locale,
}: {
  projectId: string
  agentType: 'claude' | 'codex'
  locale: Locale
}) {
  const { api, auth } = useAuth()
  const scope = auth?.session.id ?? null
  const target = `${scope ?? ''}:${projectId}:${agentType}`
  const [view, setView] = useState<LabelView>(() => empty(target))
  const visible = view.target === target ? view : empty(target)
  const generation = useRef(0)
  const current = useRef<AbortController | null>(null)
  const writing = useRef(false)
  const path = `/api/v1/project-labels/workspaces/${encodeURIComponent(projectId)}/${agentType}`

  const refresh = useCallback(
    async (background = false): Promise<WorkspaceLabelSetData | null> => {
      if (background && (writing.current || current.current)) return null
      const token = ++generation.current
      current.current?.abort()
      if (!scope || !/^prj_[0-9a-f]{32}$/.test(projectId) || document.hidden) {
        setView(empty(target))
        return null
      }
      const controller = new AbortController()
      current.current = controller
      setView((previous) =>
        background && previous.target === target && !previous.stale
          ? { ...previous, loading: true }
          : { ...empty(target), loading: true },
      )
      try {
        const [catalog, assignment] = await Promise.all([
          api.get<NavigationLabelListResponse>('/api/v1/project-labels', {
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: parseNavigationLabelListResponse,
          }),
          api.get<WorkspaceLabelSetResponse>(path, {
            signal: controller.signal,
            timeoutMs: 15_000,
            validate: parseWorkspaceLabelSetResponse,
          }),
        ])
        if (token !== generation.current || controller.signal.aborted)
          return null
        const data = assignment.data
        const definitions = new Map(
          catalog.data.labels.map((label) => [label.id, label]),
        )
        if (
          data.project_id !== projectId ||
          data.agent_type !== agentType ||
          data.labels.some((label) => {
            const definition = definitions.get(label.id)
            return (
              definition?.name !== label.name ||
              definition.color !== label.color ||
              definition.revision !== label.revision
            )
          })
        ) {
          throw new Error('Workspace label observations disagree')
        }
        setView({
          target,
          catalog: catalog.data.labels,
          assignment: data,
          loading: false,
          stale: false,
          pending: false,
          notice: 'none',
        })
        return data
      } catch {
        if (token === generation.current && !controller.signal.aborted) {
          setView(empty(target))
        }
        return null
      } finally {
        if (current.current === controller) current.current = null
      }
    },
    [agentType, api, path, projectId, scope, target],
  )

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => {
      if (scope && !document.hidden && !writing.current && !current.current) {
        void refresh(true)
      }
    }, 30_000)
    const onFocus = () => {
      if (!document.hidden && !writing.current) void refresh()
    }
    const onVisibility = () => {
      if (document.hidden) {
        generation.current += 1
        current.current?.abort()
        setView(empty(target))
      } else if (!writing.current) void refresh()
    }
    window.addEventListener('focus', onFocus)
    window.addEventListener(NAVIGATION_LABELS_CHANGED_EVENT, onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.clearInterval(interval)
      generation.current += 1
      current.current?.abort()
      window.removeEventListener('focus', onFocus)
      window.removeEventListener(NAVIGATION_LABELS_CHANGED_EVENT, onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [refresh, scope, target])

  async function toggle(labelId: string) {
    if (
      writing.current ||
      !auth ||
      !scope ||
      visible.loading ||
      visible.stale ||
      !visible.assignment ||
      document.hidden
    )
      return
    const assignment = visible.assignment
    const assigned = !assignment.labels.some((label) => label.id === labelId)
    const expectedRevision = assignment.revision
    const token = generation.current
    const controller = new AbortController()
    writing.current = true
    current.current?.abort()
    current.current = controller
    setView((previous) => ({ ...previous, pending: true, notice: 'none' }))
    let accepted = false
    let rejected: LabelView['notice'] = 'uncertain'
    try {
      const response = await api.request<WorkspaceLabelSetResponse>(
        `${path}/${encodeURIComponent(labelId)}`,
        {
          method: 'PUT',
          body: { assigned, expected_revision: expectedRevision },
          csrfToken: auth.csrf_token,
          signal: controller.signal,
          timeoutMs: 15_000,
          validate: parseWorkspaceLabelSetResponse,
        },
      )
      accepted =
        response.data.project_id === projectId &&
        response.data.agent_type === agentType &&
        response.data.workspace_id === assignment.workspace_id &&
        response.data.revision === expectedRevision + 1 &&
        response.data.labels.some((label) => label.id === labelId) === assigned
    } catch (error) {
      accepted = false
      if (error instanceof ApiError) {
        if (
          error.code === 'WORKSPACE_LABEL_CONFLICT' ||
          error.code === 'NAVIGATION_LABEL_CONFLICT' ||
          error.code === 'NAVIGATION_LABEL_NOT_FOUND'
        )
          rejected = 'conflict'
        else if (
          error.code === 'NAVIGATION_LABEL_INVALID' ||
          error.code === 'NAVIGATION_LABEL_LIMIT_EXCEEDED'
        )
          rejected = 'invalid'
      }
    } finally {
      writing.current = false
      if (current.current === controller) current.current = null
    }
    if (token !== generation.current || controller.signal.aborted) return
    const fresh = await refresh()
    if (
      !accepted ||
      !fresh ||
      fresh.revision !== expectedRevision + 1 ||
      fresh.labels.some((label) => label.id === labelId) !== assigned
    ) {
      setView((previous) => ({
        ...previous,
        notice: accepted ? 'uncertain' : rejected,
      }))
    }
  }

  return (
    <section
      className="runtime-card project-label-panel"
      aria-label={copy(locale, 'workspace.labelsTitle')}
    >
      <div className="runtime-card-heading">
        <h2>{copy(locale, 'workspace.labelsTitle')}</h2>
        <button
          className="secondary-button"
          type="button"
          disabled={visible.pending}
          onClick={() => void refresh()}
        >
          {copy(locale, 'workspace.labelsRefresh')}
        </button>
      </div>
      <p>{copy(locale, 'workspace.labelsDescription')}</p>
      {visible.loading && (
        <p role="status">{copy(locale, 'workspace.labelsLoading')}</p>
      )}
      {visible.notice !== 'none' && (
        <p role="alert">
          {copy(
            locale,
            visible.notice === 'conflict'
              ? 'workspace.labelsConflict'
              : visible.notice === 'invalid'
                ? 'workspace.labelsInvalid'
                : 'workspace.labelsUncertain',
          )}
        </p>
      )}
      {visible.stale && !visible.loading && (
        <p role="status">{copy(locale, 'workspace.labelsUnavailable')}</p>
      )}
      {!visible.stale && visible.catalog.length === 0 && (
        <p>{copy(locale, 'workspace.labelsEmpty')}</p>
      )}
      {!visible.stale && visible.assignment && visible.catalog.length > 0 && (
        <div className="project-label-chips">
          {visible.catalog.map((label) => (
            <label key={label.id} className="project-label-option">
              <input
                type="checkbox"
                checked={visible.assignment!.labels.some(
                  (item) => item.id === label.id,
                )}
                disabled={visible.pending || visible.loading}
                onChange={() => void toggle(label.id)}
              />
              <span
                className="project-label-dot"
                data-color={label.color}
                aria-hidden="true"
              />
              <OpaqueUserValue value={label.name} />
            </label>
          ))}
        </div>
      )}
    </section>
  )
}
