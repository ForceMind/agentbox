import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
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
): AuthContextValue {
  return {
    api: {
      get: vi.fn(async () => ({ status: 'ok' })),
    } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_shell', username },
      session: { id: 'ses_shell', expires_at: '2026-12-31T00:00:00Z' },
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

    expect(screen.getByText('0.3.0-rc.11', { exact: true })).toBeVisible()
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
    for (const version of screen.getAllByText('0.3.0-rc.11', { exact: true })) {
      expect(version).toHaveAttribute('lang', 'en')
      expect(version).toHaveAttribute('dir', 'ltr')
      expect(version).toHaveAttribute('translate', 'no')
    }

    fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '无法完成退出登录',
    )
  })
})
