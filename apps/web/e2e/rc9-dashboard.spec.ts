import { expect, test, type Page, type Route } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
  assertRc9Title,
} from './rc9-assertions'
import {
  createRc9DocumentContext,
  RC9_LOCALE_SCENARIOS,
  RC9_VIEWPORTS,
} from './rc9-fixtures'

const copy = {
  en: {
    title: 'Dashboard',
    checking: 'Checking',
    healthy: 'Healthy',
    unavailable: 'Unavailable',
    capabilities: 'Current capabilities',
  },
  'zh-CN': {
    title: '概览',
    checking: '正在检查',
    healthy: '正常',
    unavailable: '暂不可用',
    capabilities: '当前能力',
  },
} as const

const authData = {
  user: { id: 'adm_rc9_dashboard', username: '管理员 🚀' },
  session: { id: 'ses_rc9_dashboard', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'csrf-rc9-dashboard',
}

async function fulfillJson(route: Route, status: number, body: object) {
  await route.fulfill({ status, json: body })
}

async function installDashboardRoutes(page: Page, healthGate: Promise<void>) {
  await page.route('**/api/v1/auth/me', (route) =>
    fulfillJson(route, 200, {
      api_version: 'v1',
      request_id: 'req_rc9_dashboard_auth',
      data: authData,
    }),
  )
  await page.route('**/healthz', async (route) => {
    await healthGate
    await fulfillJson(route, 200, { status: 'ok' })
  })
  await page.route('**/readyz', (route) =>
    fulfillJson(route, 200, {
      status: 'ready',
      checks: { database: true, migrations: true },
    }),
  )
  await page.route('**/api/v1/meta', (route) =>
    fulfillJson(route, 200, {
      name: 'AgentBox',
      version: '0.3.0-rc.9',
      api_version: 'v1',
      environment: 'test',
    }),
  )
}

test('covers Dashboard loading, healthy, and unavailable states in the rc9 matrix', async ({
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
      let releaseHealth!: () => void
      const healthGate = new Promise<void>((resolve) => {
        releaseHealth = resolve
      })
      const expected = copy[locale.expectedLocale]

      try {
        const page = await context.newPage()
        await installDashboardRoutes(page, healthGate)
        await page.goto('/dashboard')
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9Title(page, new RegExp(`${expected.title} · AgentBox`))
        await expect(
          page
            .locator('.metric-card:visible')
            .getByText(expected.checking, { exact: true })
            .first(),
        ).toBeVisible()

        releaseHealth()
        await expect(
          page.getByRole('heading', { name: expected.capabilities }),
        ).toBeVisible()
        await expect(
          page
            .locator('.metric-card:visible')
            .getByText(expected.healthy, { exact: true })
            .first(),
        ).toBeVisible()
        await assertRc9TechnicalRendering(page.getByText('0.3.0-rc.9').first())
        await assertRc9TechnicalRendering(page.getByText('v1'))
        await assertRc9TechnicalRendering(page.getByText('test'))
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)

        await page.unroute('**/healthz')
        await page.route('**/healthz', (route) =>
          fulfillJson(route, 503, {
            code: 'CONTROL_PLANE_UNAVAILABLE',
            message: 'RC9-DASHBOARD-SERVER-PROSE-CANARY',
          }),
        )
        await page.reload()
        await expect(
          page
            .locator('.metric-card:visible')
            .getByText(expected.unavailable, { exact: true })
            .first(),
        ).toBeVisible()
        await assertRc9CanaryAbsent(page, 'RC9-DASHBOARD-SERVER-PROSE-CANARY')
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        releaseHealth()
        await context.close()
      }
    }
  }
})
