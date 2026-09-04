import type {
  WAWTrustProviderInvalidation,
  WAWTrustProviderPort,
} from './wawTrustProvider'
import type { WAWTrustProviderSnapshot } from './wawTrustPolicy'
import { WAW_TRUST_EXTENSION_ID } from './wawTrustChromiumIdentity.generated'

const PORT_NAME = 'agentbox-waw-trust-v1'
const MAX_RESPONSE_BYTES = 512 * 1024
const MAX_RECORD_BYTES = 4096
const MAX_ROOTS = 64
// One store snapshot may serially observe two process-lock windows and one
// bounded DNS proof. Keep the page deadline above that proven 3 s path.
const RESPONSE_DEADLINE_MS = 6000
const HEARTBEAT_INTERVAL_MS = 5000
const ID = /^[a-z]+_[a-f0-9]{32}$/
const DECIMAL = /^(?:0|[1-9][0-9]{0,19})$/
const NONCE = /^[A-Za-z0-9_-]{43}$/
const PROVIDER_EPOCH = /^[A-Za-z0-9._:-]{1,128}$/
const BASE_RESPONSE_KEYS = [
  'type',
  'protocol_version',
  'page_nonce',
  'sequence',
  'correlation_id',
] as const

interface ChromeEvent<T extends (...args: never[]) => void> {
  addListener(listener: T): void
}

interface ChromePort {
  readonly onMessage: ChromeEvent<(message: unknown) => void>
  readonly onDisconnect: ChromeEvent<() => void>
  postMessage(message: unknown): void
  disconnect(): void
}

interface ChromeRuntime {
  connect(extensionId: string, options: Readonly<{ name: string }>): ChromePort
}

interface PendingRequest {
  readonly correlationId: string
  readonly expectedType: 'OPENED' | 'SNAPSHOT' | 'PONG'
  readonly resolve: (message: Record<string, unknown>) => void
  readonly reject: (error: Error) => void
  readonly timeout: ReturnType<typeof globalThis.setTimeout>
}

function failure(): Error {
  return new Error('RUNTIME_ATTESTATION_UNVERIFIED')
}

function exactRecord(
  value: unknown,
  required: readonly string[],
): Record<string, unknown> | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  const record = value as Record<string, unknown>
  const keys = Object.keys(record)
  return keys.length === required.length &&
    required.every((key) => key in record)
    ? record
    : null
}

function encodedSize(value: unknown): number {
  try {
    return new TextEncoder().encode(JSON.stringify(value)).byteLength
  } catch {
    return Number.POSITIVE_INFINITY
  }
}

function b64url(value: unknown, limit: number): Uint8Array {
  if (
    typeof value !== 'string' ||
    value.length < 1 ||
    value.includes('=') ||
    !/^[A-Za-z0-9_-]+$/.test(value)
  ) {
    throw failure()
  }
  if (value.length % 4 === 1) throw failure()
  let binary: string
  try {
    const padding = (4 - (value.length % 4)) % 4
    binary = atob(
      value.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat(padding),
    )
  } catch {
    throw failure()
  }
  if (binary.length < 1 || binary.length > limit) throw failure()
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0))
  const canonical = btoa(binary)
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '')
  if (canonical !== value) throw failure()
  return bytes
}

