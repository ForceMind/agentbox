import { act, renderHook } from '@testing-library/react'
import type { MutableRefObject } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type {
  WorkspaceAttachmentTicketResponse,
  WorkspaceRuntimeStatus,
} from '../../lib/contracts'
import { BrowserTerminalAttachment } from './browserTerminalRenderer'
import {
  useWAWBrowserAttachment,
  type WAWAttachmentActions,
  type WAWAttachmentDependencies,
} from './useWAWBrowserAttachment'
import {
  WAW_BROWSER_SUBPROTOCOL,
  WAWBrowserController,
  type WAWBrowserControllerOptions,
  type WAWBrowserCryptoPort,
} from './wawBrowserController'
import type { AdmissionTuple } from './wawCryptoContext'
import type { KeyFrame } from './wawCryptoProfile'
import type {
  WAWTrustAuthorizationLease,
  WAWTrustProviderPort,
} from './wawTrustProvider'
import {
  WAWRc7BrowserSocket,
  WAWRc7Checkpoints,
  WAWRc7DeferredCrypto,
  WAWRc7DeferredRenderer,
  WAWRc7FakeClock,
  createWAWRc7Gate,
  createWAWRc7Schedule,
  type WAWRc7Checkpoint,
} from './wawRc7TestHarness'
import {
  encodeAwce,
  AWCEEnvelope,
  INPUT_DIRECTION,
  OUTPUT_DIRECTION,
} from './awce'
import { encodeWireFrame, FrameType, Leg, type WireRecord } from './wawWire'

