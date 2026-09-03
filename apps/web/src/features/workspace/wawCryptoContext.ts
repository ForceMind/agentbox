/** Closed, non-secret context records for the fixed WAW v1 crypto profile. */
export const WAW_PROTOCOL_ID = 'agentbox-waw/v1'
export const U64_MAX = 18_446_744_073_709_551_615n

export class WAWCryptoError extends Error {
  constructor() {
    super('STREAM_CRYPTO_FAILURE')
    this.name = 'WAWCryptoError'
  }
}

export interface AdmissionTuple {
  readonly attachment_id: string
  readonly workspace_id: string
  readonly project_id: string
  readonly agent_type: 'claude' | 'codex'
  readonly runtime_host_installation_id: string
  readonly runtime_host_installation_revision: string
  readonly auth_epoch: string
  readonly api_authority_epoch: string
  readonly lease_number: string
  readonly generation: string
  readonly binding_revision: string
  readonly mode: 'writer'
  readonly binding_digest: string
}

export interface HandshakeContext extends Omit<AdmissionTuple, 'mode'> {
  readonly runtime_epoch: string
  readonly protocol_id: typeof WAW_PROTOCOL_ID
  readonly crypto_envelope_version: 1
}

export const ADMISSION_KEYS = Object.freeze([
  'attachment_id',
  'workspace_id',
  'project_id',
  'agent_type',
  'runtime_host_installation_id',
  'runtime_host_installation_revision',
  'auth_epoch',
  'api_authority_epoch',
  'lease_number',
  'generation',
  'binding_revision',
  'mode',
  'binding_digest',
] as const)
export const CONTEXT_KEYS = Object.freeze([
  ...ADMISSION_KEYS.filter((key) => key !== 'mode'),
  'runtime_epoch',
  'protocol_id',
  'crypto_envelope_version',
] as const)

/** Accept data properties only; getters, prototypes and hidden keys are not wire data. */
export function exactRecord(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    ![Object.prototype, null].includes(Object.getPrototypeOf(value))
  )
    throw new WAWCryptoError()
  const own = Reflect.ownKeys(value)
  if (
    own.length !== keys.length ||
    own.some((key) => typeof key !== 'string' || !keys.includes(key))
  )
    throw new WAWCryptoError()
  const result: Record<string, unknown> = {}
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key)
    if (!descriptor || !descriptor.enumerable || !('value' in descriptor))
      throw new WAWCryptoError()
    result[key] = descriptor.value
  }
  return result
}

export function validateU64(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !/^[1-9][0-9]{0,19}$/.test(value) ||
    BigInt(value) > U64_MAX
  )
    throw new WAWCryptoError()
  return value
}

export function validateHex32(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value))
    throw new WAWCryptoError()
  return value
}

function validateMembers(record: Record<string, unknown>): void {
  for (const [key, prefix] of [
    ['attachment_id', 'att'],
    ['workspace_id', 'aws'],
    ['project_id', 'prj'],
    ['runtime_host_installation_id', 'wri'],
  ]) {
    const value = record[key]
    if (
      typeof value !== 'string' ||
      !new RegExp(`^${prefix}_[a-f0-9]{32}$`).test(value)
    )
      throw new WAWCryptoError()
  }
  if (record.agent_type !== 'claude' && record.agent_type !== 'codex')
    throw new WAWCryptoError()
  for (const key of [
    'runtime_host_installation_revision',
    'auth_epoch',
    'api_authority_epoch',
    'lease_number',
    'generation',
    'binding_revision',
  ])
    validateU64(record[key])
  validateHex32(record.binding_digest)
}

export function validateAdmission(value: unknown): AdmissionTuple {
  const record = exactRecord(value, ADMISSION_KEYS)
  validateMembers(record)
  if (record.mode !== 'writer') throw new WAWCryptoError()
  return Object.freeze(record) as unknown as AdmissionTuple
}

export function deriveContext(
  admission: unknown,
  runtimeEpoch: unknown,
): HandshakeContext {
  const validated = validateAdmission(admission)
  const record: Record<string, unknown> = {}
  for (const key of ADMISSION_KEYS)
    if (key !== 'mode') record[key] = validated[key]
  return validateContext({
    ...record,
    runtime_epoch: validateU64(runtimeEpoch),
    protocol_id: WAW_PROTOCOL_ID,
    crypto_envelope_version: 1,
  })
}

export function validateContext(value: unknown): HandshakeContext {
  const record = exactRecord(value, CONTEXT_KEYS)
  validateMembers(record)
  validateU64(record.runtime_epoch)
  if (
    record.protocol_id !== WAW_PROTOCOL_ID ||
    record.crypto_envelope_version !== 1
  )
    throw new WAWCryptoError()
  return Object.freeze(record) as unknown as HandshakeContext
}

/** RFC 8785 equivalent for this closed ASCII string / literal integer schema. */
export function canonicalContextBytes(value: unknown): Uint8Array {
  const context = validateContext(value)
  const canonical = Object.fromEntries(
    Object.entries(context).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
  )
  return new TextEncoder().encode(JSON.stringify(canonical))
}
