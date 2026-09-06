import { expect, test, type Page, type Route } from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9InteractiveTargets,
  assertRc9NoHorizontalOverflow,
  assertRc9TechnicalRendering,
  assertRc9Title,
} from './rc9-assertions'
import {
  createRc9DocumentContext,
  createRc9RouteHold,
  installRc9HeldRoute,
  RC9_LOCALE_SCENARIOS,
  RC9_VIEWPORTS,
} from './rc9-fixtures'

test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const serverCanary = 'RC9-PROJECTS-SERVER-PROSE-CANARY-6V3N'

const authData = {
  user: { id: 'adm_rc9_projects', username: 'synthetic-user' },
  session: { id: 'ses_rc9_projects', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'csrf-rc9-projects',
}

const git = {
  is_repository: true,
  branch: 'feature/locale-rc9',
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
  remote_url: 'https://github.com/example/agentbox.git',
  submodules_detected: true,
}

const project = {
  id: 'prj_rc9',
  slug: 'agentbox-rc9',
  display_name: '用户 Project 🚀',
  source_type: 'git_clone',
  state: 'ready',
  repository_url: 'https://github.com/example/agentbox.git',
  default_branch: 'main',
  created_at: '2026-09-03T00:00:00Z',
  updated_at: '2026-09-03T00:00:00Z',
  git,
  github: {
    available: true,
    repository: 'example/agentbox',
    pull_request_number: 42,
    pull_request_title: '用户提交标题 🚀',
    pull_request_state: serverCanary,
    pull_request_draft: true,
    pull_request_url: null,
    pull_request_base: 'main',
    pull_request_head: 'feature/locale-rc9',
    mergeability: serverCanary,
    checks: 'pending',
  },
  claude_state: 'stopped',
}

function envelope(data: unknown, requestId = 'req_rc9_projects') {
  return { api_version: 'v1', request_id: requestId, data }
}

function job(status: 'queued' | 'failed') {
  return {
    id: 'job_rc9_projects',
    type: 'git.push',
    status,
    target_type: 'project',
    target_id: project.id,
    project_id: project.id,
    progress: status === 'queued' ? 0 : 25,
    phase: status,
    result_summary: serverCanary,
    error_code: status === 'failed' ? 'GIT_PUSH_FAILED' : null,
    error_summary: serverCanary,
    created_at: '2026-09-03T00:00:00Z',
    started_at: status === 'failed' ? '2026-09-03T00:00:01Z' : null,
    finished_at: status === 'failed' ? '2026-09-03T00:00:02Z' : null,
  }
}

async function fulfillJson(route: Route, status: number, body: object) {
  await route.fulfill({ status, json: body })
}

async function installSharedRoutes(page: Page) {
  await page.route('**/api/v1/auth/me', (route) =>
    fulfillJson(route, 200, envelope(authData, 'req_rc9_projects_auth')),
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

const localeCopy = {
  en: {
    name: 'Project name',
    nameValidation: 'Enter a Project name.',
    clone: 'Clone',
    cloning: 'Cloning…',
    branch: 'Branch',
    push: 'Push',
    startClaude: 'Start Claude',
    startingClaude: 'Starting…',
  },
  'zh-CN': {
    name: 'Project 名称',
    nameValidation: '请输入 Project 名称。',
    clone: '克隆',
    cloning: '正在克隆…',
    branch: '分支',
    push: 'Push',
    startClaude: '启动 Claude',
    startingClaude: '正在启动…',
  },
} as const

test('covers localized Projects states without retaining server prose', async ({
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
      const cloneHold = createRc9RouteHold()
      try {
        const page = await context.newPage()
        await installSharedRoutes(page)
        await page.route('**/api/v1/projects', (route) =>
          route.request().method() === 'GET'
            ? fulfillJson(route, 200, envelope({ projects: [project] }))
            : route.fallback(),
        )
        await installRc9HeldRoute(page, '**/api/v1/projects/clone', cloneHold, {
          status: 202,
          json: envelope({ project, job: job('queued') }),
        })
        await page.route('**/api/v1/jobs/job_rc9_projects', (route) =>
          fulfillJson(route, 200, envelope(job('failed'))),
        )
        await page.goto('/projects')

        const expected = localeCopy[locale.expectedLocale]
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await assertRc9Title(page, 'Projects · AgentBox')

        const projectName = page.getByText('用户 Project 🚀')
        await expect(projectName).toHaveAttribute('translate', 'no')
        await expect(projectName).toHaveAttribute('dir', 'auto')
        await assertRc9TechnicalRendering(
          page.getByText('feature/locale-rc9', { exact: true }),
        )
        await assertRc9TechnicalRendering(
          page.getByText('https://github.com/example/agentbox.git', {
            exact: true,
          }),
        )

        const nameInput = page.getByLabel(expected.name, { exact: true })
        await nameInput.fill('   ')
        await page
          .locator('form')
          .first()
          .locator('button[type="submit"]')
          .click()
        await expect(page.getByText(expected.nameValidation)).toBeVisible()
        await expect(nameInput).toHaveAttribute('aria-invalid', 'true')

        await page
          .getByLabel(/Repository URL|仓库 URL/)
          .fill('https://github.com/owner/repo.git')
        const cloneButton = page.getByRole('button', {
          name: expected.clone,
          exact: true,
        })
        await cloneButton.click()
        await cloneHold.waitUntilHeld()
        await expect(
          page.getByRole('button', { name: expected.cloning }),
        ).toBeDisabled()
        cloneHold.release()

        const errorCode = page.getByText('GIT_PUSH_FAILED')
        await expect(errorCode).toBeVisible()
        await assertRc9TechnicalRendering(errorCode)
        await assertRc9CanaryAbsent(page, serverCanary)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        cloneHold.dispose()
        await context.close()
      }
    }
  }
})

test('covers localized Project detail and Claude action failures', async ({
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
      const claudeHold = createRc9RouteHold()
      try {
        const page = await context.newPage()
        await installSharedRoutes(page)
        await page.route(/\/api\/v1\/projects\/prj_rc9$/, (route) =>
          fulfillJson(route, 200, envelope(project)),
        )
        await page.route('**/api/v1/projects/prj_rc9/git/branches', (route) =>
          fulfillJson(
            route,
            200,
            envelope({
              branches: [
                { name: 'feature/locale-rc9', current: true },
                { name: 'main', current: false },
              ],
            }),
          ),
        )
        await page.route('**/api/v1/projects/prj_rc9/git/push', (route) =>
          fulfillJson(route, 202, envelope(job('failed'))),
        )
        await page.route('**/api/v1/jobs/job_rc9_projects', (route) =>
          fulfillJson(route, 200, envelope(job('failed'))),
        )
        await page.route('**/api/v1/claude/sessions/prj_rc9', (route) =>
          fulfillJson(
            route,
            200,
            envelope({
              project_id: project.id,
              display_name: project.display_name,
              state: 'stopped',
              managed: true,
              session_name: 'agentbox-claude-prj-rc9',
              attach_command: 'tmux attach-session -t =agentbox-claude-prj-rc9',
              workspace_state: 'unknown',
              tmux_running: false,
              remote_readiness: 'unknown',
            }),
          ),
        )
        await installRc9HeldRoute(
          page,
          '**/api/v1/claude/sessions/prj_rc9/start',
          claudeHold,
          {
            status: 500,
            json: {
              request_id: 'req_rc9_claude_project_failure',
              error: { code: 'CLAUDE_ACTION_FAILED', message: serverCanary },
            },
          },
        )
        await page.goto('/projects/prj_rc9')

        const expected = localeCopy[locale.expectedLocale]
        await assertRc9DocumentLocale(page, locale.expectedLocale)

        await assertRc9Title(page, '用户 Project 🚀 · AgentBox')
        await expect(
          page.getByRole('heading', { name: '用户 Project 🚀' }),
        ).toBeVisible()
        await expect(page.getByText('用户提交标题 🚀')).toHaveAttribute(
          'translate',
          'no',
        )
        await expect(
          page.getByText(expected.branch, { exact: true }),
        ).toBeVisible()
        await assertRc9TechnicalRendering(
          page.getByText('agentbox-rc9', { exact: true }),
        )
        await assertRc9TechnicalRendering(
          page.getByText('feature/locale-rc9', { exact: true }).first(),
        )
        await assertRc9TechnicalRendering(
          page.getByText('example/agentbox', { exact: true }),
        )

        await page.getByRole('button', { name: expected.push }).click()
        const jobError = page.getByText('GIT_PUSH_FAILED')
        await expect(jobError).toBeVisible()
        await assertRc9TechnicalRendering(jobError)

        await page.getByRole('button', { name: expected.startClaude }).click()
        await claudeHold.waitUntilHeld()
        await expect(
          page.getByRole('button', { name: expected.startingClaude }),
        ).toBeDisabled()
        claudeHold.release()
        await expect(page.getByText('CLAUDE_ACTION_FAILED')).toBeVisible()
        await assertRc9CanaryAbsent(page, serverCanary)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        claudeHold.dispose()
        await context.close()
      }
    }
  }
})
