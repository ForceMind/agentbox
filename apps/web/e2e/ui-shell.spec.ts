import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Locator, type Page } from '@playwright/test'

import {
  assertRc9DocumentLocale,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
} from './rc9-assertions'

// Only synthetic metadata is used. No login fields, Pair Codes, terminal
// output, real credentials, traces, or video are captured by this matrix.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const project = {
  id: `prj_${'a'.repeat(32)}`,
  slug: 'interface-kit',
  display_name: '界面组件 · Interface Kit',
  source_type: 'empty',
  state: 'ready',
  repository_url: null,
  default_branch: null,
  created_at: '2026-10-01T08:00:00Z',
  updated_at: '2026-10-06T08:00:00Z',
  git: null,
  github: null,
  claude_state: null,
}
const jobId = `job_${'b'.repeat(32)}`
const job = {
  id: jobId,
  type: 'project.create',
  status: 'needs_attention',
  target_type: 'project',
  target_id: project.id,
  project_id: project.id,
  progress: null,
  phase: null,
  result_summary: null,
  error_code: 'PROJECT_RECOVERY_REQUIRED',
  error_summary: null,
  created_at: '2026-10-06T08:00:00Z',
  started_at: null,
  finished_at: null,
}

const copy = {
  en: {
    skip: 'Skip to content',
    navigation: 'Primary navigation',
    open: 'Open navigation',
    close: 'Close navigation',
    dashboard: 'Dashboard',
    projects: 'Projects',
    logs: 'Logs',
    groups: ['Work', 'Agents', 'Manage'],
    command: 'Command center',
    commandClose: 'Close command center',
    commandSearch: 'Search pages and Projects',
    system: 'System & capabilities',
    health: 'Control plane status',
    capabilities: 'Current capabilities',
    newProject: 'New Project',
    clone: 'Clone Repository',
    name: 'Project name',
    repository: 'Repository URL',
    cancel: 'Cancel',
    stale: 'This snapshot is out of date',
    refresh: 'Refresh work overview',
  },
  'zh-CN': {
    skip: '跳到主要内容',
    navigation: '主导航',
    open: '打开导航',
    close: '关闭导航',
    dashboard: '概览',
    projects: '项目',
    logs: '日志',
    groups: ['工作', 'Agent 管理', '管理'],
    command: '命令中心',
    commandClose: '关闭命令中心',
    commandSearch: '搜索页面和项目',
    system: '系统状态与能力',
    health: '控制平面状态',
    capabilities: '当前能力',
    newProject: '新建 Project',
    clone: '克隆仓库',
    name: 'Project 名称',
    repository: '仓库 URL',
    cancel: '取消',
    stale: '此快照已过期',
    refresh: '刷新工作概览',
  },
} as const

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_ui_shell_synthetic', data }
}

async function installRoutes(page: Page) {
  const mutations: string[] = []
  const unexpected: string[] = []
  const reads: string[] = []
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = `${url.pathname}${url.search}`
    if (request.method() !== 'GET') {
      mutations.push(`${request.method()} ${path}`)
      await route.fulfill({
        status: 500,
        json: { error: { code: 'UNEXPECTED_MUTATION' } },
      })
      return
    }
    reads.push(path)
    const responses: Record<string, unknown> = {
      '/api/v1/auth/me': envelope({
        user: { id: 'adm_ui_shell', username: 'synthetic-maintainer' },
        session: { id: 'ses_ui_shell', expires_at: '2027-01-01T00:00:00Z' },
        csrf_token: 'synthetic-ui-shell-csrf',
      }),
      '/healthz': { status: 'ok' },
      '/readyz': {
        status: 'ready',
        checks: { database: true, migrations: true },
      },
      '/api/v1/meta': {
        name: 'AgentBox',
        version: '0.3.0-rc.31',
        api_version: 'v1',
        environment: 'test',
      },
      '/api/v1/jobs?scope=mine': envelope({ jobs: [job] }),
      '/api/v1/projects/recent': envelope({ projects: [project] }),
      '/api/v1/projects': envelope({ projects: [project] }),
      '/api/v1/project-favorites': envelope({ favorites: [] }),
    }
    if (!(path in responses)) {
      unexpected.push(path)
      await route.fulfill({
        status: 404,
        json: { error: { code: 'UNEXPECTED_READ' } },
      })
      return
    }
    await route.fulfill({ json: responses[path] })
  })
  return { mutations, unexpected, reads }
}

