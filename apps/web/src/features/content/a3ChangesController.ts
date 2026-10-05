import {
  ContentError,
  MAX_PAGES,
  PROTOCOL_ID,
  contextDigest,
  encodeMessage,
  selectorCommitment,
  validateContext,
  type ContentContext,
} from './a3Content'
import { A3Browser, HANDSHAKE_TIMEOUT_MS, MAX_ENVELOPE_BYTES } from './a3Crypto'
import {
  parseA3Observation,
  sameA3Binding,
  type A3Binding,
} from './a3ChangesDto'
import {
  readA3Trust,
  a3TrustHost,
  type A3ChangesChannel,
  type A3ChangesDependencies,
  type A3TrustSnapshot,
} from './a3ChangesTrust'

export type A3ChangesStatus =
  | 'empty'
  | 'loading'
  | 'unavailable'
  | 'stale'
  | 'too-large'
  | 'binary'
  | 'permission'
  | 'failed'
  | 'completed'
export type A3ChangesSnapshot = Readonly<{
  status: A3ChangesStatus
  path: string | null
  text: string | null
  completedAtMs: number | null
}>
const snapshot = (
  status: A3ChangesStatus,
  path: string | null = null,
): A3ChangesSnapshot =>
  Object.freeze({ status, path, text: null, completedAtMs: null })
const equal = (a: Uint8Array, b: Uint8Array) =>
  a.length === b.length && a.every((value, index) => value === b[index])
function fail(code = 'PATCH_PROTOCOL_INVALID'): never {
  throw new ContentError(code)
}
function failureStatus(error: unknown): A3ChangesStatus {
  const code = error instanceof ContentError ? error.message : ''
  if (code === 'PATCH_STALE' || code === 'PATCH_TIMEOUT') return 'stale'
  if (code === 'PATCH_REVOKED') return 'permission'
  if (code === 'PATCH_TOO_LARGE') return 'too-large'
  if (code === 'PATCH_UNAVAILABLE_BINARY') return 'binary'
  if (code.startsWith('PATCH_UNAVAILABLE_')) return 'unavailable'
  return 'failed'
}

/** One page-owned read generation. No fetch until deliberate read(); no retries,
 * storage, logging, prefetch, partial output, or path-based transport requests. */
