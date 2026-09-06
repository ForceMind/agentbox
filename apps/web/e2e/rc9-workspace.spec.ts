import { expect, test, type Page, type Route } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
  assertRc9FocusRestored,
  assertRc9InteractiveTargets,
  assertRc9ModalDialog,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
  assertRc9Title,
} from './rc9-assertions'
import {
  createRc9DocumentContext,
  createRc9RouteHold,
  RC9_LOCALE_SCENARIOS,
  RC9_VIEWPORTS,
} from './rc9-fixtures'

test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const projectId = `prj_${'1'.repeat(32)}`
const workspaceId = `aws_${'2'.repeat(32)}`
const alternateWorkspaceId = `aws_${'4'.repeat(32)}`
const attachmentId = `att_${'3'.repeat(32)}`
const generation = '7'
const serverCanary = 'RC9-WORKSPACE-SERVER-PROSE-CANARY-8X4Q'
const fixtureOutput = 'RC9 synthetic terminal output'
const fixtureInput = 'rc9 synthetic input'

const project = {
  id: projectId,
  slug: 'user-workspace',
  display_name: '用户 Project 🚀 长名称用于验证移动端安全换行',
  source_type: 'existing',
  state: 'ready',
  repository_url: null,
  default_branch: 'main',
  created_at: '2026-09-03T00:00:00Z',
  updated_at: '2026-09-03T00:00:00Z',
  git: null,
  github: null,
  claude_state: null,
}

const authData = {
  user: { id: `adm_${'9'.repeat(32)}`, username: '用户管理员' },
  session: {
    id: `ses_${'8'.repeat(32)}`,
    expires_at: '2026-12-31T00:00:00Z',
  },
  csrf_token: 'csrf-rc9-workspace',
}

const localeCopy = {
  en: {
    title: 'Interactive workspace',
    error: 'Workspace status is temporarily unavailable.',
    loadingProjects: 'Loading Projects…',
    unregistered:
      'This AgentType is not registered and cannot start a workspace.',
    notFound: 'The requested workspace was not found.',
    identityChanged:
      'The Project or Runtime identity changed. Refresh and try again.',
    recovery:
      'Runtime recovery review is required. Workspace operations are paused.',
    providerUnavailable:
      'The managed browser trust provider is unavailable, so no terminal ticket was requested.',
    connected: 'Connected',
    detached: 'Disconnected',
    connect: 'Connect terminal',
    reconnect: 'Reconnect',
    detach: 'Disconnect',
    sendInput: 'Send input',
    stop: 'Stop workspace',
    confirmTitle: 'Confirm workspace stop',
    cancel: 'Cancel',
    confirmStop: 'Confirm stop',
    stoppedNotice:
      'The managed process stopped. Project and Git changes were preserved.',
  },
  'zh-CN': {
    title: '交互式工作区',
    error: '工作区状态暂不可用。',
    loadingProjects: '正在加载 Project…',
    unregistered: '当前 AgentType 尚未注册，无法启动工作区。',
    notFound: '未找到请求的工作区。',
    identityChanged: 'Project 或 Runtime 身份已变化，请刷新后重试。',
    recovery: 'Runtime 需要恢复核对，工作区操作已暂停。',
    providerUnavailable:
      '受管浏览器信任 provider 不可用，因此未请求终端 ticket。',
    connected: '已连接',
    detached: '已断开',
    connect: '连接终端',
    reconnect: '重新连接',
    detach: '断开连接',
    sendInput: '发送输入',
    stop: '停止工作区',
    confirmTitle: '确认停止工作区',
    cancel: '取消',
    confirmStop: '确认停止',
    stoppedNotice: '受管进程已停止，Project 和 Git 修改已保留。',
  },
} as const

type HarnessEvidence = Readonly<{
  events: readonly string[]
  inputs: readonly Readonly<{
    byteLength: number
    endsWithCarriageReturn: boolean
  }>[]
  resizes: readonly Readonly<{ columns: number; rows: number }>[]
}>

function envelope(data: unknown, requestId = 'req_rc9_workspace') {
  return { api_version: 'v1', request_id: requestId, data }
}

async function fulfillJson(route: Route, status: number, body: object) {
  await route.fulfill({ status, json: body })
}

