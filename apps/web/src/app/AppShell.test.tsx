import { fireEvent, render, screen } from '@testing-library/react'
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

    expect(screen.getByText('0.3.0-rc.29', { exact: true })).toBeVisible()
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
    for (const version of screen.getAllByText('0.3.0-rc.29', { exact: true })) {
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
})
