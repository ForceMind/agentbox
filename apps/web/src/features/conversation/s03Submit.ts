/**
 * Isolated, explicitly constructed synthetic S03 submit fixture. No production
 * caller, authentication grant, network route, body reader or ephemeral input.
 * NX authenticates responder possession only. Public fixture keys are not secrets.
 */
import { NXInitiator, type NoiseTransport } from '../workspace/noiseNx'
import { parseConversationScope } from './conversationObservation'

export const S03_LIMITS = Object.freeze({
  body: 16_384,
  ciphertext: 16_400,
  base64: 21_867,
  raw: 22_031,
  framed: 22_035,
  channel: 1_048_576,
  relay: 262_144,
  metadata: 261_120,
  metadataRecord: 627,
  metadataConstruction: 2_508,
  webOwnedCopies: 615_006,
})
export type S03Code =
  's03_unavailable' | 's03_invalid' | 's03_busy' | 's03_revoked'
const CODES = [
  's03_unavailable',
  's03_invalid',
  's03_busy',
  's03_revoked',
] as const
function normalizeCode(value: unknown): S03Code {
  return typeof value === 'string' &&
    (CODES as readonly string[]).includes(value)
    ? (value as S03Code)
    : 's03_invalid'
}
export class S03Error extends Error {
  readonly code: S03Code
  constructor(code: S03Code) {
    super(normalizeCode(code))
    this.name = 'S03Error'
    this.code = normalizeCode(code)
    Object.freeze(this)
  }
}
function publicCode(value: unknown): S03Code {
  // Foreign throwables (including subclasses/Proxy/getters/forged instances)
  // cannot choose diagnostic text. Read only an own data descriptor, then
  // normalize again even for our frozen Error type.
  let code: unknown
  try {
    if (
      value &&
      typeof value === 'object' &&
      Object.getPrototypeOf(value) === S03Error.prototype
    ) {
      const descriptor = Object.getOwnPropertyDescriptor(value, 'code')
      if (descriptor && 'value' in descriptor) code = descriptor.value
    }
  } catch {
    /* no foreign exception survives */
  }
  return normalizeCode(code)
}
function fail(code: S03Code = 's03_invalid'): never {
  throw new S03Error(code)
}
const encoder = new TextEncoder()
const DOMAIN = 'agentbox-s03-submit/frame/v1'
const CONTEXT = 'agentbox-s03-submit/context/v1\0'
const PROLOGUE = 'agentbox-s03-submit/noise-prologue/v1\0'
const AAD = 'agentbox-s03-submit/aad/v1\0'
const MAX_U64 = (1n << 64n) - 1n
const HANDSHAKE_NS = 2_000_000_000n
const TOKEN = Symbol('synthetic S03 construction')
const fields = [
  'owner_scope',
  'auth_epoch',
  'project_id',
  'project_revision',
  'binding_revision',
  'binding_digest',
  'host_id',
  'host_revision',
  'runtime_epoch',
  'api_authority_epoch',
  'agent_type',
  'execution_kind',
  'conversation_id',
  'conversation_revision',
  'generation',
  'turn_id',
  'execution_id',
  'request_id',
  'channel_id',
  'source_lease_id',
  'adapter_profile',
] as const
export type S03Context = Readonly<
  Record<(typeof fields)[number] | 'runtime_pin', string>
>
export type S03Kind =
  'KEY_INIT' | 'KEY_ATTEST' | 'KEY_CONFIRM' | 'KEY_READY' | 'SUBMIT'
const kinds = [
  'KEY_INIT',
  'KEY_ATTEST',
  'KEY_CONFIRM',
  'KEY_READY',
  'SUBMIT',
] as const
const dataLengths = [32, 96, 111, 109] as const
const scopeFields = fields.slice(0, 16)
const typedArrayPrototype = Object.getPrototypeOf(Uint8Array.prototype)
const typedBuffer = Object.getOwnPropertyDescriptor(
  typedArrayPrototype,
  'buffer',
)!.get!
const typedLength = Object.getOwnPropertyDescriptor(
  typedArrayPrototype,
  'byteLength',
)!.get!
const arrayLength = Object.getOwnPropertyDescriptor(
  ArrayBuffer.prototype,
  'byteLength',
)!.get!
const arrayResizable = Object.getOwnPropertyDescriptor(
  ArrayBuffer.prototype,
  'resizable',
)?.get
const arrayDetached = Object.getOwnPropertyDescriptor(
  ArrayBuffer.prototype,
  'detached',
)?.get

