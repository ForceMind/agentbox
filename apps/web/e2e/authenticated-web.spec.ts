import { expect, Page, test } from '@playwright/test'

function requiredEnvironment(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`isolated E2E environment is missing ${name}`)
  return value
}

const username = requiredEnvironment('AGENTBOX_E2E_USERNAME')
const password = requiredEnvironment('AGENTBOX_E2E_PASSWORD')
const pairCode = requiredEnvironment('AGENTBOX_E2E_PAIR_CODE')

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
}

async function navigate(page: Page, label: string, expectedPath: string) {
  const mobileMenu = page.getByRole('button', { name: 'Open navigation' })
  if (await mobileMenu.isVisible()) await mobileMenu.click()
  await page.getByRole('link', { name: label, exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`${expectedPath}$`))
}

async function formalClaudeProjectId(page: Page, displayName: string) {
  const projectId = await page.evaluate(async (name) => {
    const response = await fetch('/api/v1/claude/sessions', {
      credentials: 'include',
    })
    if (!response.ok) throw new Error('could not load formal Claude Projects')
    const body = (await response.json()) as {
      data?: {
        sessions?: Array<{ display_name?: string; project_id?: string }>
      }
    }
    return body.data?.sessions?.find((session) => session.display_name === name)
      ?.project_id
  }, displayName)
  if (!projectId)
    throw new Error(`formal Project ${displayName} is unavailable`)
  expect(projectId).toMatch(/^prj_[0-9a-f]{32}$/)
  expect(projectId).not.toBe(displayName)
  return projectId
}

function projectData(overrides: Record<string, unknown> = {}) {
  return {
    id: 'prj_e2e',
    slug: 'project-a',
    display_name: 'Project A',
    source_type: 'existing',
    state: 'ready',
    repository_url: 'https://github.com/owner/repo.git',
    default_branch: 'main',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
    git: {
      is_repository: true,
      branch: 'main',
      detached_head: false,
      unborn_branch: false,
      upstream: 'origin/main',
      ahead: 0,
      behind: 0,
      staged_count: 0,
      unstaged_count: 0,
      untracked_count: 0,
      conflicted_count: 0,
      clean: true,
      remote_url: 'https://github.com/owner/repo.git',
      submodules_detected: false,
    },
    github: {
      available: true,
      repository: 'owner/repo',
      pull_request_number: null,
      pull_request_title: null,
      pull_request_state: null,
      pull_request_draft: null,
      pull_request_url: null,
      pull_request_base: null,
      pull_request_head: null,
      mergeability: null,
      checks: 'pending',
    },
    claude_state: 'stopped',
    ...overrides,
  }
}

function jobData(
  id: string,
  status: 'queued' | 'succeeded' | 'failed' | 'needs_attention',
  errorCode: string | null = null,
  errorSummary: string | null = null,
) {
  return {
    id,
    type: 'git.operation',
    status,
    target_type: 'project',
    target_id: 'prj_e2e',
    project_id: 'prj_e2e',
    progress: status === 'succeeded' ? 100 : status === 'queued' ? 0 : 25,
    phase: status,
    result_summary: status === 'succeeded' ? 'Operation completed' : null,
    error_code: errorCode,
    error_summary: errorSummary,
    created_at: '2026-08-10T00:00:00Z',
    started_at: status === 'queued' ? null : '2026-08-10T00:00:01Z',
    finished_at: status === 'queued' ? null : '2026-08-10T00:00:02Z',
  }
}

function envelope(data: unknown, requestId = 'req_e2e_project') {
  return { api_version: 'v1', request_id: requestId, data }
}

test('protects authenticated routes and presents an accessible login', async ({
  page,
}) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
  await expect(
    page.getByRole('heading', { name: 'Sign in to manage this workstation' }),
  ).toBeVisible()
  await expect(page.getByLabel('Username')).toBeVisible()
  await expect(page.getByLabel('Password')).toHaveAttribute('type', 'password')
})

