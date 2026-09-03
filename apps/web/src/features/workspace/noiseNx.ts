const PROTOCOL_NAME = 'Noise_NX_25519_AESGCM_SHA256'
const PROTOCOL_BYTES = new TextEncoder().encode(PROTOCOL_NAME)
const HASH_LEN = 32
export const MAX_MESSAGE_SIZE = 65_535
const MAX_ENCRYPT_PLAINTEXT = MAX_MESSAGE_SIZE - 16
const MAX_NONCE = 2n ** 64n - 1n

export class NoiseNXError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NoiseNXError'
  }
}

type Bytes = Uint8Array
type KeyPair = CryptoKeyPair

const validatePair = (pair: KeyPair, label: string): void => {
  if (
    !pair ||
    pair.privateKey?.algorithm.name !== 'X25519' ||
    pair.publicKey?.algorithm.name !== 'X25519' ||
    !pair.publicKey.extractable ||
    pair.privateKey.extractable ||
    !pair.privateKey.usages.includes('deriveBits')
  )
    throw new NoiseNXError(`${label} is invalid`)
}

const cryptoApi = (): Crypto => {
  if (typeof globalThis.crypto === 'undefined' || !globalThis.crypto.subtle) {
    throw new NoiseNXError('WebCrypto is unavailable')
  }
  return globalThis.crypto
}

const concat = (...parts: Bytes[]): Bytes => {
  const result = new Uint8Array(parts.reduce((n, part) => n + part.length, 0))
  let offset = 0
  for (const part of parts) {
    result.set(part, offset)
    offset += part.length
  }
  return result
}
const source = (value: Bytes): ArrayBuffer =>
  value.buffer.slice(
    value.byteOffset,
    value.byteOffset + value.byteLength,
  ) as ArrayBuffer

const nonce = (n: bigint): Bytes => {
  const value = new Uint8Array(12)
  const view = new DataView(value.buffer)
  view.setBigUint64(4, n, false)
  return value
}

const checkBytes = (
  value: Bytes,
  label: string,
  max = MAX_MESSAGE_SIZE,
): void => {
  if (
    !ArrayBuffer.isView(value) ||
    value.constructor.name !== 'Uint8Array' ||
    value.length > max
  )
    throw new NoiseNXError(`${label} is invalid`)
}
const copy = (value: Bytes): Bytes => new Uint8Array(value)

async function digest(value: Bytes): Promise<Bytes> {
  return new Uint8Array(
    await cryptoApi().subtle.digest('SHA-256', value as BufferSource),
  )
}

