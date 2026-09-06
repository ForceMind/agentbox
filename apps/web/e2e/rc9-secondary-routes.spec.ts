import { expect, test } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9NoHorizontalOverflow,
  assertRc9Title,
} from './rc9-assertions'
import {
  createRc9DocumentContext,
  RC9_LOCALE_SCENARIOS,
  RC9_VIEWPORTS,
} from './rc9-fixtures'

test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const syntheticServerProse = 'RC9-SECONDARY-SERVER-PROSE-CANARY'

test('secondary route errors localize without persisting server prose', async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'the self-managed rc9 context matrix runs once with complete device options',
  )

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      try {
        const page = await context.newPage()
        await page.route('**/api/v1/auth/me', async (route) => {
          await route.fulfill({
            status: 200,
            json: {
              api_version: 'v1',
              request_id: 'req_rc9_secondary_auth',
              data: {
                user: { id: 'adm_rc9_secondary', username: 'maintainer' },
                session: {
                  id: 'ses_rc9_secondary',
                  expires_at: '2027-01-01T00:00:00Z',
                },
                csrf_token: 'csrf-rc9-secondary',
              },
            },
          })
        })
        await page.route('**/healthz', async (route) => {
          await route.fulfill({ status: 200, json: { status: 'ok' } })
        })
        await page.route('**/api/v1/doctor', async (route) => {
          await route.fulfill({
            status: 503,
            json: {
              request_id: 'req_rc9_secondary_doctor',
              error: {
                code: 'RC9_UNKNOWN_DOCTOR_FAILURE',
                message: syntheticServerProse,
              },
            },
          })
        })

        const chinese = locale.expectedLocale === 'zh-CN'
        await page.goto('/doctor')
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9Title(
          page,
          chinese ? '诊断 · AgentBox' : 'Doctor · AgentBox',
        )
        const doctorAlert = page.getByRole('alert')
        await expect(doctorAlert).toContainText(
          chinese
            ? '操作未完成，请重试。'
            : 'The operation could not be completed. Try again.',
        )
        await assertRc9CanaryAbsent(page, syntheticServerProse)
        await assertRc9NoHorizontalOverflow(page)

        await page.goto('/settings')
        await assertRc9Title(
          page,
          chinese ? '设置 · AgentBox' : 'Settings · AgentBox',
        )
        const settingsAlert = page.getByRole('alert')
        await expect(settingsAlert).toContainText(
          chinese
            ? '操作未完成，请重试。'
            : 'The operation could not be completed. Try again.',
        )
        await assertRc9CanaryAbsent(page, syntheticServerProse)
        await assertRc9NoHorizontalOverflow(page)
      } finally {
        await context.close()
      }
    }
  }
})
