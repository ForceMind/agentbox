import { act, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext } from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import type { DoctorResponse } from '../lib/contracts'
import {
  doctorHttp,
  doctorResponse,
  heldResponse,
  jsonResponse,
} from '../test/doctorFixtures'
import { DoctorPage } from './DoctorPage'

const copy = {
  en: {
    title: 'Doctor',
    checks: 'Control plane checks',
    ready: 'Ready',
    notReady: 'Not ready',
    checkLabels: [
      'Configuration valid',
      'Database reachable',
      'Migration state current',
      'Administrator initialized',
      'Control plane ready',
    ],
    unknown: 'Unknown',
    installed: 'Installed',
    notInstalled: 'Not installed',
    available: 'Available',
    capability: 'Remote capability',
    remoteState: 'Remote state',
    authentication: 'Authentication',
    githubAuthentication: 'GitHub authentication',
    supported: 'Supported',
    unsupported: 'Unsupported',
    authenticated: 'Authenticated',
    unauthenticated: 'Unauthenticated',
    running: 'Running',
    broken: 'Broken',
    stopped: 'Stopped',
    root: 'Project Root',
    tmux: 'tmux version',
    managed: 'Managed sessions',
    unmanaged: 'Unmanaged sessions',
    warnings: 'Workspace interaction warnings',
    findings: 'Diagnostic findings',
    knownFinding: 'Codex is not installed.',
    unknownFinding: 'A runtime diagnostic was reported.',
    loading: 'Running safe checks…',
    unavailable: 'Diagnostics unavailable',
    error: 'The operation could not be completed. Try again.',
  },
  'zh-CN': {
    title: '诊断',
    checks: '控制平面检查',
    ready: '已就绪',
    notReady: '未就绪',
    checkLabels: [
      '配置有效',
      '数据库可访问',
      '迁移状态最新',
      '管理员已初始化',
      '控制平面已就绪',
    ],
    unknown: '未知',
    installed: '已安装',
    notInstalled: '未安装',
    available: '可用',
    capability: 'Remote 能力',
    remoteState: 'Remote 状态',
    authentication: '身份验证',
    githubAuthentication: 'GitHub 身份验证',
    supported: '支持',
    unsupported: '不支持',
    authenticated: '已验证',
    unauthenticated: '未验证',
    running: '运行中',
    broken: '异常',
    stopped: '已停止',
    root: 'Project 根目录',
    tmux: 'tmux 版本',
    managed: '托管会话',
    unmanaged: '非托管会话',
    warnings: 'Workspace 交互警告',
    findings: '诊断发现',
    knownFinding: '未安装 Codex。',
    unknownFinding: '发现一项 Runtime 诊断信息。',
    loading: '正在运行安全检查…',
    unavailable: '诊断信息暂不可用',
    error: '操作未完成，请重试。',
  },
} as const

function show(locale: Locale, response: Response | Promise<Response>) {
  const http = doctorHttp(response)
  const rendered = render(
    <AuthContext.Provider value={http.value}>
      <DoctorPage locale={locale} />
    </AuthContext.Provider>,
  )
  return { ...rendered, ...http }
}

function field(region: HTMLElement, label: string) {
  return within(region).getByText(label, { selector: 'dt' }).nextElementSibling
}

function expectTechnical(value: string) {
  const technical = screen.getByText(value)
  expect(technical).toHaveAttribute('lang', 'en')
  expect(technical).toHaveAttribute('dir', 'ltr')
  expect(technical).toHaveAttribute('translate', 'no')
}

function expectReadOnly(container: HTMLElement) {
  expect(
    container.querySelector(
      'button, input, select, textarea, form, [contenteditable="true"]',
    ),
  ).toBeNull()
}

