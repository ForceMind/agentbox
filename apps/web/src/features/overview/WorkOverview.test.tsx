import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { ApiClient, ApiError } from '../../lib/api'
import { type JobData, type ProjectData } from '../../lib/contracts'
import { parseRecentProjectListResponse } from './recentProjects'
import { WorkOverview } from './WorkOverview'

const PROJECT = `prj_${'a'.repeat(32)}`
const JOBS = '/api/v1/jobs?scope=mine'
const PROJECTS = '/api/v1/projects/recent'
const envelope = (data: unknown) => ({
  api_version: 'v1',
  request_id: 'req_overview',
  data,
})
function job(status: JobData['status'], id = `job_${status}`): JobData {
  return {
    id,
    type: 'project.clone',
    status,
    target_type: 'project',
    target_id: PROJECT,
    project_id: PROJECT,
    progress: 83,
    phase: 'UNTRUSTED-PHASE',
    result_summary: 'PRIVATE-RESULT',
    error_code: null,
    error_summary: 'PRIVATE-ERROR',
    created_at: '2026-10-05T00:00:00Z',
    started_at: null,
    finished_at: null,
  }
}
function project(overrides: Partial<ProjectData> = {}): ProjectData {
  return {
    id: PROJECT,
    slug: 'example',
    display_name: '项目 <script>inert()</script> 🚀',
    source_type: 'existing',
    state: 'ready',
    repository_url: null,
    default_branch: null,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-05T01:00:00Z',
    git: null,
    github: null,
    claude_state: null,
    ...overrides,
  }
}
function deferred() {
  let resolve!: (value: unknown) => void
  const promise = new Promise<unknown>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function setup(
  options: {
    jobs?: JobData[]
    projects?: ProjectData[]
    get?: (path: string, signal: AbortSignal) => Promise<unknown>
    locale?: 'en' | 'zh-CN'
  } = {},
) {
  const signals: AbortSignal[] = []
  const get = vi.fn(
    async (
      path: string,
      opts: {
        signal: AbortSignal
        validate: (value: unknown) => unknown
        timeoutMs: number
      },
    ) => {
      expect(opts.timeoutMs).toBe(15_000)
      signals.push(opts.signal)
      const value = options.get
        ? await options.get(path, opts.signal)
        : envelope(
            path === JOBS
              ? { jobs: options.jobs ?? [] }
              : { projects: options.projects ?? [] },
          )
      return opts.validate(value)
    },
  )
  const context: AuthContextValue = {
    api: { get } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_overview', username: 'maintainer' },
      session: { id: 'ses_overview', expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf-overview',
    },
    status: 'authenticated',
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }
  const view = (value: AuthContextValue) => (
    <AuthContext.Provider value={value}>
      <MemoryRouter>
        <WorkOverview locale={options.locale ?? 'en'} />
      </MemoryRouter>
    </AuthContext.Provider>
  )
  const rendered = render(view(context))
  return {
    get,
    signals,
    context,
    ...rendered,
    rerenderContext: (value: AuthContextValue) =>
      rendered.rerender(view(value)),
  }
}
afterEach(() => vi.restoreAllMocks())

describe('metadata-backed WorkOverview', () => {
  it('projects only explicit job states, bounded counts, inert names, real metadata time and existing links', async () => {
    const { get } = setup({
      jobs: [
        job('needs_attention'),
        job('running'),
        job('queued'),
        job('failed'),
        job('succeeded'),
        job('cancelled'),
      ],
      projects: [project()],
    })
    const attention = screen.getByRole('region', { name: 'Needs attention' })
    const active = screen.getByRole('region', { name: 'Active work' })
    expect(
      await within(attention).findByText('job_needs_attention'),
    ).toBeVisible()
    expect(within(attention).getByLabelText('In this window: 1')).toBeVisible()
    expect(within(active).getByLabelText('In this window: 2')).toBeVisible()
    expect(screen.getByText(/Counts cover only your 100/)).toBeVisible()
    expect(screen.getByText(/This is not last-used time/)).toBeVisible()
    expect(screen.getByText(project().display_name)).toHaveAttribute(
      'dir',
      'auto',
    )
    expect(
      document.querySelector('time[datetime="2026-10-05T01:00:00Z"]'),
    ).toBeVisible()
    expect(document.body.textContent).not.toMatch(
      /PRIVATE|UNTRUSTED|83|job_failed|job_succeeded|job_cancelled/,
    )
    expect(document.querySelector('script')).toBeNull()
    expect(
      within(attention).getByRole('link', { name: /Open project/ }),
    ).toHaveAttribute('href', `/projects/${PROJECT}`)
    expect(get.mock.calls.map((call) => call[0])).toEqual([JOBS, PROJECTS])
  })

  it('keeps a count for the complete returned window but shows at most six rows in each section', async () => {
    setup({
      jobs: Array.from({ length: 100 }, (_, i) => job('running', `job_${i}`)),
    })
    const active = screen.getByRole('region', { name: 'Active work' })
    expect(
      await within(active).findByLabelText('In this window: 100'),
    ).toBeVisible()
    expect(within(active).getAllByRole('listitem')).toHaveLength(6)
    expect(within(active).queryByText('job_6')).not.toBeInTheDocument()
  })

  it('does not turn unknown, oversized or malformed metadata into empty counts', async () => {
    setup({
      jobs: Array(101).fill(job('queued')),
      projects: [project({ updated_at: 'not-a-date' })],
    })
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(3))
    expect(screen.queryByLabelText(/In this window/)).not.toBeInTheDocument()
    expect(screen.queryByText(/No queued/)).not.toBeInTheDocument()
  })

  it('localizes loading and empty states without pretending there are zero jobs before load', async () => {
    const held = deferred()
    setup({ locale: 'zh-CN', get: () => held.promise })
    expect(screen.getAllByText('正在加载工作元数据…')).toHaveLength(3)
    expect(screen.queryByLabelText(/此窗口内/)).not.toBeInTheDocument()
    await act(async () => held.resolve(envelope({ jobs: [], projects: [] })))
    expect(await screen.findByText('此窗口内没有待处理的操作。')).toBeVisible()
    expect(screen.getByText('此窗口内没有排队或运行中的操作。')).toBeVisible()
    expect(screen.getByText(/尚无已登记的项目/)).toBeVisible()
  })

  it.each([401, 403])(
    'renders permission feedback for %i, keeps independent projects available, and never shows server prose',
    async (status) => {
      setup({
        get: async (path) => {
          if (path === JOBS)
            throw new ApiError({
              code: 'PRIVATE-CODE',
              message: 'PRIVATE-MESSAGE',
              status,
            })
          return envelope({ projects: [project()] })
        },
      })
      await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(2))
      expect(screen.getAllByRole('alert')[0]).toHaveTextContent(
        'You do not have access',
      )
      expect(screen.getByText(project().display_name)).toBeVisible()
      expect(document.body.textContent).not.toContain('PRIVATE')
    },
  )

  it('allows explicit retry after network failure without a polling loop', async () => {
    let fail = true
    const { get } = setup({
      get: async (path) => {
        if (fail) throw new Error('PRIVATE')
        return envelope(path === JOBS ? { jobs: [] } : { projects: [] })
      },
    })
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(3))
    expect(get).toHaveBeenCalledTimes(2)
    fail = false
    fireEvent.click(
      screen.getByRole('button', { name: 'Refresh work overview' }),
    )
    expect(
      await screen.findByText(
        'No queued or running operations in this window.',
      ),
    ).toBeVisible()
    expect(get).toHaveBeenCalledTimes(4)
  })

  it('clears stale rows while hidden and reads once on return despite duplicate lifecycle events', async () => {
    let visibility: DocumentVisibilityState = 'visible'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(
      () => visibility,
    )
    const { get } = setup({ jobs: [job('running')] })
    expect(await screen.findByText('job_running')).toBeVisible()
    visibility = 'hidden'
    fireEvent(document, new Event('visibilitychange'))
    expect(screen.queryByText('job_running')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/In this window/)).not.toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', { name: 'Refresh work overview' }),
    )
    expect(get).toHaveBeenCalledTimes(2)
    visibility = 'visible'
    fireEvent(document, new Event('visibilitychange'))
    fireEvent(window, new Event('pageshow'))
    fireEvent(window, new Event('online'))
    expect(await screen.findByText('job_running')).toBeVisible()
    expect(get).toHaveBeenCalledTimes(4)
  })

  it.each([
    ['offline', 'online', 'window'],
    ['pagehide', 'pageshow', 'window'],
    ['freeze', 'resume', 'document'],
  ] as const)(
    'fences %s and late responses until %s',
    async (stop, start, target) => {
      const held = deferred()
      let resumed = false
      const { get, signals } = setup({
        get: (path) =>
          resumed
            ? Promise.resolve(
                envelope(
                  path === JOBS
                    ? { jobs: [job('queued', 'job_new')] }
                    : { projects: [] },
                ),
              )
            : held.promise,
      })
      fireEvent(target === 'window' ? window : document, new Event(stop))
      expect(signals.every((signal) => signal.aborted)).toBe(true)
      await act(async () =>
        held.resolve(
          envelope({
            jobs: [job('running', 'job_old')],
            projects: [project()],
          }),
        ),
      )
      expect(screen.queryByText('job_old')).not.toBeInTheDocument()
      expect(screen.queryByText(project().display_name)).not.toBeInTheDocument()
      expect(get).toHaveBeenCalledTimes(2)
      fireEvent.click(
        screen.getByRole('button', { name: 'Refresh work overview' }),
      )
      expect(get).toHaveBeenCalledTimes(2)
      resumed = true
      fireEvent(target === 'window' ? window : document, new Event(start))
      expect(await screen.findByText('job_new')).toBeVisible()
      expect(get).toHaveBeenCalledTimes(4)
    },
  )

  it('fences user/session changes and unmount even when the old transport ignores abort', async () => {
    const old = deferred()
    const next = deferred()
    let changed = false
    const { context, rerenderContext, signals, unmount } = setup({
      get: () => (changed ? next.promise : old.promise),
    })
    changed = true
    rerenderContext({
      ...context,
      auth: { ...context.auth!, user: { id: 'adm_next', username: 'next' } },
    })
    expect(signals.slice(0, 2).every((signal) => signal.aborted)).toBe(true)
    await act(async () =>
      old.resolve(
        envelope({ jobs: [job('running', 'job_old')], projects: [project()] }),
      ),
    )
    expect(screen.queryByText('job_old')).not.toBeInTheDocument()
    unmount()
    expect(signals.every((signal) => signal.aborted)).toBe(true)
    await act(async () =>
      next.resolve(
        envelope({ jobs: [job('running', 'job_next')], projects: [] }),
      ),
    )
    expect(screen.queryByText('job_next')).not.toBeInTheDocument()
  })

  it('clears an already loaded snapshot when authentication is revoked and sends no extra GET', async () => {
    const { context, rerenderContext, get } = setup({ jobs: [job('running')] })
    expect(await screen.findByText('job_running')).toBeVisible()
    rerenderContext({ ...context, auth: null, status: 'unauthenticated' })
    expect(screen.queryByText('job_running')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/In this window/)).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('never turns a malformed project reference into a link', async () => {
    setup({ jobs: [{ ...job('needs_attention'), project_id: '../../other' }] })
    expect(await screen.findByText('job_needs_attention')).toBeVisible()
    expect(screen.getByText('No available project link')).toBeVisible()
    expect(
      screen.queryByRole('link', { name: /Open project/ }),
    ).not.toBeInTheDocument()
  })
})

describe('recent metadata parser', () => {
  it.each([
    [project({ updated_at: '2026-10-05T01:00:00' })],
    [project({ state: 'archived' })],
    [project({ claude_state: 'running' })],
    [project(), project()],
    Array(7).fill(project()),
    [project({ id: '../../escape' })],
  ])(
    'rejects ambiguous dates, runtime observations, duplicate or unbounded records %#',
    (...projects) => {
      expect(() =>
        parseRecentProjectListResponse(envelope({ projects })),
      ).toThrow()
    },
  )
})
