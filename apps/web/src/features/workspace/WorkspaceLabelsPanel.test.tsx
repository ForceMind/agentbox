import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { ApiClient, ApiError } from '../../lib/api'
import type {
  NavigationLabelData,
  WorkspaceLabelSetData,
} from '../../lib/contracts'
import { WorkspaceLabelsPanel } from './WorkspaceLabelsPanel'

const projectId = `prj_${'a'.repeat(32)}`
const workspaceId = `aws_${'c'.repeat(32)}`
const label: NavigationLabelData = {
  id: `lbl_${'b'.repeat(32)}`,
  name: 'Review',
  color: 'sky',
  revision: 1,
  updated_at: '2026-09-29T00:00:00Z',
}
const envelope = (data: object) => ({
  api_version: 'v1',
  request_id: 'req_labels',
  data,
})

function context(get: unknown, request: unknown): AuthContextValue {
  return {
    api: { get, request } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_labels', username: 'maintainer' },
      session: { id: 'ses_labels', expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf_labels',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

describe('Workspace labels', () => {
  it('converges on another client’s assignment while visible without polling a hidden page', async () => {
    let current: WorkspaceLabelSetData = {
      workspace_id: workspaceId,
      project_id: projectId,
      agent_type: 'codex',
      labels: [],
      revision: 0,
      updated_at: null,
    }
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [label] })
        : envelope(current),
    )
    let tick!: () => void
    const nativeInterval = window.setInterval.bind(window)
    const interval = vi
      .spyOn(window, 'setInterval')
      .mockImplementation((callback, delay) => {
        if (delay === 30_000 && typeof callback === 'function') {
          tick = callback as () => void
        }
        return nativeInterval(callback, delay) as unknown as ReturnType<
          typeof setInterval
        >
      })
    render(
      <AuthContext.Provider value={context(get, vi.fn())}>
        <WorkspaceLabelsPanel
          projectId={projectId}
          agentType="codex"
          locale="en"
        />
      </AuthContext.Provider>,
    )
    const checkbox = await screen.findByRole('checkbox', { name: 'Review' })
    expect(checkbox).not.toBeChecked()
    const originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden')
    try {
      current = {
        ...current,
        labels: [label],
        revision: 1,
        updated_at: '2026-09-29T00:01:00Z',
      }
      await act(async () => {
        tick()
      })
      await waitFor(() => expect(checkbox).toBeChecked())
      const readCount = get.mock.calls.length
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        value: true,
      })
      await act(async () => {
        tick()
      })
      expect(get).toHaveBeenCalledTimes(readCount)
    } finally {
      interval.mockRestore()
      if (originalHidden)
        Object.defineProperty(document, 'hidden', originalHidden)
      else Reflect.deleteProperty(document, 'hidden')
    }
  })

  it('shows a definite conflict after GET readback without retrying the write', async () => {
    const current: WorkspaceLabelSetData = {
      workspace_id: workspaceId,
      project_id: projectId,
      agent_type: 'codex',
      labels: [],
      revision: 0,
      updated_at: null,
    }
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [label] })
        : envelope(current),
    )
    const request = vi.fn(async () => {
      throw new ApiError({
        code: 'WORKSPACE_LABEL_CONFLICT',
        status: 409,
        message: 'unsafe server prose',
      })
    })
    render(
      <AuthContext.Provider value={context(get, request)}>
        <WorkspaceLabelsPanel
          projectId={projectId}
          agentType="codex"
          locale="en"
        />
      </AuthContext.Provider>,
    )
    const checkbox = await screen.findByRole('checkbox', { name: 'Review' })
    fireEvent.click(checkbox)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Workspace labels changed elsewhere.',
    )
    expect(screen.queryByText('unsafe server prose')).toBeNull()
    expect(checkbox).not.toBeChecked()
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('hides the previous Project labels immediately when selection changes', async () => {
    const otherProjectId = `prj_${'d'.repeat(32)}`
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [label] })
        : envelope({
            workspace_id: path.includes(otherProjectId)
              ? `aws_${'e'.repeat(32)}`
              : workspaceId,
            project_id: path.includes(otherProjectId)
              ? otherProjectId
              : projectId,
            agent_type: 'codex',
            labels: path.includes(otherProjectId) ? [] : [label],
            revision: path.includes(otherProjectId) ? 0 : 1,
            updated_at: path.includes(otherProjectId)
              ? null
              : '2026-09-29T00:00:00Z',
          }),
    )
    const auth = context(get, vi.fn())
    const { rerender } = render(
      <AuthContext.Provider value={auth}>
        <WorkspaceLabelsPanel
          projectId={projectId}
          agentType="codex"
          locale="en"
        />
      </AuthContext.Provider>,
    )
    expect(
      await screen.findByRole('checkbox', { name: 'Review' }),
    ).toBeChecked()
    rerender(
      <AuthContext.Provider value={auth}>
        <WorkspaceLabelsPanel
          projectId={otherProjectId}
          agentType="codex"
          locale="en"
        />
      </AuthContext.Provider>,
    )
    expect(screen.queryByRole('checkbox', { name: 'Review' })).toBeNull()
    expect(
      await screen.findByRole('checkbox', { name: 'Review' }),
    ).not.toBeChecked()
  })

  it('waits for exact ACK and fresh readback before checking an assignment', async () => {
    let current: WorkspaceLabelSetData = {
      workspace_id: workspaceId,
      project_id: projectId,
      agent_type: 'codex',
      labels: [],
      revision: 0,
      updated_at: null,
    }
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [label] })
        : envelope(current),
    )
    let finish!: (value: object) => void
    const request = vi.fn(
      () =>
        new Promise<object>((resolve) => {
          finish = resolve
        }),
    )
    render(
      <AuthContext.Provider value={context(get, request)}>
        <WorkspaceLabelsPanel
          projectId={projectId}
          agentType="codex"
          locale="en"
        />
      </AuthContext.Provider>,
    )
    const checkbox = await screen.findByRole('checkbox', { name: 'Review' })
    expect(checkbox).not.toBeChecked()
    fireEvent.click(checkbox)
    expect(checkbox).not.toBeChecked()
    expect(checkbox).toBeDisabled()
    expect(request).toHaveBeenCalledWith(
      `/api/v1/project-labels/workspaces/${projectId}/codex/${label.id}`,
      expect.objectContaining({
        method: 'PUT',
        body: { assigned: true, expected_revision: 0 },
        csrfToken: 'csrf_labels',
      }),
    )
    current = {
      ...current,
      labels: [label],
      revision: 1,
      updated_at: '2026-09-29T00:01:00Z',
    }
    finish(envelope(current))
    await waitFor(() => expect(checkbox).toBeChecked())
    expect(get).toHaveBeenCalledWith(
      `/api/v1/project-labels/workspaces/${projectId}/codex`,
      expect.objectContaining({ validate: expect.any(Function) }),
    )
  })
})
