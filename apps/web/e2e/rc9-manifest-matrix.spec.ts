import {
  expect,
  test,
  type Page,
  type Route,
  type TestInfo,
} from '@playwright/test'

import {
  assertRc9CanaryAbsent,
  assertRc9DocumentLocale,
  assertRc9Focus,
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
  type Rc9Locale,
} from './rc9-fixtures'

// This spec fills only states that are not owned by the route-specific specs.
// All transport data is synthetic and no browser artifacts are retained.
//
// Manifest coverage ledger (browser evidence, not unit substitution):
// - M01 RootRedirect/route guards/Logs/NotFound: this file, case 1.
// - M02 shell drawer/logout/health: this file, case 2.
// - M03 Doctor/Settings and M04 Projects/detail: this file, cases 3-5.
// - M05 Login validation/pending/invalid/429/unavailable: rc9-auth-shell covers
//   all five enumerated states in each locale-and-viewport document.
// - M06 Dashboard loading/healthy/unavailable: rc9-dashboard; degraded is M06 here.
// - M07 Codex Remote/Pair: rc9-codex action matrix covers desktop/mobile and both
//   locales, including Remote pending/start/stop and Pair confirmation/reveal/error.
// - M08 Workspace: rc9-workspace covers lookup failure from the production
//   preview plus success lifecycle in both locales/viewports from a distinct
//   test-only Vite harness. That harness passes attachmentDependencies explicitly
//   as a component prop; normal dist has no harness, query, sentinel or factory.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

const COPY: Record<
  Rc9Locale,
  Readonly<{
    dashboard: string
    doctor: string
    settings: string
    logs: string
    notFound: string
    signOut: string
    signingOut: string
    logoutFailed: string
    openNavigation: string
    closeNavigation: string
    projects: string
    projectName: string
    createProject: string
    creatingProject: string
    emptyProjects: string
    doctorLoading: string
    settingsLoading: string
  }>
> = {
  en: {
    dashboard: 'Dashboard',
    doctor: 'Doctor',
    settings: 'Settings',
    logs: 'Logs',
    notFound: 'Page not found',
    signOut: 'Sign out',
    signingOut: 'Signing out…',
    logoutFailed: 'Logout could not be completed',
    openNavigation: 'Open navigation',
    closeNavigation: 'Close navigation',
    projects: 'Projects',
    projectName: 'Project name',
    createProject: 'Create Project',
    creatingProject: 'Creating…',
    emptyProjects: 'No Projects yet',
    doctorLoading: 'Running safe checks…',
    settingsLoading: 'Loading safe settings…',
  },
  'zh-CN': {
    dashboard: '概览',
    doctor: '诊断',
    settings: '设置',
    logs: '日志',
    notFound: '未找到页面',
    signOut: '退出登录',
    signingOut: '正在退出…',
    logoutFailed: '无法完成退出登录',
    openNavigation: '打开导航',
    closeNavigation: '关闭导航',
    projects: 'Projects',
    projectName: 'Project 名称',
    createProject: '创建 Project',
    creatingProject: '正在创建…',
    emptyProjects: '还没有 Project',
    doctorLoading: '正在运行安全检查…',
    settingsLoading: '正在加载安全设置…',
  },
}

const SERVER_PROSE_CANARY = 'RC9-MANIFEST-SERVER-PROSE-CANARY-6J8P'

const authData = {
  user: { id: 'adm_rc9_manifest', username: 'synthetic-maintainer' },
  session: { id: 'ses_rc9_manifest', expires_at: '2027-01-01T00:00:00Z' },
  csrf_token: 'csrf-rc9-manifest',
}

const project = {
  id: 'prj_rc9_manifest',
  slug: 'manifest-project',
  display_name: 'Manifest Project',
  source_type: 'empty',
  state: 'creating',
  repository_url: null,
  default_branch: null,
  created_at: '2026-09-06T00:00:00Z',
  updated_at: '2026-09-06T00:00:00Z',
  git: null,
  github: null,
  claude_state: null,
}

const completedJob = {
  id: 'job_rc9_manifest',
  type: 'project.create',
  status: 'succeeded',
  target_type: 'project',
  target_id: project.id,
  project_id: project.id,
  progress: 100,
  phase: 'succeeded',
  result_summary: null,
  error_code: null,
  error_summary: null,
  created_at: '2026-09-06T00:00:00Z',
  started_at: '2026-09-06T00:00:00Z',
  finished_at: '2026-09-06T00:00:01Z',
}

