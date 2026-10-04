/** Inert, memory-only A3 roles. Trusted ports are supplied by an external owner;
 * fixture ports do not establish production admission, pin provenance or revocation. */
import {
  NXInitiator,
  NXResponder,
  type NoiseTransport,
} from '../workspace/noiseNx'
import {
  ContentError,
  ContentRead,
  PROTOCOL_ID,
  applicationAad,
  contextBytes,
  contextDigest,
  decodeMessage,
  validateContext,
  type ContentContext,
  type Message,
  type PatchRead,
} from './a3Content'

export const MAX_ENVELOPE_BYTES = 24 * 1024
export const MAX_CIPHERTEXT_BYTES = 16_400
export const MAX_CIPHERTEXT_BASE64URL = 21_867
export const HANDSHAKE_TIMEOUT_MS = 5000
export interface A3Current {
  readonly context: ContentContext
  readonly nowMs: number
  /** Independently obtained raw X25519 public key, never obtained from the wire. */
  readonly runtimePin: Uint8Array
}
export interface A3TrustedPort {
  current(): A3Current
}
export interface A3Options {
  readonly admissionStartedAtMs: number
  readonly admissionExpiresAtMs: number
  /** Test-only deterministic ephemeral input; omitted for fresh random keys. */
  readonly ephemeralKeyPair?: CryptoKeyPair
}
export type A3State =
  'NEW' | 'WAIT_ATTEST' | 'WAIT_CONFIRM' | 'WAIT_ACK' | 'READY' | 'CLOSED'
type KeyKind =
  'A3_KEY_INIT' | 'A3_KEY_ATTEST' | 'A3_KEY_CONFIRM' | 'A3_KEY_CONFIRM_ACK'
const DOMAIN = 'agentbox-a3-content/record/v1'
const enc = new TextEncoder()
const dec = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true })
const EMPTY = new Uint8Array()
const fail = (): never => {
  throw new ContentError()
}
const equal = (a: Uint8Array, b: Uint8Array): boolean => {
  if (a.length !== b.length) return false
  let different = 0
  for (let i = 0; i < a.length; i++) different |= a[i] ^ b[i]
  return different === 0
}
const hex = (raw: Uint8Array): string =>
  Array.from(raw, (b) => b.toString(16).padStart(2, '0')).join('')
const bytes = (value: Uint8Array, maximum: number): Uint8Array => {
  if (
    !(value instanceof Uint8Array) ||
    value.constructor !== Uint8Array ||
    !value.length ||
    value.length > maximum
  )
    fail()
  return new Uint8Array(value)
}
const canonical = (value: object): Uint8Array =>
  new Uint8Array(
    enc.encode(
      JSON.stringify(
        Object.fromEntries(
          Object.entries(value).sort(([a], [b]) =>
            a < b ? -1 : a > b ? 1 : 0,
          ),
        ),
      ),
    ),
  )
const flat =
  /^\{"[a-z_]+":(?:"[A-Za-z0-9_/:.-]*"|0|[1-9][0-9]*)(?:,"[a-z_]+":(?:"[A-Za-z0-9_/:.-]*"|0|[1-9][0-9]*))*\}$/
function parse(raw: Uint8Array, maximum: number): Record<string, unknown> {
  const copy = bytes(raw, maximum)
  const text = dec.decode(copy)
  if (!flat.test(text)) fail()
  const result = JSON.parse(text) as Record<string, unknown>
  if (Object.keys(result).length > 7 || !equal(canonical(result), copy)) fail()
  return result
}
function keys(r: Record<string, unknown>, expected: string[]): void {
  if (Object.keys(r).sort().join(',') !== expected.sort().join(',')) fail()
}
const encode64 = (value: Uint8Array): string =>
  btoa(String.fromCharCode(...value))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
