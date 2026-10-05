import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

import {
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
} from './rc9-assertions'

const jobId = (index: number) =>
  `job_${(index + 9000).toString(16).padStart(32, '0')}`
const copy = {
  en: {
    user: 'Username',
    password: 'Password',
    login: 'Sign in',
    title: 'Your work',
    attention: 'Needs attention',
    active: 'Active work',
    projects: 'Recently updated projects',
    refresh: 'Refresh work overview',
    empty: 'No queued or running operations in this window.',
    stale: 'This snapshot is out of date',
    error: 'Work metadata could not be loaded',
    permission: 'You do not have access',
    loading: 'Loading work metadata',
    health: 'Control plane status',
    attentionLink: 'Review needs attention',
  },
  'zh-CN': {
    user: '用户名',
    password: '密码',
    login: '登录',
    title: '工作概览',
    attention: '待处理',
    active: '进行中的工作',
    projects: '最近更新的项目',
    refresh: '刷新工作概览',
    empty: '此窗口内没有排队或运行中的操作。',
    stale: '此快照已过期',
    error: '无法加载工作元数据',
    permission: '你无权查看此快照',
    loading: '正在加载工作元数据',
    health: '控制平面状态',
    attentionLink: '查看待处理',
  },
} as const
async function login(page: Page, locale: keyof typeof copy) {
  const expected = copy[locale]
  await page.goto('/login')
  await page
    .getByLabel(expected.user, { exact: true })
    .fill(process.env.AGENTBOX_E2E_USERNAME!)
  await page
    .getByLabel(expected.password, { exact: true })
    .fill(process.env.AGENTBOX_E2E_PASSWORD!)
  await page.getByRole('button', { name: expected.login, exact: true }).click()
  await expect(
    page.getByRole('region', { name: expected.title, exact: true }),
  ).toBeVisible()
}

test.use({ screenshot: 'off', trace: 'off', video: 'off' })

