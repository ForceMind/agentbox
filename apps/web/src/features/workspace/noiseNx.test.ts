import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  CipherState,
  MAX_MESSAGE_SIZE,
  NoiseNXError,
  NXInitiator,
  NXResponder,
  generateX25519KeyPair,
} from './noiseNx'

const text = (value: string) => new TextEncoder().encode(value)

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

afterEach(() => vi.restoreAllMocks())

describe('Noise_NX_25519_AESGCM_SHA256', () => {
  it('completes the fixed two-message handshake and transports in both directions', async () => {
    const responderStatic = await generateX25519KeyPair()
    const initiator = new NXInitiator(text('prologue'))
    const responder = new NXResponder(text('prologue'), responderStatic)
    const message1 = await initiator.writeMessage1(text('hello'))
    expect(
      new TextDecoder().decode(await responder.readMessage1(message1)),
    ).toBe('hello')
    const message2 = await responder.writeMessage2(text('welcome'))
    expect(
      new TextDecoder().decode(await initiator.readMessage2(message2)),
    ).toBe('welcome')

    const a = initiator.takeTransport()
    const b = responder.takeTransport()
    expect(a.handshake_hash).toEqual(b.handshake_hash)
    expect(a.remote_static_public_key).toHaveLength(32)
    const outbound = await a.send.encrypt(text('from initiator'))
    expect(new TextDecoder().decode(await b.receive.decrypt(outbound))).toBe(
      'from initiator',
    )
    const inbound = await b.send.encrypt(text('from responder'))
    expect(new TextDecoder().decode(await a.receive.decrypt(inbound))).toBe(
      'from responder',
    )
  })

  it('closes a direction after tampering and rejects oversized values', async () => {
    const keyPair = await crypto.subtle.generateKey(
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt'],
    )
    const state = new CipherState(keyPair as CryptoKey)
    const ciphertext = await state.encrypt(text('secret'))
    ciphertext[0] ^= 1
    await expect(state.decrypt(ciphertext)).rejects.toBeInstanceOf(NoiseNXError)
    await expect(state.encrypt(text('again'))).rejects.toBeInstanceOf(
      NoiseNXError,
    )
    const other = new CipherState(keyPair as CryptoKey)
    await expect(
      other.encrypt(new Uint8Array(MAX_MESSAGE_SIZE + 1)),
    ).rejects.toBeInstanceOf(NoiseNXError)
  })

  it('serializes concurrent operations without reusing a nonce', async () => {
    const keyPair = await crypto.subtle.generateKey(
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt'],
    )
    const sender = new CipherState(keyPair as CryptoKey)
    const receiver = new CipherState(keyPair as CryptoKey)
    const first = sender.encrypt(text('one'))
    await expect(sender.encrypt(text('two'))).rejects.toBeInstanceOf(
      NoiseNXError,
    )
    const ciphertext = await first
    expect(sender.counter).toBe(1n)
    expect(new TextDecoder().decode(await receiver.decrypt(ciphertext))).toBe(
      'one',
    )
  })

  it('enforces handshake order without allowing a retry', async () => {
    const initiator = new NXInitiator(text('a'))
    await expect(
      initiator.readMessage2(new Uint8Array(80)),
    ).rejects.toBeInstanceOf(NoiseNXError)
    await expect(initiator.writeMessage1()).rejects.toBeInstanceOf(NoiseNXError)
  })

  it.each(['encrypt', 'decrypt'] as const)(
    'discards pending %s after destroy without advancing its counter',
    async (method) => {
      const key = await crypto.subtle.generateKey(
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt'],
      )
      const state = new CipherState(key)
      const payload =
        method === 'encrypt'
          ? text('bounded sample')
          : new Uint8Array(
              await crypto.subtle.encrypt(
                { name: 'AES-GCM', iv: new Uint8Array(12) },
                key,
                text('bounded sample'),
              ),
            )
      const entered = deferred()
      const release = deferred()
      const original = crypto.subtle[method].bind(crypto.subtle)
      vi.spyOn(crypto.subtle, method).mockImplementation(
        async (algorithm, actualKey, data) => {
          entered.resolve()
          await release.promise
          return original(algorithm, actualKey, data)
        },
      )
      const pending = state[method](payload)
      const rejected = expect(pending).rejects.toBeInstanceOf(NoiseNXError)
      try {
        await entered.promise
        state.destroy()
      } finally {
        release.resolve()
      }
      await rejected
      expect(state.counter).toBe(0n)
      await expect(state.encrypt(text('late'))).rejects.toBeInstanceOf(
        NoiseNXError,
      )
    },
  )

  it.each(['initiator', 'responder'] as const)(
    'cannot revive a destroyed %s during DH',
    async (role) => {
      const initiator = new NXInitiator(text('context'))
      const responder = new NXResponder(
        text('context'),
        await generateX25519KeyPair(),
      )
      const message1 = await initiator.writeMessage1()
      await responder.readMessage1(message1)
      const message2 =
        role === 'initiator'
          ? await responder.writeMessage2(text('challenge'))
          : undefined
      const entered = deferred()
      const release = deferred()
      const original = crypto.subtle.deriveBits.bind(crypto.subtle)
      vi.spyOn(crypto.subtle, 'deriveBits').mockImplementation(
        async (algorithm, key, length) => {
          entered.resolve()
          await release.promise
          return original(algorithm, key, length)
        },
      )
      const handshake = role === 'initiator' ? initiator : responder
      const pending = message2
        ? initiator.readMessage2(message2)
        : responder.writeMessage2(text('challenge'))
      const rejected = expect(pending).rejects.toBeInstanceOf(NoiseNXError)
      try {
        await entered.promise
        expect(() => handshake.takeTransport()).toThrow(NoiseNXError)
        handshake.destroy()
      } finally {
        release.resolve()
      }
      await rejected
      expect(() => handshake.takeTransport()).toThrow(NoiseNXError)
      await expect(
        role === 'initiator'
          ? initiator.writeMessage1()
          : responder.writeMessage2(),
      ).rejects.toBeInstanceOf(NoiseNXError)
      initiator.destroy()
      responder.destroy()
    },
  )

  it('handles destroy before the constructor digest finishes', async () => {
    const entered = deferred()
    const release = deferred()
    const original = crypto.subtle.digest.bind(crypto.subtle)
    vi.spyOn(crypto.subtle, 'digest').mockImplementation(
      async (algorithm, data) => {
        entered.resolve()
        await release.promise
        return original(algorithm, data)
      },
    )
    const handshake = new NXInitiator(text('context'))
    await entered.promise
    handshake.destroy()
    release.resolve()
    await expect(handshake.writeMessage1()).rejects.toBeInstanceOf(NoiseNXError)
    expect(() => handshake.takeTransport()).toThrow(NoiseNXError)
  })

  it.each([null, 200_000, { length: 0 }])(
    'rejects malformed handshake input before allocating or retrying: %s',
    async (value) => {
      const handshake = new NXInitiator(text('context'))
      await expect(
        handshake.writeMessage1(value as unknown as Uint8Array),
      ).rejects.toBeInstanceOf(NoiseNXError)
      await expect(handshake.writeMessage1()).rejects.toBeInstanceOf(
        NoiseNXError,
      )
    },
  )

  it('uses the exact maximum plaintext and tag boundary', async () => {
    const key = await crypto.subtle.generateKey(
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt'],
    )
    const send = new CipherState(key)
    const receive = new CipherState(key)
    const payload = new Uint8Array(MAX_MESSAGE_SIZE - 16)
    const ciphertext = await send.encrypt(payload)
    expect(ciphertext.length).toBe(MAX_MESSAGE_SIZE)
    expect(await receive.decrypt(ciphertext)).toEqual(payload)
    await expect(
      send.encrypt(new Uint8Array(MAX_MESSAGE_SIZE - 15)),
    ).rejects.toBeInstanceOf(NoiseNXError)
    await expect(send.encrypt(text('retry'))).rejects.toBeInstanceOf(
      NoiseNXError,
    )
  })

  it('closes a mismatched prologue and a low-order peer', async () => {
    const initiator = new NXInitiator(text('one'))
    const responder = new NXResponder(
      text('two'),
      await generateX25519KeyPair(),
    )
    await responder.readMessage1(await initiator.writeMessage1())
    await expect(
      initiator.readMessage2(await responder.writeMessage2()),
    ).rejects.toBeInstanceOf(NoiseNXError)
    expect(() => initiator.takeTransport()).toThrow(NoiseNXError)
    const lowOrder = new NXResponder(
      text('context'),
      await generateX25519KeyPair(),
    )
    await lowOrder.readMessage1(new Uint8Array(32))
    await expect(lowOrder.writeMessage2()).rejects.toBeInstanceOf(NoiseNXError)
    await expect(lowOrder.writeMessage2()).rejects.toBeInstanceOf(NoiseNXError)
    responder.destroy()
  })
})