test('keeps the Claude page behind authentication', async ({ page }) => {
  await page.goto('/claude')
  await expect(page).toHaveURL(/\/login$/)
  await expect(
    page.getByRole('heading', { name: 'Sign in to manage this workstation' }),
  ).toBeVisible()
})

test('keeps the Projects page behind authentication', async ({ page }) => {
  await page.goto('/projects')
  await expect(page).toHaveURL(/\/login$/)
})

test('shows formal Projects and queues safe create operations', async ({
  page,
}, testInfo) => {
  await login(page)
  await navigate(page, 'Projects', '/projects')
  await expect(page.getByRole('heading', { name: 'project-a' })).toBeVisible()
  const workspaceName = `E2E Workspace ${testInfo.project.name}`
  await page.getByLabel('Project name', { exact: true }).fill(workspaceName)
  const request = page.waitForRequest(
    (value) =>
      value.url().endsWith('/api/v1/projects') && value.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Create Project' }).click()
  const mutation = await request
  expect(mutation.headers()['x-csrf-token']).toBeTruthy()
  expect(mutation.headers()['idempotency-key']).toBeTruthy()
  await expect(page.getByText(workspaceName)).toBeVisible()
})

test('renders the Project empty state from real API data', async ({ page }) => {
  await login(page)
  await page.route('**/api/v1/projects', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: envelope({ projects: [] }) })
    } else {
      await route.fallback()
    }
  })
  await navigate(page, 'Projects', '/projects')
  await expect(
    page.getByRole('heading', { name: 'No Projects yet' }),
  ).toBeVisible()
})

test('tracks successful and failed clone Jobs without fake percentages', async ({
  page,
}) => {
  await login(page)
  let project = projectData({
    id: 'prj_clone',
    slug: 'cloned-e2e',
    display_name: 'Cloned E2E',
    state: 'creating',
    git: null,
    github: null,
    claude_state: null,
  })
  let cloneAttempt = 0
  await page.route('**/api/v1/projects', async (route) => {
    const url = new URL(route.request().url())
    if (
      url.pathname === '/api/v1/projects' &&
      route.request().method() === 'GET'
    ) {
      await route.fulfill({
        json: envelope({ projects: cloneAttempt ? [project] : [] }),
      })
      return
    }
    await route.fallback()
  })
  await page.route('**/api/v1/projects/clone', async (route) => {
    cloneAttempt += 1
    const id = cloneAttempt === 1 ? 'job_clone_success' : 'job_clone_failure'
    project = projectData({
      id: cloneAttempt === 1 ? 'prj_clone' : 'prj_clone_failure',
      slug: cloneAttempt === 1 ? 'cloned-e2e' : 'failed-clone-e2e',
      display_name: cloneAttempt === 1 ? 'Cloned E2E' : 'Failed Clone E2E',
      state: 'creating',
      git: null,
      github: null,
      claude_state: null,
    })
    await route.fulfill({
      json: envelope({ project, job: jobData(id, 'queued') }),
    })
  })
  await page.route('**/api/v1/jobs/job_clone_*', async (route) => {
    const failed = route.request().url().endsWith('job_clone_failure')
    if (failed) {
      project = { ...project, state: 'error' }
      await route.fulfill({
        json: envelope(
          jobData(
            'job_clone_failure',
            'failed',
            'GIT_AUTH_REQUIRED',
            'Git authentication is required',
          ),
        ),
      })
    } else {
      project = projectData({
        id: 'prj_clone',
        slug: 'cloned-e2e',
        display_name: 'Cloned E2E',
      })
      await route.fulfill({
        json: envelope(jobData('job_clone_success', 'succeeded')),
      })
    }
  })
  await navigate(page, 'Projects', '/projects')
  await page
    .getByLabel('Repository URL')
    .fill('https://github.com/owner/repo.git')
  await page.getByLabel('Project name (optional)').fill('Cloned E2E')
  await page.getByRole('button', { name: 'Clone' }).click()
  await expect(page.getByText(/job_clone_success · succeeded/i)).toBeVisible()
  await expect(page.getByText('Cloned E2E')).toBeVisible()

  await page
    .getByLabel('Repository URL')
    .fill('https://github.com/owner/private.git')
  await page.getByLabel('Project name (optional)').fill('Failed Clone E2E')
  await page.getByRole('button', { name: 'Clone' }).click()
  await expect(page.getByText(/job_clone_failure · failed/i)).toBeVisible()
  await expect(page.getByText(/Git authentication is required/i)).toBeVisible()
})