const doctorResponse = {
  api_version: 'v1',
  request_id: 'req_rc9_manifest_doctor',
  data: {
    status: 'ready',
    checks: {
      configuration_valid: true,
      database_reachable: true,
      migrations_current: true,
      admin_initialized: true,
      control_plane_ready: true,
    },
    policy: {
      environment: 'test',
      bind_host: '127.0.0.1',
      bind_port: 8080,
      session_ttl_seconds: 7200,
      session_idle_ttl_seconds: 1800,
      login_rate_limit: 12,
      login_rate_window_seconds: 60,
      login_lock_duration_seconds: 30,
    },
    codex: {
      installed: true,
      version: '0.3.0-rc.9',
      installation_type: 'standalone',
      remote_control: 'supported',
      remote_state: 'stopped',
      findings: ['CODEX_NOT_INSTALLED', SERVER_PROSE_CANARY],
    },
    claude: {
      installed: true,
      version: '1.0.0',
      authentication: 'authenticated',
      remote_control: 'supported',
      tmux_installed: true,
      tmux_version: '3.5',
      managed_sessions: 0,
      unmanaged_sessions: 0,
      workspace_interaction_warnings: 0,
      findings: [],
    },
    projects: {
      project_root: '/synthetic/Project Root',
      project_count: 0,
      git_installed: true,
      git_version: '2.48.0',
      github_cli_installed: true,
      github_authentication: 'authenticated',
      findings: [],
    },
  },
}

function envelope(data: unknown, requestId = 'req_rc9_manifest') {
  return { api_version: 'v1', request_id: requestId, data }
}

async function fulfillJson(route: Route, status: number, body: object) {
  await route.fulfill({ status, json: body })
}

async function installAuthenticatedShellRoutes(
  page: Page,
  health: 'ok' | 'unavailable' = 'ok',
  readiness: 'ready' | 'not_ready' = 'ready',
) {
  await page.route('**/api/v1/auth/me', (route) =>
    fulfillJson(route, 200, envelope(authData, 'req_rc9_manifest_auth')),
  )
  await page.route('**/healthz', (route) =>
    health === 'ok'
      ? fulfillJson(route, 200, { status: 'ok' })
      : fulfillJson(route, 503, {
          request_id: 'req_rc9_manifest_health',
          error: {
            code: 'CONTROL_PLANE_UNAVAILABLE',
            message: SERVER_PROSE_CANARY,
          },
        }),
  )
  await page.route('**/readyz', (route) =>
    fulfillJson(route, readiness === 'ready' ? 200 : 503, {
      status: readiness,
      checks: { database: true, migrations: true },
    }),
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

function onlyManagedDesktop(testInfo: TestInfo) {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'the self-managed rc9 context matrix runs once with exact device options',
  )
}

test('covers RootRedirect, route guards, Logs, and NotFound in the rc9 matrix', async ({
  browser,
  baseURL,
}, testInfo) => {
  onlyManagedDesktop(testInfo)

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const copy = COPY[locale.expectedLocale]
      const anonymous = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      const authHold = createRc9RouteHold()
      try {
        const page = await anonymous.newPage()
        await installRc9HeldRoute(page, '**/api/v1/auth/me', authHold, {
          status: 401,
          json: { request_id: 'req_rc9_manifest_anonymous' },
        })
        await page.goto('/')
        await authHold.waitUntilHeld()
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await expect(page.getByRole('status')).toBeVisible()
        authHold.release()
        await expect(page).toHaveURL(/\/login$/)

        await page.goto('/route-not-in-agentbox')
        await assertRc9Title(page, `${copy.notFound} · AgentBox`)
        await expect(page.getByRole('link')).toHaveAttribute('href', '/login')
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        authHold.dispose()
        await anonymous.close()
      }

      const authenticated = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      try {
        const page = await authenticated.newPage()
        await installAuthenticatedShellRoutes(page)
        await page.goto('/')
        await expect(page).toHaveURL(/\/dashboard$/)
        await page.goto('/login')
        await expect(page).toHaveURL(/\/dashboard$/)
        await assertRc9Title(page, `${copy.dashboard} · AgentBox`)
        await page.goto('/logs')
        await assertRc9Title(page, `${copy.logs} · AgentBox`)
        await expect(page.locator('.empty-state')).toBeVisible()
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        await authenticated.close()
      }
    }
  }
})

