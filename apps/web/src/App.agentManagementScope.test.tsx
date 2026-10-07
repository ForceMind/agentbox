import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import type {
  AuthEnvelope,
  ClaudeSessionListResponse,
  ClaudeSessionOutputResponse,
  ClaudeStatusResponse,
  CodexPairResponse,
  CodexStatusResponse,
} from './lib/contracts'

const authA: AuthEnvelope = {
  api_version: 'v1',
  request_id: 'req_management_auth_a',
  data: {
    user: {
      id: 'adm_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      username: 'management-fixture',
    },
    session: {
      id: 'ses_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      expires_at: '2026-10-08T00:00:00Z',
    },
    csrf_token: 'csrf-management-fixture-a',
  },
}
const authB: AuthEnvelope = {
  ...authA,
  request_id: 'req_management_auth_b',
  data: {
    ...authA.data,
    session: {
      ...authA.data.session,
      id: 'ses_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    },
    csrf_token: 'csrf-management-fixture-b',
  },
}
const codexStatus: CodexStatusResponse = {
  api_version: 'v1',
  request_id: 'req_management_codex',
  data: {
    installed: true,
    version: '1.fixture',
    selected_executable: '/fixture/bin/codex',
    alternatives: [],
    installation_type: 'standalone',
    conflict_detected: false,
    authentication: 'authenticated',
    capabilities: {
      remote_control: 'supported',
      start: 'supported',
      stop: 'supported',
      pair: 'supported',
      status: 'unsupported',
    },
    remote_state: 'stopped',
    remote_confidence: 'reported',
    diagnostics: [],
  },
}
const claudeStatus: ClaudeStatusResponse = {
  api_version: 'v1',
  request_id: 'req_management_claude',
  data: {
    installed: true,
    version: '1.fixture',
    authentication: 'authenticated',
    capabilities: {
      remote_control: 'supported',
      remote_start: 'supported',
      version: 'supported',
    },
    tmux_installed: true,
    tmux_version: '3.fixture',
    managed_sessions: 1,
    unmanaged_sessions: 0,
    workspace_interaction_warnings: 0,
    diagnostics: [],
  },
}
const projectId = 'prj_cccccccccccccccccccccccccccccccc'
const sessionName = 'agentbox-claude-prj_cccccccccccccccccccccccc-9f3a07269b11'
const claudeSessions: ClaudeSessionListResponse = {
  api_version: 'v1',
  request_id: 'req_management_sessions',
  data: {
    sessions: [
      {
        project_id: projectId,
        display_name: 'Management fixture',
        state: 'running',
        managed: true,
        session_name: sessionName,
        attach_command: `tmux attach-session -t =${sessionName}`,
        workspace_state: 'unknown',
        tmux_running: true,
        remote_readiness: 'ready',
      },
    ],
  },
}
const pairA: CodexPairResponse = {
  api_version: 'v1',
  request_id: 'req_management_pair_a',
  data: {
    pair_code: 'PAIR-SESSION-A-FIXTURE-7294',
    expires_at: null,
    display_once: true,
  },
}
const outputA: ClaudeSessionOutputResponse = {
  api_version: 'v1',
  request_id: 'req_management_output_a',
  data: {
    project_id: projectId,
    session_name: sessionName,
    output: 'CLAUDE-SESSION-A-OUTPUT-FIXTURE-7294',
    truncated: false,
    sensitive: true,
  },
}

function jsonResponse(status: number, body: object) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Only the HTTP boundary is a fixture. App, AuthProvider, route guards, API
// client, management pages and product hooks all run their production code.
function sessionReplacementFixture(sensitivePath: string) {
  let resolveSensitive!: (response: Response) => void
  const sensitiveResponse = new Promise<Response>((resolve) => {
    resolveSensitive = resolve
  })
  let meCalls = 0
  let logoutCalls = 0
  const requests: Array<{ path: string; method: string; csrf: string | null }> =
    []
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = input.toString()
    requests.push({
      path,
      method: init?.method ?? 'GET',
      csrf: new Headers(init?.headers).get('X-CSRF-Token'),
    })
    if (path === '/api/v1/auth/me') {
      meCalls += 1
      return Promise.resolve(jsonResponse(200, meCalls === 1 ? authA : authB))
    }
    if (path === '/api/v1/auth/logout') {
      logoutCalls += 1
      return Promise.resolve(
        jsonResponse(logoutCalls === 1 ? 403 : 500, {
          request_id: 'req_management_logout',
          error: {
            code: logoutCalls === 1 ? 'AUTH_CSRF_INVALID' : 'INTERNAL_ERROR',
            message: 'Synthetic logout failure',
          },
        }),
      )
    }
    if (path === sensitivePath) return sensitiveResponse
    if (path === '/api/v1/codex/status')
      return Promise.resolve(jsonResponse(200, codexStatus))
    if (path === '/api/v1/claude')
      return Promise.resolve(jsonResponse(200, claudeStatus))
    if (path === '/api/v1/claude/sessions')
      return Promise.resolve(jsonResponse(200, claudeSessions))
    if (path === '/healthz')
      return Promise.resolve(jsonResponse(200, { status: 'ok' }))
    throw new Error(`Unexpected fixture request: ${path}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { requests, resolveSensitive }
}

describe('management sensitive content after same-document session replacement', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it.each(['shown', 'pending'] as const)(
    'revokes a %s Codex Pair result owned by session A when logout recovery installs B',
    async (timing) => {
      const path = '/api/v1/codex/pair-codes'
      const fixture = sessionReplacementFixture(path)
      window.history.replaceState({}, '', '/codex')
      render(<App />)
      fireEvent.click(
        await screen.findByRole('button', { name: 'Pair New Device' }),
      )
      fireEvent.click(screen.getByRole('button', { name: 'Generate Code' }))
      if (timing === 'shown') {
        await act(async () => {
          fixture.resolveSensitive(jsonResponse(200, pairA))
        })
        expect(screen.getByText(pairA.data.pair_code)).toBeInTheDocument()
      }

      fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Logout could not be completed',
      )
      expect(window.location.pathname).toBe('/codex')
      expect(screen.getByRole('heading', { name: 'Codex' })).toBeInTheDocument()
      if (timing === 'pending') {
        await act(async () => {
          fixture.resolveSensitive(jsonResponse(200, pairA))
        })
      }

      expect(
        fixture.requests.filter(({ path }) => path.includes('/auth/')),
      ).toEqual([
        { path: '/api/v1/auth/me', method: 'GET', csrf: null },
        {
          path: '/api/v1/auth/logout',
          method: 'POST',
          csrf: authA.data.csrf_token,
        },
        { path: '/api/v1/auth/me', method: 'GET', csrf: null },
        {
          path: '/api/v1/auth/logout',
          method: 'POST',
          csrf: authB.data.csrf_token,
        },
      ])
      expect(
        fixture.requests.filter(
          ({ path }) =>
            path.startsWith('/api/v1/codex/') &&
            path !== '/api/v1/codex/status',
        ),
      ).toEqual([{ path, method: 'POST', csrf: authA.data.csrf_token }])
      expect(screen.queryByText(pairA.data.pair_code)).not.toBeInTheDocument()
    },
  )

  it.each(['shown', 'pending'] as const)(
    'revokes %s Claude output owned by session A when logout recovery installs B',
    async (timing) => {
      const path = `/api/v1/claude/sessions/${projectId}/output`
      const fixture = sessionReplacementFixture(path)
      window.history.replaceState({}, '', '/claude')
      render(<App />)
      fireEvent.click(await screen.findByRole('button', { name: 'Reveal' }))
      if (timing === 'shown') {
        await act(async () => {
          fixture.resolveSensitive(jsonResponse(200, outputA))
        })
        expect(screen.getByText(outputA.data.output)).toBeInTheDocument()
      }

      fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Logout could not be completed',
      )
      expect(window.location.pathname).toBe('/claude')
      expect(
        screen.getByRole('heading', { name: 'Claude' }),
      ).toBeInTheDocument()
      if (timing === 'pending') {
        await act(async () => {
          fixture.resolveSensitive(jsonResponse(200, outputA))
        })
      }

      expect(
        fixture.requests.filter(({ path }) => path.includes('/auth/')),
      ).toEqual([
        { path: '/api/v1/auth/me', method: 'GET', csrf: null },
        {
          path: '/api/v1/auth/logout',
          method: 'POST',
          csrf: authA.data.csrf_token,
        },
        { path: '/api/v1/auth/me', method: 'GET', csrf: null },
        {
          path: '/api/v1/auth/logout',
          method: 'POST',
          csrf: authB.data.csrf_token,
        },
      ])
      expect(
        fixture.requests.filter(({ path }) =>
          path.startsWith('/api/v1/claude/sessions/'),
        ),
      ).toEqual([{ path, method: 'GET', csrf: null }])
      expect(screen.queryByText(outputA.data.output)).not.toBeInTheDocument()
    },
  )
})