function decodeSnapshot(value: unknown): WAWTrustProviderSnapshot {
  const snapshot = exactRecord(value, [
    'schema_version',
    'provider_epoch',
    'bootstrap_record',
    'root_records',
    'pin_record',
    'authenticated_checkpoint',
    'persisted_floors',
    'trusted_time',
    'origin_network_proof',
  ])
  if (
    !snapshot ||
    snapshot.schema_version !== 'waw-trust-provider-snapshot-v1' ||
    typeof snapshot.provider_epoch !== 'string' ||
    !PROVIDER_EPOCH.test(snapshot.provider_epoch) ||
    !Array.isArray(snapshot.root_records) ||
    snapshot.root_records.length < 1 ||
    snapshot.root_records.length > MAX_ROOTS
  ) {
    throw failure()
  }
  return {
    schema_version: 'waw-trust-provider-snapshot-v1',
    provider_epoch: snapshot.provider_epoch,
    bootstrap_record: b64url(snapshot.bootstrap_record, MAX_RECORD_BYTES),
    root_records: snapshot.root_records.map((record) =>
      b64url(record, MAX_RECORD_BYTES),
    ),
    pin_record: b64url(snapshot.pin_record, MAX_RECORD_BYTES),
    authenticated_checkpoint:
      snapshot.authenticated_checkpoint as WAWTrustProviderSnapshot['authenticated_checkpoint'],
    persisted_floors:
      snapshot.persisted_floors as WAWTrustProviderSnapshot['persisted_floors'],
    trusted_time:
      snapshot.trusted_time as WAWTrustProviderSnapshot['trusted_time'],
    origin_network_proof:
      snapshot.origin_network_proof as WAWTrustProviderSnapshot['origin_network_proof'],
  }
}

function nonce(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  let binary = ''
  for (const value of bytes) binary += String.fromCharCode(value)
  return btoa(binary)
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '')
}

function correlation(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return `req_${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`
}

export class ChromiumWAWTrustProviderPort implements WAWTrustProviderPort {
  readonly authority = 'independent' as const
  readonly #port: ChromePort
  readonly #pageNonce = nonce()
  readonly #listeners = new Set<
    (reason: WAWTrustProviderInvalidation) => void
  >()
  #sequence = 1n
  #expectedResponse = 1n
  #pending: PendingRequest | null = null
  #tail: Promise<void> = Promise.resolve()
  #queued = 0
  #heartbeat: ReturnType<typeof globalThis.setTimeout> | null = null
  #closed = false
  readonly #opened: Promise<void>

