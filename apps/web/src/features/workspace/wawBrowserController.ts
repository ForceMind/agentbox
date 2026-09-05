import { decodeAwce } from './awce'
import {
  ADMISSION_TIMEOUT_MS,
  MAX_INPUT_BYTES,
  WAWInitiator,
  type KeyFrame,
} from './wawCryptoProfile'
import {
  deriveContext,
  validateAdmission,
  validateU64,
  type AdmissionTuple,
} from './wawCryptoContext'
import type { TerminalSchedulerFence } from './terminalScheduler'
import type { WAWTrustAuthorizationRequest } from './wawTrustPolicy'
import type { WAWTrustAuthorizationLease } from './wawTrustProvider'
import {
  decodeWireFrame,
  encodeWireFrame,
  FrameType,
  Leg,
  MAX_FRAME_BYTES,
  type WireFrame,
  type WireRecord,
} from './wawWire'

export const WAW_BROWSER_CONTROLLER_LIMITS = Object.freeze({
  admissionMs: ADMISSION_TIMEOUT_MS,
  inboundBufferedBytes: 256 * 1024,
  outboundBufferedBytes: 256 * 1024,
  resizeColumnsMin: 8,
  resizeColumnsMax: 240,
  resizeRowsMin: 1,
  resizeRowsMax: 200,
  resizePerSecond: 5,
  resizeBurst: 5,
  heartbeatMs: 5_000,
})

export const WAW_BROWSER_SUBPROTOCOL = 'agentbox-waw-v1'

export type WAWBrowserControllerStatus =
  | 'IDLE'
  | 'ACQUIRING_TICKET'
  | 'AUTHORIZING_TRUST'
  | 'CONNECTING'
  | 'HANDSHAKING'
  | 'CONNECTED'
  | 'DETACHING'
  | 'DETACHED'
  | 'STOPPING'
  | 'STOPPED'
  | 'FENCED'

export type WAWBrowserFenceReason =
  | 'ADMISSION_TIMEOUT'
  | 'CONTEXT_CHANGED'
  | 'TRUST_LOST'
  | 'TRANSPORT_FAILED'
  | 'PROTOCOL_INVALID'
  | 'STREAM_CRYPTO_FAILURE'
  | 'OUTPUT_RENDER_FAILED'
  | 'OUTPUT_BACKPRESSURE'
  | 'TERMINAL_PARSE_LIMIT'
  | 'PAGEHIDE'
  | 'PAGE_FROZEN'
  | 'PAGE_HIDDEN'
  | 'UNMOUNTED'
  | 'DETACH_REQUESTED'
  | 'STOP_REQUESTED'
  | 'DETACH_FAILED'
  | 'STOP_FAILED'
  | 'INPUT_UNCERTAIN'
  | 'INPUT_REJECTED'
  | 'WORKSPACE_TERMINAL'
  | 'OUTPUT_GAP'
  | 'SUPERSEDED'

export type WAWBrowserControllerErrorCode =
  | WAWBrowserFenceReason
  | 'CONTROLLER_BUSY'
  | 'CONTROLLER_NOT_CONNECTED'
  | 'INPUT_BUSY'
  | 'INPUT_INVALID'
  | 'RESIZE_INVALID'
  | 'ATTACHMENT_UNAVAILABLE'

export class WAWBrowserControllerError extends Error {
  constructor(readonly code: WAWBrowserControllerErrorCode) {
    super(code)
    this.name = 'WAWBrowserControllerError'
  }
}

export interface WAWBrowserContextLease {
  readonly signal: AbortSignal
  isCurrent(): boolean
}

export interface WAWBrowserConnectRequest {
  readonly projectId: string
  readonly workspaceId: string
  readonly agentType: 'claude' | 'codex'
  readonly generation: string
  readonly reconnect: boolean
  /** Captures the page selection, authenticated Session and UI controller epoch. */
  readonly context: WAWBrowserContextLease
}

/**
 * A control request must repeat the page's current workspace identity. It lets
 * a detached/fenced controller perform an exact cleanup or Stop without
 * borrowing a now-invalid streaming context.
 */
export interface WAWBrowserControlRequest {
  readonly projectId: string
  readonly workspaceId: string
  readonly agentType: 'claude' | 'codex'
  readonly generation: string
  readonly context: WAWBrowserContextLease
}

export interface WAWBrowserTicket extends AdmissionTuple {
  readonly protocol_version: 1
  readonly ticket: string
  readonly runtime_epoch: string
}

export interface WAWBrowserTicketPort {
  issue(request: {
    readonly workspaceId: string
    readonly agentType: 'claude' | 'codex'
    readonly reconnect: boolean
  }): Promise<WAWBrowserTicket>
}

export interface WAWBrowserTrustPort {
  authorize(
    request: WAWTrustAuthorizationRequest,
  ): Promise<Readonly<WAWTrustAuthorizationLease>>
}

export interface WAWBrowserDetachReceipt {
  readonly workspace_id: string
  readonly attachment_id: string
  readonly generation: string
  readonly lease_number: string
  readonly result: 'detached' | 'already_detached'
  readonly cleanup_state: 'ATTACH_PTY_CLOSED'
}

export interface WAWBrowserStopReceipt {
  readonly workspace_id: string
  readonly project_id: string
  readonly agent_type: 'claude' | 'codex'
  readonly generation: string
  readonly state: string
}

export interface WAWBrowserControlPort {
  detach(request: {
    readonly workspaceId: string
    readonly attachmentId: string
    readonly generation: string
    readonly leaseNumber: string
    readonly agentType: 'claude' | 'codex'
  }): Promise<WAWBrowserDetachReceipt>
  stop(request: {
    readonly workspaceId: string
    readonly generation: string
    readonly agentType: 'claude' | 'codex'
  }): Promise<WAWBrowserStopReceipt>
}

export interface WAWBrowserSocketHandlers {
  open(): void
  message(data: unknown): void
  close(event: { readonly code: number; readonly wasClean: boolean }): void
  error(): void
}

export interface WAWBrowserSocketPort {
  binaryType: 'arraybuffer'
  readonly readyState: number
  readonly bufferedAmount: number
  readonly protocol: string
  subscribe(handlers: WAWBrowserSocketHandlers): () => void
  send(bytes: Uint8Array): void
  close(code?: number): void
}

export interface WAWBrowserSocketFactory {
  create(
    url: string,
    subprotocol: typeof WAW_BROWSER_SUBPROTOCOL,
  ): WAWBrowserSocketPort
}

export interface WAWBrowserCryptoPort {
  readonly state: string
  writeKeyInit(): Promise<KeyFrame>
  readKeyAttest(frame: unknown): Promise<KeyFrame>
  readKeyConfirmAck(frame: unknown): Promise<void>
  encryptInput(plaintext: Uint8Array): Promise<Uint8Array>
  decryptOutput(
    ciphertext: Uint8Array,
    expectedCursor: bigint,
  ): Promise<Uint8Array>
  destroy(): void
}

export interface WAWBrowserCryptoFactory {
  create(
    admission: AdmissionTuple,
    runtimeEpoch: string,
    trustedFingerprint: string,
    options: {
      readonly now: () => number
      readonly admissionStartedAt: number
    },
  ): WAWBrowserCryptoPort
}

export interface WAWBrowserTerminalSchedulerPort {
  enqueueFrame(bytes: Uint8Array): Promise<void>
  resize(columns: number, rows: number): void
  cancelAttachment(): void
}

export interface WAWBrowserTerminalSchedulerFactory {
  create(options: {
    readonly onFence: (fence: TerminalSchedulerFence) => void
  }): WAWBrowserTerminalSchedulerPort
}

export type WAWBrowserSchedule = (
  callback: () => void,
  delayMs: number,
) => () => void

export type WAWBrowserInputState =
  | 'encrypting'
  | 'published'
  | 'accepted'
  | 'written_to_pty'
  | 'write_uncertain'
  | 'rejected'
  | 'local_uncertain'

