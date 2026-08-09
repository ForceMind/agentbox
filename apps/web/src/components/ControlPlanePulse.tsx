import { useEffect, useState } from 'react'

import { useAuth } from '../features/auth/AuthContext'
import { HealthResponse, parseHealthResponse } from '../lib/contracts'

type State = 'checking' | 'healthy' | 'unavailable'

export function ControlPlanePulse() {
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

  const label = {
    checking: 'Checking',
    healthy: 'Healthy',
    unavailable: 'Unavailable',
  }[state]

  return (
    <span
      className={`control-pulse pulse-${state}`}
      aria-label={`Control plane: ${label}`}
    >
      <span aria-hidden="true" />
      {label}
    </span>
  )
}
