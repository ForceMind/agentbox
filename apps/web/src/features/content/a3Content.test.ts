import { webcrypto } from 'node:crypto'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import {
  ContentRead,
  MAX_PAGE_BYTES,
  applicationAad,
  contextBytes,
  contextDigest,
  decodeContext,
  decodeMessage,
  encodeMessage,
  preparePages,
  selectorCommitment,
  validateContext,
} from './a3Content'
import fixture from '../../../../../tests/fixtures/a3_content/v1.json'
const c: Record<string, unknown> = fixture.context
const bytes = (s: string) => new Uint8Array(new TextEncoder().encode(s))
const messages = fixture.messages_json.map(bytes)
const patch = new Uint8Array(Buffer.from(fixture.patch_hex, 'hex'))
const text = (raw: Uint8Array) => new TextDecoder().decode(raw)
const started = async () => {
  const r = new ContentRead(c, 0, 30_000)
  await r.accept(messages[0], 1, c)
  return r
}
beforeAll(() => {
  vi.stubGlobal('crypto', webcrypto)
})

describe('independent A3 codec literals', () => {
  it('matches exact canonical context, messages, AAD and complete content', async () => {
    expect(text(contextBytes(c))).toBe(fixture.context_json)
    expect(decodeContext(contextBytes(c))).toEqual(c)
    expect(await contextDigest(c)).toBe(fixture.context_digest)
    expect(await selectorCommitment(fixture.selector)).toBe(
      c.selector_commitment,
    )
    expect(text(await applicationAad(c, '8'.repeat(64), 'PATCH_PAGE', 0))).toBe(
      fixture.aad_json,
    )
    for (const raw of messages)
      expect(encodeMessage(decodeMessage(raw))).toEqual(raw)
    expect(await preparePages(c, patch, '1791111111111')).toEqual(
      messages.slice(1, 3),
    )
    const r = await started()
    expect(await r.accept(messages[1], 1, c)).toBeUndefined()
    expect(await r.accept(messages[2], 1, c)).toEqual(patch)
    await expect(r.accept(messages[2], 1, c)).rejects.toThrow()
  })
  it.each(fixture.invalid_messages)(
    'rejects shared negative raw JSON %#',
    (raw) => {
      expect(() => decodeMessage(bytes(raw))).toThrow()
    },
  )
  it.each(Object.keys(c))(
    'strict context type, missing and extra checks: %s',
    (key) => {
      for (const bad of [null, true, 1, [], {}, '', 'bad']) {
        if (c[key] === bad) continue
        expect(() => validateContext({ ...c, [key]: bad })).toThrow()
      }
      const missing = { ...c }
      delete missing[key]
      expect(() => validateContext(missing)).toThrow()
      expect(() => validateContext({ ...c, extra: 'x' })).toThrow()
    },
  )
  it('rejects duplicate context, nesting, wrong UTF-8 and oversize before parse', () => {
    expect(() =>
      decodeContext(
        bytes(
          fixture.context_json.replace(
            '"protocol_version":1',
            '"protocol_version":1,"protocol_version":1',
          ),
        ),
      ),
    ).toThrow()
    for (const raw of [
      bytes('['.repeat(16384)),
      bytes(' '.repeat(16385)),
      new Uint8Array([255]),
      bytes(''),
      bytes('{}'),
    ])
      expect(() => decodeMessage(raw)).toThrow()
  })
  it('does not execute getters or retain mutable context', () => {
    const value = { ...c },
      copy = validateContext(value)
    value.request_nonce = '9'.repeat(64)
    expect(copy).toEqual(c)
    const getter = vi.fn(() => 'PATCH_READ')
    const record = JSON.parse(fixture.messages_json[0]) as Record<
      string,
      unknown
    >
    Object.defineProperty(record, 'kind', { get: getter })
    expect(() => encodeMessage(record)).toThrow()
    expect(getter).not.toHaveBeenCalled()
  })
})

