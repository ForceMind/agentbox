import type {
  WAWBrowserCryptoPort,
  WAWBrowserSchedule,
  WAWBrowserSocketHandlers,
  WAWBrowserSocketPort,
  WAWBrowserTerminalSchedulerPort,
} from './wawBrowserController'
import type { KeyFrame } from './wawCryptoProfile'

/**
 * Closed, test-only rendezvous points for rc7 composed failure tests. They are
 * deliberately names rather than caller-defined labels so diagnostics cannot
 * accidentally retain a ticket, key, or terminal payload.
 */
export const WAW_RC7_CHECKPOINTS = Object.freeze([
  'ticket-issued',
  'trust-authorized',
  'socket-open',
  'key-init',
  'key-attest',
  'key-confirm',
  'admitted',
  'input-encrypt',
  'input-send',
  'output-decrypt',
  'output-render',
  'resize-send',
  'heartbeat-send',
  'detach-cleanup',
  'stop-request',
] as const)

export type WAWRc7Checkpoint = (typeof WAW_RC7_CHECKPOINTS)[number]

export type WAWRc7Gate = {
  readonly promise: Promise<void>
  readonly state: 'pending' | 'resolved' | 'rejected'
  resolve(): void
  /** Reject only with the closed rc7 error; never retain caller error text. */
  reject(): void
  /** Drop resolver closures after a scenario no longer needs the deferred. */
  dispose(): void
}

export function createWAWRc7Gate(): WAWRc7Gate {
  let state: 'pending' | 'resolved' | 'rejected' = 'pending'
  let resolvePromise: (() => void) | null = null
  let rejectPromise: ((reason: Error) => void) | null = null
  const promise = new Promise<void>((resolve, reject) => {
    resolvePromise = resolve
    rejectPromise = reject
  })
  // A failure-injection test may intentionally release a rejected operation.
  void promise.catch(() => undefined)
  return {
    promise,
    get state() {
      return state
    },
    resolve() {
      if (state !== 'pending')
        throw new Error('rc7 deferred is already settled')
      const settle = resolvePromise
      resolvePromise = null
      rejectPromise = null
      state = 'resolved'
      if (settle === null)
        throw new Error('rc7 deferred resolver is unavailable')
      settle()
    },
    reject() {
      if (state !== 'pending')
        throw new Error('rc7 deferred is already settled')
      const settle = rejectPromise
      resolvePromise = null
      rejectPromise = null
      state = 'rejected'
      if (settle === null)
        throw new Error('rc7 deferred resolver is unavailable')
      settle(new Error('rc7 deferred rejected'))
    },
    dispose() {
      if (state === 'pending') {
        const settle = rejectPromise
        state = 'rejected'
        resolvePromise = null
        rejectPromise = null
        settle?.(new Error('rc7 deferred disposed'))
        return
      }
      resolvePromise = null
      rejectPromise = null
    },
  }
}

type CheckpointSlot = {
  readonly arrival: WAWRc7Gate
  readonly release: WAWRc7Gate
  arrived: boolean
  released: boolean
  departed: boolean
}

export class WAWRc7Checkpoints {
  readonly #slots: readonly CheckpointSlot[]
  readonly #sequence: readonly WAWRc7Checkpoint[]
  #next = 0

  constructor(sequence: readonly WAWRc7Checkpoint[]) {
    if (sequence.length < 1) throw new Error('rc7 checkpoint sequence is empty')
    for (const checkpoint of sequence) this.#assertKnown(checkpoint)
    this.#sequence = Object.freeze([...sequence])
    this.#slots = Object.freeze(
      sequence.map(() => ({
        arrival: createWAWRc7Gate(),
        release: createWAWRc7Gate(),
        arrived: false,
        released: false,
        departed: false,
      })),
    )
  }

  arrive(checkpoint: WAWRc7Checkpoint): Promise<void> {
    this.#assertKnown(checkpoint)
    const index = this.#next
    if (index === this.#sequence.length) {
      throw new Error('rc7 checkpoint arrived after declared sequence')
    }
    if (this.#sequence[index] !== checkpoint) {
      throw new Error('rc7 checkpoint arrived out of declared order')
    }
    const slot = this.#slots[index]
    this.#next += 1
    slot.arrived = true
    slot.arrival.resolve()
    return slot.release.promise.then(
      () => {
        slot.departed = true
      },
      (error: unknown) => {
        slot.departed = true
        throw error
      },
    )
  }

  reached(checkpoint: WAWRc7Checkpoint, occurrence = 1): Promise<void> {
    return this.#slot(checkpoint, occurrence).arrival.promise
  }

  release(checkpoint: WAWRc7Checkpoint, occurrence = 1): void {
    const slot = this.#slot(checkpoint, occurrence)
    if (!slot.arrived) throw new Error('rc7 checkpoint has not arrived')
    if (slot.released) throw new Error('rc7 checkpoint is already released')
    slot.released = true
    slot.release.resolve()
  }

  fail(checkpoint: WAWRc7Checkpoint, occurrence = 1): void {
    const slot = this.#slot(checkpoint, occurrence)
    if (!slot.arrived) throw new Error('rc7 checkpoint has not arrived')
    if (slot.released) throw new Error('rc7 checkpoint is already released')
    slot.released = true
    slot.release.reject()
  }

  assertComplete(): void {
    const pending = this.#sequence.filter(
      (_checkpoint, index) => !this.#slots[index].departed,
    )
    if (pending.length > 0) {
      throw new Error(
        `rc7 checkpoint sequence is incomplete: ${pending.join(', ')}`,
      )
    }
  }

  #slot(checkpoint: WAWRc7Checkpoint, occurrence: number): CheckpointSlot {
    this.#assertKnown(checkpoint)
    if (!Number.isSafeInteger(occurrence) || occurrence < 1) {
      throw new Error('rc7 checkpoint occurrence is invalid')
    }
    let matched = 0
    for (const [index, name] of this.#sequence.entries()) {
      if (name !== checkpoint) continue
      matched += 1
      if (matched === occurrence) return this.#slots[index]
    }
    throw new Error('rc7 checkpoint is not in declared sequence')
  }

  #assertKnown(checkpoint: WAWRc7Checkpoint): void {
    if (!WAW_RC7_CHECKPOINTS.includes(checkpoint)) {
      throw new Error('unknown rc7 checkpoint')
    }
  }
}

