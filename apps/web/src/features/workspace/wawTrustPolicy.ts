/**
 * Browser verification for independently provisioned WAW public trust records.
 *
 * The provider, its durable floors, trusted clock and network policy are separate
 * deployment authorities. This module can verify their bounded public snapshot;
 * its interfaces and a successful software test do not qualify a provider.
 */

import {
  parseBootstrapRecord,
  parsePinRecord,
  parseRootRecord,
  TRUST_RECORD_LIMIT,
  trustTimestamp,
  validateTrustOrigin,
  verifyTrustRecordSignature,
  WAWTrustRecordError,
  type BootstrapRecord,
  type PinRecord,
  type RootRecord,
} from './wawTrustRecords'

const MAX_ROOT_CHAIN = 64
const CLOCK_SKEW_MS = 300_000
const MAX_U64 = 18_446_744_073_709_551_615n
const SNAPSHOT_EPOCH = /^[A-Za-z0-9._:-]{1,128}$/
const HOST_ID = /^wri_[a-f0-9]{32}$/
const KEY_ID = /^[a-z0-9._-]{1,64}$/
const CHECKPOINT_KEYS = [
  'schema_version',
  'root_revision',
  'key_id',
  'public_key',
  'signer_key_id',
  'signer_public_key',
  'root_history_sha256',
  'accepted_at',
] as const
const FLOOR_KEYS = ['root_revision', 'pin'] as const
const PIN_FLOOR_KEYS = [
  'origin',
  'runtime_host_installation_id',
  'pin_revision',
] as const
const TIME_KEYS = ['utc', 'non_backward'] as const
const ORIGIN_PROOF_KEYS = [
  'effective_origin',
  'admitted_api_origin',
  'runtime_host_installation_id',
  'network_policy',
  'verified',
] as const
const SNAPSHOT_KEYS = [
  'schema_version',
  'provider_epoch',
  'bootstrap_record',
  'root_records',
  'pin_record',
  'authenticated_checkpoint',
  'persisted_floors',
  'trusted_time',
  'origin_network_proof',
] as const

export interface WAWAuthenticatedRootCheckpoint {
  readonly schema_version: 'waw-runtime-root-checkpoint-v1'
  readonly root_revision: number
  readonly key_id: string
  readonly public_key: string
  readonly signer_key_id: string
  readonly signer_public_key: string
  /** SHA-256 of the exact canonical root history through this checkpoint. */
  readonly root_history_sha256: string
  /** Trusted UTC at which the provider atomically accepted that full history. */
  readonly accepted_at: string
}

export interface WAWTrustPinFloor {
  readonly origin: string
  readonly runtime_host_installation_id: string
  readonly pin_revision: number
}

export interface WAWTrustPersistedFloors {
  readonly root_revision: number
  readonly pin: WAWTrustPinFloor
}

export interface WAWTrustedTimeEvidence {
  readonly utc: string
  readonly non_backward: true
}

export interface WAWOriginNetworkProof {
  readonly effective_origin: string
  readonly admitted_api_origin: string
  readonly runtime_host_installation_id: string
  readonly network_policy: 'production' | 'loopback-development'
  readonly verified: true
}

export interface WAWTrustProviderSnapshot {
  readonly schema_version: 'waw-trust-provider-snapshot-v1'
  readonly provider_epoch: string
  readonly bootstrap_record: Uint8Array
  readonly root_records: readonly Uint8Array[]
  readonly pin_record: Uint8Array
  readonly authenticated_checkpoint: WAWAuthenticatedRootCheckpoint | null
  readonly persisted_floors: WAWTrustPersistedFloors
  readonly trusted_time: WAWTrustedTimeEvidence
  readonly origin_network_proof: WAWOriginNetworkProof
}

export interface WAWTrustAuthorizationRequest {
  readonly effective_origin: string
  readonly admitted_api_origin: string
  readonly runtime_host_installation_id: string
  /** Exact positive uint64 wire string; never converted through Number. */
  readonly runtime_host_installation_revision: string
}

/** Public pin metadata only. This is not Noise, ADMITTED or input authority. */
export interface WAWRuntimePinAuthorization {
  readonly schema_version: 'waw-runtime-pin.v1'
  readonly repository: 'ForceMind/agentbox'
  readonly origin: string
  readonly pin_revision: number
  readonly runtime_host_installation_id: string
  readonly runtime_host_installation_revision: number
  readonly runtime_attestation_x25519_fingerprint: string
  readonly valid_from: string
  readonly valid_until: string
  readonly key_id: string
}

