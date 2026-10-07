import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
  assertRc9Title,
} from './rc9-assertions'
import { createRc9RouteHold, type Rc9RouteHold } from './rc9-fixtures'

// Real App + same-origin synthetic HTTP metadata, never hook/capability injection.
// No real accounts, Runtime access, log reads, page mutations or secret fixtures.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const MARKER = 'ui-admin-pages-fixture'
const PRIVATE_PROSE = 'synthetic-admin-server-prose-must-not-render'
const UNSAFE_BIND = 'synthetic-bind-\u202e-unavailable'
const DOCTOR_API = '/api/v1/doctor'
const LONG_VERSION = `0.${'metadata-build-'.repeat(20)}fixture`
const LONG_ROOT = `/Projects/${'metadata-directory-'.repeat(24)}fixture`
const UNKNOWN_FINDING = 'RUNTIME_METADATA_UNKNOWN'
const pages = ['doctor', 'settings', 'logs'] as const
type AdminPage = (typeof pages)[number]
type Locale = 'zh-CN' | 'en'
type DoctorMode = 'ready' | 'not-ready' | 'runtime-unknown' | 'bind-unavailable'
type Mode = DoctorMode | 'loading' | 'error'

// Deliberately independent of the production catalogs: actual browser copy is
// asserted here, while the app selects its own document locale and formatter.
const copy = {
  en: {
    doctor: 'Doctor',
    settings: 'Settings',
    logs: 'Logs',
    doctorLoading: 'Running safe checks…',
    settingsLoading: 'Loading safe settings…',
    doctorError: 'Diagnostics unavailable',
    checks: 'Control plane checks',
    controlPlane: 'Control plane',
    ready: 'Ready',
    notReady: 'Not ready',
    unknown: 'Unknown',
    unavailable: 'Unavailable',
    readOnly: 'Read only',
    remoteCapability: 'Remote capability',
    remoteState: 'Remote state',
    authentication: 'Authentication',
    bindAddress: 'Bind address',
    settingsFacts: [
      'Environment',
      'Bind address',
      'Absolute session lifetime',
      'Idle session lifetime',
      'Login rate limit',
      'Login lock duration',
    ],
    durations: [
      '2 hours',
      '30 minutes',
      '12,345 failures per 1 minute',
      '73 seconds',
    ],
    planned: 'Planned',
    notImplemented: 'Not implemented yet',
    preview: 'Product preview',
    previewDescription:
      'This section is a product preview only. It does not invoke a runtime, system command, or host service.',
    logCards: ['AgentBox logs', 'Runtime logs', 'Audit events'],
    knownFinding: 'Codex does not report Remote status.',
    unknownFinding: 'A runtime diagnostic was reported.',
    skip: 'Skip to content',
    menu: 'Open navigation',
    navigation: 'Primary navigation',
  },
  'zh-CN': {
    doctor: '诊断',
    settings: '设置',
    logs: '日志',
    doctorLoading: '正在运行安全检查…',
    settingsLoading: '正在加载安全设置…',
    doctorError: '诊断信息暂不可用',
    checks: '控制平面检查',
    controlPlane: '控制平面',
    ready: '已就绪',
    notReady: '未就绪',
    unknown: '未知',
    unavailable: '不可用',
    readOnly: '只读',
    remoteCapability: 'Remote 能力',
    remoteState: 'Remote 状态',
    authentication: '身份验证',
    bindAddress: '绑定地址',
    settingsFacts: [
      '环境',
      '绑定地址',
      '会话绝对有效期',
      '会话空闲有效期',
      '登录速率限制',
      '登录锁定时长',
    ],
    durations: ['2 小时', '30 分钟', '每 1 分钟最多 12,345 次失败', '73 秒'],
    planned: '计划中',
    notImplemented: '尚未实现',
    preview: '产品预览',
    previewDescription:
      '此区域仅展示产品预览，不会调用 Runtime、系统命令或主机服务。',
    logCards: ['AgentBox 日志', 'Runtime 日志', '审计事件'],
    knownFinding: 'Codex 不报告 Remote 状态。',
    unknownFinding: '发现一项 Runtime 诊断信息。',
    skip: '跳到主要内容',
    menu: '打开导航',
    navigation: '主导航',
  },
} as const

