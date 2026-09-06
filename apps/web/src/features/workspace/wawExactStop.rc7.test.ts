import { afterEach, describe, expect, it } from 'vitest'

import { BrowserTerminalAttachment } from './browserTerminalRenderer'
import {
  WAW_BROWSER_SUBPROTOCOL,
  WAWBrowserController,
  type WAWBrowserContextLease,
  type WAWBrowserCryptoPort,
  type WAWBrowserStopReceipt,
} from './wawBrowserController'
import type { AdmissionTuple } from './wawCryptoContext'
import type { KeyFrame } from './wawCryptoProfile'
import type { WAWTrustAuthorizationLease } from './wawTrustProvider'
import { encodeAwce, AWCEEnvelope, INPUT_DIRECTION } from './awce'
import { FrameType, Leg, encodeWireFrame, type WireRecord } from './wawWire'
import {
  WAWRc7BrowserSocket,
  WAWRc7Checkpoints,
  WAWRc7DeferredCrypto,
  WAWRc7FakeClock,
  createWAWRc7Gate,
  createWAWRc7Schedule,
  type WAWRc7Checkpoint,
} from './wawRc7TestHarness'

const ticket = {
  protocol_version: 1 as const,
  ticket: `wat_${'a'.repeat(32)}`,
  attachment_id: `att_${'1'.repeat(32)}`,
  workspace_id: `aws_${'2'.repeat(32)}`,
  project_id: `prj_${'3'.repeat(32)}`,
  agent_type: 'codex' as const,
  runtime_host_installation_id: `wri_${'4'.repeat(32)}`,
  runtime_host_installation_revision: '1',
  auth_epoch: '2',
  api_authority_epoch: '3',
  lease_number: '4',
  generation: '5',
  binding_revision: '6',
  binding_digest: '5'.repeat(64),
  mode: 'writer' as const,
  runtime_epoch: '7',
}
const admission: AdmissionTuple = {
  attachment_id: ticket.attachment_id,
  workspace_id: ticket.workspace_id,
  project_id: ticket.project_id,
  agent_type: ticket.agent_type,
  runtime_host_installation_id: ticket.runtime_host_installation_id,
  runtime_host_installation_revision: ticket.runtime_host_installation_revision,
  auth_epoch: ticket.auth_epoch,
  api_authority_epoch: ticket.api_authority_epoch,
  lease_number: ticket.lease_number,
  generation: ticket.generation,
  binding_revision: ticket.binding_revision,
  mode: ticket.mode,
  binding_digest: ticket.binding_digest,
}
const b64_32 = 'A'.repeat(43)
const b64_48 = 'A'.repeat(64)
const b64_128 = 'A'.repeat(171)

function frame(type: FrameType, body: WireRecord, hop: bigint): ArrayBuffer {
  const bytes = encodeWireFrame(type, Leg.API_TO_BROWSER, body, hop, {
    admission,
    runtimeEpoch: ticket.runtime_epoch,
  })
  const result = new ArrayBuffer(bytes.byteLength)
  new Uint8Array(result).set(bytes)
  return result
}

function attest(): WireRecord {
  return {
    protocol_version: 1,
    ...admission,
    runtime_epoch: ticket.runtime_epoch,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    crypto_envelope_version: 1,
    runtime_attestation_x25519_fingerprint: '7'.repeat(64),
    runtime_ephemeral_public_key: b64_32,
    noise_message_2: b64_128,
  }
}

function confirm(): WireRecord {
  const { mode, ...context } = admission
  void mode
  return {
    protocol_version: 1,
    ...context,
    runtime_epoch: ticket.runtime_epoch,
    protocol_id: 'agentbox-waw/v1',
    crypto_envelope_version: 1,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    ciphertext: b64_48,
    status: 'verified',
    transcript_context_hash: '6'.repeat(64),
  }
}

function admitted(): WireRecord {
  return {
    protocol_version: 1,
    ...admission,
    runtime_epoch: ticket.runtime_epoch,
    state: 'RUNNING',
    output_cursor: '0',
    lease_expires_at: '2030-01-01T00:00:00.000000Z',
  }
}

class Crypto implements WAWBrowserCryptoPort {
  state = 'WAIT_ATTEST'
  async writeKeyInit(): Promise<KeyFrame> {
    return {
      protocol_version: 1,
      ...admission,
      runtime_epoch: ticket.runtime_epoch,
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      crypto_envelope_version: 1,
      browser_ephemeral_public_key: b64_32,
      noise_message_1: b64_32,
    }
  }
  async readKeyAttest(): Promise<KeyFrame> {
    this.state = 'WAIT_ACK'
    const { mode, ...context } = admission
    void mode
    return {
      protocol_version: 1,
      ...context,
      runtime_epoch: ticket.runtime_epoch,
      protocol_id: 'agentbox-waw/v1',
      crypto_envelope_version: 1,
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      ciphertext: b64_48,
    }
  }
  async readKeyConfirmAck(): Promise<void> {
    this.state = 'VERIFIED'
  }
  async encryptInput(): Promise<Uint8Array> {
    return encodeAwce(
      new AWCEEnvelope({
        crypto_envelope_version: 1,
        direction_id: INPUT_DIRECTION,
        flags: 0,
        crypto_sequence: 1n,
        stream_cursor: 0n,
        context_id: new Uint8Array(16),
        ciphertext: new Uint8Array(17),
      }),
    )
  }
  async decryptOutput(): Promise<Uint8Array> {
    return new Uint8Array([1])
  }
  destroy(): void {
    this.state = 'CLOSED'
  }
}

