/** Strict opaque AgentBox WAW Crypto Envelope (AWCE) v1 framing. */

export const MAGIC = 'AWCE'
export const VERSION = 1
export const HEADER_SIZE = 44
export const AUTH_TAG_SIZE = 16
export const MIN_PLAINTEXT_SIZE = 1
export const MAX_PLAINTEXT_SIZE = 49_152
export const MIN_CIPHERTEXT_SIZE = MIN_PLAINTEXT_SIZE + AUTH_TAG_SIZE
export const MAX_CIPHERTEXT_SIZE = MAX_PLAINTEXT_SIZE + AUTH_TAG_SIZE
export const MIN_ENVELOPE_SIZE = HEADER_SIZE + MIN_CIPHERTEXT_SIZE
export const MAX_ENVELOPE_SIZE = HEADER_SIZE + MAX_CIPHERTEXT_SIZE
export const CONTEXT_ID_SIZE = 16
export const INPUT_DIRECTION = 1
export const OUTPUT_DIRECTION = 2
export const MIN_TERMINAL_SEQUENCE = 1n
export const MAX_TERMINAL_SEQUENCE = 0xffff_ffff_ffff_fffen
export const MIN_OUTPUT_CURSOR = 1n
export const MAX_OUTPUT_CURSOR = 0xffff_ffff_ffff_fffen

export class AWCEError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AWCEError'
  }
}

export class IncompleteAWCE extends AWCEError {
  constructor(message: string) {
    super(message)
    this.name = 'IncompleteAWCE'
  }
}

export class TrailingAWCEBytes extends AWCEError {
  constructor(message: string) {
    super(message)
    this.name = 'TrailingAWCEBytes'
  }
}

export interface AWCEHeaderFields {
  readonly crypto_envelope_version: number
  readonly direction_id: number
  readonly flags: number
  readonly crypto_sequence: bigint
  readonly stream_cursor: bigint
  readonly context_id: Uint8Array
  /** Includes the 16-byte authentication tag. */
  readonly ciphertext_length: number
}

export interface AWCEEnvelopeFields extends Omit<
  AWCEHeaderFields,
  'ciphertext_length'
> {
  readonly ciphertext: Uint8Array
}

const copy = (value: Uint8Array): Uint8Array => new Uint8Array(value)

const isExactUint8Array = (value: unknown): value is Uint8Array =>
  value instanceof Uint8Array && value.constructor === Uint8Array

const validNumber = (
  value: unknown,
  minimum: number,
  maximum: number,
): boolean =>
  typeof value === 'number' &&
  Number.isSafeInteger(value) &&
  value >= minimum &&
  value <= maximum

const validBigInt = (
  value: unknown,
  minimum: bigint,
  maximum: bigint,
): boolean => typeof value === 'bigint' && value >= minimum && value <= maximum

const invalid = (message: string): never => {
  throw new AWCEError(message)
}

const validateHeaderFields = (fields: AWCEHeaderFields): void => {
  if (fields.crypto_envelope_version !== VERSION) {
    invalid('unsupported AWCE version')
  }
  if (!validNumber(fields.direction_id, 0, 0xff)) {
    invalid('AWCE direction is invalid')
  }
  if (
    fields.direction_id !== INPUT_DIRECTION &&
    fields.direction_id !== OUTPUT_DIRECTION
  ) {
    invalid('unknown AWCE direction')
  }
  if (!validNumber(fields.flags, 0, 0xffff) || fields.flags !== 0) {
    invalid('AWCE flags are reserved and must be zero')
  }
  if (
    !validBigInt(
      fields.crypto_sequence,
      MIN_TERMINAL_SEQUENCE,
      MAX_TERMINAL_SEQUENCE,
    )
  ) {
    invalid('AWCE crypto_sequence is invalid')
  }
  if (!validBigInt(fields.stream_cursor, 0n, MAX_OUTPUT_CURSOR)) {
    invalid('AWCE stream_cursor is invalid')
  }
  if (
    (fields.direction_id === INPUT_DIRECTION && fields.stream_cursor !== 0n) ||
    (fields.direction_id === OUTPUT_DIRECTION &&
      fields.stream_cursor < MIN_OUTPUT_CURSOR)
  ) {
    invalid('AWCE stream_cursor is invalid for its direction')
  }
  if (
    !isExactUint8Array(fields.context_id) ||
    fields.context_id.length !== CONTEXT_ID_SIZE
  ) {
    invalid('AWCE context_id is invalid')
  }
  if (
    !validNumber(
      fields.ciphertext_length,
      MIN_CIPHERTEXT_SIZE,
      MAX_CIPHERTEXT_SIZE,
    )
  ) {
    invalid('AWCE ciphertext length is outside the v1 limit')
  }
}

const validateFields = (fields: AWCEEnvelopeFields): void => {
  if (!isExactUint8Array(fields.ciphertext)) {
    invalid('AWCE ciphertext length is outside the v1 limit')
  }
  validateHeaderFields({
    ...fields,
    ciphertext_length: fields.ciphertext.length,
  })
}

