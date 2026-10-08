import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page, type Route } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9InteractiveTargets,
  assertRc9ModalDialog,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
  assertRc9Title,
} from './rc9-assertions'
import { createRc9RouteHold, type Rc9RouteHold } from './rc9-fixtures'

// The real App and controllers receive only the exact synthetic metadata below.
// Production trust stays unavailable: no ticket, transport, terminal output,
// credentials, global product hook, trace, video or automatic failure capture.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const PROJECT_A = `prj_${'a'.repeat(32)}`
const PROJECT_B = `prj_${'b'.repeat(32)}`
const WORKSPACE_A = `aws_${'c'.repeat(32)}`
const WORKSPACE_B = `aws_${'d'.repeat(32)}`
const GENERATION = '7'
const LONG_NAME =
  '工作区界面 · Workspace <img src=x onerror=alert(1)> & "inert" '
    .repeat(2)
    .trim()
const PRIVATE_PROSE = 'synthetic-workspace-server-prose-must-not-render'
const LABEL = {
  id: `lbl_${'e'.repeat(32)}`,
  name: '界面验收 <b>inert</b>',
  color: 'amber',
  revision: 1,
  updated_at: '2026-10-07T00:00:00Z',
}

const copy = {
  en: {
    title: 'Interactive workspace',
    project: 'Formal READY Project',
    loadingProjects: 'Loading Projects…',
    noProjects: 'No READY Projects',
    loadingWorkspace: 'Loading workspace information…',
    unregistered:
      'This AgentType is not registered and cannot start a workspace.',
    start: 'Start workspace',
    stop: 'Stop workspace',
    connect: 'Connect terminal',
    reconnect: 'Reconnect',
    detach: 'Disconnect',
    input: 'Send input',
    running: 'Running',
    stopped: 'Stopped',
    unavailable: 'Trust provider unavailable',
    providerUnavailable:
      'The managed browser trust provider is unavailable, so no terminal ticket was requested.',
    runtime: 'Runtime metadata',
    stale:
      'The previous Runtime snapshot is no longer current. Workspace actions are paused.',
    revalidating:
      'Reconfirming the current Runtime status. Workspace actions remain paused.',
    recovery:
      'Runtime recovery review is required. Workspace operations are paused.',
    confirmTitle: 'Confirm workspace stop',
    cancel: 'Cancel',
    confirmStop: 'Confirm stop',
    stoppedNotice:
      'The managed process stopped. Project and Git changes were preserved.',
    navigation: 'Primary navigation',
    menu: 'Open navigation',
    workspace: 'Workspace',
  },
  'zh-CN': {
    title: '交互式工作区',
    project: '正式 READY Project',
    loadingProjects: '正在加载 Project…',
    noProjects: '暂无 READY Project',
    loadingWorkspace: '正在读取工作区信息…',
    unregistered: '当前 AgentType 尚未注册，无法启动工作区。',
    start: '启动工作区',
    stop: '停止工作区',
    connect: '连接终端',
    reconnect: '重新连接',
    detach: '断开连接',
    input: '发送输入',
    running: '运行中',
    stopped: '已停止',
    unavailable: '信任 provider 不可用',
    providerUnavailable:
      '受管浏览器信任 provider 不可用，因此未请求终端 ticket。',
    runtime: 'Runtime 元数据',
    stale: '之前的 Runtime 快照已失效，工作区操作已暂停。',
    revalidating: '正在重新确认当前 Runtime 状态，工作区操作仍处于暂停状态。',
    recovery: 'Runtime 需要恢复核对，工作区操作已暂停。',
    confirmTitle: '确认停止工作区',
    cancel: '取消',
    confirmStop: '确认停止',
    stoppedNotice: '受管进程已停止，Project 和 Git 修改已保留。',
    navigation: '主导航',
    menu: '打开导航',
    workspace: '工作区',
  },
} as const

type Locale = keyof typeof copy
type Mode = 'ready' | 'unregistered' | 'error' | 'forbidden' | 'disabled'

