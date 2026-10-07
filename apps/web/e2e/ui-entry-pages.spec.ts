import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
  assertRc9Title,
} from './rc9-assertions'
import { createRc9RouteHold, type Rc9RouteHold } from './rc9-fixtures'

// Isolated synthetic HTTP only. Filled forms and pending submissions are never
// captured; the original password-bearing auth suites remain capture-off.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

type Locale = 'zh-CN' | 'en'
type EntryPage = 'login' | 'not-found'
type Failure = 'invalid' | 'limited' | 'unavailable'
const MARKER = 'ui-entry-pages-fixture'
const PRIVATE_PROSE = 'synthetic-entry-server-prose-must-not-render'
const MISSING_PATH = '/entry-missing-fixture'
const SYNTHETIC_USERNAME = 'entry-synthetic-username'
const SYNTHETIC_PASSWORD = 'entry-synthetic-password'
const REQUEST_ID = `req_entry_${'metadata_'.repeat(6)}fixture`
const AUTH_PATH = '/api/v1/auth/me'
const LOGIN_PATH = '/api/v1/auth/login'
const copy = {
  en: {
    username: 'Username',
    password: 'Password',
    submit: 'Sign in',
    pending: 'Signing in…',
    details: 'Request details',
    invalid: 'The username or password is incorrect.',
    limited: 'Too many sign-in attempts. Try again later.',
    unavailable: 'The operation could not be completed. Try again.',
    retry: 'Try again in approximately 73 seconds.',
    health: 'Control plane: Healthy',
    checking: 'Control plane: Checking',
    unhealthy: 'Control plane: Unavailable',
    loginTitle: 'Sign in · AgentBox',
    missingTitle: 'Page not found · AgentBox',
    dashboard: 'Dashboard',
    toDashboard: 'Back to Dashboard',
    toLogin: 'Back to sign in',
  },
  'zh-CN': {
    username: '用户名',
    password: '密码',
    submit: '登录',
    pending: '正在登录…',
    details: '请求详情',
    invalid: '用户名或密码错误。',
    limited: '登录尝试过于频繁，请稍后重试。',
    unavailable: '操作未完成，请重试。',
    retry: '请大约 73 秒后重试。',
    health: '控制平面：正常',
    checking: '控制平面：检查中',
    unhealthy: '控制平面：不可用',
    loginTitle: '登录 · AgentBox',
    missingTitle: '未找到页面 · AgentBox',
    dashboard: '概览',
    toDashboard: '返回 Dashboard',
    toLogin: '返回登录',
  },
} as const

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_entry_metadata', data }
}

function authEnvelope() {
  return envelope({
    user: { id: 'adm_entry_fixture', username: MARKER },
    session: { id: 'ses_entry_fixture', expires_at: '2030-01-01T00:00:00Z' },
    csrf_token: 'synthetic-entry-metadata-csrf',
  })
}