// Export these exact HTTP builders for source-only production-decoder checks.
export function adminDoctorMetadata(
  mode: DoctorMode = 'ready',
  normal = false,
) {
  // Keep this small wire fixture local: the node/app composite projects have
  // separate file graphs. Every variant is checked with the production parser;
  // importing the app's test helper here would widen the node compilation.
  const response = {
    api_version: 'v1',
    request_id: 'req_admin_doctor_fixture',
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
        login_rate_limit: 12345,
        login_rate_window_seconds: 60,
        login_lock_duration_seconds: 73,
      },
      codex: {
        installed: true as boolean | null,
        version: '0.admin-fixture' as string | null,
        installation_type: 'standalone',
        remote_control: 'supported',
        remote_state: 'stopped',
        findings: [] as string[],
      },
      claude: {
        installed: true as boolean | null,
        version: '1.admin-fixture' as string | null,
        authentication: 'authenticated',
        remote_control: 'supported',
        tmux_installed: true as boolean | null,
        tmux_version: '3.admin-fixture' as string | null,
        managed_sessions: 1234,
        unmanaged_sessions: 2,
        workspace_interaction_warnings: 1,
        findings: [] as string[],
      },
      projects: {
        project_root: '/Projects/admin-fixture',
        project_count: 7,
        git_installed: true as boolean | null,
        git_version: '2.admin-fixture' as string | null,
        github_cli_installed: true as boolean | null,
        github_authentication: 'authenticated',
        findings: [] as string[],
      },
    },
  }
  const { data } = response
  if (!normal) {
    data.codex.version = LONG_VERSION
    data.claude.version = LONG_VERSION
    data.projects.project_root = LONG_ROOT
    data.codex.findings = [
      'CODEX_REMOTE_STATUS_UNSUPPORTED',
      UNKNOWN_FINDING,
      PRIVATE_PROSE,
    ]
    data.claude.findings = ['CLAUDE_REMOTE_CAPABILITY_UNKNOWN', PRIVATE_PROSE]
    data.projects.findings = ['PROJECT_WORKSPACE_UNAVAILABLE', PRIVATE_PROSE]
  }
  if (mode === 'not-ready') {
    data.status = 'not_ready'
    data.checks.database_reachable = false
    data.checks.control_plane_ready = false
  }
  if (mode === 'runtime-unknown') {
    // Control-plane checks remain ready; Runtime tri-state data is independent.
    Object.assign(data.codex, {
      installed: null,
      version: null,
      installation_type: 'unknown',
      remote_control: 'unknown',
      remote_state: 'unknown',
      findings: [UNKNOWN_FINDING, PRIVATE_PROSE],
    })
    Object.assign(data.claude, {
      installed: null,
      version: null,
      authentication: 'unknown',
      remote_control: 'unknown',
      tmux_installed: null,
      tmux_version: null,
      findings: ['CLAUDE_REMOTE_CAPABILITY_UNKNOWN', PRIVATE_PROSE],
    })
    Object.assign(data.projects, {
      git_installed: null,
      git_version: null,
      github_cli_installed: null,
      github_authentication: 'unknown',
    })
  }
  // A valid wire string rejected by safeTechnical, not an invalid nullable DTO.
  if (mode === 'bind-unavailable') data.policy.bind_host = UNSAFE_BIND
  return response
}

export function adminDoctorFailure() {
  return {
    api_version: 'v1',
    request_id: 'req_admin_metadata_error',
    error: {
      code: 'DOCTOR_UNAVAILABLE',
      category: 'unavailable',
      message: PRIVATE_PROSE,
      retryable: false,
      details: {},
    },
  }
}

function verifiedOrigin(baseURL: string | undefined) {
  if (!baseURL) throw new Error('The isolated E2E harness must provide baseURL')
  const url = new URL(baseURL)
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  )
    throw new Error('The isolated E2E baseURL must be an HTTP(S) origin')
  return url.origin
}

