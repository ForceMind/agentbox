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
}) => {
  await login(page)
  await navigate(page, 'Projects', '/projects')
  await expect(page.getByText('Project A')).toBeVisible()
  await page.getByLabel('Project name').fill('E2E Workspace')
  const request = page.waitForRequest(
    (value) =>
      value.url().endsWith('/api/v1/projects') && value.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Create Project' }).click()
  const mutation = await request
  expect(mutation.headers()['x-csrf-token']).toBeTruthy()
  expect(mutation.headers()['idempotency-key']).toBeTruthy()
  await expect(page.getByText('E2E Workspace')).toBeVisible()
})

test('shows structured Git state without dangerous actions', async ({
  page,
}) => {
  await login(page)
  await navigate(page, 'Projects', '/projects')
  await page.getByText('Project A').click()
  await expect(page.getByRole('heading', { name: 'Git' })).toBeVisible()
  await expect(page.getByText('Clean')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Pull' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Push' })).toBeVisible()
  await expect(page.getByRole('button', { name: /force/i })).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: /reset|clean|delete/i }),
  ).toHaveCount(0)
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
  await expect(page.getByRole('heading', { name: 'Project A' })).toBeVisible()
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
  const startRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith('/api/v1/claude/sessions/project-a/start') &&
      request.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Start Session' }).click()
  const request = await startRequest
  const csrf = request.headers()['x-csrf-token']
  expect(csrf).toBeTruthy()
  await expect(page.getByText('Running').first()).toBeVisible()

  const duplicate = await page.evaluate(async (token) => {
    const response = await fetch('/api/v1/claude/sessions/project-a/start', {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRF-Token': token },
    })
    return { status: response.status, body: await response.json() }
  }, csrf)
  expect(duplicate.status).toBe(200)
  expect(duplicate.body.data.outcome).toBe('already_running')

  const stopRequest = page.waitForRequest(
    (stop) =>
      stop.url().endsWith('/api/v1/claude/sessions/project-a/stop') &&
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
  let outputRequests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/sessions/trust-project/output')) {
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
    response.url().endsWith('/sessions/trust-project/output'),
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
