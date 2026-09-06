import { expect, type Page, test } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9FocusRestored,
  assertRc9InteractiveTargets,
  assertRc9ModalDialog,
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
test.beforeEach(async ({ browser }, testInfo) => {
  void browser
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'The rc9 spec creates the exact desktop/mobile contexts itself.',
  )
})

const baseURL = process.env.PLAYWRIGHT_BASE_URL
if (!baseURL) throw new Error('PLAYWRIGHT_BASE_URL is required for rc9 Codex')

const COPY: Record<
  Rc9Locale,
  Readonly<{
    loading: string
    installed: string
    lifecycle: string
    stopped: string
    running: string
    supported: string
    pair: string
    confirm: string
    generate: string
    cancel: string
    start: string
    starting: string
    stop: string
    stopping: string
    generating: string
    copy: string
    copied: string
    hide: string
    copyFailed: string
    statusUnavailable: string
    statusError: string
    genericError: string
    unknown: string
  }>
> = {
  en: {
    loading: 'Detecting Codex safely…',
    installed: 'Installed',
    lifecycle: 'Lifecycle',
    stopped: 'Stopped',
    running: 'Running',
    supported: 'Supported',
    pair: 'Pair New Device',
    confirm: 'Generate a new temporary pairing code?',
    generate: 'Generate Code',
    cancel: 'Cancel',
    start: 'Start Remote',
    starting: 'Starting…',
    stop: 'Stop Remote',
    stopping: 'Stopping…',
    generating: 'Generating…',
    copy: 'Copy',
    copied: 'Copied',
    hide: 'Hide',
    copyFailed: 'The code could not be copied. Try again.',
    statusUnavailable: 'Codex status unavailable',
    statusError: 'Codex status is temporarily unavailable.',
    genericError: 'The operation could not be completed. Try again.',
    unknown: 'Unknown',
  },
  'zh-CN': {
    loading: '正在安全检测 Codex…',
    installed: '已安装',
    lifecycle: '生命周期',
    stopped: '已停止',
    running: '运行中',
    supported: '支持',
    pair: '配对新设备',
    confirm: '生成新的临时配对码？',
    generate: '生成配对码',
    cancel: '取消',
    start: '启动 Remote',
    starting: '正在启动…',
    stop: '停止 Remote',
    stopping: '正在停止…',
    generating: '正在生成…',
    copy: '复制',
    copied: '已复制',
    hide: '隐藏',
    copyFailed: '无法复制配对码，请重试。',
    statusUnavailable: '无法获取 Codex 状态',
    statusError: 'Codex 状态暂不可用。',
    genericError: '操作未完成，请重试。',
    unknown: '未知',
  },
}

type RemoteState = 'running' | 'stopped'

function responseGate() {
  let release!: () => void
  let markHeld!: () => void
  const released = new Promise<void>((resolve) => {
    release = resolve
  })
  const held = new Promise<void>((resolve) => {
    markHeld = resolve
  })
  return { held, markHeld, release, released }
}

function statusEnvelope(
  remoteState: RemoteState = 'stopped',
  version: string | null = '0.rc9.fixture',
) {
  return {
    api_version: 'v1',
    request_id: 'req_rc9_codex_status',
    data: {
      installed: true,
      version,
      selected_executable: '/fixture/bin/codex',
      alternatives: [],
      installation_type: 'standalone',
      conflict_detected: false,
      authentication: 'authenticated',
      capabilities: {
        remote_control: 'supported',
        start: 'supported',
        stop: 'supported',
        pair: 'supported',
        status: 'unsupported',
      },
      remote_state: remoteState,
      remote_confidence: 'reported',
      diagnostics: [
        {
          code: 'CODEX_REMOTE_STATUS_UNSUPPORTED',
          severity: 'info',
          summary: 'SERVER-PROSE-MUST-NOT-RENDER',
          remediation: 'SERVER-REMEDIATION-MUST-NOT-RENDER',
        },
      ],
    },
  }
}

async function installAuthenticatedShellRoutes(page: Page): Promise<void> {
  await page.route('**/auth/me', (route) =>
    route.fulfill({
      json: {
        api_version: 'v1',
        request_id: 'req_rc9_auth',
        data: {
          user: { id: 'adm_rc9', username: 'rc9-maintainer' },
          session: { id: 'ses_rc9', expires_at: '2030-01-01T00:00:00Z' },
          csrf_token: 'csrf-rc9-fixture',
        },
      },
    }),
  )
  await page.route('**/healthz', (route) =>
    route.fulfill({ json: { status: 'ok' } }),
  )
  await page.route('**/readyz', (route) =>
    route.fulfill({
      json: {
        status: 'ready',
        checks: { database: true, migrations: true },
      },
    }),
  )
  await page.route('**/api/v1/meta', (route) =>
    route.fulfill({
      json: {
        name: 'AgentBox',
        version: '0.3.0-rc.9',
        api_version: 'v1',
        environment: 'test',
      },
    }),
  )
}

