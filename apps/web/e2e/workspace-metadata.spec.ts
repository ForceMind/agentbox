import { expect, test } from '@playwright/test'

const projectId = 'prj_0123456789abcdef0123456789abcdef'
const workspaceId = 'aws_0123456789abcdef0123456789abcdef'
const generation = '1'

const readyProject = {
  id: projectId,
  slug: 'formal-project',
  display_name: 'Formal Project',
  source_type: 'existing',
  state: 'ready',
  repository_url: null,
  default_branch: 'main',
  created_at: '2026-08-10T00:00:00Z',
  updated_at: '2026-08-10T00:00:00Z',
  git: null,
  github: null,
  claude_state: null,
}

const notReadyProject = {
  ...readyProject,
  id: 'prj_abcdefabcdefabcdefabcdefabcdefab',
  state: 'error',
}

function workspaceRow(agentType: 'claude' | 'codex', state = 'STARTING') {
  return {
    id: workspaceId,
    project_id: projectId,
    agent_type: agentType,
    state,
    reconciliation_state: 'authoritative',
    generation: 1,
    revision: 1,
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
    last_seen_at: '2026-08-10T00:00:00Z',
    exit_code: null,
    failure_code: null,
  }
}

function runtimeStatus(agentType: 'claude' | 'codex', state: string) {
  return {
    workspace_id: workspaceId,
    project_id: projectId,
    agent_type: agentType,
    generation,
    binding_revision: '1',
    binding_digest:
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    state,
    reconciliation_state: 'authoritative',
    runtime_epoch: '1',
    process_state: state === 'RUNNING' ? 'RUNNING' : 'STARTING',
    exit_code: null,
    attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
  }
}

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_e2e_workspace', data }
}

async function mockWorkspaceApi(page: import('@playwright/test').Page) {
  let lifecycleState = 'STARTING'
  const requests: Array<{
    method: string
    url: string
    body?: string
    csrf?: string
  }> = []
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    requests.push({
      method: request.method(),
      url: `${url.pathname}${url.search}`,
      body: request.postData() ?? undefined,
      csrf: request.headers()['x-csrf-token'],
    })
    if (url.pathname === '/api/v1/auth/me') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          api_version: 'v1',
          request_id: 'req_e2e_auth',
          data: {
            user: { id: 'adm_e2e', username: 'synthetic' },
            session: { id: 'ses_e2e', expires_at: '2026-12-31T00:00:00Z' },
            csrf_token: 'csrf-e2e',
          },
        }),
      })
      return
    }
    if (url.pathname === '/api/v1/projects') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          envelope({ projects: [readyProject, notReadyProject] }),
        ),
      })
      return
    }
    if (url.pathname === '/api/v1/workspaces' && request.method() === 'GET') {
      const agentType = url.searchParams.get('agent_type')
      const project = url.searchParams.get('project_id')
      const rows =
        project === projectId && agentType === 'codex'
          ? [workspaceRow('codex', lifecycleState)]
          : []
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          request_id: 'req_e2e_list',
          data: { workspaces: rows },
        }),
      })
      return
    }
    if (url.pathname === `/api/v1/workspaces/${workspaceId}/status`) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          request_id: 'req_e2e_status',
          data: runtimeStatus('codex', lifecycleState),
        }),
      })
      return
    }
    if (
      url.pathname === `/api/v1/projects/${projectId}/workspaces/codex/start`
    ) {
      lifecycleState = 'RUNNING'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          request_id: 'req_e2e_start',
          workspace_id: workspaceId,
          project_id: projectId,
          agent_type: 'codex',
          state: 'RUNNING',
          generation,
        }),
      })
      return
    }
    if (url.pathname === `/api/v1/workspaces/${workspaceId}/stop`) {
      lifecycleState = 'STOPPED'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          request_id: 'req_e2e_stop',
          workspace_id: workspaceId,
          project_id: projectId,
          agent_type: 'codex',
          generation,
          stop_operation_id: 'wso_0123456789abcdef0123456789abcdef',
          state: 'STOPPED',
        }),
      })
      return
    }
    await route.continue()
  })
  return requests
}

