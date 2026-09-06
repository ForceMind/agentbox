import { LocalizedApiError, TechnicalValue } from '../components/i18n'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useDoctor } from '../features/doctor/useDoctor'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  currentLocale,
  formatMessage,
  formatNumber,
  type Locale,
} from '../i18n'
import {
  settingsCatalog,
  type SettingsMessageParameters,
} from '../i18n/catalogs/settings'

type SettingsMessageKey = Exclude<
  keyof SettingsMessageParameters,
  | 'settings.loginRateLimit'
  | 'settings.hours'
  | 'settings.minutes'
  | 'settings.seconds'
>

function formatDuration(locale: Locale, seconds: number): string {
  if (seconds % 3600 === 0) {
    return formatMessage(locale, 'settings.hours', { count: seconds / 3600 })
  }
  if (seconds % 60 === 0) {
    return formatMessage(locale, 'settings.minutes', { count: seconds / 60 })
  }
  return formatMessage(locale, 'settings.seconds', { count: seconds })
}

export function SettingsPage({
  locale = currentLocale(),
}: {
  locale?: Locale
}) {
  const doctor = useDoctor()
  const catalog = settingsCatalog.catalogs[locale]
  const message = (key: SettingsMessageKey) => catalog[key]({})
  const bindHost =
    doctor.status === 'loaded' ? doctor.response.data.policy.bind_host : null
  usePageTitle(message('settings.title'))

  return (
    <>
      <PageHeader
        action={<StatusBadge>{message('settings.readOnly')}</StatusBadge>}
        description={message('settings.description')}
        eyebrow={message('settings.eyebrow')}
        title={message('settings.title')}
      />
      {doctor.status === 'loading' && (
        <p className="loading-panel" role="status">
          {message('settings.loading')}
        </p>
      )}
      {doctor.status === 'error' && (
        <p className="error-panel" role="alert">
          <LocalizedApiError error={doctor.error} locale={locale} role="none" />
        </p>
      )}
      {doctor.status === 'loaded' && (
        <dl className="settings-list">
          <div>
            <dt>{message('settings.environment')}</dt>
            <dd>
              <TechnicalValue value={doctor.response.data.policy.environment} />
            </dd>
          </div>
          <div>
            <dt>{message('settings.bindAddress')}</dt>
            <dd>
              {bindHost === null ? (
                message('settings.unavailable')
              ) : (
                <>
                  <TechnicalValue value={bindHost} />:{' '}
                  {formatNumber(locale, doctor.response.data.policy.bind_port)}
                </>
              )}
            </dd>
          </div>
          <div>
            <dt>{message('settings.absoluteSessionLifetime')}</dt>
            <dd>
              {formatDuration(
                locale,
                doctor.response.data.policy.session_ttl_seconds,
              )}
            </dd>
          </div>
          <div>
            <dt>{message('settings.idleSessionLifetime')}</dt>
            <dd>
              {formatDuration(
                locale,
                doctor.response.data.policy.session_idle_ttl_seconds,
              )}
            </dd>
          </div>
          <div>
            <dt>{message('settings.loginRateLimitLabel')}</dt>
            <dd>
              {catalog['settings.loginRateLimit']({
                count: formatNumber(
                  locale,
                  doctor.response.data.policy.login_rate_limit,
                ),
                duration: formatDuration(
                  locale,
                  doctor.response.data.policy.login_rate_window_seconds,
                ),
              })}
            </dd>
          </div>
          <div>
            <dt>{message('settings.loginLockDuration')}</dt>
            <dd>
              {formatDuration(
                locale,
                doctor.response.data.policy.login_lock_duration_seconds,
              )}
            </dd>
          </div>
        </dl>
      )}
      <p className="scope-note">{message('settings.scopeNote')}</p>
    </>
  )
}
