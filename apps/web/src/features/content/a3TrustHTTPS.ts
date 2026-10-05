/** Independent, explicitly selected A3 HTTPS bootstrap. No WAW/native fallback. */
import { exactRecord, validateU64 } from '../workspace/wawCryptoContext'
import { ContentError } from './a3Content'
import { CRYPTO_PROTOCOL_ID } from './a3Crypto'
import type { A3ChangesHostTrust } from './a3ChangesTrust'

export const A3_BOOTSTRAP_PATH = '/.well-known/agentbox/a3-bootstrap.v1.json'
const PROFILE_META = 'meta[name="agentbox-a3-trust-profile"]'
const BUILD_META = 'meta[name="agentbox-a3-build-identity"]'
const HEX = /^[0-9a-f]{64}$/
const UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/
const FIELDS = [
  'schema_version',
  'trust_profile',
  'purpose',
  'repository',
  'origin',
  'runtime_host_installation_id',
  'runtime_host_installation_revision',
  'runtime_attestation_x25519_public_key',
  'host_manifest_digest',
  'build_identity',
  'version',
  'valid_from',
  'valid_until',
] as const
export type A3HTTPSBootstrap = Readonly<Record<(typeof FIELDS)[number], string>>
export interface A3HTTPSTrustLease {
  readonly bootstrap: A3HTTPSBootstrap
  readonly signal: AbortSignal
  current(): A3ChangesHostTrust | null
}
function fail(): never {
  throw new ContentError('PATCH_REVOKED')
}
function metadata(selector: string): string | null {
  const values = document.querySelectorAll<HTMLMetaElement>(selector)
  return values.length === 1 ? values[0]!.content : null
}
export function a3HTTPSTrustSelected(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext === true &&
    window.location.protocol === 'https:' &&
    metadata(PROFILE_META) === 'a3-https-web-v1' &&
    HEX.test(metadata(BUILD_META) ?? '')
  )
}
function validate(raw: string, origin: string, now: number): A3HTTPSBootstrap {
  for (let index = 0; index < raw.length; index++)
    if (raw.charCodeAt(index) > 127) fail()
  const record = exactRecord(JSON.parse(raw), FIELDS)
  if (FIELDS.some((field) => typeof record[field] !== 'string')) fail()
  const value = record as Record<(typeof FIELDS)[number], string>
  const canonical =
    JSON.stringify(
      Object.fromEntries(
        Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
      ),
    ) + '\n'
  if (
    raw !== canonical ||
    value.schema_version !== 'agentbox-a3-https-bootstrap.v1' ||
    value.trust_profile !== 'a3-https-web-v1' ||
    value.purpose !== CRYPTO_PROTOCOL_ID ||
    value.repository !== 'ForceMind/agentbox' ||
    value.origin !== origin ||
    value.origin !== window.location.origin ||
    !/^wri_[0-9a-f]{32}$/.test(value.runtime_host_installation_id) ||
    !HEX.test(value.runtime_attestation_x25519_public_key) ||
    !HEX.test(value.host_manifest_digest) ||
    !HEX.test(value.build_identity) ||
    value.build_identity !== metadata(BUILD_META) ||
    !/^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$/.test(value.version) ||
    !UTC.test(value.valid_from) ||
    !UTC.test(value.valid_until)
  )
    fail()
  validateU64(value.runtime_host_installation_revision)
  const from = Date.parse(value.valid_from),
    until = Date.parse(value.valid_until)
  if (
    !Number.isFinite(from) ||
    !Number.isFinite(until) ||
    from >= until ||
    until - from > 31 * 86400000 ||
    now < from ||
    now >= until ||
    new Date(from).toISOString().replace('.000Z', 'Z') !== value.valid_from ||
    new Date(until).toISOString().replace('.000Z', 'Z') !== value.valid_until
  )
    fail()
  return Object.freeze(value)
}

