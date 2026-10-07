import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { technicalValue } from '../../i18n'
import { ApiError } from '../../lib/api'
import {
  ClaudeSessionActionResponse,
  ClaudeSessionData,
  ClaudeSessionListResponse,
  ClaudeSessionOutputResponse,
  ClaudeSessionResponse,
  ClaudeStatusData,
  ClaudeStatusResponse,
  parseClaudeSessionActionResponse,
  parseClaudeSessionListResponse,
  parseClaudeSessionOutputResponse,
  parseClaudeSessionResponse,
  parseClaudeStatusResponse,
} from '../../lib/contracts'

export type ClaudeApiErrorView = Readonly<{
  code: string
  requestId?: string
}>

export type ClaudeSessionView = Readonly<
  Pick<
    ClaudeSessionData,
    | 'project_id'
    | 'display_name'
    | 'state'
    | 'workspace_state'
    | 'tmux_running'
    | 'remote_readiness'
  > & { attach_command: string | null }
>

export type ClaudeStatusView = Readonly<
  Pick<
    ClaudeStatusData,
    | 'installed'
    | 'version'
    | 'authentication'
    | 'tmux_installed'
    | 'tmux_version'
    | 'managed_sessions'
    | 'unmanaged_sessions'
    | 'workspace_interaction_warnings'
  > & {
    capabilities: Readonly<
      Pick<ClaudeStatusData['capabilities'], 'remote_control'>
    >
  }
>

export type ClaudeRevealedOutput = Readonly<{
  output: string
  truncated: boolean
}>

type LoadedClaude = Readonly<{
  status: ClaudeStatusView
  sessions: readonly ClaudeSessionView[]
}>

export type ClaudePendingOperation = Readonly<{
  operation: 'start' | 'stop' | 'output'
  projectId: string
}>

type ProjectOperationToken = Readonly<{
  revision: number
  operation: ClaudePendingOperation['operation']
  kind: 'mutation' | 'output'
  projectId: string
}>

type RefreshToken = Readonly<{
  revision: number
  pendingMutationProjects: ReadonlySet<string>
}>

function safeError(
  error: unknown,
  fallbackCode: 'CLAUDE_ACTION_FAILED' | 'CLAUDE_RUNTIME_UNAVAILABLE',
): ClaudeApiErrorView {
  if (!(error instanceof ApiError)) return Object.freeze({ code: fallbackCode })
  return Object.freeze({
    code: error.code,
    ...(error.requestId === undefined ? {} : { requestId: error.requestId }),
  })
}

function technicalString(value: string | null): string | null {
  if (value === null) return null
  try {
    return technicalValue(value).value
  } catch {
    return null
  }
}

function sessionView(session: ClaudeSessionData): ClaudeSessionView {
  return Object.freeze({
    project_id: session.project_id,
    display_name: session.display_name,
    state: session.state,
    attach_command: technicalString(session.attach_command),
    workspace_state: session.workspace_state,
    tmux_running: session.tmux_running,
    remote_readiness: session.remote_readiness,
  })
}

function statusView(status: ClaudeStatusData): ClaudeStatusView {
  return Object.freeze({
    installed: status.installed,
    version: technicalString(status.version),
    authentication: status.authentication,
    capabilities: Object.freeze({
      remote_control: status.capabilities.remote_control,
    }),
    tmux_installed: status.tmux_installed,
    tmux_version: technicalString(status.tmux_version),
    managed_sessions: status.managed_sessions,
    unmanaged_sessions: status.unmanaged_sessions,
    workspace_interaction_warnings: status.workspace_interaction_warnings,
  })
}

