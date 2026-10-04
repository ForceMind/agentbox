import { webcrypto, createPrivateKey, createPublicKey } from 'node:crypto'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import {
  A3Browser,
  A3Runtime,
  MAX_CIPHERTEXT_BASE64URL,
  MAX_CIPHERTEXT_BYTES,
  MAX_ENVELOPE_BYTES,
  type A3Current,
} from './a3Crypto'
import {
  applicationAad,
  decodeMessage,
  preparePages,
  type Message,
  type ContentContext,
} from './a3Content'
import { generateX25519KeyPair } from '../workspace/noiseNx'
import fixture from '../../../../../tests/fixtures/a3_content/v1.json'
import vector from '../../../../../tests/fixtures/a3_content/crypto-v1.json'
const text = (raw: Uint8Array) => new TextDecoder().decode(raw)
const bytes = (s: string) => new Uint8Array(new TextEncoder().encode(s))
const canon = (r: object) =>
  bytes(
    JSON.stringify(
      Object.fromEntries(
        Object.entries(r).sort(([a], [b]) => (a < b ? -1 : 1)),
      ),
    ),
  )
const b64 = (raw: Uint8Array) => Buffer.from(raw).toString('base64url')
const read = bytes(fixture.messages_json[0])
const page = bytes(fixture.messages_json[1])
const end = bytes(fixture.messages_json[2])
const patch = new Uint8Array(Buffer.from(fixture.patch_hex, 'hex'))
const context = fixture.context as ContentContext
const options = { admissionStartedAtMs: 0, admissionExpiresAtMs: 30_000 }
beforeAll(() => {
  vi.stubGlobal('crypto', webcrypto)
})
afterEach(() => {
  vi.restoreAllMocks()
})
class MaliciousRuntime extends A3Runtime {
  async forge(
    inner: Uint8Array,
    kind: Message['kind'],
    sequence: number,
  ): Promise<Uint8Array> {
    const aad = await applicationAad(
      context,
      Buffer.from(this.transport.handshake_hash).toString('hex'),
      kind,
      sequence,
    )
    return canon({
      domain: 'agentbox-a3-content/record/v1',
      context_digest: fixture.context_digest,
      kind,
      sequence,
      ciphertext: b64(await this.transport.send.encrypt(inner, aad)),
    })
  }
}
async function pair(ready = true) {
  const keys = await generateX25519KeyPair()
  const pin = new Uint8Array(
    await crypto.subtle.exportKey('raw', keys.publicKey),
  )
  let live: A3Current = { context, nowMs: 0, runtimePin: pin }
  const port = { current: () => live }
  const browser = new A3Browser(context, port, options)
  const runtime = new MaliciousRuntime(context, port, options, keys)
  const handshake = async () => {
    const init = await browser.start()
    expect(browser.state).toBe('WAIT_ATTEST')
    const attest = await runtime.acceptInit(init)
    expect(runtime.state).toBe('WAIT_CONFIRM')
    const confirm = await browser.acceptAttest(attest)
    expect(browser.state).toBe('WAIT_ACK')
    const ack = await runtime.acceptConfirm(confirm)
    expect(runtime.state).toBe('READY')
    await browser.acceptAck(ack)
    expect(browser.state).toBe('READY')
    return { init, attest, confirm, ack }
  }
  if (ready) await handshake()
  return {
    browser,
    runtime,
    pin,
    keys,
    handshake,
    change: (next: Partial<A3Current>) => {
      live = { ...live, ...next }
    },
  }
}
async function started() {
  const p = await pair()
  expect(
    await p.runtime.decryptRead(await p.browser.encryptRead(read)),
  ).toEqual(decodeMessage(read))
  return p
}
describe('inert independent A3 encryption', () => {
  it('matches independent PyCA/Noise-C literal handshake and encrypted records exactly', async () => {
    const pairFromPublicFixture = async (
      raw: string,
    ): Promise<CryptoKeyPair> => {
      const der = Buffer.concat([
        Buffer.from('302e020100300506032b656e04220420', 'hex'),
        Buffer.from(raw, 'hex'),
      ])
      const nodePrivate = createPrivateKey({
        key: der,
        format: 'der',
        type: 'pkcs8',
      })
      const publicRaw = createPublicKey(nodePrivate)
        .export({ format: 'der', type: 'spki' })
        .subarray(-32)
      return {
        privateKey: await crypto.subtle.importKey(
          'pkcs8',
          der,
          { name: 'X25519' },
          false,
          ['deriveBits'],
        ),
        publicKey: await crypto.subtle.importKey(
          'raw',
          publicRaw,
          { name: 'X25519' },
          true,
          [],
        ),
      }
    }
    const pin = new Uint8Array(Buffer.from(vector.runtime_public, 'hex'))
    const c = vector.context as ContentContext
    const port = { current: () => ({ context: c, runtimePin: pin, nowMs: 0 }) }
    const browser = new A3Browser(c, port, {
      ...options,
      ephemeralKeyPair: await pairFromPublicFixture(vector.init_ephemeral),
    })
    const runtime = new A3Runtime(
      c,
      port,
      {
        ...options,
        ephemeralKeyPair: await pairFromPublicFixture(vector.resp_ephemeral),
      },
      await pairFromPublicFixture(vector.resp_static),
    )
    vi.spyOn(crypto, 'getRandomValues').mockImplementationOnce(
      <T extends ArrayBufferView | null>(array: T): T => {
        if (!(array instanceof Uint8Array))
          throw new Error('Unexpected vector RNG input')
        array.set(Buffer.from(vector.challenge, 'hex'))
        return array
      },
    )
    const init = await browser.start()
    expect(text(init)).toBe(vector.key_frames[0])
    const attest = await runtime.acceptInit(init)
    expect(text(attest)).toBe(vector.key_frames[1])
    const confirm = await browser.acceptAttest(attest)
    expect(text(confirm)).toBe(vector.key_frames[2])
    const ack = await runtime.acceptConfirm(confirm)
    expect(text(ack)).toBe(vector.key_frames[3])
    await browser.acceptAck(ack)
    const request = await browser.encryptRead(bytes(vector.plaintexts[0]))
    expect(text(request)).toBe(vector.records[0])
    await runtime.decryptRead(request)
    const page = await runtime.encryptResponse(bytes(vector.plaintexts[1]))
    expect(text(page)).toBe(vector.records[1])
    expect(await browser.acceptResponse(page)).toBeUndefined()
    const end = await runtime.encryptResponse(bytes(vector.plaintexts[2]))
    expect(text(end)).toBe(vector.records[2])
    expect(await browser.acceptResponse(end)).toEqual(
      new Uint8Array(Buffer.from(vector.patch_hex, 'hex')),
    )
    expect(browser.state).toBe('CLOSED')
  })
  it.each(['confirm', 'ack', 'transcript'])(
    'rejects modified %s and closes permanently',
    async (mode) => {
      const p = await pair(false)
      const confirm = await p.browser.acceptAttest(
        await p.runtime.acceptInit(await p.browser.start()),
      )
      if (mode === 'confirm') {
        const r = JSON.parse(text(confirm))
        r.data = 'A'.repeat(64)
        await expect(p.runtime.acceptConfirm(canon(r))).rejects.toThrow()
        expect(p.runtime.state).toBe('CLOSED')
      } else {
        const r = JSON.parse(text(await p.runtime.acceptConfirm(confirm)))
        if (mode === 'ack') r.data = 'A'.repeat(64)
        else r.transcript_hash = '0'.repeat(64)
        await expect(p.browser.acceptAck(canon(r))).rejects.toThrow()
        expect(p.browser.state).toBe('CLOSED')
      }
    },
  )
  it('rejects application traffic before confirmation and duplicate READ', async () => {
    const p = await pair(false)
    await expect(p.browser.encryptRead(read)).rejects.toThrow()
    expect(p.browser.state).toBe('CLOSED')
    const q = await started()
    await expect(q.browser.encryptRead(read)).rejects.toThrow()
    expect(q.browser.state).toBe('CLOSED')
  })

  it('performs NX, both n=0 confirmations and one verified read with no partial output', async () => {
    const p = await started()
    const wire = await p.runtime.encryptResponse(page)
    expect(text(wire)).not.toContain('data')
    expect(await p.browser.acceptResponse(wire)).toBeUndefined()
    const complete = await p.runtime.encryptResponse(end)
    expect(p.runtime.state).toBe('CLOSED')
    expect(await p.browser.acceptResponse(complete)).toEqual(patch)
    expect(p.browser.state).toBe('CLOSED')
    await expect(p.browser.acceptResponse(complete)).rejects.toThrow()
  })
  it('uses exact independent protocol key frames and lengths', async () => {
    const p = await pair(false)
    const frames = await p.handshake()
    for (const [name, frame] of Object.entries(frames)) {
      const r = JSON.parse(text(frame))
      expect(r.protocol_id).toBe('agentbox-a3-content/v1')
      expect(r.protocol_version).toBe(1)
      expect(r.context_digest).toBe(fixture.context_digest)
      expect(Buffer.from(r.data, 'base64url').length).toBe(
        name === 'init' ? 32 : name === 'attest' ? 128 : 48,
      )
      expect(frame).toEqual(canon(r))
      expect(Object.keys(r)).toHaveLength(name === 'ack' ? 6 : 5)
      if (name === 'ack') expect(r.transcript_hash).toMatch(/^[a-f0-9]{64}$/)
    }
  })
  it('rejects independently incorrect runtime pin', async () => {
    const p = await pair(false)
    const bad = new A3Browser(
      context,
      {
        current: () => ({ context, nowMs: 0, runtimePin: new Uint8Array(32) }),
      },
      options,
    )
    await expect(
      bad.acceptAttest(await p.runtime.acceptInit(await bad.start())),
    ).rejects.toThrow()
    expect(bad.state).toBe('CLOSED')
  })
  it.each(['pin', 'context', 'expiry', 'regression', 'revocation'])(
    'permanently closes on trusted %s drift',
    async (reason) => {
      const p = await started()
      const wire = await p.runtime.encryptResponse(page)
      if (reason === 'pin') p.change({ runtimePin: new Uint8Array(32) })
      if (reason === 'context')
        p.change({ context: { ...context, runtime_epoch: '2' } })
      if (reason === 'expiry') p.change({ nowMs: 30_000 })
      if (reason === 'regression') p.change({ nowMs: -1 })
      if (reason === 'revocation') p.browser.close()
      await expect(p.browser.acceptResponse(wire)).rejects.toThrow()
      expect(p.browser.state).toBe('CLOSED')
      p.change({ context, nowMs: 0, runtimePin: p.pin })
      await expect(p.browser.acceptResponse(wire)).rejects.toThrow()
    },
  )
  it('enforces the original 5 second handshake deadline and never resets read expiry', async () => {
    const p = await pair(false)
    const init = await p.browser.start()
    p.change({ nowMs: 4999 })
    const attest = await p.runtime.acceptInit(init)
    p.change({ nowMs: 5000 })
    await expect(p.browser.acceptAttest(attest)).rejects.toThrow()
    const q = await pair()
    q.change({ nowMs: 29999 })
    await q.runtime.decryptRead(await q.browser.encryptRead(read))
    q.change({ nowMs: 30000 })
    await expect(q.runtime.encryptResponse(page)).rejects.toThrow()
  })
  it('rejects replay and concurrent work without reusable state', async () => {
    const p = await started()
    const wire = await p.runtime.encryptResponse(page)
    await p.browser.acceptResponse(wire)
    await expect(p.browser.acceptResponse(wire)).rejects.toThrow()
    const q = await pair(false)
    const pending = q.browser.start()
    await expect(q.browser.start()).rejects.toThrow()
    await expect(pending).rejects.toThrow()
    expect(q.browser.state).toBe('CLOSED')
  })
  it.each(['domain', 'context_digest', 'kind', 'sequence', 'ciphertext'])(
    'authenticates outer %s',
    async (key) => {
      const p = await started()
      const r = JSON.parse(text(await p.runtime.encryptResponse(page)))
      r[key] =
        key === 'sequence'
          ? 1
          : key === 'kind'
            ? 'PATCH_END'
            : key === 'ciphertext'
              ? (r[key][0] === 'A' ? 'B' : 'A') + r[key].slice(1)
              : 'invalid'
      await expect(p.browser.acceptResponse(canon(r))).rejects.toThrow()
      expect(p.browser.state).toBe('CLOSED')
    },
  )
  it.each(['context_digest', 'request_nonce', 'kind', 'sequence'])(
    'rejects authenticated but inconsistent inner %s',
    async (key) => {
      const p = await started()
      const r = JSON.parse(text(page))
      r[key] =
        key === 'sequence' ? 1 : key === 'kind' ? 'PATCH_END' : 'f'.repeat(64)
      await expect(
        p.browser.acceptResponse(
          await p.runtime.forge(canon(r), 'PATCH_PAGE', 0),
        ),
      ).rejects.toThrow()
      expect(p.browser.state).toBe('CLOSED')
    },
  )
  it.each([
    'duplicate',
    'nested',
    'whitespace',
    'padding',
    'extra',
    'utf8',
    'oversize',
  ])('rejects bounded flat outer parser %s', async (kind) => {
    const p = await started()
    const wire = await p.runtime.encryptResponse(page)
    let bad = wire
    if (kind === 'duplicate')
      bad = bytes(
        text(wire).replace('"sequence":0', '"sequence":0,"sequence":0'),
      )
    if (kind === 'nested') bad = bytes('{"ciphertext":{"x":1}}')
    if (kind === 'whitespace') bad = bytes(' ' + text(wire))
    if (kind === 'padding') {
      const r = JSON.parse(text(wire))
      r.ciphertext += '='
      bad = canon(r)
    }
    if (kind === 'extra') bad = canon({ ...JSON.parse(text(wire)), extra: 'x' })
    if (kind === 'utf8') bad = new Uint8Array([255])
    if (kind === 'oversize') bad = new Uint8Array(MAX_ENVELOPE_BYTES + 1)
    const parse = vi.spyOn(JSON, 'parse')
    await expect(p.browser.acceptResponse(bad)).rejects.toThrow()
    if (['nested', 'whitespace', 'utf8', 'oversize'].includes(kind))
      expect(parse).not.toHaveBeenCalled()
  })
  it('accepts exact 16KiB plaintext/16400 cipher/21867 base64 and rejects the next encoded byte before decoding', async () => {
    const p = await started()
    const pages = await preparePages(
      context,
      bytes('x'.repeat(191504)),
      '1791111111111',
    )
    let largest = 0
    for (const raw of pages) {
      const wire = await p.runtime.encryptResponse(raw)
      const r = JSON.parse(text(wire))
      largest = Math.max(largest, r.ciphertext.length)
      expect(Buffer.from(r.ciphertext, 'base64url').length).toBe(
        raw.length + 16,
      )
      expect(wire.length).toBeLessThan(MAX_ENVELOPE_BYTES)
      const result = await p.browser.acceptResponse(wire)
      if (decodeMessage(raw).kind === 'PATCH_END')
        expect(result).toEqual(bytes('x'.repeat(191504)))
      else expect(result).toBeUndefined()
    }
    expect(largest).toBe(MAX_CIPHERTEXT_BASE64URL)
    expect(MAX_CIPHERTEXT_BYTES).toBe(16400)
    const q = await started()
    const bad = canon({
      domain: 'agentbox-a3-content/record/v1',
      context_digest: fixture.context_digest,
      kind: 'PATCH_PAGE',
      sequence: 0,
      ciphertext: 'A'.repeat(MAX_CIPHERTEXT_BASE64URL + 1),
    })
    const decode = vi.spyOn(globalThis, 'atob')
    await expect(q.browser.acceptResponse(bad)).rejects.toThrow()
    expect(decode).not.toHaveBeenCalled()
  })
  it('fences close during a pending hash before handshake bytes can escape', async () => {
    const p = await pair(false)
    const original = crypto.subtle.digest.bind(crypto.subtle)
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    vi.spyOn(crypto.subtle, 'digest').mockImplementationOnce(
      async (...args) => {
        await gate
        return original(...args)
      },
    )
    const pending = p.browser.start()
    p.browser.close()
    release()
    await expect(pending).rejects.toThrow()
    expect(p.browser.state).toBe('CLOSED')
  })
  it.each(['close', 'expiry', 'pin', 'context'])(
    'fences %s during ContentRead final digest and publishes no partial bytes',
    async (mode) => {
      const p = await started()
      await p.browser.acceptResponse(await p.runtime.encryptResponse(page))
      const wire = await p.runtime.encryptResponse(end)
      const original = crypto.subtle.digest.bind(crypto.subtle)
      vi.spyOn(crypto.subtle, 'digest').mockImplementation(async (...args) => {
        const result = await original(...args)
        const input = args[1] as Uint8Array
        if (input.byteLength === patch.length) {
          if (mode === 'close') p.browser.close()
          if (mode === 'expiry') p.change({ nowMs: 30000 })
          if (mode === 'pin') p.change({ runtimePin: new Uint8Array(32) })
          if (mode === 'context')
            p.change({ context: { ...context, runtime_epoch: '2' } })
        }
        return result
      })
      await expect(p.browser.acceptResponse(wire)).rejects.toThrow()
      expect(p.browser.state).toBe('CLOSED')
    },
  )
  it('closes on encrypted ERROR and never exposes held pages', async () => {
    const p = await started()
    await p.browser.acceptResponse(await p.runtime.encryptResponse(page))
    const error = bytes(fixture.messages_json[3])
    await expect(
      p.browser.acceptResponse(await p.runtime.encryptResponse(error)),
    ).rejects.toThrow()
    expect(p.browser.state).toBe('CLOSED')
    expect(p.runtime.state).toBe('CLOSED')
  })
  it('does not expose payload, context, challenge, keys or pin in JSON diagnostics', async () => {
    const p = await pair(false)
    expect(JSON.stringify(p.browser)).toBe('{"state":"NEW"}')
    expect(JSON.stringify(p.runtime)).toBe('{"state":"NEW"}')
    await p.handshake()
    expect(JSON.stringify(p.browser)).toBe('{"state":"READY"}')
  })
})
