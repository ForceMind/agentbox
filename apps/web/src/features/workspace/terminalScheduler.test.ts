import { describe, expect, it } from 'vitest'

import {
  TerminalScheduler,
  TerminalSchedulerError,
  type TerminalSchedulerFence,
  type TerminalTaskSchedule,
} from './terminalScheduler'
import { TerminalModel, type TerminalProjection } from './terminalModel'
import { TerminalTokenizer, type TerminalTaskResult } from './terminalTokenizer'

const utf8 = (value: string) => new TextEncoder().encode(value)

interface ScheduledTask {
  at: number
  callback: () => void
  cancelled: boolean
}

class ManualRuntime {
  now = 0
  clockStep = 0
  readonly tasks: ScheduledTask[] = []
  executed = 0
  afterCallback: (() => void) | null = null

  readonly clock = (): number => {
    const value = this.now
    this.now += this.clockStep
    return value
  }

  readonly schedule: TerminalTaskSchedule = (callback, delayMs) => {
    const task = {
      at: this.now + delayMs,
      callback,
      cancelled: false,
    }
    this.tasks.push(task)
    return () => {
      task.cancelled = true
    }
  }

  async flushCurrent(): Promise<void> {
    for (let pass = 0; pass < 20_000; pass++) {
      const index = this.#nextIndex(this.now)
      if (index < 0) {
        await Promise.resolve()
        if (this.#nextIndex(this.now) < 0) return
        continue
      }
      const [task] = this.tasks.splice(index, 1)
      this.now = Math.max(this.now, task.at)
      if (!task.cancelled) {
        this.executed++
        task.callback()
        this.afterCallback?.()
      }
      await Promise.resolve()
    }
    throw new Error('MANUAL_RUNTIME_DID_NOT_QUIESCE')
  }

  async runNextCurrent(): Promise<void> {
    const index = this.#nextIndex(this.now)
    if (index < 0) throw new Error('MANUAL_RUNTIME_NO_CURRENT_TASK')
    const [task] = this.tasks.splice(index, 1)
    this.now = Math.max(this.now, task.at)
    if (!task.cancelled) {
      this.executed++
      task.callback()
      this.afterCallback?.()
    }
    await Promise.resolve()
  }

  async advanceTo(target: number): Promise<void> {
    if (target < this.now) throw new Error('MANUAL_RUNTIME_BACKWARDS')
    while (true) {
      const index = this.#nextIndex(target)
      if (index < 0) break
      const [task] = this.tasks.splice(index, 1)
      this.now = Math.max(this.now, task.at)
      if (!task.cancelled) {
        this.executed++
        task.callback()
        this.afterCallback?.()
      }
      await Promise.resolve()
    }
    this.now = Math.max(this.now, target)
    await this.flushCurrent()
  }

  runCancelled(): void {
    const cancelled = this.tasks.filter((task) => task.cancelled)
    this.tasks.splice(
      0,
      this.tasks.length,
      ...this.tasks.filter((task) => !task.cancelled),
    )
    for (const task of cancelled) task.callback()
  }

  #nextIndex(maximum: number): number {
    let selected = -1
    for (let index = 0; index < this.tasks.length; index++) {
      const task = this.tasks[index]
      if (task.at > maximum) continue
      if (selected < 0 || task.at < this.tasks[selected].at) selected = index
    }
    return selected
  }
}

async function write(
  scheduler: TerminalScheduler,
  runtime: ManualRuntime,
  value: string,
): Promise<void> {
  const completed = scheduler.enqueueFrame(utf8(value))
  await runtime.flushCurrent()
  await completed
}

async function writeBytes(
  scheduler: TerminalScheduler,
  runtime: ManualRuntime,
  bytes: Uint8Array,
): Promise<void> {
  const completed = scheduler.enqueueFrame(bytes)
  await runtime.flushCurrent()
  await completed
}

async function lineIncident(
  scheduler: TerminalScheduler,
  runtime: ManualRuntime,
): Promise<void> {
  await write(scheduler, runtime, 'x'.repeat(32_768))
  await write(scheduler, runtime, 'x\n')
}