function context(): WAWBrowserContextLease & { invalidate(): void } {
  const aborter = new AbortController()
  return {
    signal: aborter.signal,
    isCurrent: () => !aborter.signal.aborted,
    invalidate: () => aborter.abort(),
  }
}

function receipt<T>() {
  let resolve: ((value: T) => void) | null = null
  const promise = new Promise<T>((accepted) => {
    resolve = accepted
  })
  return {
    promise,
    resolve(value: T) {
      const accepted = resolve
      resolve = null
      if (accepted === null) throw new Error('receipt resolver is unavailable')
      accepted(value)
    },
    dispose() {
      resolve = null
    },
  }
}

function trust(): WAWTrustAuthorizationLease & { revoke(): void } {
  const aborter = new AbortController()
  return {
    generation: 1,
    signal: aborter.signal,
    isCurrent: () => !aborter.signal.aborted,
    revoke: () => aborter.abort(),
    schema_version: 'waw-runtime-pin.v1',
    repository: 'ForceMind/agentbox',
    origin: 'https://agentbox.test',
    pin_revision: 1,
    runtime_host_installation_id: ticket.runtime_host_installation_id,
    runtime_host_installation_revision: 1,
    runtime_attestation_x25519_fingerprint: '7'.repeat(64),
    valid_from: '2026-01-01T00:00:00Z',
    valid_until: '2030-01-01T00:00:00Z',
    key_id: 'test-key',
  }
}

