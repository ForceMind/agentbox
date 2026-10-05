import { useLayoutEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { createA3ChangesNative, type A3NativeOwner } from './a3ChangesNative'

/** Each formal route/session owns its own bootstrap and irreversible native lifetime. */
export function useNativeA3Changes(projectId: string | undefined) {
  const { auth, status } = useAuth()
  const csrfToken = auth?.csrf_token
  const scope =
    status === 'authenticated' && auth && projectId
      ? JSON.stringify([projectId, auth.user.id, auth.session.id, csrfToken])
      : null
  const latest = useRef(scope)
  latest.current = scope
  const [owned, setOwned] = useState<{ scope: string; owner: A3NativeOwner }>()
  useLayoutEffect(() => {
    if (!scope || !projectId || !csrfToken) return
    const abort = new AbortController()
    let owner: A3NativeOwner | undefined
    void createA3ChangesNative({
      projectId,
      csrfToken,
      signal: abort.signal,
      isCurrent: () => !abort.signal.aborted && latest.current === scope,
    })
      .then((value) => {
        if (abort.signal.aborted || latest.current !== scope) {
          value?.close()
          return
        }
        owner = value
        if (value) setOwned({ scope, owner: value })
      })
      .catch(() => {
        /* Fail closed: the page stays explicitly unavailable. */
      })
    return () => {
      abort.abort()
      owner?.close()
    }
  }, [scope, projectId, csrfToken])
  return owned?.scope === scope ? owned.owner.dependencies : undefined
}
