import { describe, expect, it } from 'vitest'
import fixture from '../../../../../tests/fixtures/waw_trust/public-v1.json'
import {
  decodeTrustBase64,
  parseBootstrapRecord,
  parsePinRecord,
  parseRootRecord,
  trustSignedBytes,
  trustTimestamp,
  validateTrustOrigin,
  verifyTrustRecordSignature,
  WAWTrustRecordError,
  type PinRecord,
} from './wawTrustRecords'

const encoder = new TextEncoder()
const text = (value: string) => encoder.encode(value)
const canonical = (value: object) =>
  JSON.stringify(
    Object.fromEntries(
      Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
    ),
  )
const raw = (value: object) => text(canonical(value))
const pin = fixture.records.find((item) => item.name === 'pin')!
const root = fixture.records.find((item) => item.name === 'root')!
const successor = fixture.records.find((item) => item.name === 'successor')!
const rootPublic = root.record.public_key!

describe('unchanged public trust vectors (signature only, synthetic 2030 records)', () => {
  it('verifies the exact immutable bootstrap digest', async () => {
    const record = parseBootstrapRecord(raw(fixture.bootstrap))
    expect(Object.isFrozen(record)).toBe(true)
    const digest = await crypto.subtle.digest('SHA-256', raw(record))
    expect(
      Array.from(new Uint8Array(digest), (byte) =>
        byte.toString(16).padStart(2, '0'),
      ).join(''),
    ).toBe(fixture.bootstrap_policy_sha256)
  })

  for (const item of fixture.records) {
    it(`verifies original ${item.name} bytes, digest and Ed25519 signature`, async () => {
      const record =
        item.name === 'pin'
          ? parsePinRecord(raw(item.record))
          : parseRootRecord(raw(item.record))
      expect(Object.isFrozen(record)).toBe(true)
      const signed = trustSignedBytes(record)
      expect(new TextDecoder().decode(signed)).toBe(
        `${item.domain}\0${item.canonical_without_signature}`,
      )
      const digest = await crypto.subtle.digest('SHA-256', signed)
      expect(
        Array.from(new Uint8Array(digest), (byte) =>
          byte.toString(16).padStart(2, '0'),
        ).join(''),
      ).toBe(item.signed_bytes_sha256)
      const key =
        item.name === 'root' ? fixture.bootstrap.public_key : rootPublic
      await expect(
        verifyTrustRecordSignature(record, key),
      ).resolves.toBeUndefined()
      await expect(
        verifyTrustRecordSignature(record, successor.record.public_key!),
      ).rejects.toThrow(WAWTrustRecordError)
    })
  }

  it('copies input bytes and refuses forged typed records', async () => {
    const bytes = raw(pin.record)
    const parsed = parsePinRecord(bytes)
    bytes.fill(0)
    await expect(
      verifyTrustRecordSignature(parsed, rootPublic),
    ).resolves.toBeUndefined()
    expect(() => trustSignedBytes({ ...parsed })).toThrow(WAWTrustRecordError)
    await expect(
      verifyTrustRecordSignature({ ...parsed }, rootPublic),
    ).rejects.toThrow(WAWTrustRecordError)
    const hostile = new Proxy({} as PinRecord, {
      ownKeys() {
        throw new Error('PRIVATE-CANARY')
      },
    })
    expect(() => trustSignedBytes(hostile)).toThrow(
      'RUNTIME_ATTESTATION_UNVERIFIED',
    )
  })

  it('rejects field mutation even when its schema stays valid', async () => {
    for (const change of [
      { pin_revision: 8 },
      { key_id: 'root-2030' },
      { origin: 'https://other.agentbox.test' },
      { runtime_host_installation_revision: 4 },
      { runtime_attestation_x25519_fingerprint: '2'.repeat(64) },
      { valid_until: '2030-02-02T00:00:00.000Z' },
    ]) {
      const parsed = parsePinRecord(raw({ ...pin.record, ...change }))
      await expect(
        verifyTrustRecordSignature(parsed, rootPublic),
      ).rejects.toThrow(WAWTrustRecordError)
    }
  })
})

