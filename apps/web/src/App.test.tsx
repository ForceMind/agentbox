import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

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

function response(ok: boolean, status: number, body: object = {}) {
  return { ok, status, json: async () => body }
}

describe('AgentBox Phase 3 control plane', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the minimal login experience when no session exists', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = input.toString()
        return Promise.resolve(
          url.endsWith('/healthz') ? response(true, 200) : response(false, 401),
        )
      }),
    )

    render(<App />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'AgentBox' }),
    ).toBeInTheDocument()
    expect(screen.getByText('AI Developer Infrastructure')).toBeInTheDocument()
    expect(
      await screen.findByRole('heading', { name: 'Sign in' }),
    ).toBeInTheDocument()
  })

  it('logs in with cookie credentials and clears the password field', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.endsWith('/healthz')) return Promise.resolve(response(true, 200))
      if (url.endsWith('/auth/me')) return Promise.resolve(response(false, 401))
      expect(init?.credentials).toBe('include')
      expect(init?.method).toBe('POST')
      return Promise.resolve(response(true, 200, authenticated))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.change(await screen.findByLabelText('Username'), {
      target: { value: 'maintainer' },
    })
    const password = screen.getByLabelText('Password') as HTMLInputElement
    fireEvent.change(password, { target: { value: 'a long local passphrase' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(
      await screen.findByText('Signed in as maintainer'),
    ).toBeInTheDocument()
    expect(password).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    const freshPassword = (await screen.findByLabelText(
      'Password',
    )) as HTMLInputElement
    expect(freshPassword.value).toBe('')
  })

  it('uses the session-bound CSRF token for logout', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.endsWith('/healthz')) return Promise.resolve(response(true, 200))
      if (url.endsWith('/auth/me'))
        return Promise.resolve(response(true, 200, authenticated))
      expect(init?.method).toBe('POST')
      expect(init?.credentials).toBe('include')
      expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe(
        'csrf-test-value',
      )
      return Promise.resolve(response(true, 204))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Logout' }))

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Sign in' }),
      ).toBeInTheDocument()
    })
  })

  it('shows a healthy backend response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          input.toString().endsWith('/healthz')
            ? response(true, 200)
            : response(false, 401),
        ),
      ),
    )

    render(<App />)

    await waitFor(() => {
      expect(
        screen.getByLabelText('Backend status: Online'),
      ).toBeInTheDocument()
    })
  })
})
