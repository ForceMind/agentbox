// Presentation only. This grammar cannot authenticate paths, objects or positions.
// No I/O, persistent cache or normalization of the owner's original text.
export const DIFF_VIEW_LIMITS = Object.freeze({
  bytes: 256 * 1024,
  lines: 4000,
  hunks: 64,
  lineUnits: 8192,
  coordinate: 2147483647,
})

export type DiffRow = {
  kind: 'context' | 'added' | 'deleted' | 'marker'
  oldLine: number | null
  newLine: number | null
  text: string
}
export type DiffHunk = { header: string; rows: DiffRow[] }
export type DiffView =
  | { kind: 'unified'; headers: string; hunks: DiffHunk[] }
  | { kind: 'raw'; reason: 'format' | 'limit' }

const raw = { kind: 'raw', reason: 'format' } as const
const limited = { kind: 'raw', reason: 'limit' } as const
const decimal = '(0|[1-9][0-9]{0,9})'
const hunkPattern = new RegExp(
  `^@@ -${decimal}(?:,${decimal})? \\+${decimal}(?:,${decimal})? @@(?: .*)?$`,
)
const mode = '[0-7]{6}'
const metadataPattern = new RegExp(
  `^(?:(?:new file mode|deleted file mode) ${mode}\\n|old mode ${mode}\\nnew mode ${mode}\\n)?index [0-9a-f]{4,64}\\.\\.[0-9a-f]{4,64}(?: ${mode})?\\n$`,
)

export function parseUnifiedDiff(text: string): DiffView {
  // Check code units first, so UTF-8 allocation itself is bounded.
  if (
    text.length > DIFF_VIEW_LIMITS.bytes ||
    new TextEncoder().encode(text).length > DIFF_VIEW_LIMITS.bytes
  )
    return limited
  if (text.includes('\0')) return raw
  const lines = text.split('\n')
  if (lines.at(-1) === '') lines.pop()
  if (
    lines.length > DIFF_VIEW_LIMITS.lines ||
    lines.some((line) => line.length > DIFF_VIEW_LIMITS.lineUnits)
  )
    return limited
  if (
    !text.endsWith('\n') ||
    !/^diff --git (?:a\/.+|"a\/.+") (?:b\/.+|"b\/.+")$/.test(lines[0] ?? '')
  )
    return raw

  const oldHeader = lines.findIndex((line) => line.startsWith('--- '))
  if (
    oldHeader < 2 ||
    !metadataPattern.test(lines.slice(1, oldHeader).join('\n') + '\n') ||
    !/^--- (?:a\/.+|"a\/.+"|\/dev\/null)$/.test(lines[oldHeader]) ||
    !/^\+\+\+ (?:b\/.+|"b\/.+"|\/dev\/null)$/.test(lines[oldHeader + 1] ?? '')
  )
    return raw
  const addedFile = lines[1].startsWith('new file mode ')
  const deletedFile = lines[1].startsWith('deleted file mode ')
  if (
    (lines[oldHeader] === '--- /dev/null') !== addedFile ||
    (lines[oldHeader + 1] === '+++ /dev/null') !== deletedFile
  )
    return raw

  const hunks: DiffHunk[] = []
  let cursor = oldHeader + 2
  let oldEnd = 0
  let newEnd = 0
  let oldEof = false
  let newEof = false
  while (cursor < lines.length) {
    if (hunks.length === DIFF_VIEW_LIMITS.hunks) return limited
    const header = lines[cursor++]
    const match = hunkPattern.exec(header)
    if (!match) return raw
    const oldStart = Number(match[1])
    const oldCount = Number(match[2] ?? 1)
    const newStart = Number(match[3])
    const newCount = Number(match[4] ?? 1)
    const oldBefore = oldCount === 0 ? oldStart : oldStart - 1
    const newBefore = newCount === 0 ? newStart : newStart - 1
    if (
      (oldEof && oldBefore !== oldEnd) ||
      (newEof && newBefore !== newEnd) ||
      oldBefore < oldEnd ||
      newBefore < newEnd ||
      oldBefore - oldEnd !== newBefore - newEnd ||
      oldBefore + oldCount > DIFF_VIEW_LIMITS.coordinate ||
      newBefore + newCount > DIFF_VIEW_LIMITS.coordinate ||
      oldCount + newCount === 0 ||
      (addedFile && (oldCount !== 0 || oldStart !== 0)) ||
      (deletedFile && (newCount !== 0 || newStart !== 0))
    )
      return raw
    let oldUsed = 0
    let newUsed = 0
    let changed = false
    const rows: DiffRow[] = []
    while (cursor < lines.length && !lines[cursor].startsWith('@@')) {
      const line = lines[cursor++]
      const previous = rows.at(-1)
      if (line === '\\ No newline at end of file') {
        if (!previous || previous.kind === 'marker') return raw
        if (previous.oldLine !== null) oldEof = true
        if (previous.newLine !== null) newEof = true
        rows.push({ kind: 'marker', oldLine: null, newLine: null, text: line })
        continue
      }
      const kind =
        line[0] === ' '
          ? 'context'
          : line[0] === '+'
            ? 'added'
            : line[0] === '-'
              ? 'deleted'
              : null
      if (!kind) return raw
      const consumesOld = kind !== 'added'
      const consumesNew = kind !== 'deleted'
      if (
        (consumesOld && (oldEof || oldUsed >= oldCount)) ||
        (consumesNew && (newEof || newUsed >= newCount))
      )
        return raw
      rows.push({
        kind,
        oldLine: consumesOld ? oldStart + oldUsed++ : null,
        newLine: consumesNew ? newStart + newUsed++ : null,
        text: line,
      })
      if (kind !== 'context') changed = true
    }
    if (!changed || oldUsed !== oldCount || newUsed !== newCount) return raw
    oldEnd = oldBefore + oldCount
    newEnd = newBefore + newCount
    hunks.push({ header, rows })
  }
  return hunks.length
    ? {
        kind: 'unified',
        headers: lines.slice(0, oldHeader + 2).join('\n') + '\n',
        hunks,
      }
    : raw
}