function project(id = PROJECT_A, representative = false) {
  return {
    id,
    slug: id === PROJECT_A ? 'workspace-interface' : 'workspace-second',
    display_name:
      id === PROJECT_A
        ? representative
          ? 'AgentBox 工作台'
          : LONG_NAME
        : '第二项目 · Project B',
    source_type: 'existing',
    state: 'ready',
    repository_url: null,
    default_branch: 'main',
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-07T00:00:00Z',
    git: null,
    github: null,
    claude_state: null,
  }
}

function workspace(id = PROJECT_A, state = 'RUNNING') {
  return {
    id: id === PROJECT_A ? WORKSPACE_A : WORKSPACE_B,
    project_id: id,
    agent_type: 'codex',
    state,
    reconciliation_state: 'authoritative',
    generation: Number(GENERATION),
    revision: 1,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-07T00:00:00Z',
    last_seen_at: '2026-10-07T00:00:00Z',
    exit_code: null,
    failure_code: null,
  }
}

function runtime(id = PROJECT_A, state = 'RUNNING', disabled = false) {
  return {
    workspace_id: workspace(id).id,
    project_id: id,
    agent_type: 'codex',
    generation: GENERATION,
    binding_revision: '1',
    binding_digest: 'a'.repeat(64),
    state: disabled ? 'UNKNOWN' : state,
    reconciliation_state: disabled
      ? 'reconciliation_required'
      : 'authoritative',
    runtime_epoch: '9',
    process_state: disabled ? 'UNKNOWN' : state,
    exit_code: null,
    attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
  }
}

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_ui_workspace_synthetic', data }
}

// Workspace metadata and Runtime status use the unversioned Workspace wire
// contract; auth, Project and label responses use the versioned API envelope.
function workspaceEnvelope(data: unknown) {
  return { request_id: 'req_ui_workspace_synthetic', data }
}

function failure(code: string) {
  return {
    request_id: 'req_ui_workspace_synthetic',
    error: { code, message: PRIVATE_PROSE },
  }
}

const listPath = (id = PROJECT_A, agent = 'codex') =>
  `/api/v1/workspaces?project_id=${id}&agent_type=${agent}`
const statusPath = (id = PROJECT_A) =>
  `/api/v1/workspaces/${workspace(id).id}/status`
const workspacePath = (id = PROJECT_A) =>
  `/workspace?project_id=${id}&agent_type=codex`

