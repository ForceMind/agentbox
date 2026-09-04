import { useEffect, useState } from 'react'

import { useAuth } from '../features/auth/AuthContext'
import { currentLocale, type Locale } from '../i18n'
import { HealthResponse, parseHealthResponse } from '../lib/contracts'

type State = 'checking' | 'healthy' | 'unavailable'

const COPY = {
  en: {
    checking: 'Checking',
    healthy: 'Healthy',
    unavailable: 'Unavailable',
    prefix: 'Control plane',
  },
  'zh-CN': {
    checking: '检查中',
    healthy: '正常',
    unavailable: '不可用',
    prefix: '控制平面',
  },
} as const satisfies Record<Locale, Record<State | 'prefix', string>>

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

  const copy = COPY[locale]
  const label = copy[state]

  return (
    <span
      className={`control-pulse pulse-${state}`}
      aria-label={`${copy.prefix}: ${label}`}
    >
      <span aria-hidden="true" />
      {label}
    </span>
  )
}
