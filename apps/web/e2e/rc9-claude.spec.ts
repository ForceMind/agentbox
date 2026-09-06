import {
  expect,
  test,
  type Locator,
  type Page,
  type Route,
} from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9Title,
} from './rc9-assertions'
import {
  createRc9DocumentContext,
  createRc9RouteHold,
  RC9_LOCALE_SCENARIOS,
  RC9_VIEWPORTS,
} from './rc9-fixtures'

// Claude can render sensitive session output after an explicit reveal. Retained
// browser artifacts remain disabled independently of the shared configuration.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const statusData = {
  installed: true,
  version: '1.fixture',
  authentication: 'unknown',
  capabilities: {
    remote_control: 'supported',
    remote_start: 'supported',
    version: 'supported',
  },
  tmux_installed: true,
  tmux_version: '3.fixture',
  managed_sessions: 1,
  unmanaged_sessions: 0,
  workspace_interaction_warnings: 1,
  diagnostics: [
    {
      code: 'CLAUDE_SYNTHETIC_DIAGNOSTIC',
      severity: 'warning',
      summary: 'RC9-CLAUDE-DIAGNOSTIC-SUMMARY-CANARY',
      remediation: 'RC9-CLAUDE-DIAGNOSTIC-REMEDIATION-CANARY',
    },
  ],
}

const stoppedSession = {
  project_id: 'project-a',
  display_name: '用户项目 🚀',
  state: 'stopped',
  managed: true,
  session_name: 'agentbox-claude-project-a',
  attach_command: 'tmux attach-session -t =agentbox-claude-project-a',
  workspace_state: 'requires_user_confirmation',
  tmux_running: false,
  remote_readiness: 'unknown',
}

const copy = {
  en: {
    refresh: 'Refresh',
    loading: 'Inspecting Claude and managed sessions…',
    start: 'Start Session',
    stop: 'Stop Session',
    reveal: 'Reveal',
    hide: 'Hide',
    starting: 'Starting',
    stopped: 'Stopped',
    empty: 'No configured projects',
    unavailable: 'Claude status unavailable',
  },
  'zh-CN': {
    refresh: '刷新',
    loading: '正在检查 Claude 和托管会话…',
    start: '启动会话',
    stop: '停止会话',
    reveal: '显示',
    hide: '隐藏',
    starting: '正在启动',
    stopped: '已停止',
    empty: '没有已配置的 Project',
    unavailable: 'Claude 状态暂不可用',
  },
} as const