for (const locale of ['en', 'zh-CN'] as const) {
  test.describe(`work overview ${locale}`, () => {
    test.use({ locale })

    test('formal App reads authenticated durable metadata, preserves health, and links existing work', async ({
      page,
    }, testInfo) => {
      const expected = copy[locale]
      await login(page, locale)
      const overview = page.getByRole('region', {
        name: expected.title,
        exact: true,
      })
      const attention = overview.getByRole('region', {
        name: expected.attention,
        exact: true,
      })
      const active = overview.getByRole('region', {
        name: expected.active,
        exact: true,
      })
      const projects = overview.getByRole('region', {
        name: expected.projects,
        exact: true,
      })
      await expect(attention.getByText(jobId(1), { exact: true })).toBeVisible()
      await expect(active.getByText(jobId(2), { exact: true })).toBeVisible()
      await expect(active.getByText(jobId(3), { exact: true })).toBeVisible()
      await expect(overview.getByText(jobId(4), { exact: true })).toHaveCount(0)
      await expect(overview.getByText(jobId(5), { exact: true })).toHaveCount(0)
      await expect(overview.getByText(`job_${'f'.repeat(32)}`)).toHaveCount(0)
      await expect(
        projects.getByRole('link', { name: '界面组件 🚀', exact: true }),
      ).toBeVisible()
      await expect(
        projects.locator('time[datetime="2026-10-05T08:03:00Z"]'),
      ).toHaveCount(1)
      await expect(overview).not.toContainText('OVERVIEW-PRIVATE')
      await expect(
        page.getByRole('region', { name: expected.health }),
      ).toBeVisible()
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
      const refresh = overview.getByRole('button', { name: expected.refresh })
      // A pointer login leaves pointer modality active. Exercise actual Tab
      // navigation, rather than assuming programmatic focus is :focus-visible.
      const unfocused = await refresh.evaluate((element) => {
        const style = getComputedStyle(element)
        return [
          style.outlineStyle,
          style.outlineWidth,
          style.outlineColor,
          style.boxShadow,
        ]
      })
      const tabStops = await page
        .locator('a[href], button, input, select, textarea, [tabindex="0"]')
        .count()
      for (let index = 0; index <= tabStops; index++) {
        await page.keyboard.press('Tab')
        if (
          await refresh.evaluate(
            (element) => document.activeElement === element,
          )
        )
          break
      }
      await expect(refresh).toBeFocused()
      expect(
        await refresh.evaluate((element) => element.matches(':focus-visible')),
      ).toBe(true)
      const focused = await refresh.evaluate((element) => {
        const style = getComputedStyle(element)
        return [
          style.outlineStyle,
          style.outlineWidth,
          style.outlineColor,
          style.boxShadow,
        ]
      })
      expect(focused, 'keyboard focus must visibly change refresh').not.toEqual(
        unfocused,
      )
      await page.keyboard.press('Enter')
      await expect(refresh).toBeEnabled()
      await expect(active.getByText(jobId(2), { exact: true })).toBeVisible()
      // Images contain only synthetic seeded metadata; never credentials/CLI output.
      await page.evaluate(() => window.scrollTo(0, 0))
      await mkdir(join('test-results'), { recursive: true })
      await page.screenshot({
        path: join(
          'test-results',
          `work-overview-${locale}-${testInfo.project.name}.png`,
        ),
        fullPage: true,
      })
      const mutations: string[] = []
      page.on('request', (request) => {
        if (request.method() !== 'GET') mutations.push(request.method())
      })
      await overview.getByRole('link', { name: expected.attentionLink }).click()
      await expect(page).toHaveURL(/\/attention$/)
      await expect(page.getByText(jobId(1), { exact: true })).toBeVisible()
      await page.goBack()
      await expect(
        page.getByRole('region', { name: expected.title, exact: true }),
      ).toBeVisible()
      expect(mutations).toEqual([])
    })

    test('distinguishes loading, empty, permission, failure and stale states with bounded refresh', async ({
      page,
    }, testInfo) => {
      const expected = copy[locale]
      await login(page, locale)
      const overview = page.getByRole('region', {
        name: expected.title,
        exact: true,
      })
      await expect(overview.getByText(jobId(2), { exact: true })).toBeVisible()
      let mode: 'empty' | 'permission' | 'error' = 'empty'
      let count = 0
      let release!: () => void
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      await page.route('**/api/v1/jobs?scope=mine', async (route) => {
        count++
        if (count === 1) await gate
        await route.fulfill({
          status: mode === 'empty' ? 200 : mode === 'permission' ? 403 : 503,
          json:
            mode === 'empty'
              ? {
                  api_version: 'v1',
                  request_id: 'req_empty',
                  data: { jobs: [] },
                }
              : {
                  error: { code: 'PRIVATE', message: 'OVERVIEW-PRIVATE-ERROR' },
                },
        })
      })
      const refresh = overview.getByRole('button', { name: expected.refresh })
      await refresh.click()
      await expect(
        overview.getByText(new RegExp(expected.loading)).first(),
      ).toBeVisible()
      await expect(refresh).toBeDisabled()
      release()
      await expect(
        overview.getByText(expected.empty, { exact: true }),
      ).toBeVisible()
      mode = 'permission'
      await refresh.click()
      await expect(overview.getByRole('alert').first()).toContainText(
        expected.permission,
      )
      mode = 'error'
      await refresh.click()
      await expect(overview.getByRole('alert').first()).toContainText(
        expected.error,
      )
      await expect(overview).not.toContainText('OVERVIEW-PRIVATE')
      await page.evaluate(() => window.dispatchEvent(new Event('offline')))
      await expect(
        overview.getByText(new RegExp(expected.stale)).first(),
      ).toBeVisible()
      await refresh.click()
      expect(count).toBe(3)
      mode = 'empty'
      await page.evaluate(() => {
        window.dispatchEvent(new Event('online'))
        window.dispatchEvent(new Event('pageshow'))
      })
      await expect(
        overview.getByText(expected.empty, { exact: true }),
      ).toBeVisible()
      expect(count).toBe(4)
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
      if (locale === 'zh-CN') {
        await page.evaluate(() => window.scrollTo(0, 0))
        await page.screenshot({
          path: join(
            'test-results',
            `work-overview-empty-${testInfo.project.name}.png`,
          ),
          fullPage: true,
        })
      }
    })
  })
}
