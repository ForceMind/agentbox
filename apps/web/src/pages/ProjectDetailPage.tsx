import {
  ArrowLeft,
  ArrowUpRight,
  GitBranch,
  GitPullRequest,
  RefreshCw,
  Terminal,
} from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { LocalizedApiError, OpaqueUserValue } from '../components/i18n'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { StatusBadge } from '../components/StatusBadge'
import { useAuth } from '../features/auth/AuthContext'
import {
  useClaudeProject,
  type ClaudeSessionView,
} from '../features/claude/useClaude'
import {
  useProject,
  type ProjectJobPhase,
  type ProjectJobView,
} from '../features/projects/useProjects'
import { ProjectLabelsPanel } from '../features/projects/ProjectLabelsPanel'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  currentLocale,
  formatMessage,
  type Locale,
  type MessageArguments,
  type ParameterFreeMessageKey,
} from '../i18n'
import type { ProjectData } from '../lib/contracts'
import './ProjectDetailPage.css'

type ProjectMessageKey = Extract<ParameterFreeMessageKey, `project.${string}`>

function copy(locale: Locale, key: ProjectMessageKey): string {
  return formatMessage(locale, ...([key, {}] as MessageArguments))
}

const PROJECT_STATE_COPY = {
  creating: 'project.stateCreating',
  ready: 'project.stateReady',
  error: 'project.stateError',
  archived: 'project.stateArchived',
} as const satisfies Record<ProjectData['state'], ProjectMessageKey>

const PROJECT_SOURCE_COPY = {
  empty: 'project.sourceEmpty',
  git_clone: 'project.sourceGitClone',
  existing: 'project.sourceExisting',
} as const satisfies Record<ProjectData['source_type'], ProjectMessageKey>

const CHECKS_COPY = {
  pass: 'project.checksPass',
  fail: 'project.checksFail',
  pending: 'project.checksPending',
  unknown: 'project.checksUnknown',
} as const satisfies Record<
  NonNullable<ProjectData['github']>['checks'],
  ProjectMessageKey
>

const CLAUDE_STATE_COPY = {
  running: 'project.claudeRunning',
  stopped: 'project.claudeStopped',
  starting: 'project.claudeStarting',
  needs_interaction: 'project.claudeNeedsInteraction',
  broken: 'project.claudeBroken',
  unknown: 'project.claudeUnknown',
} as const satisfies Record<ClaudeSessionView['state'], ProjectMessageKey>

const JOB_STATUS_COPY = {
  queued: 'project.jobQueued',
  running: 'project.jobRunning',
  succeeded: 'project.jobSucceeded',
  failed: 'project.jobFailed',
  cancelled: 'project.jobCancelled',
  needs_attention: 'project.jobNeedsAttention',
} as const satisfies Record<ProjectJobView['status'], ProjectMessageKey>

const JOB_PHASE_COPY = {
  queued: 'project.phaseQueued',
  running: 'project.phaseRunning',
  executing: 'project.phaseExecuting',
  recovery_required: 'project.phaseRecoveryRequired',
  succeeded: 'project.phaseSucceeded',
  failed: 'project.phaseFailed',
  cancelled: 'project.phaseCancelled',
  needs_attention: 'project.phaseNeedsAttention',
} as const satisfies Record<ProjectJobPhase, ProjectMessageKey>

function pullRequestStateCopy(value: string | null): ProjectMessageKey {
  switch (value) {
    case 'open':
      return 'project.prStateOpen'
    case 'closed':
      return 'project.prStateClosed'
    case 'merged':
      return 'project.prStateMerged'
    default:
      return 'project.unknown'
  }
}

function mergeabilityCopy(value: string | null): ProjectMessageKey {
  switch (value) {
    case 'behind':
      return 'project.mergeabilityBehind'
    case 'blocked':
      return 'project.mergeabilityBlocked'
    case 'clean':
      return 'project.mergeabilityClean'
    case 'dirty':
      return 'project.mergeabilityDirty'
    case 'draft':
      return 'project.mergeabilityDraft'
    case 'has_hooks':
      return 'project.mergeabilityHasHooks'
    case 'unstable':
      return 'project.mergeabilityUnstable'
    default:
      return 'project.unknown'
  }
}

