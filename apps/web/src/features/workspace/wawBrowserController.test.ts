import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AWCEEnvelope,
  INPUT_DIRECTION,
  OUTPUT_DIRECTION,
  encodeAwce,
} from './awce'
import type { KeyFrame } from './wawCryptoProfile'
import { validateAdmission, type AdmissionTuple } from './wawCryptoContext'
import type { WAWTrustAuthorizationLease } from './wawTrustProvider'
import {
  FrameType,
  Leg,
  decodeWireFrame,
  encodeWireFrame,
  type WireRecord,
} from './wawWire'
import {
  WAWBrowserController,
  WAWBrowserControllerError,
  WAW_BROWSER_SUBPROTOCOL,
  type WAWBrowserContextLease,
  type WAWBrowserControlRequest,
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

beforeEach(() => {
  vi.spyOn(performance, 'now').mockReturnValue(0)
})
afterEach(() => vi.restoreAllMocks())

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
function keyInit(
  fields: AdmissionTuple = validateAdmission(admission),
  runtimeEpoch = TICKET.runtime_epoch,
): KeyFrame {
  return {
    protocol_version: 1,
    ...fields,
    runtime_epoch: runtimeEpoch,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    crypto_envelope_version: 1,
    browser_ephemeral_public_key: B64_32,
    noise_message_1: B64_32,
  }
}

function keyConfirm(
  fields: AdmissionTuple = validateAdmission(admission),
  runtimeEpoch = TICKET.runtime_epoch,
): KeyFrame {
  const { mode, ...context } = fields
  void mode
  return {
    protocol_version: 1,
    ...context,
    runtime_epoch: runtimeEpoch,
    protocol_id: 'agentbox-waw/v1',
    crypto_envelope_version: 1,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    ciphertext: B64_48,
  }
}

function keyAttest(
  fields: AdmissionTuple = validateAdmission(admission),
  runtimeEpoch = TICKET.runtime_epoch,
): WireRecord {
  return {
    protocol_version: 1,
    ...fields,
    runtime_epoch: runtimeEpoch,
    noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
    crypto_envelope_version: 1,
    runtime_attestation_x25519_fingerprint: '7'.repeat(64),
    runtime_ephemeral_public_key: B64_32,
    noise_message_2: B64_128,
  }
}

function keyConfirmAck(
  fields: AdmissionTuple = validateAdmission(admission),
  runtimeEpoch = TICKET.runtime_epoch,
): WireRecord {
  return {
    ...keyConfirm(fields, runtimeEpoch),
    status: 'verified',
    transcript_context_hash: '6'.repeat(64),
  }
}

function admitted(
  outputCursor = '0',
  fields: AdmissionTuple = validateAdmission(admission),
  runtimeEpoch = TICKET.runtime_epoch,
): WireRecord {
  return {
    protocol_version: 1,
    ...fields,
    runtime_epoch: runtimeEpoch,
    state: 'RUNNING',
    output_cursor: outputCursor,
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

function outputEnvelope(cursor = 1n): Uint8Array {
  return encodeAwce(
    new AWCEEnvelope({
      crypto_envelope_version: 1,
      direction_id: OUTPUT_DIRECTION,
      flags: 0,
      crypto_sequence: 1n,
      stream_cursor: cursor,
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

function rateLimitedInputAck(): WireRecord {
  return {
    protocol_version: 1,
    runtime_input_hop_sequence: '1',
    crypto_sequence: '1',
    result: 'rejected',
    reason_code: 'INPUT_RATE_LIMITED',
    browser_input_hop_sequence: '4',
  }
}

function acceptedInputAck(): WireRecord {
  return {
    protocol_version: 1,
    runtime_input_hop_sequence: '1',
    crypto_sequence: '1',
    result: 'accepted',
    reason_code: null,
    browser_input_hop_sequence: '4',
  }
}

function writeUncertainAck(): WireRecord {
  return {
    protocol_version: 1,
    runtime_input_hop_sequence: '1',
    crypto_sequence: '1',
    result: 'write_uncertain',
    reason_code: 'INPUT_WRITE_UNCERTAIN',
    browser_input_hop_sequence: '4',
  }
}

function baselineRedrawGap(): WireRecord {
  return {
    protocol_version: 1,
    from_cursor: '0',
    to_cursor: '0',
    reason: 'baseline_redraw',
  }
}

function appliedResizeAck(
  browserHop: bigint,
  columns = 80,
  rows = 24,
): WireRecord {
  return {
    protocol_version: 1,
    attachment_id: TICKET.attachment_id,
    lease_number: TICKET.lease_number,
    acknowledged_hop_sequence: browserHop.toString(),
    requested_columns: columns,
    requested_rows: rows,
    effective_columns: columns,
    effective_rows: rows,
    result: 'applied',
    reason_code: null,
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
  readonly protocol = WAW_BROWSER_SUBPROTOCOL
  readonly sent: Uint8Array[] = []
  closed = false
  beforeBufferedAmount: (() => void) | null = null
  #handlers: WAWBrowserSocketHandlers | null = null

  get bufferedAmount(): number {
    const before = this.beforeBufferedAmount
    this.beforeBufferedAmount = null
    before?.()
    return 0
  }

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
  output = new Uint8Array([0x41])
  deferInput = false
  #releaseInput: (() => void) | null = null

  constructor(
    readonly admissionTuple: AdmissionTuple = validateAdmission(admission),
    readonly runtimeEpoch = TICKET.runtime_epoch,
  ) {}

  async writeKeyInit(): Promise<KeyFrame> {
    return keyInit(this.admissionTuple, this.runtimeEpoch)
  }

  async readKeyAttest(): Promise<KeyFrame> {
    this.state = 'WAIT_ACK'
    return keyConfirm(this.admissionTuple, this.runtimeEpoch)
  }

  async readKeyConfirmAck(): Promise<void> {
    this.state = 'VERIFIED'
  }

  async encryptInput(): Promise<Uint8Array> {
    if (this.deferInput) {
      await new Promise<void>((resolve) => {
        this.#releaseInput = resolve
      })
    }
    return inputEnvelope()
  }

  releaseInput(): void {
    if (this.#releaseInput === null) throw new Error('input is not pending')
    this.#releaseInput()
    this.#releaseInput = null
  }

  async decryptOutput(): Promise<Uint8Array> {
    return new Uint8Array(this.output)
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

function controlRequest(
  requestContext: WAWBrowserContextLease = context(),
): WAWBrowserControlRequest {
  return {
    projectId: TICKET.project_id,
    workspaceId: TICKET.workspace_id,
    agentType: TICKET.agent_type,
    generation: TICKET.generation,
    context: requestContext,
  }
}

function trust(): WAWTrustAuthorizationLease & {
  readonly aborter: AbortController
  setCurrent(value: boolean): void
} {
  const aborter = new AbortController()
  let current = true
  return {
    aborter,
    generation: 1,
    signal: aborter.signal,
    isCurrent: () => current && !aborter.signal.aborted,
    setCurrent: (value) => {
      current = value
    },
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
  return apiFrameWithBinding(type, body, hop, validateAdmission(admission))
}

function apiFrameWithBinding(
  type: FrameType,
  body: WireRecord,
  hop: bigint,
  binding: AdmissionTuple,
  runtimeEpoch = TICKET.runtime_epoch,
): Uint8Array {
  return encodeWireFrame(type, Leg.API_TO_BROWSER, body, hop, {
    admission: binding,
    runtimeEpoch,
  })
}

function apiPayloadFrame(
  type: FrameType,
  payload: Uint8Array,
  hop: bigint,
): Uint8Array {
  return apiPayloadFrameWithBinding(
    type,
    payload,
    hop,
    validateAdmission(admission),
  )
}

function apiPayloadFrameWithBinding(
  type: FrameType,
  payload: Uint8Array,
  hop: bigint,
  binding: AdmissionTuple,
  runtimeEpoch = TICKET.runtime_epoch,
): Uint8Array {
  return encodeWireFrame(type, Leg.API_TO_BROWSER, payload, hop, {
    admission: binding,
    runtimeEpoch,
  })
}

type TerminalFixture = { frames: Uint8Array[]; cancelled: boolean }

type ControllerFixtureOptions = {
  detachAttachmentId?: string
  detachCleanupState?: string
  detachFails?: boolean
  detachGeneration?: string
  detachLeaseNumber?: string
  detachResult?: string
  detachWorkspaceId?: string
  deferDetach?: boolean
  deferRender?: boolean
  deferStop?: boolean
  freshChannels?: boolean
  manualSchedule?: boolean
  now?: () => number
  rejectRender?: boolean
  stopAgentType?: string
  stopGeneration?: string
  stopProjectId?: string
  stopWorkspaceId?: string
  stopState?: string
}

function controllerFixture(options: ControllerFixtureOptions = {}): {
  readonly controller: WAWBrowserController
  readonly socket: FakeSocket
  readonly sockets: readonly FakeSocket[]
  readonly lease: ReturnType<typeof trust>
  readonly controls: { detachCalls: number; stopCalls: number }
  readonly cryptos: readonly FakeCrypto[]
  readonly terminal: TerminalFixture
  readonly terminals: readonly TerminalFixture[]
  readonly releaseDetach: () => void
  readonly releaseRender: () => void
  readonly rejectRender: () => void
  readonly releaseStop: () => void
  readonly runNextScheduled: () => void
  readonly runLastScheduled: () => void
} {
  const lease = trust()
  const controls = { detachCalls: 0, stopCalls: 0 }
  const sockets: FakeSocket[] = []
  const cryptos: FakeCrypto[] = []
  const terminals: TerminalFixture[] = []
  const scheduled: Array<{ callback: () => void; cancelled: boolean }> = []
  let socket: FakeSocket | null = null
  let crypto: FakeCrypto | null = null
  let terminal: TerminalFixture | null = null
  let ticketCount = 0
  let releaseDetach: (() => void) | null = null
  let releaseRender: (() => void) | null = null
  let rejectRender: (() => void) | null = null
  let releaseStop: (() => void) | null = null
  const detachReceipt = {
    workspace_id: options.detachWorkspaceId ?? TICKET.workspace_id,
    attachment_id: options.detachAttachmentId ?? TICKET.attachment_id,
    generation: options.detachGeneration ?? TICKET.generation,
    lease_number: options.detachLeaseNumber ?? TICKET.lease_number,
    result: (options.detachResult ?? 'detached') as 'detached',
    cleanup_state: (options.detachCleanupState ??
      'ATTACH_PTY_CLOSED') as 'ATTACH_PTY_CLOSED',
  }
  const stopReceipt = {
    workspace_id: options.stopWorkspaceId ?? TICKET.workspace_id,
    project_id: options.stopProjectId ?? TICKET.project_id,
    agent_type: (options.stopAgentType ?? TICKET.agent_type) as
      'claude' | 'codex',
    generation: options.stopGeneration ?? TICKET.generation,
    state: options.stopState ?? 'STOPPED',
  }
  const controller = new WAWBrowserController({
    origin: ORIGIN,
    tickets: {
      issue: async () => {
        ticketCount += 1
        if (!options.freshChannels || ticketCount === 1) return TICKET
        return {
          ...TICKET,
          ticket: `wat_${'b'.repeat(32)}`,
          attachment_id: `att_${'b'.repeat(32)}`,
          lease_number: '5',
        }
      },
    },
    trust: { authorize: async () => lease },
    controls: {
      detach: async () => {
        controls.detachCalls += 1
        if (options.detachFails) throw new Error('detach failed')
        if (options.deferDetach) {
          return await new Promise<typeof detachReceipt>((resolve) => {
            releaseDetach = () => resolve(detachReceipt)
          })
        }
        return detachReceipt
      },
      stop: async () => {
        controls.stopCalls += 1
        if (options.deferStop) {
          return await new Promise<typeof stopReceipt>((resolve) => {
            releaseStop = () => resolve(stopReceipt)
          })
        }
        return stopReceipt
      },
    },
    terminal: {
      create: () => {
        terminal = { frames: [], cancelled: false }
        terminals.push(terminal)
        return {
          enqueueFrame: async (bytes) => {
            const snapshot = new Uint8Array(bytes)
            if (options.rejectRender) throw new Error('render rejected')
            if (options.deferRender) {
              await new Promise<void>((resolve, reject) => {
                releaseRender = () => {
                  terminal!.frames.push(snapshot)
                  resolve()
                }
                rejectRender = () => reject(new Error('render rejected'))
              })
              return
            }
            terminal!.frames.push(snapshot)
          },
          resize: () => undefined,
          cancelAttachment: () => {
            terminal!.cancelled = true
          },
        }
      },
    },
    sockets: {
      create: () => {
        if (socket === null || options.freshChannels) {
          socket = new FakeSocket()
          sockets.push(socket)
        }
        return socket
      },
    },
    crypto: {
      create: (nextAdmission, runtimeEpoch) => {
        if (crypto === null || options.freshChannels) {
          crypto = new FakeCrypto(nextAdmission, runtimeEpoch)
          cryptos.push(crypto)
        }
        return crypto
      },
    },
    now: options.now ?? (() => 1),
    schedule: (callback) => {
      if (!options.manualSchedule) return () => undefined
      const entry = { callback, cancelled: false }
      scheduled.push(entry)
      return () => {
        entry.cancelled = true
      }
    },
  })
  return {
    controller,
    get socket() {
      if (socket === null) throw new Error('socket is not created')
      return socket
    },
    sockets,
    lease,
    controls,
    cryptos,
    get terminal() {
      if (terminal === null) throw new Error('terminal is not created')
      return terminal
    },
    terminals,
    releaseDetach: () => {
      if (releaseDetach === null) throw new Error('detach is not pending')
      releaseDetach()
    },
    releaseRender: () => {
      if (releaseRender === null) throw new Error('render is not pending')
      releaseRender()
    },
    rejectRender: () => {
      if (rejectRender === null) throw new Error('render is not pending')
      rejectRender()
    },
    releaseStop: () => {
      if (releaseStop === null) throw new Error('stop is not pending')
      releaseStop()
    },
    runNextScheduled: () => {
      const entry = scheduled.find((candidate) => !candidate.cancelled)
      if (entry === undefined) throw new Error('no scheduled callback')
      entry.cancelled = true
      entry.callback()
    },
    runLastScheduled: () => {
      const entry = [...scheduled]
        .reverse()
        .find((candidate) => !candidate.cancelled)
      if (entry === undefined) throw new Error('no scheduled callback')
      entry.cancelled = true
      entry.callback()
    },
  }
}

async function connect(
  fixture: ReturnType<typeof controllerFixture>,
  requestContext: WAWBrowserContextLease = context(),
  outputCursor = '0',
): Promise<void> {
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
  fixture.socket.message(
    apiFrame(FrameType.ADMITTED, admitted(outputCursor), 3n),
  )
  await pending
  // ADMITTED resolves connect before the inbound queue's final continuation.
  // Drain it before a test intentionally changes page context or lifecycle.
  await settle()
  await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 0))
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
    expect(fixture.controller.snapshot.outputCursor).toBeNull()
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

  it('accepts a bounded fresh-redraw marker but advances cursor only after render', async () => {
    const fixture = controllerFixture({ deferRender: true })
    await connect(fixture, context(), '9')
    expect(fixture.controller.snapshot.outputCursor).toBeNull()

    fixture.socket.message(apiFrame(FrameType.GAP, baselineRedrawGap(), 4n))
    await settle()
    expect(fixture.controller.snapshot.status).toBe('CONNECTED')
    expect(fixture.controller.snapshot.outputCursor).toBeNull()
    expect(fixture.controller.snapshot.freshRedrawTruncated).toBe(true)

    fixture.socket.message(
      apiPayloadFrame(FrameType.OUTPUT, outputEnvelope(1n), 5n),
    )
    await settle()
    expect(fixture.terminal.frames).toHaveLength(0)
    expect(fixture.controller.snapshot.outputCursor).toBeNull()
    fixture.releaseRender()
    await settle()
    await settle()
    expect(fixture.terminal.frames).toHaveLength(1)
    expect(fixture.controller.snapshot.outputCursor).toBe('1')
  })

  it('fences a renderer rejection without advancing the output cursor', async () => {
    const fixture = controllerFixture({ rejectRender: true })
    await connect(fixture)
    fixture.socket.message(
      apiPayloadFrame(FrameType.OUTPUT, outputEnvelope(1n), 4n),
    )
    await settle()
    await settle()
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'OUTPUT_RENDER_FAILED',
      outputCursor: null,
    })
  })

  it('reports trust loss when trust becomes stale while a renderer is pending', async () => {
    const fixture = controllerFixture({ deferRender: true })
    await connect(fixture)
    fixture.socket.message(
      apiPayloadFrame(FrameType.OUTPUT, outputEnvelope(1n), 4n),
    )
    await settle()
    fixture.lease.setCurrent(false)
    fixture.releaseRender()
    await settle()
    await settle()
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'TRUST_LOST',
      outputCursor: null,
    })
  })

  it('fences every GAP except one initial bounded fresh-redraw marker', async () => {
    const fixture = controllerFixture()
    await connect(fixture)
    fixture.socket.message(apiFrame(FrameType.GAP, baselineRedrawGap(), 4n))
    await settle()
    fixture.socket.message(apiFrame(FrameType.GAP, baselineRedrawGap(), 5n))
    await settle()
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'OUTPUT_GAP',
    })

    const ordinary = controllerFixture()
    await connect(ordinary)
    ordinary.socket.message(
      apiFrame(
        FrameType.GAP,
        {
          protocol_version: 1,
          from_cursor: '1',
          to_cursor: '2',
          reason: 'ring_overflow',
        },
        4n,
      ),
    )
    await settle()
    expect(ordinary.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'OUTPUT_GAP',
    })

    const afterOutput = controllerFixture()
    await connect(afterOutput)
    afterOutput.socket.message(
      apiPayloadFrame(FrameType.OUTPUT, outputEnvelope(1n), 4n),
    )
    await settle()
    await settle()
    afterOutput.socket.message(apiFrame(FrameType.GAP, baselineRedrawGap(), 5n))
    await settle()
    expect(afterOutput.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'OUTPUT_GAP',
    })
  })

  it('always requests a fresh redraw after detach instead of reusing a destroyed model cursor', async () => {
    const fixture = controllerFixture({ freshChannels: true })
    await connect(fixture)
    const firstSocket = fixture.socket
    const firstCrypto = fixture.cryptos[0]
    const firstTerminal = fixture.terminal
    firstSocket.message(
      apiPayloadFrame(FrameType.OUTPUT, outputEnvelope(1n), 4n),
    )
    await settle()
    await settle()
    expect(fixture.controller.snapshot.outputCursor).toBe('1')
    await fixture.controller.detach(controlRequest())
    expect(firstSocket.closed).toBe(true)
    expect(firstCrypto.destroyed).toBe(true)
    expect(firstTerminal.cancelled).toBe(true)

    const reconnectContext = context()
    const pending = fixture.controller.connect({
      projectId: TICKET.project_id,
      workspaceId: TICKET.workspace_id,
      agentType: TICKET.agent_type,
      generation: TICKET.generation,
      reconnect: true,
      context: reconnectContext,
    })
    await settle()
    fixture.socket.open()
    await settle()
    const hello = decodeWireFrame(
      fixture.socket.sent[0],
      Leg.BROWSER_TO_API,
    ).jsonPayload
    expect(hello).toMatchObject({
      resume_cursor: null,
      previous_runtime_epoch: null,
    })
    expect(fixture.sockets).toHaveLength(2)
    expect(fixture.cryptos).toHaveLength(2)
    expect(fixture.terminals).toHaveLength(2)
    expect(fixture.controller.snapshot.attachment?.attachmentId).toBe(
      `att_${'b'.repeat(32)}`,
    )
    const secondAdmission = validateAdmission({
      ...admission,
      attachment_id: `att_${'b'.repeat(32)}`,
      lease_number: '5',
    })
    fixture.socket.message(
      apiFrameWithBinding(
        FrameType.KEY_ATTEST,
        keyAttest(secondAdmission),
        1n,
        secondAdmission,
      ),
    )
    await settle()
    fixture.socket.message(
      apiFrameWithBinding(
        FrameType.KEY_CONFIRM_ACK,
        keyConfirmAck(secondAdmission),
        2n,
        secondAdmission,
      ),
    )
    await settle()
    fixture.socket.message(
      apiFrameWithBinding(
        FrameType.ADMITTED,
        admitted('9', secondAdmission),
        3n,
        secondAdmission,
      ),
    )
    await pending
    expect(fixture.controller.snapshot.status).toBe('CONNECTED')
    expect(fixture.controller.snapshot.outputCursor).toBeNull()
    fixture.socket.message(
      apiPayloadFrameWithBinding(
        FrameType.OUTPUT,
        outputEnvelope(1n),
        4n,
        secondAdmission,
      ),
    )
    await settle()
    await settle()
    expect(fixture.terminals[0].frames).toHaveLength(1)
    expect(fixture.terminals[1].frames).toHaveLength(1)
    expect(fixture.controller.snapshot.outputCursor).toBe('1')
  })

  it('does not send generation-bound Stop until Detach has positive cleanup proof', async () => {
    const fixture = controllerFixture({ detachFails: true })
    await connect(fixture)

    await expect(fixture.controller.stop(controlRequest())).rejects.toEqual(
      new WAWBrowserControllerError('DETACH_FAILED'),
    )
    expect(fixture.controls.detachCalls).toBe(1)
    expect(fixture.controls.stopCalls).toBe(0)
    expect(fixture.controller.snapshot.status).toBe('FENCED')
    expect(fixture.controller.snapshot.reason).toBe('DETACH_FAILED')
  })

  it('does not send Stop when a Detach receipt has an invalid cleanup proof', async () => {
    const fixture = controllerFixture({
      detachCleanupState: 'ATTACH_PTY_CLOSE_UNCERTAIN',
    })
    await connect(fixture)
    await expect(fixture.controller.stop(controlRequest())).rejects.toEqual(
      new WAWBrowserControllerError('DETACH_FAILED'),
    )
    expect(fixture.controls.stopCalls).toBe(0)
  })

  it('rejects each independently mutated Detach receipt field', async () => {
    const mutations: readonly ControllerFixtureOptions[] = [
      { detachWorkspaceId: `aws_${'c'.repeat(32)}` },
      { detachAttachmentId: `att_${'c'.repeat(32)}` },
      { detachGeneration: '6' },
      { detachLeaseNumber: '6' },
      { detachResult: 'rejected' },
      { detachCleanupState: 'ATTACH_PTY_CLOSE_UNCERTAIN' },
    ]
    for (const mutation of mutations) {
      const fixture = controllerFixture(mutation)
      await connect(fixture)
      await expect(fixture.controller.detach(controlRequest())).rejects.toEqual(
        new WAWBrowserControllerError('DETACH_FAILED'),
      )
      await settle()
      expect(fixture.controller.snapshot).toMatchObject({
        status: 'FENCED',
        reason: 'DETACH_FAILED',
      })
    }
  })

  it('fences after a terminal input rejection and does not retry it', async () => {
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
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'INPUT_REJECTED',
    })
  })

  it('fences before resolving an uncertain input outcome', async () => {
    const fixture = controllerFixture()
    await connect(fixture)

    const pending = fixture.controller.sendInput(new Uint8Array([0x41]))
    await settle()
    fixture.socket.message(apiFrame(FrameType.ACK, acceptedInputAck(), 4n))
    await settle()
    fixture.socket.message(apiFrame(FrameType.ACK, writeUncertainAck(), 5n))
    await expect(pending).resolves.toMatchObject({
      state: 'write_uncertain',
      reasonCode: 'INPUT_WRITE_UNCERTAIN',
    })
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'INPUT_UNCERTAIN',
    })
    await expect(
      fixture.controller.sendInput(new Uint8Array([0x42])),
    ).rejects.toEqual(new WAWBrowserControllerError('CONTROLLER_NOT_CONNECTED'))
  })

  it('keeps the channel open only for a rate-limited rejected input', async () => {
    const fixture = controllerFixture()
    await connect(fixture)
    const pending = fixture.controller.sendInput(new Uint8Array([0x41]))
    await settle()
    fixture.socket.message(apiFrame(FrameType.ACK, rateLimitedInputAck(), 4n))
    await expect(pending).resolves.toMatchObject({
      state: 'rejected',
      reasonCode: 'INPUT_RATE_LIMITED',
    })
    expect(fixture.controller.snapshot.status).toBe('CONNECTED')
  })

  it('rechecks context at the final resize publication boundary', async () => {
    const fixture = controllerFixture()
    const aborter = new AbortController()
    let live = true
    const requestContext: WAWBrowserContextLease = {
      signal: aborter.signal,
      isCurrent: () => live,
    }
    await connect(fixture, requestContext)
    const sent = fixture.socket.sent.length
    fixture.socket.beforeBufferedAmount = () => {
      live = false
    }

    expect(() => fixture.controller.requestResize(80, 24)).toThrow(
      new WAWBrowserControllerError('CONTEXT_CHANGED'),
    )
    expect(fixture.socket.sent).toHaveLength(sent)
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'CONTEXT_CHANGED',
    })
  })

  it('does not publish input after deferred encryption observes stale context', async () => {
    const fixture = controllerFixture()
    const aborter = new AbortController()
    let live = true
    const requestContext: WAWBrowserContextLease = {
      signal: aborter.signal,
      isCurrent: () => live,
    }
    await connect(fixture, requestContext)
    fixture.cryptos[0].deferInput = true
    const sent = fixture.socket.sent.length
    const pending = fixture.controller.sendInput(new Uint8Array([0x41]))
    await settle()
    live = false
    fixture.cryptos[0].releaseInput()
    await expect(pending).rejects.toEqual(
      new WAWBrowserControllerError('CONTEXT_CHANGED'),
    )
    expect(fixture.socket.sent).toHaveLength(sent)
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'CONTEXT_CHANGED',
    })
  })

  it('does not publish heartbeat after trust becomes stale without an abort event', async () => {
    const fixture = controllerFixture({ manualSchedule: true })
    await connect(fixture)
    const sent = fixture.socket.sent.length
    fixture.lease.setCurrent(false)
    fixture.runNextScheduled()
    expect(fixture.socket.sent).toHaveLength(sent)
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'TRUST_LOST',
    })
  })

  it('does not publish a scheduled resize after trust becomes stale', async () => {
    let now = 1
    const fixture = controllerFixture({
      manualSchedule: true,
      now: () => now,
    })
    await connect(fixture)
    let inboundHop = 4n
    for (let browserHop = 4n; browserHop <= 8n; browserHop += 1n) {
      fixture.controller.requestResize(80, 24)
      fixture.socket.message(
        apiFrame(
          FrameType.RESIZE_ACK,
          appliedResizeAck(browserHop),
          inboundHop,
        ),
      )
      inboundHop += 1n
      await settle()
      await settle()
    }
    expect(fixture.socket.sent).toHaveLength(8)
    const sent = fixture.socket.sent.length
    fixture.controller.requestResize(80, 24)
    now = 1_000
    fixture.lease.setCurrent(false)
    fixture.runLastScheduled()
    expect(fixture.socket.sent).toHaveLength(sent)
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'TRUST_LOST',
    })
  })

  it('does not begin exact Stop from a stale control context', async () => {
    const fixture = controllerFixture()
    await connect(fixture)
    const stale = context()
    stale.aborter.abort()

    await expect(
      fixture.controller.stop(controlRequest(stale)),
    ).rejects.toEqual(new WAWBrowserControllerError('CONTEXT_CHANGED'))
    expect(fixture.controls.detachCalls).toBe(0)
    expect(fixture.controls.stopCalls).toBe(0)
  })

  it('does not issue Stop or revive state after page lifecycle fences a pending Detach', async () => {
    const fixture = controllerFixture({ deferDetach: true })
    await connect(fixture)
    const pending = fixture.controller.stop(controlRequest())
    await settle()
    expect(fixture.controls.detachCalls).toBe(1)
    expect(fixture.controls.stopCalls).toBe(0)

    fixture.controller.handlePageLifecycle('pagehide')
    fixture.releaseDetach()
    await expect(pending).rejects.toEqual(
      new WAWBrowserControllerError('CONTEXT_CHANGED'),
    )
    expect(fixture.controls.stopCalls).toBe(0)
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'PAGEHIDE',
    })
  })

  it('does not revive DETACHED after page lifecycle fences a direct pending Detach', async () => {
    const fixture = controllerFixture({ deferDetach: true })
    await connect(fixture)
    const pending = fixture.controller.detach(controlRequest())
    await settle()
    fixture.controller.handlePageLifecycle('hidden')
    fixture.releaseDetach()
    await expect(pending).rejects.toEqual(
      new WAWBrowserControllerError('CONTEXT_CHANGED'),
    )
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'PAGE_HIDDEN',
    })
  })

  it('fences a pending control operation when its own context aborts', async () => {
    const fixture = controllerFixture({ deferDetach: true })
    await connect(fixture)
    const operationContext = context()
    const pending = fixture.controller.detach(controlRequest(operationContext))
    await settle()
    operationContext.aborter.abort()
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'CONTEXT_CHANGED',
    })
    fixture.releaseDetach()
    await expect(pending).rejects.toEqual(
      new WAWBrowserControllerError('CONTEXT_CHANGED'),
    )
  })

  it('does not revive STOPPED after lifecycle fences a pending Stop receipt', async () => {
    const fixture = controllerFixture({ deferStop: true })
    await connect(fixture)
    const pending = fixture.controller.stop(controlRequest())
    await settle()
    expect(fixture.controls.stopCalls).toBe(1)
    fixture.controller.handlePageLifecycle('unmount')
    fixture.releaseStop()
    await expect(pending).rejects.toEqual(
      new WAWBrowserControllerError('CONTEXT_CHANGED'),
    )
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'UNMOUNTED',
    })
  })

  it('requires an exact STOPPED receipt before publishing the local Stop state', async () => {
    const fixture = controllerFixture({ stopState: 'RUNNING' })
    await connect(fixture)

    await expect(fixture.controller.stop(controlRequest())).rejects.toEqual(
      new WAWBrowserControllerError('STOP_FAILED'),
    )
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'STOP_FAILED',
    })
  })

  it('rejects each independently mutated Stop receipt field', async () => {
    const mutations: readonly ControllerFixtureOptions[] = [
      { stopWorkspaceId: `aws_${'c'.repeat(32)}` },
      { stopProjectId: `prj_${'c'.repeat(32)}` },
      { stopAgentType: 'claude' },
      { stopGeneration: '6' },
      { stopState: 'RUNNING' },
    ]
    for (const mutation of mutations) {
      const fixture = controllerFixture(mutation)
      await connect(fixture)
      await expect(fixture.controller.stop(controlRequest())).rejects.toEqual(
        new WAWBrowserControllerError('STOP_FAILED'),
      )
      expect(fixture.controller.snapshot).toMatchObject({
        status: 'FENCED',
        reason: 'STOP_FAILED',
      })
    }
  })

  it('keeps an exact STOPPED state across later page lifecycle events', async () => {
    const fixture = controllerFixture()
    await connect(fixture)
    await fixture.controller.stop(controlRequest())
    fixture.controller.handlePageLifecycle('pagehide')
    expect(fixture.controller.snapshot.status).toBe('STOPPED')
  })

  it('maps a freeze lifecycle event to an immediate publication fence', async () => {
    const fixture = controllerFixture()
    await connect(fixture)
    fixture.controller.handlePageLifecycle('freeze')
    expect(fixture.controller.snapshot).toMatchObject({
      status: 'FENCED',
      reason: 'PAGE_FROZEN',
    })
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
    const result = await connected.controller.stop(controlRequest())
    expect(result.detachConfirmed).toBe(true)
    expect(connected.controls.detachCalls).toBe(1)
    expect(connected.controls.stopCalls).toBe(1)
    expect(connected.controller.snapshot.status).toBe('STOPPED')
  })
})