async function assertNativeFocusTrap(page: Page, dialog: Locator) {
  await expect(dialog).toHaveAttribute('aria-modal', 'true')
  expect(await dialog.evaluate((element) => element.matches(':modal'))).toBe(
    true,
  )
  const focusables = dialog.locator('button:enabled, a[href], input:enabled')
  const first = focusables.first()
  const last = focusables.last()
  await first.focus()
  await page.keyboard.press('Shift+Tab')
  await expect(last).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(first).toBeFocused()
  await page
    .locator('main')
    .evaluate((element) => (element as HTMLElement).focus())
  expect(
    await dialog.evaluate((element) =>
      element.contains(document.activeElement),
    ),
  ).toBe(true)
}

async function capture(page: Page, name: string) {
  await mkdir('test-results', { recursive: true })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: join('test-results', `ui-shell-${name}.png`),
    fullPage: true,
  })
}

for (const locale of ['zh-CN', 'en'] as const) {
  for (const width of [360, 390, 768, 1024, 1440]) {
    for (const colorScheme of ['light', 'dark'] as const) {
      test(`shell ${locale} ${width}px ${colorScheme}: disclosure, modal, history and read-only boundaries`, async ({
        browser,
        baseURL,
      }, testInfo) => {
        test.skip(
          testInfo.project.name !== 'desktop-chromium',
          'the isolated responsive matrix runs once',
        )
        const context = await browser.newContext({
          baseURL,
          locale,
          colorScheme,
          viewport: { width, height: 900 },
          isMobile: width < 900,
          hasTouch: width < 900,
        })
        try {
          const page = await context.newPage()
          const errors: string[] = []
          page.on('pageerror', (error) => errors.push(error.message))
          const requests = await installRoutes(page)
          const expected = copy[locale]
          const mobile = width < 900
          await page.goto('/dashboard')
          await assertRc9DocumentLocale(page, locale)
          await expect(page.getByText(jobId, { exact: true })).toBeVisible()
          const palette = await page.evaluate(() => {
            const style = getComputedStyle(document.documentElement)
            return {
              colorScheme: style.colorScheme,
              background: style.getPropertyValue('--bg').trim(),
            }
          })
          expect(palette).toEqual({
            colorScheme,
            background: colorScheme === 'light' ? '#f6f5f1' : '#202320',
          })
          await page.keyboard.press('Tab')
          await expect(
            page.getByRole('link', { name: expected.skip, exact: true }),
          ).toBeFocused()
          await page.keyboard.press('Enter')
          await expect(page.locator('main')).toBeFocused()

          const system = page.locator('details.dashboard-system')
          await expect(system).not.toHaveAttribute('open', '')
          await expect(
            page.getByRole('heading', { name: expected.capabilities }),
          ).toBeHidden()
          await page.getByLabel(expected.system, { exact: true }).click()
          await expect(system).toHaveAttribute('open', '')
          await expect(
            page.getByRole('region', { name: expected.health }),
          ).toBeVisible()
          await expect(
            page.getByRole('heading', { name: expected.capabilities }),
          ).toBeVisible()
          await assertRc9NoHorizontalOverflow(page)
          await assertRc9InteractiveTargets(page)
          await page.getByLabel(expected.system, { exact: true }).click()
          await capture(page, `${locale}-${width}-${colorScheme}-dashboard`)

          if (mobile) {
            const trigger = page.locator(
              '.mobile-header button[aria-controls="mobile-navigation"]',
            )
            await expect(trigger).toHaveAccessibleName(expected.open)
            await trigger.click()
            const drawer = page.getByRole('dialog', {
              name: expected.navigation,
              exact: true,
            })
            await expect(drawer).toBeVisible()
            await expect(trigger).toHaveAttribute('aria-expanded', 'true')
            for (const group of expected.groups)
              await expect(
                drawer.getByText(group, { exact: true }),
              ).toBeVisible()
            await assertNativeFocusTrap(page, drawer)
            await assertRc9NoHorizontalOverflow(page)
            if (width === 390)
              await capture(
                page,
                `${locale}-${width}-${colorScheme}-navigation`,
              )
            await page.keyboard.press('Escape')
            await expect(drawer).toHaveCount(0)
            await expect(trigger).toBeFocused()
            await expect(trigger).toHaveAttribute('aria-expanded', 'false')
            await trigger.click()
            await drawer
              .getByRole('button', { name: expected.close, exact: true })
              .click()
            await expect(drawer).toHaveCount(0)
            await expect(trigger).toBeFocused()
            await trigger.click()
            await drawer
              .getByRole('link', { name: expected.logs, exact: true })
              .click()
            await expect(page).toHaveURL(/\/logs$/)
            await expect(drawer).toHaveCount(0)
            await trigger.click()
            await page.goBack()
            await expect(page).toHaveURL(/\/dashboard(?:#main-content)?$/)
            await expect(drawer).toHaveCount(0)
            await page.goForward()
            await expect(page).toHaveURL(/\/logs$/)
            await expect(drawer).toHaveCount(0)
            await page.goBack()
            await trigger.click()
            await page.setViewportSize({ width: 1024, height: 900 })
            await expect(drawer).toHaveCount(0)
            await page.setViewportSize({ width, height: 900 })
            await expect(trigger).toHaveAccessibleName(expected.open)
          } else {
            const navigation = page.getByRole('navigation', {
              name: expected.navigation,
            })
            for (const group of expected.groups)
              await expect(
                navigation.getByText(group, { exact: true }),
              ).toBeVisible()
            await expect(page.locator('.mobile-header')).toBeHidden()
          }

          const commandTrigger = page.getByRole('button', {
            name: expected.command,
          })
          const command = page.getByRole('dialog', {
            name: expected.command,
            exact: true,
          })
          await commandTrigger.click()
          const search = command.getByRole('combobox', {
            name: expected.commandSearch,
          })
          await expect(search).toBeFocused()
          await search.fill('Interface Kit')
          await expect(
            command.getByRole('option', { name: project.display_name }),
          ).toBeVisible()
          await assertNativeFocusTrap(page, command)
          await search.focus()
          await search.press('Escape')
          await expect(command).toHaveCount(0)
          await expect(commandTrigger).toBeFocused()
          await commandTrigger.click()
          await expect(search).toHaveValue('')
          await command
            .getByRole('button', { name: expected.commandClose, exact: true })
            .click()
          await expect(command).toHaveCount(0)
          await expect(commandTrigger).toBeFocused()
          await page.keyboard.press('Control+k')
          await search.fill(expected.projects)
          await command
            .getByRole('option', { name: expected.projects, exact: true })
            .click()
          await expect(page).toHaveURL(/\/projects$/)
          await expect(command).toHaveCount(0)
          await expect(
            page.getByRole('heading', { name: project.display_name }),
          ).toBeVisible()
          await commandTrigger.click()
          await page.goBack()
          await expect(page).toHaveURL(/\/dashboard(?:#main-content)?$/)
          await expect(command).toHaveCount(0)
          await page.goForward()
          await expect(page).toHaveURL(/\/projects$/)
          await expect(command).toHaveCount(0)

          const create = page.getByRole('button', {
            name: expected.newProject,
            exact: true,
          })
          const clone = page.getByRole('button', {
            name: expected.clone,
            exact: true,
          })
          const name = page.getByLabel(expected.name, { exact: true })
          const repository = page.getByLabel(expected.repository, {
            exact: true,
          })
          await expect(name).toHaveCount(0)
          await expect(repository).toHaveCount(0)
          await capture(page, `${locale}-${width}-${colorScheme}-projects`)
          await create.click()
          await expect(name).toBeFocused()
          await name.fill('Synthetic unsaved project')
          await page
            .getByRole('button', { name: expected.cancel, exact: true })
            .click()
          await expect(name).toHaveCount(0)
          await expect(create).toBeFocused()
          await create.click()
          await expect(name).toHaveValue('')
          await name.fill('Discard with Escape')
          await name.press('Escape')
          await expect(name).toHaveCount(0)
          await expect(create).toBeFocused()
          await clone.click()
          await expect(repository).toBeFocused()
          await repository.fill('https://github.com/example/synthetic.git')
          await assertRc9NoHorizontalOverflow(page)
          await assertRc9InteractiveTargets(page)
          await repository.press('Escape')
          await expect(repository).toHaveCount(0)
          await expect(clone).toBeFocused()
          await clone.click()
          await expect(repository).toHaveValue('')
          await create.click()
          await expect(repository).toHaveCount(0)
          await expect(name).toHaveValue('')
          await page
            .getByRole('button', { name: expected.cancel, exact: true })
            .click()
          await assertRc9NoHorizontalOverflow(page)
          await assertRc9InteractiveTargets(page)
          await create.click()
          await name.fill('Discard on newer navigation')
          await page.keyboard.press('Control+k')
          await search.fill(expected.logs)
          await command
            .getByRole('option', { name: expected.logs, exact: true })
            .click()
          await expect(page).toHaveURL(/\/logs$/)
          await page.goBack()
          await expect(page).toHaveURL(/\/projects$/)
          await expect(name).toHaveCount(0)
          await create.click()
          await expect(name).toHaveValue('')
          await name.press('Escape')
          expect(requests.mutations).toEqual([])
          expect(requests.unexpected).toEqual([])
          expect(errors).toEqual([])
        } finally {
          await context.close()
        }
      })
    }
  }
}

for (const locale of ['zh-CN', 'en'] as const) {
  test(`shell ${locale} interruption: stale overview and newer navigation cannot restore a dismissed surface`, async ({
    page,
  }) => {
    await page.addInitScript((language) => {
      Object.defineProperty(navigator, 'languages', { value: [language] })
    }, locale)
    const expected = copy[locale]
    const requests = await installRoutes(page)
    await page.goto('/dashboard')
    await expect(page.getByText(jobId, { exact: true })).toBeVisible()
    const trigger = page.getByRole('button', {
      name: expected.open,
      exact: true,
    })
    if (await trigger.isVisible()) await trigger.click()
    const beforeOffline = requests.reads.length
    await page.evaluate(() => window.dispatchEvent(new Event('offline')))
    await expect(
      page.getByRole('dialog', { name: expected.navigation }),
    ).toHaveCount(0)
    await expect(
      page.getByText(new RegExp(expected.stale)).first(),
    ).toBeVisible()
    await expect(page.getByText(jobId, { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: expected.refresh }).click()
    expect(requests.reads).toHaveLength(beforeOffline)
    await page.evaluate(() => window.dispatchEvent(new Event('online')))
    await expect(page.getByText(jobId, { exact: true })).toBeVisible()

    let release!: () => void
    let held!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const arrived = new Promise<void>((resolve) => {
      held = resolve
    })
    await page.route(
      '**/api/v1/projects',
      async (route) => {
        held()
        await gate
        await route.fulfill({
          json: envelope({
            projects: [{ ...project, display_name: 'Obsolete command result' }],
          }),
        })
      },
      { times: 1 },
    )
    try {
      await page.keyboard.press('Control+k')
      await arrived
      const command = page.getByRole('dialog', {
        name: expected.command,
        exact: true,
      })
      await command.getByRole('combobox').press('Escape')
      await expect(command).toHaveCount(0)
      await page.keyboard.press('Control+k')
      await command.getByRole('combobox').fill(expected.projects)
      await command
        .getByRole('option', { name: expected.projects, exact: true })
        .click()
      await expect(page).toHaveURL(/\/projects$/)
      release()
      await expect(
        page.getByRole('heading', { name: project.display_name }),
      ).toBeVisible()
      await expect(page.getByText('Obsolete command result')).toHaveCount(0)
      await expect(command).toHaveCount(0)
      await page.goBack()
      await expect(page.getByText(jobId, { exact: true })).toBeVisible()
      await expect(command).toHaveCount(0)
      expect(requests.mutations).toEqual([])
      expect(requests.unexpected).toEqual([])
    } finally {
      release()
    }
  })
}