export interface WAWBrowserInputSnapshot {
  readonly browserHop: string | null
  readonly cryptoSequence: string | null
  readonly state: WAWBrowserInputState
  readonly reasonCode: string | null
}

export interface WAWBrowserInputOutcome extends WAWBrowserInputSnapshot {
  readonly browserHop: string
  readonly cryptoSequence: string
  readonly state:
    'written_to_pty' | 'write_uncertain' | 'rejected' | 'local_uncertain'
}

export interface WAWBrowserAttachmentIdentity {
  readonly attachmentId: string
  readonly workspaceId: string
  readonly projectId: string
  readonly agentType: 'claude' | 'codex'
  readonly generation: string
  readonly leaseNumber: string
  readonly bindingRevision: string
  readonly bindingDigest: string
  readonly authEpoch: string
  readonly apiAuthorityEpoch: string
  readonly runtimeHostInstallationId: string
  readonly runtimeHostInstallationRevision: string
  readonly runtimeEpoch: string
}

export interface WAWBrowserControllerSnapshot {
  readonly status: WAWBrowserControllerStatus
  readonly reason: WAWBrowserFenceReason | null
  readonly attachment: WAWBrowserAttachmentIdentity | null
  readonly outputCursor: string | null
  /** Runtime had to bound the current connection's fresh redraw. */
  readonly freshRedrawTruncated: boolean
  readonly input: WAWBrowserInputSnapshot | null
}

export interface WAWBrowserStopOutcome {
  readonly detachConfirmed: boolean
  readonly detach: WAWBrowserDetachReceipt | null
  readonly stop: WAWBrowserStopReceipt
}

export interface WAWBrowserControllerOptions {
  readonly origin: string
  readonly tickets: WAWBrowserTicketPort
  readonly trust: WAWBrowserTrustPort
  readonly controls: WAWBrowserControlPort
  readonly terminal: WAWBrowserTerminalSchedulerFactory
  readonly sockets?: WAWBrowserSocketFactory
  readonly crypto?: WAWBrowserCryptoFactory
  readonly now?: () => number
  readonly schedule?: WAWBrowserSchedule
  readonly onSnapshot?: (snapshot: WAWBrowserControllerSnapshot) => void
}

interface PendingInput {
  browserHop: bigint | null
  cryptoSequence: bigint | null
  runtimeHop: bigint | null
  state: WAWBrowserInputState
  reasonCode: string | null
  published: boolean
  resolve: (outcome: WAWBrowserInputOutcome) => void
  reject: (error: WAWBrowserControllerError) => void
}

interface PendingResize {
  readonly browserHop: bigint
  readonly columns: number
  readonly rows: number
}

interface Deferred<T> {
  readonly promise: Promise<T>
  resolve(value: T): void
  reject(error: WAWBrowserControllerError): void
}

interface ActiveControlOperation {
  readonly token: symbol
  readonly identity: WAWBrowserAttachmentIdentity
  readonly context: WAWBrowserContextLease
  readonly cancel: () => void
}

const READY = 1

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (error: WAWBrowserControllerError) => void
  const promise = new Promise<T>((accepted, denied) => {
    resolve = accepted
    reject = denied
  })
  void promise.catch(() => undefined)
  return { promise, resolve, reject }
}

function defaultSchedule(callback: () => void, delayMs: number): () => void {
  const handle = globalThis.setTimeout(callback, Math.max(0, delayMs))
  return () => globalThis.clearTimeout(handle)
}

function nativeSocketFactory(): WAWBrowserSocketFactory {
  return {
    create(url, subprotocol) {
      const Constructor = globalThis.WebSocket
      if (typeof Constructor !== 'function') {
        throw new WAWBrowserControllerError('TRANSPORT_FAILED')
      }
      const socket = new Constructor(url, subprotocol)
      return {
        get binaryType() {
          return socket.binaryType as 'arraybuffer'
        },
        set binaryType(value: 'arraybuffer') {
          socket.binaryType = value
        },
        get readyState() {
          return socket.readyState
        },
        get bufferedAmount() {
          return socket.bufferedAmount
        },
        get protocol() {
          return socket.protocol
        },
        subscribe(handlers) {
          const open = () => handlers.open()
          const message = (event: MessageEvent<unknown>) =>
            handlers.message(event.data)
          const close = (event: CloseEvent) =>
            handlers.close({ code: event.code, wasClean: event.wasClean })
          const error = () => handlers.error()
          socket.addEventListener('open', open)
          socket.addEventListener('message', message)
          socket.addEventListener('close', close)
          socket.addEventListener('error', error)
          return () => {
            socket.removeEventListener('open', open)
            socket.removeEventListener('message', message)
            socket.removeEventListener('close', close)
            socket.removeEventListener('error', error)
          }
        },
        send(bytes) {
          socket.send(bytes)
        },
        close(code) {
          socket.close(code)
        },
      }
    },
  }
}

function defaultCryptoFactory(): WAWBrowserCryptoFactory {
  return {
    create(admission, runtimeEpoch, trustedFingerprint, options) {
      return new WAWInitiator(
        admission,
        runtimeEpoch,
        trustedFingerprint,
        options,
      )
    },
  }
}

