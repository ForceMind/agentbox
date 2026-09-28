import { describe, expect, it } from 'vitest'

import { visibleGitPath } from './visibleGitPath'

describe('Git display paths', () => {
  it('keeps ordinary Unicode but exposes controls and bidi formatting', () => {
    expect(visibleGitPath('src/模块.ts')).toBe('src/模块.ts')
    expect(visibleGitPath('a\nb\u202e.ts')).toBe('a\\u000ab\\u202e.ts')
  })
})
