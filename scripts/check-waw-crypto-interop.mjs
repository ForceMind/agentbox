// Real Python/WebCrypto application peers checked against an independent public vector.
// Product code is unchanged; only this disposable test process uses fixed public entropy.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createPrivateKey, createPublicKey, webcrypto } from 'node:crypto'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const requireWeb = createRequire(join(root, 'apps/web/package.json'))
let ts
let vector
let keys
const bytes = (value) => new Uint8Array(Buffer.from(value, 'hex'))
const hex = (value) => Buffer.from(value).toString('hex')
const decodedHex = (value) => Buffer.from(value, 'base64url').toString('hex')
const sample = (length) => Uint8Array.from({ length }, (_, i) => (i * 31 + 17) & 255)
const limit = 200_000
const nativeCrypto = Object.getOwnPropertyDescriptor(globalThis, 'crypto')

async function keyPair(rawHex) {
  const pkcs8 = Buffer.concat([
    Buffer.from('302e020100300506032b656e04220420', 'hex'), Buffer.from(rawHex, 'hex'),
  ])
  const object = createPrivateKey({ key: pkcs8, format: 'der', type: 'pkcs8' })
  const spki = createPublicKey(object).export({ format: 'der', type: 'spki' })
  return {
    privateKey: await webcrypto.subtle.importKey('pkcs8', pkcs8, { name: 'X25519' }, false, ['deriveBits']),
    publicKey: await webcrypto.subtle.importKey('raw', spki.subarray(-32), { name: 'X25519' }, true, []),
  }
}