export interface WAWTrustCommitEvidence {
  readonly provider_epoch: string
  readonly trusted_time: WAWTrustedTimeEvidence
}

/**
 * The asynchronous read obtains final trusted time. The synchronous guard is
 * called immediately before state replacement and must identify the exact
 * still-live provider registration and epoch without yielding.
 */
export interface WAWTrustCommitGuard {
  readEvidence(providerEpoch: string): Promise<WAWTrustCommitEvidence>
  isCurrent(providerEpoch: string): boolean
}

interface AcceptedPinState {
  readonly record: PinRecord
  readonly floor: number
  readonly retiredFingerprints: ReadonlySet<string>
}

interface AcceptedState {
  readonly bootstrap: BootstrapRecord
  readonly root: RootRecord
  readonly rootHistory: readonly RootRecord[]
  readonly rootFloor: number
  readonly retiredRootKeyIds: ReadonlySet<string>
  readonly revokedRootKeyIds: ReadonlySet<string>
  readonly pins: ReadonlyMap<string, AcceptedPinState>
  readonly trustedUtcMs: number
}

interface PreparedUpdate {
  readonly baseVersion: number
  readonly providerEpoch: string
  readonly initialTrustedUtcMs: number
  readonly bootstrap: BootstrapRecord
  readonly root: RootRecord
  readonly rootHistory: readonly RootRecord[]
  readonly rootFloor: number
  readonly retiredRootKeyIds: ReadonlySet<string>
  readonly revokedRootKeyIds: ReadonlySet<string>
  readonly pins: ReadonlyMap<string, AcceptedPinState>
  readonly pin: PinRecord
  readonly timeRecords: readonly (RootRecord | PinRecord)[]
}

function requireTrust(condition: unknown): asserts condition {
  if (!condition) throw new WAWTrustRecordError()
}

function exactKeys(
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }
  const actual = Object.keys(value)
  return (
    actual.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  )
}

function safeRevision(value: unknown, allowZero = false): number {
  requireTrust(
    typeof value === 'number' &&
      Number.isSafeInteger(value) &&
      (allowZero ? value >= 0 : value > 0),
  )
  return value
}

function requireBoundedBytes(value: unknown): asserts value is Uint8Array {
  requireTrust(
    ArrayBuffer.isView(value) &&
      Object.prototype.toString.call(value) === '[object Uint8Array]' &&
      value.byteLength > 0 &&
      value.byteLength <= TRUST_RECORD_LIMIT,
  )
}

function copyBytes(value: unknown): Uint8Array {
  // Keep this defense even though the snapshot performs a whole-set preflight:
  // a detached/resized view must not cross the copy boundary.
  requireBoundedBytes(value)
  return new Uint8Array(value)
}

function copyCheckpoint(
  value: unknown,
): Readonly<WAWAuthenticatedRootCheckpoint> | null {
  if (value === null) return null
  requireTrust(exactKeys(value, CHECKPOINT_KEYS))
  requireTrust(value.schema_version === 'waw-runtime-root-checkpoint-v1')
  const rootRevision = safeRevision(value.root_revision)
  requireTrust(typeof value.key_id === 'string' && KEY_ID.test(value.key_id))
  requireTrust(
    typeof value.public_key === 'string' &&
      typeof value.signer_key_id === 'string' &&
      KEY_ID.test(value.signer_key_id) &&
      typeof value.signer_public_key === 'string' &&
      typeof value.root_history_sha256 === 'string' &&
      /^[a-f0-9]{64}$/.test(value.root_history_sha256) &&
      typeof value.accepted_at === 'string',
  )
  return Object.freeze({
    schema_version: 'waw-runtime-root-checkpoint-v1',
    root_revision: rootRevision,
    key_id: value.key_id,
    public_key: value.public_key,
    signer_key_id: value.signer_key_id,
    signer_public_key: value.signer_public_key,
    root_history_sha256: value.root_history_sha256,
    accepted_at: value.accepted_at,
  })
}

function copyFloors(value: unknown): Readonly<WAWTrustPersistedFloors> {
  requireTrust(exactKeys(value, FLOOR_KEYS))
  requireTrust(exactKeys(value.pin, PIN_FLOOR_KEYS))
  const pin = value.pin
  requireTrust(
    typeof pin.origin === 'string' &&
      typeof pin.runtime_host_installation_id === 'string' &&
      HOST_ID.test(pin.runtime_host_installation_id),
  )
  const copiedPin = Object.freeze({
    origin: validateTrustOrigin(pin.origin),
    runtime_host_installation_id: pin.runtime_host_installation_id,
    pin_revision: safeRevision(pin.pin_revision),
  })
  return Object.freeze({
    root_revision: safeRevision(value.root_revision),
    pin: copiedPin,
  })
}

