import { useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../../lib/api'
import { DoctorResponse, parseDoctorResponse } from '../../lib/contracts'

type DoctorState =
  | { status: 'loading' }
  | { status: 'loaded'; response: DoctorResponse }
  | { status: 'error'; error: ApiError }

export function useDoctor(): DoctorState {
  const { api } = useAuth()
  const [state, setState] = useState<DoctorState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void api
      .get<DoctorResponse>('/api/v1/doctor', {
        signal: controller.signal,
        timeoutMs: 90_000,
        validate: parseDoctorResponse,
      })
      .then((response) => setState({ status: 'loaded', response }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            error:
              error instanceof ApiError
                ? error
                : new ApiError({
                    code: 'DOCTOR_UNAVAILABLE',
                    message: 'Control-plane diagnostics are unavailable',
                    status: 0,
                  }),
          })
        }
      })
    return () => controller.abort()
  }, [api])

  return state
}
