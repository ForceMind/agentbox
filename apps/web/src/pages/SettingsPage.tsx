import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useDoctor } from '../features/doctor/useDoctor'
import { usePageTitle } from '../hooks/usePageTitle'

function duration(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600} hours`
  if (seconds % 60 === 0) return `${seconds / 60} minutes`
  return `${seconds} seconds`
}

export function SettingsPage() {
  const doctor = useDoctor()
  usePageTitle('Settings')

  return (
    <>
      <PageHeader
        action={<StatusBadge>Read Only</StatusBadge>}
        description="A safe summary of active control-plane policy."
        eyebrow="Control plane"
        title="Settings"
      />
      {doctor.status === 'loading' && (
        <p className="loading-panel" role="status">
          Loading safe settings…
        </p>
      )}
      {doctor.status === 'error' && (
        <p className="error-panel" role="alert">
          {doctor.error.message}
        </p>
      )}
      {doctor.status === 'loaded' && (
        <dl className="settings-list">
          <div>
            <dt>Environment</dt>
            <dd>{doctor.response.data.policy.environment}</dd>
          </div>
          <div>
            <dt>Bind address</dt>
            <dd>
              {doctor.response.data.policy.bind_host}:
              {doctor.response.data.policy.bind_port}
            </dd>
          </div>
          <div>
            <dt>Absolute session lifetime</dt>
            <dd>{duration(doctor.response.data.policy.session_ttl_seconds)}</dd>
          </div>
          <div>
            <dt>Idle session lifetime</dt>
            <dd>
              {duration(doctor.response.data.policy.session_idle_ttl_seconds)}
            </dd>
          </div>
          <div>
            <dt>Login rate limit</dt>
            <dd>
              {doctor.response.data.policy.login_rate_limit} failures per{' '}
              {duration(doctor.response.data.policy.login_rate_window_seconds)}
            </dd>
          </div>
          <div>
            <dt>Login lock duration</dt>
            <dd>
              {duration(
                doctor.response.data.policy.login_lock_duration_seconds,
              )}
            </dd>
          </div>
        </dl>
      )}
      <p className="scope-note">
        Secrets, database URLs, filesystem paths, and credential state are never
        exposed here. Editing settings arrives in a later phase.
      </p>
    </>
  )
}