async function fixtures(
  page: Page,
  baseURL: string | undefined,
  normal = false,
) {
  const state = {
    origin: verifiedOrigin(baseURL),
    mode: 'ready' as Mode,
    holds: new Map<string, Rc9RouteHold>(),
    requests: [] as Array<{ path: string; method: string }>,
    completed: [] as string[],
    unexpected: [] as string[],
    errors: [] as string[],
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  await page.routeWebSocket('**/*', (socket) => {
    state.unexpected.push('WebSocket connection')
    socket.close()
  })
  page.on('websocket', () => state.unexpected.push('WebSocket connection'))
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    // Defense in depth: fixture credentials must never reach another origin,
    // including if a future edit changes the outer guard's registration order.
    if (url.origin !== state.origin) {
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
      return
    }
    const path = `${url.pathname}${url.search}`
    const method = request.method()
    state.requests.push({ path, method })
    if (
      method !== 'GET' ||
      !['/healthz', '/api/v1/auth/me', DOCTOR_API].includes(path)
    ) {
      state.unexpected.push(`${method} ${path}`)
      await route.abort('blockedbyclient')
      return
    }
    const mode = state.mode
    const body =
      path === '/healthz'
        ? { status: 'ok' }
        : path === '/api/v1/auth/me'
          ? {
              api_version: 'v1',
              request_id: 'req_ui_admin_auth',
              data: {
                user: { id: 'adm_ui_admin_fixture', username: MARKER },
                session: {
                  id: 'ses_ui_admin_metadata',
                  expires_at: '2030-01-01T00:00:00Z',
                },
                csrf_token: 'synthetic-admin-metadata-csrf',
              },
            }
          : mode === 'error'
            ? adminDoctorFailure()
            : adminDoctorMetadata(mode === 'loading' ? 'ready' : mode, normal)
    // Snapshot before awaiting: a held response keeps the data of its request.
    const response = {
      status: path === DOCTOR_API && mode === 'error' ? 503 : 200,
      contentType: 'application/json',
      headers: { 'Cache-Control': 'no-store' },
      body: JSON.stringify(body),
    }
    const hold = state.holds.get(path)
    state.holds.delete(path)
    if (hold) await hold.hold()
    await route.fulfill(response)
    state.completed.push(path)
  })
  // Last registered runs first: foreign requests and all unexpected same-origin
  // traffic are rejected before any fixture fulfillment or network forwarding.
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const metadata = /^\/(?:api\/|healthz$|readyz$)/.test(url.pathname)
    const document =
      request.resourceType() === 'document' &&
      /^\/(doctor|settings|logs)$/.test(url.pathname)
    const asset =
      ['script', 'stylesheet', 'font', 'image', 'other'].includes(
        request.resourceType(),
      ) &&
      /^\/(?:assets\/|src\/|node_modules\/|@vite\/|@react-refresh$|favicon\.ico$)/.test(
        url.pathname,
      )
    if (
      url.origin !== state.origin ||
      request.method() !== 'GET' ||
      (!metadata && !document && !asset)
    ) {
      const entry = `${request.method()} ${url.origin}${url.pathname}`
      state.unexpected.push(entry)
      if (metadata)
        state.requests.push({
          path: `${url.pathname}${url.search}`,
          method: request.method(),
        })
      await route.abort('blockedbyclient')
      return
    }
    await route.fallback()
  })
  return state
}
type Fixtures = Awaited<ReturnType<typeof fixtures>>

function doctorReads(state: Fixtures) {
  return state.requests.filter(({ path }) => path === DOCTOR_API).length
}

