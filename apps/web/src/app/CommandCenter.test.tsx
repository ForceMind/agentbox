import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import type { ProjectData } from '../lib/contracts'
import { ApiClient } from '../lib/api'
import { AppShell } from './AppShell'
import { commandResults } from './commandCenterResults'

const projectId = `prj_${'a'.repeat(32)}`
const project = {
  id: projectId,
  display_name: 'Alpha Project',
  slug: 'alpha-project',
  git: null,
} as ProjectData

function context(
  get: ReturnType<typeof vi.fn>,
  sessionId = 'ses_command',
): AuthContextValue {
  return {
    api: { get } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_command', username: 'maintainer' },
      session: { id: sessionId, expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf-command',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

function renderShell(get: ReturnType<typeof vi.fn>, locale: Locale = 'en') {
  render(
    <AuthContext.Provider value={context(get)}>
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route element={<AppShell locale={locale} />}>
            <Route element={<p>Dashboard landing</p>} path="/dashboard" />
            <Route element={<p>Attention landing</p>} path="/attention" />
            <Route
              element={<p>Project detail</p>}
              path="/projects/:projectId"
            />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('Command center', () => {
  it('ranks fixed navigation and visible Project metadata without creating actions', () => {
    const actions = [
      { title: 'Dashboard', href: '/dashboard' },
      { title: 'Needs attention', href: '/attention' },
    ]
    expect(
      commandResults(actions, [project], 'alpha').map((row) => row.id),
    ).toEqual([`project:${projectId}`])
    expect(
      commandResults(actions, [project], 'needs').map((row) => row.id),
    ).toEqual(['action:/attention'])
    expect(commandResults(actions, [project], '')).toHaveLength(3)
    expect(
      commandResults(
        [...actions, { title: 'External', href: 'https://example.invalid' }],
        [{ ...project, id: '../../settings' }],
        '',
      ).map((row) => row.id),
    ).toEqual(['action:/dashboard', 'action:/attention'])
  })

  it('opens with Ctrl+K, loads current Projects and navigates from keyboard selection', async () => {
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/projects'
        ? { data: { projects: [project] } }
        : { status: 'ok' },
    )
    renderShell(get)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const dialog = await screen.findByRole('dialog', { name: 'Command center' })
    expect(dialog).toBeVisible()
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith('/api/v1/projects', expect.any(Object)),
    )
    const input = screen.getByRole('combobox', {
      name: 'Search pages and Projects',
    })
    fireEvent.change(input, { target: { value: 'alpha' } })
    expect(screen.getByRole('option', { name: 'Alpha Project' })).toBeVisible()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(await screen.findByText('Project detail')).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(
      get.mock.calls.filter(([path]) => path === '/api/v1/projects'),
    ).toHaveLength(1)
  })

  it('keeps page navigation available on Project read failure and closes on Escape', async () => {
    const get = vi.fn(async (path: string) => {
      if (path === '/api/v1/projects') {
        throw new Error('private transport detail')
      }
      return { status: 'ok' }
    })
    renderShell(get)
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Projects could not be loaded',
    )
    expect(
      screen.queryByText('private transport detail'),
    ).not.toBeInTheDocument()
    const input = screen.getByRole('combobox', {
      name: 'Search pages and Projects',
    })
    fireEvent.change(input, { target: { value: 'attention' } })
    expect(
      screen.getByRole('option', { name: 'Needs attention' }),
    ).toBeVisible()
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('uses arrow selection and does not execute a Runtime action', async () => {
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/projects'
        ? { data: { projects: [] } }
        : { status: 'ok' },
    )
    renderShell(get)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const input = screen.getByRole('combobox', {
      name: 'Search pages and Projects',
    })
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(
      screen.getByRole('option', { name: 'Needs attention' }),
    ).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(await screen.findByText('Attention landing')).toBeVisible()
    expect(
      get.mock.calls.filter(([path]) => path === '/api/v1/projects'),
    ).toHaveLength(1)
  })

  it('renders Chinese command controls and keeps Project names as user data', async () => {
    const get = vi.fn(async (path: string) =>
      path === '/api/v1/projects'
        ? { data: { projects: [project] } }
        : { status: 'ok' },
    )
    renderShell(get, 'zh-CN')
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(
      await screen.findByRole('dialog', { name: '命令中心' }),
    ).toBeVisible()
    const input = screen.getByRole('combobox', { name: '搜索页面和项目' })
    fireEvent.change(input, { target: { value: 'alpha' } })
    const name = await screen.findByText('Alpha Project')
    expect(name.tagName).toBe('BDI')
    expect(name).toHaveAttribute('dir', 'auto')
  })

  it('drops a late Project list when the administrator session changes', async () => {
    let completeOld!: (value: object) => void
    const oldGet = vi.fn((path: string) =>
      path === '/api/v1/projects'
        ? new Promise<object>((resolve) => {
            completeOld = resolve
          })
        : Promise.resolve({ status: 'ok' }),
    )
    const nextGet = vi.fn(async () => ({ data: { projects: [] } }))
    const shell = (value: AuthContextValue) => (
      <AuthContext.Provider value={value}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route element={<p>Dashboard landing</p>} path="/dashboard" />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    )
    const view = render(shell(context(oldGet, 'ses_old')))
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    await waitFor(() =>
      expect(oldGet).toHaveBeenCalledWith(
        '/api/v1/projects',
        expect.any(Object),
      ),
    )
    view.rerender(shell(context(nextGet, 'ses_next')))
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    await act(async () => completeOld({ data: { projects: [project] } }))
    expect(screen.queryByText('Alpha Project')).not.toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    await waitFor(() =>
      expect(nextGet).toHaveBeenCalledWith(
        '/api/v1/projects',
        expect.any(Object),
      ),
    )
    expect(screen.queryByText('Alpha Project')).not.toBeInTheDocument()
  })

  it('aborts the pending Project read when the dialog closes', async () => {
    let requestSignal: AbortSignal | undefined
    const get = vi.fn((path: string, options?: { signal?: AbortSignal }) => {
      if (path !== '/api/v1/projects') return Promise.resolve({ status: 'ok' })
      requestSignal = options?.signal
      return new Promise<object>((_resolve, reject) => {
        options?.signal?.addEventListener(
          'abort',
          () => reject(new Error('aborted')),
          { once: true },
        )
      })
    })
    renderShell(get)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    await waitFor(() => expect(requestSignal).toBeDefined())
    fireEvent.keyDown(
      screen.getByRole('combobox', { name: 'Search pages and Projects' }),
      { key: 'Escape' },
    )
    expect(requestSignal?.aborted).toBe(true)
  })
})