function record(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    Object.getPrototypeOf(value) !== Object.prototype
  )
    fail()
  const names = Reflect.ownKeys(value)
  if (
    names.length !== keys.length ||
    names.some((key) => typeof key !== 'string' || !keys.includes(key))
  )
    fail()
  const result: Record<string, unknown> = {}
  for (const key of keys) {
    const d = Object.getOwnPropertyDescriptor(value, key)
    if (!d || !d.enumerable || !('value' in d)) fail()
    result[key] = d.value
  }
  return result
}
function isHex(value: unknown, n: number): value is string {
  return (
    typeof value === 'string' && value.length === n && /^[a-f0-9]+$/.test(value)
  )
}
function checkedBytes(
  value: unknown,
  minimum: number,
  maximum: number,
): Uint8Array {
  // Intrinsics reject Proxy, SAB, Buffer, subclasses and fake/prototyped views
  // without invoking user getters. A transparent Proxy is not a trusted root.
  if (
    !value ||
    typeof value !== 'object' ||
    Object.getPrototypeOf(value) !== Uint8Array.prototype
  )
    fail()
  const buffer = typedBuffer.call(value)
  if (Object.getPrototypeOf(buffer) !== ArrayBuffer.prototype) fail()
  arrayLength.call(buffer)
  if (arrayResizable?.call(buffer) || arrayDetached?.call(buffer)) fail()
  const length = typedLength.call(value)
  if (length < minimum || length > maximum) fail()
  // Constructing a zero-length view detects detached buffers on older engines.
  new Uint8Array(buffer, 0, 0)
  // Fixed-name checks never enumerate all numeric or arbitrary own keys.
  // In particular, do not read/call a caller-controlled iterator. All ingress
  // reaching the unchanged primitive is first copied/decoded into owned arrays.
  // Its constructor/length/buffer/slice accesses therefore see no caller hooks.
  for (const key of [
    'buffer',
    'byteLength',
    'byteOffset',
    'length',
    'constructor',
    Symbol.iterator,
  ]) {
    if (Object.hasOwn(value, key)) fail()
  }
  return value as Uint8Array
}
function safe<T>(operation: () => T): T {
  let result: T | undefined
  let okay = false
  try {
    result = operation()
    okay = true
  } catch {
    /* discard foreign errors */
  }
  if (!okay) fail()
  return result as T
}
function parseContext(value: unknown): S03Context {
  const row = record(value, [...fields, 'runtime_pin'])
  const scope: Record<string, unknown> = {}
  for (const key of scopeFields) scope[key] = row[key]
  parseConversationScope(scope)
  for (const [key, prefix] of [
    ['execution_id', 'kexe_'],
    ['request_id', 'kreq_'],
    ['channel_id', 'ks03c_'],
    ['source_lease_id', 'ks03l_'],
  ]) {
    const item = row[key]
    if (
      typeof item !== 'string' ||
      !item.startsWith(prefix) ||
      !isHex(item.slice(prefix.length), 32)
    )
      fail()
  }
  if (
    row.adapter_profile !== 'kebui-synthetic-adapter-v1' ||
    !isHex(row.runtime_pin, 64)
  )
    fail()
  return Object.freeze(row) as S03Context
}
function fromHex(value: string): Uint8Array {
  const result = new Uint8Array(value.length / 2)
  for (let i = 0; i < result.length; i++)
    result[i] = Number.parseInt(value.slice(i * 2, i * 2 + 2), 16)
  return result
}
function hex(value: Uint8Array): string {
  let result = ''
  const length = typedLength.call(value)
  for (let i = 0; i < length; i++)
    result += value[i].toString(16).padStart(2, '0')
  return result
}
function concat(...parts: Uint8Array[]): Uint8Array {
  const output = new Uint8Array(
    parts.reduce((sum, part) => sum + part.length, 0),
  )
  let at = 0
  for (const part of parts) {
    output.set(part, at)
    at += part.length
  }
  return output
}
/** Public codec/vector utility. It cannot mint a root or an admission permit. */
export function buildContext(value: unknown): Uint8Array {
  return safe(() => {
    const context = parseContext(value)
    const length =
      CONTEXT.length +
      32 +
      fields.reduce((n, key) => n + 2 + context[key].length, 0)
    if (length > 739) fail()
    const output = new Uint8Array(length)
    output.set(encoder.encode(CONTEXT))
    const view = new DataView(output.buffer)
    let at = CONTEXT.length
    for (const key of fields) {
      const item = context[key]
      view.setUint16(at, item.length, false)
      at += 2
      for (let i = 0; i < item.length; i++) output[at++] = item.charCodeAt(i)
    }
    output.set(fromHex(context.runtime_pin), at)
    return output
  })
}
export function buildPrologue(context: Uint8Array): Uint8Array {
  return safe(() =>
    concat(encoder.encode(PROLOGUE), checkedBytes(context, 1, 739)),
  )
}
export function buildAAD(
  cd: Uint8Array,
  hh: Uint8Array,
  kind: 'KEY_CONFIRM' | 'KEY_READY' | 'SUBMIT',
): Uint8Array {
  return safe(() => {
    checkedBytes(cd, 32, 32)
    checkedBytes(hh, 32, 32)
    if (kind !== 'KEY_CONFIRM' && kind !== 'KEY_READY' && kind !== 'SUBMIT')
      fail()
    const result = new Uint8Array(101)
    result.set(encoder.encode(AAD))
    result.set(cd, AAD.length)
    result.set(hh, AAD.length + 32)
    result[91] = kind === 'KEY_READY' ? 1 : 0
    result[92] = kind === 'KEY_CONFIRM' ? 3 : kind === 'KEY_READY' ? 4 : 5
    new DataView(result.buffer).setBigUint64(
      93,
      kind === 'SUBMIT' ? 1n : 0n,
      false,
    )
    return result
  })
}
export function buildCanary(
  cd: Uint8Array,
  hh: Uint8Array,
  kind: 'KEY_CONFIRM' | 'KEY_READY',
): Uint8Array {
  return safe(() => {
    checkedBytes(cd, 32, 32)
    checkedBytes(hh, 32, 32)
    if (kind !== 'KEY_CONFIRM' && kind !== 'KEY_READY') fail()
    return concat(
      encoder.encode(
        `agentbox-s03-submit/${kind === 'KEY_CONFIRM' ? 'confirm' : 'ready'}/v1\0`,
      ),
      cd,
      hh,
    )
  })
}
const alphabet =
  'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
