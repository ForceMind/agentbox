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
      project_id: 'prj_test',
      agent_type: 'claude',
      attachment_id: 'att_' + 'a'.repeat(32),
      mode: 'writer',
      lease_number: '1',
      generation: '7',
      binding_revision: '3',
      binding_digest: 'a'.repeat(64),
      auth_epoch: '2',
      api_authority_epoch: '4',
      runtime_host_installation_id: 'rhi_test',
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
})
