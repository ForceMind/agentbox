import { useEffect, useState } from 'react'

import { useAuth } from '../features/auth/AuthContext'
import { currentLocale, formatMessage, type Locale } from '../i18n'
import { HealthResponse, parseHealthResponse } from '../lib/contracts'

type State = 'checking' | 'healthy' | 'unavailable'

export function ControlPlanePulse({
  locale = currentLocale(),
}: {
  locale?: Locale
} = {}) {
  const { api } = useAuth()
  const [state, setState] = useState<State>('checking')

  useEffect(() => {
    const controller = new AbortController()
    void api
      .get<HealthResponse>('/healthz', {
        signal: controller.signal,
        validate: parseHealthResponse,
      })
      .then((result) =>
        setState(result.status === 'ok' ? 'healthy' : 'unavailable'),
      )
      .catch(() => {
        if (!controller.signal.aborted) setState('unavailable')
      })
    return () => controller.abort()
  }, [api])

  const label =
    state === 'checking'
      ? formatMessage(locale, 'shell.healthChecking', {})
      : state === 'healthy'
        ? formatMessage(locale, 'shell.healthHealthy', {})
        : formatMessage(locale, 'shell.healthUnavailable', {})

  return (
    <span
      className={`control-pulse pulse-${state}`}
      aria-label={formatMessage(locale, 'shell.controlPlaneStatus', {
        status: label,
      })}
    >
      <span aria-hidden="true" />
      {label}
    </span>
  )
}