function copyTrustedTime(value: unknown): Readonly<WAWTrustedTimeEvidence> {
  requireTrust(exactKeys(value, TIME_KEYS))
  requireTrust(value.non_backward === true && typeof value.utc === 'string')
  trustTimestamp(value.utc)
  return Object.freeze({ utc: value.utc, non_backward: true })
}

function copyOriginProof(value: unknown): Readonly<WAWOriginNetworkProof> {
  requireTrust(exactKeys(value, ORIGIN_PROOF_KEYS))
  requireTrust(
    value.verified === true &&
      typeof value.runtime_host_installation_id === 'string' &&
      HOST_ID.test(value.runtime_host_installation_id) &&
      (value.network_policy === 'production' ||
        value.network_policy === 'loopback-development'),
  )
  return Object.freeze({
    effective_origin: validateTrustOrigin(value.effective_origin),
    admitted_api_origin: validateTrustOrigin(value.admitted_api_origin),
    runtime_host_installation_id: value.runtime_host_installation_id,
    network_policy: value.network_policy,
    verified: true,
  })
}

/** Defensive copy of a bounded port snapshot. It confers no trust by itself. */
export function copyWAWTrustProviderSnapshot(
  value: unknown,
): Readonly<WAWTrustProviderSnapshot> {
  try {
    requireTrust(exactKeys(value, SNAPSHOT_KEYS))
    requireTrust(
      value.schema_version === 'waw-trust-provider-snapshot-v1' &&
        typeof value.provider_epoch === 'string' &&
        SNAPSHOT_EPOCH.test(value.provider_epoch),
    )
    requireTrust(
      Array.isArray(value.root_records) &&
        value.root_records.length > 0 &&
        value.root_records.length <= MAX_ROOT_CHAIN,
    )
    const bootstrapRecord = value.bootstrap_record
    const suppliedRootRecords = value.root_records
    const pinRecord = value.pin_record
    // Preflight every authority-bearing record before the first byte copy.
    requireBoundedBytes(bootstrapRecord)
    const rootRecords: Uint8Array[] = []
    for (let index = 0; index < suppliedRootRecords.length; index += 1) {
      requireTrust(Object.hasOwn(suppliedRootRecords, index))
      const rootRecord = suppliedRootRecords[index]
      requireBoundedBytes(rootRecord)
      rootRecords.push(rootRecord)
    }
    requireBoundedBytes(pinRecord)
    const copiedBootstrapRecord = copyBytes(bootstrapRecord)
    const copiedRootRecords: Uint8Array[] = []
    for (const rootRecord of rootRecords) {
      copiedRootRecords.push(copyBytes(rootRecord))
    }
    const copiedPinRecord = copyBytes(pinRecord)
    return Object.freeze({
      schema_version: 'waw-trust-provider-snapshot-v1',
      provider_epoch: value.provider_epoch,
      bootstrap_record: copiedBootstrapRecord,
      root_records: Object.freeze(copiedRootRecords),
      pin_record: copiedPinRecord,
      authenticated_checkpoint: copyCheckpoint(value.authenticated_checkpoint),
      persisted_floors: copyFloors(value.persisted_floors),
      trusted_time: copyTrustedTime(value.trusted_time),
      origin_network_proof: copyOriginProof(value.origin_network_proof),
    })
  } catch {
    throw new WAWTrustRecordError()
  }
}

function exactU64(value: unknown): bigint {
  requireTrust(typeof value === 'string' && /^[1-9][0-9]{0,19}$/.test(value))
  const parsed = BigInt(value)
  requireTrust(parsed <= MAX_U64)
  return parsed
}

function scopeKey(origin: string, hostId: string): string {
  return `${origin}\0${hostId}`
}

function sameRecord(
  left: RootRecord | PinRecord,
  right: RootRecord | PinRecord,
) {
  const leftEntries = Object.entries(left)
  const rightEntries = Object.entries(right)
  return (
    leftEntries.length === rightEntries.length &&
    leftEntries.every(
      ([key, value]) =>
        Object.hasOwn(right, key) && right[key as keyof typeof right] === value,
    )
  )
}

