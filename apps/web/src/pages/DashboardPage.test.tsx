import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import { ApiClient } from '../lib/api'
import { DashboardPage } from './DashboardPage'

type DashboardOptions = Readonly<{
  health?: { status: 'ok' } | Error
  meta?:
    | {
        api_version: 'v1'
        environment: 'development' | 'test' | 'production'
        name: 'AgentBox'
        version: string
      }
    | Error
  readiness?:
    | {
        checks: { database: boolean; migrations: boolean }
        status: 'ready' | 'not_ready'
      }
    | Error
}>

function authContext(options: DashboardOptions): AuthContextValue {
  const health = options.health ?? { status: 'ok' as const }
  const readiness =
    options.readiness ??
    ({
      status: 'ready' as const,
      checks: { database: true, migrations: true },
    } as const)
  const meta =
    options.meta ??
    ({
      name: 'AgentBox' as const,
      version: '0.3.0-rc.9',
      api_version: 'v1' as const,
      environment: 'test' as const,
    } as const)
  const get = vi.fn((path: string) => {
    const result =
      path === '/healthz' ? health : path === '/readyz' ? readiness : meta
    return result instanceof Error
      ? Promise.reject(result)
      : Promise.resolve(result)
  })

  return {
    api: { get } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_dashboard', username: '维护者 🚀' },
      session: { id: 'ses_dashboard', expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf-dashboard',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

function renderDashboard(locale: Locale, options: DashboardOptions = {}) {
  render(
    <AuthContext.Provider value={authContext(options)}>
      <DashboardPage locale={locale} />
    </AuthContext.Provider>,
  )
}

describe('DashboardPage rc9 localization and rendering boundaries', () => {
  it.each([
    ['en', 'Dashboard', 'Healthy', 'Current capabilities'],
    ['zh-CN', '概览', '正常', '当前能力'],
  ] as const)(
    'renders localized healthy state and current capability copy in %s',
    async (locale, title, healthy, capabilities) => {
      renderDashboard(locale)

      expect(screen.getByRole('heading', { name: title })).toBeVisible()
      await waitFor(() =>
        expect(screen.getAllByText(healthy).length).toBeGreaterThan(0),
      )
      expect(screen.getByRole('heading', { name: capabilities })).toBeVisible()
      expect(
        screen.queryByText(/Remote daemon and pairing controls arrive/i),
      ).not.toBeInTheDocument()
      expect(screen.getByText('0.3.0-rc.9')).toHaveAttribute('lang', 'en')
      expect(screen.getByText('v1')).toHaveAttribute('dir', 'ltr')
      expect(screen.getByText('test')).toHaveAttribute('translate', 'no')
      const username = screen.getByText('维护者 🚀')
      expect(username).toHaveAttribute('dir', 'auto')
      expect(username).toHaveAttribute('translate', 'no')
    },
  )

  it('reports degraded and unavailable service states without rendering unsafe metadata', async () => {
    const canary = 'SERVER-PROSE-CANARY-DASHBOARD-🚫'
    renderDashboard('en', {
      meta: {
        name: 'AgentBox',
        version: canary,
        api_version: 'v1',
        environment: 'test',
      },
      readiness: {
        status: 'not_ready',
        checks: { database: true, migrations: false },
      },
    })

    await waitFor(() =>
      expect(screen.getAllByText('Degraded').length).toBeGreaterThan(0),
    )
    expect(document.body.textContent).not.toContain(canary)
    expect(screen.getAllByText('Not Ready').length).toBeGreaterThan(0)
  })

  it('reports unavailable after the control-plane health request fails', async () => {
    renderDashboard('zh-CN', { health: new Error('untrusted failure') })

    await waitFor(() =>
      expect(screen.getAllByText('暂不可用').length).toBeGreaterThan(0),
    )
  })
})