const authData = {
  user: { id: 'adm_rc9_claude', username: 'synthetic-user' },
  session: { id: 'ses_rc9_claude', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'csrf-rc9-claude',
}

async function fulfillJson(route: Route, status: number, body: object) {
  await route.fulfill({ status, json: body })
}

async function assertClaudeTechnicalRendering(technical: Locator) {
  await expect(technical).toHaveAttribute('lang', 'en')
  await expect(technical).toHaveAttribute('dir', 'ltr')
  await expect(technical).toHaveAttribute('translate', 'no')
  expect((await technical.textContent()) ?? '').toMatch(/^[\x20-\x7e]+$/)
}

async function installSharedRoutes(page: Page) {
  await page.route('**/api/v1/auth/me', (route) =>
    fulfillJson(route, 200, {
      api_version: 'v1',
      request_id: 'req_rc9_claude_auth',
      data: authData,
    }),
  )
  await page.route('**/healthz', (route) =>
    fulfillJson(route, 200, { status: 'ok' }),
  )
  await page.route('**/api/v1/meta', (route) =>
    fulfillJson(route, 200, {
      name: 'AgentBox',
      version: '0.3.0-rc.9',
      api_version: 'v1',
      environment: 'test',
    }),
  )
}

test('covers the Claude route matrix without retaining server prose or hidden output', async ({
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
      const initialStatus = createRc9RouteHold()
      const knownAction = createRc9RouteHold()
      const expected = copy[locale.expectedLocale]
      const knownActionCanary = `RC9-KNOWN-CLAUDE-ACTION-${viewport.name}-${locale.name}`
      const unknownActionCanary = `RC9-UNKNOWN-CLAUDE-ACTION-${viewport.name}-${locale.name}`
      const unavailableCanary = `RC9-UNKNOWN-CLAUDE-STATUS-${viewport.name}-${locale.name}`
      const outputCanary = `RC9-EXPLICIT-CLAUDE-OUTPUT-${viewport.name}-${locale.name} <img src=x onerror=alert(1)>`
      let statusCalls = 0
      let sessionListCalls = 0
      let startCalls = 0

      try {
        const page = await context.newPage()
        await installSharedRoutes(page)
        await page.route('**/api/v1/claude', async (route) => {
          statusCalls += 1
          if (statusCalls === 1) await initialStatus.hold()
          if (statusCalls === 3) {
            await fulfillJson(route, 503, {
              request_id: 'req_rc9_claude_status_error',
              error: {
                code: 'CLAUDE_UNKNOWN_STATUS',
                message: unavailableCanary,
              },
            })
            return
          }
          await fulfillJson(route, 200, {
            api_version: 'v1',
            request_id: `req_rc9_claude_status_${statusCalls}`,
            data: statusData,
          })
        })
        await page.route('**/api/v1/claude/sessions', async (route) => {
          sessionListCalls += 1
          await fulfillJson(route, 200, {
            api_version: 'v1',
            request_id: `req_rc9_claude_sessions_${sessionListCalls}`,
            data: {
              sessions: sessionListCalls === 1 ? [stoppedSession] : [],
            },
          })
        })
        await page.route(
          '**/api/v1/claude/sessions/project-a/start',
          async (route) => {
            startCalls += 1
            if (startCalls <= 2) {
              const known = startCalls === 1
              if (known) await knownAction.hold()
              await fulfillJson(route, 503, {
                request_id: `req_rc9_claude_start_${startCalls}`,
                error: {
                  code: known
                    ? 'CLAUDE_RUNTIME_UNAVAILABLE'
                    : 'CLAUDE_UNKNOWN_ACTION',
                  message: known ? knownActionCanary : unknownActionCanary,
                },
              })
              return
            }
            await fulfillJson(route, 200, {
              api_version: 'v1',
              request_id: 'req_rc9_claude_start_ok',
              data: {
                outcome: 'started',
                session: {
                  ...stoppedSession,
                  state: 'starting',
                  tmux_running: true,
                },
              },
            })
          },
        )
        await page.route('**/api/v1/claude/sessions/project-a/stop', (route) =>
          fulfillJson(route, 200, {
            api_version: 'v1',
            request_id: 'req_rc9_claude_stop',
            data: { outcome: 'stopped', session: stoppedSession },
          }),
        )
        await page.route(
          '**/api/v1/claude/sessions/project-a/output',
          (route) =>
            fulfillJson(route, 200, {
              api_version: 'v1',
              request_id: 'req_rc9_claude_output',
              data: {
                project_id: 'project-a',
                session_name: 'agentbox-claude-project-a',
                output: outputCanary,
                truncated: true,
                sensitive: true,
              },
            }),
        )

        await page.goto('/claude')
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9Title(page, /Claude · AgentBox/)
        await initialStatus.waitUntilHeld()
        await expect(page.getByRole('status')).toHaveText(expected.loading)
        initialStatus.release()

        await expect(
          page.getByRole('heading', { name: 'Claude' }),
        ).toBeVisible()
        await expect(
          page.getByRole('heading', { name: '用户项目 🚀' }),
        ).toBeVisible()
        await assertRc9CanaryAbsent(
          page,
          'RC9-CLAUDE-DIAGNOSTIC-SUMMARY-CANARY',
        )
        await assertRc9CanaryAbsent(
          page,
          'RC9-CLAUDE-DIAGNOSTIC-REMEDIATION-CANARY',
        )
        await assertClaudeTechnicalRendering(page.locator('code bdi').first())
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)

        const start = page.getByRole('button', { name: expected.start })
        const sessionAction = page
          .locator('.claude-session-card .action-row button')
          .first()
        const refresh = page.getByRole('button', { name: expected.refresh })
        await start.click()
        await knownAction.waitUntilHeld()
        await expect(sessionAction).toBeDisabled()
        await expect(refresh).toBeDisabled()
        knownAction.release()
        const actionError = page.locator('.claude-action-error')
        await expect(actionError).toBeVisible()
        await assertRc9CanaryAbsent(page, knownActionCanary)
        await assertClaudeTechnicalRendering(actionError.locator('bdi').first())

        await start.click()
        await expect(actionError).toBeVisible()
        await assertRc9CanaryAbsent(page, unknownActionCanary)

        await start.click()
        await expect(
          page.getByText(expected.starting, { exact: true }),
        ).toBeVisible()
        await page.getByRole('button', { name: expected.reveal }).click()
        await expect(
          page.getByText(outputCanary, { exact: true }),
        ).toBeVisible()
        await expect(page.locator('.sensitive-output img')).toHaveCount(0)
        expect(await page.evaluate(() => localStorage.length)).toBe(0)
        expect(await page.evaluate(() => sessionStorage.length)).toBe(0)

        await page.getByRole('button', { name: expected.hide }).click()
        await expect(page.getByText(outputCanary, { exact: true })).toHaveCount(
          0,
        )
        await assertRc9CanaryAbsent(page, outputCanary)

        await page.getByRole('button', { name: expected.stop }).click()
        await expect(
          page.locator('.claude-session-card .status-badge').first(),
        ).toHaveText(expected.stopped)

        await refresh.click()
        await expect(
          page.getByRole('heading', { name: expected.empty }),
        ).toBeVisible()

        await refresh.click()
        await expect(
          page.getByRole('heading', { name: expected.unavailable }),
        ).toBeVisible()
        await assertRc9CanaryAbsent(page, unavailableCanary)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        initialStatus.dispose()
        knownAction.dispose()
        await context.close()
      }
    }
  }
})
