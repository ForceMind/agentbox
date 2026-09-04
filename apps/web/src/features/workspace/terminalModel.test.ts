import { describe, expect, it } from 'vitest'

import {
  TERMINAL_MODEL_LIMITS,
  TerminalModel,
  TerminalModelError,
  type TerminalProjection,
} from './terminalModel'
import type { TerminalToken } from './terminalTokenizer'
import {
  TERMINAL_COMBINING_RANGES,
  TERMINAL_DEFAULT_IGNORABLE_RANGES,
  TERMINAL_EMOJI_MODIFIER_BASE_RANGES,
  TERMINAL_EMOJI_MODIFIER_RANGES,
  TERMINAL_HANGUL_L_RANGES,
  TERMINAL_HANGUL_LV_RANGES,
  TERMINAL_HANGUL_LVT_RANGES,
  TERMINAL_HANGUL_T_RANGES,
  TERMINAL_HANGUL_V_RANGES,
  TERMINAL_UNICODE_SOURCES,
  TERMINAL_UNICODE_RANGE_SHA256,
  TERMINAL_UNICODE_VERSION,
  TERMINAL_WIDE_RANGES,
} from './terminalUnicodeWidthData'
import { terminalScalarWidth } from './terminalUnicodeWidth'

const text = (value: string): TerminalToken => ({ kind: 'text', text: value })
const control = (
  value: Extract<TerminalToken, { kind: 'control' }>['control'],
): TerminalToken => ({ kind: 'control', control: value })
const csi = (
  final: Extract<TerminalToken, { kind: 'csi' }>['final'],
  parameters = '',
): TerminalToken => ({ kind: 'csi', final, parameters })

let lineCeilingClock = 0

function projectedText(projection: TerminalProjection, row: number): string {
  const line = projection.lines[row]
  const cells = Array<string>(projection.columns).fill(' ')
  for (const run of line.runs) cells[run.column] = run.text
  return cells.join('').trimEnd()
}

function drainMaintenance(model: TerminalModel): void {
  while (model.hasPendingMaintenance) {
    const task = model.runMaintenanceTask(() => 0, Number.MAX_SAFE_INTEGER)
    expect(task.complete).toBe(true)
  }
}

function finishApplyWithinDeadline(
  model: TerminalModel,
  tokens: readonly TerminalToken[],
): number {
  let now = 0
  const clock = () => {
    const value = now
    now += 0.02
    return value
  }
  model.beginApplyTokens(tokens)
  let callbacks = 0
  for (; callbacks < 10_000; callbacks++) {
    const before = now
    const task = model.runApplyTask(clock, before + 5)
    expect(now - before).toBeLessThanOrEqual(5.05)
    if (task.complete) return callbacks + 1
  }
  throw new Error('APPLY_DID_NOT_COMPLETE')
}

function drainMaintenanceWithinDeadline(model: TerminalModel): number {
  let now = lineCeilingClock
  const clock = () => {
    const value = now
    now += 0.02
    return value
  }
  let callbacks = 0
  while (model.hasPendingMaintenance && callbacks < 10_000) {
    const before = now
    model.runMaintenanceTask(clock, before + 5)
    lineCeilingClock = now
    expect(now - before).toBeLessThanOrEqual(5.05)
    callbacks++
  }
  expect(model.hasPendingMaintenance).toBe(false)
  return callbacks
}

function beginOneApplyStep(
  model: TerminalModel,
  tokens: readonly TerminalToken[],
): void {
  let now = lineCeilingClock
  const clock = () => {
    const value = now
    now += 2.5
    return value
  }
  model.beginApplyTokens(tokens)
  const task = model.runApplyTask(clock, now + 5)
  lineCeilingClock = now
  expect(task.complete).toBe(false)
}

