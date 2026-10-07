import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9InteractiveTargets,
  assertRc9ModalDialog,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
} from './rc9-assertions'
import { createRc9RouteHold, type Rc9RouteHold } from './rc9-fixtures'

// Actual App + HTTP metadata only. No product hook, controller, native adapter
// or capability injection. Pair/output are rejected even if accidentally read.
// Sensitive functional coverage lives in agent-management-auth-scope.spec.ts.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const MARKER = 'ui-agent-management-fixture'
const PRIVATE_PROSE = 'synthetic-management-server-prose-must-not-render'
const PROJECT_A = `prj_${'a'.repeat(32)}`
const PROJECT_B = `prj_${'b'.repeat(32)}`
const INERT_NAME = '<img src=x onerror=alert(1)> & "Project"'
const LONG_NAME = '工作台项目与 Unicode 🌍 '.repeat(10)
const CODEX_PATH = `/fixture/${'long-metadata-directory/'.repeat(7)}bin/codex`
const CSRF = 'synthetic-management-metadata-csrf'
const CODEX_API = '/api/v1/codex/status'
const CLAUDE_API = '/api/v1/claude'
const SESSIONS_API = '/api/v1/claude/sessions'

type Agent = 'codex' | 'claude'
type CodexMode =
  'ready' | 'error' | 'unknown' | 'unsupported' | 'conflict' | 'unauthenticated'
type ClaudeMode =
  'ready' | 'empty' | 'error' | 'tmux' | 'needs-interaction' | 'long-project'

const copy = {
  en: {
    codexLoading: 'Detecting Codex safely…',
    codexError: 'Codex status unavailable',
    codexRefresh: 'Refresh Codex status',
    lifecycle: 'Lifecycle',
    start: 'Start Remote',
    stop: 'Stop Remote',
    starting: 'Starting…',
    pair: 'Pair New Device',
    confirm: 'Generate a new temporary pairing code?',
    generate: 'Generate Code',
    cancel: 'Cancel',
    unknown: 'Unknown',
    unsupported: 'Unsupported',
    conflict: 'Conflict',
    unauthenticated: 'Unauthenticated',
    running: 'Running',
    stopped: 'Stopped',
    claudeLoading: 'Inspecting Claude and managed sessions…',
    claudeError: 'Claude status unavailable',
    refresh: 'Refresh',
    empty: 'No configured projects',
    unavailable: 'Unavailable',
    interaction: 'Needs Interaction',
    trust: 'Requires user confirmation',
    startSession: 'Start Session',
    stopSession: 'Stop Session',
    copyAttach: 'Copy attach command',
    copied: 'Copied',
    reveal: 'Reveal',
    actionFailed: 'Claude action failed',
    menu: 'Open navigation',
  },
  'zh-CN': {
    codexLoading: '正在安全检测 Codex…',
    codexError: '无法获取 Codex 状态',
    codexRefresh: '刷新 Codex 状态',
    lifecycle: '生命周期',
    start: '启动 Remote',
    stop: '停止 Remote',
    starting: '正在启动…',
    pair: '配对新设备',
    confirm: '生成新的临时配对码？',
    generate: '生成配对码',
    cancel: '取消',
    unknown: '未知',
    unsupported: '不支持',
    conflict: '冲突',
    unauthenticated: '未验证',
    running: '运行中',
    stopped: '已停止',
    claudeLoading: '正在检查 Claude 和托管会话…',
    claudeError: 'Claude 状态暂不可用',
    refresh: '刷新',
    empty: '没有已配置的 Project',
    unavailable: '不可用',
    interaction: '需要交互',
    trust: '需要用户确认',
    startSession: '启动会话',
    stopSession: '停止会话',
    copyAttach: '复制 attach command',
    copied: '已复制',
    reveal: '显示',
    actionFailed: 'Claude 操作失败',
    menu: '打开导航',
  },
} as const

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_ui_management_synthetic', data }
}
function failure(code: string) {
  return {
    api_version: 'v1',
    request_id: 'req_ui_management_synthetic',
    error: {
      code,
      category: 'unavailable',
      message: PRIVATE_PROSE,
      retryable: false,
      details: {},
    },
  }
}