describe('terminal attachment scheduler', () => {
  it('runs a large frame in finite 10000-byte tokenizer tasks', async () => {
    const runtime = new ManualRuntime()
    const renders: TerminalProjection[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      createRenderTask: (projection) => {
        renders.push(projection)
        return { run: () => true }
      },
    })

    await write(scheduler, runtime, 'x'.repeat(20_001))
    expect(runtime.executed).toBe(4)
    expect(renders).toHaveLength(3)
    expect(renders.every((projection) => projection.released)).toBe(true)
    expect(scheduler.state).toBe('active')
  })

  it('shares one absolute deadline across tokenizer, model, projection and render', async () => {
    class RecordingTokenizer extends TerminalTokenizer {
      readonly deadlines: number[] = []

      override runTask(
        clock: () => number,
        deadline?: number,
      ): TerminalTaskResult {
        this.deadlines.push(deadline!)
        return super.runTask(clock, deadline)
      }
    }
    class RecordingModel extends TerminalModel {
      readonly applyDeadlines: number[] = []
      readonly projectionDeadlines: number[] = []

      override runApplyTask(clock: () => number, deadline: number) {
        this.applyDeadlines.push(deadline)
        return super.runApplyTask(clock, deadline)
      }

      override runProjectionTask(clock: () => number, deadline: number) {
        this.projectionDeadlines.push(deadline)
        return super.runProjectionTask(clock, deadline)
      }
    }
    const runtime = new ManualRuntime()
    const tokenizer = new RecordingTokenizer()
    const model = new RecordingModel(8, 1)
    const renderDeadlines: number[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      tokenizer,
      model,
      createRenderTask: () => ({
        run: (_clock, deadline) => {
          renderDeadlines.push(deadline)
          return true
        },
      }),
    })
    await write(scheduler, runtime, 'safe')
    expect(tokenizer.deadlines).toEqual([5])
    expect(model.applyDeadlines).toEqual([5])
    expect(model.projectionDeadlines).toEqual([5])
    expect(renderDeadlines).toEqual([5])
  })

  it('resumes 48000-cell projection and cooperative render before each deadline', async () => {
    const runtime = new ManualRuntime()
    runtime.clockStep = 0.0002
    const model = new TerminalModel(240, 200)
    model.applyTokens([{ kind: 'text', text: 'x'.repeat(48_000) }])
    let renderedCells = 0
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
      createRenderTask: (projection) => ({
        run: (clock, deadline) => {
          while (renderedCells < projection.columns * projection.rows) {
            if (clock() >= deadline) return false
            renderedCells++
          }
          return true
        },
      }),
    })
    scheduler.resize(240, 200)
    await runtime.flushCurrent()
    expect(renderedCells).toBe(48_000)
    expect(runtime.executed).toBeGreaterThan(2)
    expect(scheduler.state).toBe('active')
  })

  it('starts a large resize as resumable scheduler work', async () => {
    const runtime = new ManualRuntime()
    runtime.clockStep = 0.02
    const model = new TerminalModel(240, 200)
    model.applyTokens([{ kind: 'text', text: 'x'.repeat(48_000) }])
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
    })

    scheduler.resize(8, 1)
    expect([model.columns, model.rows]).toEqual([240, 200])
    expect(() => scheduler.enqueueFrame(utf8('late'))).toThrow(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_BUSY'),
    )
    await runtime.flushCurrent()
    expect(runtime.executed).toBeGreaterThan(1)
    expect([model.columns, model.rows]).toEqual([8, 1])
    expect(scheduler.state).toBe('active')
  })

  it('services the exact 100 ms carry deadline while idle and never resets it', async () => {
    const runtime = new ManualRuntime()
    const fences: TerminalSchedulerFence[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      onFence: (event) => fences.push(event),
    })
    await write(scheduler, runtime, '\x1b[')
    await runtime.advanceTo(99)
    expect(scheduler.state).toBe('active')
    await runtime.advanceTo(100)
    expect(scheduler.state).toBe('fenced')
    expect(fences).toEqual([
      { reason: 'TERMINAL_PARSE_LIMIT', attachmentEpoch: 1 },
    ])
  })

  it('preserves the tokenizer logical-line count across arbitrary waiting', async () => {
    const runtime = new ManualRuntime()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
    })
    await write(scheduler, runtime, 'x'.repeat(32_768))
    await runtime.advanceTo(60_000)
    expect(scheduler.state).toBe('active')
    await write(scheduler, runtime, 'overflow\nsafe')
    expect(scheduler.state).toBe('active')
    expect(scheduler.consecutiveIncidentWindows).toBe(0)
    await runtime.advanceTo(61_000)
    expect(scheduler.consecutiveIncidentWindows).toBe(1)
  })

  it('fences immediately when tokenizer state needs reset', async () => {
    const runtime = new ManualRuntime()
    const fences: TerminalSchedulerFence[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      onFence: (event) => fences.push(event),
    })
    const pending = scheduler.enqueueFrame(new Uint8Array(257))
    await runtime.flushCurrent()
    await expect(pending).rejects.toEqual(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'),
    )
    expect(scheduler.state).toBe('fenced')
    expect(fences[0]?.reason).toBe('TERMINAL_PARSE_LIMIT')
  })

  it('rejects an oversized frame before tokenizer admission or LF scanning', () => {
    class CountingTokenizer extends TerminalTokenizer {
      beginCalls = 0
      ownedCalls = 0

      override beginFrame(bytes: Uint8Array): void {
        this.beginCalls++
        super.beginFrame(bytes)
      }

      override beginOwnedFrame(bytes: Uint8Array): void {
        this.ownedCalls++
        super.beginOwnedFrame(bytes)
      }
    }
    const runtime = new ManualRuntime()
    const tokenizer = new CountingTokenizer()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      tokenizer,
    })

    expect(() => scheduler.enqueueFrame(new Uint8Array(32_769))).toThrow(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'),
    )
    expect(tokenizer.beginCalls).toBe(0)
    expect(tokenizer.ownedCalls).toBe(0)
    expect(tokenizer.pendingFrameBytes).toBe(0)
  })

  it('uses bounded indexed snapshot reads when a Uint8Array overrides iteration', async () => {
    class HostileIterator extends Uint8Array {
      override [Symbol.iterator](): ArrayIterator<number> {
        throw new Error('iterator must not run')
      }
    }
    const runtime = new ManualRuntime()
    const tokenizer = new TerminalTokenizer()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      tokenizer,
    })
    const pending = scheduler.enqueueFrame(new HostileIterator([0x0a]))
    expect(tokenizer.pendingFrameBytes).toBe(1)
    scheduler.cancelAttachment()
    await expect(pending).rejects.toEqual(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_CANCELLED'),
    )
  })

  it('rejects a near-limit frame before copying raw or decoded token backlog', () => {
    const runtime = new ManualRuntime()
    const model = new TerminalModel(240, 200)
    model.applyTokens([{ kind: 'text', text: 'e\u0301\u0301'.repeat(48_000) }])
    expect(model.retainedPayloadBytes).toBe(240_000)
    const tokenizer = new TerminalTokenizer()
    const fences: TerminalSchedulerFence[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
      tokenizer,
      onFence: (event) => fences.push(event),
    })

    expect(() => scheduler.enqueueFrame(new Uint8Array(32_768))).toThrow(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'),
    )
    expect(tokenizer.pendingFrameBytes).toBe(0)
    expect(scheduler.state).toBe('fenced')
    expect(fences).toEqual([
      { reason: 'TERMINAL_PARSE_LIMIT', attachmentEpoch: 1 },
    ])
  })

  it('accounts invalid-byte expansion and decoded token backlog at admission', () => {
    const runtime = new ManualRuntime()
    const model = new TerminalModel(240, 200)
    model.applyTokens([{ kind: 'text', text: 'e\u0301\u0301'.repeat(40_000) }])
    expect(model.retainedPayloadBytes).toBe(200_000)
    const tokenizer = new TerminalTokenizer()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
      tokenizer,
    })

    // Raw bytes alone would fit (200,000 + 20,000), but each invalid byte can
    // decode to U+FFFD and a task-local token string overlaps model content.
    expect(() =>
      scheduler.enqueueFrame(new Uint8Array(20_000).fill(0xff)),
    ).toThrow(new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'))
    expect(tokenizer.pendingFrameBytes).toBe(0)
  })

  it('uses the exact U+061C expansion boundary for decoded reservation', async () => {
    class TransferTrackingTokenizer extends TerminalTokenizer {
      copiedFrames = 0
      ownedFrames = 0

      override beginFrame(bytes: Uint8Array): void {
        this.copiedFrames++
        super.beginFrame(bytes)
      }

      override beginOwnedFrame(bytes: Uint8Array): void {
        this.ownedFrames++
        super.beginOwnedFrame(bytes)
      }
    }
    const frame = utf8('\u061c'.repeat(10_000))
    expect(frame.byteLength).toBe(20_000)
    // 20,000 raw + 70,000 complete-frame expansion + 35,000 task overlap.
    const exactModelBytes = 262_144 - 125_000
    const filler = 'e\u0301'.repeat(45_714) + 'é'
    expect(new TextEncoder().encode(filler).byteLength).toBe(exactModelBytes)

    const runtime = new ManualRuntime()
    const tokenizer = new TransferTrackingTokenizer()
    const exact = new TerminalModel(240, 200)
    exact.applyTokens([{ kind: 'text', text: filler }])
    expect(exact.retainedPayloadBytes).toBe(exactModelBytes)
    const accepted = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model: exact,
      tokenizer,
    })
    const pending = accepted.enqueueFrame(frame)
    expect(accepted.state).toBe('active')
    expect(tokenizer.ownedFrames).toBe(1)
    expect(tokenizer.copiedFrames).toBe(0)
    expect(tokenizer.pendingFrameBytes).toBe(frame.byteLength)
    accepted.cancelAttachment()
    await expect(pending).rejects.toEqual(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_CANCELLED'),
    )

    const rejected = new TerminalModel(240, 200)
    rejected.applyTokens([{ kind: 'text', text: `${filler}e` }])
    const denied = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model: rejected,
    })
    expect(() => denied.enqueueFrame(frame)).toThrow(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'),
    )
  })

  it('reserves the four-byte cross-frame UTF-8 carry expansion', async () => {
    const exactModelBytes = 262_127
    const filler =
      'e\u0301\u0301\u0301'.repeat(11_066) + 'e\u0301\u0301'.repeat(36_933)
    expect(new TextEncoder().encode(filler).byteLength).toBe(exactModelBytes)

    const runtime = new ManualRuntime()
    const model = new TerminalModel(240, 200)
    const tokenizer = new TerminalTokenizer()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
      tokenizer,
    })
    await writeBytes(scheduler, runtime, new Uint8Array([0xe2, 0x80]))
    expect(tokenizer.pendingUtf8CarryReservationBytes).toBe(4)
    model.applyTokens([{ kind: 'text', text: filler }])
    // Raw 1 + decoded 8 + token/model overlap 8 exactly reaches 256 KiB.
    const completion = scheduler.enqueueFrame(new Uint8Array([0x8e]))
    await runtime.flushCurrent()
    await completion
    expect(scheduler.state).toBe('active')

    const rejectedRuntime = new ManualRuntime()
    const rejectedModel = new TerminalModel(240, 200)
    const rejectedTokenizer = new TerminalTokenizer()
    const rejectedScheduler = new TerminalScheduler({
      clock: rejectedRuntime.clock,
      schedule: rejectedRuntime.schedule,
      model: rejectedModel,
      tokenizer: rejectedTokenizer,
    })
    await writeBytes(
      rejectedScheduler,
      rejectedRuntime,
      new Uint8Array([0xe2, 0x80]),
    )
    rejectedModel.applyTokens([{ kind: 'text', text: `${filler}e` }])
    expect(() =>
      rejectedScheduler.enqueueFrame(new Uint8Array([0x8e])),
    ).toThrow(new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'))

    const invalidRuntime = new ManualRuntime()
    const invalidModel = new TerminalModel(240, 200)
    const invalidScheduler = new TerminalScheduler({
      clock: invalidRuntime.clock,
      schedule: invalidRuntime.schedule,
      model: invalidModel,
    })
    await writeBytes(invalidScheduler, invalidRuntime, new Uint8Array([0xd8]))
    invalidModel.applyTokens([{ kind: 'text', text: filler }])
    await writeBytes(invalidScheduler, invalidRuntime, new Uint8Array([0xff]))
    expect(invalidScheduler.state).toBe('active')

    const d8Runtime = new ManualRuntime()
    const d8Model = new TerminalModel(240, 200)
    const d8Scheduler = new TerminalScheduler({
      clock: d8Runtime.clock,
      schedule: d8Runtime.schedule,
      model: d8Model,
    })
    await writeBytes(d8Scheduler, d8Runtime, new Uint8Array([0xd8]))
    d8Model.applyTokens([{ kind: 'text', text: filler }])
    await writeBytes(d8Scheduler, d8Runtime, new Uint8Array([0x9c]))
    expect(d8Scheduler.state).toBe('active')
  })

  it('reserves newline backlog before a 2000-line model can accept a frame', () => {
    const runtime = new ManualRuntime()
    const model = new TerminalModel(8, 200)
    model.applyTokens(
      Array.from({ length: 2_000 }, () => [
        { kind: 'text', text: 'x' } as const,
        { kind: 'control', control: 'LF' } as const,
      ]).flat(),
    )
    expect(model.retainedLogicalLines).toBe(2_000)
    const tokenizer = new TerminalTokenizer()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
      tokenizer,
    })

    expect(() => scheduler.enqueueFrame(utf8('\n'))).toThrow(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'),
    )
    expect(tokenizer.pendingFrameBytes).toBe(0)
  })

  it('keeps model ownership plus J2/LF reservation within 2000 lines every callback', async () => {
    const runtime = new ManualRuntime()
    runtime.clockStep = 0.02
    const model = new TerminalModel(8, 200)
    model.applyTokens(
      Array.from({ length: 1_799 }, () => [
        { kind: 'text', text: 'x' } as const,
        { kind: 'control', control: 'LF' } as const,
        { kind: 'control', control: 'CR' } as const,
      ]).flat(),
    )
    expect(model.retainedLogicalLines).toBe(1_800)
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
    })
    runtime.afterCallback = () => {
      expect(model.effectiveRetainedLogicalLines).toBeLessThanOrEqual(2_000)
    }
    const frame = utf8(`\x1b[2J${'\n'.repeat(200)}`)
    const pending = scheduler.enqueueFrame(frame)
    expect(model.effectiveRetainedLogicalLines).toBe(2_000)

    let settled = false
    pending.then(() => {
      settled = true
    })
    for (let turns = 0; turns < 20_000 && !settled; turns++) {
      await runtime.flushCurrent()
      if (settled) break
      const next = Math.min(
        ...runtime.tasks
          .filter((task) => !task.cancelled)
          .map((task) => task.at),
      )
      if (Number.isFinite(next) && next > runtime.now) {
        await runtime.advanceTo(next)
      }
    }
    await pending
    expect(model.effectiveRetainedLogicalLines).toBeLessThanOrEqual(2_000)
    expect(scheduler.state).toBe('active')
  })

  it('does not transfer a future-task LF reservation to an earlier bottom VT', async () => {
    const runtime = new ManualRuntime()
    const model = new TerminalModel(8, 1)
    model.applyTokens(
      Array.from({ length: 1_998 }, () => [
        { kind: 'text', text: 'x' } as const,
        { kind: 'control', control: 'LF' } as const,
        { kind: 'control', control: 'CR' } as const,
      ]).flat(),
    )
    expect(model.retainedLogicalLines).toBe(1_999)
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      model,
    })
    runtime.afterCallback = () => {
      expect(model.effectiveRetainedLogicalLines).toBeLessThanOrEqual(2_000)
    }
    const frame = utf8(`\x0b${'x'.repeat(10_000)}\n`)
    const pending = scheduler.enqueueFrame(frame)
    await runtime.flushCurrent()
    await pending
    expect(scheduler.state).toBe('active')
    expect(model.effectiveRetainedLogicalLines).toBeLessThanOrEqual(2_000)
  })

  it('fences after three consecutive recoverable fixed-window incidents', async () => {
    const runtime = new ManualRuntime()
    const fences: TerminalSchedulerFence[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      onFence: (event) => fences.push(event),
    })

    await lineIncident(scheduler, runtime)
    await runtime.advanceTo(1000)
    expect(scheduler.consecutiveIncidentWindows).toBe(1)
    await lineIncident(scheduler, runtime)
    await runtime.advanceTo(2000)
    expect(scheduler.consecutiveIncidentWindows).toBe(2)
    await lineIncident(scheduler, runtime)
    await runtime.advanceTo(3000)
    expect(scheduler.state).toBe('fenced')
    expect(fences.at(-1)?.reason).toBe('TERMINAL_PARSE_LIMIT')
  })

  it('uses one quiet fixed window to reset the consecutive count', async () => {
    const runtime = new ManualRuntime()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
    })
    await lineIncident(scheduler, runtime)
    await runtime.advanceTo(1000)
    expect(scheduler.consecutiveIncidentWindows).toBe(1)
    await runtime.advanceTo(2000)
    expect(scheduler.consecutiveIncidentWindows).toBe(0)

    await lineIncident(scheduler, runtime)
    await runtime.advanceTo(3000)
    await lineIncident(scheduler, runtime)
    await runtime.advanceTo(4000)
    expect(scheduler.consecutiveIncidentWindows).toBe(2)
    expect(scheduler.state).toBe('active')
  })

  it('splits CPU across fixed windows, carries the remainder and throttles above 50 ms', async () => {
    const runtime = new ManualRuntime()
    const renderDurations = [0, 6, 50, 0]
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      createRenderTask: () => ({
        run: () => {
          runtime.now += renderDurations.shift() ?? 0
          return true
        },
      }),
    })
    await write(scheduler, runtime, 'a')
    runtime.now = 995
    await write(scheduler, runtime, 'b')
    expect(runtime.now).toBe(1001)
    await write(scheduler, runtime, 'c')
    expect(runtime.now).toBe(1051)

    let settled = false
    const pending = scheduler.enqueueFrame(utf8('d'))
    pending.then(() => {
      settled = true
    })
    await runtime.flushCurrent()
    expect(settled).toBe(false)
    expect(scheduler.state).toBe('active')
    await runtime.advanceTo(1999)
    expect(settled).toBe(false)
    await runtime.advanceTo(2000)
    expect(settled).toBe(true)
    await pending
    expect(scheduler.consecutiveIncidentWindows).toBe(1)
    expect(scheduler.state).toBe('active')
  })

  it('limits the final callback after 49 ms to the remaining 1 ms', async () => {
    const runtime = new ManualRuntime()
    const renderDurations = [49, 1]
    const deadlines: number[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      createRenderTask: () => ({
        run: (_clock, deadline) => {
          deadlines.push(deadline)
          runtime.now += renderDurations.shift() ?? 0
          return true
        },
      }),
    })
    await write(scheduler, runtime, 'a')
    await write(scheduler, runtime, 'b')
    expect(deadlines).toEqual([5, 50])
    expect(runtime.now).toBe(50)

    let settled = false
    const pending = scheduler.enqueueFrame(utf8('c'))
    pending.then(() => {
      settled = true
    })
    await runtime.flushCurrent()
    expect(settled).toBe(false)
    expect(scheduler.state).toBe('active')
  })

  it('throttles at exactly 50 ms without recording a parser incident', async () => {
    const runtime = new ManualRuntime()
    let renders = 0
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      createRenderTask: () => ({
        run: () => {
          renders++
          runtime.now += 50
          return true
        },
      }),
    })

    await write(scheduler, runtime, 'a')
    const pending = scheduler.enqueueFrame(utf8('b'))
    await runtime.flushCurrent()
    expect(renders).toBe(1)
    await runtime.advanceTo(1000)
    await pending
    expect(renders).toBe(2)
    expect(scheduler.consecutiveIncidentWindows).toBe(0)
    expect(scheduler.state).toBe('active')
  })

  it('apportions 999 to 1001 and does not exceed either fixed window', async () => {
    const runtime = new ManualRuntime()
    const renderDurations = [2, 49, 0]
    const deadlines: number[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      createRenderTask: () => ({
        run: (_clock, deadline) => {
          deadlines.push(deadline)
          runtime.now += renderDurations.shift() ?? 0
          return true
        },
      }),
    })

    runtime.now = 999
    await write(scheduler, runtime, 'a')
    expect(runtime.now).toBe(1001)
    await write(scheduler, runtime, 'b')
    expect(runtime.now).toBe(1050)
    expect(deadlines).toEqual([1000, 1006])

    let settled = false
    const pending = scheduler.enqueueFrame(utf8('c'))
    pending.then(() => {
      settled = true
    })
    await runtime.flushCurrent()
    expect(settled).toBe(false)
    await runtime.advanceTo(2000)
    await pending
    expect(scheduler.consecutiveIncidentWindows).toBe(0)
    expect(scheduler.state).toBe('active')
  })

  it('apportions a multi-window callback and fences the third CPU incident', async () => {
    const runtime = new ManualRuntime()
    const renderDurations = [2001, 999]
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      createRenderTask: () => ({
        run: () => {
          runtime.now += renderDurations.shift() ?? 0
          return true
        },
      }),
    })
    await write(scheduler, runtime, 'a')
    expect(scheduler.consecutiveIncidentWindows).toBe(2)
    await write(scheduler, runtime, 'b')
    expect(scheduler.state).toBe('fenced')
  })

  it('invalidates late render work and write promises with the attachment epoch', async () => {
    const runtime = new ManualRuntime()
    let captured: TerminalProjection | null = null
    let cancelled = 0
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      createRenderTask: (projection) => {
        captured = projection
        return {
          run: () => false,
          cancel: () => {
            cancelled++
          },
        }
      },
    })
    const pending = scheduler.enqueueFrame(utf8('private'))
    await runtime.runNextCurrent()
    expect(captured).not.toBeNull()
    const run = captured!.lines[0].runs[0]
    const oldEpoch = scheduler.attachmentEpoch
    scheduler.cancelAttachment()
    await expect(pending).rejects.toEqual(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_CANCELLED'),
    )
    expect(scheduler.attachmentEpoch).toBe(oldEpoch + 1)
    expect(run.text).toBe('')
    expect(cancelled).toBe(1)
    runtime.runCancelled()
    expect(scheduler.state).toBe('cancelled')
    expect(runtime.tasks.filter((task) => !task.cancelled)).toHaveLength(0)
  })

  it('maps a clock failure inside running renderer work to the clock fence', async () => {
    const runtime = new ManualRuntime()
    const fences: TerminalSchedulerFence[] = []
    let rendererReadsClock = false
    const scheduler = new TerminalScheduler({
      clock: () => {
        if (rendererReadsClock) throw new Error('private clock failure')
        return runtime.clock()
      },
      schedule: runtime.schedule,
      onFence: (event) => fences.push(event),
      createRenderTask: () => ({
        run: (clock) => {
          rendererReadsClock = true
          try {
            clock()
          } finally {
            rendererReadsClock = false
          }
          return true
        },
      }),
    })

    const pending = scheduler.enqueueFrame(utf8('safe'))
    await runtime.flushCurrent()
    await expect(pending).rejects.toEqual(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_FENCED'),
    )
    expect(scheduler.state).toBe('fenced')
    expect(fences).toEqual([
      { reason: 'TERMINAL_SCHEDULER_INVALID_CLOCK', attachmentEpoch: 1 },
    ])
  })

  it('makes cancelled carry/window callbacks inert without synthetic success', async () => {
    const runtime = new ManualRuntime()
    const fences: TerminalSchedulerFence[] = []
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      onFence: (event) => fences.push(event),
    })
    await write(scheduler, runtime, '\x1b[')
    scheduler.cancelAttachment()
    runtime.now = 10_000
    runtime.runCancelled()
    expect(scheduler.state).toBe('cancelled')
    expect(scheduler.consecutiveIncidentWindows).toBe(0)
    expect(fences).toEqual([
      { reason: 'ATTACHMENT_CANCELLED', attachmentEpoch: 1 },
    ])
  })

  it('clears the copied frame reservation on cancellation', async () => {
    const runtime = new ManualRuntime()
    const tokenizer = new TerminalTokenizer()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
      tokenizer,
    })
    const pending = scheduler.enqueueFrame(utf8('private frame'))
    expect(tokenizer.pendingFrameBytes).toBe('private frame'.length)
    scheduler.cancelAttachment()
    await expect(pending).rejects.toEqual(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_CANCELLED'),
    )
    expect(tokenizer.pendingFrameBytes).toBe(0)
  })

  it('destroy permanently rejects frames and resize and is idempotent', () => {
    const runtime = new ManualRuntime()
    const scheduler = new TerminalScheduler({
      clock: runtime.clock,
      schedule: runtime.schedule,
    })
    scheduler.destroy()
    scheduler.destroy()
    expect(scheduler.state).toBe('destroyed')
    expect(() => scheduler.enqueueFrame(utf8('late'))).toThrow(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_DESTROYED'),
    )
    expect(() => scheduler.resize(120, 32)).toThrow(
      new TerminalSchedulerError('TERMINAL_SCHEDULER_DESTROYED'),
    )
  })
})
