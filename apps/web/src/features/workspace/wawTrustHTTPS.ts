/** Explicit weaker HTTPS profile; never impersonates independent native trust. */
import type { WAWTrustAuthorizationRequest } from './wawTrustPolicy'
import type { WAWTrustAuthorizationLease } from './wawTrustProvider'
import { WAWTrustRecordError } from './wawTrustRecords'

const PATH = '/.well-known/agentbox/waw-bootstrap.v1.json'
const PROFILE_META = 'meta[name="agentbox-waw-trust-profile"]'
const BUILD_META = 'meta[name="agentbox-waw-build-identity"]'
const FIELDS = [
  'schema_version',
  'trust_profile',
  'repository',
  'origin',
  'runtime_host_installation_id',
  'runtime_host_installation_revision',
  'runtime_attestation_x25519_fingerprint',
  'host_manifest_digest',
  'build_identity',
  'version',
  'valid_from',
  'valid_until',
] as const
const HEX = /^[0-9a-f]{64}$/
const U64 = /^[1-9][0-9]{0,19}$/
const UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/

function fail(): never {
  throw new WAWTrustRecordError()
}

function metadata(selector: string): string | null {
  const values = document.querySelectorAll<HTMLMetaElement>(selector)
  return values.length === 1 ? values[0]!.content : null
}

export function httpsWebTrustSelected(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext === true &&
    window.location.protocol === 'https:' &&
    metadata(PROFILE_META) === 'https-web-v1' &&
    HEX.test(metadata(BUILD_META) ?? '')
  )
}

type Bootstrap = Record<(typeof FIELDS)[number], string>

function validate(
  raw: string,
  request: WAWTrustAuthorizationRequest,
): Bootstrap {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    fail()
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail()
  const record = value as Record<string, unknown>
  if (
    Object.keys(record).length !== FIELDS.length ||
    FIELDS.some((field) => typeof record[field] !== 'string')
  )
    fail()
  const result = record as Bootstrap
  const canonical = Object.fromEntries(
    Object.keys(record)
      .sort()
      .map((key) => [key, record[key]]),
  )
  if (
    raw !== JSON.stringify(canonical) + '\n' ||
    result.schema_version !== 'agentbox-waw-https-bootstrap.v1' ||
    result.trust_profile !== 'https-web-v1' ||
    result.repository !== 'ForceMind/agentbox' ||
    result.origin !== window.location.origin ||
    result.origin !== request.effective_origin ||
    result.origin !== request.admitted_api_origin ||
    !/^wri_[0-9a-f]{32}$/.test(result.runtime_host_installation_id) ||
    result.runtime_host_installation_id !==
      request.runtime_host_installation_id ||
    !U64.test(result.runtime_host_installation_revision) ||
    BigInt(result.runtime_host_installation_revision) > 18446744073709551615n ||
    result.runtime_host_installation_revision !==
      request.runtime_host_installation_revision ||
    !HEX.test(result.runtime_attestation_x25519_fingerprint) ||
    !HEX.test(result.host_manifest_digest) ||
    !HEX.test(result.build_identity) ||
    result.build_identity !== metadata(BUILD_META) ||
    !/^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$/.test(result.version) ||
    !UTC.test(result.valid_from) ||
    !UTC.test(result.valid_until)
  )
    fail()
  const from = Date.parse(result.valid_from),
    until = Date.parse(result.valid_until),
    now = Date.now()
  if (
    !Number.isFinite(from) ||
    !Number.isFinite(until) ||
    from >= until ||
    until - from > 31 * 86400000 ||
    now < from ||
    now >= until ||
    new Date(from).toISOString().replace('.000Z', 'Z') !== result.valid_from ||
    new Date(until).toISOString().replace('.000Z', 'Z') !== result.valid_until
  )
    fail()
  return Object.freeze(result)
}

/** Origin/code integrity and browser time are assumptions, not native guarantees. */
export class WAWHTTPSTrustConsumer {
  #closed = false
  #generation = 0
  #abort: AbortController | null = null
  #poll: ReturnType<typeof setInterval> | null = null
  #lastValidated = 0

  #retire(): void {
    this.#abort?.abort()
    this.#abort = null
    if (this.#poll !== null) clearInterval(this.#poll)
    this.#poll = null
  }

  async #read(
    request: WAWTrustAuthorizationRequest,
    abort: AbortController,
  ): Promise<{ raw: string; value: Bootstrap }> {
    const timeout = setTimeout(() => abort.abort(), 5000)
    try {
      if (!httpsWebTrustSelected() || abort.signal.aborted) fail()
      const url = new URL(PATH, window.location.origin).href
      const response = await fetch(url, {
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        mode: 'same-origin',
        referrerPolicy: 'no-referrer',
        signal: abort.signal,
      })
      if (
        !response.ok ||
        response.url !== url ||
        response.redirected ||
        !/^application\/json(?:;\s*charset=utf-8)?$/i.test(
          response.headers.get('content-type') ?? '',
        ) ||
        !response.body
      )
        fail()
      const reader = response.body.getReader()
      let total = 0
      const chunks: Uint8Array[] = []
      try {
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          total += value.byteLength
          if (total > 8192 || abort.signal.aborted) fail()
          chunks.push(value)
        }
      } finally {
        await reader.cancel().catch(() => {})
      }
      const bytes = new Uint8Array(total)
      let offset = 0
      for (const chunk of chunks) {
        bytes.set(chunk, offset)
        offset += chunk.byteLength
      }
      const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
      return { raw, value: validate(raw, request) }
    } finally {
      clearTimeout(timeout)
    }
  }

  async authorize(
    request: WAWTrustAuthorizationRequest,
  ): Promise<Readonly<WAWTrustAuthorizationLease>> {
    if (this.#closed) fail()
    this.#retire()
    const generation = ++this.#generation
    const abort = new AbortController()
    this.#abort = abort
    try {
      const first = await this.#read(request, abort)
      const second = await this.#read(request, abort)
      if (
        first.raw !== second.raw ||
        this.#abort !== abort ||
        abort.signal.aborted
      )
        fail()
      this.#lastValidated = Date.now()
      let polling = false
      this.#poll = setInterval(() => {
        if (polling || abort.signal.aborted) return
        polling = true
        void this.#read(request, abort)
          .then((current) => {
            if (this.#abort !== abort || abort.signal.aborted) return
            if (current.raw !== first.raw) fail()
            this.#lastValidated = Date.now()
          })
          .catch(() => abort.abort())
          .finally(() => {
            polling = false
          })
      }, 5000)
      return Object.freeze({
        ...first.value,
        schema_version: 'agentbox-waw-https-bootstrap.v1' as const,
        trust_profile: 'https-web-v1' as const,
        repository: 'ForceMind/agentbox' as const,
        generation,
        signal: abort.signal,
        isCurrent: () =>
          !this.#closed &&
          this.#abort === abort &&
          !abort.signal.aborted &&
          httpsWebTrustSelected() &&
          metadata(BUILD_META) === first.value.build_identity &&
          window.location.origin === first.value.origin &&
          Date.now() >= this.#lastValidated &&
          Date.now() - this.#lastValidated < 10000 &&
          Date.now() < Date.parse(first.value.valid_until),
      })
    } catch {
      if (this.#abort === abort) this.#retire()
      fail()
    }
  }

  close(): void {
    this.#closed = true
    this.#retire()
  }
}
