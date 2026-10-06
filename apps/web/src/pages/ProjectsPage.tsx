import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  Boxes,
  Folder,
  GitBranch,
  GitFork,
  Plus,
  RefreshCw,
  Star,
} from 'lucide-react'

import { LocalizedApiError, OpaqueUserValue } from '../components/i18n'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import {
  useProjects,
  type ProjectJobPhase,
  type ProjectJobView,
} from '../features/projects/useProjects'
import { searchProjects } from '../features/projects/searchProjects'
import { useProjectFavorites } from '../features/projects/useProjectFavorites'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  currentLocale,
  formatMessage,
  type Locale,
  type MessageArguments,
  type ParameterFreeMessageKey,
} from '../i18n'
import type { ProjectData } from '../lib/contracts'

import './ProjectsPage.css'

type ProjectsMessageKey = Extract<ParameterFreeMessageKey, `projects.${string}`>

function copy(locale: Locale, key: ProjectsMessageKey): string {
  return formatMessage(locale, ...([key, {}] as MessageArguments))
}

function unknown(locale: Locale): string {
  return formatMessage(locale, 'common.unknown', {})
}

const PROJECT_STATE_COPY = {
  creating: 'projects.stateCreating',
  ready: 'projects.stateReady',
  error: 'projects.stateError',
  archived: 'projects.stateArchived',
} as const satisfies Record<ProjectData['state'], ProjectsMessageKey>

const CLAUDE_STATE_COPY = {
  running: 'projects.claudeRunning',
  stopped: 'projects.claudeStopped',
  starting: 'projects.claudeStarting',
  needs_interaction: 'projects.claudeNeedsInteraction',
  broken: 'projects.claudeBroken',
  unknown: 'projects.claudeUnknown',
} as const satisfies Record<
  Exclude<ProjectData['claude_state'], null>,
  ProjectsMessageKey
>

const JOB_STATUS_COPY = {
  queued: 'projects.jobQueued',
  running: 'projects.jobRunning',
  succeeded: 'projects.jobSucceeded',
  failed: 'projects.jobFailed',
  cancelled: 'projects.jobCancelled',
  needs_attention: 'projects.jobNeedsAttention',
} as const satisfies Record<ProjectJobView['status'], ProjectsMessageKey>

const JOB_PHASE_COPY = {
  queued: 'projects.phaseQueued',
  running: 'projects.phaseRunning',
  executing: 'projects.phaseExecuting',
  recovery_required: 'projects.phaseRecoveryRequired',
  succeeded: 'projects.phaseSucceeded',
  failed: 'projects.phaseFailed',
  cancelled: 'projects.phaseCancelled',
  needs_attention: 'projects.phaseNeedsAttention',
} as const satisfies Record<ProjectJobPhase, ProjectsMessageKey>

function JobStatus({ job, locale }: { job: ProjectJobView; locale: Locale }) {
  const failed = ['failed', 'needs_attention'].includes(job.status)
  return (
    <section className="runtime-card" role="status">
      <h2>{copy(locale, 'projects.operationTitle')}</h2>
      <p>
        {copy(locale, 'projects.jobLabel')}{' '}
        <SafeTechnicalValue fallback={unknown(locale)} value={job.id} /> ·{' '}
        {copy(locale, JOB_STATUS_COPY[job.status])}
      </p>
      <dl className="runtime-details compact-details">
        {job.phase && (
          <div>
            <dt>{copy(locale, 'projects.phaseLabel')}</dt>
            <dd>{copy(locale, JOB_PHASE_COPY[job.phase])}</dd>
          </div>
        )}
        {job.progress !== undefined && (
          <div>
            <dt>{copy(locale, 'projects.progressLabel')}</dt>
            <dd>
              {formatMessage(locale, 'projects.progressValue', {
                progress: String(job.progress),
              })}
            </dd>
          </div>
        )}
      </dl>
      {failed && (
        <p className="error-panel" role="alert">
          <LocalizedApiError
            error={{
              code: job.error_code ?? 'PROJECT_OPERATION_FAILED',
            }}
            locale={locale}
            role="presentation"
            showRequestId={false}
          />
        </p>
      )}
    </section>
  )
}

