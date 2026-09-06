import type {
  Browser,
  BrowserContext,
  BrowserContextOptions,
  Page,
  Route,
} from '@playwright/test'
import { devices } from '@playwright/test'

export type Rc9Locale = 'en' | 'zh-CN'

export type Rc9Viewport = Readonly<{
  name: 'desktop' | 'mobile'
  contextOptions: BrowserContextOptions
}>

/** The only two viewports accepted by the rc9 browser matrix. */
export const RC9_VIEWPORTS: readonly Rc9Viewport[] = [
  {
    name: 'desktop',
    contextOptions: {
      ...devices['Desktop Chrome'],
      viewport: { width: 1280, height: 800 },
    },
  },
  {
    name: 'mobile',
    contextOptions: {
      ...devices['Pixel 5'],
      viewport: { width: 390, height: 844 },
    },
  },
]

export type Rc9LocaleScenario = Readonly<{
  name: string
  languages: readonly unknown[] | undefined
  /**
   * This is deliberately independent from `languages`: callers can prove that
   * `navigator.language` and later preferences do not influence rc9.
   */
  language: unknown
  expectedLocale: Rc9Locale
}>

export const RC9_LOCALE_SCENARIOS: readonly Rc9LocaleScenario[] = [
  {
    name: 'zh-primary',
    languages: ['zh-Hans-CN', 'en-US'],
    language: 'en-US',
    expectedLocale: 'zh-CN',
  },
  {
    name: 'english-fallback-primary',
    languages: ['fr-FR', 'zh-CN'],
    language: 'zh-CN',
    expectedLocale: 'en',
  },
]

export type Rc9DocumentOptions = Readonly<{
  viewport: Rc9Viewport
  locale: Rc9LocaleScenario
  baseURL?: string
}>

/**
 * Creates one new browser document with a deterministic language-preference
 * surface. The init script runs before the application module, allowing rc9 to
 * observe exactly one primary preference without exposing real browser state.
 */
export async function createRc9DocumentContext(
  browser: Browser,
  options: Rc9DocumentOptions,
): Promise<BrowserContext> {
  const contextOptions: BrowserContextOptions = {
    ...options.viewport.contextOptions,
    baseURL: options.baseURL,
  }
  const context = await browser.newContext(contextOptions)
  await context.addInitScript(
    ({ languages, language }) => {
      Object.defineProperties(navigator, {
        languages: {
          configurable: true,
          get: () => languages,
        },
        language: {
          configurable: true,
          get: () => language,
        },
      })
    },
    {
      languages: options.locale.languages,
      language: options.locale.language,
    },
  )
  return context
}

type Rc9RouteFulfill = Exclude<Parameters<Route['fulfill']>[0], undefined>

export type Rc9RouteResponse =
  | Rc9RouteFulfill
  | ((route: Route) => Rc9RouteFulfill | Promise<Rc9RouteFulfill>)

export type Rc9RouteHold = Readonly<{
  hold: () => Promise<void>
  waitUntilHeld: () => Promise<void>
  release: () => void
  dispose: () => void
}>

type Deferred = {
  promise: Promise<void>
  resolve: () => void
}

function deferred(): Deferred {
  let resolve!: () => void
  const promise = new Promise<void>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

/**
 * A one-use request gate. `release()` intentionally rejects an early or repeat
 * release so E2E state transitions stay deterministic instead of timing-based.
 */
export function createRc9RouteHold(): Rc9RouteHold {
  const arrived = deferred()
  const released = deferred()
  let held = false
  let hasReleased = false

  return {
    async hold() {
      if (held) throw new Error('rc9 route hold was reached more than once')
      held = true
      arrived.resolve()
      await released.promise
    },
    waitUntilHeld: () => arrived.promise,
    release() {
      if (!held) throw new Error('rc9 route hold has not been reached')
      if (hasReleased) throw new Error('rc9 route hold was already released')
      hasReleased = true
      released.resolve()
    },
    dispose() {
      if (hasReleased) return
      hasReleased = true
      released.resolve()
    },
  }
}

/**
 * Installs a one-request held synthetic response without forwarding a real API
 * request. Call `dispose()` in test cleanup if an assertion fails before release.
 */
export async function installRc9HeldRoute(
  page: Page,
  url: string | RegExp,
  hold: Rc9RouteHold,
  response: Rc9RouteResponse,
): Promise<void> {
  await page.route(
    url,
    async (route) => {
      await hold.hold()
      const fulfilled =
        typeof response === 'function' ? await response(route) : response
      await route.fulfill(fulfilled)
    },
    { times: 1 },
  )
}
