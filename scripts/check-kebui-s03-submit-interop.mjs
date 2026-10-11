/** Fixed, offline S03 software qualification. No generic process or network relay. */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { constants } from 'node:fs'
import { access, mkdtemp, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { Writable } from 'node:stream'
import { basename, dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(join(root, 'apps/web/package.json'))
const ts = require('typescript')
const MAX_FRAME = 22031
const RELAY_RESERVATION = 262144
const META_LIMIT = 4096
const SCENARIOS = Object.freeze([
  'minimum', 'ascii_16k', 'nul_16k', 'utf8_4byte_16k', 'bom',
  'quotes_backslashes', 'crlf', 'lf', 'decomposed', 'composed', 'mixed_canary',
  'corrupt_tag', 'prefix_max', 'truncated_prefix', 'truncated_body',
  'missing_attest', 'missing_confirm', 'missing_ready', 'missing_submit',
  'held_writable', 'held_readiness', 'cancel_waiter', 'revoke_readiness',
  'remote_expiry', 'slow_reader', 'lost_ack_recovery',
  'response_prefix_max', 'truncated_response_prefix', 'truncated_response_body',
])
const POSITIVE = new Set(SCENARIOS.slice(0, 11).concat(['cancel_waiter']))
let stage = 'setup'
let scenario = 'minimum'

function safeFailure() { return new Error('s03_invalid') }
function check(condition) { if (!condition) throw safeFailure() }
function bodyFor(name) {
  switch (name) {
    case 'minimum': return new Uint8Array([120])
    case 'slow_reader':
    case 'ascii_16k': return new Uint8Array(16384).fill(120)
    case 'nul_16k': return new Uint8Array(16384)
    case 'utf8_4byte_16k': {
      const bytes = new Uint8Array(16384)
      for (let n = 0; n < bytes.length; n += 4) bytes.set([240, 159, 152, 128], n)
      return bytes
    }
    case 'bom': return new Uint8Array([239, 187, 191, 116, 101, 120, 116])
    case 'quotes_backslashes': return new Uint8Array([34, 92])
    case 'crlf': return new Uint8Array([97, 13, 10])
    case 'lf': return new Uint8Array([97, 10])
    case 'decomposed': return new Uint8Array([101, 204, 129])
    case 'composed': return new Uint8Array([195, 169])
    default: return new Uint8Array([115, 121, 110, 116, 104, 101, 116, 105, 99, 32, 83, 48, 51, 13, 10, 0])
  }
}
function byteCountFor(name) {
  if (['ascii_16k', 'nul_16k', 'utf8_4byte_16k', 'slow_reader'].includes(name)) return 16384
  return { minimum: 1, bom: 7, quotes_backslashes: 2, crlf: 3, lf: 2, decomposed: 3, composed: 2 }[name] ?? 16
}
function contextFor(fixture, name) {
  const suffix = (SCENARIOS.indexOf(name) + 1).toString(16).padStart(32, '0')
  return { ...fixture.context, request_id: `kreq_${suffix}`, channel_id: `ks03c_${suffix}`, source_lease_id: `ks03l_${suffix}` }
}

/** A whole-lane reservation remains charged even in idle protocol gaps. */
class RelayLedger {
  reserved = RELAY_RESERVATION
  live = new Map()
  peak = new Map()
  maximum = 0
  own(name, length) {
    check(this.reserved === RELAY_RESERVATION && Number.isSafeInteger(length) && length >= 0)
    check(!this.live.has(name))
    this.live.set(name, length)
    this.peak.set(name, Math.max(this.peak.get(name) ?? 0, length))
    const total = [...this.live.values()].reduce((a, b) => a + b, 0)
    this.maximum = Math.max(total, this.maximum)
    check(total <= RELAY_RESERVATION)
  }
  drop(name) { this.live.delete(name) }
  retire() { check(this.live.size === 0); this.reserved = 0 }
}

/** One reader and one accumulator. Prefix is checked before any payload buffer. */
class FrameReader {
  pending = false
  closed = false
  allocated = 0
  reads = 0
  constructor(stream, ledger) {
    this.stream = stream
    this.ledger = ledger
    stream.pause()
  }
  async waitReadable(signal) {
    if (signal.aborted || this.closed || this.stream.destroyed) throw safeFailure()
    await new Promise((resolveWait, rejectWait) => {
      const cleanup = () => {
        this.stream.off('readable', ready)
        this.stream.off('end', ended)
        this.stream.off('error', ended)
        signal.removeEventListener('abort', ended)
      }
      const ready = () => { cleanup(); resolveWait() }
      const ended = () => { cleanup(); rejectWait(safeFailure()) }
      this.stream.once('readable', ready)
      this.stream.once('end', ended)
      this.stream.once('error', ended)
      signal.addEventListener('abort', ended, { once: true })
      if (this.stream.readableEnded || signal.aborted || this.closed) ended()
      else if (this.stream.readableLength > 0) ready()
    })
  }
  async exact(target, signal) {
    let position = 0
    while (position < target.length) {
      if (signal.aborted || this.closed) throw safeFailure()
      // read(available) never asks Node to buffer an unbounded future chunk.
      const count = Math.min(target.length - position, this.stream.readableLength, MAX_FRAME)
      if (!count) { await this.waitReadable(signal); continue }
      let part = this.stream.read(count)
      check(part !== null && part.length === count)
      this.ledger.own('read_chunk', count)
      target.set(part, position)
      position += count
      part = null
      this.ledger.drop('read_chunk')
    }
  }
  async read(signal) {
    check(!this.pending && !this.closed)
    this.pending = true
    let prefix = null
    let payload = null
    try {
      this.ledger.own('read_prefix', 4)
      prefix = new Uint8Array(4)
      await this.exact(prefix, signal)
      const length = new DataView(prefix.buffer).getUint32(0, false)
      check(length > 0 && length <= MAX_FRAME)
      this.ledger.own('read_payload', length)
      payload = new Uint8Array(length)
      this.allocated = Math.max(this.allocated, length)
      await this.exact(payload, signal)
      this.reads += 1
      const result = payload
      payload = null
      return result
    } finally {
      prefix = payload = null
      this.ledger.drop('read_prefix')
      this.ledger.drop('read_payload')
      this.pending = false
    }
  }
  close() { this.closed = true; this.stream.destroy() }
}

class FixedPipe {
  attempted = 0
  submitAttempts = 0
  pendingWrite = null
  closed = false
  capacityPending = false
  held = false
  readCount = 0
  writeReturnedFalse = false
  pendingChargeObserved = false
  callbackChargeValid = true
  closeChargeObserved = false
  constructor(peer, ledger, name) {
    this.peer = peer
    this.ledger = ledger
    this.name = name
    this.reader = new FrameReader(peer.stdout, ledger)
    // Public Writable API, a single packet and callback, no additional copy.
    // libuv stdio is not a FIFO on every platform; do not change OS settings.
    this.writer = name === 'slow_reader' ? new Writable({
      highWaterMark: 4096,
      write(chunk, _encoding, callback) { peer.stdin.write(chunk, callback) },
    }) : peer.stdin
    this.writer.on('error', () => {})
    // A failed OS publication is uncertain; never retry it or print its error.
    peer.stdin.on('error', () => {})
  }
  async waitWritable(signal) {
    check(!this.capacityPending && !this.closed)
    this.capacityPending = true
    try {
      if (this.name === 'held_writable' && this.attempted === 2) {
        this.held = true
        await new Promise((_, rejectWait) => {
          const abort = () => { signal.removeEventListener('abort', abort); rejectWait(safeFailure()) }
          signal.addEventListener('abort', abort, { once: true })
          if (signal.aborted) abort()
        })
      } else if (this.name === 'remote_expiry' && this.attempted === 2) {
        await abortableDelay(160, signal)
      }
      if (this.pendingWrite) await this.pendingWrite
      if (signal.aborted || this.closed || this.peer.stdin.destroyed) throw safeFailure()
    } finally { this.capacityPending = false }
  }
  async read(signal) {
    if ((this.name === 'missing_attest' && this.readCount === 0) ||
        (this.name === 'missing_ready' && this.readCount === 1)) {
      // The peer independently omits the requested record. This is a real IO wait.
    }
    const raw = await this.reader.read(signal)
    this.readCount += 1
    return raw
  }
  write(raw) {
    check(!this.closed && !this.pendingWrite && raw instanceof Uint8Array && raw.length > 0 && raw.length <= MAX_FRAME)
    this.attempted += 1
    if (this.attempted === 3) this.submitAttempts += 1
    if (this.name === 'missing_confirm' && this.attempted === 2) return true
    if (this.name === 'missing_submit' && this.attempted === 3) return true
    const packetSize = raw.length + 4
    this.ledger.own('write_frame', packetSize)
    let packet = Buffer.allocUnsafe(raw.length + 4)
    packet.writeUInt32BE(raw.length, 0)
    packet.set(raw, 4)
    if (this.name === 'corrupt_tag' && this.attempted === 3) {
      // Corrupt a Base64 character, retaining the exact bounded outer shape.
      const start = packet.indexOf(Buffer.from('"data":"')) + 8
      check(start >= 12)
      packet[start] = packet[start] === 65 ? 66 : 65
    }
    if (this.name === 'prefix_max' && this.attempted === 1) {
      packet.writeUInt32BE(MAX_FRAME + 1, 0)
      packet = packet.subarray(0, 4)
    }
    if (this.name === 'truncated_prefix' && this.attempted === 1) packet = packet.subarray(0, 3)
    if (this.name === 'truncated_body' && this.attempted === 1) packet = packet.subarray(0, 9)
    let settle
    this.pendingWrite = new Promise(resolveWrite => { settle = resolveWrite })
    // Node owns exactly this single packet until its callback actually retires.
    const accepted = this.writer.write(packet, () => {
      this.callbackChargeValid &&= this.ledger.live.get('write_frame') === packetSize
      packet = null
      this.ledger.drop('write_frame')
      this.pendingWrite = null
      settle()
    })
    if (!accepted) {
      this.writeReturnedFalse = true
      this.pendingChargeObserved = this.pendingWrite !== null && this.ledger.live.get('write_frame') === raw.length + 4
    }
    if (['prefix_max', 'truncated_prefix', 'truncated_body'].includes(this.name) && this.attempted === 1) this.peer.stdin.end()
    return accepted
  }
  close() {
    if (this.closed) return
    if (this.pendingWrite) this.closeChargeObserved = this.ledger.live.has('write_frame') && this.ledger.reserved === RELAY_RESERVATION
    this.closed = true
    this.reader.close()
    if (!['missing_attest', 'missing_confirm', 'missing_ready', 'missing_submit', 'held_writable'].includes(this.name)) this.peer.stdin.end()
  }
  async drain() { if (this.pendingWrite) await this.pendingWrite; check(!this.reader.pending && !this.capacityPending && this.callbackChargeValid) }
}

function abortableDelay(ms, signal) {
  return new Promise((resolveWait, rejectWait) => {
    const complete = () => { signal.removeEventListener('abort', abort); resolveWait() }
    const timer = setTimeout(complete, ms)
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); rejectWait(safeFailure()) }
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
  })
}

