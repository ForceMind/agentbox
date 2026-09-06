import type { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient } from '../../lib/api'
import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { useClaude } from './useClaude'

const auth = {
  user: { id: 'adm_claude_test', username: 'maintainer' },
  session: { id: 'ses_claude_test', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'csrf-claude-test',
}

const statusData = {
  installed: true,
  version: '1.fixture',
  authentication: 'unknown',
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
  diagnostics: [
    {
      code: 'CLAUDE_DIAGNOSTIC_FIXTURE',
      severity: 'warning',
      summary: 'RAW-DIAGNOSTIC-SUMMARY-CANARY',
      remediation: 'RAW-DIAGNOSTIC-REMEDIATION-CANARY',
    },
  ],
}

const session = {
  project_id: 'project-a',
  display_name: '用户项目 🚀',
  state: 'running',
  managed: true,
  session_name: 'agentbox-claude-project-a',
  attach_command: 'tmux attach-session -t =agentbox-claude-project-a',
  workspace_state: 'unknown',
  tmux_running: true,
  remote_readiness: 'ready',
}

const secondSession = {
  ...session,
  project_id: 'project-b',
  display_name: 'Project B',
  state: 'stopped',
  session_name: 'agentbox-claude-project-b',
  attach_command: 'tmux attach-session -t =agentbox-claude-project-b',
  tmux_running: false,
  remote_readiness: 'unknown',
}

function jsonResponse(status: number, body: object) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function wrapper(api: ApiClient) {
  const value: AuthContextValue = {
    api,
    auth,
    login: async () => undefined,
    logout: async () => undefined,
    refresh: async () => auth,
    status: 'authenticated',
  }
  return function AuthWrapper({ children }: { children: ReactNode }) {
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  }
}

function successfulFetch(input: RequestInfo | URL) {
  const path = input.toString()
  if (path.endsWith('/api/v1/claude')) {
    return Promise.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_status',
        data: statusData,
      }),
    )
  }
  if (path.endsWith('/api/v1/claude/sessions')) {
    return Promise.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_sessions',
        data: { sessions: [session] },
      }),
    )
  }
  return Promise.resolve(jsonResponse(404, {}))
}

