import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const useProjectsMock = vi.hoisted(() => vi.fn())
const useFavoritesMock = vi.hoisted(() => vi.fn())

vi.mock('../features/projects/useProjects', () => ({
  useProjects: useProjectsMock,
}))
vi.mock('../features/projects/useProjectFavorites', () => ({
  useProjectFavorites: useFavoritesMock,
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

function favorites(overrides: Record<string, unknown> = {}) {
  return {
    byProject: {},
    loaded: true,
    loading: false,
    stale: false,
    error: null,
    pending: new Set<string>(),
    notice: null,
    refresh: vi.fn(async () => undefined),
    setFavorite: vi.fn(async () => undefined),
    ...overrides,
  }
}

describe('ProjectsPage localized safety boundary', () => {
  beforeEach(() => {
    useProjectsMock.mockReset()
    useFavoritesMock.mockReset()
    useFavoritesMock.mockReturnValue(favorites())
  })

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

    fireEvent.click(screen.getByRole('button', { name: '新建 Project' }))
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

  it('starts with the project collection and opens only the selected form', () => {
    const data = model()
    useProjectsMock.mockReturnValue(data)
    render(
      <MemoryRouter>
        <ProjectsPage locale="en" />
      </MemoryRouter>,
    )
    expect(screen.getByRole('region', { name: 'Projects' })).toBeVisible()
    expect(
      screen.queryByLabelText('Project name', { exact: true }),
    ).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Repository URL')).not.toBeInTheDocument()
    const createTrigger = screen.getByRole('button', { name: 'New Project' })
    const cloneTrigger = screen.getByRole('button', {
      name: 'Clone Repository',
    })
    expect(createTrigger).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(createTrigger)
    const name = screen.getByLabelText('Project name', { exact: true })
    expect(name).toHaveFocus()
    fireEvent.change(name, { target: { value: 'Unsubmitted draft' } })
    fireEvent.click(cloneTrigger)
    expect(
      screen.queryByLabelText('Project name', { exact: true }),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText('Repository URL')).toHaveFocus()
    expect(createTrigger).toHaveAttribute('aria-expanded', 'false')
    expect(cloneTrigger).toHaveAttribute('aria-expanded', 'true')
    expect(data.create).not.toHaveBeenCalled()
    expect(data.clone).not.toHaveBeenCalled()
  })

  it.each(['create', 'clone'] as const)(
    'clears %s drafts on Escape and restores the entry focus',
    (mode) => {
      const data = model()
      useProjectsMock.mockReturnValue(data)
      render(
        <MemoryRouter>
          <ProjectsPage locale="en" />
        </MemoryRouter>,
      )
      const trigger = screen.getByRole('button', {
        name: mode === 'create' ? 'New Project' : 'Clone Repository',
      })
      fireEvent.click(trigger)
      const input = screen.getByLabelText(
        mode === 'create' ? 'Project name' : 'Repository URL',
        { exact: true },
      )
      fireEvent.change(input, { target: { value: 'Draft' } })
      if (mode === 'clone')
        fireEvent.change(screen.getByLabelText('Project name (optional)'), {
          target: { value: 'Draft name' },
        })
      fireEvent.keyDown(input, { key: 'Escape' })
      expect(trigger).toHaveFocus()
      expect(trigger).toHaveAttribute('aria-expanded', 'false')
      fireEvent.click(trigger)
      expect(
        screen.getByLabelText(
          mode === 'create' ? 'Project name' : 'Repository URL',
          { exact: true },
        ),
      ).toHaveValue('')
      if (mode === 'clone')
        expect(screen.getByLabelText('Project name (optional)')).toHaveValue('')
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(trigger).toHaveFocus()
      expect(data.create).not.toHaveBeenCalled()
      expect(data.clone).not.toHaveBeenCalled()
    },
  )

  it('does not cancel or resubmit a requested operation when dismissal is attempted', async () => {
    let finish!: () => void
    const create = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve
        }),
    )
    useProjectsMock.mockReturnValue(
      model({ create, job: { id: 'job_existing', status: 'running' } }),
    )
    render(
      <MemoryRouter>
        <ProjectsPage locale="en" />
      </MemoryRouter>,
    )
    const trigger = screen.getByRole('button', { name: 'New Project' })
    fireEvent.click(trigger)
    const input = screen.getByLabelText('Project name', { exact: true })
    fireEvent.change(input, { target: { value: 'New workspace' } })
    const form = input.closest('form')!
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(create).toHaveBeenCalledTimes(1)
    expect(input).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Clone Repository' }),
    ).toBeDisabled()
    fireEvent.keyDown(form, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    await act(async () => finish())
    expect(input).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(trigger).toHaveFocus()
    expect(screen.getByText('job_existing')).toBeVisible()
    expect(create).toHaveBeenCalledTimes(1)
  })

  it('keeps clone validation and clears both clone fields after the existing request resolves', async () => {
    const clone = vi.fn(async () => undefined)
    useProjectsMock.mockReturnValue(model({ clone }))
    render(
      <MemoryRouter>
        <ProjectsPage locale="zh-CN" />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: '克隆仓库' }))
    fireEvent.click(screen.getByRole('button', { name: '克隆' }))
    expect(screen.getByText('请输入仓库 URL。')).toBeVisible()
    expect(clone).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('仓库 URL'), {
      target: { value: ' https://github.com/owner/repo ' },
    })
    fireEvent.change(screen.getByLabelText('Project 名称（可选）'), {
      target: { value: ' My project ' },
    })
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: '克隆' })),
    )
    expect(clone).toHaveBeenCalledWith(
      'https://github.com/owner/repo',
      'My project',
    )
    expect(screen.getByLabelText('仓库 URL')).toHaveValue('')
    expect(screen.getByLabelText('Project 名称（可选）')).toHaveValue('')
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

  it('filters only loaded Project metadata and distinguishes no matches from no Projects', () => {
    useProjectsMock.mockReturnValue(
      model({
        projects: [
          project({
            id: 'prj_alpha',
            display_name: 'Alpha service',
            slug: 'alpha',
          }),
          project({ id: 'prj_beta', display_name: 'Beta docs', slug: 'beta' }),
        ],
      }),
    )
    render(
      <MemoryRouter>
        <ProjectsPage locale="en" />
      </MemoryRouter>,
    )
    const query = screen.getByRole('searchbox', { name: 'Search Projects' })
    fireEvent.change(query, { target: { value: 'beta' } })
    expect(screen.getByRole('status')).toHaveTextContent(
      'Showing 1 of 2 Projects',
    )
    expect(screen.getByRole('heading', { name: 'Beta docs' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Alpha service' })).toBeNull()

    fireEvent.change(query, { target: { value: 'missing' } })
    expect(
      screen.getByRole('heading', { name: 'No matching Projects' }),
    ).toBeVisible()
    expect(
      screen.queryByRole('heading', { name: 'No Projects yet' }),
    ).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(screen.getByRole('heading', { name: 'Alpha service' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Beta docs' })).toBeVisible()
  })

  it('keeps favorites separate from links and shows a saved favorite first', () => {
    useProjectsMock.mockReturnValue(
      model({
        projects: [
          project({
            id: 'prj_alpha',
            display_name: 'Alpha service',
            slug: 'alpha',
          }),
          project({ id: 'prj_beta', display_name: 'Beta docs', slug: 'beta' }),
        ],
      }),
    )
    const setFavorite = vi.fn(async () => undefined)
    useFavoritesMock.mockReturnValue(
      favorites({
        byProject: {
          prj_beta: {
            project_id: 'prj_beta',
            favorite: true,
            revision: 1,
            updated_at: '2026-09-29T00:00:00Z',
          },
        },
        setFavorite,
      }),
    )
    render(
      <MemoryRouter>
        <ProjectsPage locale="en" />
      </MemoryRouter>,
    )
    const grid = screen.getByRole('region', { name: 'Projects' })
    const cards = grid.querySelectorAll('.project-card')
    expect(cards[0]).toHaveTextContent('Beta docs')
    expect(
      screen.getByRole('button', { name: 'Remove from favorites: Beta docs' }),
    ).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(
      screen.getByRole('button', { name: 'Add to favorites: Alpha service' }),
    )
    expect(setFavorite).toHaveBeenCalledWith('prj_alpha')
  })
})
