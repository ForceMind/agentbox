import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import type { AuthEnvelope } from './lib/contracts'
import {
  doctorResponse,
  heldResponse,
  jsonResponse,
} from './test/doctorFixtures'

const auth: AuthEnvelope = {
  api_version: 'v1',
  request_id: 'req_admin_auth_fixture',
  data: {
    user: { id: 'adm_admin_fixture', username: 'admin-fixture' },
    session: {
      id: 'ses_admin_fixture',
      expires_at: '2026-10-08T00:00:00Z',
    },
    csrf_token: 'csrf-admin-fixture',
  },
}

function fixture(
  health: Response | Promise<Response> = jsonResponse({ status: 'ok' }),
) {
  const doctorReads: Array<
    ReturnType<typeof heldResponse> & { signal: AbortSignal }
  > = []
  const requests: Array<{ path: string; method: string }> = []
  const trace: string[] = []
  let healthReads = 0
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = input.toString()
      const method = init?.method ?? 'GET'
      requests.push({ path, method })
      if (method !== 'GET')
        throw new Error(`Unexpected fixture mutation: ${method} ${path}`)
      if (path === '/api/v1/auth/me') return Promise.resolve(jsonResponse(auth))
      if (path === '/healthz') {
        healthReads += 1
        // The public LoginPage mounts its own pulse after protected shell exit.
        return Promise.resolve(
          healthReads === 1 ? health : jsonResponse({ status: 'ok' }),
        )
      }
      if (path === '/api/v1/doctor' && init?.signal) {
        const index = doctorReads.length + 1
        const held = { ...heldResponse(), signal: init.signal }
        doctorReads.push(held)
        trace.push(`doctor:${index}:start`)
        init.signal.addEventListener(
          'abort',
          () => trace.push(`doctor:${index}:abort`),
          { once: true },
        )
        // Deliberately deliver even after abort, exercising the hook's late-result fence.
        return held.promise
      }
      throw new Error(`Unexpected fixture request: ${method} ${path}`)
    }),
  )
  return { doctorReads, requests, trace }
}

