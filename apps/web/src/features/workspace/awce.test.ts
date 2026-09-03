import { describe, expect, it } from 'vitest'
import {
  AWCEEnvelope,
  AWCEError,
  decodeAwce,
  encodeAwce,
  encodeAwceHeader,
  HEADER_SIZE,
  IncompleteAWCE,
  INPUT_DIRECTION,
  MAX_CIPHERTEXT_SIZE,
  MAX_ENVELOPE_SIZE,
  MAX_OUTPUT_CURSOR,
  MAX_TERMINAL_SEQUENCE,
  OUTPUT_DIRECTION,
  TrailingAWCEBytes,
} from './awce'

const contextId = new Uint8Array([...Array(16).keys()])
const ciphertext = new Uint8Array([0x78, ...Array(16).fill(0x74)])
const fixture = new Uint8Array(
  Buffer.from(
    '41574345010100000000000000000001000000000000000000000011000102030405060708090a0b0c0d0e0f7874747474747474747474747474747474',
    'hex',
  ),
)

const envelope = (fields: object = {}): AWCEEnvelope =>
  new AWCEEnvelope({
    crypto_envelope_version: 1,
    direction_id: INPUT_DIRECTION,
    flags: 0,
    crypto_sequence: 1n,
    stream_cursor: 0n,
    context_id: contextId,
    ciphertext,
    ...(fields as Partial<ConstructorParameters<typeof AWCEEnvelope>[0]>),
  })

const headerFields = (fields: object = {}) => ({
  crypto_envelope_version: 1,
  direction_id: INPUT_DIRECTION,
  flags: 0,
  crypto_sequence: 1n,
  stream_cursor: 0n,
  context_id: contextId,
  ciphertext_length: ciphertext.length,
  ...fields,
})

