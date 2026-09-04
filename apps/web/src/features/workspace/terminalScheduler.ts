import {
  TERMINAL_MODEL_LIMITS,
  TerminalModel,
  TerminalModelError,
  type TerminalProjection,
} from './terminalModel'
import {
  TERMINAL_LIMITS,
  TerminalTokenizer,
  TerminalTokenizerError,
  type TerminalTaskResult,
} from './terminalTokenizer'

export const TERMINAL_SCHEDULER_LIMITS = Object.freeze({
  attachmentWindowMs: 1000,
  attachmentCpuMs: 50,
  consecutiveIncidentWindows: 3,
})

export type TerminalSchedulerState =
  'active' | 'fenced' | 'cancelled' | 'destroyed'

export type TerminalSchedulerFenceReason =
  | 'TERMINAL_PARSE_LIMIT'
  | 'TERMINAL_RENDER_FAILED'
  | 'TERMINAL_SCHEDULER_INVALID_CLOCK'
  | 'ATTACHMENT_CANCELLED'

export type TerminalSchedulerErrorCode =
  | 'TERMINAL_SCHEDULER_BUSY'
  | 'TERMINAL_SCHEDULER_FENCED'
  | 'TERMINAL_SCHEDULER_CANCELLED'
  | 'TERMINAL_SCHEDULER_DESTROYED'

export class TerminalSchedulerError extends Error {
  constructor(readonly code: TerminalSchedulerErrorCode) {
    super(code)
    this.name = 'TerminalSchedulerError'
  }
}

/** Internal marker so renderer clock failures cannot be mistaken for renderer faults. */
class TerminalSchedulerClockError extends Error {
  constructor() {
    super('TERMINAL_SCHEDULER_INVALID_CLOCK')
    this.name = 'TerminalSchedulerClockError'
  }
}

export interface TerminalSchedulerFence {
  readonly reason: TerminalSchedulerFenceReason
  readonly attachmentEpoch: number
}

export type TerminalTaskSchedule = (
  callback: () => void,
  delayMs: number,
) => () => void

export interface TerminalSchedulerOptions {
  readonly clock?: () => number
  readonly schedule?: TerminalTaskSchedule
  readonly createRenderTask?: (
    projection: TerminalProjection,
    attachmentEpoch: number,
  ) => TerminalRenderTask
  readonly onFence?: (event: TerminalSchedulerFence) => void
  readonly tokenizer?: TerminalTokenizer
  readonly model?: TerminalModel
}

interface PendingWrite {
  resolve: () => void
  reject: (error: TerminalSchedulerError) => void
}

interface PendingRender {
  projection: TerminalProjection
  task: TerminalRenderTask
  frameComplete: boolean | null
  epoch: number
}

interface PendingModelWork {
  readonly frameComplete: boolean | null
  readonly reservation: TerminalReservationRelease
}

interface TerminalReservation {
  rawFrameBytes: number
  decodedPotentialBytes: number
  decodedBacklogBytes: number
  logicalLines: number
}

interface TerminalReservationRelease {
  readonly decodedPotentialBytes: number
  readonly logicalLines: number
  readonly releaseRawFrame: boolean
}

export interface TerminalRenderTask {
  /** Return true only after all projection rows/cells are placed by model column. */
  run(clock: () => number, absoluteDeadlineMs: number): boolean
  cancel?(): void
}

function defaultSchedule(callback: () => void, delayMs: number): () => void {
  const handle = globalThis.setTimeout(callback, Math.max(0, delayMs))
  return () => globalThis.clearTimeout(handle)
}

/** U+061C expands from two UTF-8 bytes to the seven ASCII bytes `\\u{61C}`. */
function maximumDecodedBytes(rawBytes: number): number {
  return Math.floor((rawBytes * 7 + 1) / 2)
}

/**
 * One-attachment scheduler. Every scheduled callback runs at most one bounded
 * tokenizer task and one bounded model projection. It owns no DOM, transport,
 * heartbeat, Runtime cursor, or attachment cleanup implementation.
 */