async function fixtures(page: Page, representative = false) {
  const label = representative ? { ...LABEL, name: '界面验收' } : LABEL
  const state = {
    mode: 'ready' as Mode,
    emptyProjects: false,
    lifecycleA: 'RUNNING',
    session: 'a',
    allowStop: false,
    stopUnauthorized: false,
    holds: new Map<string, Rc9RouteHold>(),
    reads: [] as string[],
    responses: [] as string[],
    mutations: [] as { path: string; body: unknown; csrf: string }[],
    unexpected: [] as string[],
    errors: [] as string[],
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  page.on('websocket', () => state.unexpected.push('WebSocket connection'))
  const hold = async (path: string) => {
    const pending = state.holds.get(path)
    state.holds.delete(path)
    await pending?.hold()
  }
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = `${url.pathname}${url.search}`
    if (request.method() !== 'GET') {
      state.mutations.push({
        path: `${request.method()} ${path}`,
        body: request.postDataJSON(),
        csrf: request.headers()['x-csrf-token'] ?? '',
      })
      if (
        state.allowStop &&
        request.method() === 'POST' &&
        path === `/api/v1/workspaces/${WORKSPACE_A}/stop`
      ) {
        const unauthorized = state.stopUnauthorized
        await hold(path)
        if (unauthorized) {
          await route.fulfill({ status: 401, json: failure('UNAUTHENTICATED') })
        } else {
          state.lifecycleA = 'STOPPED'
          await route.fulfill({
            json: {
              request_id: 'req_ui_workspace_stop',
              workspace_id: WORKSPACE_A,
              project_id: PROJECT_A,
              agent_type: 'codex',
              generation: GENERATION,
              stop_operation_id: `wso_${'f'.repeat(32)}`,
              state: 'STOPPED',
            },
          })
        }
        state.responses.push(path)
      } else {
        state.unexpected.push(`${request.method()} ${path}`)
        await route.fulfill({
          status: 500,
          json: failure('UNEXPECTED_MUTATION'),
        })
      }
      return
    }
    state.reads.push(path)
    const responses: Record<string, unknown> = {
      '/healthz': { status: 'ok' },
      '/api/v1/auth/me': envelope({
        user: { id: 'adm_ui_workspace', username: 'synthetic-maintainer' },
        session: {
          id: `ses_ui_workspace_${state.session}`,
          expires_at: '2027-01-01T00:00:00Z',
        },
        csrf_token: `synthetic-ui-workspace-csrf-${state.session}`,
      }),
      '/api/v1/projects': envelope({
        projects: state.emptyProjects
          ? []
          : [
              project(PROJECT_A, representative),
              project(PROJECT_B, representative),
            ],
      }),
      '/api/v1/project-labels': envelope({ labels: [label] }),
    }
    for (const id of [PROJECT_A, PROJECT_B]) {
      const lifecycle = id === PROJECT_A ? state.lifecycleA : 'RUNNING'
      responses[`/api/v1/workspaces/${workspace(id).id}`] = workspaceEnvelope(
        workspace(id, lifecycle),
      )
      responses[statusPath(id)] = workspaceEnvelope(
        runtime(id, lifecycle, state.mode === 'disabled'),
      )
      for (const agent of ['claude', 'codex']) {
        responses[listPath(id, agent)] = workspaceEnvelope({
          workspaces:
            agent === 'claude' || state.mode === 'unregistered'
              ? []
              : [workspace(id, lifecycle)],
        })
        responses[`/api/v1/project-labels/workspaces/${id}/${agent}`] =
          envelope({
            workspace_id: workspace(id).id,
            project_id: id,
            agent_type: agent,
            labels: [label],
            revision: 1,
            updated_at: LABEL.updated_at,
          })
      }
    }
    if (!(path in responses)) {
      state.unexpected.push(`GET ${path}`)
      await route.fulfill({ status: 404, json: failure('UNEXPECTED_READ') })
      return
    }
    // Snapshot before the hold: a late response stays owned by the old request.
    const response = responses[path]
    const mode = state.mode
    await hold(path)
    if (path === listPath() && (mode === 'error' || mode === 'forbidden')) {
      await route.fulfill({
        status: mode === 'forbidden' ? 403 : 503,
        json: failure(
          mode === 'forbidden' ? 'FORBIDDEN' : 'WAW_STATUS_UNAVAILABLE',
        ),
      })
    } else {
      await route.fulfill({ json: response })
    }
    state.responses.push(path)
  })
  return state
}

type Fixtures = Awaited<ReturnType<typeof fixtures>>

