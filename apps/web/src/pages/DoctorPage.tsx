import { Activity, Check, X } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useDoctor } from '../features/doctor/useDoctor'
import { usePageTitle } from '../hooks/usePageTitle'

const labels = {
  configuration_valid: 'Configuration valid',
  database_reachable: 'Database reachable',
  migrations_current: 'Migration state current',
  admin_initialized: 'Administrator initialized',
  control_plane_ready: 'Control plane ready',
} as const

export function DoctorPage() {
  const doctor = useDoctor()
  usePageTitle('Doctor')

  return (
    <>
      <PageHeader
        action={
          doctor.status === 'loaded' ? (
            <StatusBadge
              tone={
                doctor.response.data.status === 'ready' ? 'good' : 'warning'
              }
            >
              {doctor.response.data.status === 'ready' ? 'Ready' : 'Not Ready'}
            </StatusBadge>
          ) : undefined
        }
        description="Read-only checks for AgentBox's own control-plane foundation."
        eyebrow="Diagnostics"
        title="Doctor"
      />

      {doctor.status === 'loading' && (
        <p className="loading-panel" role="status">
          Running safe checks…
        </p>
      )}
      {doctor.status === 'error' && (
        <section className="error-panel" role="alert">
          <Activity aria-hidden="true" />
          <div>
            <h2>Diagnostics unavailable</h2>
            <p>{doctor.error.message}</p>
          </div>
        </section>
      )}
      {doctor.status === 'loaded' && (
        <>
          <section className="check-list" aria-label="Control plane checks">
            {Object.entries(doctor.response.data.checks).map(([key, value]) => (
              <article key={key}>
                <span
                  className={value ? 'check-icon good' : 'check-icon bad'}
                  aria-hidden="true"
                >
                  {value ? <Check size={17} /> : <X size={17} />}
                </span>
                <span>{labels[key as keyof typeof labels]}</span>
                <StatusBadge tone={value ? 'good' : 'warning'}>
                  {value ? 'Ready' : 'Not Ready'}
                </StatusBadge>
              </article>
            ))}
          </section>
          <p className="scope-note">
            These checks do not inspect Codex, Claude, tmux, GitHub, systemd, or
            host networking. Those capabilities are outside Phase 4.
          </p>
        </>
      )}
    </>
  )
}
