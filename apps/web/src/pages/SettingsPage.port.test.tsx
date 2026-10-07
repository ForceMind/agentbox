import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext } from '../features/auth/AuthContext'
import {
  doctorHttp,
  doctorResponse,
  jsonResponse,
} from '../test/doctorFixtures'
import { SettingsPage } from './SettingsPage'

describe.each(['en', 'zh-CN'] as const)(
  'Settings technical bind port through actual HTTP in %s',
  (locale) => {
    afterEach(() => vi.unstubAllGlobals())

    it.each([8080, 65535])(
      'renders port %s as ungrouped technical digits while keeping policy quantities localized',
      async (port) => {
        const response = doctorResponse()
        response.data.policy.bind_port = port
        const { value, requests } = doctorHttp(jsonResponse(response))
        const { container } = render(
          <AuthContext.Provider value={value}>
            <SettingsPage locale={locale} />
          </AuthContext.Provider>,
        )
        await screen.findByText('127.0.0.1')

        const facts = screen.getAllByRole('definition')
        expect(screen.getAllByRole('term')).toHaveLength(6)
        expect(facts).toHaveLength(6)
        expect(facts.slice(2).map((fact) => fact.textContent)).toEqual(
          locale === 'en'
            ? [
                '2 hours',
                '30 minutes',
                '12,345 failures per 1 minute',
                '73 seconds',
              ]
            : ['2 小时', '30 分钟', '每 1 分钟最多 12,345 次失败', '73 秒'],
        )
        expect(requests.map(({ path, method }) => ({ path, method }))).toEqual([
          { path: '/api/v1/doctor', method: 'GET' },
        ])
        expect(
          container.querySelector(
            'button, input, select, textarea, form, a, [contenteditable="true"]',
          ),
        ).toBeNull()

        const bind = facts[1]
        expect(bind).toHaveTextContent(
          new RegExp(`^127\\.0\\.0\\.1:\\s*${port}$`),
        )
        const technicalPort = within(bind).getByText(String(port), {
          exact: true,
          selector: 'bdi',
        })
        expect(technicalPort).toHaveAttribute('lang', 'en')
        expect(technicalPort).toHaveAttribute('dir', 'ltr')
        expect(technicalPort).toHaveAttribute('translate', 'no')
      },
    )
  },
)
