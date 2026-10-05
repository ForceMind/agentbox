/** A3 has no production adapter or pin fallback. WAW trust is not A3 trust. */
import { exactRecord } from '../workspace/wawCryptoContext'
import { ContentError } from './a3Content'
import { CRYPTO_PROTOCOL_ID } from './a3Crypto'
import { parseA3Binding, type A3Binding } from './a3ChangesDto'

export type A3ChangesTrust = Readonly<{
  purpose: typeof CRYPTO_PROTOCOL_ID
  binding: A3Binding
  pin32: Uint8Array
}>
export interface A3ChangesTrustPort {
  /** Independently provisioned, current purpose-bound trust; never bootstrap data. */
  current(): A3ChangesTrust | null
  /** MUST synchronously notify before revoked/changed authority can be used. */
  subscribeInvalidation(listener: () => void): () => void
}
export interface A3ChangesChannel {
  /** One whole bounded record. Implementations must fence immediately at actual
   * publication, including after scheduling/backpressure; abort closes I/O. */
  send(bytes: Uint8Array, checkCurrent: () => void): Promise<void>
  receive(): Promise<Uint8Array>
  close(): void
  subscribeClose(listener: () => void): () => void
}
export interface A3ChangesDependencies {
  readonly trust: A3ChangesTrustPort
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
export function readA3Trust(port: A3ChangesTrustPort): A3ChangesTrust {
  try {
    const r = exactRecord(port.current(), ['purpose', 'binding', 'pin32'])
    if (
      r.purpose !== CRYPTO_PROTOCOL_ID ||
      !(r.pin32 instanceof Uint8Array) ||
      r.pin32.constructor !== Uint8Array ||
      r.pin32.length !== 32
    )
      throw new ContentError('PATCH_REVOKED')
    return Object.freeze({
      purpose: CRYPTO_PROTOCOL_ID,
      binding: parseA3Binding(r.binding),
      pin32: new Uint8Array(r.pin32),
    })
  } catch {
    throw new ContentError('PATCH_REVOKED')
  }
}