  constructor(runtime: ChromeRuntime, extensionId: string) {
    if (!/^[a-p]{32}$/.test(extensionId)) throw failure()
    this.#port = runtime.connect(extensionId, { name: PORT_NAME })
    this.#port.onMessage.addListener((message) => this.#receive(message))
    this.#port.onDisconnect.addListener(() => this.#invalidate('lost'))
    this.#opened = this.#enqueue('OPENED', 'OPEN').then(() => {
      this.#scheduleHeartbeat()
    })
  }

  subscribeInvalidation(
    listener: (reason: WAWTrustProviderInvalidation) => void,
  ): () => void {
    if (this.#closed || typeof listener !== 'function') throw failure()
    this.#listeners.add(listener)
    let live = true
    return () => {
      if (!live) return
      live = false
      this.#listeners.delete(listener)
    }
  }

  async getAtomicSnapshot(): Promise<WAWTrustProviderSnapshot> {
    await this.#opened
    const response = await this.#enqueue('SNAPSHOT', 'SNAPSHOT_GET')
    return decodeSnapshot(response.snapshot)
  }

  close(): void {
    this.#invalidate('closed')
  }

  dispose(): void {
    this.close()
  }

  #enqueue(
    expectedType: PendingRequest['expectedType'],
    type: 'OPEN' | 'SNAPSHOT_GET' | 'PING',
  ): Promise<Record<string, unknown>> {
    if (this.#closed || this.#queued >= 4) {
      return Promise.reject(failure())
    }
    this.#queued += 1
    const result = this.#tail.then(() => this.#request(expectedType, type))
    this.#tail = result.then(
      () => undefined,
      () => undefined,
    )
    void result.then(
      () => {
        this.#queued -= 1
      },
      () => {
        this.#queued -= 1
      },
    )
    return result
  }

  async #request(
    expectedType: PendingRequest['expectedType'],
    type: 'OPEN' | 'SNAPSHOT_GET' | 'PING',
  ): Promise<Record<string, unknown>> {
    if (this.#closed || this.#pending) throw failure()
    const correlationId = correlation()
    const message = {
      type,
      protocol_version: 1,
      page_nonce: this.#pageNonce,
      sequence: String(this.#sequence),
      correlation_id: correlationId,
    }
    this.#sequence += 1n
    return await new Promise((resolve, reject) => {
      const timeout = globalThis.setTimeout(() => {
        this.#invalidate('lost')
        reject(failure())
      }, RESPONSE_DEADLINE_MS)
      this.#pending = {
        correlationId,
        expectedType,
        resolve,
        reject,
        timeout,
      }
      try {
        this.#port.postMessage(message)
      } catch {
        this.#invalidate('lost')
      }
    })
  }

  #receive(value: unknown): void {
    const loose =
      value !== null && typeof value === 'object' && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : null
    const extras =
      loose?.type === 'OPENED'
        ? [
            'provider_installation_id',
            'provider_epoch',
            'document_id',
            'origin',
          ]
        : loose?.type === 'SNAPSHOT'
          ? ['snapshot']
          : loose?.type === 'INVALIDATE' || loose?.type === 'CLOSE'
            ? ['reason']
            : []
    const common = exactRecord(value, [...BASE_RESPONSE_KEYS, ...extras])
    if (
      !common ||
      encodedSize(common) > MAX_RESPONSE_BYTES ||
      common.protocol_version !== 1 ||
      common.page_nonce !== this.#pageNonce ||
      !NONCE.test(common.page_nonce) ||
      typeof common.sequence !== 'string' ||
      !DECIMAL.test(common.sequence) ||
      BigInt(common.sequence) !== this.#expectedResponse ||
      typeof common.type !== 'string' ||
      typeof common.correlation_id !== 'string' ||
      !ID.test(common.correlation_id)
    ) {
      this.#invalidate('lost')
      return
    }
    this.#expectedResponse += 1n
    if (common.type === 'INVALIDATE') {
      const reason = common.reason
      this.#invalidate(
        reason === 'changed' ||
          reason === 'closed' ||
          reason === 'time-backward'
          ? reason
          : 'lost',
      )
      return
    }
    const pending = this.#pending
    if (
      !pending ||
      common.type !== pending.expectedType ||
      common.correlation_id !== pending.correlationId
    ) {
      this.#invalidate('lost')
      return
    }
    this.#pending = null
    globalThis.clearTimeout(pending.timeout)
    pending.resolve(common)
  }

  #scheduleHeartbeat(): void {
    if (this.#closed || this.#heartbeat !== null) return
    this.#heartbeat = globalThis.setTimeout(() => {
      this.#heartbeat = null
      if (this.#closed) return
      if (this.#pending) {
        this.#scheduleHeartbeat()
        return
      }
      void this.#enqueue('PONG', 'PING')
        .then(() => this.#scheduleHeartbeat())
        .catch(() => this.#invalidate('lost'))
    }, HEARTBEAT_INTERVAL_MS)
  }

  #invalidate(reason: WAWTrustProviderInvalidation): void {
    if (this.#closed) return
    this.#closed = true
    if (this.#heartbeat !== null) {
      globalThis.clearTimeout(this.#heartbeat)
      this.#heartbeat = null
    }
    const pending = this.#pending
    this.#pending = null
    if (pending) {
      globalThis.clearTimeout(pending.timeout)
      pending.reject(failure())
    }
    try {
      this.#port.disconnect()
    } catch {
      // A disconnected browser-owned port is already closed.
    }
    for (const listener of this.#listeners) {
      try {
        listener(reason)
      } catch {
        // A listener cannot preserve the authorization of another listener.
      }
    }
    this.#listeners.clear()
  }
}

function browserRuntime(): ChromeRuntime | null {
  const chromeValue = Reflect.get(globalThis, 'chrome') as
    { runtime?: ChromeRuntime } | undefined
  return chromeValue?.runtime?.connect ? chromeValue.runtime : null
}

/** Production remains unavailable until a signed client enrollment supplies the ID. */
export function createManagedChromiumTrustProvider(): WAWTrustProviderPort | null {
  const runtime = browserRuntime()
  if (!runtime || WAW_TRUST_EXTENSION_ID === null) return null
  return new ChromiumWAWTrustProviderPort(runtime, WAW_TRUST_EXTENSION_ID)
}
