/** Fixed A3 native WebSocket and authenticated metadata adapter. No retry/fallback. */
import { exactRecord } from '../workspace/wawCryptoContext'
import { ContentError, ERROR_CODES } from './a3Content'
import { MAX_ENVELOPE_BYTES } from './a3Crypto'
import {
  parseA3Observation,
  sameA3Binding,
  type A3Binding,
  type A3StagedObservation,
} from './a3ChangesDto'
import type { A3ChangesChannel, A3ChangesDependencies } from './a3ChangesTrust'
import { a3HTTPSTrustSelected, A3HTTPSTrustConsumer } from './a3TrustHTTPS'

export const A3_NATIVE_SUBPROTOCOL = 'agentbox-a3-content-v2'
const enc = new TextEncoder()
function fail(code = 'PATCH_PROTOCOL_INVALID'): never {
  throw new ContentError(code)
}
const equal = (a: Uint8Array, b: Uint8Array) =>
  a.length === b.length && a.every((value, index) => value === b[index])
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  // Cleanup can reject before a caller has installed its await handler.
  void promise.catch(() => undefined)
  return { promise, resolve, reject }
}
function control(magic: string, sequence: number, tail: Uint8Array) {
  if (!Number.isInteger(sequence) || sequence < 0 || sequence > 0xffffffff)
    fail()
  const raw = new Uint8Array(9 + tail.length)
  raw.set(enc.encode(magic))
  raw[4] = 1
  new DataView(raw.buffer).setUint32(5, sequence, false)
  raw.set(tail, 9)
  return raw
}
function magic(raw: Uint8Array): string {
  return String.fromCharCode(...raw.subarray(0, 4))
}

/** One pending data record plus fixed ACK/challenge mailboxes, never a growing queue.
 * A3CR is an outer HTTPS observation, NOT a Runtime-signed revocation proof. */
