import { expect, test, type Page } from '@playwright/test'

import { assertRc9CanaryAbsent } from './rc9-assertions'
import { createRc9RouteHold } from './rc9-fixtures'

// Deliberately separate from the metadata screenshot fixture. These tests run
// real App/AuthProvider/API client/product hooks, and can render synthetic Pair
// or pane output. No screenshots (including manual ones), trace or video.
test.use({ screenshot: 'off', trace: 'off', video: 'off', locale: 'en' })

const MARKER = 'management-auth-scope-fixture'
const PROJECT = `prj_${'c'.repeat(32)}`
const SESSION_NAME = `agentbox-claude-${PROJECT}-scope-fixture`
const PAIR_API = '/api/v1/codex/pair-codes'
const OUTPUT_API = `/api/v1/claude/sessions/${PROJECT}/output`
const SERVER_PROSE = 'synthetic-management-auth-server-prose-must-not-render'
const A = {
  csrf: 'csrf-management-fixture-a',
  pair: 'PAIR-SESSION-A-FIXTURE-7294',
  output: 'CLAUDE-SESSION-A-OUTPUT-FIXTURE-7294',
}
const B = {
  csrf: 'csrf-management-fixture-b',
  pair: 'PAIR-SESSION-B-FIXTURE-5917',
  output: 'CLAUDE-SESSION-B-OUTPUT-FIXTURE-5917',
}

type Agent = 'codex' | 'claude'
type RequestRecord = { path: string; method: string; csrf: string | null }

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_management_scope_browser', data }
}

// Exact closed wire payloads, validated with the production decoders before CI.
export function scopePayloads(owner: 'a' | 'b') {
  const values = owner === 'a' ? A : B
  return {
    auth: envelope({
      user: { id: `adm_${'a'.repeat(32)}`, username: MARKER },
      session: {
        id: `ses_${owner.repeat(32)}`,
        expires_at: '2030-01-01T00:00:00Z',
      },
      csrf_token: values.csrf,
    }),
    codex: envelope({
      installed: true,
      version: '1.scope.fixture',
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
      remote_state: 'stopped',
      remote_confidence: 'reported',
      diagnostics: [],
    }),
    claude: envelope({
      installed: true,
      version: '1.scope.fixture',
      authentication: 'authenticated',
      capabilities: {
        remote_control: 'supported',
        remote_start: 'supported',
        version: 'supported',
      },
      tmux_installed: true,
      tmux_version: '3.scope.fixture',
      managed_sessions: 1,
      unmanaged_sessions: 0,
      workspace_interaction_warnings: 0,
      diagnostics: [],
    }),
    sessions: envelope({
      sessions: [
        {
          project_id: PROJECT,
          display_name: 'Management fixture',
          state: 'running',
          managed: true,
          session_name: SESSION_NAME,
          attach_command: `tmux attach-session -t =${SESSION_NAME}`,
          workspace_state: 'unknown',
          tmux_running: true,
          remote_readiness: 'ready',
        },
      ],
    }),
    pair: envelope({
      pair_code: values.pair,
      expires_at: null,
      display_once: true,
    }),
    output: envelope({
      project_id: PROJECT,
      session_name: SESSION_NAME,
      output: values.output,
      truncated: false,
      sensitive: true,
    }),
  }
}

