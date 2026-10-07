import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import { ApiClient } from '../lib/api'
import type { ProjectData } from '../lib/contracts'
import { ProjectDetailPage } from './ProjectDetailPage'

const A = `prj_${'a'.repeat(32)}`
const B = `prj_${'b'.repeat(32)}`
const auth = {
  user: { id: 'adm_page', username: 'fixture' },
  session: { id: 'ses_page', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'fixture-csrf',
}
const envelope = (data: unknown) => ({
  api_version: 'v1',
  request_id: 'req_page',
  data,
})
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(envelope(data)), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

function project(id: string): ProjectData {
  return {
    id,
    slug: id === A ? 'alpha' : 'beta',
    display_name: id === A ? 'Alpha Project' : 'Beta Project',
    source_type: 'existing',
    state: 'ready',
    repository_url: null,
    default_branch: 'main',
    created_at: '2026-10-07T00:00:00Z',
    updated_at: '2026-10-07T00:00:00Z',
    claude_state: 'stopped',
    git: {
      is_repository: true,
      branch: 'main',
      detached_head: false,
      unborn_branch: false,
      upstream: 'origin/main',
      ahead: 1,
      behind: 0,
      staged_count: 1,
      unstaged_count: 0,
      untracked_count: 0,
      conflicted_count: 0,
      clean: false,
      remote_url: 'https://github.com/example/project.git',
      submodules_detected: false,
    },
    github: {
      available: true,
      repository: 'example/project',
      pull_request_number: null,
      pull_request_title: null,
      pull_request_state: null,
      pull_request_draft: null,
      pull_request_url: null,
      pull_request_base: null,
      pull_request_head: null,
      mergeability: null,
      checks: 'unknown',
    },
  }
}
function session(id: string) {
  return {
    project_id: id,
    display_name: 'Fixture',
    state: 'stopped',
    managed: true,
    session_name: 'fixture',
    attach_command: 'PRIVATE-ATTACH-COMMAND',
    workspace_state: 'unknown',
    tmux_running: false,
    remote_readiness: 'unknown',
  }
}
function job(id: string) {
  return {
    id: 'job_page',
    type: 'git.pull',
    status: 'queued',
    target_type: 'project',
    target_id: id,
    project_id: id,
    progress: null,
    phase: 'queued',
    result_summary: 'PRIVATE-RESULT',
    error_code: null,
    error_summary: 'PRIVATE-ERROR',
    created_at: '2026-10-07T00:00:00Z',
    started_at: null,
    finished_at: null,
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function Navigation() {
  const navigate = useNavigate()
  return (
    <nav aria-label="Test history">
      <button onClick={() => navigate(`/projects/${A}`)}>Alpha</button>
      <button onClick={() => navigate(`/projects/${B}`)}>Beta</button>
      <button onClick={() => navigate('/other')}>Other</button>
      <button onClick={() => navigate(-1)}>Back</button>
      <button onClick={() => navigate(1)}>Forward</button>
    </nav>
  )
}
function setup(
  options: {
    fetch?: (
      path: string,
      init: RequestInit,
    ) => Response | Promise<Response> | undefined
    state?: ProjectData['state']
  } = {},
) {
  const requests: { path: string; init: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const path = String(input)
      requests.push({ path, init })
      const custom = options.fetch?.(path, init)
      if (custom !== undefined) return custom
      if (init.method !== 'GET') throw new Error(`Unexpected mutation ${path}`)
      if (path === '/api/v1/project-labels') return json({ labels: [] })
      if (path.startsWith('/api/v1/project-labels/projects/'))
        return json({
          project_id: path.split('/').at(-1),
          labels: [],
          revision: 0,
          updated_at: null,
        })
      if (path.startsWith('/api/v1/claude/sessions/'))
        return json(session(path.split('/').at(-1)!))
      if (path.endsWith('/git/branches'))
        return json({
          branches: [
            { name: 'main', current: true },
            { name: 'feature/existing', current: false },
          ],
        })
      if (/\/api\/v1\/projects\/prj_[ab]{32}$/.test(path))
        return json({
          ...project(path.split('/').at(-1)!),
          ...(options.state ? { state: options.state } : {}),
        })
      throw new Error(`Unexpected GET ${path}`)
    }),
  )
  let context: AuthContextValue = {
    api: new ApiClient(),
    auth,
    status: 'authenticated',
    login: async () => undefined,
    logout: async () => undefined,
    refresh: async () => null,
  }
  const ui = () => (
    <AuthContext.Provider value={context}>
      <MemoryRouter initialEntries={[`/projects/${A}`]}>
        <Navigation />
        <Routes>
          <Route
            path="/projects/:projectId"
            element={<ProjectDetailPage locale="en" />}
          />
          <Route path="/other" element={<h1>Other page</h1>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  )
  const view = render(ui())
  return {
    requests,
    identity(sessionId: string | null) {
      context = {
        ...context,
        auth: sessionId
          ? { ...auth, session: { ...auth.session, id: sessionId } }
          : null,
        status: sessionId ? 'authenticated' : 'unauthenticated',
      }
      view.rerender(ui())
    },
  }
}
async function ready(name = 'Alpha Project', agentAvailable = true) {
  expect(await screen.findByRole('heading', { name })).toBeVisible()
  expect(
    await screen.findByText('No labels assigned to this Project.'),
  ).toBeVisible()
  if (agentAvailable)
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Start Claude' }),
      ).toBeEnabled(),
    )
}
function openBranch(value = 'feature/new') {
  fireEvent.click(screen.getByRole('button', { name: 'Manage branches' }))
  fireEvent.change(screen.getByLabelText('Branch name'), { target: { value } })
}
function openPr() {
  fireEvent.click(screen.getByRole('button', { name: 'Prepare Draft PR' }))
  fireEvent.change(screen.getByLabelText('Pull request title'), {
    target: { value: 'Private title' },
  })
  fireEvent.change(screen.getByLabelText('Pull request base branch'), {
    target: { value: 'release' },
  })
  fireEvent.change(screen.getByLabelText('Pull request body'), {
    target: { value: 'Private body' },
  })
}
function expectEmptyPr() {
  fireEvent.click(screen.getByRole('button', { name: 'Prepare Draft PR' }))
  expect(screen.getByLabelText('Pull request title')).toHaveValue('')
  expect(screen.getByLabelText('Pull request base branch')).toHaveValue('')
  expect(screen.getByLabelText('Pull request body')).toHaveValue('')
}

