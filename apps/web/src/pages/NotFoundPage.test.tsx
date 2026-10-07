import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
} from '../features/auth/AuthContext'
import type { Locale } from '../i18n'
import { ApiClient } from '../lib/api'
import { NotFoundPage } from './NotFoundPage'

const copy = {
  en: {
    title: 'Page not found',
    signIn: 'Back to sign in',
    dashboard: 'Back to Dashboard',
  },
  'zh-CN': {
    title: '未找到页面',
    signIn: '返回登录',
    dashboard: '返回 Dashboard',
  },
} satisfies Record<Locale, Record<'title' | 'signIn' | 'dashboard', string>>

function context(status: AuthStatus): AuthContextValue {
  return {
    api: new ApiClient(),
    status,
    auth: null,
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

describe('NotFoundPage fixed recovery presentation', () => {
  it.each(['en', 'zh-CN'] as const)(
    'updates its sole Link from checking to authenticated without echoing the route in %s',
    (locale) => {
      const missing =
        '/ENTRY-PRIVATE-PATH?token=ENTRY-PRIVATE-QUERY#ENTRY-PRIVATE-HASH'
      const view = (status: AuthStatus) => (
        <MemoryRouter initialEntries={[missing]}>
          <AuthContext.Provider value={context(status)}>
            <NotFoundPage locale={locale} />
          </AuthContext.Provider>
        </MemoryRouter>
      )
      const { rerender } = render(view('checking'))
      const link = screen.getByRole('link', { name: copy[locale].signIn })
      expect(link).toHaveAttribute('href', '/login')
      expect(screen.getAllByRole('link')).toHaveLength(1)
      expect(document.title).toContain(copy[locale].title)
      expect(screen.getByRole('main')).toHaveTextContent('404')
      expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)

      rerender(view('authenticated'))
      expect(screen.getByRole('link', { name: copy[locale].dashboard })).toBe(
        link,
      )
      expect(link).toHaveAttribute('href', '/dashboard')
      expect(screen.getAllByRole('link')).toHaveLength(1)

      rerender(view('unauthenticated'))
      expect(screen.getByRole('link', { name: copy[locale].signIn })).toBe(link)
      expect(link).toHaveAttribute('href', '/login')
      expect(screen.queryByRole('button')).not.toBeInTheDocument()
      for (const sentinel of [
        'ENTRY-PRIVATE-PATH',
        'ENTRY-PRIVATE-QUERY',
        'ENTRY-PRIVATE-HASH',
      ]) {
        expect(document.body).not.toHaveTextContent(sentinel)
        expect(document.title).not.toContain(sentinel)
        expect(link.outerHTML).not.toContain(sentinel)
      }
    },
  )
})