test('shows structured Git state without dangerous actions', async ({
  page,
}) => {
  await login(page)
  await navigate(page, 'Projects', '/projects')
  await page.getByRole('heading', { name: 'project-a' }).click()
  await expect(
    page.getByRole('heading', { name: 'Git', exact: true }),
  ).toBeVisible()
  await expect(page.getByText('Clean')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Pull' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Push' })).toBeVisible()
  await expect(page.getByRole('button', { name: /force/i })).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /reset|clean|delete/i }),
  ).toHaveCount(0)
})

test('handles dirty Git, branches, safe failures, Draft PR, and Claude binding', async ({
  page,
}) => {
  await login(page)
  let draftCreated = false
  const dirtyGit = {
    is_repository: true,
    branch: 'main',
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
    remote_url: 'https://github.com/owner/repo.git',
    submodules_detected: true,
  }
  const detail = () =>
    projectData({
      git: dirtyGit,
      claude_state: 'stopped',
      github: {
        available: true,
        repository: 'owner/repo',
        pull_request_number: draftCreated ? 99 : null,
        pull_request_title: draftCreated ? 'Phase 7 E2E Draft' : null,
        pull_request_state: draftCreated ? 'open' : null,
        pull_request_draft: draftCreated ? true : null,
        pull_request_url: draftCreated
          ? 'https://github.com/owner/repo/pull/99'
          : null,
        pull_request_base: draftCreated ? 'main' : null,
        pull_request_head: draftCreated ? 'feature/phase-7' : null,
        mergeability: draftCreated ? 'clean' : null,
        checks: draftCreated ? 'pass' : 'pending',
      },
    })
  const jobs: Record<
    string,
    { status: 'succeeded' | 'failed'; code?: string; summary?: string }
  > = {}
  await page.route('**/api/v1/projects', async (route) => {
    const url = new URL(route.request().url())
    if (
      url.pathname === '/api/v1/projects' &&
      route.request().method() === 'GET'
    ) {
      await route.fulfill({ json: envelope({ projects: [detail()] }) })
      return
    }
    await route.fallback()
  })
  await page.route('**/api/v1/projects/prj_e2e/**', async (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    if (method === 'GET' && url.pathname.endsWith('/git/branches')) {
      await route.fulfill({
        json: envelope({
          branches: [
            { name: 'main', current: true },
            { name: 'feature/existing', current: false },
          ],
        }),
      })
      return
    }
    if (method === 'POST') {
      let id = 'job_unknown'
      if (url.pathname.endsWith('/git/branches')) {
        id = 'job_branch_create'
        jobs[id] = { status: 'succeeded' }
      } else if (url.pathname.endsWith('/git/switch')) {
        id = 'job_branch_switch'
        jobs[id] = {
          status: 'failed',
          code: 'PROJECT_RUNTIME_ACTIVE',
          summary:
            'Stop the managed Claude session before changing the workspace',
        }
      } else if (url.pathname.endsWith('/git/pull')) {
        id = 'job_pull'
        jobs[id] = {
          status: 'failed',
          code: 'GIT_PULL_REQUIRES_RECONCILIATION',
          summary: 'Pull requires manual reconciliation',
        }
      } else if (url.pathname.endsWith('/git/push')) {
        id = 'job_push'
        jobs[id] = {
          status: 'failed',
          code: 'GIT_UPSTREAM_MISSING',
          summary: 'Current branch has no upstream',
        }
      } else if (url.pathname.endsWith('/github/pull-requests')) {
        id = 'job_pr'
        jobs[id] = { status: 'succeeded' }
      }
      await route.fulfill({ json: envelope(jobData(id, 'queued')) })
      return
    }
    await route.fallback()
  })
  await page.route('**/api/v1/projects/prj_e2e', async (route) => {
    await route.fulfill({ json: envelope(detail()) })
  })
  await page.route('**/api/v1/claude/sessions/prj_e2e', async (route) => {
    await route.fulfill({
      json: envelope({
        project_id: 'prj_e2e',
        display_name: 'Project A',
        state: 'stopped',
        managed: true,
        session_name: 'agentbox-claude-project-a-e2e',
        attach_command: 'tmux attach-session -t =agentbox-claude-project-a-e2e',
        workspace_state: 'unknown',
        tmux_running: false,
        remote_readiness: 'unknown',
      }),
    })
  })
  await page.route('**/api/v1/jobs/job_*', async (route) => {
    const segments = new URL(route.request().url()).pathname.split('/')
    const id = segments[segments.length - 1] ?? ''
    const result = jobs[id]
    if (!result) {
      await route.fallback()
      return
    }
    if (id === 'job_pr') draftCreated = true
    await route.fulfill({
      json: envelope(
        jobData(id, result.status, result.code ?? null, result.summary ?? null),
      ),
    })
  })

  await navigate(page, 'Projects', '/projects')
  await page.getByText('Project A').click()
  await expect(page.getByText('4 changes')).toBeVisible()
  await expect(page.getByText('2 / 1')).toBeVisible()
  await expect(page.getByText(/Submodules detected/i)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start Claude' })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Current · main' }),
  ).toBeVisible()

  await page.getByLabel('Branch name').fill('feature/new')
  await page.getByRole('button', { name: 'Create branch' }).click()
  await expect(page.getByText(/job_branch_create · succeeded/i)).toBeVisible()

  await page.getByRole('button', { name: 'Switch branch' }).click()
  await expect(page.getByText(/PROJECT_RUNTIME_ACTIVE/)).toBeVisible()
  await page.getByRole('button', { name: 'Pull', exact: true }).click()
  await expect(page.getByText(/GIT_PULL_REQUIRES_RECONCILIATION/)).toBeVisible()
  await page.getByRole('button', { name: 'Push', exact: true }).click()
  await expect(page.getByText(/GIT_UPSTREAM_MISSING/)).toBeVisible()

  await page.getByLabel('Pull request title').fill('Phase 7 E2E Draft')
  await page.getByLabel('Pull request base branch').fill('develop')
  await page.getByLabel('Pull request body').fill('Safe bounded body')
  const draftRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith('/github/pull-requests') &&
      request.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Create Draft PR' }).click()
  expect((await draftRequest).postDataJSON()).toEqual({
    title: 'Phase 7 E2E Draft',
    body: 'Safe bounded body',
    base: 'develop',
  })
  await expect(page.getByText(/job_pr · succeeded/i)).toBeVisible()
  await expect(page.getByText(/#99 Phase 7 E2E Draft/)).toBeVisible()
  await expect(page.getByText(/owner\/repo · checks pass/)).toBeVisible()
  const viewport = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(viewport.scroll).toBeLessThanOrEqual(viewport.client)
})