export class TerminalScheduler {
  #state: TerminalSchedulerState = 'active'
  #epoch = 1
  #clock: () => number
  #schedule: TerminalTaskSchedule
  #createRenderTask: NonNullable<TerminalSchedulerOptions['createRenderTask']>
  #onFence: TerminalSchedulerOptions['onFence']
  #tokenizer: TerminalTokenizer
  #model: TerminalModel
  #lastTime = -Infinity
  #windowStart: number | null = null
  #windowCpuMs = 0
  #windowIncident = false
  #consecutiveIncidents = 0
  #cpuThrottled = false
  #taskCancel: (() => void) | null = null
  #deadlineCancel: (() => void) | null = null
  #deadlineAt: number | null = null
  #windowCancel: (() => void) | null = null
  #pendingWrite: PendingWrite | null = null
  #pendingRender: PendingRender | null = null
  #pendingApply: PendingModelWork | null = null
  #pendingProjection: PendingModelWork | null = null
  #pendingResize = false
  #reservation: TerminalReservation | null = null

  constructor(options: TerminalSchedulerOptions = {}) {
    this.#clock = options.clock ?? (() => performance.now())
    this.#schedule = options.schedule ?? defaultSchedule
    this.#createRenderTask =
      options.createRenderTask ??
      (() => ({
        run: () => true,
      }))
    this.#onFence = options.onFence
    this.#tokenizer = options.tokenizer ?? new TerminalTokenizer()
    this.#model = options.model ?? new TerminalModel()
  }

  get state(): TerminalSchedulerState {
    return this.#state
  }

  get attachmentEpoch(): number {
    return this.#epoch
  }

  get consecutiveIncidentWindows(): number {
    return this.#consecutiveIncidents
  }

  enqueueFrame(bytes: Uint8Array): Promise<void> {
    this.#assertActive()
    if (this.#pendingWrite || this.#pendingResize || this.#reservation) {
      throw new TerminalSchedulerError('TERMINAL_SCHEDULER_BUSY')
    }
    const reservation = this.#preflightFrameBytes(bytes)
    if (!reservation) {
      this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
      throw new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED')
    }
    const snapshot = this.#snapshotFrame(bytes)
    if (!snapshot || !this.#reserveLogicalLines(snapshot, reservation)) {
      this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
      throw new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED')
    }
    try {
      this.#model.reserveExternalLogicalLines(reservation.logicalLines)
      this.#tokenizer.beginOwnedFrame(snapshot)
    } catch (error) {
      if (
        this.#tokenizer.state === 'needs-reset' ||
        error instanceof TerminalTokenizerError ||
        error instanceof TerminalModelError
      ) {
        this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
        throw new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED')
      }
      throw error
    }
    this.#reservation = reservation
    const promise = new Promise<void>((resolve, reject) => {
      this.#pendingWrite = { resolve, reject }
    })
    this.#scheduleWork()
    return promise
  }

  resize(columns: number, rows: number): void {
    this.#assertActive()
    if (
      this.#pendingWrite ||
      this.#pendingApply ||
      this.#pendingProjection ||
      this.#pendingRender ||
      this.#pendingResize
    ) {
      throw new TerminalSchedulerError('TERMINAL_SCHEDULER_BUSY')
    }
    try {
      this.#model.beginResize(columns, rows)
      this.#pendingResize = true
    } catch (error) {
      if (
        error instanceof TerminalModelError &&
        error.code === 'TERMINAL_MODEL_FENCED'
      ) {
        this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
        throw new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED')
      }
      throw error
    }
    this.#scheduleWork()
  }

