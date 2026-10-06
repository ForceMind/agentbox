import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { Link, MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import { ApiClient, ApiError } from '../lib/api'
import { AppShell } from './AppShell'

function authContext(
  logout: () => Promise<void>,
  username = 'maintainer',
  sessionId = 'ses_shell',
): AuthContextValue {
  return {
    api: {
      get: vi.fn(async () => ({ status: 'ok' })),
    } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_shell', username },
      session: { id: sessionId, expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf-shell',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout,
    refresh: vi.fn(async () => null),
  }
}

describe('AppShell', () => {
  it('uses localized generic logout feedback instead of ApiError.message', async () => {
    const logout = vi.fn(async () => {
      throw new ApiError({
        code: 'AUTH_SESSION_INVALID',
        message: 'control-plane detail must not be rendered',
        status: 401,
      })
    })

    render(
      <AuthContext.Provider value={authContext(logout)}>
        <MemoryRouter initialEntries={['/workspace']}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route element={<Outlet />} path="*" />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    expect(screen.getByText('0.3.0-rc.31', { exact: true })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(
      await screen.findByText('Logout could not be completed'),
    ).toBeVisible()
    expect(
      screen.queryByText('control-plane detail must not be rendered'),
    ).not.toBeInTheDocument()
  })

  it('renders Chinese shell copy while preserving user and version values', async () => {
    const logout = vi.fn(async () => {
      throw new Error('logout failed')
    })

    render(
      <AuthContext.Provider value={authContext(logout, '维护者 🚀')}>
        <MemoryRouter initialEntries={['/workspace']}>
          <Routes>
            <Route element={<AppShell locale="zh-CN" />}>
              <Route element={<Outlet />} path="*" />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    expect(screen.getByRole('navigation', { name: '主导航' })).toBeVisible()
    expect(screen.getByRole('link', { name: '工作区' })).toBeVisible()
    for (const username of screen.getAllByText('维护者 🚀')) {
      expect(username.tagName).toBe('BDI')
      expect(username).toHaveAttribute('dir', 'auto')
      expect(username).toHaveAttribute('translate', 'no')
    }
    for (const version of screen.getAllByText('0.3.0-rc.31', { exact: true })) {
      expect(version).toHaveAttribute('lang', 'en')
      expect(version).toHaveAttribute('dir', 'ltr')
      expect(version).toHaveAttribute('translate', 'no')
    }

    fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '无法完成退出登录',
    )
  })

  it('keeps bounded Project views as navigation and closes without Runtime actions', async () => {
    const projectId = `prj_${'a'.repeat(32)}`
    const logout = vi.fn(async () => undefined)
    render(
      <AuthContext.Provider value={authContext(logout)}>
        <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route element={<p>Projects landing</p>} path="/projects" />
              <Route
                element={
                  <>
                    <p>Project detail</p>
                    <Link to={`/projects/${projectId}/changes`}>
                      Open changes
                    </Link>
                  </>
                }
                path="/projects/:projectId"
              />
              <Route
                element={
                  <>
                    <p>Changes view</p>
                    <Link to={`/workspace?project_id=${projectId}`}>
                      Open workspace
                    </Link>
                  </>
                }
                path="/projects/:projectId/changes"
              />
              <Route element={<p>Workspace view</p>} path="/workspace" />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    const tabs = await screen.findByRole('navigation', {
      name: 'Open Project views',
    })
    expect(tabs).toHaveTextContent('Project · aaaaaa')
    fireEvent.click(screen.getByRole('link', { name: 'Open changes' }))
    expect(await screen.findByText('Changes view')).toBeVisible()
    expect(tabs).toHaveTextContent('Changed paths · aaaaaa')
    fireEvent.click(screen.getByRole('link', { name: 'Open workspace' }))
    expect(await screen.findByText('Workspace view')).toBeVisible()
    expect(tabs).toHaveTextContent('Claude · aaaaaa')

    fireEvent.click(
      screen.getByRole('button', { name: 'Close Claude · aaaaaa' }),
    )
    expect(await screen.findByText('Changes view')).toBeVisible()
    fireEvent.click(
      screen.getByRole('button', { name: 'Close Changed paths · aaaaaa' }),
    )
    expect(await screen.findByText('Project detail')).toBeVisible()
    fireEvent.click(
      screen.getByRole('button', { name: 'Close Project · aaaaaa' }),
    )
    expect(await screen.findByText('Projects landing')).toBeVisible()
    expect(
      screen.queryByRole('navigation', { name: 'Open Project views' }),
    ).toBeNull()
    expect(logout).not.toHaveBeenCalled()
  })

  it('drops previous-session tabs before showing the new session route', async () => {
    const projectId = `prj_${'b'.repeat(32)}`
    const logout = vi.fn(async () => undefined)
    const app = (sessionId: string) => (
      <AuthContext.Provider
        value={authContext(logout, 'maintainer', sessionId)}
      >
        <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route
                element={
                  <Link to={`/projects/${projectId}/changes`}>
                    Open changes
                  </Link>
                }
                path="/projects/:projectId"
              />
              <Route
                element={<p>Changed paths view</p>}
                path="/projects/:projectId/changes"
              />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    )
    const { rerender } = render(app('ses_first'))
    expect(await screen.findByRole('link', { name: /Project ·/ })).toBeVisible()
    fireEvent.click(screen.getByRole('link', { name: 'Open changes' }))
    expect(await screen.findByText('Changed paths view')).toBeVisible()
    expect(screen.getByRole('link', { name: /Project ·/ })).toBeVisible()
    rerender(app('ses_second'))
    expect(screen.queryByRole('link', { name: /Project ·/ })).toBeNull()
    expect(
      await screen.findByRole('link', { name: /Changed paths ·/ }),
    ).toBeVisible()
  })

  it('groups real navigation and offers a keyboard skip target', async () => {
    render(
      <AuthContext.Provider value={authContext(vi.fn(async () => undefined))}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route path="*" element={<p>Content</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    const navigation = screen.getByRole('navigation', {
      name: 'Primary navigation',
    })
    expect(
      within(navigation)
        .getAllByRole('link')
        .map((link) => link.getAttribute('href')),
    ).toEqual([
      '/dashboard',
      '/attention',
      '/projects',
      '/workspace',
      '/claude',
      '/codex',
      '/doctor',
      '/logs',
      '/settings',
    ])
    expect(within(navigation).getByText('Agents')).toBeVisible()
    expect(
      screen.getByRole('link', { name: 'Skip to content' }),
    ).toHaveAttribute('href', '#main-content')
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content')
    expect(screen.getByRole('main')).toHaveAttribute('tabindex', '-1')
    expect(await screen.findByLabelText('Control plane: Healthy')).toBeVisible()
  })

  it('cancels mobile navigation without changing the route and returns focus', async () => {
    render(
      <AuthContext.Provider value={authContext(vi.fn(async () => undefined))}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route path="*" element={<p>Dashboard content</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    const trigger = screen.getByRole('button', { name: 'Open navigation' })
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Primary navigation' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(
      within(dialog).getByRole('button', { name: 'Close navigation' }),
    ).toHaveFocus()
    fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(trigger).toHaveFocus()
    expect(screen.getByText('Dashboard content')).toBeVisible()
    expect(await screen.findByLabelText('Control plane: Healthy')).toBeVisible()
    fireEvent.click(trigger)
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Close navigation',
      }),
    )
    expect(trigger).toHaveFocus()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('dismisses navigation on offline and newer route changes without reopening', async () => {
    render(
      <AuthContext.Provider value={authContext(vi.fn(async () => undefined))}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route path="/dashboard" element={<p>Dashboard content</p>} />
              <Route path="/projects" element={<p>Projects content</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    fireEvent(window, new Event('offline'))
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent(window, new Event('online'))
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('link', {
        name: 'Projects',
      }),
    )
    expect(await screen.findByText('Projects content')).toBeVisible()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('closes on a queued desktop transition even after the live media value changed back', async () => {
    let change!: (event: MediaQueryListEvent) => void
    const media = {
      matches: false,
      addEventListener: vi.fn((_name: string, listener: typeof change) => {
        change = listener
      }),
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => media),
    )
    const view = render(
      <AuthContext.Provider value={authContext(vi.fn(async () => undefined))}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route path="*" element={<p>Content</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    try {
      expect(
        await screen.findByLabelText('Control plane: Healthy'),
      ).toBeVisible()
      fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      // The event was generated at the desktop width; the current width has
      // already returned to mobile before delivery. Do not read media.matches.
      act(() => change({ matches: true } as MediaQueryListEvent))
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(
        screen.getByRole('button', { name: 'Open navigation' }),
      ).toHaveAttribute('aria-expanded', 'false')
      act(() => change({ matches: false } as MediaQueryListEvent))
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(media.removeEventListener).toHaveBeenCalledWith('change', change)
    } finally {
      view.unmount()
      vi.unstubAllGlobals()
    }
  })

  it('closes if desktop sizing was already reached before the menu subscribed', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    const view = render(
      <AuthContext.Provider value={authContext(vi.fn(async () => undefined))}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route element={<AppShell locale="en" />}>
              <Route path="*" element={<p>Content</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    try {
      expect(
        await screen.findByLabelText('Control plane: Healthy'),
      ).toBeVisible()
      fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(
        screen.getByRole('button', { name: 'Open navigation' }),
      ).toHaveAttribute('aria-expanded', 'false')
    } finally {
      view.unmount()
      vi.unstubAllGlobals()
    }
  })
})