test('returns the same public login error for incorrect credentials', async ({
  page,
}) => {
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill('an incorrect test passphrase')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toContainText('Invalid credentials')
  await expect(page).toHaveURL(/\/login$/)
})

test('logs in, survives refresh, and keeps authenticated users away from login', async ({
  page,
}) => {
  await login(page)
  await expect(page.getByText('0.3.0rc5', { exact: true })).toBeVisible()
  await expect(page.getByText('API v1', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await page.goto('/login')
  await expect(page).toHaveURL(/\/dashboard$/)
})

test('uses session-bound CSRF for logout and revokes browser access', async ({
  page,
}) => {
  await login(page)
  const logoutRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith('/api/v1/auth/logout') &&
      request.method() === 'POST',
  )
  const mobileMenu = page.getByRole('button', { name: 'Open navigation' })
  if (await mobileMenu.isVisible()) await mobileMenu.click()
  await page.getByRole('button', { name: 'Sign out' }).click()
  const request = await logoutRequest
  expect(request.headers()['x-csrf-token']).toBeTruthy()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
})

test('rejects invalid CSRF without destroying the authenticated session', async ({
  page,
}) => {
  await login(page)
  const status = await page.evaluate(async () => {
    const response = await fetch('/api/v1/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRF-Token': 'invalid-test-value' },
    })
    return response.status
  })
  expect(status).toBe(403)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
})

