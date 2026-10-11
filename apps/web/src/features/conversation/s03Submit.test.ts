// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import fixture from '../../../../../tests/fixtures/kebui_s03_submit/v1.json'
import {
  NXInitiator,
  NXResponder,
  type NoiseTransport,
} from '../workspace/noiseNx'
import {
  S03Error,
  S03_LIMITS,
  SyntheticS03Sender,
  SyntheticS03TestRoot,
  buildAAD,
  buildCanary,
  buildContext,
  buildPrologue,
  decodeFrame,
  encodeFrame,
  reserveRelayForTest,
  type S03Context,
  type SyntheticS03Endpoint,
} from './s03Submit'

const bytes = (value: string) => new TextEncoder().encode(value)
const equalBytes = (a: Uint8Array | undefined, b: Uint8Array) =>
  !!a && a.length === b.length && a.every((value, index) => value === b[index])
const fromHex = (value: string) =>
  new Uint8Array(value.match(/../g)!.map((byte) => Number.parseInt(byte, 16)))
const asHex = (value: Uint8Array) =>
  Array.from(value, (byte) => byte.toString(16).padStart(2, '0')).join('')
let sequence = 0
const roots: SyntheticS03TestRoot[] = []
const releases: (() => void)[] = []
function context(): S03Context {
  const suffix = (++sequence).toString(16).padStart(32, '0')
  return {
    ...fixture.context,
    request_id: `kreq_${suffix}`,
    channel_id: `ks03c_${suffix}`,
    source_lease_id: `ks03l_${suffix}`,
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { resolve, reject, promise }
}
async function pair(
  privateHex: string,
  publicHex: string,
): Promise<CryptoKeyPair> {
  return {
    privateKey: await crypto.subtle.importKey(
      'pkcs8',
      fromHex('302e020100300506032b656e04220420' + privateHex),
      'X25519',
      false,
      ['deriveBits'],
    ),
    publicKey: await crypto.subtle.importKey(
      'raw',
      fromHex(publicHex),
      'X25519',
      true,
      [],
    ),
  }
}
function checkError(error: unknown, code?: string): void {
  expect(error instanceof S03Error).toBe(true)
  const value = error as S03Error
  expect(value.message).toBe(code ?? value.code)
  expect(
    ['s03_invalid', 's03_unavailable', 's03_busy', 's03_revoked'].includes(
      value.code,
    ),
  ).toBe(true)
  expect(value.cause).toBeUndefined()
  expect(
    Object.keys(value).every((key) => ['name', 'code'].includes(key)),
  ).toBe(true)
  expect(value.stack?.includes('private-canary')).toBe(false)
}
async function rejection(
  promise: Promise<unknown>,
  code?: string,
): Promise<void> {
  let seen = false
  try {
    await promise
  } catch (error) {
    seen = true
    checkError(error, code)
  }
  expect(seen).toBe(true)
}
function bareEndpoint(): SyntheticS03Endpoint {
  return {
    waitWritable: async () => {},
    read: async (signal) =>
      new Promise((_resolve, reject) => {
        if (signal.aborted) reject(new Error('private-canary'))
        else
          signal.addEventListener(
            'abort',
            () => reject(new Error('private-canary')),
            { once: true },
          )
      }),
    write: () => true,
    close: () => {},
  }
}
function rootFor(
  endpoint: SyntheticS03Endpoint,
  ctx = context(),
  clock = () => 9_000_000_000_000n,
  deadline = 9_008_000_000_000n,
) {
  const root = SyntheticS03TestRoot.forFixture({
    context: ctx,
    endpoint,
    clock,
    deadline,
  })
  roots.push(root)
  return { root, sender: root.open(endpoint), context: ctx }
}
async function connection(
  options: {
    holdAttest?: boolean
    holdReady?: boolean
    wrongPin?: boolean
    corruptReady?: boolean
    writeFalse?: boolean
    clock?: () => bigint
    deadline?: bigint
  } = {},
) {
  const ctx = options.wrongPin
    ? { ...context(), runtime_pin: '0'.repeat(64) }
    : context()
  const cd = new Uint8Array(
    await crypto.subtle.digest('SHA-256', buildContext(ctx) as BufferSource),
  )
  const responder = new NXResponder(
    buildPrologue(buildContext(ctx)),
    await pair(
      fixture.keys.runtime_static_private,
      fixture.context.runtime_pin,
    ),
  )
  let transport: NoiseTransport | undefined
  let queued: Uint8Array | undefined
  let reader: ReturnType<typeof deferred<Uint8Array>> | undefined
  let closed = false
  let writes = 0
  let effects = 0
  let bodyBytes: Uint8Array | undefined
  let task: Promise<void> = Promise.resolve()
  let beforeWritable: (() => Promise<void>) | undefined
  function answer(raw: Uint8Array) {
    if (reader) {
      const target = reader
      reader = undefined
      target.resolve(raw)
    } else queued = raw
  }
  const endpoint: SyntheticS03Endpoint = {
    waitWritable: async (signal) => {
      if (signal.aborted) throw new Error('private-canary')
      await beforeWritable?.()
      if (signal.aborted) throw new Error('private-canary')
    },
    read: (signal) => {
      if (signal.aborted) return Promise.reject(new Error('private-canary'))
      if (queued) {
        const raw = queued
        queued = undefined
        return Promise.resolve(raw)
      }
      reader = deferred<Uint8Array>()
      const target = reader
      const abort = () => {
        reader = undefined
        target.reject(new Error('private-canary'))
      }
      signal.addEventListener('abort', abort, { once: true })
      return target.promise.finally(() =>
        signal.removeEventListener('abort', abort),
      )
    },
    write: (raw) => {
      if (closed) return false
      writes++
      // This fixed test peer begins processing only after its synchronous write.
      task = (async () => {
        const frame = decodeFrame(raw, asHex(cd))
        if (frame.kind === 'KEY_INIT') {
          await responder.readMessage1(frame.data)
          const message = await responder.writeMessage2()
          transport = responder.takeTransport()
          if (!options.holdAttest)
            answer(encodeFrame(asHex(cd), 'KEY_ATTEST', 0, message))
        } else if (frame.kind === 'KEY_CONFIRM') {
          const value = await transport!.receive.decrypt(
            frame.data,
            buildAAD(cd, transport!.handshake_hash, 'KEY_CONFIRM'),
          )
          expect(
            equalBytes(
              value,
              buildCanary(cd, transport!.handshake_hash, 'KEY_CONFIRM'),
            ),
          ).toBe(true)
          const message = await transport!.send.encrypt(
            buildCanary(cd, transport!.handshake_hash, 'KEY_READY'),
            buildAAD(cd, transport!.handshake_hash, 'KEY_READY'),
          )
          if (options.corruptReady) message[message.length - 1] ^= 1
          if (!options.holdReady)
            answer(encodeFrame(asHex(cd), 'KEY_READY', 0, message))
        } else {
          bodyBytes = await transport!.receive.decrypt(
            frame.data,
            buildAAD(cd, transport!.handshake_hash, 'SUBMIT'),
          )
          effects++
          transport!.destroy()
        }
      })()
      return !options.writeFalse
    },
    close: () => {
      closed = true
      if (reader) {
        reader.reject(new Error('private-canary'))
        reader = undefined
      }
    },
  }
  // Pin drift means the trusted fixture differs; wire does not choose a pin.
  const bound = options.wrongPin ? { ...ctx, runtime_pin: '0'.repeat(64) } : ctx
  const local = rootFor(endpoint, bound, options.clock, options.deadline)
  return {
    ...local,
    endpoint,
    cd,
    setWritable(value: () => Promise<void>) {
      beforeWritable = value
    },
    async result() {
      await task
      return { effects, body: bodyBytes, writes }
    },
  }
}
afterEach(() => {
  for (const root of roots.splice(0)) root.close()
  for (const release of releases.splice(0)) release()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('S03 independent canonical codecs', () => {
  it('fixes the maximum context, raw body and conservative owned-copy arithmetic', () => {
    const maximum = { ...fixture.context, agent_type: 'claude' }
    for (const key of [
      'auth_epoch',
      'project_revision',
      'binding_revision',
      'host_revision',
      'runtime_epoch',
      'api_authority_epoch',
      'conversation_revision',
      'generation',
    ])
      (maximum as Record<string, string>)[key] = '18446744073709551615'
    expect(buildContext(maximum)).toHaveLength(739)
    expect(buildPrologue(buildContext(maximum))).toHaveLength(777)
    expect(
      buildAAD(new Uint8Array(32), new Uint8Array(32), 'SUBMIT'),
    ).toHaveLength(101)
    expect(
      encodeFrame('0'.repeat(64), 'SUBMIT', 1, new Uint8Array(16_400)),
    ).toHaveLength(22_031)
    expect(JSON.stringify('\0'.repeat(16_384)).length).toBe(98_306)
    expect(S03_LIMITS.webOwnedCopies).toBe(
      4 * 16384 +
        2 * 16384 +
        3 * 16400 +
        8 * 21867 +
        10 * 22031 +
        8 * 739 +
        8 * 101 +
        65536,
    )
  })
  it.each([
    ['KEY_INIT', 32, 209],
    ['KEY_ATTEST', 96, 296],
    ['KEY_CONFIRM', 111, 317],
    ['KEY_READY', 109, 313],
    ['SUBMIT', 17, 187],
  ] as const)('round-trips exactly %s', (kind, length, rawLength) => {
    const raw = encodeFrame(
      'a'.repeat(64),
      kind,
      kind === 'SUBMIT' ? 1 : 0,
      new Uint8Array(length),
    )
    expect(raw.length).toBe(rawLength)
    const frame = decodeFrame(
      raw,
      'a'.repeat(64),
      kind,
      kind === 'SUBMIT' ? 1 : 0,
    )
    expect(equalBytes(frame.data, new Uint8Array(length))).toBe(true)
  })
  it('rejects complete raw bounds and all noncanonical flat-record forms', () => {
    const raw = encodeFrame('a'.repeat(64), 'KEY_INIT', 0, new Uint8Array(32))
    const text = new TextDecoder().decode(raw)
    const bad = [
      new Uint8Array(22_032),
      raw.slice(0, -1),
      bytes(text + '\n'),
      bytes(' ' + text),
      bytes('\ufeff' + text),
      bytes(text.replace('"version":1', '"version":1,"version":1')),
      bytes(text.replace('"version":1', '"version":1,"extra":1')),
      bytes(text.replace('"version":1', '"version":null')),
      bytes('[' + text + ']'),
      bytes(text + text),
      bytes(text.replace('KEY_INIT', 'KEY_READY')),
      bytes(text.replace('/frame/v1', '/frame/v2')),
      bytes(text.replace('"seq":0', '"seq":-0')),
      bytes(text.replace('"seq":0', '"seq":1')),
      bytes(text.replace('"seq":0', '"seq":2')),
      bytes(text.replace('"seq":0', '"seq":0.0')),
      bytes(text.replace('"seq":0', '"seq":"0"')),
      bytes(text.replace('"data":"', '"data":"=')),
      bytes(text.replace('"data":"', '"data":"\\u0041')),
      bytes(text.replace(/A","domain/, 'B","domain')),
    ]
    for (const value of bad)
      expect(() => decodeFrame(value)).toThrow('s03_invalid')
  })
  it.each(Object.keys(fixture.context))(
    'strictly rejects a changed type for %s',
    (key) => {
      expect(() => buildContext({ ...fixture.context, [key]: true })).toThrow(
        's03_invalid',
      )
    },
  )
  it('rejects accessors, subclasses, extra fields and noncanonical u64 strings', () => {
    for (const value of [
      '0',
      '01',
      '+1',
      ' 1',
      '1\n',
      '18446744073709551616',
      '١',
      1,
      1n,
      null,
    ])
      expect(() =>
        buildContext({ ...fixture.context, auth_epoch: value }),
      ).toThrow('s03_invalid')
    let calls = 0
    const row = { ...fixture.context }
    Object.defineProperty(row, 'request_id', {
      enumerable: true,
      get() {
        calls++
        return fixture.context.request_id
      },
    })
    expect(() => buildContext(row)).toThrow('s03_invalid')
    expect(calls).toBe(0)
    expect(() => buildContext({ ...fixture.context, extra: 'x' })).toThrow(
      's03_invalid',
    )
    expect(() =>
      buildContext(Object.assign(Object.create({}), fixture.context)),
    ).toThrow('s03_invalid')
  })
})

describe('S03 admitted sender lifetime and immutable input', () => {
  it.each([
    new Uint8Array([0]),
    new Uint8Array(16_384),
    bytes('😀'.repeat(4096)),
    bytes('\ufeff'),
    bytes('"\\'),
    bytes('a\r\nb'),
    bytes('e\u0301'),
    bytes('é'),
  ])('transports original strict UTF8 bytes once, case %#', async (body) => {
    const run = await connection()
    await run.sender.handshake()
    expect(run.sender.snapshot().reserved).toBe(1_048_576)
    expect(run.sender.snapshot().phase).toBe('READY')
    await run.sender.submit(body)
    const result = await run.result()
    expect(result.effects).toBe(1)
    expect(equalBytes(result.body, body)).toBe(true)
    expect(run.sender.snapshot()).toMatchObject({
      phase: 'CLOSED',
      reserved: 0,
      keysDetached: true,
      writes: 3,
      submitWrites: 1,
      sendCounter: 2,
      receiveCounter: 1,
    })
    await rejection(run.sender.submit(body), 's03_revoked')
  })
  it('snapshots before the first crypto await and cannot be changed by its caller', async () => {
    const run = await connection()
    await run.sender.handshake()
    const body = bytes('immutable synthetic fixture')
    const expected = new Uint8Array(body)
    const pending = run.sender.submit(body)
    body.fill(0)
    await pending
    expect(equalBytes((await run.result()).body, expected)).toBe(true)
  })
  it.each([
    new Uint8Array(),
    new Uint8Array(16385),
    new Uint8Array([0xc0, 0x80]),
    new Uint8Array([0xed, 0xa0, 0x80]),
    new Uint8Array([0xf4, 0x90, 0x80, 0x80]),
    new Uint8Array([0xf0, 0x9f]),
  ])(
    'fails closed on invalid plaintext %# without publication',
    async (body) => {
      const run = await connection()
      await run.sender.handshake()
      await rejection(run.sender.submit(body), 's03_invalid')
      if (body.length === 16_384)
        expect(
          Object.values(run.sender.snapshot().peakCopies).reduce(
            (sum, value) => sum + value,
            0,
          ),
        ).toBe(S03_LIMITS.webOwnedCopies)
      expect(run.sender.snapshot()).toMatchObject({
        phase: 'CLOSED',
        submitWrites: 0,
        reserved: 0,
      })
    },
  )
  it('rejects Buffer/subclass, shared/resizable/detached and accessor array impostors', async () => {
    class Subclass extends Uint8Array {}
    const detached = new Uint8Array([1])
    structuredClone(detached.buffer, { transfer: [detached.buffer] })
    const getter = new Uint8Array([1])
    let reads = 0
    Object.defineProperty(getter, 'buffer', {
      get() {
        reads++
        return new ArrayBuffer(1)
      },
    })
    const invalid = [
      Buffer.from([1]),
      new Subclass([1]),
      new Uint8Array(new SharedArrayBuffer(1)),
      detached,
      getter,
      Object.create(Uint8Array.prototype),
      new Proxy(new Uint8Array([1]), {}),
    ]
    if ('resizable' in ArrayBuffer.prototype)
      invalid.push(
        new Uint8Array(
          Reflect.construct(ArrayBuffer, [1, { maxByteLength: 2 }]),
        ),
      )
    for (const value of invalid) {
      const run = await connection()
      await run.sender.handshake()
      await rejection(run.sender.submit(value), 's03_invalid')
      expect(run.sender.snapshot().submitWrites).toBe(0)
    }
    expect(reads).toBe(0)
  })
  it('reserves before second-root context getters, and charges idle plus shared relay', () => {
    const lease = reserveRelayForTest()
    releases.push(lease.release)
    const endpoint = bareEndpoint()
    const { sender } = rootFor(endpoint)
    expect(sender.snapshot()).toMatchObject({
      reserved: 1048576,
      processReserved: 1571840,
    })
    let reads = 0
    const context = Object.defineProperty({}, 'scope', {
      get() {
        reads++
        throw new Error('private-canary')
      },
    })
    expect(() =>
      SyntheticS03TestRoot.forFixture({
        context,
        endpoint,
        clock: () => 0n,
        deadline: 1n,
      }),
    ).toThrow('s03_busy')
    expect(reads).toBe(0)
    expect(() => reserveRelayForTest()).toThrow('s03_busy')
  })
  it('rejects copied/serialized/subclass constructors and endpoint rebinding', () => {
    const endpoint = bareEndpoint()
    const { root, sender } = rootFor(endpoint)
    expect(Object.isFrozen(root)).toBe(true)
    expect(Object.isFrozen(sender)).toBe(true)
    expect(() => root.open(bareEndpoint())).toThrow('s03_revoked')
    expect(() => new SyntheticS03Sender(Symbol(), {} as never)).toThrow(
      's03_unavailable',
    )
    expect(JSON.stringify(root)).toBe('{}')
  })
  it('concurrent calls close before a second primitive invocation/copy', async () => {
    const run = await connection()
    await run.sender.handshake()
    const deferredEncrypt = deferred<ArrayBuffer>()
    vi.spyOn(crypto.subtle, 'encrypt').mockReturnValueOnce(
      deferredEncrypt.promise,
    )
    const first = run.sender.submit(bytes('private-canary'))
    await rejection(run.sender.submit(bytes('second')), 's03_busy')
    expect(run.sender.snapshot()).toMatchObject({
      phase: 'CLOSED',
      reserved: 1048576,
      busy: true,
      submitWrites: 0,
    })
    deferredEncrypt.resolve(new ArrayBuffer(30))
    await rejection(first)
    expect(run.sender.snapshot().reserved).toBe(0)
  })
  it('retains the crypto lane after local revoke until actual promise settlement', async () => {
    const run = await connection()
    await run.sender.handshake()
    const delayed = deferred<ArrayBuffer>()
    vi.spyOn(crypto.subtle, 'encrypt').mockReturnValueOnce(delayed.promise)
    const pending = run.sender.submit(bytes('private-canary'))
    await Promise.resolve()
    run.root.revoke()
    expect(run.sender.snapshot()).toMatchObject({
      phase: 'CLOSED',
      reserved: 1048576,
      keysDetached: true,
    })
    delayed.resolve(new ArrayBuffer(30))
    await rejection(pending)
    expect(run.sender.snapshot()).toMatchObject({
      reserved: 0,
      submitWrites: 0,
    })
  })
  it('rechecks local revocation after writable capacity and never publishes stale bytes', async () => {
    const run = await connection()
    await run.sender.handshake()
    const waiting = deferred<void>()
    const reached = deferred<void>()
    run.setWritable(() => {
      reached.resolve()
      return waiting.promise
    })
    const pending = run.sender.submit(bytes('private-canary'))
    await reached.promise
    run.root.revoke()
    expect(run.sender.snapshot().reserved).toBe(1048576)
    waiting.resolve()
    await rejection(pending)
    expect(run.sender.snapshot()).toMatchObject({
      reserved: 0,
      submitWrites: 0,
    })
  })
  it('records failed synchronous publication as uncertain and never retries', async () => {
    const run = await connection()
    await run.sender.handshake()
    // Root sealed endpoint method identities; changing the external object cannot
    // silently rebind the destination. Use a trusted fixed capacity event instead.
    run.setWritable(async () => {
      run.endpoint.write = () => false
    })
    await run.sender.submit(bytes('synthetic'))
    expect((await run.result()).effects).toBe(1)
    expect(run.sender.snapshot().submitWrites).toBe(1)
    const next = await connection({ writeFalse: true })
    await rejection(next.sender.handshake(), 's03_unavailable')
    expect(next.sender.snapshot()).toMatchObject({
      writes: 1,
      publicationAttempted: true,
      phase: 'CLOSED',
    })
    await next.result()
  })
})

describe('S03 role-local deadline owner and safe failures', () => {
  it('expires idle NEW with no inbound message and equality is terminal', () => {
    let now = 9_000_000_000_000n
    const endpoint = bareEndpoint()
    const { root, sender } = rootFor(endpoint, context(), () => now)
    now += 2_000_000_000n
    root.dispatchDeadlineForTest()
    expect(sender.snapshot()).toMatchObject({
      phase: 'CLOSED',
      reserved: 0,
      keysDetached: true,
      writes: 0,
    })
  })
  it.each([0, NaN, -1n, 2n ** 64n, true, '1'])(
    'rejects illegal role-local clock %#',
    (value) => {
      const endpoint = bareEndpoint()
      expect(() =>
        rootFor(endpoint, context(), () => value as bigint),
      ).toThrow()
    },
  )
  it('sticky closes on clock regression or throw without retaining its exception', async () => {
    let now = 9_000_000_000_000n
    const endpoint = bareEndpoint()
    const { root, sender } = rootFor(endpoint, context(), () => now)
    now--
    root.dispatchDeadlineForTest()
    await rejection(sender.handshake(), 's03_revoked')
    expect(() =>
      rootFor(bareEndpoint(), context(), () => {
        throw new Error('private-canary')
      }),
    ).toThrow('s03_invalid')
  })
  it('actually expires idle NEW using its single scheduled timer', async () => {
    const origin = process.hrtime.bigint()
    const start = 9_000_000_000_000n
    const { sender } = rootFor(
      bareEndpoint(),
      context(),
      () => start + process.hrtime.bigint() - origin,
      start + 40_000_000n,
    )
    await new Promise((resolve) => setTimeout(resolve, 70))
    expect(sender.snapshot()).toMatchObject({
      phase: 'CLOSED',
      reserved: 0,
      writes: 0,
    })
  })
  it.each(['attest', 'ready', 'submit'] as const)(
    'expires missing %s through its actual timer without inbound activity',
    async (missing) => {
      const start = 9_000_000_000_000n
      const origin = process.hrtime.bigint()
      const run = await connection({
        holdAttest: missing === 'attest',
        holdReady: missing === 'ready',
        clock: () => start + process.hrtime.bigint() - origin,
        deadline: start + 300_000_000n,
      })
      if (missing === 'submit') {
        await run.sender.handshake()
        expect(run.sender.snapshot().phase).toBe('READY')
        await new Promise((resolve) => setTimeout(resolve, 330))
      } else await rejection(run.sender.handshake(), 's03_revoked')
      expect(run.sender.snapshot()).toMatchObject({
        phase: 'CLOSED',
        reserved: 0,
        submitWrites: 0,
        keysDetached: true,
      })
    },
  )
})

describe('S03 runtime error-code allowlist regression', () => {
  it('sanitizes constructor input, subclasses, forged/getter codes and clock throwables', () => {
    const bad = new S03Error('private-canary' as never)
    expect(bad.message).toBe('s03_invalid')
    expect(bad.code).toBe('s03_invalid')
    expect(Object.isFrozen(bad)).toBe(true)
    class Foreign extends S03Error {}
    const getter = Object.create(S03Error.prototype)
    Object.defineProperty(getter, 'code', {
      get() {
        throw new Error('private-canary')
      },
    })
    const forged = Object.create(S03Error.prototype)
    Object.defineProperty(forged, 'code', { value: 'private-canary' })
    for (const error of [
      bad,
      new Foreign('s03_busy'),
      getter,
      forged,
      new Error('private-canary'),
    ]) {
      try {
        rootFor(bareEndpoint(), context(), () => {
          throw error
        })
      } catch (value) {
        checkError(value, 's03_invalid')
      }
    }
  })
})

describe('S03 non-admitting deterministic primitive vectors', () => {
  it('matches Python context, prologue, AAD, five frames and exact split counters', async () => {
    // These keys go directly to the unchanged primitive. No root/permit exists.
    const vectors = fixture.vectors
    const context = buildContext(fixture.context)
    expect(asHex(context) === vectors.context_hex).toBe(true)
    const cd = new Uint8Array(
      await crypto.subtle.digest('SHA-256', context as BufferSource),
    )
    expect(asHex(cd) === vectors.cd).toBe(true)
    const prologue = buildPrologue(context)
    expect(asHex(prologue) === vectors.prologue_hex).toBe(true)
    const initiator = new NXInitiator(
      prologue,
      await pair(
        fixture.keys.initiator_ephemeral_private,
        '7e698e6c04ff7ce65a05c6e5c1d0338782d223c6390db21ab9c72416c00eef6d',
      ),
    )
    const responder = new NXResponder(
      prologue,
      await pair(
        fixture.keys.runtime_static_private,
        fixture.context.runtime_pin,
      ),
      await pair(
        fixture.keys.responder_ephemeral_private,
        '50bb406cf2cc8b70ffaf66973d06c7324549d29f77602828dadad475021b107a',
      ),
    )
    const init = await initiator.writeMessage1()
    expect(asHex(init) === vectors.message1_hex).toBe(true)
    expect((await responder.readMessage1(init)).length).toBe(0)
    const attest = await responder.writeMessage2()
    expect(asHex(attest) === vectors.message2_hex).toBe(true)
    expect((await initiator.readMessage2(attest)).length).toBe(0)
    const web = initiator.takeTransport(),
      runtime = responder.takeTransport()
    const hh = web.handshake_hash
    expect(asHex(hh) === vectors.handshake_hash).toBe(true)
    expect(
      asHex(buildAAD(cd, hh, 'KEY_CONFIRM')) === vectors.aad_confirm_hex,
    ).toBe(true)
    expect(asHex(buildAAD(cd, hh, 'KEY_READY')) === vectors.aad_ready_hex).toBe(
      true,
    )
    expect(asHex(buildAAD(cd, hh, 'SUBMIT')) === vectors.aad_submit_hex).toBe(
      true,
    )
    const confirm = await web.send.encrypt(
      buildCanary(cd, hh, 'KEY_CONFIRM'),
      buildAAD(cd, hh, 'KEY_CONFIRM'),
    )
    expect(asHex(confirm) === vectors.confirm_ciphertext_hex).toBe(true)
    await runtime.receive.decrypt(confirm, buildAAD(cd, hh, 'KEY_CONFIRM'))
    const ready = await runtime.send.encrypt(
      buildCanary(cd, hh, 'KEY_READY'),
      buildAAD(cd, hh, 'KEY_READY'),
    )
    expect(asHex(ready) === vectors.ready_ciphertext_hex).toBe(true)
    await web.receive.decrypt(ready, buildAAD(cd, hh, 'KEY_READY'))
    const submit = await web.send.encrypt(
      fromHex(fixture.bodies.vector_hex),
      buildAAD(cd, hh, 'SUBMIT'),
    )
    expect(asHex(submit) === vectors.submit_ciphertext_hex).toBe(true)
    await runtime.receive.decrypt(submit, buildAAD(cd, hh, 'SUBMIT'))
    for (const [kind, data] of [
      ['KEY_INIT', init],
      ['KEY_ATTEST', attest],
      ['KEY_CONFIRM', confirm],
      ['KEY_READY', ready],
      ['SUBMIT', submit],
    ] as const)
      expect(
        asHex(
          encodeFrame(vectors.cd, kind, kind === 'SUBMIT' ? 1 : 0, data),
        ) === vectors.frames[kind],
      ).toBe(true)
    expect([
      web.send.counter,
      web.receive.counter,
      runtime.send.counter,
      runtime.receive.counter,
    ]).toEqual([2n, 1n, 1n, 2n])
    web.destroy()
    runtime.destroy()
  })
  it('admitted constructor rejects an ephemeral injection field', () => {
    const endpoint = bareEndpoint()
    expect(() =>
      SyntheticS03TestRoot.forFixture({
        ...{
          context: context(),
          endpoint,
          clock: () => 0n,
          deadline: 8_000_000_000n,
        },
        ephemeralKeyPair: {},
      } as never),
    ).toThrow('s03_invalid')
  })
})

describe('S03 synchronous local-clock reentrancy', () => {
  it('a clock callback that revokes before returning cannot pass the final guard', async () => {
    const holder: { root?: SyntheticS03TestRoot } = {}
    let revoke = false
    const endpoint = bareEndpoint()
    let writes = 0
    endpoint.write = () => {
      writes++
      return true
    }
    const run = rootFor(endpoint, context(), () => {
      if (revoke) holder.root!.revoke()
      return 9_000_000_000_000n
    })
    holder.root = run.root
    revoke = true
    await rejection(run.sender.handshake(), 's03_revoked')
    expect(writes).toBe(0)
    expect(run.sender.snapshot().reserved).toBe(0)
  })
})

describe('S03 remote proof failures', () => {
  it('rejects a valid NX peer with the wrong independently trusted static pin', async () => {
    const run = await connection({ wrongPin: true })
    await rejection(run.sender.handshake(), 's03_invalid')
    expect(run.sender.snapshot()).toMatchObject({
      writes: 1,
      submitWrites: 0,
      keysDetached: true,
      reserved: 0,
    })
    await run.result()
  })
  it('rejects a corrupt ready tag without exposing crypto causes', async () => {
    const run = await connection({ corruptReady: true })
    await rejection(run.sender.handshake(), 's03_invalid')
    expect(run.sender.snapshot()).toMatchObject({
      writes: 2,
      submitWrites: 0,
      keysDetached: true,
      reserved: 0,
    })
  })
})

describe('S03 deadline arithmetic and one timer', () => {
  it('an early dispatch replaces rather than stacks the sole scheduled handle', () => {
    vi.useFakeTimers()
    let now = 9_000_000_000_000n
    const { root, sender } = rootFor(bareEndpoint(), context(), () => now)
    expect(vi.getTimerCount()).toBe(1)
    root.dispatchDeadlineForTest()
    expect(vi.getTimerCount()).toBe(1)
    now += 1_999_999_999n
    root.dispatchDeadlineForTest()
    expect(vi.getTimerCount()).toBe(1)
    now++
    root.dispatchDeadlineForTest()
    expect(vi.getTimerCount()).toBe(0)
    expect(sender.snapshot()).toMatchObject({ phase: 'CLOSED', reserved: 0 })
  })
  it.each([0n, -1n, 9_000_000_000_000n, 2n ** 64n, 1, true, NaN])(
    'rejects original deadline %# without rebasing',
    (deadline) => {
      expect(() =>
        rootFor(
          bareEndpoint(),
          context(),
          () => 9_000_000_000_000n,
          deadline as bigint,
        ),
      ).toThrow('s03_invalid')
    },
  )
  it('rejects handshake deadline overflow rather than wrapping uint64', () => {
    expect(() =>
      rootFor(bareEndpoint(), context(), () => 2n ** 64n - 2n, 2n ** 64n - 1n),
    ).toThrow('s03_invalid')
  })
  it('sanitizes trusted read/close exceptions and retires all known-owned classes', async () => {
    const endpoint = bareEndpoint()
    endpoint.read = async () => {
      throw new Error('private-canary')
    }
    endpoint.close = () => {
      throw new Error('private-canary')
    }
    const { sender } = rootFor(endpoint)
    await rejection(sender.handshake(), 's03_unavailable')
    expect(sender.snapshot().reserved).toBe(0)
    expect(
      Object.values(sender.snapshot().liveCopies).every((value) => value === 0),
    ).toBe(true)
    expect(JSON.stringify(sender.snapshot()).includes('private-canary')).toBe(
      false,
    )
  })
})

describe('S03 sealed private-state receiver checks', () => {
  it('rejects cloned or forged method receivers with only fixed errors', () => {
    const endpoint = bareEndpoint()
    const { root, sender } = rootFor(endpoint)
    const fakeRoot = Object.create(
      SyntheticS03TestRoot.prototype,
    ) as SyntheticS03TestRoot
    const fakeSender = Object.create(
      SyntheticS03Sender.prototype,
    ) as SyntheticS03Sender
    expect(() => fakeRoot.open(endpoint)).toThrow('s03_invalid')
    expect(() => fakeRoot.close()).toThrow('s03_invalid')
    expect(() => fakeSender.handshake()).toThrow('s03_invalid')
    expect(() => fakeSender.submit(bytes('private-canary'))).toThrow(
      's03_invalid',
    )
    expect(() => fakeSender.snapshot()).toThrow('s03_invalid')
    expect(() => root.open(endpoint)).toThrow('s03_revoked')
    expect(sender.snapshot().phase).toBe('CLOSED')
  })
})

describe('bounded byte ingress rejects iterator overrides', () => {
  it.each(['accessor', 'method'] as const)(
    'rejects a raw %s iterator without calling foreign code',
    (mode) => {
      const raw = encodeFrame('a'.repeat(64), 'KEY_INIT', 0, new Uint8Array(32))
      let calls = 0
      const invoke = () => {
        calls++
        throw new Error('private-canary')
      }
      Object.defineProperty(
        raw,
        Symbol.iterator,
        mode === 'accessor' ? { get: invoke } : { value: invoke },
      )
      let caught: unknown
      try {
        decodeFrame(raw)
      } catch (error) {
        caught = error
      }
      checkError(caught, 's03_invalid')
      expect(calls).toBe(0)
    },
  )
  it('checks the byte cap before looking at an oversized raw iterator getter', () => {
    const raw = new Uint8Array(S03_LIMITS.raw + 1)
    let calls = 0
    Object.defineProperty(raw, Symbol.iterator, {
      get() {
        calls++
        throw new Error('private-canary')
      },
    })
    expect(() => decodeFrame(raw)).toThrow('s03_invalid')
    expect(calls).toBe(0)
  })
  it('rejects an input-body iterator without calling it or reaching the primitive', async () => {
    const run = await connection()
    await run.sender.handshake()
    let calls = 0
    const input = bytes('private-canary')
    Object.defineProperty(input, Symbol.iterator, {
      get() {
        calls++
        throw new Error('private-canary')
      },
    })
    const encrypt = vi.spyOn(crypto.subtle, 'encrypt')
    await rejection(run.sender.submit(input), 's03_invalid')
    expect(calls).toBe(0)
    expect(encrypt).not.toHaveBeenCalled()
    expect(run.sender.snapshot()).toMatchObject({
      reserved: 0,
      submitWrites: 0,
    })
  })
})

describe('candidate-3 persistent byte tombstone ownership', () => {
  it('retains one maximum 627-byte record and only bounded construction after channel retirement', () => {
    const endpoint = bareEndpoint()
    const baseline = reserveRelayForTest()
    releases.push(baseline.release)
    const before = baseline.snapshot()
    const maximal = { ...context(), agent_type: 'claude' }
    for (const key of [
      'auth_epoch',
      'project_revision',
      'binding_revision',
      'host_revision',
      'runtime_epoch',
      'api_authority_epoch',
      'conversation_revision',
      'generation',
    ])
      (maximal as Record<string, string>)[key] = '18446744073709551615'
    const { root, sender } = rootFor(endpoint, maximal)
    expect(sender.snapshot().metadataBytes - before.metadataBytes).toBe(627)
    expect(sender.snapshot().metadataEntries - before.metadataEntries).toBe(1)
    expect(sender.snapshot().metadataConstructionPeak).toBe(1881)
    root.close()
    baseline.release()
    expect(sender.snapshot()).toMatchObject({
      reserved: 0,
      processReserved: 261120,
      metadataReserved: 261120,
    })
    expect(sender.snapshot().metadataConstructionPeak).toBeLessThanOrEqual(2508)
    expect(() => rootFor(bareEndpoint(), maximal)).toThrow('s03_revoked')
    expect(baseline.snapshot().metadataEntries).toBe(before.metadataEntries + 1)
  })
  it.each(['request', 'channel', 'lease'] as const)(
    'OR-rejects a previously retired %s binding without adding an index copy',
    (field) => {
      const first = context()
      const { root, sender } = rootFor(bareEndpoint(), first)
      root.close()
      const count = sender.snapshot().metadataEntries
      const next = { ...context() }
      if (field === 'request') {
        next.request_id = first.request_id
      } else if (field === 'channel') {
        next.owner_scope = 'f'.repeat(64)
        next.channel_id = first.channel_id
      } else {
        next.owner_scope = 'e'.repeat(64)
        next.source_lease_id = first.source_lease_id
      }
      expect(() => rootFor(bareEndpoint(), next)).toThrow('s03_revoked')
      expect(sender.snapshot().metadataEntries).toBe(count)
    },
  )
  it('burns the original metadata even when later clock construction fails', () => {
    const next = context()
    expect(() =>
      rootFor(bareEndpoint(), next, () => {
        throw new Error('private-canary')
      }),
    ).toThrow('s03_invalid')
    expect(() => rootFor(bareEndpoint(), next)).toThrow('s03_revoked')
  })
  it('rejects the 256th entry before reading context, joining or encoding a key', () => {
    // This is deliberately last: never reset the realm owner or erase tombstones
    // to make a later test pass. A fresh test process has its own explicit realm.
    let last = rootFor(bareEndpoint())
    last.root.close()
    while (last.sender.snapshot().metadataEntries < 255) {
      last = rootFor(bareEndpoint())
      last.root.close()
    }
    expect(last.sender.snapshot()).toMatchObject({
      metadataEntries: 255,
      metadataReserved: 261120,
      reserved: 0,
      processReserved: 261120,
    })
    expect(last.sender.snapshot().metadataBytes).toBeLessThanOrEqual(255 * 627)
    let reads = 0
    const options = Object.defineProperty({}, 'context', {
      get() {
        reads++
        throw new Error('private-canary')
      },
    })
    expect(() => SyntheticS03TestRoot.forFixture(options as never)).toThrow(
      's03_busy',
    )
    expect(reads).toBe(0)
    expect(last.sender.snapshot().metadataEntries).toBe(255)
  })
})
