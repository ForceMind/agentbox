import type { ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient, ApiError } from '../../lib/api'
import type {
  ClaudeSessionActionResponse,
  ClaudeSessionData,
  ClaudeSessionResponse,
} from '../../lib/contracts'
import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { useClaudeProject } from './useClaude'

const auth = {
  user: { id: 'adm_claude_detail', username: 'maintainer' },
  session: { id: 'ses_claude_detail', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'csrf-claude-detail-fixture',
}

function session(
  projectId = 'project-a',
  state: ClaudeSessionData['state'] = 'running',
): ClaudeSessionData {
  return {
    project_id: projectId,
    display_name: `Project ${projectId}`,
    state,
    managed: true,
    session_name: `agentbox-claude-${projectId}`,
    attach_command: `tmux attach-session -t =agentbox-claude-${projectId}`,
    workspace_state: 'unknown',
    tmux_running: state === 'running',
    remote_readiness: 'unknown',
  }
}

function response(
  projectId = 'project-a',
  state: ClaudeSessionData['state'] = 'running',
): ClaudeSessionResponse {
  return {
    api_version: 'v1',
    request_id: 'req_claude_detail',
    data: session(projectId, state),
  }
}

function acknowledgement(
  projectId = 'project-a',
  state: 'running' | 'stopped' = 'stopped',
): ClaudeSessionActionResponse {
  return {
    api_version: 'v1',
    request_id: 'req_claude_action',
    data: {
      outcome: state === 'stopped' ? 'stopped' : 'started',
      session: session(projectId, state),
    },
  }
}

function failure(status = 503) {
  return new ApiError({
    code: 'CLAUDE_RUNTIME_UNAVAILABLE',
    message: 'SERVER-PROSE-CANARY',
    status,
  })
}

function deferred<T>(path: string, signal?: AbortSignal) {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept
    reject = decline
  })
  return { path, signal, promise, resolve, reject }
}

// These API mocks deliberately ignore AbortSignal, so cancellation alone cannot pass.
function harness(
  projectId: string | undefined = 'project-a',
  initialStatus: AuthContextValue['status'] = 'authenticated',
) {
  const api = new ApiClient()
  const reads: ReturnType<typeof deferred<ClaudeSessionResponse>>[] = []
  const writes: ReturnType<typeof deferred<ClaudeSessionActionResponse>>[] = []
  vi.spyOn(api, 'get').mockImplementation((path, options) => {
    const request = deferred<ClaudeSessionResponse>(path, options?.signal)
    reads.push(request)
    return request.promise as Promise<never>
  })
  vi.spyOn(api, 'post').mockImplementation((path, options) => {
    const request = deferred<ClaudeSessionActionResponse>(path, options?.signal)
    writes.push(request)
    return request.promise as Promise<never>
  })
  let context: AuthContextValue = {
    api,
    auth,
    status: initialStatus,
    login: async () => undefined,
    logout: async () => undefined,
    refresh: async () => auth,
  }
  const initialProps: { id: string | undefined } = { id: projectId }
  const hook = renderHook(
    ({ id }: { id: string | undefined }) => useClaudeProject(id),
    {
      initialProps,
      wrapper: ({ children }: { children: ReactNode }) => (
        <AuthContext.Provider value={context}>{children}</AuthContext.Provider>
      ),
    },
  )
  return {
    ...hook,
    api,
    reads,
    writes,
    route(id: string | undefined) {
      projectId = id
      hook.rerender({ id })
    },
    identity(
      nextAuth: AuthContextValue['auth'],
      status: AuthContextValue['status'] = 'authenticated',
    ) {
      context = { ...context, auth: nextAuth, status }
      hook.rerender({ id: projectId })
    },
  }
}

async function resolve<T>(request: ReturnType<typeof deferred<T>>, value: T) {
  await act(async () => {
    request.resolve(value)
    await request.promise
  })
}

