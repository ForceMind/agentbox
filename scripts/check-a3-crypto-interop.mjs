// Actual synthetic Git → same-held selector/reader → Python A3 Noise → opaque relay → Web.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath, pathToFileURL } from 'node:url'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ts = createRequire(join(root, 'apps/web/package.json'))('typescript')
const temporary = await mkdtemp(join(tmpdir(), 'agentbox-a3-crypto-'))
const hex = value => Buffer.from(value).toString('hex')
const bytes = value => new Uint8Array(Buffer.from(value, 'hex'))
const encoder = new TextEncoder()
try {
  for (const name of ['noiseNx', 'wawCryptoContext', 'a3Content', 'a3Crypto']) {
    const feature = name.startsWith('a3') ? 'content' : 'workspace'
    let text = await readFile(join(root, `apps/web/src/features/${feature}/${name}.ts`), 'utf8')
    for (const dependency of ['noiseNx', 'wawCryptoContext', 'a3Content'])
      text = text.replaceAll(`'../workspace/${dependency}'`, `'./${dependency}.mjs'`).replaceAll(`'./${dependency}'`, `'./${dependency}.mjs'`)
    const result = ts.transpileModule(text, { compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022} })
    await writeFile(join(temporary, `${name}.mjs`), result.outputText)
  }
  const { A3Browser } = await import(pathToFileURL(join(temporary, 'a3Crypto.mjs')).href)
  const { contextDigest, encodeMessage } = await import(pathToFileURL(join(temporary, 'a3Content.mjs')).href)
  const fixture = JSON.parse(await readFile(join(root, 'tests/fixtures/a3_content/crypto-v1.json'), 'utf8'))
  // Runtime static input is bytes(range(32)), distinct from deterministic oracle keys.
  const publicKey = await crypto.subtle.importKey('pkcs8', bytes('302e020100300506032b656e04220420' + Array.from({length:32}, (_, i) => i.toString(16).padStart(2, '0')).join('')), {name:'X25519'}, true, ['deriveBits'])
  const jwk = await crypto.subtle.exportKey('jwk', publicKey)
  const runtimePin = new Uint8Array(Buffer.from(jwk.x, 'base64url'))
  assert.equal(runtimePin.length, 32)
  for (const fault of ['none', 'lost-page', 'tamper-page', 'visibility-loss']) {
    const peer = spawn(process.env.AGENTBOX_A3_TEST_PYTHON ?? 'python3', [join(root, 'tests/interop/a3_git_crypto_peer.py')], {cwd:root, stdio:['pipe','pipe','pipe']})
    const timer = setTimeout(() => peer.kill('SIGKILL'), 30000)
    let stderr = ''
    peer.stderr.setEncoding('utf8'); peer.stderr.on('data', chunk => { stderr += chunk })
    const exited = new Promise(resolve => peer.on('close', (code, signal) => resolve({code, signal})))
    const lines = createInterface({input:peer.stdout})[Symbol.asyncIterator]()
    const next = async () => {const result=await lines.next(); assert.equal(result.done,false,stderr); return JSON.parse(result.value)}
    const send = wire => {assert.ok(wire.length <= 24576); peer.stdin.write(hex(wire) + '\n')}
    let browser
    try {
      const bootstrap = (await next()).fixture_bootstrap
      const context = bootstrap.context
      assert.equal(createHash('sha256').update(runtimePin).digest('hex'), bootstrap.pin_sha256)
      const trusted = {current: () => ({context, nowMs:bootstrap.now_ms, runtimePin})}
      browser = new A3Browser(context, trusted, {admissionStartedAtMs:bootstrap.now_ms, admissionExpiresAtMs:bootstrap.expires_ms})
      const opaque = []
      send(await browser.start())
      const attest = bytes((await next()).wire); opaque.push(attest)
      send(await browser.acceptAttest(attest))
      const ack = bytes((await next()).wire); opaque.push(ack)
      await browser.acceptAck(ack)
      const read = encodeMessage({protocol_id:'agentbox-a3-content/v1',protocol_version:1,context_digest:await contextDigest(context),request_nonce:context.request_nonce,kind:'PATCH_READ',selection_id:bootstrap.selection})
      send(await browser.encryptRead(read))
      let complete, rejected = false, affected = false, done
      while (true) {
        const message = await next()
        if (message.fixture_done) {done=message; break}
        const wire=bytes(message.wire); opaque.push(wire)
        const envelope=JSON.parse(new TextDecoder().decode(wire))
        assert.deepEqual(Object.keys(envelope).sort(), ['ciphertext','context_digest','domain','kind','sequence'])
        if (!affected && envelope.kind==='PATCH_PAGE' && fault!=='none') {
          affected=true
          if (fault==='lost-page') continue
          if (fault==='visibility-loss') browser.close()
          if (fault==='tamper-page') {
            envelope.ciphertext=(envelope.ciphertext[0]==='A'?'B':'A')+envelope.ciphertext.slice(1)
            const corrupt=encoder.encode(JSON.stringify(Object.fromEntries(Object.entries(envelope).sort())))
            await assert.rejects(browser.acceptResponse(corrupt)); rejected=true; continue
          }
        }
        if (rejected) continue
        try {const value=await browser.acceptResponse(wire); if(value) complete=value}
        catch (error) {if(fault==='none') throw error; rejected=true}
      }
      assert.equal(done.native_double_observations,2); assert.equal(done.burned_nonces,1)
      for(const wire of opaque) {
        const text=Buffer.from(wire).toString()
        assert.ok(!text.includes('synthetic-staged-canary') && !text.includes('unstaged-exclusion-canary') && !text.includes('selection_id'))
      }
      if(fault==='none') {
        assert.ok(complete)
        assert.equal(createHash('sha256').update(complete).digest('hex'), bootstrap.expected_sha256)
        assert.ok(new TextDecoder().decode(complete).includes('+synthetic-staged-canary-'))
        assert.ok(!new TextDecoder().decode(complete).includes('unstaged-exclusion-canary'))
      } else {assert.equal(complete,undefined); assert.equal(rejected,true)}
      peer.stdin.end()
      const result=await exited
      assert.equal(result.code,0,stderr)
    } finally {browser?.close(); clearTimeout(timer); peer.stdin.end(); if(peer.exitCode===null) peer.kill('SIGTERM')}
  }
  assert.equal(fixture.schema, 'agentbox-a3-public-crypto-vector/v1')
  console.log('A3 encrypted Git interop PASS: native double observation, original-expiry admission, opaque-only relay, verified Web bytes; loss/tamper/visibility publish no partial bytes')
} finally {await rm(temporary,{recursive:true,force:true})}
