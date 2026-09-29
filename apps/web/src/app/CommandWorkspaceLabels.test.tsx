import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import { NAVIGATION_LABELS_CHANGED_EVENT } from '../features/projects/labelEvents'
import { ApiClient, ApiError } from '../lib/api'
import type {
  NavigationLabelData,
  WorkspaceLabelSetData,
} from '../lib/contracts'
import { CommandCenter } from './CommandCenter'
import { workspaceLabelResults } from './commandCenterResults'

const projectId = `prj_${'a'.repeat(32)}`
const workspaceId = `aws_${'c'.repeat(32)}`
const label: NavigationLabelData = {
  id: `lbl_${'b'.repeat(32)}`,
  name: 'Design',
  color: 'sky',
  revision: 1,
  updated_at: '2026-09-29T00:00:00Z',
}
const metadata = {
  id: workspaceId,
  project_id: projectId,
  agent_type: 'codex',
  state: 'STOPPED',
  reconciliation_state: 'authoritative',
  generation: 1,
  revision: 1,
  created_at: '2026-09-29T00:00:00Z',
  updated_at: '2026-09-29T00:00:00Z',
  last_seen_at: '2026-09-29T00:00:00Z',
  exit_code: null,
  failure_code: null,
}

function assignment(
  labels: NavigationLabelData[],
  revision: number,
): WorkspaceLabelSetData {
  return {
    workspace_id: workspaceId,
    project_id: projectId,
    agent_type: 'codex',
    labels,
    revision,
    updated_at: revision ? '2026-09-29T00:01:00Z' : null,
  }
}