describe.each(['en', 'zh-CN'] as const)(
  'Doctor presentation through actual HTTP and projection in %s',
  (locale) => {
    afterEach(() => vi.unstubAllGlobals())
    const text = copy[locale]

    it('keeps control-plane ready independent of unknown Runtime summaries and findings', async () => {
      const response = doctorResponse()
      response.data.codex = {
        installed: null,
        version: null,
        installation_type: 'unknown',
        remote_control: 'unknown',
        remote_state: 'unknown',
        findings: ['RUNTIME_UNAVAILABLE'],
      }
      response.data.claude = {
        ...response.data.claude,
        installed: null,
        version: null,
        authentication: 'unknown',
        remote_control: 'unknown',
        tmux_installed: null,
        tmux_version: null,
      }
      response.data.projects = {
        ...response.data.projects,
        git_installed: null,
        git_version: null,
        github_cli_installed: null,
        github_authentication: 'unknown',
      }
      const { container, requests } = show(locale, jsonResponse(response))

      const checks = await screen.findByRole('region', { name: text.checks })
      expect(within(checks).getAllByRole('article')).toHaveLength(5)
      for (const label of text.checkLabels) {
        const row = within(checks).getByText(label).closest('article')
        expect(row).toHaveTextContent(text.ready)
      }
      expect(
        screen
          .getByRole('heading', { name: text.title, level: 1 })
          .closest('header'),
      ).toHaveTextContent(text.ready)
      const codex = screen.getByRole('region', { name: 'Codex' })
      expect(field(codex, text.capability)).toHaveTextContent(text.unknown)
      expect(field(codex, text.remoteState)).toHaveTextContent(text.unknown)
      const claude = screen.getByRole('region', { name: 'Claude + tmux' })
      expect(field(claude, text.authentication)).toHaveTextContent(text.unknown)
      expect(field(claude, text.tmux)).toHaveTextContent(text.unknown)
      const projects = screen.getByRole('region', { name: 'Projects + GitHub' })
      expect(field(projects, 'GitHub CLI')).toHaveTextContent(text.unknown)
      expect(field(projects, text.githubAuthentication)).toHaveTextContent(
        text.unknown,
      )
      expectTechnical('RUNTIME_UNAVAILABLE')
      expect(within(codex).getByRole('listitem')).toHaveTextContent(
        text.unknownFinding,
      )
      expect(requests).toHaveLength(1)
      expectReadOnly(container)
    })

    it('shows all five failed control-plane checks without relabeling working Runtime summaries', async () => {
      const response = doctorResponse()
      response.data.status = 'not_ready'
      for (const key of Object.keys(response.data.checks) as Array<
        keyof DoctorResponse['data']['checks']
      >)
        response.data.checks[key] = false
      const { container } = show(locale, jsonResponse(response))

      const checks = await screen.findByRole('region', { name: text.checks })
      expect(within(checks).getAllByRole('article')).toHaveLength(5)
      expect(within(checks).getAllByText(text.notReady)).toHaveLength(5)
      expect(
        screen
          .getByRole('heading', { name: text.title, level: 1 })
          .closest('header'),
      ).toHaveTextContent(text.notReady)
      const codex = screen.getByRole('region', { name: 'Codex' })
      expect(within(codex).getByText(text.installed)).toBeVisible()
      expect(field(codex, text.remoteState)).toHaveTextContent(text.stopped)
      expectReadOnly(container)
    })

    it.each([true, false, null])(
      'preserves installation=%s, capability, authentication and Remote state as separate facts',
      async (installed) => {
        const response = doctorResponse()
        const capability =
          installed === true
            ? 'supported'
            : installed === false
              ? 'unsupported'
              : 'unknown'
        const authentication =
          installed === true
            ? 'authenticated'
            : installed === false
              ? 'unauthenticated'
              : 'unknown'
        const remote =
          installed === true
            ? 'running'
            : installed === false
              ? 'broken'
              : 'unknown'
        response.data.codex = {
          ...response.data.codex,
          installed,
          remote_control: capability,
          remote_state: remote,
        }
        response.data.claude = {
          ...response.data.claude,
          installed,
          tmux_installed: installed,
          remote_control: capability,
          authentication,
        }
        response.data.projects = {
          ...response.data.projects,
          github_cli_installed: installed,
          github_authentication: authentication,
        }
        show(locale, jsonResponse(response))

        const codex = await screen.findByRole('region', { name: 'Codex' })
        const expectedInstallation =
          installed === true
            ? text.installed
            : installed === false
              ? text.notInstalled
              : text.unknown
        expect(
          within(codex).getAllByText(expectedInstallation).length,
        ).toBeGreaterThan(0)
        expect(field(codex, text.capability)).toHaveTextContent(
          text[capability],
        )
        expect(field(codex, text.remoteState)).toHaveTextContent(text[remote])
        const claude = screen.getByRole('region', { name: 'Claude + tmux' })
        expect(field(claude, text.authentication)).toHaveTextContent(
          text[authentication],
        )
        expect(field(claude, text.capability)).toHaveTextContent(
          text[capability],
        )
        expect(
          within(claude).getAllByText(
            installed === true ? text.available : text.unknown,
          ).length,
        ).toBeGreaterThan(0)
        expect(field(claude, text.managed)).toHaveTextContent('1,234')
        expect(field(claude, text.unmanaged)).toHaveTextContent('2')
        expect(field(claude, text.warnings)).toHaveTextContent('1')
        const projects = screen.getByRole('region', {
          name: 'Projects + GitHub',
        })
        expect(field(projects, 'GitHub CLI')).toHaveTextContent(
          expectedInstallation,
        )
        expect(field(projects, text.githubAuthentication)).toHaveTextContent(
          text[authentication],
        )
      },
    )

    it('uses fixed local finding copy and keeps only valid known or unknown technical codes', async () => {
      const response = doctorResponse()
      const unknown = `FUTURE_${'A'.repeat(73)}`
      const rejected = [
        'server finding prose',
        'lowercase_code',
        'BAD-CODE',
        'A'.repeat(81),
        'SERVER\nCANARY',
        '诊断正文',
      ]
      response.data.codex.findings = [
        'CODEX_NOT_INSTALLED',
        unknown,
        ...rejected,
      ]
      show(locale, jsonResponse(response))

      const findings = await screen.findByRole('list', { name: text.findings })
      expect(within(findings).getAllByRole('listitem')).toHaveLength(2)
      expect(within(findings).getByText(text.knownFinding)).toBeVisible()
      expect(within(findings).getByText(text.unknownFinding)).toBeVisible()
      expectTechnical('CODEX_NOT_INSTALLED')
      expectTechnical(unknown)
      for (const value of rejected)
        expect(document.body.textContent).not.toContain(value)
      expect(document.body).not.toHaveTextContent('req_admin_doctor_fixture')
    })

    it('renders long printable values as inert LTR text and rejects non-ASCII or control-character technical values', async () => {
      const response = doctorResponse()
      const root = `/Projects/${'segment-'.repeat(70)}<img src=x>`
      const version = `${'long-version-'.repeat(30)}<script>inert()</script>`
      response.data.projects.project_root = root
      response.data.codex.version = version
      response.data.claude.version = 'CLAUDE\nUNSAFE'
      response.data.claude.tmux_version = '版本'
      response.data.projects.git_version = 'GIT\u202eUNSAFE'
      const { container } = show(locale, jsonResponse(response))

      await screen.findByText(root)
      expectTechnical(root)
      expectTechnical(version)
      expect(container.querySelector('script, img, a')).toBeNull()
      expect(document.body).not.toHaveTextContent('CLAUDE\nUNSAFE')
      expect(document.body.textContent).not.toContain('GIT\u202eUNSAFE')
      const claude = screen.getByRole('region', { name: 'Claude + tmux' })
      expect(field(claude, text.tmux)).toHaveTextContent(text.unknown)
      const projects = screen.getByRole('region', { name: 'Projects + GitHub' })
      expect(field(projects, 'Git')).toHaveTextContent(text.unknown)
      expectReadOnly(container)
    })

    it('announces loading without success or controls, then exposes only safe localized error evidence', async () => {
      const held = heldResponse()
      const { container, requests } = show(locale, held.promise)
      expect(screen.getByRole('status')).toHaveTextContent(text.loading)
      expect(
        screen.queryByRole('region', { name: text.checks }),
      ).not.toBeInTheDocument()
      expect(
        screen.queryByText(text.ready, { exact: true }),
      ).not.toBeInTheDocument()
      expectReadOnly(container)

      await act(async () =>
        held.resolve(
          jsonResponse(
            {
              request_id: 'req_doctor_safe_error',
              error: {
                code: 'ADMIN_READ_FAILED',
                message: 'DOCTOR SERVER PRIVATE PROSE CANARY',
              },
            },
            503,
          ),
        ),
      )
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent(text.unavailable)
      expect(alert).toHaveTextContent(text.error)
      expectTechnical('ADMIN_READ_FAILED')
      expectTechnical('req_doctor_safe_error')
      expect(document.body).not.toHaveTextContent(
        'DOCTOR SERVER PRIVATE PROSE CANARY',
      )
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
      expect(requests).toHaveLength(1)
      expectReadOnly(container)
    })
  },
)