function LatestJob({ job, locale }: { job: ProjectJobView; locale: Locale }) {
  const failed = ['failed', 'needs_attention'].includes(job.status)
  return (
    <section className="runtime-card" role="status">
      <h2>{copy(locale, 'project.latestOperation')}</h2>
      <p>
        {copy(locale, 'project.jobLabel')}{' '}
        <SafeTechnicalValue
          fallback={copy(locale, 'project.unknown')}
          value={job.id}
        />{' '}
        · {copy(locale, JOB_STATUS_COPY[job.status])}
      </p>
      <dl className="runtime-details compact-details">
        {job.phase && (
          <div>
            <dt>{copy(locale, 'project.phaseLabel')}</dt>
            <dd>{copy(locale, JOB_PHASE_COPY[job.phase])}</dd>
          </div>
        )}
        {job.progress !== undefined && (
          <div>
            <dt>{copy(locale, 'project.progressLabel')}</dt>
            <dd>
              {formatMessage(locale, 'project.progressValue', {
                progress: String(job.progress),
              })}
            </dd>
          </div>
        )}
      </dl>
      {failed && (
        <p className="error-panel" role="alert">
          <LocalizedApiError
            error={{ code: job.error_code ?? 'PROJECT_OPERATION_FAILED' }}
            locale={locale}
            role="presentation"
            showRequestId={false}
          />
        </p>
      )}
    </section>
  )
}

export function ProjectDetailPage({
  locale = currentLocale(),
}: {
  locale?: Locale
}) {
  const { projectId } = useParams()
  const { auth, status } = useAuth()
  // Keep observation owners mounted so a session/route change cannot reset a
  // pagehide or freeze fence before the matching browser resume event.
  const model = useProject(projectId)
  const claude = useClaudeProject(
    model.project?.state === 'ready' ? projectId : undefined,
  )
  // A different Project or administrator session owns a new, empty set of drafts.
  const owner = JSON.stringify([
    projectId,
    status,
    auth?.user.id,
    auth?.session.id,
  ])
  return (
    <OwnedProjectDetail
      key={owner}
      locale={locale}
      model={model}
      claude={claude}
    />
  )
}

