import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page, type Route } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
} from './rc9-assertions'
import { createRc9RouteHold, type Rc9RouteHold } from './rc9-fixtures'

// Real App/API metadata routes only. The default missing A3 trust is preserved:
// no content fixture, native adapter, product hook, transport or patch capture.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const PROJECT = `prj_${'a'.repeat(32)}`
const MARKER = 'ui-changes-fixture'
const PRIVATE_PROSE = 'synthetic-changes-server-prose-must-not-render'
const INERT_NAME = '<img src=x onerror=alert(1)> & "metadata".tsx'
const LONG_NAME = `${'长路径与 Unicode 界面 🌍 '.repeat(7)}.tsx`
const PREVIOUS_PATH = `旧目录/${'旧文件名与 Unicode 🌍 '.repeat(6)}.tsx`
const CURSOR = `${'c'.repeat(64)}:4`
const CHANGES_ROUTE = `/projects/${PROJECT}/changes`
const CHANGES_API = `/api/v1/projects/${PROJECT}/git/changes`
const MORE_API = `${CHANGES_API}?cursor=${encodeURIComponent(CURSOR)}`

const copy = {
  en: {
    title: 'Changed paths',
    back: 'Back to Project',
    refresh: 'Refresh',
    loading: 'Checking Git changes…',
    empty: 'No changed paths in this repository.',
    notRepository: 'This Project is not a Git repository.',
    failed: 'Git changes could not be loaded.',
    stale: 'Changes are out of date. Return to this tab or refresh.',
    folder: 'Folder: ui',
    more: 'Load more paths',
    loadingMore: 'Loading more…',
    count: (shown: number, total: number) =>
      `Showing ${shown} of ${total} paths`,
    read: 'Read staged patch',
    reader: 'Staged patch (read-only)',
    unavailable: 'Staged content is unavailable.',
  },
  'zh-CN': {
    title: '变更路径',
    back: '返回 Project',
    refresh: '刷新',
    loading: '正在检查 Git 变更…',
    empty: '此仓库没有变更路径。',
    notRepository: '此 Project 不是 Git 仓库。',
    failed: '无法加载 Git 变更。',
    stale: '变更状态已过期。返回此页面或手动刷新。',
    folder: '文件夹: ui',
    more: '加载更多路径',
    loadingMore: '正在加载…',
    count: (shown: number, total: number) =>
      `已显示 ${shown} / ${total} 条路径`,
    read: '读取暂存补丁',
    reader: '暂存补丁（只读）',
    unavailable: '暂存内容暂不可用。',
  },
} as const

type Locale = keyof typeof copy
// Match the closed GitChangeEntryData wire contract without pulling the App
// project into Playwright's independent composite TypeScript project.
type MetadataEntry = {
  path: string
  previous_path: string | null
  kind:
    | 'added'
    | 'modified'
    | 'deleted'
    | 'renamed'
    | 'copied'
    | 'untracked'
    | 'conflicted'
    | 'typechanged'
  staged: boolean
  unstaged: boolean
}
type Mode =
  | 'ready'
  | 'partial'
  | 'empty'
  | 'not-repository'
  | 'error'
  | 'forbidden'
  | 'unauthorized'

function files(representative = false): MetadataEntry[] {
  const rows: MetadataEntry[] = [
    {
      path: 'docs/guide.md',
      previous_path: null,
      kind: 'modified',
      staged: true,
      unstaged: true,
    },
    {
      path: 'src/api/obsolete.ts',
      previous_path: null,
      kind: 'deleted',
      staged: true,
      unstaged: false,
    },
    {
      path: 'src/ui/button.tsx',
      previous_path: null,
      kind: 'added',
      staged: true,
      unstaged: false,
    },
    {
      path: `src/ui/${representative ? 'panel.tsx' : LONG_NAME}`,
      previous_path: representative ? 'src/ui/old-panel.tsx' : PREVIOUS_PATH,
      kind: 'renamed',
      staged: true,
      unstaged: false,
    },
    {
      path: 'src/ui/icon.tsx',
      previous_path: 'src/ui/original-icon.tsx',
      kind: 'copied',
      staged: true,
      unstaged: false,
    },
    {
      path: representative ? 'src/ui/preview.tsx' : `src/ui/${INERT_NAME}`,
      previous_path: null,
      kind: 'untracked',
      staged: false,
      unstaged: true,
    },
    {
      path: 'src/merge.ts',
      previous_path: null,
      kind: 'conflicted',
      staged: false,
      unstaged: true,
    },
    {
      path: 'tools/link',
      previous_path: null,
      kind: 'typechanged',
      staged: false,
      unstaged: true,
    },
    {
      path: 'README.md',
      previous_path: null,
      kind: 'modified',
      staged: false,
      unstaged: true,
    },
  ]
  return rows.sort((left, right) =>
    left.path < right.path ? -1 : left.path > right.path ? 1 : 0,
  )
}

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_ui_changes_synthetic', data }
}