function exactOrigin(value: string): URL {
  try {
    const parsed = new URL(value)
    if (
      parsed.origin !== value ||
      (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') ||
      parsed.username !== '' ||
      parsed.password !== '' ||
      parsed.pathname !== '/' ||
      parsed.search !== '' ||
      parsed.hash !== ''
    ) {
      throw new Error()
    }
    return parsed
  } catch {
    throw new WAWBrowserControllerError('PROTOCOL_INVALID')
  }
}

function streamUrl(origin: URL, workspaceId: string): string {
  if (!/^aws_[a-f0-9]{32}$/.test(workspaceId)) {
    throw new WAWBrowserControllerError('PROTOCOL_INVALID')
  }
  const result = new URL(`/api/v1/workspaces/${workspaceId}/stream`, origin)
  result.protocol = origin.protocol === 'https:' ? 'wss:' : 'ws:'
  if (
    result.hostname !== origin.hostname ||
    result.port !== origin.port ||
    result.username !== '' ||
    result.password !== '' ||
    result.search !== '' ||
    result.hash !== ''
  ) {
    throw new WAWBrowserControllerError('PROTOCOL_INVALID')
  }
  return result.href
}

function inputBytes(value: unknown): Uint8Array {
  if (
    !(value instanceof Uint8Array) ||
    value.constructor !== Uint8Array ||
    value.byteLength < 1 ||
    value.byteLength > MAX_INPUT_BYTES ||
    (typeof SharedArrayBuffer !== 'undefined' &&
      value.buffer instanceof SharedArrayBuffer)
  ) {
    throw new WAWBrowserControllerError('INPUT_INVALID')
  }
  return new Uint8Array(value)
}

function ticketIdentity(
  ticket: WAWBrowserTicket,
): WAWBrowserAttachmentIdentity {
  return Object.freeze({
    attachmentId: ticket.attachment_id,
    workspaceId: ticket.workspace_id,
    projectId: ticket.project_id,
    agentType: ticket.agent_type,
    generation: ticket.generation,
    leaseNumber: ticket.lease_number,
    bindingRevision: ticket.binding_revision,
    bindingDigest: ticket.binding_digest,
    authEpoch: ticket.auth_epoch,
    apiAuthorityEpoch: ticket.api_authority_epoch,
    runtimeHostInstallationId: ticket.runtime_host_installation_id,
    runtimeHostInstallationRevision: ticket.runtime_host_installation_revision,
    runtimeEpoch: ticket.runtime_epoch,
  })
}

function admissionFromTicket(ticket: WAWBrowserTicket): AdmissionTuple {
  return validateAdmission({
    attachment_id: ticket.attachment_id,
    workspace_id: ticket.workspace_id,
    project_id: ticket.project_id,
    agent_type: ticket.agent_type,
    runtime_host_installation_id: ticket.runtime_host_installation_id,
    runtime_host_installation_revision:
      ticket.runtime_host_installation_revision,
    auth_epoch: ticket.auth_epoch,
    api_authority_epoch: ticket.api_authority_epoch,
    lease_number: ticket.lease_number,
    generation: ticket.generation,
    binding_revision: ticket.binding_revision,
    mode: ticket.mode,
    binding_digest: ticket.binding_digest,
  })
}

function exactBigInt(value: unknown): bigint {
  return BigInt(validateU64(value))
}

function exactCursor(value: unknown): bigint {
  if (value === '0') return 0n
  return exactBigInt(value)
}

function record(frame: WireFrame): WireRecord {
  const value = frame.jsonPayload
  if (value === null) throw new WAWBrowserControllerError('PROTOCOL_INVALID')
  return value
}

/**
 * One browser attachment owner. It stores only bounded public identity/cursor/ACK
 * metadata; ticket bearers, plaintext, crypto state and raw frames stay transient.
 */
export class WAWBrowserController {
  readonly #origin: URL
  readonly #tickets: WAWBrowserTicketPort
  readonly #trust: WAWBrowserTrustPort
  readonly #controls: WAWBrowserControlPort
  readonly #terminalFactory: WAWBrowserTerminalSchedulerFactory
  readonly #sockets: WAWBrowserSocketFactory
  readonly #cryptoFactory: WAWBrowserCryptoFactory
  readonly #now: () => number
  readonly #schedule: WAWBrowserSchedule
  readonly #onSnapshot: WAWBrowserControllerOptions['onSnapshot']

  #status: WAWBrowserControllerStatus = 'IDLE'
  #reason: WAWBrowserFenceReason | null = null
  #epoch = 0
  #lastNow = -Infinity
  #context: WAWBrowserContextLease | null = null
  #contextAbort: (() => void) | null = null
  #trustLease: Readonly<WAWTrustAuthorizationLease> | null = null
  #trustAbort: (() => void) | null = null
  #identity: WAWBrowserAttachmentIdentity | null = null
  #admission: AdmissionTuple | null = null
  #socket: WAWBrowserSocketPort | null = null
  #unsubscribeSocket: (() => void) | null = null
  #crypto: WAWBrowserCryptoPort | null = null
  #terminal: WAWBrowserTerminalSchedulerPort | null = null
  #open: Deferred<void> | null = null
  #connected: Deferred<void> | null = null
  #admissionTimer: (() => void) | null = null
  #heartbeatTimer: (() => void) | null = null
  #resizeTimer: (() => void) | null = null
  #outboundHop = 1n
  #inboundHop = 1n
  #inboundTail: Promise<void> = Promise.resolve()
  #inboundBufferedBytes = 0
  #handshake: 'WAIT_ATTEST' | 'WAIT_ACK' | 'WAIT_ADMITTED' | null = null
  #canaryVerified = false
  #outputCursor: bigint | null = null
  #freshRedrawTruncated = false
  #pendingInput: PendingInput | null = null
  #pendingResize: PendingResize | null = null
  #latestResize: { readonly columns: number; readonly rows: number } | null =
    null
  #resizeTokens: number = WAW_BROWSER_CONTROLLER_LIMITS.resizeBurst
  #resizeRefillAt = 0
  #activeControlOperation: ActiveControlOperation | null = null

  constructor(options: WAWBrowserControllerOptions) {
    this.#origin = exactOrigin(options.origin)
    this.#tickets = options.tickets
    this.#trust = options.trust
    this.#controls = options.controls
    this.#terminalFactory = options.terminal
    this.#sockets = options.sockets ?? nativeSocketFactory()
    this.#cryptoFactory = options.crypto ?? defaultCryptoFactory()
    this.#now = options.now ?? (() => performance.now())
    this.#schedule = options.schedule ?? defaultSchedule
    this.#onSnapshot = options.onSnapshot
  }

  get snapshot(): WAWBrowserControllerSnapshot {
    return Object.freeze({
      status: this.#status,
      reason: this.#reason,
      attachment: this.#identity,
      outputCursor: this.#outputCursor?.toString() ?? null,
      freshRedrawTruncated: this.#freshRedrawTruncated,
      input: this.#inputSnapshot(),
    })
  }

  #inputSnapshot(): WAWBrowserInputSnapshot | null {
    const input = this.#pendingInput
    if (input === null) return null
    return Object.freeze({
      browserHop: input.browserHop?.toString() ?? null,
      cryptoSequence: input.cryptoSequence?.toString() ?? null,
      state: input.state,
      reasonCode: input.reasonCode,
    })
  }

  #emit(): void {
    try {
      this.#onSnapshot?.(this.snapshot)
    } catch {
      // A presentation observer cannot alter attachment authority.
    }
  }

  #setStatus(
    status: WAWBrowserControllerStatus,
    reason: WAWBrowserFenceReason | null = null,
  ): void {
    this.#status = status
    this.#reason = reason
    this.#emit()
  }

  #readNow(): number {
    let value: number
    try {
      value = this.#now()
    } catch {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    if (!Number.isFinite(value) || value < 0 || value < this.#lastNow) {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    this.#lastNow = value
    return value
  }

  #isCurrent(
    epoch: number,
    context = this.#context,
    trust = this.#trustLease,
  ): boolean {
    if (
      epoch !== this.#epoch ||
      context === null ||
      context !== this.#context ||
      context.signal.aborted ||
      context.isCurrent() !== true
    ) {
      return false
    }
    return (
      trust === null ||
      (trust === this.#trustLease &&
        !trust.signal.aborted &&
        trust.isCurrent() === true)
    )
  }

  #assertCurrent(
    epoch: number,
    context = this.#context,
    trust = this.#trustLease,
  ): void {
    if (this.#isCurrent(epoch, context, trust)) return
    const reason = this.#currentFenceReason(context, trust)
    if (epoch === this.#epoch) this.#teardown('FENCED', reason)
    throw new WAWBrowserControllerError(reason)
  }

  #currentFenceReason(
    context: WAWBrowserContextLease | null,
    trust: Readonly<WAWTrustAuthorizationLease> | null,
  ): 'CONTEXT_CHANGED' | 'TRUST_LOST' {
    try {
      if (
        context === null ||
        context.signal.aborted ||
        context.isCurrent() !== true
      ) {
        return 'CONTEXT_CHANGED'
      }
      if (
        trust !== null &&
        (trust.signal.aborted || trust.isCurrent() !== true)
      ) {
        return 'TRUST_LOST'
      }
    } catch {
      return 'CONTEXT_CHANGED'
    }
    return 'CONTEXT_CHANGED'
  }

  #listenToContext(context: WAWBrowserContextLease, epoch: number): void {
    const invalidate = () => {
      if (epoch === this.#epoch) this.#teardown('FENCED', 'CONTEXT_CHANGED')
    }
    context.signal.addEventListener('abort', invalidate, { once: true })
    this.#contextAbort = () =>
      context.signal.removeEventListener('abort', invalidate)
  }

  #listenToTrust(
    lease: Readonly<WAWTrustAuthorizationLease>,
    epoch: number,
  ): void {
    const invalidate = () => {
      if (epoch === this.#epoch) this.#teardown('FENCED', 'TRUST_LOST')
    }
    lease.signal.addEventListener('abort', invalidate, { once: true })
    this.#trustAbort = () =>
      lease.signal.removeEventListener('abort', invalidate)
  }

  #cancelTimers(): void {
    for (const cancel of [
      this.#admissionTimer,
      this.#heartbeatTimer,
      this.#resizeTimer,
    ]) {
      try {
        cancel?.()
      } catch {
        // Epoch fencing keeps a failed timer cancellation inert.
      }
    }
    this.#admissionTimer = null
    this.#heartbeatTimer = null
    this.#resizeTimer = null
  }

  #settleInputForFence(): void {
    const input = this.#pendingInput
    this.#pendingInput = null
    if (input === null) return
    if (
      input.published &&
      input.browserHop !== null &&
      input.cryptoSequence !== null
    ) {
      input.resolve(
        Object.freeze({
          browserHop: input.browserHop.toString(),
          cryptoSequence: input.cryptoSequence.toString(),
          state: 'local_uncertain',
          reasonCode: null,
        }),
      )
    } else {
      input.reject(new WAWBrowserControllerError('CONTEXT_CHANGED'))
    }
  }

  #teardown(
    status: WAWBrowserControllerStatus,
    reason: WAWBrowserFenceReason,
    preserveControlOperation: symbol | null = null,
  ): void {
    const error = new WAWBrowserControllerError(reason)
    this.#epoch += 1
    this.#cancelTimers()
    this.#contextAbort?.()
    this.#contextAbort = null
    this.#trustAbort?.()
    this.#trustAbort = null
    this.#context = null
    this.#trustLease = null
    if (
      this.#activeControlOperation !== null &&
      this.#activeControlOperation.token !== preserveControlOperation
    ) {
      this.#activeControlOperation.cancel()
      this.#activeControlOperation = null
    }
    this.#open?.reject(error)
    this.#open = null
    this.#connected?.reject(error)
    this.#connected = null
    this.#settleInputForFence()
    this.#latestResize = null
    this.#pendingResize = null
    this.#inboundBufferedBytes = 0
    this.#handshake = null
    this.#canaryVerified = false
    try {
      this.#unsubscribeSocket?.()
    } catch {
      // Listener removal is followed by epoch invalidation and socket close.
    }
    this.#unsubscribeSocket = null
    const socket = this.#socket
    this.#socket = null
    try {
      socket?.close(1000)
    } catch {
      // Publication is already fenced.
    }
    try {
      this.#crypto?.destroy()
    } catch {
      // Publication is already fenced.
    }
    this.#crypto = null
    try {
      this.#terminal?.cancelAttachment()
    } catch {
      // Publication is already fenced.
    }
    this.#terminal = null
    this.#admission = null
    // A new attachment always receives a fresh redraw. A destroyed terminal
    // model must never be paired with a retained cursor from an old model.
    this.#outputCursor = null
    this.#freshRedrawTruncated = false
    this.#setStatus(status, reason)
  }

  #protocolFailure(reason: WAWBrowserFenceReason = 'PROTOCOL_INVALID'): never {
    this.#teardown('FENCED', reason)
    throw new WAWBrowserControllerError(reason)
  }

  #prepareTicket(
    ticket: WAWBrowserTicket,
    request: WAWBrowserConnectRequest,
  ): AdmissionTuple {
    if (
      ticket.protocol_version !== 1 ||
      !/^wat_[a-f0-9]{32}$/.test(ticket.ticket) ||
      ticket.workspace_id !== request.workspaceId ||
      ticket.project_id !== request.projectId ||
      ticket.agent_type !== request.agentType ||
      ticket.generation !== request.generation
    ) {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    const admission = admissionFromTicket(ticket)
    deriveContext(admission, ticket.runtime_epoch)
    return admission
  }

  async connect(request: WAWBrowserConnectRequest): Promise<void> {
    if (
      !['IDLE', 'DETACHED', 'FENCED'].includes(this.#status) ||
      request.context.signal.aborted ||
      request.context.isCurrent() !== true
    ) {
      throw new WAWBrowserControllerError(
        this.#status === 'IDLE' ||
          this.#status === 'DETACHED' ||
          this.#status === 'FENCED'
          ? 'CONTEXT_CHANGED'
          : 'CONTROLLER_BUSY',
      )
    }

    if (this.#status !== 'IDLE') {
      this.#teardown('FENCED', 'SUPERSEDED')
    }
    const epoch = (this.#epoch += 1)
    this.#context = request.context
    this.#reason = null
    this.#identity = null
    this.#admission = null
    this.#socket = null
    this.#crypto = null
    this.#terminal = null
    this.#outboundHop = 1n
    this.#inboundHop = 1n
    this.#inboundTail = Promise.resolve()
    this.#inboundBufferedBytes = 0
    this.#outputCursor = null
    this.#freshRedrawTruncated = false
    this.#pendingInput = null
    this.#pendingResize = null
    this.#latestResize = null
    this.#resizeTokens = WAW_BROWSER_CONTROLLER_LIMITS.resizeBurst
    this.#listenToContext(request.context, epoch)
    this.#setStatus('ACQUIRING_TICKET')

    let issued: WAWBrowserTicket | null = null
    try {
      issued = await this.#tickets.issue({
        workspaceId: request.workspaceId,
        agentType: request.agentType,
        reconnect: request.reconnect,
      })
      this.#assertCurrent(epoch, request.context, null)
      const admission = this.#prepareTicket(issued, request)
      const identity = ticketIdentity(issued)
      this.#identity = identity
      this.#admission = admission
      this.#emit()

      this.#setStatus('AUTHORIZING_TRUST')
      const trust = await this.#trust.authorize({
        effective_origin: this.#origin.origin,
        admitted_api_origin: this.#origin.origin,
        runtime_host_installation_id: identity.runtimeHostInstallationId,
        runtime_host_installation_revision:
          identity.runtimeHostInstallationRevision,
      })
      this.#assertCurrent(epoch, request.context, null)
      if (
        trust.origin !== this.#origin.origin ||
        trust.runtime_host_installation_id !==
          identity.runtimeHostInstallationId ||
        BigInt(trust.runtime_host_installation_revision) !==
          exactBigInt(identity.runtimeHostInstallationRevision) ||
        trust.signal.aborted ||
        trust.isCurrent() !== true
      ) {
        throw new WAWBrowserControllerError('TRUST_LOST')
      }
      this.#trustLease = trust
      this.#listenToTrust(trust, epoch)
      this.#assertCurrent(epoch, request.context, trust)

      const startedAt = this.#readNow()
      this.#resizeRefillAt = startedAt
      const crypto = this.#cryptoFactory.create(
        admission,
        identity.runtimeEpoch,
        trust.runtime_attestation_x25519_fingerprint,
        { now: () => this.#readNow(), admissionStartedAt: startedAt },
      )
      this.#crypto = crypto
      const terminal = this.#terminalFactory.create({
        onFence: (fence) => this.#terminalFence(epoch, fence),
      })
      this.#terminal = terminal
      const socket = this.#sockets.create(
        streamUrl(this.#origin, identity.workspaceId),
        WAW_BROWSER_SUBPROTOCOL,
      )
      socket.binaryType = 'arraybuffer'
      if (socket.binaryType !== 'arraybuffer') {
        throw new WAWBrowserControllerError('TRANSPORT_FAILED')
      }
      this.#socket = socket
      this.#open = deferred<void>()
      this.#connected = deferred<void>()
      this.#unsubscribeSocket = socket.subscribe({
        open: () => {
          if (epoch === this.#epoch) this.#open?.resolve(undefined)
        },
        message: (data) => this.#queueInbound(epoch, data),
        close: () => {
          if (epoch === this.#epoch) {
            this.#teardown('FENCED', 'TRANSPORT_FAILED')
          }
        },
        error: () => {
          if (epoch === this.#epoch) {
            this.#teardown('FENCED', 'TRANSPORT_FAILED')
          }
        },
      })
      this.#startAdmissionTimer(epoch, startedAt)
      this.#setStatus('CONNECTING')
      await this.#open.promise
      this.#assertCurrent(epoch, request.context, trust)
      if (
        socket.readyState !== READY ||
        socket.protocol !== WAW_BROWSER_SUBPROTOCOL
      ) {
        throw new WAWBrowserControllerError('TRANSPORT_FAILED')
      }
      this.#open = null
      this.#setStatus('HANDSHAKING')

      let bearer = issued.ticket
      issued = null
      let hello: WireRecord | null = {
        protocol_version: 1,
        ...admission,
        runtime_epoch: identity.runtimeEpoch,
        // The terminal model is destroyed on every detach/fence. Reusing a
        // cursor without atomically transferring that model could skip output.
        // Reconnect therefore always requests a bounded fresh redraw.
        resume_cursor: null,
        previous_runtime_epoch: null,
        ticket: bearer,
      }
      this.#publishPayload(epoch, FrameType.WS_HELLO, hello)
      bearer = ''
      hello = null

      const init = await crypto.writeKeyInit()
      this.#assertCurrent(epoch, request.context, trust)
      this.#handshake = 'WAIT_ATTEST'
      this.#publishPayload(epoch, FrameType.KEY_INIT, init)
      await this.#connected.promise
      this.#assertCurrent(epoch, request.context, trust)
      this.#connected = null
    } catch (error) {
      if (issued !== null) issued = null
      if (epoch === this.#epoch) {
        const reason =
          error instanceof WAWBrowserControllerError
            ? error.code === 'TRUST_LOST'
              ? 'TRUST_LOST'
              : error.code === 'ADMISSION_TIMEOUT'
                ? 'ADMISSION_TIMEOUT'
                : error.code === 'TRANSPORT_FAILED'
                  ? 'TRANSPORT_FAILED'
                  : error.code === 'CONTEXT_CHANGED'
                    ? 'CONTEXT_CHANGED'
                    : 'PROTOCOL_INVALID'
            : 'PROTOCOL_INVALID'
        this.#teardown('FENCED', reason)
      }
      throw error instanceof WAWBrowserControllerError
        ? error
        : new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
  }

  #startAdmissionTimer(epoch: number, startedAt: number): void {
    const deadline = startedAt + WAW_BROWSER_CONTROLLER_LIMITS.admissionMs
    const run = () => {
      if (epoch !== this.#epoch || this.#status === 'CONNECTED') return
      let now: number
      try {
        now = this.#readNow()
      } catch {
        this.#teardown('FENCED', 'PROTOCOL_INVALID')
        return
      }
      if (now < deadline) {
        this.#admissionTimer = this.#schedule(run, deadline - now)
        return
      }
      this.#teardown('FENCED', 'ADMISSION_TIMEOUT')
    }
    try {
      this.#admissionTimer = this.#schedule(run, deadline - startedAt)
    } catch {
      this.#teardown('FENCED', 'PROTOCOL_INVALID')
    }
  }

  #terminalFence(epoch: number, fence: TerminalSchedulerFence): void {
    if (epoch !== this.#epoch) return
    this.#teardown(
      'FENCED',
      fence.reason === 'TERMINAL_RENDER_FAILED'
        ? 'OUTPUT_RENDER_FAILED'
        : 'TERMINAL_PARSE_LIMIT',
    )
  }

  #assertPublicationCurrent(epoch: number): void {
    const context = this.#context
    const trust = this.#trustLease
    let contextCurrent = false
    let trustCurrent = false
    try {
      contextCurrent = Boolean(
        context !== null &&
        !context.signal.aborted &&
        context.isCurrent() === true,
      )
      trustCurrent = Boolean(
        trust !== null && !trust.signal.aborted && trust.isCurrent() === true,
      )
    } catch {
      contextCurrent = false
    }
    if (epoch === this.#epoch && contextCurrent && trustCurrent) return
    const reason = contextCurrent ? 'TRUST_LOST' : 'CONTEXT_CHANGED'
    if (epoch === this.#epoch) this.#teardown('FENCED', reason)
    throw new WAWBrowserControllerError(reason)
  }

  #publishPayload(epoch: number, kind: FrameType, payload: unknown): bigint {
    this.#assertPublicationCurrent(epoch)
    const admission = this.#admission
    const identity = this.#identity
    if (admission === null || identity === null) {
      return this.#protocolFailure()
    }
    const hop = this.#outboundHop
    let bytes: Uint8Array
    try {
      bytes = encodeWireFrame(kind, Leg.BROWSER_TO_API, payload, hop, {
        admission,
        runtimeEpoch: identity.runtimeEpoch,
      })
    } catch {
      return this.#protocolFailure()
    }
    this.#publishBytes(epoch, bytes)
    this.#outboundHop += 1n
    return hop
  }

  #publishBytes(epoch: number, bytes: Uint8Array): void {
    try {
      this.#assertPublicationCurrent(epoch)
    } catch (error) {
      bytes.fill(0)
      throw error
    }
    const socket = this.#socket
    if (
      epoch !== this.#epoch ||
      socket === null ||
      socket.readyState !== READY
    ) {
      bytes.fill(0)
      throw new WAWBrowserControllerError('CONTEXT_CHANGED')
    }
    let buffered: number
    try {
      buffered = socket.bufferedAmount
    } catch {
      bytes.fill(0)
      return this.#protocolFailure('OUTPUT_BACKPRESSURE')
    }
    if (
      !Number.isSafeInteger(buffered) ||
      buffered < 0 ||
      buffered + bytes.byteLength >
        WAW_BROWSER_CONTROLLER_LIMITS.outboundBufferedBytes
    ) {
      bytes.fill(0)
      return this.#protocolFailure('OUTPUT_BACKPRESSURE')
    }
    try {
      // Getter-backed socket state may yield to host code. Revalidate at the
      // final synchronous publication boundary as well as before encoding.
      this.#assertPublicationCurrent(epoch)
    } catch (error) {
      bytes.fill(0)
      throw error
    }
    try {
      socket.send(bytes)
    } catch {
      bytes.fill(0)
      return this.#protocolFailure('TRANSPORT_FAILED')
    }
    bytes.fill(0)
  }

  #queueInbound(epoch: number, data: unknown): void {
    if (epoch !== this.#epoch) return
    if (
      !(data instanceof ArrayBuffer) ||
      data.constructor !== ArrayBuffer ||
      data.byteLength < 1 ||
      data.byteLength > MAX_FRAME_BYTES ||
      this.#inboundBufferedBytes + data.byteLength >
        WAW_BROWSER_CONTROLLER_LIMITS.inboundBufferedBytes
    ) {
      this.#teardown('FENCED', 'OUTPUT_BACKPRESSURE')
      return
    }
    const bytes = new Uint8Array(data.slice(0))
    this.#inboundBufferedBytes += bytes.byteLength
    this.#inboundTail = this.#inboundTail
      .then(async () => {
        if (epoch !== this.#epoch) return
        try {
          await this.#handleInbound(epoch, bytes)
        } catch (error) {
          if (epoch !== this.#epoch) return
          const reason =
            error instanceof WAWBrowserControllerError &&
            error.code === 'OUTPUT_RENDER_FAILED'
              ? 'OUTPUT_RENDER_FAILED'
              : error instanceof WAWBrowserControllerError &&
                  error.code === 'STREAM_CRYPTO_FAILURE'
                ? 'STREAM_CRYPTO_FAILURE'
                : error instanceof WAWBrowserControllerError &&
                    error.code === 'CONTEXT_CHANGED'
                  ? 'CONTEXT_CHANGED'
                  : error instanceof WAWBrowserControllerError &&
                      error.code === 'TRUST_LOST'
                    ? 'TRUST_LOST'
                    : 'PROTOCOL_INVALID'
          this.#teardown('FENCED', reason)
        } finally {
          bytes.fill(0)
          if (epoch === this.#epoch) {
            this.#inboundBufferedBytes -= bytes.byteLength
          }
        }
      })
      .catch(() => undefined)
  }

  async #handleInbound(epoch: number, raw: Uint8Array): Promise<void> {
    const admission = this.#admission
    const identity = this.#identity
    const context = this.#context
    const trust = this.#trustLease
    if (
      admission === null ||
      identity === null ||
      context === null ||
      trust === null
    ) {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    this.#assertCurrent(epoch, context, trust)
    let frame: WireFrame
    try {
      frame = decodeWireFrame(raw, Leg.API_TO_BROWSER, {
        admission,
        runtimeEpoch: identity.runtimeEpoch,
      })
    } catch {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    if (frame.hopSequence !== this.#inboundHop) {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    this.#inboundHop += 1n

    if (this.#status === 'HANDSHAKING') {
      await this.#handleHandshake(epoch, frame, context, trust)
      return
    }
    if (this.#status !== 'CONNECTED') {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    switch (frame.frameType) {
      case FrameType.OUTPUT:
        await this.#handleOutput(epoch, frame, context, trust)
        return
      case FrameType.ACK:
        this.#handleInputAck(frame)
        return
      case FrameType.RESIZE_ACK:
        this.#handleResizeAck(epoch, frame)
        return
      case FrameType.ERROR: {
        const body = record(frame)
        if (body.code === 'CONTROL_RATE_LIMITED' && body.retryable === true) {
          this.#pendingResize = null
          this.#drainResize(epoch)
          return
        }
        throw new WAWBrowserControllerError('PROTOCOL_INVALID')
      }
      case FrameType.STATE: {
        const state = record(frame).state
        if (state === 'RUNNING' || state === 'NEEDS_INTERACTION') return
        this.#teardown('FENCED', 'WORKSPACE_TERMINAL')
        return
      }
      case FrameType.EXIT:
      case FrameType.CLOSE:
        this.#teardown('FENCED', 'WORKSPACE_TERMINAL')
        return
      case FrameType.GAP: {
        const gap = record(frame)
        if (
          gap.reason === 'baseline_redraw' &&
          gap.from_cursor === '0' &&
          gap.to_cursor === '0' &&
          this.#outputCursor === null &&
          !this.#freshRedrawTruncated
        ) {
          // A fresh redraw may be bounded after the marker. It does not mean
          // a rendered cursor was lost, because this connection never sends a
          // positive resume cursor.
          this.#freshRedrawTruncated = true
          this.#emit()
          return
        }
        this.#teardown('FENCED', 'OUTPUT_GAP')
        return
      }
      case FrameType.PONG:
        return
      default:
        throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
  }

  async #handleHandshake(
    epoch: number,
    frame: WireFrame,
    context: WAWBrowserContextLease,
    trust: Readonly<WAWTrustAuthorizationLease>,
  ): Promise<void> {
    const crypto = this.#crypto
    if (crypto === null) throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    if (
      this.#handshake === 'WAIT_ATTEST' &&
      frame.frameType === FrameType.KEY_ATTEST
    ) {
      let confirm: KeyFrame
      try {
        confirm = await crypto.readKeyAttest(record(frame))
      } catch {
        throw new WAWBrowserControllerError('STREAM_CRYPTO_FAILURE')
      }
      this.#assertCurrent(epoch, context, trust)
      this.#handshake = 'WAIT_ACK'
      this.#publishPayload(epoch, FrameType.KEY_CONFIRM, confirm)
      return
    }
    if (
      this.#handshake === 'WAIT_ACK' &&
      frame.frameType === FrameType.KEY_CONFIRM_ACK
    ) {
      try {
        await crypto.readKeyConfirmAck(record(frame))
      } catch {
        throw new WAWBrowserControllerError('STREAM_CRYPTO_FAILURE')
      }
      this.#assertCurrent(epoch, context, trust)
      this.#canaryVerified = true
      this.#handshake = 'WAIT_ADMITTED'
      return
    }
    if (
      this.#handshake === 'WAIT_ADMITTED' &&
      frame.frameType === FrameType.ADMITTED
    ) {
      if (!this.#canaryVerified || crypto.state !== 'VERIFIED') {
        throw new WAWBrowserControllerError('STREAM_CRYPTO_FAILURE')
      }
      const body = record(frame)
      // Validate the Runtime's selected baseline bound, but do not present it
      // as a rendered cursor. Only a completed terminal render may advance the
      // cursor visible to a later decision.
      exactCursor(body.output_cursor)
      this.#handshake = null
      this.#admissionTimer?.()
      this.#admissionTimer = null
      this.#setStatus('CONNECTED')
      this.#startHeartbeat(epoch)
      this.#connected?.resolve(undefined)
      return
    }
    if (
      frame.frameType === FrameType.ERROR ||
      frame.frameType === FrameType.CLOSE ||
      frame.frameType === FrameType.STATE
    ) {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    throw new WAWBrowserControllerError('PROTOCOL_INVALID')
  }

  async #handleOutput(
    epoch: number,
    frame: WireFrame,
    context: WAWBrowserContextLease,
    trust: Readonly<WAWTrustAuthorizationLease>,
  ): Promise<void> {
    const crypto = this.#crypto
    const terminal = this.#terminal
    if (crypto === null || terminal === null) {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    let cursor: bigint
    try {
      cursor = decodeAwce(frame.payload).stream_cursor
    } catch {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    let plaintext: Uint8Array
    try {
      plaintext = await crypto.decryptOutput(frame.payload, cursor)
    } catch {
      throw new WAWBrowserControllerError('STREAM_CRYPTO_FAILURE')
    }
    this.#assertCurrent(epoch, context, trust)
    let rendered: Promise<void>
    try {
      rendered = terminal.enqueueFrame(plaintext)
    } catch {
      plaintext.fill(0)
      throw new WAWBrowserControllerError('OUTPUT_RENDER_FAILED')
    }
    plaintext.fill(0)
    try {
      await rendered
    } catch {
      throw new WAWBrowserControllerError('OUTPUT_RENDER_FAILED')
    }
    this.#assertCurrent(epoch, context, trust)
    this.#outputCursor = cursor
    this.#emit()
  }

  async sendInput(value: Uint8Array): Promise<WAWBrowserInputOutcome> {
    if (this.#status !== 'CONNECTED') {
      throw new WAWBrowserControllerError('CONTROLLER_NOT_CONNECTED')
    }
    if (this.#pendingInput !== null) {
      throw new WAWBrowserControllerError('INPUT_BUSY')
    }
    const plaintext = inputBytes(value)
    const epoch = this.#epoch
    const context = this.#context
    const trust = this.#trustLease
    const crypto = this.#crypto
    if (context === null || trust === null || crypto === null) {
      plaintext.fill(0)
      throw new WAWBrowserControllerError('CONTROLLER_NOT_CONNECTED')
    }
    let resolve!: (outcome: WAWBrowserInputOutcome) => void
    let reject!: (error: WAWBrowserControllerError) => void
    const outcome = new Promise<WAWBrowserInputOutcome>((accepted, denied) => {
      resolve = accepted
      reject = denied
    })
    const pending: PendingInput = {
      browserHop: null,
      cryptoSequence: null,
      runtimeHop: null,
      state: 'encrypting',
      reasonCode: null,
      published: false,
      resolve,
      reject,
    }
    this.#pendingInput = pending
    this.#emit()
    try {
      const ciphertext = await crypto.encryptInput(plaintext)
      this.#assertCurrent(epoch, context, trust)
      let cryptoSequence: bigint
      try {
        cryptoSequence = decodeAwce(ciphertext).crypto_sequence
      } catch {
        ciphertext.fill(0)
        throw new WAWBrowserControllerError('STREAM_CRYPTO_FAILURE')
      }
      const browserHop = this.#publishPayload(
        epoch,
        FrameType.INPUT,
        ciphertext,
      )
      ciphertext.fill(0)
      this.#assertCurrent(epoch, context, trust)
      if (this.#pendingInput !== pending) {
        throw new WAWBrowserControllerError('CONTEXT_CHANGED')
      }
      pending.browserHop = browserHop
      pending.cryptoSequence = cryptoSequence
      pending.published = true
      pending.state = 'published'
      this.#emit()
    } catch (error) {
      if (this.#pendingInput === pending) {
        this.#pendingInput = null
        pending.reject(
          error instanceof WAWBrowserControllerError
            ? error
            : new WAWBrowserControllerError('STREAM_CRYPTO_FAILURE'),
        )
        this.#emit()
      }
      if (epoch === this.#epoch) {
        this.#teardown('FENCED', 'STREAM_CRYPTO_FAILURE')
      }
    } finally {
      plaintext.fill(0)
    }
    return outcome
  }

  #handleInputAck(frame: WireFrame): void {
    const input = this.#pendingInput
    const body = record(frame)
    if (
      input === null ||
      input.browserHop === null ||
      input.cryptoSequence === null ||
      exactBigInt(body.browser_input_hop_sequence) !== input.browserHop ||
      exactBigInt(body.crypto_sequence) !== input.cryptoSequence
    ) {
      return this.#protocolFailure()
    }
    const runtimeHop = exactBigInt(body.runtime_input_hop_sequence)
    const result = body.result
    if (result === 'accepted') {
      if (input.state !== 'published') return this.#protocolFailure()
      input.runtimeHop = runtimeHop
      input.state = 'accepted'
      input.reasonCode = null
      this.#emit()
      return
    }
    if (result === 'rejected') {
      if (input.state !== 'published') return this.#protocolFailure()
    } else if (
      (result === 'written_to_pty' || result === 'write_uncertain') &&
      (input.state !== 'accepted' || input.runtimeHop !== runtimeHop)
    ) {
      return this.#protocolFailure()
    }
    if (
      result !== 'rejected' &&
      result !== 'written_to_pty' &&
      result !== 'write_uncertain'
    ) {
      return this.#protocolFailure()
    }
    input.state = result
    input.reasonCode = body.reason_code as string | null
    this.#pendingInput = null
    const outcome = Object.freeze({
      browserHop: input.browserHop.toString(),
      cryptoSequence: input.cryptoSequence.toString(),
      state: result,
      reasonCode: input.reasonCode,
    })
    const terminalResult =
      result === 'write_uncertain' ||
      (result === 'rejected' && input.reasonCode !== 'INPUT_RATE_LIMITED')
    if (terminalResult) {
      // Runtime closes after uncertain input. Fence before resolving so a
      // caller cannot publish a second input in the ACK/CLOSE race window.
      this.#teardown(
        'FENCED',
        result === 'write_uncertain' ? 'INPUT_UNCERTAIN' : 'INPUT_REJECTED',
      )
    }
    input.resolve(outcome)
    this.#emit()
  }

  requestResize(columns: number, rows: number): void {
    if (this.#status !== 'CONNECTED') {
      throw new WAWBrowserControllerError('CONTROLLER_NOT_CONNECTED')
    }
    this.#assertPublicationCurrent(this.#epoch)
    if (
      !Number.isInteger(columns) ||
      columns < WAW_BROWSER_CONTROLLER_LIMITS.resizeColumnsMin ||
      columns > WAW_BROWSER_CONTROLLER_LIMITS.resizeColumnsMax ||
      !Number.isInteger(rows) ||
      rows < WAW_BROWSER_CONTROLLER_LIMITS.resizeRowsMin ||
      rows > WAW_BROWSER_CONTROLLER_LIMITS.resizeRowsMax
    ) {
      throw new WAWBrowserControllerError('RESIZE_INVALID')
    }
    this.#latestResize = Object.freeze({ columns, rows })
    this.#drainResize(this.#epoch)
  }

  #refillResize(now: number): void {
    const elapsed = now - this.#resizeRefillAt
    this.#resizeTokens = Math.min(
      WAW_BROWSER_CONTROLLER_LIMITS.resizeBurst,
      this.#resizeTokens +
        (elapsed * WAW_BROWSER_CONTROLLER_LIMITS.resizePerSecond) / 1_000,
    )
    this.#resizeRefillAt = now
  }

  #drainResize(epoch: number): void {
    if (
      epoch !== this.#epoch ||
      this.#status !== 'CONNECTED' ||
      this.#pendingResize !== null ||
      this.#latestResize === null
    ) {
      return
    }
    let now: number
    try {
      now = this.#readNow()
    } catch {
      this.#teardown('FENCED', 'PROTOCOL_INVALID')
      return
    }
    this.#refillResize(now)
    if (this.#resizeTokens < 1) {
      if (this.#resizeTimer !== null) return
      const delay =
        ((1 - this.#resizeTokens) * 1_000) /
        WAW_BROWSER_CONTROLLER_LIMITS.resizePerSecond
      try {
        this.#resizeTimer = this.#schedule(() => {
          this.#resizeTimer = null
          try {
            this.#drainResize(epoch)
          } catch (error) {
            if (epoch !== this.#epoch) return
            this.#teardown(
              'FENCED',
              error instanceof WAWBrowserControllerError &&
                error.code === 'TRUST_LOST'
                ? 'TRUST_LOST'
                : 'CONTEXT_CHANGED',
            )
          }
        }, delay)
      } catch {
        this.#teardown('FENCED', 'PROTOCOL_INVALID')
      }
      return
    }
    const request = this.#latestResize
    this.#latestResize = null
    this.#resizeTokens -= 1
    const identity = this.#identity
    if (identity === null) return this.#protocolFailure()
    const browserHop = this.#publishPayload(epoch, FrameType.RESIZE, {
      protocol_version: 1,
      attachment_id: identity.attachmentId,
      lease_number: identity.leaseNumber,
      columns: request.columns,
      rows: request.rows,
    })
    this.#pendingResize = Object.freeze({
      browserHop,
      columns: request.columns,
      rows: request.rows,
    })
  }

  #handleResizeAck(epoch: number, frame: WireFrame): void {
    const pending = this.#pendingResize
    const body = record(frame)
    if (
      pending === null ||
      exactBigInt(body.acknowledged_hop_sequence) !== pending.browserHop ||
      body.requested_columns !== pending.columns ||
      body.requested_rows !== pending.rows
    ) {
      return this.#protocolFailure()
    }
    this.#pendingResize = null
    if (body.result === 'applied') {
      try {
        this.#terminal?.resize(pending.columns, pending.rows)
      } catch {
        return this.#protocolFailure('OUTPUT_RENDER_FAILED')
      }
    } else if (body.reason_code !== 'CONTROL_RATE_LIMITED') {
      return this.#protocolFailure()
    }
    this.#drainResize(epoch)
  }

  #monotonicTick(): string {
    const value = Math.max(1, Math.floor(this.#readNow() * 1_000_000))
    if (!Number.isSafeInteger(value)) {
      throw new WAWBrowserControllerError('PROTOCOL_INVALID')
    }
    return BigInt(value).toString()
  }

  #startHeartbeat(epoch: number): void {
    const run = () => {
      if (epoch !== this.#epoch || this.#status !== 'CONNECTED') return
      const identity = this.#identity
      if (identity === null) {
        this.#teardown('FENCED', 'PROTOCOL_INVALID')
        return
      }
      try {
        this.#publishPayload(epoch, FrameType.HEARTBEAT, {
          protocol_version: 1,
          attachment_id: identity.attachmentId,
          lease_number: identity.leaseNumber,
          sent_at_monotonic_tick: this.#monotonicTick(),
        })
        this.#heartbeatTimer = this.#schedule(
          run,
          WAW_BROWSER_CONTROLLER_LIMITS.heartbeatMs,
        )
      } catch {
        if (epoch === this.#epoch) {
          this.#teardown('FENCED', 'TRANSPORT_FAILED')
        }
      }
    }
    try {
      this.#heartbeatTimer = this.#schedule(
        run,
        WAW_BROWSER_CONTROLLER_LIMITS.heartbeatMs,
      )
    } catch {
      this.#teardown('FENCED', 'PROTOCOL_INVALID')
    }
  }

  #beginControlOperation(
    request: WAWBrowserControlRequest,
  ): ActiveControlOperation {
    if (this.#activeControlOperation !== null) {
      throw new WAWBrowserControllerError('CONTROLLER_BUSY')
    }
    const identity = this.#identity
    if (identity === null) {
      throw new WAWBrowserControllerError('ATTACHMENT_UNAVAILABLE')
    }
    let contextCurrent = false
    try {
      contextCurrent =
        !request.context.signal.aborted && request.context.isCurrent() === true
    } catch {
      contextCurrent = false
    }
    if (
      !contextCurrent ||
      identity.projectId !== request.projectId ||
      identity.workspaceId !== request.workspaceId ||
      identity.agentType !== request.agentType ||
      identity.generation !== request.generation
    ) {
      throw new WAWBrowserControllerError('CONTEXT_CHANGED')
    }
    const token = Symbol('waw-control-operation')
    const invalidate = () => {
      if (this.#activeControlOperation?.token === token) {
        this.#teardown('FENCED', 'CONTEXT_CHANGED')
      }
    }
    request.context.signal.addEventListener('abort', invalidate, { once: true })
    const operation = Object.freeze({
      token,
      identity,
      context: request.context,
      cancel: () =>
        request.context.signal.removeEventListener('abort', invalidate),
    })
    this.#activeControlOperation = operation
    return operation
  }

  #controlOperationCurrent(operation: ActiveControlOperation): boolean {
    try {
      return (
        this.#activeControlOperation?.token === operation.token &&
        !operation.context.signal.aborted &&
        operation.context.isCurrent() === true
      )
    } catch {
      return false
    }
  }

  #assertControlOperation(operation: ActiveControlOperation): void {
    if (this.#controlOperationCurrent(operation)) return
    throw new WAWBrowserControllerError('CONTEXT_CHANGED')
  }

  #finishControlOperation(operation: ActiveControlOperation): void {
    if (this.#activeControlOperation?.token === operation.token) {
      operation.cancel()
      this.#activeControlOperation = null
    }
  }

  #failControlOperation(
    operation: ActiveControlOperation,
    reason: WAWBrowserFenceReason,
  ): void {
    const owned = this.#activeControlOperation?.token === operation.token
    this.#finishControlOperation(operation)
    if (owned) this.#setStatus('FENCED', reason)
  }

  #checkDetachReceipt(
    identity: WAWBrowserAttachmentIdentity,
    receipt: WAWBrowserDetachReceipt,
  ): WAWBrowserDetachReceipt {
    if (
      receipt.workspace_id !== identity.workspaceId ||
      receipt.attachment_id !== identity.attachmentId ||
      receipt.generation !== identity.generation ||
      receipt.lease_number !== identity.leaseNumber ||
      (receipt.result !== 'detached' &&
        receipt.result !== 'already_detached') ||
      receipt.cleanup_state !== 'ATTACH_PTY_CLOSED'
    ) {
      throw new WAWBrowserControllerError('DETACH_FAILED')
    }
    return receipt
  }

  #checkStopReceipt(
    identity: WAWBrowserAttachmentIdentity,
    receipt: WAWBrowserStopReceipt,
  ): WAWBrowserStopReceipt {
    if (
      receipt.workspace_id !== identity.workspaceId ||
      receipt.project_id !== identity.projectId ||
      receipt.agent_type !== identity.agentType ||
      receipt.generation !== identity.generation ||
      receipt.state !== 'STOPPED'
    ) {
      throw new WAWBrowserControllerError('STOP_FAILED')
    }
    return receipt
  }

  async detach(
    request: WAWBrowserControlRequest,
  ): Promise<WAWBrowserDetachReceipt> {
    if (this.#status === 'DETACHING' || this.#status === 'STOPPING') {
      throw new WAWBrowserControllerError('CONTROLLER_BUSY')
    }
    if (!['CONNECTED', 'FENCED'].includes(this.#status)) {
      throw new WAWBrowserControllerError('CONTROLLER_NOT_CONNECTED')
    }
    const operation = this.#beginControlOperation(request)
    const { identity } = operation
    this.#teardown('DETACHING', 'DETACH_REQUESTED', operation.token)
    try {
      this.#assertControlOperation(operation)
      const receipt = await this.#controls.detach({
        workspaceId: identity.workspaceId,
        attachmentId: identity.attachmentId,
        generation: identity.generation,
        leaseNumber: identity.leaseNumber,
        agentType: identity.agentType,
      })
      const checked = this.#checkDetachReceipt(identity, receipt)
      this.#assertControlOperation(operation)
      this.#finishControlOperation(operation)
      this.#setStatus('DETACHED')
      return checked
    } catch (error) {
      this.#failControlOperation(
        operation,
        error instanceof WAWBrowserControllerError &&
          error.code === 'CONTEXT_CHANGED'
          ? 'CONTEXT_CHANGED'
          : 'DETACH_FAILED',
      )
      throw error instanceof WAWBrowserControllerError
        ? error
        : new WAWBrowserControllerError('DETACH_FAILED')
    }
  }

  async stop(
    request: WAWBrowserControlRequest,
  ): Promise<WAWBrowserStopOutcome> {
    if (this.#status === 'DETACHING' || this.#status === 'STOPPING') {
      throw new WAWBrowserControllerError('CONTROLLER_BUSY')
    }
    if (!['CONNECTED', 'DETACHED', 'FENCED'].includes(this.#status)) {
      throw new WAWBrowserControllerError('CONTROLLER_NOT_CONNECTED')
    }
    const operation = this.#beginControlOperation(request)
    const { identity } = operation
    const alreadyDetached = this.#status === 'DETACHED'
    this.#teardown('STOPPING', 'STOP_REQUESTED', operation.token)
    let detachReceipt: WAWBrowserDetachReceipt | null = null
    if (!alreadyDetached) {
      try {
        this.#assertControlOperation(operation)
        detachReceipt = this.#checkDetachReceipt(
          identity,
          await this.#controls.detach({
            workspaceId: identity.workspaceId,
            attachmentId: identity.attachmentId,
            generation: identity.generation,
            leaseNumber: identity.leaseNumber,
            agentType: identity.agentType,
          }),
        )
        this.#assertControlOperation(operation)
      } catch (error) {
        this.#failControlOperation(
          operation,
          error instanceof WAWBrowserControllerError &&
            error.code === 'CONTEXT_CHANGED'
            ? 'CONTEXT_CHANGED'
            : 'DETACH_FAILED',
        )
        throw error instanceof WAWBrowserControllerError
          ? error
          : new WAWBrowserControllerError('DETACH_FAILED')
      }
    }
    try {
      this.#assertControlOperation(operation)
      const stopReceipt = this.#checkStopReceipt(
        identity,
        await this.#controls.stop({
          workspaceId: identity.workspaceId,
          generation: identity.generation,
          agentType: identity.agentType,
        }),
      )
      this.#assertControlOperation(operation)
      this.#finishControlOperation(operation)
      this.#identity = null
      this.#setStatus('STOPPED')
      return Object.freeze({
        detachConfirmed: alreadyDetached || detachReceipt !== null,
        detach: detachReceipt,
        stop: stopReceipt,
      })
    } catch (error) {
      this.#failControlOperation(
        operation,
        error instanceof WAWBrowserControllerError &&
          error.code === 'CONTEXT_CHANGED'
          ? 'CONTEXT_CHANGED'
          : 'STOP_FAILED',
      )
      throw error instanceof WAWBrowserControllerError
        ? error
        : new WAWBrowserControllerError('STOP_FAILED')
    }
  }

  handlePageLifecycle(
    event: 'pagehide' | 'freeze' | 'hidden' | 'unmount',
  ): void {
    if (this.#status === 'STOPPED' && this.#identity === null) return
    const reason: Record<typeof event, WAWBrowserFenceReason> = {
      pagehide: 'PAGEHIDE',
      freeze: 'PAGE_FROZEN',
      hidden: 'PAGE_HIDDEN',
      unmount: 'UNMOUNTED',
    }
    this.#teardown('FENCED', reason[event])
  }

  contextChanged(): void {
    if (this.#status === 'STOPPED' && this.#identity === null) return
    this.#teardown('FENCED', 'CONTEXT_CHANGED')
  }
}
