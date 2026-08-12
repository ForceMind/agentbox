import { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient } from '../../lib/api'
import { AuthContext, AuthContextValue } from '../auth/AuthContext'
import { useProject } from './useProjects'

const auth = {
  user: { id: 'adm_test', username: 'maintainer' },
  session: { id: 'ses_test', expires_at: '2026-08-12T00:00:00Z' },
  csrf_token: 'csrf-test-value',
}

const projectResponse = {
  api_version: 'v1',
  request_id: 'req_project',
  data: {
    id: 'prj_test',
    slug: 'test-project',
    display_name: 'Test Project',
    source_type: 'existing',
    state: 'ready',
    repository_url: null,
    default_branch: null,
    created_at: '2026-08-12T00:00:00Z',
    updated_at: '2026-08-12T00:00:00Z',
    git: null,
    github: null,
    claude_state: 'stopped',
  },
}

const jobResponse = {
  api_version: 'v1',
  request_id: 'req_job',
  data: {
    id: 'job_test',
    type: 'git.pull',
    status: 'queued',
    target_type: 'project',
    target_id: 'prj_test',
    project_id: 'prj_test',
    progress: 0,
    phase: 'queued',
    result_summary: null,
    error_code: null,
    error_summary: null,
    created_at: '2026-08-12T00:00:00Z',
    started_at: null,
    finished_at: null,
  },
}

function jsonResponse(status: number, body: object) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function wrapper(api: ApiClient) {
  const value: AuthContextValue = {
    api,
    auth,
    login: async () => undefined,
    logout: async () => undefined,
    refresh: async () => auth,
    status: 'authenticated',
  }
  return function AuthWrapper({ children }: { children: ReactNode }) {
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  }
}

describe('useProject mutation idempotency', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reuses the key after an uncertain transport failure', async () => {
    const keys: string[] = []
    let attempts = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/projects/prj_test')) {
          return Promise.resolve(jsonResponse(200, projectResponse))
        }
        if (path.endsWith('/git/pull')) {
          keys.push(
            (init?.headers as Record<string, string>)['Idempotency-Key'],
          )
          attempts += 1
          return attempts === 1
            ? Promise.reject(new TypeError('response lost'))
            : Promise.resolve(jsonResponse(202, jobResponse))
        }
        return Promise.resolve(jsonResponse(404, {}))
      }),
    )
    const { result, unmount } = renderHook(() => useProject('prj_test'), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.project?.id).toBe('prj_test'))

    await act(async () => result.current.mutate('git/pull'))
    expect(result.current.error?.status).toBe(0)
    await act(async () => result.current.mutate('git/pull'))

    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
    unmount()
  })

  it('generates a new key after a definitive HTTP failure', async () => {
    const keys: string[] = []
    let attempts = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = input.toString()
        if (path.endsWith('/api/v1/projects/prj_test')) {
          return Promise.resolve(jsonResponse(200, projectResponse))
        }
        if (path.endsWith('/git/push')) {
          keys.push(
            (init?.headers as Record<string, string>)['Idempotency-Key'],
          )
          attempts += 1
          return Promise.resolve(
            attempts === 1
              ? jsonResponse(409, {
                  error: { code: 'GIT_CONFLICT', message: 'Conflict' },
                })
              : jsonResponse(202, {
                  ...jobResponse,
                  data: { ...jobResponse.data, type: 'git.push' },
                }),
          )
        }
        return Promise.resolve(jsonResponse(404, {}))
      }),
    )
    const { result, unmount } = renderHook(() => useProject('prj_test'), {
      wrapper: wrapper(new ApiClient()),
    })
    await waitFor(() => expect(result.current.project?.id).toBe('prj_test'))

    await act(async () => result.current.mutate('git/push'))
    expect(result.current.error?.status).toBe(409)
    await act(async () => result.current.mutate('git/push'))

    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).not.toBe(keys[0])
    unmount()
  })
})
