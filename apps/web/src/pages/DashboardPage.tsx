import { Activity, Bot, Boxes, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { OpaqueUserValue, TechnicalValue } from '../components/i18n'
import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, formatDate, technicalValue, type Locale } from '../i18n'
import {
  dashboardCatalog,
  type DashboardMessageParameters,
} from '../i18n/catalogs/dashboard'
import {
  HealthResponse,
  MetaResponse,
  parseHealthResponse,
  parseMetaResponse,
  parseReadinessResponse,
  ReadinessResponse,
} from '../lib/contracts'

type DashboardMessageKey = keyof DashboardMessageParameters
type DashboardSummary = 'checking' | 'healthy' | 'degraded' | 'unavailable'

const SUMMARY_MESSAGE_KEYS = {
  checking: 'dashboard.checking',
  healthy: 'dashboard.healthy',
  degraded: 'dashboard.degraded',
  unavailable: 'dashboard.unavailable',
} as const satisfies Record<DashboardSummary, DashboardMessageKey>

type DashboardData = {
  health: HealthResponse | null
  meta: MetaResponse | null
  readiness: ReadinessResponse | null
}

function safeTechnicalValue(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null
  try {
    return technicalValue(value).value
  } catch {
    return null
  }
}

function formatSessionExpiry(
  locale: Locale,
  value: string | undefined,
): string | null {
  if (value === undefined) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return formatDate(locale, date, { dateStyle: 'medium', timeStyle: 'short' })
}

