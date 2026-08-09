import { Activity, Bot, Boxes, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  HealthResponse,
  MetaResponse,
  parseHealthResponse,
  parseMetaResponse,
  parseReadinessResponse,
  ReadinessResponse,
} from '../lib/contracts'

type DashboardData = {
  health: HealthResponse | null
  meta: MetaResponse | null
  readiness: ReadinessResponse | null
}

export function DashboardPage() {
  const { api, auth } = useAuth()
  const [data, setData] = useState<DashboardData>({
    health: null,
    meta: null,
    readiness: null,
  })
  const [loading, setLoading] = useState(true)
  usePageTitle('Dashboard')

  useEffect(() => {
    const controller = new AbortController()
    void Promise.allSettled([
      api.get<HealthResponse>('/healthz', {
        signal: controller.signal,
        validate: parseHealthResponse,
      }),
      api.get<ReadinessResponse>('/readyz', {
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

  return (
    <>
      <PageHeader
        description="A truthful view of the control-plane foundation available today."
        eyebrow="Workstation overview"
        title="Dashboard"
      />

      <section className="metric-grid" aria-label="Control plane status">
        <article className="metric-card">
          <Activity aria-hidden="true" />
          <span>Control Plane</span>
          <strong>
            {loading ? 'Checking' : data.health ? 'Healthy' : 'Unavailable'}
          </strong>
          <StatusBadge tone={data.health ? 'good' : 'warning'}>
            {data.health ? 'Healthy' : loading ? 'Checking' : 'Unavailable'}
          </StatusBadge>
        </article>
        <article className="metric-card">
          <Activity aria-hidden="true" />
          <span>Readiness</span>
          <strong>
            {loading ? 'Checking' : ready ? 'Ready' : 'Not Ready'}
          </strong>
          <StatusBadge tone={ready ? 'good' : 'warning'}>
            {loading ? 'Checking' : ready ? 'Ready' : 'Not Ready'}
          </StatusBadge>
        </article>
        <article className="metric-card">
          <Boxes aria-hidden="true" />
          <span>AgentBox version</span>
          <strong>{data.meta?.version ?? 'Unavailable'}</strong>
          <small>API {data.meta?.api_version ?? 'unavailable'}</small>
        </article>
        <article className="metric-card">
          <Bot aria-hidden="true" />
          <span>Administrator</span>
          <strong>{auth?.user.username ?? 'Unavailable'}</strong>
          <small>
            Session expires{' '}
            {auth
              ? new Date(auth.session.expires_at).toLocaleString()
              : 'unavailable'}
          </small>
        </article>
      </section>

      <section className="section-heading">
        <div>
          <p className="eyebrow">Future runtime surfaces</p>
          <h2>Planned capabilities</h2>
        </div>
        <StatusBadge>Not Implemented</StatusBadge>
      </section>
      <section className="planned-grid">
        {[
          {
            icon: Bot,
            title: 'Codex',
            copy: 'Remote daemon and pairing controls arrive in a later phase.',
          },
          {
            icon: Sparkles,
            title: 'Claude',
            copy: 'Persistent remote sessions are not connected in Phase 4.',
          },
          {
            icon: Boxes,
            title: 'Projects',
            copy: 'No workspace or Git operations are available yet.',
          },
        ].map(({ icon: Icon, title, copy }) => (
          <article className="planned-card" key={title}>
            <Icon aria-hidden="true" size={21} />
            <StatusBadge>Planned</StatusBadge>
            <h2>{title}</h2>
            <p>{copy}</p>
          </article>
        ))}
      </section>

      <section className="detail-strip">
        <div>
          <span>Environment</span>
          <strong>{data.meta?.environment ?? 'Unavailable'}</strong>
        </div>
        <div>
          <span>Database</span>
          <strong>
            {data.readiness?.checks.database ? 'Ready' : 'Not Ready'}
          </strong>
        </div>
        <div>
          <span>Migrations</span>
          <strong>
            {data.readiness?.checks.migrations ? 'Ready' : 'Not Ready'}
          </strong>
        </div>
      </section>
    </>
  )
}
