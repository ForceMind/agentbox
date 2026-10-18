import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useGitChanges } from '../features/changes/useGitChanges'
import type { Locale } from '../i18n'
import { ProjectChangesPage } from './ProjectChangesPage'

vi.mock('../features/changes/useGitChanges', () => ({ useGitChanges: vi.fn() }))

const refresh = vi.fn(async () => undefined)
const loadMore = vi.fn(async () => undefined)
const cursor = `${'a'.repeat(64)}:3`

function renderPage(locale: Locale = 'en') {
  return render(
    <MemoryRouter initialEntries={['/projects/prj_fixture/changes']}>
      <Routes>
        <Route
          element={<ProjectChangesPage locale={locale} />}
          path="/projects/:projectId/changes"
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  refresh.mockClear()
  loadMore.mockClear()
  vi.mocked(useGitChanges).mockReturnValue({
    files: [
      {
        path: 'zeta.ts',
        previous_path: null,
        kind: 'modified',
        staged: true,
        unstaged: false,
      },
      {
        path: 'src/b.ts',
        previous_path: 'src/old-b.ts',
        kind: 'renamed',
        staged: true,
        unstaged: false,
      },
      {
        path: 'src/a\u202e.ts',
        previous_path: null,
        kind: 'untracked',
        staged: false,
        unstaged: true,
      },
    ],
    totalCount: 5,
    nextCursor: cursor,
    isRepository: true,
    loading: false,
    loadingMore: false,
    stale: false,
    error: null,
    refresh,
    loadMore,
  })
})

describe('Project Changed Paths page', () => {
  it('renders real metadata in tree order without inventing line stats or file bodies', () => {
    renderPage()
    const folder = screen.getByRole('button', { name: 'Folder: src' })
    expect(folder).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('a\\u202e.ts')).toBeVisible()
    expect(screen.getByText('b.ts')).toBeVisible()
    expect(screen.getByText('zeta.ts')).toBeVisible()
    expect(screen.getByText('Showing 3 of 5 paths')).toBeVisible()
    expect(screen.getByText(/Paths and status only/)).toBeVisible()
    expect(screen.queryByText('0 additions')).toBeNull()
    expect(document.querySelector('script')).toBeNull()

    fireEvent.click(folder)
    expect(folder).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('b.ts')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Load more paths' }))
    expect(loadMore).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('filters loaded metadata including renamed file paths', () => {
    renderPage('en')
    const filter = screen.getByRole('searchbox', {
      name: 'Filter loaded paths',
    })
    fireEvent.change(filter, { target: { value: 'old-b' } })
    expect(screen.getByText('b.ts')).toBeVisible()
    expect(screen.queryByText('zeta.ts')).toBeNull()
    expect(screen.queryByText('a\\u202e.ts')).toBeNull()
    expect(screen.getByText('1 of 3 loaded paths match')).toBeVisible()
    expect(loadMore).not.toHaveBeenCalled()

    fireEvent.change(filter, { target: { value: 'missing' } })
    expect(screen.getByText('No loaded paths match this filter.')).toBeVisible()
    expect(screen.getByText('0 of 3 loaded paths match')).toBeVisible()

    fireEvent.change(filter, { target: { value: '' } })
    expect(screen.getByText('zeta.ts')).toBeVisible()
    expect(screen.queryByText('No loaded paths match this filter.')).toBeNull()
    expect(screen.getByText('Showing 3 of 5 paths')).toBeVisible()
  })

  it('expands filtered folders and rejects oversized paste', () => {
    renderPage('zh-CN')
    fireEvent.click(screen.getByRole('button', { name: '文件夹: src' }))
    expect(screen.queryByText('b.ts')).toBeNull()
    const filter = screen.getByRole('searchbox', { name: '筛选已加载的路径' })
    fireEvent.change(filter, { target: { value: 'src/b' } })
    expect(screen.getByText('b.ts')).toBeVisible()
    expect(filter).toHaveValue('src/b')
    fireEvent.change(filter, { target: { value: '中'.repeat(900) } })
    expect(filter).toHaveValue('src/b')
  })
})

// A3 uses an independently injected test-only port; the v1 metadata hook stays intact.
describe('Changes deliberate staged content view', () => {
  it.each([
    {
      locale: 'zh-CN' as const,
      heading: '暂存补丁（只读）',
      unavailable: '需要独立 A3',
      read: '读取暂存补丁：',
      warning:
        '源码可能含敏感信息。仅在明确点击后读取，不支持未暂存内容；不会自动读取或重试。',
    },
    {
      locale: 'en' as const,
      heading: 'Staged patch (read-only)',
      unavailable: 'independent A3',
      read: 'Read staged patch: ',
      warning: /Source code may contain sensitive information/,
    },
  ])(
    'keeps unconfigured $locale production composition clearly unavailable',
    ({ locale, heading, unavailable, read, warning }) => {
      renderPage(locale)
      expect(screen.getByRole('region', { name: heading })).toBeVisible()
      expect(screen.getByRole('heading', { name: heading })).toBeVisible()
      expect(screen.getByText(warning)).toBeVisible()
      expect(screen.getByTestId('a3-reader-status')).toHaveTextContent(
        unavailable,
      )
      expect(
        screen.getByRole('button', { name: `${read}zeta.ts` }),
      ).toBeDisabled()
      expect(
        screen.queryByRole('button', { name: `${read}src/b.ts` }),
      ).toBeNull()
      expect(
        screen.queryByRole('button', { name: `${read}src/a\\u202e.ts` }),
      ).toBeNull()
      expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    },
  )

  it('keeps hostile and invisible path characters exact inert labels', () => {
    const path = 'dir/<img src=x onerror=alert(1)>\n\t\u202e.ts'
    const previous = 'old/<svg onload=alert(1)>\u0000.ts'
    vi.mocked(useGitChanges).mockReturnValue({
      ...vi.mocked(useGitChanges)(undefined),
      files: [
        {
          path,
          previous_path: previous,
          kind: 'modified',
          staged: true,
          unstaged: false,
        },
      ],
      totalCount: 1,
      nextCursor: null,
    })
    renderPage('en')
    expect(
      screen.getByText('<img src=x onerror=alert(1)>\\u000a\\u0009\\u202e.ts')
        .textContent,
    ).toBe('<img src=x onerror=alert(1)>\\u000a\\u0009\\u202e.ts')
    expect(
      screen.getByText('old/<svg onload=alert(1)>\\u0000.ts').textContent,
    ).toBe('old/<svg onload=alert(1)>\\u0000.ts')
    expect(
      screen.getByRole('button', {
        name: 'Read staged patch: dir/<img src=x onerror=alert(1)>\\u000a\\u0009\\u202e.ts',
      }),
    ).toBeDisabled()
    expect(
      document.querySelector('img, script, iframe, svg[onload], [onerror]'),
    ).toBeNull()
  })
})
