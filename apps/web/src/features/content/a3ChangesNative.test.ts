import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { A3ChangesController } from './a3ChangesController'
import {
  a3DangerousPatch,
  a3TestProject,
  a3TestRow,
  createA3TestFixture,
} from './a3Changes.testSupport'
import {
  createA3ChangesNative,
  A3_NATIVE_SUBPROTOCOL,
  type A3NativeOwner,
} from './a3ChangesNative'
import { A3_BOOTSTRAP_PATH } from './a3TrustHTTPS'
import {
  nativeOrigin,
  nativeBootstrap,
  nativeResponse,
  staticResponse,
  NativeTestSocket,
  selectNativeBootstrap,
} from './a3Native.testSupport'
import type { A3ChangesChannel } from './a3ChangesTrust'
import { ContentError } from './a3Content'

let elapsed = 1000
const owners: A3NativeOwner[] = [],
  controllers: A3ChangesController[] = []
const kind = (raw: Uint8Array) => String.fromCharCode(...raw.subarray(0, 4))
beforeEach(() => {
  selectNativeBootstrap()
  elapsed = 1000
  vi.spyOn(performance, 'now').mockImplementation(() => elapsed)
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('WebSocket', NativeTestSocket)
  NativeTestSocket.instances = []
  NativeTestSocket.onCreate = undefined
})
afterEach(() => {
  controllers.splice(0).forEach((value) => value.dispose())
  owners.splice(0).forEach((value) => value.close())
  document.head.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
async function setup(
  options: {
    observe?: boolean
    current?: () => boolean
    lifetime?: number
    modify?: (value: object) => object
  } = {},
) {
  const fixture = await createA3TestFixture({ lifetime: options.lifetime })
  const data = fixture.observation()
  const trust = fixture.deps.trust.current()!
  const bootstrap = {
    ...nativeBootstrap,
    runtime_attestation_x25519_public_key: Array.from(trust.pin32, (b) =>
      b.toString(16).padStart(2, '0'),
    ).join(''),
  }
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const path = new URL(String(input)).pathname
    if (path === A3_BOOTSTRAP_PATH) return staticResponse(bootstrap)
    return nativeResponse(path, {
      api_version: 'v1',
      request_id: 'req_native',
      data: options.modify?.(data) ?? data,
    })
  })
  vi.stubGlobal('fetch', fetch)
  const abort = new AbortController(),
    readAbort = new AbortController()
  const owner = (await createA3ChangesNative({
    projectId: a3TestProject,
    csrfToken: 'csrf-native-only',
    signal: abort.signal,
    isCurrent: options.current ?? (() => true),
  }))!
  owners.push(owner)
  if (options.observe !== false)
    await owner.dependencies.observe(a3TestProject, readAbort.signal)
  const request = {
    projectId: a3TestProject,
    selectionId: data.entries[0].selection_id!,
    requestNonce: 'f'.repeat(64),
  }
  return {
    fixture,
    data,
    bootstrap,
    fetch,
    abort,
    readAbort,
    owner,
    request,
    open: () => owner.dependencies.open(request, readAbort.signal),
  }
}
async function opened() {
  const f = await setup()
  const channel = await f.open()
  const socket = NativeTestSocket.instances.at(-1)!
  return { ...f, channel, socket }
}