class Peer {
  constructor() {
    this.child = spawn(process.env.AGENTBOX_WAW_CRYPTO_TEST_PYTHON ?? 'python3', [join(root, 'tests/interop/waw_crypto_peer.py')], {
      cwd: root, stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.buffer = ''
    this.pending = undefined
    this.dead = false
    this.child.stdout.setEncoding('utf8')
    this.child.stdout.on('data', (chunk) => this.receive(chunk))
    this.child.stderr.on('data', () => {})
    this.child.stdin.on('error', () => this.fail())
    this.child.on('error', () => this.fail())
    this.child.on('exit', () => this.fail())
  }
  receive(chunk) {
    this.buffer += chunk
    if (this.buffer.length > limit) return this.fail()
    const newline = this.buffer.indexOf('\n')
    if (newline < 0) return
    if (!this.pending || newline !== this.buffer.length - 1) return this.fail()
    const pending = this.pending
    this.pending = undefined
    clearTimeout(pending.timer)
    try {
      const response = JSON.parse(this.buffer.slice(0, newline))
      this.buffer = ''
      pending.resolve(response)
    } catch {
      pending.reject(new Error('bounded WAW response invalid'))
      this.fail()
    }
  }
  fail() {
    this.dead = true
    if (this.pending) {
      clearTimeout(this.pending.timer)
      this.pending.reject(new Error('WAW test peer unavailable'))
      this.pending = undefined
    }
    this.child.kill()
  }
  request(value) {
    assert.equal(this.pending, undefined)
    assert.equal(this.dead, false)
    const request = JSON.stringify(value)
    assert.ok(Buffer.byteLength(request) < limit)
    return new Promise((resolveRequest, reject) => {
      this.pending = { resolve: resolveRequest, reject, timer: setTimeout(() => this.fail(), 5_000) }
      this.child.stdin.write(`${request}\n`)
    })
  }
  close() { this.child.stdin.end(); this.fail() }
}

async function exchange(core, context, nodeRole) {
  const isBrowser = nodeRole === 'browser'
  const peer = new Peer()
  let profile
  try {
    const initialized = await peer.request({ action: 'init', role: isBrowser ? 'runtime' : 'browser' })
    assert.equal(initialized.ok, true)
    assert.equal(initialized.context, vector.canonical_context_utf8)
    const canonical = context.canonicalContextBytes(context.deriveContext(vector.admission, vector.runtime_epoch))
    assert.equal(new TextDecoder().decode(canonical), vector.canonical_context_utf8)
    assert.equal(hex(new Uint8Array(await webcrypto.subtle.digest('SHA-256', canonical))), vector.canonical_context_sha256)
    const options = { ephemeralKeyPair: await keyPair(isBrowser ? keys.init_ephemeral : keys.resp_ephemeral) }
    profile = isBrowser
      ? new core.WAWInitiator(vector.admission, vector.runtime_epoch, vector.runtime_fingerprint, options)
      : new core.WAWResponder(vector.admission, vector.runtime_epoch, await keyPair(keys.resp_static), options)
    let init, attest, confirm, ack
    if (isBrowser) {
      init = await profile.writeKeyInit()
      const response = await peer.request({ action: 'hello', frame: init })
      assert.equal(response.ok, true)
      attest = response.frame
      confirm = await profile.readKeyAttest(attest)
      const confirmed = await peer.request({ action: 'confirm', frame: confirm })
      assert.equal(confirmed.ok, true)
      ack = confirmed.frame
      await profile.readKeyConfirmAck(ack)
    } else {
      const started = await peer.request({ action: 'start' })
      assert.equal(started.ok, true)
      init = started.frame
      attest = await profile.readKeyInit(init)
      const response = await peer.request({ action: 'attest', frame: attest })
      assert.equal(response.ok, true)
      confirm = response.frame
      ack = await profile.readKeyConfirm(confirm)
      assert.equal((await peer.request({ action: 'ack', frame: ack })).ok, true)
    }
    assert.equal(decodedHex(init.noise_message_1), vector.noise_message_1)
    assert.equal(decodedHex(init.browser_ephemeral_public_key), vector.noise_message_1)
    assert.equal(decodedHex(attest.noise_message_2), vector.noise_message_2)
    assert.equal(decodedHex(attest.runtime_ephemeral_public_key), vector.noise_message_2.slice(0, 64))
    assert.equal(decodedHex(confirm.ciphertext), vector.key_confirm_ciphertext)
    assert.equal(decodedHex(ack.ciphertext), vector.key_confirm_ack_ciphertext)
    assert.equal(ack.transcript_context_hash, vector.transcript_context_hash)
    assert.equal(profile.state, 'VERIFIED')
    const status = await peer.request({ action: 'status' })
    assert.deepEqual(status, { ok: true, closed: false, ready: true, hash: vector.transcript_context_hash, context_id: vector.context_id })

    let outputCursor = BigInt(vector.output_cursor)
    const ownPayload = bytes(isBrowser ? vector.input_plaintext : vector.output_plaintext)
    const otherPayload = bytes(isBrowser ? vector.output_plaintext : vector.input_plaintext)
    const encrypt = (payload) => isBrowser ? profile.encryptInput(payload) : profile.encryptOutput(payload, outputCursor)
    const decrypt = (raw) => isBrowser ? profile.decryptOutput(raw, outputCursor) : profile.decryptInput(raw)
    const first = await encrypt(ownPayload)
    assert.equal(hex(first), isBrowser ? vector.input_awce : vector.output_awce)
    assert.deepEqual(await peer.request({ action: 'decrypt', ciphertext: hex(first), cursor: outputCursor.toString() }), { ok: true, plaintext: hex(ownPayload) })
    const firstIncoming = await peer.request({ action: 'encrypt', plaintext: hex(otherPayload), cursor: outputCursor.toString() })
    assert.equal(firstIncoming.ok, true)
    assert.equal(firstIncoming.ciphertext, isBrowser ? vector.output_awce : vector.input_awce)
    assert.equal(hex(await decrypt(bytes(firstIncoming.ciphertext))), hex(otherPayload))

    for (const maximum of [false, true]) {
      outputCursor++
      const outbound = sample(maximum ? (isBrowser ? 16_384 : 32_768) : 1)
      const inbound = sample(maximum ? (isBrowser ? 32_768 : 16_384) : 1)
      const sealed = await encrypt(outbound)
      assert.deepEqual(await peer.request({ action: 'decrypt', ciphertext: hex(sealed), cursor: outputCursor.toString() }), { ok: true, plaintext: hex(outbound) })
      const incoming = await peer.request({ action: 'encrypt', plaintext: hex(inbound), cursor: outputCursor.toString() })
      assert.equal(incoming.ok, true)
      assert.equal(hex(await decrypt(bytes(incoming.ciphertext))), hex(inbound))
    }

    outputCursor++
    const validOutgoing = await encrypt(ownPayload)
    const incoming = await peer.request({ action: 'encrypt', plaintext: hex(otherPayload), cursor: outputCursor.toString() })
    assert.equal(incoming.ok, true)
    const validIncoming = bytes(incoming.ciphertext)
    const badOutgoing = validOutgoing.slice()
    const badIncoming = validIncoming.slice()
    badOutgoing[badOutgoing.length - 1] ^= 1
    badIncoming[badIncoming.length - 1] ^= 1
    assert.deepEqual(await peer.request({ action: 'decrypt', ciphertext: hex(badOutgoing), cursor: outputCursor.toString() }), { ok: false, closed: true })
    assert.deepEqual(await peer.request({ action: 'decrypt', ciphertext: hex(validOutgoing), cursor: outputCursor.toString() }), { ok: false, closed: true })
    assert.deepEqual(await peer.request({ action: 'encrypt', plaintext: hex(otherPayload), cursor: (++outputCursor).toString() }), { ok: false, closed: true })
    outputCursor--
    await assert.rejects(decrypt(badIncoming), core.WAWCryptoError)
    await assert.rejects(decrypt(validIncoming), core.WAWCryptoError)
    await assert.rejects(encrypt(ownPayload), core.WAWCryptoError)
    assert.equal(profile.state, 'CLOSED')
  } finally {
    profile?.destroy()
    peer.close()
  }
}

let temporary
try {
  ts = requireWeb('typescript')
  vector = JSON.parse(await readFile(join(root, 'tests/fixtures/waw_crypto/profile-v1.json'), 'utf8'))
  keys = JSON.parse(await readFile(join(root, 'tests/fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json'), 'utf8'))
  temporary = await mkdtemp(join(tmpdir(), 'agentbox-waw-crypto-interop-'))
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: {
    subtle: webcrypto.subtle,
    getRandomValues(target) {
      assert.ok(target instanceof Uint8Array && target.length === 32)
      target.set(bytes(vector.challenge))
      return target
    },
  } })
  for (const name of ['noiseNx', 'awce', 'wawCryptoContext', 'wawCryptoProfile']) {
    const source = await readFile(join(root, `apps/web/src/features/workspace/${name}.ts`), 'utf8')
    const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
      .replace(/(from\s+['"])(\.\/(?:noiseNx|awce|wawCryptoContext))(['"])/g, '$1$2.mjs$3')
    await writeFile(join(temporary, `${name}.mjs`), compiled)
  }
  const core = await import(pathToFileURL(join(temporary, 'wawCryptoProfile.mjs')).href)
  const context = await import(pathToFileURL(join(temporary, 'wawCryptoContext.mjs')).href)
  await exchange(core, context, 'browser')
  await exchange(core, context, 'runtime')
  process.stdout.write('WAW crypto interop PASS: both roles, independent complete vector, bidirectional payloads, bounds, tamper/retry fences\n')
} catch {
  process.stderr.write('WAW crypto interop FAILED (public payloads and key inputs omitted)\n')
  process.exitCode = 1
} finally {
  if (nativeCrypto) Object.defineProperty(globalThis, 'crypto', nativeCrypto)
  else delete globalThis.crypto
  if (temporary) await rm(temporary, { recursive: true, force: true })
}
