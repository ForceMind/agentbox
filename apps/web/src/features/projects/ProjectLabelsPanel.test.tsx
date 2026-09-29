import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { ApiClient, ApiError } from '../../lib/api'
import type {
  NavigationLabelData,
  ProjectLabelSetData,
} from '../../lib/contracts'
import { ProjectLabelsPanel } from './ProjectLabelsPanel'

const projectId = `prj_${'a'.repeat(32)}`
const labelId = `lbl_${'b'.repeat(32)}`
const updatedAt = '2026-09-29T00:00:00Z'
const initialLabel: NavigationLabelData = {
  id: labelId,
  name: 'Design',
  color: 'sky',
  revision: 1,
  updated_at: updatedAt,
}
const originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden')

function envelope(data: object) {
  return { api_version: 'v1', request_id: 'req_labels', data } as const
}

function context(
  get: unknown,
  request: unknown,
  sessionId = 'ses_labels',
): AuthContextValue {
  return {
    api: { get, request } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_labels', username: 'maintainer' },
      session: { id: sessionId, expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf_labels',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

function withAuth(value: AuthContextValue, children: ReactNode) {
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

afterEach(() => {
  if (originalHidden) Object.defineProperty(document, 'hidden', originalHidden)
})

describe('Project labels UI', () => {
  it('waits for exact assignment ACK and fresh readback without optimistic checks', async () => {
    let current: ProjectLabelSetData = {
      project_id: projectId,
      labels: [initialLabel],
      revision: 1,
      updated_at: updatedAt,
    }
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [initialLabel] })
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
      withAuth(
        context(get, request),
        <ProjectLabelsPanel projectId={projectId} locale="en" />,
      ),
    )
    expect(await screen.findByText('Design')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Manage labels' }))
    const dialog = screen.getByRole('dialog', { name: 'Manage labels' })
    const checkbox = await within(dialog).findByRole('checkbox', {
      name: 'Design',
    })
    expect(checkbox).toBeChecked()
    fireEvent.click(checkbox)
    expect(checkbox).toBeChecked()
    expect(request).toHaveBeenCalledWith(
      `/api/v1/project-labels/projects/${projectId}/${labelId}`,
      expect.objectContaining({
        method: 'PUT',
        body: { assigned: false, expected_revision: 1 },
        csrfToken: 'csrf_labels',
      }),
    )
    current = {
      project_id: projectId,
      labels: [],
      revision: 2,
      updated_at: updatedAt,
    }
    await act(async () => finish(envelope(current)))
    await waitFor(() =>
      expect(
        within(dialog).getByRole('checkbox', { name: 'Design' }),
      ).not.toBeChecked(),
    )
    expect(request).toHaveBeenCalledTimes(1)
    expect(
      get.mock.calls.filter(([path]) => path === '/api/v1/project-labels'),
    ).toHaveLength(3)
  })

  it('re-reads a conflicting write without replaying it or rendering server prose', async () => {
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [initialLabel] })
        : envelope({
            project_id: projectId,
            labels: [],
            revision: 0,
            updated_at: null,
          }),
    )
    const request = vi.fn(async () => {
      throw new ApiError({
        code: 'PROJECT_LABEL_CONFLICT',
        message: 'private database detail',
        status: 409,
      })
    })
    render(
      withAuth(
        context(get, request),
        <ProjectLabelsPanel projectId={projectId} locale="zh-CN" />,
      ),
    )
    await screen.findByText('此项目尚未分配标签。')
    fireEvent.click(screen.getByRole('button', { name: '管理标签' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Design' }))
    expect(await screen.findByText(/标签已在其他位置变更/)).toBeVisible()
    expect(
      screen.queryByText('private database detail'),
    ).not.toBeInTheDocument()
    expect(request).toHaveBeenCalledTimes(1)
    expect(
      get.mock.calls.filter(([path]) => path === '/api/v1/project-labels'),
    ).toHaveLength(3)
  })

  it('uses GET readback after an uncertain ACK without replaying assignment', async () => {
    let assigned: ProjectLabelSetData = {
      project_id: projectId,
      labels: [],
      revision: 0,
      updated_at: null,
    }
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [initialLabel] })
        : envelope(assigned),
    )
    const request = vi.fn(async () => {
      assigned = {
        project_id: projectId,
        labels: [initialLabel],
        revision: 1,
        updated_at: updatedAt,
      }
      throw new ApiError({
        code: 'REQUEST_TIMEOUT',
        message: 'private ACK detail',
        status: 0,
      })
    })
    render(
      withAuth(
        context(get, request),
        <ProjectLabelsPanel projectId={projectId} locale="en" />,
      ),
    )
    await screen.findByText('No labels assigned to this Project.')
    fireEvent.click(screen.getByRole('button', { name: 'Manage labels' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Design' }))
    expect(
      await screen.findByText(/result could not be confirmed/i),
    ).toBeVisible()
    expect(screen.queryByText('private ACK detail')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: 'Design' })).toBeChecked(),
    )
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('shows delete impact before sending a destructive request and includes the confirmed count', async () => {
    let catalog: NavigationLabelData[] = [initialLabel]
    let assigned: ProjectLabelSetData = {
      project_id: projectId,
      labels: [initialLabel],
      revision: 1,
      updated_at: updatedAt,
    }
    const get = vi.fn(async (path: string) => {
      if (path.endsWith('/delete-impact')) {
        return envelope({ label_id: labelId, affected_project_count: 1 })
      }
      return path === '/api/v1/project-labels'
        ? envelope({ labels: catalog })
        : envelope(assigned)
    })
    const request = vi.fn(async (path: string) => {
      if (path.endsWith('/delete')) {
        catalog = []
        assigned = {
          project_id: projectId,
          labels: [],
          revision: 2,
          updated_at: updatedAt,
        }
        return envelope({ label_id: labelId, affected_project_count: 1 })
      }
      throw new Error('unexpected mutation')
    })
    render(
      withAuth(
        context(get, request),
        <ProjectLabelsPanel projectId={projectId} locale="en" />,
      ),
    )
    await screen.findByText('Design')
    fireEvent.click(screen.getByRole('button', { name: 'Manage labels' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit label: Design' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Delete label' }))
    expect(
      await screen.findByText('Delete this label from 1 Project?'),
    ).toBeVisible()
    expect(request).not.toHaveBeenCalled()
    const group = screen.getByRole('group')
    fireEvent.click(within(group).getByRole('button', { name: 'Delete label' }))
    await waitFor(() =>
      expect(
        screen.getByText('No labels assigned to this Project.'),
      ).toBeVisible(),
    )
    expect(request).toHaveBeenCalledWith(
      `/api/v1/project-labels/${labelId}/delete`,
      expect.objectContaining({
        method: 'POST',
        body: { expected_revision: 1, expected_affected_project_count: 1 },
      }),
    )
  })

  it('creates then atomically renames and recolors one shared label', async () => {
    let catalog: NavigationLabelData[] = []
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: catalog })
        : envelope({
            project_id: projectId,
            labels: [],
            revision: 0,
            updated_at: null,
          }),
    )
    const request = vi.fn(async (path: string) => {
      if (path === '/api/v1/project-labels') {
        catalog = [{ ...initialLabel, name: 'Review', color: 'red' }]
        return envelope(catalog[0]!)
      }
      if (path === `/api/v1/project-labels/${labelId}`) {
        catalog = [
          { ...catalog[0]!, name: 'Urgent', color: 'orange', revision: 2 },
        ]
        return envelope(catalog[0]!)
      }
      throw new Error('unexpected mutation')
    })
    render(
      withAuth(
        context(get, request),
        <ProjectLabelsPanel projectId={projectId} locale="en" />,
      ),
    )
    await screen.findByText('No labels assigned to this Project.')
    fireEvent.click(screen.getByRole('button', { name: 'Manage labels' }))
    const dialog = screen.getByRole('dialog', { name: 'Manage labels' })
    await within(dialog).findByText(
      'Create a label to assign it to this Project.',
    )
    fireEvent.change(
      within(dialog).getByRole('textbox', { name: 'Label name' }),
      {
        target: { value: 'Review' },
      },
    )
    fireEvent.change(
      within(dialog).getByRole('combobox', { name: 'Label color' }),
      {
        target: { value: 'red' },
      },
    )
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Create label' }),
    )
    expect(
      await within(dialog).findByRole('button', { name: 'Edit label: Review' }),
    ).toBeVisible()
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Edit label: Review' }),
    )
    const names = within(dialog).getAllByRole('textbox', { name: 'Label name' })
    fireEvent.change(names[1]!, { target: { value: 'Urgent' } })
    const colors = within(dialog).getAllByRole('combobox', {
      name: 'Label color',
    })
    fireEvent.change(colors[1]!, { target: { value: 'orange' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save label' }))
    expect(
      await within(dialog).findByRole('button', { name: 'Edit label: Urgent' }),
    ).toBeVisible()
    expect(request).toHaveBeenCalledWith(
      `/api/v1/project-labels/${labelId}`,
      expect.objectContaining({
        method: 'PUT',
        body: { name: 'Urgent', color: 'orange', expected_revision: 1 },
      }),
    )
    expect(
      screen.getByText('No labels assigned to this Project.'),
    ).toBeVisible()
  })

  it('hides prior-administrator labels immediately on session replacement', async () => {
    const oldGet = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [initialLabel] })
        : envelope({
            project_id: projectId,
            labels: [initialLabel],
            revision: 1,
            updated_at: updatedAt,
          }),
    )
    const nextGet = vi.fn(async (path: string) =>
      path === '/api/v1/project-labels'
        ? envelope({ labels: [] })
        : envelope({
            project_id: projectId,
            labels: [],
            revision: 0,
            updated_at: null,
          }),
    )
    const request = vi.fn(async () => {
      throw new Error('no mutation')
    })
    const view = render(
      withAuth(
        context(oldGet, request, 'ses_old'),
        <ProjectLabelsPanel projectId={projectId} locale="en" />,
      ),
    )
    expect(await screen.findByText('Design')).toBeVisible()
    view.rerender(
      withAuth(
        context(nextGet, request, 'ses_next'),
        <ProjectLabelsPanel projectId={projectId} locale="en" />,
      ),
    )
    expect(screen.queryByText('Design')).not.toBeInTheDocument()
    expect(
      await screen.findByText('No labels assigned to this Project.'),
    ).toBeVisible()
    expect(request).not.toHaveBeenCalled()
  })
})
