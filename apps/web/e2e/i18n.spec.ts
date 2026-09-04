import { expect, test, type Page } from '@playwright/test'

const projectId = 'prj_0123456789abcdef0123456789abcdef'
const workspaceId = 'aws_0123456789abcdef0123456789abcdef'

const auth = {
  api_version: 'v1',
  request_id: 'req_i18n_auth',
  data: {
    user: { id: 'adm_i18n', username: 'synthetic' },
    session: { id: 'ses_i18n', expires_at: '2026-12-31T00:00:00Z' },
    csrf_token: 'csrf-i18n',
  },
}

const project = {
  id: projectId,
  slug: 'locale-project',
  display_name: 'Locale Project',
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

const workspace = {
  id: workspaceId,
  project_id: projectId,
  agent_type: 'claude',
  state: 'STARTING',
  reconciliation_state: 'authoritative',
  generation: 1,
  revision: 1,
  created_at: '2026-08-10T00:00:00Z',
  updated_at: '2026-08-10T00:00:00Z',
  last_seen_at: '2026-08-10T00:00:00Z',
  exit_code: null,
  failure_code: null,
}

function envelope(data: unknown) {
  return { api_version: 'v1', request_id: 'req_i18n', data }
}

async function mockLocaleWorkspace(page: Page) {
  await page.route('**/healthz', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    })
  })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    let body: unknown = envelope({})
    if (url.pathname === '/api/v1/auth/me') body = auth
    else if (url.pathname === '/api/v1/projects') {
      body = envelope({ projects: [project] })
    } else if (url.pathname === '/api/v1/workspaces') {
      body = {
        request_id: 'req_i18n_workspaces',
        data: {
          workspaces:
            url.searchParams.get('project_id') === projectId &&
            url.searchParams.get('agent_type') === 'claude'
              ? [workspace]
              : [],
        },
      }
    } else if (url.pathname === `/api/v1/workspaces/${workspaceId}/status`) {
      body = {
        request_id: 'req_i18n_status',
        data: {
          workspace_id: workspaceId,
          project_id: projectId,
          agent_type: 'claude',
          generation: '1',
          binding_revision: '1',
          binding_digest: 'a'.repeat(64),
          state: 'STARTING',
          reconciliation_state: 'authoritative',
          runtime_epoch: '1',
          process_state: 'STARTING',
          exit_code: null,
          attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
        },
      }
    } else if (
      url.pathname === `/api/v1/projects/${projectId}/workspaces/claude/start`
    ) {
      body = {
        request_id: 'req_i18n_start',
        workspace_id: workspaceId,
        project_id: projectId,
        agent_type: 'claude',
        state: 'RUNNING',
        generation: '1',
      }
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

test('selects zh-CN only for first Chinese browser language across desktop and mobile', async ({
  browser,
  baseURL,
}) => {
  const layouts = [
    { viewport: { width: 1280, height: 900 } },
    { viewport: { width: 390, height: 844 }, isMobile: true },
  ] as const
  const samples = [
    {
      locale: 'zh-CN',
      documentLang: 'zh-CN',
      heading: '交互式工作区',
      admission: '尚未准入',
      projectLabel: '正式 READY Project',
      start: '启动工作区',
      notice: '启动请求已确认。进程状态与浏览器终端连接状态分别显示。',
      workspaceNav: '工作区',
      health: '控制平面: 正常',
    },
    {
      locale: 'en-US',
      documentLang: 'en',
      heading: 'Interactive workspace',
      admission: 'Not admitted',
    },
    {
      locale: 'fr-FR',
      documentLang: 'en',
      heading: 'Interactive workspace',
      admission: 'Not admitted',
    },
  ] as const

  for (const layout of layouts) {
    for (const sample of samples) {
      const context = await browser.newContext({
        locale: sample.locale,
        baseURL,
        viewport: layout.viewport,
        isMobile: 'isMobile' in layout ? layout.isMobile : false,
      })
      const page = await context.newPage()
      await mockLocaleWorkspace(page)
      await page.goto('/workspace')
      await expect(page.locator('html')).toHaveAttribute(
        'lang',
        sample.documentLang,
      )
      await expect(
        page.getByRole('heading', { name: sample.heading }),
      ).toBeVisible()
      await expect(
        page.getByText(sample.admission, { exact: true }),
      ).toBeVisible()
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        )
        .toBe(true)

      if (sample.locale === 'zh-CN') {
        await page.getByLabel(sample.projectLabel).selectOption(projectId)
        const start = page.getByRole('button', { name: sample.start })
        await expect(start).toBeEnabled()
        const bounds = await start.boundingBox()
        expect(bounds?.height).toBeGreaterThanOrEqual(44)
        await start.click()
        await expect(page.getByText(sample.notice)).toBeVisible()
        if (!('isMobile' in layout)) {
          await expect(
            page.getByRole('link', { name: sample.workspaceNav }).first(),
          ).toBeVisible()
          await expect(page.getByLabel(sample.health)).toBeVisible()
        }
      }
      await context.close()
    }
  }
})