/** Page-owned public-key trust only; never a Project/session authorization lease. */
export class A3HTTPSTrustConsumer {
  #closed = false
  #abort?: AbortController
  #poll?: ReturnType<typeof setInterval>
  #watch?: ReturnType<typeof setInterval>
  #lastNow = 0
  #removeLifecycle?: () => void
  #clock(): number {
    const now = Date.now()
    if (!Number.isSafeInteger(now) || now < this.#lastNow) fail()
    this.#lastNow = now
    return now
  }
  #retire(): void {
    const abort = this.#abort
    this.#abort = undefined
    clearInterval(this.#poll)
    clearInterval(this.#watch)
    this.#poll = this.#watch = undefined
    this.#removeLifecycle?.()
    this.#removeLifecycle = undefined
    abort?.abort()
  }
  async #read(origin: string, abort: AbortController) {
    const timeout = setTimeout(() => abort.abort(), 5000)
    try {
      this.#clock()
      if (
        !a3HTTPSTrustSelected() ||
        document.hidden ||
        abort.signal.aborted ||
        window.location.origin !== origin ||
        this.#abort !== abort
      )
        fail()
      const url = new URL(A3_BOOTSTRAP_PATH, origin).href
      const response = await fetch(url, {
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        mode: 'same-origin',
        referrerPolicy: 'no-referrer',
        signal: abort.signal,
      })
      if (
        response.status !== 200 ||
        response.url !== url ||
        response.redirected ||
        !/^application\/json(?:;\s*charset=utf-8)?$/i.test(
          response.headers.get('content-type') ?? '',
        ) ||
        !response.body
      )
        fail()
      const reader = response.body.getReader()
      const chunks: Uint8Array[] = []
      let total = 0
      try {
        for (;;) {
          const { done, value } = await reader.read()
          if (abort.signal.aborted || this.#abort !== abort) fail()
          if (done) break
          total += value.byteLength
          if (total > 8192) fail()
          chunks.push(value)
        }
      } finally {
        void reader.cancel().catch(() => undefined)
      }
      const bytes = new Uint8Array(total)
      let offset = 0
      for (const chunk of chunks) {
        bytes.set(chunk, offset)
        offset += chunk.byteLength
      }
      const raw = new TextDecoder('utf-8', {
        fatal: true,
        ignoreBOM: true,
      }).decode(bytes)
      if (!a3HTTPSTrustSelected() || abort.signal.aborted || document.hidden)
        fail()
      return { raw, value: validate(raw, origin, this.#clock()) }
    } finally {
      clearTimeout(timeout)
    }
  }
  async authorize(): Promise<A3HTTPSTrustLease> {
    if (this.#closed || !a3HTTPSTrustSelected() || document.hidden) fail()
    this.#retire()
    const abort = new AbortController()
    this.#abort = abort
    const origin = window.location.origin
    this.#lastNow = Date.now()
    const interrupt = () => this.close()
    const hidden = () => {
      if (document.hidden) interrupt()
    }
    document.addEventListener('visibilitychange', hidden)
    document.addEventListener('freeze', interrupt)
    window.addEventListener('pagehide', interrupt)
    window.addEventListener('offline', interrupt)
    this.#removeLifecycle = () => {
      document.removeEventListener('visibilitychange', hidden)
      document.removeEventListener('freeze', interrupt)
      window.removeEventListener('pagehide', interrupt)
      window.removeEventListener('offline', interrupt)
    }
    try {
      const first = await this.#read(origin, abort)
      const second = await this.#read(origin, abort)
      if (
        first.raw !== second.raw ||
        this.#abort !== abort ||
        abort.signal.aborted
      )
        fail()
      let lastValidated = this.#clock()
      const current = (): A3ChangesHostTrust | null => {
        try {
          const now = this.#clock()
          if (
            this.#closed ||
            this.#abort !== abort ||
            abort.signal.aborted ||
            !a3HTTPSTrustSelected() ||
            document.hidden ||
            window.location.origin !== origin ||
            metadata(BUILD_META) !== first.value.build_identity ||
            now - lastValidated >= 10000 ||
            now < Date.parse(first.value.valid_from) ||
            now >= Date.parse(first.value.valid_until)
          )
            fail()
          return Object.freeze({
            purpose: CRYPTO_PROTOCOL_ID,
            host: Object.freeze({
              runtime_host_installation_id:
                first.value.runtime_host_installation_id,
              runtime_host_installation_revision:
                first.value.runtime_host_installation_revision,
            }),
            pin32: Uint8Array.from(
              first.value.runtime_attestation_x25519_public_key.match(/../g)!,
              (p) => parseInt(p, 16),
            ),
          })
        } catch {
          if (this.#abort === abort) this.close()
          return null
        }
      }
      let polling = false
      this.#watch = setInterval(() => {
        current()
      }, 50)
      this.#poll = setInterval(() => {
        if (polling || !current()) return
        polling = true
        void this.#read(origin, abort)
          .then((next) => {
            if (!current() || next.raw !== first.raw) fail()
            lastValidated = this.#clock()
          })
          .catch(() => {
            if (this.#abort === abort) this.close()
          })
          .finally(() => {
            polling = false
          })
      }, 5000)
      return Object.freeze({
        bootstrap: first.value,
        signal: abort.signal,
        current,
      })
    } catch {
      if (this.#abort === abort) this.close()
      return fail()
    }
  }
  close(): void {
    this.#closed = true
    this.#retire()
  }
}