function decode64(value: unknown, maximum: number, size?: number): Uint8Array {
  if (
    typeof value !== 'string' ||
    !value.length ||
    value.length > Math.ceil((maximum * 4) / 3) ||
    !/^[A-Za-z0-9_-]+$/.test(value)
  )
    fail()
  const raw = Uint8Array.from(
    atob((value as string).replace(/-/g, '+').replace(/_/g, '/')),
    (c) => c.charCodeAt(0),
  )
  if (
    raw.length > maximum ||
    (size !== undefined && raw.length !== size) ||
    encode64(raw) !== value
  )
    fail()
  return raw
}
function sequence(message: Message): number {
  return message.kind === 'PATCH_READ' || message.kind === 'PATCH_ERROR'
    ? 0
    : message.sequence
}
function keyFrame(
  kind: KeyKind,
  data: Uint8Array,
  digest: string,
  transcript?: string,
): Uint8Array {
  return canonical({
    protocol_id: PROTOCOL_ID,
    protocol_version: 1,
    context_digest: digest,
    kind,
    data: encode64(data),
    ...(transcript === undefined ? {} : { transcript_hash: transcript }),
  })
}
function keyData(
  raw: Uint8Array,
  kind: KeyKind,
  digest: string,
  transcript?: string,
): Uint8Array {
  const r = parse(raw, 4096)
  keys(r, [
    'protocol_id',
    'protocol_version',
    'context_digest',
    'kind',
    'data',
    ...(kind === 'A3_KEY_CONFIRM_ACK' ? ['transcript_hash'] : []),
  ])
  if (
    r.protocol_id !== PROTOCOL_ID ||
    r.protocol_version !== 1 ||
    r.kind !== kind ||
    r.context_digest !== digest ||
    (kind === 'A3_KEY_CONFIRM_ACK' && r.transcript_hash !== transcript)
  )
    fail()
  const size = kind === 'A3_KEY_INIT' ? 32 : kind === 'A3_KEY_ATTEST' ? 128 : 48
  return decode64(r.data, size, size)
}
const sha = async (raw: Uint8Array): Promise<Uint8Array> =>
  new Uint8Array(await crypto.subtle.digest('SHA-256', raw as BufferSource))
function confirmation(challenge: Uint8Array, hash: Uint8Array): Uint8Array {
  const prefix = enc.encode('agentbox-a3-content/noise-confirm/v1')
  const result = new Uint8Array(prefix.length + 4 + 32 + 32)
  result.set(prefix)
  new DataView(result.buffer).setUint32(prefix.length, 32, false)
  result.set(challenge, prefix.length + 4)
  result.set(hash, prefix.length + 36)
  return result
}
const time = (n: number): boolean => Number.isSafeInteger(n) && n >= 0

class A3Role {
  readonly #context: ContentContext
  readonly #bound: Uint8Array
  readonly #pin: Uint8Array
  readonly #trusted: A3TrustedPort
  readonly #expires: number
  readonly #handshakeExpires: number
  #last: number
  #state: A3State = 'NEW'
  #busy = false
  #digest?: string
  #transport?: NoiseTransport
  #handshake?: NXInitiator | NXResponder
  #read: ContentRead
  #challenge?: Uint8Array
  protected get challenge(): Uint8Array | undefined {
    return this.#challenge
  }
  protected set challenge(value: Uint8Array | undefined) {
    this.#challenge = value
  }

