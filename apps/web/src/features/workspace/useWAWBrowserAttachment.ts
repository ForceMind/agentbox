import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { ApiError } from '../../lib/api'
import type {
  WorkspaceAttachmentTicketResponse,
  WorkspaceDetachResponse,
  WorkspaceRuntimeStatus,
  WorkspaceStopResponse,
} from '../../lib/contracts'
import { createBrowserTerminalSchedulerFactory } from './browserTerminalRenderer'
import {
  WAWBrowserController,
  WAWBrowserControllerError,
  type WAWBrowserConnectRequest,
  type WAWBrowserControllerOptions,
  type WAWBrowserControllerSnapshot,
  type WAWBrowserControllerStatus,
  type WAWBrowserAttachmentIdentity,
  type WAWBrowserControlRequest,
  type WAWBrowserDetachReceipt,
  type WAWBrowserInputOutcome,
  type WAWBrowserInputSnapshot,
  type WAWBrowserStopOutcome,
  type WAWBrowserTrustPort,
} from './wawBrowserController'
import {
  createManagedChromiumTrustProvider,
  managedChromiumTrustProviderAvailable,
} from './wawTrustChromiumPort'
import {
  WAWTrustProviderConsumer,
  type WAWTrustProviderPort,
} from './wawTrustProvider'

type AgentType = 'claude' | 'codex'

export type WAWAttachmentActions = {
  connect(
    workspaceId: string,
    agentType: AgentType,
    signal?: AbortSignal,
  ): Promise<WorkspaceAttachmentTicketResponse>
  reconnect(
    workspaceId: string,
    agentType: AgentType,
    signal?: AbortSignal,
  ): Promise<WorkspaceAttachmentTicketResponse>
  detach(
    workspaceId: string,
    attachmentId: string,
    generation: string,
    leaseNumber: string,
    agentType: AgentType,
    signal?: AbortSignal,
  ): Promise<WorkspaceDetachResponse>
  stop(
    workspaceId: string,
    generation: string,
    agentType: AgentType,
    signal?: AbortSignal,
  ): Promise<WorkspaceStopResponse>
}

export type WAWAttachmentView = {
  readonly status: WAWBrowserControllerStatus | 'UNAVAILABLE'
  readonly reason: string | null
  readonly outputCursor: string | null
  readonly freshRedrawTruncated: boolean
  /** Public controller metadata only; never plaintext terminal input. */
  readonly input: WAWBrowserInputSnapshot | null
  /** The last settled input result contains no plaintext or ticket material. */
  readonly lastInputOutcome: Readonly<
    Pick<WAWBrowserInputOutcome, 'state' | 'reasonCode'>
  > | null
  /** Exact attachment identity is present only after ticket admission. */
  readonly attached: WAWBrowserAttachmentIdentity | null
  readonly providerAvailable: boolean
  readonly surfaceReady: boolean
}

export type WAWAttachmentIdentity = {
  readonly projectId: string
  readonly workspaceId: string
  readonly agentType: AgentType
  readonly generation: string
  readonly bindingRevision: string
  readonly bindingDigest: string
  readonly runtimeEpoch: string
  /** A retained attachment may survive NEEDS_INTERACTION, but no new ticket may issue. */
  readonly streamEligible: boolean
  /** Existing stream may remain only while Runtime permits browser interaction. */
  readonly streamMayContinue: boolean
  readonly key: string
}

export type WAWAttachmentDependencies = {
  /** Test-only injection; production lazily creates the managed Chromium port. */
  readonly createProvider?: () => WAWTrustProviderPort | null
  /** Test-only declaration; a factory is never treated as available by itself. */
  readonly providerAvailable?: boolean
  /** Test-only injection; production requires an independent provider consumer. */
  readonly createTrust?: (provider: WAWTrustProviderPort) => OwnedTrust
  /** Named test seam; production always constructs the real controller. */
  readonly createController?: (
    options: WAWBrowserControllerOptions,
  ) => WAWAttachmentControllerPort
  readonly origin?: () => string
}

type OwnedTrust = Pick<WAWBrowserTrustPort, 'authorize'> & {
  close(): void
}

