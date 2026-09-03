import { FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useClaudeProject } from '../features/claude/useClaude'
import { useProject } from '../features/projects/useProjects'
import { usePageTitle } from '../hooks/usePageTitle'

export function ProjectDetailPage() {
  const { projectId } = useParams()
  const model = useProject(projectId)
  const claude = useClaudeProject(
    model.project?.state === 'ready' ? projectId : undefined,
  )
  const [branch, setBranch] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [base, setBase] = useState('')
  usePageTitle(model.project?.display_name ?? 'Project')
  useEffect(() => {
    if (!branch && model.branches.length > 0) {
      setBranch(model.branches.find((item) => item.current)?.name ?? '')
    }
  }, [branch, model.branches])
  if (!model.project) {
    return model.error ? (
      <p className="error-panel" role="alert">
        {model.error.message}
      </p>
    ) : (
      <p className="loading-panel">Loading Project…</p>
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
    if (branch) void model.mutate('git/branches', { branch })
  }
  function draftPr(event: FormEvent) {
    event.preventDefault()
    if (title)
      void model.mutate('github/pull-requests', {
        title,
        body,
        base: base || null,
      })
  }
  return (
    <>
      <Link className="back-link" to="/projects">
        ← Projects
      </Link>
      <PageHeader
        eyebrow="Project Workspace"
        title={project.display_name}
        description="Git operations are typed, serialized, and executed without a shell."
      />
      {model.error && (
        <p className="error-panel" role="alert">
          {model.error.message}
        </p>
      )}
      <section className="project-detail-grid">
        <article className="runtime-card">
          <div className="runtime-card-heading">
            <h2>Workspace</h2>
            <StatusBadge tone={project.state === 'ready' ? 'good' : 'warning'}>
              {project.state}
            </StatusBadge>
          </div>
          <dl className="runtime-details">
            <div>
              <dt>Slug</dt>
              <dd>{project.slug}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{project.source_type}</dd>
            </div>
          </dl>
          {project.state === 'ready' && (
            <Link
              className="primary-button"
              to={`/workspace?project_id=${encodeURIComponent(project.id)}`}
            >
              打开交互式工作区
            </Link>
          )}
        </article>
        <article className="runtime-card">
          <div className="runtime-card-heading">
            <h2>Git</h2>
            <StatusBadge tone={git?.clean ? 'good' : 'warning'}>
              {git?.is_repository
                ? git.clean
                  ? 'Clean'
                  : `${changes} changes`
                : 'Not initialized'}
            </StatusBadge>
          </div>
          {git?.is_repository && (
            <dl className="runtime-details">
              <div>
                <dt>Branch</dt>
                <dd>
                  {git.detached_head
                    ? 'Detached HEAD'
                    : (git.branch ?? 'Unborn')}
                </dd>
              </div>
              <div>
                <dt>Ahead / behind</dt>
                <dd>
                  {git.ahead} / {git.behind}
                </dd>
              </div>
              <div>
                <dt>Remote</dt>
                <dd>{git.remote_url ?? 'None'}</dd>
              </div>
              <div>
                <dt>Staged / unstaged</dt>
                <dd>
                  {git.staged_count} / {git.unstaged_count}
                </dd>
              </div>
              <div>
                <dt>Untracked / conflicted</dt>
                <dd>
                  {git.untracked_count} / {git.conflicted_count}
                </dd>
              </div>
            </dl>
          )}
          {git?.submodules_detected && (
            <p className="interaction-notice">
              Submodules detected — automatic initialization is not supported.
            </p>
          )}
        </article>
      </section>
      <section className="runtime-card">
        <h2>Safe Git actions</h2>
        <p>
          Pull is fast-forward only. Push never forces. Active Claude sessions
          block Pull and branch switching.
        </p>
        <div className="action-row">
          <button
            className="secondary-button"
            disabled={model.busy || !git?.is_repository}
            onClick={() => void model.mutate('git/pull')}
            type="button"
          >
            Pull
          </button>
          <button
            className="secondary-button"
            disabled={model.busy || !git?.is_repository}
            onClick={() => void model.mutate('git/push')}
            type="button"
          >
            Push
          </button>
        </div>
        <form className="inline-form" onSubmit={createBranch}>
          <input
            aria-label="Branch name"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="feature/name"
          />
          <button
            className="secondary-button"
            disabled={model.busy || !branch || !git?.is_repository}
            type="submit"
          >
            Create branch
          </button>
          <button
            className="secondary-button"
            disabled={model.busy || !branch}
            onClick={() => void model.mutate('git/switch', { branch })}
            type="button"
          >
            Switch branch
          </button>
        </form>
        {model.branches.length > 0 && (
          <div className="branch-list" aria-label="Local branches">
            {model.branches.map((item) => (
              <button
                className="secondary-button"
                disabled={model.busy}
                key={item.name}
                onClick={() => setBranch(item.name)}
                type="button"
              >
                {item.current ? 'Current · ' : ''}
                {item.name}
              </button>
            ))}
          </div>
        )}
      </section>
      <section className="runtime-card">
        <h2>GitHub</h2>
        <p>
          {project.github?.available
            ? `${project.github.repository} · checks ${project.github.checks}`
            : 'GitHub features unavailable for this Project.'}
        </p>
        {project.github?.pull_request_number && (
          <dl className="runtime-details">
            <div>
              <dt>Current branch PR</dt>
              <dd>
                #{project.github.pull_request_number}{' '}
                {project.github.pull_request_title ?? 'Untitled'}
              </dd>
            </div>
            <div>
              <dt>State</dt>
              <dd>
                {project.github.pull_request_draft ? 'Draft · ' : ''}
                {project.github.pull_request_state ?? 'Unknown'}
              </dd>
            </div>
            <div>
              <dt>Base / head</dt>
              <dd>
                {project.github.pull_request_base ?? 'Unknown'} ←{' '}
                {project.github.pull_request_head ?? 'Unknown'}
              </dd>
            </div>
            <div>
              <dt>Mergeability</dt>
              <dd>{project.github.mergeability ?? 'Unknown'}</dd>
            </div>
          </dl>
        )}
        <form className="inline-form" onSubmit={draftPr}>
          <input
            aria-label="Pull request title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Draft PR title"
            maxLength={256}
            required
          />
          <input
            aria-label="Pull request base branch"
            value={base}
            onChange={(e) => setBase(e.target.value)}
            placeholder="Base branch (optional)"
            maxLength={128}
          />
          <textarea
            aria-label="Pull request body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Draft PR body (do not paste credentials)"
            maxLength={16_384}
          />
          <button
            className="primary-button"
            disabled={model.busy || !project.github?.available}
            type="submit"
          >
            Create Draft PR
          </button>
        </form>
      </section>
      <section className="runtime-card">
        <div className="runtime-card-heading">
          <h2>Claude session</h2>
          <StatusBadge tone={claude.session?.tmux_running ? 'good' : 'muted'}>
            {claude.loading
              ? 'Loading'
              : (claude.session?.state.replaceAll('_', ' ') ?? 'Unavailable')}
          </StatusBadge>
        </div>
        <p>
          Branch switching and Pull are blocked while this managed session is
          active.
        </p>
        {claude.error && (
          <p className="error-panel" role="alert">
            {claude.error.message}
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
              Stop Claude
            </button>
          ) : (
            <button
              className="primary-button"
              disabled={claude.pending || project.state !== 'ready'}
              onClick={() => void claude.action('start')}
              type="button"
            >
              Start Claude
            </button>
          )}
        </div>
      </section>
      {model.job && (
        <section className="runtime-card" role="status">
          <h2>Latest operation</h2>
          <p>
            Job {model.job.id} · {model.job.status}
            {model.job.phase ? ` · ${model.job.phase}` : ''}
          </p>
          {model.job.error_summary && (
            <p className="error-panel">
              {model.job.error_code}: {model.job.error_summary}
            </p>
          )}
        </section>
      )}
    </>
  )
}
