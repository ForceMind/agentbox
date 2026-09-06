import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LocalizedApiError, OpaqueUserValue, TechnicalValue } from './index'

describe('localized API error boundary', () => {
  it('localizes a known code and renders technical evidence safely', () => {
    const error = {
      code: 'WAW_INVALID_AGENT',
      requestId: 'req_2026-09-06:1',
      get message(): never {
        throw new Error('server prose was read')
      },
    }

    render(<LocalizedApiError error={error} locale="zh-CN" />)

    expect(screen.getByRole('alert')).toHaveTextContent('所选 AgentType 无效。')
    for (const value of [error.code, error.requestId]) {
      const technical = screen.getByText(value)
      expect(technical).toHaveAttribute('lang', 'en')
      expect(technical).toHaveAttribute('dir', 'ltr')
      expect(technical).toHaveAttribute('translate', 'no')
    }
  })

  it('uses generic local copy for an unknown code and omits unsafe fields', () => {
    render(
      <LocalizedApiError
        error={{ code: '服务器错误原文', requestId: '非 ASCII' }}
        locale="en"
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      'The operation could not be completed. Try again.',
    )
    expect(screen.queryByText('服务器错误原文')).not.toBeInTheDocument()
    expect(screen.queryByText('非 ASCII')).not.toBeInTheDocument()
  })
})

describe('typed display boundaries', () => {
  it('renders technical values with fixed ASCII metadata', () => {
    render(<TechnicalValue value="refs/heads/main" />)

    const value = screen.getByText('refs/heads/main')
    expect(value).toHaveAttribute('lang', 'en')
    expect(value).toHaveAttribute('dir', 'ltr')
    expect(value).toHaveAttribute('translate', 'no')
  })

  it('renders printable ASCII HTML payloads only as text', () => {
    const payload = '<img src=x onerror=alert(1)>'
    const { container } = render(<TechnicalValue value={payload} />)

    expect(screen.getByText(payload)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('rejects Unicode at the technical component boundary', () => {
    expect(() => TechnicalValue({ value: '技术值' })).toThrow(TypeError)
  })

  it('preserves Unicode user values without treating them as technical data', () => {
    render(<OpaqueUserValue value="张三的项目 🚀" />)

    const value = screen.getByText('张三的项目 🚀')
    expect(value).toHaveAttribute('dir', 'auto')
    expect(value).toHaveAttribute('translate', 'no')
    expect(value).not.toHaveAttribute('lang', 'en')
  })
})