test('navigates every Phase 4 product surface without fake runtime data', async ({
  page,
}) => {
  await login(page)
  for (const [label, path] of [
    ['Codex', '/codex'],
    ['Claude', '/claude'],
    ['Projects', '/projects'],
    ['Doctor', '/doctor'],
    ['Logs', '/logs'],
    ['Settings', '/settings'],
  ] as const) {
    await navigate(page, label, path)
    await expect(
      page.getByRole('heading', { name: label, exact: true }),
    ).toBeVisible()
  }
  await expect(page.getByText('Online')).toHaveCount(0)
})

test('shows truthful Codex fixture status and refreshes it explicitly', async ({
  page,
}) => {
  await login(page)
  let statusRequests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/v1/codex/status')) statusRequests += 1
  })
  await navigate(page, 'Codex', '/codex')
  await expect(page.getByText('0.e2e.fixture')).toBeVisible()
  await expect(page.getByText('/fixture/bin/codex')).toBeVisible()
  await expect(page.getByText('Unknown').first()).toBeVisible()
  const beforeRefresh = statusRequests
  await page.getByRole('button', { name: 'Refresh Codex status' }).click()
  await expect.poll(() => statusRequests).toBeGreaterThan(beforeRefresh)
})

test('starts and stops Codex Remote through CSRF-protected actions', async ({
  page,
}) => {
  await login(page)
  await navigate(page, 'Codex', '/codex')
  const startRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith('/api/v1/codex/remote/start') &&
      request.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Start Remote' }).click()
  expect((await startRequest).headers()['x-csrf-token']).toBeTruthy()
  const lifecycle = page.getByRole('region', { name: 'Lifecycle' })
  await expect(lifecycle.getByText('Running', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Stop Remote' }).click()
  await expect(lifecycle.getByText('Stopped', { exact: true })).toBeVisible()
})

test('keeps Pair Code display explicit, ephemeral, and outside Web Storage', async ({
  page,
}) => {
  await login(page)
  await navigate(page, 'Codex', '/codex')
  await page.getByRole('button', { name: 'Pair New Device' }).click()
  await expect(page.getByText(pairCode)).toHaveCount(0)
  const pairResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/codex/pair-codes'),
  )
  await page.getByRole('button', { name: 'Generate Code' }).click()
  const response = await pairResponse
  expect(response.headers()['cache-control']).toBe('no-store')
  await expect(page.getByText(pairCode)).toBeVisible()
  expect(
    await page.evaluate(() => ({
      local: Object.entries(localStorage),
      session: Object.entries(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] })
  await navigate(page, 'Claude', '/claude')
  await expect(page.getByText(pairCode)).toHaveCount(0)
})

test('copies Pair Code only after a separate user action', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: (value: string) =>
          ((window as Window & { __copied?: string }).__copied = value),
      },
    })
  })
  await login(page)
  await navigate(page, 'Codex', '/codex')
  await page.getByRole('button', { name: 'Pair New Device' }).click()
  await page.getByRole('button', { name: 'Generate Code' }).click()
  await expect(page.getByText(pairCode)).toBeVisible()
  expect(
    await page.evaluate(
      () => (window as Window & { __copied?: string }).__copied ?? null,
    ),
  ).toBeNull()
  await page.getByRole('button', { name: 'Copy' }).click()
  await expect
    .poll(() =>
      page.evaluate(() => (window as Window & { __copied?: string }).__copied),
    )
    .toBe(pairCode)
})

