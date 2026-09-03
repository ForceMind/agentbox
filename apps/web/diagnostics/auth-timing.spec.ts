import { appendFile } from 'node:fs/promises'
import { expect, test, type Request, type Page } from '@playwright/test'

const username = process.env.AGENTBOX_E2E_USERNAME
const password = process.env.AGENTBOX_E2E_PASSWORD
const resultsPath = process.env.AGENTBOX_E2E_TIMING_RESULTS
if (
  !username ||
  !password ||
  !resultsPath ||
  process.env.AGENTBOX_E2E_AUTH_TIMING !== '1'
) {
  throw new Error('auth timing requires the isolated E2E harness')
}

// The normal suite is untouched. Catch diagnostic assertions before Playwright
// can retain an error/DOM context; the harness fails on any numeric failed result.
for (const valid of [true, false]) {
  test(
    valid ? 'successful login timing' : 'invalid login timing',
    async ({ page }, info) => {
      // Browser timestamps are monotonic offsets from the Sign in click.
      const result = {
        profile: info.project.name === 'desktop' ? 1 : 2,
        valid: Number(valid),
        passed: 0,
        ui_within_5s: 0,
        assertion_within_5s: 0,
        request_ms: -1,
        response_ms: -1,
        finished_ms: -1,
        visible_ms: -1,
        status: 0,
        request_failed: 0,
        measurement_error: 0,
      }
      let started = 0
      let loginRequest: Request | undefined
      page.on('request', (request) => {
        if (
          request.method() === 'POST' &&
          new URL(request.url()).pathname === '/api/v1/auth/login'
        ) {
          loginRequest = request
          result.request_ms = performance.now() - started
        }
      })
      page.on('response', (response) => {
        if (response.request() === loginRequest) {
          result.status = response.status()
          result.response_ms = performance.now() - started
        }
      })
      page.on('requestfinished', (request) => {
        if (request === loginRequest)
          result.finished_ms = performance.now() - started
      })
      page.on('requestfailed', (request) => {
        if (request === loginRequest) result.request_failed = 1
      })
      try {
        // Drain earlier samples before this fresh-context login so a stale
        // successful observation cannot substitute for this request's evidence.
        await readMetrics(page)
        await page.goto('/login', { timeout: 5_000 })
        await page.getByLabel('Username').fill(username)
        await page
          .getByLabel('Password')
          .fill(valid ? password : 'an incorrect test passphrase')
        started = performance.now()
        await page
          .getByRole('button', { name: 'Sign in' })
          .click({ timeout: 5_000 })
        if (valid) {
          await expect(
            page.getByRole('heading', { name: 'Dashboard' }),
          ).toBeVisible({ timeout: 5_000 })
        } else {
          await expect(page.getByRole('alert')).toContainText(
            'Invalid credentials',
            { timeout: 5_000 },
          )
          await expect(page).toHaveURL(/\/login$/, { timeout: 5_000 })
        }
        result.visible_ms = performance.now() - started
        result.assertion_within_5s = 1
        result.ui_within_5s = Number(result.visible_ms <= 5_000)
        result.passed = Number(
          result.status === (valid ? 200 : 401) && result.request_failed === 0,
        )
      } catch {
        // No error strings, call logs, page content or assertion attachments.
        result.measurement_error = 1
      } finally {
        try {
          await emitMetrics(page, valid ? 200 : 401)
        } catch {
          result.measurement_error = 1
          result.passed = 0
        }
        console.log(JSON.stringify({ label: 'auth_browser', ...result }))
        await appendFile(resultsPath, `${JSON.stringify(result)}\n`)
      }
    },
  )
}

type Metric = { sample: number; phase: string; ms: number }

async function readMetrics(page: Page): Promise<Metric[]> {
  const response = await page.request.get('/api/__e2e/auth-timing', {
    timeout: 2_000,
  })
  const metrics: unknown = await response.json()
  // Serialize only a fixed allowlist and bounded numeric records.
  if (
    response.status() !== 200 ||
    !metrics ||
    typeof metrics !== 'object' ||
    !('events' in metrics) ||
    !Array.isArray(metrics.events) ||
    metrics.events.length > 256
  ) {
    throw new Error('timing metrics unavailable')
  }
  const phases = new Set([
    'request_start_ms',
    'request_kind',
    'request_total_ms',
    'status',
    'executor_total_ms',
    'admission_ms',
    'pool_queue_ms',
    'worker_ms',
    'argon2_ms',
    'begin_immediate_ms',
    'loop_lag_ms',
    'dropped',
    'unhandled_error',
  ])
  const events: Metric[] = []
  for (const event of metrics.events) {
    if (
      event &&
      phases.has(event.phase) &&
      Number.isSafeInteger(event.sample) &&
      event.sample >= 0 &&
      event.sample <= 128 &&
      typeof event.ms === 'number' &&
      Number.isFinite(event.ms) &&
      event.ms >= 0
    ) {
      if (
        (event.phase === 'dropped' || event.phase === 'unhandled_error') &&
        event.ms !== 0
      )
        throw new Error('incomplete timing metadata')
      events.push({ sample: event.sample, phase: event.phase, ms: event.ms })
    } else {
      throw new Error('invalid timing metadata')
    }
  }
  for (const phase of ['dropped', 'loop_lag_ms']) {
    const summary = events.filter((event) => event.phase === phase)
    if (summary.length !== 1 || summary[0].sample !== 0) {
      throw new Error('missing timing summary')
    }
  }
  return events
}

async function emitMetrics(page: Page, expectedStatus: number) {
  const events = await readMetrics(page)
  const logins = events.filter(
    (event) => event.phase === 'request_kind' && event.ms === 1,
  )
  if (logins.length !== 1 || logins[0].sample === 0) {
    throw new Error('missing current login timing')
  }
  const current = events.filter((event) => event.sample === logins[0].sample)
  for (const phase of [
    'request_start_ms',
    'request_kind',
    'request_total_ms',
    'status',
    'executor_total_ms',
    'admission_ms',
    'pool_queue_ms',
    'worker_ms',
    'argon2_ms',
  ]) {
    if (current.filter((event) => event.phase === phase).length !== 1) {
      throw new Error('incomplete current login timing')
    }
  }
  if (
    !current.some((event) => event.phase === 'begin_immediate_ms') ||
    !current.some(
      (event) => event.phase === 'status' && event.ms === expectedStatus,
    )
  ) {
    throw new Error('incomplete current login timing')
  }
  for (const event of events) {
    console.log(JSON.stringify({ label: 'auth_backend', ...event }))
  }
}