function validAt(record: RootRecord | PinRecord, now: number): void {
  const from = trustTimestamp(record.valid_from)
  const until = trustTimestamp(record.valid_until)
  requireTrust(now >= from - CLOCK_SKEW_MS && now <= until + CLOCK_SKEW_MS)
}

function isLoopbackOrigin(origin: string): boolean {
  const host = new URL(origin).hostname
  return host === '127.0.0.1' || host === '[::1]'
}

function validateNetworkPolicy(
  proof: WAWOriginNetworkProof,
  origin: string,
): void {
  if (proof.network_policy === 'loopback-development') {
    requireTrust(isLoopbackOrigin(origin))
    return
  }
  const hostname = new URL(origin).hostname
  requireTrust(
    !isLoopbackOrigin(origin) &&
      hostname !== 'localhost' &&
      (hostname.includes('.') || hostname.startsWith('[')),
  )
}

async function sha256(value: Uint8Array): Promise<string> {
  const digest = new Uint8Array(
    await crypto.subtle.digest('SHA-256', value as BufferSource),
  )
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, '0')).join(
    '',
  )
}

function b64urlEncode(value: Uint8Array): string {
  let binary = ''
  for (const byte of value) binary += String.fromCharCode(byte)
  return btoa(binary)
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '')
}

async function rootHistoryDigest(
  records: readonly Uint8Array[],
): Promise<string> {
  return sha256(
    new TextEncoder().encode(JSON.stringify(records.map(b64urlEncode))),
  )
}

function publicAuthorization(
  pin: PinRecord,
): Readonly<WAWRuntimePinAuthorization> {
  return Object.freeze({
    schema_version: pin.schema_version,
    repository: pin.repository,
    origin: pin.origin,
    pin_revision: pin.pin_revision,
    runtime_host_installation_id: pin.runtime_host_installation_id,
    runtime_host_installation_revision: pin.runtime_host_installation_revision,
    runtime_attestation_x25519_fingerprint:
      pin.runtime_attestation_x25519_fingerprint,
    valid_from: pin.valid_from,
    valid_until: pin.valid_until,
    key_id: pin.key_id,
  })
}

/**
 * Stateful rollback consumer. Preparation is side-effect free; commit is one
 * synchronous replacement after the provider supplies fresh commit evidence.
 */
export class WAWTrustPolicy {
  #version = 0
  #state: AcceptedState | null = null

