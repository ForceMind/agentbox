import { readFile } from 'node:fs/promises'
import { createPrivateKey, createPublicKey } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import ts from 'typescript'
import { test, expect } from '@playwright/test'

test.use({ trace: 'off', video: 'off', screenshot: 'off' })

type VectorMessage = { payload: string; ciphertext: string }
type Vector = {
  name: string
  init_prologue: string
  init_ephemeral: string
  resp_prologue: string
  resp_static: string
  resp_ephemeral: string
  messages: VectorMessage[]
  handshake_hash: string
}

const root = resolve(fileURLToPath(new URL('../../../', import.meta.url)))
const fixturePath = resolve(
  root,
  'tests/fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json',
)
const sourcePath = resolve(root, 'apps/web/src/features/workspace/noiseNx.ts')

const X25519_PKCS8_PREFIX = Buffer.from(
  '302e020100300506032b656e04220420',
  'hex',
)

const pkcs8FromRaw = (raw: Buffer): Buffer =>
  Buffer.concat([X25519_PKCS8_PREFIX, raw])

// X25519 SPKI has a fixed 12-byte DER prefix; the final 32 bytes are the raw key.
const rawPublicFromPkcs8 = (pkcs8: Buffer): number[] => {
  const spki = createPublicKey(
    createPrivateKey({ key: pkcs8, format: 'der', type: 'pkcs8' }),
  ).export({ format: 'der', type: 'spki' }) as Buffer
  return Array.from(spki.subarray(-32))
}

const compiledCore = async (): Promise<string> => {
  const source = await readFile(sourcePath, 'utf8')
  return ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      useDefineForClassFields: true,
    },
    fileName: sourcePath,
  }).outputText
}

