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
  assertRc9Title,
} from './rc9-assertions'

// Every API request in this spec is isolated synthetic metadata. Capture is
// explicit and only for these two routes: never login, terminal, server prose,
// real credentials, Pair Codes, traces, videos, or general failure context.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const PROJECT_A = `prj_${'a'.repeat(32)}`
const PROJECT_B = `prj_${'b'.repeat(32)}`
const JOB_ID = `job_${'c'.repeat(32)}`
const LONG_NAME =
  '界面项目 · Interface <img src=x onerror=alert(1)> & "Navigation" '
    .repeat(2)
    .trim()
const LABEL = {
  id: `lbl_${'d'.repeat(32)}`,
  name: '界面验收 <b>inert</b>',
  color: 'amber',
  revision: 1,
  updated_at: '2026-10-07T00:00:00Z',
}
const DRAFT = 'synthetic-local-draft-canary'
const PRIVATE_PROSE = 'synthetic-server-prose-must-not-render'

function project(id = PROJECT_A) {
  return {
    id,
    slug: id === PROJECT_A ? 'interface-a' : 'interface-b',
    display_name: id === PROJECT_A ? LONG_NAME : '第二项目 · Project B',
    source_type: 'existing',
    state: 'ready',
    repository_url: 'https://github.com/synthetic/interface-kit.git',
    default_branch: 'main',
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-07T00:00:00Z',
    git: {
      is_repository: true,
      branch: 'feature/interface-kit-metadata-only',
      detached_head: false,
      unborn_branch: false,
      upstream: 'origin/main',
      ahead: 2,
      behind: 1,
      staged_count: 1,
      unstaged_count: 2,
      untracked_count: 1,
      conflicted_count: 0,
      clean: false,
      remote_url: 'https://github.com/synthetic/interface-kit.git',
      submodules_detected: true,
    },
    github: {
      available: true,
      repository: 'synthetic/interface-kit',
      pull_request_number: 42,
      pull_request_title: '元数据布局 · <script>inert-title</script>',
      pull_request_state: 'open',
      pull_request_draft: true,
      pull_request_url: 'https://github.com/synthetic/interface-kit/pull/42',
      pull_request_base: 'main',
      pull_request_head: 'feature/interface-kit-metadata-only',
      mergeability: 'unknown',
      checks: 'pending',
    },
    claude_state: 'stopped',
  }
}

function job(
  status: 'needs_attention' | 'succeeded' | 'queued' = 'needs_attention',
) {
  return {
    id: JOB_ID,
    type: 'git.branch.create',
    status,
    target_type: 'project',
    target_id: PROJECT_A,
    project_id: PROJECT_A,
    progress: status === 'queued' ? 0 : null,
    phase: null,
    result_summary: PRIVATE_PROSE,
    error_code:
      status === 'needs_attention' ? 'PROJECT_RECOVERY_REQUIRED' : null,
    error_summary: PRIVATE_PROSE,
    created_at: '2026-10-07T00:00:00Z',
    started_at: null,
    finished_at: null,
  }
}

