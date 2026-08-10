import { FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { Boxes, RefreshCw } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useProjects } from '../features/projects/useProjects'
import { usePageTitle } from '../hooks/usePageTitle'

export function ProjectsPage() {
  const model = useProjects()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [cloneName, setCloneName] = useState('')
  usePageTitle('Projects')

  function create(event: FormEvent) {
    event.preventDefault()
    if (name.trim()) void model.create(name.trim()).then(() => setName(''))
  }
  function clone(event: FormEvent) {
    event.preventDefault()
    if (url.trim())
      void model.clone(url.trim(), cloneName.trim()).then(() => setUrl(''))
  }

  return (
    <>
      <PageHeader
        eyebrow="Workspaces"
        title="Projects"
        description="Managed workspaces under the configured Project Root—never arbitrary filesystem paths."
        action={
          <button
            className="secondary-button"
            onClick={() => void model.refresh()}
            type="button"
          >
            <RefreshCw size={16} /> Refresh
          </button>
        }
      />
      {model.error && (
        <p className="error-panel" role="alert">
          {model.error.message}
        </p>
      )}
      {model.job && (
        <section className="runtime-card" role="status">
          <h2>Workspace operation</h2>
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
      <section className="project-forms">
        <form className="runtime-card" onSubmit={create}>
          <p className="eyebrow">Empty workspace</p>
          <h2>New Project</h2>
          <label>
            Project name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={128}
              required
            />
          </label>
          <button
            className="primary-button"
            disabled={model.pending}
            type="submit"
          >
            Create Project
          </button>
        </form>
        <form className="runtime-card" onSubmit={clone}>
          <p className="eyebrow">GitHub repository</p>
          <h2>Clone Repository</h2>
          <label>
            Repository URL
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
            />
          </label>
          <label>
            Project name (optional)
            <input
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
            />
          </label>
          <button
            className="primary-button"
            disabled={model.pending}
            type="submit"
          >
            Clone
          </button>
        </form>
      </section>
      {model.loading ? (
        <p className="loading-panel">Loading Projects…</p>
      ) : model.projects.length === 0 ? (
        <section className="empty-state">
          <Boxes />
          <h2>No Projects yet</h2>
          <p>Create a bounded workspace or clone an approved GitHub URL.</p>
        </section>
      ) : (
        <section className="project-grid" aria-label="Projects">
          {model.projects.map((project) => (
            <Link
              className="runtime-card project-link"
              key={project.id}
              to={`/projects/${project.id}`}
            >
              <div className="runtime-card-heading">
                <h2>{project.display_name}</h2>
                <StatusBadge
                  tone={project.state === 'ready' ? 'good' : 'warning'}
                >
                  {project.state}
                </StatusBadge>
              </div>
              <p>
                {project.source_type === 'git_clone'
                  ? 'Cloned repository'
                  : 'Workspace'}
              </p>
              <dl className="runtime-details compact-details">
                <div>
                  <dt>Branch</dt>
                  <dd>{project.git?.branch ?? 'Not initialized'}</dd>
                </div>
                <div>
                  <dt>Changes</dt>
                  <dd>
                    {project.git
                      ? project.git.staged_count +
                        project.git.unstaged_count +
                        project.git.untracked_count +
                        project.git.conflicted_count
                      : 0}
                  </dd>
                </div>
                <div>
                  <dt>Remote</dt>
                  <dd>{project.git?.remote_url ?? 'None'}</dd>
                </div>
                <div>
                  <dt>Claude</dt>
                  <dd>
                    {project.claude_state?.replaceAll('_', ' ') ?? 'Unknown'}
                  </dd>
                </div>
              </dl>
            </Link>
          ))}
        </section>
      )}
    </>
  )
}