export class A3ChangesController {
  #snapshot: A3ChangesSnapshot
  #listeners = new Set<() => void>()
  #generation = 0
  #abort?: AbortController
  #role?: A3Browser
  #channel?: A3ChangesChannel
  #unsubscribeClose?: () => void
  #unsubscribeTrust?: () => void
  #timer?: ReturnType<typeof setTimeout>
  #trust?: A3TrustSnapshot
  #binding?: A3Binding
  #context?: ContentContext
  #deadline = 0
  #handshakeDeadline = 0
  #last = 0
  #ready = false
  #disposed = false
  constructor(
    readonly projectId: string,
    readonly dependencies?: A3ChangesDependencies,
  ) {
    this.#snapshot = snapshot(this.available ? 'empty' : 'unavailable')
  }
  get available(): boolean {
    if (!this.dependencies) return false
    try {
      const trust = readA3Trust(this.dependencies.trust)
      if ('binding' in trust) return trust.binding.project_id === this.projectId
      if (!this.dependencies.admission) return false
      this.dependencies.admission.check(null)
      return /^prj_[0-9a-f]{32}$/.test(this.projectId)
    } catch {
      return false
    }
  }
  activate(): void {
    this.#disposed = false
    if (this.dependencies && !this.#unsubscribeTrust) {
      this.#unsubscribeTrust = this.dependencies.trust.subscribeInvalidation(
        () => this.clear('permission'),
      )
    }
  }
  get snapshot(): A3ChangesSnapshot {
    return this.#snapshot
  }
  subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener)
    return () => this.#listeners.delete(listener)
  }
  #publish(value: A3ChangesSnapshot): void {
    this.#snapshot = value
    for (const listener of this.#listeners) listener()
  }
  #release(): void {
    const abort = this.#abort
    const role = this.#role
    const channel = this.#channel
    const unsubscribe = this.#unsubscribeClose
    this.#abort = undefined
    this.#role = undefined
    this.#channel = undefined
    this.#unsubscribeClose = undefined
    this.#trust = undefined
    this.#binding = undefined
    this.#context = undefined
    if (this.#timer !== undefined) clearTimeout(this.#timer)
    this.#timer = undefined
    // Drop ownership before invoking adapter cleanup, which may synchronously notify.
    try {
      unsubscribe?.()
    } catch {
      /* Already fenced locally. */
    }
    abort?.abort()
    role?.close()
    try {
      channel?.close()
    } catch {
      /* Already fenced locally. */
    }
  }
  clear(status: A3ChangesStatus = 'empty'): void {
    this.#generation += 1
    this.#publish(
      snapshot(status === 'empty' && !this.available ? 'unavailable' : status),
    )
    this.#release()
  }
  dispose(): void {
    this.#disposed = true
    this.clear()
    this.#unsubscribeTrust?.()
    this.#unsubscribeTrust = undefined
    this.#listeners.clear()
  }
  #owner(token: number): number {
    if (
      this.#disposed ||
      token !== this.#generation ||
      !this.#abort ||
      this.#abort.signal.aborted ||
      document.hidden
    )
      fail('PATCH_STALE')
    const deps = this.dependencies!
    const current = readA3Trust(deps.trust)
    const bound = this.#trust!
    const host = a3TrustHost(bound),
      currentHost = a3TrustHost(current)
    if (
      !equal(bound.pin32, current.pin32) ||
      host.runtime_host_installation_id !==
        currentHost.runtime_host_installation_id ||
      host.runtime_host_installation_revision !==
        currentHost.runtime_host_installation_revision ||
      'binding' in bound !== 'binding' in current
    )
      fail('PATCH_REVOKED')
    if (
      'binding' in bound &&
      'binding' in current &&
      (!sameA3Binding(bound.binding, current.binding) ||
        current.binding.project_id !== this.projectId)
    )
      fail('PATCH_REVOKED')
    if ('host' in current && !deps.admission) fail('PATCH_REVOKED')
    deps.admission?.check(this.#binding ?? null)
    this.#channel?.check?.()
    const now = deps.nowMs()
    if (
      !Number.isSafeInteger(now) ||
      now < this.#last ||
      now >= this.#deadline ||
      (!this.#ready && now >= this.#handshakeDeadline)
    )
      fail('PATCH_TIMEOUT')
    this.#last = now
    return now
  }
  #guard(token: number): void {
    this.#owner(token)
    this.#role?.check()
  }
  #schedule(token: number): void {
    if (this.#timer !== undefined) clearTimeout(this.#timer)
    const check = () => {
      if (token !== this.#generation || this.#disposed) return
      try {
        this.#owner(token)
        if (this.#snapshot.status !== 'completed') this.#role?.check()
        this.#schedule(token)
      } catch (error) {
        this.clear(failureStatus(error))
      }
    }
    const cap = this.#ready
      ? this.#deadline
      : Math.min(this.#deadline, this.#handshakeDeadline)
    this.#timer = setTimeout(check, Math.max(1, Math.min(50, cap - this.#last)))
  }
  async #send(token: number, bytes: Uint8Array): Promise<void> {
    if (
      !(bytes instanceof Uint8Array) ||
      bytes.constructor !== Uint8Array ||
      bytes.length < 1 ||
      bytes.length > MAX_ENVELOPE_BYTES
    )
      fail()
    this.#guard(token) // No await before handing the one whole record to its owner.
    await this.#channel!.send(bytes, () => this.#guard(token))
    this.#guard(token)
  }
  async #receive(token: number): Promise<Uint8Array> {
    this.#guard(token)
    const raw = await this.#channel!.receive(() => this.#guard(token))
    this.#guard(token)
    if (
      !(raw instanceof Uint8Array) ||
      raw.constructor !== Uint8Array ||
      raw.length < 1 ||
      raw.length > MAX_ENVELOPE_BYTES
    )
      fail()
    return raw
  }
  async read(
    row: Readonly<{ path: string; kind: string; staged: boolean }>,
  ): Promise<void> {
    this.clear()
    if (this.#disposed) return
    if (
      !this.dependencies ||
      !this.available ||
      !row.staged ||
      !['added', 'modified', 'deleted'].includes(row.kind)
    ) {
      this.#publish(snapshot('unavailable', row.path))
      return
    }
    const token = this.#generation
    const deps = this.dependencies
    const abort = new AbortController()
    this.#abort = abort
    this.#publish(snapshot('loading', row.path))
    try {
      this.#trust = readA3Trust(deps.trust)
      this.#last = deps.nowMs()
      if (!Number.isSafeInteger(this.#last) || this.#last < 0) fail()
      this.#deadline = this.#last + 30_000
      this.#handshakeDeadline = this.#last + HANDSHAKE_TIMEOUT_MS
      this.#ready = false
      this.#guard(token)
      this.#schedule(token)
      const observed = parseA3Observation(
        await deps.observe(this.projectId, abort.signal),
      )
      this.#guard(token)
      const host = a3TrustHost(this.#trust)
      if (
        observed.binding.project_id !== this.projectId ||
        observed.binding.runtime_host_installation_id !==
          host.runtime_host_installation_id ||
        observed.binding.runtime_host_installation_revision !==
          host.runtime_host_installation_revision ||
        ('binding' in this.#trust &&
          !sameA3Binding(observed.binding, this.#trust.binding))
      )
        fail('PATCH_STALE')
      this.#binding = observed.binding
      this.#guard(token)
      if (!observed.entries.length) {
        this.clear('empty')
        return
      }
      const entry = observed.entries.find((entry) => entry.path === row.path)
      if (!entry || entry.kind !== row.kind) fail('PATCH_STALE')
      if (!entry.selection_id)
        fail(entry.unavailable_code ?? 'PATCH_UNAVAILABLE_KIND')
      const selectionId = entry.selection_id
      const nonceBytes = crypto.getRandomValues(new Uint8Array(32))
      const requestNonce = Array.from(nonceBytes, (byte) =>
        byte.toString(16).padStart(2, '0'),
      ).join('')
      nonceBytes.fill(0)
      const commitment = await selectorCommitment(selectionId)
      this.#guard(token)
      const { auth_epoch, ...binding } = observed.binding
      void auth_epoch // Kept in owner trust; v1 content context is unchanged.
      this.#context = validateContext({
        ...binding,
        protocol_id: PROTOCOL_ID,
        protocol_version: 1,
        side: 'staged',
        selector_commitment: commitment,
        request_nonce: requestNonce,
      })
      this.#role = new A3Browser(
        this.#context,
        {
          current: () => ({
            context: this.#context!,
            nowMs: this.#owner(token),
            runtimePin: readA3Trust(deps.trust).pin32,
          }),
        },
        {
          admissionStartedAtMs: this.#last,
          admissionExpiresAtMs: this.#deadline,
        },
      )
      const channel = await deps.open(
        { projectId: this.projectId, selectionId, requestNonce },
        abort.signal,
      )
      if (token !== this.#generation || abort.signal.aborted) {
        channel.close()
        return
      }
      this.#channel = channel
      const unsubscribe = channel.subscribeClose(() => this.clear('stale'))
      if (token !== this.#generation) {
        unsubscribe()
        return
      }
      this.#unsubscribeClose = unsubscribe
      this.#guard(token)
      const role = this.#role!
      await this.#send(token, await role.start())
      const confirm = await role.acceptAttest(await this.#receive(token))
      this.#deadline = Math.min(this.#deadline, role.effectiveDeadlineMs)
      channel.tightenDeadline?.(this.#deadline)
      this.#guard(token)
      this.#schedule(token)
      await this.#send(token, confirm)
      await role.acceptAck(await this.#receive(token))
      this.#guard(token)
      this.#ready = true
      const digest = await contextDigest(this.#context)
      this.#guard(token)
      await this.#send(
        token,
        await role.encryptRead(
          encodeMessage({
            protocol_id: PROTOCOL_ID,
            protocol_version: 1,
            context_digest: digest,
            request_nonce: requestNonce,
            kind: 'PATCH_READ',
            selection_id: selectionId,
          }),
        ),
      )
      for (let count = 0; count <= MAX_PAGES; count++) {
        const result = await role.acceptResponse(await this.#receive(token))
        this.#owner(token)
        if (result !== undefined) {
          const text = new TextDecoder('utf-8', {
            fatal: true,
            ignoreBOM: true,
          }).decode(result)
          result.fill(0)
          this.#owner(token) // Immediate fence, no await before React state publication.
          this.#publish(
            Object.freeze({
              status: 'completed',
              path: row.path,
              text,
              completedAtMs: Date.now(),
            }),
          )
          if (!deps.retainCompletedChannel) {
            this.#unsubscribeClose?.()
            this.#unsubscribeClose = undefined
            this.#channel = undefined
            channel.close()
          }
          // Keep the ORIGINAL authenticated deadline and trust/lifecycle watch.
          this.#schedule(token)
          return
        }
      }
      fail()
    } catch (error) {
      if (token === this.#generation) {
        this.clear(failureStatus(error))
      }
    }
  }
}