async function overflowingElements(page: Page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('body *'))
      .map((element) => {
        const rectangle = element.getBoundingClientRect()
        return {
          tag: element.tagName,
          className: element.className,
          text: element.textContent?.trim().slice(0, 80),
          left: rectangle.left,
          right: rectangle.right,
          width: rectangle.width,
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
        }
      })
      .filter(
        (entry) =>
          entry.left < 0 ||
          entry.right > window.innerWidth ||
          entry.scrollWidth > entry.clientWidth,
      ),
  )
}

for (const viewport of RC9_VIEWPORTS) {
  for (const localeScenario of RC9_LOCALE_SCENARIOS) {
    test(`Codex status is localized at ${viewport.name}/${localeScenario.name}`, async ({
      browser,
    }) => {
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale: localeScenario,
        baseURL,
      })
      const page = await context.newPage()
      const statusGate = responseGate()
      const copy = COPY[localeScenario.expectedLocale]
      try {
        await installAuthenticatedShellRoutes(page)
        await page.route('**/api/v1/codex/status', async (route) => {
          statusGate.markHeld()
          await statusGate.released
          await route.fulfill({ json: statusEnvelope() })
        })

        await page.goto('/codex')
        await statusGate.held
        await assertRc9DocumentLocale(page, localeScenario.expectedLocale)
        await expect(
          page.getByText(copy.loading, { exact: true }),
        ).toBeVisible()
        statusGate.release()

        await expect(
          page.getByRole('heading', { name: 'Codex', exact: true }),
        ).toBeVisible()
        await assertRc9Title(page, 'Codex · AgentBox')
        const version = page.getByText('0.rc9.fixture')
        await expect(version).toBeVisible()
        await expect(version).toHaveAttribute('lang', 'en')
        await expect(version).toHaveAttribute('dir', 'ltr')
        await expect(version).toHaveAttribute('translate', 'no')
        await expect(page.getByText('/fixture/bin/codex')).toBeVisible()
        await expect(page.getByText(copy.installed).first()).toBeVisible()
        const lifecycle = page.getByRole('region', { name: copy.lifecycle })
        await expect(
          lifecycle.getByText(copy.stopped, { exact: true }),
        ).toBeVisible()
        await expect(
          lifecycle.getByText(copy.supported, { exact: true }),
        ).toBeVisible()

        const diagnosticCode = page.getByText(
          'CODEX_REMOTE_STATUS_UNSUPPORTED',
          { exact: true },
        )
        await expect(diagnosticCode).toHaveAttribute('lang', 'en')
        await expect(diagnosticCode).toHaveAttribute('dir', 'ltr')
        await expect(diagnosticCode).toHaveAttribute('translate', 'no')
        await expect(
          page.getByText('SERVER-PROSE-MUST-NOT-RENDER'),
        ).toHaveCount(0)
        await expect(
          page.getByText('SERVER-REMEDIATION-MUST-NOT-RENDER'),
        ).toHaveCount(0)

        const refresh = page.getByRole('button', {
          name:
            localeScenario.expectedLocale === 'zh-CN'
              ? '刷新 Codex 状态'
              : 'Refresh Codex status',
        })
        await assertRc9Focus(refresh)

        const pairTrigger = page.getByRole('button', { name: copy.pair })
        await pairTrigger.click()
        const dialog = page.getByRole('dialog', { name: copy.confirm })
        const overflow = await overflowingElements(page)
        expect(overflow, JSON.stringify(overflow)).toEqual([])
        await assertRc9ModalDialog(page, dialog)
        const background = page.locator('[inert]')
        await expect(background).toHaveAttribute('aria-hidden', 'true')
        await page.keyboard.press('Shift+Tab')
        const cancel = dialog.getByRole('button', { name: copy.cancel })
        await expect(cancel).toBeFocused()
        await page.keyboard.press('Tab')
        await expect(
          dialog.getByRole('button', { name: copy.generate }),
        ).toBeFocused()
        await page.keyboard.press('Escape')
        await expect(dialog).toHaveCount(0)
        await assertRc9FocusRestored(pairTrigger)

        await pairTrigger.click()
        const reopened = page.getByRole('dialog', { name: copy.confirm })
        await assertRc9ModalDialog(page, reopened)
        await reopened.getByRole('button', { name: copy.cancel }).click()
        await assertRc9FocusRestored(pairTrigger)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        statusGate.release()
        await context.close()
      }
    })
  }
}

