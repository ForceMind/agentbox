import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { DIFF_VIEW_LIMITS, parseUnifiedDiff } from './unifiedDiff'

const headers =
  'diff --git a/f b/f\nindex 1111111..2222222 100644\n--- a/f\n+++ b/f\n'
const patch = (body: string) => headers + body
const example = patch('@@ -1,2 +1,2 @@ heading\n same\n-old\n+new\n')
function unified(text: string) {
  const result = parseUnifiedDiff(text)
  expect(result.kind).toBe('unified')
  if (result.kind !== 'unified') throw new Error('expected complete model')
  return result
}
function gitPatch(
  before: string | null,
  after: string | null,
  context = 3,
  name = 'f',
) {
  const dir = mkdtempSync(join(tmpdir(), 'agentbox-diff-'))
  const git = (...args: string[]) =>
    execFileSync('git', ['-C', dir, ...args], {
      encoding: 'utf8',
      env: {
        ...process.env,
        GIT_CONFIG_NOSYSTEM: '1',
        GIT_CONFIG_GLOBAL: '/dev/null',
      },
    })
  try {
    git('init', '-q')
    if (before !== null) {
      writeFileSync(join(dir, name), before)
      git('add', '--', name)
    }
    const tree = git('write-tree').trim()
    if (after !== null) writeFileSync(join(dir, name), after)
    else rmSync(join(dir, name))
    git('add', '-A', '--', name)
    return git(
      'diff',
      '--cached',
      '--no-ext-diff',
      '--no-textconv',
      '--no-renames',
      `--unified=${context}`,
      tree,
      '--',
      name,
    )
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

describe('bounded complete unified presentation grammar', () => {
  it('keeps every header, prefix and body character without reconstructing source', () => {
    const model = unified(example)
    expect(model.headers).toBe(headers)
    expect(model.hunks).toEqual([
      {
        header: '@@ -1,2 +1,2 @@ heading',
        rows: [
          { kind: 'context', oldLine: 1, newLine: 1, text: ' same' },
          { kind: 'deleted', oldLine: 2, newLine: null, text: '-old' },
          { kind: 'added', oldLine: null, newLine: 2, text: '+new' },
        ],
      },
    ])
  })
  it.each([
    ['added', null, '你好 🌍\nline two\n'],
    ['deleted', 'old\nline two\n', null],
    ['modified', 'old\nsame\n', 'new\nsame\n'],
    ['CRLF', 'before\r\n\t旧\r\n', 'after\r\n\t新\r\n'],
    ['no-final-newline', 'old', 'new'],
    ['add-no-final-newline', null, 'new'],
    ['delete-no-final-newline', 'old', null],
    ['empty-source', '', 'new\n'],
    ['empty-target', 'old\n', ''],
    ['blank-lines', '\nold\n', '\n\nnew\n'],
    ['dangerous', '<svg>old</svg>\n', '<img src=x onerror=alert(1)>\n'],
  ])('parses actual staged Git %s', (_name, before, after) => {
    const text = gitPatch(before, after)
    const model = unified(text)
    expect(
      model.headers +
        model.hunks
          .map(
            (hunk) =>
              hunk.header +
              '\n' +
              hunk.rows.map((row) => row.text + '\n').join(''),
          )
          .join(''),
    ).toBe(text)
  })
  it.each(['with space.txt', '中文.txt', 'quote".txt', 'tab\t.txt'])(
    'does not interpret actual quoted path %s as authority',
    (name) => {
      const text = gitPatch('old\n', 'new\n', 3, name)
      expect(unified(text).headers).toContain('diff --git ')
    },
  )
  it('keeps exact CR and EOF markers and never numbers markers', () => {
    const crlf = unified(gitPatch('before\r\n', 'after\r\n'))
    expect(crlf.hunks[0].rows[1].text).toBe('+after\r')
    const eof = unified(gitPatch('old', 'new'))
    expect(eof.hunks[0].rows.filter((row) => row.kind === 'marker')).toEqual([
      {
        kind: 'marker',
        oldLine: null,
        newLine: null,
        text: '\\ No newline at end of file',
      },
      {
        kind: 'marker',
        oldLine: null,
        newLine: null,
        text: '\\ No newline at end of file',
      },
    ])
  })
  it('uses actual multi-hunk old/new gaps and zero-count preceding-line coordinates', () => {
    const before = Array.from({ length: 30 }, (_, i) => `line ${i + 1}\n`).join(
      '',
    )
    const after =
      'inserted\n' +
      before.replace('line 20\n', '').replace('line 29\n', 'changed\n')
    const model = unified(gitPatch(before, after, 0))
    expect(model.hunks).toHaveLength(3)
    expect(model.hunks.map((hunk) => hunk.header)).toEqual([
      '@@ -0,0 +1 @@',
      '@@ -20 +20,0 @@ line 19',
      '@@ -29 +29 @@ line 28',
    ])
    expect(
      model.hunks[2].rows.map((row) => [row.oldLine, row.newLine]),
    ).toEqual([
      [29, null],
      [null, 29],
    ])
  })
  it.each([
    '',
    'plain legacy text\r\n🌍',
    headers,
    'diff --git a/f b/f\nnew file mode 100644\nindex 0000000..e69de29\n',
    'diff --git a/f b/f\nBinary files a/f and b/f differ\n',
    'diff --cc f\n@@@ -1 -1 +1 @@@\n',
    'diff --git a/f b/g\nsimilarity index 100%\nrename from f\nrename to g\n',
    example.slice(0, -1),
    example.replace('+new', '+new\0binary'),
    example + example,
    example.replace('index 1111111..2222222 100644', 'unknown header'),
    example.replace('+++ b/f', '+++ /dev/null'),
    example.replace('--- a/f', '--- /dev/null'),
    example.replace('diff --git a/f b/f', 'diff --git invalid'),
    example.replace('@@ -1,2 +1,2 @@', '@@ -01,2 +1,2 @@'),
    example.replace('@@ -1,2 +1,2 @@', '@@ -0,2 +1,2 @@'),
    example.replace('@@ -1,2 +1,2 @@', '@@ -1,2 +2,2 @@'),
    example.replace('@@ -1,2 +1,2 @@', '@@ -1,3 +1,2 @@'),
    example.replace('@@ -1,2 +1,2 @@', '@@ -1,1 +1,2 @@'),
    example.replace('@@ -1,2 +1,2 @@', '@@ -2147483647,2 +2147483647,2 @@'),
    patch('@@ -0,0 +0,0 @@\n'),
    patch('@@ -1 +1 @@\n same\n'),
    patch('@@ -1 +1 @@\n?old\n+new\n'),
    patch('@@ -1 +1 @@\n\\ No newline at end of file\n-old\n+new\n'),
    patch(
      '@@ -1 +1 @@\n-old\n\\ No newline at end of file\n\\ No newline at end of file\n+new\n',
    ),
    patch('@@ -1,2 +1 @@\n-old\n\\ No newline at end of file\n-again\n+new\n'),
    patch(
      '@@ -1 +1 @@\n-old\n+new\n\\ No newline at end of file\n@@ -3 +3 @@\n-x\n+y\n',
    ),
    example + '@@ -2 +2 @@\n-old\n+new\n',
    example + '@@ -4 +5 @@\n-old\n+new\n',
    example + '\n',
  ])('falls back wholly for unsupported/uncertain input %#', (text) => {
    expect(parseUnifiedDiff(text)).toEqual({ kind: 'raw', reason: 'format' })
  })
  it('accepts coordinate upper bound and rejects overflow/huge declarations', () => {
    expect(
      unified(patch('@@ -2147483647 +2147483647 @@\n-old\n+new\n')).hunks[0]
        .rows[0].oldLine,
    ).toBe(DIFF_VIEW_LIMITS.coordinate)
    expect(
      parseUnifiedDiff(patch('@@ -9999999999 +9999999999 @@\n-old\n+new\n'))
        .kind,
    ).toBe('raw')
  })
  it('rejects invented unchanged gaps on the /dev/null side', () => {
    const added = gitPatch(null, 'new\n')
    const deleted = gitPatch('old\n', null)
    expect(
      parseUnifiedDiff(added.replace('@@ -0,0 +1 @@', '@@ -7,0 +8 @@')),
    ).toEqual({ kind: 'raw', reason: 'format' })
    expect(
      parseUnifiedDiff(deleted.replace('@@ -1 +0,0 @@', '@@ -8 +7,0 @@')),
    ).toEqual({ kind: 'raw', reason: 'format' })
  })
  it.each([
    [null, ''],
    ['', null],
  ])(
    'uses raw for actual Git empty-file metadata without inventing an empty model',
    (before, after) => {
      expect(parseUnifiedDiff(gitPatch(before, after))).toEqual({
        kind: 'raw',
        reason: 'format',
      })
    },
  )
  it('bounds physical lines before building a row model', () => {
    const withLines = (count: number) =>
      patch(`@@ -0,0 +1,${count} @@\n` + '+\n'.repeat(count))
    expect(unified(withLines(3995)).hunks[0].rows).toHaveLength(3995)
    expect(parseUnifiedDiff(withLines(3996))).toEqual({
      kind: 'raw',
      reason: 'limit',
    })
  })
  it('bounds each physical line independently, including multibyte source', () => {
    expect(
      unified(patch('@@ -0,0 +1 @@\n+' + 'x'.repeat(8191) + '\n')).hunks[0]
        .rows[0].text,
    ).toHaveLength(8192)
    expect(
      parseUnifiedDiff(patch('@@ -0,0 +1 @@\n+' + 'x'.repeat(8192) + '\n')),
    ).toEqual({ kind: 'raw', reason: 'limit' })
  })
  it('bounds UTF-8 bytes at the exact inclusive boundary without mistaking units for bytes', () => {
    const base = patch(
      '@@ -0,0 +1,40 @@\n' + ('+' + 'x'.repeat(6400) + '\n').repeat(40),
    )
    const padding =
      DIFF_VIEW_LIMITS.bytes - new TextEncoder().encode(base).length
    const exact = base.replace('@@\n', '@@ ' + 'x'.repeat(padding - 1) + '\n')
    expect(new TextEncoder().encode(exact)).toHaveLength(DIFF_VIEW_LIMITS.bytes)
    unified(exact)
    expect(parseUnifiedDiff(exact.replace('@@ ', '@@ x'))).toEqual({
      kind: 'raw',
      reason: 'limit',
    })
    expect(parseUnifiedDiff(base.replaceAll('x', '界'))).toEqual({
      kind: 'raw',
      reason: 'limit',
    })
  })
  it('bounds hunk count and never returns an accepted prefix', () => {
    const hunks = (count: number) =>
      patch(
        Array.from(
          { length: count },
          (_, i) => `@@ -${i * 3 + 1} +${i * 3 + 1} @@\n-old\n+new\n`,
        ).join(''),
      )
    expect(unified(hunks(64)).hunks).toHaveLength(64)
    expect(parseUnifiedDiff(hunks(65))).toEqual({
      kind: 'raw',
      reason: 'limit',
    })
  })
})