export type WAWAttachmentControllerPort = {
  readonly snapshot: WAWBrowserControllerSnapshot
  connect(request: WAWBrowserConnectRequest): Promise<void>
  detach(request: WAWBrowserControlRequest): Promise<WAWBrowserDetachReceipt>
  stop(request: WAWBrowserControlRequest): Promise<WAWBrowserStopOutcome>
  /** Implementations synchronously copy input before returning their pending ACK promise. */
  sendInput(value: Uint8Array): Promise<WAWBrowserInputOutcome>
  requestResize(columns: number, rows: number): void
  contextChanged(): void
  handlePageLifecycle(event: 'pagehide' | 'freeze' | 'hidden' | 'unmount'): void
}

type Attempt = {
  readonly token: symbol
  readonly epoch: number
  readonly authScope: string
  readonly identity: WAWAttachmentIdentity
  readonly abort: AbortController
  readonly controller: WAWAttachmentControllerPort
  readonly trust: OwnedTrust
  readonly portFailure: { value: ApiError | null }
  trustClosed: boolean
}

type AttachmentSnapshotView = Omit<
  WAWAttachmentView,
  'providerAvailable' | 'surfaceReady' | 'lastInputOutcome'
>

const IDLE_VIEW: AttachmentSnapshotView = Object.freeze({
  status: 'IDLE',
  reason: null,
  outputCursor: null,
  freshRedrawTruncated: false,
  input: null,
  attached: null,
})

/** CSS uses the same fixed 8px × 20px terminal grid. */
export const WAW_TERMINAL_VIEWPORT_METRICS = Object.freeze({
  cellWidthPx: 8,
  cellHeightPx: 20,
  horizontalPaddingPx: 16,
  verticalPaddingPx: 16,
  columnsMin: 8,
  columnsMax: 240,
  rowsMin: 1,
  rowsMax: 200,
})

function asError(code: string): ApiError {
  return new ApiError({
    code,
    message: 'Browser terminal operation could not be completed',
    status: 0,
  })
}

function pageVisible(): boolean {
  return (
    typeof document === 'undefined' || document.visibilityState === 'visible'
  )
}

function resolvedIdentity(input: {
  projectId: string | null
  workspaceId: string | null
  agentType: AgentType
  generation: string | null
  runtime: WorkspaceRuntimeStatus | null
}): WAWAttachmentIdentity | null {
  const { projectId, workspaceId, agentType, generation, runtime } = input
  if (
    projectId === null ||
    workspaceId === null ||
    generation === null ||
    runtime === null ||
    runtime.workspace_id !== workspaceId ||
    runtime.project_id !== projectId ||
    runtime.agent_type !== agentType ||
    runtime.generation !== generation ||
    runtime.reconciliation_state !== 'authoritative' ||
    ![
      'RUNNING',
      'NEEDS_INTERACTION',
      'TRUST_REQUIRED',
      'LOGIN_REQUIRED',
    ].includes(runtime.state)
  ) {
    return null
  }
  return Object.freeze({
    projectId,
    workspaceId,
    agentType,
    generation,
    bindingRevision: runtime.binding_revision,
    bindingDigest: runtime.binding_digest,
    runtimeEpoch: runtime.runtime_epoch,
    streamEligible: runtime.state === 'RUNNING',
    streamMayContinue: ['RUNNING', 'NEEDS_INTERACTION'].includes(runtime.state),
    key: [
      projectId,
      workspaceId,
      agentType,
      generation,
      runtime.binding_revision,
      runtime.binding_digest,
      runtime.runtime_epoch,
    ].join(':'),
  })
}

function viewFromSnapshot(
  snapshot: WAWBrowserControllerSnapshot,
): AttachmentSnapshotView {
  return Object.freeze({
    status: snapshot.status,
    reason: snapshot.reason,
    outputCursor: snapshot.outputCursor,
    freshRedrawTruncated: snapshot.freshRedrawTruncated,
    input: snapshot.input,
    attached: snapshot.attachment,
  })
}

/**
 * Owns one page's browser attachment attempt. Ticket/crypto/raw terminal data
 * never enter React state; only bounded controller metadata is exposed.
 */