function fixture(checkpoints: readonly WAWRc7Checkpoint[]) {
  const gates = new WAWRc7Checkpoints(checkpoints)
  const socket = new WAWRc7BrowserSocket()
  const clock = new WAWRc7FakeClock()
  const schedule = createWAWRc7Schedule(clock)
  const lifecycle = context()
  const trustLease = trust()
  const trustOwner = { closed: false }
  const crypto = new Crypto()
  const detachGate = createWAWRc7Gate()
  const stopGate = createWAWRc7Gate()
  const detachReceipt = receipt<{
    workspace_id: string
    attachment_id: string
    generation: string
    lease_number: string
    result: 'detached'
    cleanup_state: 'ATTACH_PTY_CLOSED'
  }>()
  const stopReceipt = receipt<WAWBrowserStopReceipt>()
  const calls = { detach: 0, stop: 0, generations: [] as string[] }
  const controller = new WAWBrowserController({
    origin: 'https://agentbox.test',
    tickets: { issue: async () => ticket },
    trust: { authorize: async () => trustLease },
    controls: {
      detach: async (request) => {
        calls.detach += 1
        calls.generations.push(request.generation)
        await gates.arrive('detach-cleanup')
        await detachGate.promise
        return detachReceipt.promise
      },
      stop: async (request) => {
        calls.stop += 1
        calls.generations.push(request.generation)
        await gates.arrive('stop-request')
        await stopGate.promise
        return stopReceipt.promise
      },
    },
    sockets: { create: () => socket },
    crypto: { create: () => new WAWRc7DeferredCrypto(crypto, gates) },
    terminal: {
      create: ({ onFence }) =>
        new BrowserTerminalAttachment(document.createElement('div'), onFence),
    },
    now: clock.now,
    schedule: schedule.schedule,
  })
  return {
    gates,
    socket,
    clock,
    schedule,
    lifecycle,
    trustLease,
    crypto,
    closeTrust: () => {
      trustOwner.closed = true
    },
    trustOwner,
    detachGate,
    stopGate,
    detachReceipt,
    stopReceipt,
    calls,
    controller,
  }
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

function expectNoBrowserStorage(): void {
  const local = window.localStorage
  const session = window.sessionStorage
  if (local !== undefined) expect(local.length).toBe(0)
  if (session !== undefined) expect(session.length).toBe(0)
}

async function connected(test: ReturnType<typeof fixture>): Promise<void> {
  const pending = test.controller.connect({
    projectId: ticket.project_id,
    workspaceId: ticket.workspace_id,
    agentType: ticket.agent_type,
    generation: ticket.generation,
    reconnect: false,
    context: test.lifecycle,
  })
  await settle()
  test.socket.open(WAW_BROWSER_SUBPROTOCOL)
  await test.gates.reached('key-init')
  test.gates.release('key-init')
  await settle()
  test.socket.message(frame(FrameType.KEY_ATTEST, attest(), 1n))
  await test.gates.reached('key-attest')
  test.gates.release('key-attest')
  await settle()
  test.socket.message(frame(FrameType.KEY_CONFIRM_ACK, confirm(), 2n))
  await test.gates.reached('key-confirm')
  expect(test.crypto.state).toBe('VERIFIED')
  test.gates.release('key-confirm')
  await settle()
  test.socket.message(frame(FrameType.ADMITTED, admitted(), 3n))
  await pending
}

function request(test: ReturnType<typeof fixture>) {
  return {
    projectId: ticket.project_id,
    workspaceId: ticket.workspace_id,
    agentType: ticket.agent_type,
    generation: ticket.generation,
    context: test.lifecycle,
  }
}

afterEach(() => undefined)

describe('rc7 exact Stop failure injection', () => {
  it('does not send Stop before positive detach proof and late detach cannot revive after pagehide', async () => {
    const test = fixture([
      'key-init',
      'key-attest',
      'key-confirm',
      'detach-cleanup',
    ])
    await connected(test)
    const pending = test.controller.stop(request(test))
    await test.gates.reached('detach-cleanup')
    expect(test.calls).toMatchObject({
      detach: 1,
      stop: 0,
      generations: [ticket.generation],
    })
    test.controller.handlePageLifecycle('pagehide')
    test.gates.release('detach-cleanup')
    test.detachGate.resolve()
    test.detachReceipt.resolve({
      workspace_id: ticket.workspace_id,
      attachment_id: ticket.attachment_id,
      generation: ticket.generation,
      lease_number: ticket.lease_number,
      result: 'detached',
      cleanup_state: 'ATTACH_PTY_CLOSED',
    })
    await settle()
    await expect(pending).rejects.toMatchObject({ code: 'CONTEXT_CHANGED' })
    expect(test.calls.stop).toBe(0)
    expect(test.controller.snapshot.status).toBe('FENCED')
    expect(test.controller.snapshot.attachment?.generation).toBe(
      ticket.generation,
    )
    await expect(
      test.controller.sendInput(new Uint8Array([1])),
    ).rejects.toMatchObject({ code: 'CONTROLLER_NOT_CONNECTED' })
    expect(() => test.controller.requestResize(80, 24)).toThrow(
      'CONTROLLER_NOT_CONNECTED',
    )
    test.gates.assertComplete()
    test.socket.assertDrained()
    test.schedule.assertDrained()
    test.closeTrust()
    expect(test.trustOwner.closed).toBe(true)
    expect(test.crypto.state).toBe('CLOSED')
    expectNoBrowserStorage()
    test.detachGate.dispose()
    test.stopGate.dispose()
    test.detachReceipt.dispose()
    test.stopReceipt.dispose()
  })

  it('does not publish STOPPED from a late Stop receipt after a page lifecycle fence', async () => {
    const test = fixture([
      'key-init',
      'key-attest',
      'key-confirm',
      'detach-cleanup',
      'stop-request',
    ])
    await connected(test)
    const pending = test.controller.stop(request(test))
    await test.gates.reached('detach-cleanup')
    test.gates.release('detach-cleanup')
    test.detachGate.resolve()
    test.detachReceipt.resolve({
      workspace_id: ticket.workspace_id,
      attachment_id: ticket.attachment_id,
      generation: ticket.generation,
      lease_number: ticket.lease_number,
      result: 'detached',
      cleanup_state: 'ATTACH_PTY_CLOSED',
    })
    await test.gates.reached('stop-request')
    expect(test.calls).toMatchObject({
      detach: 1,
      stop: 1,
      generations: [ticket.generation, ticket.generation],
    })
    test.controller.handlePageLifecycle('pagehide')
    test.gates.release('stop-request')
    test.stopGate.resolve()
    test.stopReceipt.resolve({
      workspace_id: ticket.workspace_id,
      project_id: ticket.project_id,
      agent_type: ticket.agent_type,
      generation: ticket.generation,
      state: 'STOPPED',
    })
    await settle()
    await expect(pending).rejects.toMatchObject({ code: 'CONTEXT_CHANGED' })
    expect(test.controller.snapshot.status).not.toBe('STOPPED')
    expect(test.controller.snapshot.attachment?.generation).toBe(
      ticket.generation,
    )
    expect(test.controller.snapshot.status).toBe('FENCED')
    test.gates.assertComplete()
    test.socket.assertDrained()
    test.schedule.assertDrained()
    test.closeTrust()
    expect(test.trustOwner.closed).toBe(true)
    expect(test.crypto.state).toBe('CLOSED')
    expectNoBrowserStorage()
    test.detachGate.dispose()
    test.stopGate.dispose()
    test.detachReceipt.dispose()
    test.stopReceipt.dispose()
  })
})
