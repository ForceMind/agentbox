import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { Boxes, RefreshCw } from 'lucide-react'

import { LocalizedApiError, OpaqueUserValue } from '../components/i18n'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import {
  useProjects,
  type ProjectJobPhase,
  type ProjectJobView,
} from '../features/projects/useProjects'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  currentLocale,
  formatMessage,
  type Locale,
  type MessageArguments,
  type ParameterFreeMessageKey,
} from '../i18n'
import type { ProjectData } from '../lib/contracts'

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
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [cloneName, setCloneName] = useState('')
  const [nameInvalid, setNameInvalid] = useState(false)
  const [urlInvalid, setUrlInvalid] = useState(false)
  const [submission, setSubmission] = useState<'create' | 'clone' | null>(null)
  usePageTitle(copy(locale, 'projects.title'))

  async function create(event: FormEvent) {
    event.preventDefault()
    const projectName = name.trim()
    if (!projectName) {
      setNameInvalid(true)
      return
    }
    setNameInvalid(false)
    setSubmission('create')
    try {
      await model.create(projectName)
      setName('')
    } finally {
      setSubmission(null)
    }
  }

  async function clone(event: FormEvent) {
    event.preventDefault()
    const repositoryUrl = url.trim()
    if (!repositoryUrl) {
      setUrlInvalid(true)
      return
    }
    setUrlInvalid(false)
    setSubmission('clone')
    try {
      await model.clone(repositoryUrl, cloneName.trim())
      setUrl('')
    } finally {
      setSubmission(null)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={copy(locale, 'projects.eyebrow')}
        title={copy(locale, 'projects.title')}
        description={copy(locale, 'projects.description')}
        action={
          <button
            className="secondary-button"
            onClick={() => void model.refresh()}
            type="button"
          >
            <RefreshCw aria-hidden="true" size={16} />{' '}
            {copy(locale, 'projects.refresh')}
          </button>
        }
      />
      {model.error && (
        <p className="error-panel">
          <LocalizedApiError error={model.error} locale={locale} />
        </p>
      )}
      {model.job && <JobStatus job={model.job} locale={locale} />}
      <section className="project-forms">
        <form className="runtime-card" noValidate onSubmit={create}>
          <p className="eyebrow">{copy(locale, 'projects.emptyWorkspace')}</p>
          <h2>{copy(locale, 'projects.newProject')}</h2>
          <label>
            {copy(locale, 'projects.projectName')}
            <input
              aria-describedby={nameInvalid ? 'project-name-error' : undefined}
              aria-invalid={nameInvalid}
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
          <button
            className="primary-button"
            disabled={model.pending || submission !== null}
            type="submit"
          >
            {submission === 'create'
              ? copy(locale, 'projects.creatingProject')
              : copy(locale, 'projects.createProject')}
          </button>
        </form>
        <form className="runtime-card" noValidate onSubmit={clone}>
          <p className="eyebrow">{copy(locale, 'projects.githubRepository')}</p>
          <h2>{copy(locale, 'projects.cloneRepository')}</h2>
          <label>
            {copy(locale, 'projects.repositoryUrl')}
            <input
              aria-describedby={urlInvalid ? 'repository-url-error' : undefined}
              aria-invalid={urlInvalid}
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
              value={cloneName}
              onChange={(event) => setCloneName(event.target.value)}
            />
          </label>
          <button
            className="primary-button"
            disabled={model.pending || submission !== null}
            type="submit"
          >
            {submission === 'clone'
              ? copy(locale, 'projects.cloning')
              : copy(locale, 'projects.clone')}
          </button>
        </form>
      </section>
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
      ) : (
        <section
          className="project-grid"
          aria-label={copy(locale, 'projects.gridAria')}
        >
          {model.projects.map((project) => {
            const changes = project.git
              ? project.git.staged_count +
                project.git.unstaged_count +
                project.git.untracked_count +
                project.git.conflicted_count
              : 0
            return (
              <Link
                className="runtime-card project-link"
                key={project.id}
                to={`/projects/${encodeURIComponent(project.id)}`}
              >
                <div className="runtime-card-heading">
                  <h2>
                    <OpaqueUserValue value={project.display_name} />
                  </h2>
                  <StatusBadge
                    tone={project.state === 'ready' ? 'good' : 'warning'}
                  >
                    {copy(locale, PROJECT_STATE_COPY[project.state])}
                  </StatusBadge>
                </div>
                <p>
                  {copy(
                    locale,
                    project.source_type === 'git_clone'
                      ? 'projects.sourceCloned'
                      : 'projects.sourceWorkspace',
                  )}
                </p>
                <dl className="runtime-details compact-details">
                  <div>
                    <dt>{copy(locale, 'projects.branch')}</dt>
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
            )
          })}
        </section>
      )}
    </>
  )
}