// Exported only for the source-only production-decoder validation command.
// These are the exact payload builders used by the HTTP fixture below.
export function codexMetadata(
  mode: CodexMode = 'ready',
  representative = false,
  running = false,
) {
  const capability =
    mode === 'unknown'
      ? 'unknown'
      : mode === 'unsupported' || mode === 'conflict'
        ? 'unsupported'
        : 'supported'
  return envelope({
    installed: true,
    version: mode === 'unknown' ? null : '1.ui.fixture',
    selected_executable:
      mode === 'unknown'
        ? null
        : representative
          ? '/fixture/bin/codex'
          : CODEX_PATH,
    alternatives:
      mode === 'conflict'
        ? ['/fixture/standalone/codex', '/fixture/npm/codex']
        : [],
    installation_type:
      mode === 'unknown'
        ? 'unknown'
        : mode === 'conflict'
          ? 'conflict'
          : 'standalone',
    conflict_detected: mode === 'conflict',
    authentication:
      mode === 'unknown'
        ? 'unknown'
        : mode === 'unauthenticated'
          ? 'unauthenticated'
          : 'authenticated',
    capabilities: {
      remote_control: capability,
      start: capability,
      stop: capability,
      pair: capability,
      status: 'unsupported',
    },
    remote_state:
      mode === 'unknown' || mode === 'conflict'
        ? 'unknown'
        : running
          ? 'running'
          : 'stopped',
    remote_confidence:
      mode === 'unknown' || mode === 'conflict' ? 'unknown' : 'reported',
    diagnostics: [
      {
        code:
          mode === 'conflict'
            ? 'CODEX_INSTALLATION_CONFLICT'
            : 'CODEX_REMOTE_STATUS_UNSUPPORTED',
        severity: mode === 'conflict' ? 'warning' : 'info',
        summary: PRIVATE_PROSE,
        remediation: PRIVATE_PROSE,
      },
    ],
  })
}

export function claudeMetadata(
  mode: ClaudeMode = 'ready',
  representative = false,
) {
  const sessions = [
    {
      project_id: PROJECT_A,
      display_name: representative ? 'AgentBox 工作台' : INERT_NAME,
      state: 'stopped',
      managed: true,
      session_name: `agentbox-claude-${PROJECT_A}-fixture`,
      attach_command: `tmux attach-session -t =agentbox-claude-${PROJECT_A}-fixture`,
      workspace_state: 'unknown',
      tmux_running: false,
      remote_readiness: 'unknown',
    },
    {
      project_id: PROJECT_B,
      display_name: representative ? '文档与工具' : LONG_NAME,
      state: mode === 'needs-interaction' ? 'needs_interaction' : 'running',
      managed: true,
      session_name: `agentbox-claude-${PROJECT_B}-${mode === 'long-project' ? 'metadata-only-name-'.repeat(12) : 'fixture'}`,
      attach_command: `tmux attach-session -t =agentbox-claude-${PROJECT_B}-${mode === 'long-project' ? 'metadata-only-name-'.repeat(12) : 'fixture'}`,
      workspace_state:
        mode === 'needs-interaction' ? 'requires_user_confirmation' : 'unknown',
      tmux_running: true,
      remote_readiness: 'unknown',
    },
  ]
  return {
    status: envelope({
      installed: true,
      version: '1.ui.fixture',
      authentication: 'unknown',
      capabilities: {
        remote_control: 'supported',
        remote_start: 'supported',
        version: 'supported',
      },
      tmux_installed: mode !== 'tmux',
      tmux_version: mode === 'tmux' ? null : '3.ui.fixture',
      managed_sessions: mode === 'empty' || mode === 'tmux' ? 0 : 1,
      unmanaged_sessions: 2,
      workspace_interaction_warnings: mode === 'needs-interaction' ? 1 : 0,
      diagnostics: [
        {
          code: 'CLAUDE_REMOTE_READINESS_UNKNOWN',
          severity: 'info',
          summary: PRIVATE_PROSE,
          remediation: PRIVATE_PROSE,
        },
      ],
    }),
    sessions: envelope({
      sessions:
        mode === 'empty'
          ? []
          : mode === 'tmux'
            ? sessions.map((session) => ({
                ...session,
                state: 'stopped',
                tmux_running: false,
              }))
            : sessions,
    }),
  }
}