/** A validated immutable AWCE v1 envelope with opaque copied byte fields. */
export class AWCEEnvelope {
  readonly crypto_envelope_version: number
  readonly direction_id: number
  readonly flags: number
  readonly crypto_sequence: bigint
  readonly stream_cursor: bigint
  readonly #context_id: Uint8Array
  readonly #ciphertext: Uint8Array

  constructor(fields: AWCEEnvelopeFields) {
    if (!fields || typeof fields !== 'object') {
      invalid('AWCE envelope fields are invalid')
    }
    validateFields(fields)
    this.crypto_envelope_version = fields.crypto_envelope_version
    this.direction_id = fields.direction_id
    this.flags = fields.flags
    this.crypto_sequence = fields.crypto_sequence
    this.stream_cursor = fields.stream_cursor
    this.#context_id = copy(fields.context_id)
    this.#ciphertext = copy(fields.ciphertext)
    Object.freeze(this)
  }

  get context_id(): Uint8Array {
    return copy(this.#context_id)
  }

  get ciphertext(): Uint8Array {
    return copy(this.#ciphertext)
  }

  get ciphertext_length(): number {
    return this.#ciphertext.length
  }
}

const requireExactEnvelope = (value: unknown): AWCEEnvelope => {
  if (
    !value ||
    typeof value !== 'object' ||
    Object.getPrototypeOf(value) !== AWCEEnvelope.prototype
  ) {
    invalid('AWCE envelope must be an exact typed record')
  }
  return value as AWCEEnvelope
}

/** Encode one exact AWCE v1 envelope without inspecting opaque bytes. */
export const encodeAwce = (value: unknown): Uint8Array => {
  const envelope = requireExactEnvelope(value)
  const result = new Uint8Array(HEADER_SIZE + envelope.ciphertext_length)
  result.set(
    encodeAwceHeader({
      crypto_envelope_version: envelope.crypto_envelope_version,
      direction_id: envelope.direction_id,
      flags: envelope.flags,
      crypto_sequence: envelope.crypto_sequence,
      stream_cursor: envelope.stream_cursor,
      context_id: envelope.context_id,
      ciphertext_length: envelope.ciphertext_length,
    }),
  )
  result.set(envelope.ciphertext, HEADER_SIZE)
  return result
}

/**
 * Encode the exact 44-byte AWCE header before opaque ciphertext exists.
 *
 * This only constructs framing bytes. It does not create an authenticated
 * envelope or establish any cryptographic context.
 */
export const encodeAwceHeader = (fields: unknown): Uint8Array => {
  if (!fields || typeof fields !== 'object') {
    invalid('AWCE header fields are invalid')
  }
  const header = fields as AWCEHeaderFields
  validateHeaderFields(header)
  const result = new Uint8Array(HEADER_SIZE)
  const view = new DataView(result.buffer)
  result.set([0x41, 0x57, 0x43, 0x45], 0)
  view.setUint8(4, header.crypto_envelope_version)
  view.setUint8(5, header.direction_id)
  view.setUint16(6, header.flags, false)
  view.setBigUint64(8, header.crypto_sequence, false)
  view.setBigUint64(16, header.stream_cursor, false)
  view.setUint32(24, header.ciphertext_length, false)
  result.set(header.context_id, 28)
  return result
}

/** Decode exactly one AWCE v1 envelope and reject truncation or trailing bytes. */
export const decodeAwce = (data: unknown): AWCEEnvelope => {
  if (!isExactUint8Array(data)) {
    throw new TypeError('AWCE envelope must be Uint8Array')
  }
  if (data.length < HEADER_SIZE) {
    throw new IncompleteAWCE('AWCE header is incomplete')
  }
  if (data.length > MAX_ENVELOPE_SIZE) {
    invalid('AWCE envelope exceeds the v1 limit')
  }
  if (
    data[0] !== 0x41 ||
    data[1] !== 0x57 ||
    data[2] !== 0x43 ||
    data[3] !== 0x45
  ) {
    invalid('invalid AWCE magic')
  }
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  const ciphertextLength = view.getUint32(24, false)
  if (
    ciphertextLength < MIN_CIPHERTEXT_SIZE ||
    ciphertextLength > MAX_CIPHERTEXT_SIZE
  ) {
    invalid('AWCE ciphertext length is outside the v1 limit')
  }
  const expectedLength = HEADER_SIZE + ciphertextLength
  if (data.length < expectedLength) {
    throw new IncompleteAWCE('AWCE ciphertext is incomplete')
  }
  if (data.length > expectedLength) {
    throw new TrailingAWCEBytes(
      'AWCE single-envelope decode has trailing bytes',
    )
  }
  return new AWCEEnvelope({
    crypto_envelope_version: view.getUint8(4),
    direction_id: view.getUint8(5),
    flags: view.getUint16(6, false),
    crypto_sequence: view.getBigUint64(8, false),
    stream_cursor: view.getBigUint64(16, false),
    context_id: data.slice(28, HEADER_SIZE),
    ciphertext: data.slice(HEADER_SIZE),
  })
}

export const encode_awce = encodeAwce
export const decode_awce = decodeAwce
export const encode_awce_header = encodeAwceHeader