  /** pagehide/freeze/unmount call this once; no quiet window is synthesized. */
  cancelAttachment(): void {
    if (this.#state !== 'active') return
    this.#close('cancelled', 'ATTACHMENT_CANCELLED', true)
  }

  destroy(): void {
    if (this.#state === 'destroyed') return
    this.#close('destroyed', 'ATTACHMENT_CANCELLED', false)
  }

  #assertActive(): void {
    if (this.#state === 'active') return
    const code: TerminalSchedulerErrorCode =
      this.#state === 'destroyed'
        ? 'TERMINAL_SCHEDULER_DESTROYED'
        : this.#state === 'cancelled'
          ? 'TERMINAL_SCHEDULER_CANCELLED'
          : 'TERMINAL_SCHEDULER_FENCED'
    throw new TerminalSchedulerError(code)
  }

  #readTime(): number {
    let value: number
    try {
      value = this.#clock()
    } catch {
      throw new TerminalSchedulerClockError()
    }
    if (!Number.isFinite(value) || value < 0 || value < this.#lastTime) {
      throw new TerminalSchedulerClockError()
    }
    this.#lastTime = value
    return value
  }

  #cancelHandle(name: 'task' | 'deadline' | 'window'): void {
    const handle =
      name === 'task'
        ? this.#taskCancel
        : name === 'deadline'
          ? this.#deadlineCancel
          : this.#windowCancel
    try {
      handle?.()
    } catch {
      // Cancellation is best effort; the captured epoch still makes it inert.
    }
    if (name === 'task') this.#taskCancel = null
    else if (name === 'deadline') {
      this.#deadlineCancel = null
      this.#deadlineAt = null
    } else this.#windowCancel = null
  }

