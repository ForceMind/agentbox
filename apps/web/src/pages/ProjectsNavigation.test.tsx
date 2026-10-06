import { StrictMode, useEffect } from 'react'
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from '@testing-library/react'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const useProjectsMock = vi.hoisted(() => vi.fn())
const useFavoritesMock = vi.hoisted(() => vi.fn())
vi.mock('../features/projects/useProjects', () => ({
  useProjects: useProjectsMock,
}))
vi.mock('../features/projects/useProjectFavorites', () => ({
  useProjectFavorites: useFavoritesMock,
}))
import { ProjectsPage } from './ProjectsPage'
import { LogsPage } from './LogsPage'

const unmounted = vi.fn()
const create = vi.fn(async () => undefined)
const clone = vi.fn(async () => undefined)
const copy = {
  en: {
    create: 'New Project',
    clone: 'Clone Repository',
    name: 'Project name',
    url: 'Repository URL',
    cloneName: 'Project name (optional)',
    logs: 'Logs',
  },
  'zh-CN': {
    create: '新建 Project',
    clone: '克隆仓库',
    name: 'Project 名称',
    url: '仓库 URL',
    cloneName: 'Project 名称（可选）',
    logs: '日志',
  },
} as const

function Navigation() {
  const navigate = useNavigate()
  return (
    <nav>
      <button onClick={() => void navigate('/logs')}>Leave projects</button>
      <button onClick={() => void navigate(-1)}>History Back</button>
    </nav>
  )
}
function ProjectRoute({ locale }: { locale: keyof typeof copy }) {
  useEffect(
    () => () => {
      unmounted()
    },
    [],
  )
  return <ProjectsPage locale={locale} />
}

describe('Projects navigation draft lifecycle', () => {
  beforeEach(() => {
    unmounted.mockClear()
    create.mockClear()
    clone.mockClear()
    window.history.replaceState(null, '', '/projects')
    useProjectsMock.mockReturnValue({
      create,
      clone,
      projects: [],
      loading: false,
      pending: false,
      error: null,
      job: null,
      refresh: vi.fn(async () => undefined),
    })
    useFavoritesMock.mockReturnValue({
      byProject: {},
      loaded: true,
      loading: false,
      stale: false,
      error: null,
      pending: new Set(),
      notice: null,
      refresh: vi.fn(async () => undefined),
      setFavorite: vi.fn(async () => undefined),
    })
  })
  afterEach(cleanup)
  for (const locale of ['en', 'zh-CN'] as const) {
    for (const mode of ['create', 'clone'] as const) {
      it(`${locale} ${mode}: a completed route leave and history return clear unsaved drafts`, async () => {
        const expected = copy[locale]
        render(
          <StrictMode>
            <BrowserRouter>
              <Navigation />
              <Routes>
                <Route
                  path="/projects"
                  element={<ProjectRoute locale={locale} />}
                />
                <Route path="/logs" element={<LogsPage locale={locale} />} />
              </Routes>
            </BrowserRouter>
          </StrictMode>,
        )
        const trigger = mode === 'create' ? expected.create : expected.clone
        fireEvent.click(screen.getByRole('button', { name: trigger }))
        const field = mode === 'create' ? expected.name : expected.url
        fireEvent.change(screen.getByLabelText(field), {
          target: {
            value:
              mode === 'create'
                ? 'Synthetic unsaved draft'
                : 'https://github.com/example/synthetic.git',
          },
        })
        if (mode === 'clone')
          fireEvent.change(screen.getByLabelText(expected.cloneName), {
            target: { value: 'Synthetic clone name' },
          })
        const beforeLeave = unmounted.mock.calls.length
        fireEvent.click(screen.getByRole('button', { name: 'Leave projects' }))
        expect(
          await screen.findByRole('heading', { name: expected.logs, level: 1 }),
        ).toBeVisible()
        expect(unmounted).toHaveBeenCalledTimes(beforeLeave + 1)
        expect(screen.queryByLabelText(field)).not.toBeInTheDocument()
        await act(async () => {
          fireEvent.click(screen.getByRole('button', { name: 'History Back' }))
        })
        await waitFor(() => expect(window.location.pathname).toBe('/projects'))
        expect(
          await screen.findByRole('heading', { name: 'Projects', level: 1 }),
        ).toBeVisible()
        expect(screen.queryByLabelText(field)).not.toBeInTheDocument()
        fireEvent.click(screen.getByRole('button', { name: trigger }))
        expect(screen.getByLabelText(field)).toHaveValue('')
        if (mode === 'clone')
          expect(screen.getByLabelText(expected.cloneName)).toHaveValue('')
        expect(create).not.toHaveBeenCalled()
        expect(clone).not.toHaveBeenCalled()
      })
    }
  }
})
