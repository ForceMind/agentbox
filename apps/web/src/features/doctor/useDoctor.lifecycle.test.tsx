import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClient } from '../../lib/api'
import {
  doctorHttp,
  doctorResponse,
  heldResponse,
  jsonResponse,
} from '../../test/doctorFixtures'
import { AuthContext } from '../auth/AuthContext'
import { useDoctor } from './useDoctor'

describe('useDoctor existing HTTP lifecycle', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('retains the 90-second timeout and emits only the projected timeout code', async () => {
    vi.useFakeTimers()
    const { value } = doctorHttp(heldResponse().promise)
    let signal: AbortSignal | undefined
    const requests: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        requests.push(input.toString())
        signal = init?.signal ?? undefined
        return new Promise<Response>((_resolve, reject) => {
          signal?.addEventListener(
            'abort',
            () =>
              reject(new DOMException('synthetic timeout prose', 'AbortError')),
            { once: true },
          )
        })
      }),
    )
    const wrapper = ({ children }: { children: ReactNode }) => (
      <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    )
    const { result } = renderHook(() => useDoctor(), { wrapper })

    expect(requests).toEqual(['/api/v1/doctor'])
    await act(async () => vi.advanceTimersByTimeAsync(89_999))
    expect(signal?.aborted).toBe(false)
    expect(result.current).toEqual({ status: 'loading' })
    await act(async () => vi.advanceTimersByTimeAsync(1))
    expect(signal?.aborted).toBe(true)
    expect(result.current).toEqual({
      status: 'error',
      error: { code: 'REQUEST_TIMEOUT' },
    })
    expect(requests).toHaveLength(1)
  })

  it('aborts a replaced API request and cannot overwrite its successor with a late failure', async () => {
    const first = heldResponse()
    const second = heldResponse()
    const { value } = doctorHttp(first.promise)
    const signals: AbortSignal[] = []
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      expect(input.toString()).toBe('/api/v1/doctor')
      expect(init?.method).toBe('GET')
      if (!init?.signal) throw new Error('Doctor must supply an abort signal')
      signals.push(init.signal)
      return signals.length === 1 ? first.promise : second.promise
    })
    vi.stubGlobal('fetch', fetchMock)
    let currentValue = value
    const wrapper = ({ children }: { children: ReactNode }) => (
      <AuthContext.Provider value={currentValue}>
        {children}
      </AuthContext.Provider>
    )
    const { result, rerender } = renderHook(() => useDoctor(), { wrapper })
    expect(signals).toHaveLength(1)

    currentValue = { ...value, api: new ApiClient() }
    rerender()
    expect(signals).toHaveLength(2)
    expect(signals[0].aborted).toBe(true)
    expect(signals[1].aborted).toBe(false)
    const current = doctorResponse()
    current.data.codex.version = 'CURRENT-API-VERSION'
    await act(async () => second.resolve(jsonResponse(current)))
    expect(result.current).toMatchObject({
      status: 'loaded',
      response: { data: { codex: { version: 'CURRENT-API-VERSION' } } },
    })

    const late = jsonResponse(
      {
        request_id: 'req_old_api',
        error: {
          code: 'OLD_API_FAILURE',
          message: 'OLD API PRIVATE PROSE CANARY',
        },
      },
      503,
    )
    const parsed = vi.spyOn(late, 'json')
    await act(async () => first.resolve(late))
    expect(parsed).toHaveBeenCalledOnce()
    expect(result.current).toMatchObject({
      status: 'loaded',
      response: { data: { codex: { version: 'CURRENT-API-VERSION' } } },
    })
    expect(JSON.stringify(result.current)).not.toContain('OLD_API_FAILURE')
    expect(JSON.stringify(result.current)).not.toContain(
      'OLD API PRIVATE PROSE CANARY',
    )
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
