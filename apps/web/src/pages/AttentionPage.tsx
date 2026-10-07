import { ArrowUpRight, CircleAlert, CircleCheck, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../components/PageHeader'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { StatusBadge } from '../components/StatusBadge'
import { useOverviewResource } from '../features/overview/useOverviewResource'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, formatDate, formatMessage, type Locale } from '../i18n'
import { parseJobListResponse, type JobListResponse } from '../lib/contracts'
import './AttentionPage.css'

const PROJECT_ID = /^prj_[0-9a-f]{32}$/
const JOB_ID = /^job_[A-Za-z0-9_-]{1,96}$/
const JOB_TYPE = /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,3}$/
const REASON_CODE = /^[A-Z][A-Z0-9_]{0,79}$/

function boundedIdentifier(value: string | null, pattern: RegExp) {
  return value !== null && value.length <= 100 && pattern.test(value)
    ? value
    : null
}
const PHASE_COPY = {
  loading: 'attention.loading',
  stale: 'attention.stale',
  error: 'attention.failed',
  forbidden: 'attention.forbidden',
} as const

export function AttentionPage({
  locale = currentLocale(),
}: {
  locale?: Locale
}) {
  const [refreshSequence, setRefreshSequence] = useState(0)
  const resource = useOverviewResource<JobListResponse>(
    '/api/v1/jobs?scope=mine',
    parseJobListResponse,
    refreshSequence,
  )
  const jobs =
    resource.phase === 'ready'
      ? resource.data.data.jobs.filter(
          (job) => job.status === 'needs_attention',
        )
      : []
  usePageTitle(formatMessage(locale, 'attention.title', {}))

  return (
    <div className="attention-page">
      <PageHeader
        eyebrow={formatMessage(locale, 'attention.eyebrow', {})}
        title={formatMessage(locale, 'attention.title', {})}
        description={formatMessage(locale, 'attention.description', {})}
        action={
          <button
            className="secondary-button attention-refresh"
            disabled={
              resource.phase === 'loading' ||
              resource.phase === 'stale' ||
              resource.phase === 'forbidden'
            }
            onClick={() => setRefreshSequence((current) => current + 1)}
            type="button"
          >
            <RefreshCw aria-hidden="true" size={16} />
            {formatMessage(locale, 'attention.refresh', {})}
          </button>
        }
      />
      {resource.phase !== 'ready' ? (
        <section
          className={`runtime-card attention-state${resource.phase === 'error' || resource.phase === 'forbidden' ? ' attention-state-error' : ''}`}
          role={
            resource.phase === 'error' || resource.phase === 'forbidden'
              ? 'alert'
              : 'status'
          }
        >
          <CircleAlert aria-hidden="true" size={24} />
          <p>{formatMessage(locale, PHASE_COPY[resource.phase], {})}</p>
        </section>
      ) : (
        <>
          <div className="attention-summary">
            <p>
              {formatMessage(locale, 'attention.count', {
                count: String(jobs.length),
              })}
            </p>
            <p className="attention-observed">
              {formatMessage(locale, 'attention.observed', {})}{' '}
              <time dateTime={resource.receivedAt.toISOString()}>
                {formatDate(locale, resource.receivedAt, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })}
              </time>
            </p>
          </div>
          {jobs.length === 0 ? (
            <section
              className="runtime-card attention-state attention-empty"
              role="status"
            >
              <CircleCheck aria-hidden="true" size={28} />
              <h2>{formatMessage(locale, 'attention.empty', {})}</h2>
              <p>{formatMessage(locale, 'attention.window', {})}</p>
            </section>
          ) : (
            <ol className="attention-list">
              {jobs.map((job) => (
                <li className="runtime-card attention-item" key={job.id}>
                  <div className="attention-item-heading">
                    <span className="attention-item-icon">
                      <CircleAlert aria-hidden="true" size={21} />
                    </span>
                    <h2>
                      <SafeTechnicalValue
                        fallback={formatMessage(
                          locale,
                          'attention.unknown',
                          {},
                        )}
                        value={boundedIdentifier(job.type, JOB_TYPE)}
                      />
                    </h2>
                    <StatusBadge tone="warning">
                      {formatMessage(locale, 'attention.title', {})}
                    </StatusBadge>
                  </div>
                  <dl className="attention-reason">
                    <dt>{formatMessage(locale, 'attention.reason', {})}</dt>
                    <dd>
                      <SafeTechnicalValue
                        fallback={formatMessage(
                          locale,
                          'attention.unknown',
                          {},
                        )}
                        value={boundedIdentifier(job.error_code, REASON_CODE)}
                      />
                    </dd>
                  </dl>
                  <div className="attention-item-footer">
                    <details className="attention-details">
                      <summary>
                        {formatMessage(locale, 'attention.details', {})}
                      </summary>
                      <dl className="runtime-details compact-details">
                        <div>
                          <dt>{formatMessage(locale, 'attention.job', {})}</dt>
                          <dd>
                            <SafeTechnicalValue
                              fallback={formatMessage(
                                locale,
                                'attention.unknown',
                                {},
                              )}
                              value={boundedIdentifier(job.id, JOB_ID)}
                            />
                          </dd>
                        </div>
                      </dl>
                    </details>
                    {job.project_id && PROJECT_ID.test(job.project_id) ? (
                      <Link
                        className="secondary-button attention-project-link"
                        to={`/projects/${job.project_id}`}
                      >
                        {formatMessage(locale, 'attention.project', {})}
                        <ArrowUpRight aria-hidden="true" size={16} />
                      </Link>
                    ) : (
                      <p className="attention-unlinked">
                        {formatMessage(locale, 'attention.unlinked', {})}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  )
}