describe('closed canonical records', () => {
  it.each([
    '',
    'null',
    '[]',
    '{}',
    '\ufeff{}',
    '{"a":1,"a":1}',
    ' '.repeat(4097),
    '"' + 'x'.repeat(4095) + '"',
  ])('rejects missing/malformed/oversized input %s', (value) => {
    expect(() => parsePinRecord(text(value))).toThrow(WAWTrustRecordError)
  })

  it.each([
    (value: string) => ` ${value}`,
    (value: string) => `${value}\n`,
    (value: string) =>
      value.replace('"pin_revision":7', '"pin_revision":7,"pin_revision":7'),
    (value: string) => value.replace('"pin_revision":7', '"pin_revision":7.0'),
    (value: string) => value.replace('"pin_revision":7', '"pin_revision":7e0'),
    (value: string) => value.replace('"pin_revision":7', '"pin_revision":-0'),
    (value: string) => value.replace('root-2029', 'root-\\u0032029'),
  ])('rejects alternate JSON bytes before signature checking', (mutate) => {
    expect(() => parsePinRecord(text(mutate(canonical(pin.record))))).toThrow(
      WAWTrustRecordError,
    )
  })

  it('rejects invalid UTF-8 and a UTF-8 BOM', () => {
    const bytes = raw(pin.record)
    expect(() => parsePinRecord(new Uint8Array([0xff, ...bytes]))).toThrow(
      WAWTrustRecordError,
    )
    expect(() =>
      parsePinRecord(new Uint8Array([0xef, 0xbb, 0xbf, ...bytes])),
    ).toThrow(WAWTrustRecordError)
  })

  it.each([
    { schema_version: 'waw-runtime-pin-v1' },
    { state: 'ACTIVE' },
    { key_id: 'root-2029\n' },
    { key_id: 'root-2029\u0085' },
    { runtime_attestation_x25519_fingerprint: '1'.repeat(64) + '\n' },
    { pin_revision: 0 },
    { pin_revision: -1 },
    { pin_revision: 1.5 },
    { pin_revision: true },
    { pin_revision: '7' },
    { pin_revision: Number.MAX_SAFE_INTEGER + 1 },
    { runtime_host_installation_revision: Number.MAX_SAFE_INTEGER + 1 },
    { valid_from: '2030-02-01T00:00:00.000Z' },
    { valid_from: '2029-02-29T00:00:00.000Z' },
    { valid_from: '2030-01-01T00:00:00Z' },
    { revoked_at: '2030-03-01T00:00:00.000Z' },
    { signature_algorithm: 'ed25519' },
    { signature: 'A'.repeat(85) },
    { signature: pin.record.signature + '=' },
    { signature: 'A'.repeat(85) + 'B' },
    { supersedes_fingerprint: {} },
    { repository: 'example/other' },
  ])('rejects invalid pin field set %j', (change) => {
    expect(() => parsePinRecord(raw({ ...pin.record, ...change }))).toThrow(
      WAWTrustRecordError,
    )
  })

  it.each([
    { state: 'REVOKED', revoked_at: null },
    { state: 'ACTIVE', revoked_at: '2030-01-15T00:00:00.000Z' },
    { root_revision: 1, supersedes_key_id: 'old-root' },
    { root_revision: 1, signer_key_id: 'other-key' },
    { root_revision: 2, supersedes_key_id: null },
    { public_key: 'A'.repeat(42) + 'B' },
    { root_revision: Number.MAX_SAFE_INTEGER + 1 },
  ])('rejects invalid root schema %j', (change) => {
    expect(() => parseRootRecord(raw({ ...root.record, ...change }))).toThrow(
      WAWTrustRecordError,
    )
  })

  it('admits safe integer limits syntactically without claiming signature/lifecycle validity', () => {
    const candidate = parsePinRecord(
      raw({
        ...pin.record,
        pin_revision: Number.MAX_SAFE_INTEGER,
        runtime_host_installation_revision: Number.MAX_SAFE_INTEGER,
      }),
    )
    expect(candidate.pin_revision).toBe(Number.MAX_SAFE_INTEGER)
  })

  it('parses a bounded revocation as data; no attachment acceptance is returned', () => {
    const parsed = parseRootRecord(
      raw({
        ...root.record,
        root_revision: 2,
        state: 'REVOKED',
        revoked_at: '2030-01-15T00:00:00.000Z',
        supersedes_key_id: 'root-2029',
      }),
    )
    expect(parsed.state).toBe('REVOKED')
  })
})

describe('scalar syntax does not substitute deployment policy', () => {
  it.each([
    'https://example.agentbox.test',
    'https://example.agentbox.test:8443',
    'https://127.0.0.1:8443',
    'https://[2001:db8::1]',
    'https://[::ffff:c000:201]',
  ])('accepts exact effective origin syntax %s', (origin) => {
    expect(validateTrustOrigin(origin)).toBe(origin)
  })

  it.each([
    'http://example.test',
    'https://EXAMPLE.test',
    'https://example.test:443',
    'https://example.test/',
    'https://user@example.test',
    'https://example.test?a',
    'https://example.test#x',
    'https://127.000.000.001',
    'https://127.1',
    'https://2130706433',
    'https://256.1.1.1',
    'https://[::ffff:192.0.2.1]',
    'https://example.test.',
    'https://[2001:0db8::1]',
    'https://[2001:DB8::1]',
    'https://[fe80::1%25eth0]',
    'https://a..test',
    `https://${'a'.repeat(64)}.test`,
  ])('rejects alternate/malformed origin %s', (origin) => {
    expect(() => validateTrustOrigin(origin)).toThrow(WAWTrustRecordError)
  })

  it('requires exact calendar/precision and fixed base64 lengths', () => {
    expect(trustTimestamp('2032-02-29T00:00:00.000Z')).toBe(
      Date.parse('2032-02-29T00:00:00.000Z'),
    )
    expect(() => trustTimestamp('2031-02-29T00:00:00.000Z')).toThrow(
      WAWTrustRecordError,
    )
    expect(() => trustTimestamp('2030-01-01T00:00:00.000Z\n')).toThrow(
      WAWTrustRecordError,
    )
    expect(decodeTrustBase64(fixture.bootstrap.public_key, 32)).toHaveLength(32)
    expect(() =>
      decodeTrustBase64(fixture.bootstrap.public_key + '=', 32),
    ).toThrow(WAWTrustRecordError)
  })
})
