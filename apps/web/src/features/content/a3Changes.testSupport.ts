/** Test-only synthetic counterpart: actual A3 crypto, never production wiring. */
import { vi } from 'vitest'
import { generateX25519KeyPair } from '../workspace/noiseNx'
import { A3Runtime, CRYPTO_PROTOCOL_ID } from './a3Crypto'
import {
  ContentError,
  PROTOCOL_ID,
  contextDigest,
  encodeMessage,
  preparePages,
  selectorCommitment,
  validateContext,
} from './a3Content'
import type { A3Binding } from './a3ChangesDto'
import type { A3ChangesDependencies, A3ChangesTrust } from './a3ChangesTrust'

export const a3TestProject = `prj_${'a'.repeat(32)}`
export const a3TestRow = { path: 'success.txt', kind: 'modified', staged: true }
export const a3DangerousPatch = `diff --git a/success.txt b/success.txt\n+<img src=x onerror="window.a3Executed=true"><script>alert(1)</script>\n+[click](javascript:alert(2)) 你好 🌍\n${'+synthetic row\n'.repeat(2000)}`
export async function createA3TestFixture(
  options: {
    holdEnd?: boolean
    malformed?: boolean
    dropPage?: boolean
    errorCode?: string
    lifetime?: number
    patch?: string
  } = {},
) {
  const keys = await generateX25519KeyPair()
  const pin = new Uint8Array(
    await crypto.subtle.exportKey('raw', keys.publicKey),
  )
  let now = 1000
  const binding: A3Binding = Object.freeze({
    project_id: a3TestProject,
    project_revision: '1',
    binding_revision: '1',
    binding_digest: 'b'.repeat(64),
    runtime_host_installation_id: `wri_${'c'.repeat(32)}`,
    runtime_host_installation_revision: '1',
    runtime_epoch: '1',
    session_scope: 'd'.repeat(64),
    auth_epoch: '1',
  })
  let trust: A3ChangesTrust = {
    purpose: CRYPTO_PROTOCOL_ID,
    binding,
    pin32: pin,
  }
  let selection = 0
  const listeners = new Set<() => void>()
  const closeListeners = new Set<() => void>()
  let release: (() => void) | undefined
  let held = false
  let closed = 0
  let sent = 0
  const requests: Parameters<A3ChangesDependencies['open']>[0][] = []
  const observation = () => ({
    schema_version: 'a3-staged-observation/v1',
    snapshot_sha256: 'e'.repeat(64),
    binding,
    entries: [
      {
        path: a3TestRow.path,
        kind: 'modified',
        side: 'staged',
        selection_id: String(++selection).padStart(156, 'A'),
        unavailable_code: null,
      },
    ],
  })
  const deps: A3ChangesDependencies = {
    trust: {
      current: () => trust,
      subscribeInvalidation: (listener) => {
        listeners.add(listener)
        return () => listeners.delete(listener)
      },
    },
    nowMs: () => now,
    observe: vi.fn(async () => observation()),
    open: vi.fn(async (request, signal) => {
      requests.push(request)
      const { auth_epoch, ...fields } = binding
      void auth_epoch
      const context = validateContext({
        ...fields,
        protocol_id: PROTOCOL_ID,
        protocol_version: 1,
        side: 'staged',
        selector_commitment: await selectorCommitment(request.selectionId),
        request_nonce: request.requestNonce,
      })
      const runtime = new A3Runtime(
        context,
        { current: () => ({ context, runtimePin: pin, nowMs: now }) },
        {
          admissionStartedAtMs: now,
          admissionExpiresAtMs: now + (options.lifetime ?? 30_000),
        },
        keys,
      )
      const queue: Uint8Array[] = []
      let step = 0
      let received = 0
      let ownClosed = false
      return {
        async send(raw: Uint8Array, checkCurrent: () => void) {
          checkCurrent()
          if (signal.aborted || ownClosed) throw new ContentError()
          sent += 1
          if (step++ === 0) queue.push(await runtime.acceptInit(raw))
          else if (step === 2) queue.push(await runtime.acceptConfirm(raw))
          else {
            await runtime.decryptRead(raw)
            const pages = options.errorCode
              ? [
                  encodeMessage({
                    protocol_id: PROTOCOL_ID,
                    protocol_version: 1,
                    kind: 'PATCH_ERROR',
                    context_digest: await contextDigest(context),
                    request_nonce: request.requestNonce,
                    code: options.errorCode,
                  }),
                ]
              : await preparePages(
                  context,
                  new Uint8Array(
                    new TextEncoder().encode(options.patch ?? a3DangerousPatch),
                  ),
                  '1791111111111',
                )
            for (const page of pages)
              queue.push(await runtime.encryptResponse(page))
            if (options.dropPage) queue.shift()
            if (options.malformed) queue[0] = new Uint8Array(24 * 1024 + 1)
          }
        },
        async receive() {
          received += 1
          if (options.holdEnd && received > 2 && queue.length === 1) {
            held = true
            await new Promise<void>((resolve) => {
              release = resolve
            })
          }
          const frame = queue.shift()
          if (!frame) throw new ContentError()
          return frame
        },
        close() {
          ownClosed = true
          closed += 1
          runtime.close()
        },
        subscribeClose(listener: () => void) {
          closeListeners.add(listener)
          return () => closeListeners.delete(listener)
        },
      }
    }),
  }
  return {
    deps,
    binding,
    requests,
    observation,
    get held() {
      return held
    },
    get closed() {
      return closed
    },
    get sent() {
      return sent
    },
    now: (value: number) => {
      now = value
    },
    release: () => {
      release?.()
      release = undefined
    },
    invalidate: (change: Partial<A3ChangesTrust> = {}) => {
      trust = { ...trust, ...change }
      for (const listener of listeners) listener()
    },
    silentlyChange: (change: Partial<A3ChangesTrust>) => {
      trust = { ...trust, ...change }
    },
    disconnect: () => {
      for (const listener of closeListeners) listener()
    },
  }
}
