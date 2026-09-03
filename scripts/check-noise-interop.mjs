// Run actual Python/WebCrypto peers against the pinned public Noise-C vector.
// No application/host keys are loaded. Ciphertext stays in bounded child pipes.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createPrivateKey, createPublicKey, webcrypto } from 'node:crypto';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const requireWeb = createRequire(join(root, 'apps/web/package.json'));
const ts = requireWeb('typescript');
const fixture = JSON.parse(await readFile(join(root, 'tests/fixtures/noise_nx/noise-c-nx-aesgcm-sha256.json'), 'utf8'));
const bytes = (hex) => new Uint8Array(Buffer.from(hex, 'hex'));
const hex = (data) => Buffer.from(data).toString('hex');
const text = (value) => new TextEncoder().encode(value);
const ad = text('agentbox-noise-interop/ad');
Object.defineProperty(globalThis, 'crypto', { value: webcrypto, configurable: true });

async function keyPair(rawHex) {
  // Public test-vector private keys only; production uses non-extractable
  // generated keys. Node derives the matching public half for this fixture.
  const pkcs8 = Buffer.concat([Buffer.from('302e020100300506032b656e04220420', 'hex'), Buffer.from(rawHex, 'hex')]);
  const privateObject = createPrivateKey({ key: pkcs8, format: 'der', type: 'pkcs8' });
  const spki = createPublicKey(privateObject).export({ format: 'der', type: 'spki' });
  return {
    privateKey: await webcrypto.subtle.importKey('pkcs8', pkcs8, { name: 'X25519' }, false, ['deriveBits']),
    publicKey: await webcrypto.subtle.importKey('raw', spki.subarray(-32), { name: 'X25519' }, true, []),
  };
}

class Peer {
  constructor() {
    this.child = spawn(process.env.AGENTBOX_NOISE_TEST_PYTHON ?? 'python3', [join(root, 'tests/interop/noise_peer.py')], {
      cwd: root,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.buffer = '';
    this.pending = undefined;
    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', (chunk) => {
      this.buffer += chunk;
      if (this.buffer.length > 200_000) return this.fail();
      const newline = this.buffer.indexOf('\n');
      if (newline < 0) return;
      if (!this.pending || newline !== this.buffer.length - 1) return this.fail();
      const { resolve: finish, reject, timer } = this.pending;
      this.pending = undefined;
      clearTimeout(timer);
      try {
        const result = JSON.parse(this.buffer.slice(0, newline));
        this.buffer = '';
        finish(result);
      } catch {
        reject(new Error('bounded peer response invalid'));
      }
    });
    // Drain errors without printing potentially unsafe foreign exception data.
    this.child.stderr.on('data', () => {});
    this.child.stdin.on('error', () => this.fail());
    this.child.on('error', () => this.fail());
    this.child.on('exit', () => { if (this.pending) this.fail(); });
  }
  fail() {
    if (this.pending) {
      clearTimeout(this.pending.timer);
      this.pending.reject(new Error('Noise test peer unavailable'));
      this.pending = undefined;
    }
    this.child.kill();
  }
  request(value) {
    assert.equal(this.pending, undefined);
    return new Promise((resolveRequest, reject) => {
      this.pending = {
        resolve: resolveRequest,
        reject,
        timer: setTimeout(() => this.fail(), 5_000),
      };
      this.child.stdin.write(`${JSON.stringify(value)}\n`);
    });
  }
  close() { this.child.stdin.end(); this.child.kill(); }
}

