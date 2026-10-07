import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext } from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import {
  doctorHttp,
  doctorResponse,
  heldResponse,
  jsonResponse,
} from '../test/doctorFixtures'
import { SettingsPage } from './SettingsPage'

const copy = {
  en: {
    title: 'Settings',
    readOnly: 'Read only',
    loading: 'Loading safe settings…',
    unavailable: 'Unavailable',
    labels: [
      'Environment',
      'Bind address',
      'Absolute session lifetime',
      'Idle session lifetime',
      'Login rate limit',
      'Login lock duration',
    ],
    hours: '2 hours',
    minutes: '30 minutes',
    seconds: '73 seconds',
    rate: '12,345 failures per 1 minute',
    error: 'The operation could not be completed. Try again.',
  },
  'zh-CN': {
    title: '设置',
    readOnly: '只读',
    loading: '正在加载安全设置…',
    unavailable: '不可用',
    labels: [
      '环境',
      '绑定地址',
      '会话绝对有效期',
      '会话空闲有效期',
      '登录速率限制',
      '登录锁定时长',
    ],
    hours: '2 小时',
    minutes: '30 分钟',
    seconds: '73 秒',
    rate: '每 1 分钟最多 12,345 次失败',
    error: '操作未完成，请重试。',
  },
} as const

function show(locale: Locale, response: Response | Promise<Response>) {
  const http = doctorHttp(response)
  const rendered = render(
    <AuthContext.Provider value={http.value}>
      <SettingsPage locale={locale} />
    </AuthContext.Provider>,
  )
  return { ...rendered, ...http }
}

function expectReadOnly(container: HTMLElement) {
  expect(
    container.querySelector(
      'button, input, select, textarea, form, a, [contenteditable="true"]',
    ),
  ).toBeNull()
}

describe.each(['en', 'zh-CN'] as const)(
  'Settings policy through actual HTTP and projection in %s',
  (locale) => {
    afterEach(() => vi.unstubAllGlobals())
    const text = copy[locale]

    it('shows exactly the original six policy facts, formatted durations and no editing or Runtime data', async () => {
      const response = doctorResponse()
      const { container, requests } = show(locale, jsonResponse(response))
      await screen.findByText('test')

      expect(
        screen.getByRole('heading', { name: text.title, level: 1 }),
      ).toBeVisible()
      expect(screen.getByText(text.readOnly)).toBeVisible()
      expect(
        screen.getAllByRole('term').map((term) => term.textContent),
      ).toEqual(text.labels)
      expect(
        screen
          .getAllByRole('definition')
          .map((definition) =>
            definition.textContent?.replace(/\s+/g, ' ').trim(),
          ),
      ).toEqual([
        'test',
        '127.0.0.1: 8080',
        text.hours,
        text.minutes,
        text.rate,
        text.seconds,
      ])
      for (const value of ['test', '127.0.0.1']) {
        expect(screen.getByText(value)).toHaveAttribute('lang', 'en')
        expect(screen.getByText(value)).toHaveAttribute('dir', 'ltr')
        expect(screen.getByText(value)).toHaveAttribute('translate', 'no')
      }
      expect(document.body).not.toHaveTextContent(
        response.data.projects.project_root,
      )
      expect(document.body).not.toHaveTextContent(response.data.codex.version!)
      expect(document.body).not.toHaveTextContent(response.data.claude.version!)
      expect(document.body).not.toHaveTextContent('req_admin_doctor_fixture')
      expect(requests).toHaveLength(1)
      expectReadOnly(container)
    })

    it.each([
      [3600, '1 hour', '1 小时'],
      [60, '1 minute', '1 分钟'],
      [1, '1 second', '1 秒'],
    ] as const)(
      'retains the existing singular duration units for %s seconds',
      async (seconds, en, zh) => {
        const response = doctorResponse()
        response.data.policy.session_ttl_seconds = seconds
        response.data.policy.session_idle_ttl_seconds = seconds
        response.data.policy.login_lock_duration_seconds = seconds
        response.data.policy.login_rate_window_seconds = seconds
        response.data.policy.login_rate_limit = 1
        show(locale, jsonResponse(response))
        await screen.findByText('test')

        const duration = locale === 'en' ? en : zh
        expect(
          screen
            .getAllByRole('definition')
            .slice(2)
            .map((field) => field.textContent),
        ).toEqual([
          duration,
          duration,
          locale === 'en'
            ? `1 failures per ${duration}`
            : `每 ${duration}最多 1 次失败`,
          duration,
        ])
      },
    )

    it.each(['不可用主机', 'unsafe\nhost'])(
      'uses the unavailable fallback when the bind host cannot be projected safely: %s',
      async (host) => {
        const response = doctorResponse()
        response.data.policy.bind_host = host
        const { container } = show(locale, jsonResponse(response))
        await screen.findByText(text.unavailable)

        const bind = screen.getByText(text.labels[1], {
          selector: 'dt',
        }).nextElementSibling
        expect(bind).toHaveTextContent(new RegExp(`^${text.unavailable}$`))
        expect(document.body.textContent).not.toContain(host)
        expect(bind).not.toHaveTextContent('8,080')
        expect(bind).not.toHaveTextContent('8080')
        expect(screen.getAllByRole('term')).toHaveLength(6)
        expectReadOnly(container)
      },
    )

    it('renders a long printable bind host as inert technical text', async () => {
      const response = doctorResponse()
      const host = `${'metadata-'.repeat(50)}<img src=x>.invalid`
      response.data.policy.bind_host = host
      const { container } = show(locale, jsonResponse(response))
      const value = await screen.findByText(host)

      expect(value).toHaveAttribute('lang', 'en')
      expect(value).toHaveAttribute('dir', 'ltr')
      expect(value).toHaveAttribute('translate', 'no')
      expect(container.querySelector('img, script')).toBeNull()
      expect(screen.getAllByRole('term')).toHaveLength(6)
      expectReadOnly(container)
    })

    it('announces loading and a safe localized error without stale facts, retries or controls', async () => {
      const held = heldResponse()
      const { container, requests } = show(locale, held.promise)
      expect(screen.getByRole('status')).toHaveTextContent(text.loading)
      expect(screen.queryByRole('term')).not.toBeInTheDocument()
      expectReadOnly(container)

      await act(async () =>
        held.resolve(
          jsonResponse(
            {
              request_id: 'req_settings_safe_error',
              error: {
                code: 'SETTINGS_READ_FAILED',
                message: 'SETTINGS SERVER PRIVATE PROSE CANARY',
              },
            },
            503,
          ),
        ),
      )
      expect(screen.getByRole('alert')).toHaveTextContent(text.error)
      expect(screen.getByText('SETTINGS_READ_FAILED')).toHaveAttribute(
        'translate',
        'no',
      )
      expect(screen.getByText('req_settings_safe_error')).toHaveAttribute(
        'dir',
        'ltr',
      )
      expect(document.body).not.toHaveTextContent(
        'SETTINGS SERVER PRIVATE PROSE CANARY',
      )
      expect(screen.queryByRole('term')).not.toBeInTheDocument()
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
      expect(requests).toHaveLength(1)
      expectReadOnly(container)
    })
  },
)