function workspaceRow(
  state: 'RUNNING' | 'STOPPED' | 'UNKNOWN',
  reconciliationState = 'authoritative',
) {
  return {
    id: workspaceId,
    project_id: projectId,
    agent_type: 'codex',
    state,
    reconciliation_state: reconciliationState,
    generation: Number(generation),
    revision: 1,
    created_at: '2026-09-03T00:00:00Z',
    updated_at: '2026-09-03T00:00:00Z',
    last_seen_at: '2026-09-03T00:00:00Z',
    exit_code: null,
    failure_code: null,
  }
}

function runtimeStatus(
  state: 'RUNNING' | 'STOPPED' | 'UNKNOWN',
  options: Readonly<{
    reconciliationState?: string
    workspaceId?: string
  }> = {},
) {
  return {
    workspace_id: options.workspaceId ?? workspaceId,
    project_id: projectId,
    agent_type: 'codex',
    generation,
    binding_revision: '1',
    binding_digest: 'a'.repeat(64),
    state,
    reconciliation_state: options.reconciliationState ?? 'authoritative',
    runtime_epoch: '9',
    process_state: state,
    exit_code: null,
    attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
  }
}

function attachmentTicket() {
  return {
    protocol_version: 1,
    request_id: `req_${'1'.repeat(32)}`,
    ticket: `wat_${'a'.repeat(32)}`,
    workspace_id: workspaceId,
    project_id: projectId,
    agent_type: 'codex',
    attachment_id: attachmentId,
    mode: 'writer',
    lease_number: '4',
    generation,
    binding_revision: '1',
    binding_digest: 'a'.repeat(64),
    auth_epoch: '5',
    api_authority_epoch: '6',
    runtime_host_installation_id: `wri_${'4'.repeat(32)}`,
    runtime_host_installation_revision: '7',
    runtime_epoch: '9',
    expires_at: '2026-12-31T00:00:00Z',
  }
}

type Mutation = Readonly<{ path: string; body: string | null }>

async function installSuccessRoutes(page: Page): Promise<Mutation[]> {
  const mutations: Mutation[] = []
  let lifecycle: 'RUNNING' | 'STOPPED' = 'RUNNING'
  await page.route('**/healthz', (route) =>
    fulfillJson(route, 200, { status: 'ok' }),
  )
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'POST') {
      mutations.push({ path: url.pathname, body: request.postData() })
    }
    if (url.pathname === '/api/v1/projects') {
      await fulfillJson(route, 200, envelope({ projects: [project] }))
      return
    }
    if (url.pathname === '/api/v1/workspaces') {
      await fulfillJson(route, 200, {
        request_id: 'req_rc9_workspace_list',
        data: { workspaces: [workspaceRow(lifecycle)] },
      })
      return
    }
    if (url.pathname === `/api/v1/workspaces/${workspaceId}/status`) {
      await fulfillJson(route, 200, {
        request_id: 'req_rc9_workspace_status',
        data: runtimeStatus(lifecycle),
      })
      return
    }
    if (
      url.pathname === `/api/v1/workspaces/${workspaceId}/attachments` ||
      url.pathname === `/api/v1/workspaces/${workspaceId}/reconnect`
    ) {
      await fulfillJson(route, 200, attachmentTicket())
      return
    }
    if (url.pathname === `/api/v1/workspaces/${workspaceId}/detach`) {
      await fulfillJson(route, 200, {
        request_id: `req_${'5'.repeat(32)}`,
        detach_operation_id: `dop_${'6'.repeat(32)}`,
        workspace_id: workspaceId,
        attachment_id: attachmentId,
        generation,
        lease_number: '4',
        result: 'detached',
        cleanup_state: 'ATTACH_PTY_CLOSED',
        state: 'RUNNING',
      })
      return
    }
    if (url.pathname === `/api/v1/workspaces/${workspaceId}/stop`) {
      lifecycle = 'STOPPED'
      await fulfillJson(route, 200, {
        request_id: `req_${'7'.repeat(32)}`,
        workspace_id: workspaceId,
        project_id: projectId,
        agent_type: 'codex',
        generation,
        stop_operation_id: `sop_${'8'.repeat(32)}`,
        state: 'STOPPED',
      })
      return
    }
    await route.abort('blockedbyclient')
  })
  return mutations
}

