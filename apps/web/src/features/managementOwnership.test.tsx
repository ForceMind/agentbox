import { StrictMode, type ReactNode } from 'react'
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient } from '../lib/api'
import type {
  AuthData,
  ClaudeSessionResponse,
  ClaudeStatusResponse,
  CodexStatusResponse,
} from '../lib/contracts'
import { ClaudePage } from '../pages/ClaudePage'
import { CodexPage } from '../pages/CodexPage'
import { AuthContext, type AuthContextValue } from './auth/AuthContext'
import { useClaude } from './claude/useClaude'
import { useCodex } from './codex/useCodex'

const authA: AuthData = {
  user: { id: 'user-a', username: 'owner-fixture' },
  session: { id: 'session-a', expires_at: '2026-12-31T00:00:00Z' },
  csrf_token: 'csrf-a',
}
const authB: AuthData = {
  ...authA,
  session: { ...authA.session, id: 'session-b' },
  csrf_token: 'csrf-b',
}
const codexStatus: CodexStatusResponse = {
  api_version: 'v1',
  request_id: 'req_codex_owner',
  data: {
    installed: true,
    version: '1.fixture',
    selected_executable: '/fixture/codex',
    alternatives: [],
    installation_type: 'standalone',
    conflict_detected: false,
    authentication: 'authenticated',
    capabilities: {
      remote_control: 'supported',
      start: 'supported',
      stop: 'supported',
      pair: 'supported',
      status: 'unsupported',
    },
    remote_state: 'stopped',
    remote_confidence: 'reported',
    diagnostics: [],
  },
}
const claudeStatus: ClaudeStatusResponse = {
  api_version: 'v1',
  request_id: 'req_claude_owner',
  data: {
    installed: true,
    version: '1.fixture',
    authentication: 'authenticated',
    capabilities: {
      remote_control: 'supported',
      remote_start: 'supported',
      version: 'supported',
    },
    tmux_installed: true,
    tmux_version: '3.fixture',
    managed_sessions: 1,
    unmanaged_sessions: 0,
    workspace_interaction_warnings: 0,
    diagnostics: [],
  },
}
const session: ClaudeSessionResponse['data'] = {
  project_id: 'project-a',
  display_name: 'Project fixture',
  state: 'running',
  managed: true,
  session_name: 'agentbox-claude-project-a',
  attach_command: 'tmux attach-session -t =agentbox-claude-project-a',
  workspace_state: 'unknown',
  tmux_running: true,
  remote_readiness: 'ready',
}
function pair(code = 'PAIR-OWNER-A') {
  return {
    api_version: 'v1',
    request_id: 'req_pair_owner',
    data: { pair_code: code, expires_at: null, display_once: true },
  }
}
function output(text = 'OUTPUT-OWNER-A') {
  return {
    api_version: 'v1',
    request_id: 'req_output_owner',
    data: {
      project_id: session.project_id,
      session_name: session.session_name,
      output: text,
      truncated: false,
      sensitive: true,
    },
  }
}
function actionResponse() {
  return {
    api_version: 'v1',
    request_id: 'req_action_owner',
    data: {
      outcome: 'stopped',
      session: { ...session, state: 'stopped', tmux_running: false },
    },
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}
function fixture(strict = false) {
  const api = new ApiClient()
  const get = vi.spyOn(api, 'get').mockImplementation(async (path) => {
    if (path === '/api/v1/codex/status') return codexStatus
    if (path === '/api/v1/claude') return claudeStatus
    if (path === '/api/v1/claude/sessions')
      return {
        api_version: 'v1',
        request_id: 'req_sessions_owner',
        data: { sessions: [session] },
      }
    if (path.endsWith('/output')) return output()
    throw new Error('Unexpected fixture read')
  })
  const post = vi
    .spyOn(api, 'post')
    .mockImplementation(async (path) =>
      path.endsWith('/pair-codes') ? pair() : actionResponse(),
    )
  let auth: AuthData | null = authA
  const wrapper = ({ children }: { children: ReactNode }) => {
    const value: AuthContextValue = {
      api,
      auth,
      status: auth ? 'authenticated' : 'unauthenticated',
      login: async () => {},
      logout: async () => {},
      refresh: async () => auth,
    }
    const provider = (
      <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    )
    return strict ? <StrictMode>{provider}</StrictMode> : provider
  }
  return {
    api,
    get,
    post,
    wrapper,
    replace: (next: AuthData | null) => {
      auth = next
    },
  }
}
async function settle() {
  await act(async () => {})
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('management hook owner lifetime', () => {
  it.each([
    ['session', authB],
    ['user', { ...authA, user: { ...authA.user, id: 'user-b' } }],
    ['CSRF', { ...authA, csrf_token: 'csrf-rotated' }],
  ] as const)(
    'masks shown Pair/output on the first %s replacement render and blocks old closures',
    async (_kind, replacement) => {
      const f = fixture()
      const snapshots: Array<{
        pair: string | undefined
        output: string | undefined
        codex: string
        claude: string
      }> = []
      const { result, rerender, unmount } = renderHook(
        () => {
          const codex = useCodex()
          const claude = useClaude()
          snapshots.push({
            pair: codex.pair?.pair_code,
            output: claude.outputs['project-a']?.output,
            codex: codex.view.status,
            claude: claude.view.status,
          })
          return { codex, claude }
        },
        { wrapper: f.wrapper },
      )
      await waitFor(() =>
        expect(result.current.claude.view.status).toBe('loaded'),
      )
      await act(async () => {
        await result.current.codex.generatePairCode()
        await result.current.claude.revealOutput('project-a')
      })
      const old = result.current
      expect(old.codex.pair?.pair_code).toBe('PAIR-OWNER-A')
      expect(old.claude.outputs['project-a']?.output).toBe('OUTPUT-OWNER-A')
      snapshots.length = 0
      f.replace(replacement)
      rerender()
      expect(snapshots[0]).toEqual({
        pair: undefined,
        output: undefined,
        codex: 'loading',
        claude: 'loading',
      })
      await settle()
      const reads = f.get.mock.calls.length
      const writes = f.post.mock.calls.length
      await act(async () => {
        await old.codex.refresh()
        await old.codex.remoteAction('start')
        await old.codex.generatePairCode()
        await old.claude.refresh()
        await old.claude.sessionAction('project-a', 'stop')
        await old.claude.revealOutput('project-a')
      })
      expect(f.get).toHaveBeenCalledTimes(reads)
      expect(f.post).toHaveBeenCalledTimes(writes)
      await act(async () => {
        await result.current.codex.generatePairCode()
        await result.current.claude.revealOutput('project-a')
      })
      act(() => {
        old.codex.clearPair()
        old.claude.hideOutput('project-a')
      })
      expect(result.current.codex.pair).not.toBeNull()
      expect(result.current.claude.outputs['project-a']).toBeDefined()
      const current = result.current
      unmount()
      const finalReads = f.get.mock.calls.length
      const finalWrites = f.post.mock.calls.length
      await current.codex.refresh()
      await current.codex.generatePairCode()
      await current.codex.remoteAction('stop')
      await current.claude.refresh()
      await current.claude.revealOutput('project-a')
      await current.claude.sessionAction('project-a', 'start')
      current.codex.clearPair()
      current.claude.hideOutput('project-a')
      expect(f.get).toHaveBeenCalledTimes(finalReads)
      expect(f.post).toHaveBeenCalledTimes(finalWrites)
    },
  )

  it.each(['resolve', 'reject'] as const)(
    'keeps new Pair pending when old %s/finally arrives, then allows explicit retry',
    async (outcome) => {
      const f = fixture()
      const oldRequest = deferred<ReturnType<typeof pair>>()
      const newRequest = deferred<ReturnType<typeof pair>>()
      f.post
        .mockImplementationOnce(() => oldRequest.promise)
        .mockImplementationOnce(() => newRequest.promise)
      const { result, rerender } = renderHook(() => useCodex(), {
        wrapper: f.wrapper,
      })
      await settle()
      let oldAction!: Promise<void>
      act(() => {
        oldAction = result.current.generatePairCode()
      })
      const oldSignal = f.post.mock.calls[0][1]?.signal
      f.replace(authB)
      rerender()
      await settle()
      expect(oldSignal?.aborted).toBe(true)
      let newAction!: Promise<void>
      act(() => {
        newAction = result.current.generatePairCode()
      })
      await act(async () => {
        if (outcome === 'resolve') oldRequest.resolve(pair())
        else oldRequest.reject(new Error('old failure'))
        await oldAction
      })
      expect(result.current.pending).toBe('pair')
      expect(result.current.actionError).toBeNull()
      expect(result.current.pair).toBeNull()
      await act(async () => {
        newRequest.reject(new Error('new failure'))
        await newAction
      })
      expect(result.current.pending).toBeNull()
      expect(result.current.actionError?.code).toBe('CODEX_PAIR_FAILED')
      expect(f.post).toHaveBeenCalledTimes(2)
      await act(async () => result.current.generatePairCode())
      expect(result.current.pair).not.toBeNull()
      expect(f.post).toHaveBeenLastCalledWith(
        '/api/v1/codex/pair-codes',
        expect.objectContaining({ csrfToken: 'csrf-b', timeoutMs: 130000 }),
      )
    },
  )

  it('synchronously deduplicates Pair and Remote calls until the owning action settles', async () => {
    const f = fixture()
    const request = deferred<ReturnType<typeof pair>>()
    f.post.mockImplementationOnce(() => request.promise)
    const { result } = renderHook(() => useCodex(), { wrapper: f.wrapper })
    await settle()
    const actions = result.current
    let first!: Promise<void>
    await act(async () => {
      first = actions.generatePairCode()
      await actions.generatePairCode()
      await actions.remoteAction('start')
      await actions.remoteAction('stop')
    })
    expect(f.post).toHaveBeenCalledTimes(1)
    expect(result.current.pending).toBe('pair')
    await act(async () => {
      request.resolve(pair())
      await first
    })
    expect(result.current.pending).toBeNull()
    await act(async () => result.current.remoteAction('start'))
    expect(f.post).toHaveBeenCalledTimes(2)
    expect(result.current.pending).toBeNull()
  })

  it('does not refresh or replay after an old Remote mutation settles', async () => {
    const f = fixture()
    const oldRequest = deferred<unknown>()
    f.post.mockImplementationOnce(() => oldRequest.promise)
    const { result, rerender } = renderHook(() => useCodex(), {
      wrapper: f.wrapper,
    })
    await settle()
    let action!: Promise<void>
    act(() => {
      action = result.current.remoteAction('start')
    })
    f.replace(authB)
    rerender()
    await settle()
    const reads = f.get.mock.calls.length
    await act(async () => {
      oldRequest.resolve({})
      await action
    })
    expect(f.get).toHaveBeenCalledTimes(reads)
    expect(f.post).toHaveBeenCalledTimes(1)
  })

  it.each(['output', 'mutation'] as const)(
    'isolates old Claude %s and its finally from a new same-Project operation',
    async (kind) => {
      const f = fixture()
      const oldRequest = deferred<unknown>()
      const newRequest = deferred<unknown>()
      if (kind === 'output') {
        const normal = f.get.getMockImplementation()!
        let count = 0
        f.get.mockImplementation((path, options) =>
          path.endsWith('/output')
            ? ++count === 1
              ? oldRequest.promise
              : newRequest.promise
            : normal(path, options),
        )
      } else
        f.post
          .mockImplementationOnce(() => oldRequest.promise)
          .mockImplementationOnce(() => newRequest.promise)
      const { result, rerender } = renderHook(() => useClaude(), {
        wrapper: f.wrapper,
      })
      await settle()
      const run = () =>
        kind === 'output'
          ? result.current.revealOutput('project-a')
          : result.current.sessionAction('project-a', 'stop')
      let oldAction!: Promise<void>
      act(() => {
        oldAction = run()
      })
      const oldSignal = (
        kind === 'output' ? f.get.mock.calls.at(-1) : f.post.mock.calls[0]
      )?.[1]?.signal
      f.replace(authB)
      rerender()
      await settle()
      expect(oldSignal?.aborted).toBe(true)
      let newAction!: Promise<void>
      act(() => {
        newAction = run()
      })
      await act(async () => {
        oldRequest.resolve(
          kind === 'output' ? output('OLD-OUTPUT') : actionResponse(),
        )
        await oldAction
      })
      expect(result.current.pending).toEqual([
        {
          projectId: 'project-a',
          operation: kind === 'output' ? 'output' : 'stop',
        },
      ])
      expect(result.current.outputs).toEqual({})
      expect(result.current.actionErrors).toEqual({})
      await act(async () => {
        newRequest.reject(new Error('new failure'))
        await newAction
      })
      expect(result.current.pending).toEqual([])
      expect(result.current.actionErrors['project-a']?.code).toBe(
        'CLAUDE_ACTION_FAILED',
      )
      if (kind === 'output') f.get.mockResolvedValueOnce(output('NEW-OUTPUT'))
      await act(async () => run())
      expect(result.current.actionErrors).toEqual({})
    },
  )

  it('aborts the sibling Claude refresh read when the first read fails', async () => {
    const f = fixture()
    const pending = deferred<unknown>()
    f.get.mockImplementation((path) =>
      path.endsWith('/sessions')
        ? pending.promise
        : Promise.reject(new Error('status failed')),
    )
    const { result } = renderHook(() => useClaude(), { wrapper: f.wrapper })
    await settle()
    expect(result.current.view.status).toBe('error')
    expect(
      f.get.mock.calls.find(([path]) => path.endsWith('/sessions'))?.[1]?.signal
        ?.aborted,
    ).toBe(true)
    pending.resolve({ data: { sessions: [session] } })
    await settle()
    expect(result.current.view.status).toBe('error')
  })

  it('keeps old callbacks revoked after A to B to A and supports StrictMode setup', async () => {
    const f = fixture(true)
    const { result, rerender } = renderHook(
      () => ({ codex: useCodex(), claude: useClaude() }),
      { wrapper: f.wrapper },
    )
    await settle()
    expect(result.current.codex.view.status).toBe('loaded')
    expect(result.current.claude.view.status).toBe('loaded')
    const old = result.current
    f.replace(authB)
    rerender()
    await settle()
    f.replace(authA)
    rerender()
    await settle()
    const reads = f.get.mock.calls.length
    const writes = f.post.mock.calls.length
    await act(async () => {
      await old.codex.generatePairCode()
      await old.claude.revealOutput('project-a')
    })
    expect(f.get).toHaveBeenCalledTimes(reads)
    expect(f.post).toHaveBeenCalledTimes(writes)
    await act(async () => {
      await result.current.codex.generatePairCode()
      await result.current.claude.revealOutput('project-a')
    })
    expect(result.current.codex.pair).not.toBeNull()
    expect(result.current.claude.outputs['project-a']).toBeDefined()
  })

  it('keeps the 90-second Pair display lifetime owned by the current scope', async () => {
    vi.useFakeTimers()
    const f = fixture()
    const { result, rerender } = renderHook(() => useCodex(), {
      wrapper: f.wrapper,
    })
    await settle()
    await act(async () => result.current.generatePairCode())
    act(() => vi.advanceTimersByTime(45000))
    f.replace(authB)
    rerender()
    await settle()
    await act(async () => result.current.generatePairCode())
    act(() => vi.advanceTimersByTime(45000))
    expect(result.current.pair).not.toBeNull()
    act(() => vi.advanceTimersByTime(44999))
    expect(result.current.pair).not.toBeNull()
    act(() => vi.advanceTimersByTime(1))
    expect(result.current.pair).toBeNull()
    expect(f.post).toHaveBeenCalledTimes(2)
  })
})

function clipboard() {
  const writeText = vi.fn<(value: string) => Promise<void>>()
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  })
  return writeText
}
async function generatePairFromPage() {
  fireEvent.click(screen.getByRole('button', { name: 'Pair New Device' }))
  fireEvent.click(screen.getByRole('button', { name: 'Generate Code' }))
  await settle()
}

