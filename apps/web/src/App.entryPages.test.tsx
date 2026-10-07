import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import type { AuthEnvelope } from './lib/contracts'
import { heldResponse } from './test/doctorFixtures'

const auth: AuthEnvelope = {
  api_version: 'v1',
  request_id: 'req_entry_auth',
  data: {
    user: { id: 'adm_entry_fixture', username: 'entry-fixture' },
    session: { id: 'ses_entry_fixture', expires_at: '2026-10-08T00:00:00Z' },
    csrf_token: 'ENTRY-CSRF-PRIVATE-CANARY',
  },
}
const privatePassword = 'ENTRY-PASSWORD-PRIVATE-CANARY'
const privateProse = 'ENTRY-SERVER-PROSE-PRIVATE-CANARY'

function response(status: number, body: unknown, headers: HeadersInit = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function failure(status: number, requestId: unknown = 'req_entry_failure') {
  return response(
    status,
    {
      request_id: requestId,
      error: { code: 'ENTRY_UNKNOWN_FAILURE', message: privateProse },
    },
    status === 429 ? { 'Retry-After': '73' } : {},
  )
}

function fixture(
  login: (init: RequestInit) => Promise<Response>,
  recovery: Response | Promise<Response> = failure(401),
) {
  const requests: Array<{ path: string; method: string; body: unknown }> = []
  const unexpected: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = input.toString()
      const method = init?.method ?? 'GET'
      requests.push({
        path,
        method,
        body: init?.body ? JSON.parse(String(init.body)) : null,
      })
      if (path === '/api/v1/auth/login' && method === 'POST')
        return login(init!)
      if (path === '/api/v1/auth/me' && method === 'GET')
        return Promise.resolve(recovery)
      const reads: Record<string, unknown> = {
        '/healthz': { status: 'ok' },
        '/readyz': {
          status: 'ready',
          checks: { database: true, migrations: true },
        },
        '/api/v1/meta': {
          name: 'AgentBox',
          version: 'fixture',
          api_version: 'v1',
          environment: 'test',
        },
        '/api/v1/jobs?scope=mine': {
          api_version: 'v1',
          request_id: 'req_entry_jobs',
          data: { jobs: [] },
        },
        '/api/v1/projects/recent': {
          api_version: 'v1',
          request_id: 'req_entry_projects',
          data: { projects: [] },
        },
      }
      if (method === 'GET' && path in reads)
        return Promise.resolve(response(200, reads[path]))
      unexpected.push(`${method} ${path}`)
      throw new Error(`Unexpected entry fixture request: ${method} ${path}`)
    }),
  )
  return {
    requests,
    unexpected,
    posts: () => requests.filter(({ method }) => method === 'POST'),
  }
}

async function submitCredentials(username = '  entry-fixture  ') {
  fireEvent.change(await screen.findByLabelText('Username'), {
    target: { value: username },
  })
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: privatePassword },
  })
  const button = screen.getByRole('button', { name: 'Sign in' })
  fireEvent.submit(button.closest('form')!)
  return button
}

function expectNoPrivateDisplay() {
  for (const sentinel of [
    privatePassword,
    privateProse,
    auth.data.csrf_token,
  ]) {
    expect(document.body).not.toHaveTextContent(sentinel)
    expect(document.title).not.toContain(sentinel)
    expect(JSON.stringify(window.localStorage)).not.toContain(sentinel)
    expect(JSON.stringify(window.sessionStorage)).not.toContain(sentinel)
  }
}