async function exchange(core, browserRole) {
  const peer = new Peer();
  let handshake;
  let transport;
  try {
    const pythonRole = browserRole === 'initiator' ? 'responder' : 'initiator';
    assert.equal((await peer.request({ action: 'init', role: pythonRole })).ok, true);
    const prologue = bytes(fixture.init_prologue);
    if (browserRole === 'initiator') {
      handshake = new core.NXInitiator(prologue, await keyPair(fixture.init_ephemeral));
      const message1 = await handshake.writeMessage1(bytes(fixture.messages[0].payload));
      assert.equal(hex(message1), fixture.messages[0].ciphertext);
      assert.equal((await peer.request({ action: 'read1', message: hex(message1) })).matches, true);
      const reply = await peer.request({ action: 'write2' });
      assert.equal(reply.message, fixture.messages[1].ciphertext);
      assert.equal(hex(await handshake.readMessage2(bytes(reply.message))), fixture.messages[1].payload);
    } else {
      handshake = new core.NXResponder(prologue, await keyPair(fixture.resp_static), await keyPair(fixture.resp_ephemeral));
      const reply = await peer.request({ action: 'write1' });
      assert.equal(reply.message, fixture.messages[0].ciphertext);
      assert.equal(hex(await handshake.readMessage1(bytes(reply.message))), fixture.messages[0].payload);
      const message2 = await handshake.writeMessage2(bytes(fixture.messages[1].payload));
      assert.equal(hex(message2), fixture.messages[1].ciphertext);
      assert.equal((await peer.request({ action: 'read2', message: hex(message2) })).matches, true);
    }
    transport = handshake.takeTransport();
    const python = await peer.request({ action: 'split' });
    assert.equal(python.hash, fixture.handshake_hash);
    assert.equal(hex(transport.handshake_hash), fixture.handshake_hash);
    for (let index = 2; index < fixture.messages.length; index += 1) {
      const item = fixture.messages[index];
      const browserSends = (index % 2 === 0) === (browserRole === 'initiator');
      if (browserSends) {
        const encrypted = await transport.send.encrypt(bytes(item.payload));
        assert.equal(hex(encrypted), item.ciphertext);
        assert.equal((await peer.request({ action: 'vector_decrypt', index, ciphertext: hex(encrypted) })).matches, true);
      } else {
        const encrypted = await peer.request({ action: 'vector_encrypt', index });
        assert.equal(encrypted.ciphertext, item.ciphertext);
        assert.equal(hex(await transport.receive.decrypt(bytes(encrypted.ciphertext))), item.payload);
      }
    }
    for (let index = 0; index < 3; index += 1) {
      const outbound = await transport.send.encrypt(text('synthetic WebCrypto-to-Python input'), ad);
      assert.equal((await peer.request({ action: 'decrypt', ciphertext: hex(outbound) })).matches, true);
      const inbound = await peer.request({ action: 'encrypt' });
      assert.equal(new TextDecoder().decode(await transport.receive.decrypt(bytes(inbound.ciphertext), ad)), 'synthetic Python-to-WebCrypto input');
    }
    const tampered = await transport.send.encrypt(text('synthetic WebCrypto-to-Python input'), ad);
    tampered[tampered.length - 1] ^= 1;
    assert.equal((await peer.request({ action: 'decrypt', ciphertext: hex(tampered) })).rejected, true);
    const retry = await transport.send.encrypt(text('synthetic WebCrypto-to-Python input'), ad);
    assert.equal((await peer.request({ action: 'decrypt', ciphertext: hex(retry) })).rejected, true);
    assert.equal((await peer.request({ action: 'destroy' })).ok, true);
  } finally {
    transport?.destroy();
    handshake?.destroy();
    peer.close();
  }
}

const temporary = await mkdtemp(join(tmpdir(), 'agentbox-noise-interop-'));
try {
  const source = await readFile(join(root, 'apps/web/src/features/workspace/noiseNx.ts'), 'utf8');
  const result = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  });
  const modulePath = join(temporary, 'noiseNx.mjs');
  await writeFile(modulePath, result.outputText);
  const core = await import(pathToFileURL(modulePath).href);
  await exchange(core, 'initiator');
  await exchange(core, 'responder');
  process.stdout.write('Noise NX interop PASS: both roles, independent vector, AD, bidirectional transport, tamper fence\n');
} catch {
  process.stderr.write('Noise NX interop FAILED (payloads and keys omitted)\n');
  process.exitCode = 1;
} finally {
  await rm(temporary, { recursive: true, force: true });
}