function boundedCollector(stream, ledger, label) {
  ledger.own(label, META_LIMIT)
  const storage = Buffer.alloc(META_LIMIT)
  let length = 0
  let invalid = false
  const done = new Promise(resolveDone => {
    stream.on('data', part => {
      if (part.length > META_LIMIT - length) { invalid = true; stream.destroy(); return }
      storage.set(part, length)
      length += part.length
    })
    stream.once('end', resolveDone)
    stream.once('close', resolveDone)
    stream.once('error', () => { invalid = true; resolveDone() })
  })
  return { done, result() { check(!invalid); return storage.subarray(0, length) }, retire() { storage.fill(0); ledger.drop(label) } }
}

function metadataResult(raw, name) {
  check(raw.length > 0 && raw.length <= META_LIMIT)
  // Metadata is seven bounded scalar fields, never the content pipe format.
  for (const byte of raw) check(byte >= 32 && byte <= 126)
  const text = raw.toString('ascii')
  check(/^[\x20-\x7e]+$/.test(text))
  const result = JSON.parse(text)
  check(JSON.stringify(result) === text)
  check(Object.keys(result).join(',') === 'scenario,phase,effects,bytes,original_identity_match,pool_drained,safe_errors')
  check(result.scenario === name && ['ACKNOWLEDGED', 'UNKNOWN', 'REJECTED', 'EXPIRED', 'CLOSED'].includes(result.phase))
  check(Number.isInteger(result.effects) && result.effects >= 0 && result.effects <= 1)
  check(Number.isInteger(result.bytes) && result.bytes >= 0 && result.bytes <= 16384)
  check(typeof result.original_identity_match === 'boolean' && result.pool_drained === true && result.safe_errors === true)
  return result
}