function base64(data: Uint8Array): Uint8Array {
  const output = new Uint8Array(Math.ceil((data.length * 4) / 3))
  let at = 0
  for (let i = 0; i < data.length; i += 3) {
    const n = (data[i] << 16) | ((data[i + 1] ?? 0) << 8) | (data[i + 2] ?? 0)
    output[at++] = alphabet.charCodeAt((n >>> 18) & 63)
    output[at++] = alphabet.charCodeAt((n >>> 12) & 63)
    if (i + 1 < data.length) output[at++] = alphabet.charCodeAt((n >>> 6) & 63)
    if (i + 2 < data.length) output[at++] = alphabet.charCodeAt(n & 63)
  }
  return output
}
function frameShape(kind: S03Kind, seq: number, length: number): void {
  const index = kinds.indexOf(kind)
  if (index < 0 || seq !== (kind === 'SUBMIT' ? 1 : 0)) fail()
  if (
    index === 4
      ? length < 17 || length > S03_LIMITS.ciphertext
      : length !== dataLengths[index]
  )
    fail()
}
export function encodeFrame(
  cd: string,
  kind: S03Kind,
  seq: number,
  value: Uint8Array,
): Uint8Array {
  return safe(() => {
    if (!isHex(cd, 64)) fail()
    checkedBytes(value, 1, S03_LIMITS.ciphertext)
    frameShape(kind, seq, value.length)
    const prefix = encoder.encode(`{"context":"${cd}","data":"`)
    const suffix = encoder.encode(
      `","domain":"${DOMAIN}","kind":"${kind}","seq":${seq},"version":1}`,
    )
    return concat(prefix, base64(value), suffix)
  })
}
export type S03Frame = Readonly<{
  context: string
  kind: S03Kind
  seq: number
  data: Uint8Array
}>
export function decodeFrame(
  raw: Uint8Array,
  cd?: string,
  kind?: S03Kind,
  seq?: number,
): S03Frame {
  return safe(() => {
    checkedBytes(raw, 1, S03_LIMITS.raw)
    // Bounded ASCII conversion and flat anchored scanner: no JSON parser, nested
    // allocations, permissive escapes or decoding prior to the complete bound.
    const rawLength = typedLength.call(raw)
    for (let i = 0; i < rawLength; i++) if (raw[i] > 127) fail()
    const text = new TextDecoder('utf-8', {
      fatal: true,
      ignoreBOM: true,
    }).decode(raw)
    const match =
      /^\{"context":"([a-f0-9]{64})","data":"([A-Za-z0-9_-]+)","domain":"agentbox-s03-submit\/frame\/v1","kind":"(KEY_INIT|KEY_ATTEST|KEY_CONFIRM|KEY_READY|SUBMIT)","seq":([01]),"version":1\}$/.exec(
        text,
      )
    if (!match || match[0].length !== text.length) fail()
    const capturedKind = match[3] as S03Kind
    const capturedSeq = Number(match[4])
    if (
      (cd !== undefined && match[1] !== cd) ||
      (kind !== undefined && capturedKind !== kind) ||
      (seq !== undefined && capturedSeq !== seq)
    )
      fail()
    const encoded = match[2]
    if (encoded.length > S03_LIMITS.base64 || encoded.length % 4 === 1) fail()
    const length = Math.floor((encoded.length * 3) / 4)
    frameShape(capturedKind, capturedSeq, length)
    const last = alphabet.indexOf(encoded[encoded.length - 1])
    if (
      (encoded.length % 4 === 2 && last & 15) ||
      (encoded.length % 4 === 3 && last & 3)
    )
      fail()
    const data = new Uint8Array(length)
    let accumulator = 0,
      bits = 0,
      at = 0
    for (let i = 0; i < encoded.length; i++) {
      accumulator = (accumulator << 6) | alphabet.indexOf(encoded[i])
      bits += 6
      if (bits >= 8) {
        bits -= 8
        data[at++] = (accumulator >>> bits) & 255
      }
    }
    return Object.freeze({
      context: match[1],
      kind: capturedKind,
      seq: capturedSeq,
      data,
    })
  })
}
export const decodeS03Frame = decodeFrame
function equal(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  let delta = 0
  for (let i = 0; i < a.length; i++) delta |= a[i] ^ b[i]
  return delta === 0
}

