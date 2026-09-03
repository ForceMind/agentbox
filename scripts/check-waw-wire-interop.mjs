// Verify public synthetic R5 WAW wire framing against the independent Python codec.
// This check proves codec interoperability only; it has no socket, key, or admission effects.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const requireWeb = createRequire(join(root, "apps/web/package.json"));
const limit = 200_000;
const maxRequests = 256;
const text = new TextEncoder();
const hex = (value) => Buffer.from(value).toString("hex");
const bytes = (value) => new Uint8Array(Buffer.from(value, "hex"));
const equal = (left, right) => assert.deepEqual([...left], [...right]);

class Peer {
  constructor() {
    this.requests = 0;
    this.buffer = "";
    this.pending = undefined;
    this.child = spawn(
      process.env.AGENTBOX_WAW_WIRE_TEST_PYTHON ?? "python3",
      [join(root, "tests/interop/waw_wire_peer.py")],
      { cwd: root, stdio: ["pipe", "pipe", "pipe"] },
    );
    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk) => this.#receive(chunk));
    this.child.stderr.on("data", () => {});
    this.child.stdin.on("error", () => this.#fail());
    this.child.on("error", () => this.#fail());
    this.child.on("exit", () => this.#fail());
  }

  #receive(chunk) {
    this.buffer += chunk;
    const newline = this.buffer.indexOf("\n");
    if (this.buffer.length > limit || newline < 0)
      return this.buffer.length > limit && this.#fail();
    if (!this.pending || newline !== this.buffer.length - 1)
      return this.#fail();
    const pending = this.pending;
    this.pending = undefined;
    clearTimeout(pending.timer);
    try {
      const response = JSON.parse(this.buffer.slice(0, newline));
      this.buffer = "";
      pending.resolve(response);
    } catch {
      pending.reject(new Error("WAW wire test response invalid"));
      this.#fail();
    }
  }

  #fail() {
    if (this.pending) {
      clearTimeout(this.pending.timer);
      this.pending.reject(new Error("WAW wire test peer unavailable"));
      this.pending = undefined;
    }
    this.child.kill();
  }