async function boundaries(page: Page, state: Fixtures) {
  expect(state.unexpected).toEqual([])
  expect(state.errors).toEqual([])
  expect(state.requests.every(({ method }) => method === 'GET')).toBe(true)
  expect(
    state.requests.every(({ path }) =>
      ['/healthz', '/api/v1/auth/me', DOCTOR_API].includes(path),
    ),
  ).toBe(true)
  await expect(
    page.locator(
      '.pair-secret, .sensitive-output, input[type="password"], textarea, pre, [contenteditable="true"]',
    ),
  ).toHaveCount(0)
  expect(
    await page
      .locator('input')
      .evaluateAll((inputs) =>
        inputs.every((input) => (input as HTMLInputElement).value === ''),
      ),
  ).toBe(true)
  await assertRc9CanaryAbsent(page, PRIVATE_PROSE)
  await assertRc9CanaryAbsent(page, UNSAFE_BIND)
  expect(
    await page.evaluate(() => ({
      local: Object.entries(localStorage),
      session: Object.entries(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] })
}

async function loaded(
  page: Page,
  route: AdminPage,
  locale: Locale,
  mode: DoctorMode = 'ready',
  normal = false,
) {
  const expected = copy[locale]
  const root = page.locator(`.${route}-page`)
  await expect(
    root.getByRole('heading', { level: 1, name: expected[route], exact: true }),
  ).toBeVisible()
  await assertRc9Title(page, `${expected[route]} · AgentBox`)
  await assertRc9DocumentLocale(page, locale)
  await expect(
    root.locator('button, input, select, textarea, form, a[href]'),
  ).toHaveCount(0)
  if (route === 'doctor') {
    await expect(
      root.getByRole('region', { name: expected.checks, exact: true }),
    ).toBeVisible()
    await expect(
      root.locator('.admin-header-state > span:not(.status-badge)'),
    ).toHaveText(expected.controlPlane)
    await expect(root.locator('.check-list > article')).toHaveCount(5)
    await expect(
      root.locator('.doctor-runtime-grid > .runtime-card'),
    ).toHaveCount(3)
    await expect(root.locator('.admin-header-state .status-badge')).toHaveText(
      mode === 'not-ready' ? expected.notReady : expected.ready,
    )
    await expect(root.locator('.check-list .status-good')).toHaveCount(
      mode === 'not-ready' ? 3 : 5,
    )
    await expect(root.locator('.check-list .status-warning')).toHaveCount(
      mode === 'not-ready' ? 2 : 0,
    )
    if (mode === 'runtime-unknown') {
      const codex = root.getByRole('region', { name: 'Codex', exact: true })
      await expect(
        codex.locator('.runtime-card-heading .status-badge'),
      ).toHaveText(expected.unknown)
      for (const label of [expected.remoteCapability, expected.remoteState]) {
        await expect(
          codex
            .locator('dl > div')
            .filter({ has: page.getByText(label, { exact: true }) })
            .locator('dd'),
        ).toHaveText(expected.unknown)
      }
      const claude = root.getByRole('region', {
        name: 'Claude + tmux',
        exact: true,
      })
      await expect(
        claude
          .locator('dl > div')
          .filter({
            has: page.getByText(expected.authentication, { exact: true }),
          })
          .locator('dd'),
      ).toHaveText(expected.unknown)
      await expect(
        claude.locator('.runtime-card-heading .status-badge'),
      ).toHaveText(expected.unknown)
    } else if (!normal) {
      await expect(root.getByText(LONG_VERSION, { exact: true })).toHaveCount(2)
      await expect(root.getByText(LONG_ROOT, { exact: true })).toBeVisible()
      await assertRc9TechnicalRendering(
        root.getByText(LONG_ROOT, { exact: true }),
      )
      await assertRc9TechnicalRendering(
        root.getByText(LONG_VERSION, { exact: true }).first(),
      )
      await expect(root.locator('.diagnostic-list').first()).toContainText(
        expected.knownFinding,
      )
      await expect(root.locator('.diagnostic-list').first()).toContainText(
        expected.unknownFinding,
      )
      await assertRc9TechnicalRendering(
        root.getByText(UNKNOWN_FINDING, { exact: true }),
      )
    }
  } else if (route === 'settings') {
    await expect(root.locator('.page-header .status-badge')).toHaveText(
      expected.readOnly,
    )
    await expect(root.locator('.settings-policy-grid > section')).toHaveCount(3)
    await expect(root.locator('dt')).toHaveText([...expected.settingsFacts])
    await expect(root.locator('dd')).toHaveCount(6)
    for (const value of expected.durations)
      await expect(root.getByText(value, { exact: true })).toBeVisible()
    const bind = root
      .locator('dl > div')
      .filter({ has: page.getByText(expected.bindAddress, { exact: true }) })
      .locator('dd')
    await expect(bind).toHaveText(
      mode === 'bind-unavailable' ? expected.unavailable : '127.0.0.1: 8080',
    )
    await expect(root).not.toContainText('/Projects/')
    await expect(root.locator('.runtime-card, .diagnostic-list')).toHaveCount(0)
  } else {
    await expect(
      root.getByRole('heading', { name: expected.notImplemented, exact: true }),
    ).toBeVisible()
    await expect(
      root.getByText(expected.preview, { exact: true }),
    ).toBeVisible()
    await expect(
      root.getByText(expected.previewDescription, { exact: true }),
    ).toBeVisible()
    await expect(root.locator('.planned-grid > article')).toHaveCount(3)
    await expect(root.locator('.planned-card h2')).toHaveText([
      ...expected.logCards,
    ])
    await expect(root.locator('.status-badge')).toHaveText(
      Array(4).fill(expected.planned),
    )
    await expect(root.locator('table, pre, input, button, dl')).toHaveCount(0)
  }
}

async function layout(page: Page, route: AdminPage, width: number) {
  const root = page.locator(`.${route}-page`)
  const cards = root.locator(
    route === 'doctor'
      ? '.doctor-runtime-grid > .runtime-card'
      : route === 'settings'
        ? '.settings-policy-grid > section'
        : '.planned-grid > article',
  )
  if (await cards.count()) {
    const first = (await cards.nth(0).boundingBox())!
    const second = (await cards.nth(1).boundingBox())!
    expect(first).not.toBeNull()
    expect(second).not.toBeNull()
    if (width >= 1024) {
      expect(Math.abs(first.y - second.y)).toBeLessThanOrEqual(1)
      expect(second.x).toBeGreaterThanOrEqual(first.x + first.width - 1)
    } else expect(second.y).toBeGreaterThanOrEqual(first.y + first.height - 1)
  }
  const geometry = await root.evaluate((element) => {
    const inside = (child: DOMRect, parent: DOMRect) =>
      child.left >= parent.left - 1 &&
      child.right <= parent.right + 1 &&
      child.top >= parent.top - 1 &&
      child.bottom <= parent.bottom + 1
    const textFits = (item: Element) => {
      const box = item.getBoundingClientRect()
      const walker = document.createTreeWalker(item, NodeFilter.SHOW_TEXT)
      let node: Node | null
      let readable = false
      while ((node = walker.nextNode())) {
        if (!node.textContent?.trim()) continue
        const range = document.createRange()
        range.selectNodeContents(node)
        for (const line of Array.from(range.getClientRects())) {
          if (line.width <= 0) continue
          readable = true
          if (line.height < 10 || !inside(line, box)) return false
        }
      }
      return (
        readable &&
        item.scrollWidth <= item.clientWidth + 1 &&
        item.scrollHeight <= item.clientHeight + 1
      )
    }
    return {
      facts: Array.from(element.querySelectorAll('dl > div')).map((tile) => {
        const label = tile.querySelector('dt')!
        const value = tile.querySelector('dd')!
        const tileBox = tile.getBoundingClientRect()
        return {
          label: label.textContent,
          contained:
            inside(label.getBoundingClientRect(), tileBox) &&
            inside(value.getBoundingClientRect(), tileBox),
          labelFits: textFits(label),
          valueFits: textFits(value),
          follows:
            value.getBoundingClientRect().top >=
            label.getBoundingClientRect().bottom - 1,
        }
      }),
      headings: Array.from(element.querySelectorAll('h1, h2')).map(
        (heading) => ({ text: heading.textContent, fits: textFits(heading) }),
      ),
      badges: Array.from(element.querySelectorAll('.status-badge')).map(
        (badge) => {
          const range = document.createRange()
          range.selectNodeContents(badge)
          const lines = Array.from(range.getClientRects()).filter(
            (rect) => rect.width > 0 && rect.height > 0,
          )
          return {
            text: badge.textContent,
            lines: lines.length,
            fits: textFits(badge),
            contained: inside(
              badge.getBoundingClientRect(),
              badge.parentElement!.getBoundingClientRect(),
            ),
          }
        },
      ),
    }
  })
  for (const fact of geometry.facts)
    expect(fact, `fact ${fact.label}`).toMatchObject({
      contained: true,
      labelFits: true,
      valueFits: true,
      follows: true,
    })
  for (const heading of geometry.headings)
    expect(heading, `heading ${heading.text}`).toMatchObject({ fits: true })
  for (const badge of geometry.badges)
    expect(badge, `whole state label ${badge.text}`).toMatchObject({
      lines: 1,
      fits: true,
      contained: true,
    })
  await assertRc9NoHorizontalOverflow(page)
}

async function capture(
  page: Page,
  state: Fixtures,
  route: AdminPage,
  name: string,
) {
  const url = new URL(page.url())
  expect(url.origin).toBe(state.origin)
  expect(`${url.pathname}${url.search}${url.hash}`).toBe(`/${route}`)
  await expect(page.locator('.app-frame')).toContainText(MARKER)
  await boundaries(page, state)
  await mkdir('test-results', { recursive: true })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: join('test-results', `ui-admin-pages-${route}-${name}.png`),
    fullPage: true,
  })
}