/** Trusted, fixed test pipe. close must unregister and settle a pending read or
 * capacity wait. write performs exactly one synchronous whole-record write. */
export interface SyntheticS03Endpoint {
  waitWritable(signal: AbortSignal): Promise<void>
  read(signal: AbortSignal): Promise<Uint8Array>
  write(raw: Uint8Array): boolean
  close(): void
}
type Phase =
  'NEW' | 'INIT_SENT' | 'CONFIRM_SENT' | 'READY' | 'SUBMIT_ATTEMPTED' | 'CLOSED'
type CopyClass =
  | 'payload'
  | 'validation'
  | 'cipher'
  | 'base64'
  | 'wire'
  | 'context'
  | 'aad'
  | 'fixed'
const ceilings: Readonly<Record<CopyClass, number>> = Object.freeze({
  payload: 4 * 16_384,
  validation: 2 * 16_384,
  cipher: 3 * 16_400,
  base64: 8 * 21_867,
  wire: 10 * 22_031,
  context: 8 * 739,
  aad: 8 * 101,
  fixed: 65_536,
})
class Workspace {
  readonly live = {
    payload: 0,
    validation: 0,
    cipher: 0,
    base64: 0,
    wire: 0,
    context: 0,
    aad: 0,
    fixed: 0,
  }
  readonly peak = { ...this.live }
  charge(kind: CopyClass, amount: number): void {
    this.live[kind] += amount
    if (this.live[kind] > ceilings[kind]) fail('s03_busy')
    this.peak[kind] = Math.max(this.peak[kind], this.live[kind])
  }
  clear(kind: CopyClass): void {
    this.live[kind] = 0
  }
  retire(): void {
    for (const kind of Object.keys(this.live) as CopyClass[]) this.clear(kind)
  }
}
// The fixed harness owns exactly one realm and one module instance. This is
// not a multi-vm/iframe/worker process-global authority or production guarantee.
let liveRoot: object | undefined
const tombstones: Uint8Array[] = []
let metadataReserved = 0
let metadataBytes = 0
function processReserved(): number {
  return (
    (liveRoot ? S03_LIMITS.channel : 0) +
    (relayOwner ? S03_LIMITS.relay : 0) +
    metadataReserved
  )
}
function sameTombstoneBinding(
  candidate: Uint8Array,
  previous: Uint8Array,
  prefixEnd: number,
  channelEnd: number,
): boolean {
  let prefixSame = true,
    channelSame = true,
    leaseSame = true
  let field = 0,
    channelLength = 0,
    leaseLength = 0
  // One bounded byte-span pass; no decoded old strings, copies or hidden index.
  for (let i = 0; i < previous.length; i++) {
    const byte = previous[i]
    if (field < 18) {
      if (byte === 124 && ++field === 18) {
        prefixSame = prefixSame && i === prefixEnd
        continue
      }
      prefixSame = prefixSame && i < prefixEnd && byte === candidate[i]
    } else if (field === 18) {
      if (byte === 124) {
        field++
        channelSame =
          channelSame && channelLength === channelEnd - prefixEnd - 1
        continue
      }
      channelSame =
        channelSame &&
        prefixEnd + 1 + channelLength < channelEnd &&
        byte === candidate[prefixEnd + 1 + channelLength]
      channelLength++
    } else {
      leaseSame =
        leaseSame &&
        channelEnd + 1 + leaseLength < candidate.length &&
        byte === candidate[channelEnd + 1 + leaseLength]
      leaseLength++
    }
  }
  leaseSame = leaseSame && leaseLength === candidate.length - channelEnd - 1
  return prefixSame || channelSame || leaseSame
}
function retainTombstone(state: State): void {
  // Capacity was checked BEFORE root/context construction. Recheck immediately
  // before the only join/encode, with the live channel reservation still held.
  if (tombstones.length >= 255) fail('s03_busy')
  let joined: string | undefined
  let encoded: Uint8Array | undefined
  try {
    joined = fields
      .slice(0, 20)
      .map((key) => state.context![key])
      .join('|')
    if (joined.length > S03_LIMITS.metadataRecord) fail()
    encoded = encoder.encode(joined)
    state.metadataConstructionPeak = joined.length * 2 + encoded.length
    if (state.metadataConstructionPeak > S03_LIMITS.metadataConstruction)
      fail('s03_busy')
    let delimiters = 0,
      prefixEnd = 0,
      channelEnd = 0
    for (let i = 0; i < encoded.length; i++) {
      if (encoded[i] !== 124) continue
      delimiters++
      if (delimiters === 18) prefixEnd = i
      else if (delimiters === 19) channelEnd = i
    }
    if (
      tombstones.some((previous) =>
        sameTombstoneBinding(encoded!, previous, prefixEnd, channelEnd),
      )
    )
      fail('s03_revoked')
    // Transfer this exact single ordinary byte array to the persistent owner.
    // It is never returned, modified, decoded, copied or erased on close.
    tombstones.push(encoded)
    metadataBytes += encoded.length
    encoded = undefined
  } finally {
    joined = undefined
    encoded = undefined
  }
}
let generation = 0
let relayOwner: object | undefined
/** The fixed harness reserves its relay in the SAME realm-wide ledger. Release
 * only after its pipe callbacks/accumulators have actually drained. */
