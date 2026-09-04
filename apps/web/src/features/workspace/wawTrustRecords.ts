/** Closed public trust records and signature verification, without trust authority.
 *
 * This module never installs a root/pin, reads browser storage, trusts API data,
 * chooses a clock, grants admission or advances Noise. The independent provider
 * and lifecycle verifier must supply those separate proofs.
 */

export const TRUST_RECORD_LIMIT = 4096
export const TRUST_REVISION_LIMIT = Number.MAX_SAFE_INTEGER

export class WAWTrustRecordError extends Error {
  constructor() {
    super('RUNTIME_ATTESTATION_UNVERIFIED')
    this.name = 'WAWTrustRecordError'
  }
}

export interface BootstrapRecord {
  readonly schema_version: 'waw-runtime-bootstrap-v1'
  readonly key_id: 'bootstrap-2029'
  readonly public_key: string
}

export interface RootRecord {
  readonly schema_version: 'waw-runtime-root-v1'
  readonly root_revision: number
  readonly key_id: string
  readonly public_key: string
  readonly signer_key_id: string
  readonly state: 'ACTIVE' | 'REVOKED'
  readonly valid_from: string
  readonly valid_until: string
  readonly revoked_at: string | null
  readonly supersedes_key_id: string | null
  readonly signature_algorithm: 'Ed25519'
  readonly signature: string
}

export interface PinRecord {
  readonly schema_version: 'waw-runtime-pin.v1'
  readonly repository: 'ForceMind/agentbox'
  readonly origin: string
  readonly pin_revision: number
  readonly runtime_host_installation_id: string
  readonly runtime_host_installation_revision: number
  readonly runtime_attestation_x25519_fingerprint: string
  readonly valid_from: string
  readonly valid_until: string
  readonly revoked_at: string | null
  readonly supersedes_fingerprint: string | null
  readonly signature_algorithm: 'Ed25519'
  readonly key_id: string
  readonly signature: string
}

type RecordObject = Record<string, unknown>
type SignedRecord = RootRecord | PinRecord
const BOOTSTRAP_KEYS = ['schema_version', 'key_id', 'public_key']
const ROOT_KEYS = [
  'schema_version',
  'root_revision',
  'key_id',
  'public_key',
  'signer_key_id',
  'state',
  'valid_from',
  'valid_until',
  'revoked_at',
  'supersedes_key_id',
  'signature_algorithm',
  'signature',
]
const PIN_KEYS = [
  'schema_version',
  'repository',
  'origin',
  'pin_revision',
  'runtime_host_installation_id',
  'runtime_host_installation_revision',
  'runtime_attestation_x25519_fingerprint',
  'valid_from',
  'valid_until',
  'revoked_at',
  'supersedes_fingerprint',
  'signature_algorithm',
  'key_id',
  'signature',
]
const ID = /^[a-z0-9._-]{1,64}$/
const HEX = /^[a-f0-9]{64}$/
const encoder = new TextEncoder()
// Validation provenance only; membership is not signer/lifecycle authority.
const parsedSignedRecords = new WeakSet<object>()

function requireValue(condition: unknown): asserts condition {
  if (!condition) throw new WAWTrustRecordError()
}

/** Exact base64url; no padding, alternate spelling or unused-bit normalization. */
export function decodeTrustBase64(
  value: unknown,
  size: 32 | 64,
): Uint8Array<ArrayBuffer> {
  requireValue(typeof value === 'string' && /^[A-Za-z0-9_-]+$/.test(value))
  requireValue(value.length === (size === 32 ? 43 : 86))
  let binary: string
  try {
    binary = atob(
      value.replace(/-/g, '+').replace(/_/g, '/') +
        '='.repeat(-value.length & 3),
    )
  } catch {
    throw new WAWTrustRecordError()
  }
  requireValue(binary.length === size)
  requireValue(
    btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '') ===
      value,
  )
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}

function revision(value: unknown): void {
  requireValue(
    typeof value === 'number' && Number.isSafeInteger(value) && value > 0,
  )
}

export function trustTimestamp(value: unknown): number {
  requireValue(
    typeof value === 'string' &&
      /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value),
  )
  const timestamp = Date.parse(value)
  requireValue(
    Number.isFinite(timestamp) && new Date(timestamp).toISOString() === value,
  )
  return timestamp
}

/** Syntax/effective-origin identity only; independent DNS/network policy is separate. */
export function validateTrustOrigin(value: unknown): string {
  requireValue(typeof value === 'string' && /^[\x21-\x7e]+$/.test(value))
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new WAWTrustRecordError()
  }
  requireValue(url.protocol === 'https:' && url.origin === value)
  const host = url.hostname
  if (host.startsWith('[')) {
    // Browser/API Origin serialization uses the canonical WHATWG IPv6 form.
    // Restrict the source spelling to lowercase bracketed hexadecimal so an
    // embedded dotted-IPv4 spelling cannot compare differently across ports.
    requireValue(/^\[[0-9a-f:]+\]$/.test(host))
  } else {
    requireValue(host.length <= 253)
    if (/^[0-9.]+$/.test(host)) {
      const octets = host.split('.')
      requireValue(
        octets.length === 4 &&
          octets.every(
            (part) => /^(0|[1-9][0-9]{0,2})$/.test(part) && Number(part) <= 255,
          ),
      )
    } else {
      requireValue(
        host
          .split('.')
          .every((label) =>
            /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label),
          ),
      )
    }
  }
  return value
}

function canonical(value: RecordObject): string {
  // Only the closed flat schema's ASCII scalars/safe integers reach this point.
  return JSON.stringify(
    Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, value[key]]),
    ),
  )
}