export function ProjectsPage({
  locale = currentLocale(),
}: {
  locale?: Locale
}) {
  const model = useProjects()
  const favorites = useProjectFavorites()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [cloneName, setCloneName] = useState('')
  const [nameInvalid, setNameInvalid] = useState(false)
  const [urlInvalid, setUrlInvalid] = useState(false)
  const [submission, setSubmission] = useState<'create' | 'clone' | null>(null)
  const [query, setQuery] = useState('')
  const [formMode, setFormMode] = useState<'create' | 'clone' | null>(null)
  const createTrigger = useRef<HTMLButtonElement>(null)
  const cloneTrigger = useRef<HTMLButtonElement>(null)
  const firstInput = useRef<HTMLInputElement>(null)
  const submissionLock = useRef(false)

  useEffect(() => {
    if (formMode) firstInput.current?.focus()
  }, [formMode])

  function clearDraft() {
    setName('')
    setUrl('')
    setCloneName('')
    setNameInvalid(false)
    setUrlInvalid(false)
  }

  function dismissForm() {
    if (submissionLock.current || model.pending) return
    clearDraft()
    setFormMode(null)
    const trigger = formMode === 'create' ? createTrigger : cloneTrigger
    trigger.current?.focus()
  }

  function openForm(mode: 'create' | 'clone') {
    if (submissionLock.current || model.pending) return
    if (mode === formMode) {
      dismissForm()
      return
    }
    clearDraft()
    setFormMode(mode)
  }
  const visibleProjects = useMemo(
    () => searchProjects(model.projects, query),
    [model.projects, query],
  )
  const orderedProjects = useMemo(() => {
    if (query.trim() || !favorites.loaded) return visibleProjects
    return [...visibleProjects].sort(
      (left, right) =>
        Number(Boolean(favorites.byProject[right.id]?.favorite)) -
        Number(Boolean(favorites.byProject[left.id]?.favorite)),
    )
  }, [favorites.byProject, favorites.loaded, query, visibleProjects])
  usePageTitle(copy(locale, 'projects.title'))

  async function create(event: FormEvent) {
    event.preventDefault()
    if (submissionLock.current || model.pending) return
    const projectName = name.trim()
    if (!projectName) {
      setNameInvalid(true)
      return
    }
    setNameInvalid(false)
    submissionLock.current = true
    setSubmission('create')
    try {
      await model.create(projectName)
      setName('')
    } finally {
      submissionLock.current = false
      setSubmission(null)
    }
  }

  async function clone(event: FormEvent) {
    event.preventDefault()
    if (submissionLock.current || model.pending) return
    const repositoryUrl = url.trim()
    if (!repositoryUrl) {
      setUrlInvalid(true)
      return
    }
    setUrlInvalid(false)
    submissionLock.current = true
    setSubmission('clone')
    try {
      await model.clone(repositoryUrl, cloneName.trim())
      setUrl('')
      setCloneName('')
    } finally {
      submissionLock.current = false
      setSubmission(null)
    }
  }

  return (
    <div className="projects-page">
      <PageHeader
        eyebrow={copy(locale, 'projects.eyebrow')}
        title={copy(locale, 'projects.title')}
        description={copy(locale, 'projects.description')}
        action={
          <div className="projects-page-actions">
            <button
              className="secondary-button"
              onClick={() => {
                void model.refresh()
                void favorites.refresh()
              }}
              type="button"
            >
              <RefreshCw aria-hidden="true" size={16} />{' '}
              {copy(locale, 'projects.refresh')}
            </button>
            <button
              aria-controls="project-entry-panel"
              aria-expanded={formMode === 'clone'}
              className="secondary-button"
              disabled={model.pending || submission !== null}
              onClick={() => openForm('clone')}
              ref={cloneTrigger}
              type="button"
            >
              <GitFork aria-hidden="true" size={16} />
              {copy(locale, 'projects.cloneRepository')}
            </button>
            <button
              aria-controls="project-entry-panel"
              aria-expanded={formMode === 'create'}
              className="primary-button"
              disabled={model.pending || submission !== null}
              onClick={() => openForm('create')}
              ref={createTrigger}
              type="button"
            >
              <Plus aria-hidden="true" size={16} />
              {copy(locale, 'projects.newProject')}
            </button>
          </div>
        }
      />
      {model.error && (
        <p className="error-panel">
          <LocalizedApiError error={model.error} locale={locale} />
        </p>
      )}
      {model.job && <JobStatus job={model.job} locale={locale} />}
      {favorites.error && (
        <p className="error-panel" role="alert">
          {copy(locale, 'projects.favoriteFailed')}{' '}
          <LocalizedApiError
            error={favorites.error}
            locale={locale}
            role="presentation"
          />
        </p>
      )}
      {favorites.notice && (
        <p className="interaction-notice" role="status">
          {copy(
            locale,
            favorites.notice.code === 'PROJECT_FAVORITE_CONFLICT'
              ? 'projects.favoriteConflict'
              : 'projects.favoriteUncertain',
          )}
        </p>
      )}
      <section
        aria-label={
          formMode === 'clone'
            ? copy(locale, 'projects.cloneRepository')
            : copy(locale, 'projects.newProject')
        }
        className="project-forms project-entry"
        hidden={formMode === null}
        id="project-entry-panel"
        onKeyDown={(event) => {
          if (
            event.key === 'Escape' &&
            !submissionLock.current &&
            !model.pending
          ) {
            event.preventDefault()
            event.stopPropagation()
            dismissForm()
          }
        }}
      >
        {formMode === 'create' && (
          <form className="runtime-card" noValidate onSubmit={create}>
            <p className="eyebrow">{copy(locale, 'projects.emptyWorkspace')}</p>
            <h2>{copy(locale, 'projects.newProject')}</h2>
            <p className="project-entry-description">
              {copy(locale, 'projects.creationBoundary')}
            </p>
            <label>
              {copy(locale, 'projects.projectName')}
              <input
                aria-describedby={
                  nameInvalid ? 'project-name-error' : undefined
                }
                aria-invalid={nameInvalid}
                disabled={model.pending || submission !== null}
                ref={firstInput}
                value={name}
                onChange={(event) => {
                  setName(event.target.value)
                  if (event.target.value.trim()) setNameInvalid(false)
                }}
                maxLength={128}
                required
              />
            </label>
            {nameInvalid && (
              <p className="error-panel" id="project-name-error" role="alert">
                {copy(locale, 'projects.projectNameValidation')}
              </p>
            )}
            <div className="project-entry-actions">
              <button
                className="primary-button"
                disabled={model.pending || submission !== null}
                type="submit"
              >
                {submission === 'create'
                  ? copy(locale, 'projects.creatingProject')
                  : copy(locale, 'projects.createProject')}
              </button>
              <button
                className="secondary-button"
                disabled={model.pending || submission !== null}
                onClick={dismissForm}
                type="button"
              >
                {copy(locale, 'projects.cancel')}
              </button>
            </div>
          </form>
        )}
        {formMode === 'clone' && (
          <form className="runtime-card" noValidate onSubmit={clone}>
            <p className="eyebrow">
              {copy(locale, 'projects.githubRepository')}
            </p>
            <h2>{copy(locale, 'projects.cloneRepository')}</h2>
            <p className="project-entry-description">
              {copy(locale, 'projects.creationBoundary')}
            </p>
            <label>
              {copy(locale, 'projects.repositoryUrl')}
              <input
                aria-describedby={
                  urlInvalid ? 'repository-url-error' : undefined
                }
                aria-invalid={urlInvalid}
                disabled={model.pending || submission !== null}
                ref={firstInput}
                value={url}
                onChange={(event) => {
                  setUrl(event.target.value)
                  if (event.target.value.trim()) setUrlInvalid(false)
                }}
                placeholder={copy(locale, 'projects.repositoryPlaceholder')}
                required
              />
            </label>
            {urlInvalid && (
              <p className="error-panel" id="repository-url-error" role="alert">
                {copy(locale, 'projects.cloneUrlValidation')}
              </p>
            )}
            <label>
              {copy(locale, 'projects.cloneProjectName')}
              <input
                disabled={model.pending || submission !== null}
                value={cloneName}
                onChange={(event) => setCloneName(event.target.value)}
              />
            </label>
            <div className="project-entry-actions">
              <button
                className="primary-button"
                disabled={model.pending || submission !== null}
                type="submit"
              >
                {submission === 'clone'
                  ? copy(locale, 'projects.cloning')
                  : copy(locale, 'projects.clone')}
              </button>
              <button
                className="secondary-button"
                disabled={model.pending || submission !== null}
                onClick={dismissForm}
                type="button"
              >
                {copy(locale, 'projects.cancel')}
              </button>
            </div>
          </form>
        )}
      </section>
      {(favorites.loading || favorites.stale) && model.projects.length > 0 && (
        <p role="status">
          {copy(
            locale,
            favorites.stale
              ? 'projects.favoriteStale'
              : 'projects.favoriteLoading',
          )}
        </p>
      )}
      {model.projects.length > 0 && (
        <div className="project-search">
          <label htmlFor="project-search-query">
            {copy(locale, 'projects.searchLabel')}
          </label>
          <div>
            <input
              autoComplete="off"
              id="project-search-query"
              maxLength={96}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={copy(locale, 'projects.searchPlaceholder')}
              type="search"
              value={query}
            />
            {query && (
              <button
                className="secondary-button"
                onClick={() => setQuery('')}
                type="button"
              >
                {copy(locale, 'projects.clearSearch')}
              </button>
            )}
          </div>
          {query.trim() && (
            <p role="status">
              {formatMessage(locale, 'projects.matchCount', {
                shown: String(visibleProjects.length),
                total: String(model.projects.length),
              })}
            </p>
          )}
        </div>
      )}
      {model.loading ? (
        <p className="loading-panel" role="status">
          {copy(locale, 'projects.loading')}
        </p>
      ) : model.projects.length === 0 ? (
        <section className="empty-state">
          <Boxes aria-hidden="true" />
          <h2>{copy(locale, 'projects.emptyTitle')}</h2>
          <p>{copy(locale, 'projects.emptyDescription')}</p>
        </section>
      ) : visibleProjects.length === 0 ? (
        <section className="empty-state" role="status">
          <h2>{copy(locale, 'projects.noMatchesTitle')}</h2>
          <p>{copy(locale, 'projects.noMatchesDescription')}</p>
        </section>
      ) : (
        <section
          className="project-grid"
          aria-label={copy(locale, 'projects.gridAria')}
        >
          {orderedProjects.map((project) => {
            const changes = project.git
              ? project.git.staged_count +
                project.git.unstaged_count +
                project.git.untracked_count +
                project.git.conflicted_count
              : 0
            const isFavorite = Boolean(
              favorites.byProject[project.id]?.favorite,
            )
            const saving = favorites.pending.has(project.id)
            return (
              <div className="project-card" key={project.id}>
                <Link
                  className="runtime-card project-link"
                  to={`/projects/${encodeURIComponent(project.id)}`}
                >
                  <div className="project-card-identity">
                    <span className="project-card-icon">
                      <Folder aria-hidden="true" size={21} />
                    </span>
                    <div>
                      <h2>
                        <OpaqueUserValue value={project.display_name} />
                      </h2>
                      <p className="project-card-source">
                        {copy(
                          locale,
                          project.source_type === 'git_clone'
                            ? 'projects.sourceCloned'
                            : 'projects.sourceWorkspace',
                        )}
                      </p>
                    </div>
                    <ArrowUpRight
                      aria-hidden="true"
                      className="project-open-icon"
                      size={17}
                    />
                  </div>
                  <div className="project-card-state">
                    <StatusBadge
                      tone={project.state === 'ready' ? 'good' : 'warning'}
                    >
                      {copy(locale, PROJECT_STATE_COPY[project.state])}
                    </StatusBadge>
                  </div>
                  <p className="project-card-slug">
                    {copy(locale, 'projects.slug')}{' '}
                    <OpaqueUserValue value={project.slug} />
                  </p>
                  <dl className="runtime-details compact-details project-card-metadata">
                    <div>
                      <dt>
                        <GitBranch aria-hidden="true" size={13} />
                        {copy(locale, 'projects.branch')}
                      </dt>
                      <dd>
                        {project.git?.branch !== null &&
                        project.git?.branch !== undefined ? (
                          <SafeTechnicalValue
                            fallback={unknown(locale)}
                            value={project.git.branch}
                          />
                        ) : (
                          copy(locale, 'projects.notInitialized')
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>{copy(locale, 'projects.changes')}</dt>
                      <dd>{changes}</dd>
                    </div>
                    <div>
                      <dt>{copy(locale, 'projects.remote')}</dt>
                      <dd>
                        {project.git?.remote_url !== null &&
                        project.git?.remote_url !== undefined ? (
                          <SafeTechnicalValue
                            fallback={unknown(locale)}
                            value={project.git.remote_url}
                          />
                        ) : (
                          copy(locale, 'projects.none')
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>{copy(locale, 'projects.claude')}</dt>
                      <dd>
                        {copy(
                          locale,
                          project.claude_state
                            ? CLAUDE_STATE_COPY[project.claude_state]
                            : 'projects.claudeUnknown',
                        )}
                      </dd>
                    </div>
                  </dl>
                </Link>
                <button
                  aria-label={`${copy(locale, isFavorite ? 'projects.removeFavorite' : 'projects.addFavorite')}: ${project.display_name}`}
                  aria-pressed={isFavorite}
                  className="secondary-button project-favorite"
                  disabled={
                    !favorites.loaded ||
                    favorites.loading ||
                    favorites.stale ||
                    saving
                  }
                  onClick={() => void favorites.setFavorite(project.id)}
                  type="button"
                >
                  <Star
                    aria-hidden="true"
                    fill={isFavorite ? 'currentColor' : 'none'}
                    size={16}
                  />{' '}
                  {copy(
                    locale,
                    saving
                      ? 'projects.favoriteSaving'
                      : isFavorite
                        ? 'projects.removeFavorite'
                        : 'projects.addFavorite',
                  )}
                </button>
              </div>
            )
          })}
        </section>
      )}
    </div>
  )
}
