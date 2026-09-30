import { useEffect, useMemo, useRef, useState } from 'react'

import { OpaqueUserValue } from '../components/i18n'
import { useAuth } from '../features/auth/AuthContext'
import { formatMessage, type Locale } from '../i18n'
import {
  parseProjectListResponse,
  type ProjectData,
  type ProjectListResponse,
} from '../lib/contracts'
import {
  commandResults,
  workspaceLabelResults,
  type CommandCenterAction,
  type CommandResult,
} from './commandCenterResults'
import { useCommandWorkspaceLabels } from './useCommandWorkspaceLabels'

import './CommandCenter.css'

export function CommandCenter({
  actions,
  locale,
  onClose,
  onNavigate,
  workspaceId = null,
}: {
  actions: readonly CommandCenterAction[]
  locale: Locale
  onClose: () => void
  onNavigate: (href: string) => void
  workspaceId?: string | null
}) {
  const { api, auth } = useAuth()
  const [projectRead, setProjectRead] = useState<{
    projects: ProjectData[]
    loading: boolean
    error: boolean
  }>({ projects: [], loading: true, error: false })
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const labels = useCommandWorkspaceLabels(workspaceId)
  const dialog = useRef<HTMLDialogElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const results = useMemo(
    () => [
      ...commandResults(actions, projectRead.projects, query),
      ...workspaceLabelResults(
        labels.catalog,
        new Set(labels.assignment?.labels.map((label) => label.id) ?? []),
        query,
      ),
    ],
    [actions, labels.assignment, labels.catalog, projectRead.projects, query],
  )
  const activeIndex = Math.min(selectedIndex, Math.max(0, results.length - 1))

  useEffect(() => {
    const controller = new AbortController()
    let current = true
    void api
      .get<ProjectListResponse>('/api/v1/projects', {
        signal: controller.signal,
        timeoutMs: 45_000,
        validate: parseProjectListResponse,
      })
      .then((response) => {
        if (current) {
          setProjectRead({
            projects: response.data.projects,
            loading: false,
            error: false,
          })
        }
      })
      .catch(() => {
        if (current) {
          setProjectRead({ projects: [], loading: false, error: true })
        }
      })
    return () => {
      current = false
      controller.abort()
    }
  }, [api, auth?.session.id])

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (typeof element.showModal === 'function') element.showModal()
    else element.setAttribute('open', '')
    input.current?.focus()
    return () => {
      if (typeof element.close === 'function' && element.open) element.close()
      else element.removeAttribute('open')
    }
  }, [])

  function run(result: CommandResult) {
    if (labels.pending) return
    if (result.kind === 'workspace-label') {
      void labels.toggle(result.label.id)
      return
    }
    onClose()
    onNavigate(result.href)
  }

  return (
    <dialog
      aria-label={formatMessage(locale, 'shell.commandCenter', {})}
      aria-modal="true"
      className="command-center-dialog"
      onCancel={(event) => {
        event.preventDefault()
        if (!labels.pending) onClose()
      }}
      ref={dialog}
    >
      <div className="command-center-heading">
        <h2>{formatMessage(locale, 'shell.commandCenter', {})}</h2>
        <button
          aria-label={formatMessage(locale, 'shell.closeCommandCenter', {})}
          className="icon-button"
          disabled={labels.pending}
          onClick={onClose}
          type="button"
        >
          ×
        </button>
      </div>
      <input
        aria-activedescendant={
          results.length > 0 ? `command-result-${activeIndex}` : undefined
        }
        aria-controls="command-center-results"
        aria-expanded="true"
        aria-label={formatMessage(
          locale,
          workspaceId ? 'shell.commandSearchWorkspace' : 'shell.commandSearch',
          {},
        )}
        autoComplete="off"
        className="command-center-input"
        maxLength={128}
        onChange={(event) => {
          setQuery(event.target.value)
          setSelectedIndex(0)
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && results.length > 0) {
            event.preventDefault()
            setSelectedIndex((current) => (current + 1) % results.length)
          } else if (event.key === 'ArrowUp' && results.length > 0) {
            event.preventDefault()
            setSelectedIndex(
              (current) => (current - 1 + results.length) % results.length,
            )
          } else if (event.key === 'Enter' && results[activeIndex]) {
            event.preventDefault()
            run(results[activeIndex])
          } else if (event.key === 'Escape' && !labels.pending) {
            event.preventDefault()
            onClose()
          }
        }}
        placeholder={formatMessage(
          locale,
          'shell.commandSearchPlaceholder',
          {},
        )}
        ref={input}
        role="combobox"
        type="search"
        value={query}
      />
      <div
        className="command-center-results"
        id="command-center-results"
        role="listbox"
      >
        {results.map((result, index) => (
          <div
            aria-label={
              result.kind === 'action'
                ? result.title
                : result.kind === 'project'
                  ? result.project.display_name
                  : undefined
            }
            aria-disabled={labels.pending}
            aria-selected={index === activeIndex}
            className={`command-center-result${index === activeIndex ? ' selected' : ''}`}
            id={`command-result-${index}`}
            key={result.id}
            onClick={() => run(result)}
            onMouseDown={(event) => event.preventDefault()}
            role="option"
          >
            <span>
              {result.kind === 'action' ? (
                result.title
              ) : result.kind === 'project' ? (
                <OpaqueUserValue value={result.project.display_name} />
              ) : (
                <>
                  {formatMessage(locale, 'shell.commandLabelAs', {})}{' '}
                  <OpaqueUserValue value={result.label.name} />
                </>
              )}
            </span>
            <small>
              {formatMessage(
                locale,
                result.kind === 'action'
                  ? 'shell.commandPage'
                  : result.kind === 'project'
                    ? 'shell.commandProject'
                    : result.assigned
                      ? 'shell.commandLabelAssigned'
                      : 'shell.commandLabelAvailable',
                {},
              )}
            </small>
          </div>
        ))}
      </div>
      {projectRead.loading && (
        <p className="command-center-status" role="status">
          {formatMessage(locale, 'shell.commandLoading', {})}
        </p>
      )}
      {projectRead.error && (
        <p className="command-center-status" role="alert">
          {formatMessage(locale, 'shell.commandLoadFailed', {})}
        </p>
      )}
      {labels.loading && (
        <p className="command-center-status" role="status">
          {formatMessage(locale, 'shell.commandLabelsLoading', {})}
        </p>
      )}
      {labels.notice && (
        <p className="command-center-status" role="alert">
          {formatMessage(
            locale,
            labels.notice === 'conflict'
              ? 'shell.commandLabelsConflict'
              : labels.notice === 'invalid'
                ? 'shell.commandLabelsInvalid'
                : labels.notice === 'unavailable'
                  ? 'shell.commandLabelsUnavailable'
                  : 'shell.commandLabelsUncertain',
            {},
          )}
        </p>
      )}
      {!projectRead.loading && !projectRead.error && results.length === 0 && (
        <p className="command-center-status" role="status">
          {formatMessage(
            locale,
            workspaceId ? 'shell.commandEmptyWorkspace' : 'shell.commandEmpty',
            {},
          )}
        </p>
      )}
    </dialog>
  )
}