function OwnedProjectDetail({
  locale,
  model,
  claude,
}: {
  locale: Locale
  model: ReturnType<typeof useProject>
  claude: ReturnType<typeof useClaudeProject>
}) {
  const [branch, setBranch] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [base, setBase] = useState('')
  const [form, setForm] = useState<'branch' | 'pr' | null>(null)
  const branchTrigger = useRef<HTMLButtonElement>(null)
  const prTrigger = useRef<HTMLButtonElement>(null)
  const firstInput = useRef<HTMLInputElement>(null)
  usePageTitle(model.project?.display_name ?? copy(locale, 'project.title'))

  function clearDrafts() {
    setForm(null)
    setBranch('')
    setTitle('')
    setBody('')
    setBase('')
  }

  function closeForm() {
    const trigger = form === 'branch' ? branchTrigger : prTrigger
    clearDrafts()
    trigger.current?.focus()
  }

  function openForm(next: 'branch' | 'pr') {
    clearDrafts()
    setForm(next)
  }

  useEffect(() => {
    if (form) firstInput.current?.focus()
  }, [form])
  useEffect(() => {
    const hide = () => {
      if (document.visibilityState === 'hidden') clearDrafts()
    }
    document.addEventListener('visibilitychange', hide)
    document.addEventListener('freeze', clearDrafts)
    window.addEventListener('pagehide', clearDrafts)
    window.addEventListener('offline', clearDrafts)
    return () => {
      document.removeEventListener('visibilitychange', hide)
      document.removeEventListener('freeze', clearDrafts)
      window.removeEventListener('pagehide', clearDrafts)
      window.removeEventListener('offline', clearDrafts)
    }
  }, [])

  const pageNavigation = (
    <div className="project-detail-navigation">
      <Link className="back-link secondary-button project-back" to="/projects">
        <ArrowLeft aria-hidden="true" size={16} />
        {copy(locale, 'project.backToProjects')}
      </Link>
      <button
        className="secondary-button"
        disabled={
          model.phase === 'loading' ||
          model.phase === 'stale' ||
          model.phase === 'forbidden' ||
          model.pending !== null
        }
        onClick={() => {
          clearDrafts()
          void model.refresh()
        }}
        type="button"
      >
        <RefreshCw aria-hidden="true" size={16} />
        {copy(locale, 'project.refresh')}
      </button>
    </div>
  )

  if (!model.project) {
    return (
      <div className="project-detail-page">
        {pageNavigation}
        {model.error ? (
          <section className="error-panel" role="alert">
            <h1>{copy(locale, 'project.unavailableTitle')}</h1>
            {model.phase === 'forbidden' && (
              <p>{copy(locale, 'project.forbidden')}</p>
            )}
            <LocalizedApiError
              error={model.error}
              locale={locale}
              role="presentation"
            />
          </section>
        ) : (
          <p
            className="runtime-card"
            role={model.phase === 'forbidden' ? 'alert' : 'status'}
          >
            {copy(
              locale,
              model.phase === 'stale'
                ? 'project.stale'
                : model.phase === 'forbidden'
                  ? 'project.forbidden'
                  : 'project.loading',
            )}
          </p>
        )}
      </div>
    )
  }

  const project = model.project
  const git = project.git
  const ready = project.state === 'ready' && model.phase === 'ready'
  const gitEnabled = ready && !!git?.is_repository && !model.busy
  const prEnabled = ready && !!project.github?.available && !model.busy
  const changes = git
    ? git.staged_count +
      git.unstaged_count +
      git.untracked_count +
      git.conflicted_count
    : 0
  const branchName = git?.detached_head ? (
    copy(locale, 'project.detachedHead')
  ) : git?.branch !== null && git?.branch !== undefined ? (
    <SafeTechnicalValue
      fallback={copy(locale, 'project.unknown')}
      value={git.branch}
    />
  ) : (
    copy(
      locale,
      git?.unborn_branch ? 'project.unbornBranch' : 'project.unknown',
    )
  )

  function createBranch(event: FormEvent) {
    event.preventDefault()
    if (gitEnabled && branch.trim())
      void model.mutate('git/branches', { branch: branch.trim() })
  }

  function draftPr(event: FormEvent) {
    event.preventDefault()
    if (prEnabled && title.trim())
      void model.mutate('github/pull-requests', {
        title,
        body,
        base: base || null,
      })
  }

  return (
    <div className="project-detail-page">
      {pageNavigation}
      <header className="page-header project-detail-header">
        <div>
          <p className="eyebrow">{copy(locale, 'project.eyebrow')}</p>
          <h1>
            <OpaqueUserValue value={project.display_name} />
          </h1>
          <p className="page-description">
            {copy(locale, 'project.description')}
          </p>
          <div className="project-summary-meta">
            <StatusBadge tone={project.state === 'ready' ? 'good' : 'warning'}>
              {copy(locale, PROJECT_STATE_COPY[project.state])}
            </StatusBadge>
            <span>
              {copy(locale, PROJECT_SOURCE_COPY[project.source_type])}
            </span>
          </div>
        </div>
        <div className="project-primary-actions">
          {ready && (
            <Link
              className="primary-button"
              to={`/workspace?project_id=${encodeURIComponent(project.id)}`}
            >
              <Terminal aria-hidden="true" size={18} />
              {copy(locale, 'project.openWorkspace')}
              <ArrowUpRight aria-hidden="true" size={16} />
            </Link>
          )}
          {ready && git?.is_repository && (
            <Link
              className="secondary-button"
              to={`/projects/${encodeURIComponent(project.id)}/changes`}
            >
              {copy(locale, 'project.openChanges')}
              <ArrowUpRight aria-hidden="true" size={16} />
            </Link>
          )}
        </div>
      </header>
      {model.error && (
        <p className="error-panel">
          <LocalizedApiError error={model.error} locale={locale} />
        </p>
      )}
      {model.job && <LatestJob job={model.job} locale={locale} />}
      <div className="project-detail-columns">
        <div className="project-detail-main">
          <section
            className="runtime-card project-git-card"
            aria-labelledby="project-git-title"
          >
            <div className="runtime-card-heading">
              <h2 id="project-git-title">
                <GitBranch aria-hidden="true" size={19} />
                {copy(locale, 'project.git')}
              </h2>
              <StatusBadge tone={git?.clean ? 'good' : 'warning'}>
                {git?.is_repository
                  ? git.clean
                    ? copy(locale, 'project.gitClean')
                    : formatMessage(locale, 'project.gitChanges', {
                        count: String(changes),
                      })
                  : copy(
                      locale,
                      git ? 'project.notInitialized' : 'project.unknown',
                    )}
              </StatusBadge>
            </div>
            {git?.is_repository && (
              <dl className="project-git-summary">
                <div>
                  <dt>{copy(locale, 'project.branch')}</dt>
                  <dd>{branchName}</dd>
                </div>
                <div>
                  <dt>{copy(locale, 'project.aheadBehind')}</dt>
                  <dd>
                    {git.ahead} / {git.behind}
                  </dd>
                </div>
              </dl>
            )}
            <p className="project-section-description">
              {copy(locale, 'project.gitActionsDescription')}
            </p>
            <div
              className="project-action-row"
              aria-label={copy(locale, 'project.gitActionsTitle')}
            >
              <button
                className="secondary-button"
                disabled={!gitEnabled}
                onClick={() => void model.mutate('git/pull')}
                type="button"
              >
                {copy(
                  locale,
                  model.pending === 'git/pull'
                    ? 'project.pulling'
                    : 'project.pull',
                )}
              </button>
              <button
                className="secondary-button"
                disabled={!gitEnabled}
                onClick={() => void model.mutate('git/push')}
                type="button"
              >
                {copy(
                  locale,
                  model.pending === 'git/push'
                    ? 'project.pushing'
                    : 'project.push',
                )}
              </button>
              <button
                ref={branchTrigger}
                className="secondary-button"
                disabled={!ready || !git?.is_repository}
                aria-expanded={form === 'branch'}
                aria-controls="project-branch-form"
                onClick={() =>
                  form === 'branch' ? closeForm() : openForm('branch')
                }
                type="button"
              >
                <GitBranch aria-hidden="true" size={16} />
                {copy(locale, 'project.manageBranches')}
              </button>
            </div>
            {form === 'branch' && (
              <form
                id="project-branch-form"
                className="project-action-form"
                aria-label={copy(locale, 'project.manageBranches')}
                onSubmit={createBranch}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault()
                    event.stopPropagation()
                    closeForm()
                  }
                }}
              >
                <label htmlFor="project-branch-name">
                  {copy(locale, 'project.branchName')}
                </label>
                <input
                  id="project-branch-name"
                  ref={firstInput}
                  value={branch}
                  onChange={(event) => setBranch(event.target.value)}
                  placeholder={copy(locale, 'project.branchPlaceholder')}
                  disabled={!gitEnabled}
                />
                {model.branches.length > 0 && (
                  <div
                    className="branch-list"
                    aria-label={copy(locale, 'project.localBranches')}
                  >
                    {model.branches.map((item) => (
                      <button
                        className="secondary-button"
                        disabled={!gitEnabled}
                        key={item.name}
                        onClick={() => setBranch(item.name)}
                        type="button"
                      >
                        {item.current &&
                          `${copy(locale, 'project.currentBranch')} · `}
                        <SafeTechnicalValue
                          fallback={copy(locale, 'project.unknown')}
                          value={item.name}
                        />
                      </button>
                    ))}
                  </div>
                )}
                <div className="project-action-row">
                  <button
                    className="primary-button"
                    disabled={!gitEnabled || !branch.trim()}
                    type="submit"
                  >
                    {copy(
                      locale,
                      model.pending === 'git/branches'
                        ? 'project.creatingBranch'
                        : 'project.createBranch',
                    )}
                  </button>
                  <button
                    className="secondary-button"
                    disabled={!gitEnabled || !branch.trim()}
                    onClick={() =>
                      void model.mutate('git/switch', { branch: branch.trim() })
                    }
                    type="button"
                  >
                    {copy(
                      locale,
                      model.pending === 'git/switch'
                        ? 'project.switchingBranch'
                        : 'project.switchBranch',
                    )}
                  </button>
                  <button
                    className="secondary-button"
                    onClick={closeForm}
                    type="button"
                  >
                    {copy(locale, 'project.cancel')}
                  </button>
                </div>
                <p className="project-form-note">
                  {copy(locale, 'project.cancelHint')}
                </p>
              </form>
            )}
            <details className="project-technical-details">
              <summary>{copy(locale, 'project.gitDetails')}</summary>
              <dl className="runtime-details">
                <div>
                  <dt>{copy(locale, 'project.remote')}</dt>
                  <dd>
                    {git?.remote_url ? (
                      <SafeTechnicalValue
                        fallback={copy(locale, 'project.unknown')}
                        value={git.remote_url}
                      />
                    ) : (
                      copy(locale, 'project.none')
                    )}
                  </dd>
                </div>
                {git?.is_repository && (
                  <>
                    <div>
                      <dt>{copy(locale, 'project.stagedUnstaged')}</dt>
                      <dd>
                        {git.staged_count} / {git.unstaged_count}
                      </dd>
                    </div>
                    <div>
                      <dt>{copy(locale, 'project.untrackedConflicted')}</dt>
                      <dd>
                        {git.untracked_count} / {git.conflicted_count}
                      </dd>
                    </div>
                  </>
                )}
              </dl>
              {git?.submodules_detected && (
                <p className="interaction-notice">
                  {copy(locale, 'project.submodulesDetected')}
                </p>
              )}
            </details>
          </section>
          <section
            className="runtime-card project-github-card"
            aria-labelledby="project-github-title"
          >
            <div className="runtime-card-heading">
              <h2 id="project-github-title">
                <GitPullRequest aria-hidden="true" size={19} />
                {copy(locale, 'project.github')}
              </h2>
              {project.github?.available && (
                <StatusBadge
                  tone={project.github.checks === 'pass' ? 'good' : 'muted'}
                >
                  {copy(locale, 'project.checks')} ·{' '}
                  {copy(locale, CHECKS_COPY[project.github.checks])}
                </StatusBadge>
              )}
            </div>
            <p className="project-section-description">
              {project.github?.available ? (
                <SafeTechnicalValue
                  fallback={copy(locale, 'project.unknown')}
                  value={project.github.repository}
                />
              ) : (
                copy(locale, 'project.githubUnavailable')
              )}
            </p>
            {project.github?.pull_request_number && (
              <div className="project-pull-request">
                <p className="project-pr-title">
                  #{project.github.pull_request_number}{' '}
                  {project.github.pull_request_title ? (
                    <OpaqueUserValue
                      value={project.github.pull_request_title}
                    />
                  ) : (
                    copy(locale, 'project.untitled')
                  )}
                </p>
                <p>
                  {project.github.pull_request_draft &&
                    `${copy(locale, 'project.draft')} · `}
                  {copy(
                    locale,
                    pullRequestStateCopy(project.github.pull_request_state),
                  )}
                </p>
                <details className="project-technical-details">
                  <summary>{copy(locale, 'project.prDetails')}</summary>
                  <dl className="runtime-details">
                    <div>
                      <dt>{copy(locale, 'project.baseHead')}</dt>
                      <dd>
                        <SafeTechnicalValue
                          fallback={copy(locale, 'project.unknown')}
                          value={project.github.pull_request_base}
                        />{' '}
                        ←{' '}
                        <SafeTechnicalValue
                          fallback={copy(locale, 'project.unknown')}
                          value={project.github.pull_request_head}
                        />
                      </dd>
                    </div>
                    <div>
                      <dt>{copy(locale, 'project.mergeability')}</dt>
                      <dd>
                        {copy(
                          locale,
                          mergeabilityCopy(project.github.mergeability),
                        )}
                      </dd>
                    </div>
                  </dl>
                </details>
              </div>
            )}
            <button
              ref={prTrigger}
              className="secondary-button"
              disabled={!ready || !project.github?.available}
              aria-expanded={form === 'pr'}
              aria-controls="project-pr-form"
              onClick={() => (form === 'pr' ? closeForm() : openForm('pr'))}
              type="button"
            >
              <GitPullRequest aria-hidden="true" size={16} />
              {copy(locale, 'project.prepareDraftPr')}
            </button>
            {form === 'pr' && (
              <form
                id="project-pr-form"
                className="project-action-form"
                aria-label={copy(locale, 'project.prepareDraftPr')}
                onSubmit={draftPr}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault()
                    event.stopPropagation()
                    closeForm()
                  }
                }}
              >
                <label htmlFor="project-pr-title">
                  {copy(locale, 'project.prTitle')}
                </label>
                <input
                  id="project-pr-title"
                  ref={firstInput}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder={copy(locale, 'project.prTitlePlaceholder')}
                  maxLength={256}
                  required
                  disabled={!prEnabled}
                />
                <label htmlFor="project-pr-base">
                  {copy(locale, 'project.prBase')}
                </label>
                <input
                  id="project-pr-base"
                  value={base}
                  onChange={(event) => setBase(event.target.value)}
                  placeholder={copy(locale, 'project.prBasePlaceholder')}
                  maxLength={128}
                  disabled={!prEnabled}
                />
                <label htmlFor="project-pr-body">
                  {copy(locale, 'project.prBody')}
                </label>
                <textarea
                  id="project-pr-body"
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  placeholder={copy(locale, 'project.prBodyPlaceholder')}
                  maxLength={16_384}
                  disabled={!prEnabled}
                />
                <div className="project-action-row">
                  <button
                    className="primary-button"
                    disabled={!prEnabled || !title.trim()}
                    type="submit"
                  >
                    {copy(
                      locale,
                      model.pending === 'github/pull-requests'
                        ? 'project.creatingDraftPr'
                        : 'project.createDraftPr',
                    )}
                  </button>
                  <button
                    className="secondary-button"
                    onClick={closeForm}
                    type="button"
                  >
                    {copy(locale, 'project.cancel')}
                  </button>
                </div>
                <p className="project-form-note">
                  {copy(locale, 'project.cancelHint')}
                </p>
              </form>
            )}
          </section>
        </div>
        <aside
          className="project-detail-secondary"
          aria-label={copy(locale, 'project.context')}
        >
          <section className="runtime-card project-workspace-card">
            <h2>{copy(locale, 'project.workspace')}</h2>
            <p className="project-section-description">
              {copy(locale, 'project.workspaceReadiness')}
            </p>
            <details className="project-technical-details">
              <summary>{copy(locale, 'project.projectDetails')}</summary>
              <dl className="runtime-details">
                <div>
                  <dt>{copy(locale, 'project.projectId')}</dt>
                  <dd>
                    <SafeTechnicalValue
                      fallback={copy(locale, 'project.unknown')}
                      value={project.id}
                    />
                  </dd>
                </div>
                <div>
                  <dt>{copy(locale, 'project.slug')}</dt>
                  <dd>
                    <SafeTechnicalValue
                      fallback={copy(locale, 'project.unknown')}
                      value={project.slug}
                    />
                  </dd>
                </div>
                <div>
                  <dt>{copy(locale, 'project.source')}</dt>
                  <dd>
                    {copy(locale, PROJECT_SOURCE_COPY[project.source_type])}
                  </dd>
                </div>
              </dl>
            </details>
          </section>
          <ProjectLabelsPanel locale={locale} projectId={project.id} />
          <section className="runtime-card project-claude-card">
            <div className="runtime-card-heading">
              <h2>{copy(locale, 'project.claudeSession')}</h2>
              <StatusBadge
                tone={claude.session?.tmux_running ? 'good' : 'muted'}
              >
                {copy(
                  locale,
                  claude.loading
                    ? 'project.claudeLoading'
                    : claude.session
                      ? CLAUDE_STATE_COPY[claude.session.state]
                      : 'project.claudeUnavailable',
                )}
              </StatusBadge>
            </div>
            <p className="project-section-description">
              {copy(locale, 'project.claudeDescription')}
            </p>
            {claude.error && (
              <p className="error-panel">
                <LocalizedApiError error={claude.error} locale={locale} />
              </p>
            )}
            <div className="project-action-row">
              {claude.session?.tmux_running ? (
                <button
                  className="secondary-button"
                  disabled={claude.pending || claude.phase !== 'ready'}
                  onClick={() => void claude.action('stop')}
                  type="button"
                >
                  {copy(
                    locale,
                    claude.pending
                      ? 'project.stoppingClaude'
                      : 'project.stopClaude',
                  )}
                </button>
              ) : (
                <button
                  className="secondary-button"
                  disabled={
                    claude.pending || claude.phase !== 'ready' || !ready
                  }
                  onClick={() => void claude.action('start')}
                  type="button"
                >
                  {copy(
                    locale,
                    claude.pending
                      ? 'project.startingClaude'
                      : 'project.startClaude',
                  )}
                </button>
              )}
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