beforeEach(() => {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ProjectDetailPage real router and request lifecycle', () => {
  it('clears Branch/PR drafts on Cancel and Escape, returns focus, and never mutates', async () => {
    const h = setup()
    await ready()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    openBranch()
    expect(screen.getByLabelText('Branch name')).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(
      screen.getByRole('button', { name: 'Manage branches' }),
    ).toHaveFocus()
    openBranch('')
    expect(screen.getByLabelText('Branch name')).toHaveValue('')
    fireEvent.keyDown(screen.getByLabelText('Branch name'), { key: 'Escape' })
    expect(
      screen.getByRole('button', { name: 'Manage branches' }),
    ).toHaveFocus()
    openPr()
    fireEvent.keyDown(screen.getByLabelText('Pull request body'), {
      key: 'Escape',
    })
    expect(
      screen.getByRole('button', { name: 'Prepare Draft PR' }),
    ).toHaveFocus()
    expectEmptyPr()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(h.requests.every(({ init }) => init.method === 'GET')).toBe(true)
  })

  it('owns all drafts by Project and resets through real A → B → Back → Forward', async () => {
    const h = setup()
    await ready()
    openPr()
    fireEvent.click(screen.getByRole('button', { name: 'Beta' }))
    expect(
      screen.queryByRole('heading', { name: 'Alpha Project' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await ready('Beta Project')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    openBranch('beta-private')
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(
      screen.queryByRole('heading', { name: 'Beta Project' }),
    ).not.toBeInTheDocument()
    await ready()
    expectEmptyPr()
    fireEvent.click(screen.getByRole('button', { name: 'Forward' }))
    await ready('Beta Project')
    fireEvent.click(screen.getByRole('button', { name: 'Manage branches' }))
    expect(screen.getByLabelText('Branch name')).toHaveValue('')
    expect(h.requests.every(({ init }) => init.method === 'GET')).toBe(true)
  })

  it('does not restore forms after leaving the page and using Back', async () => {
    setup()
    await ready()
    openBranch()
    fireEvent.click(screen.getByRole('button', { name: 'Other' }))
    expect(screen.getByRole('heading', { name: 'Other page' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Manage branches' }))
    expect(screen.getByLabelText('Branch name')).toHaveValue('')
  })

  it('recovers a failed Project read with explicit refresh and clears drafts without replaying writes', async () => {
    const pending = deferred<Response>()
    let reads = 0
    const h = setup({
      fetch: (path, init) => {
        if (init.method !== 'GET' || path !== `/api/v1/projects/${A}`)
          return undefined
        reads += 1
        if (reads === 1)
          return new Response(
            JSON.stringify({
              error: {
                code: 'CONTROL_PLANE_UNAVAILABLE',
                message: 'private failure',
              },
            }),
            { status: 503, headers: { 'Content-Type': 'application/json' } },
          )
        if (reads === 2) return pending.promise
        return undefined
      },
    })
    expect(await screen.findByRole('alert')).toBeVisible()
    const refresh = screen.getByRole('button', { name: 'Refresh Project' })
    expect(refresh).toBeEnabled()
    fireEvent.click(refresh)
    expect(refresh).toBeDisabled()
    fireEvent.click(refresh)
    expect(reads).toBe(2)
    await act(async () => {
      pending.resolve(json(project(A)))
      await pending.promise
    })
    await ready()
    openPr()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh Project' }))
    await ready()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expectEmptyPr()
    expect(h.requests.every(({ init }) => init.method === 'GET')).toBe(true)
    expect(document.body.textContent).not.toContain('private failure')
  })

  it('clears drafts and observations on administrator session replacement and logout', async () => {
    const h = setup()
    await ready()
    openPr()
    h.identity('ses_replacement')
    expect(screen.queryByDisplayValue('Private title')).not.toBeInTheDocument()
    await ready()
    expectEmptyPr()
    h.identity(null)
    expect(
      screen.queryByRole('heading', { name: 'Alpha Project' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('permission')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it.each(['offline', 'pagehide', 'freeze', 'hidden'] as const)(
    'clears forms on %s and resumes with GET only',
    async (event) => {
      const h = setup()
      await ready()
      openPr()
      if (event === 'hidden')
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
      fireEvent(
        event === 'hidden' || event === 'freeze' ? document : window,
        new Event(event === 'hidden' ? 'visibilitychange' : event),
      )
      expect(screen.getByRole('status')).toHaveTextContent('out of date')
      expect(
        screen.getByRole('button', { name: 'Refresh Project' }),
      ).toBeDisabled()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      const count = h.requests.length
      await act(async () => {
        await Promise.resolve()
      })
      expect(h.requests).toHaveLength(count)
      if (event === 'hidden')
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
      const resume = {
        offline: 'online',
        pagehide: 'pageshow',
        freeze: 'resume',
        hidden: 'visibilitychange',
      }[event]
      fireEvent(
        event === 'hidden' || event === 'freeze' ? document : window,
        new Event(resume),
      )
      await ready()
      expectEmptyPr()
      expect(h.requests.every(({ init }) => init.method === 'GET')).toBe(true)
    },
  )

  it('disables repeated writes while pending and closing does not cancel an accepted Job', async () => {
    const post = deferred<Response>()
    const h = setup({
      fetch: (path, init) =>
        init.method === 'POST' && path.endsWith('/github/pull-requests')
          ? post.promise
          : undefined,
    })
    await ready()
    openPr()
    fireEvent.click(screen.getByRole('button', { name: 'Create Draft PR' }))
    expect(screen.getByRole('button', { name: 'Creating…' })).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Refresh Project' }),
    ).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Creating…' }))
    expect(
      h.requests.filter(({ init }) => init.method === 'POST'),
    ).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(
      screen.getByRole('button', { name: 'Prepare Draft PR' }),
    ).toHaveFocus()
    await act(async () => {
      post.resolve(json(job(A)))
      await post.promise
    })
    expect(
      await screen.findByRole('heading', { name: 'Latest operation' }),
    ).toBeVisible()
    expect(screen.getByText('job_page')).toBeVisible()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pull' })).toBeDisabled()
    expect(document.body.textContent).not.toContain('PRIVATE-')
  })

  it.each(['pagehide', 'freeze'] as const)(
    'retains the %s fence through route and session changes until resume',
    async (event) => {
      const h = setup()
      await ready()
      openPr()
      fireEvent(event === 'freeze' ? document : window, new Event(event))
      const requests = h.requests.length
      h.identity('ses_suspended')
      fireEvent.click(screen.getByRole('button', { name: 'Beta' }))
      expect(screen.getByRole('status')).toHaveTextContent('out of date')
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      await act(async () => {
        await Promise.resolve()
      })
      expect(h.requests).toHaveLength(requests)
      fireEvent(
        event === 'freeze' ? document : window,
        new Event(event === 'freeze' ? 'resume' : 'pageshow'),
      )
      await ready('Beta Project')
      expectEmptyPr()
      expect(h.requests.every(({ init }) => init.method === 'GET')).toBe(true)
    },
  )

  it('rejects a late Project A operation after navigating to Project B', async () => {
    const post = deferred<Response>()
    const h = setup({
      fetch: (_path, init) =>
        init.method === 'POST' ? post.promise : undefined,
    })
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Pull' }))
    fireEvent.click(screen.getByRole('button', { name: 'Beta' }))
    await ready('Beta Project')
    await act(async () => {
      post.resolve(json(job(A)))
      await post.promise
    })
    expect(screen.queryByText('job_page')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pull' })).toBeEnabled()
    expect(
      h.requests.filter(({ init }) => init.method === 'POST'),
    ).toHaveLength(1)
  })

  it('recovers an interrupted Job poll by reading its known identity without repeating the operation', async () => {
    let jobReads = 0
    const h = setup({
      fetch: (path, init) => {
        if (init.method === 'POST') return json(job(A))
        if (path === '/api/v1/jobs/job_page') {
          jobReads += 1
          if (jobReads === 1)
            return new Response(
              JSON.stringify({
                error: {
                  code: 'CONTROL_PLANE_UNAVAILABLE',
                  message: 'private poll failure',
                },
              }),
              { status: 503, headers: { 'Content-Type': 'application/json' } },
            )
          return json({ ...job(A), status: 'succeeded', phase: 'succeeded' })
        }
        return undefined
      },
    })
    await ready()
    vi.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Pull' }))
    })
    expect(screen.getByText('job_page')).toBeVisible()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750)
    })
    expect(jobReads).toBe(1)
    expect(screen.getByRole('alert')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Pull' })).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Refresh Project' }),
    ).toBeEnabled()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Refresh Project' }))
    })
    vi.useRealTimers()
    await ready()
    expect(screen.getByRole('status')).toHaveTextContent('Succeeded')
    expect(screen.getByRole('button', { name: 'Pull' })).toBeEnabled()
    expect(jobReads).toBe(2)
    expect(
      h.requests.filter(({ init }) => init.method === 'POST'),
    ).toHaveLength(1)
    expect(document.body.textContent).not.toContain('private poll failure')
  })

  it('withholds Workspace/Changes and all mutations for a non-READY Project', async () => {
    const h = setup({ state: 'creating' })
    await ready('Alpha Project', false)
    expect(
      screen.queryByRole('link', { name: 'Open Interactive Workspace' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'View changed paths' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pull' })).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Prepare Draft PR' }),
    ).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Start Claude' })).toBeDisabled()
    await waitFor(() =>
      expect(h.requests.every(({ init }) => init.method === 'GET')).toBe(true),
    )
  })
})
