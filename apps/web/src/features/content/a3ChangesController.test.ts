import { webcrypto } from 'node:crypto'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { A3ChangesController } from './a3ChangesController'
import {
  a3DangerousPatch,
  a3TestProject,
  a3TestRow,
  createA3TestFixture,
} from './a3Changes.testSupport'
import { parseA3Binding, parseA3Observation } from './a3ChangesDto'
import { readA3Trust } from './a3ChangesTrust'

beforeAll(() => vi.stubGlobal('crypto', webcrypto))
const controllers: A3ChangesController[] = []
afterEach(() => {
  for (const controller of controllers.splice(0)) controller.dispose()
  vi.useRealTimers()
  vi.restoreAllMocks()
})
async function setup(options: Parameters<typeof createA3TestFixture>[0] = {}) {
  const f = await createA3TestFixture(options)
  const controller = new A3ChangesController(a3TestProject, f.deps)
  controller.activate()
  controllers.push(controller)
  return { ...f, fixture: f, controller }
}

describe('page-owned A3 full read controller', () => {
  it('is unavailable without an adapter and makes no automatic observation/read', async () => {
    const unavailable = new A3ChangesController(a3TestProject)
    expect(unavailable.snapshot.status).toBe('unavailable')
    await unavailable.read(a3TestRow)
    expect(unavailable.snapshot.text).toBeNull()
    const { deps, controller } = await setup()
    expect(controller.snapshot.status).toBe('empty')
    expect(deps.observe).not.toHaveBeenCalled()
    expect(deps.open).not.toHaveBeenCalled()
  })
  it('uses fresh observation, nonce and full actual crypto for every deliberate read', async () => {
    const { controller, deps, requests } = await setup()
    await controller.read(a3TestRow)
    expect(controller.snapshot).toMatchObject({
      status: 'completed',
      text: a3DangerousPatch,
    })
    await controller.read(a3TestRow)
    expect(deps.observe).toHaveBeenCalledTimes(2)
    expect(requests).toHaveLength(2)
    expect(requests[1].requestNonce).toMatch(/^[a-f0-9]{64}$/)
    expect(requests[1].requestNonce).not.toBe(requests[0].requestNonce)
    expect(requests[1].selectionId).not.toBe(requests[0].selectionId)
    expect(Object.keys(requests[0]).sort()).toEqual([
      'projectId',
      'requestNonce',
      'selectionId',
    ])
  })
  it('never shows PAGEs, clears immediately on cancel and ignores a late END', async () => {
    const { controller, fixture } = await setup({ holdEnd: true })
    const pending = controller.read(a3TestRow)
    await vi.waitFor(() => expect(fixture.held).toBe(true))
    expect(controller.snapshot).toMatchObject({ status: 'loading', text: null })
    controller.clear()
    expect(controller.snapshot.text).toBeNull()
    expect(fixture.closed).toBe(1)
    fixture.release()
    await pending
    expect(controller.snapshot.status).toBe('empty')
    expect(controller.snapshot.text).toBeNull()
  })
  it.each(['malformed', 'dropPage'] as const)(
    'discards %s frames without partial success',
    async (mode) => {
      const { controller, fixture } = await setup({ [mode]: true })
      await controller.read(a3TestRow)
      expect(controller.snapshot).toMatchObject({
        status: 'failed',
        text: null,
      })
      expect(fixture.closed).toBe(1)
    },
  )
  it.each([
    ['PATCH_TOO_LARGE', 'too-large'],
    ['PATCH_UNAVAILABLE_BINARY', 'binary'],
    ['PATCH_STALE', 'stale'],
    ['PATCH_REVOKED', 'permission'],
    ['PATCH_UNAVAILABLE_ENCODING', 'unavailable'],
  ])('maps bounded encrypted %s to %s', async (errorCode, status) => {
    const { controller } = await setup({ errorCode })
    await controller.read(a3TestRow)
    expect(controller.snapshot).toMatchObject({ status, text: null })
  })
  it('expires the completed result at the authenticated tightened deadline without renewing it', async () => {
    const { controller, fixture } = await setup({ lifetime: 1000 })
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('completed')
    fixture.now(1999)
    await new Promise((resolve) => setTimeout(resolve, 55))
    expect(controller.snapshot.status).toBe('completed')
    fixture.now(2000)
    await vi.waitFor(() => expect(controller.snapshot.status).toBe('stale'))
    expect(controller.snapshot.text).toBeNull()
  })
  it('fences expiry during a pending END and does not republish after release', async () => {
    const { controller, fixture } = await setup({
      holdEnd: true,
      lifetime: 1000,
    })
    const pending = controller.read(a3TestRow)
    await vi.waitFor(() => expect(fixture.held).toBe(true))
    fixture.now(2000)
    await vi.waitFor(() => expect(controller.snapshot.status).toBe('stale'))
    fixture.release()
    await pending
    expect(controller.snapshot.text).toBeNull()
  })
  it('clears completed text synchronously on trust/auth epoch loss', async () => {
    const { controller, fixture } = await setup()
    await controller.read(a3TestRow)
    fixture.invalidate({ binding: { ...fixture.binding, auth_epoch: '2' } })
    expect(controller.snapshot).toMatchObject({
      status: 'permission',
      text: null,
    })
  })
  it('detects changed pins even if a defective provider omits its notification', async () => {
    const { controller, fixture } = await setup()
    await controller.read(a3TestRow)
    fixture.silentlyChange({ pin32: new Uint8Array(32) })
    await vi.waitFor(() =>
      expect(controller.snapshot.status).toBe('permission'),
    )
    expect(controller.snapshot.text).toBeNull()
  })
  it('closes pending I/O on disconnect', async () => {
    const { controller, fixture } = await setup({ holdEnd: true })
    const pending = controller.read(a3TestRow)
    await vi.waitFor(() => expect(fixture.held).toBe(true))
    fixture.disconnect()
    expect(controller.snapshot.status).toBe('stale')
    fixture.release()
    await pending
    expect(controller.snapshot.text).toBeNull()
  })
  it('checks the generation again at actual publication after queued send backpressure', async () => {
    const { controller, deps, fixture } = await setup()
    let release!: () => void
    let queued = false
    vi.mocked(deps.open).mockImplementationOnce(async () => {
      return {
        send: async (_raw, checkCurrent) => {
          queued = true
          await new Promise<void>((resolve) => {
            release = resolve
          })
          checkCurrent()
          throw new Error('must not publish')
        },
        receive: async () => {
          throw new Error('must not receive')
        },
        close: vi.fn(),
        subscribeClose: () => () => undefined,
      }
    })
    const pending = controller.read(a3TestRow)
    await vi.waitFor(() => expect(queued).toBe(true))
    fixture.invalidate()
    release()
    await pending
    expect(controller.snapshot).toMatchObject({
      status: 'permission',
      text: null,
    })
    expect(fixture.sent).toBe(0)
  })
  it('rejects untrusted purpose, missing pin, and observation-supplied pin', async () => {
    const { deps, fixture, controller } = await setup()
    fixture.silentlyChange({ purpose: 'agentbox-waw/v1' as never })
    expect(() => readA3Trust(deps.trust)).toThrow()
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('unavailable')
    expect(deps.observe).not.toHaveBeenCalled()
    expect(() =>
      parseA3Observation({ ...fixture.observation(), pin: 'a'.repeat(64) }),
    ).toThrow()
  })
  it('rejects stale row replacement without opening a content channel', async () => {
    const { controller, deps } = await setup()
    await controller.read({ ...a3TestRow, path: 'other.txt' })
    expect(controller.snapshot.status).toBe('stale')
    expect(deps.open).not.toHaveBeenCalled()
  })
  it('closes an adapter that resolves only after cancellation, without subscribing or sending', async () => {
    const { controller, deps } = await setup()
    const channel = {
      send: vi.fn(),
      receive: vi.fn(),
      close: vi.fn(),
      subscribeClose: vi.fn(),
    }
    let release!: () => void
    vi.mocked(deps.open).mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => {
        release = resolve
      })
      return channel
    })
    const pending = controller.read(a3TestRow)
    await vi.waitFor(() => expect(release).toBeDefined())
    controller.clear()
    release()
    await pending
    expect(channel.close).toHaveBeenCalledTimes(1)
    expect(channel.subscribeClose).not.toHaveBeenCalled()
    expect(channel.send).not.toHaveBeenCalled()
    expect(controller.snapshot.text).toBeNull()
  })
  it('late old open closes only its handle after a new generation completes', async () => {
    const { controller, deps, fixture } = await setup()
    const old = {
      send: vi.fn(),
      receive: vi.fn(),
      close: vi.fn(),
      subscribeClose: vi.fn(),
    }
    let release!: () => void
    vi.mocked(deps.open).mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => {
        release = resolve
      })
      return old
    })
    const first = controller.read(a3TestRow)
    await vi.waitFor(() => expect(release).toBeDefined())
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('completed')
    const newest = controller.snapshot
    const closes = fixture.closed
    release()
    await first
    expect(old.close).toHaveBeenCalledTimes(1)
    expect(old.send).not.toHaveBeenCalled()
    expect(old.subscribeClose).not.toHaveBeenCalled()
    expect(fixture.closed).toBe(closes)
    expect(controller.snapshot).toBe(newest)
  })
  it('a deferred old crypto digest cannot send or publish into a newer completed generation', async () => {
    const { controller, deps, fixture } = await setup()
    const digest = crypto.subtle.digest.bind(crypto.subtle)
    let release!: () => void
    vi.spyOn(crypto.subtle, 'digest').mockImplementationOnce(
      async (...args) => {
        const result = await digest(...args)
        await new Promise<void>((resolve) => {
          release = resolve
        })
        return result
      },
    )
    const first = controller.read(a3TestRow)
    await vi.waitFor(() => expect(release).toBeDefined())
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('completed')
    const newest = controller.snapshot
    release()
    await first
    expect(controller.snapshot).toBe(newest)
    expect(deps.open).toHaveBeenCalledTimes(1)
    expect(fixture.requests).toHaveLength(1)
  })
  it('does not observe unsupported or unstaged rows', async () => {
    const { controller, deps } = await setup()
    await controller.read({ ...a3TestRow, staged: false })
    await controller.read({ ...a3TestRow, kind: 'renamed' })
    expect(deps.observe).not.toHaveBeenCalled()
    expect(controller.snapshot.status).toBe('unavailable')
  })
  it('returns empty only for an actual empty fresh observation', async () => {
    const { controller, deps, fixture } = await setup()
    vi.mocked(deps.observe).mockResolvedValue({
      ...fixture.observation(),
      entries: [],
    })
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('empty')
    expect(deps.open).not.toHaveBeenCalled()
  })
  it('fences a superseded delayed observation and never opens its channel', async () => {
    const { controller, deps, fixture } = await setup()
    let release!: (value: unknown) => void
    vi.mocked(deps.observe).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve
        }),
    )
    const first = controller.read(a3TestRow)
    await controller.read(a3TestRow)
    expect(controller.snapshot.status).toBe('completed')
    release(fixture.observation())
    await first
    expect(controller.snapshot.status).toBe('completed')
    expect(deps.open).toHaveBeenCalledTimes(1)
  })
})

