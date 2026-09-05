import { describe, expect, it } from 'vitest'

import { AWCEEnvelope, INPUT_DIRECTION, encodeAwce } from './awce'
import type { KeyFrame } from './wawCryptoProfile'
import { validateAdmission } from './wawCryptoContext'
import type { WAWTrustAuthorizationLease } from './wawTrustProvider'
import { FrameType, Leg, encodeWireFrame, type WireRecord } from './wawWire'
import {
  WAWBrowserController,
  WAWBrowserControllerError,
  WAW_BROWSER_SUBPROTOCOL,
  type WAWBrowserContextLease,
  type WAWBrowserCryptoPort,
  type WAWBrowserSocketHandlers,
  type WAWBrowserSocketPort,
  type WAWBrowserTicket,
} from './wawBrowserController'

const ORIGIN = 'https://agentbox.test'
const TICKET: WAWBrowserTicket = {
  protocol_version: 1,
  ticket: `wat_${'a'.repeat(32)}`,
  attachment_id: `att_${'1'.repeat(32)}`,
  workspace_id: `aws_${'2'.repeat(32)}`,
  project_id: `prj_${'3'.repeat(32)}`,
  agent_type: 'codex',
  runtime_host_installation_id: `wri_${'4'.repeat(32)}`,
  runtime_host_installation_revision: '1',
  auth_epoch: '2',
  api_authority_epoch: '3',
  lease_number: '4',
  generation: '5',
  binding_revision: '6',
  binding_digest: '5'.repeat(64),
  mode: 'writer',
  runtime_epoch: '7',
}

const B64_32 = 'A'.repeat(43)
const B64_48 = 'A'.repeat(64)
const B64_128 = 'A'.repeat(171)

const admission = {
  attachment_id: TICKET.attachment_id,
  workspace_id: TICKET.workspace_id,
  project_id: TICKET.project_id,
  agent_type: TICKET.agent_type,
  runtime_host_installation_id: TICKET.runtime_host_installation_id,
  runtime_host_installation_revision: TICKET.runtime_host_installation_revision,
  auth_epoch: TICKET.auth_epoch,
  api_authority_epoch: TICKET.api_authority_epoch,
  lease_number: TICKET.lease_number,
  generation: TICKET.generation,
  binding_revision: TICKET.binding_revision,
  mode: TICKET.mode,
  binding_digest: TICKET.binding_digest,
} as const
const handshakeContext = {
  attachment_id: admission.attachment_id,
  workspace_id: admission.workspace_id,
  project_id: admission.project_id,
  agent_type: admission.agent_type,
  runtime_host_installation_id: admission.runtime_host_installation_id,
  runtime_host_installation_revision:
    admission.runtime_host_installation_revision,
  auth_epoch: admission.auth_epoch,
  api_authority_epoch: admission.api_authority_epoch,
  lease_number: admission.lease_number,
  generation: admission.generation,
  binding_revision: admission.binding_revision,
  binding_digest: admission.binding_digest,
} as const

function keyInit(): KeyFrame {
  return {
    protocol_version: 1,
    ...admission,
    runtime_epoch: TICKET.runtime_epoch,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    crypto_envelope_version: 1,
    browser_ephemeral_public_key: B64_32,
    noise_message_1: B64_32,
  }
}

function keyConfirm(): KeyFrame {
  return {
    protocol_version: 1,
    ...handshakeContext,
    runtime_epoch: TICKET.runtime_epoch,
    protocol_id: 'agentbox-waw/v1',
    crypto_envelope_version: 1,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    ciphertext: B64_48,
  }
}

function keyAttest(): WireRecord {
  return {
    protocol_version: 1,
    ...admission,
    runtime_epoch: TICKET.runtime_epoch,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    crypto_envelope_version: 1,
    runtime_attestation_x25519_fingerprint: '7'.repeat(64),
    runtime_ephemeral_public_key: B64_32,
    noise_message_2: B64_128,
  }
}