const projectId = `prj_${'1'.repeat(32)}`
const workspaceId = `aws_${'2'.repeat(32)}`
const ticket: WorkspaceAttachmentTicketResponse = {
  protocol_version: 1,
  request_id: `req_${'1'.repeat(32)}`,
  ticket: `wat_${'a'.repeat(32)}`,
  workspace_id: workspaceId,
  project_id: projectId,
  agent_type: 'codex',
  attachment_id: `att_${'3'.repeat(32)}`,
  mode: 'writer',
  lease_number: '4',
  generation: '7',
  binding_revision: '1',
  binding_digest: 'a'.repeat(64),
  auth_epoch: '5',
  api_authority_epoch: '6',
  runtime_host_installation_id: `wri_${'4'.repeat(32)}`,
  runtime_host_installation_revision: '7',
  runtime_epoch: '9',
  expires_at: '2030-01-01T00:00:00Z',
}
const runtime: WorkspaceRuntimeStatus = {
  workspace_id: workspaceId,
  project_id: projectId,
  agent_type: 'codex',
  generation: ticket.generation,
  binding_revision: ticket.binding_revision,
  binding_digest: ticket.binding_digest,
  state: 'RUNNING',
  reconciliation_state: 'authoritative',
  runtime_epoch: ticket.runtime_epoch,
  process_state: 'RUNNING',
  exit_code: null,
  attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
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

function keyConfirm(): KeyFrame {
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

function record(type: FrameType, body: WireRecord, hop: bigint): ArrayBuffer {
  const frame = encodeWireFrame(type, Leg.API_TO_BROWSER, body, hop, {
    admission,
    runtimeEpoch: ticket.runtime_epoch,
  })
  const copy = new ArrayBuffer(frame.byteLength)
  new Uint8Array(copy).set(frame)
  return copy
}

function payloadRecord(
  type: FrameType,
  payload: Uint8Array,
  hop: bigint,
): ArrayBuffer {
  const frame = encodeWireFrame(type, Leg.API_TO_BROWSER, payload, hop, {
    admission,
    runtimeEpoch: ticket.runtime_epoch,
  })
  const copy = new ArrayBuffer(frame.byteLength)
  new Uint8Array(copy).set(frame)
  return copy
}

function attestation(): WireRecord {
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

function confirmation(): WireRecord {
  return {
    ...keyConfirm(),
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

function output(): ArrayBuffer {
  const envelope = encodeAwce(
    new AWCEEnvelope({
      crypto_envelope_version: 1,
      direction_id: OUTPUT_DIRECTION,
      flags: 0,
      crypto_sequence: 1n,
      stream_cursor: 1n,
      context_id: new Uint8Array(16),
      ciphertext: new Uint8Array(17),
    }),
  )
  return payloadRecord(FrameType.OUTPUT, envelope, 4n)
}

class TestCrypto implements WAWBrowserCryptoPort {
  state = 'WAIT_ATTEST'
  destroyed = false
  #output = new Uint8Array([65])

  setOutputCanary(value: Uint8Array): void {
    this.#output.fill(0)
    this.#output = new Uint8Array(value)
  }
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
    return keyConfirm()
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
    return new Uint8Array(this.#output)
  }
  destroy(): void {
    this.destroyed = true
    this.state = 'CLOSED'
    this.#output.fill(0)
  }
}

function canaryDigest(bytes: Uint8Array): string {
  let value = 0x811c9dc5
  for (const byte of bytes) value = Math.imul(value ^ byte, 0x01000193)
  return (value >>> 0).toString(16).padStart(8, '0')
}

function generatedCanary(): Uint8Array {
  const random = new Uint8Array(1)
  globalThis.crypto.getRandomValues(random)
  return Uint8Array.of(33 + (random[0]! % 90))
}

function lease(): WAWTrustAuthorizationLease & { revoke(): void } {
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
    runtime_host_installation_revision: 7,
    runtime_attestation_x25519_fingerprint: '7'.repeat(64),
    valid_from: '2026-01-01T00:00:00Z',
    valid_until: '2030-01-01T00:00:00Z',
    key_id: 'test-key',
  }
}

type Fixture = ReturnType<typeof fixture>

function fixture(sequence: readonly WAWRc7Checkpoint[]) {
  const checkpoints = new WAWRc7Checkpoints(sequence)
  const clock = new WAWRc7FakeClock()
  const scheduled = createWAWRc7Schedule(clock)
  const socket = new WAWRc7BrowserSocket()
  const trustLease = lease()
  const crypto = new TestCrypto()
  const owners = { trustClosed: 0, providerDisposed: 0 }
  const surfaces: HTMLElement[] = []
  const controllers: WAWBrowserController[] = []
  const ticketGate = createWAWRc7Gate()
  let pendingTicket = false
  const actions: WAWAttachmentActions = {
    connect: vi.fn(async () => {
      if (pendingTicket) {
        await checkpoints.arrive('ticket-issued')
        await ticketGate.promise
      }
      return ticket
    }),
    reconnect: vi.fn(async () => ticket),
    detach: vi.fn(async () => ({
      request_id: `req_${'5'.repeat(32)}`,
      detach_operation_id: `dop_${'6'.repeat(32)}`,
      workspace_id: workspaceId,
      attachment_id: ticket.attachment_id,
      generation: ticket.generation,
      lease_number: ticket.lease_number,
      result: 'detached' as const,
      cleanup_state: 'ATTACH_PTY_CLOSED' as const,
      state: 'RUNNING',
    })),
    stop: vi.fn(async () => ({
      request_id: `req_${'7'.repeat(32)}`,
      stop_operation_id: `sop_${'8'.repeat(32)}`,
      workspace_id: workspaceId,
      project_id: projectId,
      agent_type: 'codex' as const,
      generation: ticket.generation,
      state: 'STOPPED',
    })),
  }
  const provider: WAWTrustProviderPort = {
    authority: 'independent',
    subscribeInvalidation: () => () => undefined,
    getAtomicSnapshot: async () => {
      throw new Error('test provider never reads a snapshot')
    },
    dispose: () => {
      owners.providerDisposed += 1
    },
  }
  const dependencies: WAWAttachmentDependencies = {
    providerAvailable: true,
    createProvider: () => provider,
    createTrust: () => ({
      authorize: async () => trustLease,
      close: () => {
        owners.trustClosed += 1
      },
    }),
    origin: () => 'https://agentbox.test',
    createController: (options: WAWBrowserControllerOptions) => {
      const surface = document.createElement('div')
      surfaces.push(surface)
      const controller = new WAWBrowserController({
        ...options,
        now: clock.now,
        schedule: scheduled.schedule,
        sockets: { create: () => socket },
        crypto: {
          create: () => new WAWRc7DeferredCrypto(crypto, checkpoints),
        },
        terminal: {
          create: ({ onFence }) =>
            new WAWRc7DeferredRenderer(
              new BrowserTerminalAttachment(surface, onFence),
              checkpoints,
            ),
        },
      })
      controllers.push(controller)
      return controller
    },
  }
  return {
    actions,
    checkpoints,
    clock,
    controllers,
    crypto,
    owners,
    dependencies,
    pendingTicket: () => {
      pendingTicket = true
    },
    releaseTicket: () => ticketGate.resolve(),
    scheduled,
    socket,
    surfaces,
    trustLease,
    dispose: () => ticketGate.dispose(),
  }
}

function render(fixture: Fixture) {
  const contextEpoch = { current: 1 } as MutableRefObject<number>
  const hook = renderHook(() =>
    useWAWBrowserAttachment({
      actions: fixture.actions,
      agentType: 'codex',
      authScope: 'ses_test:csrf_test',
      contextEpoch,
      generation: ticket.generation,
      projectId,
      runtime,
      workspaceId,
      dependencies: fixture.dependencies,
    }),
  )
  act(() => {
    hook.result.current.setSurface(document.createElement('div'))
    hook.result.current.setViewport(document.createElement('div'))
  })
  return hook
}

async function settle(): Promise<void> {
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

async function connect(fixture: Fixture, hook: ReturnType<typeof render>) {
  let pending!: Promise<void>
  act(() => {
    pending = hook.result.current.connect()
  })
  await act(async () => {
    await settle()
    fixture.socket.open(WAW_BROWSER_SUBPROTOCOL)
  })
  await fixture.checkpoints.reached('key-init')
  await act(async () => {
    fixture.checkpoints.release('key-init')
    await settle()
    fixture.socket.message(record(FrameType.KEY_ATTEST, attestation(), 1n))
  })
  await fixture.checkpoints.reached('key-attest')
  await act(async () => {
    fixture.checkpoints.release('key-attest')
    await settle()
    fixture.socket.message(
      record(FrameType.KEY_CONFIRM_ACK, confirmation(), 2n),
    )
  })
  await fixture.checkpoints.reached('key-confirm')
  expect(fixture.crypto.state).toBe('VERIFIED')
  await act(async () => {
    fixture.checkpoints.release('key-confirm')
    await settle()
    fixture.socket.message(record(FrameType.ADMITTED, admitted(), 3n))
    await pending
  })
}

function finish(
  fixture: Fixture,
  hook: ReturnType<typeof render>,
  cryptoWasCreated = true,
): void {
  act(() => hook.unmount())
  fixture.socket.assertDrained()
  fixture.scheduled.assertDrained()
  fixture.checkpoints.assertComplete()
  expectNoBrowserStorage()
  expect(
    fixture.surfaces.every((surface) => surface.childNodes.length === 0),
  ).toBe(true)
  expect(fixture.owners.trustClosed).toBeGreaterThan(0)
  if (cryptoWasCreated) expect(fixture.crypto.destroyed).toBe(true)
  fixture.dispose()
}

afterEach(() => vi.restoreAllMocks())

describe('rc7 browser lifecycle composition', () => {
  it('fences a pending ticket on pagehide and cannot revive it after its late resolution', async () => {
    const test = fixture(['ticket-issued'])
    test.pendingTicket()
    const hook = render(test)
    let pending!: Promise<void>
    act(() => {
      pending = hook.result.current.connect()
    })
    await test.checkpoints.reached('ticket-issued')
    act(() => test.checkpoints.release('ticket-issued'))
    await act(async () => {
      await settle()
      window.dispatchEvent(new Event('pagehide'))
    })
    expect(test.actions.connect).toHaveBeenCalledTimes(1)
    test.releaseTicket()
    await expect(pending).rejects.toMatchObject({ code: 'CONTEXT_CHANGED' })
    expect(test.controllers).toHaveLength(1)
    expect(test.socket.state).toBe('connecting')
    expect(hook.result.current.view.status).toBe('FENCED')
    expect(test.actions.reconnect).not.toHaveBeenCalled()
    finish(test, hook, false)
  })

  it('fences pending render and input when trust is lost, without publishing after lifecycle cleanup', async () => {
    const test = fixture([
      'key-init',
      'key-attest',
      'key-confirm',
      'output-decrypt',
      'output-render',
      'input-encrypt',
    ])
    const hook = render(test)
    await connect(test, hook)
    expect(hook.result.current.canInput).toBe(true)
    const canary = generatedCanary()
    const digest = canaryDigest(canary)
    test.crypto.setOutputCanary(canary)

    act(() => test.socket.message(output()))
    await test.checkpoints.reached('output-decrypt')
    await act(async () => {
      test.checkpoints.release('output-decrypt')
      await settle()
    })
    await test.checkpoints.reached('output-render')
    let input!: Promise<unknown>
    act(() => {
      input = test.controllers[0]!.sendInput(new Uint8Array(canary))
    })
    await test.checkpoints.reached('input-encrypt')
    await act(async () => {
      test.trustLease.revoke()
      test.checkpoints.release('output-render')
      test.checkpoints.release('input-encrypt')
      await expect(input).rejects.toMatchObject({ code: 'CONTEXT_CHANGED' })
      await settle()
    })
    expect(hook.result.current.view.status).toBe('FENCED')
    expect(hook.result.current.view.outputCursor).toBeNull()
    expect(hook.result.current.canInput).toBe(false)
    expect(
      test.surfaces.every((surface) => surface.childNodes.length === 0),
    ).toBe(true)
    expect(
      JSON.stringify({
        gates: test.checkpoints,
        socket: test.socket.sentMetadata,
      }),
    ).not.toContain(digest)
    canary.fill(0)
    finish(test, hook)
  })

  it('fences socket error/backpressure and cancels scheduled work without retaining frame data', async () => {
    const failing = fixture(['key-init', 'key-attest', 'key-confirm'])
    const failingHook = render(failing)
    await connect(failing, failingHook)
    act(() => failing.socket.error())
    await act(async () => settle())
    expect(failingHook.result.current.view.status).toBe('FENCED')
    finish(failing, failingHook)

    const pressured = fixture([
      'key-init',
      'key-attest',
      'key-confirm',
      'input-encrypt',
    ])
    const pressuredHook = render(pressured)
    await connect(pressured, pressuredHook)
    pressured.socket.setBufferedAmount(262_144)
    let input!: Promise<unknown>
    act(() => {
      input = pressured.controllers[0]!.sendInput(new Uint8Array([1]))
    })
    void input.catch(() => undefined)
    await pressured.checkpoints.reached('input-encrypt')
    await act(async () => {
      pressured.checkpoints.release('input-encrypt')
      await settle()
    })
    await expect(input).rejects.toMatchObject({ code: 'CONTEXT_CHANGED' })
    expect(pressured.controllers[0]!.snapshot.reason).toBe(
      'OUTPUT_BACKPRESSURE',
    )
    pressured.clock.advanceBy(60_000)
    pressured.scheduled.runDue()
    expect(pressuredHook.result.current.view.status).toBe('FENCED')
    finish(pressured, pressuredHook)
  })
})
