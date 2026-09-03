import { afterEach, describe, expect, it, vi } from 'vitest'
import { decodeAwce, HEADER_SIZE } from './awce'
import {
  generateX25519KeyPair,
  NXInitiator,
  NXResponder,
  PROTOCOL_NAME,
} from './noiseNx'
import {
  ADMISSION_KEYS,
  CONTEXT_KEYS,
  canonicalContextBytes,
  deriveContext,
} from './wawCryptoContext'
import {
  MAX_INPUT_BYTES,
  MAX_OUTPUT_BYTES,
  WAWCryptoError,
  WAWInitiator,
  WAWResponder,
  type CryptoProfileOptions,
  type KeyFrame,
} from './wawCryptoProfile'

const A = {
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
const EPOCH = '18446744073709551615'
const bytes = (value: string) => new Uint8Array(new TextEncoder().encode(value))
const encode = (raw: Uint8Array) => Buffer.from(raw).toString('base64url')
const decode = (value: unknown) =>
  new Uint8Array(Buffer.from(value as string, 'base64url'))
const hash = async (raw: Uint8Array) =>
  Buffer.from(
    await crypto.subtle.digest('SHA-256', raw as BufferSource),
  ).toString('hex')
const channels: Array<{ destroy(): void }> = []

async function peers(options: CryptoProfileOptions = {}) {
  const key = await generateX25519KeyPair()
  const fingerprint = await hash(
    new Uint8Array(await crypto.subtle.exportKey('raw', key.publicKey)),
  )
  const browser = new WAWInitiator(A, EPOCH, fingerprint, options)
  const runtime = new WAWResponder(A, EPOCH, key, options)
  channels.push(browser, runtime)
  return { browser, runtime, key, fingerprint }
}
async function attested(options: CryptoProfileOptions = {}) {
  const pair = await peers(options)
  const init = await pair.browser.writeKeyInit()
  const attest = await pair.runtime.readKeyInit(init)
  return { ...pair, init, attest }
}
async function confirmed() {
  const pair = await attested()
  const confirm = await pair.browser.readKeyAttest(pair.attest)
  const ack = await pair.runtime.readKeyConfirm(confirm)
  return { ...pair, confirm, ack }
}
async function connected() {
  const pair = await confirmed()
  await pair.browser.readKeyConfirmAck(pair.ack)
  return pair
}
function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}
async function blockCrypto(
  method: 'encrypt' | 'decrypt' | 'digest' | 'deriveBits',
  start: () => Promise<unknown>,
  cancel: () => void,
) {
  const entered = deferred()
  const release = deferred()
  if (method === 'digest') {
    const original = crypto.subtle.digest.bind(crypto.subtle)
    vi.spyOn(crypto.subtle, 'digest').mockImplementation(
      async (algorithm, data) => {
        entered.resolve()
        await release.promise
        return original(algorithm, data)
      },
    )
  } else if (method === 'deriveBits') {
    const original = crypto.subtle.deriveBits.bind(crypto.subtle)
    vi.spyOn(crypto.subtle, 'deriveBits').mockImplementation(
      async (algorithm, key, length) => {
        entered.resolve()
        await release.promise
        return original(algorithm, key, length)
      },
    )
  } else {
    const original = crypto.subtle[method].bind(crypto.subtle)
    vi.spyOn(crypto.subtle, method).mockImplementation(
      async (algorithm, key, data) => {
        entered.resolve()
        await release.promise
        return original(algorithm, key, data)
      },
    )
  }
  const rejection = expect(start()).rejects.toBeInstanceOf(WAWCryptoError)
  await entered.promise
  try {
    cancel()
  } finally {
    release.resolve()
  }
  await rejection
}

afterEach(() => {
  vi.restoreAllMocks()
  for (const channel of channels.splice(0)) channel.destroy()
})