export function useWAWBrowserAttachment(options: {
  readonly actions: WAWAttachmentActions
  readonly agentType: AgentType
  readonly authScope: string
  readonly contextEpoch: React.MutableRefObject<number>
  readonly generation: string | null
  readonly projectId: string | null
  readonly runtime: WorkspaceRuntimeStatus | null
  readonly workspaceId: string | null
  readonly dependencies?: WAWAttachmentDependencies
}) {
  const { dependencies } = options
  const mounted = useRef(false)
  const attemptRef = useRef<Attempt | null>(null)
  const pageControlAbort = useRef(new AbortController())
  const surfaceRef = useRef<HTMLElement | null>(null)
  const viewportRef = useRef<HTMLElement | null>(null)
  const inputClearerRef = useRef<(() => void) | null>(null)
  const identityRef = useRef<WAWAttachmentIdentity | null>(null)
  const authScopeRef = useRef(options.authScope)
  const [surfaceReady, setSurfaceReady] = useState(false)
  const [viewportReady, setViewportReady] = useState(false)
  const providerAvailable = useMemo(
    () =>
      dependencies?.createProvider !== undefined
        ? dependencies.providerAvailable === true
        : managedChromiumTrustProviderAvailable(),
    [dependencies],
  )
  const [snapshot, setSnapshot] = useState<AttachmentSnapshotView>(IDLE_VIEW)
  const [lastInputOutcome, setLastInputOutcome] = useState<Readonly<
    Pick<WAWBrowserInputOutcome, 'state' | 'reasonCode'>
  > | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const identity = resolvedIdentity(options)
  identityRef.current = identity
  authScopeRef.current = options.authScope

  const scopeCurrent = useCallback(
    (attempt: Attempt): boolean => {
      return (
        mounted.current &&
        attemptRef.current === attempt &&
        authScopeRef.current === attempt.authScope &&
        options.contextEpoch.current === attempt.epoch &&
        identityRef.current?.key === attempt.identity.key
      )
    },
    [options.contextEpoch],
  )

  const current = useCallback(
    (attempt: Attempt): boolean =>
      scopeCurrent(attempt) &&
      identityRef.current?.streamMayContinue === true &&
      !attempt.abort.signal.aborted &&
      pageVisible(),
    [scopeCurrent],
  )

  const controlCurrent = useCallback(
    (attempt: Attempt, lease: AbortController): boolean =>
      scopeCurrent(attempt) &&
      pageControlAbort.current === lease &&
      !lease.signal.aborted,
    [scopeCurrent],
  )

  const closeTrust = useCallback((attempt: Attempt) => {
    if (attempt.trustClosed) return
    attempt.trustClosed = true
    try {
      attempt.trust.close()
    } catch {
      // A broken provider cannot retain an attachment or block page cleanup.
    }
  }, [])

  const clearSurface = useCallback(() => {
    const surface = surfaceRef.current
    if (surface === null) return
    let cleared = false
    try {
      surface.replaceChildren()
      cleared = surface.childNodes.length === 0 && surface.textContent === ''
    } catch {
      try {
        surface.textContent = ''
      } catch {
        // Verify below; a retained plaintext surface is never a successful fence.
      }
    }
    if (!cleared) {
      cleared = surface.childNodes.length === 0 && surface.textContent === ''
    }
    if (!cleared && mounted.current) setError(asError('OUTPUT_RENDER_FAILED'))
  }, [])

  const clearInputSurface = useCallback(() => {
    try {
      inputClearerRef.current?.()
    } catch {
      if (mounted.current) setError(asError('INPUT_UNCERTAIN'))
    }
  }, [])

  const fence = useCallback(
    (lifecycle?: 'pagehide' | 'freeze' | 'hidden' | 'unmount') => {
      clearInputSurface()
      const pageAbort = pageControlAbort.current
      if (!pageAbort.signal.aborted) pageAbort.abort()
      pageControlAbort.current = new AbortController()
      const attempt = attemptRef.current
      if (attempt !== null) {
        if (!attempt.abort.signal.aborted) attempt.abort.abort()
        if (lifecycle) attempt.controller.handlePageLifecycle(lifecycle)
        else attempt.controller.contextChanged()
        closeTrust(attempt)
        if (mounted.current)
          setSnapshot(viewFromSnapshot(attempt.controller.snapshot))
      }
      if (mounted.current) setLastInputOutcome(null)
      clearSurface()
    },
    [clearInputSurface, clearSurface, closeTrust],
  )

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      fence('unmount')
    }
  }, [fence])

  const attachmentScope = `${options.authScope}\u0000${identity?.key ?? ''}`
  const previousScope = useRef<string | null>(null)
  useLayoutEffect(() => {
    if (
      previousScope.current !== null &&
      previousScope.current !== attachmentScope
    ) {
      setError(null)
      fence()
      setSnapshot(IDLE_VIEW)
    }
    previousScope.current = attachmentScope
  }, [attachmentScope, fence])

  const previousStreamMayContinue = useRef<boolean | null>(null)
  useLayoutEffect(() => {
    const streamMayContinue = identity?.streamMayContinue === true
    if (previousStreamMayContinue.current === true && !streamMayContinue) {
      fence()
    }
    previousStreamMayContinue.current = streamMayContinue
  }, [fence, identity?.streamMayContinue])

  useEffect(() => {
    const onPageHide = () => fence('pagehide')
    const onFreeze = () => fence('freeze')
    const refreshVisibleControl = () => {
      const attempt = attemptRef.current
      if (
        attempt !== null &&
        controlCurrent(attempt, pageControlAbort.current) &&
        pageVisible()
      ) {
        setSnapshot(viewFromSnapshot(attempt.controller.snapshot))
      }
    }
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') fence('hidden')
      else refreshVisibleControl()
    }
    const onPageShow = () => refreshVisibleControl()
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('pageshow', onPageShow)
    document.addEventListener('freeze', onFreeze)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('pageshow', onPageShow)
      document.removeEventListener('freeze', onFreeze)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [controlCurrent, fence])

  const setSurface = useCallback(
    (surface: HTMLElement | null) => {
      if (surfaceRef.current === surface) return
      if (surfaceRef.current !== null) fence()
      surfaceRef.current = surface
      setSurfaceReady(surface !== null)
    },
    [fence],
  )

  const setViewport = useCallback((viewport: HTMLElement | null) => {
    if (viewportRef.current === viewport) return
    viewportRef.current = viewport
    setViewportReady(viewport !== null)
  }, [])

  const setInputClearer = useCallback((clearer: (() => void) | null) => {
    inputClearerRef.current = clearer
  }, [])

  const createAttempt = useCallback((): Attempt => {
    const currentIdentity = identityRef.current
    const surface = surfaceRef.current
    if (
      currentIdentity === null ||
      !currentIdentity.streamEligible ||
      surface === null ||
      !surfaceReady ||
      viewportRef.current === null ||
      !viewportReady ||
      !pageVisible()
    ) {
      throw asError('ATTACHMENT_UNAVAILABLE')
    }
    const provider =
      dependencies?.createProvider !== undefined
        ? dependencies.createProvider()
        : createManagedChromiumTrustProvider()
    if (provider === null) throw asError('ATTACHMENT_UNAVAILABLE')
    let trust: OwnedTrust | null = null
    const portFailure: { value: ApiError | null } = { value: null }
    try {
      trust =
        dependencies?.createTrust?.(provider) ??
        new WAWTrustProviderConsumer([provider])
      const abort = new AbortController()
      const epoch = options.contextEpoch.current
      const token = Symbol(String(epoch))
      const isAttemptCurrent = () => {
        const active = attemptRef.current
        return (
          mounted.current &&
          active !== null &&
          active.token === token &&
          !abort.signal.aborted &&
          pageVisible() &&
          identityRef.current?.streamMayContinue === true &&
          authScopeRef.current === options.authScope &&
          options.contextEpoch.current === epoch &&
          identityRef.current?.key === currentIdentity.key
        )
      }
      const requireCurrent = () => {
        if (!isAttemptCurrent())
          throw new WAWBrowserControllerError('CONTEXT_CHANGED')
      }
      const controllerOptions: WAWBrowserControllerOptions = {
        origin: dependencies?.origin?.() ?? window.location.origin,
        tickets: {
          issue: async (request) => {
            requireCurrent()
            let ticket: WorkspaceAttachmentTicketResponse
            try {
              ticket = request.reconnect
                ? await options.actions.reconnect(
                    request.workspaceId,
                    request.agentType,
                    abort.signal,
                  )
                : await options.actions.connect(
                    request.workspaceId,
                    request.agentType,
                    abort.signal,
                  )
            } catch (cause) {
              if (abort.signal.aborted) {
                throw new WAWBrowserControllerError('CONTEXT_CHANGED')
              }
              if (cause instanceof ApiError) portFailure.value = cause
              throw cause
            }
            requireCurrent()
            return ticket
          },
        },
        trust,
        controls: {
          detach: async (request) => {
            let result: WorkspaceDetachResponse
            try {
              result = await options.actions.detach(
                request.workspaceId,
                request.attachmentId,
                request.generation,
                request.leaseNumber,
                request.agentType,
                request.signal,
              )
            } catch (cause) {
              if (request.signal.aborted) {
                throw new WAWBrowserControllerError('CONTEXT_CHANGED')
              }
              if (cause instanceof ApiError) portFailure.value = cause
              throw cause
            }
            if (request.signal.aborted) {
              throw new WAWBrowserControllerError('CONTEXT_CHANGED')
            }
            return result
          },
          stop: async (request) => {
            let result: WorkspaceStopResponse
            try {
              result = await options.actions.stop(
                request.workspaceId,
                request.generation,
                request.agentType,
                request.signal,
              )
            } catch (cause) {
              if (request.signal.aborted) {
                throw new WAWBrowserControllerError('CONTEXT_CHANGED')
              }
              if (cause instanceof ApiError) portFailure.value = cause
              throw cause
            }
            if (request.signal.aborted) {
              throw new WAWBrowserControllerError('CONTEXT_CHANGED')
            }
            return result
          },
        },
        terminal: createBrowserTerminalSchedulerFactory(surface),
        onSnapshot: (next) => {
          if (!isAttemptCurrent()) {
            return
          }
          setSnapshot(viewFromSnapshot(next))
          if (['FENCED', 'DETACHED', 'STOPPED'].includes(next.status)) {
            queueMicrotask(() => {
              const currentAttempt = attemptRef.current
              if (currentAttempt?.token === token) closeTrust(currentAttempt)
            })
          }
        },
      }
      const controller =
        dependencies?.createController?.(controllerOptions) ??
        new WAWBrowserController(controllerOptions)
      const attempt = {
        token,
        epoch,
        authScope: options.authScope,
        identity: currentIdentity,
        abort,
        controller,
        trust,
        portFailure,
        trustClosed: false,
      }
      attemptRef.current = attempt
      return attempt
    } catch (error) {
      if (trust !== null) {
        try {
          trust.close()
        } catch {
          // A failed constructor cannot retain provider ownership.
        }
      } else {
        try {
          provider.dispose()
        } catch {
          // A failed provider cannot block a fail-closed attempt.
        }
      }
      throw error
    }
  }, [
    closeTrust,
    dependencies,
    options.actions,
    options.authScope,
    options.contextEpoch,
    surfaceReady,
    viewportReady,
  ])

  const connect = useCallback(
    async (reconnect: boolean) => {
      if (!pageVisible()) {
        const unavailable = asError('CONTEXT_CHANGED')
        setError(unavailable)
        setSnapshot({
          ...IDLE_VIEW,
          status: 'FENCED',
          reason: unavailable.code,
        })
        throw unavailable
      }
      if (!providerAvailable) {
        const unavailable = asError('ATTACHMENT_UNAVAILABLE')
        setError(unavailable)
        setSnapshot({
          ...IDLE_VIEW,
          status: 'UNAVAILABLE',
          reason: unavailable.code,
        })
        throw unavailable
      }
      const previous = attemptRef.current
      if (previous?.controller.snapshot.status === 'CONNECTED') {
        throw asError('CONTROLLER_BUSY')
      }
      if (previous !== null) {
        if (!previous.abort.signal.aborted) previous.abort.abort()
        previous.controller.contextChanged()
        closeTrust(previous)
      }
      setError(null)
      setLastInputOutcome(null)
      let attempt: Attempt | null = null
      try {
        const created = createAttempt()
        attempt = created
        await created.controller.connect({
          projectId: created.identity.projectId,
          workspaceId: created.identity.workspaceId,
          agentType: created.identity.agentType,
          generation: created.identity.generation,
          reconnect,
          context: Object.freeze({
            signal: created.abort.signal,
            isCurrent: () => current(created),
          }),
        } satisfies WAWBrowserConnectRequest)
      } catch (cause) {
        if (attempt === null || current(attempt)) {
          const failure =
            attempt?.portFailure.value ??
            (cause instanceof WAWBrowserControllerError
              ? asError(cause.code)
              : cause instanceof ApiError
                ? cause
                : asError('WAW_ACTION_FAILED'))
          if (failure.code === 'ATTACHMENT_UNAVAILABLE') {
            setSnapshot({
              ...IDLE_VIEW,
              status: 'UNAVAILABLE',
              reason: failure.code,
            })
          }
          setError(failure)
        }
        if (attempt !== null) closeTrust(attempt)
        throw (
          attempt?.portFailure.value ??
          (cause instanceof ApiError ||
          cause instanceof WAWBrowserControllerError
            ? cause
            : asError('WAW_ACTION_FAILED'))
        )
      }
    },
    [closeTrust, createAttempt, current, providerAvailable],
  )

  const controlRequest = useCallback(
    (attempt: Attempt): WAWBrowserControlRequest => {
      const lease = pageControlAbort.current
      return Object.freeze({
        projectId: attempt.identity.projectId,
        workspaceId: attempt.identity.workspaceId,
        agentType: attempt.identity.agentType,
        generation: attempt.identity.generation,
        context: Object.freeze({
          signal: lease.signal,
          isCurrent: () => controlCurrent(attempt, lease),
        }),
      })
    },
    [controlCurrent],
  )

  const detach = useCallback(async (): Promise<WAWBrowserDetachReceipt> => {
    const attempt = attemptRef.current
    if (attempt === null) throw asError('ATTACHMENT_UNAVAILABLE')
    attempt.portFailure.value = null
    try {
      return await attempt.controller.detach(controlRequest(attempt))
    } catch (cause) {
      throw attempt.portFailure.value ?? cause
    } finally {
      closeTrust(attempt)
    }
  }, [closeTrust, controlRequest])

  const stop = useCallback(async (): Promise<WAWBrowserStopOutcome> => {
    const attempt = attemptRef.current
    if (attempt === null) throw asError('ATTACHMENT_UNAVAILABLE')
    attempt.portFailure.value = null
    try {
      return await attempt.controller.stop(controlRequest(attempt))
    } catch (cause) {
      throw attempt.portFailure.value ?? cause
    } finally {
      closeTrust(attempt)
    }
  }, [closeTrust, controlRequest])

  const sendInput = useCallback(
    async (text: string): Promise<WAWBrowserInputOutcome> => {
      const attempt = attemptRef.current
      if (attempt === null || !current(attempt)) {
        throw asError('CONTROLLER_NOT_CONNECTED')
      }
      if (attempt.controller.snapshot.input !== null)
        throw asError('INPUT_BUSY')
      const bytes = new TextEncoder().encode(text)
      setLastInputOutcome(null)
      let pending: Promise<WAWBrowserInputOutcome>
      try {
        pending = attempt.controller.sendInput(bytes)
      } finally {
        bytes.fill(0)
      }
      const outcome = await pending
      if (scopeCurrent(attempt)) {
        setLastInputOutcome(
          Object.freeze({
            state: outcome.state,
            reasonCode: outcome.reasonCode,
          }),
        )
      }
      return outcome
    },
    [current, scopeCurrent],
  )

  useEffect(() => {
    const viewport = viewportRef.current
    if (
      viewport === null ||
      typeof ResizeObserver !== 'function' ||
      attemptRef.current?.controller.snapshot.status !== 'CONNECTED'
    ) {
      return
    }
    const report = (width: number, height: number) => {
      if (
        !Number.isFinite(width) ||
        !Number.isFinite(height) ||
        width <= 0 ||
        height <= 0
      ) {
        return
      }
      const contentWidth =
        width - WAW_TERMINAL_VIEWPORT_METRICS.horizontalPaddingPx * 2
      const contentHeight =
        height - WAW_TERMINAL_VIEWPORT_METRICS.verticalPaddingPx * 2
      if (contentWidth <= 0 || contentHeight <= 0) return
      const attempt = attemptRef.current
      if (
        attempt === null ||
        !current(attempt) ||
        attempt.controller.snapshot.status !== 'CONNECTED'
      ) {
        return
      }
      const columns = Math.max(
        WAW_TERMINAL_VIEWPORT_METRICS.columnsMin,
        Math.min(
          WAW_TERMINAL_VIEWPORT_METRICS.columnsMax,
          Math.floor(contentWidth / WAW_TERMINAL_VIEWPORT_METRICS.cellWidthPx),
        ),
      )
      const rows = Math.max(
        WAW_TERMINAL_VIEWPORT_METRICS.rowsMin,
        Math.min(
          WAW_TERMINAL_VIEWPORT_METRICS.rowsMax,
          Math.floor(
            contentHeight / WAW_TERMINAL_VIEWPORT_METRICS.cellHeightPx,
          ),
        ),
      )
      try {
        attempt.controller.requestResize(columns, rows)
      } catch (cause) {
        if (current(attempt)) {
          setError(
            cause instanceof WAWBrowserControllerError
              ? asError(cause.code)
              : asError('WAW_ACTION_FAILED'),
          )
        }
      }
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries.find((candidate) => candidate.target === viewport)
      if (entry !== undefined) {
        report(entry.contentRect.width, entry.contentRect.height)
      }
    })
    observer.observe(viewport)
    report(viewport.clientWidth, viewport.clientHeight)
    return () => observer.disconnect()
  }, [current, snapshot.status, viewportReady])

  const currentIdentity = identityRef.current
  const attempt = attemptRef.current
  const currentAttempt =
    attempt !== null &&
    currentIdentity?.key === attempt.identity.key &&
    current(attempt)
  const controlAttempt =
    attempt !== null &&
    currentIdentity?.key === attempt.identity.key &&
    controlCurrent(attempt, pageControlAbort.current)
  const currentSnapshot = controlAttempt ? attempt.controller.snapshot : null
  const snapshotView = currentSnapshot
    ? viewFromSnapshot(currentSnapshot)
    : snapshot
  const view: WAWAttachmentView = Object.freeze({
    ...snapshotView,
    ...(providerAvailable
      ? {}
      : {
          status: 'UNAVAILABLE' as const,
          reason: snapshotView.reason ?? 'ATTACHMENT_UNAVAILABLE',
        }),
    providerAvailable,
    surfaceReady,
    lastInputOutcome,
  })
  const status = view.status

  return {
    view,
    error,
    identity: currentIdentity,
    setSurface,
    setViewport,
    setInputClearer,
    fence,
    connect: () => connect(false),
    reconnect: () => connect(true),
    detach,
    stop,
    sendInput,
    controlSignal: () => pageControlAbort.current.signal,
    canConnect:
      currentIdentity !== null &&
      currentIdentity.streamEligible &&
      surfaceReady &&
      viewportReady &&
      providerAvailable &&
      pageVisible() &&
      view.status !== 'UNAVAILABLE' &&
      (attempt === null || ['FENCED', 'DETACHED'].includes(status)),
    canReconnect:
      controlAttempt &&
      currentIdentity?.streamEligible === true &&
      surfaceReady &&
      viewportReady &&
      providerAvailable &&
      pageVisible() &&
      ['FENCED', 'DETACHED'].includes(status),
    canDetach:
      controlAttempt &&
      view.attached !== null &&
      ['CONNECTED', 'FENCED'].includes(status),
    canInput: currentAttempt && status === 'CONNECTED' && view.input === null,
    canResize: currentAttempt && status === 'CONNECTED',
    canControlStop:
      controlAttempt &&
      view.attached !== null &&
      ['CONNECTED', 'FENCED', 'DETACHED'].includes(status),
  }
}
