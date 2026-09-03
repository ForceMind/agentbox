import { createPrivateKey, createPublicKey } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { expect, test } from '@playwright/test'

test.use({ trace: 'off', video: 'off', screenshot: 'off' })

const root = resolve(fileURLToPath(new URL('../../../', import.meta.url)))
const names = [
  'awce',
  'noiseNx',
  'wawCryptoContext',
  'wawCryptoProfile',
] as const
type Vector = {
  admission: Record<string, string>
  runtime_epoch: string
  runtime_fingerprint: string
  canonical_context_utf8: string
  challenge: string
  noise_message_1: string
  noise_message_2: string
  key_confirm_ciphertext: string
  key_confirm_ack_ciphertext: string
  transcript_context_hash: string
  input_plaintext: string
  output_plaintext: string
  input_awce: string
  output_awce: string
  output_cursor: string
}

function publicTestPair(rawHex: string) {
  const privateDer = Buffer.concat([
    Buffer.from('302e020100300506032b656e04220420', 'hex'),
    Buffer.from(rawHex, 'hex'),
  ])
  const publicDer = createPublicKey(
    createPrivateKey({ key: privateDer, format: 'der', type: 'pkcs8' }),
  ).export({ format: 'der', type: 'spki' })
  return {
    privateDer: Array.from(privateDer),
    publicRaw: Array.from(publicDer.subarray(-32)),
  }
}

