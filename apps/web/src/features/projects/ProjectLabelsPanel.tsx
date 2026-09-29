import { type FormEvent, useEffect, useRef, useState } from 'react'

import { LocalizedApiError, OpaqueUserValue } from '../../components/i18n'
import {
  formatMessage,
  type Locale,
  type MessageArguments,
  type ParameterFreeMessageKey,
} from '../../i18n'
import {
  NAVIGATION_LABEL_COLORS,
  type NavigationLabelColor,
  type NavigationLabelData,
} from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'
import { useProjectLabels } from './useProjectLabels'

import './ProjectLabelsPanel.css'

type FreeLabelKey = Extract<ParameterFreeMessageKey, `project.labels${string}`>

function copy(locale: Locale, key: FreeLabelKey): string {
  return formatMessage(locale, ...([key, {}] as MessageArguments))
}

const COLOR_KEYS = {
  violet: 'project.labelsColorViolet',
  sky: 'project.labelsColorSky',
  emerald: 'project.labelsColorEmerald',
  orange: 'project.labelsColorOrange',
  pink: 'project.labelsColorPink',
  indigo: 'project.labelsColorIndigo',
  teal: 'project.labelsColorTeal',
  red: 'project.labelsColorRed',
  amber: 'project.labelsColorAmber',
  blue: 'project.labelsColorBlue',
} as const satisfies Record<NavigationLabelColor, FreeLabelKey>

function LabelChip({ value }: { value: NavigationLabelData }) {
  return (
    <span className="project-label-chip">
      <span
        aria-hidden="true"
        className="project-label-dot"
        data-color={value.color}
      />
      <OpaqueUserValue value={value.name} />
    </span>
  )
}