for (const viewport of RC9_VIEWPORTS) {
  for (const localeScenario of RC9_LOCALE_SCENARIOS) {
    test(`Codex Remote and Pair actions cover ${viewport.name}/${localeScenario.name}`, async ({
      browser,
    }) => {
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale: localeScenario,
        baseURL,
      })
      const copy = COPY[localeScenario.expectedLocale]
      const page = await context.newPage()
      let remoteState: RemoteState = 'stopped'
      let pairAttempts = 0
      const startHold = createRc9RouteHold()
      const stopHold = createRc9RouteHold()
      const pairHold = createRc9RouteHold()
      const pairCode = 'PAIR-CODE-RC9-FIXTURE-1234'
      const pairErrorCanary = 'SERVER-PAIR-ERROR-CANARY-RC9-4X8H'
      const clipboardErrorCanary = 'CLIPBOARD-ERROR-CANARY-RC9-6N3P'
      try {
        await page.addInitScript(() => {
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: (value: string) => {
                ;(window as Window & { __rc9Copied?: string }).__rc9Copied =
                  value
                return Promise.resolve()
              },
            },
          })
        })
        await installAuthenticatedShellRoutes(page)
        await page.route('**/api/v1/codex/status', (route) =>
          route.fulfill({ json: statusEnvelope(remoteState) }),
        )
        await page.route('**/api/v1/codex/remote/*', async (route) => {
          expect(route.request().method()).toBe('POST')
          expect(route.request().headers()['x-csrf-token']).toBe(
            'csrf-rc9-fixture',
          )
          const operation = route.request().url().endsWith('/start')
            ? 'start'
            : 'stop'
          await (operation === 'start' ? startHold : stopHold).hold()
          remoteState = operation === 'start' ? 'running' : 'stopped'
          await route.fulfill({
            json: {
              api_version: 'v1',
              request_id: `req_rc9_${operation}`,
              data: {
                outcome: operation === 'start' ? 'started' : 'stopped',
                remote_state: remoteState,
              },
            },
          })
        })
        await page.route('**/api/v1/codex/pair-codes', async (route) => {
          pairAttempts += 1
          if (pairAttempts === 1) {
            await pairHold.hold()
            await route.fulfill({
              json: {
                api_version: 'v1',
                request_id: 'req_rc9_pair',
                data: {
                  pair_code: pairCode,
                  expires_at: null,
                  display_once: true,
                },
              },
            })
            return
          }
          await route.fulfill({
            status: 503,
            json: {
              api_version: 'v1',
              request_id: 'req_rc9_pair_error',
              error: {
                code: 'UNRECOGNIZED_PAIR_FAILURE',
                message: pairErrorCanary,
              },
            },
          })
        })

        await page.goto('/codex')
        await assertRc9DocumentLocale(page, localeScenario.expectedLocale)
        await expect(
          page.getByText(copy.stopped, { exact: true }).first(),
        ).toBeVisible()
        await page.getByRole('button', { name: copy.start }).click()
        await startHold.waitUntilHeld()
        await expect(
          page.getByRole('button', { name: copy.starting }),
        ).toBeDisabled()
        await assertRc9NoHorizontalOverflow(page)
        startHold.release()
        await expect(
          page.getByText(copy.running, { exact: true }).first(),
        ).toBeVisible()
        await page.getByRole('button', { name: copy.stop }).click()
        await stopHold.waitUntilHeld()
        await expect(
          page.getByRole('button', { name: copy.stopping }),
        ).toBeDisabled()
        stopHold.release()
        await expect(
          page.getByText(copy.stopped, { exact: true }).first(),
        ).toBeVisible()

        const pairTrigger = page.getByRole('button', { name: copy.pair })
        await pairTrigger.click()
        const pairDialog = page.getByRole('dialog', { name: copy.confirm })
        await assertRc9ModalDialog(page, pairDialog)
        await expect(page.locator('[inert]')).toHaveAttribute(
          'aria-hidden',
          'true',
        )
        const generate = pairDialog.getByRole('button', { name: copy.generate })
        await expect(generate).toBeFocused()
        await generate.click()
        await pairHold.waitUntilHeld()
        await expect(
          page.getByRole('button', { name: copy.generating }),
        ).toBeDisabled()
        pairHold.release()
        const secret = page.getByText(pairCode, { exact: true })
        await expect(secret).toBeVisible()
        await expect(page.locator('.pair-secret')).toBeFocused()
        await expect(secret).toHaveAttribute('lang', 'en')
        await expect(secret).toHaveAttribute('dir', 'ltr')
        await expect(secret).toHaveAttribute('translate', 'no')
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
        expect(
          await page.evaluate(() => ({
            local: Object.entries(localStorage),
            session: Object.entries(sessionStorage),
          })),
        ).toEqual({ local: [], session: [] })
        await page.getByRole('button', { name: copy.copy }).click()
        await expect(
          page.getByRole('button', { name: copy.copied }),
        ).toBeVisible()
        await expect
          .poll(() =>
            page.evaluate(
              () => (window as Window & { __rc9Copied?: string }).__rc9Copied,
            ),
          )
          .toBe(pairCode)

        await page.evaluate((canary) => {
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: () => Promise.reject(new Error(canary)),
            },
          })
        }, clipboardErrorCanary)
        await page.getByRole('button', { name: copy.copied }).click()
        await expect(page.getByRole('alert')).toContainText(copy.copyFailed)
        await assertRc9CanaryAbsent(page, clipboardErrorCanary)

        await page.getByRole('button', { name: copy.hide }).click()
        await expect(secret).toHaveCount(0)
        await page.getByRole('button', { name: copy.pair }).click()
        await page.getByRole('button', { name: copy.generate }).click()
        await expect(page.getByRole('alert')).toContainText(copy.genericError)
        await expect(page.getByRole('alert')).toBeFocused()
        await assertRc9CanaryAbsent(page, pairErrorCanary)
        const errorCode = page.getByText('UNRECOGNIZED_PAIR_FAILURE')
        await expect(errorCode).toHaveAttribute('lang', 'en')
        await expect(errorCode).toHaveAttribute('dir', 'ltr')
        await expect(errorCode).toHaveAttribute('translate', 'no')
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        startHold.dispose()
        stopHold.dispose()
        pairHold.dispose()
        await context.close()
      }
    })
  }
}