function failure(code: string) {
  return {
    api_version: 'v1',
    request_id: 'req_ui_changes_synthetic',
    error: {
      code,
      category:
        code === 'UNAUTHENTICATED'
          ? 'unauthenticated'
          : code === 'FORBIDDEN'
            ? 'forbidden'
            : 'unavailable',
      message: PRIVATE_PROSE,
      retryable: false,
      details: {},
    },
  }
}

async function fixtures(page: Page, representative = false) {
  const state = {
    mode: 'ready' as Mode,
    session: 'a',
    rows: files(representative),
    staleMore: false,
    holds: new Map<string, Rc9RouteHold>(),
    reads: [] as string[],
    responses: [] as string[],
    unexpected: [] as string[],
    errors: [] as string[],
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  page.on('websocket', () => state.unexpected.push('WebSocket connection'))
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = `${url.pathname}${url.search}`
    if (request.method() !== 'GET') {
      state.unexpected.push(`${request.method()} ${path}`)
      await route.fulfill({ status: 500, json: failure('UNEXPECTED_MUTATION') })
      return
    }
    state.reads.push(path)
    const project = {
      id: PROJECT,
      slug: 'changes-interface',
      display_name: 'AgentBox 工作台',
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
    const responses: Record<string, unknown> = {
      '/healthz': { status: 'ok' },
      '/api/v1/auth/me': envelope({
        user: { id: 'adm_ui_changes', username: MARKER },
        session: {
          id: `ses_ui_changes_${state.session}`,
          expires_at: '2027-01-01T00:00:00Z',
        },
        csrf_token: `synthetic-ui-changes-csrf-${state.session}`,
      }),
      [`/api/v1/projects/${PROJECT}`]: envelope(project),
      '/api/v1/project-labels': envelope({ labels: [] }),
      [`/api/v1/project-labels/projects/${PROJECT}`]: envelope({
        project_id: PROJECT,
        labels: [],
        revision: 1,
        updated_at: project.updated_at,
      }),
      [`/api/v1/claude/sessions/${PROJECT}`]: envelope({
        project_id: PROJECT,
        display_name: project.display_name,
        state: 'stopped',
        managed: true,
        session_name: 'agentbox-claude-changes-synthetic',
        attach_command:
          'tmux attach-session -t =agentbox-claude-changes-synthetic',
        workspace_state: 'unknown',
        tmux_running: false,
        remote_readiness: 'unknown',
      }),
    }
    const isChanges = path === CHANGES_API || path === MORE_API
    if (!isChanges && !(path in responses)) {
      state.unexpected.push(`GET ${path}`)
      await route.fulfill({ status: 404, json: failure('UNEXPECTED_READ') })
      return
    }
    // Snapshot the whole response before awaiting: an old response must retain
    // its old scope/data, so late-callback assertions cannot accidentally pass.
    const mode = state.mode
    const empty = mode === 'empty' || mode === 'not-repository'
    const partial = mode === 'partial'
    const data = envelope({
      is_repository: mode !== 'not-repository',
      files: empty
        ? []
        : partial
          ? path === MORE_API
            ? state.rows.slice(4)
            : state.rows.slice(0, 4)
          : [...state.rows],
      total_count: empty
        ? 0
        : state.rows.length + (path === MORE_API && state.staleMore ? 1 : 0),
      next_cursor: partial && path === CHANGES_API ? CURSOR : null,
    })
    const response = isChanges ? data : responses[path]
    const pending = state.holds.get(path)
    state.holds.delete(path)
    await pending?.hold()
    if (isChanges && ['error', 'forbidden', 'unauthorized'].includes(mode)) {
      const status =
        mode === 'forbidden' ? 403 : mode === 'unauthorized' ? 401 : 503
      await route.fulfill({
        status,
        json: failure(
          status === 403
            ? 'FORBIDDEN'
            : status === 401
              ? 'UNAUTHENTICATED'
              : 'GIT_CHANGES_UNAVAILABLE',
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

async function assertClosedReader(page: Page) {
  await expect(page.getByTestId('a3-complete-patch')).toHaveCount(0)
  await expect(
    page.locator(
      '.verified-patch-view, .changes-reader-path, .changes-reader-time',
    ),
  ).toHaveCount(0)
  const controls = page.locator('.changes-read')
  for (let index = 0; index < (await controls.count()); index += 1) {
    await expect(controls.nth(index)).toBeDisabled()
  }
}

async function assertBoundaries(page: Page, state: Fixtures) {
  expect(state.unexpected).toEqual([])
  expect(state.errors).toEqual([])
  // This applies only to this unconfigured metadata fixture. Native A3's
  // existing security/currentness polling remains covered by its own specs.
  expect(
    state.reads.some((path) =>
      /\/(?:staged-observation|staged-stream|tickets|attachments|output)(?:[/?]|$)/.test(
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
  await assertClosedReader(page)
}

async function ready(page: Page, locale: Locale, shown = 9, total = 9) {
  const expected = copy[locale]
  await expect(
    page.getByRole('heading', { name: expected.title, level: 1, exact: true }),
  ).toBeVisible()
  await expect(page.locator('.changes-count')).toHaveText(
    expected.count(shown, total),
  )
  await expect(page.locator('.changes-file')).toHaveCount(shown)
  await expect(
    page.getByRole('heading', { name: expected.reader, exact: true }),
  ).toBeVisible()
  await expect(page.getByTestId('a3-reader-status')).toContainText(
    expected.unavailable,
  )
  await assertClosedReader(page)
}

async function assertLayout(page: Page, width: number) {
  const tree = await page.locator('.changes-card').boundingBox()
  const reader = await page.locator('#a3-changes-reader').boundingBox()
  expect(tree).not.toBeNull()
  expect(reader).not.toBeNull()
  if (width >= 1200) {
    expect(Math.abs(tree!.y - reader!.y)).toBeLessThanOrEqual(1)
    expect(reader!.x).toBeGreaterThanOrEqual(tree!.x + tree!.width)
  } else {
    expect(reader!.y).toBeGreaterThanOrEqual(tree!.y + tree!.height)
  }
  await assertRc9NoHorizontalOverflow(page)
}

async function capture(page: Page, state: Fixtures, name: string) {
  // Fail closed before writing pixels: exact route + synthetic account marker,
  // no content DOM, password/input values, server prose or unknown API traffic.
  expect(new URL(page.url()).pathname + new URL(page.url()).search).toBe(
    CHANGES_ROUTE,
  )
  await expect(page.locator('.app-frame')).toContainText(MARKER)
  await expect(
    page.locator(
      'input[type="password"], textarea, pre, [contenteditable="true"]',
    ),
  ).toHaveCount(0)
  expect(
    await page
      .locator('input')
      .evaluateAll((elements) =>
        elements.every((element) => (element as HTMLInputElement).value === ''),
      ),
  ).toBe(true)
  await assertBoundaries(page, state)
  await mkdir('test-results', { recursive: true })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: join('test-results', `ui-changes-${name}.png`),
    fullPage: true,
  })
}

async function capturePhone(
  page: Page,
  state: Fixtures,
  name: string,
  project: string,
) {
  if (project === 'mobile-chromium') await capture(page, state, name)
}

for (const locale of ['zh-CN', 'en'] as const) {
  for (const width of [360, 390, 768, 1024, 1440]) {
    for (const colorScheme of ['light', 'dark'] as const) {
      test(`Changes metadata ${locale} ${width} ${colorScheme}`, async ({
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
          await page.goto(CHANGES_ROUTE)
          await ready(page, locale)
          await assertRc9DocumentLocale(page, locale)
          await expect(
            page
              .locator('.changes-file-name')
              .getByText(INERT_NAME, { exact: true }),
          ).toBeVisible()
          await expect(
            page
              .locator('.changes-file-name')
              .getByText(LONG_NAME, { exact: true }),
          ).toBeVisible()
          await expect(
            page
              .locator('.changes-previous')
              .getByText(PREVIOUS_PATH, { exact: true }),
          ).toBeVisible()
          await expect(
            page.locator(
              '.changes-tree img, .changes-tree script, .changes-tree a',
            ),
          ).toHaveCount(0)
          await expect(page.locator('.changes-read')).toHaveCount(3)
          await assertRc9Focus(
            page.getByRole('button', {
              name: copy[locale].refresh,
              exact: true,
            }),
          )
          await assertRc9InteractiveTargets(page)
          await assertLayout(page, width)
          await capture(page, state, `ready-${locale}-${width}-${colorScheme}`)
        } finally {
          await context.close()
        }
      })
    }
  }

  test.describe(`Changes interactions ${locale}`, () => {
    test.use({ locale, contextOptions: { reducedMotion: 'reduce' } })

    test('renders bounded loading, empty, not-repository, error and forbidden states', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      state.holds.set(CHANGES_API, hold)
      try {
        await page.goto(CHANGES_ROUTE)
        await hold.waitUntilHeld()
        await expect(
          page.getByText(expected.loading, { exact: true }),
        ).toBeVisible()
        await expect(page.locator('.changes-file, .changes-count')).toHaveCount(
          0,
        )
        await capturePhone(
          page,
          state,
          `loading-${locale}`,
          testInfo.project.name,
        )
        hold.release()
        await ready(page, locale)
        for (const mode of [
          'empty',
          'not-repository',
          'error',
          'forbidden',
        ] as const) {
          state.mode = mode
          await page
            .getByRole('button', { name: expected.refresh, exact: true })
            .click()
          await expect(
            page.getByText(
              mode === 'empty'
                ? expected.empty
                : mode === 'not-repository'
                  ? expected.notRepository
                  : expected.failed,
              { exact: true },
            ),
          ).toBeVisible()
          await expect(
            page.locator('.changes-file, .changes-count'),
          ).toHaveCount(0)
          if (mode === 'error' || mode === 'forbidden') {
            await assertRc9TechnicalRendering(
              page.getByText(
                mode === 'error' ? 'GIT_CHANGES_UNAVAILABLE' : 'FORBIDDEN',
                { exact: true },
              ),
            )
          }
          await assertRc9NoHorizontalOverflow(page)
          await capturePhone(
            page,
            state,
            `${mode}-${locale}`,
            testInfo.project.name,
          )
        }
        state.mode = 'ready'
        await page
          .getByRole('button', { name: expected.refresh, exact: true })
          .click()
        await ready(page, locale)
        await assertBoundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('folds folders by keyboard and refreshes metadata without requesting content', async ({
      page,
    }) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      await page.goto(CHANGES_ROUTE)
      await ready(page, locale)
      const folder = page.getByRole('button', {
        name: expected.folder,
        exact: true,
      })
      await assertRc9Focus(folder)
      await page.keyboard.press('Enter')
      await expect(folder).toHaveAttribute('aria-expanded', 'false')
      await expect(page.locator('.changes-file')).toHaveCount(5)
      // Folding changes visibility, never the authoritative total or loaded count.
      await expect(page.locator('.changes-count')).toHaveText(
        expected.count(9, 9),
      )
      await page.keyboard.press('Space')
      await expect(folder).toHaveAttribute('aria-expanded', 'true')
      await ready(page, locale)
      await page
        .locator('.changes-read')
        .first()
        .evaluate((button) => (button as HTMLButtonElement).click())
      await assertClosedReader(page)
      const readsBefore = state.reads.filter(
        (path) => path === CHANGES_API,
      ).length
      await page
        .getByRole('button', { name: expected.refresh, exact: true })
        .click()
      await ready(page, locale)
      expect(state.reads.filter((path) => path === CHANGES_API)).toHaveLength(
        readsBefore + 1,
      )
      await assertBoundaries(page, state)
    })

    test('uses actual total_count through partial pagination and prevents repeated Load more', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      state.mode = 'partial'
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      state.holds.set(MORE_API, hold)
      try {
        await page.goto(CHANGES_ROUTE)
        await ready(page, locale, 4, 9)
        await capturePhone(
          page,
          state,
          `partial-${locale}`,
          testInfo.project.name,
        )
        const more = page.getByRole('button', {
          name: expected.more,
          exact: true,
        })
        await assertRc9Focus(more)
        await more.evaluate((button) => {
          ;(button as HTMLButtonElement).click()
          ;(button as HTMLButtonElement).click()
        })
        await hold.waitUntilHeld()
        await expect(
          page.getByRole('button', { name: expected.loadingMore, exact: true }),
        ).toBeDisabled()
        await expect(page.locator('.changes-count')).toHaveText(
          expected.count(4, 9),
        )
        await capturePhone(
          page,
          state,
          `loading-more-${locale}`,
          testInfo.project.name,
        )
        hold.release()
        await ready(page, locale)
        await expect(page.locator('.changes-more')).toHaveCount(0)
        expect(state.reads.filter((path) => path === MORE_API)).toHaveLength(1)
        await assertBoundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('drops every old row when a paged snapshot changes and recovers only after Refresh', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      state.mode = 'partial'
      state.staleMore = true
      const expected = copy[locale]
      await page.goto(CHANGES_ROUTE)
      await ready(page, locale, 4, 9)
      await page
        .getByRole('button', { name: expected.more, exact: true })
        .click()
      await expect(
        page.getByText('GIT_CHANGES_STALE', { exact: true }),
      ).toBeVisible()
      await expect(
        page.locator('.changes-file, .changes-count, .changes-more'),
      ).toHaveCount(0)
      await capturePhone(
        page,
        state,
        `stale-page-${locale}`,
        testInfo.project.name,
      )
      state.mode = 'ready'
      state.staleMore = false
      await page
        .getByRole('button', { name: expected.refresh, exact: true })
        .click()
      await ready(page, locale)
      await assertBoundaries(page, state)
    })

    test('clears hidden metadata and keeps unavailable reads closed offline and after returning', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      await page.goto(CHANGES_ROUTE)
      await ready(page, locale)
      await page.context().setOffline(true)
      await assertClosedReader(page)
      await capturePhone(
        page,
        state,
        `offline-${locale}`,
        testInfo.project.name,
      )
      await page.context().setOffline(false)
      await page.evaluate(() => {
        Object.defineProperty(document, 'hidden', {
          configurable: true,
          value: true,
        })
        document.dispatchEvent(new Event('visibilitychange'))
      })
      await expect(
        page.getByText(expected.stale, { exact: true }),
      ).toBeVisible()
      await expect(page.locator('.changes-file, .changes-count')).toHaveCount(0)
      await capturePhone(
        page,
        state,
        `hidden-stale-${locale}`,
        testInfo.project.name,
      )
      await page.evaluate(() => {
        delete (document as unknown as { hidden?: boolean }).hidden
        document.dispatchEvent(new Event('visibilitychange'))
      })
      await ready(page, locale)
      await assertBoundaries(page, state)
    })

    test('Back and Forward fence a late metadata reply from a previous route owner', async ({
      page,
    }) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      const hold = createRc9RouteHold()
      try {
        await page.goto(CHANGES_ROUTE)
        await ready(page, locale)
        state.rows = [
          {
            path: 'late-route-owner.txt',
            previous_path: null,
            kind: 'added',
            staged: true,
            unstaged: false,
          },
        ]
        state.holds.set(CHANGES_API, hold)
        await page
          .getByRole('button', { name: expected.refresh, exact: true })
          .click()
        await hold.waitUntilHeld()
        await page
          .getByRole('link', { name: expected.back, exact: true })
          .click()
        await expect(page).toHaveURL(`/projects/${PROJECT}`)
        await expect(page.locator('#a3-changes-reader')).toHaveCount(0)
        state.rows = files()
        await page.goBack()
        await expect(page).toHaveURL(CHANGES_ROUTE)
        await ready(page, locale)
        const completed = state.responses.filter(
          (path) => path === CHANGES_API,
        ).length
        hold.release()
        await expect
          .poll(
            () => state.responses.filter((path) => path === CHANGES_API).length,
          )
          .toBe(completed + 1)
        await ready(page, locale)
        await expect(
          page.getByText('late-route-owner.txt', { exact: true }),
        ).toHaveCount(0)
        await page.goForward()
        await expect(page).toHaveURL(`/projects/${PROJECT}`)
        await expect(page.locator('#a3-changes-reader')).toHaveCount(0)
        await page.goBack()
        await ready(page, locale)
        await assertBoundaries(page, state)
      } finally {
        hold.dispose()
      }
    })

    test('removes all Changes state on session expiry and enters a new session with fresh metadata', async ({
      page,
    }) => {
      const state = await fixtures(page)
      await page.goto(CHANGES_ROUTE)
      await ready(page, locale)
      state.mode = 'unauthorized'
      await page
        .getByRole('button', { name: copy[locale].refresh, exact: true })
        .click()
      await expect(page).toHaveURL(/\/login$/)
      await expect(page.locator('input[type="password"]')).toBeVisible()
      await expect(
        page.locator('#a3-changes-reader, .changes-tree, .work-tabs'),
      ).toHaveCount(0)
      state.session = 'b'
      state.mode = 'empty'
      await page.goto(CHANGES_ROUTE)
      await expect(
        page.getByText(copy[locale].empty, { exact: true }),
      ).toBeVisible()
      await expect(page.locator('.changes-file, .changes-count')).toHaveCount(0)
      expect(
        state.reads.filter((path) => path === '/api/v1/auth/me'),
      ).toHaveLength(2)
      await assertBoundaries(page, state)
    })
  })
}

test('captures normal-name Chinese desktop and mobile metadata previews', async ({
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
      await page.goto(CHANGES_ROUTE)
      await ready(page, 'zh-CN')
      await assertLayout(page, width)
      await assertRc9InteractiveTargets(page)
      await capture(page, state, `preview-zh-CN-${width}-${colorScheme}`)
    } finally {
      await context.close()
    }
  }
})