function keyConfirmAck(): WireRecord {
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
    runtime_epoch: TICKET.runtime_epoch,
    state: 'RUNNING',
    output_cursor: '0',
    lease_expires_at: '2030-01-01T00:00:00.000000Z',
  }
}

function inputEnvelope(): Uint8Array {
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

function rejectedInputAck(): WireRecord {
  return {
    protocol_version: 1,
    runtime_input_hop_sequence: '1',
    crypto_sequence: '1',
    result: 'rejected',
    reason_code: 'ATTACHMENT_STALE',
    browser_input_hop_sequence: '4',
  }
}

function hello(): WireRecord {
  return {
    protocol_version: 1,
    ...admission,
    runtime_epoch: TICKET.runtime_epoch,
    resume_cursor: null,
    previous_runtime_epoch: null,
    ticket: TICKET.ticket,
  }
}

class FakeSocket implements WAWBrowserSocketPort {
  binaryType = 'arraybuffer' as const
  readonly readyState = 1
  readonly bufferedAmount = 0
  readonly protocol = WAW_BROWSER_SUBPROTOCOL
  readonly sent: Uint8Array[] = []
  closed = false
  #handlers: WAWBrowserSocketHandlers | null = null

  subscribe(handlers: WAWBrowserSocketHandlers): () => void {
    this.#handlers = handlers
    return () => {
      this.#handlers = null
    }
  }

  send(bytes: Uint8Array): void {
    this.sent.push(new Uint8Array(bytes))
  }

  close(): void {
    this.closed = true
  }

  open(): void {
    this.#handlers?.open()
  }

  message(bytes: Uint8Array): void {
    this.#handlers?.message(bytes.buffer.slice(0))
  }
}

class FakeCrypto implements WAWBrowserCryptoPort {
  state = 'WAIT_ATTEST'
  destroyed = false

  async writeKeyInit(): Promise<KeyFrame> {
    return keyInit()
  }

  async readKeyAttest(): Promise<KeyFrame> {
    this.state = 'WAIT_ACK'
    return keyConfirm()
  }

  async readKeyConfirmAck(): Promise<void> {
    this.state = 'VERIFIED'
  }

  async encryptInput(): Promise<Uint8Array> {
    return inputEnvelope()
  }

  async decryptOutput(): Promise<Uint8Array> {
    throw new Error('output is outside this handshake fixture')
  }

  destroy(): void {
    this.destroyed = true
    this.state = 'CLOSED'
  }
}

function context(): WAWBrowserContextLease & {
  readonly aborter: AbortController
} {
  const aborter = new AbortController()
  return {
    aborter,
    signal: aborter.signal,
    isCurrent: () => !aborter.signal.aborted,
  }
}

function trust(): WAWTrustAuthorizationLease & {
  readonly aborter: AbortController
} {
  const aborter = new AbortController()
  return {
    aborter,
    generation: 1,
    signal: aborter.signal,
    isCurrent: () => !aborter.signal.aborted,
    schema_version: 'waw-runtime-pin.v1',
    repository: 'ForceMind/agentbox',
    origin: ORIGIN,
    pin_revision: 1,
    runtime_host_installation_id: TICKET.runtime_host_installation_id,
    runtime_host_installation_revision: 1,
    runtime_attestation_x25519_fingerprint: '7'.repeat(64),
    valid_from: '2026-01-01T00:00:00Z',
    valid_until: '2030-01-01T00:00:00Z',
    key_id: 'test-key',
  }
}

async function settle(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

function apiFrame(type: FrameType, body: WireRecord, hop: bigint): Uint8Array {
  return encodeWireFrame(type, Leg.API_TO_BROWSER, body, hop, {
    admission,
    runtimeEpoch: TICKET.runtime_epoch,
  })
}

function controllerFixture(detachFails = false): {
  readonly controller: WAWBrowserController
  readonly socket: FakeSocket
  readonly lease: ReturnType<typeof trust>
  readonly controls: { detachCalls: number; stopCalls: number }
} {
  const socket = new FakeSocket()
  const lease = trust()
  const controls = { detachCalls: 0, stopCalls: 0 }
  const controller = new WAWBrowserController({
    origin: ORIGIN,
    tickets: { issue: async () => TICKET },
    trust: { authorize: async () => lease },
    controls: {
      detach: async () => {
        controls.detachCalls += 1
        if (detachFails) throw new Error('detach failed')
        return {
          workspace_id: TICKET.workspace_id,
          attachment_id: TICKET.attachment_id,
          generation: TICKET.generation,
          lease_number: TICKET.lease_number,
          result: 'detached',
          cleanup_state: 'ATTACH_PTY_CLOSED',
        }
      },
      stop: async () => {
        controls.stopCalls += 1
        return {
          workspace_id: TICKET.workspace_id,
          project_id: TICKET.project_id,
          agent_type: TICKET.agent_type,
          generation: TICKET.generation,
          state: 'STOPPED',
        }
      },
    },
    terminal: {
      create: () => ({
        enqueueFrame: async () => undefined,
        resize: () => undefined,
        cancelAttachment: () => undefined,
      }),
    },
    sockets: { create: () => socket },
    crypto: { create: () => new FakeCrypto() },
    now: () => 1,
    schedule: () => () => undefined,
  })
  return { controller, socket, lease, controls }
}

async function connect(
  fixture: ReturnType<typeof controllerFixture>,
): Promise<void> {
  const requestContext = context()
  const pending = fixture.controller.connect({
    projectId: TICKET.project_id,
    workspaceId: TICKET.workspace_id,
    agentType: TICKET.agent_type,
    generation: TICKET.generation,
    reconnect: false,
    context: requestContext,
  })
  await settle()
  fixture.socket.open()
  await settle()
  fixture.socket.message(apiFrame(FrameType.KEY_ATTEST, keyAttest(), 1n))
  await settle()
  fixture.socket.message(
    apiFrame(FrameType.KEY_CONFIRM_ACK, keyConfirmAck(), 2n),
  )
  await settle()
  fixture.socket.message(apiFrame(FrameType.ADMITTED, admitted(), 3n))
  await pending
}

describe('WAWBrowserController', () => {
  it('uses wire-valid fixture frames', () => {
    expect(() => validateAdmission(admission)).not.toThrow()
    expect(() =>
      encodeWireFrame(FrameType.WS_HELLO, Leg.BROWSER_TO_API, hello(), 1n),
    ).not.toThrow()
    expect(() =>
      encodeWireFrame(FrameType.WS_HELLO, Leg.BROWSER_TO_API, hello(), 1n, {
        admission,
        runtimeEpoch: TICKET.runtime_epoch,
      }),
    ).not.toThrow()
    expect(() =>
      encodeWireFrame(FrameType.KEY_INIT, Leg.BROWSER_TO_API, keyInit(), 2n, {
        admission,
        runtimeEpoch: TICKET.runtime_epoch,
      }),
    ).not.toThrow()
    expect(() => apiFrame(FrameType.KEY_ATTEST, keyAttest(), 1n)).not.toThrow()
    expect(() =>
      encodeWireFrame(
        FrameType.KEY_CONFIRM,
        Leg.BROWSER_TO_API,
        keyConfirm(),
        3n,
        { admission, runtimeEpoch: TICKET.runtime_epoch },
      ),
    ).not.toThrow()
    expect(() =>
      apiFrame(FrameType.KEY_CONFIRM_ACK, keyConfirmAck(), 2n),
    ).not.toThrow()
    expect(() => apiFrame(FrameType.ADMITTED, admitted(), 3n)).not.toThrow()
  })

  it('does not publish CONNECTED before local canary verification and ADMITTED', async () => {
    const fixture = controllerFixture()
    const requestContext = context()
    const pending = fixture.controller.connect({
      projectId: TICKET.project_id,
      workspaceId: TICKET.workspace_id,
      agentType: TICKET.agent_type,
      generation: TICKET.generation,
      reconnect: false,
      context: requestContext,
    })
    void pending.catch(() => undefined)
    await settle()
    fixture.socket.open()
    await settle()
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'HANDSHAKING',
      reason: null,
    })
    expect(fixture.socket.sent).toHaveLength(2)

    fixture.socket.message(apiFrame(FrameType.KEY_ATTEST, keyAttest(), 1n))
    await settle()
    expect(fixture.controller.snapshot.status).toBe('HANDSHAKING')

    fixture.socket.message(
      apiFrame(FrameType.KEY_CONFIRM_ACK, keyConfirmAck(), 2n),
    )
    await settle()
    expect(fixture.controller.snapshot.status).toBe('HANDSHAKING')

    fixture.socket.message(apiFrame(FrameType.ADMITTED, admitted(), 3n))
    await pending
    expect(fixture.controller.snapshot.status).toBe('CONNECTED')
    expect(fixture.controller.snapshot.outputCursor).toBe('0')
  })

  it('fences immediately when its independent trust lease is lost', async () => {
    const fixture = controllerFixture()
    const requestContext = context()
    const pending = fixture.controller.connect({
      projectId: TICKET.project_id,
      workspaceId: TICKET.workspace_id,
      agentType: TICKET.agent_type,
      generation: TICKET.generation,
      reconnect: false,
      context: requestContext,
    })
    await settle()
    fixture.socket.open()
    await settle()
    fixture.lease.aborter.abort()
    await expect(pending).rejects.toMatchObject({ code: 'TRUST_LOST' })
    expect(fixture.controller.snapshot.status).toBe('FENCED')
    expect(fixture.controller.snapshot.reason).toBe('TRUST_LOST')
    expect(fixture.socket.closed).toBe(true)
  })

  it('does not send generation-bound Stop until Detach has positive cleanup proof', async () => {
    const fixture = controllerFixture(true)
    await connect(fixture)

    await expect(fixture.controller.stop()).rejects.toEqual(
      new WAWBrowserControllerError('DETACH_FAILED'),
    )
    expect(fixture.controls.detachCalls).toBe(1)
    expect(fixture.controls.stopCalls).toBe(0)
    expect(fixture.controller.snapshot.status).toBe('FENCED')
    expect(fixture.controller.snapshot.reason).toBe('DETACH_FAILED')
  })

  it('keeps one input owner and does not retry a rejected input', async () => {
    const fixture = controllerFixture()
    await connect(fixture)

    const pending = fixture.controller.sendInput(new Uint8Array([0x41]))
    await settle()
    expect(fixture.socket.sent).toHaveLength(4)
    fixture.socket.message(apiFrame(FrameType.ACK, rejectedInputAck(), 4n))
    await expect(pending).resolves.toMatchObject({
      state: 'rejected',
      browserHop: '4',
      cryptoSequence: '1',
    })
    expect(fixture.socket.sent).toHaveLength(4)
    expect(fixture.controller.snapshot.status).toBe('CONNECTED')
  })

  it('fences publication on page lifecycle and only stops after a positive detach', async () => {
    const fixture = controllerFixture()
    await connect(fixture)
    fixture.controller.handlePageLifecycle('pagehide')
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'PAGEHIDE',
    })
    expect(fixture.socket.closed).toBe(true)

    const connected = controllerFixture()
    await connect(connected)
    const result = await connected.controller.stop()
    expect(result.detachConfirmed).toBe(true)
    expect(connected.controls.detachCalls).toBe(1)
    expect(connected.controls.stopCalls).toBe(1)
    expect(connected.controller.snapshot.status).toBe('STOPPED')
  })
})
