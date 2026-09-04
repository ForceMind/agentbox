import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import { ApiClient, ApiError } from '../lib/api'
import { AppShell } from './AppShell'

function authContext(logout: () => Promise<void>): AuthContextValue {
  return {
    api: {
      get: vi.fn(async () => ({ status: 'ok' })),
    } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_shell', username: 'maintainer' },
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
            <Route element={<AppShell />}>
              <Route element={<Outlet />} path="*" />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(
      await screen.findByText('Logout could not be completed'),
    ).toBeVisible()
    expect(
      screen.queryByText('control-plane detail must not be rendered'),
    ).not.toBeInTheDocument()
  })
})