describe('WAW fixed Noise application profile', () => {
  it('exchanges exact key schemas, 32/128 byte NX messages, and 48 byte n=0 confirmations', async () => {
    const { browser, runtime, init, attest, confirm, ack } = await connected()
    expect(Object.keys(init).sort()).toEqual(
      [
        ...ADMISSION_KEYS,
        'protocol_version',
        'noise_protocol',
        'crypto_envelope_version',
        'runtime_epoch',
        'browser_ephemeral_public_key',
        'noise_message_1',
      ].sort(),
    )
    expect(Object.keys(attest).sort()).toEqual(
      [
        ...ADMISSION_KEYS,
        'protocol_version',
        'noise_protocol',
        'crypto_envelope_version',
        'runtime_epoch',
        'runtime_attestation_x25519_fingerprint',
        'runtime_ephemeral_public_key',
        'noise_message_2',
      ].sort(),
    )
    expect(Object.keys(confirm).sort()).toEqual(
      [
        ...CONTEXT_KEYS,
        'protocol_version',
        'noise_protocol',
        'ciphertext',
      ].sort(),
    )
    expect(Object.keys(ack).sort()).toEqual(
      [
        ...CONTEXT_KEYS,
        'protocol_version',
        'noise_protocol',
        'ciphertext',
        'status',
        'transcript_context_hash',
      ].sort(),
    )
    expect(decode(init.noise_message_1)).toHaveLength(32)
    expect(decode(attest.noise_message_2)).toHaveLength(128)
    expect(decode(confirm.ciphertext)).toHaveLength(48)
    expect(decode(ack.ciphertext)).toHaveLength(48)
    expect(browser.state).toBe('VERIFIED')
    expect(runtime.state).toBe('VERIFIED')
    expect(Object.isFrozen(confirm)).toBe(true)
    const input = await browser.encryptInput(bytes('synthetic-input'))
    expect(decodeAwce(input).crypto_sequence).toBe(1n)
    expect(await runtime.decryptInput(input)).toEqual(bytes('synthetic-input'))
    const output = await runtime.encryptOutput(
      bytes('synthetic-output'),
      9_007_199_254_740_993n,
    )
    const envelope = decodeAwce(output)
    expect(envelope.crypto_sequence).toBe(1n)
    expect(envelope.context_id).toEqual(
      new Uint8Array(
        Buffer.from(ack.transcript_context_hash as string, 'hex'),
      ).slice(0, 16),
    )
    expect(await browser.decryptOutput(output, 9_007_199_254_740_993n)).toEqual(
      bytes('synthetic-output'),
    )
    expect(
      decodeAwce(await browser.encryptInput(bytes('second'))).crypto_sequence,
    ).toBe(2n)
    expect(JSON.stringify(browser)).toBe('{"state":"VERIFIED"}')
    expect(JSON.stringify(runtime)).toBe('{"state":"VERIFIED"}')
  })

  it.each(ADMISSION_KEYS)(
    'rejects stale bound admission %s before Noise advancement',
    async (key) => {
      const { browser, runtime } = await peers()
      const init = await browser.writeKeyInit()
      const dh = vi.spyOn(crypto.subtle, 'deriveBits')
      await expect(
        runtime.readKeyInit({ ...init, [key]: 'stale' }),
      ).rejects.toThrow('STREAM_CRYPTO_FAILURE')
      expect(dh).not.toHaveBeenCalled()
      expect(runtime.state).toBe('CLOSED')
      await expect(runtime.readKeyInit(init)).rejects.toThrow(
        'STREAM_CRYPTO_FAILURE',
      )
    },
  )

  it.each(CONTEXT_KEYS)(
    'compares confirmation context %s to bound context',
    async (key) => {
      const { browser, runtime, attest } = await attested()
      const confirm = await browser.readKeyAttest(attest)
      const decrypt = vi.spyOn(crypto.subtle, 'decrypt')
      await expect(
        runtime.readKeyConfirm({ ...confirm, [key]: 'stale' }),
      ).rejects.toThrow('STREAM_CRYPTO_FAILURE')
      expect(decrypt).not.toHaveBeenCalled()
      expect(runtime.state).toBe('CLOSED')
    },
  )

  it.each([
    [
      'extra protocol_id',
      (frame: KeyFrame) => ({ ...frame, protocol_id: 'agentbox-waw/v1' }),
    ],
    [
      'missing field',
      (frame: KeyFrame) => {
        const result = { ...frame }
        delete result.mode
        return result
      },
    ],
    [
      'string version',
      (frame: KeyFrame) => ({ ...frame, protocol_version: '1' }),
    ],
    [
      'algorithm',
      (frame: KeyFrame) => ({
        ...frame,
        noise_protocol: 'Noise_XX_25519_AESGCM_SHA256',
      }),
    ],
    ['epoch', (frame: KeyFrame) => ({ ...frame, runtime_epoch: '2' })],
    ['number revision', (frame: KeyFrame) => ({ ...frame, generation: 5 })],
    [
      'base64 padding',
      (frame: KeyFrame) => ({
        ...frame,
        noise_message_1: frame.noise_message_1 + '=',
      }),
    ],
    [
      'wrong size',
      (frame: KeyFrame) => ({
        ...frame,
        noise_message_1: encode(new Uint8Array(33)),
      }),
    ],
    [
      'mismatched e',
      (frame: KeyFrame) => ({
        ...frame,
        browser_ephemeral_public_key: encode(new Uint8Array(32)),
      }),
    ],
    [
      'noncanonical trailing bits',
      (frame: KeyFrame) => {
        const raw = frame.noise_message_1 as string
        const chars =
          'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        return {
          ...frame,
          noise_message_1:
            raw.slice(0, -1) + chars[chars.indexOf(raw.at(-1)!) | 1],
        }
      },
    ],
  ] as const)('rejects KEY_INIT %s', async (_name, mutate) => {
    const { browser, runtime } = await peers()
    await expect(
      runtime.readKeyInit(mutate(await browser.writeKeyInit())),
    ).rejects.toBeInstanceOf(WAWCryptoError)
    expect(runtime.state).toBe('CLOSED')
  })

  it.each(['fingerprint', 'e', 'length', 'tag', 'extra', 'version'] as const)(
    'rejects KEY_ATTEST %s and closes both channel directions',
    async (field) => {
      const { browser, attest } = await attested()
      const bad = { ...attest }
      if (field === 'fingerprint')
        bad.runtime_attestation_x25519_fingerprint = '0'.repeat(64)
      if (field === 'e')
        bad.runtime_ephemeral_public_key = encode(new Uint8Array(32))
      if (field === 'length') bad.noise_message_2 = encode(new Uint8Array(127))
      if (field === 'tag') {
        const raw = decode(bad.noise_message_2)
        raw[127] ^= 1
        bad.noise_message_2 = encode(raw)
      }
      if (field === 'extra') bad.protocol_id = 'agentbox-waw/v1'
      if (field === 'version') bad.crypto_envelope_version = '1'
      await expect(browser.readKeyAttest(bad)).rejects.toBeInstanceOf(
        WAWCryptoError,
      )
      await expect(
        browser.encryptInput(bytes('denied')),
      ).rejects.toBeInstanceOf(WAWCryptoError)
      expect(browser.state).toBe('CLOSED')
    },
  )

  it('requires an independently supplied pin even when the frame claims that pin', async () => {
    const { runtime } = await peers()
    const browser = new WAWInitiator(A, EPOCH, 'b'.repeat(64))
    channels.push(browser)
    const attest = await runtime.readKeyInit(await browser.writeKeyInit())
    await expect(
      browser.readKeyAttest({
        ...attest,
        runtime_attestation_x25519_fingerprint: 'b'.repeat(64),
      }),
    ).rejects.toBeInstanceOf(WAWCryptoError)
    expect(browser.state).toBe('CLOSED')
  })

  it.each([
    'hash',
    'status',
    'ciphertext',
    'mode',
    'missing',
    'padding',
  ] as const)('rejects KEY_CONFIRM_ACK %s', async (field) => {
    const { browser, ack } = await confirmed()
    const bad = { ...ack }
    if (field === 'hash') bad.transcript_context_hash = '0'.repeat(64)
    if (field === 'status') bad.status = 'VERIFIED'
    if (field === 'ciphertext') {
      const raw = decode(bad.ciphertext)
      raw[47] ^= 1
      bad.ciphertext = encode(raw)
    }
    if (field === 'mode') bad.mode = 'writer'
    if (field === 'missing') delete bad.protocol_version
    if (field === 'padding') bad.ciphertext = bad.ciphertext + '='
    await expect(browser.readKeyConfirmAck(bad)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    expect(browser.state).toBe('CLOSED')
  })

  it('verifies exact ACK canary even with a valid n=0 authenticated ciphertext', async () => {
    const { browser, key, fingerprint } = await peers()
    const responder = new NXResponder(
      canonicalContextBytes(deriveContext(A, EPOCH)),
      key,
    )
    channels.push(responder)
    const init = await browser.writeKeyInit()
    await responder.readMessage1(decode(init.noise_message_1))
    const message = await responder.writeMessage2(
      crypto.getRandomValues(new Uint8Array(32)),
    )
    const transport = responder.takeTransport()
    channels.push(transport)
    await browser.readKeyAttest({
      ...A,
      protocol_version: 1,
      crypto_envelope_version: 1,
      runtime_epoch: EPOCH,
      noise_protocol: PROTOCOL_NAME,
      runtime_attestation_x25519_fingerprint: fingerprint,
      runtime_ephemeral_public_key: encode(message.slice(0, 32)),
      noise_message_2: encode(message),
    })
    const badCanary = await transport.send.encrypt(new Uint8Array(32))
    await expect(
      browser.readKeyConfirmAck({
        ...deriveContext(A, EPOCH),
        protocol_version: 1,
        noise_protocol: PROTOCOL_NAME,
        status: 'verified',
        transcript_context_hash: Buffer.from(transport.handshake_hash).toString(
          'hex',
        ),
        ciphertext: encode(badCanary),
      }),
    ).rejects.toBeInstanceOf(WAWCryptoError)
    expect(browser.state).toBe('CLOSED')
  })

  it('rejects authenticated but incorrect confirmation plaintext and uses a fresh 32-byte CSPRNG challenge', async () => {
    const { runtime } = await peers()
    const browser = new NXInitiator(
      canonicalContextBytes(deriveContext(A, EPOCH)),
    )
    channels.push(browser)
    const message = await browser.writeMessage1()
    const entropy = vi.spyOn(crypto, 'getRandomValues')
    const attest = await runtime.readKeyInit({
      ...A,
      protocol_version: 1,
      crypto_envelope_version: 1,
      runtime_epoch: EPOCH,
      noise_protocol: PROTOCOL_NAME,
      browser_ephemeral_public_key: encode(message),
      noise_message_1: encode(message),
    })
    expect(entropy).toHaveBeenCalledTimes(1)
    expect(entropy.mock.calls[0][0]).toHaveLength(32)
    expect(
      await browser.readMessage2(decode(attest.noise_message_2)),
    ).toHaveLength(32)
    const transport = browser.takeTransport()
    channels.push(transport)
    await expect(
      runtime.readKeyConfirm({
        ...deriveContext(A, EPOCH),
        protocol_version: 1,
        noise_protocol: PROTOCOL_NAME,
        ciphertext: encode(await transport.send.encrypt(new Uint8Array(32))),
      }),
    ).rejects.toBeInstanceOf(WAWCryptoError)
    expect(runtime.state).toBe('CLOSED')
    expect(await hash(bytes('agentbox-waw/noise-confirm-ack/v1'))).toBe(
      'fbb2854eb233e77bae587d1480d40192379527e27de780b24010ec97714490c3',
    )
  })

  it('blocks terminal payloads before ACK, and rejects duplicate/out-of-order key frames', async () => {
    const { browser, runtime, attest } = await attested()
    await expect(browser.encryptInput(bytes('early'))).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    await expect(browser.readKeyAttest(attest)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    await expect(runtime.readKeyInit({})).rejects.toBeInstanceOf(WAWCryptoError)
    const live = await connected()
    await expect(
      live.browser.readKeyConfirmAck(live.ack),
    ).rejects.toBeInstanceOf(WAWCryptoError)
    const fresh = await peers()
    await expect(fresh.browser.readKeyConfirmAck({})).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
  })

  it('accepts exact active chunk bounds and preserves input snapshots during async work', async () => {
    const { browser, runtime } = await connected()
    const input = new Uint8Array(MAX_INPUT_BYTES).fill(31)
    const pending = browser.encryptInput(input)
    input.fill(7)
    expect(await runtime.decryptInput(await pending)).toEqual(
      new Uint8Array(MAX_INPUT_BYTES).fill(31),
    )
    const output = new Uint8Array(MAX_OUTPUT_BYTES)
    expect(
      await browser.decryptOutput(await runtime.encryptOutput(output, 1n), 1n),
    ).toEqual(output)
  })

  it.each([0, MAX_INPUT_BYTES + 1])(
    'rejects invalid INPUT plaintext size %i',
    async (size) => {
      const { browser } = await connected()
      await expect(
        browser.encryptInput(new Uint8Array(size)),
      ).rejects.toBeInstanceOf(WAWCryptoError)
      expect(browser.state).toBe('CLOSED')
    },
  )
  it.each([0, MAX_OUTPUT_BYTES + 1])(
    'rejects invalid OUTPUT plaintext size %i',
    async (size) => {
      const { runtime } = await connected()
      await expect(
        runtime.encryptOutput(new Uint8Array(size), 1n),
      ).rejects.toBeInstanceOf(WAWCryptoError)
      expect(runtime.state).toBe('CLOSED')
    },
  )

  it.each([
    0,
    4,
    5,
    6,
    8,
    15,
    16,
    23,
    24,
    27,
    28,
    43,
    HEADER_SIZE,
    HEADER_SIZE + 16,
  ])('authenticates AWCE header, body and tag byte %i', async (offset) => {
    const { browser, runtime } = await connected()
    const packet = await runtime.encryptOutput(bytes('x'), 1n)
    packet[offset] ^= 1
    await expect(browser.decryptOutput(packet, 1n)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    expect(browser.state).toBe('CLOSED')
    await expect(browser.encryptInput(bytes('denied'))).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
  })
  it('rejects reordered and replayed sequences, wrong direction and independently wrong cursor', async () => {
    const pair = await connected()
    const first = await pair.browser.encryptInput(bytes('one'))
    const second = await pair.browser.encryptInput(bytes('two'))
    await expect(pair.runtime.decryptInput(second)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    const replay = await connected()
    const raw = await replay.browser.encryptInput(bytes('one'))
    await replay.runtime.decryptInput(raw)
    await expect(replay.runtime.decryptInput(raw)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    const direction = await connected()
    await expect(
      direction.browser.decryptOutput(first, 1n),
    ).rejects.toBeInstanceOf(WAWCryptoError)
    const cursor = await connected()
    await expect(
      cursor.browser.decryptOutput(
        await cursor.runtime.encryptOutput(bytes('one'), 2n),
        1n,
      ),
    ).rejects.toBeInstanceOf(WAWCryptoError)
  })
  it('authenticates a syntactically valid altered cursor even when it matches independent metadata', async () => {
    const { browser, runtime } = await connected()
    const packet = await runtime.encryptOutput(bytes('a'), 1n)
    new DataView(packet.buffer).setBigUint64(16, 2n, false)
    const decrypt = vi.spyOn(crypto.subtle, 'decrypt')
    await expect(browser.decryptOutput(packet, 2n)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    expect(decrypt).toHaveBeenCalledTimes(1)
  })

  it.each([null, 100_000_000, { length: 10 }, new Uint8ClampedArray(10)])(
    'rejects malformed terminal data before encryption or copying',
    async (value) => {
      const { browser } = await connected()
      const encrypt = vi.spyOn(crypto.subtle, 'encrypt')
      await expect(browser.encryptInput(value)).rejects.toBeInstanceOf(
        WAWCryptoError,
      )
      expect(encrypt).not.toHaveBeenCalled()
    },
  )
  it.each([0n, 1, -1n, 18_446_744_073_709_551_615n])(
    'rejects invalid output cursor %s',
    async (cursor) => {
      const { runtime } = await connected()
      await expect(
        runtime.encryptOutput(bytes('one'), cursor as bigint),
      ).rejects.toBeInstanceOf(WAWCryptoError)
    },
  )
  it('requires increasing ring cursors while allowing external GAP jumps', async () => {
    const { browser, runtime } = await connected()
    await browser.decryptOutput(await runtime.encryptOutput(bytes('a'), 1n), 1n)
    await browser.decryptOutput(
      await runtime.encryptOutput(bytes('b'), 20n),
      20n,
    )
    await expect(runtime.encryptOutput(bytes('c'), 20n)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
  })
  it('reconnect creates fresh transcript and keys; old ciphertext cannot cross channels', async () => {
    const previous = await connected()
    const old = await previous.browser.encryptInput(bytes('old'))
    const fresh = await connected()
    expect(previous.init.browser_ephemeral_public_key).not.toBe(
      fresh.init.browser_ephemeral_public_key,
    )
    expect(previous.ack.transcript_context_hash).not.toBe(
      fresh.ack.transcript_context_hash,
    )
    await expect(fresh.runtime.decryptInput(old)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
  })
  it('uses one shared 5 s deadline and rejects clock rollback', async () => {
    let now = 0
    const { browser, runtime } = await peers({
      now: () => now,
      admissionStartedAt: 0,
    })
    const init = await browser.writeKeyInit()
    now = 4_999
    const attest = await runtime.readKeyInit(init)
    now = 5_000
    await expect(browser.readKeyAttest(attest)).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
    expect(browser.state).toBe('CLOSED')
    now = 100
    const rollback = await peers({ now: () => now })
    now = 99
    await expect(rollback.browser.writeKeyInit()).rejects.toBeInstanceOf(
      WAWCryptoError,
    )
  })
  it('destroys an idle handshake on its deadline', async () => {
    vi.useFakeTimers()
    try {
      const { browser, runtime } = await peers({ now: () => 0 })
      await vi.advanceTimersByTimeAsync(5_000)
      expect(browser.state).toBe('CLOSED')
      expect(runtime.state).toBe('CLOSED')
    } finally {
      vi.useRealTimers()
    }
  })

  it.each(['encrypt', 'decrypt'] as const)(
    'discards late terminal %s completion after destroy',
    async (method) => {
      const { browser, runtime } = await connected()
      const output = await runtime.encryptOutput(bytes('output'), 1n)
      await blockCrypto(
        method,
        () =>
          method === 'encrypt'
            ? browser.encryptInput(bytes('input'))
            : browser.decryptOutput(output, 1n),
        () => browser.destroy(),
      )
      expect(browser.state).toBe('CLOSED')
      await expect(browser.encryptInput(bytes('late'))).rejects.toBeInstanceOf(
        WAWCryptoError,
      )
    },
  )
  it.each(['digest', 'deriveBits'] as const)(
    'discards late handshake %s completion after destroy',
    async (method) => {
      const { browser, attest } = await attested()
      await blockCrypto(
        method,
        () => browser.readKeyAttest(attest),
        () => browser.destroy(),
      )
      expect(browser.state).toBe('CLOSED')
    },
  )
  it('pending ACK crypto cannot report VERIFIED or accept premature input', async () => {
    const { browser, ack } = await confirmed()
    let premature: Promise<unknown> | undefined
    await blockCrypto(
      'decrypt',
      () => browser.readKeyConfirmAck(ack),
      () => {
        expect(browser.state).toBe('WAIT_ACK')
        premature = expect(
          browser.encryptInput(bytes('premature')),
        ).rejects.toBeInstanceOf(WAWCryptoError)
      },
    )
    await premature
    expect(browser.state).toBe('CLOSED')
  })
  it('concurrent operations fence the pending encryption, without returning either result', async () => {
    const { browser } = await connected()
    let concurrent: Promise<unknown> | undefined
    await blockCrypto(
      'encrypt',
      () => browser.encryptInput(bytes('one')),
      () => {
        concurrent = expect(
          browser.encryptInput(bytes('two')),
        ).rejects.toBeInstanceOf(WAWCryptoError)
      },
    )
    await concurrent
    expect(browser.state).toBe('CLOSED')
  })

  it.each(['browser', 'runtime'] as const)(
    'allows healthy full-duplex %s send/receive overlap',
    async (role) => {
      const { browser, runtime } = await connected()
      const incoming =
        role === 'browser'
          ? await runtime.encryptOutput(bytes('incoming'), 1n)
          : await browser.encryptInput(bytes('incoming'))
      const entered = deferred()
      const release = deferred()
      const original = crypto.subtle.encrypt.bind(crypto.subtle)
      vi.spyOn(crypto.subtle, 'encrypt').mockImplementation(
        async (algorithm, key, data) => {
          entered.resolve()
          await release.promise
          return original(algorithm, key, data)
        },
      )
      const pending =
        role === 'browser'
          ? browser.encryptInput(bytes('outgoing'))
          : runtime.encryptOutput(bytes('outgoing'), 1n)
      await entered.promise
      try {
        expect(
          await (role === 'browser'
            ? browser.decryptOutput(incoming, 1n)
            : runtime.decryptInput(incoming)),
        ).toEqual(bytes('incoming'))
        expect(browser.state).toBe('VERIFIED')
        expect(runtime.state).toBe('VERIFIED')
      } finally {
        release.resolve()
      }
      const outgoing = await pending
      expect(decodeAwce(outgoing).crypto_sequence).toBe(1n)
      expect(
        await (role === 'browser'
          ? runtime.decryptInput(outgoing)
          : browser.decryptOutput(outgoing, 1n)),
      ).toEqual(bytes('outgoing'))
    },
  )

  it.each(['encrypt', 'decrypt'] as const)(
    'a failure in the opposite direction fences pending %s',
    async (method) => {
      const { browser, runtime } = await connected()
      const output = await runtime.encryptOutput(bytes('output'), 1n)
      let failure: Promise<unknown> | undefined
      await blockCrypto(
        method,
        () =>
          method === 'encrypt'
            ? browser.encryptInput(bytes('input'))
            : browser.decryptOutput(output, 1n),
        () => {
          if (method === 'encrypt') {
            const damaged = output.slice()
            damaged[0] ^= 1
            failure = expect(
              browser.decryptOutput(damaged, 1n),
            ).rejects.toBeInstanceOf(WAWCryptoError)
          } else {
            failure = expect(
              browser.encryptInput(new Uint8Array()),
            ).rejects.toBeInstanceOf(WAWCryptoError)
          }
        },
      )
      await failure
      expect(browser.state).toBe('CLOSED')
    },
  )
})
