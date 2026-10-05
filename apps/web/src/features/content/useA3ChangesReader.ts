import {
  useContext,
  useLayoutEffect,
  useMemo,
  useSyncExternalStore,
} from 'react'
import { AuthContext } from '../auth/AuthContext'
import { A3ChangesController } from './a3ChangesController'
import type { A3ChangesDependencies } from './a3ChangesTrust'

/** Formal callers construct independent static trust plus native admission.
 * Unconfigured pages and historical synthetic tests keep their separate paths. */
export function useA3ChangesReader(
  projectId: string | undefined,
  dependencies?: A3ChangesDependencies,
) {
  const auth = useContext(AuthContext)
  const sessionId = auth?.auth?.session.id
  const csrfToken = auth?.auth?.csrf_token
  const authenticated = auth?.status === 'authenticated' && Boolean(sessionId)
  const controller = useMemo(
    () =>
      new A3ChangesController(
        projectId ?? '',
        authenticated && sessionId && csrfToken ? dependencies : undefined,
      ),
    // Session identity is only a local fence; it never enters A3 context/transport.
    // Native auth epoch is independently checked by the live admitted channel.
    [projectId, dependencies, authenticated, sessionId, csrfToken],
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
