import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import { ApiClient } from '../lib/api'
import { LoginPage } from './LoginPage'

const labels = {
  en: { username: 'Username', password: 'Password', submit: 'Sign in' },
  'zh-CN': { username: '用户名', password: '密码', submit: '登录' },
} satisfies Record<Locale, Record<'username' | 'password' | 'submit', string>>

function renderLogin(
  locale: Locale,
  login: AuthContextValue['login'] = vi.fn(async () => undefined),
) {
  const value: AuthContextValue = {
    api: new ApiClient(),
    auth: null,
    status: 'unauthenticated',
    login,
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ status: 'ok' }))),
  )
  render(
    <AuthContext.Provider value={value}>
      <LoginPage locale={locale} />
    </AuthContext.Provider>,
  )
  return {
    login,
    username: screen.getByLabelText(labels[locale].username),
    password: screen.getByLabelText(labels[locale].password),
    submit: screen.getByRole('button', { name: labels[locale].submit }),
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('LoginPage form presentation contracts', () => {
  it.each(['en', 'zh-CN'] as const)(
    'retains accessible credential input attributes and initial focus in %s',
    async (locale) => {
      const { username, password, submit } = renderLogin(locale)
      await act(async () => undefined)

      expect(username).toHaveFocus()
      expect(username).toBeRequired()
      expect(username).toHaveAttribute('autocomplete', 'username')
      expect(username).toHaveAttribute('autocapitalize', 'none')
      expect(username).toHaveAttribute('maxlength', '64')
      expect(password).toBeRequired()
      expect(password).toHaveAttribute('type', 'password')
      expect(password).toHaveAttribute('autocomplete', 'current-password')
      expect(password).toHaveAttribute('maxlength', '1024')
      expect(submit).toHaveAttribute('type', 'submit')
      expect(submit).toBeDisabled()
      expect(screen.queryByRole('link')).not.toBeInTheDocument()
      expect(screen.getAllByRole('button')).toHaveLength(1)
      expect(
        screen.getByRole('complementary', {
          name:
            locale === 'en' ? 'AgentBox product context' : 'AgentBox 产品简介',
        }),
      ).toHaveTextContent(
        locale === 'en' ? 'No browser shell' : '浏览器不提供 shell',
      )
      expect(
        screen.getByRole('heading', {
          name:
            locale === 'en' ? 'Start with a Project.' : '从一个 Project 开始。',
        }),
      ).toBeInTheDocument()
    },
  )

  it.each([
    ['', 'fixture-password'],
    ['   ', 'fixture-password'],
    ['fixture-user', ''],
  ])(
    'rejects inadmissible form values without calling login (%j)',
    async (name, secret) => {
      const { username, password, submit, login } = renderLogin('en')
      fireEvent.change(username, { target: { value: name } })
      fireEvent.change(password, { target: { value: secret } })
      expect(submit).toBeDisabled()
      // Native form submission is the shared handler for click and keyboard entry.
      // Browser tests separately verify the actual Enter-key default action.
      fireEvent.submit(submit.closest('form')!)
      await act(async () => undefined)
      expect(login).not.toHaveBeenCalled()
      expect(password).toHaveValue(secret)
    },
  )

  it('keeps the original username and clears the password after a settled success', async () => {
    let complete!: () => void
    const login = vi.fn(
      () => new Promise<void>((resolve) => (complete = resolve)),
    )
    const { username, password, submit } = renderLogin('en', login)
    fireEvent.change(username, { target: { value: '  fixture-user  ' } })
    fireEvent.change(password, { target: { value: 'fixture-password' } })
    fireEvent.submit(submit.closest('form')!)

    expect(login).toHaveBeenCalledExactlyOnceWith(
      '  fixture-user  ',
      'fixture-password',
    )
    expect(submit).toBeDisabled()
    expect(submit).toHaveTextContent('Signing in…')
    fireEvent.click(submit)
    expect(login).toHaveBeenCalledTimes(1)

    await act(async () => complete())
    expect(username).toHaveValue('  fixture-user  ')
    expect(password).toHaveValue('')
    expect(submit).toBeDisabled()
    expect(submit).toHaveTextContent('Sign in')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each(['en', 'zh-CN'] as const)(
    'clears the password on a non-API rejection without exposing its prose in %s',
    async (locale) => {
      const login = vi.fn(async () => {
        throw new Error('ENTRY-PRIVATE-TRANSPORT-CANARY')
      })
      const { username, password, submit } = renderLogin(locale, login)
      fireEvent.change(username, { target: { value: 'fixture-user' } })
      fireEvent.change(password, { target: { value: 'ENTRY-SECRET-CANARY' } })
      fireEvent.submit(submit.closest('form')!)

      expect(await screen.findByRole('alert')).toHaveTextContent(
        locale === 'en'
          ? 'The control plane is unavailable.'
          : '控制平面暂不可用。',
      )
      expect(username).toHaveValue('fixture-user')
      expect(password).toHaveValue('')
      expect(document.body).not.toHaveTextContent(
        'ENTRY-PRIVATE-TRANSPORT-CANARY',
      )
      expect(document.body).not.toHaveTextContent('ENTRY-SECRET-CANARY')
      expect(login).toHaveBeenCalledTimes(1)
    },
  )
})