async function hmac(key: Bytes, data: Bytes): Promise<Bytes> {
  const imported = await cryptoApi().subtle.importKey(
    'raw',
    source(key),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  return new Uint8Array(
    await cryptoApi().subtle.sign('HMAC', imported, data as BufferSource),
  )
}

async function hkdf(ck: Bytes, material: Bytes): Promise<[Bytes, Bytes]> {
  const temp = await hmac(ck, material)
  const first = await hmac(temp, new Uint8Array([1]))
  const second = await hmac(temp, concat(first, new Uint8Array([2])))
  return [first, second]
}

async function publicKey(pair: KeyPair): Promise<Bytes> {
  try {
    return new Uint8Array(
      await cryptoApi().subtle.exportKey('raw', pair.publicKey),
    )
  } catch {
    throw new NoiseNXError('X25519 public key export failed')
  }
}

async function importPublic(raw: Bytes): Promise<CryptoKey> {
  if (raw.length !== 32) throw new NoiseNXError('X25519 public key is invalid')
  try {
    return await cryptoApi().subtle.importKey(
      'raw',
      source(raw),
      { name: 'X25519' },
      false,
      [],
    )
  } catch {
    throw new NoiseNXError('X25519 public key is invalid')
  }
}

async function dh(pair: KeyPair, peer: Bytes): Promise<Bytes> {
  const key = await importPublic(peer)
  try {
    return new Uint8Array(
      await cryptoApi().subtle.deriveBits(
        { name: 'X25519', public: key },
        pair.privateKey,
        256,
      ),
    )
  } catch {
    throw new NoiseNXError('X25519 DH failed')
  }
}

export async function generateX25519KeyPair(): Promise<KeyPair> {
  try {
    return (await cryptoApi().subtle.generateKey({ name: 'X25519' }, false, [
      'deriveBits',
    ])) as KeyPair
  } catch {
    throw new NoiseNXError('X25519 key generation failed')
  }
}

export class CipherState {
  #key?: CryptoKey
  #counter = 0n
  #closed = false
  #busy = false
  #epoch = 0

  constructor(key: CryptoKey) {
    if (
      key.algorithm.name !== 'AES-GCM' ||
      (key.algorithm as { length?: number }).length !== 256 ||
      key.extractable ||
      !key.usages.includes('encrypt') ||
      !key.usages.includes('decrypt')
    )
      throw new NoiseNXError('CipherState key is invalid')
    this.#key = key
  }

  get counter(): bigint {
    return this.#counter
  }

  async encrypt(
    plaintext: Bytes,
    ad: Bytes = new Uint8Array(),
  ): Promise<Bytes> {
    try {
      checkBytes(plaintext, 'plaintext', MAX_ENCRYPT_PLAINTEXT)
      checkBytes(ad, 'associated data')
    } catch (error) {
      this.destroy()
      return Promise.reject(error)
    }
    plaintext = copy(plaintext)
    ad = copy(ad)
    const token = this.#epoch
    return this.#serial(async () => {
      this.#ready(plaintext, ad, false)
      try {
        const result = new Uint8Array(
          await cryptoApi().subtle.encrypt(
            {
              name: 'AES-GCM',
              iv: source(nonce(this.#counter)),
              additionalData: source(ad),
              tagLength: 128,
            },
            this.#key!,
            source(plaintext),
          ),
        )
        this.#assert(token)
        this.#advance()
        return result
      } catch {
        this.#closed = true
        throw new NoiseNXError('Noise encryption failed')
      }
    })
  }

  async decrypt(
    ciphertext: Bytes,
    ad: Bytes = new Uint8Array(),
  ): Promise<Bytes> {
    try {
      checkBytes(ciphertext, 'ciphertext')
      checkBytes(ad, 'associated data')
    } catch (error) {
      this.destroy()
      return Promise.reject(error)
    }
    if (ciphertext.length < 16) {
      this.destroy()
      return Promise.reject(new NoiseNXError('ciphertext is invalid'))
    }
    ciphertext = copy(ciphertext)
    ad = copy(ad)
    const token = this.#epoch
    return this.#serial(async () => {
      this.#ready(ciphertext, ad, true)
      try {
        const result = new Uint8Array(
          await cryptoApi().subtle.decrypt(
            {
              name: 'AES-GCM',
              iv: source(nonce(this.#counter)),
              additionalData: source(ad),
              tagLength: 128,
            },
            this.#key!,
            source(ciphertext),
          ),
        )
        this.#assert(token)
        this.#advance()
        return result
      } catch {
        this.#closed = true
        throw new NoiseNXError('Noise authentication failed')
      }
    })
  }

  destroy(): void {
    this.#closed = true
    this.#epoch += 1
    this.#key = undefined
  }

  #assert(token: number): void {
    if (this.#closed || this.#epoch !== token)
      throw new NoiseNXError('CipherState is closed')
  }

  #ready(value: Bytes, ad: Bytes, decrypt: boolean): void {
    if (this.#closed || !this.#key)
      throw new NoiseNXError('CipherState is closed')
    checkBytes(
      value,
      decrypt ? 'ciphertext' : 'plaintext',
      decrypt ? MAX_MESSAGE_SIZE : MAX_ENCRYPT_PLAINTEXT,
    )
    checkBytes(ad, 'associated data')
    if (this.#counter >= MAX_NONCE) {
      this.#closed = true
      throw new NoiseNXError('Noise nonce exhausted')
    }
  }
  #advance(): void {
    this.#counter += 1n
  }
  #serial<T>(operation: () => Promise<T>): Promise<T> {
    if (this.#busy || this.#closed)
      return Promise.reject(new NoiseNXError('CipherState is busy or closed'))
    this.#busy = true
    return operation()
      .catch((error) => {
        this.destroy()
        throw error instanceof NoiseNXError
          ? error
          : new NoiseNXError('Noise operation failed')
      })
      .finally(() => {
        this.#busy = false
      })
  }
}

export interface NoiseTransport {
  readonly send: CipherState
  readonly receive: CipherState
  readonly handshake_hash: Bytes
  readonly remote_static_public_key: Bytes
  destroy(): void
}

class Handshake {
  #h: Bytes
  #ck: Bytes
  #cipher?: CipherState
  #closed = false
  #transport?: NoiseTransport
  #ready: Promise<void>
  #busy = false
  #epoch = 0

