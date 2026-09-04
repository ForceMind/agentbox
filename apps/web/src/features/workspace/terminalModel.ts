import type { TerminalToken } from './terminalTokenizer'
import {
  isTerminalEmojiModifier,
  isTerminalEmojiModifierBase,
  joinsHangulCluster,
  terminalHangulRole,
  terminalScalarWidth,
  type TerminalHangulRole,
} from './terminalUnicodeWidth'

export const TERMINAL_MODEL_LIMITS = Object.freeze({
  minColumns: 8,
  maxColumns: 240,
  minRows: 1,
  maxRows: 200,
  payloadBytes: 256 * 1024,
  logicalLines: 2000,
  combiningCodePointsPerCell: 8,
})

export type TerminalModelState = 'active' | 'fenced' | 'destroyed'
export type TerminalModelErrorCode =
  | 'TERMINAL_MODEL_INVALID_VIEWPORT'
  | 'TERMINAL_MODEL_INVALID_TOKEN'
  | 'TERMINAL_MODEL_PROJECTION_PENDING'
  | 'TERMINAL_MODEL_BUSY'
  | 'TERMINAL_MODEL_INVALID_CLOCK'
  | 'TERMINAL_MODEL_FENCED'
  | 'TERMINAL_MODEL_DESTROYED'

export class TerminalModelError extends Error {
  constructor(readonly code: TerminalModelErrorCode) {
    super(code)
    this.name = 'TerminalModelError'
  }
}

export const TERMINAL_PALETTE = Object.freeze([
  'black',
  'red',
  'green',
  'yellow',
  'blue',
  'magenta',
  'cyan',
  'white',
  'bright-black',
  'bright-red',
  'bright-green',
  'bright-yellow',
  'bright-blue',
  'bright-magenta',
  'bright-cyan',
  'bright-white',
] as const)

export type TerminalPaletteColor = (typeof TERMINAL_PALETTE)[number]
export interface TerminalTextStyle {
  readonly foreground: TerminalPaletteColor | null
  readonly background: TerminalPaletteColor | null
  readonly bold: boolean
  readonly dim: boolean
  readonly italic: boolean
  readonly underline: boolean
  readonly inverse: boolean
}

export interface TerminalTextRun {
  readonly column: number
  readonly width: 1 | 2
  readonly text: string
  readonly style: TerminalTextStyle
}

export interface TerminalProjectionLine {
  readonly row: number
  readonly runs: readonly TerminalTextRun[]
}

export interface TerminalModelResult {
  readonly state: TerminalModelState
  readonly status: 'TERMINAL_PARSE_LIMIT' | null
  readonly rejectedOperations: number
  readonly discardedCombining: number
  readonly externalLineTransfers: number
}

export interface TerminalModelTaskResult {
  readonly complete: boolean
  readonly result: TerminalModelResult | null
}

export interface TerminalProjectionTaskResult {
  readonly complete: boolean
  readonly projection: TerminalProjection | null
}

export interface TerminalResizeTaskResult {
  readonly complete: boolean
  readonly result: TerminalModelResult | null
}

export interface TerminalMaintenanceTaskResult {
  readonly complete: boolean
}

interface Content {
  text: string
  bytes: number
  combining: number
  hangulRole: TerminalHangulRole | null
  emojiModifierBase: boolean
  refs: number
}

interface ProjectionLifetime {
  released: boolean
  contents: Content[]
}

interface Cell {
  content: Content
  width: 1 | 2
  styleKey: number
}

type Line = Map<number, Cell>

interface Cursor {
  x: number
  y: number
}

interface Screen {
  columns: number
  rows: number
  lines: Array<Line | null>
  cursor: Cursor
  savedCursor: Cursor
  styleKey: number
  wrapPending: boolean
  lastWritten: { row: number; column: number } | null
}

const FLAG_BOLD = 1 << 0
const FLAG_DIM = 1 << 1
const FLAG_ITALIC = 1 << 2
const FLAG_UNDERLINE = 1 << 3
const FLAG_INVERSE = 1 << 4
const FOREGROUND_SHIFT = 5
const BACKGROUND_SHIFT = 10
const COLOR_MASK = 0x1f

const DEFAULT_STYLE: TerminalTextStyle = Object.freeze({
  foreground: null,
  background: null,
  bold: false,
  dim: false,
  italic: false,
  underline: false,
  inverse: false,
})

function validViewport(columns: number, rows: number): boolean {
  return (
    Number.isInteger(columns) &&
    Number.isInteger(rows) &&
    columns >= TERMINAL_MODEL_LIMITS.minColumns &&
    columns <= TERMINAL_MODEL_LIMITS.maxColumns &&
    rows >= TERMINAL_MODEL_LIMITS.minRows &&
    rows <= TERMINAL_MODEL_LIMITS.maxRows
  )
}

function makeScreen(columns: number, rows: number): Screen {
  return {
    columns,
    rows,
    lines: Array<Line | null>(rows).fill(null),
    cursor: { x: 0, y: 0 },
    savedCursor: { x: 0, y: 0 },
    styleKey: 0,
    wrapPending: false,
    lastWritten: null,
  }
}

function utf8Bytes(text: string): number {
  let bytes = 0
  for (const scalar of text) {
    const value = scalar.codePointAt(0)!
    bytes += value <= 0x7f ? 1 : value <= 0x7ff ? 2 : value <= 0xffff ? 3 : 4
  }
  return bytes
}

function decodeStyle(key: number): TerminalTextStyle {
  if (key === 0) return DEFAULT_STYLE
  const foreground = (key >>> FOREGROUND_SHIFT) & COLOR_MASK
  const background = (key >>> BACKGROUND_SHIFT) & COLOR_MASK
  return Object.freeze({
    foreground: foreground ? TERMINAL_PALETTE[foreground - 1] : null,
    background: background ? TERMINAL_PALETTE[background - 1] : null,
    bold: Boolean(key & FLAG_BOLD),
    dim: Boolean(key & FLAG_DIM),
    italic: Boolean(key & FLAG_ITALIC),
    underline: Boolean(key & FLAG_UNDERLINE),
    inverse: Boolean(key & FLAG_INVERSE),
  })
}

function parseDecimal(value: string, maximum: number): number | null {
  if (value === '' || value === '0') return 1
  if (!/^[0-9]+$/.test(value)) return null
  let result = 0
  for (const character of value) {
    result = Math.min(maximum, result * 10 + character.charCodeAt(0) - 48)
  }
  return result
}

function singleCount(parameters: string, maximum: number): number | null {
  if (parameters.includes(';') || parameters.includes('?')) return null
  return parseDecimal(parameters, maximum)
}

