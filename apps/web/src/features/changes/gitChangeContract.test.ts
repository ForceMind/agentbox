import { describe, expect, it } from 'vitest'

import { parseGitChangePageResponse } from '../../lib/contracts'

const valid = {
  api_version: 'v1',
  request_id: 'req_changes',
  data: {
    is_repository: true,
    files: [
      {
        path: 'src/模块.ts',
        previous_path: null,
        kind: 'modified',
        staged: false,
        unstaged: true,
      },
    ],
    total_count: 1,
    next_cursor: null,
  },
}

describe('Project Git Changes response', () => {
  it('accepts bounded Unicode path metadata without claiming file contents', () => {
    const page = parseGitChangePageResponse(valid)
    expect(page.data.files[0].path).toBe('src/模块.ts')
    expect(page.data.total_count).toBe(1)
    expect(JSON.stringify(page)).not.toContain('file_content')
  })

  it.each([
    { ...valid, data: { ...valid.data, file_content: 'SECRET-CANARY' } },
    {
      ...valid,
      data: {
        ...valid.data,
        files: [{ ...valid.data.files[0], path: '../escape' }],
      },
    },
    {
      ...valid,
      data: {
        ...valid.data,
        files: [valid.data.files[0], valid.data.files[0]],
      },
    },
    { ...valid, data: { ...valid.data, next_cursor: 'not-a-cursor' } },
    {
      ...valid,
      data: {
        ...valid.data,
        files: [{ ...valid.data.files[0], kind: 'renamed' }],
      },
    },
  ])('rejects unexpected content, paths and cursor shapes', (payload) => {
    expect(() => parseGitChangePageResponse(payload)).toThrow()
  })
})