export class WAWRc7FakeClock {
  #now: number

  constructor(initialNow = 0) {
    if (!Number.isFinite(initialNow) || initialNow < 0) {
      throw new Error('invalid rc7 clock value')
    }
    this.#now = initialNow
  }

  now = (): number => this.#now

  advanceTo(nextNow: number): void {
    if (!Number.isFinite(nextNow) || nextNow < this.#now) {
      throw new Error('rc7 clock cannot move backwards')
    }
    this.#now = nextNow
  }

  advanceBy(milliseconds: number): void {
    if (!Number.isFinite(milliseconds) || milliseconds < 0) {
      throw new Error('rc7 clock cannot move backwards')
    }
    this.advanceTo(this.#now + milliseconds)
  }
}

export type WAWRc7SocketState = 'connecting' | 'open' | 'closing' | 'closed'

export class WAWRc7BrowserSocket implements WAWBrowserSocketPort {
  binaryType = 'arraybuffer' as const
  #state: WAWRc7SocketState = 'connecting'
  #protocol = ''
  #bufferedAmount = 0
  #sendFailure: Error | null = null
  #handlers: WAWBrowserSocketHandlers | null = null
  readonly #sent: Uint8Array[] = []

  get readyState(): number {
    return { connecting: 0, open: 1, closing: 2, closed: 3 }[this.#state]
  }

  get bufferedAmount(): number {
    return this.#bufferedAmount
  }

  get protocol(): string {
    return this.#protocol
  }

  get state(): WAWRc7SocketState {
    return this.#state
  }

  /** Non-secret metadata is retained; test bytes require one-shot extraction. */
  get sentMetadata(): readonly {
    readonly requested: number
    readonly digest: string
  }[] {
    return this.#sent.map((bytes) => ({
      requested: bytes.byteLength,
      digest: digest(bytes),
    }))
  }

  subscribe(handlers: WAWBrowserSocketHandlers): () => void {
    this.#handlers = handlers
    return () => {
      if (this.#handlers === handlers) this.#handlers = null
    }
  }

  send(bytes: Uint8Array): void {
    if (this.#sendFailure !== null) throw this.#sendFailure
    if (this.#state !== 'open') throw new Error('socket is not open')
    this.#sent.push(new Uint8Array(bytes))
  }

  takeSentBytes(): readonly Uint8Array[] {
    const values = this.#sent.map((bytes) => new Uint8Array(bytes))
    for (const bytes of this.#sent) bytes.fill(0)
    this.#sent.length = 0
    return values
  }

  close(): void {
    if (this.#state === 'closed') return
    this.#state = 'closed'
    this.#scrub()
  }

  open(protocol: string): void {
    if (this.#state !== 'connecting') throw new Error('socket cannot open')
    this.#state = 'open'
    this.#protocol = protocol
    this.#handlers?.open()
  }

  message(data: ArrayBuffer): void {
    if (this.#state !== 'open') throw new Error('socket is not open')
    this.#handlers?.message(data)
  }

  error(): void {
    this.#handlers?.error()
  }

  remoteClose(code = 1006, wasClean = false): void {
    if (this.#state === 'closed') return
    this.#state = 'closed'
    this.#handlers?.close({ code, wasClean })
    this.#scrub()
  }

  setBufferedAmount(bytes: number): void {
    if (!Number.isSafeInteger(bytes) || bytes < 0) {
      throw new Error('invalid socket buffered amount')
    }
    this.#bufferedAmount = bytes
  }

  failSends(error: Error | null): void {
    this.#sendFailure =
      error === null ? null : new Error('rc7 injected send failure')
  }

  assertDrained(): void {
    if (
      this.#sent.length !== 0 ||
      this.#sendFailure !== null ||
      this.#handlers !== null ||
      this.#bufferedAmount !== 0
    ) {
      throw new Error('rc7 browser socket retained scenario state')
    }
  }

  #scrub(): void {
    for (const bytes of this.#sent) bytes.fill(0)
    this.#sent.length = 0
    this.#sendFailure = null
    this.#handlers = null
    this.#bufferedAmount = 0
    this.#protocol = ''
  }
}

function digest(bytes: Uint8Array): string {
  let value = 0x811c9dc5
  for (const byte of bytes) value = Math.imul(value ^ byte, 0x01000193)
  return (value >>> 0).toString(16).padStart(8, '0')
}

export type WAWRc7CryptoDelegate = Pick<WAWBrowserCryptoPort, 'destroy'> & {
  readonly state: string
  writeKeyInit(): Promise<KeyFrame>
  readKeyAttest(frame: unknown): Promise<KeyFrame>
  readKeyConfirmAck(frame: unknown): Promise<void>
  encryptInput(plaintext: Uint8Array): Promise<Uint8Array>
  decryptOutput(
    ciphertext: Uint8Array,
    expectedCursor: bigint,
  ): Promise<Uint8Array>
}

export class WAWRc7DeferredCrypto implements WAWBrowserCryptoPort {
  readonly #delegate: WAWRc7CryptoDelegate
  readonly #checkpoints: WAWRc7Checkpoints

  constructor(delegate: WAWRc7CryptoDelegate, checkpoints: WAWRc7Checkpoints) {
    this.#delegate = delegate
    this.#checkpoints = checkpoints
  }

  get state(): string {
    return this.#delegate.state
  }
  async writeKeyInit(): Promise<KeyFrame> {
    await this.#checkpoints.arrive('key-init')
    return this.#delegate.writeKeyInit()
  }
  async readKeyAttest(frame: unknown): Promise<KeyFrame> {
    await this.#checkpoints.arrive('key-attest')
    return this.#delegate.readKeyAttest(frame)
  }
  async readKeyConfirmAck(frame: unknown): Promise<void> {
    await this.#delegate.readKeyConfirmAck(frame)
    await this.#checkpoints.arrive('key-confirm')
  }
  async encryptInput(plaintext: Uint8Array): Promise<Uint8Array> {
    await this.#checkpoints.arrive('input-encrypt')
    return this.#delegate.encryptInput(plaintext)
  }
  async decryptOutput(
    ciphertext: Uint8Array,
    expectedCursor: bigint,
  ): Promise<Uint8Array> {
    await this.#checkpoints.arrive('output-decrypt')
    return this.#delegate.decryptOutput(ciphertext, expectedCursor)
  }
  destroy(): void {
    this.#delegate.destroy()
  }
}

export class WAWRc7DeferredRenderer implements WAWBrowserTerminalSchedulerPort {
  readonly #delegate: WAWBrowserTerminalSchedulerPort
  readonly #checkpoints: WAWRc7Checkpoints

  constructor(
    delegate: WAWBrowserTerminalSchedulerPort,
    checkpoints: WAWRc7Checkpoints,
  ) {
    this.#delegate = delegate
    this.#checkpoints = checkpoints
  }

  async enqueueFrame(bytes: Uint8Array): Promise<void> {
    const pending = this.#delegate.enqueueFrame(bytes)
    await this.#checkpoints.arrive('output-render')
    await pending
  }
  resize(columns: number, rows: number): void {
    this.#delegate.resize(columns, rows)
  }
  cancelAttachment(): void {
    this.#delegate.cancelAttachment()
  }
}

export function createWAWRc7Schedule(clock: WAWRc7FakeClock): {
  readonly schedule: WAWBrowserSchedule
  runDue(): void
  assertDrained(): void
} {
  const timers = new Set<{
    readonly at: number
    callback: (() => void) | null
    cancelled: boolean
  }>()
  return {
    schedule(callback, delayMs) {
      const timer: {
        readonly at: number
        callback: (() => void) | null
        cancelled: boolean
      } = {
        at: clock.now() + Math.max(0, delayMs),
        callback,
        cancelled: false,
      }
      timers.add(timer)
      return () => {
        timer.cancelled = true
        timer.callback = null
        timers.delete(timer)
      }
    },
    runDue() {
      for (;;) {
        const next = [...timers]
          .filter((timer) => !timer.cancelled && timer.at <= clock.now())
          .sort((left, right) => left.at - right.at)[0]
        if (next === undefined) return
        next.cancelled = true
        timers.delete(next)
        const callback = next.callback
        next.callback = null
        callback?.()
      }
    },
    assertDrained() {
      if (timers.size !== 0) throw new Error('rc7 scheduler retained callbacks')
    },
  }
}
