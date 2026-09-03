/** Memory-only application profile. Admission, trust provisioning and sockets are external. */
import {
  decodeAwce,
  encodeAwceHeader,
  HEADER_SIZE,
  INPUT_DIRECTION,
  OUTPUT_DIRECTION,
  MAX_OUTPUT_CURSOR,
} from './awce'
import {
  NXInitiator,
  NXResponder,
  PROTOCOL_NAME,
  type NoiseTransport,
} from './noiseNx'
import {
  ADMISSION_KEYS,
  CONTEXT_KEYS,
  canonicalContextBytes,
  deriveContext,
  exactRecord,
  validateAdmission,
  validateHex32,
  WAWCryptoError,
  type AdmissionTuple,
  type HandshakeContext,
} from './wawCryptoContext'

export { WAWCryptoError } from './wawCryptoContext'
export const MAX_INPUT_BYTES = 16_384
export const MAX_OUTPUT_BYTES = 32_768
export const ADMISSION_TIMEOUT_MS = 5_000
export type KeyFrame = Readonly<Record<string, string | number>>
export type CryptoProfileState =
  'NEW' | 'WAIT_ATTEST' | 'WAIT_CONFIRM' | 'WAIT_ACK' | 'VERIFIED' | 'CLOSED'
export interface CryptoProfileOptions {
  /** Monotonic milliseconds; injectable only for deterministic deadline tests. */
  readonly now?: () => number
  /** Original shared admission start, never a new per-frame timeout. */
  readonly admissionStartedAt?: number
  readonly ephemeralKeyPair?: CryptoKeyPair
}

const text = (value: string): Uint8Array => new TextEncoder().encode(value)
const EMPTY = new Uint8Array()
const CONFIRM_DOMAIN = text('agentbox-waw/noise-confirm/v1')
const ACK_CANARY = new Uint8Array(
  'fbb2854eb233e77bae587d1480d40192379527e27de780b24010ec97714490c3'
    .match(/../g)!
    .map((pair) => parseInt(pair, 16)),
)
const COMMON_KEYS = ['protocol_version', 'noise_protocol'] as const
const INIT_KEYS = [
  ...ADMISSION_KEYS,
  ...COMMON_KEYS,
  'crypto_envelope_version',
  'runtime_epoch',
  'browser_ephemeral_public_key',
  'noise_message_1',
]
const ATTEST_KEYS = [
  ...ADMISSION_KEYS,
  ...COMMON_KEYS,
  'crypto_envelope_version',
  'runtime_epoch',
  'runtime_attestation_x25519_fingerprint',
  'runtime_ephemeral_public_key',
  'noise_message_2',
]
const CONFIRM_KEYS = [...CONTEXT_KEYS, ...COMMON_KEYS, 'ciphertext']
const ACK_KEYS = [...CONFIRM_KEYS, 'status', 'transcript_context_hash']

const concat = (...parts: Uint8Array[]): Uint8Array => {
  const result = new Uint8Array(
    parts.reduce((size, part) => size + part.length, 0),
  )
  let offset = 0
  for (const part of parts) {
    result.set(part, offset)
    offset += part.length
  }
  return result
}
const equal = (a: Uint8Array, b: Uint8Array): boolean => {
  if (a.length !== b.length) return false
  let difference = 0
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i]
  return difference === 0
}
const hex = (bytes: Uint8Array): string =>
  Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
const digest = async (bytes: Uint8Array): Promise<Uint8Array> =>
  new Uint8Array(await crypto.subtle.digest('SHA-256', bytes as BufferSource))
const bytesCopy = (value: unknown, maximum: number): Uint8Array => {
  if (
    !(value instanceof Uint8Array) ||
    value.constructor !== Uint8Array ||
    value.length < 1 ||
    value.length > maximum
  )
    throw new WAWCryptoError()
  return new Uint8Array(value)
}
const encode = (value: Uint8Array): string =>
  btoa(String.fromCharCode(...value))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
