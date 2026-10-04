/** Inert A3 codecs: no networking, admission, crypto state, storage or UI. */
import {
  exactRecord,
  validateHex32,
  validateU64,
} from '../workspace/wawCryptoContext'

export const PROTOCOL_ID = 'agentbox-a3-content/v1'
export const VERSION = 1
export const MAX_PAGE_BYTES = 16_384
export const MAX_CONTROL_BYTES = 4096
export const MAX_PAGES = 16
export const MAX_PATCH_BYTES = 262_144
export const MAX_LINES = 4096
export const MAX_READ_MS = 30_000
const MAX_TIME = Number.MAX_SAFE_INTEGER
const SELECTOR_DOMAIN = 'agentbox-a3-content/selector/v1\0'
export const ERROR_CODES = Object.freeze([
  'PATCH_STALE',
  'PATCH_TIMEOUT',
  'PATCH_TOO_LARGE',
  'PATCH_REVOKED',
  'PATCH_UNAVAILABLE_BINARY',
  'PATCH_UNAVAILABLE_BUSY',
  'PATCH_UNAVAILABLE_CONFIG',
  'PATCH_UNAVAILABLE_ENCODING',
  'PATCH_UNAVAILABLE_GIT',
  'PATCH_UNAVAILABLE_KIND',
  'PATCH_UNAVAILABLE_MODE',
  'PATCH_UNAVAILABLE_PATH',
  'PATCH_UNAVAILABLE_REPOSITORY',
  'PATCH_UNAVAILABLE_SENSITIVE_PATH',
  'PATCH_UNAVAILABLE_STATUS',
])
export class ContentError extends Error {
  constructor(code = 'PATCH_PROTOCOL_INVALID') {
    super(code)
    this.name = 'ContentError'
  }
}
export interface ContentContext {
  readonly protocol_id: typeof PROTOCOL_ID
  readonly protocol_version: 1
  readonly project_id: string
  readonly project_revision: string
  readonly binding_revision: string
  readonly binding_digest: string
  readonly runtime_host_installation_id: string
  readonly runtime_host_installation_revision: string
  readonly session_scope: string
  readonly runtime_epoch: string
  readonly selector_commitment: string
  readonly side: 'staged'
  readonly request_nonce: string
}
interface Common {
  readonly protocol_id: typeof PROTOCOL_ID
  readonly protocol_version: 1
  readonly context_digest: string
  readonly request_nonce: string
}
export interface PatchRead extends Common {
  readonly kind: 'PATCH_READ'
  readonly selection_id: string
}
interface Description extends Common {
  readonly sequence: number
  readonly total_bytes: number
  readonly patch_digest: string
  readonly observed_at_ms: string
  readonly complete: boolean
}
export interface PatchPage extends Description {
  readonly kind: 'PATCH_PAGE'
  readonly data: string
}
export interface PatchEnd extends Description {
  readonly kind: 'PATCH_END'
}
export interface PatchError extends Common {
  readonly kind: 'PATCH_ERROR'
  readonly code: string
}
export type Message = PatchRead | PatchPage | PatchEnd | PatchError
const CONTEXT_KEYS = [
  'protocol_id',
  'protocol_version',
  'project_id',
  'project_revision',
  'binding_revision',
  'binding_digest',
  'runtime_host_installation_id',
  'runtime_host_installation_revision',
  'session_scope',
  'runtime_epoch',
  'selector_commitment',
  'side',
  'request_nonce',
]
const COMMON_KEYS = [
  'protocol_id',
  'protocol_version',
  'context_digest',
  'request_nonce',
  'kind',
]
const DESCRIPTION_KEYS = [
  ...COMMON_KEYS,
  'sequence',
  'total_bytes',
  'patch_digest',
  'observed_at_ms',
  'complete',
]
const MESSAGE_KEYS = {
  PATCH_READ: [...COMMON_KEYS, 'selection_id'],
  PATCH_PAGE: [...DESCRIPTION_KEYS, 'data'],
  PATCH_END: DESCRIPTION_KEYS,
  PATCH_ERROR: [...COMMON_KEYS, 'code'],
}
const encoder = new TextEncoder()
const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true })
const atom = '(?:"[A-Za-z0-9_/:.\\-]*"|true|false|0|[1-9][0-9]*)'
const flat = new RegExp(
  '^\\{"[a-z_]+":' + atom + '(?:,"[a-z_]+":' + atom + ')*\\}$',
)
function fail(): never {
  throw new ContentError()
}
function integer(value: unknown, low: number, high: number): number {
  if (
    typeof value !== 'number' ||
    !Number.isSafeInteger(value) ||
    Object.is(value, -0) ||
    value < low ||
    value > high
  )
    fail()
  return value
}
function hex(value: unknown): string {
  try {
    return validateHex32(value)
  } catch {
    return fail()
  }
}
function u64(value: unknown): string {
  try {
    return validateU64(value)
  } catch {
    return fail()
  }
}
function record(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  try {
    return exactRecord(value, keys)
  } catch {
    return fail()
  }
}
function profile(r: Record<string, unknown>): void {
  if (r.protocol_id !== PROTOCOL_ID || r.protocol_version !== 1) fail()
}
/** RFC8785 equivalent only for these closed flat ASCII / boolean / small integer records. */
function canonical(value: object): Uint8Array {
  return new Uint8Array(
    encoder.encode(
      JSON.stringify(
        Object.fromEntries(
          Object.entries(value).sort(([a], [b]) =>
            a < b ? -1 : a > b ? 1 : 0,
          ),
        ),
      ),
    ),
  )
}
function parse(raw: Uint8Array, limit: number): Record<string, unknown> {
  try {
    if (
      !(raw instanceof Uint8Array) ||
      raw.constructor !== Uint8Array ||
      raw.length < 1 ||
      raw.length > limit
    )
      fail()
    const text = decoder.decode(raw)
    // No recursion or user-controlled nesting is passed into JSON.parse.
    if (!flat.test(text)) fail()
    const value = JSON.parse(text) as Record<string, unknown>
    if (
      Object.keys(value).length > 16 ||
      decoder.decode(canonical(value)) !== text
    )
      fail()
    return value
  } catch {
    return fail()
  }
}
export function validateContext(value: unknown): ContentContext {
  const r = record(value, CONTEXT_KEYS)
  profile(r)
  for (const [key, prefix] of [
    ['project_id', 'prj'],
    ['runtime_host_installation_id', 'wri'],
  ])
    if (
      typeof r[key] !== 'string' ||
      !new RegExp(`^${prefix}_[a-f0-9]{32}$`).test(r[key] as string)
    )
      fail()
  for (const key of [
    'project_revision',
    'binding_revision',
    'runtime_host_installation_revision',
    'runtime_epoch',
  ])
    u64(r[key])
  for (const key of [
    'binding_digest',
    'session_scope',
    'selector_commitment',
    'request_nonce',
  ])
    hex(r[key])
  if (r.side !== 'staged') fail()
  return Object.freeze(r) as unknown as ContentContext
}
export function contextBytes(value: unknown): Uint8Array {
  return canonical(validateContext(value))
}
export function decodeContext(raw: Uint8Array): ContentContext {
  return validateContext(parse(raw, MAX_CONTROL_BYTES))
}
async function digest(bytes: Uint8Array): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', new Uint8Array(bytes))
  return Array.from(new Uint8Array(hash), (n) =>
    n.toString(16).padStart(2, '0'),
  ).join('')
}
export async function contextDigest(value: unknown): Promise<string> {
  return digest(contextBytes(value))
}
function selector(value: unknown): string {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{156}$/.test(value)) fail()
  return value
}
export async function selectorCommitment(value: unknown): Promise<string> {
  return digest(encoder.encode(SELECTOR_DOMAIN + selector(value)))
}
export async function applicationAad(
  context: unknown,
  transcriptHash: string,
  kind: Message['kind'],
  sequence: number,
): Promise<Uint8Array> {
  if (typeof kind !== 'string' || !Object.hasOwn(MESSAGE_KEYS, kind)) fail()
  integer(sequence, 0, MAX_PAGES)
  if ((kind === 'PATCH_READ' || kind === 'PATCH_ERROR') && sequence !== 0)
    fail()
  if (kind === 'PATCH_PAGE' && sequence >= MAX_PAGES) fail()
  if (kind === 'PATCH_END' && sequence === 0) fail()
  const transcript = hex(transcriptHash)
  const bound = contextBytes(context)
  return canonical({
    domain: 'agentbox-a3-content/aad/v1',
    context_digest: await digest(bound),
    transcript_hash: transcript,
    kind,
    sequence,
    direction:
      kind === 'PATCH_READ' ? 'browser-to-runtime' : 'runtime-to-browser',
  })
}
function b64(raw: Uint8Array): string {
  return btoa(Array.from(raw, (b) => String.fromCharCode(b)).join(''))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
}
function payload(value: unknown): Uint8Array {
  if (
    typeof value !== 'string' ||
    value.length < 1 ||
    value.length > MAX_PAGE_BYTES ||
    !/^[A-Za-z0-9_-]+$/.test(value)
  )
    fail()
  try {
    const raw = Uint8Array.from(
      atob(
        value.replace(/-/g, '+').replace(/_/g, '/') +
          '='.repeat((4 - (value.length % 4)) % 4),
      ),
      (c) => c.charCodeAt(0),
    )
    if (b64(raw) !== value) fail()
    return raw
  } catch {
    return fail()
  }
}
export function validateMessage(value: unknown): Message {
  // Inspect kind as a data property before copying all fields; never run getters.
  if (!value || typeof value !== 'object') fail()
  const descriptor = Object.getOwnPropertyDescriptor(value, 'kind')
  if (
    !descriptor ||
    !('value' in descriptor) ||
    typeof descriptor.value !== 'string' ||
    !Object.hasOwn(MESSAGE_KEYS, descriptor.value)
  )
    fail()
  const kind = descriptor.value as Message['kind']
  const r = record(value, MESSAGE_KEYS[kind])
  profile(r)
  hex(r.context_digest)
  hex(r.request_nonce)
  if (kind === 'PATCH_READ') selector(r.selection_id)
  else if (kind === 'PATCH_ERROR') {
    if (typeof r.code !== 'string' || !ERROR_CODES.includes(r.code)) fail()
  } else {
    integer(
      r.sequence,
      kind === 'PATCH_PAGE' ? 0 : 1,
      kind === 'PATCH_PAGE' ? 15 : 16,
    )
    const total = integer(r.total_bytes, 1, MAX_PATCH_BYTES)
    hex(r.patch_digest)
    u64(r.observed_at_ms)
    if (
      typeof r.complete !== 'boolean' ||
      r.complete !== (kind === 'PATCH_END')
    )
      fail()
    if (kind === 'PATCH_PAGE' && payload(r.data).length > total) fail()
  }
  if (
    canonical(r).length >
    (kind === 'PATCH_PAGE' ? MAX_PAGE_BYTES : MAX_CONTROL_BYTES)
  )
    fail()
  return Object.freeze(r) as unknown as Message
}
export function encodeMessage(value: unknown): Uint8Array {
  return canonical(validateMessage(value))
}
export function decodeMessage(raw: Uint8Array): Message {
  return validateMessage(parse(raw, MAX_PAGE_BYTES))
}
async function common(c: ContentContext): Promise<Common> {
  return {
    protocol_id: PROTOCOL_ID,
    protocol_version: VERSION,
    context_digest: await contextDigest(c),
    request_nonce: c.request_nonce,
  }
}
function patchText(raw: Uint8Array): string {
  if (
    !(raw instanceof Uint8Array) ||
    raw.constructor !== Uint8Array ||
    raw.length < 1 ||
    raw.length > MAX_PATCH_BYTES
  )
    throw new ContentError('PATCH_TOO_LARGE')
  let text: string
  try {
    text = decoder.decode(raw)
  } catch {
    throw new ContentError('PATCH_UNAVAILABLE_ENCODING')
  }
  // Match Python str.splitlines, including CRLF as a single boundary.
  // These control separators intentionally match Python str.splitlines.
  // eslint-disable-next-line no-control-regex
  const lines = text.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/)
  if (lines.at(-1) === '') lines.pop()
  if (lines.length > MAX_LINES) throw new ContentError('PATCH_TOO_LARGE')
  return text
}
export async function preparePages(
  context: unknown,
  patch: Uint8Array,
  observedAtMs: string,
): Promise<readonly Uint8Array[]> {
  const c = validateContext(context)
  patchText(patch)
  const copy = new Uint8Array(patch),
    observed = u64(observedAtMs)
  const description = {
    ...(await common(c)),
    kind: 'PATCH_PAGE',
    total_bytes: copy.length,
    patch_digest: await digest(copy),
    observed_at_ms: observed,
    complete: false,
  }
  const overhead = canonical({ ...description, sequence: 15, data: '' }).length
  const capacity = Math.floor(((MAX_PAGE_BYTES - overhead) * 6) / 8)
  const count = Math.ceil(copy.length / capacity)
  if (count > MAX_PAGES) throw new ContentError('PATCH_TOO_LARGE')
  const pages = Array.from({ length: count }, (_, index) =>
    encodeMessage({
      ...description,
      sequence: index,
      data: b64(copy.slice(index * capacity, (index + 1) * capacity)),
    }),
  )
  return [
    ...pages,
    encodeMessage({
      ...description,
      kind: 'PATCH_END',
      sequence: count,
      complete: true,
    }),
  ]
}

