/**
 * Read-only consumer for one explicitly supplied independent trust-provider port.
 *
 * No default/global provider exists here. The page, API, localStorage and
 * IndexedDB cannot create a provider, install records, or reset persisted floors
 * through this interface. A real port still requires separate deployment proof.
 */

import {
  copyWAWTrustProviderSnapshot,
  WAWTrustPolicy,
  type WAWRuntimePinAuthorization,
  type WAWTrustAuthorizationRequest,
  type WAWTrustProviderSnapshot,
} from './wawTrustPolicy'
import { WAWTrustRecordError } from './wawTrustRecords'

export type WAWTrustProviderAuthority = 'independent' | 'synthetic-test'
export type WAWTrustProviderInvalidation =
  'changed' | 'lost' | 'closed' | 'time-backward'

/**
 * Deployment-supplied port. Implementing this TypeScript shape is not proof that
 * its authority, persistence, clock, network policy or invalidation path is real.
 */
export interface WAWTrustProviderPort {
  readonly authority: WAWTrustProviderAuthority
  subscribeInvalidation(
    listener: (reason: WAWTrustProviderInvalidation) => void,
  ): () => void
  getAtomicSnapshot(): Promise<WAWTrustProviderSnapshot>
  dispose(): void
}

export interface WAWTrustProviderConsumerOptions {
  /** Synthetic mode is explicit and exists only for software tests. */
  readonly mode?: 'production' | 'synthetic-test'
}

/**
 * Public pin metadata tied to one exact provider registration generation.
 * Provider invalidation aborts the signal synchronously; this still does not
 * grant Noise, ADMITTED, writer, terminal-input or attachment authority.
 */
export interface WAWTrustAuthorizationLease extends WAWRuntimePinAuthorization {
  readonly generation: number
  readonly signal: AbortSignal
  isCurrent(): boolean
}

interface ProviderRegistration {
  readonly generation: number
  readonly port: WAWTrustProviderPort
  readonly abortController: AbortController
  live: boolean
  providerEpoch: string | null
  unsubscribe: (() => void) | null
  unsubscribed: boolean
}

function fail(): never {
  throw new WAWTrustRecordError()
}

function bytesEqual(left: Uint8Array, right: Uint8Array): boolean {
  return (
    left.byteLength === right.byteLength &&
    left.every((value, index) => value === right[index])
  )
}

/** Compare every authority-bearing field; trusted UTC may advance separately. */
function sameSnapshotAuthority(
  left: Readonly<WAWTrustProviderSnapshot>,
  right: Readonly<WAWTrustProviderSnapshot>,
): boolean {
  const leftCheckpoint = left.authenticated_checkpoint
  const rightCheckpoint = right.authenticated_checkpoint
  const checkpointEqual =
    leftCheckpoint === null || rightCheckpoint === null
      ? leftCheckpoint === rightCheckpoint
      : Object.keys(leftCheckpoint).every(
          (key) =>
            leftCheckpoint[key as keyof typeof leftCheckpoint] ===
            rightCheckpoint[key as keyof typeof rightCheckpoint],
        )
  return (
    left.provider_epoch === right.provider_epoch &&
    bytesEqual(left.bootstrap_record, right.bootstrap_record) &&
    left.root_records.length === right.root_records.length &&
    left.root_records.every((record, index) =>
      bytesEqual(record, right.root_records[index]!),
    ) &&
    bytesEqual(left.pin_record, right.pin_record) &&
    checkpointEqual &&
    left.persisted_floors.root_revision ===
      right.persisted_floors.root_revision &&
    left.persisted_floors.pin.origin === right.persisted_floors.pin.origin &&
    left.persisted_floors.pin.runtime_host_installation_id ===
      right.persisted_floors.pin.runtime_host_installation_id &&
    left.persisted_floors.pin.pin_revision ===
      right.persisted_floors.pin.pin_revision &&
    left.origin_network_proof.effective_origin ===
      right.origin_network_proof.effective_origin &&
    left.origin_network_proof.admitted_api_origin ===
      right.origin_network_proof.admitted_api_origin &&
    left.origin_network_proof.runtime_host_installation_id ===
      right.origin_network_proof.runtime_host_installation_id &&
    left.origin_network_proof.network_policy ===
      right.origin_network_proof.network_policy &&
    right.origin_network_proof.verified === true
  )
}

/**
 * Holds accepted public rollback state while provider invalidations immediately
 * remove usable authorization. It never creates Noise or attachment authority.
 */
export class WAWTrustProviderConsumer {
  readonly #ports: readonly WAWTrustProviderPort[]
  readonly #policy: WAWTrustPolicy
  readonly #requiredAuthority: WAWTrustProviderAuthority
  #generation = 0
  #registration: ProviderRegistration | null = null
  #authorization: Readonly<WAWTrustAuthorizationLease> | null = null
  #closed = false
  readonly #disposedPorts = new WeakSet<object>()