describe('single-use bounded transcript', () => {
  it.each([
    { sequence: 1 },
    { request_nonce: '9'.repeat(64) },
    { context_digest: '9'.repeat(64) },
  ])('fences gaps and scope mismatch', async (change) => {
    const r = await started()
    await expect(
      r.accept(
        encodeMessage({ ...decodeMessage(messages[1]), ...change }),
        1,
        c,
      ),
    ).rejects.toThrow()
    await expect(r.accept(messages[1], 1, c)).rejects.toThrow()
  })
  it('fences read/page replay and premature messages', async () => {
    for (const [first, second] of [
      [0, 0],
      [0, 2],
      [1, 0],
      [2, 0],
      [3, 0],
    ]) {
      const r = new ContentRead(c, 0, 30_000)
      await expect(
        (async () => {
          await r.accept(messages[first], 1, c)
          await r.accept(messages[second], 1, c)
        })(),
      ).rejects.toThrow()
      await expect(r.accept(messages[0], 1, c)).rejects.toThrow()
    }
    const r = await started()
    await r.accept(messages[1], 1, c)
    await expect(r.accept(messages[1], 1, c)).rejects.toThrow()
  })
  it.each(['total_bytes', 'patch_digest', 'observed_at_ms'])(
    'rejects END metadata drift: %s',
    async (key) => {
      const r = await started()
      await r.accept(messages[1], 1, c)
      const value =
        key === 'total_bytes'
          ? patch.length + 1
          : key === 'patch_digest'
            ? '9'.repeat(64)
            : '2'
      await expect(
        r.accept(
          encodeMessage({ ...decodeMessage(messages[2]), [key]: value }),
          1,
          c,
        ),
      ).rejects.toThrow()
    },
  )
  it('hashes actual content rather than trusting consistent metadata', async () => {
    const r = await started()
    await r.accept(
      encodeMessage({
        ...decodeMessage(messages[1]),
        patch_digest: '9'.repeat(64),
      }),
      1,
      c,
    )
    await expect(
      r.accept(
        encodeMessage({
          ...decodeMessage(messages[2]),
          patch_digest: '9'.repeat(64),
        }),
        1,
        c,
      ),
    ).rejects.toThrow()
  })
  it.each(Object.keys(c))('closes on currentness change: %s', async (key) => {
    const r = await started()
    expect(() => r.check(2, { ...c, [key]: 'changed' })).toThrow()
    await expect(r.accept(messages[1], 2, c)).rejects.toThrow()
  })
  it('checks exact deadline, regression, close and ERROR', async () => {
    for (const now of [30000, 30001, 0, 1.5]) {
      const r = await started()
      await expect(r.accept(messages[1], now, c)).rejects.toThrow()
    }
    const r = await started()
    r.close()
    await expect(r.accept(messages[1], 1, c)).rejects.toThrow()
    const error = await started()
    await expect(error.accept(messages[3], 1, c)).rejects.toThrow('PATCH_STALE')
    await expect(error.accept(messages[1], 1, c)).rejects.toThrow()
  })
  it('fences overlap, late hash completion and deadline notification during awaits', async () => {
    const r = await started()
    const first = r.accept(messages[1], 1, c)
    await expect(r.accept(messages[1], 1, c)).rejects.toThrow()
    await expect(first).rejects.toThrow()
    const late = await started()
    await late.accept(messages[1], 1, c)
    const finish = late.accept(messages[2], 1, c)
    late.close()
    await expect(finish).rejects.toThrow()
    const timed = await started()
    const pending = timed.accept(messages[1], 1, c)
    expect(() => timed.check(30000, c)).toThrow('PATCH_TIMEOUT')
    await expect(pending).rejects.toThrow()
  })
  it('preflights exact capacity without returning partial pages', async () => {
    const capacity = 11969,
      limit = capacity * 16
    const pages = await preparePages(
      c,
      new Uint8Array(limit).fill(120),
      '1791111111111',
    )
    expect(pages).toHaveLength(17)
    expect(pages[10].length).toBe(MAX_PAGE_BYTES)
    expect(pages.every((p) => p.length <= MAX_PAGE_BYTES)).toBe(true)
    const r = await started()
    for (const page of pages.slice(0, -1))
      expect(await r.accept(page, 1, c)).toBeUndefined()
    expect((await r.accept(pages.at(-1)!, 1, c))?.length).toBe(limit)
    for (const size of [limit + 1, 262144, 262145])
      await expect(
        preparePages(c, new Uint8Array(size).fill(120), '1791111111111'),
      ).rejects.toThrow('PATCH_TOO_LARGE')
  })
  it.each(['\n', '\r', '\r\n', '\v', '\f', '\x1c', '\x85', '\u2028', '\u2029'])(
    'matches full UTF-8 line budget: %#',
    async (separator) => {
      await preparePages(c, bytes(('x' + separator).repeat(4096)), '1')
      await expect(
        preparePages(c, bytes(('x' + separator).repeat(4097)), '1'),
      ).rejects.toThrow('PATCH_TOO_LARGE')
    },
  )
  it('rejects invalid UTF-8 and wrong selector commitment', async () => {
    await expect(preparePages(c, new Uint8Array([255]), '1')).rejects.toThrow(
      'PATCH_UNAVAILABLE_ENCODING',
    )
    const r = new ContentRead(c, 0, 30000)
    await expect(
      r.accept(
        encodeMessage({
          ...decodeMessage(messages[0]),
          selection_id: 'B'.repeat(156),
        }),
        1,
        c,
      ),
    ).rejects.toThrow()
  })
})

