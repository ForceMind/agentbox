import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { httpsWebTrustSelected, WAWHTTPSTrustConsumer } from './wawTrustHTTPS'

const ORIGIN = 'https://example.agentbox.test'
const BUILD = 'b'.repeat(64)
const request = {
  effective_origin: ORIGIN,
  admitted_api_origin: ORIGIN,
  runtime_host_installation_id: 'wri_' + '1'.repeat(32),
  runtime_host_installation_revision: '1',
}
const bootstrap = {
  schema_version: 'agentbox-waw-https-bootstrap.v1',
  trust_profile: 'https-web-v1',
  repository: 'ForceMind/agentbox',
  origin: ORIGIN,
  runtime_host_installation_id: request.runtime_host_installation_id,
  runtime_host_installation_revision: '1',
  runtime_attestation_x25519_fingerprint: 'a'.repeat(64),
  host_manifest_digest: 'c'.repeat(64),
  build_identity: BUILD,
  version: '0.3.0rc30',
  valid_from: '2026-10-01T00:00:00Z',
  valid_until: '2026-10-02T00:00:00Z',
}
const canonical = (value: object) =>
  JSON.stringify(
    Object.fromEntries(
      Object.entries(value).sort(([a], [b]) => a.localeCompare(b)),
    ),
  ) + '\n'
const consumers: WAWHTTPSTrustConsumer[] = []

function response(value: object = bootstrap, raw?: string) {
  const result = new Response(raw ?? canonical(value), {
    headers: { 'content-type': 'application/json' },
  })
  Object.defineProperty(result, 'url', {
    value: ORIGIN + '/.well-known/agentbox/waw-bootstrap.v1.json',
  })
  return result
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-01T12:00:00Z'))
  vi.stubGlobal('location', new URL(ORIGIN))
  vi.stubGlobal('isSecureContext', true)
  document.head.innerHTML = `<meta name="agentbox-waw-trust-profile" content="https-web-v1"><meta name="agentbox-waw-build-identity" content="${BUILD}">`
})
afterEach(() => {
  consumers.splice(0).forEach((consumer) => consumer.close())
  document.head.innerHTML = ''
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
function consumer() {
  const result = new WAWHTTPSTrustConsumer()
  consumers.push(result)
  return result
}

describe('explicit weaker HTTPS trust', () => {
  it('authorizes only fresh exact public identity without native records', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(() =>
      Promise.resolve(response()),
    )
    vi.stubGlobal('fetch', fetch)
    expect(httpsWebTrustSelected()).toBe(true)
    const lease = await consumer().authorize(request)
    expect(lease.schema_version).toBe('agentbox-waw-https-bootstrap.v1')
    expect(lease.isCurrent()).toBe(true)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[0]?.[1]).toMatchObject({
      credentials: 'omit',
      redirect: 'error',
      cache: 'no-store',
    })
  })

  it.each([
    'origin',
    'host',
    'revision',
    'build',
    'expired',
    'unknown',
    'duplicate',
    'noncanonical',
  ])('rejects %s bootstrap', async (kind) => {
    const value: Record<string, unknown> = { ...bootstrap }
    if (kind === 'origin') value.origin = 'https://other.agentbox.test'
    if (kind === 'host')
      value.runtime_host_installation_id = 'wri_' + '2'.repeat(32)
    if (kind === 'revision') value.runtime_host_installation_revision = '2'
    if (kind === 'build') value.build_identity = 'd'.repeat(64)
    if (kind === 'expired') value.valid_until = '2026-10-01T01:00:00Z'
    if (kind === 'unknown') value.extra = 'unrecognized'
    const raw =
      kind === 'duplicate'
        ? canonical(value).replace('{', '{"origin":"ignored",')
        : kind === 'noncanonical'
          ? JSON.stringify(value)
          : undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(response(value, raw))),
    )
    await expect(consumer().authorize(request)).rejects.toThrow()
  })

  it('rejects changed bootstrap between initial reads', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response())
        .mockResolvedValueOnce(
          response({ ...bootstrap, host_manifest_digest: 'd'.repeat(64) }),
        ),
    )
    await expect(consumer().authorize(request)).rejects.toThrow()
  })

  it('fences build changes, lost freshness and close', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(response())),
    )
    const trust = consumer(),
      lease = await trust.authorize(request)
    document.querySelector<HTMLMetaElement>(
      'meta[name="agentbox-waw-build-identity"]',
    )!.content = 'd'.repeat(64)
    expect(lease.isCurrent()).toBe(false)
    trust.close()
    expect(lease.signal.aborted).toBe(true)
  })

  it('requires explicit secure document metadata', () => {
    document.head.innerHTML = ''
    expect(httpsWebTrustSelected()).toBe(false)
    vi.stubGlobal('isSecureContext', false)
    expect(httpsWebTrustSelected()).toBe(false)
  })

  it('aborts the live lease on bootstrap rotation during polling', async () => {
    let rotated = false
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          response(
            rotated
              ? {
                  ...bootstrap,
                  runtime_attestation_x25519_fingerprint: 'd'.repeat(64),
                }
              : bootstrap,
          ),
        ),
      ),
    )
    const lease = await consumer().authorize(request)
    rotated = true
    await vi.advanceTimersByTimeAsync(5000)
    expect(lease.signal.aborted).toBe(true)
    expect(lease.isCurrent()).toBe(false)
  })

  it('fences backward browser time without claiming native clock authority', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(response())),
    )
    const lease = await consumer().authorize(request)
    vi.setSystemTime(new Date('2026-10-01T11:59:59Z'))
    expect(lease.isCurrent()).toBe(false)
  })
})
