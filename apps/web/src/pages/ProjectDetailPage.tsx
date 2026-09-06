import { type FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { LocalizedApiError, OpaqueUserValue } from '../components/i18n'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { StatusBadge } from '../components/StatusBadge'
import {
  useClaudeProject,
  type ClaudeSessionView,
} from '../features/claude/useClaude'
import {
  useProject,
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
  const model = useProject(projectId)
  const claude = useClaudeProject(
    model.project?.state === 'ready' ? projectId : undefined,
  )
  const [branch, setBranch] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [base, setBase] = useState('')
  usePageTitle(model.project?.display_name ?? copy(locale, 'project.title'))

  useEffect(() => {
    if (!branch && model.branches.length > 0) {
      setBranch(model.branches.find((item) => item.current)?.name ?? '')
    }
  }, [branch, model.branches])

  if (!model.project) {
    return (
      <>
        <Link className="back-link secondary-button" to="/projects">
          ← {copy(locale, 'project.backToProjects')}
        </Link>
        {model.error ? (
          <section className="error-panel" role="alert">
            <div>
              <h1>{copy(locale, 'project.unavailableTitle')}</h1>
              <LocalizedApiError
                error={model.error}
                locale={locale}
                role="presentation"
              />
            </div>
          </section>
        ) : (
          <p className="loading-panel" role="status">
            {copy(locale, 'project.loading')}
          </p>
        )}
      </>
    )
  }

  const project = model.project
  const git = project.git
  const changes = git
    ? git.staged_count +
      git.unstaged_count +
      git.untracked_count +
      git.conflicted_count
    : 0

  function createBranch(event: FormEvent) {
    event.preventDefault()
    const nextBranch = branch.trim()
    if (nextBranch) void model.mutate('git/branches', { branch: nextBranch })
  }

  function draftPr(event: FormEvent) {
    event.preventDefault()
    if (title.trim()) {
      void model.mutate('github/pull-requests', {
        title,
        body,
        base: base || null,
      })
    }
  }

  return (
    <>
      <Link className="back-link secondary-button" to="/projects">
        ← {copy(locale, 'project.backToProjects')}
      </Link>
      <header className="page-header">
        <div>
          <p className="eyebrow">{copy(locale, 'project.eyebrow')}</p>
          <h1>
            <OpaqueUserValue value={project.display_name} />
          </h1>
          <p className="page-description">
            {copy(locale, 'project.description')}
          </p>
        </div>
      </header>
      {model.error && (
        <p className="error-panel">
          <LocalizedApiError error={model.error} locale={locale} />
        </p>
      )}
      <section className="project-detail-grid">
        <article className="runtime-card">
          <div className="runtime-card-heading">
            <h2>{copy(locale, 'project.workspace')}</h2>
            <StatusBadge tone={project.state === 'ready' ? 'good' : 'warning'}>
              {copy(locale, PROJECT_STATE_COPY[project.state])}
            </StatusBadge>
          </div>
          <dl className="runtime-details">
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
              <dd>{copy(locale, PROJECT_SOURCE_COPY[project.source_type])}</dd>
            </div>
          </dl>
          {project.state === 'ready' && (
            <Link
              className="primary-button action-button"
              style={{
                alignItems: 'center',
                display: 'inline-flex',
                justifyContent: 'center',
              }}
              to={`/workspace?project_id=${encodeURIComponent(project.id)}`}
            >
              {copy(locale, 'project.openWorkspace')}
            </Link>
          )}
        </article>
        <article className="runtime-card">
          <div className="runtime-card-heading">
            <h2>{copy(locale, 'project.git')}</h2>
            <StatusBadge tone={git?.clean ? 'good' : 'warning'}>
              {git?.is_repository
                ? git.clean
                  ? copy(locale, 'project.gitClean')
                  : formatMessage(locale, 'project.gitChanges', {
                      count: String(changes),
                    })
                : copy(locale, 'project.notInitialized')}
            </StatusBadge>
          </div>
          {git?.is_repository && (
            <dl className="runtime-details">
              <div>
                <dt>{copy(locale, 'project.branch')}</dt>
                <dd>
                  {git.detached_head ? (
                    copy(locale, 'project.detachedHead')
                  ) : git.branch !== null ? (
                    <SafeTechnicalValue
                      fallback={copy(locale, 'project.unknown')}
                      value={git.branch}
                    />
                  ) : (
                    copy(locale, 'project.unbornBranch')
                  )}
                </dd>
              </div>
              <div>
                <dt>{copy(locale, 'project.aheadBehind')}</dt>
                <dd>
                  {git.ahead} / {git.behind}
                </dd>
              </div>
              <div>
                <dt>{copy(locale, 'project.remote')}</dt>
                <dd>
                  {git.remote_url !== null ? (
                    <SafeTechnicalValue
                      fallback={copy(locale, 'project.unknown')}
                      value={git.remote_url}
                    />
                  ) : (
                    copy(locale, 'project.none')
                  )}
                </dd>
              </div>
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
            </dl>
          )}
          {git?.submodules_detected && (
            <p className="interaction-notice">
              {copy(locale, 'project.submodulesDetected')}
            </p>
          )}
        </article>
      </section>
      <section className="runtime-card">
        <h2>{copy(locale, 'project.gitActionsTitle')}</h2>
        <p>{copy(locale, 'project.gitActionsDescription')}</p>
        <div className="action-row">
          <button
            className="secondary-button"
            disabled={model.busy || !git?.is_repository}
            onClick={() => void model.mutate('git/pull')}
            type="button"
          >
            {model.pending === 'git/pull'
              ? copy(locale, 'project.pulling')
              : copy(locale, 'project.pull')}
          </button>
          <button
            className="secondary-button"
            disabled={model.busy || !git?.is_repository}
            onClick={() => void model.mutate('git/push')}
            type="button"
          >
            {model.pending === 'git/push'
              ? copy(locale, 'project.pushing')
              : copy(locale, 'project.push')}
          </button>
        </div>
        <form className="inline-form" onSubmit={createBranch}>
          <input
            aria-label={copy(locale, 'project.branchName')}
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
            placeholder={copy(locale, 'project.branchPlaceholder')}
          />
          <button
            className="secondary-button"
            disabled={model.busy || !branch.trim() || !git?.is_repository}
            type="submit"
          >
            {model.pending === 'git/branches'
              ? copy(locale, 'project.creatingBranch')
              : copy(locale, 'project.createBranch')}
          </button>
          <button
            className="secondary-button"
            disabled={model.busy || !branch.trim()}
            onClick={() =>
              void model.mutate('git/switch', { branch: branch.trim() })
            }
            type="button"
          >
            {model.pending === 'git/switch'
              ? copy(locale, 'project.switchingBranch')
              : copy(locale, 'project.switchBranch')}
          </button>
        </form>
        {model.branches.length > 0 && (
          <div
            className="branch-list"
            aria-label={copy(locale, 'project.localBranches')}
          >
            {model.branches.map((item) => (
              <button
                className="secondary-button"
                disabled={model.busy}
                key={item.name}
                onClick={() => setBranch(item.name)}
                type="button"
              >
                {item.current && `${copy(locale, 'project.currentBranch')} · `}
                <SafeTechnicalValue
                  fallback={copy(locale, 'project.unknown')}
                  value={item.name}
                />
              </button>
            ))}
          </div>
        )}
      </section>
      <section className="runtime-card">
        <h2>{copy(locale, 'project.github')}</h2>
        {project.github?.available ? (
          <p>
            {project.github.repository !== null ? (
              <SafeTechnicalValue
                fallback={copy(locale, 'project.unknown')}
                value={project.github.repository}
              />
            ) : (
              copy(locale, 'project.unknown')
            )}{' '}
            · {copy(locale, 'project.checks')}{' '}
            {copy(locale, CHECKS_COPY[project.github.checks])}
          </p>
        ) : (
          <p>{copy(locale, 'project.githubUnavailable')}</p>
        )}
        {project.github?.pull_request_number && (
          <dl className="runtime-details">
            <div>
              <dt>{copy(locale, 'project.currentBranchPr')}</dt>
              <dd>
                #{project.github.pull_request_number}{' '}
                {project.github.pull_request_title ? (
                  <OpaqueUserValue value={project.github.pull_request_title} />
                ) : (
                  copy(locale, 'project.untitled')
                )}
              </dd>
            </div>
            <div>
              <dt>{copy(locale, 'project.prState')}</dt>
              <dd>
                {project.github.pull_request_draft &&
                  `${copy(locale, 'project.draft')} · `}
                {copy(
                  locale,
                  pullRequestStateCopy(project.github.pull_request_state),
                )}
              </dd>
            </div>
            <div>
              <dt>{copy(locale, 'project.baseHead')}</dt>
              <dd>
                {project.github.pull_request_base !== null ? (
                  <SafeTechnicalValue
                    fallback={copy(locale, 'project.unknown')}
                    value={project.github.pull_request_base}
                  />
                ) : (
                  copy(locale, 'project.unknown')
                )}{' '}
                ←{' '}
                {project.github.pull_request_head !== null ? (
                  <SafeTechnicalValue
                    fallback={copy(locale, 'project.unknown')}
                    value={project.github.pull_request_head}
                  />
                ) : (
                  copy(locale, 'project.unknown')
                )}
              </dd>
            </div>
            <div>
              <dt>{copy(locale, 'project.mergeability')}</dt>
              <dd>
                {copy(locale, mergeabilityCopy(project.github.mergeability))}
              </dd>
            </div>
          </dl>
        )}
        <form className="inline-form" onSubmit={draftPr}>
          <input
            aria-label={copy(locale, 'project.prTitle')}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={copy(locale, 'project.prTitlePlaceholder')}
            maxLength={256}
            required
          />
          <input
            aria-label={copy(locale, 'project.prBase')}
            value={base}
            onChange={(event) => setBase(event.target.value)}
            placeholder={copy(locale, 'project.prBasePlaceholder')}
            maxLength={128}
          />
          <textarea
            aria-label={copy(locale, 'project.prBody')}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder={copy(locale, 'project.prBodyPlaceholder')}
            maxLength={16_384}
          />
          <button
            className="primary-button"
            disabled={model.busy || !project.github?.available}
            type="submit"
          >
            {model.pending === 'github/pull-requests'
              ? copy(locale, 'project.creatingDraftPr')
              : copy(locale, 'project.createDraftPr')}
          </button>
        </form>
      </section>
      <section className="runtime-card">
        <div className="runtime-card-heading">
          <h2>{copy(locale, 'project.claudeSession')}</h2>
          <StatusBadge tone={claude.session?.tmux_running ? 'good' : 'muted'}>
            {claude.loading
              ? copy(locale, 'project.claudeLoading')
              : claude.session
                ? copy(locale, CLAUDE_STATE_COPY[claude.session.state])
                : copy(locale, 'project.claudeUnavailable')}
          </StatusBadge>
        </div>
        <p>{copy(locale, 'project.claudeDescription')}</p>
        {claude.error && (
          <p className="error-panel">
            <LocalizedApiError error={claude.error} locale={locale} />
          </p>
        )}
        <div className="action-row">
          {claude.session?.tmux_running ? (
            <button
              className="secondary-button"
              disabled={claude.pending}
              onClick={() => void claude.action('stop')}
              type="button"
            >
              {claude.pending
                ? copy(locale, 'project.stoppingClaude')
                : copy(locale, 'project.stopClaude')}
            </button>
          ) : (
            <button
              className="primary-button"
              disabled={claude.pending || project.state !== 'ready'}
              onClick={() => void claude.action('start')}
              type="button"
            >
              {claude.pending
                ? copy(locale, 'project.startingClaude')
                : copy(locale, 'project.startClaude')}
            </button>
          )}
        </div>
      </section>
      {model.job && <LatestJob job={model.job} locale={locale} />}
    </>
  )
}