function finishApplyWithinLineCeiling(
  model: TerminalModel,
  tokens: readonly TerminalToken[],
): void {
  let now = lineCeilingClock
  const clock = () => {
    const value = now
    now += 0.02
    return value
  }
  model.beginApplyTokens(tokens)
  for (let callbacks = 0; callbacks < 20_000; callbacks++) {
    const before = now
    const task = model.runApplyTask(clock, before + 5)
    lineCeilingClock = now
    expect(now - before).toBeLessThanOrEqual(5.05)
    expect(model.effectiveRetainedLogicalLines).toBeLessThanOrEqual(
      TERMINAL_MODEL_LIMITS.logicalLines,
    )
    if (task.complete) {
      expect(task.result?.state).toBe('active')
      return
    }
  }
  throw new Error('LINE_CEILING_APPLY_DID_NOT_COMPLETE')
}

function fillHistoryTo(model: TerminalModel, lineFeeds: number): void {
  model.applyTokens(
    Array.from({ length: lineFeeds }, () => [
      text('x'),
      control('LF'),
      control('CR'),
    ]).flat(),
  )
}

describe('fixed Unicode terminal width', () => {
  it('pins a reviewable UCD version and canonical range digest', () => {
    expect(TERMINAL_UNICODE_VERSION).toBe('13.0.0')
    expect(TERMINAL_UNICODE_RANGE_SHA256).toMatch(/^[a-f0-9]{64}$/)
    expect(Object.isFrozen(TERMINAL_COMBINING_RANGES)).toBe(true)
    expect(Object.isFrozen(TERMINAL_COMBINING_RANGES[0])).toBe(true)
    expect(Object.isFrozen(TERMINAL_WIDE_RANGES)).toBe(true)
    expect(Object.isFrozen(TERMINAL_WIDE_RANGES[0])).toBe(true)
    expect(Object.isFrozen(TERMINAL_UNICODE_SOURCES)).toBe(true)
    expect(TERMINAL_UNICODE_SOURCES).toHaveLength(6)
    expect(TERMINAL_UNICODE_SOURCES[0]).toMatchObject({
      filename: 'DerivedGeneralCategory.txt',
      url: 'https://www.unicode.org/Public/13.0.0/ucd/extracted/DerivedGeneralCategory.txt',
    })
    for (const source of TERMINAL_UNICODE_SOURCES) {
      expect(source.sha256).toMatch(/^[a-f0-9]{64}$/)
    }
    expect(terminalScalarWidth('A'.codePointAt(0)!)).toBe(1)
    expect(terminalScalarWidth('界'.codePointAt(0)!)).toBe(2)
    expect(terminalScalarWidth('\u0301'.codePointAt(0)!)).toBe(0)
    expect(TERMINAL_DEFAULT_IGNORABLE_RANGES).toHaveLength(17)
    expect(TERMINAL_HANGUL_L_RANGES).toHaveLength(2)
    expect(TERMINAL_HANGUL_V_RANGES).toHaveLength(2)
    expect(TERMINAL_HANGUL_T_RANGES).toHaveLength(2)
    expect(TERMINAL_HANGUL_LV_RANGES).toHaveLength(399)
    expect(TERMINAL_HANGUL_LVT_RANGES).toHaveLength(399)
    expect(TERMINAL_EMOJI_MODIFIER_RANGES).toHaveLength(1)
    expect(TERMINAL_EMOJI_MODIFIER_BASE_RANGES).toHaveLength(38)
  })

  it('combines Hangul GB6-GB8 and emoji modifiers into fixed model cells', () => {
    const model = new TerminalModel(16, 1)
    model.applyTokens([text('A☝🏽B각C')])
    const projection = model.project()
    expect(projection.lines[0].runs).toMatchObject([
      { column: 0, width: 1, text: 'A' },
      { column: 1, width: 2, text: '☝🏽' },
      { column: 3, width: 1, text: 'B' },
      { column: 4, width: 2, text: '각' },
      { column: 6, width: 1, text: 'C' },
    ])
    expect(projectedText(projection, 0)).toBe('A☝🏽 B각 C')
    projection.release()

    const standalone = new TerminalModel(8, 1)
    standalone.applyTokens([text('🏽X')])
    const standaloneProjection = standalone.project()
    expect(standaloneProjection.lines[0].runs).toMatchObject([
      { column: 0, width: 2, text: '🏽' },
      { column: 2, width: 1, text: 'X' },
    ])
    standaloneProjection.release()
  })

  it.each([
    ['ᄀ', 'ᄂ'],
    ['ᄀ', 'ᅡ'],
    ['ᄀ', '가'],
    ['ᄀ', '각'],
    ['가', 'ᅡ'],
    ['ᅡ', 'ᅢ'],
    ['가', 'ᆨ'],
    ['ᅡ', 'ᆨ'],
    ['각', 'ᆨ'],
    ['ᆨ', 'ᆫ'],
  ])('applies the UAX29 Hangul no-break pair %s + %s', (left, right) => {
    const model = new TerminalModel(8, 1)
    model.applyTokens([text(left + right)])
    const projection = model.project()
    expect(projection.lines[0].runs).toMatchObject([
      { column: 0, text: left + right },
    ])
    projection.release()
  })

  it('keeps Hangul roles scalar-adjacent while allowing emoji-base Extend modifier', () => {
    const hangul = new TerminalModel(8, 1)
    hangul.applyTokens([text('ᄀ\u0301ᅡ')])
    let projection = hangul.project()
    expect(projection.lines[0].runs).toMatchObject([
      { column: 0, width: 2, text: 'ᄀ\u0301' },
      { column: 2, width: 1, text: 'ᅡ' },
    ])
    projection.release()

    const emoji = new TerminalModel(8, 1)
    emoji.applyTokens([text('☝\u0301🏽X')])
    projection = emoji.project()
    expect(projection.lines[0].runs).toMatchObject([
      { column: 0, width: 2, text: '☝\u0301🏽' },
      { column: 2, width: 1, text: 'X' },
    ])
    projection.release()
  })

  it('keeps tokenizer-denied zero-width and bidi scalars invalid', () => {
    for (const value of [
      0, 0x7f, 0x80, 0xd800, 0x200b, 0x200f, 0x202a, 0x202e, 0x2060, 0x2066,
      0x2069, 0xfeff, 0x110000,
    ]) {
      expect(terminalScalarWidth(value)).toBeNull()
    }
    for (const scalar of String.raw`\u{202A}`) {
      expect(terminalScalarWidth(scalar.codePointAt(0)!)).toBe(1)
    }
  })
})

