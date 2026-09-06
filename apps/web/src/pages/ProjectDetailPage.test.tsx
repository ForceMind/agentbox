import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const useProjectMock = vi.hoisted(() => vi.fn())
const useClaudeProjectMock = vi.hoisted(() => vi.fn())

vi.mock('../features/projects/useProjects', () => ({
  useProject: useProjectMock,
}))

vi.mock('../features/claude/useClaude', () => ({
  useClaudeProject: useClaudeProjectMock,
}))

import { ProjectDetailPage } from './ProjectDetailPage'

const canary = 'RC9-PROJECT-DETAIL-SERVER-PROSE-CANARY-2R7D'

function project() {
  return {
    id: 'prj_fixture',
    slug: '用户-project',
    display_name: '用户 Project 🚀',
    source_type: 'git_clone' as const,
    state: 'ready' as const,
    repository_url: 'https://github.com/用户/仓库.git',
    default_branch: 'main',
    created_at: '2026-09-03T00:00:00Z',
    updated_at: '2026-09-03T00:00:00Z',
    git: {
      is_repository: true,
      branch: '功能/本地化',
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
      remote_url: 'https://github.com/用户/仓库.git',
      submodules_detected: true,
    },
    github: {
      available: true,
      repository: '用户/仓库',
      pull_request_number: 42,
      pull_request_title: '用户提交标题 🚀',
      pull_request_state: canary,
      pull_request_draft: true,
      pull_request_url: null,
      pull_request_base: '主分支',
      pull_request_head: '功能/本地化',
      mergeability: canary,
      checks: 'pending' as const,
    },
    claude_state: 'stopped' as const,
  }
}

function projectModel(overrides: Record<string, unknown> = {}) {
  return {
    branches: [
      { name: '功能/本地化', current: true },
      { name: 'main', current: false },
    ],
    busy: false,
    error: {
      code: 'RC9_UNKNOWN_PROJECT_ACTION',
      message: canary,
      requestId: 'req_project_detail_safe',
    },
    job: {
      id: 'job_project_detail',
      status: 'needs_attention' as const,
      phase: 'recovery_required' as const,
      progress: 25,
      error_code: 'GIT_PULL_REQUIRES_RECONCILIATION',
      error_summary: canary,
      result_summary: canary,
    },
    mutate: vi.fn(async () => undefined),
    pending: null,
    project: project(),
    refresh: vi.fn(async () => undefined),
    ...overrides,
  }
}

function claudeModel(overrides: Record<string, unknown> = {}) {
  return {
    action: vi.fn(async () => undefined),
    error: {
      code: 'CLAUDE_ACTION_FAILED',
      message: canary,
      requestId: 'req_claude_project_safe',
    },
    loading: false,
    pending: false,
    refresh: vi.fn(async () => undefined),
    session: {
      project_id: 'prj_fixture',
      display_name: '用户 Project 🚀',
      state: 'stopped' as const,
      workspace_state: 'unknown' as const,
      tmux_running: false,
      remote_readiness: 'unknown' as const,
      attach_command: null,
    },
    ...overrides,
  }
}

function renderDetail(locale: 'en' | 'zh-CN' = 'zh-CN') {
  return render(
    <MemoryRouter initialEntries={['/projects/prj_fixture']}>
      <Routes>
        <Route
          element={<ProjectDetailPage locale={locale} />}
          path="/projects/:projectId"
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProjectDetailPage localized safety boundary', () => {
  beforeEach(() => {
    useProjectMock.mockReset()
    useClaudeProjectMock.mockReset()
    useClaudeProjectMock.mockReturnValue(claudeModel())
  })

  it('localizes Git, PR, Claude and Job states without server prose', () => {
    const model = projectModel()
    useProjectMock.mockReturnValue(model)
    renderDetail()

    expect(
      screen.getByRole('heading', { name: '用户 Project 🚀' }),
    ).toBeVisible()
    expect(screen.getByText('用户 Project 🚀')).toHaveAttribute(
      'translate',
      'no',
    )
    expect(screen.queryByText('用户-project')).not.toBeInTheDocument()
    expect(screen.queryByText('功能/本地化')).not.toBeInTheDocument()
    expect(screen.queryByText('用户/仓库')).not.toBeInTheDocument()
    expect(screen.getByText('用户提交标题 🚀')).toHaveAttribute('dir', 'auto')
    const validBranch = screen.getByText('main')
    expect(validBranch).toHaveAttribute('lang', 'en')
    expect(validBranch).toHaveAttribute('dir', 'ltr')
    expect(validBranch).toHaveAttribute('translate', 'no')
    expect(screen.getAllByText('未知').length).toBeGreaterThanOrEqual(4)
    expect(screen.getByText('4 项变更')).toBeVisible()
    expect(screen.getByText('需要恢复')).toBeVisible()
    expect(screen.getByText('25%')).toBeVisible()
    expect(
      screen.getByText('GIT_PULL_REQUIRES_RECONCILIATION'),
    ).toHaveAttribute('lang', 'en')
    expect(screen.getByText('req_project_detail_safe')).toHaveAttribute(
      'translate',
      'no',
    )
    expect(document.body.textContent).not.toContain(canary)

    const branch = screen.getByLabelText('分支名称')
    fireEvent.change(branch, { target: { value: ' 新分支 ' } })
    fireEvent.click(screen.getByRole('button', { name: '创建分支' }))
    expect(model.mutate).toHaveBeenCalledWith('git/branches', {
      branch: '新分支',
    })

    fireEvent.change(screen.getByLabelText('Pull request 标题'), {
      target: { value: '用户 PR 标题' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建 Draft PR' }))
    expect(model.mutate).toHaveBeenCalledWith(
      'github/pull-requests',
      expect.objectContaining({ title: '用户 PR 标题' }),
    )

    fireEvent.click(screen.getByRole('button', { name: '启动 Claude' }))
    expect(
      useClaudeProjectMock.mock.results[0]?.value.action,
    ).toHaveBeenCalledWith('start')
  })

  it('renders localized loading and not-found failures safely', () => {
    useProjectMock.mockReturnValue(
      projectModel({ branches: [], error: null, job: null, project: null }),
    )
    const { unmount } = renderDetail('en')
    expect(screen.getByRole('status')).toHaveTextContent('Loading Project…')
    unmount()

    useProjectMock.mockReturnValue(
      projectModel({
        branches: [],
        error: {
          code: 'PROJECT_NOT_FOUND',
          message: canary,
          requestId: 'req_project_not_found',
        },
        job: null,
        project: null,
      }),
    )
    renderDetail('zh-CN')
    expect(
      screen.getByRole('heading', { name: 'Project 不可用' }),
    ).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent(
      '未找到请求的 Project。',
    )
    expect(document.body.textContent).not.toContain(canary)
  })

  it('uses localized pending labels for Git and Claude actions', () => {
    useProjectMock.mockReturnValue(
      projectModel({ busy: true, error: null, job: null, pending: 'git/pull' }),
    )
    useClaudeProjectMock.mockReturnValue(
      claudeModel({ error: null, pending: true }),
    )
    renderDetail('en')

    expect(screen.getByRole('button', { name: 'Pulling…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Starting…' })).toBeDisabled()
  })
})