const copy = {
  en: {
    projects: 'Projects',
    attention: 'Needs attention',
    branch: 'Manage branches',
    branchName: 'Branch name',
    pr: 'Prepare Draft PR',
    prTitle: 'Pull request title',
    prBase: 'Pull request base branch',
    prBody: 'Pull request body',
    cancel: 'Cancel',
    create: 'Create branch',
    createPr: 'Create Draft PR',
    details: 'Technical details',
    gitDetails: 'Git details',
    openProject: 'Open project',
    workspace: 'Open Interactive Workspace',
    workspaceTitle: 'Interactive workspace',
    changes: 'View changed paths',
    changesTitle: 'Changed paths',
    navigation: 'Primary navigation',
    menu: 'Open navigation',
    refresh: 'Refresh',
    projectLoading: 'Loading Project…',
    attentionLoading: 'Checking recent operations…',
    attentionError: 'Recent operations could not be loaded.',
    attentionForbidden: 'You do not have permission to view these operations.',
    empty: 'No recent operations need attention.',
    staleProject: 'Project status is out of date.',
    staleAttention: 'Status is out of date.',
    startClaude: 'Start Claude',
  },
  'zh-CN': {
    projects: 'Projects',
    attention: '待处理',
    branch: '管理分支',
    branchName: '分支名称',
    pr: '准备 Draft PR',
    prTitle: 'Pull request 标题',
    prBase: 'Pull request base 分支',
    prBody: 'Pull request 正文',
    cancel: '取消',
    create: '创建分支',
    createPr: '创建 Draft PR',
    details: '技术详情',
    gitDetails: 'Git 详情',
    openProject: '打开项目',
    workspace: '打开交互式工作区',
    workspaceTitle: '交互式工作区',
    changes: '查看变更路径',
    changesTitle: '变更路径',
    navigation: '主导航',
    menu: '打开导航',
    refresh: '刷新',
    projectLoading: '正在加载 Project…',
    attentionLoading: '正在检查最近操作…',
    attentionError: '无法加载最近操作。',
    attentionForbidden: '你没有查看这些操作的权限。',
    empty: '最近没有需要处理的操作。',
    staleProject: 'Project 状态已过期。',
    staleAttention: '状态已过期。',
    startClaude: '启动 Claude',
  },
} as const

type Locale = keyof typeof copy
type Mode =
  'ready' | 'empty' | 'error' | 'forbidden' | 'unauthorized' | 'not-ready'

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_ui_detail_synthetic', data }
}

