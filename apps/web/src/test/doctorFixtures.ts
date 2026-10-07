import { vi } from 'vitest'

import type { AuthContextValue } from '../features/auth/AuthContext'
import { ApiClient } from '../lib/api'
export { doctorResponse } from './doctorResponseFixture'

export function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function heldResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

// Only HTTP is synthetic: ApiClient, DTO validation, useDoctor and page
// rendering remain real. A rejected path or method cannot silently pass.
export function doctorHttp(response: Response | Promise<Response>) {
  const requests: Array<{
    path: string
    method: string
    signal: AbortSignal | undefined
  }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = input.toString()
      const method = init?.method ?? 'GET'
      requests.push({ path, method, signal: init?.signal ?? undefined })
      if (path !== '/api/v1/doctor' || method !== 'GET' || !init?.signal) {
        throw new Error(`Unexpected Doctor fixture request: ${method} ${path}`)
      }
      return Promise.resolve(response)
    }),
  )
  const value: AuthContextValue = {
    api: new ApiClient(),
    auth: null,
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
  return { requests, value }
}
