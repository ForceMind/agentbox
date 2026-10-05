import { useEffect, useRef, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../../lib/api'

export type OverviewResource<T> =
  | {
      phase: 'loading' | 'stale' | 'error' | 'forbidden'
      data: null
      receivedAt: null
    }
  | { phase: 'ready'; data: T; receivedAt: Date }

type OwnedResource<T> = { owner: string | null; value: OverviewResource<T> }

/** One bounded metadata GET per visible lifecycle, never a background poll. */
export function useOverviewResource<T>(
  path: string,
  validate: (value: unknown) => T,
  refreshSequence: number,
): OverviewResource<T> {
  const { api, auth, status } = useAuth()
  const owner =
    status === 'authenticated' && auth
      ? `${auth.user.id}:${auth.session.id}`
      : null
  const [state, setState] = useState<OwnedResource<T>>({
    owner: null,
    value: { phase: 'loading', data: null, receivedAt: null },
  })

  // Explicit refresh/auth changes must not reset a pagehide/freeze/offline fence.
  const availability = useRef({ suspended: false, offline: !navigator.onLine })

  useEffect(() => {
    let pending: AbortController | null = null
    let disposed = false
    let dirty = true

    function clear(phase: 'loading' | 'stale' | 'error' | 'forbidden') {
      setState({ owner, value: { phase, data: null, receivedAt: null } })
    }
    function invalidate() {
      dirty = true
      pending?.abort()
      pending = null
      clear('stale')
    }
    function refresh() {
      if (
        disposed ||
        owner === null ||
        !dirty ||
        availability.current.suspended ||
        availability.current.offline ||
        document.visibilityState === 'hidden'
      )
        return
      dirty = false
      const controller = new AbortController()
      pending = controller
      clear('loading')
      void api
        .get<T>(path, {
          signal: controller.signal,
          timeoutMs: 15_000,
          validate,
        })
        .then((data) => {
          if (disposed || controller.signal.aborted || pending !== controller)
            return
          setState({
            owner,
            value: { phase: 'ready', data, receivedAt: new Date() },
          })
        })
        .catch((error: unknown) => {
          if (disposed || controller.signal.aborted || pending !== controller)
            return
          clear(
            error instanceof ApiError && [401, 403].includes(error.status)
              ? 'forbidden'
              : 'error',
          )
        })
        .finally(() => {
          if (pending === controller) pending = null
        })
    }
    function visibility() {
      if (document.visibilityState === 'hidden') invalidate()
      else refresh()
    }
    function suspend() {
      availability.current.suspended = true
      invalidate()
    }
    function resume() {
      availability.current.suspended = false
      refresh()
    }
    function goOffline() {
      availability.current.offline = true
      invalidate()
    }
    function goOnline() {
      availability.current.offline = false
      refresh()
    }

    if (owner === null) clear('forbidden')
    else if (
      availability.current.suspended ||
      availability.current.offline ||
      document.visibilityState === 'hidden'
    )
      clear('stale')
    else refresh()
    document.addEventListener('visibilitychange', visibility)
    document.addEventListener('freeze', suspend)
    document.addEventListener('resume', resume)
    window.addEventListener('pagehide', suspend)
    window.addEventListener('pageshow', resume)
    window.addEventListener('offline', goOffline)
    window.addEventListener('online', goOnline)
    return () => {
      disposed = true
      pending?.abort()
      document.removeEventListener('visibilitychange', visibility)
      document.removeEventListener('freeze', suspend)
      document.removeEventListener('resume', resume)
      window.removeEventListener('pagehide', suspend)
      window.removeEventListener('pageshow', resume)
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('online', goOnline)
    }
  }, [api, owner, path, refreshSequence, validate])

  // Do not render a prior user's rows even for the render before effect cleanup.
  if (state.owner !== owner)
    return {
      phase: owner ? 'loading' : 'forbidden',
      data: null,
      receivedAt: null,
    }
  return state.value
}
