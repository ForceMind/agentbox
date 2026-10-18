// Orca tokenization plus AgentBox loaded-path/rename semantics.
import { describe, expect, it } from 'vitest'
import {
  FILE_NAME_FILTER_QUERY_MAX_BYTES,
  filterChangedPaths,
  isFileNameFilterQueryTooLarge,
  pathMatchesFileNameFilterTokens,
  splitFileNameFilterTokens,
} from './fileNameFilter'

describe('Orca filename filter in Changes', () => {
  it('tokenizes ordinary and Unicode whitespace without empty tokens', () => {
    const tokens = splitFileNameFilterTokens('  SRC\u00a0\tTest\u3000中文\n')
    expect(tokens).toEqual(['src', 'test', '中文'])
    expect(splitFileNameFilterTokens(' \uFEFF ')).toEqual([])
  })

  it('matches every term within the same path, case-insensitively', () => {
    const terms = splitFileNameFilterTokens('src  File')
    const matches = (path: string) => pathMatchesFileNameFilterTokens(path, terms)
    expect(matches('src/deep/FILE.ts')).toBe(true)
    expect(matches('other/file.ts')).toBe(false)
    expect(pathMatchesFileNameFilterTokens('anything', [])).toBe(true)
  })

  it('matches rename sources without mixed-path tokens', () => {
    const files = [
      { path: 'src/new.ts', previous_path: 'src/old.ts' },
      { path: 'src/example.ts', previous_path: null },
      { path: 'docs/file.md', previous_path: null },
    ] as const
    const find = (query: string) =>
      filterChangedPaths(files, splitFileNameFilterTokens(query))
    expect(find('old')).toEqual([files[0]])
    expect(find('src new')).toEqual([files[0]])
    expect(find('old example')).toEqual([])
    expect(filterChangedPaths(files, [])).toEqual(files)
    expect(files).toHaveLength(3)
  })

  it('enforces the 2 KiB UTF-8 limit for text inputs', () => {
    expect(FILE_NAME_FILTER_QUERY_MAX_BYTES).toBe(2048)
    expect(isFileNameFilterQueryTooLarge('a'.repeat(2048))).toBe(false)
    expect(isFileNameFilterQueryTooLarge('a'.repeat(2049))).toBe(true)
    expect(isFileNameFilterQueryTooLarge('中'.repeat(682))).toBe(false)
    expect(isFileNameFilterQueryTooLarge('中'.repeat(683))).toBe(true)
    expect(isFileNameFilterQueryTooLarge('😀'.repeat(513))).toBe(true)
  })
})
