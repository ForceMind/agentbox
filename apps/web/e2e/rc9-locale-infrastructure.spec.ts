import { expect, test } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9NonEmptyTitle,
} from './rc9-assertions'
import {
  createRc9DocumentContext,
  createRc9RouteHold,
  installRc9HeldRoute,
  RC9_LOCALE_SCENARIOS,
  RC9_VIEWPORTS,
} from './rc9-fixtures'

// Login is a non-sensitive route. Sensitive surface specs must keep this
// explicit declaration even though the shared configuration has the same fence.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const syntheticServerProse = 'RC9-SYNTHETIC-SERVER-PROSE-CANARY'

const authData = {
  user: { id: 'adm_rc9_synthetic', username: 'synthetic-user' },
  session: { id: 'ses_rc9_synthetic', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'csrf-rc9-synthetic',
}

test('creates exactly four isolated rc9 browser documents and fences synthetic server prose', async ({
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
      const firstLogin = createRc9RouteHold()
      try {
        const page = await context.newPage()
        await page.route('**/api/v1/auth/me', async (route) => {
          await route.fulfill({
            status: 401,
            json: { request_id: 'req_rc9_me' },
          })
        })
        await page.route('**/healthz', async (route) => {
          await route.fulfill({ status: 200, json: { status: 'ok' } })
        })
        await page.route('**/api/v1/auth/login', async (route) => {
          await route.fulfill({
            status: 200,
            json: {
              api_version: 'v1',
              request_id: 'req_rc9_login_ok',
              data: authData,
            },
          })
        })
        await installRc9HeldRoute(page, '**/api/v1/auth/login', firstLogin, {
          status: 500,
          json: {
            request_id: 'req_rc9_login_error',
            error: {
              code: 'RC9_UNKNOWN_SERVER_FAILURE',
              message: syntheticServerProse,
            },
          },
        })
        await page.goto('/login')

        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9NonEmptyTitle(page)
        await expect(page.locator('main')).toBeVisible()
        await assertRc9InteractiveTargets(page)
        const username = page.locator('input').nth(0)
        const password = page.locator('input').nth(1)
        const submit = page.locator('button[type="submit"]')
        await expect(username).toBeVisible()
        await assertRc9Focus(username)
        await username.fill('synthetic-user')
        await password.fill('synthetic-password')
        await submit.click()
        await firstLogin.waitUntilHeld()
        await expect(submit).toBeDisabled()
        firstLogin.release()
        const error = page.getByRole('alert')
        await expect(error).toBeVisible()
        await expect(error).toContainText(
          locale.expectedLocale === 'zh-CN'
            ? '操作未完成，请重试。'
            : 'The operation could not be completed. Try again.',
        )
        await assertRc9InteractiveTargets(page)
        await assertRc9CanaryAbsent(page, syntheticServerProse)

        await password.fill('synthetic-password')
        await submit.click()
        await expect(page).toHaveURL(/\/dashboard$/)
        await assertRc9CanaryAbsent(page, syntheticServerProse)
        await assertRc9NoHorizontalOverflow(page)
      } finally {
        firstLogin.dispose()
        await context.close()
      }
    }
  }
})
