import {
  useContext,
  useLayoutEffect,
  useMemo,
  useSyncExternalStore,
} from 'react'
import { AuthContext } from '../auth/AuthContext'
import { A3ChangesController } from './a3ChangesController'
import type { A3ChangesDependencies } from './a3ChangesTrust'

/** Production callers deliberately omit dependencies until a separately reviewed
 * A3 adapter AND independent A3 purpose pin are available. */
export function useA3ChangesReader(
  projectId: string | undefined,
  dependencies?: A3ChangesDependencies,
) {
  const auth = useContext(AuthContext)
  const sessionId = auth?.auth?.session.id
  const authenticated = auth?.status === 'authenticated' && Boolean(sessionId)
  const controller = useMemo(
    () =>
      new A3ChangesController(
        projectId ?? '',
        authenticated && sessionId ? dependencies : undefined,
      ),
    // Session identity is only a local fence; it never enters A3 context/transport.
    // Auth epoch is independently checked and synchronously invalidated by trust.
    [projectId, dependencies, authenticated, sessionId],
  )
  const state = useSyncExternalStore(
    controller.subscribe,
    () => controller.snapshot,
    () => controller.snapshot,
  )
  useLayoutEffect(() => {
    controller.activate()
    const hidden = () => {
      if (document.hidden) controller.clear('stale')
    }
    const interrupt = () => controller.clear('stale')
    document.addEventListener('visibilitychange', hidden)
    document.addEventListener('freeze', interrupt)
    window.addEventListener('pagehide', interrupt)
    window.addEventListener('offline', interrupt)
    return () => {
      document.removeEventListener('visibilitychange', hidden)
      document.removeEventListener('freeze', interrupt)
      window.removeEventListener('pagehide', interrupt)
      window.removeEventListener('offline', interrupt)
      controller.dispose()
    }
  }, [controller])
  return {
    state,
    controller,
    available: Boolean(authenticated && controller.available),
  }
}
