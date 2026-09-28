import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { ApiClient, ApiError } from '../../lib/api'
import type {
  ProjectFavoriteListResponse,
  ProjectFavoriteResponse,
} from '../../lib/contracts'
import { useProjectFavorites } from './useProjectFavorites'

const projectId = `prj_${'a'.repeat(32)}`
const originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden')
const saved = {
  project_id: projectId,
  favorite: true,
  revision: 1,
  updated_at: '2026-09-29T00:00:00Z',
}
function list(favorites: ProjectFavoriteListResponse['data']['favorites']) {
  return {
    api_version: 'v1',
    request_id: 'req_list',
    data: { favorites },
  } as const
}
function response(data: ProjectFavoriteResponse['data']) {
  return { api_version: 'v1', request_id: 'req_set', data } as const
}
function context(
  get: unknown,
  request: unknown,
  sessionId = 'ses_first',
): AuthContextValue {
  return {
    api: { get, request } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_fixture', username: 'maintainer' },
      session: { id: sessionId, expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf_fixture',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}
function withAuth(value: AuthContextValue) {
  return function wrapper({ children }: { children: ReactNode }) {
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  }
}

afterEach(() => {
  if (originalHidden) Object.defineProperty(document, 'hidden', originalHidden)
})

describe('Project favorite browser observation', () => {
  it('waits for the server ACK before showing a favorite', async () => {
    let finish: ((value: ProjectFavoriteResponse) => void) | undefined
    const get = vi.fn(async () => list([]))
    const request = vi.fn(
      () =>
        new Promise<ProjectFavoriteResponse>((resolve) => {
          finish = resolve
        }),
    )
    const { result } = renderHook(() => useProjectFavorites(), {
      wrapper: withAuth(context(get, request)),
    })
    await waitFor(() => expect(result.current.loaded).toBe(true))
    let action: Promise<void> | undefined
    act(() => {
      action = result.current.setFavorite(projectId)
    })
    expect(result.current.pending.has(projectId)).toBe(true)
    expect(result.current.byProject[projectId]).toBeUndefined()
    expect(request).toHaveBeenCalledWith(
      `/api/v1/project-favorites/${projectId}`,
      expect.objectContaining({
        method: 'PUT',
        body: { favorite: true, expected_revision: 0 },
        csrfToken: 'csrf_fixture',
      }),
    )
    await act(async () => {
      finish?.(response(saved))
      await action
    })
    expect(result.current.byProject[projectId]).toEqual(saved)
    expect(result.current.pending.size).toBe(0)
  })

  it('re-reads after a conflict and never retries the mutation', async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(list([]))
      .mockResolvedValueOnce(list([saved]))
    const request = vi.fn(async () => {
      throw new ApiError({
        code: 'PROJECT_FAVORITE_CONFLICT',
        message: 'untrusted server prose',
        status: 409,
      })
    })
    const { result } = renderHook(() => useProjectFavorites(), {
      wrapper: withAuth(context(get, request)),
    })
    await waitFor(() => expect(result.current.loaded).toBe(true))
    await act(async () => result.current.setFavorite(projectId))
    await waitFor(() =>
      expect(result.current.byProject[projectId]).toEqual(saved),
    )
    expect(result.current.notice?.code).toBe('PROJECT_FAVORITE_CONFLICT')
    expect(request).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledTimes(2)
    expect(JSON.stringify(result.current)).not.toContain(
      'untrusted server prose',
    )
  })

  it('resolves an uncertain acknowledgment by GET without replaying PUT', async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(list([]))
      .mockResolvedValueOnce(list([saved]))
    const request = vi.fn(async () => {
      throw new ApiError({
        code: 'REQUEST_TIMEOUT',
        message: 'private proxy detail',
        status: 0,
      })
    })
    const { result } = renderHook(() => useProjectFavorites(), {
      wrapper: withAuth(context(get, request)),
    })
    await waitFor(() => expect(result.current.loaded).toBe(true))
    await act(async () => result.current.setFavorite(projectId))
    await waitFor(() =>
      expect(result.current.byProject[projectId]).toEqual(saved),
    )
    expect(result.current.notice?.code).toBe('PROJECT_FAVORITE_UNCERTAIN')
    expect(request).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledTimes(2)
    expect(JSON.stringify(result.current)).not.toContain('private proxy detail')
  })

  it('does not publish a mismatched successful acknowledgment', async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(list([]))
      .mockResolvedValueOnce(list([]))
    const request = vi.fn(async () =>
      response({ ...saved, project_id: `prj_${'b'.repeat(32)}` }),
    )
    const { result } = renderHook(() => useProjectFavorites(), {
      wrapper: withAuth(context(get, request)),
    })
    await waitFor(() => expect(result.current.loaded).toBe(true))
    await act(async () => result.current.setFavorite(projectId))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    expect(result.current.byProject[projectId]).toBeUndefined()
    expect(result.current.notice?.code).toBe('PROJECT_FAVORITE_UNCERTAIN')
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('clears loaded rows when the document hides and re-reads on return', async () => {
    const get = vi.fn(async () => list([saved]))
    const request = vi.fn()
    const { result } = renderHook(() => useProjectFavorites(), {
      wrapper: withAuth(context(get, request)),
    })
    await waitFor(() =>
      expect(result.current.byProject[projectId]).toEqual(saved),
    )
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      value: true,
    })
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(result.current.stale).toBe(true)
    expect(result.current.byProject).toEqual({})
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      value: false,
    })
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    await waitFor(() =>
      expect(result.current.byProject[projectId]).toEqual(saved),
    )
    expect(get).toHaveBeenCalledTimes(2)
    expect(request).not.toHaveBeenCalled()
  })

  it('discards previous-session rows before a new session response', async () => {
    const get = vi.fn(async () => list([saved]))
    const request = vi.fn()
    let current = context(get, request, 'ses_first')
    function wrapper({ children }: { children: ReactNode }) {
      return (
        <AuthContext.Provider value={current}>{children}</AuthContext.Provider>
      )
    }
    const { result, rerender } = renderHook(() => useProjectFavorites(), {
      wrapper,
    })
    await waitFor(() =>
      expect(result.current.byProject[projectId]).toEqual(saved),
    )
    current = context(get, request, 'ses_second')
    rerender()
    expect(result.current.byProject).toEqual({})
    await waitFor(() => expect(result.current.loaded).toBe(true))
  })
})