async function checkedInterpreter() {
  const input = process.env.AGENTBOX_S03_TEST_PYTHON
  check(typeof input === 'string' && isAbsolute(input) && /^python(?:3(?:\.\d+)?)?$/.test(basename(input)))
  const candidate = resolve(input)
  const target = await realpath(candidate)
  check((await stat(target)).isFile() && /^python(?:3(?:\.\d+)?)?$/.test(basename(target)))
  await access(candidate, constants.X_OK)
  return candidate
}

async function transpile(directory) {
  const sources = [
    ['noiseNx', 'workspace/noiseNx'],
    ['workspaceState', 'workspace/workspaceState'],
    ['workspaceMetadata', 'workspace/workspaceMetadata'],
    ['conversationObservation', 'conversation/conversationObservation'],
    ['s03Submit', 'conversation/s03Submit'],
  ]
  for (const [name, relative] of sources) {
    let source = await readFile(join(root, `apps/web/src/features/${relative}.ts`), 'utf8')
    for (const [dependency] of sources) {
      source = source.replaceAll(`'../workspace/${dependency}'`, `'./${dependency}.mjs'`).replaceAll(`'./${dependency}'`, `'./${dependency}.mjs'`)
    }
    const result = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } })
    await writeFile(join(directory, `${name}.mjs`), result.outputText)
  }
  return import(pathToFileURL(join(directory, 's03Submit.mjs')).href)
}