test('runs the fixed Noise NX vector in native browser WebCrypto', async ({
  page,
  browser,
}, testInfo) => {
  const vector = JSON.parse(await readFile(fixturePath, 'utf8')) as Vector
  const source = await compiledCore()
  const initEphemeral = pkcs8FromRaw(Buffer.from(vector.init_ephemeral, 'hex'))
  const respStatic = pkcs8FromRaw(Buffer.from(vector.resp_static, 'hex'))
  const respEphemeral = pkcs8FromRaw(Buffer.from(vector.resp_ephemeral, 'hex'))
  const keyMaterial = {
    initEphemeralPkcs8: Array.from(initEphemeral),
    initEphemeralPublic: rawPublicFromPkcs8(initEphemeral),
    respStaticPkcs8: Array.from(respStatic),
    respStaticPublic: rawPublicFromPkcs8(respStatic),
    respEphemeralPkcs8: Array.from(respEphemeral),
    respEphemeralPublic: rawPublicFromPkcs8(respEphemeral),
  }

  await page.goto('/')
  const markers = await page.evaluate(
    async ({ sourceText, vectorData, keys }) => {
      if (!window.isSecureContext || !window.crypto.subtle)
        throw new Error('native browser WebCrypto unavailable')
      const module = { exports: {} as Record<string, unknown> }
      new Function('module', 'exports', sourceText)(module, module.exports)
      const core = module.exports as {
        NXInitiator: new (
          prologue: Uint8Array,
          pair?: CryptoKeyPair,
        ) => {
          writeMessage1(payload: Uint8Array): Promise<Uint8Array>
          readMessage2(raw: Uint8Array): Promise<Uint8Array>
          takeTransport(): {
            send: {
              encrypt(payload: Uint8Array, ad?: Uint8Array): Promise<Uint8Array>
            }
            receive: {
              decrypt(
                ciphertext: Uint8Array,
                ad?: Uint8Array,
              ): Promise<Uint8Array>
            }
            handshake_hash: Uint8Array
            destroy(): void
          }
          destroy(): void
        }
        NXResponder: new (
          prologue: Uint8Array,
          staticPair: CryptoKeyPair,
          ephemeralPair?: CryptoKeyPair,
        ) => {
          readMessage1(raw: Uint8Array): Promise<Uint8Array>
          writeMessage2(payload: Uint8Array): Promise<Uint8Array>
          takeTransport(): {
            send: {
              encrypt(payload: Uint8Array, ad?: Uint8Array): Promise<Uint8Array>
            }
            receive: {
              decrypt(
                ciphertext: Uint8Array,
                ad?: Uint8Array,
              ): Promise<Uint8Array>
            }
            handshake_hash: Uint8Array
            destroy(): void
          }
          destroy(): void
        }
      }
      const bytes = (hex: string) =>
        Uint8Array.from(
          hex.match(/../g)!.map((part) => Number.parseInt(part, 16)),
        )
      const equal = (actual: Uint8Array, expected: string) => {
        if (
          Array.from(actual, (value) =>
            value.toString(16).padStart(2, '0'),
          ).join('') !== expected
        )
          throw new Error('vector mismatch')
      }
      const pair = async (pkcs8: number[], publicRaw: number[]) => ({
        privateKey: await window.crypto.subtle.importKey(
          'pkcs8',
          Uint8Array.from(pkcs8),
          { name: 'X25519' },
          false,
          ['deriveBits'],
        ),
        publicKey: await window.crypto.subtle.importKey(
          'raw',
          Uint8Array.from(publicRaw),
          { name: 'X25519' },
          true,
          [],
        ),
      })
      const initPair = await pair(
        keys.initEphemeralPkcs8,
        keys.initEphemeralPublic,
      )
      const staticPair = await pair(keys.respStaticPkcs8, keys.respStaticPublic)
      const respPair = await pair(
        keys.respEphemeralPkcs8,
        keys.respEphemeralPublic,
      )
      if (
        initPair.privateKey.extractable ||
        staticPair.privateKey.extractable ||
        respPair.privateKey.extractable
      )
        throw new Error('private key became extractable')
      if (
        !initPair.publicKey.extractable ||
        !staticPair.publicKey.extractable ||
        !respPair.publicKey.extractable
      )
        throw new Error('public key is not exportable')

      const initiator = new core.NXInitiator(
        bytes(vectorData.init_prologue),
        initPair,
      )
      const responder = new core.NXResponder(
        bytes(vectorData.resp_prologue),
        staticPair,
        respPair,
      )
      const message1 = await initiator.writeMessage1(
        bytes(vectorData.messages[0].payload),
      )
      equal(message1, vectorData.messages[0].ciphertext)
      if (
        Array.from(await responder.readMessage1(message1)).join() !==
        bytes(vectorData.messages[0].payload).join()
      )
        throw new Error('payload mismatch')
      const message2 = await responder.writeMessage2(
        bytes(vectorData.messages[1].payload),
      )
      equal(message2, vectorData.messages[1].ciphertext)
      if (
        Array.from(await initiator.readMessage2(message2)).join() !==
        bytes(vectorData.messages[1].payload).join()
      )
        throw new Error('payload mismatch')
      const left = initiator.takeTransport()
      const right = responder.takeTransport()
      equal(left.handshake_hash, vectorData.handshake_hash)
      equal(right.handshake_hash, vectorData.handshake_hash)
      for (let index = 2; index < vectorData.messages.length; index += 1) {
        const item = vectorData.messages[index]
        const payload = bytes(item.payload)
        if (index % 2 === 0) {
          const ciphertext = await left.send.encrypt(payload)
          equal(ciphertext, item.ciphertext)
          if (
            Array.from(await right.receive.decrypt(ciphertext)).join() !==
            Array.from(payload).join()
          )
            throw new Error('payload mismatch')
        } else {
          const ciphertext = await right.send.encrypt(payload)
          equal(ciphertext, item.ciphertext)
          if (
            Array.from(await left.receive.decrypt(ciphertext)).join() !==
            Array.from(payload).join()
          )
            throw new Error('payload mismatch')
        }
      }
      const ad = bytes('6167656e74626f782d6e61746976652d6164')
      const sample = bytes('7265747279')
      equal(
        await right.receive.decrypt(await left.send.encrypt(sample, ad), ad),
        '7265747279',
      )
      equal(
        await left.receive.decrypt(await right.send.encrypt(sample, ad), ad),
        '7265747279',
      )
      const valid = await left.send.encrypt(sample, ad)
      const tampered = new Uint8Array(valid)
      tampered[0] ^= 1
      await right.receive.decrypt(tampered, ad).then(
        () => {
          throw new Error('tamper accepted')
        },
        () => undefined,
      )
      await right.receive.decrypt(valid, ad).then(
        () => {
          throw new Error('retry accepted')
        },
        () => undefined,
      )
      left.destroy()
      right.destroy()
      initiator.destroy()
      responder.destroy()
      return [
        'browser-webcrypto',
        'handshake-2-messages',
        'transport-4-goldens',
        'bidirectional-associated-data',
        'tamper-retry-rejected',
      ]
    },
    { sourceText: source, vectorData: vector, keys: keyMaterial },
  )

  expect(markers).toEqual([
    'browser-webcrypto',
    'handshake-2-messages',
    'transport-4-goldens',
    'bidirectional-associated-data',
    'tamper-retry-rejected',
  ])
  expect(testInfo.project.name).toMatch(/chromium/)
  expect(await browser.version()).toBeTruthy()
  testInfo.annotations.push({
    type: 'browser-version',
    description: browser.version(),
  })
})