export function DashboardPage({ locale }: { locale?: Locale }) {
  const { api, auth } = useAuth()
  const selectedLocale = locale ?? currentLocale()
  const catalog = dashboardCatalog.catalogs[selectedLocale]
  const message = (key: DashboardMessageKey) => catalog[key]({})
  const [data, setData] = useState<DashboardData>({
    health: null,
    meta: null,
    readiness: null,
  })
  const [loading, setLoading] = useState(true)
  usePageTitle(message('dashboard.title'))

  useEffect(() => {
    const controller = new AbortController()
    void Promise.allSettled([
      api.get<HealthResponse>('/healthz', {
        signal: controller.signal,
        validate: parseHealthResponse,
      }),
      api.get<ReadinessResponse>('/readyz', {
        acceptStatuses: [503],
        signal: controller.signal,
        validate: parseReadinessResponse,
      }),
      api.get<MetaResponse>('/api/v1/meta', {
        signal: controller.signal,
        validate: parseMetaResponse,
      }),
    ]).then(([health, readiness, meta]) => {
      if (controller.signal.aborted) return
      setData({
        health: health.status === 'fulfilled' ? health.value : null,
        readiness: readiness.status === 'fulfilled' ? readiness.value : null,
        meta: meta.status === 'fulfilled' ? meta.value : null,
      })
      setLoading(false)
    })
    return () => controller.abort()
  }, [api])

  const ready = data.readiness?.status === 'ready'
  const summary: DashboardSummary = loading
    ? 'checking'
    : data.health === null
      ? 'unavailable'
      : ready && data.meta !== null
        ? 'healthy'
        : 'degraded'
  const summaryTone =
    summary === 'healthy'
      ? 'good'
      : summary === 'checking'
        ? 'muted'
        : 'warning'
  const summaryMessage = message(SUMMARY_MESSAGE_KEYS[summary])
  const healthMessage = message(
    loading
      ? 'dashboard.checking'
      : data.health
        ? 'dashboard.healthy'
        : 'dashboard.unavailable',
  )
  const readinessMessage = message(
    loading
      ? 'dashboard.checking'
      : ready
        ? 'dashboard.ready'
        : 'dashboard.notReady',
  )
  const version = safeTechnicalValue(data.meta?.version)
  const apiVersion = safeTechnicalValue(data.meta?.api_version)
  const environment = safeTechnicalValue(data.meta?.environment)
  const sessionExpiry = formatSessionExpiry(
    selectedLocale,
    auth?.session.expires_at,
  )

  return (
    <>
      <PageHeader
        action={<StatusBadge tone={summaryTone}>{summaryMessage}</StatusBadge>}
        description={message('dashboard.description')}
        eyebrow={message('dashboard.eyebrow')}
        title={message('dashboard.title')}
      />

      <section
        className="metric-grid"
        aria-label={message('dashboard.statusAria')}
      >
        <article className="metric-card">
          <Activity aria-hidden="true" />
          <span>{message('dashboard.controlPlane')}</span>
          <strong>{healthMessage}</strong>
          <StatusBadge tone={data.health ? 'good' : 'warning'}>
            {healthMessage}
          </StatusBadge>
        </article>
        <article className="metric-card">
          <Activity aria-hidden="true" />
          <span>{message('dashboard.readiness')}</span>
          <strong>{readinessMessage}</strong>
          <StatusBadge tone={ready ? 'good' : 'warning'}>
            {readinessMessage}
          </StatusBadge>
        </article>
        <article className="metric-card">
          <Boxes aria-hidden="true" />
          <span>{message('dashboard.agentboxVersion')}</span>
          <strong>
            {version ? (
              <TechnicalValue value={version} />
            ) : (
              message('dashboard.unavailable')
            )}
          </strong>
          <small>
            {message('dashboard.apiVersion')}{' '}
            {apiVersion ? (
              <TechnicalValue value={apiVersion} />
            ) : (
              message('dashboard.unavailable')
            )}
          </small>
        </article>
        <article className="metric-card">
          <Bot aria-hidden="true" />
          <span>{message('dashboard.administrator')}</span>
          <strong>
            {auth ? (
              <OpaqueUserValue value={auth.user.username} />
            ) : (
              message('dashboard.unavailable')
            )}
          </strong>
          <small>
            {message('dashboard.sessionExpires')}{' '}
            {sessionExpiry ?? message('dashboard.unavailable')}
          </small>
        </article>
      </section>

      <section className="section-heading">
        <div>
          <p className="eyebrow">
            {message('dashboard.currentCapabilitiesEyebrow')}
          </p>
          <h2>{message('dashboard.currentCapabilitiesTitle')}</h2>
        </div>
        <StatusBadge>
          {message('dashboard.currentCapabilitiesStatus')}
        </StatusBadge>
      </section>
      <section className="planned-grid">
        {[
          {
            icon: Bot,
            title: message('dashboard.codexTitle'),
            copy: message('dashboard.codexDescription'),
          },
          {
            icon: Sparkles,
            title: message('dashboard.claudeTitle'),
            copy: message('dashboard.claudeDescription'),
          },
          {
            icon: Boxes,
            title: message('dashboard.projectsTitle'),
            copy: message('dashboard.projectsDescription'),
          },
        ].map(({ icon: Icon, title, copy }) => (
          <article className="planned-card" key={title}>
            <Icon aria-hidden="true" size={21} />
            <StatusBadge>
              {message('dashboard.currentCapabilitiesStatus')}
            </StatusBadge>
            <h2>{title}</h2>
            <p>{copy}</p>
          </article>
        ))}
      </section>

      <section className="detail-strip">
        <div>
          <span>{message('dashboard.environment')}</span>
          <strong>
            {environment ? (
              <TechnicalValue value={environment} />
            ) : (
              message('dashboard.unavailable')
            )}
          </strong>
        </div>
        <div>
          <span>{message('dashboard.database')}</span>
          <strong>
            {data.readiness?.checks.database
              ? message('dashboard.ready')
              : message('dashboard.notReady')}
          </strong>
        </div>
        <div>
          <span>{message('dashboard.migrations')}</span>
          <strong>
            {data.readiness?.checks.migrations
              ? message('dashboard.ready')
              : message('dashboard.notReady')}
          </strong>
        </div>
      </section>
    </>
  )
}
