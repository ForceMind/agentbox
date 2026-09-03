import { describe, expect, it } from 'vitest'
import vector from '../../../../../tests/fixtures/waw_crypto/profile-v1.json'
import {
  ADMISSION_KEYS,
  CONTEXT_KEYS,
  canonicalContextBytes,
  deriveContext,
  validateAdmission,
  validateContext,
  WAWCryptoError,
} from './wawCryptoContext'

const admission = {
  attachment_id: `att_${'1'.repeat(32)}`,
  workspace_id: `aws_${'2'.repeat(32)}`,
  project_id: `prj_${'3'.repeat(32)}`,
  agent_type: 'codex',
  runtime_host_installation_id: `wri_${'4'.repeat(32)}`,
  runtime_host_installation_revision: '9007199254740993',
  auth_epoch: '2',
  api_authority_epoch: '3',
  lease_number: '4',
  generation: '5',
  binding_revision: '6',
  mode: 'writer',
  binding_digest: 'a'.repeat(64),
}

// Hand-written sorted ASCII JSON, independent of production serialization.
const golden =
  '{"agent_type":"codex","api_authority_epoch":"3","attachment_id":"att_11111111111111111111111111111111","auth_epoch":"2","binding_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","binding_revision":"6","crypto_envelope_version":1,"generation":"5","lease_number":"4","project_id":"prj_33333333333333333333333333333333","protocol_id":"agentbox-waw/v1","runtime_epoch":"18446744073709551615","runtime_host_installation_id":"wri_44444444444444444444444444444444","runtime_host_installation_revision":"9007199254740993","workspace_id":"aws_22222222222222222222222222222222"}'

describe('WAW exact context', () => {
  it('matches independent canonical bytes without rounding uint64 strings', () => {
    const context = deriveContext(admission, '18446744073709551615')
    expect(canonicalContextBytes(context)).toEqual(
      new TextEncoder().encode(golden),
    )
    expect(Object.keys(context)).toHaveLength(15)
    expect(Object.keys(validateAdmission(admission))).toHaveLength(13)
    expect(Object.isFrozen(context)).toBe(true)
    expect(Object.isFrozen(validateAdmission(admission))).toBe(true)
    const reverse = Object.fromEntries(Object.entries(context).reverse())
    expect(canonicalContextBytes(reverse)).toEqual(
      new TextEncoder().encode(golden),
    )
  })
  it('matches the shared independent application-vector context and SHA-256', async () => {
    const context = deriveContext(vector.admission, vector.runtime_epoch)
    const canonical = canonicalContextBytes(context)
    expect(new TextDecoder().decode(canonical)).toBe(
      vector.canonical_context_utf8,
    )
    expect(
      Buffer.from(
        await crypto.subtle.digest('SHA-256', canonical as BufferSource),
      ).toString('hex'),
    ).toBe(vector.canonical_context_sha256)
  })
  it('copies the closed records and never adds mode, origin, ticket or cursor', () => {
    const original = { ...admission }
    const saved = validateAdmission(original)
    original.generation = '90'
    expect(saved.generation).toBe('5')
    const context = deriveContext(saved, '1')
    for (const key of ['mode', 'origin', 'ticket', 'cursor', 'context']) {
      expect(context).not.toHaveProperty(key)
      expect(() =>
        validateContext({ ...context, [key]: 'unexpected' }),
      ).toThrow(WAWCryptoError)
    }
  })
  it.each(ADMISSION_KEYS)(
    'rejects missing or invalid admission member %s',
    (key) => {
      const partial: Record<string, unknown> = { ...admission }
      delete partial[key]
      expect(() => validateAdmission(partial)).toThrow(WAWCryptoError)
      expect(() => deriveContext({ ...admission, [key]: null }, '1')).toThrow(
        WAWCryptoError,
      )
    },
  )
  it.each(CONTEXT_KEYS)(
    'rejects missing or invalid context member %s',
    (key) => {
      const context: Record<string, unknown> = {
        ...deriveContext(admission, '1'),
      }
      delete context[key]
      expect(() => validateContext(context)).toThrow(WAWCryptoError)
      expect(() =>
        validateContext({ ...deriveContext(admission, '1'), [key]: null }),
      ).toThrow(WAWCryptoError)
    },
  )
  it.each([
    '0',
    '01',
    '+1',
    '-1',
    '1.0',
    '1e1',
    ' 1',
    '1\n',
    '18446744073709551616',
    '9'.repeat(2000),
    1,
    9007199254740993n,
    true,
    null,
  ])('rejects noncanonical or invalid uint64 %s', (value) => {
    expect(() => deriveContext(admission, value)).toThrow(WAWCryptoError)
    expect(() =>
      validateAdmission({ ...admission, generation: value }),
    ).toThrow(WAWCryptoError)
  })
  it.each(['viewer', '', 1, false])(
    'validates mode before omitting it: %s',
    (mode) => {
      expect(() => deriveContext({ ...admission, mode }, '1')).toThrow(
        WAWCryptoError,
      )
    },
  )
  it('rejects hidden keys, accessors, symbols, prototypes and non-ASCII values', () => {
    let accessed = false
    const getter = { ...admission }
    Object.defineProperty(getter, 'mode', {
      enumerable: true,
      get() {
        accessed = true
        return 'writer'
      },
    })
    const hidden = { ...admission }
    Object.defineProperty(hidden, 'extra', { value: 1 })
    for (const record of [
      getter,
      hidden,
      { ...admission, [Symbol()]: 1 },
      Object.create(admission),
      [],
      { ...admission, agent_type: 'ｃodex' },
      { ...admission, binding_digest: 'A'.repeat(64) },
    ])
      expect(() => validateAdmission(record)).toThrow(WAWCryptoError)
    expect(accessed).toBe(false)
  })
})