async function installFailureRoutes(page: Page) {
  await page.route('**/healthz', (route) =>
    fulfillJson(route, 200, { status: 'ok' }),
  )
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/me') {
      await fulfillJson(
        route,
        200,
        envelope(authData, 'req_rc9_workspace_auth'),
      )
      return
    }
    if (url.pathname === '/api/v1/meta') {
      await fulfillJson(route, 200, {
        name: 'AgentBox',
        version: '0.3.0-rc.9',
        api_version: 'v1',
        environment: 'test',
      })
      return
    }
    if (url.pathname === '/api/v1/projects') {
      await fulfillJson(route, 200, envelope({ projects: [project] }))
      return
    }
    if (url.pathname === '/api/v1/workspaces') {
      await fulfillJson(route, 503, {
        request_id: 'req_rc9_workspace_failure',
        error: {
          code: 'WAW_STATUS_UNAVAILABLE',
          message: serverCanary,
        },
      })
      return
    }
    await route.abort('blockedbyclient')
  })
}

type ProductionWorkspaceScenario =
  | 'loading'
  | 'unregistered'
  | 'direct-success'
  | 'direct-not-found'
  | 'direct-identity-mismatch'
  | 'direct-reconciliation'
  | 'provider-unavailable'

/**
 * Uses the normal production App preview. The only injected terminal controller
 * remains confined to the distinct harness used by the lifecycle test above.
 */
async function installProductionWorkspaceRoutes(
  page: Page,
  scenario: ProductionWorkspaceScenario,
) {
  const projectsHold = scenario === 'loading' ? createRc9RouteHold() : null
  await page.route('**/healthz', (route) =>
    fulfillJson(route, 200, { status: 'ok' }),
  )
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/me') {
      await fulfillJson(
        route,
        200,
        envelope(authData, 'req_rc9_workspace_auth'),
      )
      return
    }
    if (url.pathname === '/api/v1/meta') {
      await fulfillJson(route, 200, {
        name: 'AgentBox',
        version: '0.3.0-rc.9',
        api_version: 'v1',
        environment: 'test',
      })
      return
    }
    if (url.pathname === '/api/v1/projects') {
      if (projectsHold !== null) await projectsHold.hold()
      await fulfillJson(route, 200, envelope({ projects: [project] }))
      return
    }
    if (url.pathname === `/api/v1/workspaces/${workspaceId}`) {
      if (scenario === 'direct-not-found') {
        await fulfillJson(route, 404, {
          request_id: 'req_rc9_workspace_not_found',
          error: {
            code: 'WORKSPACE_NOT_FOUND',
            message: serverCanary,
          },
        })
      } else {
        const row =
          scenario === 'direct-reconciliation'
            ? workspaceRow('UNKNOWN', 'reconciliation_required')
            : workspaceRow('RUNNING')
        await fulfillJson(route, 200, {
          request_id: 'req_rc9_workspace_direct',
          data: row,
        })
      }
      return
    }
    if (url.pathname === '/api/v1/workspaces') {
      const row =
        scenario === 'unregistered' || scenario === 'loading'
          ? null
          : workspaceRow('RUNNING')
      await fulfillJson(route, 200, {
        request_id: 'req_rc9_workspace_list',
        data: { workspaces: row === null ? [] : [row] },
      })
      return
    }
    if (url.pathname === `/api/v1/workspaces/${workspaceId}/status`) {
      const status =
        scenario === 'direct-identity-mismatch'
          ? runtimeStatus('RUNNING', { workspaceId: alternateWorkspaceId })
          : scenario === 'direct-reconciliation'
            ? runtimeStatus('UNKNOWN', {
                reconciliationState: 'reconciliation_required',
              })
            : runtimeStatus('RUNNING')
      await fulfillJson(route, 200, {
        request_id: 'req_rc9_workspace_status',
        data: status,
      })
      return
    }
    await route.abort('blockedbyclient')
  })
  return { projectsHold }
}

async function readHarnessEvidence(page: Page): Promise<HarnessEvidence> {
  const value = await page
    .getByTestId('workspace-harness-evidence')
    .textContent()
  if (value === null) throw new Error('Workspace harness evidence is missing')
  return JSON.parse(value) as HarnessEvidence
}