test('disables Pair when the capability contract is unsupported', async ({
  page,
}) => {
  await login(page)
  await page.route('**/api/v1/codex/status', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.data.capabilities.pair = 'unsupported'
    await route.fulfill({ response, json: body })
  })
  await navigate(page, 'Codex', '/codex')
  await expect(
    page.getByRole('button', { name: 'Pair New Device' }),
  ).toBeDisabled()
})

test('fails closed on Pair errors without rendering raw Runtime output', async ({
  page,
}) => {
  await login(page)
  await page.route('**/api/v1/codex/pair-codes', async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        api_version: 'v1',
        request_id: 'req_pair_failure',
        error: {
          code: 'CODEX_PAIR_OUTPUT_UNRECOGNIZED',
          category: 'broken',
          message: 'Codex did not return a recognizable pairing code',
          retryable: false,
          details: {},
        },
      }),
      contentType: 'application/json',
      headers: { 'Cache-Control': 'no-store' },
      status: 503,
    })
  })
  await navigate(page, 'Codex', '/codex')
  await page.getByRole('button', { name: 'Pair New Device' }).click()
  await page.getByRole('button', { name: 'Generate Code' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'Codex did not return a recognizable pairing code',
  )
  await expect(page.getByText(pairCode)).toHaveCount(0)
})

test('shows installed Claude, conservative Remote state, and unmanaged count only', async ({
  page,
}) => {
  await login(page)
  await navigate(page, 'Claude', '/claude')
  await expect(page.getByText('1.e2e.fixture')).toBeVisible()
  await expect(page.getByText('3.e2e.fixture')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'project-a' })).toBeVisible()
  await expect(page.getByText('Needs Interaction')).toBeVisible()
  await expect(
    page.getByText(/never accepts Workspace Trust automatically/i),
  ).toBeVisible()
  await expect(page.getByText('Connected')).toHaveCount(0)
  await expect(page.getByText('claude-legacy')).toHaveCount(0)
  await expect(page.getByText('personal-session')).toHaveCount(0)
  await expect(
    page.getByText('Unmanaged sessions').locator('..'),
  ).toContainText('2')
})

test('starts, detects duplicate start, and stops only a managed Claude session', async ({
  page,
}) => {
  await login(page)
  await navigate(page, 'Claude', '/claude')
  const projectId = await formalClaudeProjectId(page, 'project-a')
  const startRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith(`/api/v1/claude/sessions/${projectId}/start`) &&
      request.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Start Session' }).click()
  const request = await startRequest
  const csrf = request.headers()['x-csrf-token']
  expect(csrf).toBeTruthy()
  await expect(page.getByText('Running').first()).toBeVisible()

  const duplicate = await page.evaluate(
    async ({ token, id }) => {
      const response = await fetch(
        `/api/v1/claude/sessions/${encodeURIComponent(id)}/start`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { 'X-CSRF-Token': token },
        },
      )
      return { status: response.status, body: await response.json() }
    },
    { token: csrf, id: projectId },
  )
  expect(duplicate.status).toBe(200)
  expect(duplicate.body.data.outcome).toBe('already_running')

  const stopRequest = page.waitForRequest(
    (stop) =>
      stop.url().endsWith(`/api/v1/claude/sessions/${projectId}/stop`) &&
      stop.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Stop Session' }).first().click()
  expect((await stopRequest).headers()['x-csrf-token']).toBeTruthy()
  await expect(
    page.getByRole('button', { name: 'Start Session' }),
  ).toBeVisible()
  await expect(
    page.getByText(/does not delete the project/i).first(),
  ).toBeVisible()
})