async function fixtures(page: Page, representative = false) {
  const state = {
    codexMode: 'ready' as CodexMode,
    claudeMode: 'ready' as ClaudeMode,
    running: false,
    representative,
    sessionOverrides: new Map<string, Record<string, unknown>>(),
    mutationErrors: new Set<string>(),
    holds: new Map<string, Rc9RouteHold>(),
    requests: [] as Array<{
      path: string
      method: string
      csrf: string | null
    }>,
    completed: [] as string[],
    unexpected: [] as string[],
    errors: [] as string[],
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  page.on('websocket', () => state.unexpected.push('WebSocket connection'))
  const baseOrigin = new URL(process.env.PLAYWRIGHT_BASE_URL!).origin
  page.on('request', (request) => {
    const url = new URL(request.url())
    const metadata = /^\/(?:api\/|healthz$|readyz$)/.test(url.pathname)
    const document =
      request.resourceType() === 'document' &&
      /^\/(?:codex|claude)$/.test(url.pathname)
    const asset =
      ['script', 'stylesheet', 'font', 'image', 'other'].includes(
        request.resourceType(),
      ) &&
      /^\/(?:assets\/|src\/|node_modules\/|@vite\/|@react-refresh$|favicon\.ico$)/.test(
        url.pathname,
      )
    if (url.origin !== baseOrigin || (!metadata && !document && !asset))
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
  })
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    // Defense in depth: a foreign URL must never receive synthetic auth or
    // sensitive fixture content, even if routing precedence changes later.
    if (url.origin !== baseOrigin) {
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
      return
    }
    const path = `${url.pathname}${url.search}`
    const method = request.method()
    state.requests.push({
      path,
      method,
      csrf: request.headers()['x-csrf-token'] ?? null,
    })
    const metadata = claudeMetadata(state.claudeMode, representative)
    const list = metadata.sessions.data as {
      sessions: Array<Record<string, unknown>>
    }
    const sessions = list.sessions.map((session) => ({
      ...session,
      ...state.sessionOverrides.get(String(session.project_id)),
    }))
    const responses: Record<string, unknown> = {
      '/healthz': { status: 'ok' },
      '/api/v1/auth/me': envelope({
        user: { id: 'adm_ui_management', username: MARKER },
        session: {
          id: 'ses_ui_management_metadata',
          expires_at: '2030-01-01T00:00:00Z',
        },
        csrf_token: CSRF,
      }),
      [CODEX_API]: codexMetadata(
        state.codexMode,
        representative,
        state.running,
      ),
      [CLAUDE_API]: metadata.status,
      [SESSIONS_API]: envelope({ sessions }),
    }
    let status = 200
    let body: unknown
    const codexAction = /^\/api\/v1\/codex\/remote\/(start|stop)$/.exec(path)
    const claudeAction =
      /^\/api\/v1\/claude\/sessions\/(prj_[ab]{32})\/(start|stop)$/.exec(path)
    if (method === 'GET' && path in responses) {
      body = responses[path]
      if (
        (path === CODEX_API && state.codexMode === 'error') ||
        (path === CLAUDE_API && state.claudeMode === 'error')
      ) {
        status = 503
        body = failure(
          path === CODEX_API
            ? 'CODEX_STATUS_UNAVAILABLE'
            : 'CLAUDE_RUNTIME_UNAVAILABLE',
        )
      }
    } else if (
      method === 'POST' &&
      (codexAction || claudeAction) &&
      request.headers()['x-csrf-token'] === CSRF
    ) {
      if (state.mutationErrors.has(path)) {
        status = 503
        body = failure(
          codexAction ? 'CODEX_ACTION_FAILED' : 'CLAUDE_ACTION_FAILED',
        )
      } else if (codexAction) {
        state.running = codexAction[1] === 'start'
        body = envelope({
          outcome: state.running ? 'started' : 'stopped',
          remote_state: state.running ? 'running' : 'stopped',
        })
      } else {
        const [, projectId, operation] = claudeAction!
        const session = sessions.find((item) => item.project_id === projectId)!
        const running = operation === 'start'
        const next = {
          ...session,
          state: running ? 'running' : 'stopped',
          tmux_running: running,
        }
        state.sessionOverrides.set(projectId, next)
        body = envelope({
          outcome: running ? 'started' : 'stopped',
          session: next,
        })
      }
    } else {
      state.unexpected.push(`${method} ${path}`)
      status = 500
      body = failure('UNEXPECTED_REQUEST')
    }
    // Snapshot before awaiting so late metadata cannot acquire a new owner/value.
    const response = {
      status,
      body: JSON.stringify(body),
      contentType: 'application/json',
      headers: { 'Cache-Control': 'no-store' },
    }
    const hold = state.holds.get(path)
    state.holds.delete(path)
    if (hold) await hold.hold()
    await route.fulfill(response)
    state.completed.push(path)
  })
  // Playwright applies the last registered route first. Guard every request
  // before falling back to the narrower API fixture or own-origin assets.
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== baseOrigin) {
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
      return
    }
    await route.fallback()
  })
  return state
}
type Fixtures = Awaited<ReturnType<typeof fixtures>>