async function reject<T>(
  request: ReturnType<typeof deferred<T>>,
  value: unknown,
) {
  await act(async () => {
    request.reject(value)
    await request.promise.catch(() => undefined)
  })
}

describe('useClaudeProject owner and lifecycle fencing', () => {
  afterEach(() => vi.restoreAllMocks())

  it('projects only approved session fields and exposes consistent loading phases', async () => {
    const h = harness()
    expect(h.result.current.loading).toBe(true)
    expect(h.result.current.phase).toBe('loading')
    await resolve(h.reads[0], response())
    expect(h.result.current).toMatchObject({
      phase: 'ready',
      loading: false,
      pending: false,
      stale: false,
    })
    expect(h.result.current.session).not.toHaveProperty('managed')
    expect(h.result.current.session).not.toHaveProperty('session_name')
  })

  it('clears the prior route observation before the new GET settles', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    h.route('project-b')
    expect(h.result.current.session).toBeNull()
    expect(h.result.current.loading).toBe(true)
    await resolve(h.reads[1], response('project-b'))
    expect(h.result.current.session?.project_id).toBe('project-b')
  })

  it('does not revive the first A request after A → B → A', async () => {
    const h = harness()
    h.route('project-b')
    expect(h.reads[0].signal?.aborted).toBe(true)
    h.route('project-a')
    await resolve(h.reads[2], response('project-a', 'stopped'))
    await resolve(h.reads[0], response())
    await reject(h.reads[1], failure())
    expect(h.result.current.session?.state).toBe('stopped')
    expect(h.result.current.error).toBeNull()
    expect(h.result.current.phase).toBe('ready')
  })

  it.each(['user', 'session'] as const)(
    'fences %s replacement on the same ApiClient and rejects retained handlers',
    async (field) => {
      const h = harness()
      await resolve(h.reads[0], response())
      const oldAction = h.result.current.action
      const oldRefresh = h.result.current.refresh
      act(() => {
        void oldRefresh()
      })
      const replacement =
        field === 'user'
          ? { ...auth, user: { ...auth.user, id: 'adm_replacement' } }
          : { ...auth, session: { ...auth.session, id: 'ses_replacement' } }
      h.identity(replacement)
      expect(h.result.current.session).toBeNull()
      await act(async () => {
        await oldAction('stop')
        await oldRefresh()
      })
      expect(h.reads).toHaveLength(3)
      expect(h.writes).toHaveLength(0)
      await reject(h.reads[1], failure(403))
      expect(h.result.current.error).toBeNull()
      expect(h.result.current.loading).toBe(true)
      await resolve(h.reads[2], response('project-a', 'stopped'))
      expect(h.result.current.session?.state).toBe('stopped')
    },
  )

  it('does not invalidate equivalent auth metadata and uses the current CSRF token', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    h.identity({ ...auth, csrf_token: 'csrf-refreshed-fixture' })
    expect(h.reads).toHaveLength(1)
    act(() => {
      void h.result.current.action('stop')
    })
    expect(h.api.post).toHaveBeenCalledWith(
      '/api/v1/claude/sessions/project-a/stop',
      expect.objectContaining({ csrfToken: 'csrf-refreshed-fixture' }),
    )
    await resolve(h.writes[0], acknowledgement())
  })

  it('rejects the departed auth action ACK while the replacement owner is loading', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      void h.result.current.action('stop')
    })
    h.identity({ ...auth, session: { ...auth.session, id: 'ses_next' } })
    expect(h.writes[0].signal?.aborted).toBe(true)
    await resolve(h.writes[0], acknowledgement())
    expect(h.result.current).toMatchObject({
      session: null,
      pending: false,
      loading: true,
      error: null,
    })
    await resolve(h.reads[1], response())
    expect(h.result.current.session?.state).toBe('running')
  })

  it('ignores a superseded refresh error and finally while the newest GET is pending', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      void h.result.current.refresh()
      void h.result.current.refresh()
    })
    await reject(h.reads[1], failure())
    expect(h.result.current.loading).toBe(true)
    expect(h.result.current.error).toBeNull()
    await resolve(h.reads[2], response('project-a', 'stopped'))
    expect(h.result.current.loading).toBe(false)
    expect(h.result.current.session?.state).toBe('stopped')
  })

  it('suppresses double actions synchronously and preserves the original API contract', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      void h.result.current.action('stop')
      void h.result.current.action('start')
    })
    expect(h.writes).toHaveLength(1)
    expect(h.writes[0].path).toBe('/api/v1/claude/sessions/project-a/stop')
    expect(h.api.post).toHaveBeenCalledWith(
      h.writes[0].path,
      expect.objectContaining({ csrfToken: auth.csrf_token }),
    )
    expect(h.result.current.pending).toBe(true)
    await resolve(h.writes[0], acknowledgement())
    expect(h.result.current.pending).toBe(false)
    expect(h.result.current.session?.state).toBe('stopped')
  })

  it('a departed action failure and finally cannot clear a newer route action', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      void h.result.current.action('stop')
    })
    h.route('project-b')
    await resolve(h.reads[1], response('project-b'))
    act(() => {
      void h.result.current.action('stop')
    })
    await reject(h.writes[0], failure(403))
    expect(h.result.current.pending).toBe(true)
    expect(h.result.current.error).toBeNull()
    expect(h.result.current.session?.project_id).toBe('project-b')
    await resolve(h.writes[1], acknowledgement('project-b'))
    expect(h.result.current.pending).toBe(false)
  })

  it('allows an explicit retry after an ordinary action failure without automatic replay', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      void h.result.current.action('stop')
    })
    await reject(h.writes[0], failure())
    expect(h.result.current).toMatchObject({
      phase: 'ready',
      pending: false,
      loading: false,
    })
    expect(h.writes).toHaveLength(1)
    expect(JSON.stringify(h.result.current)).not.toContain(
      'SERVER-PROSE-CANARY',
    )
    act(() => {
      void h.result.current.action('stop')
    })
    expect(h.writes).toHaveLength(2)
    await resolve(h.writes[1], acknowledgement())
    expect(h.result.current.error).toBeNull()
  })

  it('a departed action ACK cannot revive after A → B → A', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      void h.result.current.action('stop')
    })
    h.route('project-b')
    h.route('project-a')
    await resolve(h.reads[2], response())
    await resolve(h.writes[0], acknowledgement())
    expect(h.result.current.session?.state).toBe('running')
  })

  it.each(['before', 'during'] as const)(
    'does not let a GET started %s an action overwrite its ACK',
    async (timing) => {
      const h = harness()
      await resolve(h.reads[0], response())
      act(() => {
        if (timing === 'before') void h.result.current.refresh()
        void h.result.current.action('stop')
        if (timing === 'during') void h.result.current.refresh()
      })
      expect(h.reads).toHaveLength(2)
      expect(h.writes).toHaveLength(1)
      await resolve(h.writes[0], acknowledgement())
      await resolve(h.reads[1], response())
      expect(h.result.current.session?.state).toBe('stopped')
      expect(h.result.current).toMatchObject({
        loading: false,
        pending: false,
        phase: 'ready',
      })
    },
  )

  it('discards a GET error that overlaps an acknowledged action', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      void h.result.current.action('stop')
      void h.result.current.refresh()
    })
    await resolve(h.writes[0], acknowledgement())
    await reject(h.reads[1], failure(403))
    expect(h.result.current.error).toBeNull()
    expect(h.result.current.session?.state).toBe('stopped')
  })

  it('rejects GET and mutation response project_id mismatches', async () => {
    const h = harness()
    await resolve(h.reads[0], response('project-b'))
    expect(h.result.current.session).toBeNull()
    expect(h.result.current.phase).toBe('error')
    await act(async () => h.result.current.action('start'))
    expect(h.writes).toHaveLength(0)
    act(() => {
      void h.result.current.refresh()
    })
    await resolve(h.reads[1], response())
    act(() => {
      void h.result.current.action('stop')
    })
    await resolve(h.writes[0], acknowledgement('project-b'))
    expect(h.result.current.session).toBeNull()
    expect(h.result.current.error?.code).toBe('CLAUDE_ACTION_FAILED')
    expect(h.result.current.pending).toBe(false)
  })

  it.each([401, 403])(
    'clears observations and forbids actions after HTTP %i',
    async (status) => {
      const h = harness()
      await resolve(h.reads[0], response())
      act(() => {
        void h.result.current.refresh()
      })
      await reject(h.reads[1], failure(status))
      expect(h.result.current).toMatchObject({
        session: null,
        loading: false,
        phase: 'forbidden',
      })
      expect(JSON.stringify(h.result.current)).not.toContain(
        'SERVER-PROSE-CANARY',
      )
      await act(async () => h.result.current.action('start'))
      expect(h.writes).toHaveLength(0)
    },
  )

  it.each(['hidden', 'offline', 'pagehide', 'freeze'] as const)(
    'clears %s observations and resumes with only a fresh GET',
    async (event) => {
      const h = harness()
      await resolve(h.reads[0], response())
      const retained = h.result.current.action
      act(() => {
        void retained('stop')
      })
      const visibility = vi
        .spyOn(document, 'visibilityState', 'get')
        .mockReturnValue('visible')
      act(() => {
        if (event === 'hidden') {
          visibility.mockReturnValue('hidden')
          document.dispatchEvent(new Event('visibilitychange'))
        } else
          (event === 'freeze' ? document : window).dispatchEvent(
            new Event(event),
          )
        void retained('start')
      })
      expect(h.result.current).toMatchObject({
        session: null,
        error: null,
        pending: false,
        loading: false,
        stale: true,
        phase: 'stale',
      })
      await act(async () => h.result.current.refresh())
      h.identity({
        ...auth,
        session: { ...auth.session, id: 'ses_after_suspend' },
      })
      expect(h.reads).toHaveLength(1)
      await resolve(h.writes[0], acknowledgement())
      expect(h.result.current.session).toBeNull()
      act(() => {
        if (event === 'hidden') {
          visibility.mockReturnValue('visible')
          document.dispatchEvent(new Event('visibilitychange'))
        } else if (event === 'offline')
          window.dispatchEvent(new Event('online'))
        else if (event === 'pagehide')
          window.dispatchEvent(new Event('pageshow'))
        else document.dispatchEvent(new Event('resume'))
      })
      expect(h.reads).toHaveLength(2)
      expect(h.writes).toHaveLength(1)
      await act(async () => h.result.current.action('start'))
      expect(h.writes).toHaveLength(1)
      await resolve(h.reads[1], response('project-a', 'stopped'))
      expect(h.result.current.phase).toBe('ready')
    },
  )

  it('keeps independent pagehide and freeze fences until both resume', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    act(() => {
      window.dispatchEvent(new Event('pagehide'))
      document.dispatchEvent(new Event('freeze'))
    })
    act(() => document.dispatchEvent(new Event('resume')))
    expect(h.reads).toHaveLength(1)
    expect(h.result.current.phase).toBe('stale')
    act(() => window.dispatchEvent(new Event('pageshow')))
    expect(h.reads).toHaveLength(2)
  })

  it.each([
    ['pagehide', 'route'],
    ['pagehide', 'auth'],
    ['freeze', 'route'],
    ['freeze', 'auth'],
  ] as const)(
    'preserves %s across %s replacement until the matching resume',
    async (suspension, replacement) => {
      const h = harness()
      await resolve(h.reads[0], response())
      const retained = {
        refresh: h.result.current.refresh,
        action: h.result.current.action,
      }
      act(() => {
        if (suspension === 'pagehide')
          window.dispatchEvent(new Event('pagehide'))
        else document.dispatchEvent(new Event('freeze'))
      })
      if (replacement === 'route') h.route('project-b')
      else
        h.identity({
          ...auth,
          session: { ...auth.session, id: 'ses_suspended_replacement' },
        })
      expect(h.result.current).toMatchObject({
        session: null,
        phase: 'stale',
        loading: false,
        pending: false,
      })
      await act(async () => {
        await retained.refresh()
        await h.result.current.refresh()
        await retained.action('start')
        await h.result.current.action('stop')
      })
      expect(h.reads).toHaveLength(1)
      expect(h.writes).toHaveLength(0)
      act(() => {
        if (suspension === 'pagehide')
          document.dispatchEvent(new Event('resume'))
        else window.dispatchEvent(new Event('pageshow'))
      })
      await act(async () => h.result.current.refresh())
      expect(h.reads).toHaveLength(1)
      expect(h.result.current.phase).toBe('stale')
      act(() => {
        if (suspension === 'pagehide')
          window.dispatchEvent(new Event('pageshow'))
        else document.dispatchEvent(new Event('resume'))
      })
      expect(h.reads).toHaveLength(2)
      expect(h.writes).toHaveLength(0)
      expect(h.result.current).toMatchObject({
        session: null,
        phase: 'loading',
      })
      await act(async () => h.result.current.action('start'))
      expect(h.writes).toHaveLength(0)
      const projectId = replacement === 'route' ? 'project-b' : 'project-a'
      expect(h.reads[1].path).toBe(`/api/v1/claude/sessions/${projectId}`)
      await resolve(h.reads[1], response(projectId))
      expect(h.result.current.phase).toBe('ready')
      expect(h.result.current.session?.project_id).toBe(projectId)
    },
  )

  it.each(['hidden', 'offline'] as const)(
    'hides an observation if the browser becomes %s before its event is delivered',
    async (event) => {
      const h = harness()
      await resolve(h.reads[0], response())
      if (event === 'hidden')
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
      else vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
      h.identity({ ...auth })
      expect(h.result.current).toMatchObject({
        phase: 'stale',
        stale: true,
        session: null,
        error: null,
        pending: false,
        loading: false,
      })
      await act(async () => h.result.current.action('start'))
      expect(h.writes).toHaveLength(0)
    },
  )

  it('ignores a suspended GET failure and its finally after a resumed GET starts', async () => {
    const h = harness()
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(h.reads[0].signal?.aborted).toBe(true)
    act(() => {
      window.dispatchEvent(new Event('pageshow'))
      window.dispatchEvent(new Event('pageshow'))
    })
    expect(h.reads).toHaveLength(2)
    await reject(h.reads[0], failure(401))
    expect(h.result.current).toMatchObject({
      phase: 'loading',
      loading: true,
      error: null,
      session: null,
    })
    await resolve(h.reads[1], response())
    expect(h.result.current.phase).toBe('ready')
  })

  it('clears observations when the route no longer names a Project', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    h.route(undefined)
    expect(h.result.current).toMatchObject({
      session: null,
      loading: false,
      phase: 'stale',
    })
    await act(async () => {
      await h.result.current.action('start')
      await h.result.current.refresh()
    })
    expect(h.reads).toHaveLength(1)
    expect(h.writes).toHaveLength(0)
  })

  it('does not start requests or actions without an authenticated owner', async () => {
    const h = harness('project-a', 'checking')
    await act(async () => {
      await h.result.current.refresh()
      await h.result.current.action('start')
    })
    expect(h.reads).toHaveLength(0)
    expect(h.writes).toHaveLength(0)
    expect(h.result.current.loading).toBe(false)
    h.identity(null, 'unauthenticated')
    expect(h.result.current.phase).toBe('forbidden')
  })

  it('invalidates retained handlers and pending work on unmount', async () => {
    const h = harness()
    await resolve(h.reads[0], response())
    const { action, refresh } = h.result.current
    h.unmount()
    await act(async () => {
      await action('start')
      await refresh()
    })
    expect(h.reads).toHaveLength(1)
    expect(h.writes).toHaveLength(0)
  })
})
