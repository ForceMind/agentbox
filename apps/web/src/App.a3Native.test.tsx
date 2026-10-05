import { webcrypto } from 'node:crypto'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { useGitChanges } from './features/changes/useGitChanges'
import {
  a3TestProject,
  createA3TestFixture,
} from './features/content/a3Changes.testSupport'
import {
  nativeOrigin,
  nativeBootstrap,
  nativeResponse,
  staticResponse,
  NativeTestSocket,
  selectNativeBootstrap,
} from './features/content/a3Native.testSupport'
import { A3_BOOTSTRAP_PATH } from './features/content/a3TrustHTTPS'

vi.mock('./features/changes/useGitChanges', () => ({ useGitChanges: vi.fn() }))
const auth = {
  user: { id: 'adm_native', username: '测试管理员' },
  session: { id: 'ses_native', expires_at: '2026-10-06T00:00:00Z' },
  csrf_token: 'csrf-native-formal',
}
beforeEach(() => {
  selectNativeBootstrap()
  vi.stubGlobal(
    'location',
    new URL(`${nativeOrigin}/projects/${a3TestProject}/changes`),
  )
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('WebSocket', NativeTestSocket)
  NativeTestSocket.instances = []
  NativeTestSocket.onCreate = undefined
  vi.mocked(useGitChanges).mockReturnValue({
    files: [
      {
        path: 'success.txt',
        previous_path: null,
        kind: 'modified',
        staged: true,
        unstaged: false,
      },
    ],
    totalCount: 1,
    nextCursor: null,
    isRepository: true,
    loading: false,
    loadingMore: false,
    stale: false,
    error: null,
    refresh: async () => undefined,
    loadMore: async () => undefined,
  })
})
afterEach(() => {
  cleanup()
  document.head.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
async function source() {
  const fixture = await createA3TestFixture()
  const data = fixture.observation()
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const path = new URL(String(input), nativeOrigin).pathname
    if (path === '/api/v1/auth/me')
      return nativeResponse(path, {
        api_version: 'v1',
        request_id: 'req_auth',
        data: auth,
      })
    if (path === A3_BOOTSTRAP_PATH) return staticResponse(nativeBootstrap)
    if (path.endsWith('/git/staged-observation'))
      return nativeResponse(path, {
        api_version: 'v1',
        request_id: 'req_obs',
        data,
      })
    if (path === '/healthz') return nativeResponse(path, { status: 'ok' })
    if (path === '/readyz')
      return nativeResponse(path, {
        status: 'ready',
        checks: { database: true, migrations: true },
      })
    return nativeResponse(path, {
      api_version: 'v1',
      request_id: 'req_other',
      data: {},
    })
  })
  vi.stubGlobal('fetch', fetch)
  return { fetch }
}
describe('formal App Changes route constructs native dependencies', () => {
  it('loads only independent static trust before deliberate click, with no injected page adapter', async () => {
    const { fetch } = await source()
    NativeTestSocket.onCreate = (socket) => {
      socket.autoReady = false
      socket.onData = () =>
        socket.message(
          new Uint8Array(
            new TextEncoder().encode('A3ER\x01PATCH_UNAVAILABLE_BINARY'),
          ),
        )
    }
    render(<App />)
    const button = await screen.findByRole('button', {
      name: '读取暂存补丁：success.txt',
    })
    await waitFor(() => expect(button).toBeEnabled())
    expect(
      fetch.mock.calls.filter(([url]) =>
        String(url).endsWith(A3_BOOTSTRAP_PATH),
      ),
    ).toHaveLength(2)
    expect(
      fetch.mock.calls.some(([url]) =>
        String(url).endsWith('/staged-observation'),
      ),
    ).toBe(false)
    expect(NativeTestSocket.instances).toHaveLength(0)
    fireEvent.click(button)
    await waitFor(() =>
      expect(screen.getByTestId('a3-reader-status')).toHaveTextContent(
        '这是二进制文件',
      ),
    )
    expect(NativeTestSocket.instances).toHaveLength(1)
    expect(NativeTestSocket.instances[0].url).toBe(
      `wss://a3.agentbox.test/api/v1/projects/${a3TestProject}/git/staged-stream`,
    )
  })
  it('keeps the unconfigured formal page explicitly unavailable with zero A3 network', async () => {
    const { fetch } = await source()
    document.head.innerHTML = ''
    render(<App />)
    const button = await screen.findByRole('button', {
      name: '读取暂存补丁：success.txt',
    })
    expect(button).toBeDisabled()
    expect(screen.getByTestId('a3-reader-status')).toHaveTextContent(
      '暂存内容暂不可用',
    )
    expect(
      fetch.mock.calls.some(
        ([url]) =>
          String(url).includes('a3-bootstrap') ||
          String(url).endsWith('/staged-observation'),
      ),
    ).toBe(false)
    expect(NativeTestSocket.instances).toHaveLength(0)
  })
})