test('verifies the WAW application vector and duplex fences in native WebCrypto', async ({
  page,
}) => {
  const vector = JSON.parse(
    await readFile(
      resolve(root, 'tests/fixtures/waw_crypto/profile-v1.json'),
      'utf8',
    ),
  ) as Vector
  const publicKeys = JSON.parse(
    await readFile(
      resolve(root, 'tests/fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json'),
      'utf8',
    ),
  ) as { init_ephemeral: string; resp_ephemeral: string; resp_static: string }
  const sources: Record<string, string> = {}
  for (const name of names) {
    const source = await readFile(
      resolve(root, `apps/web/src/features/workspace/${name}.ts`),
      'utf8',
    )
    sources[name] = ts.transpileModule(source, {
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.CommonJS,
      },
    }).outputText
  }
  const keys = {
    browser: publicTestPair(publicKeys.init_ephemeral),
    runtime: publicTestPair(publicKeys.resp_ephemeral),
    static: publicTestPair(publicKeys.resp_static),
  }
  await page.goto('/')
  const result = await page.evaluate(
    async ({ sources, vector, keys }) => {
      const loaded = new Map<string, Record<string, unknown>>()
      const load = (specifier: string): Record<string, unknown> => {
        const name = specifier.replace(/^\.\//, '')
        if (!Object.prototype.hasOwnProperty.call(sources, name))
          throw new Error('unknown test module')
        if (loaded.has(name)) return loaded.get(name)!
        const module = { exports: {} }
        loaded.set(name, module.exports)
        new Function('module', 'exports', 'require', sources[name])(
          module,
          module.exports,
          load,
        )
        return module.exports
      }
      type Frame = Readonly<Record<string, string | number>>
      type Endpoint = { state: string; destroy(): void }
      type BrowserEndpoint = Endpoint & {
        writeKeyInit(): Promise<Frame>
        readKeyAttest(frame: unknown): Promise<Frame>
        readKeyConfirmAck(frame: unknown): Promise<void>
        encryptInput(bytes: Uint8Array): Promise<Uint8Array>
        decryptOutput(bytes: Uint8Array, cursor: bigint): Promise<Uint8Array>
      }
      type RuntimeEndpoint = Endpoint & {
        readKeyInit(frame: unknown): Promise<Frame>
        readKeyConfirm(frame: unknown): Promise<Frame>
        decryptInput(bytes: Uint8Array): Promise<Uint8Array>
        encryptOutput(bytes: Uint8Array, cursor: bigint): Promise<Uint8Array>
      }
      type Options = { ephemeralKeyPair: CryptoKeyPair }
      // Dynamic module boundary only; app source is separately typechecked.
      const core = load('wawCryptoProfile') as {
        WAWInitiator: new (
          admission: unknown,
          epoch: unknown,
          pin: string,
          options: Options,
        ) => BrowserEndpoint
        WAWResponder: new (
          admission: unknown,
          epoch: unknown,
          key: CryptoKeyPair,
          options: Options,
        ) => RuntimeEndpoint
      }
      const context = load('wawCryptoContext') as {
        deriveContext(
          admission: unknown,
          epoch: unknown,
        ): Record<string, string | number>
        canonicalContextBytes(context: unknown): Uint8Array
      }
      const bytes = (value: string) =>
        Uint8Array.from(
          value.match(/../g)!.map((part) => Number.parseInt(part, 16)),
        )
      const hex = (value: Uint8Array) =>
        Array.from(value, (byte) => byte.toString(16).padStart(2, '0')).join('')
      const decodedHex = (value: string) =>
        hex(
          Uint8Array.from(
            atob(value.replace(/-/g, '+').replace(/_/g, '/')),
            (c) => c.charCodeAt(0),
          ),
        )
      const check = (value: boolean) => {
        if (!value) throw new Error('public vector mismatch')
      }
      const pair = async (value: {
        privateDer: number[]
        publicRaw: number[]
      }) => ({
        privateKey: await crypto.subtle.importKey(
          'pkcs8',
          new Uint8Array(value.privateDer),
          { name: 'X25519' },
          false,
          ['deriveBits'],
        ),
        publicKey: await crypto.subtle.importKey(
          'raw',
          new Uint8Array(value.publicRaw),
          { name: 'X25519' },
          true,
          [],
        ),
      })
      const priorRandom = Object.getOwnPropertyDescriptor(
        crypto,
        'getRandomValues',
      )
      let browser: InstanceType<typeof core.WAWInitiator> | undefined
      let runtime: InstanceType<typeof core.WAWResponder> | undefined
      try {
        check(window.isSecureContext)
        // Public fixed challenge for this test only; all AES/DH/hash is native.
        Object.defineProperty(crypto, 'getRandomValues', {
          configurable: true,
          value(target: Uint8Array) {
            check(target.length === 32)
            target.set(bytes(vector.challenge))
            return target
          },
        })
        const browserPair = await pair(keys.browser)
        const runtimePair = await pair(keys.runtime)
        const staticPair = await pair(keys.static)
        check(
          !browserPair.privateKey.extractable &&
            !runtimePair.privateKey.extractable &&
            !staticPair.privateKey.extractable,
        )
        browser = new core.WAWInitiator(
          vector.admission,
          vector.runtime_epoch,
          vector.runtime_fingerprint,
          { ephemeralKeyPair: browserPair },
        )
        runtime = new core.WAWResponder(
          vector.admission,
          vector.runtime_epoch,
          staticPair,
          { ephemeralKeyPair: runtimePair },
        )
        check(
          new TextDecoder().decode(
            context.canonicalContextBytes(
              context.deriveContext(vector.admission, vector.runtime_epoch),
            ),
          ) === vector.canonical_context_utf8,
        )
        const init = await browser.writeKeyInit()
        const attest = await runtime.readKeyInit(init)
        const confirm = await browser.readKeyAttest(attest)
        const ack = await runtime.readKeyConfirm(confirm)
        await browser.readKeyConfirmAck(ack)
        check(
          decodedHex(String(init.noise_message_1)) === vector.noise_message_1,
        )
        check(
          decodedHex(String(attest.noise_message_2)) === vector.noise_message_2,
        )
        check(
          decodedHex(String(confirm.ciphertext)) ===
            vector.key_confirm_ciphertext,
        )
        check(
          decodedHex(String(ack.ciphertext)) ===
            vector.key_confirm_ack_ciphertext,
        )
        check(ack.transcript_context_hash === vector.transcript_context_hash)
        const cursor = BigInt(vector.output_cursor)
        const input = bytes(vector.input_plaintext)
        const output = bytes(vector.output_plaintext)
        const firstInput = await browser.encryptInput(input)
        const firstOutput = await runtime.encryptOutput(output, cursor)
        check(
          hex(firstInput) === vector.input_awce &&
            hex(firstOutput) === vector.output_awce,
        )
        const [secondInput, rendered] = await Promise.all([
          browser.encryptInput(input),
          browser.decryptOutput(firstOutput, cursor),
        ])
        const [secondOutput, received] = await Promise.all([
          runtime.encryptOutput(output, cursor + BigInt(1)),
          runtime.decryptInput(firstInput),
        ])
        check(
          hex(rendered) === vector.output_plaintext &&
            hex(received) === vector.input_plaintext,
        )
        check(
          hex(await runtime.decryptInput(secondInput)) ===
            vector.input_plaintext,
        )
        check(
          hex(await browser.decryptOutput(secondOutput, cursor + BigInt(1))) ===
            vector.output_plaintext,
        )
        const validInput = await browser.encryptInput(input)
        const validOutput = await runtime.encryptOutput(
          output,
          cursor + BigInt(2),
        )
        const corruptInput = validInput.slice()
        const corruptOutput = validOutput.slice()
        corruptInput[corruptInput.length - 1] ^= 1
        corruptOutput[corruptOutput.length - 1] ^= 1
        const rejected = async (operation: () => Promise<unknown>) => {
          try {
            await operation()
            return false
          } catch {
            return true
          }
        }
        check(await rejected(() => runtime!.decryptInput(corruptInput)))
        check(await rejected(() => runtime!.decryptInput(validInput)))
        check(
          await rejected(() =>
            runtime!.encryptOutput(output, cursor + BigInt(3)),
          ),
        )
        check(
          await rejected(() =>
            browser!.decryptOutput(corruptOutput, cursor + BigInt(2)),
          ),
        )
        check(
          await rejected(() =>
            browser!.decryptOutput(validOutput, cursor + BigInt(2)),
          ),
        )
        check(await rejected(() => browser!.encryptInput(input)))
        return {
          verified: true,
          duplex: true,
          closed: browser.state === 'CLOSED' && runtime.state === 'CLOSED',
        }
      } catch {
        return { verified: false, duplex: false, closed: false }
      } finally {
        browser?.destroy()
        runtime?.destroy()
        if (priorRandom)
          Object.defineProperty(crypto, 'getRandomValues', priorRandom)
        else Reflect.deleteProperty(crypto, 'getRandomValues')
      }
    },
    { sources, vector, keys },
  )
  expect(result).toEqual({ verified: true, duplex: true, closed: true })
})
