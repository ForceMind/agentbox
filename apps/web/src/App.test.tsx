import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('AgentBox engineering skeleton', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the project identity and skeleton status', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => undefined)),
    )

    render(<App />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'AgentBox' }),
    ).toBeInTheDocument()
    expect(screen.getByText('AI Developer Infrastructure')).toBeInTheDocument()
    expect(screen.getByText('Engineering skeleton')).toBeInTheDocument()
  })

  it('shows a healthy backend response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok' }),
      }),
    )

    render(<App />)

    await waitFor(() => {
      expect(
        screen.getByLabelText('Backend status: Online'),
      ).toBeInTheDocument()
    })
  })
})
