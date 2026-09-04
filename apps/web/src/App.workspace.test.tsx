import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

const auth = {
  api_version: 'v1',
  request_id: 'req_workspace_route',
  data: {
    user: { id: 'adm_workspace', username: 'maintainer' },
    session: { id: 'ses_workspace', expires_at: '2026-08-10T00:00:00Z' },
    csrf_token: 'csrf-workspace',
  },
}

function jsonResponse(body: object, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

describe('Workspace routes', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (input.toString().endsWith('/api/v1/auth/me')) {
          return jsonResponse(auth)
        }
        return jsonResponse({})
      }),
    )
  })

  afterEach(() => vi.unstubAllGlobals())

  it.each(['/workspace', '/workspace/aws_0123456789abcdef0123456789abcdef'])(
    'protects and renders %s through App routing',
    async (path) => {
      window.history.replaceState({}, '', path)
      render(<App />)

      expect(
        await screen.findByRole('heading', { name: 'Interactive workspace' }),
      ).toBeInTheDocument()
      expect(screen.getByText('Not admitted')).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Workspace' })).toHaveAttribute(
        'href',
        '/workspace',
      )
    },
  )

  it('keeps the legacy Claude route distinct from Workspace', async () => {
    window.history.replaceState({}, '', '/workspace')
    render(<App />)
    expect(
      await screen.findByRole('heading', { name: 'Interactive workspace' }),
    ).toBeInTheDocument()
    expect(
      screen
        .queryAllByRole('heading')
        .some((heading) => heading.textContent === 'Claude'),
    ).toBe(false)
  })
})
