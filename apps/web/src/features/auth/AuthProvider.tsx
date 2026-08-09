import { ReactNode, useEffect, useMemo, useState } from 'react'

import { ApiClient, ApiError } from '../../lib/api'
import { AuthData, AuthEnvelope, parseAuthEnvelope } from '../../lib/contracts'
import { AuthContext, AuthStatus } from './AuthContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('checking')
  const [auth, setAuth] = useState<AuthData | null>(null)
  const api = useMemo(
    () =>
      new ApiClient(() => {
        setAuth(null)
        setStatus('unauthenticated')
      }),
    [],
  )

  async function refresh(): Promise<AuthData | null> {
    try {
      const response = await api.get<AuthEnvelope>('/api/v1/auth/me', {
        suppressUnauthorizedRecovery: true,
        validate: parseAuthEnvelope,
      })
      setAuth(response.data)
      setStatus('authenticated')
      return response.data
    } catch (error) {
      setAuth(null)
      setStatus('unauthenticated')
      if (error instanceof ApiError && error.status === 401) return null
      throw error
    }
  }

  useEffect(() => {
    let active = true
    void api
      .get<AuthEnvelope>('/api/v1/auth/me', {
        suppressUnauthorizedRecovery: true,
        validate: parseAuthEnvelope,
      })
      .then((response) => {
        if (active) {
          setAuth(response.data)
          setStatus('authenticated')
        }
      })
      .catch(() => {
        if (active) {
          setAuth(null)
          setStatus('unauthenticated')
        }
      })
    return () => {
      active = false
    }
  }, [api])

  async function login(username: string, password: string): Promise<void> {
    const response = await api.post<AuthEnvelope>('/api/v1/auth/login', {
      body: { username, password },
      suppressUnauthorizedRecovery: true,
      validate: parseAuthEnvelope,
    })
    setAuth(response.data)
    setStatus('authenticated')
  }

  async function logout(): Promise<void> {
    if (!auth) return
    try {
      await api.post<void>('/api/v1/auth/logout', {
        csrfToken: auth.csrf_token,
        suppressUnauthorizedRecovery: true,
      })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setAuth(null)
        setStatus('unauthenticated')
        return
      }
      if (!(error instanceof ApiError) || error.status !== 403) throw error

      const refreshed = await refresh()
      if (!refreshed) return
      try {
        await api.post<void>('/api/v1/auth/logout', {
          csrfToken: refreshed.csrf_token,
          suppressUnauthorizedRecovery: true,
        })
      } catch (retryError) {
        if (retryError instanceof ApiError && retryError.status === 401) {
          setAuth(null)
          setStatus('unauthenticated')
          return
        }
        throw retryError
      }
    }
    setAuth(null)
    setStatus('unauthenticated')
  }

  return (
    <AuthContext.Provider value={{ api, auth, login, logout, refresh, status }}>
      {children}
    </AuthContext.Provider>
  )
}
