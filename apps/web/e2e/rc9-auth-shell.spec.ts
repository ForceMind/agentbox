import { expect, test, type Page } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9Title,
} from './rc9-assertions'
import {
  createRc9DocumentContext,
  createRc9RouteHold,
  RC9_LOCALE_SCENARIOS,
  RC9_VIEWPORTS,
  type Rc9Locale,
} from './rc9-fixtures'

test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const RC9_AUTH_STATE_COVERAGE = [
  'validation-empty',
  'pending',
  'invalid-credentials',
  'rate-limited',
  'unavailable',
] as const

type Rc9AuthState = (typeof RC9_AUTH_STATE_COVERAGE)[number]

const COPY: Readonly<
  Record<
    Rc9Locale,
    Readonly<{
      username: string
      usernamePlaceholder: string
      password: string
      passwordPlaceholder: string
      submit: string
      pending: string
      invalidCredentials: string
      rateLimited: string
      retryAfter: string
      unavailable: string
      requestDetails: string
      health: string
      title: string
    }>
  >
> = {
  en: {
    username: 'Username',
    usernamePlaceholder: 'Enter your username',
    password: 'Password',
    passwordPlaceholder: 'Enter your password',
    submit: 'Sign in',
    pending: 'Signing in…',
    invalidCredentials: 'The username or password is incorrect.',
    rateLimited: 'Too many sign-in attempts. Try again later.',
    retryAfter: 'Try again in approximately 73 seconds.',
    unavailable: 'The operation could not be completed. Try again.',
    requestDetails: 'Request details',
    health: 'Control plane: Healthy',
    title: 'Sign in · AgentBox',
  },
  'zh-CN': {
    username: '用户名',
    usernamePlaceholder: '请输入用户名',
    password: '密码',
    passwordPlaceholder: '请输入密码',
    submit: '登录',
    pending: '正在登录…',
    invalidCredentials: '用户名或密码错误。',
    rateLimited: '登录尝试过于频繁，请稍后重试。',
    retryAfter: '请大约 73 秒后重试。',
    unavailable: '操作未完成，请重试。',
    requestDetails: '请求详情',
    health: '控制平面：正常',
    title: '登录 · AgentBox',
  },
}

const LOGIN_RESPONSES = [
  {
    state: 'invalid-credentials',
    status: 401,
    code: 'AUTH_INVALID_CREDENTIALS',
    requestId: 'req_rc9_login_invalid',
    canary: 'RC9-AUTH-INVALID-SERVER-PROSE-CANARY',
  },
  {
    state: 'rate-limited',
    status: 429,
    code: 'AUTH_RATE_LIMITED',
    requestId: 'req_rc9_login_rate_limited',
    canary: 'RC9-AUTH-RATE-SERVER-PROSE-CANARY',
    retryAfter: '73',
  },
  {
    state: 'unavailable',
    status: 500,
    code: 'RC9_UNKNOWN_SERVER_FAILURE',
    requestId: 'req_rc9_login_unavailable',
    canary: 'RC9-AUTH-UNAVAILABLE-SERVER-PROSE-CANARY',
  },
] as const

async function assertTechnicalRequestId(
  page: Page,
  requestDetails: string,
  requestId: string,
) {
  await page.getByText(requestDetails, { exact: true }).click()
  const technical = page.getByText(requestId, { exact: true })
  await expect(technical).toHaveAttribute('lang', 'en')
  await expect(technical).toHaveAttribute('dir', 'ltr')
  await expect(technical).toHaveAttribute('translate', 'no')
  expect(await technical.textContent()).toMatch(/^[\x20-\x7e]+$/)
}

test('covers every Login state in four isolated locale and viewport documents', async ({
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
      const covered = new Set<Rc9AuthState>()
      let loginRequests = 0
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
          const response = LOGIN_RESPONSES[loginRequests]
          if (response === undefined) {
            throw new Error('unexpected rc9 Login request')
          }
          loginRequests += 1
          if (response.state === 'invalid-credentials') {
            await firstLogin.hold()
          }
          await route.fulfill({
            status: response.status,
            headers:
              'retryAfter' in response
                ? { 'Retry-After': response.retryAfter }
                : undefined,
            json: {
              request_id: response.requestId,
              error: { code: response.code, message: response.canary },
            },
          })
        })
        await page.goto('/login')

        const copy = COPY[locale.expectedLocale]
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9Title(page, copy.title)
        await expect(page.getByLabel(copy.health)).toBeVisible()
        const form = page.locator('form')
        const username = page.getByLabel(copy.username)
        const password = page.getByLabel(copy.password)
        const submit = page.locator('button[type="submit"]')
        await expect(username).toHaveAttribute(
          'placeholder',
          copy.usernamePlaceholder,
        )
        await expect(password).toHaveAttribute(
          'placeholder',
          copy.passwordPlaceholder,
        )
        await expect(username).toHaveAttribute('required', '')
        await expect(password).toHaveAttribute('required', '')
        await expect(submit).toHaveAccessibleName(copy.submit)

        await assertRc9Focus(username)
        await expect(submit).toBeDisabled()
        expect(
          await form.evaluate((element) => {
            if (!(element instanceof HTMLFormElement)) {
              throw new Error('rc9 Login form is missing')
            }
            return element.checkValidity()
          }),
        ).toBe(false)
        await form.evaluate((element) => {
          if (!(element instanceof HTMLFormElement)) {
            throw new Error('rc9 Login form is missing')
          }
          element.requestSubmit()
        })
        expect(loginRequests).toBe(0)
        await expect(page.getByRole('alert')).toHaveCount(0)
        covered.add('validation-empty')

        await username.fill('synthetic-user')
        await assertRc9Focus(password)
        await password.fill('synthetic-password')
        await submit.click()
        await firstLogin.waitUntilHeld()
        await expect(submit).toBeDisabled()
        await expect(submit).toHaveText(copy.pending)
        covered.add('pending')
        firstLogin.release()

        const alert = page.getByRole('alert')
        await expect(alert).toContainText(copy.invalidCredentials)
        await expect(password).toHaveValue('')
        await assertRc9CanaryAbsent(page, LOGIN_RESPONSES[0].canary)
        await assertTechnicalRequestId(
          page,
          copy.requestDetails,
          LOGIN_RESPONSES[0].requestId,
        )
        covered.add('invalid-credentials')

        await password.fill('synthetic-password')
        await submit.click()
        await expect(alert).toContainText(copy.rateLimited)
        await expect(alert).toContainText(copy.retryAfter)
        await assertRc9CanaryAbsent(page, LOGIN_RESPONSES[1].canary)
        await assertTechnicalRequestId(
          page,
          copy.requestDetails,
          LOGIN_RESPONSES[1].requestId,
        )
        covered.add('rate-limited')

        await password.fill('synthetic-password')
        await submit.click()
        await expect(alert).toContainText(copy.unavailable)
        await assertRc9CanaryAbsent(page, LOGIN_RESPONSES[2].canary)
        await assertTechnicalRequestId(
          page,
          copy.requestDetails,
          LOGIN_RESPONSES[2].requestId,
        )
        covered.add('unavailable')

        expect(loginRequests).toBe(LOGIN_RESPONSES.length)
        expect(Array.from(covered)).toEqual(RC9_AUTH_STATE_COVERAGE)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        firstLogin.dispose()
        await context.close()
      }
    }
  }
})