async function fixtures(page: Page, baseURL: string | undefined) {
  if (!baseURL) throw new Error('The isolated E2E harness must provide baseURL')
  const base = new URL(baseURL)
  if (
    !['http:', 'https:'].includes(base.protocol) ||
    base.username ||
    base.password ||
    base.pathname !== '/' ||
    base.search ||
    base.hash
  )
    throw new Error('The isolated baseURL must be an HTTP(S) origin')
  const state = {
    origin: base.origin,
    authenticated: false,
    dashboardAllowed: false,
    health: 'healthy' as 'healthy' | 'unavailable',
    failure: 'invalid' as Failure,
    loginAllowance: 0,
    loginCount: 0,
    holds: new Map<string, Rc9RouteHold>(),
    requests: [] as string[],
    completed: [] as string[],
    unexpected: [] as string[],
    errors: [] as string[],
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  await page.routeWebSocket('**/*', (socket) => {
    state.unexpected.push('WebSocket')
    socket.close()
  })
  page.on('websocket', () => state.unexpected.push('WebSocket'))
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = `${url.pathname}${url.search}`
    const method = request.method()
    const reject = async () => {
      state.unexpected.push(`${method} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
    }
    if (url.origin !== state.origin) {
      await reject()
      return
    }
    state.requests.push(`${method} ${path}`)
    let status = 200
    let body: unknown
    const headers: Record<string, string> = { 'Cache-Control': 'no-store' }
    if (method === 'POST' && path === LOGIN_PATH && state.loginAllowance > 0) {
      state.loginAllowance -= 1
      state.loginCount += 1
      // Validate in place, never retain or print the request body.
      const submitted = request.postDataJSON() as Record<string, unknown>
      if (
        submitted.username !== SYNTHETIC_USERNAME ||
        submitted.password !== SYNTHETIC_PASSWORD ||
        Object.keys(submitted).length !== 2
      ) {
        await reject()
        return
      }
      status =
        state.failure === 'invalid'
          ? 401
          : state.failure === 'limited'
            ? 429
            : 500
      body = {
        api_version: 'v1',
        request_id: REQUEST_ID,
        error: {
          code:
            state.failure === 'unavailable'
              ? 'ENTRY_SYNTHETIC_UNKNOWN'
              : 'AUTH_INVALID_CREDENTIALS',
          message: PRIVATE_PROSE,
          category: 'validation',
          retryable: false,
          details: {},
        },
      }
      if (state.failure === 'limited') headers['Retry-After'] = '73'
    } else if (method === 'GET' && path === AUTH_PATH) {
      status = state.authenticated ? 200 : 401
      body = state.authenticated
        ? authEnvelope()
        : { request_id: 'req_entry_anonymous' }
    } else if (method === 'GET' && path === '/healthz') {
      status = state.health === 'healthy' ? 200 : 503
      body =
        state.health === 'healthy'
          ? { status: 'ok' }
          : {
              error: {
                code: 'CONTROL_PLANE_UNAVAILABLE',
                message: PRIVATE_PROSE,
              },
            }
    } else if (method === 'GET' && state.dashboardAllowed) {
      const responses: Record<string, unknown> = {
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
        '/api/v1/jobs?scope=mine': envelope({ jobs: [] }),
        '/api/v1/projects/recent': envelope({ projects: [] }),
      }
      if (!(path in responses)) {
        await reject()
        return
      }
      body = responses[path]
    } else {
      await reject()
      return
    }
    const response = {
      status,
      headers,
      contentType: 'application/json',
      body: JSON.stringify(body),
    }
    const hold = state.holds.get(path)
    state.holds.delete(path)
    if (hold) await hold.hold()
    await route.fulfill(response)
    state.completed.push(`${method} ${path}`)
  })
  // Last registered runs first. No fixture, including synthetic login, may
  // fulfill foreign-origin traffic or forward an unexpected mutation.
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const metadata = /^\/(?:api\/|healthz$|readyz$)/.test(url.pathname)
    const login =
      request.method() === 'POST' &&
      url.pathname === LOGIN_PATH &&
      !url.search &&
      state.loginAllowance > 0
    const document =
      request.resourceType() === 'document' &&
      ['/login', MISSING_PATH, '/dashboard'].includes(url.pathname)
    const asset =
      ['script', 'stylesheet', 'font', 'image', 'other'].includes(
        request.resourceType(),
      ) &&
      /^\/(?:assets\/|src\/|node_modules\/|@vite\/|@react-refresh$|favicon\.ico$)/.test(
        url.pathname,
      )
    if (
      url.origin !== state.origin ||
      (request.method() !== 'GET' && !login) ||
      (!metadata && !document && !asset)
    ) {
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
      return
    }
    await route.fallback()
  })
  return state
}
type Fixtures = Awaited<ReturnType<typeof fixtures>>

async function boundaries(page: Page, state: Fixtures, empty = true) {
  expect(state.unexpected).toEqual([])
  expect(state.errors).toEqual([])
  await assertRc9CanaryAbsent(page, PRIVATE_PROSE)
  await assertRc9CanaryAbsent(page, SYNTHETIC_PASSWORD)
  await expect(
    page.locator(
      '.pair-secret, .sensitive-output, textarea, pre, [contenteditable="true"]',
    ),
  ).toHaveCount(0)
  if (empty) {
    expect(
      await page
        .locator('input')
        .evaluateAll((inputs) =>
          inputs.every((input) => (input as HTMLInputElement).value === ''),
        ),
    ).toBe(true)
    await assertRc9CanaryAbsent(page, SYNTHETIC_USERNAME)
  }
  expect(
    await page.evaluate(() => ({
      local: Object.entries(localStorage),
      session: Object.entries(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] })
}

async function loaded(
  page: Page,
  state: Fixtures,
  route: EntryPage,
  locale: Locale,
) {
  await expect(
    page.locator(route === 'login' ? '.login-page' : '.not-found'),
  ).toBeVisible()
  await assertRc9DocumentLocale(page, locale)
  await assertRc9Title(
    page,
    route === 'login' ? copy[locale].loginTitle : copy[locale].missingTitle,
  )
  await expect
    .poll(
      () =>
        state.completed.filter((entry) => entry === `GET ${AUTH_PATH}`).length,
    )
    .toBe(1)
  if (route === 'login') {
    await expect(
      page.getByLabel(copy[locale].username, { exact: true }),
    ).toHaveAttribute('autocomplete', 'username')
    await expect(
      page.getByLabel(copy[locale].password, { exact: true }),
    ).toHaveAttribute('type', 'password')
    await expect(
      page.getByLabel(copy[locale].password, { exact: true }),
    ).toHaveAttribute('autocomplete', 'current-password')
    await expect(
      page.getByRole('button', { name: copy[locale].submit, exact: true }),
    ).toBeDisabled()
    await expect(page.locator('.login-page input')).toHaveCount(2)
    await assertRc9TechnicalRendering(page.locator('.app-version code > bdi'))
  } else {
    await expect(page.locator('a[href]')).toHaveCount(1)
    await expect(page.getByRole('link')).toHaveAttribute(
      'href',
      state.authenticated ? '/dashboard' : '/login',
    )
    await expect(page.locator('input, form, button')).toHaveCount(0)
    // The browser URL necessarily contains the missing route; only page content
    // must omit it. Secret-canary checks use the broader surface scanner below.
    await expect(page.locator('body')).not.toContainText(MISSING_PATH)
  }
}

async function layout(page: Page, route: EntryPage, width: number) {
  await assertRc9NoHorizontalOverflow(page)
  await assertRc9InteractiveTargets(page)
  const root = page.locator(route === 'login' ? '.login-page' : '.not-found')
  const text = await root.evaluate((element) =>
    Array.from(
      element.querySelectorAll(
        'h1, h2, p, label > span, li, summary, .login-error strong',
      ),
    )
      .filter((item) => item.getBoundingClientRect().height > 0)
      .map((item) => {
        const box = item.getBoundingClientRect()
        const walker = document.createTreeWalker(item, NodeFilter.SHOW_TEXT)
        let node: Node | null
        let fits = true
        while ((node = walker.nextNode())) {
          if (!node.textContent?.trim()) continue
          const range = document.createRange()
          range.selectNodeContents(node)
          for (const line of Array.from(range.getClientRects()))
            if (
              line.width > 0 &&
              (line.left < box.left - 1 ||
                line.right > box.right + 1 ||
                line.top < box.top - 1 ||
                line.bottom > box.bottom + 1 ||
                line.height < 10)
            )
              fits = false
        }
        return {
          tag: item.tagName,
          fits,
          overflow: item.scrollWidth > item.clientWidth + 1,
        }
      }),
  )
  for (const item of text)
    expect(item).toMatchObject({ fits: true, overflow: false })
  if (route === 'login') {
    const panel = (await page.locator('.login-panel').boundingBox())!
    const context = (await page.locator('.login-context').boundingBox())!
    expect(panel).not.toBeNull()
    expect(context).not.toBeNull()
    if (width >= 960) {
      expect(context.x).toBeGreaterThanOrEqual(panel.x + panel.width - 1)
    } else expect(context.y).toBeGreaterThanOrEqual(panel.y + panel.height - 1)
  }
}

async function capture(
  page: Page,
  state: Fixtures,
  route: EntryPage,
  name: string,
) {
  const url = new URL(page.url())
  expect(url.origin).toBe(state.origin)
  expect(`${url.pathname}${url.search}${url.hash}`).toBe(
    route === 'login' ? '/login' : MISSING_PATH,
  )
  expect(state.completed).toContain(`GET ${AUTH_PATH}`)
  await expect(
    page.locator(route === 'login' ? '.login-page' : '.not-found'),
  ).toBeVisible()
  await expect(page.locator('.app-frame')).toHaveCount(0)
  if (route === 'login')
    await expect(page.locator('input[type="password"]')).toHaveValue('')
  await boundaries(page, state)
  await mkdir('test-results', { recursive: true })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: join('test-results', `ui-entry-pages-${route}-${name}.png`),
    fullPage: true,
  })
}

// 48 clean entry-page PNG: Login includes both sides of its 960px breakpoint.
for (const route of ['login', 'not-found'] as const) {
  for (const locale of ['zh-CN', 'en'] as const) {
    for (const width of route === 'login'
      ? [360, 390, 768, 900, 960, 1024, 1440]
      : [360, 390, 768, 1024, 1440]) {
      for (const colorScheme of ['light', 'dark'] as const) {
        test(`${route} empty ${locale} ${width} ${colorScheme}`, async ({
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
            await page.goto(route === 'login' ? '/login' : MISSING_PATH)
            await loaded(page, state, route, locale)
            if (route === 'login')
              await expect(
                page.getByLabel(copy[locale].health, { exact: true }),
              ).toBeVisible()
            await layout(page, route, width)
            await capture(
              page,
              state,
              route,
              `empty-${locale}-${width}-${colorScheme}`,
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
  test.describe(`Entry state and keyboard ${locale}`, () => {
    test.use({
      locale,
      colorScheme: 'light',
      contextOptions: { reducedMotion: 'reduce' },
    })
    for (const failure of ['invalid', 'limited', 'unavailable'] as const) {
      test(`Login ${failure}: clear inputs before safe error capture`, async ({
        page,
        baseURL,
      }, testInfo) => {
        const state = await fixtures(page, baseURL)
        state.failure = failure
        await page.goto('/login')
        await loaded(page, state, 'login', locale)
        const username = page.getByLabel(copy[locale].username, { exact: true })
        const password = page.getByLabel(copy[locale].password, { exact: true })
        await expect(username).toBeFocused()
        await username.fill(SYNTHETIC_USERNAME)
        await page.keyboard.press('Tab')
        await expect(password).toBeFocused()
        await password.fill(SYNTHETIC_PASSWORD)
        state.loginAllowance = 1
        await page.keyboard.press('Enter')
        await expect(page.getByRole('alert')).toContainText(
          copy[locale][failure],
        )
        await expect(password).toHaveValue('')
        await expect(username).toHaveValue(SYNTHETIC_USERNAME)
        expect(state.loginCount).toBe(1)
        if (failure === 'limited')
          await expect(page.getByRole('alert')).toContainText(
            copy[locale].retry,
          )
        // Username retention is the product contract; explicit test cleanup is
        // required before any artifact. No pending or filled-form image exists.
        await username.fill('')
        const summary = page.locator('summary')
        await assertRc9Focus(summary)
        await page.keyboard.press('Enter')
        await expect(page.locator('details')).toHaveAttribute('open', '')
        await assertRc9TechnicalRendering(
          page.getByText(REQUEST_ID, { exact: true }),
        )
        await layout(page, 'login', page.viewportSize()!.width)
        if (testInfo.project.name === 'mobile-chromium')
          await capture(page, state, 'login', `${failure}-${locale}-390-light`)
        await boundaries(page, state)
      })
    }

    for (const health of ['checking', 'unavailable'] as const) {
      test(`Login health ${health} retains manual sign-in`, async ({
        page,
        baseURL,
      }, testInfo) => {
        const state = await fixtures(page, baseURL)
        const hold = createRc9RouteHold()
        if (health === 'checking') state.holds.set('/healthz', hold)
        else state.health = 'unavailable'
        try {
          await page.goto('/login')
          await loaded(page, state, 'login', locale)
          await expect(
            page.getByLabel(
              health === 'checking'
                ? copy[locale].checking
                : copy[locale].unhealthy,
              { exact: true },
            ),
          ).toBeVisible()
          await layout(page, 'login', page.viewportSize()!.width)
          if (testInfo.project.name === 'mobile-chromium')
            await capture(
              page,
              state,
              'login',
              `health-${health}-${locale}-390-light`,
            )
          await boundaries(page, state)
        } finally {
          hold.dispose()
        }
      })
    }

    test('Login pending has one explicit request; manual retry clears the old error', async ({
      page,
      baseURL,
    }) => {
      const state = await fixtures(page, baseURL)
      const hold = createRc9RouteHold()
      state.holds.set(LOGIN_PATH, hold)
      try {
        await page.goto('/login')
        await loaded(page, state, 'login', locale)
        const username = page.getByLabel(copy[locale].username, { exact: true })
        const password = page.getByLabel(copy[locale].password, { exact: true })
        await username.fill(SYNTHETIC_USERNAME)
        await password.fill(SYNTHETIC_PASSWORD)
        state.loginAllowance = 1
        await password.press('Enter')
        await expect(
          page.getByRole('button', { name: copy[locale].pending, exact: true }),
        ).toBeDisabled()
        await expect.poll(() => state.loginCount).toBe(1)
        await password.press('Enter')
        await page.keyboard.press('Tab')
        expect(state.loginCount).toBe(1)
        await hold.waitUntilHeld()
        hold.release()
        await expect(page.getByRole('alert')).toContainText(
          copy[locale].invalid,
        )
        await expect(password).toHaveValue('')
        const retry = createRc9RouteHold()
        state.holds.set(LOGIN_PATH, retry)
        try {
          state.failure = 'limited'
          await password.fill(SYNTHETIC_PASSWORD)
          state.loginAllowance = 1
          await page
            .getByRole('button', { name: copy[locale].submit, exact: true })
            .click()
          await expect.poll(() => state.loginCount).toBe(2)
          await expect(page.getByRole('alert')).toHaveCount(0)
          await expect(
            page.getByRole('button', {
              name: copy[locale].pending,
              exact: true,
            }),
          ).toBeDisabled()
          await retry.waitUntilHeld()
          retry.release()
          await expect(page.getByRole('alert')).toContainText(
            copy[locale].limited,
          )
          await expect(password).toHaveValue('')
          await username.fill('')
          await boundaries(page, state)
          expect(state.loginCount).toBe(2)
        } finally {
          retry.dispose()
        }
      } finally {
        hold.dispose()
      }
    })

    for (const authenticated of [false, true]) {
      test(`NotFound ${authenticated ? 'authenticated' : 'anonymous'} follows its sole route and history`, async ({
        page,
        baseURL,
      }, testInfo) => {
        const state = await fixtures(page, baseURL)
        state.authenticated = authenticated
        state.dashboardAllowed = authenticated
        await page.goto(MISSING_PATH)
        await loaded(page, state, 'not-found', locale)
        await layout(page, 'not-found', page.viewportSize()!.width)
        if (authenticated && testInfo.project.name === 'mobile-chromium')
          await capture(
            page,
            state,
            'not-found',
            `authenticated-${locale}-390-light`,
          )
        const link = page.getByRole('link', {
          name: authenticated ? copy[locale].toDashboard : copy[locale].toLogin,
          exact: true,
        })
        await page.keyboard.press('Tab')
        await expect(link).toBeFocused()
        await assertRc9Focus(link)
        await page.keyboard.press('Enter')
        await expect(page).toHaveURL(
          `${state.origin}${authenticated ? '/dashboard' : '/login'}`,
        )
        if (authenticated)
          await expect(
            page.getByRole('heading', {
              level: 1,
              name: copy[locale].dashboard,
              exact: true,
            }),
          ).toBeVisible()
        else
          await expect(
            page.getByLabel(copy[locale].username, { exact: true }),
          ).toBeVisible()
        const destinationTitle = authenticated
          ? `${copy[locale].dashboard} · AgentBox`
          : copy[locale].loginTitle
        await assertRc9Title(page, destinationTitle)
        await page.goBack()
        await expect(page).toHaveURL(`${state.origin}${MISSING_PATH}`)
        await expect(page.getByRole('link')).toHaveAttribute(
          'href',
          authenticated ? '/dashboard' : '/login',
        )
        await assertRc9Title(page, copy[locale].missingTitle)
        await page.goForward()
        await expect(page).toHaveURL(
          `${state.origin}${authenticated ? '/dashboard' : '/login'}`,
        )
        await expect(page.locator('.not-found')).toHaveCount(0)
        await assertRc9Title(page, destinationTitle)
        await boundaries(page, state)
      })
    }

    test('forced colors and reduced motion keep entry controls visible', async ({
      page,
      baseURL,
    }) => {
      const state = await fixtures(page, baseURL)
      await page.emulateMedia({
        forcedColors: 'active',
        reducedMotion: 'reduce',
      })
      await page.goto('/login')
      await loaded(page, state, 'login', locale)
      await layout(page, 'login', page.viewportSize()!.width)
      await assertRc9Focus(
        page.getByLabel(copy[locale].username, { exact: true }),
      )
      await page.goto(MISSING_PATH)
      await expect(page.locator('.not-found')).toBeVisible()
      await layout(page, 'not-found', page.viewportSize()!.width)
      await assertRc9Focus(page.getByRole('link'))
      await boundaries(page, state)
    })
  })
}