export class TerminalProjection {
  readonly mode: 'normal' | 'alternate'
  readonly columns: number
  readonly rows: number
  readonly lines: readonly TerminalProjectionLine[]
  #lifetime: ProjectionLifetime
  #released = false
  #releaseOwner: (() => void) | null

  constructor(
    mode: 'normal' | 'alternate',
    columns: number,
    rows: number,
    lines: ProjectionLine[],
    lifetime: ProjectionLifetime,
    releaseOwner: () => void,
  ) {
    this.mode = mode
    this.columns = columns
    this.rows = rows
    this.#lifetime = lifetime
    this.lines = Object.freeze(lines)
    this.#releaseOwner = releaseOwner
    Object.freeze(this)
  }

  get released(): boolean {
    return this.#released
  }

  release(): void {
    this.#releaseOwner?.()
  }

  /** @internal Clears all model-owned projection references and visible text. */
  _releaseFromOwner(): void {
    if (this.#released) return
    this.#released = true
    this.#releaseOwner = null
    this.#lifetime.released = true
  }
}

class ProjectionRun implements TerminalTextRun {
  readonly column: number
  readonly width: 1 | 2
  readonly style: TerminalTextStyle
  readonly #lifetime: ProjectionLifetime
  readonly #contentIndex: number

  constructor(
    column: number,
    cell: Cell,
    lifetime: ProjectionLifetime,
    contentIndex: number,
  ) {
    this.column = column
    this.width = cell.width
    this.style = decodeStyle(cell.styleKey)
    this.#lifetime = lifetime
    this.#contentIndex = contentIndex
    Object.freeze(this)
  }

  get text(): string {
    if (this.#lifetime.released) return ''
    return this.#lifetime.contents[this.#contentIndex]?.text ?? ''
  }
}

class ProjectionLine implements TerminalProjectionLine {
  readonly row: number
  readonly runs: readonly TerminalTextRun[]

  constructor(row: number, runs: ProjectionRun[]) {
    this.row = row
    this.runs = Object.freeze(runs)
    Object.freeze(this)
  }
}

interface ProjectionRecord {
  projection: TerminalProjection
  lifetime: ProjectionLifetime
  lineCount: number
}

interface ProjectionBuild {
  readonly mode: 'normal' | 'alternate'
  readonly screen: Screen
  readonly lifetime: ProjectionLifetime
  readonly lines: ProjectionLine[]
  readonly lineCount: number
  row: number
  column: number
  runs: ProjectionRun[]
}

interface ProjectionRequest {
  readonly mode: 'normal' | 'alternate'
  readonly screen: Screen
  readonly lineCount: number
}

interface ProjectionReleaseWork {
  readonly contents: Content[]
  index: number
}

interface LineReleaseWork {
  readonly line: Line | null
  cells: IterableIterator<Cell> | null
}

interface LineArrayReleaseWork {
  readonly lines: Array<Line | null>
  index: number
}

interface ApplyTextWork {
  readonly value: string
  offset: number
  phase: 'validate' | 'apply'
}

interface ClearRangeWork {
  readonly kind: 'clear-range'
  readonly screen: Screen
  readonly row: number
  readonly start: number
  readonly end: number
  line: Line | null
  cells: IterableIterator<[number, Cell]> | null
}

interface DisplayEraseWork {
  readonly kind: 'display-erase'
  readonly screen: Screen
  readonly mode: 0 | 1 | 2
  readonly row: number
  clear: ClearRangeWork | null
  prepared: boolean
}

interface LineMutationWork {
  readonly kind: 'line-mutation'
  readonly screen: Screen
  readonly action: 'scroll-up' | 'scroll-down' | 'insert-lines' | 'delete-lines'
  readonly amount: number
  readonly toHistory: boolean
  readonly transfersExternalLine: boolean
  transferredExternalLine: boolean
}

interface AlternateEnableWork {
  readonly kind: 'alternate-enable'
}

type ApplyOperation =
  ClearRangeWork | DisplayEraseWork | LineMutationWork | AlternateEnableWork

interface ApplyRecord {
  readonly tokens: readonly TerminalToken[]
  tokenIndex: number
  text: ApplyTextWork | null
  operation: ApplyOperation | null
  budgetPending: boolean
  rejectedOperations: number
  discardedCombining: number
  limited: boolean
  externalLineTransfers: number
  externalLineTransfersAvailable: number
}

interface ResizeScreenWork {
  readonly screen: Screen
  readonly columns: number
  readonly rows: number
  readonly toHistory: boolean
  columnRow: number
  cells: IterableIterator<[number, Cell]> | null
}

interface ResizeRecord {
  readonly screens: readonly ResizeScreenWork[]
  readonly logicalIncrease: number
  screenIndex: number
  budgetPending: boolean
  headroomReserved: boolean
}

/**
 * Sparse, project-owned terminal state. Cell text is retained in one Content
 * record and projections hold counted references to those records; projection
 * creation never joins or duplicates terminal strings. Lines move between the
 * screen and history instead of being copied.
 */
export class TerminalModel {
  #state: TerminalModelState = 'active'
  #normal: Screen
  #alternate: Screen | null = null
  #history: Array<Line | null> = []
  #payloadBytes = 0
  #pendingProjection: ProjectionRecord | null = null
  #projectionRequest: ProjectionRequest | null = null
  #projectionBuild: ProjectionBuild | null = null
  #applyRecord: ApplyRecord | null = null
  #resizeRecord: ResizeRecord | null = null
  #projectionReleases: ProjectionReleaseWork[] = []
  #lineReleases: LineReleaseWork[] = []
  #lineArrayReleases: LineArrayReleaseWork[] = []
  #maintenanceLogicalLines = 0
  #externalReservedLines = 0
  #lastWorkTime = -Infinity

  constructor(columns = 120, rows = 32) {
    if (!validViewport(columns, rows)) {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_VIEWPORT')
    }
    this.#normal = makeScreen(columns, rows)
  }

  get state(): TerminalModelState {
    return this.#state
  }

  get columns(): number {
    return this.#activeScreen().columns
  }

  get rows(): number {
    return this.#activeScreen().rows
  }

  get mode(): 'normal' | 'alternate' {
    return this.#alternate ? 'alternate' : 'normal'
  }

  get retainedPayloadBytes(): number {
    return this.#payloadBytes
  }

