import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import { ApiClient, ApiError } from '../lib/api'
import { LoginPage } from './LoginPage'

type FailureOptions = Readonly<{
  code: string
  requestId?: string
  retryAfter?: number
  status: number
}>

function unreadableServerProse(options: FailureOptions) {
  const canary = 'RC9-LOGIN-SERVER-PROSE-CANARY'
  let messageReads = 0
  const error = new ApiError({ ...options, message: canary })
  Object.defineProperty(error, 'message', {
    configurable: true,
    get: () => {
      messageReads += 1
      return canary
    },
  })
  return { error, canary, messageReads: () => messageReads }
}

function authContext(login: () => Promise<void>): AuthContextValue {
  return {
    api: {
      get: vi.fn(async () => ({ status: 'ok' })),
    } as unknown as ApiClient,
    auth: null,
    status: 'unauthenticated',
    login,
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

async function submitLogin(locale: Locale, failure: FailureOptions) {
  const observed = unreadableServerProse(failure)
  const login = vi.fn(async () => {
    throw observed.error
  })
  render(
    <AuthContext.Provider value={authContext(login)}>
      <LoginPage locale={locale} />
    </AuthContext.Provider>,
  )

  const labels =
    locale === 'zh-CN'
      ? { username: '用户名', password: '密码', submit: '登录' }
      : { username: 'Username', password: 'Password', submit: 'Sign in' }
  fireEvent.change(screen.getByLabelText(labels.username), {
    target: { value: 'maintainer' },
  })
  fireEvent.change(screen.getByLabelText(labels.password), {
    target: { value: 'test password' },
  })
  fireEvent.click(screen.getByRole('button', { name: labels.submit }))

  await waitFor(() => expect(login).toHaveBeenCalledTimes(1))
  const alert = await screen.findByRole('alert')
  expect(observed.messageReads()).toBe(0)
  expect(alert).not.toHaveTextContent(observed.canary)
  return { alert, observed }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('LoginPage localized error boundary', () => {
  it.each([
    ['en', 'The control plane is unavailable.'],
    ['zh-CN', '控制平面暂不可用。'],
  ] as const)(
    'localizes a known API code in %s without reading server prose',
    async (locale, expected) => {
      const { alert, observed } = await submitLogin(locale, {
        code: 'CONTROL_PLANE_UNAVAILABLE',
        requestId: 'req_rc9_known',
        status: 503,
      })

      expect(alert).toHaveTextContent(expected)
      const requestId = screen.getByText('req_rc9_known')
      expect(requestId).toHaveAttribute('lang', 'en')
      expect(requestId).toHaveAttribute('dir', 'ltr')
      expect(requestId).toHaveAttribute('translate', 'no')
      expect(observed.messageReads()).toBe(0)
    },
  )

  it.each([
    ['en', 'The operation could not be completed. Try again.'],
    ['zh-CN', '操作未完成，请重试。'],
  ] as const)(
    'uses the local generic message for an unknown API code in %s',
    async (locale, expected) => {
      const { alert, observed } = await submitLogin(locale, {
        code: 'RC9_UNKNOWN_SERVER_FAILURE',
        status: 500,
      })

      expect(alert).toHaveTextContent(expected)
      expect(observed.messageReads()).toBe(0)
    },
  )

  it.each([
    ['en', 'The username or password is incorrect.'],
    ['zh-CN', '用户名或密码错误。'],
  ] as const)(
    'normalizes every 401 response to the public credential error in %s',
    async (locale, expected) => {
      const { alert } = await submitLogin(locale, {
        code: 'RC9_UNKNOWN_AUTH_FAILURE',
        status: 401,
      })
      expect(alert).toHaveTextContent(expected)
    },
  )

  it.each([
    [
      'en',
      'Too many sign-in attempts. Try again later.',
      'Try again in approximately 73 seconds.',
    ],
    ['zh-CN', '登录尝试过于频繁，请稍后重试。', '请大约 73 秒后重试。'],
  ] as const)(
    'normalizes 429 and formats Retry-After in %s',
    async (locale, expected, retryCopy) => {
      const { alert } = await submitLogin(locale, {
        code: 'RC9_UNKNOWN_RATE_LIMIT',
        retryAfter: 73,
        status: 429,
      })
      expect(alert).toHaveTextContent(expected)
      expect(alert).toHaveTextContent(retryCopy)
    },
  )

  it('omits an unsafe request ID instead of treating it as display text', async () => {
    const unsafeRequestId = '请求\nRC9-UNSAFE-ID'
    const { alert } = await submitLogin('en', {
      code: 'CONTROL_PLANE_UNAVAILABLE',
      requestId: unsafeRequestId,
      status: 503,
    })

    expect(alert).not.toHaveTextContent('RC9-UNSAFE-ID')
    expect(screen.queryByText('Request details')).not.toBeInTheDocument()
  })
})
