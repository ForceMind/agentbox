import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useGitChanges } from '../features/changes/useGitChanges'
import { ProjectChangesPage } from './ProjectChangesPage'

vi.mock('../features/changes/useGitChanges', () => ({ useGitChanges: vi.fn() }))

const refresh = vi.fn(async () => undefined)
const loadMore = vi.fn(async () => undefined)
const cursor = `${'a'.repeat(64)}:3`

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/prj_fixture/changes']}>
      <Routes>
        <Route
          element={<ProjectChangesPage locale="en" />}
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
})

// A3 uses an independently injected test-only port; the v1 metadata hook stays intact.
describe('Changes deliberate staged content view', () => {
  it('keeps default production composition clearly unavailable', () => {
    renderPage()
    expect(screen.getByTestId('a3-reader-status')).toHaveTextContent(
      '需要独立 A3',
    )
    expect(
      screen.getByRole('button', { name: '读取暂存补丁：zeta.ts' }),
    ).toBeDisabled()
    expect(
      screen.queryByRole('button', { name: /读取暂存补丁：src\/b/ }),
    ).toBeNull()
    expect(
      screen.queryByRole('button', { name: /读取暂存补丁：src\/a/ }),
    ).toBeNull()
  })
})
