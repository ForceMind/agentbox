import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  A3HTTPSTrustConsumer,
  a3HTTPSTrustSelected,
  A3_BOOTSTRAP_PATH,
} from './a3TrustHTTPS'
import {
  nativeBootstrap,
  nativeOrigin,
  nativeBuild,
  staticResponse,
  canonicalBootstrap,
  selectNativeBootstrap,
} from './a3Native.testSupport'
const consumers: A3HTTPSTrustConsumer[] = []
const consumer = () => {
  const value = new A3HTTPSTrustConsumer()
  consumers.push(value)
  return value
}
beforeEach(() => {
  vi.useFakeTimers()
  selectNativeBootstrap()
})
afterEach(() => {
  consumers.splice(0).forEach((value) => value.close())
  document.head.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
describe('A3 independent HTTPS host trust', () => {
  it.each(['timeout', 'close'])(
    'aborts a pending bounded bootstrap body on %s',
    async (mode) => {
      let signal: AbortSignal | undefined
      vi.stubGlobal(
        'fetch',
        vi.fn<typeof globalThis.fetch>(async (_url, init) => {
          signal = init!.signal!
          const body = new ReadableStream<Uint8Array>({
            start(controller) {
              signal!.addEventListener(
                'abort',
                () =>
                  controller.error(new DOMException('Aborted', 'AbortError')),
                { once: true },
              )
            },
          })
          const response = new Response(body, {
            headers: { 'content-type': 'application/json' },
          })
          Object.defineProperty(response, 'url', {
            value: nativeOrigin + A3_BOOTSTRAP_PATH,
          })
          return response
        }),
      )
      const owner = consumer(),
        pending = owner.authorize()
      void pending.catch(() => undefined)
      await Promise.resolve()
      if (mode === 'timeout') await vi.advanceTimersByTimeAsync(5000)
      else owner.close()
      await expect(pending).rejects.toThrow()
      expect(signal!.aborted).toBe(true)
    },
  )

  it('requires two fresh bounded matching reads and establishes only purpose/host/pin', async () => {
    const fetch = vi.fn(() => Promise.resolve(staticResponse()))
    vi.stubGlobal('fetch', fetch)
    const lease = await consumer().authorize()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[0]).toEqual([
      nativeOrigin + A3_BOOTSTRAP_PATH,
      expect.objectContaining({
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        mode: 'same-origin',
        referrerPolicy: 'no-referrer',
      }),
    ])
    expect(lease.current()).toEqual({
      purpose: nativeBootstrap.purpose,
      host: {
        runtime_host_installation_id:
          nativeBootstrap.runtime_host_installation_id,
        runtime_host_installation_revision: '1',
      },
      pin32: new Uint8Array(32).fill(0xaa),
    })
    expect(Object.keys(lease.current()!).sort()).toEqual([
      'host',
      'pin32',
      'purpose',
    ])
    lease.current()!.pin32.fill(0)
    expect(lease.current()!.pin32[0]).toBe(0xaa)
  })
  it.each([
    'missing',
    'waw-only',
    'duplicate',
    'insecure',
    'http',
    'bad-build',
  ])('does no network for unconfigured %s selection', async (kind) => {
    if (kind === 'missing') document.head.innerHTML = ''
    if (kind === 'waw-only')
      document.head.innerHTML = `<meta name="agentbox-waw-trust-profile" content="https-web-v1"><meta name="agentbox-waw-build-identity" content="${nativeBuild}">`
    if (kind === 'duplicate')
      document.head.innerHTML +=
        '<meta name="agentbox-a3-trust-profile" content="a3-https-web-v1">'
    if (kind === 'insecure') vi.stubGlobal('isSecureContext', false)
    if (kind === 'http')
      vi.stubGlobal('location', new URL('http://a3.agentbox.test'))
    if (kind === 'bad-build')
      document.querySelector<HTMLMetaElement>(
        'meta[name="agentbox-a3-build-identity"]',
      )!.content = 'not-a-build'
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect(a3HTTPSTrustSelected()).toBe(false)
    await expect(consumer().authorize()).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each([
    ['schema_version', 'agentbox-waw-https-bootstrap.v1'],
    ['trust_profile', 'https-web-v1'],
    ['purpose', 'agentbox-a3-content/crypto/v1'],
    ['repository', 'someone/else'],
    ['origin', 'https://other.example'],
    ['runtime_host_installation_id', 'bad'],
    ['runtime_host_installation_revision', '0'],
    ['runtime_host_installation_revision', '18446744073709551616'],
    ['runtime_attestation_x25519_public_key', 'a'.repeat(63)],
    ['host_manifest_digest', 'A'.repeat(64)],
    ['build_identity', 'e'.repeat(64)],
    ['valid_until', '2026-10-05T01:00:00Z'],
    ['valid_until', '2026-11-06T00:00:00Z'],
    ['valid_from', '2026-10-05T00:00:00.000Z'],
    ['version', 'unknown'],
    ['unexpected', 'credential'],
  ])('rejects invalid %s=%s', async (field, value) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(staticResponse({ ...nativeBootstrap, [field]: value })),
      ),
    )
    await expect(consumer().authorize()).rejects.toThrow()
  })
  it.each([
    'noncanonical',
    'duplicate',
    'missing',
    'oversize',
    'redirect',
    'wrong-url',
    'mime',
  ])('rejects %s wire without issuing a lease', async (kind) => {
    let raw = canonicalBootstrap(nativeBootstrap)
    if (kind === 'noncanonical') raw = JSON.stringify(nativeBootstrap)
    if (kind === 'duplicate') raw = raw.replace('{', '{"origin":"ignored",')
    if (kind === 'missing')
      raw = canonicalBootstrap({ ...nativeBootstrap, purpose: undefined })
    if (kind === 'oversize') raw = ' '.repeat(8193)
    vi.stubGlobal(
      'fetch',
      vi.fn(() => {
        const response = staticResponse(nativeBootstrap, raw)
        if (kind === 'redirect')
          Object.defineProperty(response, 'redirected', { value: true })
        if (kind === 'wrong-url')
          return Promise.resolve(
            new Response(raw, {
              headers: { 'content-type': 'application/json' },
            }),
          )
        if (kind === 'mime') response.headers.set('content-type', 'text/plain')
        return Promise.resolve(response)
      }),
    )
    await expect(consumer().authorize()).rejects.toThrow()
  })
  it('rejects mismatched initial reads and never adopts observation-supplied trust', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(staticResponse())
        .mockResolvedValueOnce(
          staticResponse({
            ...nativeBootstrap,
            runtime_attestation_x25519_public_key: 'e'.repeat(64),
          }),
        ),
    )
    await expect(consumer().authorize()).rejects.toThrow()
  })
  it.each([
    'build',
    'origin',
    'rollback',
    'expiry',
    'hide',
    'freeze',
    'pagehide',
    'offline',
    'close',
  ])('irreversibly invalidates on %s', async (kind) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(staticResponse())),
    )
    const owner = consumer(),
      lease = await owner.authorize()
    if (kind === 'build')
      document.querySelector<HTMLMetaElement>(
        'meta[name="agentbox-a3-build-identity"]',
      )!.content = 'e'.repeat(64)
    if (kind === 'origin')
      vi.stubGlobal('location', new URL('https://other.example'))
    if (kind === 'rollback')
      vi.mocked(Date.now).mockReturnValue(Date.parse('2026-10-05T11:59:59Z'))
    if (kind === 'expiry')
      vi.mocked(Date.now).mockReturnValue(Date.parse('2026-10-06T00:00:00Z'))
    if (kind === 'hide') {
      vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
      document.dispatchEvent(new Event('visibilitychange'))
    }
    if (kind === 'freeze') document.dispatchEvent(new Event('freeze'))
    if (kind === 'pagehide' || kind === 'offline')
      window.dispatchEvent(new Event(kind))
    if (kind === 'close') owner.close()
    expect(lease.current()).toBeNull()
    expect(lease.signal.aborted).toBe(true)
    selectNativeBootstrap()
    expect(lease.current()).toBeNull()
  })
  it('closes on poll rotation and on failed fresh reads', async () => {
    const fetch = vi.fn(() => Promise.resolve(staticResponse()))
    vi.stubGlobal('fetch', fetch)
    const first = await consumer().authorize()
    fetch.mockImplementation(() =>
      Promise.resolve(
        staticResponse({
          ...nativeBootstrap,
          host_manifest_digest: 'e'.repeat(64),
        }),
      ),
    )
    await vi.advanceTimersByTimeAsync(5000)
    expect(first.signal.aborted).toBe(true)
    fetch.mockImplementation(() => Promise.resolve(staticResponse()))
    const second = await consumer().authorize()
    fetch.mockRejectedValue(new Error('lost'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(second.signal.aborted).toBe(true)
  })
  it('fences lost freshness synchronously without relying on scheduled polling', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(staticResponse())),
    )
    const lease = await consumer().authorize()
    vi.mocked(Date.now).mockReturnValue(Date.parse('2026-10-05T12:00:10Z'))
    expect(lease.current()).toBeNull()
    expect(lease.signal.aborted).toBe(true)
  })
})
