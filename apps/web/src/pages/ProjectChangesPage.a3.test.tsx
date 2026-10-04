import { webcrypto } from 'node:crypto'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'
import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import { useGitChanges } from '../features/changes/useGitChanges'
import {
  a3DangerousPatch,
  a3TestProject,
  createA3TestFixture,
} from '../features/content/a3Changes.testSupport'
import { ApiClient } from '../lib/api'
import { ProjectChangesPage } from './ProjectChangesPage'

vi.mock('../features/changes/useGitChanges', () => ({ useGitChanges: vi.fn() }))
beforeAll(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
const refresh = vi.fn(async () => undefined)
const auth = {
  user: { id: 'adm_fixture', username: '测试管理员' },
  session: { id: 'ses_fixture', expires_at: '2027-01-01T00:00:00Z' },
  csrf_token: 'synthetic-unit-only',
}
const authValue: AuthContextValue = {
  api: new ApiClient(),
  auth,
  status: 'authenticated',
  login: async () => undefined,
  logout: async () => undefined,
  refresh: async () => auth,
}
beforeEach(() => {
  refresh.mockClear()
  vi.mocked(useGitChanges).mockReturnValue({
    files: [
      {
        path: 'success.txt',
        previous_path: null,
        kind: 'modified',
        staged: true,
        unstaged: true,
      },
    ],
    totalCount: 1,
    nextCursor: null,
    isRepository: true,
    loading: false,
    loadingMore: false,
    stale: false,
    error: null,
    refresh,
    loadMore: async () => undefined,
  })
})
async function setup(options: Parameters<typeof createA3TestFixture>[0] = {}) {
  const fixture = await createA3TestFixture(options)
  const tree = (value = authValue) => (
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[`/projects/${a3TestProject}/changes`]}>
        <Routes>
          <Route
            element={<ProjectChangesPage a3Dependencies={fixture.deps} />}
            path="/projects/:projectId/changes"
          />
          <Route element={<p>已离开变更页</p>} path="/projects/:projectId" />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  )
  const rendered = render(tree())
  const read = () =>
    fireEvent.click(
      screen.getByRole('button', { name: '读取暂存补丁：success.txt' }),
    )
  const complete = async () => {
    read()
    await screen.findByTestId('a3-complete-patch')
  }
  return { fixture, rendered, tree, read, complete }
}
describe('A3 page lifecycle and inert React rendering', () => {
  it('reads only after deliberate native-button activation and renders dangerous source as inert text', async () => {
    const { fixture, complete } = await setup()
    const button = screen.getByRole('button', {
      name: '读取暂存补丁：success.txt',
    })
    fireEvent.mouseEnter(button)
    button.focus()
    expect(fixture.deps.observe).not.toHaveBeenCalled()
    expect(fixture.deps.open).not.toHaveBeenCalled()
    await complete()
    const patch = screen.getByTestId('a3-complete-patch')
    expect(patch.textContent).toBe(a3DangerousPatch)
    expect(patch.querySelector('img,script,a,svg')).toBeNull()
    expect(patch).toHaveAttribute('tabindex', '0')
    expect(screen.getByText(/浏览器读取完成时间/)).toHaveTextContent(
      '非仓库观察时间',
    )
    expect(fixture.requests[0]).not.toHaveProperty('path')
    expect(screen.getByTestId('a3-reader-status')).toHaveAttribute(
      'aria-live',
      'polite',
    )
  })
  it('clears completed content before a metadata refresh and never re-reads automatically', async () => {
    const { fixture, complete } = await setup()
    await complete()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
  })
  it('cancels pending END and ignores delayed bytes', async () => {
    const { fixture, read } = await setup({ holdEnd: true })
    read()
    await waitFor(() => expect(fixture.held).toBe(true))
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '取消读取' }))
    expect(fixture.closed).toBe(1)
    await act(async () => fixture.release())
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(screen.getByTestId('a3-reader-status')).toHaveTextContent('尚未读取')
  })
  it.each(['freeze', 'pagehide', 'offline', 'visibilitychange'])(
    'clears plaintext on %s without replay when visible',
    async (event) => {
      const { complete, fixture } = await setup()
      await complete()
      if (event === 'visibilitychange')
        vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
      act(() =>
        (event === 'freeze' || event === 'visibilitychange'
          ? document
          : window
        ).dispatchEvent(new Event(event)),
      )
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
      expect(screen.getByTestId('a3-reader-status')).toHaveTextContent('已失效')
      if (event === 'visibilitychange') {
        vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
        act(() => document.dispatchEvent(new Event('visibilitychange')))
      }
      expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
    },
  )
  it('clears immediately on independent trust invalidation', async () => {
    const { complete, fixture } = await setup()
    await complete()
    act(() => fixture.invalidate())
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(screen.getByTestId('a3-reader-status')).toHaveTextContent('读取权限')
  })
  it.each(['session', 'logout'])(
    'clears after %s context change before paint',
    async (change) => {
      const { complete, rendered, tree } = await setup()
      await complete()
      rendered.rerender(
        tree(
          change === 'logout'
            ? { ...authValue, auth: null, status: 'unauthenticated' }
            : {
                ...authValue,
                auth: {
                  ...auth,
                  session: { ...auth.session, id: 'ses_replaced' },
                },
              },
        ),
      )
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    },
  )
  it('closes held content on route unmount and drops late replies', async () => {
    const { fixture, read } = await setup({ holdEnd: true })
    read()
    await waitFor(() => expect(fixture.held).toBe(true))
    fireEvent.click(screen.getByRole('link'))
    expect(screen.getByText('已离开变更页')).toBeVisible()
    expect(fixture.closed).toBe(1)
    await act(async () => fixture.release())
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
  })
  it.each([
    ['PATCH_TOO_LARGE', '超出完整读取上限'],
    ['PATCH_UNAVAILABLE_BINARY', '二进制文件'],
    ['PATCH_STALE', '已失效'],
    ['PATCH_REVOKED', '读取权限'],
    ['PATCH_UNAVAILABLE_ENCODING', '暂存内容暂不可用'],
  ])('shows actionable Chinese state for %s', async (errorCode, expected) => {
    const { read } = await setup({ errorCode })
    read()
    await waitFor(() =>
      expect(screen.getByTestId('a3-reader-status')).toHaveTextContent(
        expected,
      ),
    )
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
  })
})