  constructor(
    ports: readonly WAWTrustProviderPort[],
    options: WAWTrustProviderConsumerOptions = {},
  ) {
    this.#ports = Object.freeze([...ports])
    this.#policy = new WAWTrustPolicy()
    this.#requiredAuthority =
      options.mode === 'synthetic-test' ? 'synthetic-test' : 'independent'
  }

  get currentAuthorization(): Readonly<WAWTrustAuthorizationLease> | null {
    return this.#authorization
  }

  #isCurrent(
    registration: ProviderRegistration,
    providerEpoch?: string,
  ): boolean {
    return (
      this.#registration === registration &&
      registration.live &&
      (providerEpoch === undefined ||
        registration.providerEpoch === providerEpoch)
    )
  }

  #disposePort(port: WAWTrustProviderPort): void {
    if (this.#disposedPorts.has(port)) return
    this.#disposedPorts.add(port)
    try {
      port.dispose()
    } catch {
      // A broken provider cannot block browser-side teardown.
    }
  }

  #retireRegistration(
    registration: ProviderRegistration,
    disposePort = false,
  ): void {
    const wasCurrent = this.#registration === registration
    registration.live = false
    if (wasCurrent) {
      this.#generation += 1
      this.#registration = null
      this.#authorization = null
    }
    if (!registration.abortController.signal.aborted) {
      registration.abortController.abort()
    }
    if (!registration.unsubscribed && registration.unsubscribe !== null) {
      const unsubscribe = registration.unsubscribe
      registration.unsubscribe = null
      registration.unsubscribed = true
      try {
        unsubscribe()
      } catch {
        // A broken provider cannot preserve authorization or block local cleanup.
      }
    }
    if (
      disposePort &&
      (wasCurrent ||
        this.#registration === null ||
        this.#registration.port !== registration.port)
    ) {
      this.#disposePort(registration.port)
    }
  }

  #retireCurrent(): void {
    const registration = this.#registration
    if (registration !== null) this.#retireRegistration(registration)
  }

  close(): void {
    if (this.#closed) return
    this.#closed = true
    this.#retireCurrent()
    for (const port of this.#ports) this.#disposePort(port)
  }

  async authorize(
    request: WAWTrustAuthorizationRequest,
  ): Promise<Readonly<WAWTrustAuthorizationLease>> {
    if (this.#closed) fail()
    this.#retireCurrent()
    if (
      this.#ports.length !== 1 ||
      this.#ports[0]!.authority !== this.#requiredAuthority
    ) {
      fail()
    }

    const port = this.#ports[0]!
    const registration: ProviderRegistration = {
      generation: (this.#generation += 1),
      port,
      abortController: new AbortController(),
      live: true,
      providerEpoch: null,
      unsubscribe: null,
      unsubscribed: false,
    }
    this.#registration = registration

    try {
      // Subscription is intentionally established before the first snapshot.
      const unsubscribe = port.subscribeInvalidation(() => {
        this.#retireRegistration(registration, true)
      })
      if (typeof unsubscribe !== 'function') fail()
      registration.unsubscribe = unsubscribe
      if (!this.#isCurrent(registration)) fail()

      const first = copyWAWTrustProviderSnapshot(await port.getAtomicSnapshot())
      if (!this.#isCurrent(registration)) fail()
      registration.providerEpoch = first.provider_epoch

      const authorization = await this.#policy.consume(first, request, {
        readEvidence: async (providerEpoch) => {
          if (!this.#isCurrent(registration, providerEpoch)) fail()
          const current = copyWAWTrustProviderSnapshot(
            await port.getAtomicSnapshot(),
          )
          if (
            !this.#isCurrent(registration, providerEpoch) ||
            current.provider_epoch !== providerEpoch ||
            !sameSnapshotAuthority(first, current)
          ) {
            fail()
          }
          return Object.freeze({
            provider_epoch: current.provider_epoch,
            trusted_time: current.trusted_time,
          })
        },
        // WAWTrustPolicy invokes this exact-registration/epoch guard
        // synchronously immediately before its accepted-state replacement.
        isCurrent: (providerEpoch) =>
          this.#isCurrent(registration, providerEpoch),
      })
      if (
        authorization === null ||
        !this.#isCurrent(registration, first.provider_epoch)
      ) {
        fail()
      }

      const lease: Readonly<WAWTrustAuthorizationLease> = Object.freeze({
        ...authorization,
        generation: registration.generation,
        signal: registration.abortController.signal,
        isCurrent: () =>
          this.#isCurrent(registration, first.provider_epoch) &&
          !registration.abortController.signal.aborted,
      })
      this.#authorization = lease
      return lease
    } catch {
      // Retire only this attempt. A newer concurrent registration remains live.
      this.#retireRegistration(registration, true)
      throw new WAWTrustRecordError()
    }
  }
}