const decode = (value: unknown, size: number): Uint8Array => {
  if (
    typeof value !== 'string' ||
    value.length !== Math.ceil((size * 4) / 3) ||
    !/^[A-Za-z0-9_-]+$/.test(value)
  )
    throw new WAWCryptoError()
  const result = Uint8Array.from(
    atob(value.replace(/-/g, '+').replace(/_/g, '/')),
    (char) => char.charCodeAt(0),
  )
  if (result.length !== size || encode(result) !== value)
    throw new WAWCryptoError()
  return result
}
const outputCursor = (value: unknown, previous: bigint): bigint => {
  if (
    typeof value !== 'bigint' ||
    value < 1n ||
    value > MAX_OUTPUT_CURSOR ||
    value <= previous
  )
    throw new WAWCryptoError()
  return value
}

class Profile {
  protected readonly admission: AdmissionTuple
  protected readonly context: HandshakeContext
  protected handshake?: NXInitiator | NXResponder
  #transport?: NoiseTransport
  #state: CryptoProfileState = 'NEW'
  #busy = new Set<'handshake' | 'send' | 'receive'>()
  #epoch = 0
  #timer?: ReturnType<typeof setTimeout>
  #now: () => number
  #lastTime: number
  #deadline: number
  #outputCursor = 0n