async function boundaries(page: Page, state: Fixtures) {
  expect(state.unexpected).toEqual([])
  expect(state.errors).toEqual([])
  expect(
    state.requests.filter(({ path }) =>
      /\/(?:pair-codes|output)(?:[/?]|$)/.test(path),
    ),
  ).toEqual([])
  await expect(page.locator('.pair-secret, .sensitive-output pre')).toHaveCount(
    0,
  )
  await assertRc9CanaryAbsent(page, PRIVATE_PROSE)
  expect(
    await page.evaluate(() => ({
      local: Object.entries(localStorage),
      session: Object.entries(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] })
}

async function ready(page: Page, agent: Agent) {
  await expect(
    page.getByRole('heading', {
      name: agent === 'codex' ? 'Codex' : 'Claude',
      level: 1,
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.locator(`.${agent}-page`).getByText('1.ui.fixture', { exact: true }),
  ).toBeVisible()
  if (agent === 'claude')
    await expect(page.locator('.claude-session-card')).toHaveCount(2)
}

async function layout(page: Page, agent: Agent, width: number) {
  const cards = page.locator(
    agent === 'codex'
      ? '.codex-layout > .runtime-card'
      : '.claude-runtime-grid > .runtime-card',
  )
  const first = await cards.nth(0).boundingBox()
  const second = await cards.nth(1).boundingBox()
  expect(first).not.toBeNull()
  expect(second).not.toBeNull()
  if (width >= 1024) {
    expect(Math.abs(first!.y - second!.y)).toBeLessThanOrEqual(1)
    expect(second!.x).toBeGreaterThanOrEqual(first!.x + first!.width)
  } else {
    expect(second!.y).toBeGreaterThanOrEqual(first!.y + first!.height)
  }
  // A page can fit its viewport while nested fact grids squeeze their own
  // labels/values. Check the actual rendered cells at every matrix width.
  const facts = await page
    .locator(`.${agent}-page .runtime-details > div`)
    .evaluateAll((tiles) =>
      tiles.map((tile) => {
        const bounds = (element: Element | null) => {
          if (!element) return null
          const rect = element.getBoundingClientRect()
          return {
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
          }
        }
        return {
          tile: bounds(tile)!,
          label: bounds(tile.querySelector(':scope > dt')),
          value: bounds(tile.querySelector(':scope > dd')),
        }
      }),
    )
  expect(facts.length).toBeGreaterThan(0)
  for (let index = 0; index < facts.length; index += 1) {
    const fact = facts[index]
    expect(fact.label, `fact ${index} label`).not.toBeNull()
    expect(fact.value, `fact ${index} value`).not.toBeNull()
    for (const [name, item] of [
      ['label', fact.label!],
      ['value', fact.value!],
    ] as const) {
      expect(item.left, `fact ${index} ${name} left`).toBeGreaterThanOrEqual(
        fact.tile.left - 1,
      )
      expect(item.right, `fact ${index} ${name} right`).toBeLessThanOrEqual(
        fact.tile.right + 1,
      )
      expect(item.top, `fact ${index} ${name} top`).toBeGreaterThanOrEqual(
        fact.tile.top - 1,
      )
      expect(item.bottom, `fact ${index} ${name} bottom`).toBeLessThanOrEqual(
        fact.tile.bottom + 1,
      )
      expect(
        item.scrollWidth,
        `fact ${index} ${name} text overflow`,
      ).toBeLessThanOrEqual(item.clientWidth + 1)
    }
    expect(
      fact.value!.top,
      `fact ${index} value follows its label`,
    ).toBeGreaterThanOrEqual(fact.label!.bottom - 1)
  }
  await assertRc9NoHorizontalOverflow(page)
}

async function capture(
  page: Page,
  state: Fixtures,
  agent: Agent,
  name: string,
) {
  const url = new URL(page.url())
  expect(`${url.pathname}${url.search}${url.hash}`).toBe(`/${agent}`)
  await expect(page.locator('.app-frame')).toContainText(MARKER)
  await expect(
    page.locator(
      'input[type="password"], textarea, pre, [contenteditable="true"]',
    ),
  ).toHaveCount(0)
  expect(
    await page
      .locator('input')
      .evaluateAll((inputs) =>
        inputs.every((input) => (input as HTMLInputElement).value === ''),
      ),
  ).toBe(true)
  await boundaries(page, state)
  await mkdir('test-results', { recursive: true })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: join('test-results', `ui-agent-management-${agent}-${name}.png`),
    fullPage: true,
  })
}
async function capturePhone(
  page: Page,
  state: Fixtures,
  agent: Agent,
  name: string,
  project: string,
) {
  if (project === 'mobile-chromium') await capture(page, state, agent, name)
}

for (const agent of ['codex', 'claude'] as const) {
  for (const locale of ['zh-CN', 'en'] as const) {
    for (const width of [360, 390, 768, 1024, 1440]) {
      for (const colorScheme of ['light', 'dark'] as const) {
        test(`${agent} metadata ${locale} ${width} ${colorScheme}`, async ({
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
            await page.goto(`/${agent}`)
            await ready(page, agent)
            await assertRc9DocumentLocale(page, locale)
            const refresh = page.getByRole('button', {
              name:
                agent === 'codex'
                  ? copy[locale].codexRefresh
                  : copy[locale].refresh,
              exact: true,
            })
            await assertRc9Focus(refresh)
            if (agent === 'codex') {
              await assertRc9TechnicalRendering(
                page.getByText(CODEX_PATH, { exact: true }),
              )
              await expect(
                page.getByRole('button', {
                  name: copy[locale].start,
                  exact: true,
                }),
              ).toBeEnabled()
              await expect(
                page.getByRole('button', {
                  name: copy[locale].stop,
                  exact: true,
                }),
              ).toBeDisabled()
              await expect(
                page.getByRole('button', {
                  name: copy[locale].pair,
                  exact: true,
                }),
              ).toBeEnabled()
            } else {
              await expect(
                page.getByRole('heading', { name: INERT_NAME, exact: true }),
              ).toBeVisible()
              await expect(
                page.getByRole('heading', {
                  name: LONG_NAME.trim(),
                  exact: true,
                }),
              ).toBeVisible()
              await expect(
                page.locator(
                  '.claude-session-card img, .claude-session-card script, .claude-session-card a',
                ),
              ).toHaveCount(0)
              await expect(
                page
                  .locator('.claude-session-card')
                  .first()
                  .getByRole('button', {
                    name: copy[locale].reveal,
                    exact: true,
                  }),
              ).toBeDisabled()
            }
            await assertRc9InteractiveTargets(page)
            await layout(page, agent, width)
            await capture(
              page,
              state,
              agent,
              `ready-${locale}-${width}-${colorScheme}`,
            )
          } finally {
            await context.close()
          }
        })
      }
    }
  }
}

for (const locale of ['zh-CN', 'en'] as const) {
  test.describe(`Agent management metadata interactions ${locale}`, () => {
    test.use({ locale, contextOptions: { reducedMotion: 'reduce' } })

    test('Codex loading, error and conservative capability/authentication states', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      state.holds.set(CODEX_API, hold)
      try {
        await page.goto('/codex')
        await hold.waitUntilHeld()
        await expect(
          page.getByText(expected.codexLoading, { exact: true }),
        ).toBeVisible()
        await capturePhone(
          page,
          state,
          'codex',
          `loading-${locale}`,
          testInfo.project.name,
        )
        hold.release()
        await ready(page, 'codex')
        for (const mode of [
          'error',
          'unknown',
          'unsupported',
          'conflict',
          'unauthenticated',
        ] as const) {
          state.codexMode = mode
          await page.reload()
          if (mode === 'error') {
            await expect(
              page.getByRole('heading', {
                name: expected.codexError,
                exact: true,
              }),
            ).toBeVisible()
            await expect(page.locator('.codex-layout')).toHaveCount(0)
            await assertRc9TechnicalRendering(
              page.getByText('CODEX_STATUS_UNAVAILABLE', { exact: true }),
            )
          } else {
            await expect(
              page
                .locator('.codex-page')
                .getByText(expected[mode], { exact: true })
                .first(),
            ).toBeVisible()
            await expect(
              page.getByRole('button', { name: expected.pair, exact: true }),
            ).toBeDisabled()
            if (mode !== 'unauthenticated') {
              await expect(
                page.getByRole('button', { name: expected.start, exact: true }),
              ).toBeDisabled()
              await expect(
                page.getByRole('button', { name: expected.stop, exact: true }),
              ).toBeDisabled()
            }
            // The UI does not infer an authentication requirement for Remote start.
            if (mode === 'unauthenticated')
              await expect(
                page.getByRole('button', { name: expected.start, exact: true }),
              ).toBeEnabled()
          }
          await assertRc9NoHorizontalOverflow(page)
          await capturePhone(
            page,
            state,
            'codex',
            `${mode}-${locale}`,
            testInfo.project.name,
          )
        }
        await boundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('Pair confirmation is inert, keyboard trapped, cancellable and discarded by Back', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      await page.goto('/claude')
      await ready(page, 'claude')
      const link = page.locator('.primary-nav a[href="/codex"]:visible')
      if ((await link.count()) === 0)
        await page
          .getByRole('button', { name: expected.menu, exact: true })
          .click()
      await page.locator('.primary-nav a[href="/codex"]:visible').click()
      await ready(page, 'codex')
      const trigger = page.getByRole('button', {
        name: expected.pair,
        exact: true,
      })
      await assertRc9Focus(trigger)
      await page.keyboard.press('Enter')
      const dialog = page.getByRole('dialog', { name: expected.confirm })
      const generate = dialog.getByRole('button', {
        name: expected.generate,
        exact: true,
      })
      const cancel = dialog.getByRole('button', {
        name: expected.cancel,
        exact: true,
      })
      await assertRc9ModalDialog(page, dialog)
      await expect(page.locator('.codex-page[inert]')).toHaveCount(1)
      await expect(generate).toBeFocused()
      await page.keyboard.press('Shift+Tab')
      await expect(cancel).toBeFocused()
      await page.keyboard.press('Tab')
      await expect(generate).toBeFocused()
      await assertRc9Focus(cancel)
      await assertRc9InteractiveTargets(page)
      await capturePhone(
        page,
        state,
        'codex',
        `confirmation-${locale}`,
        testInfo.project.name,
      )
      await cancel.click()
      await expect(dialog).toHaveCount(0)
      await expect(trigger).toBeFocused()
      await trigger.click()
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(trigger).toBeFocused()
      await trigger.click()
      await page.goBack()
      await expect(page).toHaveURL('/claude')
      await ready(page, 'claude')
      await expect(dialog).toHaveCount(0)
      await page.goForward()
      await ready(page, 'codex')
      await expect(dialog).toHaveCount(0)
      await boundaries(page, state)
    })

    test('Codex existing start/stop, pending deduplication, failure and explicit refresh', async ({
      page,
    }) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const path = '/api/v1/codex/remote/start'
      const hold = createRc9RouteHold()
      try {
        await page.goto('/codex')
        await ready(page, 'codex')
        state.holds.set(path, hold)
        await page
          .getByRole('button', { name: expected.start, exact: true })
          .evaluate((button) => {
            ;(button as HTMLButtonElement).click()
            ;(button as HTMLButtonElement).click()
          })
        await hold.waitUntilHeld()
        for (const name of [
          expected.starting,
          expected.stop,
          expected.pair,
          expected.codexRefresh,
        ])
          await expect(
            page.getByRole('button', { name, exact: true }),
          ).toBeDisabled()
        hold.release()
        await expect(
          page
            .getByRole('region', { name: expected.lifecycle })
            .getByText(expected.running, { exact: true }),
        ).toBeVisible()
        expect(
          state.requests.filter((request) => request.path === path),
        ).toEqual([{ path, method: 'POST', csrf: CSRF }])
        await page
          .getByRole('button', { name: expected.stop, exact: true })
          .click()
        await expect(
          page
            .getByRole('region', { name: expected.lifecycle })
            .getByText(expected.stopped, { exact: true }),
        ).toBeVisible()
        state.mutationErrors.add(path)
        await page
          .getByRole('button', { name: expected.start, exact: true })
          .click()
        await expect(
          page.getByText('CODEX_ACTION_FAILED', { exact: true }),
        ).toBeVisible()
        await expect(
          page.getByRole('button', { name: expected.start, exact: true }),
        ).toBeEnabled()
        const count = state.requests.filter(
          (request) => request.path === CODEX_API,
        ).length
        await page
          .getByRole('button', { name: expected.codexRefresh, exact: true })
          .click()
        await ready(page, 'codex')
        expect(
          state.requests.filter((request) => request.path === CODEX_API),
        ).toHaveLength(count + 1)
        await boundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('Claude loading, empty, error, tmux unavailable, interaction and long metadata', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      state.holds.set(CLAUDE_API, hold)
      try {
        await page.goto('/claude')
        await hold.waitUntilHeld()
        await expect(
          page.getByText(expected.claudeLoading, { exact: true }),
        ).toBeVisible()
        hold.release()
        await ready(page, 'claude')
        for (const mode of [
          'empty',
          'error',
          'tmux',
          'needs-interaction',
          'long-project',
        ] as const) {
          state.claudeMode = mode
          await page
            .getByRole('button', { name: expected.refresh, exact: true })
            .click()
          if (mode === 'empty' || mode === 'error') {
            await expect(
              page.getByRole('heading', {
                name: mode === 'empty' ? expected.empty : expected.claudeError,
                exact: true,
              }),
            ).toBeVisible()
            await expect(page.locator('.claude-session-card')).toHaveCount(0)
          } else {
            await ready(page, 'claude')
            if (mode === 'tmux')
              await expect(
                page
                  .locator('.claude-runtime-grid')
                  .getByText(expected.unavailable, { exact: true }),
              ).toBeVisible()
            if (mode === 'needs-interaction') {
              await expect(
                page
                  .locator('.claude-session-card')
                  .last()
                  .getByText(expected.interaction, { exact: true }),
              ).toBeVisible()
              await expect(
                page
                  .locator('.claude-session-card')
                  .last()
                  .getByText(expected.trust, { exact: true }),
              ).toBeVisible()
              await expect(page.locator('.interaction-notice')).toBeVisible()
            }
            if (mode === 'long-project')
              await expect(page.locator('.attach-box').last()).toContainText(
                'metadata-only-name-'.repeat(12),
              )
          }
          await assertRc9NoHorizontalOverflow(page)
          await capturePhone(
            page,
            state,
            'claude',
            `${mode}-${locale}`,
            testInfo.project.name,
          )
        }
        await boundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('Claude attach copy and same-Project guards preserve other Project action/error ownership', async ({
      page,
    }) => {
      await page.addInitScript(() =>
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: {
            writeText: async (value: string) => {
              ;(window as Window & { __attachCopy?: string }).__attachCopy =
                value
            },
          },
        }),
      )
      const state = await fixtures(page)
      const expected = copy[locale]
      const path = `${SESSIONS_API}/${PROJECT_A}/start`
      const otherPath = `${SESSIONS_API}/${PROJECT_B}/stop`
      const hold = createRc9RouteHold()
      try {
        await page.goto('/claude')
        await ready(page, 'claude')
        const first = page.locator('.claude-session-card').first()
        const second = page.locator('.claude-session-card').last()
        expect(
          await page.evaluate(
            () =>
              (window as Window & { __attachCopy?: string }).__attachCopy ??
              null,
          ),
        ).toBeNull()
        await assertRc9Focus(
          first.getByRole('button', { name: expected.copyAttach, exact: true }),
        )
        await first
          .getByRole('button', { name: expected.copyAttach, exact: true })
          .click()
        await expect(
          first.getByRole('button', { name: expected.copied, exact: true }),
        ).toBeVisible()
        expect(
          await page.evaluate(
            () => (window as Window & { __attachCopy?: string }).__attachCopy,
          ),
        ).toBe(`tmux attach-session -t =agentbox-claude-${PROJECT_A}-fixture`)
        state.holds.set(path, hold)
        state.mutationErrors.add(path)
        await first
          .getByRole('button', { name: expected.startSession, exact: true })
          .evaluate((button) => {
            ;(button as HTMLButtonElement).click()
            ;(button as HTMLButtonElement).click()
          })
        await hold.waitUntilHeld()
        await expect(
          page.getByRole('button', { name: expected.refresh, exact: true }),
        ).toBeDisabled()
        await expect(
          first.getByRole('button', { name: expected.starting, exact: true }),
        ).toBeDisabled()
        await expect(
          first.getByRole('button', { name: expected.reveal, exact: true }),
        ).toBeDisabled()
        await expect(
          second.getByRole('button', {
            name: expected.stopSession,
            exact: true,
          }),
        ).toBeEnabled()
        await second
          .getByRole('button', { name: expected.stopSession, exact: true })
          .click()
        await expect(
          second.getByRole('button', {
            name: expected.startSession,
            exact: true,
          }),
        ).toBeEnabled()
        hold.release()
        await expect(
          first.getByRole('heading', {
            name: expected.actionFailed,
            exact: true,
          }),
        ).toBeVisible()
        await expect(second.locator('.claude-action-error')).toHaveCount(0)
        expect(
          state.requests.filter((request) => request.path === path),
        ).toEqual([{ path, method: 'POST', csrf: CSRF }])
        expect(
          state.requests.filter((request) => request.path === otherPath),
        ).toEqual([{ path: otherPath, method: 'POST', csrf: CSRF }])
        state.mutationErrors.delete(path)
        await first
          .getByRole('button', { name: expected.startSession, exact: true })
          .click()
        await expect(
          first.getByRole('button', {
            name: expected.stopSession,
            exact: true,
          }),
        ).toBeEnabled()
        await expect(first.locator('.claude-action-error')).toHaveCount(0)
        await boundaries(page, state)
      } finally {
        hold.dispose()
      }
    })
  })
}

test('normal-name Chinese desktop and mobile management previews', async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'ordinary preview context matrix runs once',
  )
  for (const agent of ['codex', 'claude'] as const) {
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
        await page.goto(`/${agent}`)
        await ready(page, agent)
        await layout(page, agent, width)
        await assertRc9InteractiveTargets(page)
        await capture(
          page,
          state,
          agent,
          `preview-zh-CN-${width}-${colorScheme}`,
        )
      } finally {
        await context.close()
      }
    }
  }
})