it.each([0, 1, 2, 3])(
  'requires exact fields and scalar types for message %s',
  (index) => {
    const message = JSON.parse(fixture.messages_json[index]) as Record<
      string,
      unknown
    >
    for (const [key, original] of Object.entries(message)) {
      for (const bad of [null, [], {}, true, '']) {
        if (bad === original) continue
        expect(() => encodeMessage({ ...message, [key]: bad })).toThrow()
      }
      const missing = { ...message }
      delete missing[key]
      expect(() => encodeMessage(missing)).toThrow()
    }
    expect(() => encodeMessage({ ...message, extra: 'x' })).toThrow()
  },
)
it('bounds uint64, whole PAGE bytes and giant integer spellings', () => {
  const page = decodeMessage(messages[1])
  expect(() =>
    encodeMessage({
      ...page,
      total_bytes: 20_000,
      data: btoa('x'.repeat(12288)),
    }),
  ).toThrow()
  for (const value of ['0', '01', '18446744073709551616', '1.0', ' 1'])
    expect(() => validateContext({ ...c, runtime_epoch: value })).toThrow()
  expect(() =>
    decodeMessage(
      bytes(
        fixture.messages_json[0].replace(
          '"protocol_version":1',
          '"protocol_version":' + '9'.repeat(5000),
        ),
      ),
    ),
  ).toThrow()
})
it('rejects valid but mismatching expected current contexts', async () => {
  for (const key of [
    'binding_digest',
    'session_scope',
    'selector_commitment',
    'request_nonce',
  ]) {
    const changed = { ...c, [key]: '9'.repeat(64) }
    expect(validateContext(changed)).toBeTruthy()
    const r = await started()
    expect(() => r.check(2, changed)).toThrow()
  }
  for (const key of [
    'project_revision',
    'binding_revision',
    'runtime_host_installation_revision',
    'runtime_epoch',
  ]) {
    const r = await started()
    expect(() => r.check(2, { ...c, [key]: '99' })).toThrow()
  }
})

it.each(['\n', '\r', '\u2028', '\u2029'])(
  'rejects trailing line terminators in every object-level scalar: %#',
  async (tail) => {
    for (const [key, value] of Object.entries(c)) {
      if (typeof value !== 'string') continue
      expect(() => validateContext({ ...c, [key]: value + tail })).toThrow()
      expect(() => contextBytes({ ...c, [key]: value + tail })).toThrow()
    }
    await expect(selectorCommitment(fixture.selector + tail)).rejects.toThrow()
    await expect(
      applicationAad(c, '8'.repeat(64) + tail, 'PATCH_PAGE', 0),
    ).rejects.toThrow()
    for (const raw of fixture.messages_json) {
      const message = JSON.parse(raw) as Record<string, unknown>
      for (const [key, value] of Object.entries(message)) {
        if (typeof value === 'string')
          expect(() =>
            encodeMessage({ ...message, [key]: value + tail }),
          ).toThrow()
      }
    }
  },
)
it('does not coerce an AAD kind or call its toString', async () => {
  const toString = vi.fn(() => 'PATCH_PAGE')
  for (const kind of [
    ['PATCH_PAGE'],
    new String('PATCH_PAGE'),
    { toString },
    1,
    true,
    null,
  ]) {
    await expect(
      applicationAad(c, '8'.repeat(64), kind as never, 0),
    ).rejects.toThrow()
  }
  expect(toString).not.toHaveBeenCalled()
})
