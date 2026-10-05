// Real Git + actual API route/admission/opaque fixture -> shipped Web controller.
// This is a Node integration check, NOT browser/DOM/physical-client evidence.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath, pathToFileURL } from 'node:url'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ts = createRequire(join(root, 'apps/web/package.json'))('typescript')
const temporary = await mkdtemp(join(tmpdir(), 'agentbox-a3-changes-'))
const modules = ['noiseNx', 'wawCryptoContext', 'a3Content', 'a3Crypto', 'a3ChangesDto', 'a3ChangesTrust', 'a3ChangesController']
const bytes = value => new Uint8Array(Buffer.from(value, 'hex'))
const hex = value => Buffer.from(value).toString('hex')
globalThis.document = { hidden: false }
try {
  for (const name of modules) {
    const feature = name.startsWith('a3') ? 'content' : 'workspace'
    let source = await readFile(join(root, `apps/web/src/features/${feature}/${name}.ts`), 'utf8')
    for (const dependency of modules)
      source = source.replaceAll(`'../workspace/${dependency}'`, `'./${dependency}.mjs'`).replaceAll(`'./${dependency}'`, `'./${dependency}.mjs'`)
    const result = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } })
    await writeFile(join(temporary, `${name}.mjs`), result.outputText)
  }
  const { A3ChangesController } = await import(pathToFileURL(join(temporary, 'a3ChangesController.mjs')).href)
  const { ContentError } = await import(pathToFileURL(join(temporary, 'a3Content.mjs')).href)
  for (const [path, mode, status] of [
    ['success.txt', 'normal', 'completed'], ['binary.bin', 'normal', 'binary'],
    ['large.txt', 'normal', 'too-large'], ['.env', 'normal', 'unavailable'],
    ['success.txt', 'tamper', 'failed'], ['success.txt', 'drop-page', 'failed'],
    ['success.txt', 'permission', 'permission'],
  ]) {
    const peer = spawn(process.env.AGENTBOX_A3_TEST_PYTHON ?? 'python3', [join(root, 'tests/interop/a3_changes_peer.py')], { cwd: root, stdio: ['pipe', 'pipe', 'ignore'] })
    const timer = setTimeout(() => peer.kill('SIGKILL'), 30000)
    let identifier = 0
    const pending = new Map()
    let readyResolve
    const ready = new Promise(resolve => { readyResolve = resolve })
    const exited = new Promise(resolve => peer.on('close', resolve))
    const lines = createInterface({ input: peer.stdout })
    lines.on('line', line => {
      const value = JSON.parse(line)
      if (value.ready) return readyResolve()
      const entry = pending.get(value.id)
      assert.ok(entry)
      pending.delete(value.id)
      if (value.ok) entry.resolve(value.result)
      else entry.reject(new ContentError(/^(AUTH_|SESSION_)/.test(value.code) ? 'PATCH_REVOKED' : value.code))
    })
    const call = (op, payload = {}) => new Promise((resolve, reject) => {
      const id = ++identifier
      pending.set(id, { resolve, reject })
      peer.stdin.write(JSON.stringify({ id, op, payload }) + '\n')
    })
    let controller
    try {
      await ready
      const trust = await call('trust')
      assert.equal(typeof trust.binding.auth_epoch, 'string')
      await call('mode', { value: mode })
      let live = { purpose: trust.purpose, binding: trust.binding, pin32: bytes(trust.pin) }
      let invalidate
      const deps = {
        trust: { current: () => live, subscribeInvalidation: callback => { invalidate = callback; return () => {} } },
        nowMs: () => Math.floor(performance.now()),
        observe: () => call('bootstrap'),
        open: async request => {
          const { handle } = await call('open', request)
          let closed = false
          return {
            send: async (raw, guard) => { if (closed) throw new ContentError(); guard(); await call('send', { handle, wire: hex(raw) }) },
            receive: async () => bytes((await call('receive', { handle })).wire),
            close: () => { closed = true; void call('close', { handle }).catch(() => {}) },
            subscribeClose: () => () => {},
          }
        },
      }
      controller = new A3ChangesController('prj_' + 'a'.repeat(32), deps)
      controller.activate()
      assert.equal((await call('status')).observations, 0)
      await controller.read({ path, kind: 'added', staged: true })
      assert.equal(controller.snapshot.status, status, `${path}/${mode}`)
      assert.equal((await call('status')).observations, mode === 'permission' ? 0 : 1)
      if (status === 'completed') {
        assert.ok(controller.snapshot.text.includes('A3 synthetic complete diff'))
        assert.ok(controller.snapshot.text.includes('<img src=x onerror=window.a3Executed=true>'))
        assert.ok(!controller.snapshot.text.includes('unstaged-exclusion-canary'))
        const result = await call('status')
        assert.equal(result.diff_count, 2)
        assert.equal(result.burned_nonces, 1)
        live = null
        invalidate()
        assert.equal(controller.snapshot.text, null)
        assert.equal(controller.snapshot.status, 'permission')
      } else assert.equal(controller.snapshot.text, null)
      controller.dispose()
      await call('close')
      assert.equal((await call('status')).active, 0)
      peer.stdin.end()
      assert.equal(await exited, 0)
    } finally {
      controller?.dispose()
      clearTimeout(timer)
      peer.kill()
      lines.close()
    }
  }
  console.log('A3 Changes actual API/Git/opaque -> Web controller: 7 scenarios PASS')
} finally {
  await rm(temporary, { recursive: true, force: true })
}
