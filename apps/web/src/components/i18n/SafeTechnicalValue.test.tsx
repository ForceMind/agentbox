import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SafeTechnicalValue } from './SafeTechnicalValue'

describe('SafeTechnicalValue', () => {
  it('renders printable ASCII values inside the fixed technical boundary', () => {
    render(<SafeTechnicalValue fallback="Unknown" value="refs/heads/main" />)

    const value = screen.getByText('refs/heads/main')
    expect(value).toHaveAttribute('lang', 'en')
    expect(value).toHaveAttribute('dir', 'ltr')
    expect(value).toHaveAttribute('translate', 'no')
  })

  it('uses caller-owned fallback copy for invalid external values', () => {
    render(<SafeTechnicalValue fallback="未知" value="功能/本地化" />)

    expect(screen.getByText('未知')).toBeInTheDocument()
    expect(screen.queryByText('功能/本地化')).not.toBeInTheDocument()
  })

  it('does not throw for missing or non-string values', () => {
    const { rerender } = render(
      <SafeTechnicalValue fallback="Unknown" value={null} />,
    )
    expect(screen.getByText('Unknown')).toBeInTheDocument()

    rerender(<SafeTechnicalValue fallback="Unknown" value={{}} />)
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })
})