describe('actual App entry pages and HTTP contracts', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/login')
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it.each([
    {
      name: '401',
      result: () => failure(401),
      expected: 'The username or password is incorrect.',
    },
    {
      name: '429',
      result: () => failure(429),
      expected: 'Too many sign-in attempts. Try again later.',
    },
    {
      name: 'unknown 500',
      result: () => failure(500),
      expected: 'The operation could not be completed. Try again.',
    },
    {
      name: 'malformed 200',
      result: () => response(200, { data: { token: privateProse } }),
      expected: 'The control plane is unavailable.',
    },
    {
      name: 'non-JSON proxy 503',
      result: () => new Response(privateProse, { status: 503 }),
      expected: 'The operation could not be completed. Try again.',
    },
  ])(
    'clears the password after $name and retries only on an explicit new submission',
    async ({ name, result, expected }) => {
      const retry = heldResponse()
      let attempts = 0
      const http = fixture(async () =>
        ++attempts === 1 ? result() : retry.promise,
      )
      render(<App />)
      await submitCredentials()

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(expected)
      expect(screen.getByLabelText('Username')).toHaveValue('  entry-fixture  ')
      expect(screen.getByLabelText('Password')).toHaveValue('')
      expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
      expect(http.posts()).toEqual([
        {
          path: '/api/v1/auth/login',
          method: 'POST',
          body: { username: '  entry-fixture  ', password: privatePassword },
        },
      ])
      if (name === '429') {
        expect(alert).toHaveTextContent(
          'Try again in approximately 73 seconds.',
        )
        vi.useFakeTimers()
        await act(async () => vi.advanceTimersByTimeAsync(73_000))
        expect(alert).toHaveTextContent(
          'Try again in approximately 73 seconds.',
        )
        vi.useRealTimers()
      }
      expect(http.posts()).toHaveLength(1)
      expectNoPrivateDisplay()

      fireEvent.change(screen.getByLabelText('Password'), {
        target: { value: 'ENTRY-RETRY-PASSWORD' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      const pending = screen.getByRole('button', { name: 'Signing in…' })
      expect(pending).toBeDisabled()
      fireEvent.click(pending)
      expect(http.posts()).toHaveLength(2)
      expect(http.posts()[1].body).toEqual({
        username: '  entry-fixture  ',
        password: 'ENTRY-RETRY-PASSWORD',
      })

      await act(async () => retry.resolve(response(200, auth)))
      await screen.findByRole('heading', { name: 'Dashboard', level: 1 })
      expect(window.location.pathname).toBe('/dashboard')
      expect(http.posts()).toHaveLength(2)
      expect(http.unexpected).toEqual([])
      expectNoPrivateDisplay()
    },
  )

  it.each([
    { name: 'maximum safe length', id: `req_${'a'.repeat(68)}`, visible: true },
    { name: 'overlong value', id: `req_${'a'.repeat(69)}`, visible: false },
    {
      name: 'control character',
      id: 'req_private\nREQUEST-ID-CANARY',
      visible: false,
    },
    { name: 'markup', id: '<img src=REQUEST-ID-CANARY>', visible: false },
    {
      name: 'non-string value',
      id: { token: 'REQUEST-ID-CANARY' },
      visible: false,
    },
  ])(
    'allows request details only after the real API parser accepts $name',
    async ({ id, visible }) => {
      const http = fixture(async () => failure(401, id))
      render(<App />)
      await submitCredentials()
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent('The username or password is incorrect.')
      if (visible) {
        const technicalId = screen.getByText(String(id))
        expect(technicalId).toHaveAttribute('lang', 'en')
        expect(technicalId).toHaveAttribute('dir', 'ltr')
        expect(technicalId).toHaveAttribute('translate', 'no')
        expect(technicalId.closest('details')).not.toHaveAttribute('open')
      } else {
        expect(screen.queryByText('Request details')).not.toBeInTheDocument()
        expect(document.body).not.toHaveTextContent('REQUEST-ID-CANARY')
        if (typeof id === 'string')
          expect(document.body).not.toHaveTextContent(id)
      }
      expect(screen.getByLabelText('Password')).toHaveValue('')
      expect(http.posts()).toHaveLength(1)
      expect(http.unexpected).toEqual([])
    },
  )

  it.each(['network', 'timeout'] as const)(
    'recovers from a real API %s rejection with one manual retry',
    async (kind) => {
      let attempts = 0
      let pendingSignal: AbortSignal | null = null
      const http = fixture((init) => {
        attempts += 1
        if (attempts > 1) return Promise.resolve(response(200, auth))
        if (kind === 'network')
          return Promise.reject(new TypeError(privateProse))
        pendingSignal = init.signal as AbortSignal
        return new Promise<Response>((_, reject) => {
          init.signal!.addEventListener(
            'abort',
            () => reject(new DOMException(privateProse, 'AbortError')),
            { once: true },
          )
        })
      })
      render(<App />)
      await screen.findByLabelText('Username')
      if (kind === 'timeout') vi.useFakeTimers()
      fireEvent.change(screen.getByLabelText('Username'), {
        target: { value: 'entry-fixture' },
      })
      fireEvent.change(screen.getByLabelText('Password'), {
        target: { value: privatePassword },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
      if (kind === 'timeout') {
        expect(
          screen.getByRole('button', { name: 'Signing in…' }),
        ).toBeDisabled()
        await act(async () => vi.advanceTimersByTimeAsync(10_000))
        expect(pendingSignal).toHaveProperty('aborted', true)
        vi.useRealTimers()
      }
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(
        kind === 'timeout'
          ? 'The request timed out. Try again.'
          : 'The control plane is unavailable.',
      )
      expect(screen.getByLabelText('Password')).toHaveValue('')
      expect(screen.getByLabelText('Username')).toHaveValue('entry-fixture')
      expect(http.posts()).toHaveLength(1)
      expectNoPrivateDisplay()
      await submitCredentials('entry-fixture')
      await screen.findByRole('heading', { name: 'Dashboard', level: 1 })
      expect(http.posts()).toHaveLength(2)
      expect(http.unexpected).toEqual([])
    },
  )

  it.each([
    'https://outside.invalid/ENTRY-RETURN',
    '//outside.invalid/ENTRY-RETURN',
  ])(
    'ignores external returnTo %s and keeps the fixed Dashboard destination',
    async (returnTo) => {
      window.history.replaceState(
        { returnTo },
        '',
        `/login?returnTo=${encodeURIComponent(returnTo)}`,
      )
      const http = fixture(async () => response(200, auth))
      render(<App />)
      await submitCredentials()
      await screen.findByRole('heading', { name: 'Dashboard', level: 1 })
      expect(window.location.pathname).toBe('/dashboard')
      expect(window.location.search).toBe('')
      expect(http.posts()).toHaveLength(1)
      expect(http.requests.every(({ path }) => path.startsWith('/'))).toBe(true)
      expect(http.unexpected).toEqual([])
      expect(document.body).not.toHaveTextContent('ENTRY-RETURN')
    },
  )

  it.each([false, true])(
    'uses the sole 404 recovery Link and real Back/Forward history (authenticated=%s)',
    async (authenticated) => {
      const recovery = heldResponse()
      const http = fixture(async () => failure(401), recovery.promise)
      const missing =
        '/ENTRY-MISSING-PATH?private=ENTRY-MISSING-QUERY#ENTRY-MISSING-HASH'
      window.history.replaceState({}, '', missing)
      render(<App />)
      const link = screen.getByRole('link', { name: 'Back to sign in' })
      expect(link).toHaveAttribute('href', '/login')
      expect(screen.getAllByRole('link')).toHaveLength(1)
      expect(http.requests.map(({ path }) => path)).toEqual(['/api/v1/auth/me'])
      await act(async () =>
        recovery.resolve(authenticated ? response(200, auth) : failure(401)),
      )
      const label = authenticated ? 'Back to Dashboard' : 'Back to sign in'
      const destination = authenticated ? '/dashboard' : '/login'
      expect(screen.getByRole('link', { name: label })).toBe(link)
      expect(link).toHaveAttribute('href', destination)
      fireEvent.click(link)
      await waitFor(() => expect(window.location.pathname).toBe(destination))
      if (authenticated)
        await screen.findByRole('heading', { name: 'Dashboard', level: 1 })
      else await screen.findByRole('button', { name: 'Sign in' })

      act(() => window.history.back())
      await screen.findByRole('link', { name: label })
      expect(
        `${window.location.pathname}${window.location.search}${window.location.hash}`,
      ).toBe(missing)
      expect(screen.getAllByRole('link')).toHaveLength(1)
      for (const sentinel of [
        'ENTRY-MISSING-PATH',
        'ENTRY-MISSING-QUERY',
        'ENTRY-MISSING-HASH',
      ]) {
        expect(document.body).not.toHaveTextContent(sentinel)
        expect(document.title).not.toContain(sentinel)
      }
      act(() => window.history.forward())
      await waitFor(() => expect(window.location.pathname).toBe(destination))
      if (authenticated)
        await screen.findByRole('heading', { name: 'Dashboard', level: 1 })
      else await screen.findByRole('button', { name: 'Sign in' })
      expect(http.posts()).toHaveLength(0)
      expect(
        http.requests.filter(({ path }) => path === '/api/v1/auth/me'),
      ).toHaveLength(1)
      expect(http.unexpected).toEqual([])
    },
  )
})
