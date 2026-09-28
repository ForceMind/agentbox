import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
    result_summary: null,
    error_code:
      status === 'needs_attention' ? 'PROJECT_RECOVERY_REQUIRED' : null,
    error_summary: 'private server detail must stay hidden',
    created_at: '2026-09-28T00:00:00Z',
    started_at: null,
    finished_at: null,
  }
}

function response(jobs: JobData[]): JobListResponse {
  return {
    api_version: 'v1',
    request_id: 'req_attention',
    data: { jobs },
  }
}

function renderAttention(
  fetchJobs: (call: number) => JobListResponse | Error,
  locale: 'en' | 'zh-CN' = 'zh-CN',
) {
  let calls = 0
  const get = vi.fn(
    async (
      path: string,
      options: { validate: (value: unknown) => unknown },
    ) => {
      expect(path).toBe('/api/v1/jobs')
      const result = fetchJobs(++calls)
      if (result instanceof Error) throw result
      return options.validate(result)
    },
  )
  const context: AuthContextValue = {
    api: { get } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_attention', username: 'maintainer' },
      session: { id: 'ses_attention', expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf-attention',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
  render(
    <AuthContext.Provider value={context}>
      <MemoryRouter>
        <AttentionPage locale={locale} />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
  return get
}

afterEach(() => vi.restoreAllMocks())

describe('AttentionPage', () => {
  it('shows only real needs_attention Jobs and links a valid Project', async () => {
    const get = renderAttention(() =>
      response([
        job('succeeded', 'job_done'),
        job('needs_attention', 'job_review'),
      ]),
    )

    expect(await screen.findByText('job_review')).toBeVisible()
    expect(screen.queryByText('job_done')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /打开项目/ })).toHaveAttribute(
      'href',
      `/projects/${PROJECT}`,
    )
    expect(
      screen.queryByText('private server detail must stay hidden'),
    ).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('distinguishes an empty result from a failed query', async () => {
    const get = renderAttention(
      (call) => (call === 1 ? response([]) : new Error('private failure')),
      'en',
    )

    expect(
      await screen.findByText('No recent operations need attention.'),
    ).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Recent operations could not be loaded.',
    )
    expect(screen.queryByText('private failure')).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('invalidates the observation while hidden and reads again on return', async () => {
    let visibility: DocumentVisibilityState = 'visible'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(
      () => visibility,
    )
    const get = renderAttention((call) =>
      call === 1 ? response([job('needs_attention', 'job_old')]) : response([]),
    )

    expect(await screen.findByText('job_old')).toBeVisible()
    visibility = 'hidden'
    fireEvent(document, new Event('visibilitychange'))
    expect(screen.getByRole('status')).toHaveTextContent('状态已过期')
    expect(screen.queryByText('job_old')).not.toBeInTheDocument()

    visibility = 'visible'
    fireEvent(document, new Event('visibilitychange'))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('最近没有需要处理的操作。')).toBeVisible()
  })

  it('rejects a list that exceeds the server response bound', () => {
    expect(() =>
      parseJobListResponse(response(Array(101).fill(job('queued', 'job_x')))),
    ).toThrow('exceeds its bound')
  })
})