test('copies generated attach command and reveals sensitive output only on demand', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: (value: string) =>
          ((window as Window & { __claudeCopied?: string }).__claudeCopied =
            value),
      },
    })
  })
  await login(page)
  const projectId = await formalClaudeProjectId(page, 'trust-project')
  let outputRequests = 0
  page.on('request', (request) => {
    if (request.url().endsWith(`/sessions/${projectId}/output`)) {
      outputRequests += 1
    }
  })
  await navigate(page, 'Claude', '/claude')
  expect(outputRequests).toBe(0)
  await page.getByRole('button', { name: 'Copy attach command' }).nth(1).click()
  await expect
    .poll(() =>
      page.evaluate(
        () => (window as Window & { __claudeCopied?: string }).__claudeCopied,
      ),
    )
    .toBe('tmux attach-session -t =agentbox-claude-trust-project-e2efixture')

  const outputResponse = page.waitForResponse((response) =>
    response.url().endsWith(`/sessions/${projectId}/output`),
  )
  await page.getByRole('button', { name: 'Reveal' }).nth(1).click()
  const response = await outputResponse
  expect(response.headers()['cache-control']).toBe('no-store')
  await expect(page.getByText('CLAUDE-OUTPUT-CANARY')).toBeVisible()
  expect(outputRequests).toBe(1)
  expect(
    await page.evaluate(() => ({
      local: Object.entries(localStorage),
      session: Object.entries(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] })
  await page.getByRole('button', { name: 'Hide' }).click()
  await expect(page.getByText('CLAUDE-OUTPUT-CANARY')).toHaveCount(0)
})

test('renders unknown Claude readiness without a fake connected claim', async ({
  page,
}) => {
  await login(page)
  await page.route('**/api/v1/claude/sessions', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.data.sessions[1].state = 'unknown'
    body.data.sessions[1].remote_readiness = 'unknown'
    await route.fulfill({ response, json: body })
  })
  await navigate(page, 'Claude', '/claude')
  await expect(page.getByText('Unknown').first()).toBeVisible()
  await expect(page.getByText('Connected')).toHaveCount(0)
})

test('recovers from invalid and browser-expired session cookies', async ({
  page,
  context,
}) => {
  await login(page)
  await context.clearCookies()
  await context.addCookies([
    { name: 'agentbox_session', value: 'invalid-cookie', url: page.url() },
  ])
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)

  await login(page)
  await context.clearCookies()
  await context.addCookies([
    {
      name: 'agentbox_session',
      value: 'expired-cookie',
      url: page.url(),
      expires: Math.floor(Date.now() / 1000) - 60,
    },
  ])
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
})

test('does not persist session or CSRF material in Web storage', async ({
  page,
}) => {
  await login(page)
  const stored = await page.evaluate(() => ({
    local: Object.entries(localStorage),
    session: Object.entries(sessionStorage),
  }))
  expect(stored).toEqual({ local: [], session: [] })
})

test('fits the viewport and keeps primary controls comfortably tappable', async ({
  page,
}) => {
  await login(page)
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth)

  const mobileMenu = page.getByRole('button', { name: 'Open navigation' })
  if (await mobileMenu.isVisible()) {
    const box = await mobileMenu.boundingBox()
    expect(box?.width).toBeGreaterThanOrEqual(44)
    expect(box?.height).toBeGreaterThanOrEqual(44)
  }
})

test('provides branded 404 and semantic page landmarks', async ({ page }) => {
  await page.goto('/this-route-does-not-exist')
  await expect(
    page.getByRole('heading', { name: 'That route is not part of AgentBox.' }),
  ).toBeVisible()
  await expect(page.getByRole('main')).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Back to sign in' }),
  ).toBeVisible()
})
