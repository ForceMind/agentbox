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
import type { Locale } from '../i18n'
import { ProjectChangesPage } from './ProjectChangesPage'

vi.mock('../features/changes/useGitChanges', () => ({ useGitChanges: vi.fn() }))
beforeAll(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
const refresh = vi.fn(async () => undefined)
const loadMore = vi.fn(async () => undefined)
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
  loadMore.mockClear()
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
    loadMore,
  })
})
async function setup({
  locale = 'zh-CN',
  trustAvailable = true,
  ...options
}: NonNullable<Parameters<typeof createA3TestFixture>[0]> & {
  locale?: Locale
  trustAvailable?: boolean
} = {}) {
  const fixture = await createA3TestFixture(options)
  if (!trustAvailable)
    vi.spyOn(fixture.deps.trust, 'current').mockReturnValue(null)
  const tree = (value = authValue, selectedLocale: Locale = locale) => (
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[`/projects/${a3TestProject}/changes`]}>
        <Routes>
          <Route
            element={
              <ProjectChangesPage
                locale={selectedLocale}
                a3Dependencies={fixture.deps}
              />
            }
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
      screen.getByRole('button', {
        name:
          locale === 'zh-CN'
            ? '读取暂存补丁：success.txt'
            : 'Read staged patch: success.txt',
      }),
    )
  const complete = async () => {
    read()
    await screen.findByTestId('a3-complete-patch')
  }
  return { fixture, rendered, tree, read, complete }
}
describe('A3 page lifecycle and inert React rendering', () => {
  const unifiedSource =
    'diff --git a/success.txt b/success.txt\nindex 1111111..2222222 100644\n--- a/success.txt\n+++ b/success.txt\n@@ -1 +1 @@\n-old\r\n+<svg onload=alert(1)>新 🌍\r\n'
  it.each([
    'clear',
    'refresh',
    'freeze',
    'pagehide',
    'offline',
    'visibilitychange',
    'trust',
    'auth-epoch',
    'expiry',
    'route',
    'session',
  ])(
    'destroys the active unified model and raw controls on %s without replay',
    async (event) => {
      const { complete, fixture, rendered, tree } = await setup({
        patch: unifiedSource,
      })
      await complete()
      expect(screen.getByTestId('unified-diff-table')).toBeVisible()
      fireEvent.click(screen.getByRole('button', { name: '原文' }))
      expect(screen.getByTestId('a3-complete-patch').textContent).toBe(
        unifiedSource,
      )
      fireEvent.click(screen.getByRole('button', { name: '统一视图' }))
      expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
      if (event === 'clear')
        fireEvent.click(screen.getByRole('button', { name: '清除内容' }))
      else if (event === 'refresh')
        fireEvent.click(screen.getByRole('button', { name: '刷新' }))
      else if (event === 'route') fireEvent.click(screen.getByRole('link'))
      else if (event === 'trust') act(() => fixture.invalidate())
      else if (event === 'auth-epoch')
        act(() =>
          fixture.invalidate({
            binding: { ...fixture.binding, auth_epoch: '2' },
          }),
        )
      else if (event === 'expiry') {
        act(() => fixture.now(31_001))
        await waitFor(() =>
          expect(screen.queryByTestId('a3-complete-patch')).toBeNull(),
        )
      } else if (event === 'session')
        rendered.rerender(
          tree({
            ...authValue,
            auth: { ...auth, session: { ...auth.session, id: 'ses_next' } },
          }),
        )
      else {
        if (event === 'visibilitychange')
          vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
        act(() =>
          (event === 'freeze' || event === 'visibilitychange'
            ? document
            : window
          ).dispatchEvent(new Event(event)),
        )
      }
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
      expect(screen.queryByTestId('unified-diff-table')).toBeNull()
      expect(screen.queryByRole('button', { name: '原文' })).toBeNull()
      expect(document.body.textContent).not.toContain('onload')
      expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
    },
  )
  it('starts a fresh completed owner with default unified/wrap preferences after clear', async () => {
    const { complete, fixture } = await setup({ patch: unifiedSource })
    await complete()
    fireEvent.click(screen.getByRole('button', { name: '原文' }))
    fireEvent.click(screen.getByRole('checkbox', { name: '换行显示' }))
    fireEvent.click(screen.getByRole('button', { name: '清除内容' }))
    await complete()
    expect(screen.getByTestId('unified-diff-table')).toBeVisible()
    expect(screen.getByRole('checkbox', { name: '换行显示' })).toBeChecked()
    expect(fixture.deps.observe).toHaveBeenCalledTimes(2)
  })
  it('keeps one read and the original authenticated deadline through locale, raw, wrap and folder changes', async () => {
    const metadata = vi.mocked(useGitChanges)(undefined)
    vi.mocked(useGitChanges).mockReturnValue({
      ...metadata,
      files: [
        ...metadata.files,
        {
          path: 'group/other.ts',
          previous_path: null,
          kind: 'modified',
          staged: false,
          unstaged: true,
        },
      ],
      totalCount: 2,
    })
    const { complete, fixture, rendered, tree } = await setup({
      patch: unifiedSource,
      lifetime: 1200,
    })
    await complete()
    act(() => fixture.now(2199))
    fireEvent.click(screen.getByRole('button', { name: '原文' }))
    fireEvent.click(screen.getByRole('checkbox', { name: '换行显示' }))
    fireEvent.click(screen.getByRole('button', { name: '文件夹: group' }))
    rendered.rerender(tree(authValue, 'en'))
    const raw = screen.getByLabelText('Complete staged patch: raw text')
    expect(raw.textContent).toBe(unifiedSource)
    expect(raw).toHaveClass('diff-no-wrap')
    expect(screen.getByRole('button', { name: 'Raw text' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(
      screen.getByRole('checkbox', { name: 'Wrap lines' }),
    ).not.toBeChecked()
    expect(
      screen.getByRole('button', { name: 'Folder: group' }),
    ).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Unified view' }))
    fireEvent.click(screen.getByRole('button', { name: 'Folder: group' }))
    act(() => window.dispatchEvent(new Event('resize')))
    expect(screen.getByTestId('unified-diff-table')).toBeVisible()
    expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
    expect(fixture.deps.open).toHaveBeenCalledTimes(1)
    act(() => fixture.now(2200))
    await waitFor(() =>
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull(),
    )
    expect(screen.queryByRole('button', { name: 'Raw text' })).toBeNull()
    expect(document.body.textContent).not.toContain('onload')
    expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
    expect(fixture.deps.open).toHaveBeenCalledTimes(1)
  })
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
    fireEvent.click(screen.getByRole('button', { name: '刷新' }))
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
  })
  it('clears completed content before loading more metadata and never replays it', async () => {
    vi.mocked(useGitChanges).mockReturnValue({
      ...vi.mocked(useGitChanges)(undefined),
      nextCursor: `${'a'.repeat(64)}:1`,
      totalCount: 2,
    })
    const { fixture, complete, rendered, tree } = await setup({
      patch: unifiedSource,
    })
    await complete()
    fireEvent.click(screen.getByRole('button', { name: '加载更多路径' }))
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(screen.queryByTestId('unified-diff-table')).toBeNull()
    expect(screen.queryByRole('checkbox', { name: '换行显示' })).toBeNull()
    expect(document.body.textContent).not.toContain('onload')
    expect(loadMore).toHaveBeenCalledTimes(1)
    rendered.rerender(tree())
    expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
    expect(fixture.deps.open).toHaveBeenCalledTimes(1)
  })
  it('replaces a pending selection and ignores its late observation without losing the new completed owner', async () => {
    const metadata = vi.mocked(useGitChanges)(undefined)
    vi.mocked(useGitChanges).mockReturnValue({
      ...metadata,
      files: [
        ...metadata.files,
        {
          path: 'next.txt',
          previous_path: null,
          kind: 'modified',
          staged: true,
          unstaged: false,
        },
      ],
      totalCount: 2,
    })
    const { fixture, read } = await setup({ patch: unifiedSource })
    const initialObservation = fixture.observation()
    let releaseInitial!: (value: unknown) => void
    vi.mocked(fixture.deps.observe)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            releaseInitial = resolve
          }),
      )
      .mockImplementationOnce(async () => {
        const observed = fixture.observation()
        return {
          ...observed,
          entries: observed.entries.map((entry) => ({
            ...entry,
            path: 'next.txt',
          })),
        }
      })
    read()
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(fixture.deps.open).not.toHaveBeenCalled()
    const initialSignal = vi.mocked(fixture.deps.observe).mock.calls[0][1]
    fireEvent.click(
      screen.getByRole('button', { name: '读取暂存补丁：next.txt' }),
    )
    expect(initialSignal.aborted).toBe(true)
    await screen.findByTestId('unified-diff-table')
    const completed = screen.getByTestId('a3-complete-patch')
    await act(async () => releaseInitial(initialObservation))
    expect(screen.getByTestId('a3-complete-patch')).toBe(completed)
    expect(
      screen.getByRole('region', { name: '暂存补丁（只读）' }),
    ).toHaveTextContent('next.txt')
    expect(fixture.deps.observe).toHaveBeenCalledTimes(2)
    expect(fixture.deps.open).toHaveBeenCalledTimes(1)
    expect(fixture.requests[0]).not.toHaveProperty('path')
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
  it.each(['session', 'logout', 'csrf-token'])(
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
                  ...(change === 'csrf-token'
                    ? { csrf_token: 'synthetic-unit-replaced' }
                    : { session: { ...auth.session, id: 'ses_replaced' } }),
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

const readerLocales = [
  {
    locale: 'zh-CN' as const,
    heading: '暂存补丁（只读）',
    metadata: '路径与状态',
    read: '读取暂存补丁：',
    empty: '尚未读取内容。请明确选择一个已暂存的新增、修改或删除文件。',
    loading: '正在验证身份并读取完整暂存补丁，可随时取消。',
    completed: '完整暂存补丁已验证。内容仅作文本显示，到期或离开页面后清除。',
    unavailable:
      '暂存内容暂不可用。需要独立 A3 内容连接和可信凭据；仍可查看路径与状态。',
    failed: '完整性验证或连接失败，内容已清除。请刷新后重新选择文件。',
    warning:
      '源码可能含敏感信息。仅在明确点击后读取，不支持未暂存内容；不会自动读取或重试。',
    cancel: '取消读取',
    clear: '清除内容',
    time: '浏览器读取完成时间：',
    timeMeaning: '非仓库观察时间',
    formatFallback: '此补丁格式不支持统一视图，已显示完整原文，未截断。',
  },
  {
    locale: 'en' as const,
    heading: 'Staged patch (read-only)',
    metadata: 'Path metadata',
    read: 'Read staged patch: ',
    empty:
      'No content has been read. Explicitly select a staged added, modified or deleted file.',
    loading:
      'Verifying identity and reading the complete staged patch. You can cancel at any time.',
    completed:
      'The complete staged patch has been verified. It is displayed as text only and cleared when it expires or you leave the page.',
    unavailable:
      'Staged content is unavailable. An independent A3 content connection and trusted credentials are required. Paths and status remain available.',
    failed:
      'Integrity verification or the connection failed. Content has been cleared. Refresh and select a file again.',
    warning:
      'Source code may contain sensitive information. Reading starts only after an explicit click and supports staged content only. Reads and retries are never automatic.',
    cancel: 'Cancel read',
    clear: 'Clear content',
    time: 'Browser read completed: ',
    timeMeaning: 'not repository observation time',
    formatFallback:
      'This patch format is not supported by the unified view. The complete original text is shown without truncation.',
  },
]
describe.each(readerLocales)(
  'localized A3 ownership and readable states ($locale)',
  (copy) => {
    it('names the deliberate loading/completed controls and identifies browser completion time honestly', async () => {
      const browserCompletedAt = 1700000123456
      vi.spyOn(Date, 'now').mockReturnValue(browserCompletedAt)
      const { fixture, read } = await setup({
        locale: copy.locale,
        holdEnd: true,
      })
      expect(screen.getByRole('heading', { name: copy.metadata })).toBeVisible()
      expect(screen.getByRole('region', { name: copy.heading })).toBeVisible()
      expect(screen.getByText(copy.warning)).toBeVisible()
      const status = screen.getByTestId('a3-reader-status')
      expect(status).toHaveAttribute('role', 'status')
      expect(status).toHaveAttribute('aria-live', 'polite')
      expect(status.textContent).toBe(copy.empty)
      expect(fixture.deps.observe).not.toHaveBeenCalled()
      read()
      await waitFor(() => expect(fixture.held).toBe(true))
      expect(status.textContent).toBe(copy.loading)
      expect(screen.getByRole('button', { name: copy.cancel })).toBeEnabled()
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
      expect(screen.queryByText(new RegExp(copy.time))).toBeNull()
      await act(async () => fixture.release())
      const patch = await screen.findByTestId('a3-complete-patch')
      expect(status.textContent).toBe(copy.completed)
      expect(screen.queryByRole('button', { name: copy.cancel })).toBeNull()
      expect(screen.getByText(copy.formatFallback)).toBeVisible()
      expect(patch.textContent).toBe(a3DangerousPatch)
      expect(patch.querySelector('img,script,a,svg,iframe')).toBeNull()
      const time = screen.getByText(new RegExp(copy.time))
      expect(time).toHaveTextContent(
        new Date(browserCompletedAt).toLocaleString(copy.locale),
      )
      expect(time).toHaveTextContent(copy.timeMeaning)
      expect(time.textContent).not.toContain(
        new Date(1791111111111).toLocaleString(copy.locale),
      )
      fireEvent.click(screen.getByRole('button', { name: copy.clear }))
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
      expect(screen.queryByText(new RegExp(copy.time))).toBeNull()
      expect(document.body.textContent).not.toContain('onerror')
      expect(status.textContent).toBe(copy.empty)
      expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
      expect(fixture.deps.open).toHaveBeenCalledTimes(1)
    })
    it('keeps a present adapter unavailable when its independent trust is missing', async () => {
      const { fixture, read } = await setup({
        locale: copy.locale,
        trustAvailable: false,
      })
      expect(screen.getByTestId('a3-reader-status').textContent).toBe(
        copy.unavailable,
      )
      expect(
        screen.getByRole('button', { name: `${copy.read}success.txt` }),
      ).toBeDisabled()
      read()
      expect(fixture.deps.observe).not.toHaveBeenCalled()
      expect(fixture.deps.open).not.toHaveBeenCalled()
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    })
    it('never exposes a read for non-staged or non-add/modify/delete rows', async () => {
      const metadata = vi.mocked(useGitChanges)(undefined)
      const unsupported = [
        ...(['added', 'modified', 'deleted'] as const).map((kind) => ({
          path: `unstaged-${kind}.txt`,
          previous_path: null,
          kind,
          staged: false,
          unstaged: true,
        })),
        ...(
          [
            'renamed',
            'copied',
            'untracked',
            'conflicted',
            'typechanged',
          ] as const
        ).map((kind) => ({
          path: `${kind}.txt`,
          previous_path: null,
          kind,
          staged: true,
          unstaged: false,
        })),
      ]
      vi.mocked(useGitChanges).mockReturnValue({
        ...metadata,
        files: [...metadata.files, ...unsupported],
        totalCount: unsupported.length + 1,
      })
      const { fixture } = await setup({ locale: copy.locale })
      expect(
        screen.getByRole('button', { name: `${copy.read}success.txt` }),
      ).toBeEnabled()
      for (const row of unsupported) {
        expect(
          screen.queryByRole('button', { name: `${copy.read}${row.path}` }),
        ).toBeNull()
        fireEvent.click(screen.getByText(row.path))
        fireEvent.mouseEnter(screen.getByText(row.path))
      }
      expect(fixture.deps.observe).not.toHaveBeenCalled()
      expect(fixture.deps.open).not.toHaveBeenCalled()
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    })
    it('labels failed integrity without ever showing partial content or retrying', async () => {
      const { fixture, read } = await setup({
        locale: copy.locale,
        malformed: true,
      })
      read()
      await waitFor(() =>
        expect(screen.getByTestId('a3-reader-status').textContent).toBe(
          copy.failed,
        ),
      )
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
      expect(screen.queryByRole('button', { name: copy.cancel })).toBeNull()
      expect(screen.queryByRole('button', { name: copy.clear })).toBeNull()
      expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
      expect(fixture.deps.open).toHaveBeenCalledTimes(1)
    })
  },
)

it.each([
  [
    'PATCH_TOO_LARGE',
    'The patch exceeds the complete-read limit. No partial content is shown. Select a smaller staged change.',
  ],
  [
    'PATCH_UNAVAILABLE_BINARY',
    'This is a binary file. Text patches are not supported for it. Select a text file.',
  ],
  [
    'PATCH_STALE',
    'This read is no longer current and its content has been cleared. Refresh the page and select a file again.',
  ],
  [
    'PATCH_REVOKED',
    'Read permission or trusted credentials are no longer valid. Content has been cleared. Reload the page and verify access before trying again.',
  ],
  [
    'PATCH_UNAVAILABLE_ENCODING',
    'Staged content is unavailable. An independent A3 content connection and trusted credentials are required. Paths and status remain available.',
  ],
])('shows actionable English state for %s', async (errorCode, expected) => {
  const { read, fixture } = await setup({ locale: 'en', errorCode })
  read()
  await waitFor(() =>
    expect(screen.getByTestId('a3-reader-status').textContent).toBe(expected),
  )
  expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Clear content' })).toBeNull()
  expect(fixture.deps.observe).toHaveBeenCalledTimes(1)
  expect(fixture.deps.open).toHaveBeenCalledTimes(1)
})