async function runScenario(module, fixture, python, name) {
  scenario = name
  stage = 'spawn'
  const ledger = new RelayLedger()
  const relay = module.reserveRelayForTest()
  const metadataBefore = relay.snapshot()
  let expectedMetadataBytes = metadataBefore.metadataBytes + 19
  for (const key of Object.keys(fixture.context)) {
    if (key !== 'adapter_profile' && key !== 'runtime_pin') expectedMetadataBytes += fixture.context[key].length
  }
  if (name === 'lost_ack_recovery') ledger.own('recovery_catalog', 5 * META_LIMIT)
  const peer = spawn(python, [join(root, 'tests/interop/kebui_s03_submit_peer.py'), name], {
    cwd: root,
    env: {
      PATH: dirname(python), LANG: 'C.UTF-8', PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1',
      PYTHONPATH: ['agentbox-core', 'agentbox-protocol', 'agentbox-runtime'].map(part => join(root, 'packages', part, 'src')).join(':'),
    },
    stdio: ['pipe', 'pipe', 'pipe', 'pipe'],
  })
  const metadata = boundedCollector(peer.stdio[3], ledger, 'metadata')
  const diagnostics = boundedCollector(peer.stderr, ledger, 'stderr')
  let killedByWatchdog = false
  const watchdog = setTimeout(() => { killedByWatchdog = true; peer.kill('SIGKILL') }, 25000)
  const exited = new Promise(resolveExit => {
    peer.once('error', () => resolveExit({ code: -1 }))
    peer.once('close', code => resolveExit({ code }))
  })
  const pipe = new FixedPipe(peer, ledger, name)
  const endpoint = Object.freeze({
    waitWritable: signal => pipe.waitWritable(signal),
    read: signal => pipe.read(signal),
    write: raw => pipe.write(raw),
    close: () => pipe.close(),
  })
  let webRoot
  let sender
  let failed = false
  let result
  try {
    stage = 'construct'
    if (name === 'remote_expiry') await new Promise(resolveWait => setTimeout(resolveWait, 11000))
    const origin = process.hrtime.bigint()
    webRoot = module.SyntheticS03TestRoot.forFixture({
      context: contextFor(fixture, name), endpoint,
      clock: () => 9000000000000n + (process.hrtime.bigint() - origin),
      deadline: 9008000000000n,
    })
    sender = webRoot.open(endpoint)
    check(sender.snapshot().processReserved === 1571840)
    stage = 'handshake'
    try {
      await sender.handshake()
      stage = 'submit'
      await sender.submit(bodyFor(name))
    } catch { failed = true }
    stage = 'metadata'
    // Source/worker readiness expiry is independent of Web transport closure.
    const exit = await exited
    await Promise.all([metadata.done, diagnostics.done])
    check(!killedByWatchdog && exit.code === 0 && diagnostics.result().length === 0)
    result = metadataResult(metadata.result(), name)
    if (POSITIVE.has(name)) {
      check(!failed && result.phase === 'ACKNOWLEDGED' && result.effects === 1)
      check(result.original_identity_match && result.bytes === byteCountFor(name))
    } else if (name === 'slow_reader') {
      check(failed && pipe.writeReturnedFalse && pipe.pendingChargeObserved && pipe.closeChargeObserved && pipe.submitAttempts === 1)
      check(result.phase === 'ACKNOWLEDGED' && result.effects === 1 && result.bytes === 16384 && result.original_identity_match)
    } else if (name === 'lost_ack_recovery') {
      check(result.phase === 'UNKNOWN' && result.effects === 1 && result.bytes === 16 && result.original_identity_match)
    } else if (name === 'held_readiness' || name === 'revoke_readiness') {
      check(result.phase === 'UNKNOWN' && result.effects === 0)
    } else {
      check(result.effects === 0 && result.bytes === 0)
    }
    if (name === 'remote_expiry') check(pipe.submitAttempts === 1)
    if (name === 'held_writable') check(pipe.held && pipe.submitAttempts === 0)
    if (name === 'prefix_max') check(result.phase === 'REJECTED')
    if (['response_prefix_max', 'truncated_response_prefix'].includes(name)) check(pipe.reader.allocated === 0)
    if (name === 'truncated_response_body') check(pipe.reader.allocated === 296)
    stage = 'drain'
    webRoot.close()
    pipe.close()
    await pipe.drain()
    metadata.retire()
    diagnostics.retire()
    ledger.drop('recovery_catalog')
    ledger.retire()
    check(sender.snapshot().reserved === 0 && sender.snapshot().keysDetached)
    check(sender.snapshot().metadataConstructionPeak <= 2508)
    check(relay.snapshot().reserved === RELAY_RESERVATION)
    relay.release()
    const retained = relay.snapshot()
    check(retained.processReserved === 261120 && retained.metadataReserved === 261120)
    check(retained.metadataEntries === metadataBefore.metadataEntries + 1 && retained.metadataEntries <= 255)
    check(retained.metadataBytes === expectedMetadataBytes && retained.metadataBytes <= 255 * 627)
    console.log(`S03 ${name} PASS phase=${result.phase} effects=${result.effects} bytes=${result.bytes} identity=${result.original_identity_match} drained=${result.pool_drained} web_uncertain=${failed && pipe.submitAttempts === 1} relay_peak=${ledger.maximum} retained_metadata=${retained.metadataBytes} entries=${retained.metadataEntries}`)
  } finally {
    webRoot?.close()
    pipe.close()
    clearTimeout(watchdog)
    if (peer.exitCode === null) peer.kill('SIGTERM')
    await exited
    await pipe.drain()
  }
}

let temporary
try {
  const requested = process.argv.slice(2)
  check(requested.length === 0 || (requested.length === 1 && SCENARIOS.includes(requested[0])))
  const python = await checkedInterpreter()
  temporary = await mkdtemp(join(tmpdir(), 'agentbox-s03-interop-'))
  // One authorized Web realm, one imported module instance, one accounting
  // domain for the entire finite run. No reset, cache-busting or extra workers.
  const module = await transpile(temporary)
  const fixture = JSON.parse(await readFile(join(root, 'tests/fixtures/kebui_s03_submit/v1.json'), 'utf8'))
  assert.equal(fixture.profile, 's03-submit-synthetic-v1-candidate-3')
  for (const name of requested.length ? requested : SCENARIOS) await runScenario(module, fixture, python, name)
  console.log('S03 binary interop PASS: actual fresh Web sender, original Python issuer/owner/journal/consumer, bounded independent metadata')
} catch {
  console.error(`S03 interop FAIL scenario=${scenario} stage=${stage}`)
  process.exitCode = 1
} finally {
  if (temporary) await rm(temporary, { recursive: true, force: true })
}