describe('formal A3 native factory', () => {
  it('makes no A3 network calls without its own static marker pair', async () => {
    document.head.innerHTML = ''
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect(
      await createA3ChangesNative({
        projectId: a3TestProject,
        csrfToken: 'csrf',
        signal: new AbortController().signal,
        isCurrent: () => true,
      }),
    ).toBeUndefined()
    expect(fetch).not.toHaveBeenCalled()
    expect(NativeTestSocket.instances).toHaveLength(0)
  })
  it('does not prefetch metadata/content and sends exact credentialed metadata POST only on observation', async () => {
    const f = await setup({ observe: false })
    expect(f.fetch).toHaveBeenCalledTimes(2)
    expect(NativeTestSocket.instances).toHaveLength(0)
    await f.owner.dependencies.observe(a3TestProject, f.readAbort.signal)
    expect(f.fetch).toHaveBeenLastCalledWith(
      `${nativeOrigin}/api/v1/projects/${a3TestProject}/git/staged-observation`,
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          'X-CSRF-Token': 'csrf-native-only',
        },
      }),
    )
    expect(f.fetch.mock.calls.at(-1)![1]).not.toHaveProperty('body')
    expect(f.owner.dependencies.trust.current()).not.toHaveProperty('binding')
  })
  it('opens exact WSS URL and binary closed JSON, waits READY and currentness before resolution', async () => {
    const { socket, channel, request } = await opened()
    expect(socket.url).toBe(
      `wss://a3.agentbox.test/api/v1/projects/${a3TestProject}/git/staged-stream`,
    )
    expect(socket.requestedProtocol).toBe(A3_NATIVE_SUBPROTOCOL)
    expect(socket.binaryType).toBe('arraybuffer')
    expect(JSON.parse(new TextDecoder().decode(socket.sent[0]))).toEqual({
      schema_version: 'a3-open/v1',
      selection_id: request.selectionId,
      request_nonce: request.requestNonce,
      csrf_token: 'csrf-native-only',
    })
    expect(socket.sent[1]).toHaveLength(25)
    expect(kind(socket.sent[1])).toBe('A3CQ')
    expect(() => channel.check!()).not.toThrow()
  })
  it('burns one native opening per observation and rejects selector/path/origin substitution', async () => {
    const f = await setup()
    await expect(
      f.owner.dependencies.open(
        { ...f.request, selectionId: 'Z'.repeat(156) },
        f.readAbort.signal,
      ),
    ).rejects.toThrow()
    await expect(
      f.owner.dependencies.open(
        { ...f.request, projectId: `${a3TestProject}?target=other` },
        f.readAbort.signal,
      ),
    ).rejects.toThrow()
    expect(NativeTestSocket.instances).toHaveLength(0)
    await f.open()
    await expect(f.open()).rejects.toThrow()
    expect(NativeTestSocket.instances).toHaveLength(1)
  })
  it.each([
    'project_id',
    'runtime_host_installation_id',
    'runtime_host_installation_revision',
  ])(
    'rejects authenticated metadata with mismatched %s before WS',
    async (field) => {
      const f = await setup({
        observe: false,
        modify: (value) => ({
          ...value,
          binding: {
            ...(value as { binding: object }).binding,
            [field]:
              field === 'project_id'
                ? `prj_${'b'.repeat(32)}`
                : field === 'runtime_host_installation_id'
                  ? `wri_${'b'.repeat(32)}`
                  : '2',
          },
        }),
      })
      await expect(
        f.owner.dependencies.observe(a3TestProject, f.readAbort.signal),
      ).rejects.toThrow()
      expect(NativeTestSocket.instances).toHaveLength(0)
    },
  )
  it('rejects API pin injection and oversized bodies', async () => {
    const f = await setup({
      observe: false,
      modify: (value) => ({ ...value, pin32: 'injected' }),
    })
    await expect(
      f.owner.dependencies.observe(a3TestProject, f.readAbort.signal),
    ).rejects.toThrow()
    f.fetch.mockImplementation(async (input) =>
      nativeResponse(
        new URL(String(input)).pathname,
        ' '.repeat(2 * 1024 * 1024 + 1),
        true,
      ),
    )
    await expect(
      f.owner.dependencies.observe(a3TestProject, f.readAbort.signal),
    ).rejects.toThrow('PATCH_TOO_LARGE')
  })
  it('independently fences local session/CSRF scope and cancels the native owner', async () => {
    let current = true
    const f = await setup({ current: () => current })
    const channel = await f.open(),
      closed = vi.fn()
    channel.subscribeClose(closed)
    current = false
    expect(() => f.owner.dependencies.admission!.check(f.data.binding)).toThrow(
      'PATCH_REVOKED',
    )
    expect(closed).toHaveBeenCalledTimes(1)
    expect(f.owner.dependencies.trust.current()).toBeNull()
  })
})