class NativeA3Channel implements A3ChangesChannel {
  readonly #socket: WebSocket
  readonly #opened = deferred<A3ChangesChannel>()
  readonly #listeners = new Set<() => void>()
  #deadline: number
  #last: number
  #closed = false
  #error: ContentError = new ContentError('PATCH_STALE')
  #ready = false
  #exposed = false
  #writing = false
  #sending = false
  #consuming = false
  #slot?: Uint8Array
  #receiver?: ReturnType<typeof deferred<Uint8Array>> & { guard: () => void }
  #recordSequence = 0
  #challengeSequence = 0
  #challenge?: { raw: Uint8Array; issued: number; sent: boolean }
  #freshUntil = 0
  #nextChallenge = 0
  #timer?: ReturnType<typeof setInterval>
  #openTimeout?: ReturnType<typeof setTimeout>
  constructor(
    url: string,
    readonly opener: string,
    readonly signal: AbortSignal,
    readonly guard: () => void,
    readonly nowMs: () => number,
    readonly onClosed: (channel: NativeA3Channel) => void,
  ) {
    this.#last = nowMs()
    this.#deadline = this.#last + 30000
    this.#base()
    this.#socket = new WebSocket(url, A3_NATIVE_SUBPROTOCOL)
    this.#socket.binaryType = 'arraybuffer'
    this.#socket.addEventListener('open', this.#onOpen)
    this.#socket.addEventListener('message', this.#onMessage)
    this.#socket.addEventListener('close', this.#onClose)
    this.#socket.addEventListener('error', this.#onClose)
    signal.addEventListener('abort', this.#onClose, { once: true })
    this.#openTimeout = setTimeout(
      () => this.#terminate(new ContentError('PATCH_TIMEOUT')),
      5000,
    )
    this.#timer = setInterval(() => {
      try {
        const now = this.#base()
        if (this.#exposed) this.check()
        if (this.#challenge && now >= this.#challenge.issued + 1000)
          fail('PATCH_STALE')
        if (this.#ready && !this.#challenge && now >= this.#nextChallenge)
          this.#issueChallenge()
      } catch (error) {
        this.#terminate(error)
      }
    }, 50)
    if (signal.aborted) this.#onClose()
  }
  get opened(): Promise<A3ChangesChannel> {
    return this.#opened.promise
  }
  #base(): number {
    if (this.#closed) throw this.#error
    this.guard()
    const now = this.nowMs()
    if (this.signal.aborted || document.hidden) fail('PATCH_STALE')
    if (
      !Number.isSafeInteger(now) ||
      now < this.#last ||
      now < 0 ||
      now >= this.#deadline
    )
      fail('PATCH_TIMEOUT')
    this.#last = now
    return now
  }
  check(): void {
    try {
      const now = this.#base()
      if (!this.#exposed || now >= this.#freshUntil) fail('PATCH_STALE')
    } catch (error) {
      this.#terminate(error)
      throw this.#error
    }
  }
  tightenDeadline(deadlineMs: number): void {
    try {
      this.check()
      if (
        !Number.isSafeInteger(deadlineMs) ||
        deadlineMs > this.#deadline ||
        deadlineMs <= this.#base()
      )
        fail('PATCH_TIMEOUT')
      this.#deadline = deadlineMs
    } catch (error) {
      this.#terminate(error)
      throw this.#error
    }
  }
  #onOpen = () => {
    try {
      this.#base()
      if (
        this.#socket.protocol !== A3_NATIVE_SUBPROTOCOL ||
        this.#socket.readyState !== WebSocket.OPEN ||
        this.#socket.bufferedAmount !== 0
      )
        fail()
      // Exact Origin/CSRF initial message only; credentials never enter the URL.
      this.#socket.send(new Uint8Array(enc.encode(this.opener)))
    } catch (error) {
      this.#terminate(error)
    }
  }
  #onClose = () => {
    this.#terminate(new ContentError('PATCH_STALE'))
  }
  #onMessage = (event: MessageEvent<unknown>) => {
    try {
      this.#base()
      if (
        !(event.data instanceof ArrayBuffer) ||
        event.data.constructor !== ArrayBuffer
      )
        fail()
      if (!event.data.byteLength || event.data.byteLength > MAX_ENVELOPE_BYTES)
        fail()
      const raw = new Uint8Array(event.data).slice()
      const kind = magic(raw)
      if (kind === 'A3ER') {
        if (
          raw.length < 6 ||
          raw.length > 100 ||
          raw[4] !== 1 ||
          raw.subarray(5).some((b) => b > 127)
        )
          fail()
        const code = new TextDecoder('ascii').decode(raw.subarray(5))
        if (!ERROR_CODES.includes(code)) fail()
        fail(code)
      }
      if (kind === 'A3RD') {
        if (this.#ready || raw.length !== 5 || raw[4] !== 1) fail()
        this.#ready = true
        this.#issueChallenge()
        return
      }
      if (kind === 'A3CR') {
        // A delayed matching reply cannot revive expired prior freshness.
        if (this.#exposed) this.check()
        const challenge = this.#challenge
        if (
          !this.#ready ||
          !challenge ||
          !challenge.sent ||
          raw.length !== 25 ||
          raw[4] !== 1 ||
          !equal(raw.subarray(5), challenge.raw.subarray(5)) ||
          this.#base() >= challenge.issued + 1000
        )
          fail()
        this.#freshUntil = challenge.issued + 1000
        this.#nextChallenge = challenge.issued + 250
        this.#challenge = undefined
        if (!this.#exposed) {
          this.#exposed = true
          clearTimeout(this.#openTimeout)
          this.check()
          this.#opened.resolve(this)
        }
        return
      }
      if (kind.startsWith('A3')) fail() // No wrong-direction/unknown transport controls.
      this.check()
      if (!this.#ready || this.#slot) fail()
      this.#slot = raw
      this.#deliver()
    } catch (error) {
      this.#terminate(error)
    }
  }
  #issueChallenge(): void {
    if (this.#challenge) fail()
    const issued = this.#base()
    const raw = control(
      'A3CQ',
      this.#challengeSequence++,
      crypto.getRandomValues(new Uint8Array(16)),
    )
    const challenge = { raw, issued, sent: false }
    this.#challenge = challenge
    void this.#write(
      raw,
      () => {
        this.#base()
        if (this.#exposed) this.check()
        if (this.#challenge !== challenge || this.#base() >= issued + 1000)
          fail('PATCH_STALE')
      },
      () => {
        challenge.sent = true
      },
    ).catch((error) => this.#terminate(error))
  }
  async #write(
    raw: Uint8Array,
    guard: () => void,
    beforeSend?: () => void,
  ): Promise<void> {
    const started = this.#base()
    // There are only three possible fixed callers: one data send, ACK and challenge.
    while (this.#writing) {
      guard()
      if (this.#base() >= started + 1000) fail('PATCH_TIMEOUT')
      await new Promise<void>((resolve) => setTimeout(resolve, 5))
    }
    this.#writing = true
    try {
      for (;;) {
        guard()
        if (this.#base() >= started + 1000) fail('PATCH_TIMEOUT')
        if (
          this.#socket.readyState !== WebSocket.OPEN ||
          this.#socket.bufferedAmount > MAX_ENVELOPE_BYTES
        )
          fail()
        if (this.#socket.bufferedAmount === 0) break
        await new Promise<void>((resolve) => setTimeout(resolve, 5))
      }
      guard()
      this.#base()
      beforeSend?.()
      // No await between final currentness and the actual browser send frontier.
      this.#socket.send(raw)
    } finally {
      this.#writing = false
    }
  }
  async send(value: Uint8Array, checkCurrent: () => void): Promise<void> {
    try {
      this.check()
      if (
        this.#sending ||
        !(value instanceof Uint8Array) ||
        value.constructor !== Uint8Array ||
        value.length < 1 ||
        value.length > MAX_ENVELOPE_BYTES
      )
        fail()
      this.#sending = true
      const raw = new Uint8Array(value)
      await this.#write(raw, () => {
        this.check()
        checkCurrent()
      })
      this.check()
      checkCurrent()
    } catch (error) {
      this.#terminate(error)
      throw this.#error
    } finally {
      this.#sending = false
    }
  }
  receive(checkCurrent: () => void = () => undefined): Promise<Uint8Array> {
    try {
      this.check()
      checkCurrent()
      if (this.#receiver || this.#consuming) fail()
      const result = { ...deferred<Uint8Array>(), guard: checkCurrent }
      this.#receiver = result
      this.#deliver()
      return result.promise
    } catch (error) {
      this.#terminate(error)
      return Promise.reject(this.#error)
    }
  }
  #deliver(): void {
    const receiver = this.#receiver,
      raw = this.#slot
    if (!receiver || !raw || this.#consuming) return
    this.#consuming = true
    void (async () => {
      this.check()
      receiver.guard()
      const digest = new Uint8Array(
        await crypto.subtle.digest('SHA-256', new Uint8Array(raw).buffer),
      )
      this.check()
      receiver.guard()
      const ack = control('A3CA', this.#recordSequence++, digest)
      await this.#write(
        ack,
        () => {
          this.check()
          receiver.guard()
        },
        () => {
          if (this.#receiver !== receiver || this.#slot !== raw) fail()
          this.#slot = undefined
        },
      )
      this.check()
      receiver.guard()
      this.#receiver = undefined
      this.#consuming = false
      receiver.resolve(raw)
    })().catch((error) => this.#terminate(error))
  }
  #terminate(error: unknown): void {
    if (this.#closed) return
    this.#closed = true
    this.#error = error instanceof ContentError ? error : new ContentError()
    clearInterval(this.#timer)
    clearTimeout(this.#openTimeout)
    this.signal.removeEventListener('abort', this.#onClose)
    this.#socket?.removeEventListener('open', this.#onOpen)
    this.#socket?.removeEventListener('message', this.#onMessage)
    this.#socket?.removeEventListener('close', this.#onClose)
    this.#socket?.removeEventListener('error', this.#onClose)
    this.#slot = this.#challenge = undefined
    this.#receiver?.reject(this.#error)
    this.#receiver = undefined
    this.#opened.reject(this.#error)
    try {
      this.#socket?.close()
    } catch {
      /* Already fenced. */
    }
    this.onClosed(this)
    for (const listener of this.#listeners) listener()
    this.#listeners.clear()
  }
  close(): void {
    this.#terminate(new ContentError('PATCH_STALE'))
  }
  subscribeClose(listener: () => void): () => void {
    if (this.#closed) {
      listener()
      return () => undefined
    }
    this.#listeners.add(listener)
    return () => this.#listeners.delete(listener)
  }
}

async function observation(
  url: string,
  csrfToken: string,
  signal: AbortSignal,
): Promise<A3StagedObservation> {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    redirect: 'error',
    mode: 'same-origin',
    referrerPolicy: 'no-referrer',
    signal,
    headers: { Accept: 'application/json', 'X-CSRF-Token': csrfToken },
  })
  if (signal.aborted) fail('PATCH_STALE')
  if (
    response.url !== url ||
    response.redirected ||
    !response.body ||
    !/^application\/json(?:;\s*charset=utf-8)?$/i.test(
      response.headers.get('content-type') ?? '',
    )
  )
    fail()
  const reader = response.body.getReader(),
    chunks: Uint8Array[] = []
  let total = 0
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (signal.aborted) fail('PATCH_STALE')
      if (done) break
      total += value.byteLength
      if (total > 2 * 1024 * 1024) fail('PATCH_TOO_LARGE')
      chunks.push(value)
    }
  } finally {
    void reader.cancel().catch(() => undefined)
  }
  const bytes = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    bytes.set(chunk, offset)
    offset += chunk.byteLength
  }
  const value: unknown = JSON.parse(
    new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes),
  )
  if (response.status !== 200) {
    if (response.status === 401 || response.status === 403)
      fail('PATCH_REVOKED')
    const envelope = exactRecord(value, ['api_version', 'request_id', 'error'])
    const error = exactRecord(envelope.error, [
      'code',
      'category',
      'message',
      'retryable',
      'details',
    ])
    fail(
      typeof error.code === 'string' && ERROR_CODES.includes(error.code)
        ? error.code
        : undefined,
    )
  }
  const envelope = exactRecord(value, ['api_version', 'request_id', 'data'])
  if (
    envelope.api_version !== 'v1' ||
    typeof envelope.request_id !== 'string' ||
    !/^[A-Za-z0-9._:-]{1,96}$/.test(envelope.request_id)
  )
    fail()
  return parseA3Observation(envelope.data)
}

export type A3NativeOwner = Readonly<{
  dependencies: A3ChangesDependencies
  close(): void
}>
/** The formal route calls this factory; no API/bootstrap value can choose an address. */
export async function createA3ChangesNative(options: {
  projectId: string
  csrfToken: string
  isCurrent(): boolean
  signal: AbortSignal
}): Promise<A3NativeOwner | undefined> {
  if (!a3HTTPSTrustSelected()) return undefined
  if (
    !/^prj_[0-9a-f]{32}$/.test(options.projectId) ||
    !options.csrfToken ||
    options.csrfToken.length > 4096 ||
    !options.isCurrent() ||
    options.signal.aborted
  )
    fail('PATCH_REVOKED')
  const consumer = new A3HTTPSTrustConsumer()
  const listeners = new Set<() => void>(),
    channels = new Set<NativeA3Channel>()
  let closed = false
  let current:
    | { observation: A3StagedObservation; signal: AbortSignal; opened: boolean }
    | undefined
  let generation = 0
  const close = () => {
    if (closed) return
    closed = true
    generation++
    current = undefined
    options.signal.removeEventListener('abort', close)
    consumer.close()
    for (const channel of channels) channel.close()
    channels.clear()
    for (const listener of listeners) listener()
    listeners.clear()
  }
  options.signal.addEventListener('abort', close, { once: true })
  try {
    const lease = await consumer.authorize()
    lease.signal.addEventListener('abort', close, { once: true })
    const base = () => {
      if (
        closed ||
        options.signal.aborted ||
        !options.isCurrent() ||
        !lease.current()
      ) {
        close()
        fail('PATCH_REVOKED')
      }
    }
    base()
    const check = (binding: A3Binding | null) => {
      base()
      if (
        binding &&
        (!current ||
          current.signal.aborted ||
          !sameA3Binding(binding, current.observation.binding))
      )
        fail('PATCH_REVOKED')
    }
    const origin = lease.bootstrap.origin
    const nowMs = () => Math.floor(performance.now())
    const dependencies: A3ChangesDependencies = {
      trust: {
        current: () => {
          try {
            base()
            return lease.current()
          } catch {
            return null
          }
        },
        subscribeInvalidation(listener) {
          if (closed) {
            listener()
            return () => undefined
          }
          listeners.add(listener)
          return () => listeners.delete(listener)
        },
      },
      admission: { check },
      retainCompletedChannel: true,
      nowMs,
      async observe(projectId, signal) {
        base()
        if (projectId !== options.projectId || signal.aborted)
          fail('PATCH_REVOKED')
        const token = ++generation
        current = undefined
        const abort = new AbortController()
        const cancel = () => abort.abort()
        signal.addEventListener('abort', cancel, { once: true })
        options.signal.addEventListener('abort', cancel, { once: true })
        lease.signal.addEventListener('abort', cancel, { once: true })
        const timeout = setTimeout(cancel, 5000)
        try {
          const result = await observation(
            new URL(
              `/api/v1/projects/${projectId}/git/staged-observation`,
              origin,
            ).href,
            options.csrfToken,
            abort.signal,
          )
          base()
          if (signal.aborted || abort.signal.aborted || generation !== token)
            fail('PATCH_STALE')
          const host = lease.current()!.host
          if (
            result.binding.project_id !== projectId ||
            result.binding.runtime_host_installation_id !==
              host.runtime_host_installation_id ||
            result.binding.runtime_host_installation_revision !==
              host.runtime_host_installation_revision
          )
            fail('PATCH_REVOKED')
          current = { observation: result, signal, opened: false }
          return result
        } finally {
          clearTimeout(timeout)
          signal.removeEventListener('abort', cancel)
          options.signal.removeEventListener('abort', cancel)
          lease.signal.removeEventListener('abort', cancel)
        }
      },
      async open(request, signal) {
        const admitted = current
        if (
          !admitted ||
          admitted.signal !== signal ||
          admitted.opened ||
          signal.aborted ||
          request.projectId !== options.projectId ||
          !/^[0-9a-f]{64}$/.test(request.requestNonce) ||
          !/^[A-Za-z0-9_-]{156}$/.test(request.selectionId) ||
          !admitted.observation.entries.some(
            (e) => e.selection_id === request.selectionId,
          )
        )
          fail('PATCH_STALE')
        check(admitted.observation.binding)
        admitted.opened = true // Never retry an uncertain opening for this observation.
        const opener = JSON.stringify({
          schema_version: 'a3-open/v1',
          selection_id: request.selectionId,
          request_nonce: request.requestNonce,
          csrf_token: options.csrfToken,
        })
        if (enc.encode(opener).length > 8192) fail()
        const url = new URL(
          `/api/v1/projects/${options.projectId}/git/staged-stream`,
          origin,
        )
        url.protocol = 'wss:'
        const channel = new NativeA3Channel(
          url.href,
          opener,
          signal,
          () => {
            if (current !== admitted) fail('PATCH_STALE')
            check(admitted.observation.binding)
          },
          nowMs,
          (closedChannel) => {
            channels.delete(closedChannel)
          },
        )
        channels.add(channel)
        try {
          return await channel.opened
        } catch (error) {
          channel.close()
          channels.delete(channel)
          throw error
        }
      },
    }
    return Object.freeze({ dependencies, close })
  } catch (error) {
    close()
    throw error
  }
}