test('M06 covers Dashboard degraded when readiness is not ready', async ({
  browser,
  baseURL,
}, testInfo) => {
  onlyManagedDesktop(testInfo)
  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      try {
        const page = await context.newPage()
        await installAuthenticatedShellRoutes(page, 'ok', 'not_ready')
        await page.goto('/dashboard')
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        await expect(
          page.locator('.page-header > .status-badge'),
        ).toContainText(locale.expectedLocale === 'zh-CN' ? '降级' : 'Degraded')
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        await context.close()
      }
    }
  }
})

test('covers Shell mobile drawer, failed logout, and unavailable health in the rc9 matrix', async ({
  browser,
  baseURL,
}, testInfo) => {
  onlyManagedDesktop(testInfo)

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const copy = COPY[locale.expectedLocale]
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      const logoutHold = createRc9RouteHold()
      try {
        const page = await context.newPage()
        await installAuthenticatedShellRoutes(page, 'unavailable')
        await installRc9HeldRoute(page, '**/api/v1/auth/logout', logoutHold, {
          status: 500,
          json: {
            request_id: 'req_rc9_manifest_logout',
            error: {
              code: 'RC9_UNKNOWN_LOGOUT_FAILURE',
              message: SERVER_PROSE_CANARY,
            },
          },
        })
        await page.goto('/dashboard')
        await assertRc9DocumentLocale(page, locale.expectedLocale)
        if (viewport.name === 'mobile') {
          const menu = page.locator('.mobile-header button')
          await expect(menu).toHaveAccessibleName(copy.openNavigation)
          await assertRc9Focus(menu)
          await menu.click()
          await expect(menu).toHaveAttribute('aria-expanded', 'true')
          await expect(
            page.getByRole('button', { name: copy.closeNavigation }),
          ).toBeVisible()
          await expect(page.locator('#mobile-navigation')).toBeVisible()
        }
        await expect(
          viewport.name === 'mobile'
            ? page.locator(
                '#mobile-navigation .control-pulse.pulse-unavailable',
              )
            : page.locator('.desktop-sidebar .control-pulse.pulse-unavailable'),
        ).toBeVisible()
        await assertRc9CanaryAbsent(page, SERVER_PROSE_CANARY)
        await assertRc9TechnicalRendering(
          page.locator('.app-version bdi').first(),
        )

        let logout = page.locator('.sidebar-footer button')
        await expect(logout).toHaveText(copy.signOut)
        if (viewport.name === 'mobile') {
          logout = page.locator('#mobile-navigation button.mobile-logout')
          await expect(logout).toHaveText(copy.signOut)
        }
        await logout.click()
        await logoutHold.waitUntilHeld()
        await expect(logout).toBeDisabled()
        await expect(logout).toHaveText(copy.signingOut)
        logoutHold.release()
        await expect(page.getByRole('alert')).toContainText(copy.logoutFailed)
        await assertRc9CanaryAbsent(page, SERVER_PROSE_CANARY)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        logoutHold.dispose()
        await context.close()
      }
    }
  }
})

test('covers Doctor and Settings loading, loaded, and error states in the rc9 matrix', async ({
  browser,
  baseURL,
}, testInfo) => {
  onlyManagedDesktop(testInfo)

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const copy = COPY[locale.expectedLocale]
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      const doctorHold = createRc9RouteHold()
      let requestNumber = 0
      try {
        const page = await context.newPage()
        await installAuthenticatedShellRoutes(page)
        await page.route('**/api/v1/doctor', async (route) => {
          requestNumber += 1
          if (requestNumber === 1) {
            await doctorHold.hold()
            await fulfillJson(route, 200, doctorResponse)
            return
          }
          if (requestNumber === 3) {
            await fulfillJson(route, 503, {
              request_id: 'req_rc9_manifest_doctor_error',
              error: {
                code: 'RC9_UNKNOWN_DOCTOR_FAILURE',
                message: SERVER_PROSE_CANARY,
              },
            })
            return
          }
          await fulfillJson(route, 200, doctorResponse)
        })

        await page.goto('/doctor')
        await doctorHold.waitUntilHeld()
        await assertRc9Title(page, `${copy.doctor} · AgentBox`)
        await expect(page.getByRole('status')).toHaveText(copy.doctorLoading)
        doctorHold.release()
        await expect(
          page.getByRole('heading', { name: copy.doctor }),
        ).toBeVisible()
        await assertRc9TechnicalRendering(page.getByText('0.3.0-rc.9').first())
        await assertRc9CanaryAbsent(page, SERVER_PROSE_CANARY)

        await page.goto('/settings')
        await assertRc9Title(page, `${copy.settings} · AgentBox`)
        await expect(
          page.getByRole('heading', { name: copy.settings }),
        ).toBeVisible()
        await assertRc9TechnicalRendering(page.getByText('test'))

        await page.goto('/doctor')
        await expect(page.getByRole('alert')).toBeVisible()
        const code = page.getByText('RC9_UNKNOWN_DOCTOR_FAILURE')
        await assertRc9TechnicalRendering(code)
        await assertRc9CanaryAbsent(page, SERVER_PROSE_CANARY)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        doctorHold.dispose()
        await context.close()
      }
    }
  }
})

