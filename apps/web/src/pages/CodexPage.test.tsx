import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const useCodexMock = vi.hoisted(() => vi.fn())

vi.mock('../features/codex/useCodex', () => ({
  useCodex: useCodexMock,
}))

import { CodexPage } from './CodexPage'

function loadedView(diagnostics: unknown[] = []) {
  return {
    status: 'loaded' as const,
    response: {
      api_version: 'v1' as const,
      request_id: 'req_codex_page',
      data: {
        installed: true,
        version: '1.fixture',
        selected_executable: '/fixture/bin/codex',
        alternatives: [],
        installation_type: 'standalone' as const,
        conflict_detected: false,
        authentication: 'authenticated' as const,
        capabilities: {
          remote_control: 'supported' as const,
          start: 'supported' as const,
          stop: 'supported' as const,
          pair: 'supported' as const,
          status: 'unsupported' as const,
        },
        remote_state: 'stopped' as const,
        remote_confidence: 'reported' as const,
        diagnostics,
      },
    },
  }
}

function model(overrides: Record<string, unknown> = {}) {
  return {
    actionError: null,
    clearPair: vi.fn(),
    generatePairCode: vi.fn(() => Promise.resolve()),
    pair: null,
    pending: null,
    refresh: vi.fn(() => Promise.resolve()),
    remoteAction: vi.fn(() => Promise.resolve()),
    view: loadedView(),
    ...overrides,
  }
}

describe('CodexPage localized safety boundary', () => {
  beforeEach(() => {
    useCodexMock.mockReset()
  })

  it('never renders server prose from action errors or diagnostics', () => {
    const canary = 'SERVER-PROSE-CANARY-CODEX-DOM-7J2M'
    useCodexMock.mockReturnValue(
      model({
        actionError: {
          code: 'UNTRUSTED_SERVER_PROSE',
          message: canary,
          requestId: 'req_codex_safe',
        },
        view: loadedView([
          {
            code: 'CODEX_REMOTE_STATUS_UNSUPPORTED',
            severity: 'info',
            summary: canary,
            remediation: canary,
          },
        ]),
      }),
    )

    render(<CodexPage />)

    expect(document.body.textContent).not.toContain(canary)
    expect(
      screen.getByText('The operation could not be completed. Try again.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Codex Remote status is not supported by this installation.',
      ),
    ).toBeInTheDocument()
    const code = screen.getByText('UNTRUSTED_SERVER_PROSE')
    expect(code).toHaveAttribute('lang', 'en')
    expect(code).toHaveAttribute('dir', 'ltr')
    expect(code).toHaveAttribute('translate', 'no')
    const version = screen.getByText('1.fixture')
    expect(version).toHaveAttribute('lang', 'en')
    expect(version).toHaveAttribute('dir', 'ltr')
    expect(version).toHaveAttribute('translate', 'no')
  })

  it('falls back to localized unknown copy for invalid protocol values', () => {
    const view = loadedView()
    view.response.data.version = '版本 1'
    view.response.data.selected_executable = '/fixture/可执行/codex'
    useCodexMock.mockReturnValue(
      model({
        pair: {
          pair_code: '配对码',
          expires_at: null,
          display_once: true,
        },
        view,
      }),
    )

    render(<CodexPage />)

    for (const value of ['版本 1', '/fixture/可执行/codex', '配对码']) {
      expect(screen.queryByText(value)).not.toBeInTheDocument()
    }
    expect(screen.getAllByText('Unknown')).toHaveLength(3)
  })

  it('reports clipboard failure without exposing the thrown error', async () => {
    const canary = 'CLIPBOARD-ERROR-CANARY-CODEX-8Q6N'
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: vi.fn(() => Promise.reject(new Error(canary))),
      },
    })
    useCodexMock.mockReturnValue(
      model({
        pair: {
          pair_code: 'PAIR-CODE-FIXTURE-1234',
          expires_at: null,
          display_once: true,
        },
      }),
    )

    render(<CodexPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))

    expect(
      await screen.findByText('The code could not be copied. Try again.'),
    ).toBeInTheDocument()
    expect(document.body.textContent).not.toContain(canary)
  })

  it('isolates Pair confirmation, traps Tab, and restores focus on Escape and Cancel', async () => {
    useCodexMock.mockReturnValue(model())
    render(<CodexPage />)

    const trigger = screen.getByRole('button', { name: 'Pair New Device' })
    fireEvent.click(trigger)

    const dialog = screen.getByRole('dialog')
    const generate = screen.getByRole('button', { name: 'Generate Code' })
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    await waitFor(() => expect(generate).toHaveFocus())
    const background = document.querySelector('[inert]')
    expect(background).toHaveAttribute('aria-hidden', 'true')

    fireEvent.keyDown(generate, { key: 'Tab', shiftKey: true })
    expect(cancel).toHaveFocus()
    fireEvent.keyDown(cancel, { key: 'Tab' })
    expect(generate).toHaveFocus()
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(trigger).toHaveFocus())

    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('moves focus to the one-time code after Generate succeeds', async () => {
    const pairCode = 'PAIR-CODE-FOCUS-FIXTURE-6428'
    const initial = model()
    const revealed = model({
      pair: {
        pair_code: pairCode,
        expires_at: null,
        display_once: true,
      },
    })
    initial.generatePairCode = vi.fn(async () => {
      useCodexMock.mockReturnValue(revealed)
    })
    useCodexMock.mockReturnValue(initial)
    const { rerender } = render(<CodexPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Pair New Device' }))
    fireEvent.click(screen.getByRole('button', { name: 'Generate Code' }))
    rerender(<CodexPage />)

    const reveal = screen.getByText(pairCode).closest('.pair-secret')
    await waitFor(() => expect(reveal).toHaveFocus())
  })

  it('moves focus to the localized error after Generate fails', async () => {
    const initial = model()
    const failed = model({
      actionError: {
        code: 'CODEX_PAIR_FAILED',
        requestId: 'req_pair_focus',
      },
    })
    initial.generatePairCode = vi.fn(async () => {
      useCodexMock.mockReturnValue(failed)
    })
    useCodexMock.mockReturnValue(initial)
    const { rerender } = render(<CodexPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Pair New Device' }))
    fireEvent.click(screen.getByRole('button', { name: 'Generate Code' }))
    rerender(<CodexPage />)

    const error = screen.getByRole('alert')
    await waitFor(() => expect(error).toHaveFocus())
  })
})
