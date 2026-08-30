import { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient } from '../../lib/api'
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
  afterEach(() => vi.unstubAllGlobals())

  it('loads bounded metadata and URL-encodes the workspace identifier', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse(200, statusResponse)),
    )
    vi.stubGlobal('fetch', fetchMock)
    const workspaceId = 'aws_0123456789abcdef0123456789abcdef'
    const { result } = renderHook(() => useWorkspaceStatus(workspaceId), {
      wrapper: wrapper(new ApiClient()),
    })

    await waitFor(() => expect(result.current.view.status).toBe('loaded'))
    expect(result.current.view).toMatchObject({
      status: 'loaded',
      response: statusResponse,
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
        error: { status },
      })
    },
  )

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
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce(jsonResponse(200, statusResponse))
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
      response: statusResponse,
    })
  })

  it('does not update state after unmount', async () => {
    let resolve!: (response: Response) => void
    const pending = new Promise<Response>((value) => {
      resolve = value
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(() => pending),
    )
    const { unmount } = renderHook(
      () => useWorkspaceStatus('aws_0123456789abcdef0123456789abcdef'),
      { wrapper: wrapper(new ApiClient()) },
    )

    unmount()
    resolve(jsonResponse(200, statusResponse))
    await act(async () => await pending)
  })
})
