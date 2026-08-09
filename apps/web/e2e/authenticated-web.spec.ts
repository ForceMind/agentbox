import { expect, Page, test } from '@playwright/test'

function requiredEnvironment(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`isolated E2E environment is missing ${name}`)
  return value
}

const username = requiredEnvironment('AGENTBOX_E2E_USERNAME')
const password = requiredEnvironment('AGENTBOX_E2E_PASSWORD')

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