  request(value) {
    assert.equal(this.pending, undefined);
    assert.ok(++this.requests <= maxRequests);
    const raw = JSON.stringify(value);
    assert.ok(Buffer.byteLength(raw) < limit);
    return new Promise((resolveRequest, reject) => {
      this.pending = {
        resolve: resolveRequest,
        reject,
        timer: setTimeout(() => this.#fail(), 5_000),
      };
      this.child.stdin.write(`${raw}\n`);
    });
  }

  close() {
    this.child.stdin.end();
    this.child.kill();
  }
}

const admission = Object.freeze({
  attachment_id: `att_${"1".repeat(32)}`,
  workspace_id: `aws_${"2".repeat(32)}`,
  project_id: `prj_${"3".repeat(32)}`,
  agent_type: "codex",
  runtime_host_installation_id: `wri_${"4".repeat(32)}`,
  runtime_host_installation_revision: "18446744073709551615",
  auth_epoch: "2",
  api_authority_epoch: "3",
  lease_number: "4",
  generation: "9007199254740993",
  binding_revision: "6",
  mode: "writer",
  binding_digest: "5".repeat(64),
});
const epoch = "18446744073709551615";
const base = () => ({ protocol_version: 1 });
const a = () => ({ ...admission });
const c = () => ({
  ...Object.fromEntries(
    Object.entries(admission).filter(([key]) => key !== "mode"),
  ),
  runtime_epoch: epoch,
  protocol_id: "agentbox-waw/v1",
  crypto_envelope_version: 1,
});
const lease = () => ({
  attachment_id: admission.attachment_id,
  lease_number: admission.lease_number,
});
const b64 = (length, seed) =>
  Buffer.from(
    Uint8Array.from({ length }, (_, index) => (seed + index * 29) & 0xff),
  ).toString("base64url");
const opaque = (length, seed) =>
  Uint8Array.from({ length }, (_, index) => (seed + index * 37) & 0xff);

function activeEnvelope(awce, kind, index) {
  const input = kind === 9;
  return awce.encodeAwce(
    new awce.AWCEEnvelope({
      crypto_envelope_version: 1,
      direction_id: input ? 1 : 2,
      flags: 0,
      crypto_sequence: 9_007_199_254_740_993n + BigInt(index),
      stream_cursor: input ? 0n : 9_007_199_254_740_993n + BigInt(index),
      context_id: opaque(16, index),
      ciphertext: opaque(17, index + 19),
    }),
  );
}

function payloadFor(awce, kind, index, leg) {
  if (kind === 9 || kind === 10) return activeEnvelope(awce, kind, index);
  const payload = base();
  if (kind === 1 || kind === 2) {
    Object.assign(payload, a(), {
      runtime_epoch: epoch,
      resume_cursor: null,
      previous_runtime_epoch: null,
      [kind === 1 ? "ticket" : "capability"]:
        kind === 1 ? `wat_${"6".repeat(32)}` : "6".repeat(64),
    });
  } else if (kind === 3) {
    Object.assign(payload, a(), {
      runtime_epoch: epoch,
      noise_protocol: "Noise_NX_25519_AESGCM_SHA256",
      crypto_envelope_version: 1,
      browser_ephemeral_public_key: b64(32, index),
      noise_message_1: b64(32, index + 1),
    });
  } else if (kind === 4) {
    Object.assign(payload, a(), {
      runtime_epoch: epoch,
      noise_protocol: "Noise_NX_25519_AESGCM_SHA256",
      crypto_envelope_version: 1,
      runtime_attestation_x25519_fingerprint: "7".repeat(64),
      runtime_ephemeral_public_key: b64(32, index),
      noise_message_2: b64(128, index + 1),
    });
  } else if (kind === 5 || kind === 6) {
    Object.assign(payload, c(), {
      noise_protocol: "Noise_NX_25519_AESGCM_SHA256",
      ciphertext: b64(48, index),
    });
    if (kind === 6)
      Object.assign(payload, {
        status: "verified",
        transcript_context_hash: "8".repeat(64),
      });
  } else if (kind === 7 || kind === 8 || kind === 23) {
    Object.assign(payload, a(), {
      runtime_epoch: epoch,
      state: "RUNNING",
      output_cursor: "0",
    });
    if (kind === 7)
      Object.assign(payload, { input_limit: 16384, output_limit: 32768 });
    if (kind === 8)
      Object.assign(payload, {
        lease_expires_at: "2030-02-28T12:30:59.123456Z",
      });
    if (kind === 23)
      Object.assign(payload, { admission_fence: "9".repeat(64) });
  } else if (kind === 11)
    Object.assign(payload, lease(), { columns: 80, rows: 24 });
  else if (kind === 12)
    Object.assign(payload, lease(), {
      sent_at_monotonic_tick: "9007199254740993",
    });
  else if (kind === 13)
    Object.assign(payload, {
      nonce: "a".repeat(16),
      sent_at_monotonic_tick: "9007199254740993",
    });
  else if (kind === 14)
    Object.assign(payload, {
      nonce: "a".repeat(16),
      echoed_sent_at_monotonic_tick: "9007199254740993",
    });
  else if (kind === 15) Object.assign(payload, lease());
  else if (kind === 16)
    Object.assign(payload, { state: "EXITED", exit_code: null });
  else if (kind === 17)
    Object.assign(payload, {
      from_cursor: "0",
      to_cursor: "0",
      reason: "baseline_redraw",
    });
  else if (kind === 18) {
    Object.assign(payload, {
      runtime_input_hop_sequence: "9007199254740993",
      crypto_sequence: "9007199254740993",
      result: "accepted",
      reason_code: null,
    });
    if (leg === "api-to-browser")
      Object.assign(payload, {
        browser_input_hop_sequence: "9007199254740994",
      });
  } else if (kind === 19)
    Object.assign(payload, {
      code: "PROTOCOL_INVALID",
      retryable: false,
      request_id: `wreq_${"b".repeat(32)}`,
    });
  else if (kind === 20)
    Object.assign(payload, {
      code: "PROTOCOL_INVALID",
      workspace_state_at_close: "RUNNING",
    });
  else if (kind === 21) {
    Object.assign(payload, {
      workspace_id: admission.workspace_id,
      project_id: admission.project_id,
      agent_type: "codex",
      generation: "9007199254740993",
      state: "RUNNING",
      reason_code: null,
    });
    if (leg === "runtime-to-api")
      Object.assign(payload, { runtime_epoch: epoch });
  } else if (kind === 22 || kind === 24 || kind === 25) {
    Object.assign(payload, a(), { runtime_epoch: epoch });
    if (kind === 24)
      Object.assign(payload, { admission_fence: "9".repeat(64) });
    if (kind === 25)
      Object.assign(payload, { result: "committed", reason_code: null });
  } else if (kind === 26) {
    Object.assign(payload, lease(), {
      acknowledged_hop_sequence: "9007199254740993",
      requested_columns: 80,
      requested_rows: 24,
      effective_columns: 80,
      effective_rows: 24,
      result: "applied",
      reason_code: null,
    });
  } else if (kind === 27) {
    Object.assign(payload, leg === "runtime-to-api" ? a() : lease(), {
      acknowledged_hop_sequence: "9007199254740993",
      result: "detached",
      cleanup_state: "ATTACH_PTY_CLOSED",
      reason_code: null,
    });
    if (leg === "runtime-to-api")
      Object.assign(payload, { runtime_epoch: epoch });
  } else throw new Error("fixture profile is unsupported");
  return payload;
}

function rawControl(kind, payload, hop = 1n) {
  const rawPayload =
    typeof payload === "string"
      ? text.encode(payload)
      : text.encode(JSON.stringify(payload));
  const raw = new Uint8Array(24 + rawPayload.length);
  const view = new DataView(raw.buffer);
  view.setUint32(0, 0x41425753);
  view.setUint8(4, 1);
  view.setUint8(5, kind);
  view.setUint32(8, rawPayload.length);
  view.setBigUint64(12, hop);
  raw.set(rawPayload, 24);
  return raw;
}

async function rejected(core, peer, raw, leg) {
  assert.throws(() => core.decodeWireFrame(raw, leg), core.WireError);
  assert.deepEqual(
    await peer.request({ action: "decode", leg, wire: hex(raw) }),
    { ok: false },
  );
}

async function checkProfile(core, awce, peer, leg, kind, index) {
  const payload = payloadFor(awce, kind, index, leg);
  const hop = 9_007_199_254_740_993n + BigInt(index);
  const tsWire = core.encodeWireFrame(kind, leg, payload, hop);
  const decodedByPython = await peer.request({
    action: "decode",
    leg,
    wire: hex(tsWire),
  });
  assert.deepEqual(decodedByPython, {
    ok: true,
    payload: hex(tsWire.slice(24)),
  });

  const encodedByPython = await peer.request({
    action: "encode",
    frame_type: kind,
    leg,
    hop: hop.toString(),
    payload: payload instanceof Uint8Array ? hex(payload) : payload,
  });
  assert.equal(encodedByPython.ok, true);
  const pythonWire = bytes(encodedByPython.wire);
  const decodedByTs = core.decodeWireFrame(pythonWire, leg);
  equal(decodedByTs.payload, pythonWire.slice(24));
  if (payload instanceof Uint8Array) equal(decodedByTs.payload, payload);
  else assert.deepEqual(decodedByTs.jsonPayload, payload);
}

async function checkForwarding(core, awce, peer) {
  for (const [kind, source, target, hop] of [
    [3, "browser-to-api", "api-to-runtime", 72n],
    [4, "runtime-to-api", "api-to-browser", 73n],
    [9, "browser-to-api", "api-to-runtime", 74n],
    [10, "runtime-to-api", "api-to-browser", 75n],
  ]) {
    const sourceWire = core.encodeWireFrame(
      kind,
      source,
      payloadFor(awce, kind, Number(hop), source),
      7n,
    );
    const sourceFrame = core.decodeWireFrame(sourceWire, source);
    const forwardedByTs = core.forwardWireFrame(sourceFrame, target, hop);
    equal(forwardedByTs.slice(0, 12), sourceWire.slice(0, 12));
    equal(forwardedByTs.slice(20), sourceWire.slice(20));
    assert.notEqual(
      hex(forwardedByTs.slice(12, 20)),
      hex(sourceWire.slice(12, 20)),
    );
    assert.deepEqual(
      await peer.request({
        action: "forward",
        source_leg: source,
        target_leg: target,
        hop: hop.toString(),
        wire: hex(sourceWire),
      }),
      { ok: true, wire: hex(forwardedByTs) },
    );
  }

  const original = payloadFor(awce, 3, 91, "browser-to-api");
  const pretty = ` \n${JSON.stringify(original, null, 2)}\t`;
  const sourceWire = rawControl(3, pretty, 8n);
  const sourceFrame = core.decodeWireFrame(sourceWire, "browser-to-api");
  const forwardedByTs = core.forwardWireFrame(
    sourceFrame,
    "api-to-runtime",
    92n,
  );
  equal(sourceFrame.payload, text.encode(pretty));
  equal(forwardedByTs.slice(20), sourceWire.slice(20));
  assert.deepEqual(
    await peer.request({
      action: "forward",
      source_leg: "browser-to-api",
      target_leg: "api-to-runtime",
      hop: "92",
      wire: hex(sourceWire),
    }),
    { ok: true, wire: hex(forwardedByTs) },
  );
}

async function checkRejections(core, peer) {
  const error = payloadFor(null, 19, 0, "api-to-browser");
  const valid = rawControl(19, error);
  const duplicate = JSON.stringify(error).replace(
    "{",
    '{"protocol_version":1,',
  );
  const escapedDuplicate = JSON.stringify(error).replace(
    "{",
    '{"\\u0070rotocol_version":1,',
  );
  const surrogate = JSON.stringify(error).replace(
    "PROTOCOL_INVALID",
    "\\ud800",
  );
  const resize = payloadFor(null, 11, 0, "browser-to-api");
  const hugeExponent = JSON.stringify(resize).replace(
    '"columns":80',
    '"columns":8e9999999',
  );
  const unknown = { ...error, unknown: true };
  const invalid = [
    [rawControl(19, unknown), "api-to-browser"],
    [rawControl(19, duplicate), "api-to-browser"],
    [rawControl(19, escapedDuplicate), "api-to-browser"],
    [rawControl(19, surrogate), "api-to-browser"],
    [rawControl(11, hugeExponent), "browser-to-api"],
    [new Uint8Array([...valid, 0]), "api-to-browser"],
    [rawControl(2, { protocol_version: 1 }), "browser-to-api"],
    [valid.slice(0, -1), "api-to-browser"],
  ];
  for (const [raw, leg] of invalid) await rejected(core, peer, raw, leg);
}

async function main() {
  const ts = requireWeb("typescript");
  const fixture = JSON.parse(
    await readFile(
      join(root, "tests/fixtures/waw_wire/interop-cases.json"),
      "utf8",
    ),
  );
  assert.equal(fixture.schema_version, 1);
  assert.equal(fixture.profiles.length, 50);
  assert.equal(
    new Set(fixture.profiles.map(([leg, kind]) => `${leg}/${kind}`)).size,
    50,
  );
  const temporary = await mkdtemp(join(tmpdir(), "agentbox-waw-wire-interop-"));
  let peer;
  try {
    for (const name of ["awce", "wawCryptoContext", "wawWire"]) {
      const source = await readFile(
        join(root, `apps/web/src/features/workspace/${name}.ts`),
        "utf8",
      );
      const compiled = ts
        .transpileModule(source, {
          compilerOptions: {
            target: ts.ScriptTarget.ES2022,
            module: ts.ModuleKind.ES2022,
          },
        })
        .outputText.replace(
          /(from\s+['"])(\.\/(?:awce|wawCryptoContext))(['"])/g,
          "$1$2.mjs$3",
        );
      await writeFile(join(temporary, `${name}.mjs`), compiled);
    }
    const core = await import(
      pathToFileURL(join(temporary, "wawWire.mjs")).href
    );
    const awce = await import(pathToFileURL(join(temporary, "awce.mjs")).href);
    peer = new Peer();
    // These use the product's actual elapsed-clock budget on all four legs. They
    // are deliberately separate from the complete structural matrix below and
    // are not a benchmark.
    const actualClockProfiles = fixture.profiles.filter(
      ([leg, kind]) =>
        (leg === "browser-to-api" && kind === 1) ||
        (leg === "api-to-browser" && kind === 4) ||
        (leg === "api-to-runtime" && kind === 2) ||
        (leg === "runtime-to-api" && kind === 7),
    );
    assert.equal(actualClockProfiles.length, 4);
    for (const [index, [leg, kind]] of actualClockProfiles.entries())
      await checkProfile(core, awce, peer, leg, kind, index + 1);

    const nativePerformance = Object.getOwnPropertyDescriptor(
      globalThis,
      "performance",
    );
    try {
      // Wire codecs retain their 5ms product budget. A deterministic clock makes
      // the full fixture a schema/framing interop test, not a timing assertion.
      Object.defineProperty(globalThis, "performance", {
        configurable: true,
        value: { now: () => 0 },
      });
      for (const [index, [leg, kind]] of fixture.profiles.entries())
        await checkProfile(core, awce, peer, leg, kind, index + 1);
      await checkForwarding(core, awce, peer);
      await checkRejections(core, peer);
    } finally {
      if (nativePerformance)
        Object.defineProperty(globalThis, "performance", nativePerformance);
      else delete globalThis.performance;
    }
    process.stdout.write(
      "WAW wire interop PASS: 4 actual-clock probes; 50 controlled-clock direction/type profiles, bidirectional codec payloads, opaque relay, raw key JSON forwarding, and shared rejection fences\n",
    );
  } finally {
    peer?.close();
    await rm(temporary, { recursive: true, force: true });
  }
}

try {
  await main();
} catch {
  process.stderr.write(
    "WAW wire interop FAILED (public synthetic payloads omitted)\n",
  );
  process.exitCode = 1;
}