describe('actual App read-only administration request ownership', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the current Settings policy when the prior Doctor HTTP response arrives', async () => {
    const http = fixture()
    window.history.replaceState({}, '', '/doctor')
    render(<App />)
    await screen.findByRole('heading', { name: 'Doctor', level: 1 })
    await waitFor(() => expect(http.doctorReads).toHaveLength(1))
    fireEvent.click(screen.getByRole('link', { name: 'Settings' }))
    await screen.findByRole('heading', { name: 'Settings', level: 1 })
    await waitFor(() => expect(http.doctorReads).toHaveLength(2))

    const settings = doctorResponse()
    settings.data.policy.environment = 'production'
    settings.data.policy.bind_host = 'current-settings.invalid'
    settings.data.policy.session_ttl_seconds = 3600
    await act(async () => http.doctorReads[1].resolve(jsonResponse(settings)))
    expect(screen.getByText('current-settings.invalid')).toBeVisible()
    expect(screen.getByText('1 hour')).toBeVisible()

    const stale = doctorResponse()
    stale.data.policy.bind_host = 'stale-doctor-policy.invalid'
    stale.data.codex.version = 'STALE-DOCTOR-ONLY-VERSION'
    const late = jsonResponse(stale)
    const parsed = vi.spyOn(late, 'json')
    await act(async () => http.doctorReads[0].resolve(late))
    expect(parsed).toHaveBeenCalledOnce()
    expect(http.doctorReads[0].signal.aborted).toBe(true)
    expect(window.location.pathname).toBe('/settings')
    expect(
      screen.getByRole('heading', { name: 'Settings', level: 1 }),
    ).toBeVisible()
    expect(screen.getByText('production')).toBeVisible()
    expect(screen.getByText('current-settings.invalid')).toBeVisible()
    expect(screen.getByText('1 hour')).toBeVisible()
    expect(screen.getAllByRole('term')).toHaveLength(6)
    expect(document.body).not.toHaveTextContent('stale-doctor-policy.invalid')
    expect(document.body).not.toHaveTextContent('STALE-DOCTOR-ONLY-VERSION')
    expect(http.trace).toEqual([
      'doctor:1:start',
      'doctor:1:abort',
      'doctor:2:start',
    ])
    expect(http.requests.filter(({ path }) => path !== '/healthz')).toEqual([
      { path: '/api/v1/auth/me', method: 'GET' },
      { path: '/api/v1/doctor', method: 'GET' },
      { path: '/api/v1/doctor', method: 'GET' },
    ])
    expect(
      http.requests.filter(({ path }) => path === '/healthz'),
    ).toHaveLength(1)
  })

  it('aborts Doctor → Settings → Back requests and ignores both older HTTP responses', async () => {
    const http = fixture()
    window.history.replaceState({}, '', '/doctor')
    render(<App />)
    await screen.findByRole('heading', { name: 'Doctor', level: 1 })
    await waitFor(() => expect(http.doctorReads).toHaveLength(1))

    fireEvent.click(screen.getByRole('link', { name: 'Settings' }))
    await screen.findByRole('heading', { name: 'Settings', level: 1 })
    await waitFor(() => expect(http.doctorReads).toHaveLength(2))
    expect(http.doctorReads[0].signal.aborted).toBe(true)

    act(() => window.history.back())
    await screen.findByRole('heading', { name: 'Doctor', level: 1 })
    await waitFor(() => expect(http.doctorReads).toHaveLength(3))
    expect(window.location.pathname).toBe('/doctor')
    expect(http.trace).toEqual([
      'doctor:1:start',
      'doctor:1:abort',
      'doctor:2:start',
      'doctor:2:abort',
      'doctor:3:start',
    ])
    expect(http.doctorReads[2].signal.aborted).toBe(false)

    const current = doctorResponse()
    current.data.codex.version = 'CURRENT-DOCTOR-VERSION'
    current.data.projects.project_root = '/Projects/current-doctor'
    await act(async () => http.doctorReads[2].resolve(jsonResponse(current)))
    expect(screen.getByText('CURRENT-DOCTOR-VERSION')).toBeVisible()

    for (const [index, old] of http.doctorReads.slice(0, 2).entries()) {
      const stale = doctorResponse()
      stale.data.codex.version = `STALE-ROUTE-VERSION-${index}`
      stale.data.projects.project_root = `/Projects/stale-route-${index}`
      stale.data.policy.bind_host = `stale-policy-${index}.invalid`
      const response = jsonResponse(stale)
      const parsed = vi.spyOn(response, 'json')
      await act(async () => old.resolve(response))
      expect(parsed).toHaveBeenCalledOnce()
      expect(document.body).not.toHaveTextContent(stale.data.codex.version)
      expect(document.body).not.toHaveTextContent(
        stale.data.projects.project_root,
      )
      expect(document.body).not.toHaveTextContent(stale.data.policy.bind_host)
      expect(screen.getByText('CURRENT-DOCTOR-VERSION')).toBeVisible()
      expect(screen.getByText('/Projects/current-doctor')).toBeVisible()
    }
    expect(http.requests.filter(({ path }) => path !== '/healthz')).toEqual([
      { path: '/api/v1/auth/me', method: 'GET' },
      { path: '/api/v1/doctor', method: 'GET' },
      { path: '/api/v1/doctor', method: 'GET' },
      { path: '/api/v1/doctor', method: 'GET' },
    ])
    expect(
      http.requests.filter(({ path }) => path === '/healthz'),
    ).toHaveLength(1)
  })

  it.each([
    ['/doctor', 'Doctor'],
    ['/settings', 'Settings'],
  ])(
    'keeps %s unmounted after a real 401 even when its pending HTTP result arrives',
    async (path, title) => {
      const health = heldResponse()
      const http = fixture(health.promise)
      window.history.replaceState({}, '', path)
      render(<App />)
      await screen.findByRole('heading', { name: title, level: 1 })
      await waitFor(() => expect(http.doctorReads).toHaveLength(1))
      expect(http.doctorReads[0].signal.aborted).toBe(false)

      await act(async () =>
        health.resolve(
          jsonResponse(
            {
              request_id: 'req_admin_unauthorized',
              error: {
                code: 'AUTH_SESSION_REQUIRED',
                message: 'ADMIN-401-SERVER-PROSE',
              },
            },
            401,
          ),
        ),
      )
      await screen.findByRole('button', { name: 'Sign in' })
      expect(window.location.pathname).toBe('/login')
      expect(http.doctorReads[0].signal.aborted).toBe(true)
      expect(
        screen.queryByRole('heading', { name: title, level: 1 }),
      ).not.toBeInTheDocument()

      const late = doctorResponse()
      late.data.codex.version = 'LATE-PROTECTED-VERSION'
      late.data.policy.bind_host = 'late-protected.invalid'
      const response = jsonResponse(late)
      const parsed = vi.spyOn(response, 'json')
      await act(async () => http.doctorReads[0].resolve(response))
      expect(parsed).toHaveBeenCalledOnce()
      expect(window.location.pathname).toBe('/login')
      expect(screen.getByRole('button', { name: 'Sign in' })).toBeVisible()
      expect(
        screen.queryByRole('heading', { name: title, level: 1 }),
      ).not.toBeInTheDocument()
      expect(document.body).not.toHaveTextContent('LATE-PROTECTED-VERSION')
      expect(document.body).not.toHaveTextContent('late-protected.invalid')
      expect(document.body).not.toHaveTextContent('ADMIN-401-SERVER-PROSE')
      expect(http.trace).toEqual(['doctor:1:start', 'doctor:1:abort'])
      expect(
        http.requests.map(({ path: requestPath }) => requestPath).sort(),
      ).toEqual(['/api/v1/auth/me', '/api/v1/doctor', '/healthz', '/healthz'])
    },
  )

  it('renders the actual Logs route with shell reads only', async () => {
    const http = fixture()
    window.history.replaceState({}, '', '/logs')
    render(<App />)

    await screen.findByRole('heading', { name: 'Not implemented yet' })
    await screen.findByLabelText('Control plane: Healthy')
    expect(
      screen.getByRole('heading', { name: 'Logs', level: 1 }),
    ).toBeVisible()
    expect(http.doctorReads).toHaveLength(0)
    expect(http.requests).toEqual([
      { path: '/api/v1/auth/me', method: 'GET' },
      { path: '/healthz', method: 'GET' },
    ])
  })
})
