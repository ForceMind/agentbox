import { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient } from '../../lib/api'
import { AuthContext, AuthContextValue } from '../auth/AuthContext'
import { useWorkspaceActions } from './useWorkspaceActions'

const auth = {
  user: { id: 'adm_test', username: 'maintainer' },
  session: { id: 'ses_test', expires_at: '2026-08-12T00:00:00Z' },
  csrf_token: 'csrf-test-value',
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

describe('useWorkspaceActions', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('issues a transient attachment ticket with CSRF protection', async () => {
    const ticket = {
      protocol_version: 1,
      request_id: 'wreq_test',
      ticket: 'ticket-memory-only',
      workspace_id: 'aws_0123456789abcdef0123456789abcdef',
      project_id: 'prj_' + '1'.repeat(32),
      agent_type: 'claude',
      attachment_id: 'att_' + 'a'.repeat(32),
      mode: 'writer',
      lease_number: '1',
      generation: '7',
      binding_revision: '3',
      binding_digest: 'a'.repeat(64),
      auth_epoch: '2',
      api_authority_epoch: '4',
      runtime_host_installation_id: 'wri_' + '2'.repeat(32),
      runtime_host_installation_revision: '1',
      runtime_epoch: '5',
      expires_at: '2026-08-12T00:00:00Z',
    }
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(ticket), { status: 200 })),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useWorkspaceActions(), {
      wrapper: wrapper(new ApiClient()),
    })

    let response: unknown
    await act(async () => {
      response = await result.current.connect(ticket.workspace_id)
    })
    await waitFor(() => expect(result.current.pending).toBeNull())
    expect(response).toMatchObject({ attachment_id: ticket.attachment_id })
    expect(window.localStorage).toHaveLength(0)
    expect(window.sessionStorage).toHaveLength(0)
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/workspaces/${ticket.workspace_id}/attachments`,
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-CSRF-Token': auth.csrf_token }),
      }),
    )
  })

  it('uses fixed Claude and Codex start routes and rejects a mismatched response', async () => {
    const response = (agentType: string) => ({
      request_id: 'req_start',
      workspace_id: 'aws_0123456789abcdef0123456789abcdef',
      project_id: 'prj_0123456789abcdef0123456789abcdef',
      agent_type: agentType,
      state: 'RUNNING',
      generation: '1',
    })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(response('claude')), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(response('codex')), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(response('claude')), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useWorkspaceActions(), {
      wrapper: wrapper(new ApiClient()),
    })
    await act(async () => {
      await result.current.start(
        'prj_0123456789abcdef0123456789abcdef',
        'claude',
      )
    })
    await act(async () => {
      await result.current.start(
        'prj_0123456789abcdef0123456789abcdef',
        'codex',
      )
    })
    await act(async () => {
      await expect(
        result.current.start('prj_0123456789abcdef0123456789abcdef', 'codex'),
      ).rejects.toThrow()
    })
    expect(fetchMock.mock.calls[0][0]).toContain('/workspaces/claude/start')
    expect(fetchMock.mock.calls[1][0]).toContain('/workspaces/codex/start')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('rejects a concurrent action as busy and keeps ticket response ephemeral', async () => {
    let release!: (response: Response) => void
    const pending = new Promise<Response>((resolve) => {
      release = resolve
    })
    const fetchMock = vi.fn(() => pending)
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useWorkspaceActions(), {
      wrapper: wrapper(new ApiClient()),
    })
    let first: Promise<unknown>
    act(() => {
      first = result.current.connect('aws_0123456789abcdef0123456789abcdef')
    })
    await waitFor(() => expect(result.current.pending).toBe('connect'))
    await act(async () => {
      await expect(
        result.current.stop('aws_0123456789abcdef0123456789abcdef', '1'),
      ).rejects.toMatchObject({ code: 'WAW_ACTION_BUSY' })
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await act(async () => {
      release(new Response(JSON.stringify({}), { status: 500 }))
      await expect(first!).rejects.toThrow()
    })
  })

  it('rejects Stop and Detach replies for a different generation or lease', async () => {
    const workspaceId = 'aws_' + '1'.repeat(32)
    const stop = {
      request_id: 'req_stop',
      workspace_id: workspaceId,
      project_id: 'prj_' + '2'.repeat(32),
      agent_type: 'codex',
      generation: '1',
      stop_operation_id: 'wso_' + '3'.repeat(32),
      state: 'STOPPED',
    }
    const detached = {
      request_id: 'req_detach',
      workspace_id: workspaceId,
      detach_operation_id: 'wdo_' + '4'.repeat(32),
      attachment_id: 'att_' + '5'.repeat(32),
      generation: '1',
      lease_number: '7',
      result: 'detached',
      cleanup_state: 'ATTACH_PTY_CLOSED',
      state: 'RUNNING',
    }
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useWorkspaceActions(), {
      wrapper: wrapper(new ApiClient()),
    })
    for (const body of [
      { ...stop, generation: '2' },
      { ...stop, agent_type: 'claude' },
    ]) {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(body), { status: 200 }),
      )
      await act(async () => {
        await expect(
          result.current.stop(workspaceId, '1', 'codex'),
        ).rejects.toThrow()
      })
    }
    for (const patch of [
      { attachment_id: 'att_' + '6'.repeat(32) },
      { generation: '2' },
      { lease_number: '8' },
    ]) {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ ...detached, ...patch }), {
          status: 200,
        }),
      )
      await act(async () => {
        await expect(
          result.current.detach(
            workspaceId,
            detached.attachment_id,
            '1',
            '7',
            'codex',
          ),
        ).rejects.toThrow()
      })
    }
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(stop), { status: 200 }),
    )
    await act(async () => {
      expect(
        (await result.current.stop(workspaceId, '1', 'codex'))?.state,
      ).toBe('STOPPED')
    })
    expect(result.current.error).toBeNull()
    expect(window.localStorage).toHaveLength(0)
  })

  it('invalidates an old session response without clearing a new pending operation', async () => {
    const projectId = 'prj_' + '1'.repeat(32)
    const body = {
      request_id: 'req_start',
      workspace_id: 'aws_' + '2'.repeat(32),
      project_id: projectId,
      agent_type: 'codex',
      state: 'RUNNING',
      generation: '1',
    }
    const releases: ((response: Response) => void)[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>((resolve) => releases.push(resolve))),
    )
    let currentAuth = auth
    const api = new ApiClient()
    function ChangingAuth({ children }: { children: ReactNode }) {
      return (
        <AuthContext.Provider
          value={{
            api,
            auth: currentAuth,
            status: 'authenticated',
            login: async () => undefined,
            logout: async () => undefined,
            refresh: async () => currentAuth,
          }}
        >
          {children}
        </AuthContext.Provider>
      )
    }
    const { result, rerender } = renderHook(() => useWorkspaceActions(), {
      wrapper: ChangingAuth,
    })
    let old: Promise<unknown>
    act(() => {
      old = result.current.start(projectId, 'codex').catch((error) => error)
    })
    act(() => {
      currentAuth = {
        ...auth,
        session: { ...auth.session, id: 'ses_new' },
        csrf_token: 'csrf-new',
      }
      rerender()
    })
    expect(result.current.pending).toBeNull()
    let next: Promise<unknown>
    act(() => {
      next = result.current.start(projectId, 'codex')
    })
    await act(async () => {
      releases[0](new Response(JSON.stringify(body), { status: 200 }))
      expect(await old!).toMatchObject({ code: 'WAW_ACTION_STALE' })
    })
    expect(result.current.pending).toBe('start')
    expect(result.current.error).toBeNull()
    await act(async () => {
      releases[1](new Response(JSON.stringify(body), { status: 200 }))
      await next!
    })
    expect(result.current.pending).toBeNull()
  })

  it('does not return a response after unmount or send an invalid AgentType', async () => {
    let release!: (response: Response) => void
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { result, unmount } = renderHook(() => useWorkspaceActions(), {
      wrapper: wrapper(new ApiClient()),
    })
    await expect(
      result.current.start('prj_' + '1'.repeat(32), 'shell' as 'codex'),
    ).rejects.toMatchObject({ code: 'WAW_INVALID_AGENT' })
    expect(fetchMock).not.toHaveBeenCalled()
    let request: Promise<unknown>
    act(() => {
      request = result.current
        .start('prj_' + '1'.repeat(32), 'codex')
        .catch((error) => error)
    })
    unmount()
    release(
      new Response(
        JSON.stringify({
          request_id: 'req_start',
          workspace_id: 'aws_' + '2'.repeat(32),
          project_id: 'prj_' + '1'.repeat(32),
          agent_type: 'codex',
          state: 'RUNNING',
          generation: '1',
        }),
        { status: 200 },
      ),
    )
    expect(await request!).toMatchObject({ code: 'WAW_ACTION_STALE' })
  })
})