describe('AWCE v1', () => {
  it('uses the public fixed binary vector', () => {
    const decoded = decodeAwce(fixture)
    expect(fixture).toHaveLength(HEADER_SIZE + ciphertext.length)
    expect(decoded.crypto_envelope_version).toBe(1)
    expect(decoded.direction_id).toBe(INPUT_DIRECTION)
    expect(decoded.flags).toBe(0)
    expect(decoded.crypto_sequence).toBe(1n)
    expect(decoded.stream_cursor).toBe(0n)
    expect(decoded.context_id).toEqual(contextId)
    expect(decoded.ciphertext).toEqual(ciphertext)
    expect(encodeAwce(decoded)).toEqual(fixture)
  })

  it('encodes the fixed header before ciphertext and shares the body prefix', () => {
    const value = envelope()
    const header = encodeAwceHeader(headerFields())
    expect(header).toHaveLength(HEADER_SIZE)
    expect(header).toEqual(fixture.slice(0, HEADER_SIZE))
    expect(encodeAwce(value).slice(0, HEADER_SIZE)).toEqual(header)
  })

  it('encodes high-bit sequences and maximum ciphertext length in a header', () => {
    const header = encodeAwceHeader(
      headerFields({
        direction_id: OUTPUT_DIRECTION,
        crypto_sequence: MAX_TERMINAL_SEQUENCE,
        stream_cursor: MAX_OUTPUT_CURSOR,
        ciphertext_length: MAX_CIPHERTEXT_SIZE,
      }),
    )
    const view = new DataView(
      header.buffer,
      header.byteOffset,
      header.byteLength,
    )
    expect(view.getBigUint64(8, false)).toBe(MAX_TERMINAL_SEQUENCE)
    expect(view.getBigUint64(16, false)).toBe(MAX_OUTPUT_CURSOR)
    expect(view.getUint32(24, false)).toBe(MAX_CIPHERTEXT_SIZE)
  })

  it.each([
    { ciphertext_length: 16 },
    { ciphertext_length: MAX_CIPHERTEXT_SIZE + 1 },
    { ciphertext_length: true },
    { ciphertext_length: 17n },
    { context_id: new Uint8Array(15) },
    { context_id: new Uint8ClampedArray(16) },
    { direction_id: INPUT_DIRECTION, stream_cursor: 1n },
    { direction_id: OUTPUT_DIRECTION, stream_cursor: 0n },
  ])('rejects invalid header fields', (fields) => {
    expect(() => encodeAwceHeader(headerFields(fields))).toThrow(AWCEError)
  })

  it('decodes a hand-written vector above Number precision', () => {
    const highBitFixture = new Uint8Array(
      Buffer.from(
        '41574345010200000020000000000001800000000000000100000011000102030405060708090a0b0c0d0e0f7874747474747474747474747474747474',
        'hex',
      ),
    )
    const decoded = decodeAwce(highBitFixture)
    expect(decoded.crypto_sequence).toBe(9_007_199_254_740_993n)
    expect(decoded.stream_cursor).toBe(9_223_372_036_854_775_809n)
    expect(encodeAwce(decoded)).toEqual(highBitFixture)
  })

  it('decodes an exact envelope from a non-zero byte offset', () => {
    const padded = new Uint8Array(fixture.length + 2)
    padded.set(fixture, 1)
    expect(
      decodeAwce(padded.subarray(1, fixture.length + 1)).ciphertext,
    ).toEqual(ciphertext)
  })

  it('copies opaque bytes at construction, access and encoding', () => {
    const originalContext = new Uint8Array(contextId)
    const originalCiphertext = new Uint8Array(ciphertext)
    const value = envelope({
      context_id: originalContext,
      ciphertext: originalCiphertext,
    })
    originalContext[0] = 255
    originalCiphertext[0] = 255
    const returned = value.ciphertext
    returned[0] = 255
    const encoded = encodeAwce(value)
    encoded[HEADER_SIZE] = 255
    expect(value.context_id).toEqual(contextId)
    expect(value.ciphertext).toEqual(ciphertext)
    expect(encodeAwce(value)).toEqual(fixture)
    expect(Object.isFrozen(value)).toBe(true)
  })

  it('does not alias decoded input, returned opaque bytes or encoded output', () => {
    const raw = fixture.slice()
    const decoded = decodeAwce(raw)
    raw[28] = 255
    raw[HEADER_SIZE] = 255
    const returnedContext = decoded.context_id
    const returnedCiphertext = decoded.ciphertext
    returnedContext[0] = 255
    returnedCiphertext[0] = 255
    const encoded = encodeAwce(decoded)
    encoded[28] = 255
    encoded[HEADER_SIZE] = 255
    expect(decoded.context_id).toEqual(contextId)
    expect(decoded.ciphertext).toEqual(ciphertext)
    expect(encodeAwce(decoded)).toEqual(fixture)
  })

  it.each([
    [INPUT_DIRECTION, 0n],
    [OUTPUT_DIRECTION, 1n],
    [OUTPUT_DIRECTION, MAX_OUTPUT_CURSOR],
  ])('accepts direction %i with cursor %s', (direction_id, stream_cursor) => {
    expect(() => envelope({ direction_id, stream_cursor })).not.toThrow()
  })

  it.each([
    { crypto_envelope_version: 2 },
    { crypto_envelope_version: true },
    { direction_id: 3 },
    { direction_id: true },
    { flags: 1 },
    { flags: true },
    { crypto_sequence: 1 },
    { crypto_sequence: 0n },
    { crypto_sequence: MAX_TERMINAL_SEQUENCE + 1n },
    { stream_cursor: 1 },
    { stream_cursor: MAX_OUTPUT_CURSOR + 1n },
    { context_id: new Uint8Array(15) },
    { context_id: new Uint8ClampedArray(16) },
    { ciphertext: new Uint8Array(16) },
    { ciphertext: new Uint8Array(MAX_CIPHERTEXT_SIZE + 1) },
    { ciphertext: new Uint8ClampedArray(17) },
    { direction_id: INPUT_DIRECTION, stream_cursor: 1n },
    { direction_id: OUTPUT_DIRECTION, stream_cursor: 0n },
  ])('rejects invalid typed or boundary fields', (fields) => {
    expect(() => envelope(fields)).toThrow(AWCEError)
  })

  it('accepts exact ciphertext bounds', () => {
    expect(
      encodeAwce(envelope({ ciphertext: new Uint8Array(17) })),
    ).toHaveLength(61)
    const maximum = envelope({
      ciphertext: new Uint8Array(MAX_CIPHERTEXT_SIZE),
    })
    expect(encodeAwce(maximum)).toHaveLength(MAX_ENVELOPE_SIZE)
    expect(decodeAwce(encodeAwce(maximum)).ciphertext).toEqual(
      maximum.ciphertext,
    )
  })

  it('rejects mutated headers, truncation, trailing bytes and non-byte input', () => {
    const mutations = [
      (raw: Uint8Array) => new Uint8Array([0, ...raw.slice(1)]),
      (raw: Uint8Array) =>
        new Uint8Array([...raw.slice(0, 4), 2, ...raw.slice(5)]),
      (raw: Uint8Array) =>
        new Uint8Array([...raw.slice(0, 5), 3, ...raw.slice(6)]),
      (raw: Uint8Array) =>
        new Uint8Array([...raw.slice(0, 6), 0, 1, ...raw.slice(8)]),
      (raw: Uint8Array) =>
        new Uint8Array([
          ...raw.slice(0, 8),
          ...Array(8).fill(0),
          ...raw.slice(16),
        ]),
      (raw: Uint8Array) =>
        new Uint8Array([
          ...raw.slice(0, 16),
          ...Array(7).fill(0),
          1,
          ...raw.slice(24),
        ]),
      (raw: Uint8Array) =>
        new Uint8Array([...raw.slice(0, 24), 0, 0, 0, 16, ...raw.slice(28)]),
    ]
    for (const mutate of mutations)
      expect(() => decodeAwce(mutate(fixture))).toThrow(AWCEError)
    expect(() => decodeAwce(fixture.slice(0, HEADER_SIZE - 1))).toThrow(
      IncompleteAWCE,
    )
    expect(() => decodeAwce(fixture.slice(0, -1))).toThrow(IncompleteAWCE)
    expect(() => decodeAwce(new Uint8Array([...fixture, 0]))).toThrow(
      TrailingAWCEBytes,
    )
    expect(() => decodeAwce(new Uint8Array(MAX_ENVELOPE_SIZE + 1))).toThrow(
      AWCEError,
    )
    expect(() => decodeAwce(new Uint8ClampedArray(fixture))).toThrow(TypeError)
  })
})