  constructor(
    admission: unknown,
    runtimeEpoch: unknown,
    options: CryptoProfileOptions,
  ) {
    this.admission = validateAdmission(admission)
    this.context = deriveContext(this.admission, runtimeEpoch)
    this.#now = options.now ?? (() => performance.now())
    this.#lastTime = this.#now()
    const started = options.admissionStartedAt ?? this.#lastTime
    if (
      !Number.isFinite(started) ||
      !Number.isFinite(this.#lastTime) ||
      started > this.#lastTime ||
      this.#lastTime - started >= ADMISSION_TIMEOUT_MS
    )
      throw new WAWCryptoError()
    this.#deadline = started + ADMISSION_TIMEOUT_MS
    this.#timer = setTimeout(
      () => this.destroy(),
      this.#deadline - this.#lastTime,
    )
  }
  get state(): CryptoProfileState {
    return this.#state
  }
  /** No key, challenge, payload, transcript or pin enters default JSON diagnostics. */
  toJSON(): { state: CryptoProfileState } {
    return { state: this.#state }
  }

  protected guard(token: number): void {
    if (this.#state === 'CLOSED' || token !== this.#epoch)
      throw new WAWCryptoError()
    if (this.#state !== 'VERIFIED') {
      const now = this.#now()
      if (
        !Number.isFinite(now) ||
        now < this.#lastTime ||
        now >= this.#deadline
      )
        throw new WAWCryptoError()
      this.#lastTime = now
    }
  }
  protected async operation<T>(
    expected: CryptoProfileState,
    next: CryptoProfileState,
    work: (token: number) => Promise<T>,
    lane: 'handshake' | 'send' | 'receive' = 'handshake',
  ): Promise<T> {
    if (
      this.#state !== expected ||
      this.#busy.has(lane) ||
      this.#busy.has('handshake') ||
      (lane === 'handshake' && this.#busy.size !== 0)
    ) {
      this.destroy()
      throw new WAWCryptoError()
    }
    this.#busy.add(lane)
    const token = this.#epoch
    try {
      this.guard(token)
      const result = await work(token)
      this.guard(token)
      this.#state = next
      if (next === 'VERIFIED') {
        clearTimeout(this.#timer)
        this.#timer = undefined
      }
      return result
    } catch {
      this.destroy()
      throw new WAWCryptoError()
    } finally {
      this.#busy.delete(lane)
    }
  }
  protected installTransport(): void {
    this.#transport = this.handshake!.takeTransport()
    this.handshake = undefined
  }
  protected get transport(): NoiseTransport {
    if (!this.#transport) throw new WAWCryptoError()
    return this.#transport
  }
  protected keyFrame(
    extra: Record<string, string | number>,
    context = false,
  ): KeyFrame {
    return Object.freeze({
      ...(context ? this.context : this.admission),
      protocol_version: 1,
      noise_protocol: PROTOCOL_NAME,
      crypto_envelope_version: 1,
      runtime_epoch: this.context.runtime_epoch,
      ...extra,
    })
  }
  protected frame(
    value: unknown,
    keys: readonly string[],
    context = false,
  ): Record<string, unknown> {
    const frame = exactRecord(value, keys)
    if (
      frame.protocol_version !== 1 ||
      frame.crypto_envelope_version !== 1 ||
      frame.noise_protocol !== PROTOCOL_NAME ||
      frame.runtime_epoch !== this.context.runtime_epoch
    )
      throw new WAWCryptoError()
    const expected = context ? this.context : this.admission
    for (const [key, member] of Object.entries(expected))
      if (frame[key] !== member) throw new WAWCryptoError()
    return frame
  }
  protected async send(
    plaintext: unknown,
    direction: number,
    cursor: unknown,
  ): Promise<Uint8Array> {
    return this.operation(
      'VERIFIED',
      'VERIFIED',
      async (token) => {
        const plain = bytesCopy(
          plaintext,
          direction === INPUT_DIRECTION ? MAX_INPUT_BYTES : MAX_OUTPUT_BYTES,
        )
        try {
          const checkedCursor =
            direction === OUTPUT_DIRECTION
              ? outputCursor(cursor, this.#outputCursor)
              : 0n
          const transport = this.transport
          const header = encodeAwceHeader({
            crypto_envelope_version: 1,
            direction_id: direction,
            flags: 0,
            crypto_sequence: transport.send.counter,
            stream_cursor: checkedCursor,
            context_id: transport.handshake_hash.slice(0, 16),
            ciphertext_length: plain.length + 16,
          })
          const ciphertext = await transport.send.encrypt(
            plain,
            concat(
              header,
              transport.handshake_hash,
              text(
                direction === INPUT_DIRECTION
                  ? 'browser-to-runtime'
                  : 'runtime-to-browser',
              ),
            ),
          )
          this.guard(token)
          if (direction === OUTPUT_DIRECTION) this.#outputCursor = checkedCursor
          return concat(header, ciphertext)
        } finally {
          plain.fill(0)
        }
      },
      'send',
    )
  }
  protected async receive(
    raw: unknown,
    direction: number,
    expectedCursor: unknown,
  ): Promise<Uint8Array> {
    return this.operation(
      'VERIFIED',
      'VERIFIED',
      async (token) => {
        const maximum =
          direction === INPUT_DIRECTION ? MAX_INPUT_BYTES : MAX_OUTPUT_BYTES
        const packet = bytesCopy(raw, HEADER_SIZE + maximum + 16)
        const envelope = decodeAwce(packet)
        const cursor =
          direction === OUTPUT_DIRECTION
            ? outputCursor(expectedCursor, this.#outputCursor)
            : 0n
        const transport = this.transport
        if (
          envelope.direction_id !== direction ||
          envelope.crypto_sequence !== transport.receive.counter ||
          envelope.stream_cursor !== cursor ||
          !equal(envelope.context_id, transport.handshake_hash.slice(0, 16))
        )
          throw new WAWCryptoError()
        const plaintext = await transport.receive.decrypt(
          envelope.ciphertext,
          concat(
            packet.slice(0, HEADER_SIZE),
            transport.handshake_hash,
            text(
              direction === INPUT_DIRECTION
                ? 'browser-to-runtime'
                : 'runtime-to-browser',
            ),
          ),
        )
        try {
          this.guard(token)
          if (direction === OUTPUT_DIRECTION) this.#outputCursor = cursor
          return plaintext
        } catch (error) {
          plaintext.fill(0)
          throw error
        }
      },
      'receive',
    )
  }
  destroy(): void {
    this.#state = 'CLOSED'
    this.#epoch += 1
    clearTimeout(this.#timer)
    this.#timer = undefined
    this.handshake?.destroy()
    this.handshake = undefined
    this.#transport?.destroy()
    this.#transport = undefined
  }
}

/** Browser role. The fingerprint must come from an independently verified trust provider. */
export class WAWInitiator extends Profile {
  #trustedFingerprint?: string
  constructor(
    admission: unknown,
    runtimeEpoch: unknown,
    trustedFingerprint: unknown,
    options: CryptoProfileOptions = {},
  ) {
    // Validate the pin before any constructor launches WebCrypto.
    const pin = validateHex32(trustedFingerprint)
    super(admission, runtimeEpoch, options)
    this.#trustedFingerprint = pin
    try {
      this.handshake = new NXInitiator(
        canonicalContextBytes(this.context),
        options.ephemeralKeyPair,
      )
    } catch {
      this.destroy()
      throw new WAWCryptoError()
    }
  }
  writeKeyInit(): Promise<KeyFrame> {
    return this.operation('NEW', 'WAIT_ATTEST', async (token) => {
      const message = await (this.handshake as NXInitiator).writeMessage1()
      this.guard(token)
      if (message.length !== 32) throw new WAWCryptoError()
      return this.keyFrame({
        browser_ephemeral_public_key: encode(message),
        noise_message_1: encode(message),
      })
    })
  }
  readKeyAttest(value: unknown): Promise<KeyFrame> {
    return this.operation('WAIT_ATTEST', 'WAIT_ACK', async (token) => {
      const frame = this.frame(value, ATTEST_KEYS)
      const fingerprint = validateHex32(
        frame.runtime_attestation_x25519_fingerprint,
      )
      if (fingerprint !== this.#trustedFingerprint) throw new WAWCryptoError()
      const message = decode(frame.noise_message_2, 128)
      if (
        !equal(
          message.subarray(0, 32),
          decode(frame.runtime_ephemeral_public_key, 32),
        )
      )
        throw new WAWCryptoError()
      const challenge = await (this.handshake as NXInitiator).readMessage2(
        message,
      )
      try {
        this.guard(token)
        if (challenge.length !== 32) throw new WAWCryptoError()
        this.installTransport()
        const transport = this.transport
        const actualFingerprint = await digest(
          transport.remote_static_public_key,
        )
        this.guard(token)
        if (hex(actualFingerprint) !== this.#trustedFingerprint)
          throw new WAWCryptoError()
        const confirmation = await digest(
          concat(
            CONFIRM_DOMAIN,
            new Uint8Array([0, 0, 0, 32]),
            challenge,
            transport.handshake_hash,
          ),
        )
        try {
          this.guard(token)
          const ciphertext = await transport.send.encrypt(confirmation, EMPTY)
          this.guard(token)
          return this.keyFrame({ ciphertext: encode(ciphertext) }, true)
        } finally {
          confirmation.fill(0)
        }
      } finally {
        challenge.fill(0)
      }
    })
  }
  readKeyConfirmAck(value: unknown): Promise<void> {
    return this.operation('WAIT_ACK', 'VERIFIED', async (token) => {
      const frame = this.frame(value, ACK_KEYS, true)
      if (
        frame.status !== 'verified' ||
        validateHex32(frame.transcript_context_hash) !==
          hex(this.transport.handshake_hash)
      )
        throw new WAWCryptoError()
      const ciphertext = decode(frame.ciphertext, 48)
      const plaintext = await this.transport.receive.decrypt(ciphertext, EMPTY)
      try {
        this.guard(token)
        if (!equal(plaintext, ACK_CANARY)) throw new WAWCryptoError()
      } finally {
        plaintext.fill(0)
      }
    })
  }
  encryptInput(plaintext: unknown): Promise<Uint8Array> {
    return this.send(plaintext, INPUT_DIRECTION, 0n)
  }
  decryptOutput(raw: unknown, expectedCursor: bigint): Promise<Uint8Array> {
    return this.receive(raw, OUTPUT_DIRECTION, expectedCursor)
  }
  destroy(): void {
    this.#trustedFingerprint = undefined
    super.destroy()
  }
}

/** Responder for profile verification and interoperability, not a browser Runtime service. */
export class WAWResponder extends Profile {
  #staticKeyPair?: CryptoKeyPair
  #challenge?: Uint8Array
  constructor(
    admission: unknown,
    runtimeEpoch: unknown,
    staticKeyPair: CryptoKeyPair,
    options: CryptoProfileOptions = {},
  ) {
    super(admission, runtimeEpoch, options)
    try {
      this.handshake = new NXResponder(
        canonicalContextBytes(this.context),
        staticKeyPair,
        options.ephemeralKeyPair,
      )
      this.#staticKeyPair = { ...staticKeyPair }
    } catch {
      this.destroy()
      throw new WAWCryptoError()
    }
  }
  readKeyInit(value: unknown): Promise<KeyFrame> {
    return this.operation('NEW', 'WAIT_CONFIRM', async (token) => {
      const frame = this.frame(value, INIT_KEYS)
      const message = decode(frame.noise_message_1, 32)
      if (!equal(message, decode(frame.browser_ephemeral_public_key, 32)))
        throw new WAWCryptoError()
      const publicKey = new Uint8Array(
        await crypto.subtle.exportKey('raw', this.#staticKeyPair!.publicKey),
      )
      this.guard(token)
      this.#staticKeyPair = undefined
      const fingerprint = await digest(publicKey)
      this.guard(token)
      const handshake = this.handshake as NXResponder
      const payload = await handshake.readMessage1(message)
      this.guard(token)
      if (payload.length !== 0) throw new WAWCryptoError()
      this.#challenge = crypto.getRandomValues(new Uint8Array(32))
      const message2 = await handshake.writeMessage2(this.#challenge)
      this.guard(token)
      if (message2.length !== 128) throw new WAWCryptoError()
      this.installTransport()
      return this.keyFrame({
        runtime_attestation_x25519_fingerprint: hex(fingerprint),
        runtime_ephemeral_public_key: encode(message2.slice(0, 32)),
        noise_message_2: encode(message2),
      })
    })
  }
  readKeyConfirm(value: unknown): Promise<KeyFrame> {
    return this.operation('WAIT_CONFIRM', 'VERIFIED', async (token) => {
      const frame = this.frame(value, CONFIRM_KEYS, true)
      const ciphertext = decode(frame.ciphertext, 48)
      const transport = this.transport
      const confirmation = await digest(
        concat(
          CONFIRM_DOMAIN,
          new Uint8Array([0, 0, 0, 32]),
          this.#challenge!,
          transport.handshake_hash,
        ),
      )
      try {
        this.guard(token)
        const plaintext = await transport.receive.decrypt(ciphertext, EMPTY)
        try {
          this.guard(token)
          if (!equal(plaintext, confirmation)) throw new WAWCryptoError()
        } finally {
          plaintext.fill(0)
        }
        const ack = await transport.send.encrypt(ACK_CANARY, EMPTY)
        this.guard(token)
        this.#challenge!.fill(0)
        this.#challenge = undefined
        return this.keyFrame(
          {
            status: 'verified',
            transcript_context_hash: hex(transport.handshake_hash),
            ciphertext: encode(ack),
          },
          true,
        )
      } finally {
        confirmation.fill(0)
      }
    })
  }
  decryptInput(raw: unknown): Promise<Uint8Array> {
    return this.receive(raw, INPUT_DIRECTION, 0n)
  }
  encryptOutput(plaintext: unknown, cursor: bigint): Promise<Uint8Array> {
    return this.send(plaintext, OUTPUT_DIRECTION, cursor)
  }
  destroy(): void {
    this.#staticKeyPair = undefined
    this.#challenge?.fill(0)
    this.#challenge = undefined
    super.destroy()
  }
}
