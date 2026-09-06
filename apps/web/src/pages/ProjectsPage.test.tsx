import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const useProjectsMock = vi.hoisted(() => vi.fn())

vi.mock('../features/projects/useProjects', () => ({
  useProjects: useProjectsMock,
}))

import { ProjectsPage } from './ProjectsPage'

function project(overrides: Record<string, unknown> = {}) {
  return {
    id: 'prj_fixture',
    slug: '用户-project',
    display_name: '用户 Project 🚀',
    source_type: 'git_clone' as const,
    state: 'ready' as const,
    repository_url: 'https://github.com/owner/repo.git',
    default_branch: 'main',
    created_at: '2026-09-03T00:00:00Z',
    updated_at: '2026-09-03T00:00:00Z',
    git: {
      is_repository: true,
      branch: '功能/本地化',
      detached_head: false,
      unborn_branch: false,
      upstream: 'origin/main',
      ahead: 0,
      behind: 0,
      staged_count: 1,
      unstaged_count: 2,
      untracked_count: 0,
      conflicted_count: 0,
      clean: false,
      remote_url: 'https://github.com/用户/仓库.git',
      submodules_detected: false,
    },
    github: null,
    claude_state: 'needs_interaction' as const,
    ...overrides,
  }
}

function model(overrides: Record<string, unknown> = {}) {
  return {
    clone: vi.fn(async () => undefined),
    create: vi.fn(async () => undefined),
    error: null,
    job: null,
    loading: false,
    pending: false,
    projects: [project()],
    refresh: vi.fn(async () => undefined),
    ...overrides,
  }
}

describe('ProjectsPage localized safety boundary', () => {
  beforeEach(() => useProjectsMock.mockReset())

  it('localizes cards and Job failures without rendering server prose', () => {
    const canary = 'RC9-PROJECTS-SERVER-PROSE-CANARY-4M8W'
    useProjectsMock.mockReturnValue(
      model({
        error: {
          code: 'RC9_UNKNOWN_PROJECTS_ERROR',
          message: canary,
          requestId: 'req_projects_safe',
        },
        job: {
          id: 'job_projects_fixture',
          status: 'failed',
          phase: 'failed',
          progress: 25,
          error_code: 'GIT_AUTH_REQUIRED',
          error_summary: canary,
          result_summary: canary,
        },
      }),
    )

    render(
      <MemoryRouter>
        <ProjectsPage locale="zh-CN" />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('heading', { name: 'Projects' }),
    ).toBeInTheDocument()
    expect(screen.getByText('用户 Project 🚀')).toHaveAttribute(
      'translate',
      'no',
    )
    expect(screen.queryByText('功能/本地化')).not.toBeInTheDocument()
    expect(
      screen.queryByText('https://github.com/用户/仓库.git'),
    ).not.toBeInTheDocument()
    expect(screen.getAllByText('未知')).toHaveLength(2)
    expect(screen.getByText('需要交互')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(screen.getByText('GIT_AUTH_REQUIRED')).toHaveAttribute('lang', 'en')
    expect(screen.getByText('req_projects_safe')).toHaveAttribute('dir', 'ltr')
    expect(document.body.textContent).not.toContain(canary)
  })

  it('validates whitespace and exposes a bounded pending state', async () => {
    let finishCreate: (() => void) | undefined
    const create = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finishCreate = resolve
        }),
    )
    useProjectsMock.mockReturnValue(model({ create, projects: [] }))
    render(
      <MemoryRouter>
        <ProjectsPage locale="zh-CN" />
      </MemoryRouter>,
    )

    const name = screen.getByLabelText('Project 名称')
    fireEvent.change(name, { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: '创建 Project' }))
    expect(screen.getByText('请输入 Project 名称。')).toBeInTheDocument()
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(create).not.toHaveBeenCalled()

    fireEvent.change(name, { target: { value: '  新项目  ' } })
    fireEvent.click(screen.getByRole('button', { name: '创建 Project' }))
    expect(create).toHaveBeenCalledWith('新项目')
    expect(screen.getByRole('button', { name: '正在创建…' })).toBeDisabled()
    await act(async () => finishCreate?.())
  })

  it('covers localized loading and empty states', () => {
    useProjectsMock.mockReturnValue(model({ loading: true, projects: [] }))
    const { rerender } = render(
      <MemoryRouter>
        <ProjectsPage locale="en" />
      </MemoryRouter>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Loading Projects…')

    useProjectsMock.mockReturnValue(model({ loading: false, projects: [] }))
    rerender(
      <MemoryRouter>
        <ProjectsPage locale="zh-CN" />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('heading', { name: '还没有 Project' }),
    ).toBeVisible()
  })
})