export function reserveRelayForTest() {
  if (relayOwner) fail('s03_busy')
  const identity = Object.freeze({})
  relayOwner = identity
  return Object.freeze({
    release(): void {
      if (relayOwner === identity) relayOwner = undefined
    },
    snapshot() {
      return Object.freeze({
        reserved: relayOwner === identity ? S03_LIMITS.relay : 0,
        processReserved: processReserved(),
        metadataReserved,
        metadataBytes,
        metadataEntries: tombstones.length,
      })
    },
  })
}

type State = {
  identity: object
  generation: number
  endpointIdentity: SyntheticS03Endpoint
  endpoint: SyntheticS03Endpoint
  context?: S03Context
  pin?: Uint8Array
  cd?: Uint8Array
  cdHex?: string
  handshake?: NXInitiator
  transport?: NoiseTransport
  deadline?: DeadlineOwner
  phase: Phase
  busy: boolean
  opened: boolean
  retired: boolean
  writes: number
  submitWrites: number
  publicationAttempted: boolean
  sendCounter: number
  receiveCounter: number
  metadataConstructionPeak: number
  workspace: Workspace
}
function retire(state: State): void {
  if (state.phase !== 'CLOSED' || state.busy || state.retired) return
  state.context = undefined
  state.pin = undefined
  state.cd = undefined
  state.cdHex = undefined
  state.deadline = undefined
  state.workspace.retire()
  state.retired = true
  if (liveRoot === state.identity) liveRoot = undefined
}
function close(state: State): void {
  if (state.phase !== 'CLOSED') {
    state.phase = 'CLOSED'
    state.handshake?.destroy()
    state.handshake = undefined
    state.transport?.destroy()
    state.transport = undefined
    state.deadline?.close()
    try {
      state.endpoint.close()
    } catch {
      /* fixed failure only; no exception retained */
    }
  }
  retire(state)
}
class DeadlineOwner {
  readonly signal: AbortSignal
  readonly expired: Promise<void>
  #controller = new AbortController()
  #resolve!: () => void
  #timer?: ReturnType<typeof setTimeout>
  #waiter?: () => void
  #clock: () => bigint
  #floor: bigint
  #target: bigint
  #original: bigint
  #closed = false
  #state: State
  constructor(state: State, clock: () => bigint, original: bigint) {
    this.#state = state
    this.#clock = clock
    this.signal = this.#controller.signal
    this.expired = new Promise((resolve) => {
      this.#resolve = resolve
    })
    this.#floor = this.readInitial()
    if (
      typeof original !== 'bigint' ||
      original <= this.#floor ||
      original > MAX_U64 ||
      this.#floor > MAX_U64 - HANDSHAKE_NS
    )
      fail()
    this.#original = original
    this.#target =
      original < this.#floor + HANDSHAKE_NS
        ? original
        : this.#floor + HANDSHAKE_NS
    this.arm()
  }
  private readInitial(): bigint {
    const value = this.#clock()
    if (typeof value !== 'bigint' || value < 0n || value > MAX_U64)
      fail('s03_revoked')
    return value
  }
  check(): void {
    if (this.#closed) fail('s03_revoked')
    let valid = false
    try {
      const now = this.readInitial()
      valid =
        !this.#closed &&
        this.#state.phase !== 'CLOSED' &&
        now >= this.#floor &&
        now < this.#target
      if (valid) this.#floor = now
    } catch {
      /* fixed, no foreign clock message */
    }
    if (!valid) {
      safe(() => close(this.#state))
      fail('s03_revoked')
    }
  }
  ready(): void {
    this.check()
    this.#target = this.#original
    this.arm()
  }
  private arm(): void {
    if (this.#timer !== undefined) clearTimeout(this.#timer)
    const remaining = this.#target - this.#floor
    const ms = Number((remaining + 999_999n) / 1_000_000n)
    this.#timer = setTimeout(() => this.dispatch(), Math.min(ms, 2_147_483_647))
  }
  dispatch(): void {
    if (this.#timer !== undefined) clearTimeout(this.#timer)
    this.#timer = undefined
    try {
      this.check()
      this.arm()
    } catch {
      safe(() => close(this.#state))
    }
  }
  close(): void {
    if (this.#closed) return
    this.#closed = true
    if (this.#timer !== undefined) clearTimeout(this.#timer)
    this.#timer = undefined
    this.#resolve()
    this.#controller.abort()
    this.#waiter?.()
  }
  async wait<T>(operation: Promise<T>): Promise<T> {
    if (this.#waiter) fail('s03_busy')
    // One removable expiry listener; unlike repeated Promise.race(expired), old
    // completed waits cannot leave accumulating reactions on the shared promise.
    const outcome = { okay: false }
    let value: T | undefined
    let settle!: () => void
    const settled = new Promise<void>((resolve) => {
      settle = resolve
    })
    const observed = operation.then(
      (result) => {
        value = result
        outcome.okay = true
        settle()
      },
      () => {
        outcome.okay = false
        settle()
      },
    )
    this.#waiter = settle
    if (this.#closed) {
      outcome.okay = false
      settle()
    }
    await settled
    this.#waiter = undefined
    // On expiry, abort/close has requested cancellation. Reservation remains
    // charged until the actual adapter continuation retires, even if it is slow.
    await observed
    if (this.#closed) {
      value = undefined
      fail('s03_revoked')
    }
    if (!outcome.okay) {
      value = undefined
      fail('s03_unavailable')
    }
    this.check()
    return value as T
  }
}
function guard(state: State, phase: Phase): void {
  if (
    state.phase !== phase ||
    liveRoot !== state.identity ||
    state.retired ||
    state.generation !== generation
  )
    fail('s03_revoked')
  state.deadline!.check()
  if (
    state.phase !== phase ||
    liveRoot !== state.identity ||
    state.retired ||
    state.generation !== generation
  )
    fail('s03_revoked')
}
async function publish(
  state: State,
  frame: Uint8Array,
  phase: Phase,
): Promise<void> {
  guard(state, phase)
  await state.deadline!.wait(
    state.endpoint.waitWritable(state.deadline!.signal),
  )
  guard(state, phase)
  // Only fixed metadata mutations occur between the last local observation
  // and the synchronous write; neither calls external/user code.
  state.publicationAttempted = true
  state.writes += 1
  if (phase === 'SUBMIT_ATTEMPTED') state.submitWrites += 1
  if (state.endpoint.write(frame) !== true) fail('s03_unavailable')
  guard(state, phase)
}
async function receive(
  state: State,
  phase: Phase,
  kind: S03Kind,
): Promise<Uint8Array> {
  guard(state, phase)
  const raw = await state.deadline!.wait(
    state.endpoint.read(state.deadline!.signal),
  )
  guard(state, phase)
  checkedBytes(raw, 1, S03_LIMITS.raw)
  state.workspace.charge('wire', raw.length * 4)
  try {
    return decodeFrame(raw, state.cdHex!, kind, 0).data
  } finally {
    state.workspace.clear('wire')
  }
}
async function serial(
  state: State,
  operation: () => Promise<void>,
): Promise<void> {
  if (state.busy) {
    close(state)
    fail('s03_busy')
  }
  if (state.phase === 'CLOSED') fail('s03_revoked')
  state.busy = true
  let error: S03Code | undefined
  try {
    await operation()
  } catch (value) {
    error = publicCode(value)
    close(state)
  } finally {
    state.busy = false
    retire(state)
  }
  if (error) fail(error)
}
export type SyntheticS03FixtureOptions = Readonly<{
  context: unknown
  endpoint: SyntheticS03Endpoint
  clock: () => bigint
  deadline: bigint
}>
export class SyntheticS03TestRoot {
  #state: State
  private constructor(token: symbol, state: State) {
    if (token !== TOKEN || new.target !== SyntheticS03TestRoot)
      fail('s03_unavailable')
    this.#state = state
    Object.freeze(this)
  }
  /** Explicit trusted TEST construction only, never JSON/network bootstrap. */
  static forFixture(options: SyntheticS03FixtureOptions): SyntheticS03TestRoot {
    if (liveRoot !== undefined || tombstones.length >= 255) fail('s03_busy')
    metadataReserved = S03_LIMITS.metadata
    const identity = Object.freeze({})
    liveRoot = identity // whole-channel lane, BEFORE context/pin/clock/key copies
    let state: State | undefined
    let result: SyntheticS03TestRoot | undefined
    let error: S03Code = 's03_invalid'
    try {
      const row = record(options, ['context', 'endpoint', 'clock', 'deadline'])
      const ports = record(row.endpoint, [
        'waitWritable',
        'read',
        'write',
        'close',
      ])
      if (
        Object.values(ports).some((port) => typeof port !== 'function') ||
        typeof row.clock !== 'function'
      )
        fail()
      const endpoint = row.endpoint as SyntheticS03Endpoint
      const bound = Object.freeze({
        waitWritable: endpoint.waitWritable.bind(endpoint),
        read: endpoint.read.bind(endpoint),
        write: endpoint.write.bind(endpoint),
        close: endpoint.close.bind(endpoint),
      })
      state = {
        identity,
        generation: ++generation,
        endpointIdentity: endpoint,
        endpoint: bound,
        phase: 'NEW',
        busy: false,
        opened: false,
        retired: false,
        writes: 0,
        submitWrites: 0,
        publicationAttempted: false,
        sendCounter: 0,
        receiveCounter: 0,
        metadataConstructionPeak: 0,
        workspace: new Workspace(),
      }
      state.workspace.charge('fixed', 65_536)
      state.context = parseContext(row.context)
      retainTombstone(state)
      state.pin = fromHex(state.context.runtime_pin)
      state.workspace.charge('context', 8 * 739)
      state.deadline = new DeadlineOwner(
        state,
        row.clock as () => bigint,
        row.deadline as bigint,
      )
      result = new SyntheticS03TestRoot(TOKEN, state)
    } catch (value) {
      error = publicCode(value)
    }
    if (!result) {
      if (state) close(state)
      else if (liveRoot === identity) liveRoot = undefined
      fail(error)
    }
    return result
  }
  open(endpoint: SyntheticS03Endpoint): SyntheticS03Sender {
    const state = safe(() => this.#state)
    if (state.opened || endpoint !== state.endpointIdentity) {
      close(state)
      fail('s03_revoked')
    }
    guard(state, 'NEW')
    state.opened = true
    return new SyntheticS03Sender(TOKEN, state)
  }
  revoke(): void {
    safe(() => close(this.#state))
  }
  close(): void {
    safe(() => close(this.#state))
  }
  dispatchDeadlineForTest(): void {
    safe(() => this.#state.deadline?.dispatch())
  }
}
export class SyntheticS03Sender {
  #state: State
  constructor(token: symbol, state: State) {
    if (token !== TOKEN || new.target !== SyntheticS03Sender)
      fail('s03_unavailable')
    this.#state = state
    Object.freeze(this)
  }
  handshake(): Promise<void> {
    const state = safe(() => this.#state)
    return serial(state, async () => {
      guard(state, 'NEW')
      state.phase = 'INIT_SENT'
      let context: Uint8Array | undefined = buildContext(state.context)
      state.cd = new Uint8Array(
        await crypto.subtle.digest('SHA-256', context as BufferSource),
      )
      guard(state, 'INIT_SENT')
      state.cdHex = hex(state.cd)
      state.handshake = new NXInitiator(buildPrologue(context)) // fresh primitive keypair only
      context = undefined
      let outgoing: Uint8Array | undefined =
        await state.handshake.writeMessage1()
      guard(state, 'INIT_SENT')
      let frame: Uint8Array | undefined = encodeFrame(
        state.cdHex,
        'KEY_INIT',
        0,
        outgoing,
      )
      outgoing = undefined
      await publish(state, frame, 'INIT_SENT')
      frame = undefined
      let incoming: Uint8Array | undefined = await receive(
        state,
        'INIT_SENT',
        'KEY_ATTEST',
      )
      guard(state, 'INIT_SENT')
      const payload = await state.handshake.readMessage2(incoming)
      incoming = undefined
      guard(state, 'INIT_SENT')
      if (payload.length !== 0) fail()
      state.transport = state.handshake.takeTransport()
      state.handshake = undefined
      if (!equal(state.transport.remote_static_public_key, state.pin!)) fail()
      state.phase = 'CONFIRM_SENT'
      if (state.transport.send.counter !== 0n) fail()
      outgoing = await state.transport.send.encrypt(
        buildCanary(state.cd, state.transport.handshake_hash, 'KEY_CONFIRM'),
        buildAAD(state.cd, state.transport.handshake_hash, 'KEY_CONFIRM'),
      )
      guard(state, 'CONFIRM_SENT')
      state.sendCounter = 1
      frame = encodeFrame(state.cdHex, 'KEY_CONFIRM', 0, outgoing)
      outgoing = undefined
      await publish(state, frame, 'CONFIRM_SENT')
      frame = undefined
      incoming = await receive(state, 'CONFIRM_SENT', 'KEY_READY')
      guard(state, 'CONFIRM_SENT')
      if (state.transport.receive.counter !== 0n) fail()
      let ready: Uint8Array | undefined = await state.transport.receive.decrypt(
        incoming,
        buildAAD(state.cd, state.transport.handshake_hash, 'KEY_READY'),
      )
      incoming = undefined
      guard(state, 'CONFIRM_SENT')
      state.receiveCounter = 1
      if (
        !equal(
          ready,
          buildCanary(state.cd, state.transport.handshake_hash, 'KEY_READY'),
        )
      )
        fail()
      ready = undefined
      state.deadline!.ready()
      state.phase = 'READY'
    })
  }
  submit(input: Uint8Array): Promise<void> {
    const state = safe(() => this.#state)
    // serial invokes this closure synchronously, so reservation/busy validation
    // and snapshot happen before submit returns its first Promise to the caller.
    return serial(state, async () => {
      guard(state, 'READY')
      state.phase = 'SUBMIT_ATTEMPTED'
      let body: Uint8Array | undefined
      let cipher: Uint8Array | undefined
      let frame: Uint8Array | undefined
      try {
        checkedBytes(input, 1, S03_LIMITS.body)
        state.workspace.charge('payload', input.length * 4)
        body = new Uint8Array(input)
        input = new Uint8Array()
        state.workspace.charge('validation', body.length * 2)
        new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(body)
        state.workspace.clear('validation')
        if (state.transport!.send.counter !== 1n) fail()
        state.workspace.charge('aad', 8 * 101)
        cipher = await state.transport!.send.encrypt(
          body,
          buildAAD(state.cd!, state.transport!.handshake_hash, 'SUBMIT'),
        )
        body = undefined
        state.workspace.clear('payload')
        state.workspace.clear('aad')
        guard(state, 'SUBMIT_ATTEMPTED')
        state.sendCounter = 2
        state.workspace.charge('cipher', cipher.length * 3)
        state.workspace.charge('base64', Math.ceil((cipher.length * 4) / 3) * 8)
        frame = encodeFrame(state.cdHex!, 'SUBMIT', 1, cipher)
        cipher = undefined
        state.workspace.clear('cipher')
        state.workspace.clear('base64')
        state.workspace.charge('wire', frame.length * 10)
        await publish(state, frame, 'SUBMIT_ATTEMPTED')
      } finally {
        input = new Uint8Array()
        body = undefined
        cipher = undefined
        frame = undefined
        close(state)
      }
    })
  }
  close(): void {
    safe(() => close(this.#state))
  }
  snapshot() {
    const state = safe(() => this.#state)
    return Object.freeze({
      processReserved: processReserved(),
      metadataReserved,
      metadataBytes,
      metadataEntries: tombstones.length,
      metadataConstructionPeak: state.metadataConstructionPeak,
      phase: state.phase,
      busy: state.busy,
      reserved: state.retired ? 0 : S03_LIMITS.channel,
      writes: state.writes,
      submitWrites: state.submitWrites,
      publicationAttempted: state.publicationAttempted,
      sendCounter: state.sendCounter,
      receiveCounter: state.receiveCounter,
      keysDetached: !state.handshake && !state.transport,
      liveCopies: Object.freeze({ ...state.workspace.live }),
      peakCopies: Object.freeze({ ...state.workspace.peak }),
    })
  }
}
