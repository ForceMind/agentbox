import { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient, ApiError } from '../../lib/api'
import { AuthContext, AuthContextValue } from '../auth/AuthContext'
import { useWorkspaceStatus } from './useWorkspaceStatus'

const auth = {
  user: { id: 'adm_test', username: 'maintainer' },
  session: { id: 'ses_test', expires_at: '2026-08-12T00:00:00Z' },
  csrf_token: 'csrf-test-value',
}

const statusResponse = {
  request_id: 'wreq_test',
  data: {
    workspace_id: 'aws_0123456789abcdef0123456789abcdef',
    project_id: 'prj_test',
    agent_type: 'claude',
    generation: '7',
    binding_revision: '3',
    binding_digest: 'a'.repeat(64),
    state: 'running',
    reconciliation_state: 'healthy',
    runtime_epoch: 'epoch_test',
    process_state: 'running',
    exit_code: null,
    attachment_capacity: { admitted: '0', pending: '0', limit: '1' },
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

describe('useWorkspaceStatus', () => {
  afterEach(() => {
    setVisibility('visible')
    setOnline(true)
    vi.unstubAllGlobals()
  })

  function setVisibility(value: DocumentVisibilityState) {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value,
    })
  }

  function setOnline(value: boolean) {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value,
    })
  }

  it('loads bounded metadata and URL-encodes the workspace identifier', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(200, statusResponse))
    vi.stubGlobal('fetch', fetchMock)
    const workspaceId = 'aws_0123456789abcdef0123456789abcdef'
    const { result } = renderHook(() => useWorkspaceStatus(workspaceId), {
      wrapper: wrapper(new ApiClient()),
    })

    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    expect(result.current.view).toMatchObject({
      status: 'loaded',
      response: statusResponse,
      receivedAt: expect.any(Number),
      observationToken: expect.any(Number),
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/status`,
      expect.objectContaining({ credentials: 'include', method: 'GET' }),
    )
  })

  it.each([401, 404, 502, 503])(
    'reports HTTP %s as an error without admission',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.resolve(jsonResponse(status, {}))),
      )
      const { result } = renderHook(
        () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
        { wrapper: wrapper(new ApiClient()) },
      )

      await waitFor(() => expect(result.current.view.status).toBe('error'))
      expect(result.current.view).toMatchObject({
        status: 'error',
        error: { code: `HTTP_${status}` },
      })
    },
  )

  it('stores only stable error evidence without reading ApiError.message', async () => {
    const messageRead = vi.fn()
    const failure = new ApiError({
      code: 'WAW_STATUS_UNAVAILABLE',
      message: 'unsafe server status prose',
      requestId: 'req_workspace_status',
      retryAfter: 17,
      status: 503,
    })
    Object.defineProperty(failure, 'message', {
      configurable: true,
      get: () => {
        messageRead()
        return 'unsafe server status prose'
      },
    })
    const api = {
      get: vi.fn(async () => {
        throw failure
      }),
    } as unknown as ApiClient
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(api) },
    )

    await waitFor(() => expect(result.current.view.status).toBe('error'))
    expect(result.current.view).toEqual({
      status: 'error',
      error: {
        code: 'WAW_STATUS_UNAVAILABLE',
        requestId: 'req_workspace_status',
        retryAfter: 17,
      },
    })
    expect(messageRead).not.toHaveBeenCalled()
    expect(JSON.stringify(result.current.view)).not.toContain(
      'unsafe server status prose',
    )
  })

  it('does not request status when no workspace is selected', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useWorkspaceStatus(undefined), {
      wrapper: wrapper(new ApiClient()),
    })

    await waitFor(() => expect(result.current.view.status).toBe('idle'))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('ignores a stale response after the workspace changes', async () => {
    let resolveFirst!: (response: Response) => void
    const first = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })
    const secondResponse = {
      ...statusResponse,
      data: {
        ...statusResponse.data,
        workspace_id: 'aws_fedcba9876543210fedcba9876543210',
      },
    }
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce(jsonResponse(200, secondResponse))
    vi.stubGlobal('fetch', fetchMock)
    const { result, rerender } = renderHook(
      ({ workspaceId }: { workspaceId: string }) =>
        useWorkspaceStatus(workspaceId),
      {
        initialProps: { workspaceId: 'aws_0123456789abcdef0123456789abcdef' },
        wrapper: wrapper(new ApiClient()),
      },
    )

    rerender({ workspaceId: 'aws_fedcba9876543210fedcba9876543210' })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    resolveFirst(jsonResponse(200, { ...statusResponse, request_id: 'stale' }))
    await act(async () => await first)
    expect(result.current.view).toMatchObject({
      status: 'loaded',
      response: secondResponse,
    })
  })

  it('does not update state after unmount', async () => {
    let resolve!: (response: Response) => void
    const pending = new Promise<Response>((value) => {
      resolve = value
    })
    const fetchMock = vi.fn<typeof fetch>().mockReturnValue(pending)
    vi.stubGlobal('fetch', fetchMock)
    const { unmount } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )

    unmount()
    expect(fetchMock.mock.calls[0]![1]?.signal?.aborted).toBe(true)
    resolve(jsonResponse(200, statusResponse))
    await act(async () => await pending)
  })

  it('invalidates a loaded observation synchronously when the page becomes hidden', async () => {
    setVisibility('visible')
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(200, statusResponse))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    setVisibility('hidden')
    act(() => document.dispatchEvent(new Event('visibilitychange')))

    expect(result.current.view.status).toBe('stale')
    expect(JSON.stringify(result.current.view)).not.toContain('runtime_epoch')
  })

  it('performs one coalesced read-only refresh after returning visible', async () => {
    setVisibility('visible')
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementation(() =>
        Promise.resolve(jsonResponse(200, statusResponse)),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    setVisibility('hidden')
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    setVisibility('visible')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('pageshow'))
    })

    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(
      fetchMock.mock.calls.every(([, init]) => init?.method === 'GET'),
    ).toBe(true)
  })

  it('aborts the in-flight GET and ignores its late success after pagehide', async () => {
    setVisibility('visible')
    let release!: (response: Response) => void
    const pending = new Promise<Response>((resolve) => {
      release = resolve
    })
    const fetchMock = vi.fn<typeof fetch>().mockReturnValue(pending)
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const signal = fetchMock.mock.calls[0]![1]?.signal

    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(signal?.aborted).toBe(true)
    expect(result.current.view.status).toBe('stale')

    release(jsonResponse(200, statusResponse))
    await act(async () => await pending)
    expect(result.current.view.status).toBe('stale')
    expect(JSON.stringify(result.current.view)).not.toContain('runtime_epoch')
  })

  it('does not let an old request finally clear the new single-flight request', async () => {
    setVisibility('visible')
    let releaseFirst!: (response: Response) => void
    let releaseSecond!: (response: Response) => void
    const first = new Promise<Response>((resolve) => {
      releaseFirst = resolve
    })
    const second = new Promise<Response>((resolve) => {
      releaseSecond = resolve
    })
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockReturnValueOnce(first)
      .mockReturnValueOnce(second)
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    act(() => window.dispatchEvent(new Event('pagehide')))
    act(() => window.dispatchEvent(new Event('pageshow')))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.current.view.status).toBe('revalidating')

    releaseFirst(jsonResponse(200, { ...statusResponse, request_id: 'old' }))
    await act(async () => await first)
    act(() => {
      window.dispatchEvent(new Event('pageshow'))
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.current.view.status).toBe('revalidating')

    releaseSecond(jsonResponse(200, statusResponse))
    await act(async () => await second)
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
  })

  it('ignores a late GET failure after offline invalidation', async () => {
    setVisibility('visible')
    setOnline(true)
    let reject!: (error: Error) => void
    const pending = new Promise<Response>((_resolve, fail) => {
      reject = fail
    })
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockReturnValue(pending))
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )

    setOnline(false)
    act(() => window.dispatchEvent(new Event('offline')))
    reject(new Error('late network failure'))
    await act(async () => await pending.catch(() => undefined))

    expect(result.current.view.status).toBe('stale')
    expect(JSON.stringify(result.current.view)).not.toContain(
      'late network failure',
    )
  })

  it('invalidates a loaded observation on freeze and refreshes once on return', async () => {
    setVisibility('visible')
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementation(() =>
        Promise.resolve(jsonResponse(200, statusResponse)),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    act(() => document.dispatchEvent(new Event('freeze')))
    expect(result.current.view.status).toBe('stale')
    act(() => {
      window.dispatchEvent(new Event('pageshow'))
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('does not read while visible but offline and coalesces the online event burst', async () => {
    setVisibility('visible')
    setOnline(true)
    let releaseSecond!: (response: Response) => void
    const second = new Promise<Response>((resolve) => {
      releaseSecond = resolve
    })
    const fetchMock = vi
      .fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValueOnce(jsonResponse(200, statusResponse))
      .mockReturnValueOnce(second)
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    setOnline(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('pageshow'))
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result.current.view.status).toBe('stale')

    setOnline(true)
    act(() => {
      window.dispatchEvent(new Event('online'))
      window.dispatchEvent(new Event('pageshow'))
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('online'))
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.current.view.status).toBe('revalidating')
    releaseSecond(jsonResponse(200, statusResponse))
    await act(async () => await second)
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
  })

  it('does not treat the initial pageshow or duplicate visible events as a refresh', async () => {
    setVisibility('visible')
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(200, statusResponse))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))

    act(() => {
      window.dispatchEvent(new Event('pageshow'))
      document.dispatchEvent(new Event('visibilitychange'))
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await act(async () => await Promise.resolve())
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('aborts the old request when the session or CSRF scope changes', async () => {
    setVisibility('visible')
    let currentAuth = auth
    let releaseFirst!: (response: Response) => void
    const first = new Promise<Response>((resolve) => {
      releaseFirst = resolve
    })
    const nextResponse = { ...statusResponse, request_id: 'wreq_new_scope' }
    const fetchMock = vi
      .fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce(jsonResponse(200, nextResponse))
    vi.stubGlobal('fetch', fetchMock)
    const dynamicApi = new ApiClient()
    function DynamicWrapper({ children }: { children: ReactNode }) {
      return (
        <AuthContext.Provider
          value={{
            api: dynamicApi,
            auth: currentAuth,
            login: async () => undefined,
            logout: async () => undefined,
            refresh: async () => currentAuth,
            status: 'authenticated',
          }}
        >
          {children}
        </AuthContext.Provider>
      )
    }
    const { result, rerender } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: DynamicWrapper },
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const oldSignal = fetchMock.mock.calls[0]![1]?.signal

    currentAuth = {
      ...auth,
      session: { ...auth.session, id: 'ses_new' },
      csrf_token: 'csrf-new',
    }
    rerender()
    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    expect(oldSignal?.aborted).toBe(true)
    expect(result.current.view).toMatchObject({
      status: 'loaded',
      response: nextResponse,
    })

    releaseFirst(jsonResponse(200, { ...statusResponse, request_id: 'old' }))
    await act(async () => await first)
    expect(result.current.view).toMatchObject({
      status: 'loaded',
      response: nextResponse,
    })
  })
})