async function fixtures(page: Page, agent: Agent) {
  const first = createRc9RouteHold()
  const second = createRc9RouteHold()
  const state = {
    requests: [] as RequestRecord[],
    completedSensitive: [] as number[],
    meCalls: 0,
    logoutCalls: 0,
    sensitiveCalls: 0,
    unexpected: [] as string[],
    errors: [] as string[],
    first,
    second,
  }
  page.on('pageerror', (error) => state.errors.push(error.message))
  page.on('websocket', () => state.unexpected.push('WebSocket connection'))
  const baseOrigin = new URL(process.env.PLAYWRIGHT_BASE_URL!).origin
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.origin !== baseOrigin)
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
  })
  await page.route(/\/(?:api\/|healthz|readyz)/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    // Defense in depth: a foreign URL must never receive synthetic auth or
    // sensitive fixture content, even if routing precedence changes later.
    if (url.origin !== baseOrigin) {
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
      return
    }
    const path = `${url.pathname}${url.search}`
    const method = request.method()
    state.requests.push({
      path,
      method,
      csrf: request.headers()['x-csrf-token'] ?? null,
    })
    let status = 200
    let body: unknown
    if (path === '/api/v1/auth/me' && method === 'GET') {
      state.meCalls += 1
      body = scopePayloads(state.meCalls === 1 ? 'a' : 'b').auth
    } else if (path === '/api/v1/auth/logout' && method === 'POST') {
      state.logoutCalls += 1
      status = state.logoutCalls === 1 ? 403 : 500
      body = {
        request_id: 'req_management_scope_logout',
        error: {
          code: status === 403 ? 'AUTH_CSRF_INVALID' : 'INTERNAL_ERROR',
          message: SERVER_PROSE,
        },
      }
    } else if (
      path === (agent === 'codex' ? PAIR_API : OUTPUT_API) &&
      method === (agent === 'codex' ? 'POST' : 'GET')
    ) {
      state.sensitiveCalls += 1
      const ordinal = state.sensitiveCalls
      const payloads = scopePayloads(ordinal === 1 ? 'a' : 'b')
      const sensitive = JSON.stringify(
        agent === 'codex' ? payloads.pair : payloads.output,
      )
      if (ordinal > 2)
        state.unexpected.push(`hidden sensitive replay ${method} ${path}`)
      if (ordinal === 1) await first.hold()
      if (ordinal === 2) await second.hold()
      await route.fulfill({
        status: 200,
        body: sensitive,
        contentType: 'application/json',
        headers: { 'Cache-Control': 'no-store' },
      })
      state.completedSensitive.push(ordinal)
      return
    } else {
      const payloads = scopePayloads(state.meCalls > 1 ? 'b' : 'a')
      const metadata: Record<string, unknown> = {
        '/healthz': { status: 'ok' },
        '/api/v1/codex/status': payloads.codex,
        '/api/v1/claude': payloads.claude,
        '/api/v1/claude/sessions': payloads.sessions,
      }
      if (method === 'GET' && path in metadata) body = metadata[path]
      else {
        state.unexpected.push(`${method} ${path}`)
        status = 500
        body = { error: { code: 'UNEXPECTED_REQUEST', message: SERVER_PROSE } }
      }
    }
    await route.fulfill({
      status,
      json: body,
      headers: { 'Cache-Control': 'no-store' },
    })
  })
  // Playwright applies the last registered route first. Guard every request
  // before falling back to the narrower API fixture or own-origin assets.
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== baseOrigin) {
      state.unexpected.push(`${request.method()} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
      return
    }
    await route.fallback()
  })
  return state
}

async function explicitSensitiveAction(page: Page, agent: Agent) {
  if (agent === 'codex') {
    await page
      .getByRole('button', { name: 'Pair New Device', exact: true })
      .click()
    await page
      .getByRole('button', { name: 'Generate Code', exact: true })
      .click()
  } else await page.getByRole('button', { name: 'Reveal', exact: true }).click()
}

async function replaceSessionThroughFailedLogout(page: Page) {
  const signOut = page.getByRole('button', { name: 'Sign out', exact: true })
  if (!(await signOut.isVisible()))
    await page
      .getByRole('button', { name: 'Open navigation', exact: true })
      .click()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(
    page
      .getByRole('alert')
      .filter({ hasText: 'Logout could not be completed' })
      .last(),
  ).toBeVisible()
  // Mobile logout lives in the real navigation dialog. Dismiss it so later
  // assertions exercise visible page actions instead of bypassing inertness.
  const drawer = page.locator('#mobile-navigation')
  if (await drawer.isVisible())
    await drawer
      .getByRole('button', { name: 'Close navigation', exact: true })
      .click()
}

for (const agent of ['codex', 'claude'] as const) {
  for (const timing of ['shown', 'pending'] as const) {
    test(`${agent} ${timing} sensitive owner A is revoked by real logout recovery to B without replay`, async ({
      page,
    }) => {
      const state = await fixtures(page, agent)
      const path = agent === 'codex' ? PAIR_API : OUTPUT_API
      const valueA = agent === 'codex' ? A.pair : A.output
      const valueB = agent === 'codex' ? B.pair : B.output
      try {
        await page.goto(`/${agent}`)
        await expect(
          page.getByRole('heading', {
            name: agent === 'codex' ? 'Codex' : 'Claude',
            level: 1,
            exact: true,
          }),
        ).toBeVisible()
        await expect(page.locator('.app-frame')).toContainText(MARKER)
        await explicitSensitiveAction(page, agent)
        await state.first.waitUntilHeld()
        if (timing === 'shown') {
          state.first.release()
          await expect(page.getByText(valueA, { exact: true })).toBeVisible()
        }

        await replaceSessionThroughFailedLogout(page)
        await expect(page).toHaveURL(`/${agent}`)
        await expect(page.locator('input[type="password"]')).toHaveCount(0)
        await expect(
          page.getByRole('heading', {
            name: agent === 'codex' ? 'Codex' : 'Claude',
            level: 1,
            exact: true,
          }),
        ).toBeVisible()
        await expect(
          page.getByRole('button', {
            name: agent === 'codex' ? 'Pair New Device' : 'Reveal',
            exact: true,
          }),
        ).toBeEnabled()
        await assertRc9CanaryAbsent(page, valueA)
        expect(
          state.requests.filter((request) =>
            request.path.startsWith('/api/v1/auth/'),
          ),
        ).toEqual([
          { path: '/api/v1/auth/me', method: 'GET', csrf: null },
          { path: '/api/v1/auth/logout', method: 'POST', csrf: A.csrf },
          { path: '/api/v1/auth/me', method: 'GET', csrf: null },
          { path: '/api/v1/auth/logout', method: 'POST', csrf: B.csrf },
        ])
        const sensitiveRequests = () =>
          state.requests.filter((request) =>
            /\/(?:pair-codes|output)(?:[/?]|$)/.test(request.path),
          )
        expect(sensitiveRequests()).toEqual([
          {
            path,
            method: agent === 'codex' ? 'POST' : 'GET',
            csrf: agent === 'codex' ? A.csrf : null,
          },
        ])

        // A fresh B action stays pending while the obsolete server reply is
        // released after owner cancellation. It must not contaminate B/pending.
        // Aborted fetches need not consume that reply; late callback/finally
        // isolation is proved separately by the unchanged ownership unit tests.
        await explicitSensitiveAction(page, agent)
        await state.second.waitUntilHeld()
        const pending = page.getByRole('button', {
          name: agent === 'codex' ? 'Generating…' : 'Loading…',
          exact: true,
        })
        await expect(pending).toBeDisabled()
        if (timing === 'pending') state.first.release()
        await expect.poll(() => state.completedSensitive.includes(1)).toBe(true)
        await assertRc9CanaryAbsent(page, valueA)
        await expect(pending).toBeDisabled()
        state.second.release()
        await expect(page.getByText(valueB, { exact: true })).toBeVisible()
        await assertRc9CanaryAbsent(page, valueA)
        expect(sensitiveRequests()).toEqual([
          {
            path,
            method: agent === 'codex' ? 'POST' : 'GET',
            csrf: agent === 'codex' ? A.csrf : null,
          },
          {
            path,
            method: agent === 'codex' ? 'POST' : 'GET',
            csrf: agent === 'codex' ? B.csrf : null,
          },
        ])
        await page.getByRole('button', { name: 'Hide', exact: true }).click()
        await assertRc9CanaryAbsent(page, valueA)
        await assertRc9CanaryAbsent(page, valueB)
        await assertRc9CanaryAbsent(page, SERVER_PROSE)
        expect(state.sensitiveCalls).toBe(2)
        expect(state.unexpected).toEqual([])
        expect(state.errors).toEqual([])
        expect(
          await page.evaluate(() => ({
            local: Object.entries(localStorage),
            session: Object.entries(sessionStorage),
          })),
        ).toEqual({ local: [], session: [] })
      } finally {
        state.first.dispose()
        state.second.dispose()
      }
    })
  }
}