function parse(raw: Uint8Array, keys: readonly string[]): RecordObject {
  requireValue(
    ArrayBuffer.isView(raw) &&
      Object.prototype.toString.call(raw) === '[object Uint8Array]',
  )
  requireValue(raw.byteLength > 0 && raw.byteLength <= TRUST_RECORD_LIMIT)
  let text: string
  let value: unknown
  try {
    text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(
      new Uint8Array(raw),
    )
    value = JSON.parse(text)
  } catch {
    throw new WAWTrustRecordError()
  }
  requireValue(
    value !== null && typeof value === 'object' && !Array.isArray(value),
  )
  const record = value as RecordObject
  requireValue(
    Object.keys(record).length === keys.length &&
      keys.every((key) => Object.hasOwn(record, key)),
  )
  // Flat scalars bound canonicalization and exclude nested prototypes/objects.
  requireValue(
    Object.values(record).every(
      (item) =>
        item === null ||
        typeof item === 'number' ||
        (typeof item === 'string' && !/[^\x20-\x7e]/.test(item)),
    ),
  )
  // Equality rejects duplicate keys, whitespace, aliases/escaping and lossy
  // number tokens before a candidate can be signature-verified or installed.
  requireValue(canonical(record) === text)
  return record
}

function signatureFields(record: RecordObject): void {
  requireValue(record.signature_algorithm === 'Ed25519')
  requireValue(typeof record.key_id === 'string' && ID.test(record.key_id))
  decodeTrustBase64(record.signature, 64)
  const from = trustTimestamp(record.valid_from)
  const until = trustTimestamp(record.valid_until)
  requireValue(until > from)
  if (record.revoked_at !== null) {
    const revoked = trustTimestamp(record.revoked_at)
    requireValue(from <= revoked && revoked <= until)
  }
}

export function parseBootstrapRecord(raw: Uint8Array): BootstrapRecord {
  const record = parse(raw, BOOTSTRAP_KEYS)
  requireValue(
    record.schema_version === 'waw-runtime-bootstrap-v1' &&
      record.key_id === 'bootstrap-2029',
  )
  decodeTrustBase64(record.public_key, 32)
  return Object.freeze(record) as unknown as BootstrapRecord
}

export function parseRootRecord(raw: Uint8Array): RootRecord {
  const record = parse(raw, ROOT_KEYS)
  requireValue(record.schema_version === 'waw-runtime-root-v1')
  signatureFields(record)
  revision(record.root_revision)
  decodeTrustBase64(record.public_key, 32)
  requireValue(
    typeof record.signer_key_id === 'string' && ID.test(record.signer_key_id),
  )
  requireValue(record.state === 'ACTIVE' || record.state === 'REVOKED')
  requireValue((record.state === 'ACTIVE') === (record.revoked_at === null))
  if (record.root_revision === 1) {
    requireValue(
      record.supersedes_key_id === null &&
        record.signer_key_id === 'bootstrap-2029' &&
        record.state === 'ACTIVE',
    )
  } else {
    requireValue(
      typeof record.supersedes_key_id === 'string' &&
        ID.test(record.supersedes_key_id),
    )
  }
  parsedSignedRecords.add(record)
  return Object.freeze(record) as unknown as RootRecord
}

export function parsePinRecord(raw: Uint8Array): PinRecord {
  const record = parse(raw, PIN_KEYS)
  requireValue(
    record.schema_version === 'waw-runtime-pin.v1' &&
      record.repository === 'ForceMind/agentbox',
  )
  signatureFields(record)
  validateTrustOrigin(record.origin)
  revision(record.pin_revision)
  revision(record.runtime_host_installation_revision)
  requireValue(
    typeof record.runtime_host_installation_id === 'string' &&
      /^wri_[a-f0-9]{32}$/.test(record.runtime_host_installation_id),
  )
  requireValue(
    typeof record.runtime_attestation_x25519_fingerprint === 'string' &&
      HEX.test(record.runtime_attestation_x25519_fingerprint),
  )
  requireValue(
    record.supersedes_fingerprint === null ||
      (typeof record.supersedes_fingerprint === 'string' &&
        HEX.test(record.supersedes_fingerprint)),
  )
  parsedSignedRecords.add(record)
  return Object.freeze(record) as unknown as PinRecord
}

/** Only parser-owned frozen records; this returns signing bytes, not trust. */
export function trustSignedBytes(
  candidate: SignedRecord,
): Uint8Array<ArrayBuffer> {
  requireValue(parsedSignedRecords.has(candidate))
  const record = candidate
  const body = Object.fromEntries(
    Object.entries(record).filter(([key]) => key !== 'signature'),
  )
  const domain =
    record.schema_version === 'waw-runtime-root-v1'
      ? 'agentbox-waw/runtime-root/v1'
      : 'agentbox-waw/runtime-pin/v1'
  return encoder.encode(`${domain}\0${canonical(body)}`)
}

/** Cryptographic signature only. Signer/lifecycle/time/floor authority is external. */
export async function verifyTrustRecordSignature(
  candidate: SignedRecord,
  signerPublicKey: string,
): Promise<void> {
  try {
    const bytes = trustSignedBytes(candidate)
    const signature = decodeTrustBase64(candidate.signature, 64)
    const key = await crypto.subtle.importKey(
      'raw',
      decodeTrustBase64(signerPublicKey, 32),
      'Ed25519',
      false,
      ['verify'],
    )
    requireValue(await crypto.subtle.verify('Ed25519', key, signature, bytes))
  } catch {
    throw new WAWTrustRecordError()
  }
}
