import { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient, ApiError } from '../../lib/api'
import { AuthContext, AuthContextValue } from '../auth/AuthContext'
import { useProject } from './useProjects'

const auth = {
  user: { id: 'adm_test', username: 'maintainer' },
  session: { id: 'ses_test', expires_at: '2026-08-12T00:00:00Z' },
  csrf_token: 'csrf-test-value',
}

const projectResponse = {
  api_version: 'v1',
  request_id: 'req_project',
  data: {
    id: 'prj_test',
    slug: 'test-project',
    display_name: 'Test Project',
    source_type: 'existing',
    state: 'ready',
    repository_url: null,
    default_branch: null,
    created_at: '2026-08-12T00:00:00Z',
    updated_at: '2026-08-12T00:00:00Z',
    git: null,
    github: null,
    claude_state: 'stopped',
  },
}

const jobResponse = {
  api_version: 'v1',
  request_id: 'req_job',
  data: {
    id: 'job_test',
    type: 'git.pull',
    status: 'queued',
    target_type: 'project',
    target_id: 'prj_test',
    project_id: 'prj_test',
    progress: 0,
    phase: 'queued',
    result_summary: null,
    error_code: null,
    error_summary: null,
    created_at: '2026-08-12T00:00:00Z',
    started_at: null,
    finished_at: null,
  },
}

function jsonResponse(status: number, body: object) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
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

describe('useProject mutation idempotency', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reuses the key after an uncertain transport failure', async () => {
    const keys: string[] = []
    let attempts = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/projects/prj_test')) {
          return Promise.resolve(jsonResponse(200, projectResponse))
        }
        if (path.endsWith('/git/pull')) {
          keys.push(
            (init?.headers as Record<string, string>)['Idempotency-Key'],
          )
          attempts += 1
          return attempts === 1
            ? Promise.reject(new TypeError('response lost'))
            : Promise.resolve(jsonResponse(202, jobResponse))
        }
        return Promise.resolve(jsonResponse(404, {}))
      }),
    )
    const { result, unmount } = renderHook(() => useProject('prj_test'), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.project?.id).toBe('prj_test'))

    await act(async () => result.current.mutate('git/pull'))
    expect(result.current.error?.code).toBe('CONTROL_PLANE_UNAVAILABLE')
    await act(async () => result.current.mutate('git/pull'))

    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
    unmount()
  })

  it('generates a new key after a definitive HTTP failure', async () => {
    const keys: string[] = []
    let attempts = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/projects/prj_test')) {
          return Promise.resolve(jsonResponse(200, projectResponse))
        }
        if (path.endsWith('/git/push')) {
          keys.push(
            (init?.headers as Record<string, string>)['Idempotency-Key'],
          )
          attempts += 1
          return Promise.resolve(
            attempts === 1
              ? jsonResponse(409, {
                  error: { code: 'GIT_CONFLICT', message: 'Conflict' },
                })
              : jsonResponse(202, {
                  ...jobResponse,
                  data: { ...jobResponse.data, type: 'git.push' },
                }),
          )
        }
        return Promise.resolve(jsonResponse(404, {}))
      }),
    )
    const { result, unmount } = renderHook(() => useProject('prj_test'), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.project?.id).toBe('prj_test'))

    await act(async () => result.current.mutate('git/push'))
    expect(result.current.error?.code).toBe('GIT_CONFLICT')
    await act(async () => result.current.mutate('git/push'))

    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).not.toBe(keys[0])
    unmount()
  })

  it('exposes only bounded Job fields and discards every server summary', async () => {
    const serverCanary = 'RC9-PROJECT-JOB-SUMMARY-CANARY-9H4K'
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/projects/prj_test')) {
          return Promise.resolve(jsonResponse(200, projectResponse))
        }
        if (path.endsWith('/git/push')) {
          return Promise.resolve(
            jsonResponse(202, {
              ...jobResponse,
              data: {
                ...jobResponse.data,
                status: 'failed',
                phase: serverCanary,
                progress: 25,
                error_code: 'GIT_PUSH_FAILED',
                error_summary: serverCanary,
                result_summary: serverCanary,
              },
            }),
          )
        }
        return Promise.resolve(jsonResponse(404, {}))
      }),
    )
    const { result, unmount } = renderHook(() => useProject('prj_test'), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.project?.id).toBe('prj_test'))

    await act(async () => result.current.mutate('git/push'))

    expect(result.current.job).toEqual({
      id: 'job_test',
      status: 'failed',
      progress: 25,
      error_code: 'GIT_PUSH_FAILED',
    })
    expect(result.current.job).not.toHaveProperty('error_summary')
    expect(result.current.job).not.toHaveProperty('result_summary')
    expect(JSON.stringify(result.current.job)).not.toContain(serverCanary)
    unmount()
  })

  it('converts API failures without reading server message prose', async () => {
    const canary = 'RC9-PROJECT-API-MESSAGE-CANARY-5T2Q'
    let messageReads = 0
    const failure = new ApiError({
      code: 'PROJECT_NOT_FOUND',
      message: canary,
      requestId: 'req_project_safe_error',
      status: 404,
    })
    Object.defineProperty(failure, 'message', {
      configurable: true,
      get: () => {
        messageReads += 1
        return canary
      },
    })
    const api = {
      get: vi.fn(async () => {
        throw failure
      }),
    } as unknown as ApiClient
    const { result, unmount } = renderHook(() => useProject('prj_test'), {
      wrapper: wrapper(api),
    })

    await waitFor(() =>
      expect(result.current.error).toEqual({
        code: 'PROJECT_NOT_FOUND',
        requestId: 'req_project_safe_error',
      }),
    )
    expect(messageReads).toBe(0)
    expect(JSON.stringify(result.current.error)).not.toContain(canary)
    unmount()
  })
})