function context(get: unknown, request: unknown): AuthContextValue {
  return {
    api: { get, request } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_command', username: 'maintainer' },
      session: { id: 'ses_command', expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf-command',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

function view(get: unknown, request: unknown) {
  const onClose = vi.fn()
  render(
    <AuthContext.Provider value={context(get, request)}>
      <CommandCenter
        actions={[]}
        locale="en"
        onClose={onClose}
        onNavigate={vi.fn()}
        workspaceId={workspaceId}
      />
    </AuthContext.Provider>,
  )
  return onClose
}

describe('Workspace label command choices', () => {
  it('keeps label choices query-only and keyed by immutable identity', () => {
    expect(workspaceLabelResults([label], new Set(), '')).toEqual([])
    expect(
      workspaceLabelResults([label], new Set([label.id]), 'label'),
    ).toMatchObject([
      {
        kind: 'workspace-label',
        id: `workspace-label:${label.id}`,
        assigned: true,
      },
    ])
    expect(workspaceLabelResults([label], new Set(), 'other')).toEqual([])
  })

  it('toggles the exact current Workspace label with CAS and GET readback', async () => {
    const changed = vi.fn()
    window.addEventListener(NAVIGATION_LABELS_CHANGED_EVENT, changed)
    let current = assignment([], 0)
    const get = vi.fn(async (path: string) => {
      if (path === '/api/v1/projects') return { data: { projects: [] } }
      if (path === `/api/v1/workspaces/${workspaceId}`) return metadata
      if (path === '/api/v1/project-labels')
        return { data: { labels: [label] } }
      return { data: current }
    })
    const request = vi.fn(async () => {
      current = assignment([label], 1)
      return { data: current }
    })
    const onClose = view(get, request)
    const dialog = await screen.findByRole('dialog', { name: 'Command center' })
    const search = within(dialog).getByRole('combobox', {
      name: 'Search pages, Projects and Workspace labels',
    })
    fireEvent.change(search, { target: { value: 'label' } })
    const option = await within(dialog).findByRole('option', {
      name: /Label as Design/,
    })
    expect(option).toHaveTextContent('Available')
    fireEvent.click(option)
    await waitFor(() =>
      expect(
        within(dialog).getByRole('option', { name: /Label as Design/ }),
      ).toHaveTextContent('Assigned'),
    )
    expect(request).toHaveBeenCalledWith(
      `/api/v1/project-labels/workspaces/${projectId}/codex/${label.id}`,
      expect.objectContaining({
        method: 'PUT',
        body: { assigned: true, expected_revision: 0 },
        csrfToken: 'csrf-command',
      }),
    )
    expect(
      get.mock.calls.filter(
        ([path]) => path === `/api/v1/workspaces/${workspaceId}`,
      ),
    ).toHaveLength(2)
    expect(request).toHaveBeenCalledTimes(1)
    expect(changed).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
    window.removeEventListener(NAVIGATION_LABELS_CHANGED_EVENT, changed)
  })

  it('re-reads a rejected conflict without replay or server prose', async () => {
    const get = vi.fn(async (path: string) => {
      if (path === '/api/v1/projects') return { data: { projects: [] } }
      if (path === `/api/v1/workspaces/${workspaceId}`) return metadata
      if (path === '/api/v1/project-labels')
        return { data: { labels: [label] } }
      return { data: assignment([], 0) }
    })
    const request = vi.fn(async () => {
      throw new ApiError({
        code: 'WORKSPACE_LABEL_CONFLICT',
        status: 409,
        message: 'private server prose',
      })
    })
    view(get, request)
    const dialog = await screen.findByRole('dialog', { name: 'Command center' })
    const search = within(dialog).getByRole('combobox', {
      name: 'Search pages, Projects and Workspace labels',
    })
    fireEvent.change(search, { target: { value: 'design' } })
    fireEvent.click(
      await within(dialog).findByRole('option', { name: /Label as Design/ }),
    )
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Workspace labels changed elsewhere.',
    )
    expect(screen.queryByText('private server prose')).toBeNull()
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('keeps modal navigation fenced until the label write is acknowledged', async () => {
    let current = assignment([], 0)
    const get = vi.fn(async (path: string) => {
      if (path === '/api/v1/projects') return { data: { projects: [] } }
      if (path === `/api/v1/workspaces/${workspaceId}`) return metadata
      if (path === '/api/v1/project-labels')
        return { data: { labels: [label] } }
      return { data: current }
    })
    let finish!: (value: object) => void
    const request = vi.fn(
      () =>
        new Promise<object>((resolve) => {
          finish = resolve
        }),
    )
    const onClose = view(get, request)
    const dialog = await screen.findByRole('dialog', { name: 'Command center' })
    const search = within(dialog).getByRole('combobox', {
      name: 'Search pages, Projects and Workspace labels',
    })
    fireEvent.change(search, { target: { value: 'label' } })
    const option = await within(dialog).findByRole('option', {
      name: /Label as Design/,
    })
    fireEvent.click(option)
    expect(option).toHaveAttribute('aria-disabled', 'true')
    expect(
      within(dialog).getByRole('button', { name: 'Close command center' }),
    ).toBeDisabled()
    fireEvent.keyDown(search, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
    current = assignment([label], 1)
    await act(async () => finish({ data: current }))
    await waitFor(() =>
      expect(
        within(dialog).getByRole('option', { name: /Label as Design/ }),
      ).toHaveTextContent('Assigned'),
    )
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('re-reads after a hidden pending write settles without replaying it', async () => {
    let current = assignment([], 0)
    const get = vi.fn(async (path: string) => {
      if (path === '/api/v1/projects') return { data: { projects: [] } }
      if (path === `/api/v1/workspaces/${workspaceId}`) return metadata
      if (path === '/api/v1/project-labels')
        return { data: { labels: [label] } }
      return { data: current }
    })
    let finish!: (value: object) => void
    const request = vi.fn(
      () =>
        new Promise<object>((resolve) => {
          finish = resolve
        }),
    )
    view(get, request)
    const dialog = await screen.findByRole('dialog', { name: 'Command center' })
    const search = within(dialog).getByRole('combobox', {
      name: 'Search pages, Projects and Workspace labels',
    })
    fireEvent.change(search, { target: { value: 'design' } })
    fireEvent.click(
      await within(dialog).findByRole('option', { name: /Label as Design/ }),
    )
    expect(request).toHaveBeenCalledTimes(1)
    const originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden')
    try {
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        value: true,
      })
      fireEvent(document, new Event('visibilitychange'))
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        value: false,
      })
      fireEvent(document, new Event('visibilitychange'))
      current = assignment([label], 1)
      await act(async () => finish({ data: current }))
      await waitFor(() =>
        expect(
          within(dialog).getByRole('option', { name: /Label as Design/ }),
        ).toHaveTextContent('Assigned'),
      )
      expect(request).toHaveBeenCalledTimes(1)
    } finally {
      if (originalHidden)
        Object.defineProperty(document, 'hidden', originalHidden)
      else Reflect.deleteProperty(document, 'hidden')
    }
  })
})