test('exercises the managed Workspace page lifecycle in both locales and viewports', async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'the self-managed rc9 context matrix runs once with complete device options',
  )
  test.setTimeout(120_000)
  const harnessBaseURL = process.env.PLAYWRIGHT_HARNESS_BASE_URL ?? baseURL

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL: harnessBaseURL,
      })
      try {
        const page = await context.newPage()
        const mutations = await installSuccessRoutes(page)
        const expected = localeCopy[locale.expectedLocale]
        await page.goto('/e2e/rc9-workspace-harness.html')

        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9Title(page, `${expected.title} · AgentBox`)
        const connect = page.getByRole('button', { name: expected.connect })
        await expect(connect).toBeEnabled()
        await connect.click()
        await expect(
          page.getByText(expected.connected, { exact: true }),
        ).toBeVisible()
        const terminal = page.getByRole('log')
        await expect(terminal).toContainText(fixtureOutput)

        const input = page.getByRole('textbox', { name: expected.sendInput })
        await input.fill(fixtureInput)
        await input.press('Enter')
        await expect(input).toHaveValue('')
        await expect
          .poll(() => readHarnessEvidence(page).then((value) => value.inputs))
          .toEqual([
            {
              byteLength: new TextEncoder().encode(`${fixtureInput}\r`)
                .byteLength,
              endsWithCarriageReturn: true,
            },
          ])
        await assertRc9CanaryAbsent(page, fixtureInput)
        await expect
          .poll(() =>
            readHarnessEvidence(page).then((value) => value.resizes.length),
          )
          .toBeGreaterThan(0)

        await page.getByRole('button', { name: expected.detach }).click()
        await expect(
          page.getByText(expected.detached, { exact: true }),
        ).toBeVisible()
        await expect(terminal).toHaveText('')

        const reconnect = page.getByRole('button', {
          name: expected.reconnect,
        })
        await expect(reconnect).toBeEnabled()
        await reconnect.click()
        await expect(
          page.getByText(expected.connected, { exact: true }),
        ).toBeVisible()

        const stop = page.getByRole('button', { name: expected.stop })
        await assertRc9Focus(stop)
        await stop.click()
        const dialog = page.getByRole('dialog', {
          name: expected.confirmTitle,
        })
        await assertRc9ModalDialog(page, dialog)
        await expect(
          dialog.getByRole('button', { name: expected.cancel }),
        ).toBeFocused()
        await dialog.getByRole('button', { name: expected.cancel }).click()
        await expect(dialog).toBeHidden()
        await assertRc9FocusRestored(stop)

        await stop.click()
        await assertRc9ModalDialog(page, dialog)
        await dialog.getByRole('button', { name: expected.confirmStop }).click()
        await expect(page.getByText(expected.stoppedNotice)).toBeVisible()
        await expect(terminal).toHaveText('')

        const evidence = await readHarnessEvidence(page)
        expect(evidence.events).toContain('provider:create')
        expect(evidence.events).toContain('trust:authorize')
        expect(evidence.events).toContain('controller:connect')
        expect(evidence.events).toContain('controller:reconnect')
        expect(evidence.events).toContain('controller:detach')
        expect(evidence.events).toContain('controller:stop')
        expect(evidence.events).toContain('controller:stop:detach-confirmed')
        expect(JSON.stringify(evidence)).not.toContain(fixtureInput)
        expect(
          evidence.events.indexOf('controller:stop:detach-confirmed'),
        ).toBeLessThan(evidence.events.indexOf('controller:stop'))

        expect(
          mutations.filter(
            (request) =>
              request.path === `/api/v1/workspaces/${workspaceId}/attachments`,
          ),
        ).toEqual([
          {
            path: `/api/v1/workspaces/${workspaceId}/attachments`,
            body: '{"mode":"writer"}',
          },
        ])
        expect(
          mutations.filter(
            (request) =>
              request.path === `/api/v1/workspaces/${workspaceId}/reconnect`,
          ),
        ).toEqual([
          {
            path: `/api/v1/workspaces/${workspaceId}/reconnect`,
            body: '{}',
          },
        ])
        expect(
          mutations.filter(
            (request) =>
              request.path === `/api/v1/workspaces/${workspaceId}/detach`,
          ),
        ).toHaveLength(2)
        expect(
          mutations.filter(
            (request) =>
              request.path === `/api/v1/workspaces/${workspaceId}/stop`,
          ),
        ).toEqual([
          {
            path: `/api/v1/workspaces/${workspaceId}/stop`,
            body: `{"generation":"${generation}"}`,
          },
        ])
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        await context.close()
      }
    }
  }
})