  async #prepare(
    rawSnapshot: WAWTrustProviderSnapshot,
    request: WAWTrustAuthorizationRequest,
  ): Promise<PreparedUpdate> {
    const snapshot = copyWAWTrustProviderSnapshot(rawSnapshot)
    const initialTrustedUtcMs = trustTimestamp(snapshot.trusted_time.utc)
    requireTrust(initialTrustedUtcMs >= (this.#state?.trustedUtcMs ?? 0))
    const effectiveOrigin = validateTrustOrigin(request.effective_origin)
    const admittedApiOrigin = validateTrustOrigin(request.admitted_api_origin)
    requireTrust(
      typeof request.runtime_host_installation_id === 'string' &&
        HOST_ID.test(request.runtime_host_installation_id),
    )
    const wireHostRevision = exactU64(
      request.runtime_host_installation_revision,
    )
    const proof = snapshot.origin_network_proof
    requireTrust(
      effectiveOrigin === admittedApiOrigin &&
        proof.effective_origin === effectiveOrigin &&
        proof.admitted_api_origin === admittedApiOrigin &&
        proof.runtime_host_installation_id ===
          request.runtime_host_installation_id,
    )
    validateNetworkPolicy(proof, effectiveOrigin)

    const bootstrap = parseBootstrapRecord(snapshot.bootstrap_record)
    const roots = snapshot.root_records.map((record) => parseRootRecord(record))
    const pin = parsePinRecord(snapshot.pin_record)
    const rootFloor = snapshot.persisted_floors.root_revision
    const pinFloor = snapshot.persisted_floors.pin
    requireTrust(
      roots.at(-1)!.root_revision === rootFloor &&
        pinFloor.origin === pin.origin &&
        pinFloor.runtime_host_installation_id ===
          pin.runtime_host_installation_id &&
        pinFloor.pin_revision === pin.pin_revision,
    )

    const checkpoint = snapshot.authenticated_checkpoint
    const latestActiveIndex =
      roots.at(-1)!.state === 'ACTIVE' ? roots.length - 1 : roots.length - 2
    requireTrust(
      latestActiveIndex >= 0 && roots[latestActiveIndex]!.state === 'ACTIVE',
    )
    const latestActive = roots[latestActiveIndex]!
    requireTrust(
      latestActive.root_revision === 1
        ? checkpoint === null
        : checkpoint !== null,
    )
    let checkpointIndex = -1
    if (checkpoint !== null) {
      requireTrust(checkpoint !== null)
      checkpointIndex = roots.findIndex(
        (root) =>
          root.root_revision === checkpoint.root_revision &&
          root.key_id === checkpoint.key_id &&
          root.public_key === checkpoint.public_key &&
          root.signer_key_id === checkpoint.signer_key_id,
      )
      requireTrust(
        checkpointIndex === latestActiveIndex && checkpointIndex >= 1,
      )
      const checkpointSigner = roots[checkpointIndex - 1]!
      requireTrust(
        checkpoint.signer_key_id === checkpointSigner.key_id &&
          checkpoint.signer_public_key === checkpointSigner.public_key,
      )
      requireTrust(
        checkpoint.root_history_sha256 ===
          (await rootHistoryDigest(
            snapshot.root_records.slice(0, checkpointIndex + 1),
          )),
      )
      const acceptedAt = trustTimestamp(checkpoint.accepted_at)
      requireTrust(acceptedAt <= initialTrustedUtcMs)
      validAt(roots[checkpointIndex - 1]!, acceptedAt)
      validAt(roots[checkpointIndex]!, acceptedAt)
    }
    requireTrust(
      pin.origin === effectiveOrigin &&
        pin.runtime_host_installation_id ===
          request.runtime_host_installation_id &&
        BigInt(pin.runtime_host_installation_revision) === wireHostRevision,
    )

    requireTrust(roots[0]!.root_revision === 1)
    let previous: RootRecord | null = this.#state?.root ?? null
    let index = 0
    const retiredRootKeyIds = new Set(this.#state?.retiredRootKeyIds ?? [])
    const revokedRootKeyIds = new Set(this.#state?.revokedRootKeyIds ?? [])
    const rootHistory: RootRecord[] = [...(this.#state?.rootHistory ?? [])]
    const timeRecords: (RootRecord | PinRecord)[] = []

    if (this.#state) {
      requireTrust(
        bootstrap.key_id === this.#state.bootstrap.key_id &&
          bootstrap.public_key === this.#state.bootstrap.public_key &&
          rootFloor >= this.#state.rootFloor,
      )
      const acceptedIndex = roots.findIndex((root) =>
        sameRecord(root, this.#state!.root),
      )
      previous = this.#state.root
      requireTrust(acceptedIndex >= 0)
      const suppliedHistory = roots.slice(0, acceptedIndex + 1)
      requireTrust(
        suppliedHistory.length === rootHistory.length &&
          suppliedHistory.every((root, rootIndex) =>
            sameRecord(root, rootHistory[rootIndex]!),
          ),
      )
      index = acceptedIndex + 1
    } else {
      await verifyTrustRecordSignature(roots[0]!, bootstrap.public_key)
      previous = roots[0]!
      rootHistory.push(previous)
      index = 1
    }

    requireTrust(previous !== null)
    for (; index < roots.length; index += 1) {
      const candidate = roots[index]!
      requireTrust(
        previous.state === 'ACTIVE' &&
          previous.root_revision < Number.MAX_SAFE_INTEGER &&
          candidate.root_revision === previous.root_revision + 1 &&
          candidate.supersedes_key_id === previous.key_id,
      )
      if (candidate.state === 'ACTIVE') {
        requireTrust(
          candidate.signer_key_id === previous.key_id &&
            candidate.key_id !== previous.key_id &&
            candidate.public_key !== previous.public_key &&
            !retiredRootKeyIds.has(candidate.key_id) &&
            !revokedRootKeyIds.has(candidate.key_id),
        )
        await verifyTrustRecordSignature(candidate, previous.public_key)
        retiredRootKeyIds.add(previous.key_id)
      } else {
        requireTrust(
          candidate.signer_key_id === bootstrap.key_id &&
            candidate.key_id === previous.key_id &&
            candidate.public_key === previous.public_key,
        )
        await verifyTrustRecordSignature(candidate, bootstrap.public_key)
        revokedRootKeyIds.add(candidate.key_id)
      }
      previous = candidate
      rootHistory.push(candidate)
    }
    requireTrust(previous.root_revision === rootFloor)
    timeRecords.push(previous)
    if (previous.state === 'ACTIVE') {
      requireTrust(
        !retiredRootKeyIds.has(previous.key_id) &&
          !revokedRootKeyIds.has(previous.key_id),
      )
    }

    await verifyTrustRecordSignature(pin, previous.public_key)
    requireTrust(pin.key_id === previous.key_id)
    timeRecords.push(pin)

    const pins = new Map(this.#state?.pins ?? [])
    const pinScope = scopeKey(pin.origin, pin.runtime_host_installation_id)
    const oldPin = pins.get(pinScope)
    let retiredFingerprints = new Set(oldPin?.retiredFingerprints ?? [])
    if (oldPin) {
      requireTrust(pin.pin_revision >= oldPin.floor)
      if (pin.pin_revision === oldPin.floor) {
        requireTrust(sameRecord(pin, oldPin.record))
        retiredFingerprints = new Set(oldPin.retiredFingerprints)
      } else {
        requireTrust(
          pin.supersedes_fingerprint ===
            oldPin.record.runtime_attestation_x25519_fingerprint,
        )
        if (pin.revoked_at !== null) {
          requireTrust(
            pin.runtime_attestation_x25519_fingerprint ===
              oldPin.record.runtime_attestation_x25519_fingerprint,
          )
        } else {
          requireTrust(
            pin.runtime_attestation_x25519_fingerprint !==
              oldPin.record.runtime_attestation_x25519_fingerprint &&
              !retiredFingerprints.has(
                pin.runtime_attestation_x25519_fingerprint,
              ) &&
              trustTimestamp(pin.valid_from) >
                trustTimestamp(oldPin.record.valid_until),
          )
        }
        retiredFingerprints.add(
          oldPin.record.runtime_attestation_x25519_fingerprint,
        )
      }
    }
    pins.set(
      pinScope,
      Object.freeze({
        record: pin,
        floor: pin.pin_revision,
        retiredFingerprints,
      }),
    )

    return {
      baseVersion: this.#version,
      providerEpoch: snapshot.provider_epoch,
      initialTrustedUtcMs,
      bootstrap,
      root: previous,
      rootHistory,
      rootFloor,
      retiredRootKeyIds,
      revokedRootKeyIds,
      pins,
      pin,
      timeRecords,
    }
  }

  /**
   * Verify a read-only candidate and atomically replace accepted public state.
   * A valid revocation is committed but returns null and never authorizes use.
   */
  async consume(
    snapshot: WAWTrustProviderSnapshot,
    request: WAWTrustAuthorizationRequest,
    commitGuard: WAWTrustCommitGuard,
  ): Promise<Readonly<WAWRuntimePinAuthorization> | null> {
    try {
      const prepared = await this.#prepare(snapshot, request)
      const evidence = await commitGuard.readEvidence(prepared.providerEpoch)
      requireTrust(
        exactKeys(evidence, ['provider_epoch', 'trusted_time']) &&
          evidence.provider_epoch === prepared.providerEpoch,
      )
      const finalTime = copyTrustedTime(evidence.trusted_time)
      const trustedUtcMs = trustTimestamp(finalTime.utc)
      requireTrust(
        trustedUtcMs >= prepared.initialTrustedUtcMs &&
          trustedUtcMs >= (this.#state?.trustedUtcMs ?? 0) &&
          prepared.baseVersion === this.#version,
      )
      for (const record of prepared.timeRecords) validAt(record, trustedUtcMs)

      const state: AcceptedState = Object.freeze({
        bootstrap: prepared.bootstrap,
        root: prepared.root,
        rootHistory: Object.freeze([...prepared.rootHistory]),
        rootFloor: prepared.rootFloor,
        retiredRootKeyIds: new Set(prepared.retiredRootKeyIds),
        revokedRootKeyIds: new Set(prepared.revokedRootKeyIds),
        pins: new Map(prepared.pins),
        trustedUtcMs,
      })
      requireTrust(
        prepared.baseVersion === this.#version &&
          commitGuard.isCurrent(prepared.providerEpoch) === true,
      )
      this.#state = state
      this.#version += 1

      if (
        prepared.root.state !== 'ACTIVE' ||
        prepared.pin.revoked_at !== null
      ) {
        return null
      }
      requireTrust(
        !prepared.retiredRootKeyIds.has(prepared.root.key_id) &&
          !prepared.revokedRootKeyIds.has(prepared.root.key_id),
      )
      return publicAuthorization(prepared.pin)
    } catch {
      throw new WAWTrustRecordError()
    }
  }
}
