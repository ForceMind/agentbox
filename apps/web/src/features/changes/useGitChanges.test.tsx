import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { ApiClient, ApiError } from '../../lib/api'
import type { GitChangePageResponse } from '../../lib/contracts'
import { useGitChanges } from './useGitChanges'

function page(path: string, nextCursor: string | null): GitChangePageResponse {
  return {
    api_version: 'v1',
    request_id: 'req_changes',
    data: {
      is_repository: true,
      files: [
        {
          path,
          previous_path: null,
          kind: 'modified',
          staged: false,
          unstaged: true,
        },
      ],
      total_count: 2,
      next_cursor: nextCursor,
    },
  }
}

const cursor = `${'a'.repeat(64)}:1`
const originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden')

function authContext(get: unknown): AuthContextValue {
  return {
    api: { get } as unknown as ApiClient,
    auth: {
      user: { id: 'adm_fixture', username: 'maintainer' },
      session: { id: 'ses_fixture', expires_at: '2026-12-31T00:00:00Z' },
      csrf_token: 'csrf_fixture',
    },
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

function withAuth(context: AuthContextValue) {
  return function wrapper({ children }: { children: ReactNode }) {
    return (
      <AuthContext.Provider value={context}>{children}</AuthContext.Provider>
    )
  }
}

afterEach(() => {
  if (originalHidden) Object.defineProperty(document, 'hidden', originalHidden)
})

describe('Project Git Changes observation', () => {
  it('pages a stable snapshot and clears it when the document is hidden', async () => {
    const get = vi.fn(async (path: string) =>
      path.includes('?cursor=')
        ? page('src/second.ts', null)
        : page('src/first.ts', cursor),
    )
    const { result } = renderHook(() => useGitChanges('prj_fixture'), {
      wrapper: withAuth(authContext(get)),
    })
    await waitFor(() =>
      expect(result.current.files.map((file) => file.path)).toEqual([
        'src/first.ts',
      ]),
    )
    await act(async () => result.current.loadMore())
    expect(result.current.files.map((file) => file.path)).toEqual([
      'src/first.ts',
      'src/second.ts',
    ])
    expect(result.current.nextCursor).toBeNull()

    Object.defineProperty(document, 'hidden', {
      configurable: true,
      value: true,
    })
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(result.current.stale).toBe(true)
    expect(result.current.files).toEqual([])

    Object.defineProperty(document, 'hidden', {
      configurable: true,
      value: false,
    })
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    await waitFor(() =>
      expect(result.current.files.map((file) => file.path)).toEqual([
        'src/first.ts',
      ]),
    )
    expect(get).toHaveBeenCalledTimes(3)
  })

  it('discards a late response after the formal Project changes', async () => {
    let finishOld: ((value: GitChangePageResponse) => void) | undefined
    const get = vi.fn((path: string) =>
      path.includes('project-a')
        ? new Promise<GitChangePageResponse>((resolve) => {
            finishOld = resolve
          })
        : Promise.resolve({
            ...page('project-b/file.ts', null),
            data: { ...page('project-b/file.ts', null).data, total_count: 1 },
          }),
    )
    const { result, rerender } = renderHook(
      ({ projectId }) => useGitChanges(projectId),
      {
        initialProps: { projectId: 'project-a' },
        wrapper: withAuth(authContext(get)),
      },
    )
    await waitFor(() => expect(finishOld).toBeDefined())
    rerender({ projectId: 'project-b' })
    await waitFor(() =>
      expect(result.current.files.map((file) => file.path)).toEqual([
        'project-b/file.ts',
      ]),
    )
    await act(async () => finishOld?.(page('project-a/stale.ts', null)))
    expect(result.current.files.map((file) => file.path)).toEqual([
      'project-b/file.ts',
    ])
  })

  it('hides previous Project paths on the first render after route change', async () => {
    let finishNew: ((value: GitChangePageResponse) => void) | undefined
    const get = vi.fn((path: string) =>
      path.includes('project-a')
        ? Promise.resolve({
            ...page('project-a/private.ts', null),
            data: {
              ...page('project-a/private.ts', null).data,
              total_count: 1,
            },
          })
        : new Promise<GitChangePageResponse>((resolve) => {
            finishNew = resolve
          }),
    )
    const { result, rerender } = renderHook(
      ({ projectId }) => useGitChanges(projectId),
      {
        initialProps: { projectId: 'project-a' },
        wrapper: withAuth(authContext(get)),
      },
    )
    await waitFor(() =>
      expect(result.current.files[0]?.path).toBe('project-a/private.ts'),
    )
    rerender({ projectId: 'project-b' })
    expect(result.current.files).toEqual([])
    await act(async () =>
      finishNew?.({
        ...page('project-b/file.ts', null),
        data: { ...page('project-b/file.ts', null).data, total_count: 1 },
      }),
    )
    expect(result.current.files[0]?.path).toBe('project-b/file.ts')
  })

  it('does not mix pages after the Runtime reports a changed snapshot', async () => {
    const get = vi.fn(async (path: string) => {
      if (path.includes('?cursor=')) {
        throw new ApiError({
          code: 'GIT_CHANGES_STALE',
          message: 'untrusted server detail',
          status: 409,
        })
      }
      return page('src/first.ts', cursor)
    })
    const { result } = renderHook(() => useGitChanges('prj_fixture'), {
      wrapper: withAuth(authContext(get)),
    })
    await waitFor(() => expect(result.current.files).toHaveLength(1))
    await act(async () => result.current.loadMore())
    expect(result.current.files).toEqual([])
    expect(result.current.stale).toBe(true)
    expect(result.current.error?.code).toBe('GIT_CHANGES_STALE')
    expect(JSON.stringify(result.current)).not.toContain(
      'untrusted server detail',
    )
  })
})
