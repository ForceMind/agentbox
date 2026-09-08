import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'

import { useAuth } from '../auth/AuthContext'
import {
  parseWorkspaceRuntimeStatusResponse,
  WorkspaceRuntimeStatusResponse,
} from '../../lib/contracts'
import { workspaceApiError, type WorkspaceApiErrorView } from './workspaceView'

type ReceivedSnapshot = Readonly<{ receivedAt: number | null }>

export type WorkspaceStatusView =
  | { status: 'idle' }
  | { status: 'loading' }
  | ({ status: 'stale' } & ReceivedSnapshot)
  | ({ status: 'revalidating' } & ReceivedSnapshot)
  | {
      status: 'loaded'
      response: WorkspaceRuntimeStatusResponse
      receivedAt: number
      observationToken: number
    }
  | {
      status: 'error'
      error: WorkspaceApiErrorView
      receivedAt?: number
    }

type ActiveRequest = {
  readonly controller: AbortController
  readonly generation: number
  readonly scope: string
  promise: Promise<void>
}

/** Fetches bounded metadata only; it never creates an admission or terminal transport. */
export function useWorkspaceStatus(
  workspaceId: string | undefined,
  refreshKey = '',
  onInvalidate?: () => void,
) {
  const { api, auth } = useAuth()
  const scope = `${auth?.session.id ?? ''}:${auth?.csrf_token ?? ''}:${workspaceId ?? ''}:${refreshKey}`
  const [snapshot, setSnapshot] = useState<{
    scope: string
    view: WorkspaceStatusView
  }>({ scope: '', view: { status: 'idle' } })
  const mounted = useRef(false)
  const currentScope = useRef('')
  const requestGeneration = useRef(0)
  const observationToken = useRef(0)
  const observationAbort = useRef<AbortController | null>(null)
  const activeRequest = useRef<ActiveRequest | null>(null)
  const lastReceivedAt = useRef<number | null>(null)
  const needsRevalidation = useRef(false)
  const pageHidden = useRef(false)
  const frozen = useRef(false)
  const offline = useRef(
    typeof navigator !== 'undefined' && navigator.onLine === false,
  )
  const invalidationCallback = useRef(onInvalidate)

  useLayoutEffect(() => {
    invalidationCallback.current = onInvalidate
    if (currentScope.current === scope) return
    currentScope.current = scope
    requestGeneration.current += 1
    observationToken.current += 1
    observationAbort.current?.abort()
    observationAbort.current = null
    activeRequest.current?.controller.abort()
    activeRequest.current = null
    lastReceivedAt.current = null
    needsRevalidation.current = false
  }, [onInvalidate, scope])

  const pageCanRead = useCallback(
    () =>
      typeof document !== 'undefined' &&
      document.visibilityState !== 'hidden' &&
      !pageHidden.current &&
      !frozen.current &&
      !offline.current &&
      (typeof navigator === 'undefined' || navigator.onLine !== false),
    [],
  )

  const invalidate = useCallback(() => {
    requestGeneration.current += 1
    observationToken.current += 1
    observationAbort.current?.abort()
    observationAbort.current = null
    needsRevalidation.current = !!workspaceId
    const request = activeRequest.current
    activeRequest.current = null
    request?.controller.abort()
    invalidationCallback.current?.()
    if (mounted.current) {
      setSnapshot({
        scope,
        view: workspaceId
          ? { status: 'stale', receivedAt: lastReceivedAt.current }
          : { status: 'idle' },
      })
    }
  }, [scope, workspaceId])

  const refresh = useCallback(async () => {
    if (!workspaceId) {
      needsRevalidation.current = false
      setSnapshot({ scope, view: { status: 'idle' } })
      return
    }
    if (!pageCanRead()) {
      needsRevalidation.current = true
      setSnapshot({
        scope,
        view: { status: 'stale', receivedAt: lastReceivedAt.current },
      })
      return
    }
    const existing = activeRequest.current
    if (existing?.scope === scope) return existing.promise

    const generation = ++requestGeneration.current
    const token = ++observationToken.current
    observationAbort.current?.abort()
    observationAbort.current = null
    const controller = new AbortController()
    const request: ActiveRequest = {
      controller,
      generation,
      scope,
      promise: Promise.resolve(),
    }
    const wasInvalidated = needsRevalidation.current
    setSnapshot({
      scope,
      view: wasInvalidated
        ? { status: 'revalidating', receivedAt: lastReceivedAt.current }
        : { status: 'loading' },
    })
    request.promise = (async () => {
      try {
        const response = await api.get<WorkspaceRuntimeStatusResponse>(
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/status`,
          {
            timeoutMs: 10_000,
            signal: controller.signal,
            // The controller compares all Runtime identity fields against the
            // selected metadata row and emits the specific fenced identity error.
            // Keeping the parsed response here lets that higher-level guard
            // distinguish an identity mismatch from transport unavailability.
            validate: parseWorkspaceRuntimeStatusResponse,
          },
        )
        if (
          mounted.current &&
          !controller.signal.aborted &&
          currentScope.current === scope &&
          requestGeneration.current === generation &&
          observationToken.current === token &&
          pageCanRead()
        ) {
          const receivedAt = Date.now()
          const loadedAbort = new AbortController()
          lastReceivedAt.current = receivedAt
          observationAbort.current = loadedAbort
          needsRevalidation.current = false
          setSnapshot({
            scope,
            view: {
              status: 'loaded',
              response,
              receivedAt,
              observationToken: token,
            },
          })
        }
      } catch (error) {
        if (
          mounted.current &&
          !controller.signal.aborted &&
          currentScope.current === scope &&
          requestGeneration.current === generation &&
          observationToken.current === token &&
          pageCanRead()
        ) {
          needsRevalidation.current = false
          setSnapshot({
            scope,
            view: {
              status: 'error',
              error: workspaceApiError(error, 'WAW_STATUS_UNAVAILABLE'),
              ...(lastReceivedAt.current === null
                ? {}
                : { receivedAt: lastReceivedAt.current }),
            },
          })
        }
      } finally {
        if (activeRequest.current === request) activeRequest.current = null
      }
    })()
    activeRequest.current = request
    return request.promise
  }, [api, pageCanRead, scope, workspaceId])

  useEffect(() => {
    mounted.current = true
    offline.current = navigator.onLine === false
    const recover = () => {
      if (needsRevalidation.current && pageCanRead()) void refresh()
    }
    const onPageHide = () => {
      pageHidden.current = true
      invalidate()
    }
    const onPageShow = () => {
      pageHidden.current = false
      frozen.current = false
      recover()
    }
    const onFreeze = () => {
      frozen.current = true
      invalidate()
    }
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        pageHidden.current = true
        invalidate()
      } else {
        pageHidden.current = false
        frozen.current = false
        recover()
      }
    }
    const onOffline = () => {
      offline.current = true
      invalidate()
    }
    const onOnline = () => {
      offline.current = false
      recover()
    }
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('pageshow', onPageShow)
    window.addEventListener('offline', onOffline)
    window.addEventListener('online', onOnline)
    document.addEventListener('freeze', onFreeze)
    document.addEventListener('visibilitychange', onVisibility)
    void refresh()
    return () => {
      mounted.current = false
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('pageshow', onPageShow)
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('online', onOnline)
      document.removeEventListener('freeze', onFreeze)
      document.removeEventListener('visibilitychange', onVisibility)
      requestGeneration.current += 1
      observationToken.current += 1
      observationAbort.current?.abort()
      observationAbort.current = null
      const request = activeRequest.current
      activeRequest.current = null
      request?.controller.abort()
    }
  }, [invalidate, pageCanRead, refresh])

  const view: WorkspaceStatusView =
    snapshot.scope === scope
      ? snapshot.view
      : workspaceId
        ? pageCanRead()
          ? { status: 'loading' }
          : { status: 'stale', receivedAt: null }
        : { status: 'idle' }
  const currentViewToken =
    view.status === 'loaded' ? view.observationToken : null
  const currentSignal =
    view.status === 'loaded' ? (observationAbort.current?.signal ?? null) : null
  const isCurrent = useCallback(
    (token: number | null) =>
      token !== null &&
      mounted.current &&
      currentScope.current === scope &&
      observationToken.current === token &&
      pageCanRead(),
    [pageCanRead, scope],
  )
  return {
    refresh,
    view,
    observationToken: currentViewToken,
    observationSignal: currentSignal,
    isCurrent,
  }
}
