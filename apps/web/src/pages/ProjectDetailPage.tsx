import { FormEvent, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useProject } from '../features/projects/useProjects'
import { usePageTitle } from '../hooks/usePageTitle'

export function ProjectDetailPage() {
  const { projectId } = useParams()
  const model = useProject(projectId)
  const [branch, setBranch] = useState('')
  const [title, setTitle] = useState('')
  usePageTitle(model.project?.display_name ?? 'Project')
  if (!model.project) return <p className="loading-panel">Loading Project…</p>
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
    if (title) void model.mutate('github/pull-requests', { title, body: '' })
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
            </dl>
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
            onClick={() => void model.mutate('git/pull')}
            type="button"
          >
            Pull
          </button>
          <button
            className="secondary-button"
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
          <button className="secondary-button" type="submit">
            Create branch
          </button>
          <button
            className="secondary-button"
            onClick={() => void model.mutate('git/switch', { branch })}
            type="button"
          >
            Switch branch
          </button>
        </form>
      </section>
      <section className="runtime-card">
        <h2>GitHub</h2>
        <p>
          {project.github?.available
            ? `${project.github.repository} · checks ${project.github.checks}`
            : 'GitHub features unavailable for this Project.'}
        </p>
        <form className="inline-form" onSubmit={draftPr}>
          <input
            aria-label="Pull request title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Draft PR title"
          />
          <button className="primary-button" type="submit">
            Create Draft PR
          </button>
        </form>
      </section>
      {model.pending && (
        <p role="status">Operation queued. Track it in Jobs.</p>
      )}
    </>
  )
}