for (const localeScenario of RC9_LOCALE_SCENARIOS) {
  test(`Codex rejects non-ASCII version prose for ${localeScenario.name}`, async ({
    browser,
  }) => {
    const viewport = RC9_VIEWPORTS[0]
    if (!viewport) throw new Error('rc9 desktop fixture missing')
    const context = await createRc9DocumentContext(browser, {
      viewport,
      locale: localeScenario,
      baseURL,
    })
    const page = await context.newPage()
    const canary = `服务端版本说明-${localeScenario.expectedLocale}`
    try {
      await installAuthenticatedShellRoutes(page)
      await page.route('**/api/v1/codex/status', (route) =>
        route.fulfill({ json: statusEnvelope('stopped', canary) }),
      )

      await page.goto('/codex')
      const copy = COPY[localeScenario.expectedLocale]
      await expect(page.getByText(copy.unknown, { exact: true })).toBeVisible()
      await assertRc9CanaryAbsent(page, canary)
    } finally {
      await context.close()
    }
  })
}

for (const localeScenario of RC9_LOCALE_SCENARIOS) {
  test(`Codex status failure ignores server prose for ${localeScenario.name}`, async ({
    browser,
  }) => {
    const viewport = RC9_VIEWPORTS[0]
    if (!viewport) throw new Error('rc9 desktop fixture missing')
    const context = await createRc9DocumentContext(browser, {
      viewport,
      locale: localeScenario,
      baseURL,
    })
    const page = await context.newPage()
    const canary = `SERVER-STATUS-PROSE-CANARY-${localeScenario.expectedLocale}`
    try {
      await installAuthenticatedShellRoutes(page)
      await page.route('**/api/v1/codex/status', (route) =>
        route.fulfill({
          status: 503,
          json: {
            api_version: 'v1',
            request_id: 'req_rc9_status_error',
            error: {
              code: 'CODEX_STATUS_UNAVAILABLE',
              message: canary,
            },
          },
        }),
      )

      await page.goto('/codex')
      const copy = COPY[localeScenario.expectedLocale]
      await expect(
        page.getByRole('heading', { name: copy.statusUnavailable }),
      ).toBeVisible()
      await expect(page.getByRole('alert')).toContainText(copy.statusError)
      await assertRc9CanaryAbsent(page, canary)
      await expect(page.getByText('CODEX_STATUS_UNAVAILABLE')).toHaveAttribute(
        'lang',
        'en',
      )
    } finally {
      await context.close()
    }
  })
}
