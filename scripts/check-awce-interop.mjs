// Verify the strict opaque AWCE v1 codec against an independent Python peer.
// Test bytes are synthetic opaque payloads; no cryptography, keys, or claims occur here.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const requireWeb = createRequire(join(root, 'apps/web/package.json'))
const ts = requireWeb('typescript')
const limit = 200_000
const fixedVector =
  '41574345010100000000000000000001000000000000000000000011000102030405060708090a0b0c0d0e0f7874747474747474747474747474747474'
const bytes = (hex) => new Uint8Array(Buffer.from(hex, 'hex'))
const hex = (value) => Buffer.from(value).toString('hex')

class Peer {
  constructor() {
    this.child = spawn(process.env.AGENTBOX_AWCE_TEST_PYTHON ?? 'python3', [join(root, 'tests/interop/awce_peer.py')], {
      cwd: root,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.buffer = ''
    this.pending = undefined
    this.child.stdout.setEncoding('utf8')
    this.child.stdout.on('data', (chunk) => this.receive(chunk))
    this.child.stderr.on('data', () => {})
    this.child.stdin.on('error', () => this.fail())
    this.child.on('error', () => this.fail())
    this.child.on('exit', () => this.fail())
  }
  receive(chunk) {
    this.buffer += chunk
    const newline = this.buffer.indexOf('\n')
    if (this.buffer.length > limit || newline < 0) return this.buffer.length > limit && this.fail()
    if (!this.pending || newline !== this.buffer.length - 1) return this.fail()
    const pending = this.pending
    this.pending = undefined
    clearTimeout(pending.timer)
    try {
      const response = JSON.parse(this.buffer.slice(0, newline))
      this.buffer = ''
      pending.resolve(response)
    } catch {
      pending.reject(new Error('AWCE test response invalid'))
      this.fail()
    }
  }
  fail() {
    if (this.pending) {
      clearTimeout(this.pending.timer)
      this.pending.reject(new Error('AWCE test peer unavailable'))
      this.pending = undefined
    }
    this.child.kill()
  }
  request(value) {
    assert.equal(this.pending, undefined)
    const raw = JSON.stringify(value)
    assert.ok(raw.length < limit)
    return new Promise((resolveRequest, reject) => {
      this.pending = { resolve: resolveRequest, reject, timer: setTimeout(() => this.fail(), 5_000) }
      this.child.stdin.write(`${raw}\n`)
    })
  }
  close() { this.child.stdin.end(); this.child.kill() }
}

const opaque = (length, seed) => Uint8Array.from({ length }, (_, index) => (seed + index * 37 + (index >>> 3)) & 0xff)
const fields = (direction, sequence, cursor, ciphertextLength, seed) => ({
  crypto_envelope_version: 1,
  direction_id: direction,
  flags: 0,
  crypto_sequence: sequence,
  stream_cursor: cursor,
  context_id: opaque(16, seed),
  ciphertext: opaque(ciphertextLength, seed + 19),
})
const peerFields = (value) => ({
  action: 'encode',
  version: value.crypto_envelope_version,
  direction: value.direction_id,
  flags: value.flags,
  sequence: value.crypto_sequence.toString(),
  cursor: value.stream_cursor.toString(),
  context_id: hex(value.context_id),
  ciphertext: hex(value.ciphertext),
})

async function assertBothDirections(core, peer, value) {
  const fromTs = hex(core.encodeAwce(new core.AWCEEnvelope(value)))
  const pythonDecoded = await peer.request({ action: 'decode_reencode', envelope: fromTs })
  assert.deepEqual(pythonDecoded, { ok: true, envelope: fromTs })

  const pythonEncoded = await peer.request(peerFields(value))
  assert.equal(pythonEncoded.ok, true)
  const fromPython = bytes(pythonEncoded.envelope)
  assert.equal(hex(core.encodeAwce(core.decodeAwce(fromPython))), pythonEncoded.envelope)
  assert.equal(pythonEncoded.envelope, fromTs)
}

async function main() {
  const temporary = await mkdtemp(join(tmpdir(), 'agentbox-awce-interop-'))
  let peer
  try {
    const source = await readFile(join(root, 'apps/web/src/features/workspace/awce.ts'), 'utf8')
    const result = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } })
    const modulePath = join(temporary, 'awce.mjs')
    await writeFile(modulePath, result.outputText)
    const core = await import(pathToFileURL(modulePath).href)
    peer = new Peer()

    // This literal is hand-authored in both codec unit-test suites.
    assert.equal(hex(core.encodeAwce(core.decodeAwce(bytes(fixedVector)))), fixedVector)
    assert.deepEqual(await peer.request({ action: 'decode_reencode', envelope: fixedVector }), { ok: true, envelope: fixedVector })

    await assertBothDirections(core, peer, fields(1, 9_007_199_254_740_993n, 0n, 17, 3))
    await assertBothDirections(core, peer, fields(2, 0xffff_ffff_ffff_fffen, 0xffff_ffff_ffff_fffen, 49_168, 71))

    const invalid = [
      ['version', `${fixedVector.slice(0, 8)}02${fixedVector.slice(10)}`],
      ['flags', `${fixedVector.slice(0, 12)}0001${fixedVector.slice(16)}`],
      ['length', `${fixedVector.slice(0, 48)}00000010${fixedVector.slice(56)}`],
      ['reserved sequence', `${fixedVector.slice(0, 16)}ffffffffffffffff${fixedVector.slice(32)}`],
      ['trailing', `${fixedVector}00`],
    ]
    for (const [, raw] of invalid) {
      assert.throws(() => core.decodeAwce(bytes(raw)), core.AWCEError)
      assert.deepEqual(await peer.request({ action: 'decode_reencode', envelope: raw }), { ok: false })
    }
    process.stdout.write('AWCE interop PASS: fixed vector, bidirectional encoding, u64 bounds, body bounds, and malformed framing\n')
  } finally {
    peer?.close()
    await rm(temporary, { recursive: true, force: true })
  }
}

try {
  await main()
} catch {
  process.stderr.write('AWCE interop FAILED (opaque payloads omitted)\n')
  process.exitCode = 1
}
