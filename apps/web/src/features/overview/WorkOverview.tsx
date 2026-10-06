import {
  ArrowRight,
  CircleAlert,
  Folder,
  Layers3,
  RefreshCw,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { OpaqueUserValue } from '../../components/i18n'
import { SafeTechnicalValue } from '../../components/i18n/SafeTechnicalValue'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDate, formatNumber, type Locale } from '../../i18n'
import {
  dashboardCatalog,
  type DashboardMessageParameters,
} from '../../i18n/catalogs/dashboard'
import { parseJobListResponse, type JobData } from '../../lib/contracts'
import { parseRecentProjectListResponse, PROJECT_ID } from './recentProjects'
import {
  useOverviewResource,
  type OverviewResource,
} from './useOverviewResource'
import './WorkOverview.css'

type Copy = (key: keyof DashboardMessageParameters) => string

const JOB_STATUS = {
  queued: 'dashboard.queued',
  running: 'dashboard.running',
  needs_attention: 'dashboard.needsAttention',
} as const

function ResourceFeedback({
  resource,
  message,
}: {
  resource: OverviewResource<unknown>
  message: Copy
}) {
  if (resource.phase === 'ready') return null
  const key = {
    loading: 'dashboard.loadingWork',
    stale: 'dashboard.staleWork',
    error: 'dashboard.failedWork',
    forbidden: 'dashboard.permissionWork',
  } as const
  return (
    <p
      className="overview-feedback"
      role={
        resource.phase === 'error' || resource.phase === 'forbidden'
          ? 'alert'
          : 'status'
      }
    >
      {message(key[resource.phase])}
    </p>
  )
}

function ReceivedAt({
  date,
  locale,
  message,
}: {
  date: Date | null
  locale: Locale
  message: Copy
}) {
  return (
    date && (
      <p className="overview-received">
        {message('dashboard.received')}{' '}
        <time dateTime={date.toISOString()}>
          {formatDate(locale, date, {
            dateStyle: 'medium',
            timeStyle: 'short',
          })}
        </time>
      </p>
    )
  )
}

function JobRows({ jobs, message }: { jobs: JobData[]; message: Copy }) {
  return (
    <ol className="overview-list">
      {jobs.slice(0, 6).map((job) => (
        <li key={job.id}>
          <div className="overview-row-heading">
            <h4>
              <SafeTechnicalValue
                value={job.type}
                fallback={message('dashboard.unknown')}
              />
            </h4>
            {job.status in JOB_STATUS && (
              <StatusBadge
                tone={job.status === 'needs_attention' ? 'warning' : 'muted'}
              >
                {message(JOB_STATUS[job.status as keyof typeof JOB_STATUS])}
              </StatusBadge>
            )}
          </div>
          <p className="overview-job-id">
            {message('dashboard.jobId')}{' '}
            <SafeTechnicalValue
              value={job.id}
              fallback={message('dashboard.unknown')}
            />
          </p>
          {job.error_code && (
            <p>
              <SafeTechnicalValue
                value={job.error_code}
                fallback={message('dashboard.unknown')}
              />
            </p>
          )}
          {job.project_id && PROJECT_ID.test(job.project_id) ? (
            <Link className="overview-link" to={`/projects/${job.project_id}`}>
              {message('dashboard.openProject')}{' '}
              <SafeTechnicalValue
                value={job.project_id}
                fallback={message('dashboard.unknown')}
              />
            </Link>
          ) : (
            <p>{message('dashboard.noProjectLink')}</p>
          )}
        </li>
      ))}
    </ol>
  )
}

