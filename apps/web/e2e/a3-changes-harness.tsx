/** CI-only entry: real native Git/API/admission/opaque relay, actual Web crypto and DOM. */
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthContext } from '../src/features/auth/AuthContext'
import { ContentError, ERROR_CODES } from '../src/features/content/a3Content'
import { parseA3Binding } from '../src/features/content/a3ChangesDto'
import { MAX_ENVELOPE_BYTES } from '../src/features/content/a3Crypto'
import {
  readA3Trust,
  type A3ChangesDependencies,
  type A3ChangesTrust,
} from '../src/features/content/a3ChangesTrust'
import { ApiClient } from '../src/lib/api'
import { ProjectChangesPage } from '../src/pages/ProjectChangesPage'
import '../src/styles.css'

declare global {
  interface Window {
    __a3FixtureCall(
      op: string,
      payload: Record<string, unknown>,
    ): Promise<unknown>
    a3Executed?: boolean
  }
}
const projectId = `prj_${'a'.repeat(32)}`
const hex = (raw: Uint8Array) =>
  Array.from(raw, (byte) => byte.toString(16).padStart(2, '0')).join('')
function bytes(wire: unknown) {
  if (
    typeof wire !== 'string' ||
    wire.length === 0 ||
    wire.length > MAX_ENVELOPE_BYTES * 2 ||
    !/^(?:[a-f0-9]{2})+$/.test(wire)
  )
    throw new ContentError()
  return Uint8Array.from(wire.match(/../g)!, (pair) => parseInt(pair, 16))
}
async function call(op: string, payload: Record<string, unknown> = {}) {
  try {
    return await window.__a3FixtureCall(op, payload)
  } catch (error) {
    const message = error instanceof Error ? error.message : ''
    const code = ERROR_CODES.find((code) => message.endsWith(code))
    throw new ContentError(
      code ??
        (/AUTH_|SESSION_/.test(message)
          ? 'PATCH_REVOKED'
          : 'PATCH_PROTOCOL_INVALID'),
    )
  }
}
async function start() {
  const fixture = (await call('trust')) as {
    purpose: A3ChangesTrust['purpose']
    binding: unknown
    pin: string
  }
  const query = new URLSearchParams(location.search)
  let trusted: A3ChangesTrust | null =
    query.get('missing') === 'pin'
      ? null
      : {
          purpose: fixture.purpose,
          binding: parseA3Binding(fixture.binding),
          pin32: bytes(fixture.pin),
        }
  const listeners = new Set<() => void>()
  const trust = {
    current: () => trusted,
    subscribeInvalidation(listener: () => void) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
  if (trusted) readA3Trust(trust)
  window.addEventListener('a3-test-trust-revoke', () => {
    trusted = null
    for (const listener of listeners) listener()
  })
  let pendingClose = Promise.resolve()
  const dependencies: A3ChangesDependencies = {
    trust,
    // Fixture local elapsed clock only, closed explicitly on lifecycle changes.
    nowMs: () => Math.floor(performance.now()),
    async observe(requestedProject, signal) {
      if (requestedProject !== projectId || signal.aborted)
        throw new ContentError('PATCH_REVOKED')
      const observation = await call('bootstrap')
      if (signal.aborted) throw new ContentError('PATCH_STALE')
      return observation
    },
    async open(request, signal) {
      await pendingClose
      if (signal.aborted) throw new ContentError('PATCH_STALE')
      const { handle } = (await call('open', request)) as { handle: string }
      let closed = false
      let sending = false
      let receiving = false
      const closeListeners = new Set<() => void>()
      const disconnect = () => {
        for (const listener of closeListeners) listener()
      }
      const close = () => {
        if (closed) return
        closed = true
        signal.removeEventListener('abort', close)
        window.removeEventListener('a3-test-disconnect', disconnect)
        pendingClose = call('close', { handle }).then(
          () => undefined,
          () => undefined,
        )
      }
      signal.addEventListener('abort', close, { once: true })
      window.addEventListener('a3-test-disconnect', disconnect)
      if (signal.aborted) close()
      return {
        async send(raw: Uint8Array, checkCurrent: () => void) {
          if (
            closed ||
            sending ||
            raw.length < 1 ||
            raw.length > MAX_ENVELOPE_BYTES
          )
            throw new ContentError()
          sending = true
          try {
            const wire = hex(raw)
            checkCurrent() // Actual browser bridge publication boundary, no await.
            await call('send', { wire, handle })
          } finally {
            sending = false
          }
        },
        async receive() {
          if (closed || receiving) throw new ContentError()
          receiving = true
          try {
            const result = (await call('receive', { handle })) as {
              wire: string
            }
            // hold-end deliberately returns late bytes; the real controller fences them.
            return bytes(result.wire)
          } finally {
            receiving = false
          }
        },
        close,
        subscribeClose(listener: () => void) {
          closeListeners.add(listener)
          if (closed) listener()
          return () => closeListeners.delete(listener)
        },
      }
    },
  }
  const auth = {
    user: { id: `adm_${'9'.repeat(32)}`, username: '合成测试管理员' },
    session: {
      id: `ses_${'8'.repeat(32)}`,
      expires_at: '2099-01-01T00:00:00Z',
    },
    csrf_token: 'synthetic-dom-only-not-bridge-credential',
  }
  const root = document.getElementById('root')
  if (!root) throw new Error('A3 fixture root is missing')
  createRoot(root).render(
    <AuthContext.Provider
      value={{
        api: new ApiClient(),
        auth,
        status: 'authenticated',
        login: async () => undefined,
        logout: async () => undefined,
        refresh: async () => auth,
      }}
    >
      <main
        style={{
          width: '100%',
          maxWidth: '70rem',
          margin: '0 auto',
          padding: '1rem',
          boxSizing: 'border-box',
        }}
      >
        <MemoryRouter initialEntries={[`/projects/${projectId}/changes`]}>
          <Routes>
            <Route
              path="/projects/:projectId/changes"
              element={
                <ProjectChangesPage
                  locale="zh-CN"
                  a3Dependencies={
                    query.get('missing') === 'adapter'
                      ? undefined
                      : dependencies
                  }
                />
              }
            />
            <Route path="/projects/:projectId" element={<p>已离开变更页</p>} />
          </Routes>
        </MemoryRouter>
      </main>
    </AuthContext.Provider>,
  )
}
void start()
