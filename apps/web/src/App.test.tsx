import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

const authenticated = {
  api_version: 'v1',
  request_id: 'req_test',
  data: {
    user: { id: 'adm_test', username: 'maintainer' },
    session: { id: 'ses_test', expires_at: '2026-08-10T00:00:00Z' },
    csrf_token: 'csrf-test-value',
  },
}

function jsonResponse(status: number, body?: object, headers?: HeadersInit) {
  return new Response(status === 204 ? null : JSON.stringify(body ?? {}), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function unauthenticatedFetch(input: RequestInfo | URL) {
  const path = input.toString()
  if (path.endsWith('/healthz'))
    return Promise.resolve(jsonResponse(200, { status: 'ok' }))
  return Promise.resolve(
    jsonResponse(401, {
      request_id: 'req_unauthenticated',
      error: {
        code: 'AUTH_SESSION_INVALID',
        message: 'Authentication required',
      },
    }),
  )
}

function authenticatedFetch(input: RequestInfo | URL, init?: RequestInit) {
  const path = input.toString()
  if (path.endsWith('/auth/me'))
    return Promise.resolve(jsonResponse(200, authenticated))
  if (path.endsWith('/healthz'))
    return Promise.resolve(jsonResponse(200, { status: 'ok' }))
  if (path.endsWith('/readyz')) {
    return Promise.resolve(
      jsonResponse(200, {
        status: 'ready',
        checks: { database: true, migrations: true },
      }),
    )
  }
  if (path.endsWith('/api/v1/meta')) {
    return Promise.resolve(
      jsonResponse(200, {
        name: 'AgentBox',
        version: '0.1.0-dev.0',
        api_version: 'v1',
        environment: 'test',
      }),
    )
  }
  if (path.endsWith('/auth/logout')) {
    expect(init?.credentials).toBe('include')
    return Promise.resolve(jsonResponse(204))
  }
  return Promise.resolve(jsonResponse(404))
}

describe('AgentBox authenticated Web foundation', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps protected routes behind session recovery', async () => {
    window.history.replaceState({}, '', '/dashboard')
    vi.stubGlobal('fetch', vi.fn(unauthenticatedFetch))

    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent(
      'Restoring your session',
    )
    expect(
      await screen.findByRole('heading', {
        name: 'Sign in to manage this workstation',
      }),
    ).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
  })

  it('renders accessible login fields and blocks an empty submission', async () => {
    window.history.replaceState({}, '', '/login')
    const fetchMock = vi.fn(unauthenticatedFetch)
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    const button = await screen.findByRole('button', { name: 'Sign in' })
    expect(screen.getByLabelText('Username')).toHaveAttribute(
      'autocomplete',
      'username',
    )
    expect(screen.getByLabelText('Password')).toHaveAttribute(
      'type',
      'password',
    )
    expect(button).toBeDisabled()
  })

  it('logs in, clears password state, and reaches the truthful Dashboard', async () => {
    window.history.replaceState({}, '', '/login')
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = input.toString()
      if (path.endsWith('/auth/login')) {
        expect(init?.credentials).toBe('include')
        return Promise.resolve(jsonResponse(200, authenticated))
      }
      if (path.endsWith('/auth/me')) return unauthenticatedFetch(input)
      return authenticatedFetch(input, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.change(await screen.findByLabelText('Username'), {
      target: { value: 'maintainer' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'a sufficiently long passphrase' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(
      await screen.findByRole('heading', { name: 'Dashboard' }),
    ).toBeInTheDocument()
    expect(screen.getAllByText('maintainer').length).toBeGreaterThan(0)
    expect(
      screen.queryByDisplayValue('a sufficiently long passphrase'),
    ).not.toBeInTheDocument()
    expect(window.location.pathname).toBe('/dashboard')
  })

  it('shows generic invalid credentials with a safe request id', async () => {
    window.history.replaceState({}, '', '/login')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (input.toString().endsWith('/auth/login')) {
          return Promise.resolve(
            jsonResponse(401, {
              request_id: 'req_login-123',
              error: {
                code: 'AUTH_INVALID_CREDENTIALS',
                message: 'Invalid credentials',
              },
            }),
          )
        }
        return unauthenticatedFetch(input)
      }),
    )

    render(<App />)
    fireEvent.change(await screen.findByLabelText('Username'), {
      target: { value: 'nobody' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'wrong password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Invalid credentials',
    )
    fireEvent.click(screen.getByText('Request details'))
    expect(screen.getByText('req_login-123')).toBeInTheDocument()
  })

  it('shows bounded rate-limit guidance', async () => {
    window.history.replaceState({}, '', '/login')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        input.toString().endsWith('/auth/login')
          ? Promise.resolve(
              jsonResponse(
                429,
                {
                  request_id: 'req_rate',
                  error: { code: 'AUTH_RATE_LIMITED', message: 'Rate limited' },
                },
                { 'Retry-After': '73' },
              ),
            )
          : unauthenticatedFetch(input),
      ),
    )

    render(<App />)
    fireEvent.change(await screen.findByLabelText('Username'), {
      target: { value: 'maintainer' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'wrong password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many failed attempts',
    )
    expect(screen.getByRole('alert')).toHaveTextContent(
      'approximately 73 seconds',
    )
  })

  it('restores an authenticated session and redirects /login to Dashboard', async () => {
    window.history.replaceState({}, '', '/login')
    vi.stubGlobal('fetch', vi.fn(authenticatedFetch))

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'Dashboard' }),
    ).toBeInTheDocument()
    expect(window.location.pathname).toBe('/dashboard')
  })

  it('navigates through the product shell without inventing runtime state', async () => {
    window.history.replaceState({}, '', '/dashboard')
    vi.stubGlobal('fetch', vi.fn(authenticatedFetch))
    render(<App />)

    fireEvent.click(await screen.findByRole('link', { name: 'Codex' }))
    expect(
      await screen.findByRole('heading', { name: 'Codex' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Not implemented yet')).toBeInTheDocument()
    expect(screen.queryByText('Online')).not.toBeInTheDocument()
  })

  it('uses the current session CSRF token when logging out', async () => {
    window.history.replaceState({}, '', '/dashboard')
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (input.toString().endsWith('/auth/logout')) {
        expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe(
          'csrf-test-value',
        )
      }
      return authenticatedFetch(input, init)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(
      await screen.findByRole('heading', {
        name: 'Sign in to manage this workstation',
      }),
    ).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
  })

  it('refreshes CSRF once after a stale-token rejection', async () => {
    window.history.replaceState({}, '', '/dashboard')
    const refreshed = {
      ...authenticated,
      data: { ...authenticated.data, csrf_token: 'csrf-refreshed-value' },
    }
    let meCalls = 0
    let logoutCalls = 0
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = input.toString()
      if (path.endsWith('/auth/me')) {
        meCalls += 1
        return Promise.resolve(
          jsonResponse(200, meCalls === 1 ? authenticated : refreshed),
        )
      }
      if (path.endsWith('/auth/logout')) {
        logoutCalls += 1
        const token = (init?.headers as Record<string, string>)['X-CSRF-Token']
        if (logoutCalls === 1) {
          expect(token).toBe('csrf-test-value')
          return Promise.resolve(
            jsonResponse(403, {
              request_id: 'req_csrf',
              error: {
                code: 'AUTH_CSRF_INVALID',
                message: 'CSRF validation failed',
              },
            }),
          )
        }
        expect(token).toBe('csrf-refreshed-value')
        return Promise.resolve(jsonResponse(204))
      }
      return authenticatedFetch(input, init)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(
      await screen.findByRole('heading', {
        name: 'Sign in to manage this workstation',
      }),
    ).toBeInTheDocument()
    expect(logoutCalls).toBe(2)
    expect(meCalls).toBe(2)
  })

  it('clears stale auth after a protected API returns 401', async () => {
    window.history.replaceState({}, '', '/dashboard')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input.toString()
        if (path.endsWith('/auth/me'))
          return Promise.resolve(jsonResponse(200, authenticated))
        if (path.endsWith('/readyz')) {
          return Promise.resolve(
            jsonResponse(401, {
              request_id: 'req_expired',
              error: {
                code: 'AUTH_SESSION_INVALID',
                message: 'Authentication required',
              },
            }),
          )
        }
        return authenticatedFetch(input)
      }),
    )

    render(<App />)

    expect(
      await screen.findByRole('heading', {
        name: 'Sign in to manage this workstation',
      }),
    ).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
  })

  it('never persists session or CSRF state in browser storage', async () => {
    window.history.replaceState({}, '', '/dashboard')
    vi.stubGlobal('fetch', vi.fn(authenticatedFetch))
    render(<App />)

    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(window.localStorage).toHaveLength(0)
    expect(window.sessionStorage).toHaveLength(0)
  })
})