export function WorkOverview({ locale }: { locale: Locale }) {
  const message: Copy = (key) => dashboardCatalog.catalogs[locale][key]({})
  const [refreshSequence, setRefreshSequence] = useState(0)
  const jobs = useOverviewResource(
    '/api/v1/jobs?scope=mine',
    parseJobListResponse,
    refreshSequence,
  )
  const projects = useOverviewResource(
    '/api/v1/projects/recent',
    parseRecentProjectListResponse,
    refreshSequence,
  )
  const attention =
    jobs.data?.data.jobs.filter((job) => job.status === 'needs_attention') ?? []
  const active =
    jobs.data?.data.jobs.filter(
      (job) => job.status === 'queued' || job.status === 'running',
    ) ?? []
  const refreshing = jobs.phase === 'loading' || projects.phase === 'loading'

  return (
    <section className="work-overview" aria-labelledby="work-overview-title">
      <div className="section-heading overview-heading">
        <div>
          <h2 id="work-overview-title">{message('dashboard.workTitle')}</h2>
          <p>{message('dashboard.workDescription')}</p>
        </div>
        <button
          className="secondary-button"
          type="button"
          disabled={refreshing}
          onClick={() => setRefreshSequence((value) => value + 1)}
        >
          <RefreshCw aria-hidden="true" size={16} />
          {message('dashboard.refreshWork')}
        </button>
      </div>
      <div className="overview-grid">
        {(
          [
            {
              id: 'attention',
              icon: CircleAlert,
              title: 'dashboard.attention',
              empty: 'dashboard.emptyAttention',
              rows: attention,
            },
            {
              id: 'active',
              icon: Layers3,
              title: 'dashboard.active',
              empty: 'dashboard.emptyActive',
              rows: active,
            },
          ] as const
        ).map(({ id, icon: Icon, title, empty, rows }) => (
          <section
            className={`overview-card overview-card-${id}`}
            aria-labelledby={`overview-${id}`}
            key={id}
          >
            <div className="overview-card-heading">
              <h3 id={`overview-${id}`}>
                <Icon aria-hidden="true" size={18} />
                {message(title)}
              </h3>
              {jobs.phase === 'ready' && (
                <span
                  className="overview-count"
                  aria-label={`${message('dashboard.windowCount')}: ${formatNumber(locale, rows.length)}`}
                >
                  {formatNumber(locale, rows.length)}
                </span>
              )}
            </div>
            <ResourceFeedback resource={jobs} message={message} />
            {jobs.phase === 'ready' &&
              (rows.length ? (
                <JobRows jobs={rows} message={message} />
              ) : (
                <p className="overview-feedback" role="status">
                  {message(empty)}
                </p>
              ))}
            <ReceivedAt
              date={jobs.receivedAt}
              locale={locale}
              message={message}
            />
            {id === 'attention' && (
              <Link className="overview-link overview-footer" to="/attention">
                {message('dashboard.allAttention')}
                <ArrowRight aria-hidden="true" size={15} />
              </Link>
            )}
          </section>
        ))}
      </div>
      <p className="overview-scope overview-job-scope">
        {message('dashboard.jobsScope')} {message('dashboard.visibleLimit')}
      </p>
      <section
        className="overview-card overview-projects"
        aria-labelledby="overview-projects"
      >
        <div className="overview-card-heading">
          <h3 id="overview-projects">
            <Folder aria-hidden="true" size={18} />
            {message('dashboard.recentProjects')}
          </h3>
          <Link className="overview-link overview-footer" to="/projects">
            {message('dashboard.allProjects')}
            <ArrowRight aria-hidden="true" size={15} />
          </Link>
        </div>
        <p className="overview-scope">{message('dashboard.projectsScope')}</p>
        <ResourceFeedback resource={projects} message={message} />
        {projects.phase === 'ready' &&
          (projects.data.data.projects.length ? (
            <ol className="overview-list overview-project-list">
              {projects.data.data.projects.map((project) => (
                <li key={project.id}>
                  <h4>
                    <Link
                      className="overview-link"
                      to={`/projects/${project.id}`}
                    >
                      <OpaqueUserValue value={project.display_name} />
                    </Link>
                  </h4>
                  <p>
                    {message('dashboard.metadataUpdated')}{' '}
                    <time dateTime={project.updated_at}>
                      {formatDate(locale, new Date(project.updated_at), {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </time>
                  </p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="overview-feedback" role="status">
              {message('dashboard.emptyProjects')}
            </p>
          ))}
        <ReceivedAt
          date={projects.receivedAt}
          locale={locale}
          message={message}
        />
      </section>
    </section>
  )
}