  constructor(prologue: Bytes) {
    checkBytes(prologue, 'prologue')
    this.#h = new Uint8Array(HASH_LEN)
    this.#h.set(PROTOCOL_BYTES)
    this.#ck = this.#h
    this.#ready = this.mixHash(prologue)
    // Construction starts one digest. Observe rejection even if a caller
    // destroys the object before its first operation; serial still awaits the
    // original promise and reports the bounded failure to that caller.
    void this.#ready.catch(() => this.destroy())
  }

  protected get closed(): boolean {
    return this.#closed
  }
  protected operationToken(): number {
    return this.#epoch
  }
  protected guard(token: number): void {
    if (this.#closed || token !== this.#epoch)
      throw new NoiseNXError('Noise handshake is closed')
  }
  protected async serial<T>(operation: () => Promise<T>): Promise<T> {
    if (this.#busy || this.#closed)
      return Promise.reject(
        new NoiseNXError('Noise handshake is busy or closed'),
      )
    this.#busy = true
    const token = this.#epoch
    return this.#ready
      .then(() => {
        if (this.#closed) throw new NoiseNXError('Noise handshake is closed')
        return operation()
      })
      .then((result) => {
        this.guard(token)
        return result
      })
      .catch((error) => {
        this.destroy()
        throw error instanceof NoiseNXError
          ? error
          : new NoiseNXError('Noise handshake failed')
      })
      .finally(() => {
        this.#busy = false
      })
  }
  protected async mixHash(data: Bytes): Promise<void> {
    const token = this.#epoch
    const result = await digest(concat(this.#h, data))
    this.guard(token)
    this.#h = result
  }
  protected async mixKey(material: Bytes): Promise<void> {
    const token = this.#epoch
    const [ck, key] = await hkdf(this.#ck, material)
    this.guard(token)
    const next = new CipherState(
      await cryptoApi().subtle.importKey(
        'raw',
        source(key),
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt'],
      ),
    )
    try {
      this.guard(token)
    } catch (error) {
      next.destroy()
      throw error
    }
    this.#ck = ck
    this.#cipher?.destroy()
    this.#cipher = next
  }
  protected async encryptHash(data: Bytes): Promise<Bytes> {
    const result = this.#cipher
      ? await this.#cipher.encrypt(data, this.#h)
      : data
    await this.mixHash(result)
    return result
  }
  protected async decryptHash(data: Bytes): Promise<Bytes> {
    const result = this.#cipher
      ? await this.#cipher.decrypt(data, this.#h)
      : data
    await this.mixHash(data)
    return result
  }
  protected check(raw: Bytes): void {
    if (this.#closed) throw new NoiseNXError('Noise handshake is closed')
    checkBytes(raw, 'handshake message')
  }
  protected snapshot(raw: Bytes, maximum = MAX_MESSAGE_SIZE): Bytes {
    try {
      checkBytes(raw, 'handshake message', maximum)
    } catch (error) {
      this.destroy()
      throw error
    }
    return copy(raw)
  }
  protected async finish(remote: Bytes, initiator: boolean): Promise<void> {
    const token = this.#epoch
    const [first, second] = await hkdf(this.#ck, new Uint8Array())
    this.guard(token)
    const make = async (key: Bytes): Promise<CipherState> =>
      new CipherState(
        await cryptoApi().subtle.importKey(
          'raw',
          source(key),
          { name: 'AES-GCM', length: 256 },
          false,
          ['encrypt', 'decrypt'],
        ),
      )
    const send = await make(initiator ? first : second)
    let receive: CipherState
    try {
      this.guard(token)
      receive = await make(initiator ? second : first)
      try {
        this.guard(token)
      } catch (error) {
        receive.destroy()
        throw error
      }
    } catch (error) {
      send.destroy()
      throw error
    }
    const hash = new Uint8Array(this.#h)
    this.#transport = {
      send,
      receive,
      handshake_hash: hash,
      remote_static_public_key: new Uint8Array(remote),
      destroy() {
        send.destroy()
        receive.destroy()
      },
    }
  }
  takeTransport(): NoiseTransport {
    if (this.#busy || this.#closed || !this.#transport)
      throw new NoiseNXError('Noise transport is unavailable')
    const value = this.#transport
    this.#transport = undefined
    this.#closed = true
    this.#cipher?.destroy()
    this.#cipher = undefined
    this.#h = new Uint8Array()
    this.#ck = new Uint8Array()
    return value
  }
  destroy(): void {
    this.#closed = true
    this.#epoch += 1
    this.#cipher?.destroy()
    this.#cipher = undefined
    this.#transport?.destroy()
    this.#transport = undefined
    this.#h = new Uint8Array()
    this.#ck = new Uint8Array()
  }
}

export class NXInitiator extends Handshake {
  #e?: KeyPair
  #re?: Bytes
  #message1Written = false
  constructor(prologue: Bytes, ephemeralKeyPair?: KeyPair) {
    super(prologue)
    if (ephemeralKeyPair) validatePair(ephemeralKeyPair, 'ephemeral key pair')
    this.#e = ephemeralKeyPair ? { ...ephemeralKeyPair } : undefined
  }
  async writeMessage1(payload: Bytes = new Uint8Array()): Promise<Bytes> {
    payload = this.snapshot(payload, MAX_MESSAGE_SIZE - 32)
    return this.serial(async () => {
      if (this.#message1Written || this.#re)
        throw new NoiseNXError('message1 is not writable')
      checkBytes(payload, 'payload', MAX_MESSAGE_SIZE - 32)
      this.#e ??= await generateX25519KeyPair()
      const pub = await publicKey(this.#e)
      await this.mixHash(pub)
      await this.mixHash(payload)
      this.#message1Written = true
      return concat(pub, payload)
    })
  }
  async readMessage2(raw: Bytes): Promise<Bytes> {
    raw = this.snapshot(raw)
    return this.serial(async () => {
      this.check(raw)
      if (!this.#message1Written || this.#re || !this.#e || raw.length < 96)
        throw new NoiseNXError('message2 is invalid or out of order')
      this.#re = raw.slice(0, 32)
      await this.mixHash(this.#re)
      await this.mixKey(await dh(this.#e, this.#re))
      const remote = await this.decryptHash(raw.slice(32, 80))
      if (remote.length !== 32)
        throw new NoiseNXError('responder static key is invalid')
      await this.mixKey(await dh(this.#e, remote))
      const payload = await this.decryptHash(raw.slice(80))
      await this.finish(remote, true)
      this.#e = undefined
      return payload
    })
  }
  destroy(): void {
    this.#e = undefined
    this.#re = undefined
    super.destroy()
  }
}

export class NXResponder extends Handshake {
  #s?: KeyPair
  #e?: KeyPair
  #re?: Bytes
  #message1Read = false
  constructor(
    prologue: Bytes,
    staticKeyPair: KeyPair,
    ephemeralKeyPair?: KeyPair,
  ) {
    super(prologue)
    validatePair(staticKeyPair, 'static key pair')
    if (ephemeralKeyPair) validatePair(ephemeralKeyPair, 'ephemeral key pair')
    this.#s = { ...staticKeyPair }
    this.#e = ephemeralKeyPair ? { ...ephemeralKeyPair } : undefined
  }
  async readMessage1(raw: Bytes): Promise<Bytes> {
    raw = this.snapshot(raw)
    return this.serial(async () => {
      this.check(raw)
      if (this.#message1Read || this.#re || raw.length < 32)
        throw new NoiseNXError('message1 is invalid or out of order')
      this.#re = raw.slice(0, 32)
      await this.mixHash(this.#re)
      const payload = raw.slice(32)
      await this.mixHash(payload)
      this.#message1Read = true
      return payload
    })
  }
  async writeMessage2(payload: Bytes = new Uint8Array()): Promise<Bytes> {
    payload = this.snapshot(payload, MAX_MESSAGE_SIZE - 96)
    return this.serial(async () => {
      if (!this.#message1Read || !this.#re || !this.#s)
        throw new NoiseNXError('message2 is not writable')
      checkBytes(payload, 'payload', MAX_MESSAGE_SIZE - 96)
      this.#e ??= await generateX25519KeyPair()
      const ep = await publicKey(this.#e)
      await this.mixHash(ep)
      await this.mixKey(await dh(this.#e, this.#re))
      const sp = await publicKey(this.#s)
      const encrypted = await this.encryptHash(sp)
      await this.mixKey(await dh(this.#s, this.#re))
      const encryptedPayload = await this.encryptHash(payload)
      await this.finish(new Uint8Array(), false)
      this.#e = undefined
      this.#s = undefined
      return concat(ep, encrypted, encryptedPayload)
    })
  }
  destroy(): void {
    this.#e = undefined
    this.#s = undefined
    this.#re = undefined
    super.destroy()
  }
}

export { PROTOCOL_NAME }
