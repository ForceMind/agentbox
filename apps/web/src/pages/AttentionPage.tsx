import { RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '../components/PageHeader'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, formatDate, formatMessage, type Locale } from '../i18n'
import {
  parseJobListResponse,
  type JobData,
  type JobListResponse,
} from '../lib/contracts'
import './AttentionPage.css'

type AttentionPhase = 'loading' | 'ready' | 'stale' | 'error'
type AttentionState = Readonly<{
  phase: AttentionPhase
  jobs: JobData[]
  observedAt: Date | null
}>

const PROJECT_ID = /^prj_[0-9a-f]{32}$/

function statusCopy(locale: Locale, phase: AttentionPhase): string {
  switch (phase) {
    case 'loading':
      return formatMessage(locale, 'attention.loading', {})
    case 'stale':
      return formatMessage(locale, 'attention.stale', {})
    case 'error':
      return formatMessage(locale, 'attention.failed', {})
    case 'ready':
      return ''
  }
}

export function AttentionPage({
  locale = currentLocale(),
}: {
  locale?: Locale
}) {
  const { api } = useAuth()
  const [refreshSequence, setRefreshSequence] = useState(0)
  const [state, setState] = useState<AttentionState>({
    phase: 'loading',
    jobs: [],
    observedAt: null,
  })
  usePageTitle(formatMessage(locale, 'attention.title', {}))

  useEffect(() => {
    let pending: AbortController | null = null

    function refresh() {
      pending?.abort()
      const controller = new AbortController()
      pending = controller
      setState({ phase: 'loading', jobs: [], observedAt: null })
      void api
        .get<JobListResponse>('/api/v1/jobs', {
          signal: controller.signal,
          timeoutMs: 15_000,
          validate: parseJobListResponse,
        })
        .then((response) => {
          if (controller.signal.aborted) return
          setState({
            phase: 'ready',
            jobs: response.data.jobs.filter(
              (job) => job.status === 'needs_attention',
            ),
            observedAt: new Date(),
          })
        })
        .catch(() => {
          if (controller.signal.aborted) return
          setState({ phase: 'error', jobs: [], observedAt: null })
        })
    }

    function onVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        pending?.abort()
        setState((current) => ({ ...current, phase: 'stale' }))
      } else {
        refresh()
      }
    }

    if (document.visibilityState === 'hidden') {
      setState((current) => ({ ...current, phase: 'stale' }))
    } else {
      refresh()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      pending?.abort()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [api, refreshSequence])

  return (
    <>
      <PageHeader
        eyebrow={formatMessage(locale, 'attention.eyebrow', {})}
        title={formatMessage(locale, 'attention.title', {})}
        description={formatMessage(locale, 'attention.description', {})}
        action={
          <button
            className="secondary-button"
            onClick={() => setRefreshSequence((current) => current + 1)}
            type="button"
          >
            <RefreshCw aria-hidden="true" size={16} />{' '}
            {formatMessage(locale, 'attention.refresh', {})}
          </button>
        }
      />

      {state.phase !== 'ready' ? (
        <p
          className={state.phase === 'error' ? 'error-panel' : 'runtime-card'}
          role={state.phase === 'error' ? 'alert' : 'status'}
        >
          {statusCopy(locale, state.phase)}
        </p>
      ) : state.jobs.length === 0 ? (
        <p className="runtime-card" role="status">
          {formatMessage(locale, 'attention.empty', {})}
        </p>
      ) : (
        <>
          {state.observedAt && (
            <p className="attention-observed">
              {formatMessage(locale, 'attention.observed', {})}{' '}
              {formatDate(locale, state.observedAt, {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
            </p>
          )}
          <ol className="attention-list">
            {state.jobs.map((job) => (
              <li className="runtime-card attention-item" key={job.id}>
                <h2>
                  <SafeTechnicalValue
                    fallback={formatMessage(locale, 'attention.unknown', {})}
                    value={job.type}
                  />
                </h2>
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
                        value={job.id}
                      />
                    </dd>
                  </div>
                  {job.error_code && (
                    <div>
                      <dt>{formatMessage(locale, 'attention.reason', {})}</dt>
                      <dd>
                        <SafeTechnicalValue
                          fallback={formatMessage(
                            locale,
                            'attention.unknown',
                            {},
                          )}
                          value={job.error_code}
                        />
                      </dd>
                    </div>
                  )}
                </dl>
                {job.project_id && PROJECT_ID.test(job.project_id) ? (
                  <Link to={`/projects/${job.project_id}`}>
                    {formatMessage(locale, 'attention.project', {})}{' '}
                    <SafeTechnicalValue
                      fallback={formatMessage(locale, 'attention.unknown', {})}
                      value={job.project_id}
                    />
                  </Link>
                ) : (
                  <p>{formatMessage(locale, 'attention.unlinked', {})}</p>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  )
}
