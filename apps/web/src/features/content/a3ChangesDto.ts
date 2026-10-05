/** Separate staged-selector DTO. Metadata v1 and its strict clients are unchanged. */
import {
  exactRecord,
  validateHex32,
  validateU64,
} from '../workspace/wawCryptoContext'
import {
  ContentError,
  ERROR_CODES,
  PROTOCOL_ID,
  validateContext,
} from './a3Content'

export const A3_BINDING_KEYS = [
  'project_id',
  'project_revision',
  'binding_revision',
  'binding_digest',
  'runtime_host_installation_id',
  'runtime_host_installation_revision',
  'runtime_epoch',
  'session_scope',
  'auth_epoch',
] as const
export type A3Binding = Readonly<
  Record<(typeof A3_BINDING_KEYS)[number], string>
>
export type A3StagedEntry = Readonly<{
  path: string
  kind: string
  side: 'staged'
  selection_id: string | null
  unavailable_code: string | null
}>
export type A3StagedObservation = Readonly<{
  schema_version: 'a3-staged-observation/v1'
  snapshot_sha256: string
  binding: A3Binding
  entries: readonly A3StagedEntry[]
}>
function fail(): never {
  throw new ContentError()
}

export function parseA3Binding(value: unknown): A3Binding {
  try {
    const r = exactRecord(value, A3_BINDING_KEYS)
    const { auth_epoch, ...context } = r
    validateU64(auth_epoch)
    validateContext({
      ...context,
      protocol_id: PROTOCOL_ID,
      protocol_version: 1,
      side: 'staged',
      selector_commitment: '0'.repeat(64),
      request_nonce: '0'.repeat(64),
    })
    return Object.freeze(r) as A3Binding
  } catch {
    return fail()
  }
}
export function sameA3Binding(a: A3Binding, b: A3Binding): boolean {
  return A3_BINDING_KEYS.every((key) => a[key] === b[key])
}
export function parseA3Observation(value: unknown): A3StagedObservation {
  try {
    const r = exactRecord(value, [
      'schema_version',
      'snapshot_sha256',
      'binding',
      'entries',
    ])
    if (r.schema_version !== 'a3-staged-observation/v1') fail()
    const snapshot = validateHex32(r.snapshot_sha256)
    const binding = parseA3Binding(r.binding)
    if (!Array.isArray(r.entries)) fail()
    if (r.entries.length > 10_000) throw new ContentError('PATCH_TOO_LARGE')
    const paths = new Set<string>()
    const source = r.entries as unknown[]
    if (
      Object.getPrototypeOf(source) !== Array.prototype ||
      Reflect.ownKeys(source).length !== source.length + 1
    )
      fail()
    let totalBytes = 0
    const entries = Array.from({ length: source.length }, (_, index) => {
      const descriptor = Object.getOwnPropertyDescriptor(source, String(index))
      if (!descriptor || !descriptor.enumerable || !('value' in descriptor))
        fail()
      const value: unknown = descriptor.value
      const e = exactRecord(value, [
        'path',
        'kind',
        'side',
        'selection_id',
        'unavailable_code',
      ])
      if (
        typeof e.path !== 'string' ||
        !e.path.length ||
        new TextEncoder().encode(e.path).length > 4096 ||
        paths.has(e.path)
      )
        fail()
      if (
        typeof e.kind !== 'string' ||
        ![
          'added',
          'modified',
          'deleted',
          'renamed',
          'copied',
          'untracked',
          'conflicted',
          'typechanged',
        ].includes(e.kind)
      )
        fail()
      if (e.side !== 'staged') fail()
      if (e.selection_id !== null) {
        if (
          typeof e.selection_id !== 'string' ||
          !/^[A-Za-z0-9_-]{156}$/.test(e.selection_id) ||
          e.unavailable_code !== null ||
          !['added', 'modified', 'deleted'].includes(e.kind)
        )
          fail()
      } else if (
        typeof e.unavailable_code !== 'string' ||
        !ERROR_CODES.includes(e.unavailable_code)
      )
        fail()
      paths.add(e.path as string)
      totalBytes += new TextEncoder().encode(JSON.stringify(e)).length
      if (totalBytes > 2 * 1024 * 1024)
        throw new ContentError('PATCH_TOO_LARGE')
      return Object.freeze(e) as A3StagedEntry
    })
    const result = Object.freeze({
      schema_version: 'a3-staged-observation/v1' as const,
      snapshot_sha256: snapshot,
      binding,
      entries: Object.freeze(entries),
    })
    if (
      new TextEncoder().encode(JSON.stringify(result)).length >
      2 * 1024 * 1024
    )
      throw new ContentError('PATCH_TOO_LARGE')
    return result
  } catch (error) {
    if (error instanceof ContentError) throw error
    return fail()
  }
}