/** Pure single-use transcript model. The owner supplies trusted currentness/time. */
export class ContentRead {
  readonly #context: ContentContext
  readonly #deadline: number
  #last: number
  #closed = false
  #busy = false
  #started = false
  #pages: Uint8Array[] = []
  #size = 0
  #description: string | undefined
  constructor(context: unknown, nowMs: number, deadlineMs: number) {
    this.#context = validateContext(context)
    this.#last = integer(nowMs, 0, MAX_TIME)
    this.#deadline = integer(
      deadlineMs,
      nowMs + 1,
      Math.min(MAX_TIME, nowMs + MAX_READ_MS),
    )
  }
  close(): void {
    this.#closed = true
    this.#pages = []
    this.#size = 0
    this.#description = undefined
  }
  check(nowMs: number, currentContext: unknown): void {
    try {
      if (
        this.#closed ||
        decoder.decode(contextBytes(currentContext)) !==
          decoder.decode(contextBytes(this.#context))
      )
        fail()
      integer(nowMs, this.#last, MAX_TIME)
      if (nowMs >= this.#deadline) throw new ContentError('PATCH_TIMEOUT')
      this.#last = nowMs
    } catch (error) {
      this.close()
      throw error
    }
  }
  async accept(
    raw: Uint8Array,
    nowMs: number,
    currentContext: unknown,
  ): Promise<Uint8Array | undefined> {
    try {
      this.check(nowMs, currentContext)
      if (this.#busy) fail()
      this.#busy = true
      const message = decodeMessage(raw)
      const bound = await contextDigest(this.#context)
      if (
        this.#closed ||
        message.context_digest !== bound ||
        message.request_nonce !== this.#context.request_nonce
      )
        fail()
      if (message.kind === 'PATCH_READ') {
        if (
          this.#started ||
          (await selectorCommitment(message.selection_id)) !==
            this.#context.selector_commitment ||
          this.#closed
        )
          fail()
        this.#started = true
        return
      }
      if (!this.#started) fail()
      if (message.kind === 'PATCH_ERROR') throw new ContentError(message.code)
      const description = JSON.stringify([
        message.total_bytes,
        message.patch_digest,
        message.observed_at_ms,
      ])
      if (this.#description !== undefined && description !== this.#description)
        fail()
      if (message.sequence !== this.#pages.length) fail()
      if (message.kind === 'PATCH_PAGE') {
        const data = payload(message.data)
        if (
          this.#pages.length >= MAX_PAGES ||
          this.#size + data.length > message.total_bytes
        )
          fail()
        this.#description = description
        this.#pages.push(data)
        this.#size += data.length
        return
      }
      const patch = new Uint8Array(this.#size)
      let offset = 0
      for (const page of this.#pages) {
        patch.set(page, offset)
        offset += page.length
      }
      if (
        this.#size !== message.total_bytes ||
        (await digest(patch)) !== message.patch_digest ||
        this.#closed
      )
        fail()
      patchText(patch)
      this.close()
      return patch
    } catch (error) {
      this.close()
      throw error
    } finally {
      this.#busy = false
    }
  }
}