describe('management page confirmation and clipboard ownership', () => {
  it('revokes an open Pair confirmation when the owner changes', async () => {
    const f = fixture()
    const { rerender } = render(<CodexPage />, { wrapper: f.wrapper })
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'Pair New Device' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    f.replace(authB)
    rerender(<CodexPage />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(f.post).not.toHaveBeenCalled()
    await settle()
    await generatePairFromPage()
    expect(f.post).toHaveBeenCalledTimes(1)
    expect(f.post).toHaveBeenLastCalledWith(
      '/api/v1/codex/pair-codes',
      expect.objectContaining({ csrfToken: 'csrf-b' }),
    )
  })

  it.each(['resolve', 'reject'] as const)(
    'ignores old Pair clipboard %s without overwriting the current copy result',
    async (outcome) => {
      const f = fixture()
      const oldCopy = deferred<void>()
      const newCopy = deferred<void>()
      const writeText = clipboard()
        .mockImplementationOnce(() => oldCopy.promise)
        .mockImplementationOnce(() => newCopy.promise)
      const { rerender } = render(<CodexPage />, { wrapper: f.wrapper })
      await settle()
      await generatePairFromPage()
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
      f.replace(authB)
      rerender(<CodexPage />)
      await settle()
      await generatePairFromPage()
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
      await act(async () => {
        newCopy.resolve()
        await newCopy.promise
      })
      expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
      await act(async () => {
        if (outcome === 'resolve') oldCopy.resolve()
        else oldCopy.reject(new Error('old clipboard failure'))
      })
      expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
      expect(
        screen.queryByText('The code could not be copied. Try again.'),
      ).not.toBeInTheDocument()
      expect(writeText).toHaveBeenCalledTimes(2)
    },
  )

  it('ignores Pair clipboard completion after Hide and a new explicit Generate', async () => {
    const f = fixture()
    const pendingCopy = deferred<void>()
    clipboard().mockImplementationOnce(() => pendingCopy.promise)
    render(<CodexPage />, { wrapper: f.wrapper })
    await settle()
    await generatePairFromPage()
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }))
    await generatePairFromPage()
    await act(async () => {
      pendingCopy.resolve()
      await pendingCopy.promise
    })
    expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Copied' }),
    ).not.toBeInTheDocument()
  })

  it('isolates Claude copy completion and its feedback timer across owners', async () => {
    vi.useFakeTimers()
    const f = fixture()
    const oldCopy = deferred<void>()
    const newCopy = deferred<void>()
    const writeText = clipboard()
      .mockImplementationOnce(() => oldCopy.promise)
      .mockImplementationOnce(() => newCopy.promise)
    const { rerender } = render(<ClaudePage />, { wrapper: f.wrapper })
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'Copy attach command' }))
    f.replace(authB)
    rerender(<ClaudePage />)
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'Copy attach command' }))
    await act(async () => {
      newCopy.resolve()
      await newCopy.promise
    })
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1000))
    await act(async () => {
      oldCopy.resolve()
      await oldCopy.promise
    })
    act(() => vi.advanceTimersByTime(499))
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))
    expect(
      screen.getByRole('button', { name: 'Copy attach command' }),
    ).toBeInTheDocument()
    expect(writeText).toHaveBeenCalledTimes(2)
  })

  it('drops Claude copied feedback when refresh replaces the session snapshot', async () => {
    vi.useFakeTimers()
    const f = fixture()
    clipboard().mockResolvedValue(undefined)
    render(<ClaudePage />, { wrapper: f.wrapper })
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'Copy attach command' }))
    await settle()
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    await settle()
    expect(
      screen.getByRole('button', { name: 'Copy attach command' }),
    ).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1500))
    expect(
      screen.queryByRole('button', { name: 'Copied' }),
    ).not.toBeInTheDocument()
  })
})