test('covers empty Projects plus create pending, success, and error in the rc9 matrix', async ({
  browser,
  baseURL,
}, testInfo) => {
  onlyManagedDesktop(testInfo)

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const copy = COPY[locale.expectedLocale]
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      const listHold = createRc9RouteHold()
      const createHold = createRc9RouteHold()
      let createCalls = 0
      try {
        const page = await context.newPage()
        await installAuthenticatedShellRoutes(page)
        await installRc9HeldRoute(page, '**/api/v1/projects', listHold, {
          status: 200,
          json: envelope({ projects: [] }),
        })
        await page.route('**/api/v1/projects', async (route) => {
          if (route.request().method() !== 'POST') return route.fallback()
          createCalls += 1
          if (createCalls === 1) {
            await createHold.hold()
            await fulfillJson(
              route,
              200,
              envelope({ project, job: completedJob }),
            )
            return
          }
          await fulfillJson(route, 500, {
            request_id: 'req_rc9_manifest_create_error',
            error: {
              code: 'RC9_UNKNOWN_PROJECT_FAILURE',
              message: SERVER_PROSE_CANARY,
            },
          })
        })
        await page.goto('/projects')
        await listHold.waitUntilHeld()
        await assertRc9Title(page, `${copy.projects} · AgentBox`)
        await expect(page.getByRole('status')).toBeVisible()
        listHold.release()
        await expect(
          page.getByRole('heading', { name: copy.emptyProjects }),
        ).toBeVisible()

        const projectName = page.getByLabel(copy.projectName, { exact: true })
        const create = page
          .locator('form')
          .first()
          .locator('button[type="submit"]')
        await expect(create).toHaveAccessibleName(copy.createProject)
        await assertRc9Focus(projectName)
        await projectName.fill('Manifest Project')
        await create.click()
        await createHold.waitUntilHeld()
        await expect(create).toBeDisabled()
        await expect(create).toHaveText(copy.creatingProject)
        createHold.release()
        await expect(page.getByText('Manifest Project')).toHaveAttribute(
          'translate',
          'no',
        )
        await assertRc9TechnicalRendering(page.getByText(completedJob.id))

        await projectName.fill('Failed Project')
        await create.click()
        const errorCode = page.getByText('RC9_UNKNOWN_PROJECT_FAILURE')
        await expect(errorCode).toBeVisible()
        await assertRc9TechnicalRendering(errorCode)
        await assertRc9CanaryAbsent(page, SERVER_PROSE_CANARY)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        listHold.dispose()
        createHold.dispose()
        await context.close()
      }
    }
  }
})

test('covers Project detail not-found without duplicating the detail success matrix', async ({
  browser,
  baseURL,
}, testInfo) => {
  onlyManagedDesktop(testInfo)

  for (const viewport of RC9_VIEWPORTS) {
    for (const locale of RC9_LOCALE_SCENARIOS) {
      const context = await createRc9DocumentContext(browser, {
        viewport,
        locale,
        baseURL,
      })
      try {
        const page = await context.newPage()
        await installAuthenticatedShellRoutes(page)
        await page.route('**/api/v1/projects/missing-rc9', (route) =>
          fulfillJson(route, 404, {
            request_id: 'req_rc9_manifest_project_missing',
            error: {
              code: 'PROJECT_NOT_FOUND',
              message: SERVER_PROSE_CANARY,
            },
          }),
        )
        await page.goto('/projects/missing-rc9')
        await expect(page.getByRole('heading')).toBeVisible()
        const code = page.getByText('PROJECT_NOT_FOUND')
        await assertRc9TechnicalRendering(code)
        await expect(page.locator('.back-link')).toHaveAttribute(
          'href',
          '/projects',
        )
        await assertRc9CanaryAbsent(page, SERVER_PROSE_CANARY)
        await assertRc9NoHorizontalOverflow(page)
        await assertRc9InteractiveTargets(page)
      } finally {
        await context.close()
      }
    }
  }
})