function deferredResponse() {
  let resolve!: (value: unknown) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<unknown>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function detailResponse(id: string, repository = false) {
  return {
    ...projectResponse,
    data: {
      ...projectResponse.data,
      id,
      git: repository ? { is_repository: true } : null,
    },
  }
}

function detailJob(projectId: string, status = 'queued', id = 'job_test') {
  return {
    ...jobResponse,
    data: {
      ...jobResponse.data,
      id,
      status,
      project_id: projectId,
      target_id: projectId,
    },
  }
}

function detailHarness() {
  const gets: Array<ReturnType<typeof deferredResponse> & { path: string }> = []
  const posts: Array<
    ReturnType<typeof deferredResponse> & { path: string; options: unknown }
  > = []
  const api = {
    get: vi.fn((path: string) => {
      const request = { ...deferredResponse(), path }
      gets.push(request)
      return request.promise
    }),
    post: vi.fn((path: string, options: unknown) => {
      const request = { ...deferredResponse(), path, options }
      posts.push(request)
      return request.promise
    }),
  } as unknown as ApiClient
  let currentAuth: typeof auth | null = auth
  const snapshots: Array<string | null> = []
  function AuthWrapper({ children }: { children: ReactNode }) {
    return (
      <AuthContext.Provider
        value={{
          api,
          auth: currentAuth,
          status: currentAuth ? 'authenticated' : 'unauthenticated',
          login: async () => undefined,
          logout: async () => undefined,
          refresh: async () => currentAuth,
        }}
      >
        {children}
      </AuthContext.Provider>
    )
  }
  const hook = renderHook(
    ({ id }: { id: string | undefined }) => {
      const detail = useProject(id)
      snapshots.push(detail.project?.id ?? null)
      return detail
    },
    {
      initialProps: { id: 'project-a' as string | undefined },
      wrapper: AuthWrapper,
    },
  )
  return {
    ...hook,
    gets,
    posts,
    snapshots,
    setAuth(value: typeof auth | null) {
      currentAuth = value
    },
  }
}

describe('useProject route, adminSession and lifecycle ownership', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('clears synchronously on A → B and rejects a late A response after A → B → A', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.refresh()
    })
    const oldA = h.gets[1]
    const before = h.snapshots.length
    h.rerender({ id: 'project-b' })
    expect(h.snapshots[before]).toBeNull()
    expect(h.result.current.project).toBeNull()
    h.rerender({ id: 'project-a' })
    await act(async () => h.gets[3].resolve(detailResponse('project-a')))
    await act(async () =>
      oldA.resolve({
        ...detailResponse('project-a'),
        data: { ...detailResponse('project-a').data, display_name: 'OLD A' },
      }),
    )
    await act(async () => h.gets[2].reject(new Error('old B failure')))
    expect(h.result.current.project?.display_name).toBe('Test Project')
    expect(h.result.current.error).toBeNull()
  })

  it.each(['user', 'session'] as const)(
    'fences %s replacement even when ApiClient and route stay the same',
    async (field) => {
      const h = detailHarness()
      await act(async () => h.gets[0].resolve(detailResponse('project-a')))
      const oldMutate = h.result.current.mutate
      h.setAuth({ ...auth, [field]: { ...auth[field], id: 'replacement' } })
      const before = h.snapshots.length
      h.rerender({ id: 'project-a' })
      expect(h.snapshots[before]).toBeNull()
      expect(h.gets).toHaveLength(2)
      await act(async () => oldMutate('git/pull'))
      expect(h.posts).toHaveLength(0)
      await act(async () => h.gets[1].resolve(detailResponse('project-a')))
      h.setAuth(null)
      h.rerender({ id: 'project-a' })
      expect(h.result.current.project).toBeNull()
      expect(h.result.current.busy).toBe(true)
    },
  )

  it('rejects late branch data and errors without exposing a partial project', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a', true)))
    expect(h.result.current.project).toBeNull()
    h.rerender({ id: 'project-b' })
    await act(async () => h.gets[2].resolve(detailResponse('project-b')))
    await act(async () =>
      h.gets[1].resolve({
        data: { branches: [{ name: 'old-private-branch', current: true }] },
      }),
    )
    expect(h.result.current.branches).toEqual([])
    expect(h.result.current.project?.id).toBe('project-b')
    act(() => {
      void h.result.current.refresh()
    })
    const stale = h.gets[3]
    act(() => {
      void h.result.current.refresh()
    })
    await act(async () => h.gets[4].resolve(detailResponse('project-b')))
    await act(async () => stale.reject(new Error('old error')))
    expect(h.result.current.error).toBeNull()
  })

  it('blocks synchronous double mutations and ignores an old POST/finally during a new pending operation', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
      void h.result.current.mutate('git/pull')
    })
    expect(h.posts).toHaveLength(1)
    h.rerender({ id: 'project-b' })
    await act(async () => h.gets[1].resolve(detailResponse('project-b')))
    act(() => {
      void h.result.current.mutate('git/push')
    })
    await act(async () => h.posts[0].resolve(detailJob('project-a')))
    expect(h.result.current.pending).toBe('git/push')
    expect(h.result.current.job).toBeNull()
    expect(h.result.current.busy).toBe(true)
    await act(async () => h.posts[1].resolve(detailJob('project-b')))
    expect(h.result.current.job?.id).toBe('job_test')
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    expect(h.posts).toHaveLength(2)
  })

  it('does not let an old Job poll refresh or overwrite another route', async () => {
    vi.useFakeTimers()
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    await act(async () => h.posts[0].resolve(detailJob('project-a')))
    await act(async () => vi.advanceTimersByTime(750))
    expect(h.gets[1].path).toBe('/api/v1/jobs/job_test')
    h.rerender({ id: 'project-b' })
    await act(async () => h.gets[2].resolve(detailResponse('project-b')))
    await act(async () =>
      h.gets[1].resolve(detailJob('project-a', 'succeeded')),
    )
    expect(h.gets).toHaveLength(3)
    expect(h.result.current.job).toBeNull()
    expect(h.result.current.project?.id).toBe('project-b')
  })

  it('rejects response identities for project, mutation Job and polled Job', async () => {
    vi.useFakeTimers()
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-b')))
    expect(h.result.current.project).toBeNull()
    expect(h.result.current.error?.code).toBe('PROJECT_RESPONSE_INVALID')
    act(() => {
      void h.result.current.refresh()
    })
    await act(async () => h.gets[1].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    await act(async () => h.posts[0].resolve(detailJob('project-b')))
    expect(h.result.current.job).toBeNull()
    expect(h.result.current.error?.code).toBe('PROJECT_JOB_RESPONSE_INVALID')
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    await act(async () => h.posts[1].resolve(detailJob('project-a')))
    await act(async () => vi.advanceTimersByTime(750))
    await act(async () =>
      h.gets[2].resolve(detailJob('project-a', 'succeeded', 'different-job')),
    )
    expect(h.result.current.job).toMatchObject({
      id: 'job_test',
      status: 'queued',
    })
    expect(h.result.current.error?.code).toBe('PROJECT_JOB_RESPONSE_INVALID')
    expect(h.result.current.busy).toBe(true)
    act(() => {
      void h.result.current.mutate('git/push')
    })
    expect(h.posts).toHaveLength(2)
    act(() => {
      void h.result.current.refresh()
    })
    expect(h.gets[3].path).toBe('/api/v1/jobs/job_test')
    await act(async () =>
      h.gets[3].resolve(detailJob('project-a', 'succeeded')),
    )
    expect(h.gets[4].path).toBe('/api/v1/projects/project-a')
    await act(async () => h.gets[4].resolve(detailResponse('project-a')))
    expect(h.result.current.busy).toBe(false)
  })

  it.each([
    ['offline', 'online', window],
    ['pagehide', 'pageshow', window],
    ['freeze', 'resume', document],
  ] as const)(
    'clears on %s, fences old POST, and resumes only GET on %s',
    async (hide, show, target) => {
      const h = detailHarness()
      await act(async () => h.gets[0].resolve(detailResponse('project-a')))
      const mutate = h.result.current.mutate
      act(() => {
        void mutate('git/pull')
      })
      act(() => target.dispatchEvent(new Event(hide)))
      expect(h.result.current.project).toBeNull()
      expect(h.result.current.job).toBeNull()
      expect(h.result.current.busy).toBe(true)
      await act(async () => mutate('git/push'))
      await act(async () => h.result.current.refresh())
      expect(h.posts).toHaveLength(1)
      expect(h.gets).toHaveLength(1)
      act(() => target.dispatchEvent(new Event(show)))
      expect(h.gets).toHaveLength(2)
      await act(async () => h.gets[1].resolve(detailResponse('project-a')))
      act(() => {
        void h.result.current.mutate('git/push')
      })
      await act(async () => h.posts[0].reject(new Error('late old operation')))
      expect(h.result.current.pending).toBe('git/push')
      expect(h.result.current.error).toBeNull()
      expect(h.posts).toHaveLength(2)
    },
  )

  it('explicit refresh recovers a known Job after transient poll failure without replaying POST', async () => {
    vi.useFakeTimers()
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    await act(async () => h.posts[0].resolve(detailJob('project-a')))
    await act(async () => vi.advanceTimersByTime(750))
    await act(async () =>
      h.gets[1].reject(new Error('temporary transport failure')),
    )
    expect(h.result.current.busy).toBe(true)
    act(() => {
      void h.result.current.refresh()
    })
    expect(h.gets[2].path).toBe('/api/v1/jobs/job_test')
    await act(async () =>
      h.gets[2].resolve(detailJob('project-a', 'succeeded')),
    )
    expect(h.gets[3].path).toBe('/api/v1/projects/project-a')
    await act(async () => h.gets[3].resolve(detailResponse('project-a', true)))
    await act(async () =>
      h.gets[4].resolve({
        data: { branches: [{ name: 'fresh-branch', current: true }] },
      }),
    )
    expect(h.result.current.job?.status).toBe('succeeded')
    expect(h.result.current.branches[0]?.name).toBe('fresh-branch')
    expect(h.result.current.busy).toBe(false)
    expect(h.posts).toHaveLength(1)
  })

  it('permanently rejects an old in-flight poll after readback finishes in the same React batch', async () => {
    vi.useFakeTimers()
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    await act(async () => h.posts[0].resolve(detailJob('project-a')))
    await act(async () => vi.advanceTimersByTime(750))
    expect(h.gets[1].path).toBe('/api/v1/jobs/job_test')
    await act(async () => {
      const refreshPromise = h.result.current.refresh()
      expect(h.gets[2].path).toBe('/api/v1/jobs/job_test')
      h.gets[2].resolve(detailJob('project-a', 'succeeded'))
      await h.gets[2].promise
      expect(h.gets[3].path).toBe('/api/v1/projects/project-a')
      h.gets[3].resolve(detailResponse('project-a'))
      await refreshPromise
      // Both loading and ready publications are batched: effect cleanup has
      // not yet cancelled the old request, whose transport ignores abort.
      h.gets[1].resolve(detailJob('project-a', 'queued'))
      await h.gets[1].promise
    })
    expect(h.result.current.job?.status).toBe('succeeded')
    expect(h.result.current.busy).toBe(false)
    expect(h.gets).toHaveLength(4)
    expect(h.posts).toHaveLength(1)
  })

  it.each(['detail', 'branches'] as const)(
    'keeps the known active Job through %s refresh failure and recovers on the next GET',
    async (failureStage) => {
      vi.useFakeTimers()
      const h = detailHarness()
      await act(async () => h.gets[0].resolve(detailResponse('project-a')))
      act(() => {
        void h.result.current.mutate('git/pull')
      })
      await act(async () => h.posts[0].resolve(detailJob('project-a')))
      act(() => {
        void h.result.current.refresh()
      })
      expect(h.gets[1].path).toBe('/api/v1/jobs/job_test')
      await act(async () =>
        h.gets[1].resolve(detailJob('project-a', 'running')),
      )
      if (failureStage === 'branches')
        await act(async () =>
          h.gets[2].resolve(detailResponse('project-a', true)),
        )
      const failedIndex = failureStage === 'branches' ? 3 : 2
      await act(async () =>
        h.gets[failedIndex].reject(new Error('temporary metadata failure')),
      )
      expect(h.result.current.phase).toBe('error')
      expect(h.result.current.project).toBeNull()
      expect(h.result.current.job).toMatchObject({
        id: 'job_test',
        status: 'running',
      })
      expect(h.result.current.busy).toBe(true)
      await act(async () => vi.advanceTimersByTime(1000))
      expect(h.gets).toHaveLength(failedIndex + 1)
      act(() => {
        void h.result.current.refresh()
      })
      const retry = failedIndex + 1
      expect(h.gets[retry].path).toBe('/api/v1/jobs/job_test')
      await act(async () =>
        h.gets[retry].resolve(detailJob('project-a', 'succeeded')),
      )
      await act(async () =>
        h.gets[retry + 1].resolve(detailResponse('project-a')),
      )
      expect(h.result.current.busy).toBe(false)
      expect(h.result.current.job?.status).toBe('succeeded')
      expect(h.posts).toHaveLength(1)
    },
  )

  it('a terminal POST acknowledgement reads fresh project and branches before releasing actions', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/branches', { branch: 'new-branch' })
    })
    await act(async () =>
      h.posts[0].resolve(detailJob('project-a', 'succeeded')),
    )
    expect(h.gets).toHaveLength(2)
    expect(h.gets[1].path).toBe('/api/v1/projects/project-a')
    expect(h.result.current.project).toBeNull()
    expect(h.result.current.busy).toBe(true)
    await act(async () => h.result.current.mutate('git/pull'))
    expect(h.posts).toHaveLength(1)
    await act(async () => h.gets[1].resolve(detailResponse('project-a', true)))
    await act(async () =>
      h.gets[2].resolve({
        data: { branches: [{ name: 'new-branch', current: true }] },
      }),
    )
    expect(h.result.current.branches[0]?.name).toBe('new-branch')
    expect(h.result.current.busy).toBe(false)
  })

  it('blocks a retained mutation callback when refreshed project state is no longer ready', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    const mutate = h.result.current.mutate
    act(() => {
      void h.result.current.refresh()
    })
    await act(async () =>
      h.gets[1].resolve({
        ...detailResponse('project-a'),
        data: { ...detailResponse('project-a').data, state: 'creating' },
      }),
    )
    act(() => {
      void mutate('git/pull')
    })
    expect(h.posts).toHaveLength(0)
  })

  it('retains the uncertain operation key across suspension and separates replacement adminSessions', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    act(() => window.dispatchEvent(new Event('pagehide')))
    act(() => window.dispatchEvent(new Event('pageshow')))
    expect(h.posts).toHaveLength(1)
    await act(async () => h.gets[1].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    const first = h.posts[0].options as { idempotencyKey: string }
    const retry = h.posts[1].options as { idempotencyKey: string }
    expect(retry.idempotencyKey).toBe(first.idempotencyKey)
    await act(async () => h.posts[0].reject(new Error('old transport failure')))
    expect(h.result.current.pending).toBe('git/pull')
    h.setAuth({
      ...auth,
      session: { ...auth.session, id: 'replacement-session' },
    })
    h.rerender({ id: 'project-a' })
    await act(async () => h.gets[2].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    expect(
      (h.posts[2].options as { idempotencyKey: string }).idempotencyKey,
    ).not.toBe(first.idempotencyKey)
    await act(async () => h.posts[1].resolve(detailJob('project-a')))
    expect(h.result.current.pending).toBe('git/pull')
    expect(h.result.current.job).toBeNull()
  })

  it('rejects an abort-ignoring GET after suspension and blocks actions until fresh GET', async () => {
    const h = detailHarness()
    act(() => window.dispatchEvent(new Event('offline')))
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    expect(h.result.current.project).toBeNull()
    expect(h.result.current.phase).toBe('stale')
    act(() => window.dispatchEvent(new Event('online')))
    await act(async () => h.result.current.mutate('git/pull'))
    expect(h.posts).toHaveLength(0)
    await act(async () => h.gets[1].resolve(detailResponse('project-a')))
    expect(h.result.current.phase).toBe('ready')
    expect(h.result.current.busy).toBe(false)
  })

  it('clears observations and blocks another mutation after a permission failure', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => {
      void h.result.current.mutate('git/pull')
    })
    await act(async () =>
      h.posts[0].reject(
        new ApiError({
          status: 403,
          code: 'FORBIDDEN',
          message: 'private server prose',
        }),
      ),
    )
    expect(h.result.current.phase).toBe('forbidden')
    expect(h.result.current.project).toBeNull()
    expect(h.result.current.pending).toBeNull()
    await act(async () => h.result.current.mutate('git/pull'))
    expect(h.posts).toHaveLength(1)
  })

  it.each([
    ['pagehide', 'route', 'pageshow', window],
    ['pagehide', 'session', 'pageshow', window],
    ['freeze', 'route', 'resume', document],
    ['freeze', 'session', 'resume', document],
  ] as const)(
    'preserves %s through %s ownership replacement until %s',
    async (hide, replace, resume, target) => {
      const h = detailHarness()
      await act(async () => h.gets[0].resolve(detailResponse('project-a')))
      const oldRefresh = h.result.current.refresh
      const oldMutate = h.result.current.mutate
      act(() => target.dispatchEvent(new Event(hide)))
      if (replace === 'session')
        h.setAuth({
          ...auth,
          session: { ...auth.session, id: 'replacement-session' },
        })
      const id = replace === 'route' ? 'project-b' : 'project-a'
      h.rerender({ id })
      expect(h.result.current.phase).toBe('stale')
      expect(h.result.current.project).toBeNull()
      await act(async () => {
        await oldRefresh()
        await h.result.current.refresh()
        await oldMutate('git/pull')
        await h.result.current.mutate('git/pull')
      })
      expect(h.gets).toHaveLength(1)
      expect(h.posts).toHaveLength(0)
      act(() => target.dispatchEvent(new Event(resume)))
      expect(h.gets).toHaveLength(2)
      expect(h.gets[1].path).toBe(`/api/v1/projects/${id}`)
      await act(async () => h.gets[1].resolve(detailResponse(id)))
      expect(h.result.current.phase).toBe('ready')
    },
  )

  it('keeps pagehide and freeze fences independently until both are released', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a')))
    act(() => window.dispatchEvent(new Event('pagehide')))
    act(() => document.dispatchEvent(new Event('freeze')))
    act(() => document.dispatchEvent(new Event('resume')))
    expect(h.result.current.phase).toBe('stale')
    expect(h.gets).toHaveLength(1)
    act(() => window.dispatchEvent(new Event('pageshow')))
    expect(h.gets).toHaveLength(2)
  })

  it('visibility loss clears branch observations and does not defeat a pagehide fence', async () => {
    const h = detailHarness()
    await act(async () => h.gets[0].resolve(detailResponse('project-a', true)))
    await act(async () =>
      h.gets[1].resolve({
        data: { branches: [{ name: 'main', current: true }] },
      }),
    )
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(h.result.current.branches).toEqual([])
    expect(h.result.current.project).toBeNull()
    act(() => window.dispatchEvent(new Event('pagehide')))
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(h.gets).toHaveLength(2)
    act(() => window.dispatchEvent(new Event('pageshow')))
    expect(h.gets).toHaveLength(3)
  })
})
