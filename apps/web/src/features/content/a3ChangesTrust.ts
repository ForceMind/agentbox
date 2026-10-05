/** A3 host trust and dynamic admission are separate. WAW trust is not A3 trust. */
import { exactRecord, validateU64 } from '../workspace/wawCryptoContext'
import { ContentError } from './a3Content'
import { CRYPTO_PROTOCOL_ID } from './a3Crypto'
import { parseA3Binding, type A3Binding } from './a3ChangesDto'

export type A3ChangesTrust = Readonly<{
  purpose: typeof CRYPTO_PROTOCOL_ID
  binding: A3Binding
  pin32: Uint8Array
}>
export type A3HostBinding = Readonly<
  Pick<
    A3Binding,
    'runtime_host_installation_id' | 'runtime_host_installation_revision'
  >
>
export type A3ChangesHostTrust = Readonly<{
  purpose: typeof CRYPTO_PROTOCOL_ID
  host: A3HostBinding
  pin32: Uint8Array
}>
export type A3TrustSnapshot = A3ChangesTrust | A3ChangesHostTrust
export interface A3ChangesTrustPort {
  /** Independently provisioned, current purpose-bound trust; never observation data. */
  current(): A3TrustSnapshot | null
  /** MUST synchronously notify before revoked/changed authority can be used. */
  subscribeInvalidation(listener: () => void): () => void
}
export interface A3ChangesChannel {
  /** One whole bounded record. Implementations must fence immediately at actual
   * publication, including after scheduling/backpressure; abort closes I/O. */
  send(bytes: Uint8Array, checkCurrent: () => void): Promise<void>
  receive(checkCurrent?: () => void): Promise<Uint8Array>
  /** Native observed-currentness check, separate from original crypto expiry. */
  check?(): void
  /** Tighten transport controls to the same authenticated local selector deadline. */
  tightenDeadline?(deadlineMs: number): void
  close(): void
  subscribeClose(listener: () => void): () => void
}
export interface A3ChangesDependencies {
  readonly trust: A3ChangesTrustPort
  /** Required for host-only trust; fresh metadata never supplies a trusted pin. */
  readonly admission?: { check(binding: A3Binding | null): void }
  /** Native streams keep live remote-currentness ownership through original END expiry. */
  readonly retainCompletedChannel?: boolean
  observe(projectId: string, signal: AbortSignal): Promise<unknown>
  open(
    request: Readonly<{
      projectId: string
      selectionId: string
      requestNonce: string
    }>,
    signal: AbortSignal,
  ): Promise<A3ChangesChannel>
  /** Trusted progressing integer elapsed milliseconds, compatible Runtime rate.
   * Owners must close on suspension; this does not promise arbitrary clock safety. */
  nowMs(): number
}
export function a3TrustHost(trust: A3TrustSnapshot): A3HostBinding {
  return 'host' in trust ? trust.host : trust.binding
}
export function readA3Trust(port: A3ChangesTrustPort): A3TrustSnapshot {
  try {
    const value = port.current()
    const hostOnly =
      value !== null &&
      Object.getOwnPropertyDescriptor(value, 'host') !== undefined
    const r = exactRecord(value, [
      'purpose',
      hostOnly ? 'host' : 'binding',
      'pin32',
    ])
    if (
      r.purpose !== CRYPTO_PROTOCOL_ID ||
      !(r.pin32 instanceof Uint8Array) ||
      r.pin32.constructor !== Uint8Array ||
      r.pin32.length !== 32
    )
      throw new ContentError('PATCH_REVOKED')
    if (hostOnly) {
      const host = exactRecord(r.host, [
        'runtime_host_installation_id',
        'runtime_host_installation_revision',
      ])
      if (
        typeof host.runtime_host_installation_id !== 'string' ||
        !/^wri_[0-9a-f]{32}$/.test(host.runtime_host_installation_id)
      )
        throw new ContentError('PATCH_REVOKED')
      validateU64(host.runtime_host_installation_revision)
      return Object.freeze({
        purpose: CRYPTO_PROTOCOL_ID,
        host: Object.freeze({
          runtime_host_installation_id: host.runtime_host_installation_id,
          runtime_host_installation_revision:
            host.runtime_host_installation_revision as string,
        }),
        pin32: new Uint8Array(r.pin32),
      })
    }
    return Object.freeze({
      purpose: CRYPTO_PROTOCOL_ID,
      binding: parseA3Binding(r.binding),
      pin32: new Uint8Array(r.pin32),
    })
  } catch {
    throw new ContentError('PATCH_REVOKED')
  }
}