// 60 stress PNGs, one self-managed context per route/locale/width/theme.
for (const route of pages) {
  for (const locale of ['zh-CN', 'en'] as const) {
    for (const width of [360, 390, 768, 1024, 1440]) {
      for (const colorScheme of ['light', 'dark'] as const) {
        test(`${route} metadata ${locale} ${width} ${colorScheme}`, async ({
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
            const state = await fixtures(page, baseURL)
            await page.goto(`/${route}`)
            await loaded(page, route, locale)
            expect(doctorReads(state)).toBe(route === 'logs' ? 0 : 1)
            await assertRc9InteractiveTargets(page)
            await layout(page, route, width)
            await capture(
              page,
              state,
              route,
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

// Six normal Chinese previews use ordinary metadata, separate from long values.
for (const route of pages) {
  for (const [width, colorScheme] of [
    [1440, 'light'],
    [390, 'dark'],
  ] as const) {
    test(`${route} normal Chinese preview ${width} ${colorScheme}`, async ({
      browser,
      baseURL,
    }, testInfo) => {
      test.skip(
        testInfo.project.name !== 'desktop-chromium',
        'self-managed preview context runs once',
      )
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
        const state = await fixtures(page, baseURL, true)
        await page.goto(`/${route}`)
        await loaded(page, route, 'zh-CN', 'ready', true)
        expect(doctorReads(state)).toBe(route === 'logs' ? 0 : 1)
        await layout(page, route, width)
        await capture(
          page,
          state,
          route,
          `preview-zh-CN-${width}-${colorScheme}`,
        )
      } finally {
        await context.close()
      }
    })
  }
}

for (const locale of ['zh-CN', 'en'] as const) {
  test.describe(`Read-only admin states and shell ${locale}`, () => {
    test.use({
      locale,
      colorScheme: 'light',
      contextOptions: { reducedMotion: 'reduce' },
    })
    for (const [route, mode] of [
      ['doctor', 'loading'],
      ['doctor', 'not-ready'],
      ['doctor', 'runtime-unknown'],
      ['doctor', 'error'],
      ['settings', 'loading'],
      ['settings', 'error'],
      ['settings', 'bind-unavailable'],
    ] as const) {
      test(`${route} ${mode}`, async ({ page, baseURL }, testInfo) => {
        const state = await fixtures(page, baseURL)
        state.mode = mode
        const hold = createRc9RouteHold()
        if (mode === 'loading') state.holds.set(DOCTOR_API, hold)
        try {
          await page.goto(`/${route}`)
          const root = page.locator(`.${route}-page`)
          if (mode === 'loading') {
            await hold.waitUntilHeld()
            await expect(root.getByRole('status')).toHaveText(
              copy[locale][
                route === 'doctor' ? 'doctorLoading' : 'settingsLoading'
              ],
            )
            await expect(root.locator('dl')).toHaveCount(0)
          } else if (mode === 'error') {
            await expect(root.getByRole('alert')).toBeVisible()
            await expect(
              root.getByText('DOCTOR_UNAVAILABLE', { exact: true }),
            ).toBeVisible()
            if (route === 'doctor')
              await expect(
                root.getByRole('heading', {
                  name: copy[locale].doctorError,
                  exact: true,
                }),
              ).toBeVisible()
            await expect(root.locator('dl')).toHaveCount(0)
          } else await loaded(page, route, locale, mode)
          await expect(
            root.locator('button, input, select, textarea, form, a[href]'),
          ).toHaveCount(0)
          await assertRc9DocumentLocale(page, locale)
          expect(doctorReads(state)).toBe(1)
          await layout(page, route, page.viewportSize()!.width)
          // States execute on both projects; only the 14 phone images are kept.
          if (testInfo.project.name === 'mobile-chromium')
            await capture(page, state, route, `${mode}-${locale}`)
          await boundaries(page, state)
          if (mode === 'loading') {
            hold.release()
            await loaded(page, route, locale)
            expect(doctorReads(state)).toBe(1)
            await boundaries(page, state)
          }
        } finally {
          hold.dispose()
        }
      })
    }

    test('keyboard skip, drawer restoration and Doctor Settings Logs history', async ({
      page,
      baseURL,
    }) => {
      const state = await fixtures(page, baseURL)
      await page.goto('/doctor')
      await loaded(page, 'doctor', locale)
      await page.keyboard.press('Tab')
      await expect(
        page.getByRole('link', { name: copy[locale].skip, exact: true }),
      ).toBeFocused()
      await page.keyboard.press('Enter')
      await expect(page.locator('#main-content')).toBeFocused()
      if (page.viewportSize()!.width < 900) {
        const menu = page.getByRole('button', {
          name: copy[locale].menu,
          exact: true,
        })
        await menu.click()
        const drawer = page.getByRole('dialog', {
          name: copy[locale].navigation,
          exact: true,
        })
        // Native <dialog> supplies its role implicitly. Check the actual modal
        // and keyboard behavior without requiring a redundant role attribute.
        await expect(drawer).toBeVisible()
        await expect(drawer).toHaveAccessibleName(copy[locale].navigation)
        await expect(drawer).toHaveAttribute('aria-modal', 'true')
        expect(
          await drawer.evaluate(
            (element) =>
              element instanceof HTMLDialogElement &&
              element.open &&
              element.matches(':modal'),
          ),
        ).toBe(true)
        const focusables = drawer.locator(
          'button:enabled, a[href], input:enabled',
        )
        const first = focusables.first()
        const last = focusables.last()
        await expect(first).toBeFocused()
        await page.keyboard.press('Shift+Tab')
        await expect(last).toBeFocused()
        await page.keyboard.press('Tab')
        await expect(first).toBeFocused()
        await page
          .locator('#main-content')
          .evaluate((element) => (element as HTMLElement).focus())
        expect(
          await drawer.evaluate((element) =>
            element.contains(document.activeElement),
          ),
        ).toBe(true)
        await assertRc9NoHorizontalOverflow(page)
        await page.keyboard.press('Escape')
        await expect(drawer).toHaveCount(0)
        await expect(menu).toBeFocused()
      }
      await navigate(page, 'settings', locale)
      await loaded(page, 'settings', locale)
      expect(doctorReads(state)).toBe(2)
      await navigate(page, 'logs', locale)
      await loaded(page, 'logs', locale)
      expect(doctorReads(state)).toBe(2)
      await page.goBack()
      await expect(page).toHaveURL('/settings')
      await loaded(page, 'settings', locale)
      expect(doctorReads(state)).toBe(3)
      await page.goBack()
      await expect(page).toHaveURL(/\/doctor#main-content$/)
      await loaded(page, 'doctor', locale)
      expect(doctorReads(state)).toBe(4)
      await page.goForward()
      await loaded(page, 'settings', locale)
      expect(doctorReads(state)).toBe(5)
      await page.goForward()
      await expect(page).toHaveURL('/logs')
      await loaded(page, 'logs', locale)
      expect(doctorReads(state)).toBe(5)
      await boundaries(page, state)
    })

    test('held Doctor response is discarded across Settings and Back', async ({
      page,
      baseURL,
    }) => {
      const state = await fixtures(page, baseURL)
      state.mode = 'not-ready'
      const hold = createRc9RouteHold()
      state.holds.set(DOCTOR_API, hold)
      try {
        await page.goto('/doctor')
        await hold.waitUntilHeld()
        await expect(
          page.getByText(copy[locale].doctorLoading, { exact: true }),
        ).toBeVisible()
        state.mode = 'ready'
        await navigate(page, 'settings', locale)
        await loaded(page, 'settings', locale)
        expect(doctorReads(state)).toBe(2)
        hold.release()
        await expect
          .poll(
            () => state.completed.filter((path) => path === DOCTOR_API).length,
          )
          .toBe(2)
        await expect(page.locator('.doctor-page')).toHaveCount(0)
        await loaded(page, 'settings', locale)
        await page.goBack()
        await expect(page).toHaveURL('/doctor')
        await loaded(page, 'doctor', locale)
        expect(doctorReads(state)).toBe(3)
        await expect(
          page.locator('.doctor-page .admin-header-state'),
        ).not.toContainText(copy[locale].notReady)
        await boundaries(page, state)
      } finally {
        hold.dispose()
      }
    })
  })
}

async function navigate(page: Page, route: AdminPage, locale: Locale) {
  const link = page.locator(`.primary-nav a[href="/${route}"]:visible`)
  if ((await link.count()) === 0)
    await page
      .getByRole('button', { name: copy[locale].menu, exact: true })
      .click()
  await page.locator(`.primary-nav a[href="/${route}"]:visible`).click()
  await expect(page).toHaveURL(`/${route}`)
  await expect(page.locator('#mobile-navigation')).toHaveCount(0)
}