function LabelManager({
  labels,
  locale,
  onClose,
}: {
  labels: ReturnType<typeof useProjectLabels>
  locale: Locale
  onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const [name, setName] = useState('')
  const [color, setColor] = useState<NavigationLabelColor>('sky')
  const [editing, setEditing] = useState<NavigationLabelData | null>(null)
  const [editName, setEditName] = useState('')
  const [editColor, setEditColor] = useState<NavigationLabelColor>('sky')
  const [deleteImpact, setDeleteImpact] = useState<number | null>(null)
  const assigned = new Set(labels.assignment?.labels.map((label) => label.id))
  const editorStale =
    editing !== null &&
    labels.catalog.find((current) => current.id === editing.id)?.revision !==
      editing.revision

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (typeof element.showModal === 'function') element.showModal()
    else element.setAttribute('open', '')
    closeButton.current?.focus()
    return () => {
      if (typeof element.close === 'function' && element.open) element.close()
      else element.removeAttribute('open')
    }
  }, [])

  async function create(event: FormEvent) {
    event.preventDefault()
    if (await labels.create(name, color)) setName('')
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!editing || editorStale) return
    if (await labels.update(editing, editName, editColor)) {
      setEditing(null)
      setDeleteImpact(null)
    }
  }

  async function inspectDelete() {
    if (!editing || editorStale) return
    setDeleteImpact(await labels.inspectDelete(editing.id))
  }

  async function remove() {
    if (!editing || editorStale || deleteImpact === null) return
    const accepted = await labels.remove(editing, deleteImpact)
    setDeleteImpact(null)
    if (accepted) setEditing(null)
  }

  return (
    <dialog
      aria-label={copy(locale, 'project.labelsManage')}
      aria-modal="true"
      className="project-label-dialog"
      onCancel={(event) => {
        event.preventDefault()
        if (!labels.pending) onClose()
      }}
      ref={dialog}
    >
      <div className="runtime-card-heading">
        <h2>{copy(locale, 'project.labelsManage')}</h2>
        <button
          aria-label={copy(locale, 'project.labelsClose')}
          className="icon-button"
          disabled={labels.pending}
          onClick={onClose}
          ref={closeButton}
          type="button"
        >
          ×
        </button>
      </div>
      {labels.loading ? (
        <p className="loading-panel" role="status">
          {copy(locale, 'project.labelsLoading')}
        </p>
      ) : !labels.loaded || labels.stale ? (
        <p className="interaction-notice" role="status">
          {copy(locale, 'project.labelsUnavailable')}
        </p>
      ) : (
        <>
          <div className="project-label-options">
            {labels.catalog.map((label) => (
              <div className="project-label-option" key={label.id}>
                <label>
                  <input
                    checked={assigned.has(label.id)}
                    disabled={labels.pending || editorStale}
                    onChange={() => void labels.setAssignment(label.id)}
                    type="checkbox"
                  />
                  <LabelChip value={label} />
                </label>
                <button
                  aria-label={`${copy(locale, 'project.labelsEdit')}: ${label.name}`}
                  className="secondary-button"
                  disabled={labels.pending}
                  onClick={() => {
                    setEditing({ ...label })
                    setEditName(label.name)
                    setEditColor(label.color)
                    setDeleteImpact(null)
                  }}
                  type="button"
                >
                  {copy(locale, 'project.labelsEdit')}
                </button>
              </div>
            ))}
          </div>
          {labels.catalog.length === 0 && (
            <p>{copy(locale, 'project.labelsCatalogEmpty')}</p>
          )}
          <form
            className="project-label-form"
            onSubmit={(event) => void create(event)}
          >
            <label>
              {copy(locale, 'project.labelsName')}
              <input
                maxLength={64}
                onChange={(event) => setName(event.target.value)}
                value={name}
              />
            </label>
            <label>
              {copy(locale, 'project.labelsColor')}
              <select
                onChange={(event) =>
                  setColor(event.target.value as NavigationLabelColor)
                }
                value={color}
              >
                {NAVIGATION_LABEL_COLORS.map((option) => (
                  <option key={option} value={option}>
                    {copy(locale, COLOR_KEYS[option])}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary-button"
              disabled={labels.pending || !name.trim()}
              type="submit"
            >
              {copy(locale, 'project.labelsCreate')}
            </button>
          </form>
          {editing && (
            <form
              className="project-label-form"
              onSubmit={(event) => void save(event)}
            >
              <h3>{copy(locale, 'project.labelsEdit')}</h3>
              <label>
                {copy(locale, 'project.labelsName')}
                <input
                  maxLength={64}
                  onChange={(event) => {
                    setEditName(event.target.value)
                    setDeleteImpact(null)
                  }}
                  value={editName}
                />
              </label>
              <label>
                {copy(locale, 'project.labelsColor')}
                <select
                  onChange={(event) => {
                    setEditColor(event.target.value as NavigationLabelColor)
                    setDeleteImpact(null)
                  }}
                  value={editColor}
                >
                  {NAVIGATION_LABEL_COLORS.map((option) => (
                    <option key={option} value={option}>
                      {copy(locale, COLOR_KEYS[option])}
                    </option>
                  ))}
                </select>
              </label>
              {editorStale && (
                <p className="interaction-notice" role="status">
                  {copy(locale, 'project.labelsConflict')}
                </p>
              )}
              <div className="action-row">
                <button
                  className="secondary-button"
                  disabled={
                    labels.pending ||
                    editorStale ||
                    !editName.trim() ||
                    (editName.trim() === editing.name &&
                      editColor === editing.color)
                  }
                  type="submit"
                >
                  {copy(locale, 'project.labelsSave')}
                </button>
                <button
                  className="secondary-button"
                  disabled={labels.pending || editorStale}
                  onClick={() => void inspectDelete()}
                  type="button"
                >
                  {copy(locale, 'project.labelsDelete')}
                </button>
              </div>
              {deleteImpact !== null && (
                <div className="project-label-delete-confirm" role="group">
                  <p>
                    {formatMessage(locale, 'project.labelsDeleteConfirm', {
                      count: String(deleteImpact),
                    })}
                  </p>
                  <button
                    className="secondary-button"
                    disabled={labels.pending || editorStale}
                    onClick={() => void remove()}
                    type="button"
                  >
                    {copy(locale, 'project.labelsDelete')}
                  </button>
                  <button
                    className="secondary-button"
                    disabled={labels.pending}
                    onClick={() => setDeleteImpact(null)}
                    type="button"
                  >
                    {copy(locale, 'project.labelsDeleteCancel')}
                  </button>
                </div>
              )}
            </form>
          )}
        </>
      )}
    </dialog>
  )
}

export function ProjectLabelsPanel({
  projectId,
  locale,
}: {
  projectId: string
  locale: Locale
}) {
  const labels = useProjectLabels(projectId)
  const { auth } = useAuth()
  const scope = auth?.session.id ?? null
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)

  useEffect(() => setOpen(false), [projectId, scope])

  function close() {
    setOpen(false)
    window.setTimeout(() => {
      if (trigger.current?.isConnected) trigger.current.focus()
    }, 0)
  }

  const conflict =
    labels.notice?.code === 'NAVIGATION_LABEL_CONFLICT' ||
    labels.notice?.code === 'NAVIGATION_LABEL_NAME_TAKEN' ||
    labels.notice?.code === 'PROJECT_LABEL_CONFLICT'

  return (
    <section className="runtime-card project-label-panel">
      <div className="runtime-card-heading">
        <h2>{copy(locale, 'project.labelsTitle')}</h2>
        <button
          className="secondary-button"
          disabled={!labels.loaded || labels.stale || labels.pending}
          onClick={() => {
            setOpen(true)
            void labels.refresh()
          }}
          ref={trigger}
          type="button"
        >
          {copy(locale, 'project.labelsManage')}
        </button>
      </div>
      <p>{copy(locale, 'project.labelsDescription')}</p>
      {labels.loading && (
        <p className="loading-panel" role="status">
          {copy(locale, 'project.labelsLoading')}
        </p>
      )}
      {labels.error && (
        <p className="error-panel" role="alert">
          {copy(locale, 'project.labelsUnavailable')}{' '}
          <LocalizedApiError
            error={labels.error}
            locale={locale}
            role="presentation"
          />
          <button
            className="secondary-button"
            onClick={() => void labels.refresh()}
            type="button"
          >
            {copy(locale, 'project.labelsRefresh')}
          </button>
        </p>
      )}
      {labels.notice && (
        <p className="interaction-notice" role="status">
          {copy(
            locale,
            conflict ? 'project.labelsConflict' : 'project.labelsUncertain',
          )}
        </p>
      )}
      {labels.loaded && (
        <div className="project-label-chips">
          {labels.assignment?.labels.length ? (
            labels.assignment.labels.map((label) => (
              <LabelChip key={label.id} value={label} />
            ))
          ) : (
            <p>{copy(locale, 'project.labelsEmpty')}</p>
          )}
        </div>
      )}
      {open && <LabelManager labels={labels} locale={locale} onClose={close} />}
    </section>
  )
}