  get retainedLogicalLines(): number {
    return (
      this.#normal.rows +
      (this.#alternate?.rows ?? 0) +
      this.#history.length +
      this.#maintenanceLogicalLines +
      (this.#pendingProjection?.lineCount ??
        this.#projectionBuild?.lineCount ??
        0)
    )
  }

  get historyLines(): number {
    return this.#history.length
  }

  get effectiveRetainedLogicalLines(): number {
    return this.retainedLogicalLines + this.#externalReservedLines
  }

  get hasPendingMaintenance(): boolean {
    return Boolean(
      this.#projectionReleases.length ||
      this.#lineReleases.length ||
      this.#lineArrayReleases.length,
    )
  }

  reserveExternalLogicalLines(lines: number): void {
    this.#assertActive()
    if (!Number.isInteger(lines) || lines < 0) {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_TOKEN')
    }
    if (
      this.effectiveRetainedLogicalLines + lines >
      TERMINAL_MODEL_LIMITS.logicalLines
    ) {
      this.#fence()
      throw new TerminalModelError('TERMINAL_MODEL_FENCED')
    }
    this.#externalReservedLines += lines
  }

  releaseExternalLogicalLines(lines: number): void {
    this.#assertActive()
    if (
      !Number.isInteger(lines) ||
      lines < 0 ||
      lines > this.#externalReservedLines
    ) {
      this.#fence()
      throw new TerminalModelError('TERMINAL_MODEL_FENCED')
    }
    this.#externalReservedLines -= lines
  }

  applyTokens(tokens: readonly TerminalToken[]): TerminalModelResult {
    this.beginApplyTokens(tokens)
    for (;;) {
      const task = this.runApplyTask(
        () => Math.max(0, this.#lastWorkTime),
        Number.MAX_SAFE_INTEGER,
      )
      if (task.complete) return task.result!
    }
  }

  beginApplyTokens(
    tokens: readonly TerminalToken[],
    externalLineTransfersAvailable = 0,
  ): void {
    this.#assertActive()
    if (!Array.isArray(tokens)) {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_TOKEN')
    }
    if (
      !Number.isInteger(externalLineTransfersAvailable) ||
      externalLineTransfersAvailable < 0 ||
      externalLineTransfersAvailable > this.#externalReservedLines
    ) {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_TOKEN')
    }
    if (
      this.#applyRecord ||
      this.#projectionRequest ||
      this.#projectionBuild ||
      this.#resizeRecord
    ) {
      throw new TerminalModelError('TERMINAL_MODEL_BUSY')
    }
    this.#applyRecord = {
      tokens: tokens.slice(),
      tokenIndex: 0,
      text: null,
      operation: null,
      budgetPending: false,
      rejectedOperations: 0,
      discardedCombining: 0,
      limited: false,
      externalLineTransfers: 0,
      externalLineTransfersAvailable,
    }
  }

  runApplyTask(
    clock: () => number,
    absoluteDeadlineMs: number,
  ): TerminalModelTaskResult {
    this.#assertActive()
    const record = this.#applyRecord
    if (!record) throw new TerminalModelError('TERMINAL_MODEL_BUSY')
    let now = this.#readWorkTime(clock, absoluteDeadlineMs)
    while (this.#state === 'active' && now < absoluteDeadlineMs) {
      if (this.#runMaintenanceStep()) {
        // Projected content is released before any new mutation can consume
        // budget, one retained cell at a time.
      } else if (record.operation) {
        if (this.#runApplyOperation(record.operation, record)) {
          record.operation = null
          record.budgetPending = true
        }
      } else if (record.budgetPending) {
        record.budgetPending = !this.#enforceBudgetStep()
        if (this.#state !== 'active') record.limited = true
      } else if (record.text) {
        this.#runTextStep(record)
      } else if (record.tokenIndex < record.tokens.length) {
        this.#startToken(record)
      } else {
        this.#applyRecord = null
        return Object.freeze({
          complete: true,
          result: this.#modelResult(record),
        })
      }
      now = this.#readWorkTime(clock, absoluteDeadlineMs)
    }
    if (this.#state !== 'active') {
      this.#applyRecord = null
      return Object.freeze({
        complete: true,
        result: this.#modelResult(record),
      })
    }
    return Object.freeze({ complete: false, result: null })
  }

  resize(columns: number, rows: number): TerminalModelResult {
    this.beginResize(columns, rows)
    for (;;) {
      const task = this.runResizeTask(
        () => Math.max(0, this.#lastWorkTime),
        Number.MAX_SAFE_INTEGER,
      )
      if (task.complete) return task.result!
    }
  }

  /**
   * Starts a resize without scanning rows, cells, or history synchronously.
   * Call runResizeTask with the scheduler's absolute callback deadline until it
   * completes; no output work may interleave with the resize record.
   */
  beginResize(columns: number, rows: number): void {
    this.#assertActive()
    if (
      this.#applyRecord ||
      this.#projectionRequest ||
      this.#projectionBuild ||
      this.#resizeRecord
    ) {
      throw new TerminalModelError('TERMINAL_MODEL_BUSY')
    }
    if (!validViewport(columns, rows)) {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_VIEWPORT')
    }
    const screens: ResizeScreenWork[] = [
      {
        screen: this.#normal,
        columns,
        rows,
        toHistory: true,
        columnRow: 0,
        cells: null,
      },
    ]
    if (this.#alternate) {
      screens.push({
        screen: this.#alternate,
        columns,
        rows,
        toHistory: false,
        columnRow: 0,
        cells: null,
      })
    }
    const logicalIncrease = screens.reduce(
      (total, screen) => Math.max(0, screen.rows - screen.screen.rows) + total,
      0,
    )
    this.#resizeRecord = {
      screens,
      logicalIncrease,
      screenIndex: 0,
      budgetPending: false,
      headroomReserved: logicalIncrease === 0,
    }
  }

  runResizeTask(
    clock: () => number,
    absoluteDeadlineMs: number,
  ): TerminalResizeTaskResult {
    this.#assertActive()
    const record = this.#resizeRecord
    if (!record) throw new TerminalModelError('TERMINAL_MODEL_BUSY')
    let now = this.#readWorkTime(clock, absoluteDeadlineMs)
    while (this.#state === 'active' && now < absoluteDeadlineMs) {
      if (this.#runMaintenanceStep()) {
        // Keep release work under the same caller deadline as resize work.
      } else if (!record.headroomReserved) {
        if (this.#reserveLogicalHeadroom(record.logicalIncrease)) {
          record.headroomReserved = true
        }
      } else if (record.screenIndex < record.screens.length) {
        const screen = record.screens[record.screenIndex]
        if (this.#resizeScreenStep(screen)) record.screenIndex++
      } else if (record.budgetPending) {
        if (this.#enforceBudgetStep()) {
          this.#resizeRecord = null
          return Object.freeze({ complete: true, result: this.#resizeResult() })
        }
      } else {
        record.budgetPending = true
      }
      now = this.#readWorkTime(clock, absoluteDeadlineMs)
    }
    if (this.#state !== 'active') {
      this.#resizeRecord = null
      return Object.freeze({ complete: true, result: this.#resizeResult() })
    }
    return Object.freeze({ complete: false, result: null })
  }

  project(): TerminalProjection {
    this.beginProjection()
    for (;;) {
      const task = this.runProjectionTask(
        () => Math.max(0, this.#lastWorkTime),
        Number.MAX_SAFE_INTEGER,
      )
      if (task.complete) return task.projection!
    }
  }

  beginProjection(): void {
    this.#assertActive()
    if (this.#pendingProjection) {
      throw new TerminalModelError('TERMINAL_MODEL_PROJECTION_PENDING')
    }
    if (
      this.#applyRecord ||
      this.#projectionRequest ||
      this.#projectionBuild ||
      this.#resizeRecord
    ) {
      throw new TerminalModelError('TERMINAL_MODEL_BUSY')
    }
    const screen = this.#activeScreen()
    this.#projectionRequest = {
      mode: this.mode,
      screen,
      lineCount: screen.rows,
    }
  }

  runProjectionTask(
    clock: () => number,
    absoluteDeadlineMs: number,
  ): TerminalProjectionTaskResult {
    this.#assertActive()
    let now = this.#readWorkTime(clock, absoluteDeadlineMs)
    while (this.#state === 'active' && now < absoluteDeadlineMs) {
      if (this.#runMaintenanceStep()) {
        // A released projection must relinquish its retained cells before a
        // later projection can consume shared model budget.
      } else if (this.#projectionRequest) {
        const request = this.#projectionRequest
        if (this.#reserveLogicalHeadroom(request.lineCount)) {
          this.#projectionRequest = null
          this.#projectionBuild = {
            mode: request.mode,
            screen: request.screen,
            lifetime: { released: false, contents: [] },
            lines: [],
            lineCount: request.lineCount,
            row: 0,
            column: 0,
            runs: [],
          }
        }
      } else if (
        this.#payloadBytes > TERMINAL_MODEL_LIMITS.payloadBytes ||
        this.effectiveRetainedLogicalLines > TERMINAL_MODEL_LIMITS.logicalLines
      ) {
        this.#enforceBudgetStep()
      } else {
        const build = this.#projectionBuild
        if (!build) throw new TerminalModelError('TERMINAL_MODEL_BUSY')
        if (build.row < build.screen.rows) {
          const line = build.screen.lines[build.row]
          const cell = line?.get(build.column)
          if (cell) {
            this.#retain(cell.content)
            const contentIndex = build.lifetime.contents.length
            build.lifetime.contents.push(cell.content)
            const run = new ProjectionRun(
              build.column,
              cell,
              build.lifetime,
              contentIndex,
            )
            build.runs.push(run)
          }
          build.column++
          if (build.column === build.screen.columns) {
            build.lines.push(new ProjectionLine(build.row, build.runs))
            build.row++
            build.column = 0
            build.runs = []
          }
        } else {
          const projection = new TerminalProjection(
            build.mode,
            build.screen.columns,
            build.screen.rows,
            build.lines,
            build.lifetime,
            () => this.#releaseProjection(projection),
          )
          this.#projectionBuild = null
          this.#pendingProjection = {
            projection,
            lifetime: build.lifetime,
            lineCount: build.lineCount,
          }
          return Object.freeze({ complete: true, projection })
        }
      }
      now = this.#readWorkTime(clock, absoluteDeadlineMs)
    }
    if (this.#state !== 'active') {
      throw new TerminalModelError('TERMINAL_MODEL_FENCED')
    }
    return Object.freeze({ complete: false, projection: null })
  }

  runMaintenanceTask(
    clock: () => number,
    absoluteDeadlineMs: number,
  ): TerminalMaintenanceTaskResult {
    this.#assertActive()
    let now = this.#readWorkTime(clock, absoluteDeadlineMs)
    while (now < absoluteDeadlineMs) {
      if (!this.#runMaintenanceStep()) {
        return Object.freeze({ complete: true })
      }
      now = this.#readWorkTime(clock, absoluteDeadlineMs)
    }
    return Object.freeze({ complete: !this.hasPendingMaintenance })
  }

  destroy(): void {
    if (this.#state === 'destroyed') return
    this.#clearAll()
    this.#state = 'destroyed'
  }

  #assertActive(): void {
    if (this.#state !== 'active') {
      throw new TerminalModelError(
        this.#state === 'destroyed'
          ? 'TERMINAL_MODEL_DESTROYED'
          : 'TERMINAL_MODEL_FENCED',
      )
    }
  }

  #readWorkTime(clock: () => number, deadline: number): number {
    if (!Number.isFinite(deadline) || deadline < 0) {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_CLOCK')
    }
    let value: number
    try {
      value = clock()
    } catch {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_CLOCK')
    }
    if (!Number.isFinite(value) || value < 0 || value < this.#lastWorkTime) {
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_CLOCK')
    }
    this.#lastWorkTime = value
    return value
  }

  #modelResult(record: ApplyRecord): TerminalModelResult {
    return Object.freeze({
      state: this.#state,
      status: record.limited ? 'TERMINAL_PARSE_LIMIT' : null,
      rejectedOperations: record.rejectedOperations,
      discardedCombining: record.discardedCombining,
      externalLineTransfers: record.externalLineTransfers,
    })
  }

  #resizeResult(): TerminalModelResult {
    return Object.freeze({
      state: this.#state,
      status: this.#state === 'active' ? null : 'TERMINAL_PARSE_LIMIT',
      rejectedOperations: 0,
      discardedCombining: 0,
      externalLineTransfers: 0,
    })
  }

  #startToken(record: ApplyRecord): void {
    const token = record.tokens[record.tokenIndex++]
    if (!token || typeof token !== 'object') {
      record.rejectedOperations++
      return
    }
    if (token.kind === 'text') {
      if (typeof token.text !== 'string') {
        record.rejectedOperations++
        return
      }
      record.text = { value: token.text, offset: 0, phase: 'validate' }
      return
    }
    const screen = this.#activeScreen()
    if (token.kind === 'control') {
      if (
        ['LF', 'VT', 'FF'].includes(token.control) &&
        screen.cursor.y === screen.rows - 1
      ) {
        this.#resetMotion(screen)
        record.operation = {
          kind: 'line-mutation',
          screen,
          action: 'scroll-up',
          amount: 1,
          toHistory: screen === this.#normal && !this.#alternate,
          transfersExternalLine:
            record.externalLineTransfers <
            record.externalLineTransfersAvailable,
          transferredExternalLine: false,
        }
      } else if (!this.#applyControl(screen, token.control)) {
        record.rejectedOperations++
      }
    } else if (token.kind === 'cursor') {
      if (token.action === 'save') this.#saveCursor(screen)
      else if (token.action === 'restore') this.#restoreCursor(screen)
      else record.rejectedOperations++
    } else if (token.kind === 'alternate-screen') {
      if (typeof token.enabled !== 'boolean') record.rejectedOperations++
      else if (token.enabled && !this.#alternate) {
        record.operation = { kind: 'alternate-enable' }
      } else this.#setAlternate(token.enabled)
    } else if (token.kind === 'csi') {
      const lineMutation = this.#beginLineMutationCsi(
        screen,
        token.final,
        token.parameters,
      )
      if (lineMutation) {
        record.operation = lineMutation
      } else {
        const erase = this.#beginEraseCsi(screen, token.final, token.parameters)
        if (erase) record.operation = erase
        else if (!this.#applyCsi(screen, token.final, token.parameters)) {
          record.rejectedOperations++
        }
      }
    } else {
      record.rejectedOperations++
    }
    if (!record.operation) record.budgetPending = true
  }