function failure(code: string) {
  return {
    api_version: 'v1',
    request_id: 'req_ui_detail_synthetic',
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

function gate() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

async function fixtures(page: Page, representative = false) {
  const label = representative ? { ...LABEL, name: 'Interface review' } : LABEL
  const projectData = (id = PROJECT_A) => {
    const data = project(id)
    return representative
      ? {
          ...data,
          display_name: id === PROJECT_A ? 'Interface Kit' : 'Project B',
          github: {
            ...data.github,
            pull_request_title: 'Clarify project navigation',
          },
        }
      : data
  }
  const state = {
    projectMode: 'ready' as Mode,
    attentionMode: 'ready' as Mode,
    projectGate: null as ReturnType<typeof gate> | null,
    attentionGate: null as ReturnType<typeof gate> | null,
    mutationGate: null as ReturnType<typeof gate> | null,
    allowBranch: false,
    reads: [] as string[],
    mutations: [] as {
      path: string
      body: unknown
      csrf: string
      key: string
    }[],
    unexpected: [] as string[],
    errors: [] as string[],
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  const respondMode = async (route: Route, mode: Mode) => {
    const status =
      mode === 'forbidden' ? 403 : mode === 'unauthorized' ? 401 : 503
    const code =
      status === 403
        ? 'FORBIDDEN'
        : status === 401
          ? 'UNAUTHENTICATED'
          : 'CONTROL_PLANE_UNAVAILABLE'
    await route.fulfill({ status, json: failure(code) })
  }
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = `${url.pathname}${url.search}`
    if (request.method() !== 'GET') {
      state.mutations.push({
        path: `${request.method()} ${path}`,
        body: request.postDataJSON(),
        csrf: request.headers()['x-csrf-token'] ?? '',
        key: request.headers()['idempotency-key'] ?? '',
      })
      if (
        state.allowBranch &&
        request.method() === 'POST' &&
        path === `/api/v1/projects/${PROJECT_A}/git/branches`
      ) {
        await state.mutationGate?.promise
        await route.fulfill({ json: envelope(job('queued')) })
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
    if (path === '/api/v1/jobs?scope=mine') {
      await state.attentionGate?.promise
      if (
        ['error', 'forbidden', 'unauthorized'].includes(state.attentionMode)
      ) {
        await respondMode(route, state.attentionMode)
      } else {
        await route.fulfill({
          json: envelope({
            jobs:
              state.attentionMode === 'empty'
                ? []
                : [job(), { ...job('succeeded'), id: 'job_completed' }],
          }),
        })
      }
      return
    }
    if (
      path === `/api/v1/projects/${PROJECT_A}` ||
      path === `/api/v1/projects/${PROJECT_B}`
    ) {
      await state.projectGate?.promise
      if (['error', 'forbidden', 'unauthorized'].includes(state.projectMode)) {
        await respondMode(route, state.projectMode)
      } else {
        const row = {
          ...projectData(path.endsWith(PROJECT_A) ? PROJECT_A : PROJECT_B),
          ...(state.projectMode === 'not-ready' ? { state: 'creating' } : {}),
          ...(state.projectMode === 'empty' ? { git: null, github: null } : {}),
        }
        await route.fulfill({ json: envelope(row) })
      }
      return
    }
    const responses: Record<string, unknown> = {
      // Existing shell ControlPlanePulse performs this fixed read on each mount.
      '/healthz': { status: 'ok' },
      '/api/v1/auth/me': envelope({
        user: { id: 'adm_ui_detail', username: 'synthetic-maintainer' },
        session: { id: 'ses_ui_detail', expires_at: '2027-01-01T00:00:00Z' },
        csrf_token: 'synthetic-ui-detail-csrf',
      }),
      '/api/v1/projects': envelope({
        projects: [projectData(), projectData(PROJECT_B)],
      }),
      '/api/v1/project-favorites': envelope({ favorites: [] }),
      '/api/v1/project-labels': envelope({ labels: [label] }),
      [`/api/v1/jobs/${JOB_ID}`]: envelope(job('queued')),
    }
    for (const id of [PROJECT_A, PROJECT_B]) {
      responses[`/api/v1/projects/${id}/git/branches`] = envelope({
        branches: [
          { name: projectData(id).git.branch, current: true },
          { name: 'main', current: false },
          { name: 'feature/existing', current: false },
        ],
      })
      responses[`/api/v1/claude/sessions/${id}`] = envelope({
        project_id: id,
        display_name: projectData(id).display_name,
        state: 'stopped',
        managed: true,
        session_name: `agentbox-claude-${projectData(id).slug}-synthetic`,
        attach_command: `tmux attach-session -t =agentbox-claude-${projectData(id).slug}-synthetic`,
        workspace_state: 'unknown',
        tmux_running: false,
        remote_readiness: 'unknown',
      })
      responses[`/api/v1/project-labels/projects/${id}`] = envelope({
        project_id: id,
        labels: [label],
        revision: 1,
        updated_at: LABEL.updated_at,
      })
      responses[`/api/v1/projects/${id}/git/changes`] = envelope({
        is_repository: true,
        files: [],
        total_count: 0,
        next_cursor: null,
      })
      // Opening the existing Workspace route also reads its label assignment.
      responses[`/api/v1/project-labels/workspaces/${id}/claude`] = envelope({
        workspace_id:
          id === PROJECT_A
            ? 'aws_9693f27179ae4ec81d3c493f07463bd3'
            : 'aws_5ccab47b63c8af34e6beac2835e328e2',
        project_id: id,
        agent_type: 'claude',
        labels: [],
        revision: 0,
        updated_at: null,
      })
      responses[`/api/v1/workspaces?project_id=${id}&agent_type=claude`] = {
        request_id: 'req_ui_detail_workspace',
        data: { workspaces: [] },
      }
    }
    if (!(path in responses)) {
      state.unexpected.push(`GET ${path}`)
      await route.fulfill({ status: 404, json: failure('UNEXPECTED_READ') })
      return
    }
    await route.fulfill({ json: responses[path] })
  })
  return state
}

type Fixtures = Awaited<ReturnType<typeof fixtures>>

async function assertBoundaries(page: Page, state: Fixtures, mutations = 0) {
  expect(state.unexpected).toEqual([])
  expect(state.mutations).toHaveLength(mutations)
  expect(state.errors).toEqual([])
  expect(
    state.reads.some((path) =>
      /\/(?:output|staged-observation|staged-stream|tickets|providers)(?:[/?]|$)/.test(
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

async function heading(page: Page, title: string) {
  await expect(
    page.getByRole('heading', { name: title, level: 1, exact: true }),
  ).toBeVisible()
  await assertRc9Title(page, `${title} · AgentBox`)
}

async function readyProject(page: Page, locale: Locale, id = PROJECT_A) {
  await heading(page, project(id).display_name)
  await expect(
    page.getByRole('button', { name: copy[locale].branch, exact: true }),
  ).toBeEnabled()
  await expect(
    page.getByRole('button', { name: copy[locale].startClaude, exact: true }),
  ).toBeEnabled()
  await expect(page.getByText(LABEL.name, { exact: true })).toBeVisible()
}

async function navigate(page: Page, locale: Locale, label: string) {
  const menu = page.getByRole('button', {
    name: copy[locale].menu,
    exact: true,
  })
  if (await menu.isVisible()) await menu.click()
  await page
    .getByRole('navigation', { name: copy[locale].navigation, exact: true })
    .getByRole('link', { name: label, exact: true })
    .click()
  await heading(page, label)
}

async function captureRepresentative(
  page: Page,
  name: string,
  locale: Locale,
  browserProject: string,
) {
  // Ready pages have the full matrix. Additional states are sampled once per
  // desktop English and phone Chinese, rather than multiplying all dimensions.
  if (
    (locale === 'en' && browserProject === 'desktop-chromium') ||
    (locale === 'zh-CN' && browserProject === 'mobile-chromium') ||
    (locale === 'en' &&
      browserProject === 'mobile-chromium' &&
      /^(?:error|forbidden)-project-/.test(name))
  ) {
    await capture(page, name)
  }
}

async function capture(page: Page, name: string) {
  // Fail closed before retaining pixels, even if a fixture accidentally expires.
  expect(new URL(page.url()).pathname).toMatch(
    /^\/(?:attention|projects\/prj_[ab]{32})$/,
  )
  await expect(
    page.locator(
      'input[type="password"], .workspace-terminal, .project-action-form',
    ),
  ).toHaveCount(0)
  await assertRc9CanaryAbsent(page, PRIVATE_PROSE)
  await mkdir('test-results', { recursive: true })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: join('test-results', `ui-detail-${name}.png`),
    fullPage: true,
  })
}

for (const locale of ['zh-CN', 'en'] as const) {
  for (const width of [360, 390, 768, 1024, 1440]) {
    for (const colorScheme of ['light', 'dark'] as const) {
      test(`detail + attention ${locale} ${width}px ${colorScheme}: ready metadata and keyboard disclosures`, async ({
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
          reducedMotion: 'reduce',
          viewport: { width, height: 900 },
          isMobile: width < 900,
          hasTouch: width < 900,
        })
        try {
          const page = await context.newPage()
          const state = await fixtures(page)
          const expected = copy[locale]
          await page.goto(`/projects/${PROJECT_A}`)
          await readyProject(page, locale)
          await assertRc9DocumentLocale(page, locale)
          expect(
            await page.evaluate(
              () => getComputedStyle(document.documentElement).colorScheme,
            ),
          ).toBe(colorScheme)
          expect(
            await page.evaluate(
              () => matchMedia('(prefers-reduced-motion: reduce)').matches,
            ),
          ).toBe(true)
          await expect(
            page.locator(
              '.project-detail-page img, .project-detail-page script',
            ),
          ).toHaveCount(0)
          await expect(page.locator('.project-action-form')).toHaveCount(0)
          await assertRc9InteractiveTargets(page)
          await assertRc9NoHorizontalOverflow(page)
          await capture(page, `project-${locale}-${width}-${colorScheme}`)
          await assertRc9Focus(
            page.locator('.project-technical-details summary').first(),
          )
          if (locale === 'en' && width === 1024 && colorScheme === 'dark') {
            await capture(page, 'focus-project-en-1024-dark')
          }

          const branch = page.getByRole('button', {
            name: expected.branch,
            exact: true,
          })
          await assertRc9Focus(branch)
          await page.keyboard.press('Enter')
          const branchName = page.getByLabel(expected.branchName, {
            exact: true,
          })
          await expect(branchName).toBeFocused()
          await branchName.fill(DRAFT)
          await page
            .getByRole('button', { name: expected.cancel, exact: true })
            .click()
          await expect(branch).toBeFocused()
          await expect(branch).toHaveAttribute('aria-expanded', 'false')
          await assertRc9CanaryAbsent(page, DRAFT)
          const pr = page.getByRole('button', {
            name: expected.pr,
            exact: true,
          })
          await pr.focus()
          await page.keyboard.press('Enter')
          await expect(
            page.getByLabel(expected.prTitle, { exact: true }),
          ).toBeFocused()
          await page.getByLabel(expected.prTitle, { exact: true }).fill(DRAFT)
          await page.getByLabel(expected.prBase, { exact: true }).fill(DRAFT)
          await page.getByLabel(expected.prBody, { exact: true }).fill(DRAFT)
          await assertRc9InteractiveTargets(page)
          await assertRc9NoHorizontalOverflow(page)
          await page.keyboard.press('Escape')
          await expect(pr).toBeFocused()
          await assertRc9CanaryAbsent(page, DRAFT)

          await navigate(page, locale, expected.attention)
          await expect(
            page.getByText('PROJECT_RECOVERY_REQUIRED', { exact: true }),
          ).toBeVisible()
          await expect(
            page.getByText('job_completed', { exact: true }),
          ).toHaveCount(0)
          await expect(
            page.getByText(JOB_ID, { exact: true }),
          ).not.toBeVisible()
          const observed = page.locator('.attention-observed time')
          await expect(observed).toHaveAttribute('datetime', /T/)
          const receivedAt = await observed.getAttribute('datetime')
          expect(Math.abs(Date.now() - Date.parse(receivedAt!))).toBeLessThan(
            60_000,
          )
          await assertRc9InteractiveTargets(page)
          await assertRc9NoHorizontalOverflow(page)
          await capture(page, `attention-${locale}-${width}-${colorScheme}`)
          const disclosure = page.locator('.attention-details summary')
          await assertRc9Focus(disclosure)
          if (locale === 'en' && width === 1024 && colorScheme === 'dark') {
            await capture(page, 'focus-attention-en-1024-dark')
          }
          await page.keyboard.press('Enter')
          await assertRc9TechnicalRendering(
            page.getByText(JOB_ID, { exact: true }),
          )
          await assertRc9TechnicalRendering(
            page.getByText('PROJECT_RECOVERY_REQUIRED', { exact: true }),
          )
          await page
            .getByRole('link', { name: expected.openProject, exact: true })
            .click()
          await readyProject(page, locale)
          await expect(page.locator('.attention-list')).toHaveCount(0)
          await assertBoundaries(page, state)
        } finally {
          await context.close()
        }
      })
    }
  }

  test.describe(`detail focused ${locale}`, () => {
    test.use({ locale })

    test('commits Project A → B, Back and Forward before checking draft ownership; Workspace/Changes stay navigation only', async ({
      page,
    }) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      await page.goto('/projects')
      await heading(page, expected.projects)
      await page.getByRole('heading', { name: LONG_NAME, exact: true }).click()
      await readyProject(page, locale)
      await page.locator('main a[href="/projects"]').click()
      await heading(page, expected.projects)
      await expect(page.locator('.project-detail-page')).toHaveCount(0)
      await page
        .getByRole('heading', {
          name: project(PROJECT_B).display_name,
          exact: true,
        })
        .click()
      await readyProject(page, locale, PROJECT_B)
      const tabA = page.locator(`.work-tabs a[href="/projects/${PROJECT_A}"]`)
      const tabB = page.locator(`.work-tabs a[href="/projects/${PROJECT_B}"]`)
      await tabA.click()
      await readyProject(page, locale)
      await page.getByRole('button', { name: expected.pr, exact: true }).click()
      await page.getByLabel(expected.prTitle, { exact: true }).fill(DRAFT)
      await page.getByLabel(expected.prBody, { exact: true }).fill(DRAFT)
      await tabB.click()
      await readyProject(page, locale, PROJECT_B)
      await expect(
        page.getByRole('heading', { name: LONG_NAME, level: 1, exact: true }),
      ).toHaveCount(0)
      await expect(page.locator('.project-action-form')).toHaveCount(0)
      await assertRc9CanaryAbsent(page, DRAFT)
      await page.goBack()
      await readyProject(page, locale)
      await expect(page.locator('.project-action-form')).toHaveCount(0)
      await page.getByRole('button', { name: expected.pr, exact: true }).click()
      await expect(
        page.getByLabel(expected.prTitle, { exact: true }),
      ).toHaveValue('')
      await page.keyboard.press('Escape')
      await page.goForward()
      await readyProject(page, locale, PROJECT_B)
      await expect(page.locator('.project-action-form')).toHaveCount(0)
      await page
        .getByRole('link', { name: expected.changes, exact: true })
        .click()
      await heading(page, expected.changesTitle)
      await expect(page.locator('.project-detail-page')).toHaveCount(0)
      await page.goBack()
      await readyProject(page, locale, PROJECT_B)
      await page
        .getByRole('link', { name: expected.workspace, exact: true })
        .click()
      await heading(page, expected.workspaceTitle)
      await expect(page.locator('.project-detail-page')).toHaveCount(0)
      await expect
        .poll(() =>
          state.reads.includes(
            `/api/v1/workspaces?project_id=${PROJECT_B}&agent_type=claude`,
          ),
        )
        .toBe(true)
      await page.goBack()
      await readyProject(page, locale, PROJECT_B)
      await assertBoundaries(page, state)
    })

    test('guards same-tick repeated mutations and retains submitted Job identity after cancelling local input', async ({
      page,
    }) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      state.allowBranch = true
      state.mutationGate = gate()
      await page.goto(`/projects/${PROJECT_A}`)
      await readyProject(page, locale)
      await page
        .getByRole('button', { name: expected.branch, exact: true })
        .click()
      await page
        .getByLabel(expected.branchName, { exact: true })
        .fill('feature/synthetic-guard')
      await page.locator('#project-branch-form').evaluate((form) => {
        ;(form as HTMLFormElement).requestSubmit()
        ;(form as HTMLFormElement).requestSubmit()
      })
      await expect.poll(() => state.mutations.length).toBe(1)
      await expect(
        page.locator('#project-branch-form button[type="submit"]'),
      ).toBeDisabled()
      await page
        .getByRole('button', { name: expected.cancel, exact: true })
        .click()
      await expect(page.locator('#project-branch-form')).toHaveCount(0)
      state.mutationGate.release()
      await expect(page.getByText(JOB_ID, { exact: true })).toBeVisible()
      await expect
        .poll(() => state.reads.includes(`/api/v1/jobs/${JOB_ID}`))
        .toBe(true)
      await assertRc9TechnicalRendering(page.getByText(JOB_ID, { exact: true }))
      expect(state.mutations[0]).toMatchObject({
        path: `POST /api/v1/projects/${PROJECT_A}/git/branches`,
        body: { branch: 'feature/synthetic-guard' },
        csrf: 'synthetic-ui-detail-csrf',
      })
      expect(state.mutations[0].key).not.toBe('')
      await assertBoundaries(page, state, 1)
    })

    test('clears metadata and local drafts offline, then rereads without replaying actions', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      await page.goto(`/projects/${PROJECT_A}`)
      await readyProject(page, locale)
      await page.getByRole('button', { name: expected.pr, exact: true }).click()
      await page.getByLabel(expected.prTitle, { exact: true }).fill(DRAFT)
      const before = state.reads.filter(
        (path) => path === `/api/v1/projects/${PROJECT_A}`,
      ).length
      await page.context().setOffline(true)
      await expect(page.getByRole('status')).toContainText(
        expected.staleProject,
      )
      await expect(page.locator('.project-action-form')).toHaveCount(0)
      await expect(
        page.getByRole('heading', { name: LONG_NAME, level: 1, exact: true }),
      ).toHaveCount(0)
      await assertRc9CanaryAbsent(page, DRAFT)
      await captureRepresentative(
        page,
        `stale-project-${locale}-${testInfo.project.name}`,
        locale,
        testInfo.project.name,
      )
      await page.context().setOffline(false)
      await readyProject(page, locale)
      expect(
        state.reads.filter((path) => path === `/api/v1/projects/${PROJECT_A}`)
          .length,
      ).toBeGreaterThan(before)
      await expect(page.locator('.project-action-form')).toHaveCount(0)
      await navigate(page, locale, expected.attention)
      await expect(page.locator('.attention-item')).toHaveCount(1)
      await page.context().setOffline(true)
      await expect(page.getByRole('status')).toContainText(
        expected.staleAttention,
      )
      await expect(
        page.locator('.attention-item, .attention-observed'),
      ).toHaveCount(0)
      await expect(
        page.getByRole('button', { name: expected.refresh, exact: true }),
      ).toBeDisabled()
      await captureRepresentative(
        page,
        `stale-attention-${locale}-${testInfo.project.name}`,
        locale,
        testInfo.project.name,
      )
      await page.context().setOffline(false)
      await expect(page.locator('.attention-item')).toHaveCount(1)
      await assertBoundaries(page, state)
    })

    test('renders bounded loading, empty, error, forbidden and not-ready states without runtime claims', async ({
      page,
    }, testInfo) => {
      const state = await fixtures(page)
      const expected = copy[locale]
      state.projectGate = gate()
      await page.goto(`/projects/${PROJECT_A}`)
      await expect(page.getByRole('status')).toContainText(
        expected.projectLoading,
      )
      await captureRepresentative(
        page,
        `loading-project-${locale}-${testInfo.project.name}`,
        locale,
        testInfo.project.name,
      )
      state.projectGate.release()
      state.projectGate = null
      await readyProject(page, locale)
      for (const mode of [
        'empty',
        'not-ready',
        'error',
        'forbidden',
      ] as const) {
        state.projectMode = mode
        const before = state.reads.length
        await page.reload()
        if (mode === 'error' || mode === 'forbidden') {
          await expect(
            page.locator('.project-detail-page [role="alert"]'),
          ).toBeVisible()
          await expect(
            page.getByRole('button', { name: expected.branch, exact: true }),
          ).toHaveCount(0)
        } else {
          await heading(page, LONG_NAME)
          await expect(
            page.getByText(LABEL.name, { exact: true }),
          ).toBeVisible()
          await expect(
            page.getByRole('button', { name: expected.branch, exact: true }),
          ).toBeDisabled()
          await expect(
            page.getByRole('button', { name: expected.pr, exact: true }),
          ).toBeDisabled()
          if (mode === 'not-ready') {
            await expect(
              page.getByRole('link', { name: expected.workspace, exact: true }),
            ).toHaveCount(0)
            await expect(
              page.getByRole('button', {
                name: expected.startClaude,
                exact: true,
              }),
            ).toBeDisabled()
            expect(
              state.reads
                .slice(before)
                .some(
                  (path) =>
                    path.includes('/claude/sessions/') ||
                    path.endsWith('/git/branches'),
                ),
            ).toBe(false)
          }
        }
        await assertRc9NoHorizontalOverflow(page)
        await captureRepresentative(
          page,
          `${mode}-project-${locale}-${testInfo.project.name}`,
          locale,
          testInfo.project.name,
        )
      }
      state.attentionGate = gate()
      await navigate(page, locale, expected.attention)
      await expect(page.getByRole('status')).toContainText(
        expected.attentionLoading,
      )
      await captureRepresentative(
        page,
        `loading-attention-${locale}-${testInfo.project.name}`,
        locale,
        testInfo.project.name,
      )
      state.attentionGate.release()
      state.attentionGate = null
      await expect(page.locator('.attention-item')).toHaveCount(1)
      for (const mode of ['empty', 'error', 'forbidden'] as const) {
        state.attentionMode = mode
        await page.reload()
        await heading(page, expected.attention)
        if (mode === 'empty')
          await expect(page.getByRole('status')).toContainText(expected.empty)
        else
          await expect(page.getByRole('alert')).toContainText(
            mode === 'error'
              ? expected.attentionError
              : expected.attentionForbidden,
          )
        await expect(page.locator('.attention-item')).toHaveCount(0)
        await assertRc9NoHorizontalOverflow(page)
        await captureRepresentative(
          page,
          `${mode}-attention-${locale}-${testInfo.project.name}`,
          locale,
          testInfo.project.name,
        )
      }
      await assertBoundaries(page, state)
    })

    test('removes the authenticated DOM on session expiry without capturing the login page', async ({
      page,
    }) => {
      const state = await fixtures(page)
      await page.goto('/attention')
      await expect(page.locator('.attention-item')).toHaveCount(1)
      state.attentionMode = 'unauthorized'
      await page
        .getByRole('button', { name: copy[locale].refresh, exact: true })
        .click()
      await expect(page.locator('input[type="password"]')).toBeVisible()
      await expect(page).toHaveURL(/\/login$/)
      await expect(
        page.locator('.attention-page, .project-detail-page, .work-tabs'),
      ).toHaveCount(0)
      await assertBoundaries(page, state)
    })

    test('keeps both ready surfaces usable at desktop 200% zoom-equivalent reflow', async ({
      page,
    }, testInfo) => {
      test.skip(
        testInfo.project.name !== 'desktop-chromium',
        'desktop zoom-equivalent reflow runs once',
      )
      // 1280px at 200% browser zoom exposes 640 CSS px to media queries.
      // This tests that reflow size explicitly; it does not claim native zoom.
      await page.setViewportSize({ width: 640, height: 400 })
      const state = await fixtures(page)
      await page.goto(`/projects/${PROJECT_A}`)
      await readyProject(page, locale)
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
      await navigate(page, locale, copy[locale].attention)
      await expect(page.locator('.attention-item')).toHaveCount(1)
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
      await assertBoundaries(page, state)
    })
  })
}

test('captures ordinary synthetic metadata for review without replacing the adversarial matrix', async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'representative screenshots run once alongside the complete responsive matrix',
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
      await page.goto(`/projects/${PROJECT_A}`)
      await heading(page, 'Interface Kit')
      await expect(
        page.getByRole('button', { name: copy['zh-CN'].branch, exact: true }),
      ).toBeEnabled()
      await expect(
        page.getByRole('button', {
          name: copy['zh-CN'].startClaude,
          exact: true,
        }),
      ).toBeEnabled()
      await expect(
        page.getByText('Interface review', { exact: true }),
      ).toBeVisible()
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
      await capture(page, `preview-project-zh-CN-${width}-${colorScheme}`)
      await navigate(page, 'zh-CN', copy['zh-CN'].attention)
      await expect(page.locator('.attention-item')).toHaveCount(1)
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
      await capture(page, `preview-attention-zh-CN-${width}-${colorScheme}`)
      await assertBoundaries(page, state)
    } finally {
      await context.close()
    }
  }
})