describe('closed A3 observation data', () => {
  it('rejects getters, extra credential fields, duplicate rows, unsupported selectors and unknown errors', async () => {
    const f = await createA3TestFixture()
    const o = f.observation()
    expect(parseA3Observation(o).binding).toEqual(f.binding)
    for (const bad of [
      { ...o, csrf_token: 'never' },
      { ...o, binding: { ...f.binding, relative_key: 'private' } },
      { ...o, entries: [o.entries[0], o.entries[0]] },
      { ...o, entries: [{ ...o.entries[0], kind: 'renamed' }] },
      {
        ...o,
        entries: [
          {
            ...o.entries[0],
            selection_id: null,
            unavailable_code: 'UNBOUNDED_DETAIL',
          },
        ],
      },
      { ...o, entries: [{ ...o.entries[0], side: 'unstaged' }] },
      { ...o, entries: [{ ...o.entries[0], selection_id: 'a'.repeat(155) }] },
    ])
      expect(() => parseA3Observation(bad)).toThrow()
    const getter = vi.fn(() => '1')
    const badBinding = { ...f.binding }
    Object.defineProperty(badBinding, 'auth_epoch', {
      enumerable: true,
      get: getter,
    })
    expect(() => parseA3Binding(badBinding)).toThrow()
    expect(getter).not.toHaveBeenCalled()
  })
})
