import { expect, test, type Page } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
} from './rc9-assertions'
import { createRc9RouteHold, RC9_LOCALE_SCENARIOS } from './rc9-fixtures'

test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const projectId = `prj_${'5'.repeat(32)}`
const workspaceId = `aws_${'6'.repeat(32)}`
const unsafeProse = 'WORKSPACE_RETURN_SERVER_PROSE_MUST_NOT_SURVIVE'
const project = {
  id: projectId,
  slug: 'workspace-return',
  display_name: '返回 Project 🚀',
  source_type: 'existing',
  state: 'ready',
  repository_url: null,
  default_branch: 'main',
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
  git: null,
  github: null,
  claude_state: null,
}
const row = {
  id: workspaceId,
  project_id: projectId,
  agent_type: 'codex',
  state: 'RUNNING',
  reconciliation_state: 'authoritative',
  generation: 7,
  revision: 1,
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
  last_seen_at: '2026-09-08T00:00:00Z',
  exit_code: null,
  failure_code: null,
}
const runtime = {
  workspace_id: workspaceId,
  project_id: projectId,
  agent_type: 'codex',
  generation: '7',
  binding_revision: '1',
  binding_digest: 'a'.repeat(64),
  state: 'RUNNING',
  reconciliation_state: 'authoritative',
  runtime_epoch: '9',
  process_state: 'RUNNING',
  exit_code: null,
  attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
}

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_workspace_return', data }
}

/** Browser events are simulated; no production hook or test switch is installed. */
async function lifecycle(
  page: Page,
  options: { visible: boolean; online: boolean; events: string[] },
) {
  await page.evaluate(({ visible, online, events }) => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: visible ? 'visible' : 'hidden',
    })
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: online,
    })
    for (const event of events) {
      if (event === 'visibilitychange' || event === 'freeze') {
        document.dispatchEvent(new Event(event))
      } else if (event === 'pageshow') {
        window.dispatchEvent(
          new PageTransitionEvent(event, { persisted: true }),
        )
      } else {
        window.dispatchEvent(new Event(event))
      }
    }
  }, options)
}

for (const locale of RC9_LOCALE_SCENARIOS) {
  test(`returning Workspace revalidates before control for ${locale.name}`, async ({
    page,
  }) => {
    const stopName =
      locale.expectedLocale === 'zh-CN' ? '停止工作区' : 'Stop workspace'
    const failureText =
      locale.expectedLocale === 'zh-CN'
        ? '工作区状态暂不可用。'
        : 'Workspace status is temporarily unavailable.'
    const resumedRead = createRc9RouteHold()
    let statusReads = 0
    let failStatus = false
    let runtimeState = 'RUNNING'
    const mutations: string[] = []
    await page.addInitScript((scenario) => {
      Object.defineProperty(navigator, 'languages', {
        configurable: true,
        get: () => scenario.languages,
      })
      Object.defineProperty(navigator, 'language', {
        configurable: true,
        get: () => scenario.language,
      })
    }, locale)
    await page.route('**/healthz', (route) =>
      route.fulfill({ json: { status: 'ok' } }),
    )
    await page.route('**/api/v1/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (route.request().method() !== 'GET') {
        mutations.push(path)
        await route.abort('blockedbyclient')
      } else if (path === '/api/v1/auth/me') {
        await route.fulfill({
          json: envelope({
            user: { id: 'adm_return', username: 'synthetic-user' },
            session: { id: 'ses_return', expires_at: '2099-01-01T00:00:00Z' },
            csrf_token: 'synthetic-workspace-return-csrf',
          }),
        })
      } else if (path === '/api/v1/projects') {
        await route.fulfill({ json: envelope({ projects: [project] }) })
      } else if (path === '/api/v1/workspaces') {
        await route.fulfill({
          json: { request_id: 'req_return_list', data: { workspaces: [row] } },
        })
      } else if (path === `/api/v1/workspaces/${workspaceId}/status`) {
        statusReads += 1
        if (statusReads === 2) await resumedRead.hold()
        await route.fulfill(
          failStatus
            ? {
                status: 503,
                json: {
                  request_id: 'req_return_failed',
                  error: {
                    code: 'WAW_STATUS_UNAVAILABLE',
                    message: unsafeProse,
                  },
                },
              }
            : {
                json: {
                  request_id: 'req_return_status',
                  data: {
                    ...runtime,
                    state: runtimeState,
                    process_state:
                      runtimeState === 'RUNNING' ? 'RUNNING' : 'NOT_STARTED',
                  },
                },
              },
        )
      } else {
        await route.abort('blockedbyclient')
      }
    })

    try {
      await page.goto(`/workspace?project_id=${projectId}&agent_type=codex`)
      const stop = page.getByRole('button', { name: stopName, exact: true })
      await expect(stop).toBeEnabled()
      await assertRc9DocumentLocale(page, locale.expectedLocale)
      await expect(page.locator('time')).toBeVisible()
      expect(statusReads).toBe(1)

      await stop.click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await lifecycle(page, {
        visible: false,
        online: false,
        events: ['offline', 'visibilitychange', 'pagehide', 'freeze'],
      })
      await expect(stop).toBeDisabled()
      await expect(page.getByRole('dialog')).toBeHidden()
      await expect(page.locator('time')).toHaveCount(0)
      await lifecycle(page, {
        visible: true,
        online: false,
        events: ['pageshow', 'visibilitychange'],
      })
      await expect(stop).toBeDisabled()
      expect(statusReads).toBe(1)

      await lifecycle(page, {
        visible: true,
        online: true,
        events: ['online', 'pageshow', 'visibilitychange', 'online'],
      })
      await resumedRead.waitUntilHeld()
      await expect(stop).toBeDisabled()
      expect(statusReads).toBe(2)
      expect(mutations).toEqual([])
      resumedRead.release()
      await expect(stop).toBeEnabled()
      await expect(page.locator('time')).toBeVisible()
      await expect(page.getByRole('dialog')).toBeHidden()
      expect(statusReads).toBe(2)

      // The fresh Runtime can stop while the retained metadata row is RUNNING.
      // Matching identity alone must not revive controls for the old state.
      runtimeState = 'STOPPED'
      await lifecycle(page, {
        visible: false,
        online: true,
        events: ['visibilitychange'],
      })
      await lifecycle(page, {
        visible: true,
        online: true,
        events: ['visibilitychange', 'pageshow'],
      })
      await expect(page.locator('time')).toBeVisible()
      await expect(stop).toBeDisabled()
      await expect(page.getByRole('dialog')).toBeHidden()
      expect(statusReads).toBe(3)
      expect(mutations).toEqual([])

      failStatus = true
      await lifecycle(page, {
        visible: false,
        online: true,
        events: ['visibilitychange'],
      })
      await lifecycle(page, {
        visible: true,
        online: true,
        events: ['visibilitychange', 'pageshow'],
      })
      await expect(page.getByText(failureText, { exact: true })).toBeVisible()
      await expect(stop).toBeDisabled()
      await expect(page.locator('time')).toHaveCount(0)
      expect(statusReads).toBe(4)
      expect(mutations).toEqual([])
      await assertRc9CanaryAbsent(page, unsafeProse)
      await assertRc9NoHorizontalOverflow(page)
      await assertRc9InteractiveTargets(page)
    } finally {
      resumedRead.dispose()
    }
  })
}
