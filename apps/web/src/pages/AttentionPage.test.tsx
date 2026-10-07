import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import { ApiClient } from '../lib/api'
import {
  parseJobListResponse,
  type JobData,
  type JobListResponse,
} from '../lib/contracts'
import { AttentionPage } from './AttentionPage'

const PROJECT = 'prj_' + 'a'.repeat(32)
const auth = {
  user: { id: 'adm_attention', username: 'maintainer' },
  session: { id: 'ses_attention', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'fixture-attention',
}
function job(status: JobData['status'], id: string): JobData {
  return {
    id,
    type: 'project.clone',
    status,
    target_type: 'project',
    target_id: PROJECT,
    project_id: PROJECT,
    progress: null,
    phase: null,
    result_summary: 'private result must stay hidden',
    error_code:
      status === 'needs_attention' ? 'PROJECT_RECOVERY_REQUIRED' : null,
    error_summary: 'private server detail must stay hidden',
    created_at: '2026-09-28T00:00:00Z',
    started_at: null,
    finished_at: null,
  }
}
function response(jobs: JobData[]): JobListResponse {
  return { api_version: 'v1', request_id: 'req_attention', data: { jobs } }
}
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function History() {
  const navigate = useNavigate()
  return (
    <nav aria-label="Test history">
      <button onClick={() => navigate(-1)}>Back</button>
      <button onClick={() => navigate(1)}>Forward</button>
    </nav>
  )
}
function setup(
  fetchJobs: (call: number) => Response | Promise<Response>,
  locale: 'en' | 'zh-CN' = 'en',
) {
  const signals: AbortSignal[] = []
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, options: RequestInit = {}) => {
      expect(input).toBe('/api/v1/jobs?scope=mine')
      expect(options.method).toBe('GET')
      signals.push(options.signal as AbortSignal)
      return fetchJobs(signals.length)
    },
  )
  vi.stubGlobal('fetch', fetchMock)
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
      <MemoryRouter initialEntries={['/attention']}>
        <History />
        <Routes>
          <Route
            path="/attention"
            element={<AttentionPage locale={locale} />}
          />
          <Route
            path="/projects/:projectId"
            element={<h1>Project destination</h1>}
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  )
  const view = render(ui())
  return {
    fetchMock,
    signals,
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
async function showJob(id: string, locale: 'en' | 'zh-CN' = 'en') {
  await screen.findByText(id)
  fireEvent.click(
    screen.getByText(locale === 'en' ? 'Technical details' : '技术详情'),
  )
  expect(screen.getByText(id)).toBeVisible()
}
beforeEach(() => {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('AttentionPage real read-only resource', () => {
  it('shows only needs_attention Jobs with actual reason, receivedAt and a valid Project link', async () => {
    const h = setup(
      () =>
        json(
          response([
            job('succeeded', 'job_done'),
            job('needs_attention', 'job_review'),
          ]),
        ),
      'zh-CN',
    )
    await showJob('job_review', 'zh-CN')
    expect(screen.queryByText('job_done')).not.toBeInTheDocument()
    expect(screen.getByText('PROJECT_RECOVERY_REQUIRED')).toBeVisible()
    expect(screen.getByRole('link', { name: '打开项目' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT}`,
    )
    expect(
      document.querySelector('time')?.getAttribute('datetime'),
    ).toBeTruthy()
    expect(document.body.textContent).not.toContain('private')
    expect(h.fetchMock).toHaveBeenCalledTimes(1)
  })

  it('distinguishes loading, empty, and failed reads and disables repeated refresh', async () => {
    const pending = deferred<Response>()
    const h = setup((call) =>
      call === 1
        ? pending.promise
        : json(
            { error: { code: 'UNAVAILABLE', message: 'private failure' } },
            500,
          ),
    )
    expect(screen.getByRole('status')).toHaveTextContent(
      'Checking recent operations',
    )
    const refresh = screen.getByRole('button', { name: 'Refresh' })
    expect(refresh).toBeDisabled()
    fireEvent.click(refresh)
    expect(h.fetchMock).toHaveBeenCalledTimes(1)
    await act(async () => {
      pending.resolve(json(response([])))
      await pending.promise
    })
    expect(
      await screen.findByText('No recent operations need attention.'),
    ).toBeVisible()
    expect(
      screen.getByText('This view covers your 100 most recently created Jobs.'),
    ).toBeVisible()
    fireEvent.click(refresh)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Recent operations could not be loaded.',
    )
    expect(document.body.textContent).not.toContain('private failure')
    expect(h.fetchMock).toHaveBeenCalledTimes(2)
  })

  it.each([401, 403])(
    'distinguishes permission failure %s from empty data',
    async (status) => {
      setup(() =>
        json(
          {
            error: { code: 'FORBIDDEN', message: 'private permission detail' },
          },
          status,
        ),
      )
      expect(await screen.findByRole('alert')).toHaveTextContent(
        'You do not have permission',
      )
      expect(
        screen.queryByText('No recent operations need attention.'),
      ).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled()
      expect(document.body.textContent).not.toContain('private permission')
    },
  )

  it.each(['hidden', 'offline', 'pagehide', 'freeze'] as const)(
    'clears received rows on %s and only reads again after resume',
    async (event) => {
      const h = setup((call) =>
        json(response(call === 1 ? [job('needs_attention', 'job_old')] : [])),
      )
      await showJob('job_old')
      if (event === 'hidden')
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
      fireEvent(
        event === 'hidden' || event === 'freeze' ? document : window,
        new Event(event === 'hidden' ? 'visibilitychange' : event),
      )
      expect(screen.getByRole('status')).toHaveTextContent(
        'Status is out of date',
      )
      expect(screen.queryByText('job_old')).not.toBeInTheDocument()
      expect(document.querySelector('time')).toBeNull()
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
      expect(h.fetchMock).toHaveBeenCalledTimes(1)
      if (event === 'hidden')
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
      const resume = {
        hidden: 'visibilitychange',
        offline: 'online',
        pagehide: 'pageshow',
        freeze: 'resume',
      }[event]
      fireEvent(
        event === 'hidden' || event === 'freeze' ? document : window,
        new Event(resume),
      )
      expect(
        await screen.findByText('No recent operations need attention.'),
      ).toBeVisible()
      expect(h.fetchMock).toHaveBeenCalledTimes(2)
    },
  )

  it('aborts old reads and rejects late rows after session replacement and logout', async () => {
    const old = deferred<Response>()
    const next = deferred<Response>()
    const h = setup((call) => (call === 1 ? old.promise : next.promise))
    h.identity('ses_next')
    expect(h.signals[0].aborted).toBe(true)
    await act(async () => {
      old.resolve(json(response([job('needs_attention', 'job_old')])))
      await old.promise
    })
    expect(screen.queryByText('job_old')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Checking recent operations',
    )
    h.identity(null)
    expect(h.signals[1].aborted).toBe(true)
    await act(async () => {
      next.resolve(json(response([job('needs_attention', 'job_next')])))
      await next.promise
    })
    expect(screen.queryByText('job_next')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('permission')
  })

  it('does not reopen a pagehide fence when the administrator session changes', async () => {
    const h = setup(() => json(response([job('needs_attention', 'job_old')])))
    await showJob('job_old')
    fireEvent(window, new Event('pagehide'))
    h.identity('ses_next')
    expect(screen.getByRole('status')).toHaveTextContent('out of date')
    expect(h.fetchMock).toHaveBeenCalledTimes(1)
    fireEvent(window, new Event('pageshow'))
    await waitFor(() => expect(h.fetchMock).toHaveBeenCalledTimes(2))
  })

  it('uses a real Project navigation link and clears expanded details after Back/Forward', async () => {
    const h = setup(() =>
      json(response([job('needs_attention', 'job_review')])),
    )
    await showJob('job_review')
    fireEvent.click(screen.getByRole('link', { name: 'Open project' }))
    expect(
      screen.getByRole('heading', { name: 'Project destination' }),
    ).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByText('job_review')).not.toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Forward' }))
    expect(
      screen.getByRole('heading', { name: 'Project destination' }),
    ).toBeVisible()
    expect(h.fetchMock).toHaveBeenCalledTimes(2)
  })

  it('hides malformed or secret-like protocol text and does not create an invalid Project link', async () => {
    const item = {
      ...job('needs_attention', 'Bearer private-token'),
      type: 'https://secret.example/token',
      project_id: '../outside',
      error_code: 'token=private-token',
    }
    setup(() => json(response([item])))
    expect(await screen.findByText('No project link')).toBeVisible()
    expect(
      screen.queryByRole('link', { name: 'Open project' }),
    ).not.toBeInTheDocument()
    expect(screen.getAllByText('Unknown').length).toBeGreaterThan(1)
    expect(document.body.textContent).not.toContain('private-token')
    expect(document.body.textContent).not.toContain('secret.example')
  })

  it('rejects a response beyond the recent 100 Jobs bound as an error', async () => {
    const oversized = response(
      Array.from({ length: 101 }, (_, i) => job('needs_attention', `job_${i}`)),
    )
    expect(() => parseJobListResponse(oversized)).toThrow('exceeds its bound')
    setup(() => json(oversized))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Recent operations could not be loaded.',
    )
    expect(screen.queryByText('job_0')).not.toBeInTheDocument()
  })
})
