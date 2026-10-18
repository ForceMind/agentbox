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
    expect(splitFileNameFilterTokens('  SRC\u00a0\tTest\u3000中文\n')).toEqual([
      'src',
      'test',
      '中文',
    ])
    expect(splitFileNameFilterTokens(' \uFEFF ')).toEqual([])
  })

  it('matches every term within the same path, case-insensitively', () => {
    const terms = splitFileNameFilterTokens('src  File')
    expect(pathMatchesFileNameFilterTokens('src/deep/FILE.ts', terms)).toBe(true)
    expect(pathMatchesFileNameFilterTokens('other/file.ts', terms)).toBe(false)
    expect(pathMatchesFileNameFilterTokens('anything', [])).toBe(true)
  })

  it('matches rename sources, without joining tokens across unrelated paths', () => {
    const files = [
      { path: 'src/new.ts', previous_path: 'src/old.ts' },
      { path: 'src/example.ts', previous_path: null },
      { path: 'docs/file.md', previous_path: null },
    ] as const
    expect(filterChangedPaths(files, splitFileNameFilterTokens('old'))).toEqual([
      files[0],
    ])
    expect(filterChangedPaths(files, splitFileNameFilterTokens('src new'))).toEqual([
      files[0],
    ])
    expect(filterChangedPaths(files, splitFileNameFilterTokens('old example'))).toEqual([])
    expect(filterChangedPaths(files, [])).toEqual(files)
    expect(files).toHaveLength(3)
  })

  it('enforces Orca 2 KiB UTF-8 query limit for ASCII and multibyte text', () => {
    expect(FILE_NAME_FILTER_QUERY_MAX_BYTES).toBe(2048)
    expect(isFileNameFilterQueryTooLarge('a'.repeat(2048))).toBe(false)
    expect(isFileNameFilterQueryTooLarge('a'.repeat(2049))).toBe(true)
    expect(isFileNameFilterQueryTooLarge('中'.repeat(682))).toBe(false)
    expect(isFileNameFilterQueryTooLarge('中'.repeat(683))).toBe(true)
    expect(isFileNameFilterQueryTooLarge('😀'.repeat(513))).toBe(true)
  })
})