async function assertBoundaries(page: Page, state: Fixtures, mutations = 0) {
  expect(state.unexpected).toEqual([])
  expect(state.errors).toEqual([])
  expect(state.mutations).toHaveLength(mutations)
  expect(
    state.reads.some((path) =>
      /\/(?:attachments|tickets|providers|output|staged-stream)(?:[/?]|$)/.test(
        path,
      ),
    ),
  ).toBe(false)
  await assertRc9CanaryAbsent(page, PRIVATE_PROSE)
  expect(
    await page.evaluate(() => ({
      local: Object.entries(localStorage),
      session: Object.entries(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] })
}

async function ready(page: Page, locale: Locale, id = PROJECT_A) {
  const expected = copy[locale]
  await expect(
    page.getByRole('heading', { name: expected.title, level: 1, exact: true }),
  ).toBeVisible()
  await assertRc9Title(page, `${expected.title} · Kebui`)
  await expect(page.getByLabel(expected.project, { exact: true })).toHaveValue(
    id,
  )
  await expect(
    page.getByRole('button', { name: expected.stop, exact: true }),
  ).toBeEnabled()
  await expect(page.getByText(workspace(id).id, { exact: true })).toBeVisible()
  await expect(page.locator('.workspace-status-card time')).toBeVisible()
  await expect(
    page.locator('.workspace-connection-state').first(),
  ).toContainText(expected.unavailable)
  await expect(
    page.getByText(expected.providerUnavailable, { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.project-label-option')).toHaveCount(1)
  await assertClosedTerminal(page, locale)
}

async function assertClosedTerminal(page: Page, locale: Locale) {
  const expected = copy[locale]
  for (const name of [
    expected.connect,
    expected.reconnect,
    expected.detach,
    expected.input,
  ]) {
    await expect(page.getByRole('button', { name, exact: true })).toBeDisabled()
  }
  await expect(
    page.getByRole('textbox', { name: expected.input, exact: true }),
  ).toBeDisabled()
  await expect(
    page.getByRole('textbox', { name: expected.input, exact: true }),
  ).toHaveValue('')
  await expect(page.getByRole('log')).toHaveCount(1)
  await expect(page.getByRole('log')).toHaveText('')
  await expect(page.getByRole('log')).toHaveAttribute('aria-live', 'off')
}

async function capture(page: Page, name: string) {
  // Fail closed before retaining pixels: only the synthetic Workspace route,
  // with no output nodes or input text, may reach the explicit PNG allowlist.
  expect(new URL(page.url()).pathname).toMatch(
    /^\/workspace(?:\/aws_[cd]{32})?$/,
  )
  await expect(page.locator('input[type="password"]')).toHaveCount(0)
  await expect(page.locator('.workspace-terminal-surface')).toHaveCount(1)
  await expect(page.locator('.workspace-terminal-surface')).toHaveText('')
  await expect(page.locator('.workspace-terminal-surface > *')).toHaveCount(0)
  await expect(page.locator('.workspace-terminal-input input')).toHaveValue('')
  await assertRc9CanaryAbsent(page, PRIVATE_PROSE)
  await mkdir('test-results', { recursive: true })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: join('test-results', `ui-workspace-${name}.png`),
    fullPage: true,
  })
}

async function capturePhone(page: Page, name: string, projectName: string) {
  if (projectName === 'mobile-chromium') await capture(page, name)
}

async function openWorkspaceNavigation(page: Page, locale: Locale) {
  const expected = copy[locale]
  const menu = page.getByRole('button', { name: expected.menu, exact: true })
  if (await menu.isVisible()) await menu.click()
  await page
    .getByRole('navigation', { name: expected.navigation, exact: true })
    .getByRole('link', { name: expected.workspace, exact: true })
    .click()
  await expect(page).toHaveURL(/\/workspace$/)
  await expect(page.getByLabel(expected.project, { exact: true })).toHaveValue(
    '',
  )
}

for (const locale of ['zh-CN', 'en'] as const) {
  for (const width of [360, 390, 768, 1024, 1440]) {
    for (const colorScheme of ['light', 'dark'] as const) {
      test(`Workspace metadata ${locale} ${width} ${colorScheme}`, async ({
        browser,
        baseURL,
      }, testInfo) => {
        test.skip(
          testInfo.project.name !== 'desktop-chromium',
          'self-managed responsive context matrix runs once',
        )
        const context = await browser.newContext({
          baseURL,
          locale,
          colorScheme,
          reducedMotion: 'reduce',
          viewport: { width, height: 900 },
          isMobile: width < 900,
          hasTouch: width < 900,
        })
        try {
          const page = await context.newPage()
          const state = await fixtures(page)
          await page.goto(`/workspace/${WORKSPACE_A}`)
          await ready(page, locale)
          await assertRc9DocumentLocale(page, locale)
          await expect(
            page
              .locator('.workspace-status-card')
              .getByText(copy[locale].running, { exact: true }),
          ).toBeVisible()
          await expect(
            page.locator('.workspace-current-selection bdi').first(),
          ).toHaveText(LONG_NAME)
          await expect(
            page.locator(
              '.workspace-current-selection img, .workspace-current-selection script, .project-label-option b',
            ),
          ).toHaveCount(0)
          const surface = await page
            .locator('.workspace-terminal-surface')
            .elementHandle()
          const viewport = await page
            .locator('.workspace-terminal-frame')
            .elementHandle()
          expect(surface).not.toBeNull()
          expect(viewport).not.toBeNull()
          const geometry = await page
            .locator('.workspace-terminal-frame')
            .boundingBox()
          const disclosure = page.locator('.workspace-metadata > summary')
          await expect(disclosure).toHaveText(copy[locale].runtime)
          await assertRc9Focus(disclosure)
          await page.keyboard.press('Enter')
          await expect(page.locator('.workspace-metadata')).toHaveAttribute(
            'open',
            '',
          )
          await assertRc9TechnicalRendering(
            page
              .locator('.workspace-metadata')
              .getByText('RUNNING', { exact: true })
              .first(),
          )
          await assertRc9NoHorizontalOverflow(page)
          await page.keyboard.press('Space')
          await expect(page.locator('.workspace-metadata')).not.toHaveAttribute(
            'open',
            '',
          )
          expect(
            await surface!.evaluate(
              (node) =>
                node.isConnected &&
                node === document.querySelector('.workspace-terminal-surface'),
            ),
          ).toBe(true)
          expect(
            await viewport!.evaluate(
              (node) =>
                node.isConnected &&
                node === document.querySelector('.workspace-terminal-frame'),
            ),
          ).toBe(true)
          expect(
            (await page.locator('.workspace-terminal-frame').boundingBox())
              ?.height,
          ).toBe(geometry?.height)
          expect(
            await surface!.evaluate((node) => {
              const style = getComputedStyle(node)
              return {
                cell: style
                  .getPropertyValue('--waw-terminal-cell-width')
                  .trim(),
                line: style.lineHeight,
                padding: style.padding,
                reducedMotion: matchMedia('(prefers-reduced-motion: reduce)')
                  .matches,
              }
            }),
          ).toEqual({
            cell: '8px',
            line: '20px',
            padding: '16px',
            reducedMotion: true,
          })
          await assertRc9InteractiveTargets(page)
          await assertRc9NoHorizontalOverflow(page)
          await assertBoundaries(page, state)
          await capture(page, `ready-${locale}-${width}-${colorScheme}`)
        } finally {
          await context.close()
        }
      })
    }
  }

  test.describe(`Workspace focused ${locale}`, () => {
    test.use({
      locale,
      colorScheme: locale === 'zh-CN' ? 'dark' : 'light',
      contextOptions: { reducedMotion: 'reduce' },
    })

    test('renders loading, empty, unregistered, error, forbidden and disabled metadata states', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      state.holds.set('/api/v1/projects', hold)
      try {
        await page.goto('/workspace')
        await hold.waitUntilHeld()
        const select = page.getByLabel(expected.project, { exact: true })
        await expect(select).toBeDisabled()
        await expect(select.locator('option:checked')).toHaveText(
          expected.loadingProjects,
        )
        await capturePhone(page, `loading-${locale}`, testInfo.project.name)
        hold.release()
        await expect(select).toBeEnabled()
        state.emptyProjects = true
        await page.reload()
        await expect(select.locator('option:checked')).toHaveText(
          expected.noProjects,
        )
        await expect(select).toBeDisabled()
        await expect(
          page.getByRole('button', { name: expected.start, exact: true }),
        ).toBeDisabled()
        await capturePhone(page, `empty-${locale}`, testInfo.project.name)
        state.emptyProjects = false
        for (const mode of [
          'unregistered',
          'error',
          'forbidden',
          'disabled',
        ] as const) {
          state.mode = mode
          await page.goto(workspacePath())
          if (mode === 'unregistered') {
            await expect(
              page.getByText(expected.unregistered, { exact: true }),
            ).toBeVisible()
          } else if (mode === 'disabled') {
            await expect(
              page.getByText(expected.recovery, { exact: true }),
            ).toBeVisible()
            await expect(
              page.getByText('reconciliation_required', { exact: true }),
            ).toBeVisible()
          } else {
            const code =
              mode === 'forbidden' ? 'FORBIDDEN' : 'WAW_STATUS_UNAVAILABLE'
            await expect(
              page.locator('.workspace-selection-card [role="alert"]'),
            ).toBeVisible()
            await assertRc9TechnicalRendering(
              page.getByText(code, { exact: true }),
            )
            await expect(
              page.getByText('req_ui_workspace_synthetic', { exact: true }),
            ).toBeVisible()
          }
          await expect(
            page.getByRole('button', { name: expected.start, exact: true }),
          ).toBeDisabled()
          await expect(
            page.getByRole('button', { name: expected.stop, exact: true }),
          ).toBeDisabled()
          await assertClosedTerminal(page, locale)
          await assertRc9NoHorizontalOverflow(page)
          await assertRc9InteractiveTargets(page)
          await capturePhone(page, `${mode}-${locale}`, testInfo.project.name)
        }
        await assertBoundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('clears confirmation offline and shows revalidation before restoring current controls', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      try {
        await page.goto(workspacePath())
        await ready(page, locale)
        const surface = await page.getByRole('log').elementHandle()
        await page
          .getByRole('button', { name: expected.stop, exact: true })
          .click()
        await expect(page.getByRole('dialog')).toBeVisible()
        await page.context().setOffline(true)
        await expect(
          page.getByText(expected.stale, { exact: true }),
        ).toBeVisible()
        await expect(page.getByRole('dialog')).toBeHidden()
        await expect(page.locator('.workspace-status-card time')).toHaveCount(0)
        await expect(
          page.getByRole('button', { name: expected.stop, exact: true }),
        ).toBeDisabled()
        await capturePhone(page, `stale-${locale}`, testInfo.project.name)
        state.holds.set(statusPath(), hold)
        await page.context().setOffline(false)
        await hold.waitUntilHeld()
        await expect(
          page.getByText(expected.revalidating, { exact: true }),
        ).toBeVisible()
        await expect(
          page.getByRole('button', { name: expected.stop, exact: true }),
        ).toBeDisabled()
        await capturePhone(
          page,
          `revalidating-${locale}`,
          testInfo.project.name,
        )
        hold.release()
        await ready(page, locale)
        await expect(page.getByRole('dialog')).toBeHidden()
        expect(
          await surface!.evaluate(
            (node) =>
              node.isConnected &&
              node === document.querySelector('.workspace-terminal-surface'),
          ),
        ).toBe(true)
        await assertBoundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('keeps pending exact Stop modal, disables Cancel and ignores Escape and repeated confirmation', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      state.allowStop = true
      const expected = copy[locale]
      const path = `/api/v1/workspaces/${WORKSPACE_A}/stop`
      const hold = createRc9RouteHold()
      state.holds.set(path, hold)
      try {
        await page.goto(workspacePath())
        await ready(page, locale)
        const stop = page.getByRole('button', {
          name: expected.stop,
          exact: true,
        })
        const dialog = page.getByRole('dialog', {
          name: expected.confirmTitle,
          exact: true,
        })
        await assertRc9Focus(stop)
        await page.keyboard.press('Enter')
        await assertRc9ModalDialog(page, dialog)
        const cancel = dialog.getByRole('button', {
          name: expected.cancel,
          exact: true,
        })
        await expect(cancel).toBeFocused()
        await expect(
          dialog.getByText(WORKSPACE_A, { exact: true }),
        ).toBeVisible()
        await expect(
          dialog.getByText(GENERATION, { exact: true }),
        ).toBeVisible()
        await capturePhone(page, `dialog-${locale}`, testInfo.project.name)
        await cancel.click()
        await expect(dialog).toBeHidden()
        await expect(stop).toBeFocused()
        await stop.click()
        await page.keyboard.press('Escape')
        await expect(dialog).toBeHidden()
        await expect(stop).toBeFocused()
        expect(state.mutations).toEqual([])
        await stop.click()
        const confirm = dialog.getByRole('button', {
          name: expected.confirmStop,
          exact: true,
        })
        await confirm.evaluate((button) => {
          ;(button as HTMLButtonElement).click()
          ;(button as HTMLButtonElement).click()
        })
        await hold.waitUntilHeld()
        await expect(confirm).toBeDisabled()
        await expect(cancel).toBeDisabled()
        await page.keyboard.press('Escape')
        await cancel.evaluate((button) => (button as HTMLButtonElement).click())
        await expect(dialog).toBeVisible()
        expect(state.mutations).toEqual([
          {
            path: `POST ${path}`,
            body: { generation: GENERATION },
            csrf: 'synthetic-ui-workspace-csrf-a',
          },
        ])
        await capturePhone(
          page,
          `pending-stop-${locale}`,
          testInfo.project.name,
        )
        hold.release()
        await expect(dialog).toBeHidden()
        await expect(
          page.getByText(expected.stoppedNotice, { exact: true }),
        ).toBeVisible()
        await expect(
          page.getByRole('button', { name: expected.start, exact: true }),
        ).toBeEnabled()
        await expect(stop).toBeDisabled()
        await assertClosedTerminal(page, locale)
        await assertBoundaries(page, state, 1)
      } finally {
        hold.dispose()
      }
    })

    test('Back and Forward re-enter the real route and ignore a previous pending Stop reply', async ({
      page,
    }) => {
      const state = await fixtures(page)
      state.allowStop = true
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      const path = `/api/v1/workspaces/${WORKSPACE_A}/stop`
      try {
        await page.goto(workspacePath())
        await ready(page, locale)
        await openWorkspaceNavigation(page, locale)
        await page
          .getByLabel(expected.project, { exact: true })
          .selectOption(PROJECT_B)
        await page
          .getByLabel('AgentType', { exact: true })
          .selectOption('codex')
        await ready(page, locale, PROJECT_B)
        await page.locator(`.work-tabs a[href="${workspacePath()}"]`).click()
        await ready(page, locale)
        state.holds.set(path, hold)
        await page
          .getByRole('button', { name: expected.stop, exact: true })
          .click()
        await page
          .getByRole('dialog')
          .getByRole('button', { name: expected.confirmStop, exact: true })
          .click()
        await hold.waitUntilHeld()
        await page.goBack()
        await expect(page).toHaveURL(/\/workspace$/)
        await expect(page.getByRole('dialog')).toBeHidden()
        await page
          .getByLabel(expected.project, { exact: true })
          .selectOption(PROJECT_B)
        await page
          .getByLabel('AgentType', { exact: true })
          .selectOption('codex')
        await ready(page, locale, PROJECT_B)
        hold.release()
        await expect.poll(() => state.responses.includes(path)).toBe(true)
        await ready(page, locale, PROJECT_B)
        await expect(
          page.getByText(expected.stoppedNotice, { exact: true }),
        ).toHaveCount(0)
        await expect(page.getByText(WORKSPACE_A, { exact: true })).toHaveCount(
          0,
        )
        await page.goForward()
        await expect(page).toHaveURL(workspacePath())
        await expect(
          page.getByLabel(expected.project, { exact: true }),
        ).toHaveValue(PROJECT_A)
        await expect(
          page.getByRole('button', { name: expected.start, exact: true }),
        ).toBeEnabled()
        await assertRc9Title(page, `${expected.title} · Kebui`)
        await expect(page.getByRole('dialog')).toBeHidden()
        await expect(
          page.getByText(expected.stoppedNotice, { exact: true }),
        ).toHaveCount(0)
        await assertBoundaries(page, state, 1)
      } finally {
        hold.dispose()
      }
    })

    test('keeps Project and AgentType selection current when old metadata arrives late', async ({
      page,
    }) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      state.holds.set(listPath(), hold)
      try {
        await page.goto('/workspace')
        const projectSelect = page.getByLabel(expected.project, { exact: true })
        await expect(projectSelect).toBeEnabled()
        await page
          .getByLabel('AgentType', { exact: true })
          .selectOption('codex')
        await projectSelect.selectOption(PROJECT_A)
        await hold.waitUntilHeld()
        await expect(
          page.getByText(expected.loadingWorkspace, { exact: true }),
        ).toBeVisible()
        await projectSelect.selectOption(PROJECT_B)
        await ready(page, locale, PROJECT_B)
        hold.release()
        await expect.poll(() => state.responses.includes(listPath())).toBe(true)
        await ready(page, locale, PROJECT_B)
        await expect(page.getByText(WORKSPACE_A, { exact: true })).toHaveCount(
          0,
        )
        expect(state.reads).not.toContain(statusPath())
        await page
          .getByLabel('AgentType', { exact: true })
          .selectOption('claude')
        await expect(
          page.getByText(expected.unregistered, { exact: true }),
        ).toBeVisible()
        await expect(
          page.getByRole('button', { name: expected.stop, exact: true }),
        ).toBeDisabled()
        await page
          .getByLabel('AgentType', { exact: true })
          .selectOption('codex')
        await ready(page, locale, PROJECT_B)
        await expect(page.getByRole('dialog')).toBeHidden()
        await assertBoundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('removes an old Stop confirmation on session expiry and re-enters with fresh metadata', async ({
      page,
    }) => {
      const state = await fixtures(page)
      state.allowStop = true
      state.stopUnauthorized = true
      const expected = copy[locale]
      await page.goto(workspacePath())
      await ready(page, locale)
      await page
        .getByRole('button', { name: expected.stop, exact: true })
        .click()
      await page
        .getByRole('dialog')
        .getByRole('button', { name: expected.confirmStop, exact: true })
        .click()
      await expect(page).toHaveURL(/\/login$/)
      await expect(page.locator('input[type="password"]')).toBeVisible()
      await expect(page.locator('.workspace-page, .work-tabs')).toHaveCount(0)
      state.session = 'b'
      state.stopUnauthorized = false
      await page.goto(workspacePath())
      await ready(page, locale)
      await expect(page.getByRole('dialog')).toBeHidden()
      await expect(
        page.getByText(expected.stoppedNotice, { exact: true }),
      ).toHaveCount(0)
      expect(
        state.reads.filter((path) => path === '/api/v1/auth/me'),
      ).toHaveLength(2)
      expect(state.mutations[0]).toMatchObject({
        body: { generation: GENERATION },
        csrf: 'synthetic-ui-workspace-csrf-a',
      })
      await assertBoundaries(page, state, 1)
    })
  })
}

test('captures normal-name Chinese previews alongside the adversarial matrix', async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'ordinary preview context matrix runs once',
  )
  for (const [width, colorScheme] of [
    [1440, 'light'],
    [390, 'dark'],
  ] as const) {
    const context = await browser.newContext({
      baseURL,
      locale: 'zh-CN',
      colorScheme,
      reducedMotion: 'reduce',
      viewport: { width, height: 900 },
      isMobile: width < 900,
      hasTouch: width < 900,
    })
    try {
      const page = await context.newPage()
      const state = await fixtures(page, true)
      await page.goto(workspacePath())
      await ready(page, 'zh-CN')
      await expect(page.locator('.workspace-current-selection')).toContainText(
        'AgentBox 工作台',
      )
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
      await assertBoundaries(page, state)
      await capture(page, `preview-zh-CN-${width}-${colorScheme}`)
    } finally {
      await context.close()
    }
  }
})