describe('bounded one-slot A3 native channel', () => {
  it('ACKs exact consumed bytes only after final post-digest guard and preserves the record', async () => {
    const { socket, channel } = await opened()
    const raw = new Uint8Array([1, 2, 3]),
      guard = vi.fn()
    socket.message(raw)
    expect(socket.sent.filter((value) => kind(value) === 'A3CA')).toHaveLength(
      0,
    )
    expect(await channel.receive(guard)).toEqual(raw)
    const ack = socket.sent.find((value) => kind(value) === 'A3CA')!
    expect(ack).toHaveLength(41)
    expect(ack[4]).toBe(1)
    expect(new DataView(ack.buffer).getUint32(5)).toBe(0)
    expect(ack.subarray(9)).toEqual(
      new Uint8Array(await crypto.subtle.digest('SHA-256', raw)),
    )
    expect(guard).toHaveBeenCalled()
  })
  it.each([
    'text',
    'blob',
    'oversize',
    'empty',
    'second-record',
    'duplicate-ready',
    'wrong-control',
  ])('closes permanently on %s input', async (mode) => {
    const { socket, channel } = await opened(),
      closed = vi.fn()
    channel.subscribeClose(closed)
    if (mode === 'text') socket.message('plaintext')
    if (mode === 'blob') socket.message(new Blob(['bad']))
    if (mode === 'oversize') socket.message(new Uint8Array(24 * 1024 + 1))
    if (mode === 'empty') socket.message(new Uint8Array())
    if (mode === 'second-record') {
      socket.message(new Uint8Array([1]))
      socket.message(new Uint8Array([2]))
    }
    if (mode === 'duplicate-ready')
      socket.message(new Uint8Array([65, 51, 82, 68, 1]))
    if (mode === 'wrong-control')
      socket.message(new TextEncoder().encode('A3XX\x01'))
    expect(closed).toHaveBeenCalledTimes(1)
    expect(socket.close).toHaveBeenCalledTimes(1)
    await expect(channel.receive()).rejects.toThrow()
  })
  it('rejects concurrent receiver ownership without allocating another pending slot', async () => {
    const { channel } = await opened()
    const first = channel.receive()
    await expect(channel.receive()).rejects.toThrow()
    await expect(first).rejects.toThrow()
  })
  it('rejects concurrent external send ownership and bounds blocked bufferedAmount', async () => {
    const { channel, socket } = await opened()
    socket.bufferedAmount = 1
    const first = channel.send(new Uint8Array([1]), () => undefined)
    await expect(
      channel.send(new Uint8Array([2]), () => undefined),
    ).rejects.toThrow()
    await expect(first).rejects.toThrow()
    expect(socket.sent).toHaveLength(2)
    const second = await opened()
    second.socket.bufferedAmount = 24 * 1024 + 1
    await expect(
      second.channel.send(new Uint8Array([3]), () => undefined),
    ).rejects.toThrow()
  })
  it('rechecks the controller at actual send after backpressure and never publishes cancelled bytes', async () => {
    const { channel, socket } = await opened()
    socket.bufferedAmount = 1
    let valid = true
    const pending = channel.send(new Uint8Array([1]), () => {
      if (!valid) throw new ContentError('PATCH_STALE')
    })
    valid = false
    socket.bufferedAmount = 0
    await expect(pending).rejects.toThrow('PATCH_STALE')
    expect(socket.sent).toHaveLength(2)
  })
  it('does not ACK after cancellation during asynchronous SHA256', async () => {
    const { channel, socket, readAbort } = await opened()
    let release!: () => void
    const digest = crypto.subtle.digest.bind(crypto.subtle)
    vi.spyOn(crypto.subtle, 'digest').mockImplementationOnce(
      async (...args) => {
        const value = await digest(...args)
        await new Promise<void>((resolve) => {
          release = resolve
        })
        return value
      },
    )
    socket.message(new Uint8Array([1, 2]))
    const pending = channel.receive()
    await vi.waitFor(() => expect(release).toBeDefined())
    readAbort.abort()
    release()
    await expect(pending).rejects.toThrow()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(socket.sent.filter((raw) => kind(raw) === 'A3CA')).toHaveLength(0)
  })
  it('rejects wrong subprotocol and does not send an opener', async () => {
    NativeTestSocket.onCreate = (socket) => {
      socket.protocol = 'agentbox-waw'
    }
    const f = await setup()
    await expect(f.open()).rejects.toThrow()
    expect(NativeTestSocket.instances[0].sent).toHaveLength(0)
  })
  it('maps only fixed preflight errors before READY', async () => {
    NativeTestSocket.onCreate = (socket) => {
      socket.autoReady = false
      socket.onData = () =>
        queueMicrotask(() =>
          socket.message(
            new TextEncoder().encode('A3ER\x01PATCH_UNAVAILABLE_BINARY'),
          ),
        )
    }
    const f = await setup()
    await expect(f.open()).rejects.toThrow('PATCH_UNAVAILABLE_BINARY')
    expect(NativeTestSocket.instances[0].sent).toHaveLength(1)
  })
  it.each(['unsolicited', 'wrong-challenge', 'old-reply', 'late-reply'])(
    'fences %s currentness instead of renewing it',
    async (mode) => {
      const { channel, socket } = await opened()
      const oldReply = new Uint8Array(socket.sent[1])
      oldReply.set(new TextEncoder().encode('A3CR'))
      if (mode === 'unsolicited' || mode === 'old-reply')
        socket.message(oldReply)
      else {
        socket.autoCurrent = false
        elapsed = 1250
        await vi.waitFor(() =>
          expect(socket.sent.filter((r) => kind(r) === 'A3CQ')).toHaveLength(2),
        )
        const reply = new Uint8Array(
          socket.sent.filter((r) => kind(r) === 'A3CQ').at(-1)!,
        )
        reply.set(new TextEncoder().encode('A3CR'))
        if (mode === 'wrong-challenge') reply[24] ^= 1
        if (mode === 'late-reply') elapsed = 2250
        socket.message(reply)
      }
      expect(() => channel.check!()).toThrow()
      expect(socket.close).toHaveBeenCalledTimes(1)
    },
  )
  it('cannot renew expired prior freshness before the overdue timer runs', async () => {
    const { channel, socket } = await opened()
    socket.autoCurrent = false
    elapsed = 1250
    await vi.waitFor(() =>
      expect(socket.sent.filter((r) => kind(r) === 'A3CQ')).toHaveLength(2),
    )
    const reply = new Uint8Array(
      socket.sent.filter((r) => kind(r) === 'A3CQ').at(-1)!,
    )
    reply.set(new TextEncoder().encode('A3CR'))
    // Prior freshness expired at 2000; this challenge itself expires at 2250.
    elapsed = 2100
    socket.message(reply)
    expect(socket.close).toHaveBeenCalledTimes(1)
    expect(() => channel.check!()).toThrow()
  })
  it('bounds freshness by issue time, not late receipt, and never revives a closed owner', async () => {
    const { channel, socket } = await opened()
    socket.autoCurrent = false
    elapsed = 1250
    await vi.waitFor(() =>
      expect(socket.sent.filter((r) => kind(r) === 'A3CQ')).toHaveLength(2),
    )
    const reply = new Uint8Array(
      socket.sent.filter((r) => kind(r) === 'A3CQ').at(-1)!,
    )
    reply.set(new TextEncoder().encode('A3CR'))
    elapsed = 1990
    socket.message(reply)
    elapsed = 2249
    expect(() => channel.check!()).not.toThrow()
    elapsed = 2250
    expect(() => channel.check!()).toThrow()
    elapsed = 2000
    socket.message(reply)
    expect(() => channel.check!()).toThrow()
  })
  it('detects progressing-clock regression and rejects pending receive on close', async () => {
    const { channel } = await opened()
    const pending = channel.receive()
    elapsed = 999
    expect(() => channel.check!()).toThrow('PATCH_TIMEOUT')
    await expect(pending).rejects.toThrow()
  })
})

