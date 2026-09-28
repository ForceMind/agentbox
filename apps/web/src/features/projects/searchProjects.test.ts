import { describe, expect, it } from 'vitest'

import type { ProjectData } from '../../lib/contracts'
import { searchProjects } from './searchProjects'

function project(
  id: string,
  name: string,
  slug = id,
  branch: string | null = null,
): ProjectData {
  return {
    id,
    display_name: name,
    slug,
    git: branch === null ? null : { branch },
    repository_url: 'https://example.invalid/private-canary',
  } as ProjectData
}

function ids(rows: readonly ProjectData[], query: string): string[] {
  return searchProjects(rows, query).map((row) => row.id)
}

describe('formal Project search', () => {
  const docs = project('docs', 'Docs redesign', 'design-docs', 'feature/ux')
  const payments = project(
    'payments',
    'Payments refactor',
    'payments',
    'feature/checkout',
  )

  it('keeps API order for empty queries and requires every term to match', () => {
    expect(ids([docs, payments], '  ')).toEqual(['docs', 'payments'])
    expect(ids([docs, payments], 'pay ref')).toEqual(['payments'])
    expect(ids([docs, payments], 'ref pay')).toEqual(['payments'])
    expect(ids([docs, payments], 'pay missing')).toEqual([])
  })

  it('matches visible title, slug and branch without searching hidden URLs', () => {
    expect(ids([docs, payments], 'checkout')).toEqual(['payments'])
    expect(ids([docs, payments], 'design-docs')).toEqual(['docs'])
    expect(ids([docs, payments], 'private-canary')).toEqual([])
    const hiddenBranch = project(
      'hidden',
      'Ordinary project',
      'ordinary',
      '功能/本地化',
    )
    expect(ids([hiddenBranch], '功能')).toEqual([])
  })

  it('ranks exact and readable word matches ahead of scattered matches', () => {
    const exact = project('exact', 'payments')
    const prefix = project('prefix', 'payments next')
    const embedded = project('embedded', 'nonpayments payments')
    expect(ids([embedded, prefix, exact], 'PAYMENTS')).toEqual([
      'exact',
      'prefix',
      'embedded',
    ])
    expect(ids([embedded], 'payments')).toEqual(['embedded'])
    expect(ids([docs], 'docrdes')).toEqual([])
  })

  it('supports Unicode names and preserves API order on equal scores', () => {
    const first = project('first', '账单 服务')
    const second = project('second', '账单 工具')
    expect(ids([second, first], '账单')).toEqual(['second', 'first'])
    expect(ids([second, first], '服务')).toEqual(['first'])
  })
})
