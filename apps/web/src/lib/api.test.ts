import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient } from './api'
import { parseAuthEnvelope, parseReadinessResponse } from './contracts'

describe('ApiClient', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('always includes cookie credentials and JSON headers', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ value: 'ok' }), { status: 200 }),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await new ApiClient().post('/api/v1/example', {
      body: { safe: true },
      csrfToken: 'csrf-memory-only',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/example',
      expect.objectContaining({
        credentials: 'include',
        method: 'POST',
        headers: expect.objectContaining({
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRF-Token': 'csrf-memory-only',
        }),
      }),
    )
  })

  it('maps the API error envelope without accepting hostile request ids', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              request_id: '<script>alert(1)</script>',
              error: { code: 'SAFE_ERROR', message: 'Safe message' },
            }),
            { status: 403, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
      ),
    )

    await expect(new ApiClient().get('/api/v1/example')).rejects.toEqual(
      expect.objectContaining({
        code: 'SAFE_ERROR',
        message: 'Safe message',
        requestId: undefined,
        status: 403,
      }),
    )
  })

  it('invokes centralized unauthorized recovery once', async () => {
    const onUnauthorized = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('{}', { status: 401 }))),
    )

    await expect(
      new ApiClient(onUnauthorized).get('/api/v1/example'),
    ).rejects.toThrow()
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('rejects malformed successful responses through a contract validator', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ api_version: 'v1', data: {} }), {
            status: 200,
          }),
        ),
      ),
    )

    await expect(
      new ApiClient().get('/api/v1/auth/me', { validate: parseAuthEnvelope }),
    ).rejects.toEqual(
      expect.objectContaining({ code: 'CONTROL_PLANE_UNAVAILABLE', status: 0 }),
    )
  })

  it('validates an explicitly accepted non-success response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              status: 'not_ready',
              checks: { database: true, migrations: false },
            }),
            { status: 503, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
      ),
    )

    await expect(
      new ApiClient().get('/readyz', {
        acceptStatuses: [503],
        validate: parseReadinessResponse,
      }),
    ).resolves.toEqual({
      status: 'not_ready',
      checks: { database: true, migrations: false },
    })
  })
})