  constructor(context: unknown, trusted: A3TrustedPort, options: A3Options) {
    this.#context = validateContext(context)
    this.#bound = contextBytes(this.#context)
    this.#trusted = trusted
    const live = trusted.current()
    this.#pin = bytes(live.runtimePin, 32)
    if (
      this.#pin.length !== 32 ||
      !time(live.nowMs) ||
      !time(options.admissionStartedAtMs) ||
      !time(options.admissionExpiresAtMs) ||
      options.admissionStartedAtMs > live.nowMs ||
      options.admissionExpiresAtMs <= live.nowMs ||
      options.admissionExpiresAtMs > options.admissionStartedAtMs + 30_000
    )
      fail()
    this.#expires = options.admissionExpiresAtMs
    this.#handshakeExpires = options.admissionStartedAtMs + HANDSHAKE_TIMEOUT_MS
    this.#last = live.nowMs
    this.#read = new ContentRead(
      this.#context,
      options.admissionStartedAtMs,
      this.#expires,
    )
    this.guard()
  }
  get state(): A3State {
    return this.#state
  }
  toJSON(): { state: A3State } {
    return { state: this.#state }
  }
  close(): void {
    this.#state = 'CLOSED'
    this.#handshake?.destroy()
    this.#handshake = undefined
    this.#transport?.destroy()
    this.#transport = undefined
    this.challenge?.fill(0)
    this.challenge = undefined
    this.#read.close()
  }
  /** Owner calls this on idle revocation/currentness notifications. */
  check(): void {
    try {
      this.guard()
    } catch (error) {
      this.close()
      throw error
    }
  }
  protected guard(): A3Current {
    if (this.#state === 'CLOSED') fail()
    const current = this.#trusted.current()
    if (
      !time(current.nowMs) ||
      current.nowMs < this.#last ||
      current.nowMs >= this.#expires ||
      (this.#state !== 'READY' && current.nowMs >= this.#handshakeExpires) ||
      !equal(contextBytes(current.context), this.#bound) ||
      !equal(bytes(current.runtimePin, 32), this.#pin)
    )
      fail()
    this.#last = current.nowMs
    return current
  }
  protected async checked<T>(promise: Promise<T>): Promise<T> {
    const value = await promise
    this.guard()
    return value
  }
  protected async operation<T>(
    expected: A3State,
    next: A3State,
    work: () => Promise<T>,
    terminal = false,
  ): Promise<T> {
    try {
      if (this.#busy || this.#state !== expected) fail()
      this.#busy = true
      this.guard()
      const result = await work()
      this.guard()
      this.#state = next
      if (terminal) this.close()
      return result
    } catch (error) {
      this.close()
      throw error
    } finally {
      this.#busy = false
    }
  }
  protected get context(): ContentContext {
    return this.#context
  }
  protected get prologue(): Uint8Array {
    return new Uint8Array(this.#bound)
  }
  protected get pin(): Uint8Array {
    return new Uint8Array(this.#pin)
  }
  protected set handshake(value: NXInitiator | NXResponder) {
    this.#handshake = value
  }
  protected set transport(value: NoiseTransport) {
    this.#transport = value
  }
  protected get transport(): NoiseTransport {
    if (!this.#transport) fail()
    return this.#transport!
  }
  protected async digest(): Promise<string> {
    this.#digest ??= await this.checked(contextDigest(this.#context))
    this.guard()
    return this.#digest
  }
  protected async acceptPlain(
    raw: Uint8Array,
  ): Promise<Uint8Array | undefined> {
    const current = this.guard()
    return this.checked(this.#read.accept(raw, current.nowMs, current.context))
  }
  protected validateBound(raw: Uint8Array): Message {
    const message = decodeMessage(raw)
    if (
      message.context_digest !== this.#digest ||
      message.request_nonce !== this.#context.request_nonce
    )
      fail()
    return message
  }
  protected async encrypt(raw: Uint8Array): Promise<Uint8Array> {
    raw = bytes(raw, 16_384)
    const message = this.validateBound(raw)
    const aad = await this.checked(
      applicationAad(
        this.#context,
        hex(this.transport.handshake_hash),
        message.kind,
        sequence(message),
      ),
    )
    if (this.transport.send.counter < 1n) fail()
    const ciphertext = await this.checked(this.transport.send.encrypt(raw, aad))
    const result = canonical({
      domain: DOMAIN,
      context_digest: this.#digest,
      kind: message.kind,
      sequence: sequence(message),
      ciphertext: encode64(ciphertext),
    })
    if (
      result.length > MAX_ENVELOPE_BYTES ||
      ciphertext.length > MAX_CIPHERTEXT_BYTES
    )
      fail()
    return result
  }
  protected async decrypt(raw: Uint8Array, read: boolean): Promise<Uint8Array> {
    const r = parse(raw, MAX_ENVELOPE_BYTES)
    keys(r, ['domain', 'context_digest', 'kind', 'sequence', 'ciphertext'])
    if (
      r.domain !== DOMAIN ||
      r.context_digest !== this.#digest ||
      typeof r.kind !== 'string' ||
      (read
        ? r.kind !== 'PATCH_READ'
        : !['PATCH_PAGE', 'PATCH_END', 'PATCH_ERROR'].includes(r.kind)) ||
      typeof r.sequence !== 'number'
    )
      fail()
    const aad = await this.checked(
      applicationAad(
        this.#context,
        hex(this.transport.handshake_hash),
        r.kind as Message['kind'],
        r.sequence as number,
      ),
    )
    const ciphertext = decode64(r.ciphertext, MAX_CIPHERTEXT_BYTES)
    if (ciphertext.length < 16 || this.transport.receive.counter < 1n) fail()
    const plaintext = await this.checked(
      this.transport.receive.decrypt(ciphertext, aad),
    )
    const message = this.validateBound(plaintext)
    if (message.kind !== r.kind || sequence(message) !== r.sequence) fail()
    return plaintext
  }
}

/** Browser owns verification and only publishes the whole patch after END. */
export class A3Browser extends A3Role {
  #ephemeral?: CryptoKeyPair
  #nx?: NXInitiator
  constructor(context: unknown, trusted: A3TrustedPort, options: A3Options) {
    super(context, trusted, options)
    this.#ephemeral = options.ephemeralKeyPair
  }
  override close(): void {
    this.#ephemeral = undefined
    this.#nx = undefined
    super.close()
  }
  start(): Promise<Uint8Array> {
    return this.operation('NEW', 'WAIT_ATTEST', async () => {
      const digest = await this.checked(this.digest())
      this.#nx = new NXInitiator(this.prologue, this.#ephemeral)
      this.#ephemeral = undefined
      this.handshake = this.#nx
      const data = await this.checked(this.#nx.writeMessage1())
      return keyFrame('A3_KEY_INIT', data, digest)
    })
  }
  acceptAttest(raw: Uint8Array): Promise<Uint8Array> {
    return this.operation('WAIT_ATTEST', 'WAIT_ACK', async () => {
      raw = bytes(raw, 4096)
      const digest = await this.checked(this.digest())
      this.challenge = await this.checked(
        this.#nx!.readMessage2(keyData(raw, 'A3_KEY_ATTEST', digest)),
      )
      this.transport = this.#nx!.takeTransport()
      if (
        this.challenge.length !== 32 ||
        !equal(this.transport.remote_static_public_key, this.pin) ||
        this.transport.send.counter !== 0n
      )
        fail()
      const proof = await this.checked(
        sha(confirmation(this.challenge, this.transport.handshake_hash)),
      )
      const data = await this.checked(this.transport.send.encrypt(proof, EMPTY))
      return keyFrame('A3_KEY_CONFIRM', data, digest)
    })
  }
  acceptAck(raw: Uint8Array): Promise<void> {
    return this.operation('WAIT_ACK', 'READY', async () => {
      raw = bytes(raw, 4096)
      const digest = await this.checked(this.digest())
      if (this.transport.receive.counter !== 0n) fail()
      const proof = await this.checked(
        this.transport.receive.decrypt(
          keyData(
            raw,
            'A3_KEY_CONFIRM_ACK',
            digest,
            hex(this.transport.handshake_hash),
          ),
          EMPTY,
        ),
      )
      const expected = await this.checked(
        sha(enc.encode('agentbox-a3-content/noise-confirm-ack/v1')),
      )
      if (!equal(proof, expected)) fail()
      this.challenge?.fill(0)
      this.challenge = undefined
    })
  }
  encryptRead(raw: Uint8Array): Promise<Uint8Array> {
    return this.operation('READY', 'READY', async () => {
      raw = bytes(raw, 4096)
      if (this.validateBound(raw).kind !== 'PATCH_READ') fail()
      await this.checked(this.acceptPlain(raw))
      return this.checked(this.encrypt(raw))
    })
  }
  acceptResponse(raw: Uint8Array): Promise<Uint8Array | undefined> {
    return this.operation('READY', 'READY', async () => {
      const plaintext = await this.checked(this.decrypt(raw, false))
      const result = await this.checked(this.acceptPlain(plaintext))
      return result
    }).then((result) => {
      // No await between the final currentness fence and plaintext publication.
      this.check()
      if (result !== undefined) this.close()
      return result
    })
  }
}

/** Runtime fixture role; no key loading, admission, resolver or production I/O. */
export class A3Runtime extends A3Role {
  #nx: NXResponder
  readonly #staticPublic: CryptoKey
  #started = false
  constructor(
    context: unknown,
    trusted: A3TrustedPort,
    options: A3Options,
    staticKeyPair: CryptoKeyPair,
  ) {
    super(context, trusted, options)
    this.#staticPublic = staticKeyPair.publicKey
    this.#nx = new NXResponder(
      this.prologue,
      staticKeyPair,
      options.ephemeralKeyPair,
    )
    this.handshake = this.#nx
  }
  acceptInit(raw: Uint8Array): Promise<Uint8Array> {
    return this.operation('NEW', 'WAIT_CONFIRM', async () => {
      raw = bytes(raw, 4096)
      const digest = await this.checked(this.digest())
      const own = new Uint8Array(
        await this.checked(crypto.subtle.exportKey('raw', this.#staticPublic)),
      )
      if (!equal(own, this.pin)) fail()
      const payload = await this.checked(
        this.#nx.readMessage1(keyData(raw, 'A3_KEY_INIT', digest)),
      )
      if (payload.length !== 0) fail()
      this.challenge = crypto.getRandomValues(new Uint8Array(32))
      const data = await this.checked(this.#nx.writeMessage2(this.challenge))
      this.transport = this.#nx.takeTransport()
      return keyFrame('A3_KEY_ATTEST', data, digest)
    })
  }
  acceptConfirm(raw: Uint8Array): Promise<Uint8Array> {
    return this.operation('WAIT_CONFIRM', 'READY', async () => {
      raw = bytes(raw, 4096)
      const digest = await this.checked(this.digest())
      if (
        this.transport.receive.counter !== 0n ||
        this.transport.send.counter !== 0n
      )
        fail()
      const proof = await this.checked(
        this.transport.receive.decrypt(
          keyData(raw, 'A3_KEY_CONFIRM', digest),
          EMPTY,
        ),
      )
      const expected = await this.checked(
        sha(confirmation(this.challenge!, this.transport.handshake_hash)),
      )
      if (!equal(proof, expected)) fail()
      const ack = await this.checked(
        sha(enc.encode('agentbox-a3-content/noise-confirm-ack/v1')),
      )
      const data = await this.checked(this.transport.send.encrypt(ack, EMPTY))
      this.challenge?.fill(0)
      this.challenge = undefined
      return keyFrame(
        'A3_KEY_CONFIRM_ACK',
        data,
        digest,
        hex(this.transport.handshake_hash),
      )
    })
  }
  decryptRead(raw: Uint8Array): Promise<PatchRead> {
    return this.operation('READY', 'READY', async () => {
      if (this.#started) fail()
      const plaintext = await this.checked(this.decrypt(raw, true))
      await this.checked(this.acceptPlain(plaintext))
      this.#started = true
      return this.validateBound(plaintext) as PatchRead
    })
  }
  encryptResponse(raw: Uint8Array): Promise<Uint8Array> {
    let terminal = false
    return this.operation('READY', 'READY', async () => {
      if (!this.#started) fail()
      raw = bytes(raw, 16_384)
      const message = this.validateBound(raw)
      if (message.kind === 'PATCH_READ') fail()
      terminal = message.kind === 'PATCH_END' || message.kind === 'PATCH_ERROR'
      if (message.kind !== 'PATCH_ERROR')
        await this.checked(this.acceptPlain(raw))
      return this.checked(this.encrypt(raw))
    }).then((result) => {
      this.check()
      if (terminal) this.close()
      return result
    })
  }
}