export function useClaudeProject(projectId: string | undefined) {
  const { api, auth, status } = useAuth()
  const userId = auth?.user.id
  const sessionId = auth?.session.id
  // Object identity distinguishes separate visits to the same Project/session.
  const owner = useMemo(
    () => ({ api, projectId, userId, sessionId, status }),
    [api, projectId, userId, sessionId, status],
  )
  const currentOwner = useRef(owner)
  currentOwner.current = owner
  const currentAuth = useRef(auth)
  currentAuth.current = auth
  const availability = useRef({
    offline: !navigator.onLine,
    pageHidden: false,
    frozen: false,
  })
  type Phase = 'loading' | 'ready' | 'stale' | 'error' | 'forbidden'
  type State = {
    phase: Phase
    session: ClaudeSessionView | null
    error: ClaudeApiErrorView | null
    loading: boolean
    pending: boolean
  }
  const [state, setState] = useState<State & { owner: typeof owner }>({
    owner,
    phase: 'loading',
    session: null,
    error: null,
    loading: true,
    pending: false,
  })
  const control = useRef<{
    owner: typeof owner
    refresh: () => Promise<void>
    action: (operation: 'start' | 'stop') => Promise<void>
  } | null>(null)

  useEffect(() => {
    let disposed = false
    let epoch = 0
    let read: AbortController | null = null
    let mutation: AbortController | null = null
    let current: State = {
      phase: 'loading',
      session: null,
      error: null,
      loading: true,
      pending: false,
    }
    const authenticated =
      owner.status === 'authenticated' &&
      Boolean(owner.userId && owner.sessionId)

    function available() {
      return (
        !availability.current.offline &&
        !availability.current.pageHidden &&
        !availability.current.frozen &&
        navigator.onLine &&
        document.visibilityState !== 'hidden'
      )
    }
    function owns(requestEpoch = epoch) {
      return (
        !disposed && currentOwner.current === owner && requestEpoch === epoch
      )
    }
    function commit(next: State) {
      if (!owns()) return
      current = next
      setState({ ...next, owner })
    }
    function clear(phase: Phase, error: ClaudeApiErrorView | null = null) {
      commit({
        phase,
        error,
        session: null,
        loading: phase === 'loading',
        pending: false,
      })
    }
    function cancelRead() {
      read?.abort()
      read = null
    }
    function invalidate() {
      epoch += 1
      cancelRead()
      mutation?.abort()
      mutation = null
      clear(authenticated ? 'stale' : 'forbidden')
    }
    async function refresh() {
      if (!owns() || !authenticated || !owner.projectId || !available()) return
      cancelRead()
      const request = new AbortController()
      const requestEpoch = epoch
      // A read issued during a mutation cannot establish its outcome, even if
      // its response arrives after the action acknowledgement.
      const overlappedMutation = mutation !== null
      read = request
      commit({
        ...current,
        phase: current.session ? 'ready' : 'loading',
        loading: true,
      })
      try {
        const response = await owner.api.get<ClaudeSessionResponse>(
          `/api/v1/claude/sessions/${encodeURIComponent(owner.projectId)}`,
          {
            signal: request.signal,
            timeoutMs: CLAUDE_STATUS_TIMEOUT_MS,
            validate: parseClaudeSessionResponse,
          },
        )
        if (
          !owns(requestEpoch) ||
          !available() ||
          read !== request ||
          request.signal.aborted ||
          overlappedMutation
        )
          return
        if (response.data.project_id !== owner.projectId) {
          clear('error', { code: 'CLAUDE_RUNTIME_UNAVAILABLE' })
          return
        }
        commit({
          ...current,
          phase: 'ready',
          session: sessionView(response.data),
          error: null,
        })
      } catch (value) {
        if (
          !owns(requestEpoch) ||
          !available() ||
          read !== request ||
          request.signal.aborted ||
          overlappedMutation
        )
          return
        clear(
          value instanceof ApiError && [401, 403].includes(value.status)
            ? 'forbidden'
            : 'error',
          safeError(value, 'CLAUDE_RUNTIME_UNAVAILABLE'),
        )
      } finally {
        if (owns(requestEpoch) && available() && read === request) {
          read = null
          commit({ ...current, loading: false })
        }
      }
    }
    async function action(operation: 'start' | 'stop') {
      const actionAuth = currentAuth.current
      if (
        !owns() ||
        !authenticated ||
        !owner.projectId ||
        !actionAuth ||
        !available() ||
        current.phase !== 'ready' ||
        mutation !== null
      )
        return
      const request = new AbortController()
      const requestEpoch = epoch
      mutation = request
      // Invalidate any older GET synchronously, before a second action can run.
      cancelRead()
      commit({ ...current, pending: true, loading: false, error: null })
      try {
        const response = await owner.api.post<ClaudeSessionActionResponse>(
          `/api/v1/claude/sessions/${encodeURIComponent(owner.projectId)}/${operation}`,
          {
            signal: request.signal,
            csrfToken: actionAuth.csrf_token,
            timeoutMs: CLAUDE_MUTATION_TIMEOUT_MS,
            validate: parseClaudeSessionActionResponse,
          },
        )
        if (
          !owns(requestEpoch) ||
          !available() ||
          mutation !== request ||
          request.signal.aborted
        )
          return
        cancelRead()
        if (response.data.session.project_id !== owner.projectId) {
          clear('error', { code: 'CLAUDE_ACTION_FAILED' })
          return
        }
        commit({
          ...current,
          phase: 'ready',
          session: sessionView(response.data.session),
          error: null,
          loading: false,
        })
      } catch (value) {
        if (
          !owns(requestEpoch) ||
          !available() ||
          mutation !== request ||
          request.signal.aborted
        )
          return
        cancelRead()
        const error = safeError(value, 'CLAUDE_ACTION_FAILED')
        if (value instanceof ApiError && [401, 403].includes(value.status))
          clear('forbidden', error)
        else commit({ ...current, error, loading: false })
      } finally {
        if (owns(requestEpoch) && available() && mutation === request) {
          mutation = null
          commit({ ...current, pending: false })
        }
      }
    }
    function resumeIfStale() {
      if (current.phase === 'stale' && available()) void refresh()
    }
    function visibilityChanged() {
      if (document.visibilityState === 'hidden') invalidate()
      else resumeIfStale()
    }
    function goOffline() {
      availability.current.offline = true
      invalidate()
    }
    function goOnline() {
      availability.current.offline = false
      resumeIfStale()
    }
    function pageHide() {
      availability.current.pageHidden = true
      invalidate()
    }
    function pageShow() {
      availability.current.pageHidden = false
      resumeIfStale()
    }
    function freeze() {
      availability.current.frozen = true
      invalidate()
    }
    function resume() {
      availability.current.frozen = false
      resumeIfStale()
    }

    control.current = { owner, refresh, action }
    if (!authenticated) clear('forbidden')
    else if (!owner.projectId || !available()) clear('stale')
    else void refresh()
    document.addEventListener('visibilitychange', visibilityChanged)
    document.addEventListener('freeze', freeze)
    document.addEventListener('resume', resume)
    window.addEventListener('offline', goOffline)
    window.addEventListener('online', goOnline)
    window.addEventListener('pagehide', pageHide)
    window.addEventListener('pageshow', pageShow)
    return () => {
      disposed = true
      cancelRead()
      mutation?.abort()
      if (control.current?.owner === owner) control.current = null
      document.removeEventListener('visibilitychange', visibilityChanged)
      document.removeEventListener('freeze', freeze)
      document.removeEventListener('resume', resume)
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('online', goOnline)
      window.removeEventListener('pagehide', pageHide)
      window.removeEventListener('pageshow', pageShow)
    }
  }, [owner])

  const refresh = useCallback(async () => {
    if (currentOwner.current === owner && control.current?.owner === owner)
      await control.current.refresh()
  }, [owner])
  const action = useCallback(
    async (operation: 'start' | 'stop') => {
      if (currentOwner.current === owner && control.current?.owner === owner)
        await control.current.action(operation)
    },
    [owner],
  )
  // Browser state can change before its lifecycle event is delivered. Hide an
  // observation in that render too, without waiting for the event/effect fence.
  const authenticated = status === 'authenticated' && Boolean(auth)
  const available =
    Boolean(projectId) &&
    !availability.current.offline &&
    !availability.current.pageHidden &&
    !availability.current.frozen &&
    navigator.onLine &&
    document.visibilityState !== 'hidden'
  const owned = state.owner === owner && authenticated && available
  const phase: Phase = !authenticated
    ? 'forbidden'
    : !available
      ? 'stale'
      : owned
        ? state.phase
        : 'loading'
  return {
    action,
    refresh,
    phase,
    stale: phase === 'stale',
    session: owned ? state.session : null,
    error: owned ? state.error : null,
    loading: owned ? state.loading : phase === 'loading',
    pending: owned && state.pending,
  }
}

