import { webcrypto } from 'node:crypto'
import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { ApiClient } from '../../lib/api'
import { useNativeA3Changes } from './useNativeA3Changes'
import { a3TestProject, createA3TestFixture } from './a3Changes.testSupport'
import type { A3ChangesDependencies } from './a3ChangesTrust'
import {
  nativeOrigin,
  nativeResponse,
  staticResponse,
  NativeTestSocket,
  selectNativeBootstrap,
} from './a3Native.testSupport'
import { A3_BOOTSTRAP_PATH } from './a3TrustHTTPS'

const auth: AuthContextValue = {
  api: new ApiClient(),
  status: 'authenticated',
  auth: {
    user: { id: 'adm_native', username: 'admin' },
    session: { id: 'ses_native', expires_at: '2026-10-06T00:00:00Z' },
    csrf_token: 'csrf-native',
  },
  login: async () => undefined,
  logout: async () => undefined,
  refresh: async () => null,
}
let latest: A3ChangesDependencies | undefined
function Probe({ projectId }: { projectId: string }) {
  latest = useNativeA3Changes(projectId)
  return <p>{latest ? 'ready' : 'unavailable'}</p>
}
function tree(value = auth, projectId = a3TestProject) {
  return (
    <AuthContext.Provider value={value}>
      <Probe projectId={projectId} />
    </AuthContext.Provider>
  )
}
function changed(mode: string) {
  if (mode === 'session')
    return {
      ...auth,
      auth: {
        ...auth.auth!,
        session: { ...auth.auth!.session, id: 'ses_changed' },
      },
    }
  if (mode === 'csrf')
    return { ...auth, auth: { ...auth.auth!, csrf_token: 'csrf-changed' } }
  return auth
}
beforeEach(() => {
  selectNativeBootstrap()
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('WebSocket', NativeTestSocket)
  NativeTestSocket.instances = []
  NativeTestSocket.onCreate = undefined
  latest = undefined
})
afterEach(() => {
  cleanup()
  document.head.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
describe('page-owned native bootstrap generations', () => {
  it.each(['route', 'session', 'csrf'])(
    'fences delayed old bootstrap on %s change',
    async (mode) => {
      let firstSignal: AbortSignal | undefined
      let release!: () => void
      const fetch = vi.fn<typeof globalThis.fetch>(async (_input, init) => {
        if (fetch.mock.calls.length === 1) {
          firstSignal = init!.signal!
          await new Promise<void>((resolve) => {
            release = resolve
          })
        }
        return staticResponse()
      })
      vi.stubGlobal('fetch', fetch)
      const view = render(tree())
      await waitFor(() => expect(release).toBeDefined())
      view.rerender(
        tree(
          changed(mode),
          mode === 'route' ? `prj_${'b'.repeat(32)}` : a3TestProject,
        ),
      )
      expect(firstSignal!.aborted).toBe(true)
      await waitFor(() => expect(latest).toBeDefined())
      const newest = latest
      release()
      await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
      expect(latest).toBe(newest)
      expect(NativeTestSocket.instances).toHaveLength(0)
    },
  )
  it.each(['route', 'session', 'csrf'])(
    'closes pending native open on %s change and ignores late READY',
    async (mode) => {
      const fixture = await createA3TestFixture(),
        data = fixture.observation()
      vi.stubGlobal(
        'fetch',
        vi.fn<typeof globalThis.fetch>(async (input) => {
          const path = new URL(String(input), nativeOrigin).pathname
          return path === A3_BOOTSTRAP_PATH
            ? staticResponse()
            : nativeResponse(path, {
                api_version: 'v1',
                request_id: 'req_native',
                data,
              })
        }),
      )
      NativeTestSocket.onCreate = (socket) => {
        socket.autoReady = false
      }
      const view = render(tree())
      await waitFor(() => expect(latest).toBeDefined())
      const old = latest!,
        abort = new AbortController()
      await old.observe(a3TestProject, abort.signal)
      const pending = old.open(
        {
          projectId: a3TestProject,
          selectionId: data.entries[0].selection_id!,
          requestNonce: 'f'.repeat(64),
        },
        abort.signal,
      )
      void pending.catch(() => undefined)
      await waitFor(() => expect(NativeTestSocket.instances).toHaveLength(1))
      const socket = NativeTestSocket.instances[0]
      view.rerender(
        tree(
          changed(mode),
          mode === 'route' ? `prj_${'b'.repeat(32)}` : a3TestProject,
        ),
      )
      await expect(pending).rejects.toThrow()
      expect(socket.close).toHaveBeenCalledTimes(1)
      expect(old.trust.current()).toBeNull()
      socket.message(new Uint8Array([65, 51, 82, 68, 1]))
      await waitFor(() => expect(latest).toBeDefined())
      expect(latest).not.toBe(old)
      expect(socket.sent).toHaveLength(1)
    },
  )
})