async function controllerFixture(lifetime?: number) {
  const f = await setup({ observe: false, lifetime })
  let runtime: A3ChangesChannel | undefined
  const next = async (socket: NativeTestSocket) => {
    try {
      const raw = await runtime!.receive()
      socket.message(raw)
    } catch {
      /* Synthetic Runtime queue has no unsolicited output. */
    }
  }
  NativeTestSocket.onCreate = (socket) => {
    socket.autoReady = false
    socket.onData = (raw) => {
      if (socket.sent.length === 1) {
        const opening = JSON.parse(new TextDecoder().decode(raw)) as {
          selection_id: string
          request_nonce: string
        }
        void f.fixture.deps
          .open(
            {
              projectId: a3TestProject,
              selectionId: opening.selection_id,
              requestNonce: opening.request_nonce,
            },
            f.readAbort.signal,
          )
          .then((channel) => {
            runtime = channel
            socket.message(new Uint8Array([65, 51, 82, 68, 1]))
          })
      } else if (kind(raw) === 'A3CA') void next(socket)
      else void runtime!.send(raw, () => undefined).then(() => next(socket))
    }
  }
  const controller = new A3ChangesController(
    a3TestProject,
    f.owner.dependencies,
  )
  controller.activate()
  controllers.push(controller)
  return { ...f, controller }
}
describe('native complete-END currentness ownership', () => {
  it('discards a late authenticated decrypt after the page-owned auth/route scope aborts', async () => {
    const f = await controllerFixture()
    const decrypt = crypto.subtle.decrypt.bind(crypto.subtle)
    let release!: () => void
    vi.spyOn(crypto.subtle, 'decrypt').mockImplementationOnce(
      async (...args) => {
        const value = await decrypt(...args)
        await new Promise<void>((resolve) => {
          release = resolve
        })
        return value
      },
    )
    const pending = f.controller.read(a3TestRow)
    await vi.waitFor(() => expect(release).toBeDefined())
    f.abort.abort()
    expect(f.controller.snapshot.text).toBeNull()
    const sent = NativeTestSocket.instances[0].sent.length
    release()
    await pending
    expect(f.controller.snapshot.text).toBeNull()
    expect(NativeTestSocket.instances[0].sent).toHaveLength(sent)
  })

  it('never renews the authenticated shorter selector deadline even with fresh live replies', async () => {
    const { controller } = await controllerFixture(1000)
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('completed')
    const socket = NativeTestSocket.instances[0]
    elapsed = 1500
    await vi.waitFor(() =>
      expect(socket.sent.filter((raw) => kind(raw) === 'A3CQ')).toHaveLength(2),
    )
    elapsed = 2000
    await vi.waitFor(() => expect(controller.snapshot.text).toBeNull())
    expect(socket.close).toHaveBeenCalledTimes(1)
  })

  it('uses actual A3 crypto with independent static pin and retains WS after verified END', async () => {
    const { controller } = await controllerFixture()
    expect(controller.available).toBe(true)
    await controller.read(a3TestRow)
    expect(controller.snapshot).toMatchObject({
      status: 'completed',
      text: a3DangerousPatch,
    })
    const socket = NativeTestSocket.instances[0]
    expect(socket.close).not.toHaveBeenCalled()
    controller.clear()
    expect(controller.snapshot.text).toBeNull()
    expect(socket.close).toHaveBeenCalledTimes(1)
  })
  it('clears retained complete text on API pause/currentness expiry without resetting the selector lifetime', async () => {
    const { controller } = await controllerFixture()
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('completed')
    NativeTestSocket.instances[0].autoCurrent = false
    elapsed = 2000
    await vi.waitFor(() => expect(controller.snapshot.text).toBeNull())
    expect(controller.snapshot.status).toBe('stale')
  })
})
