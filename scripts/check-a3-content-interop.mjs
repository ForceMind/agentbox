// Pure deterministic A3 codecs only: no keys, encryption, transport or admission.
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const requireWeb = createRequire(join(root, 'apps/web/package.json'))
const ts = requireWeb('typescript')
const hex = value => Buffer.from(value).toString('hex')
const bytes = value => new Uint8Array(Buffer.from(value, 'hex'))
const encoder = new TextEncoder()
const fixture = JSON.parse(await readFile(join(root, 'tests/fixtures/a3_content/v1.json'), 'utf8'))
const temporary = await mkdtemp(join(tmpdir(), 'agentbox-a3-interop-'))
try {
  for (const [source, destination] of [
    ['apps/web/src/features/workspace/wawCryptoContext.ts', 'wawCryptoContext.mjs'],
    ['apps/web/src/features/content/a3Content.ts', 'a3Content.mjs'],
  ]) {
    const text = (await readFile(join(root, source), 'utf8')).replace('../workspace/wawCryptoContext', './wawCryptoContext.mjs')
    const result = ts.transpileModule(text, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022}})
    await writeFile(join(temporary, destination), result.outputText)
  }
  const codec = await import(pathToFileURL(join(temporary, 'a3Content.mjs')).href)
  const c = fixture.context
  assert.equal(Buffer.from(codec.contextBytes(c)).toString(), fixture.context_json)
  assert.equal(await codec.contextDigest(c), fixture.context_digest)
  assert.equal(await codec.selectorCommitment(fixture.selector), c.selector_commitment)
  const aad = await codec.applicationAad(c, '8'.repeat(64), 'PATCH_PAGE', 0)
  assert.equal(Buffer.from(aad).toString(), fixture.aad_json)
  for (const raw of fixture.messages_json) assert.equal(Buffer.from(codec.encodeMessage(codec.decodeMessage(encoder.encode(raw)))).toString(), raw)
  for (const raw of fixture.invalid_messages) assert.throws(() => codec.decodeMessage(encoder.encode(raw)))
  const patches = [bytes(fixture.patch_hex), new Uint8Array(191504).fill(120), encoder.encode('x'.repeat(11968) + '🌍' + 'y'.repeat(12000))]
  for (const patch of patches) {
    const pages = await codec.preparePages(c, patch, '1791111111111')
    const result = spawnSync(process.env.AGENTBOX_A3_TEST_PYTHON ?? 'python3', [join(root, 'tests/interop/a3_content_peer.py')], {
      cwd: root, encoding: 'utf8', timeout: 15000, maxBuffer: 4_000_000,
      input: JSON.stringify({context: c, patch_hex: hex(patch), observed_at_ms: '1791111111111', messages_hex: [hex(encoder.encode(fixture.messages_json[0])), ...pages.map(hex)], invalid_messages: fixture.invalid_messages}),
    })
    assert.equal(result.status, 0, result.stderr || result.error?.message)
    const peer = JSON.parse(result.stdout)
    assert.equal(peer.context_hex, hex(codec.contextBytes(c)))
    assert.equal(peer.aad_hex, hex(aad))
    assert.equal(peer.rejected, fixture.invalid_messages.length)
    assert.deepEqual(peer.pages_hex, pages.map(hex))
    const receiver = new codec.ContentRead(c, 0, 30000)
    await receiver.accept(encoder.encode(fixture.messages_json[0]), 1, c)
    let complete
    for (const raw of peer.pages_hex) {
      const fromPython = bytes(raw)
      assert.equal(hex(codec.encodeMessage(codec.decodeMessage(fromPython))), raw)
      complete = await receiver.accept(fromPython, 1, c)
    }
    assert.equal(hex(complete), hex(patch))
  }
  await assert.rejects(codec.preparePages(c, new Uint8Array(191505).fill(120), '1791111111111'), /PATCH_TOO_LARGE/)
  console.log('A3 codec interop: literal context/AAD/four messages, 16 shared negatives, both directions, exact capacity and split UTF-8 passed; no crypto/transport claim')
} finally { await rm(temporary, {recursive: true, force: true}) }
