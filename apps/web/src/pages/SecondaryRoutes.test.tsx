import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import { ApiClient, ApiError } from '../lib/api'
import type { DoctorResponse } from '../lib/contracts'
import { DoctorPage } from './DoctorPage'
import { LogsPage } from './LogsPage'
import { NotFoundPage } from './NotFoundPage'
import { SettingsPage } from './SettingsPage'

const doctorResponse: DoctorResponse = {
  api_version: 'v1',
  request_id: 'req_rc9_doctor',
  data: {
    status: 'ready',
    checks: {
      configuration_valid: true,
      database_reachable: true,
      migrations_current: true,
      admin_initialized: true,
      control_plane_ready: true,
    },
    policy: {
      environment: 'test',
      bind_host: '127.0.0.1',
      bind_port: 8080,
      session_ttl_seconds: 7200,
      session_idle_ttl_seconds: 1800,
      login_rate_limit: 12_345,
      login_rate_window_seconds: 60,
      login_lock_duration_seconds: 73,
    },
    codex: {
      installed: true,
      version: '0.3.0-rc.9',
      installation_type: 'standalone',
      remote_control: 'supported',
      remote_state: 'stopped',
      findings: ['CODEX_NOT_INSTALLED', 'RC9-SERVER-PROSE-CANARY'],
    },
    claude: {
      installed: true,
      version: '1.2.3',
      authentication: 'authenticated',
      remote_control: 'supported',
      tmux_installed: true,
      tmux_version: '3.5',
      managed_sessions: 1234,
      unmanaged_sessions: 0,
      workspace_interaction_warnings: 0,
      findings: [],
    },
    projects: {
      project_root: '/Projects/维护者',
      project_count: 12_345,
      git_installed: true,
      git_version: '2.48.0',
      github_cli_installed: true,
      github_authentication: 'authenticated',
      findings: ['PROJECT_WORKSPACE_UNAVAILABLE'],
    },
  },
}

function authContext(
  doctor: DoctorResponse | Error = doctorResponse,
  status: AuthContextValue['status'] = 'authenticated',
): AuthContextValue {
  return {
    api: {
      get: vi.fn(async () => {
        if (doctor instanceof Error) throw doctor
        return doctor
      }),
    } as unknown as ApiClient,
    auth: null,
    status,
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

function renderDoctor(
  locale: Locale,
  doctor: DoctorResponse | Error = doctorResponse,
) {
  render(
    <AuthContext.Provider value={authContext(doctor)}>
      <DoctorPage locale={locale} />
    </AuthContext.Provider>,
  )
}

function unreadableServerProse() {
  const canary = 'RC9-SECONDARY-SERVER-PROSE-CANARY'
  let messageReads = 0
  const error = new ApiError({
    code: 'RC9_UNKNOWN_DOCTOR_FAILURE',
    message: canary,
    requestId: 'req_rc9_secondary',
    status: 503,
  })
  Object.defineProperty(error, 'message', {
    configurable: true,
    get: () => {
      messageReads += 1
      return canary
    },
  })
  return { canary, error, messageReads: () => messageReads }
}

describe('secondary route rc9 localization and render fences', () => {
  it.each([
    [
      'en',
      'Doctor',
      'Configuration valid',
      'Codex is not installed.',
      'Unknown',
    ],
    ['zh-CN', '诊断', '配置有效', '未安装 Codex。', '未知'],
  ] as const)(
    'localizes Doctor summaries and restricts unknown findings in %s',
    async (locale, title, check, knownFinding, technicalFallback) => {
      renderDoctor(locale)

      expect(screen.getByRole('heading', { name: title })).toBeVisible()
      await waitFor(() => expect(screen.getByText(check)).toBeVisible())
      expect(screen.getByText(knownFinding)).toBeVisible()
      expect(screen.getByText('CODEX_NOT_INSTALLED')).toHaveAttribute(
        'translate',
        'no',
      )
      expect(document.body.textContent).not.toContain('RC9-SERVER-PROSE-CANARY')
      expect(screen.getByText(technicalFallback)).toBeVisible()
      expect(document.body.textContent).not.toContain('/Projects/维护者')
    },
  )

  it.each([
    ['en', 'The operation could not be completed. Try again.'],
    ['zh-CN', '操作未完成，请重试。'],
  ] as const)(
    'uses LocalizedApiError for Settings failures in %s',
    async (locale, copy) => {
      const observed = unreadableServerProse()
      render(
        <AuthContext.Provider value={authContext(observed.error)}>
          <SettingsPage locale={locale} />
        </AuthContext.Provider>,
      )

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(copy)
      expect(alert).not.toHaveTextContent(observed.canary)
      expect(observed.messageReads()).toBe(0)
    },
  )

  it.each([
    [
      'en',
      'Diagnostics unavailable',
      'The operation could not be completed. Try again.',
    ],
    ['zh-CN', '诊断信息暂不可用', '操作未完成，请重试。'],
  ] as const)(
    'uses LocalizedApiError for Doctor failures in %s',
    async (locale, heading, copy) => {
      const observed = unreadableServerProse()
      renderDoctor(locale, observed.error)

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(heading)
      expect(alert).toHaveTextContent(copy)
      expect(alert).not.toHaveTextContent(observed.canary)
      expect(observed.messageReads()).toBe(0)
    },
  )

  it.each([
    ['en', 'Settings', '2 hours', '12,345 failures per 1 minute'],
    ['zh-CN', '设置', '2 小时', '每 1 分钟最多 12,345 次失败'],
  ] as const)(
    'formats Settings durations and counts using the selected locale in %s',
    async (locale, title, lifetime, limit) => {
      render(
        <AuthContext.Provider value={authContext()}>
          <SettingsPage locale={locale} />
        </AuthContext.Provider>,
      )

      expect(screen.getByRole('heading', { name: title })).toBeVisible()
      await waitFor(() => expect(screen.getByText(lifetime)).toBeVisible())
      expect(screen.getByText(limit)).toBeVisible()
      expect(screen.getByText('127.0.0.1')).toHaveAttribute('lang', 'en')
    },
  )

  it.each([
    ['en', 'Logs', 'Not implemented yet', 'Back to Dashboard'],
    ['zh-CN', '日志', '尚未实现', '返回 Dashboard'],
  ] as const)(
    'localizes Logs planned state and NotFound navigation in %s',
    (locale, logs, planned, back) => {
      const { unmount } = render(<LogsPage locale={locale} />)
      expect(screen.getByRole('heading', { name: logs })).toBeVisible()
      expect(screen.getByRole('heading', { name: planned })).toBeVisible()
      unmount()

      render(
        <AuthContext.Provider value={authContext(doctorResponse)}>
          <MemoryRouter>
            <NotFoundPage locale={locale} />
          </MemoryRouter>
        </AuthContext.Provider>,
      )
      expect(screen.getByRole('link', { name: back })).toHaveAttribute(
        'href',
        '/dashboard',
      )
    },
  )
})