  #scheduleGuarded(
    kind: 'task' | 'deadline' | 'window',
    callback: (epoch: number) => void,
    delayMs: number,
  ): void {
    const epoch = this.#epoch
    let cancel: () => void
    try {
      cancel = this.#schedule(
        () => {
          if (kind === 'task') this.#taskCancel = null
          else if (kind === 'deadline') {
            this.#deadlineCancel = null
            this.#deadlineAt = null
          } else this.#windowCancel = null
          if (this.#state !== 'active' || epoch !== this.#epoch) return
          callback(epoch)
        },
        Math.max(0, delayMs),
      )
    } catch {
      this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
      return
    }
    if (kind === 'task') this.#taskCancel = cancel
    else if (kind === 'deadline') this.#deadlineCancel = cancel
    else this.#windowCancel = cancel
  }

  #scheduleWork(): void {
    if (this.#state !== 'active' || this.#taskCancel || this.#cpuThrottled) {
      return
    }
    this.#scheduleGuarded('task', (epoch) => this.#runOneTask(epoch), 0)
  }

  #runOneTask(epoch: number): void {
    let before: number
    try {
      before = this.#readTime()
      this.#advanceWindows(before)
    } catch {
      this.#close('fenced', 'TERMINAL_SCHEDULER_INVALID_CLOCK', true)
      return
    }
    if (this.#state !== 'active' || epoch !== this.#epoch) return
    this.#ensureWindow(before)
    if (this.#windowCpuMs >= TERMINAL_SCHEDULER_LIMITS.attachmentCpuMs) {
      this.#cpuThrottled = true
      this.#ensureWindowTimer(before)
      this.#scheduleCarryDeadline(before)
      return
    }
    const windowEnd =
      this.#windowStart! + TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs
    const deadline = Math.min(
      before + TERMINAL_LIMITS.taskMs,
      before +
        Math.max(
          0,
          TERMINAL_SCHEDULER_LIMITS.attachmentCpuMs - this.#windowCpuMs,
        ),
      windowEnd,
    )
    let tokenizerRan = false
    let incident = false
    let phase: 'tokenizer' | 'model' | 'render' = 'tokenizer'
    try {
      while (this.#state === 'active') {
        const current = this.#readTime()
        if (current >= deadline) break
        if (this.#pendingRender) {
          phase = 'render'
          const record = this.#pendingRender
          const complete = record.task.run(() => this.#readTime(), deadline)
          if (typeof complete !== 'boolean') {
            throw new TerminalModelError('TERMINAL_MODEL_INVALID_TOKEN')
          }
          if (!complete) break
          this.#finishRender(record)
          if (record.frameComplete !== null) break
        } else if (this.#model.hasPendingMaintenance) {
          phase = 'model'
          const task = this.#model.runMaintenanceTask(
            () => this.#readTime(),
            deadline,
          )
          if (!task.complete) break
        } else if (this.#pendingProjection) {
          phase = 'model'
          const context = this.#pendingProjection
          const task = this.#model.runProjectionTask(
            () => this.#readTime(),
            deadline,
          )
          if (!task.complete) break
          this.#pendingProjection = null
          this.#startRender(task.projection!, context.frameComplete)
        } else if (this.#pendingApply) {
          phase = 'model'
          const context = this.#pendingApply
          const task = this.#model.runApplyTask(
            () => this.#readTime(),
            deadline,
          )
          if (!task.complete) break
          this.#pendingApply = null
          const result = task.result!
          incident ||= result.status !== null
          if (result.state === 'fenced') {
            this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
            return
          }
          this.#model.releaseExternalLogicalLines(
            context.reservation.logicalLines - result.externalLineTransfers,
          )
          this.#releaseReservation(context.reservation)
          this.#model.beginProjection()
          this.#pendingProjection = context
        } else if (this.#pendingResize) {
          phase = 'model'
          const task = this.#model.runResizeTask(
            () => this.#readTime(),
            deadline,
          )
          if (!task.complete) break
          this.#pendingResize = false
          const result = task.result!
          if (result.state === 'fenced' || result.status) {
            this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
            return
          }
          this.#model.beginProjection()
          this.#pendingProjection = {
            frameComplete: null,
            reservation: {
              decodedPotentialBytes: 0,
              logicalLines: 0,
              releaseRawFrame: false,
            },
          }
        } else {
          phase = 'tokenizer'
          if (tokenizerRan || !this.#pendingWrite) break
          tokenizerRan = true
          const task = this.#runTokenizer(deadline)
          incident ||= task.status !== null
          const reservation = this.#reservationReleaseFor(task)
          if (task.tokens.length) {
            this.#model.beginApplyTokens(task.tokens, reservation.logicalLines)
            this.#pendingApply = {
              frameComplete: task.frameComplete,
              reservation,
            }
          } else {
            this.#model.releaseExternalLogicalLines(reservation.logicalLines)
            this.#releaseReservation(reservation)
            this.#afterTask(task.frameComplete)
            break
          }
        }
      }
    } catch (error) {
      if (this.#state !== 'active') return
      const invalidClock =
        error instanceof TerminalSchedulerClockError ||
        (error instanceof TerminalModelError &&
          error.code === 'TERMINAL_MODEL_INVALID_CLOCK')
      this.#close(
        'fenced',
        invalidClock
          ? 'TERMINAL_SCHEDULER_INVALID_CLOCK'
          : phase === 'render'
            ? 'TERMINAL_RENDER_FAILED'
            : 'TERMINAL_PARSE_LIMIT',
        true,
      )
      return
    }
    if (this.#state !== 'active') return

    let after: number
    try {
      after = this.#readTime()
    } catch {
      this.#close('fenced', 'TERMINAL_SCHEDULER_INVALID_CLOCK', true)
      return
    }
    this.#accountCpu(before, after)
    if (this.#state !== 'active') return
    if (incident) this.#recordIncidentAt(after)
    this.#scheduleCarryDeadline(after)
    if (this.#hasWork()) this.#scheduleWork()
  }

  #runTokenizer(deadline: number): TerminalTaskResult {
    let task: TerminalTaskResult
    try {
      task = this.#tokenizer.runTask(() => this.#readTime(), deadline)
    } catch (error) {
      const invalidClock =
        error instanceof TerminalTokenizerError &&
        error.code === 'TERMINAL_TOKENIZER_INVALID_CLOCK'
      this.#close(
        'fenced',
        invalidClock
          ? 'TERMINAL_SCHEDULER_INVALID_CLOCK'
          : 'TERMINAL_PARSE_LIMIT',
        true,
      )
      throw new TerminalModelError(
        invalidClock
          ? 'TERMINAL_MODEL_INVALID_CLOCK'
          : 'TERMINAL_MODEL_INVALID_TOKEN',
      )
    }
    if (task.state === 'needs-reset') {
      this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
      throw new TerminalModelError('TERMINAL_MODEL_INVALID_TOKEN')
    }
    return task
  }

  #afterTask(frameComplete: boolean): void {
    if (this.#state !== 'active') return
    if (frameComplete && this.#pendingWrite) {
      const pending = this.#pendingWrite
      this.#pendingWrite = null
      pending.resolve()
    }
  }

  /** Performs O(1) byte-capacity checks before allocating any snapshot. */
  #preflightFrameBytes(bytes: Uint8Array): TerminalReservation | null {
    if (
      !ArrayBuffer.isView(bytes) ||
      Object.prototype.toString.call(bytes) !== '[object Uint8Array]'
    ) {
      return {
        rawFrameBytes: 0,
        decodedPotentialBytes: 0,
        decodedBacklogBytes: 0,
        logicalLines: 0,
      }
    }
    if (bytes.byteLength > TERMINAL_LIMITS.frameBytes) return null
    const rawFrameBytes = bytes.byteLength
    const utf8CarryBytes = this.#tokenizer.pendingUtf8CarryReservationBytes
    // OSC/CSI/string carry has no rendered payload and remains bounded by the
    // tokenizer's independent 4 KiB sequence parser limit.
    const decodedPotentialBytes =
      maximumDecodedBytes(rawFrameBytes) + utf8CarryBytes
    // A task-local decoded token string coexists with newly created model
    // content. Reserve the same fixed maximum expansion for one task.
    const decodedBacklogBytes =
      maximumDecodedBytes(Math.min(rawFrameBytes, TERMINAL_LIMITS.taskBytes)) +
      utf8CarryBytes
    if (
      this.#model.retainedPayloadBytes +
        rawFrameBytes +
        decodedPotentialBytes +
        decodedBacklogBytes >
      TERMINAL_MODEL_LIMITS.payloadBytes
    ) {
      return null
    }
    return {
      rawFrameBytes,
      decodedPotentialBytes,
      decodedBacklogBytes,
      logicalLines: 0,
    }
  }

  /** Creates the one bounded non-shared snapshot used for both scan and transfer. */
  #snapshotFrame(bytes: Uint8Array): Uint8Array | null {
    if (
      !ArrayBuffer.isView(bytes) ||
      Object.prototype.toString.call(bytes) !== '[object Uint8Array]' ||
      bytes.byteLength > TERMINAL_LIMITS.frameBytes ||
      (typeof SharedArrayBuffer !== 'undefined' &&
        bytes.buffer instanceof SharedArrayBuffer)
    ) {
      return null
    }
    const snapshot = new Uint8Array(bytes.byteLength)
    for (let index = 0; index < bytes.byteLength; index++) {
      snapshot[index] = bytes[index]
    }
    return snapshot
  }

  #reserveLogicalLines(
    bytes: Uint8Array,
    reservation: TerminalReservation,
  ): boolean {
    let logicalLines = 0
    for (let index = 0; index < bytes.byteLength; index++) {
      if (bytes[index] === 0x0a) logicalLines++
    }
    if (
      this.#model.retainedLogicalLines + logicalLines >
      TERMINAL_MODEL_LIMITS.logicalLines
    ) {
      return false
    }
    reservation.logicalLines = logicalLines
    return true
  }

  #reservationReleaseFor(task: TerminalTaskResult): TerminalReservationRelease {
    return {
      decodedPotentialBytes: Math.min(
        this.#reservation?.decodedPotentialBytes ?? 0,
        maximumDecodedBytes(task.consumedBytes),
      ),
      logicalLines: Math.min(
        this.#reservation?.logicalLines ?? 0,
        task.consumedLineFeeds,
      ),
      releaseRawFrame: task.frameComplete,
    }
  }

  #releaseReservation(release: TerminalReservationRelease): void {
    const reservation = this.#reservation
    if (!reservation) return
    reservation.decodedPotentialBytes = Math.max(
      0,
      reservation.decodedPotentialBytes - release.decodedPotentialBytes,
    )
    reservation.logicalLines = Math.max(
      0,
      reservation.logicalLines - release.logicalLines,
    )
    if (release.releaseRawFrame) {
      reservation.rawFrameBytes = 0
      reservation.decodedPotentialBytes = 0
      reservation.decodedBacklogBytes = 0
      reservation.logicalLines = 0
    }
    if (
      reservation.rawFrameBytes === 0 &&
      reservation.decodedPotentialBytes === 0 &&
      reservation.decodedBacklogBytes === 0 &&
      reservation.logicalLines === 0
    ) {
      this.#reservation = null
    }
  }

  #hasWork(): boolean {
    return Boolean(
      this.#pendingWrite ||
      this.#pendingApply ||
      this.#pendingProjection ||
      this.#pendingRender ||
      this.#pendingResize ||
      this.#model.hasPendingMaintenance,
    )
  }

  #startRender(
    projection: TerminalProjection,
    frameComplete: boolean | null,
  ): void {
    if (this.#state !== 'active') return
    let task: TerminalRenderTask
    try {
      task = this.#createRenderTask(projection, this.#epoch)
      if (!task || typeof task.run !== 'function') throw new Error()
    } catch {
      projection.release()
      this.#close('fenced', 'TERMINAL_RENDER_FAILED', true)
      return
    }
    const record: PendingRender = {
      projection,
      task,
      frameComplete,
      epoch: this.#epoch,
    }
    this.#pendingRender = record
  }

  #finishRender(record: PendingRender): void {
    if (
      this.#state !== 'active' ||
      this.#epoch !== record.epoch ||
      this.#pendingRender !== record
    ) {
      return
    }
    this.#pendingRender = null
    record.projection.release()
    if (record.frameComplete !== null) this.#afterTask(record.frameComplete)
  }

  #ensureWindow(now: number): void {
    if (this.#windowStart === null) {
      this.#windowStart =
        Math.floor(now / TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs) *
        TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs
    }
  }

  #recordIncidentAt(now: number): void {
    this.#advanceWindows(now)
    if (this.#state !== 'active') return
    this.#ensureWindow(now)
    this.#windowIncident = true
    this.#ensureWindowTimer(now)
  }

  #advanceWindows(now: number): void {
    if (this.#windowStart === null) return
    const windows = Math.floor(
      (now - this.#windowStart) / TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs,
    )
    if (windows < 1) return
    this.#finishWindow()
    if (this.#state !== 'active') return
    if (windows > 1) {
      // Every unobserved complete window after the first is quiet. Suspension
      // cancels the attachment, so this is only an active monotonic-time gap.
      this.#consecutiveIncidents = 0
      this.#windowStart! +=
        (windows - 1) * TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs
      this.#windowCpuMs = 0
      this.#windowIncident = false
      this.#cpuThrottled = false
    }
    this.#cancelHandle('window')
    if (this.#consecutiveIncidents) this.#ensureWindowTimer(now)
  }

  #finishWindow(): void {
    if (this.#windowStart === null) return
    if (this.#windowIncident) this.#consecutiveIncidents++
    else this.#consecutiveIncidents = 0
    if (
      this.#consecutiveIncidents >=
      TERMINAL_SCHEDULER_LIMITS.consecutiveIncidentWindows
    ) {
      this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
      return
    }
    this.#windowStart += TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs
    this.#windowCpuMs = 0
    this.#windowIncident = false
    this.#cpuThrottled = false
  }

  #accountCpu(before: number, after: number): void {
    this.#advanceWindows(before)
    this.#ensureWindow(before)
    let cursor = before
    while (this.#state === 'active' && cursor < after) {
      const boundary =
        this.#windowStart! + TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs
      const end = Math.min(after, boundary)
      this.#windowCpuMs += end - cursor
      if (this.#windowCpuMs >= TERMINAL_SCHEDULER_LIMITS.attachmentCpuMs) {
        this.#cpuThrottled = true
      }
      if (this.#windowCpuMs > TERMINAL_SCHEDULER_LIMITS.attachmentCpuMs) {
        this.#windowIncident = true
      }
      cursor = end
      if (cursor === boundary) this.#finishWindow()
    }
    if (this.#state !== 'active') return
    if (
      this.#cpuThrottled ||
      this.#windowIncident ||
      this.#consecutiveIncidents
    ) {
      this.#ensureWindowTimer(after)
    }
  }

  #ensureWindowTimer(now: number): void {
    if (this.#windowCancel || this.#windowStart === null) return
    const deadline =
      this.#windowStart + TERMINAL_SCHEDULER_LIMITS.attachmentWindowMs
    this.#scheduleGuarded(
      'window',
      () => {
        let current: number
        try {
          current = this.#readTime()
          this.#advanceWindows(current)
        } catch {
          this.#close('fenced', 'TERMINAL_SCHEDULER_INVALID_CLOCK', true)
          return
        }
        if (this.#state !== 'active') return
        if (current < deadline) {
          this.#ensureWindowTimer(current)
          return
        }
        if (this.#hasWork()) this.#scheduleWork()
      },
      deadline - now,
    )
  }

  #scheduleCarryDeadline(now: number): void {
    const deadline = this.#tokenizer.nextDeadlineMs
    if (deadline === null) {
      this.#cancelHandle('deadline')
      return
    }
    if (deadline === this.#deadlineAt && this.#deadlineCancel) return
    this.#cancelHandle('deadline')
    this.#deadlineAt = deadline
    this.#scheduleGuarded(
      'deadline',
      () => {
        let current: number
        try {
          current = this.#readTime()
        } catch {
          this.#close('fenced', 'TERMINAL_SCHEDULER_INVALID_CLOCK', true)
          return
        }
        if (current < deadline) {
          this.#scheduleCarryDeadline(current)
          return
        }
        // Carry is ambiguous at its exact deadline. Do not reset and continue
        // midstream; this attachment must be replaced with a fresh one.
        this.#close('fenced', 'TERMINAL_PARSE_LIMIT', true)
      },
      deadline - now,
    )
  }

  #close(
    state: Exclude<TerminalSchedulerState, 'active'>,
    reason: TerminalSchedulerFenceReason,
    notify: boolean,
  ): void {
    if (this.#state === 'destroyed') return
    if (this.#state !== 'active' && state !== 'destroyed') return
    const closingEpoch = this.#epoch
    this.#state = state
    this.#epoch++
    this.#cancelHandle('task')
    this.#cancelHandle('deadline')
    this.#cancelHandle('window')
    try {
      this.#pendingRender?.task.cancel?.()
    } catch {
      // The captured epoch still makes a failed renderer cancellation inert.
    }
    this.#pendingRender?.projection.release()
    this.#pendingRender = null
    this.#pendingApply = null
    this.#pendingProjection = null
    this.#pendingResize = false
    this.#reservation = null
    try {
      this.#tokenizer.destroy()
    } catch {
      // The tokenizer may already be irreversibly fenced; no reset is attempted.
    }
    this.#model.destroy()
    if (this.#pendingWrite) {
      const pending = this.#pendingWrite
      this.#pendingWrite = null
      const code: TerminalSchedulerErrorCode =
        state === 'destroyed'
          ? 'TERMINAL_SCHEDULER_DESTROYED'
          : state === 'cancelled'
            ? 'TERMINAL_SCHEDULER_CANCELLED'
            : 'TERMINAL_SCHEDULER_FENCED'
      pending.reject(new TerminalSchedulerError(code))
    }
    if (notify) {
      try {
        this.#onFence?.(
          Object.freeze({ reason, attachmentEpoch: closingEpoch }),
        )
      } catch {
        // Fence notification cannot restore or alter local terminal ownership.
      }
    }
  }
}