test('runs the synthetic Codex metadata lifecycle with exact stop confirmation', async ({
  page,
}) => {
  const requests = await mockWorkspaceApi(page)
  await page.goto('/workspace')

  const projectSelect = page.getByLabel('正式 READY Project')
  await expect(projectSelect.locator('option[value^="prj_"]')).toHaveCount(1)
  await projectSelect.selectOption(projectId)
  const agentSelect = page.getByLabel('AgentType', { exact: true })
  await agentSelect.selectOption('codex')
  await expect(page.getByText('启动中')).toBeVisible()
  await expect(page.getByText('NOT ADMITTED')).toBeVisible()
  await expect(page.getByRole('button', { name: '连接终端' })).toBeDisabled()

  await page.getByRole('button', { name: '启动工作区' }).click()
  await expect(page.getByText('运行中')).toBeVisible()
  await expect(page.getByText('NOT ADMITTED')).toBeVisible()
  const startRequest = requests.find((request) =>
    request.url.endsWith('/workspaces/codex/start'),
  )
  expect(startRequest?.method).toBe('POST')
  expect(startRequest?.body).toBe('{}')
  expect(startRequest?.csrf).toBe('csrf-e2e')

  const stop = page.getByRole('button', { name: '停止工作区' })
  const stopCount = () =>
    requests.filter((request) =>
      request.url.endsWith(`/workspaces/${workspaceId}/stop`),
    ).length
  const beforeStop = stopCount()
  await stop.click()
  await expect(
    page.getByRole('heading', { name: '确认停止工作区' }),
  ).toBeVisible()
  await expect(page.getByRole('dialog').getByText(workspaceId)).toBeVisible()
  await expect(page.getByText(`Generation：${generation}`)).toBeVisible()
  expect(stopCount()).toBe(beforeStop)
  await page.getByRole('button', { name: '取消' }).click()
  await expect(
    page.getByRole('heading', { name: '确认停止工作区' }),
  ).toBeHidden()
  await expect(stop).toBeFocused()

  await stop.click()
  await page.keyboard.press('Escape')
  await expect(
    page.getByRole('heading', { name: '确认停止工作区' }),
  ).toBeHidden()
  await expect(stop).toBeFocused()
  await stop.click()
  await page.getByRole('button', { name: '确认停止' }).click()
  await expect(page.getByText('已停止', { exact: true })).toBeVisible()
  expect(stopCount()).toBe(beforeStop + 1)
  const stopRequest = requests.find((request) =>
    request.url.endsWith(`/workspaces/${workspaceId}/stop`),
  )
  expect(stopRequest?.method).toBe('POST')
  expect(stopRequest?.csrf).toBe('csrf-e2e')
  expect(JSON.parse(stopRequest?.body ?? '{}')).toEqual({ generation })
  expect(stopRequest?.body).toBe(`{"generation":"${generation}"}`)
})

test('rejects unregistered AgentType and remains bounded on mobile', async ({
  page,
}) => {
  const requests = await mockWorkspaceApi(page)
  await page.goto('/workspace')
  await page.getByLabel('正式 READY Project').selectOption(projectId)
  await page.getByLabel('AgentType', { exact: true }).selectOption('codex')
  await expect(page.getByText('启动中')).toBeVisible()
  await page.getByLabel('AgentType', { exact: true }).selectOption('claude')
  await expect(
    page.getByText('当前 AgentType 尚未注册，无法启动工作区。'),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '启动工作区' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '停止工作区' })).toBeDisabled()
  await page.keyboard.press('Escape')
  expect(
    requests.some((request) => request.url.includes('agent_type=claude')),
  ).toBe(true)
  expect(
    await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      storage: [window.localStorage.length, window.sessionStorage.length],
    })),
  ).toEqual({ overflow: false, storage: [0, 0] })
  for (const button of await page.locator('button:visible').all()) {
    const box = await button.boundingBox()
    expect(box?.width).toBeGreaterThanOrEqual(44)
    expect(box?.height).toBeGreaterThanOrEqual(44)
  }
})