export type ClaudeViewState =
  | { status: 'loading' }
  | { status: 'error'; error: ClaudeApiErrorView }
  | { status: 'loaded'; data: LoadedClaude }

const CLAUDE_STATUS_TIMEOUT_MS = 45_000
const CLAUDE_MUTATION_TIMEOUT_MS = 45_000

export function useClaude() {
  const { api, auth, status } = useAuth()
  const userId = auth?.user.id
  const sessionId = auth?.session.id
  const csrfToken = auth?.csrf_token
  const owner = useMemo(
    () => ({ api, userId, sessionId, csrfToken, status }),
    [api, userId, sessionId, csrfToken, status],
  )
  const currentOwner = useRef(owner)
  currentOwner.current = owner
  type State = {
    view: ClaudeViewState
    pending: readonly ClaudePendingOperation[]
    refreshing: boolean
    actionErrors: Readonly<Record<string, ClaudeApiErrorView>>
    outputs: Record<string, ClaudeRevealedOutput>
  }
  const [state, setState] = useState<State & { owner: typeof owner }>({
    owner,
    view: { status: 'loading' },
    pending: [],
    refreshing: false,
    actionErrors: {},
    outputs: {},
  })
  const control = useRef<{
    owner: typeof owner
    refresh: () => Promise<void>
    sessionAction: (
      projectId: string,
      operation: 'start' | 'stop',
    ) => Promise<void>
    revealOutput: (projectId: string) => Promise<void>
    hideOutput: (projectId: string) => void
  } | null>(null)

  useEffect(() => {
    let disposed = false
    const requests = new Set<AbortController>()
    const authenticated =
      owner.status === 'authenticated' &&
      Boolean(owner.userId && owner.sessionId)
    function owns() {
      return !disposed && authenticated && currentOwner.current === owner
    }
    function update<K extends keyof State>(
      key: K,
      value: State[K] | ((current: State[K]) => State[K]),
    ) {
      if (!owns()) return
      setState((current) => {
        if (!owns() || current.owner !== owner) return current
        return {
          ...current,
          [key]: typeof value === 'function' ? value(current[key]) : value,
        }
      })
    }
    const setView = (value: State['view']) => update('view', value)
    const setPending = (value: State['pending']) => update('pending', value)
    const setRefreshing = (value: boolean) => update('refreshing', value)
    const setActionErrors = (
      value:
        | State['actionErrors']
        | ((current: State['actionErrors']) => State['actionErrors']),
    ) => update('actionErrors', value)
    const setOutputs = (
      value:
        State['outputs'] | ((current: State['outputs']) => State['outputs']),
    ) => update('outputs', value)
    let revision = 0
    let viewRef: ClaudeViewState = { status: 'loading' }
    let loadedRef: LoadedClaude | null = null
    const pendingRef = new Map<number, ProjectOperationToken>()
    const refreshRef = new Set<number>()
    let latestRefreshRevisionRef = 0
    let latestMutationRevisionRef = 0
    const latestActionRevisionRef = new Map<string, number>()
    const sessionOverridesRef = new Map<
      string,
      Readonly<{ revision: number; session: ClaudeSessionView }>
    >()
    function nextRevision() {
      revision += 1
      return revision
    }

    function commitView(next: ClaudeViewState) {
      viewRef = next
      if (next.status === 'loaded') loadedRef = next.data
      setView(next)
    }

    function beginProjectOperation(
      projectId: string,
      operation: 'start' | 'stop' | 'output',
    ): ProjectOperationToken | null {
      for (const token of pendingRef.values()) {
        if (token.projectId === projectId) return null
      }
      const token = Object.freeze({
        revision: nextRevision(),
        operation,
        kind:
          operation === 'output' ? ('output' as const) : ('mutation' as const),
        projectId,
      })
      pendingRef.set(token.revision, token)
      latestActionRevisionRef.set(projectId, token.revision)
      if (token.kind === 'mutation') {
        latestMutationRevisionRef = token.revision
      }
      setPending(
        Array.from(pendingRef.values(), (entry) =>
          Object.freeze({
            operation: entry.operation,
            projectId: entry.projectId,
          }),
        ),
      )
      return token
    }

    function endProjectOperation(token: ProjectOperationToken) {
      if (!pendingRef.delete(token.revision)) return
      setPending(
        Array.from(pendingRef.values(), (entry) =>
          Object.freeze({
            operation: entry.operation,
            projectId: entry.projectId,
          }),
        ),
      )
    }

    function clearActionError(projectId: string) {
      setActionErrors((current) => {
        if (!(projectId in current)) return current
        const next = { ...current }
        delete next[projectId]
        return Object.freeze(next)
      })
    }

    function setActionError(
      token: ProjectOperationToken,
      error: ClaudeApiErrorView,
    ) {
      if (latestActionRevisionRef.get(token.projectId) !== token.revision) {
        return
      }
      setActionErrors((current) =>
        Object.freeze({ ...current, [token.projectId]: error }),
      )
    }

    function endRefresh(token: RefreshToken) {
      if (!refreshRef.delete(token.revision)) return
      setRefreshing(refreshRef.size > 0)
    }

    function mergeRefreshSessions(
      sessions: readonly ClaudeSessionView[],
      token: RefreshToken,
    ): readonly ClaudeSessionView[] {
      const merged = new Map(
        sessions.map((session) => [session.project_id, session] as const),
      )
      for (const [projectId, override] of sessionOverridesRef) {
        if (
          override.revision > token.revision ||
          token.pendingMutationProjects.has(projectId)
        ) {
          merged.set(projectId, override.session)
        }
      }
      return Object.freeze(Array.from(merged.values()))
    }

    function applySessionOverride(
      projectId: string,
      operationRevision: number,
      session: ClaudeSessionView,
    ) {
      sessionOverridesRef.set(
        projectId,
        Object.freeze({ revision: operationRevision, session }),
      )
      const current = loadedRef
      if (current === null) return
      const sessions = current.sessions.some(
        (candidate) => candidate.project_id === projectId,
      )
        ? current.sessions.map((candidate) =>
            candidate.project_id === projectId ? session : candidate,
          )
        : [...current.sessions, session]
      commitView({
        status: 'loaded',
        data: Object.freeze({
          ...current,
          sessions: Object.freeze(sessions),
        }),
      })
    }

    async function refresh() {
      if (!owns()) return
      const request = new AbortController()
      requests.add(request)
      revision += 1
      const refreshRevision = revision
      const pendingMutationProjects = new Set<string>()
      for (const pendingToken of pendingRef.values()) {
        if (pendingToken.kind === 'mutation') {
          pendingMutationProjects.add(pendingToken.projectId)
        }
      }
      const token: RefreshToken = Object.freeze({
        revision: refreshRevision,
        pendingMutationProjects,
      })
      latestRefreshRevisionRef = refreshRevision
      refreshRef.add(refreshRevision)
      setRefreshing(true)
      setActionErrors({})
      setOutputs({})
      if (viewRef.status !== 'loaded') {
        commitView({ status: 'loading' })
      }
      try {
        const [status, sessions] = await Promise.all([
          owner.api.get<ClaudeStatusResponse>('/api/v1/claude', {
            signal: request.signal,
            timeoutMs: CLAUDE_STATUS_TIMEOUT_MS,
            validate: parseClaudeStatusResponse,
          }),
          owner.api.get<ClaudeSessionListResponse>('/api/v1/claude/sessions', {
            signal: request.signal,
            timeoutMs: CLAUDE_STATUS_TIMEOUT_MS,
            validate: parseClaudeSessionListResponse,
          }),
        ])
        if (
          !owns() ||
          request.signal.aborted ||
          latestRefreshRevisionRef !== token.revision
        )
          return
        commitView({
          status: 'loaded',
          data: Object.freeze({
            status: statusView(status.data),
            sessions: mergeRefreshSessions(
              sessions.data.sessions.map(sessionView),
              token,
            ),
          }),
        })
      } catch (error) {
        if (
          !owns() ||
          request.signal.aborted ||
          latestRefreshRevisionRef !== token.revision
        )
          return
        const mutationOverlapped =
          token.pendingMutationProjects.size > 0 ||
          latestMutationRevisionRef > token.revision
        if (mutationOverlapped && loadedRef !== null) {
          commitView({ status: 'loaded', data: loadedRef })
        } else {
          commitView({
            status: 'error',
            error: safeError(error, 'CLAUDE_RUNTIME_UNAVAILABLE'),
          })
        }
      } finally {
        // Promise.all may settle before its sibling read; close both requests.
        request.abort()
        requests.delete(request)
        if (owns()) endRefresh(token)
      }
    }

    async function sessionAction(
      projectId: string,
      operation: 'start' | 'stop',
    ) {
      if (!owns() || !owner.csrfToken) return
      const token = beginProjectOperation(projectId, operation)
      if (token === null) return
      const request = new AbortController()
      requests.add(request)
      clearActionError(projectId)
      setOutputs((current) => {
        const next = { ...current }
        delete next[projectId]
        return next
      })
      try {
        const response = await owner.api.post<ClaudeSessionActionResponse>(
          `/api/v1/claude/sessions/${encodeURIComponent(projectId)}/${operation}`,
          {
            csrfToken: owner.csrfToken,
            signal: request.signal,
            timeoutMs: CLAUDE_MUTATION_TIMEOUT_MS,
            validate: parseClaudeSessionActionResponse,
          },
        )
        if (!owns() || request.signal.aborted) return
        if (response.data.session.project_id !== projectId) {
          setActionError(token, { code: 'CLAUDE_ACTION_FAILED' })
          return
        }
        applySessionOverride(
          projectId,
          token.revision,
          sessionView(response.data.session),
        )
      } catch (error) {
        if (!owns() || request.signal.aborted) return
        setActionError(token, safeError(error, 'CLAUDE_ACTION_FAILED'))
      } finally {
        requests.delete(request)
        if (owns()) endProjectOperation(token)
      }
    }

    async function revealOutput(projectId: string) {
      if (!owns()) return
      const token = beginProjectOperation(projectId, 'output')
      if (token === null) return
      const request = new AbortController()
      requests.add(request)
      clearActionError(projectId)
      try {
        const response = await owner.api.get<ClaudeSessionOutputResponse>(
          `/api/v1/claude/sessions/${encodeURIComponent(projectId)}/output`,
          {
            signal: request.signal,
            timeoutMs: CLAUDE_STATUS_TIMEOUT_MS,
            validate: parseClaudeSessionOutputResponse,
          },
        )
        if (!owns() || request.signal.aborted) return
        if (response.data.project_id !== projectId) {
          setActionError(token, { code: 'CLAUDE_ACTION_FAILED' })
          return
        }
        if (latestRefreshRevisionRef > token.revision) return
        setOutputs((current) => ({
          ...current,
          [projectId]: Object.freeze({
            output: response.data.output,
            truncated: response.data.truncated,
          }),
        }))
      } catch (error) {
        if (!owns() || request.signal.aborted) return
        setActionError(token, safeError(error, 'CLAUDE_ACTION_FAILED'))
      } finally {
        requests.delete(request)
        if (owns()) endProjectOperation(token)
      }
    }

    function hideOutput(projectId: string) {
      if (!owns()) return
      setOutputs((current) => {
        const next = { ...current }
        delete next[projectId]
        return next
      })
    }
    setState({
      owner,
      view: { status: 'loading' },
      pending: [],
      refreshing: false,
      actionErrors: {},
      outputs: {},
    })
    const controls = { owner, refresh, sessionAction, revealOutput, hideOutput }
    control.current = controls
    void refresh()
    return () => {
      disposed = true
      // This cancels browser requests, not already submitted Runtime actions.
      for (const request of requests) request.abort()
      requests.clear()
      if (control.current === controls) control.current = null
    }
  }, [owner])

  const isCurrent = useCallback(
    () => currentOwner.current === owner && control.current?.owner === owner,
    [owner],
  )
  const refresh = useCallback(async () => {
    if (isCurrent()) await control.current?.refresh()
  }, [isCurrent])
  async function sessionAction(projectId: string, operation: 'start' | 'stop') {
    if (isCurrent()) await control.current?.sessionAction(projectId, operation)
  }
  async function revealOutput(projectId: string) {
    if (isCurrent()) await control.current?.revealOutput(projectId)
  }
  function hideOutput(projectId: string) {
    if (isCurrent()) control.current?.hideOutput(projectId)
  }
  // Mask old data on the first replacement render, before effects can reset it.
  const owned = state.owner === owner && owner.status === 'authenticated'
  return {
    actionErrors: owned ? state.actionErrors : {},
    hideOutput,
    isCurrent,
    outputs: owned ? state.outputs : {},
    pending: owned ? state.pending : [],
    refreshing: owned && state.refreshing,
    refresh,
    revealOutput,
    sessionAction,
    view: owned ? state.view : ({ status: 'loading' } as const),
  }
}