test('covers the production Workspace route and state matrix without test injection', async ({
  browser,
  baseURL,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'the self-managed rc9 context matrix runs once with complete device options',
  )
  test.setTimeout(120_000)

  const scenarios: readonly ProductionWorkspaceScenario[] = [
    'loading',
    'unregistered',
    'direct-success',
    'direct-not-found',
    'direct-identity-mismatch',
    'direct-reconciliation',
    'provider-unavailable',
  ]

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      try {
        const expected = localeCopy[locale.expectedLocale]
        for (const scenario of scenarios) {
          const page = await context.newPage()
          let heldProjects: ReturnType<typeof createRc9RouteHold> | null = null
          try {
            const routes = await installProductionWorkspaceRoutes(
              page,
              scenario,
            )
            heldProjects = routes.projectsHold
            const path = scenario.startsWith('direct-')
              ? `/workspace/${workspaceId}`
              : `/workspace?project_id=${projectId}&agent_type=codex`
            await page.goto(path)

            await assertRc9DocumentLocale(page, locale.expectedLocale)
            await assertRc9Title(page, `${expected.title} · AgentBox`)

            if (scenario === 'loading') {
              if (heldProjects === null)
                throw new Error('loading scenario must hold the Project route')
              await heldProjects.waitUntilHeld()
              const projectSelect = page.getByLabel(
                locale.expectedLocale === 'zh-CN'
                  ? '正式 READY Project'
                  : 'Formal READY Project',
              )
              await expect(projectSelect).toBeDisabled()
              await expect(projectSelect.locator('option:checked')).toHaveText(
                expected.loadingProjects,
              )
              await assertRc9NoHorizontalOverflow(page)
              await assertRc9InteractiveTargets(page)
              heldProjects.release()
              await expect(page.getByText(expected.unregistered)).toBeVisible()
            } else if (scenario === 'unregistered') {
              await expect(page.getByText(expected.unregistered)).toBeVisible()
            } else if (scenario === 'direct-not-found') {
              await expect(page.getByText(expected.notFound)).toBeVisible()
              await assertRc9TechnicalRendering(
                page.getByText('WORKSPACE_NOT_FOUND', { exact: true }),
              )
            } else if (scenario === 'direct-identity-mismatch') {
              await expect(
                page.getByText(expected.identityChanged),
              ).toBeVisible()
              await assertRc9TechnicalRendering(
                page.getByText('PROJECT_IDENTITY_CHANGED', { exact: true }),
              )
            } else if (scenario === 'direct-reconciliation') {
              await expect(page.getByText(expected.recovery)).toBeVisible()
              await assertRc9TechnicalRendering(
                page.getByText('reconciliation_required', { exact: true }),
              )
              await expect(
                page.getByRole('button', { name: expected.connect }),
              ).toBeDisabled()
            } else {
              await expect(
                page.getByText(expected.providerUnavailable),
              ).toBeVisible()
              await assertRc9TechnicalRendering(
                page.getByText('ATTACHMENT_UNAVAILABLE', { exact: true }),
              )
              await expect(
                page.getByRole('button', { name: expected.connect }),
              ).toBeDisabled()
              if (scenario === 'direct-success') {
                await assertRc9TechnicalRendering(
                  page.getByText(workspaceId, { exact: true }),
                )
              }
            }

            await assertRc9CanaryAbsent(page, serverCanary)
            await assertRc9NoHorizontalOverflow(page)
            await assertRc9InteractiveTargets(page)
          } finally {
            heldProjects?.dispose()
            await page.close()
          }
        }
      } finally {
        await context.close()
      }
    }
  }
})

test('localizes Workspace lookup failures without retaining server prose', async ({
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
      try {
        const page = await context.newPage()
        await installFailureRoutes(page)
        await page.goto(`/workspace?project_id=${projectId}&agent_type=codex`)
        const expected = localeCopy[locale.expectedLocale]

        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9Title(page, `${expected.title} · AgentBox`)
        await expect(page.getByText(expected.error)).toBeVisible()
        await assertRc9TechnicalRendering(
          page.getByText('WAW_STATUS_UNAVAILABLE'),
        )
        await assertRc9CanaryAbsent(page, serverCanary)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        await context.close()
      }
    }
  }
})