describe('bounded terminal model', () => {
  it('renders closed typed controls on normal and disposable alternate screens', () => {
    const model = new TerminalModel(8, 2)
    model.applyTokens([text('normal')])
    model.applyTokens([
      { kind: 'alternate-screen', enabled: true },
      text('alt'),
    ])
    const alternate = model.project()
    expect(alternate.mode).toBe('alternate')
    expect(projectedText(alternate, 0)).toBe('alt')
    alternate.release()

    model.applyTokens([{ kind: 'alternate-screen', enabled: false }])
    const normal = model.project()
    expect(normal.mode).toBe('normal')
    expect(projectedText(normal, 0)).toBe('normal')
    normal.release()
    expect(model.retainedPayloadBytes).toBe(6)
  })

  it('bounds cursor movement, erase, scroll and the closed SGR palette', () => {
    const model = new TerminalModel(8, 2)
    let result = model.applyTokens([
      csi('m', '1;31'),
      text('red'),
      control('CR'),
      control('LF'),
      text('second'),
      csi('H', '999999;999999'),
      text('Z'),
    ])
    expect(result.rejectedOperations).toBe(0)
    let projection = model.project()
    expect(projectedText(projection, 0)).toBe('red')
    expect(projectedText(projection, 1)).toBe('second Z')
    expect(projection.lines[0].runs[0].style).toMatchObject({
      foreground: 'red',
      bold: true,
    })
    projection.release()

    result = model.applyTokens([csi('A', '?1'), csi('K', '9')])
    expect(result.rejectedOperations).toBe(2)
    projection = model.project()
    expect(projectedText(projection, 1)).toBe('second Z')
    projection.release()

    model.applyTokens([csi('J', '2'), csi('H', '1;1'), text('one')])
    projection = model.project()
    expect(projectedText(projection, 0)).toBe('one')
    expect(projectedText(projection, 1)).toBe('')
    projection.release()

    model.applyTokens([csi('S', '9999')])
    expect(model.historyLines).toBe(2)
    projection = model.project()
    expect(projectedText(projection, 0)).toBe('')
    projection.release()
  })

  it('implements bounded insert/delete line and character operations', () => {
    const model = new TerminalModel(8, 3)
    model.applyTokens([
      text('abcdef'),
      csi('H', '1;3'),
      csi('@', '2'),
      csi('H', '1;5'),
      csi('P', '2'),
      csi('H', '2;1'),
      text('row2'),
      csi('H', '2;1'),
      csi('L', '1'),
    ])
    let projection = model.project()
    expect(projectedText(projection, 0)).toBe('ab  ef')
    expect(projectedText(projection, 1)).toBe('')
    expect(projectedText(projection, 2)).toBe('row2')
    projection.release()

    model.applyTokens([csi('M', '99')])
    projection = model.project()
    expect(projectedText(projection, 1)).toBe('')
    expect(projectedText(projection, 2)).toBe('')
    projection.release()
  })

  it('accounts a copy-free projection and releases overwritten ownership', () => {
    const model = new TerminalModel(8, 1)
    model.applyTokens([text('safe')])
    const before = model.retainedPayloadBytes
    const projection = model.project()
    expect(Object.isFrozen(projection)).toBe(true)
    expect(Object.isFrozen(projection.lines)).toBe(true)
    expect(Object.isFrozen(projection.lines[0])).toBe(true)
    expect(Object.isFrozen(projection.lines[0].runs)).toBe(true)
    expect(model.retainedPayloadBytes).toBe(before)
    const retainedRun = projection.lines[0].runs[0]
    expect(retainedRun.text).toBe('s')
    expect(() => model.project()).toThrow(
      new TerminalModelError('TERMINAL_MODEL_PROJECTION_PENDING'),
    )

    model.applyTokens([control('CR'), text('X')])
    expect(retainedRun.text).toBe('s')
    expect(model.retainedPayloadBytes).toBe(before + 1)
    projection.release()
    expect(retainedRun.text).toBe('')
    expect(projection.lines).toHaveLength(1)
    expect(model.hasPendingMaintenance).toBe(true)
    drainMaintenance(model)
    expect(model.retainedPayloadBytes).toBe(before)

    const current = model.project()
    expect(projectedText(current, 0)).toBe('Xafe')
    current.release()
  })

  it('keeps pending projection combining ownership until overwrite release', () => {
    const model = new TerminalModel(8, 1)
    model.applyTokens([text('e')])
    const pending = model.project()
    const oldRun = pending.lines[0].runs[0]
    model.applyTokens([text('\u0301')])
    expect(oldRun.text).toBe('e')
    expect(model.retainedPayloadBytes).toBe(4)
    pending.release()
    expect(oldRun.text).toBe('')
    expect(model.hasPendingMaintenance).toBe(true)
    drainMaintenance(model)
    expect(model.retainedPayloadBytes).toBe(3)
    const current = model.project()
    expect(current.lines[0].runs[0].text).toBe('e\u0301')
    current.release()
  })

  it('caps combining ownership and releases it on overwrite', () => {
    const model = new TerminalModel(8, 1)
    const accents = '\u0301'.repeat(
      TERMINAL_MODEL_LIMITS.combiningCodePointsPerCell,
    )
    const result = model.applyTokens([text(`e${accents}\u0301`)])
    expect(result.status).toBe('TERMINAL_PARSE_LIMIT')
    expect(result.discardedCombining).toBe(1)
    expect(model.retainedPayloadBytes).toBe(1 + accents.length * 2)
    let projection = model.project()
    expect(projection.lines[0].runs[0]).toMatchObject({
      column: 0,
      width: 1,
      text: `e${accents}`,
    })
    projection.release()

    model.applyTokens([control('CR'), text('界')])
    projection = model.project()
    expect(projection.lines[0].runs[0]).toMatchObject({
      column: 0,
      width: 2,
      text: '界',
    })
    projection.release()
    expect(model.retainedPayloadBytes).toBe(3)
  })

  it('trims the oldest history before the shared 2000-line ceiling', () => {
    const model = new TerminalModel(8, 1)
    const tokens: TerminalToken[] = []
    for (let index = 0; index < 2105; index++) {
      tokens.push(text('x'), control('LF'), control('CR'))
    }
    const result = model.applyTokens(tokens)
    expect(result.state).toBe('active')
    expect(model.retainedLogicalLines).toBeLessThanOrEqual(
      TERMINAL_MODEL_LIMITS.logicalLines,
    )
    expect(model.historyLines).toBe(TERMINAL_MODEL_LIMITS.logicalLines - 1)
    expect(model.retainedPayloadBytes).toBeLessThanOrEqual(
      TERMINAL_MODEL_LIMITS.payloadBytes,
    )
    const projection = model.project()
    expect(model.retainedLogicalLines).toBe(TERMINAL_MODEL_LIMITS.logicalLines)
    expect(model.historyLines).toBe(TERMINAL_MODEL_LIMITS.logicalLines - 2)
    projection.release()
  })

  it('shares the line budget across normal, alternate, history and pending projection', () => {
    const model = new TerminalModel(8, 2)
    const tokens: TerminalToken[] = []
    for (let index = 0; index < 2105; index++) {
      tokens.push(text('x'), control('LF'), control('CR'))
    }
    model.applyTokens(tokens)
    expect(model.historyLines).toBe(TERMINAL_MODEL_LIMITS.logicalLines - 2)
    model.applyTokens([{ kind: 'alternate-screen', enabled: true }])
    expect(model.historyLines).toBe(TERMINAL_MODEL_LIMITS.logicalLines - 4)
    const projection = model.project()
    expect(model.mode).toBe('alternate')
    expect(model.historyLines).toBe(TERMINAL_MODEL_LIMITS.logicalLines - 6)
    expect(model.retainedLogicalLines).toBe(TERMINAL_MODEL_LIMITS.logicalLines)
    projection.release()
  })

  it('reserves logical headroom before display, projection, resize and text wrap', () => {
    const display = new TerminalModel(8, 200)
    fillHistoryTo(display, 1_999)
    expect(display.retainedLogicalLines).toBe(2_000)
    finishApplyWithinLineCeiling(display, [csi('J', '2')])

    const projection = new TerminalModel(8, 200)
    fillHistoryTo(projection, 1_999)
    projection.beginProjection()
    let now = 0
    const clock = () => {
      const value = now
      now += 0.02
      return value
    }
    for (let callbacks = 0; callbacks < 20_000; callbacks++) {
      const task = projection.runProjectionTask(clock, now + 5)
      expect(projection.effectiveRetainedLogicalLines).toBeLessThanOrEqual(
        TERMINAL_MODEL_LIMITS.logicalLines,
      )
      if (task.complete) {
        task.projection?.release()
        break
      }
    }

    const resized = new TerminalModel(8, 1)
    fillHistoryTo(resized, 2_000)
    expect(resized.retainedLogicalLines).toBe(2_000)
    resized.beginResize(8, 200)
    now = 0
    for (let callbacks = 0; callbacks < 20_000; callbacks++) {
      const task = resized.runResizeTask(clock, now + 5)
      expect(resized.effectiveRetainedLogicalLines).toBeLessThanOrEqual(
        TERMINAL_MODEL_LIMITS.logicalLines,
      )
      if (task.complete) break
    }

    const wrapped = new TerminalModel(8, 1)
    fillHistoryTo(wrapped, 2_000)
    finishApplyWithinLineCeiling(wrapped, [text('xx')])
  })

  it('reserves headroom before 200-line alternate scroll and line mutations', () => {
    for (const final of ['S', 'L', 'M'] as const) {
      const model = new TerminalModel(8, 200)
      fillHistoryTo(model, 1_799)
      finishApplyWithinLineCeiling(model, [
        { kind: 'alternate-screen', enabled: true },
      ])
      expect(model.effectiveRetainedLogicalLines).toBe(2_000)
      finishApplyWithinLineCeiling(model, [csi(final, '200')])
    }
  })

  it('resumes 48000-cell apply and projection at absolute deadlines', () => {
    const model = new TerminalModel(240, 200)
    let now = 0
    const clock = () => {
      const value = now
      now += 0.01
      return value
    }
    model.beginApplyTokens([text('x'.repeat(48_000))])
    let applyTasks = 0
    for (;;) {
      const before = now
      const task = model.runApplyTask(clock, before + 5)
      applyTasks++
      expect(now - before).toBeLessThanOrEqual(5.03)
      if (task.complete) {
        expect(task.result?.state).toBe('active')
        break
      }
    }
    expect(applyTasks).toBeGreaterThan(100)

    model.beginProjection()
    let projectionTasks = 0
    for (;;) {
      const before = now
      const task = model.runProjectionTask(clock, before + 5)
      projectionTasks++
      expect(now - before).toBeLessThanOrEqual(5.03)
      if (task.complete) {
        expect(task.projection?.lines).toHaveLength(200)
        expect(task.projection?.lines[199].runs).toHaveLength(240)
        task.projection?.release()
        break
      }
    }
    expect(projectionTasks).toBeGreaterThan(80)
  })

  it('releases cells cropped by resize without clamping the requested viewport', () => {
    const model = new TerminalModel(16, 1)
    model.applyTokens([text('0123456789abcdef')])
    expect(model.retainedPayloadBytes).toBe(16)
    model.resize(8, 1)
    expect([model.columns, model.rows]).toEqual([8, 1])
    expect(model.retainedPayloadBytes).toBe(8)
    const projection = model.project()
    expect(projectedText(projection, 0)).toBe('01234567')
    projection.release()
  })

  it('resumes a populated resize under one absolute scheduler deadline', () => {
    const model = new TerminalModel(240, 200)
    model.applyTokens([text('x'.repeat(48_000))])
    let now = 0
    const clock = () => {
      const value = now
      now += 0.02
      return value
    }

    model.beginResize(8, 1)
    expect([model.columns, model.rows]).toEqual([240, 200])
    let tasks = 0
    for (; tasks < 1_000; tasks++) {
      const before = now
      const task = model.runResizeTask(clock, before + 5)
      expect(now - before).toBeLessThanOrEqual(5.05)
      if (task.complete) {
        expect(task.result?.state).toBe('active')
        break
      }
    }
    expect(tasks).toBeLessThan(1_000)
    expect(tasks).toBeGreaterThan(0)
    expect([model.columns, model.rows]).toEqual([8, 1])
    const projection = model.project()
    expect(projection.lines).toHaveLength(1)
    projection.release()
  })

  it('releases a full display and alternate screen one retained cell per task step', () => {
    const normal = new TerminalModel(240, 200)
    normal.applyTokens([text('x'.repeat(48_000))])
    expect(finishApplyWithinDeadline(normal, [csi('J', '2')])).toBeGreaterThan(
      100,
    )
    expect(normal.retainedPayloadBytes).toBe(0)

    const alternate = new TerminalModel(240, 200)
    alternate.applyTokens([
      { kind: 'alternate-screen', enabled: true },
      text('x'.repeat(48_000)),
    ])
    expect(
      finishApplyWithinDeadline(alternate, [
        { kind: 'alternate-screen', enabled: false },
      ]),
    ).toBeGreaterThan(100)
    expect(alternate.retainedPayloadBytes).toBe(0)
  })

  it('counts detached erase and alternate lines until maintenance releases them', () => {
    const erased = new TerminalModel(240, 200)
    erased.applyTokens([text('x'.repeat(48_000))])
    expect(erased.retainedLogicalLines).toBe(200)
    beginOneApplyStep(erased, [csi('J', '2')])
    expect(erased.retainedLogicalLines).toBe(400)
    drainMaintenanceWithinDeadline(erased)
    expect(erased.retainedLogicalLines).toBe(200)

    const alternate = new TerminalModel(240, 200)
    alternate.applyTokens([
      { kind: 'alternate-screen', enabled: true },
      text('x'.repeat(48_000)),
    ])
    expect(alternate.retainedLogicalLines).toBe(400)
    beginOneApplyStep(alternate, [{ kind: 'alternate-screen', enabled: false }])
    expect(alternate.retainedLogicalLines).toBe(400)
    drainMaintenanceWithinDeadline(alternate)
    expect(alternate.retainedLogicalLines).toBe(200)
  })

  it('releases a full projection through deadline-bounded maintenance', () => {
    const model = new TerminalModel(240, 200)
    model.applyTokens([text('x'.repeat(48_000))])
    const projection = model.project()
    projection.release()
    expect(projection.lines[0].runs[0].text).toBe('')
    expect(drainMaintenanceWithinDeadline(model)).toBeGreaterThan(100)
    expect(model.retainedPayloadBytes).toBe(48_000)
  })

  it('drains alternate-screen scroll releases under the same deadline', () => {
    const model = new TerminalModel(240, 200)
    model.applyTokens([
      { kind: 'alternate-screen', enabled: true },
      text('x'.repeat(48_000)),
    ])

    expect(finishApplyWithinDeadline(model, [csi('S', '200')])).toBeGreaterThan(
      100,
    )
    expect(model.retainedPayloadBytes).toBe(0)
  })

  it('uses one array operation for a 200-line scroll, then releases cells by deadline', () => {
    const model = new TerminalModel(240, 200)
    model.applyTokens([
      { kind: 'alternate-screen', enabled: true },
      text('x'.repeat(48_000)),
    ])
    beginOneApplyStep(model, [csi('S', '200')])
    expect(model.retainedLogicalLines).toBe(600)
    expect(drainMaintenanceWithinDeadline(model)).toBeGreaterThan(100)
    expect(model.retainedLogicalLines).toBe(400)
    expect(model.retainedPayloadBytes).toBe(0)
  })

  it('does not preallocate terminal payload and fences active content over 256 KiB', () => {
    const model = new TerminalModel(240, 200)
    expect(model.retainedPayloadBytes).toBe(0)
    expect(model.retainedLogicalLines).toBe(200)
    model.applyTokens([{ kind: 'alternate-screen', enabled: true }])
    expect(model.retainedPayloadBytes).toBe(0)
    expect(model.retainedLogicalLines).toBe(400)
    const empty = model.project()
    expect(model.retainedLogicalLines).toBe(600)
    empty.release()

    const largeActiveScreen = `😀${'\u0301'.repeat(8)}`.repeat(14_000)
    const result = model.applyTokens([text(largeActiveScreen)])
    expect(result).toMatchObject({
      state: 'fenced',
      status: 'TERMINAL_PARSE_LIMIT',
    })
    expect(model.retainedPayloadBytes).toBe(0)
    expect(() => model.applyTokens([text('late')])).toThrow(
      new TerminalModelError('TERMINAL_MODEL_FENCED'),
    )
  })

  it.each([
    [120, 32],
    [40, 24],
    [8, 1],
    [240, 200],
  ])('accepts desktop/mobile viewport %ix%i', (columns, rows) => {
    const model = new TerminalModel(columns, rows)
    expect([model.columns, model.rows]).toEqual([columns, rows])
    model.resize(columns, rows)
  })

  it.each([
    [7, 1],
    [241, 1],
    [8, 0],
    [8, 201],
    [8.5, 20],
  ])('rejects invalid viewport %sx%s without clamping', (columns, rows) => {
    expect(() => new TerminalModel(columns, rows)).toThrow(
      new TerminalModelError('TERMINAL_MODEL_INVALID_VIEWPORT'),
    )
  })

  it('destroy is idempotent, clears projection refs and permanently rejects reuse', () => {
    const model = new TerminalModel(8, 1)
    model.applyTokens([text('private')])
    const projection = model.project()
    const run = projection.lines[0].runs[0]
    model.destroy()
    model.destroy()
    expect(model.state).toBe('destroyed')
    expect(model.retainedPayloadBytes).toBe(0)
    expect(run.text).toBe('')
    expect(() => model.resize(8, 1)).toThrow(
      new TerminalModelError('TERMINAL_MODEL_DESTROYED'),
    )
  })
})
