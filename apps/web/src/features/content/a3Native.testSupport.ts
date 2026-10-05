/** Synthetic public bootstrap/WS fixtures; never imported by production code. */
import { vi } from 'vitest'
import { A3_NATIVE_SUBPROTOCOL } from './a3ChangesNative'
import { CRYPTO_PROTOCOL_ID } from './a3Crypto'
import { A3_BOOTSTRAP_PATH } from './a3TrustHTTPS'

export const nativeOrigin = 'https://a3.agentbox.test'
export const nativeBuild = 'b'.repeat(64)
export const nativeBootstrap = {
  schema_version: 'agentbox-a3-https-bootstrap.v1',
  trust_profile: 'a3-https-web-v1',
  purpose: CRYPTO_PROTOCOL_ID,
  repository: 'ForceMind/agentbox',
  origin: nativeOrigin,
  runtime_host_installation_id: `wri_${'c'.repeat(32)}`,
  runtime_host_installation_revision: '1',
  runtime_attestation_x25519_public_key: 'a'.repeat(64),
  host_manifest_digest: 'd'.repeat(64),
  build_identity: nativeBuild,
  version: '0.3.0rc30',
  valid_from: '2026-10-05T00:00:00Z',
  valid_until: '2026-10-06T00:00:00Z',
}
export const canonicalBootstrap = (value: object) =>
  JSON.stringify(
    Object.fromEntries(
      Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
    ),
  ) + '\n'
export function staticResponse(value: object = nativeBootstrap, raw?: string) {
  return nativeResponse(
    A3_BOOTSTRAP_PATH,
    raw ?? canonicalBootstrap(value),
    true,
  )
}
export function nativeResponse(
  path: string,
  value: unknown,
  raw = false,
  status = 200,
) {
  const response = new Response(
    raw ? (value as string) : JSON.stringify(value),
    {
      status,
      headers: { 'content-type': 'application/json' },
    },
  )
  Object.defineProperty(response, 'url', { value: nativeOrigin + path })
  return response
}
export function selectNativeBootstrap() {
  vi.stubGlobal('location', new URL(nativeOrigin))
  vi.stubGlobal('isSecureContext', true)
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-05T12:00:00Z'))
  document.head.innerHTML = `<meta name="agentbox-a3-trust-profile" content="a3-https-web-v1"><meta name="agentbox-a3-build-identity" content="${nativeBuild}">`
}
export class NativeTestSocket extends EventTarget {
  static OPEN = 1
  static instances: NativeTestSocket[] = []
  static onCreate?: (socket: NativeTestSocket) => void
  binaryType = 'blob'
  readyState = 0
  bufferedAmount = 0
  protocol = A3_NATIVE_SUBPROTOCOL
  sent: Uint8Array[] = []
  autoReady = true
  autoCurrent = true
  onData?: (data: Uint8Array) => void
  close = vi.fn(() => {
    this.readyState = 3
  })
  constructor(
    readonly url: string,
    readonly requestedProtocol: string,
  ) {
    super()
    NativeTestSocket.instances.push(this)
    NativeTestSocket.onCreate?.(this)
    queueMicrotask(() => {
      if (this.readyState !== 0) return
      this.readyState = 1
      this.dispatchEvent(new Event('open'))
    })
  }
  send(value: Uint8Array) {
    if (!(value instanceof Uint8Array)) throw new Error('binary-only fixture')
    const raw = new Uint8Array(value)
    this.sent.push(raw)
    const kind = String.fromCharCode(...raw.subarray(0, 4))
    if (kind === 'A3CQ' && this.autoCurrent) {
      const reply = new Uint8Array(raw)
      reply.set(new TextEncoder().encode('A3CR'))
      queueMicrotask(() => this.message(reply))
    } else if (this.sent.length === 1 && this.autoReady) {
      queueMicrotask(() => this.message(new Uint8Array([65, 51, 82, 68, 1])))
    } else this.onData?.(raw)
  }
  message(raw: Uint8Array | string | Blob) {
    this.dispatchEvent(
      new MessageEvent('message', {
        data: ArrayBuffer.isView(raw)
          ? new Uint8Array(raw as Uint8Array).buffer
          : raw,
      }),
    )
  }
  disconnect() {
    this.dispatchEvent(new Event('close'))
  }
}