  #beginEraseCsi(
    screen: Screen,
    final: string,
    parameters: unknown,
  ): ApplyOperation | false {
    if (typeof parameters !== 'string') return false
    if (final === 'J') {
      const mode = this.#eraseMode(parameters)
      if (mode === null) return false
      const row = screen.cursor.y
      return {
        kind: 'display-erase',
        screen,
        mode,
        row,
        clear: null,
        prepared: false,
      }
    }
    if (final === 'K') {
      const mode = this.#eraseMode(parameters)
      if (mode === null) return false
      if (mode === 2)
        return this.#beginClearRange(screen, screen.cursor.y, 0, screen.columns)
      return this.#beginClearRange(
        screen,
        screen.cursor.y,
        mode === 0 ? screen.cursor.x : 0,
        mode === 0 ? screen.columns : screen.cursor.x + 1,
      )
    }
    return false
  }

  #beginLineMutationCsi(
    screen: Screen,
    final: string,
    parameters: unknown,
  ): LineMutationWork | null {
    if (!['L', 'M', 'S', 'T'].includes(final)) return null
    if (typeof parameters !== 'string') return null
    const count = singleCount(parameters, screen.rows)
    if (count === null) return null
    const action =
      final === 'L'
        ? 'insert-lines'
        : final === 'M'
          ? 'delete-lines'
          : final === 'S'
            ? 'scroll-up'
            : 'scroll-down'
    const amount =
      action === 'insert-lines' || action === 'delete-lines'
        ? Math.min(count, screen.rows - screen.cursor.y)
        : Math.min(screen.rows, count)
    return {
      kind: 'line-mutation',
      screen,
      action,
      amount,
      toHistory:
        action === 'scroll-up' && screen === this.#normal && !this.#alternate,
      transfersExternalLine: false,
      transferredExternalLine: false,
    }
  }

  #runApplyOperation(work: ApplyOperation, record: ApplyRecord): boolean {
    if (work.kind === 'alternate-enable') {
      if (!this.#reserveLogicalHeadroom(this.#normal.rows)) return false
      this.#setAlternate(true)
      return true
    }
    if (work.kind === 'line-mutation') {
      if (work.transfersExternalLine && !work.transferredExternalLine) {
        this.#transferExternalLogicalLine()
        record.externalLineTransfers++
        work.transferredExternalLine = true
      }
      if (!this.#reserveLogicalHeadroom(work.amount)) return false
      if (work.action === 'scroll-up') {
        this.#scrollUp(work.screen, work.amount, work.toHistory)
      } else if (work.action === 'scroll-down') {
        this.#scrollDown(work.screen, work.amount)
      } else if (work.action === 'insert-lines') {
        this.#insertLines(work.screen, work.amount)
      } else this.#deleteLines(work.screen, work.amount)
      return true
    }
    if (work.kind !== 'display-erase') return this.#runClearRangeStep(work)
    if (!work.prepared) {
      const incoming =
        work.mode === 2
          ? work.screen.rows
          : work.mode === 0
            ? work.screen.rows - work.row - 1
            : work.row
      if (!this.#reserveLogicalHeadroom(incoming)) return false
      const oldLines = work.screen.lines
      if (work.mode === 2) {
        work.screen.lines = Array<Line | null>(work.screen.rows).fill(null)
        work.screen.lastWritten = null
        this.#releaseLineArray(oldLines)
        work.prepared = true
        return true
      }
      if (work.mode === 0) {
        const released = oldLines.slice(work.row + 1)
        work.screen.lines = [
          ...oldLines.slice(0, work.row + 1),
          ...Array<Line | null>(work.screen.rows - work.row - 1).fill(null),
        ]
        this.#releaseLineArray(released)
        work.clear = this.#beginClearRange(
          work.screen,
          work.row,
          work.screen.cursor.x,
          work.screen.columns,
        )
      } else {
        const released = oldLines.slice(0, work.row)
        work.screen.lines = [
          ...Array<Line | null>(work.row).fill(null),
          ...oldLines.slice(work.row),
        ]
        this.#releaseLineArray(released)
        work.clear = this.#beginClearRange(
          work.screen,
          work.row,
          0,
          work.screen.cursor.x + 1,
        )
      }
      work.prepared = true
    }
    return work.clear ? this.#runClearRangeStep(work.clear) : true
  }

  #beginClearRange(
    screen: Screen,
    row: number,
    start: number,
    end: number,
  ): ClearRangeWork {
    screen.lastWritten = null
    return {
      kind: 'clear-range',
      screen,
      row,
      start,
      end,
      line: null,
      cells: null,
    }
  }

  #runClearRangeStep(work: ClearRangeWork): boolean {
    if (!work.line) work.line = work.screen.lines[work.row]
    const line = work.line
    if (!line) return true
    if (!work.cells) work.cells = line.entries()
    const cell = work.cells.next()
    if (cell.done) {
      if (!line.size) work.screen.lines[work.row] = null
      return true
    }
    const [column, value] = cell.value
    if (column < work.end && column + value.width > work.start) {
      line.delete(column)
      this.#release(value.content)
    }
    return false
  }

  #runTextStep(record: ApplyRecord): void {
    const work = record.text!
    if (work.offset >= work.value.length) {
      if (work.phase === 'validate') {
        work.phase = 'apply'
        work.offset = 0
      } else {
        record.text = null
      }
      return
    }
    const value = work.value.codePointAt(work.offset)!
    const scalar = String.fromCodePoint(value)
    if (work.phase === 'validate') {
      if (terminalScalarWidth(value) === null) {
        record.rejectedOperations++
        record.text = null
        return
      }
    } else {
      const result = this.#applyScalar(this.#activeScreen(), scalar, value)
      if (result === 'deferred') return
      if (result === 'discarded') {
        record.discardedCombining++
        record.limited = true
      }
      record.budgetPending = true
    }
    work.offset += scalar.length
  }

  #activeScreen(): Screen {
    return this.#alternate ?? this.#normal
  }

  #newContent(
    text: string,
    combining = 0,
    hangulRole: TerminalHangulRole | null = null,
    emojiModifierBase = false,
  ): Content {
    const content = {
      text,
      bytes: utf8Bytes(text),
      combining,
      hangulRole,
      emojiModifierBase,
      refs: 1,
    }
    this.#payloadBytes += content.bytes
    return content
  }

  #retain(content: Content): void {
    content.refs++
  }

  #release(content: Content): void {
    if (--content.refs === 0) {
      this.#payloadBytes -= content.bytes
      content.text = ''
      content.bytes = 0
      content.combining = 0
      content.hangulRole = null
      content.emojiModifierBase = false
    }
  }

  #releaseLine(line: Line | null, alreadyCounted = false): void {
    if (!alreadyCounted) this.#maintenanceLogicalLines++
    this.#lineReleases.push({ line, cells: line?.values() ?? null })
  }

  #releaseLineArray(lines: Array<Line | null>): void {
    if (!lines.length) return
    this.#maintenanceLogicalLines += lines.length
    this.#lineArrayReleases.push({ lines, index: 0 })
  }

  #releaseScreen(screen: Screen): void {
    const lines = screen.lines
    screen.lines = Array<Line | null>(screen.rows).fill(null)
    screen.lastWritten = null
    this.#releaseLineArray(lines)
  }

  #releaseProjection(projection: TerminalProjection): void {
    const record = this.#pendingProjection
    if (!record || record.projection !== projection) return
    this.#pendingProjection = null
    const contents = record.lifetime.contents
    record.lifetime.contents = []
    record.lifetime.released = true
    projection._releaseFromOwner()
    if (contents.length) this.#projectionReleases.push({ contents, index: 0 })
  }

  /** Returns true only when one retained projection cell was released. */
  #runMaintenanceStep(): boolean {
    const projection = this.#projectionReleases[0]
    if (projection) {
      const content = projection.contents[projection.index]
      if (content) this.#release(content)
      projection.index++
      if (projection.index >= projection.contents.length) {
        this.#projectionReleases.shift()
      }
      return true
    }
    const line = this.#lineReleases[0]
    if (line) {
      const cell = line.cells?.next()
      if (!cell || cell.done) {
        line.line?.clear()
        this.#lineReleases.shift()
        this.#maintenanceLogicalLines--
      } else {
        this.#release(cell.value.content)
      }
      return true
    }
    const lines = this.#lineArrayReleases[0]
    if (!lines) return false
    this.#releaseLine(lines.lines[lines.index] ?? null, true)
    lines.index++
    if (lines.index >= lines.lines.length) {
      this.#lineArrayReleases.shift()
    }
    return true
  }

  /**
   * Keeps the logical-line ceiling true at every observable task boundary.
   * Moving history into maintenance does not create headroom by itself; a later
   * maintenance step must release that detached line before mutation proceeds.
   */
  #reserveLogicalHeadroom(incoming: number): boolean {
    if (!Number.isInteger(incoming) || incoming < 0) {
      this.#fence()
      return false
    }
    if (
      this.effectiveRetainedLogicalLines + incoming <=
      TERMINAL_MODEL_LIMITS.logicalLines
    ) {
      return true
    }
    if (this.#history.length) {
      this.#releaseLine(this.#history.shift()!)
      return false
    }
    if (this.hasPendingMaintenance) return false
    this.#fence()
    return false
  }

  #transferExternalLogicalLine(): boolean {
    if (this.#externalReservedLines < 1) {
      this.#fence()
      return false
    }
    this.#externalReservedLines--
    return true
  }

  #clearAll(): void {
    this.#applyRecord = null
    this.#resizeRecord = null
    this.#projectionRequest = null
    if (this.#projectionBuild) {
      this.#projectionBuild.lifetime.released = true
      this.#projectionBuild.lifetime.contents = []
      this.#projectionBuild = null
    }
    if (this.#pendingProjection) {
      this.#pendingProjection.lifetime.released = true
      this.#pendingProjection.lifetime.contents = []
      this.#pendingProjection.projection._releaseFromOwner()
      this.#pendingProjection = null
    }
    this.#projectionReleases.length = 0
    this.#lineReleases.length = 0
    this.#lineArrayReleases.length = 0
    this.#maintenanceLogicalLines = 0
    this.#externalReservedLines = 0
    const columns = this.#normal.columns
    const rows = this.#normal.rows
    this.#normal = makeScreen(columns, rows)
    this.#alternate = null
    this.#history = []
    this.#payloadBytes = 0
  }

  #fence(): void {
    if (this.#state !== 'active') return
    this.#clearAll()
    this.#state = 'fenced'
  }

  #enforceBudgetStep(): boolean {
    if (this.#state !== 'active') return true
    const overBudget =
      this.#payloadBytes > TERMINAL_MODEL_LIMITS.payloadBytes ||
      this.effectiveRetainedLogicalLines > TERMINAL_MODEL_LIMITS.logicalLines
    if (!overBudget) return true
    if (this.#history.length) {
      this.#releaseLine(this.#history.shift()!)
      return false
    }
    if (
      this.#payloadBytes > TERMINAL_MODEL_LIMITS.payloadBytes ||
      this.effectiveRetainedLogicalLines > TERMINAL_MODEL_LIMITS.logicalLines
    ) {
      this.#fence()
    }
    return true
  }

  #getLine(screen: Screen, row: number, create: boolean): Line | null {
    let line = screen.lines[row]
    if (!line && create) {
      line = new Map()
      screen.lines[row] = line
    }
    return line
  }

  #clearWriteRange(
    screen: Screen,
    row: number,
    start: number,
    end: number,
  ): void {
    const line = this.#getLine(screen, row, false)
    if (!line) return
    for (const column of [start - 1, start]) {
      const cell = line.get(column)
      if (!cell) continue
      if (column < end && column + cell.width > start) {
        line.delete(column)
        this.#release(cell.content)
      }
    }
    if (!line.size) screen.lines[row] = null
    screen.lastWritten = null
  }

  #writeCell(screen: Screen, scalar: string, width: 1 | 2): boolean {
    if (screen.wrapPending) {
      if (!this.#lineFeed(screen)) return false
      screen.cursor.x = 0
      screen.wrapPending = false
    }
    if (width === 2 && screen.cursor.x === screen.columns - 1) {
      if (!this.#lineFeed(screen)) return false
      screen.cursor.x = 0
    }
    const column = screen.cursor.x
    this.#clearWriteRange(screen, screen.cursor.y, column, column + width)
    const line = this.#getLine(screen, screen.cursor.y, true)!
    const value = scalar.codePointAt(0)!
    line.set(column, {
      content: this.#newContent(
        scalar,
        0,
        terminalHangulRole(value),
        isTerminalEmojiModifierBase(value),
      ),
      width,
      styleKey: screen.styleKey,
    })
    screen.lastWritten = { row: screen.cursor.y, column }
    if (column + width >= screen.columns) {
      screen.cursor.x = screen.columns - 1
      screen.wrapPending = true
    } else {
      screen.cursor.x = column + width
    }
    return true
  }

  #appendCombining(screen: Screen, scalar: string): boolean {
    const position = screen.lastWritten
    if (!position) return false
    const cell = screen.lines[position.row]?.get(position.column)
    if (!cell) return false
    if (
      cell.content.combining >= TERMINAL_MODEL_LIMITS.combiningCodePointsPerCell
    ) {
      return false
    }
    this.#appendCellContent(
      cell,
      scalar,
      cell.content.combining + 1,
      null,
      cell.content.emojiModifierBase,
    )
    return true
  }

  #appendCellContent(
    cell: Cell,
    scalar: string,
    combining: number,
    hangulRole: TerminalHangulRole | null,
    emojiModifierBase: boolean,
  ): void {
    const replacement = this.#newContent(
      cell.content.text + scalar,
      combining,
      hangulRole,
      emojiModifierBase,
    )
    this.#release(cell.content)
    cell.content = replacement
  }

  #applyScalar(
    screen: Screen,
    scalar: string,
    value: number,
  ): 'applied' | 'discarded' | 'deferred' {
    const width = terminalScalarWidth(value)!
    if (width === 0)
      return this.#appendCombining(screen, scalar) ? 'applied' : 'discarded'
    const position = screen.lastWritten
    const cell = position
      ? screen.lines[position.row]?.get(position.column)
      : undefined
    if (isTerminalEmojiModifier(value)) {
      if (cell?.content.emojiModifierBase) {
        this.#appendCellContent(
          cell,
          scalar,
          cell.content.combining,
          null,
          false,
        )
      } else {
        return this.#writeCell(screen, scalar, 2) ? 'applied' : 'deferred'
      }
      return 'applied'
    }
    const role = terminalHangulRole(value)
    if (cell && joinsHangulCluster(cell.content.hangulRole, role)) {
      this.#appendCellContent(cell, scalar, cell.content.combining, role, false)
      return 'applied'
    }
    return this.#writeCell(screen, scalar, width) ? 'applied' : 'deferred'
  }

  #resetMotion(screen: Screen): void {
    screen.wrapPending = false
    screen.lastWritten = null
  }

  #applyControl(screen: Screen, control: string): boolean {
    if (!['BS', 'HT', 'LF', 'VT', 'FF', 'CR'].includes(control)) return false
    this.#resetMotion(screen)
    if (control === 'BS') screen.cursor.x = Math.max(0, screen.cursor.x - 1)
    else if (control === 'HT') {
      screen.cursor.x = Math.min(
        screen.columns - 1,
        (Math.floor(screen.cursor.x / 8) + 1) * 8,
      )
    } else if (control === 'LF' || control === 'VT' || control === 'FF') {
      this.#lineFeed(screen)
    } else if (control === 'CR') screen.cursor.x = 0
    return true
  }

  #lineFeed(screen: Screen): boolean {
    if (screen.cursor.y < screen.rows - 1) {
      screen.lastWritten = null
      screen.wrapPending = false
      screen.cursor.y++
      return true
    }
    if (!this.#reserveLogicalHeadroom(1)) return false
    screen.lastWritten = null
    screen.wrapPending = false
    this.#scrollUp(screen, 1, screen === this.#normal && !this.#alternate)
    return true
  }

  #scrollUp(screen: Screen, count: number, toHistory: boolean): void {
    const amount = Math.min(screen.rows, Math.max(1, count))
    const removed = screen.lines.splice(0, amount)
    screen.lines.push(...Array<Line | null>(amount).fill(null))
    if (toHistory) this.#history.push(...removed)
    else this.#releaseLineArray(removed)
    screen.lastWritten = null
  }

  #scrollDown(screen: Screen, count: number): void {
    const amount = Math.min(screen.rows, Math.max(1, count))
    const removed = screen.lines.splice(screen.rows - amount, amount)
    screen.lines.unshift(...Array<Line | null>(amount).fill(null))
    this.#releaseLineArray(removed)
    screen.lastWritten = null
  }

  #saveCursor(screen: Screen): void {
    screen.savedCursor = { ...screen.cursor }
    this.#resetMotion(screen)
  }

  #restoreCursor(screen: Screen): void {
    screen.cursor = {
      x: Math.min(screen.columns - 1, Math.max(0, screen.savedCursor.x)),
      y: Math.min(screen.rows - 1, Math.max(0, screen.savedCursor.y)),
    }
    this.#resetMotion(screen)
  }

  #setAlternate(enabled: boolean): void {
    if (enabled) {
      if (!this.#alternate) {
        this.#alternate = makeScreen(this.#normal.columns, this.#normal.rows)
      }
    } else if (this.#alternate) {
      this.#releaseScreen(this.#alternate)
      this.#alternate = null
    }
  }

  #applyCsi(screen: Screen, final: string, parameters: unknown): boolean {
    if (typeof parameters !== 'string' || parameters.length > 32) return false
    if (final === 'm') return this.#applySgr(screen, parameters)
    if (final === 's' || final === 'u') {
      if (parameters !== '') return false
      if (final === 's') this.#saveCursor(screen)
      else this.#restoreCursor(screen)
      return true
    }
    if (final === 'H' || final === 'f') {
      if (parameters.includes('?')) return false
      const parts = parameters === '' ? [] : parameters.split(';')
      if (parts.length > 2) return false
      const row = parseDecimal(parts[0] ?? '', screen.rows)
      const column = parseDecimal(parts[1] ?? '', screen.columns)
      if (row === null || column === null) return false
      this.#resetMotion(screen)
      screen.cursor = { x: column - 1, y: row - 1 }
      return true
    }
    if (final === 'J' || final === 'K') return false
    const vertical =
      final === 'A' ||
      final === 'B' ||
      final === 'E' ||
      final === 'F' ||
      final === 'L' ||
      final === 'M' ||
      final === 'S' ||
      final === 'T'
    const maximum = vertical ? screen.rows : screen.columns
    const count = singleCount(parameters, maximum)
    if (count === null) return false
    if (!'ABCDEFGJKLM PST@'.replaceAll(' ', '').includes(final)) return false
    this.#resetMotion(screen)
    if (final === 'A') screen.cursor.y = Math.max(0, screen.cursor.y - count)
    else if (final === 'B')
      screen.cursor.y = Math.min(screen.rows - 1, screen.cursor.y + count)
    else if (final === 'C')
      screen.cursor.x = Math.min(screen.columns - 1, screen.cursor.x + count)
    else if (final === 'D')
      screen.cursor.x = Math.max(0, screen.cursor.x - count)
    else if (final === 'E') {
      screen.cursor.y = Math.min(screen.rows - 1, screen.cursor.y + count)
      screen.cursor.x = 0
    } else if (final === 'F') {
      screen.cursor.y = Math.max(0, screen.cursor.y - count)
      screen.cursor.x = 0
    } else if (final === 'G') screen.cursor.x = count - 1
    else if (final === 'L') this.#insertLines(screen, count)
    else if (final === 'M') this.#deleteLines(screen, count)
    else if (final === 'P') this.#deleteCharacters(screen, count)
    else if (final === '@') this.#insertCharacters(screen, count)
    else if (final === 'S')
      this.#scrollUp(screen, count, screen === this.#normal && !this.#alternate)
    else if (final === 'T') this.#scrollDown(screen, count)
    return true
  }

  #eraseMode(parameters: string): 0 | 1 | 2 | null {
    if (parameters === '') return 0
    if (parameters === '0' || parameters === '1' || parameters === '2') {
      return Number(parameters) as 0 | 1 | 2
    }
    return null
  }

  #insertLines(screen: Screen, count: number): void {
    const amount = Math.min(count, screen.rows - screen.cursor.y)
    screen.lines.splice(
      screen.cursor.y,
      0,
      ...Array<Line | null>(amount).fill(null),
    )
    this.#releaseLineArray(screen.lines.splice(screen.rows, amount))
  }

  #deleteLines(screen: Screen, count: number): void {
    const amount = Math.min(count, screen.rows - screen.cursor.y)
    const removed = screen.lines.splice(screen.cursor.y, amount)
    screen.lines.push(...Array<Line | null>(amount).fill(null))
    this.#releaseLineArray(removed)
  }

  #insertCharacters(screen: Screen, count: number): void {
    const row = screen.cursor.y
    const line = screen.lines[row]
    if (!line) return
    // One sparse row has at most 240 cells, a fixed local upper bound.
    const replacement: Line = new Map()
    for (const [column, cell] of line) {
      if (column + cell.width <= screen.cursor.x) replacement.set(column, cell)
      else if (column < screen.cursor.x) this.#release(cell.content)
      else {
        const target = column + count
        if (target + cell.width <= screen.columns) replacement.set(target, cell)
        else this.#release(cell.content)
      }
    }
    screen.lines[row] = replacement.size ? replacement : null
  }

  #deleteCharacters(screen: Screen, count: number): void {
    const row = screen.cursor.y
    const line = screen.lines[row]
    if (!line) return
    const end = Math.min(screen.columns, screen.cursor.x + count)
    const shift = end - screen.cursor.x
    // One sparse row has at most 240 cells, a fixed local upper bound.
    const replacement: Line = new Map()
    for (const [column, cell] of line) {
      if (column + cell.width <= screen.cursor.x) replacement.set(column, cell)
      else if (column >= end) replacement.set(column - shift, cell)
      else this.#release(cell.content)
    }
    screen.lines[row] = replacement.size ? replacement : null
  }

  #applySgr(screen: Screen, parameters: string): boolean {
    if (parameters.includes('?')) return false
    const parts = parameters === '' ? ['0'] : parameters.split(';')
    let key = screen.styleKey
    for (const part of parts) {
      if (!/^[0-9]{0,3}$/.test(part)) return false
      const code = part === '' ? 0 : Number(part)
      if (code === 0) key = 0
      else if (code === 1) key |= FLAG_BOLD
      else if (code === 2) key |= FLAG_DIM
      else if (code === 3) key |= FLAG_ITALIC
      else if (code === 4) key |= FLAG_UNDERLINE
      else if (code === 7) key |= FLAG_INVERSE
      else if (code === 22) key &= ~(FLAG_BOLD | FLAG_DIM)
      else if (code === 23) key &= ~FLAG_ITALIC
      else if (code === 24) key &= ~FLAG_UNDERLINE
      else if (code === 27) key &= ~FLAG_INVERSE
      else if (code >= 30 && code <= 37) {
        key =
          (key & ~(COLOR_MASK << FOREGROUND_SHIFT)) |
          ((code - 29) << FOREGROUND_SHIFT)
      } else if (code === 39) key &= ~(COLOR_MASK << FOREGROUND_SHIFT)
      else if (code >= 40 && code <= 47) {
        key =
          (key & ~(COLOR_MASK << BACKGROUND_SHIFT)) |
          ((code - 39) << BACKGROUND_SHIFT)
      } else if (code === 49) key &= ~(COLOR_MASK << BACKGROUND_SHIFT)
      else if (code >= 90 && code <= 97) {
        key =
          (key & ~(COLOR_MASK << FOREGROUND_SHIFT)) |
          ((code - 81) << FOREGROUND_SHIFT)
      } else if (code >= 100 && code <= 107) {
        key =
          (key & ~(COLOR_MASK << BACKGROUND_SHIFT)) |
          ((code - 91) << BACKGROUND_SHIFT)
      } else return false
    }
    screen.styleKey = key
    return true
  }

  #resizeScreenStep(work: ResizeScreenWork): boolean {
    const { screen, columns, rows, toHistory } = work
    if (screen.rows > rows) {
      const removed = screen.lines.shift() ?? null
      if (toHistory) this.#history.push(removed)
      else this.#releaseLine(removed)
      screen.rows--
      screen.cursor.y = Math.max(0, screen.cursor.y - 1)
      screen.savedCursor.y = Math.max(0, screen.savedCursor.y - 1)
      return false
    }
    if (screen.rows < rows) {
      screen.lines.push(null)
      screen.rows++
      return false
    }
    if (columns < screen.columns && work.columnRow < screen.rows) {
      const line = screen.lines[work.columnRow]
      if (!line) {
        work.columnRow++
        return false
      }
      if (!work.cells) work.cells = line.entries()
      const cell = work.cells.next()
      if (!cell.done) {
        const [column, value] = cell.value
        if (column + value.width > columns) {
          line.delete(column)
          this.#release(value.content)
        }
        return false
      }
      if (!line.size) screen.lines[work.columnRow] = null
      work.cells = null
      work.columnRow++
      return false
    }
    screen.columns = columns
    screen.cursor.x = Math.min(columns - 1, screen.cursor.x)
    screen.cursor.y = Math.min(rows - 1, screen.cursor.y)
    screen.savedCursor.x = Math.min(columns - 1, screen.savedCursor.x)
    screen.savedCursor.y = Math.min(rows - 1, screen.savedCursor.y)
    this.#resetMotion(screen)
    return true
  }
}