describe('useClaude safe view projection', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('exposes only the approved status and session fields', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch))
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })

    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    expect(JSON.stringify(result.current)).not.toContain(
      'RAW-DIAGNOSTIC-SUMMARY-CANARY',
    )
    expect(JSON.stringify(result.current)).not.toContain(
      'RAW-DIAGNOSTIC-REMEDIATION-CANARY',
    )
    if (result.current.view.status !== 'loaded') throw new Error('not loaded')
    expect(result.current.view.data.status).not.toHaveProperty('diagnostics')
    expect(result.current.view.data.status.capabilities).toEqual({
      remote_control: 'supported',
    })
    expect(result.current.view.data.sessions[0]).not.toHaveProperty('managed')
    expect(result.current.view.data.sessions[0]).not.toHaveProperty(
      'session_name',
    )
    expect(result.current.view.data.sessions[0].display_name).toBe(
      '用户项目 🚀',
    )
  })

  it.each([
    ['CLAUDE_RUNTIME_UNAVAILABLE', 'KNOWN-SERVER-PROSE-CANARY'],
    ['CLAUDE_VENDOR_UNKNOWN', 'UNKNOWN-SERVER-PROSE-CANARY'],
  ])('drops raw prose for %s', async (code, canary) => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (input.toString().endsWith('/api/v1/claude')) {
          return Promise.resolve(
            jsonResponse(503, {
              request_id: 'req_claude_error',
              error: { code, message: canary },
            }),
          )
        }
        return successfulFetch(input)
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })

    await waitFor(() => expect(result.current.view.status).toBe('error'))
    expect(result.current.view).toEqual({
      status: 'error',
      error: { code, requestId: 'req_claude_error' },
    })
    expect(JSON.stringify(result.current)).not.toContain(canary)
  })

  it('retains revealed output only until Hide and drops envelope identity', async () => {
    const outputCanary = 'EXPLICIT-OUTPUT-CANARY <script>ignored()</script>'
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = input.toString()
      if (path.endsWith('/sessions/project-a/output')) {
        return Promise.resolve(
          jsonResponse(200, {
            api_version: 'v1',
            request_id: 'req_output',
            data: {
              project_id: 'project-a',
              session_name: 'RAW-SESSION-NAME-CANARY',
              output: outputCanary,
              truncated: true,
              sensitive: true,
            },
          }),
        )
      }
      return successfulFetch(input)
    })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    expect(
      fetchMock.mock.calls.some(([input]) =>
        input.toString().endsWith('/output'),
      ),
    ).toBe(false)

    await act(async () => result.current.revealOutput('project-a'))
    expect(result.current.outputs).toEqual({
      'project-a': { output: outputCanary, truncated: true },
    })
    expect(JSON.stringify(result.current.outputs)).not.toContain(
      'RAW-SESSION-NAME-CANARY',
    )

    act(() => result.current.hideOutput('project-a'))
    expect(result.current.outputs).toEqual({})

    await act(async () => result.current.revealOutput('project-a'))
    expect(result.current.outputs['project-a']?.output).toBe(outputCanary)
    await act(async () => result.current.refresh())
    expect(result.current.outputs).toEqual({})
  })

  it('keeps each Project pending until its own out-of-order mutation completes', async () => {
    const projectA = deferred<Response>()
    const projectB = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/claude/sessions')) {
          return Promise.resolve(
            jsonResponse(200, {
              api_version: 'v1',
              request_id: 'req_sessions',
              data: { sessions: [session, secondSession] },
            }),
          )
        }
        if (path.endsWith('/sessions/project-a/stop')) {
          return projectA.promise
        }
        if (path.endsWith('/sessions/project-b/start')) {
          return projectB.promise
        }
        return successfulFetch(input)
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    let actionA!: Promise<void>
    let actionB!: Promise<void>
    act(() => {
      actionA = result.current.sessionAction('project-a', 'stop')
      actionB = result.current.sessionAction('project-b', 'start')
    })
    await waitFor(() =>
      expect(result.current.pending).toEqual([
        { operation: 'stop', projectId: 'project-a' },
        { operation: 'start', projectId: 'project-b' },
      ]),
    )

    projectB.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_project_b_start',
        data: {
          outcome: 'started',
          session: {
            ...secondSession,
            state: 'starting',
            tmux_running: true,
          },
        },
      }),
    )
    await act(async () => actionB)
    expect(result.current.pending).toEqual([
      { operation: 'stop', projectId: 'project-a' },
    ])
    if (result.current.view.status !== 'loaded') throw new Error('not loaded')
    expect(
      result.current.view.data.sessions.find(
        (candidate) => candidate.project_id === 'project-b',
      )?.state,
    ).toBe('starting')

    projectA.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_project_a_stop',
        data: {
          outcome: 'stopped',
          session: { ...session, state: 'stopped', tmux_running: false },
        },
      }),
    )
    await act(async () => actionA)
    expect(result.current.pending).toEqual([])
    if (result.current.view.status !== 'loaded') throw new Error('not loaded')
    expect(
      result.current.view.data.sessions.find(
        (candidate) => candidate.project_id === 'project-a',
      )?.state,
    ).toBe('stopped')
  })

  it('keeps Project A failure after Project B succeeds first', async () => {
    const projectA = deferred<Response>()
    const projectB = deferred<Response>()
    const serverProse = 'PROJECT-A-FAILURE-SERVER-PROSE-CANARY'
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/claude/sessions')) {
          return Promise.resolve(
            jsonResponse(200, {
              api_version: 'v1',
              request_id: 'req_sessions',
              data: { sessions: [session, secondSession] },
            }),
          )
        }
        if (path.endsWith('/sessions/project-a/stop')) return projectA.promise
        if (path.endsWith('/sessions/project-b/start')) return projectB.promise
        return successfulFetch(input)
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    let actionA!: Promise<void>
    let actionB!: Promise<void>
    act(() => {
      actionA = result.current.sessionAction('project-a', 'stop')
      actionB = result.current.sessionAction('project-b', 'start')
    })
    projectB.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_project_b_start',
        data: {
          outcome: 'started',
          session: {
            ...secondSession,
            state: 'starting',
            tmux_running: true,
          },
        },
      }),
    )
    await act(async () => actionB)
    expect(result.current.actionErrors).toEqual({})

    projectA.resolve(
      jsonResponse(503, {
        request_id: 'req_project_a_failure',
        error: {
          code: 'CLAUDE_RUNTIME_UNAVAILABLE',
          message: serverProse,
        },
      }),
    )
    await act(async () => actionA)
    expect(result.current.actionErrors).toEqual({
      'project-a': {
        code: 'CLAUDE_RUNTIME_UNAVAILABLE',
        requestId: 'req_project_a_failure',
      },
    })
    expect(JSON.stringify(result.current)).not.toContain(serverProse)
  })

  it('retains two cross-Project failures without mixing their ownership', async () => {
    const projectA = deferred<Response>()
    const projectB = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/claude/sessions')) {
          return Promise.resolve(
            jsonResponse(200, {
              api_version: 'v1',
              request_id: 'req_sessions',
              data: { sessions: [session, secondSession] },
            }),
          )
        }
        if (path.endsWith('/sessions/project-a/stop')) return projectA.promise
        if (path.endsWith('/sessions/project-b/start')) return projectB.promise
        return successfulFetch(input)
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    let actionA!: Promise<void>
    let actionB!: Promise<void>
    act(() => {
      actionA = result.current.sessionAction('project-a', 'stop')
      actionB = result.current.sessionAction('project-b', 'start')
    })
    projectA.resolve(
      jsonResponse(503, {
        request_id: 'req_failure_a',
        error: { code: 'CLAUDE_ACTION_FAILED', message: 'FAILURE-A-PROSE' },
      }),
    )
    projectB.resolve(
      jsonResponse(409, {
        request_id: 'req_failure_b',
        error: { code: 'CLAUDE_VENDOR_UNKNOWN', message: 'FAILURE-B-PROSE' },
      }),
    )
    await act(async () => Promise.all([actionB, actionA]))

    expect(result.current.actionErrors).toEqual({
      'project-a': {
        code: 'CLAUDE_ACTION_FAILED',
        requestId: 'req_failure_a',
      },
      'project-b': {
        code: 'CLAUDE_VENDOR_UNKNOWN',
        requestId: 'req_failure_b',
      },
    })
    expect(JSON.stringify(result.current)).not.toContain('FAILURE-A-PROSE')
    expect(JSON.stringify(result.current)).not.toContain('FAILURE-B-PROSE')
  })

  it('attributes an action identity mismatch to the requested Project', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (input.toString().endsWith('/sessions/project-a/stop')) {
          return Promise.resolve(
            jsonResponse(200, {
              api_version: 'v1',
              request_id: 'req_identity_mismatch',
              data: {
                outcome: 'stopped',
                session: {
                  ...secondSession,
                  state: 'stopped',
                  tmux_running: false,
                },
              },
            }),
          )
        }
        return successfulFetch(input)
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    await act(async () => result.current.sessionAction('project-a', 'stop'))
    expect(result.current.actionErrors).toEqual({
      'project-a': { code: 'CLAUDE_ACTION_FAILED' },
    })
    if (result.current.view.status !== 'loaded') throw new Error('not loaded')
    expect(result.current.view.data.sessions[0].project_id).toBe('project-a')
    expect(result.current.view.data.sessions[0].state).toBe('running')
  })

  it('keeps an output failure local to its Project and drops server prose', async () => {
    const canary = 'OUTPUT-FAILURE-SERVER-PROSE-CANARY'
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (input.toString().endsWith('/sessions/project-a/output')) {
          return Promise.resolve(
            jsonResponse(503, {
              request_id: 'req_output_failure',
              error: { code: 'CLAUDE_OUTPUT_UNKNOWN', message: canary },
            }),
          )
        }
        return successfulFetch(input)
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    await act(async () => result.current.revealOutput('project-a'))
    expect(result.current.actionErrors).toEqual({
      'project-a': {
        code: 'CLAUDE_OUTPUT_UNKNOWN',
        requestId: 'req_output_failure',
      },
    })
    expect(result.current.outputs).toEqual({})
    expect(JSON.stringify(result.current)).not.toContain(canary)
  })

  it('rejects a same-Project overlap before it can create an older response', async () => {
    const first = deferred<Response>()
    let actionRequests = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input.toString()
        if (
          path.endsWith('/sessions/project-a/stop') ||
          path.endsWith('/sessions/project-a/start')
        ) {
          actionRequests += 1
          return first.promise
        }
        return successfulFetch(input)
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    let firstAction!: Promise<void>
    await act(async () => {
      firstAction = result.current.sessionAction('project-a', 'stop')
      await result.current.sessionAction('project-a', 'start')
    })
    expect(actionRequests).toBe(1)
    expect(result.current.pending).toEqual([
      { operation: 'stop', projectId: 'project-a' },
    ])

    first.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_first_stop',
        data: {
          outcome: 'stopped',
          session: { ...session, state: 'stopped', tmux_running: false },
        },
      }),
    )
    await act(async () => firstAction)
    expect(result.current.pending).toEqual([])
  })

  it('preserves a mutation result when an overlapping refresh resolves stale', async () => {
    const mutation = deferred<Response>()
    const refreshedStatus = deferred<Response>()
    const staleSessions = deferred<Response>()
    let statusCalls = 0
    let sessionCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/claude')) {
          statusCalls += 1
          return statusCalls === 1
            ? successfulFetch(input)
            : refreshedStatus.promise
        }
        if (path.endsWith('/api/v1/claude/sessions')) {
          sessionCalls += 1
          return sessionCalls === 1
            ? successfulFetch(input)
            : staleSessions.promise
        }
        if (path.endsWith('/sessions/project-a/stop')) {
          return mutation.promise
        }
        return Promise.resolve(jsonResponse(404, {}))
      }),
    )
    const { result } = renderHook(() => useClaude(), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    let mutationPromise!: Promise<void>
    act(() => {
      mutationPromise = result.current.sessionAction('project-a', 'stop')
    })
    await waitFor(() =>
      expect(result.current.pending).toEqual([
        { operation: 'stop', projectId: 'project-a' },
      ]),
    )
    let refreshPromise!: Promise<void>
    act(() => {
      refreshPromise = result.current.refresh()
    })
    await waitFor(() => expect(result.current.refreshing).toBe(true))

    mutation.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_mutation_stop',
        data: {
          outcome: 'stopped',
          session: { ...session, state: 'stopped', tmux_running: false },
        },
      }),
    )
    await act(async () => mutationPromise)
    expect(result.current.pending).toEqual([])

    refreshedStatus.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_refresh_status',
        data: statusData,
      }),
    )
    staleSessions.resolve(
      jsonResponse(200, {
        api_version: 'v1',
        request_id: 'req_refresh_sessions',
        data: { sessions: [session] },
      }),
    )
    await act(async () => refreshPromise)

    expect(result.current.refreshing).toBe(false)
    if (result.current.view.status !== 'loaded') throw new Error('not loaded')
    expect(result.current.view.data.sessions[0].state).toBe('stopped')
    expect(result.current.view.data.sessions[0].tmux_running).toBe(false)
  })
})
