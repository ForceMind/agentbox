import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  useClaude,
  type ClaudeSessionView,
  type ClaudeStatusView,
} from '../features/claude/useClaude'
import { localizeApiError } from '../i18n'
import {
  claudeCatalog,
  type ClaudeMessageParameters,
} from '../i18n/catalogs/claude'
import { ClaudePage } from './ClaudePage'

vi.mock('../features/claude/useClaude', () => ({ useClaude: vi.fn() }))

const sessionA = {
  project_id: 'project-a',
  display_name: 'Project A',
  state: 'running',
  attach_command: 'tmux attach-session -t =agentbox-claude-project-a',
  workspace_state: 'unknown',
  tmux_running: true,
  remote_readiness: 'ready',
} as const

const sessionB = {
  ...sessionA,
  project_id: 'project-b',
  display_name: 'Project B',
  attach_command: 'tmux attach-session -t =agentbox-claude-project-b',
} as const

function model(): ReturnType<typeof useClaude> {
  return {
    actionErrors: {
      'project-a': {
        code: 'CLAUDE_RUNTIME_UNAVAILABLE',
        requestId: 'req_project_a_failure',
        message: 'PROJECT-A-SERVER-PROSE-CANARY',
      },
    },
    hideOutput: vi.fn(),
    isCurrent: () => true,
    outputs: {},
    pending: [],
    refresh: vi.fn(async () => undefined),
    refreshing: false,
    revealOutput: vi.fn(async () => undefined),
    sessionAction: vi.fn(async () => undefined),
    view: {
      status: 'loaded',
      data: {
        status: {
          installed: true,
          version: '1.fixture',
          authentication: 'unknown',
          capabilities: { remote_control: 'supported' },
          tmux_installed: true,
          tmux_version: '3.fixture',
          managed_sessions: 2,
          unmanaged_sessions: 0,
          workspace_interaction_warnings: 0,
        },
        sessions: [sessionA, sessionB],
      },
    },
  } as ReturnType<typeof useClaude>
}

describe('ClaudePage Project-local action errors', () => {
  afterEach(() => vi.clearAllMocks())

  it('renders Project A local error without leaking it into Project B', () => {
    vi.mocked(useClaude).mockReturnValue(model())
    render(<ClaudePage locale="en" />)

    const projectA = screen
      .getByRole('heading', { name: 'Project A' })
      .closest('article')
    const projectB = screen
      .getByRole('heading', { name: 'Project B' })
      .closest('article')
    expect(projectA).not.toBeNull()
    expect(projectB).not.toBeNull()

    const projectAAlert = within(projectA as HTMLElement).getByRole('alert')
    expect(projectAAlert).toHaveTextContent(
      'Claude is temporarily unavailable.',
    )
    expect(projectAAlert).toHaveTextContent('CLAUDE_RUNTIME_UNAVAILABLE')
    expect(within(projectB as HTMLElement).queryByRole('alert')).toBeNull()
    expect(screen.queryByText('PROJECT-A-SERVER-PROSE-CANARY')).toBeNull()
  })
})

function presentationModel(
  overrides: Partial<ReturnType<typeof useClaude>> = {},
): ReturnType<typeof useClaude> {
  return { ...model(), actionErrors: {}, ...overrides }
}

function loadedClaude(
  sessions: readonly ClaudeSessionView[] = [sessionA, sessionB],
  status: Partial<ClaudeStatusView> = {},
) {
  const original = model().view
  if (original.status !== 'loaded') throw new Error('Expected loaded fixture')
  return {
    status: 'loaded' as const,
    data: {
      sessions,
      status: { ...original.data.status, ...status },
    },
  }
}

function projectCard(name: string): HTMLElement {
  const card = screen.getByRole('heading', { name }).closest('article')
  expect(card).not.toBeNull()
  return card as HTMLElement
}

describe.each(['zh-CN', 'en'] as const)(
  'ClaudePage management presentation in %s',
  (locale) => {
    const message = (key: keyof ClaudeMessageParameters) =>
      claudeCatalog.catalogs[locale][key]({})
    const field = (
      container: HTMLElement,
      key: keyof ClaudeMessageParameters,
    ) =>
      within(container).getByText(message(key), { selector: 'dt' })
        .nextElementSibling

    afterEach(() => vi.clearAllMocks())

    it.each(['loading', 'error'] as const)(
      'distinguishes %s from an empty Project list without exposing action controls',
      (status) => {
        const current = presentationModel({
          view:
            status === 'loading'
              ? { status }
              : {
                  status,
                  error: {
                    code: 'CLAUDE_RUNTIME_UNAVAILABLE',
                    requestId: 'req_claude_unavailable',
                  },
                },
        })
        vi.mocked(useClaude).mockReturnValue(current)
        render(<ClaudePage locale={locale} />)

        expect(
          screen.getByRole('heading', {
            name: message('claude.title'),
            level: 1,
          }),
        ).toBeVisible()
        if (status === 'loading') {
          expect(screen.getByRole('status')).toHaveTextContent(
            message('claude.loading'),
          )
          expect(screen.queryByRole('alert')).toBeNull()
        } else {
          expect(screen.getByRole('alert')).toHaveTextContent(
            localizeApiError(locale, 'CLAUDE_RUNTIME_UNAVAILABLE'),
          )
          expect(
            screen.getByRole('heading', {
              name: message('claude.statusUnavailable'),
            }),
          ).toBeVisible()
        }
        expect(
          screen.queryByRole('heading', {
            name: message('claude.noConfiguredProjects'),
          }),
        ).toBeNull()
        expect(
          screen.queryByRole('heading', { name: sessionA.display_name }),
        ).toBeNull()
        expect(
          screen.queryByRole('button', { name: message('claude.reveal') }),
        ).toBeNull()
        expect(document.querySelector('.sensitive-output pre')).toBeNull()
        expect(current.sessionAction).not.toHaveBeenCalled()
        expect(current.revealOutput).not.toHaveBeenCalled()
      },
    )

    it('keeps an empty managed Project list distinct from unmanaged tmux counts', () => {
      const current = presentationModel({
        view: loadedClaude([], {
          managed_sessions: 0,
          unmanaged_sessions: 7,
          workspace_interaction_warnings: 2,
        }),
      })
      vi.mocked(useClaude).mockReturnValue(current)
      render(<ClaudePage locale={locale} />)

      expect(
        screen.getByRole('heading', {
          name: message('claude.noConfiguredProjects'),
        }),
      ).toBeVisible()
      expect(
        screen.getByText(message('claude.noConfiguredProjectsDescription')),
      ).toBeVisible()
      expect(field(document.body, 'claude.managedSessions')).toHaveTextContent(
        '0',
      )
      expect(
        field(document.body, 'claude.unmanagedSessions'),
      ).toHaveTextContent('7')
      expect(
        field(document.body, 'claude.workspaceWarnings'),
      ).toHaveTextContent('2')
      expect(
        screen.queryByRole('region', { name: message('claude.sessionsAria') }),
      ).toBeNull()
      expect(
        screen.queryByRole('button', { name: message('claude.startSession') }),
      ).toBeNull()
      expect(current.revealOutput).not.toHaveBeenCalled()
      expect(current.sessionAction).not.toHaveBeenCalled()
    })

    it('preserves installation, authentication, Remote capability and tmux unavailability independently', () => {
      vi.mocked(useClaude).mockReturnValue(
        presentationModel({
          view: loadedClaude([], {
            installed: false,
            version: null,
            authentication: 'unknown',
            capabilities: { remote_control: 'unsupported' },
            tmux_installed: false,
            tmux_version: null,
            managed_sessions: 0,
          }),
        }),
      )
      render(<ClaudePage locale={locale} />)

      const installation = screen.getByRole('region', {
        name: message('claude.installationAria'),
      })
      expect(field(installation, 'claude.installed')).toHaveTextContent(
        message('claude.no'),
      )
      expect(field(installation, 'claude.authentication')).toHaveTextContent(
        'unknown',
      )
      expect(field(installation, 'claude.remoteCapability')).toHaveTextContent(
        'unsupported',
      )
      expect(
        within(installation).getByText(message('claude.unavailable')),
      ).toBeVisible()
      expect(
        within(installation).getAllByText(message('claude.unknown')),
      ).toHaveLength(2)
      expect(screen.queryByText(message('claude.ready'))).toBeNull()
      expect(screen.queryByRole('alert')).toBeNull()
    })

    it.each([
      [
        'running',
        'claude.stateRunning',
        true,
        'ready',
        'initialized_by_agentbox',
        'claude.workspaceInitialized',
      ],
      [
        'stopped',
        'claude.stateStopped',
        false,
        'unknown',
        'unknown',
        'claude.workspaceUnknown',
      ],
      [
        'starting',
        'claude.stateStarting',
        true,
        'unknown',
        'unknown',
        'claude.workspaceUnknown',
      ],
      [
        'needs_interaction',
        'claude.stateNeedsInteraction',
        true,
        'unknown',
        'requires_user_confirmation',
        'claude.workspaceRequiresConfirmation',
      ],
      [
        'broken',
        'claude.stateBroken',
        false,
        'unknown',
        'unknown',
        'claude.workspaceUnknown',
      ],
      [
        'unknown',
        'claude.stateUnknown',
        false,
        'unknown',
        'unknown',
        'claude.workspaceUnknown',
      ],
    ] as const)(
      'shows %s without conflating session state, tmux, readiness and Workspace Trust',
      (
        state,
        stateKey,
        tmuxRunning,
        remoteReadiness,
        workspaceState,
        workspaceKey,
      ) => {
        const current = presentationModel({
          view: loadedClaude([
            {
              ...sessionA,
              state,
              tmux_running: tmuxRunning,
              remote_readiness: remoteReadiness,
              workspace_state: workspaceState,
            },
          ]),
        })
        vi.mocked(useClaude).mockReturnValue(current)
        render(<ClaudePage locale={locale} />)

        const card = projectCard(sessionA.display_name)
        expect(
          within(card).getByText(message('claude.sessionState'))
            .nextElementSibling,
        ).toHaveTextContent(message(stateKey))
        expect(field(card, 'claude.tmux')).toHaveTextContent(
          message(tmuxRunning ? 'claude.stateRunning' : 'claude.stateStopped'),
        )
        expect(field(card, 'claude.remoteReadiness')).toHaveTextContent(
          message(
            remoteReadiness === 'ready' ? 'claude.ready' : 'claude.unknown',
          ),
        )
        expect(field(card, 'claude.workspaceTrust')).toHaveTextContent(
          message(workspaceKey),
        )
        expect(
          within(card).getByRole('button', {
            name: message(
              tmuxRunning ? 'claude.stopSession' : 'claude.startSession',
            ),
          }),
        ).toBeEnabled()
        expect(
          within(card).getByRole('button', { name: message('claude.reveal') }),
        ).toHaveProperty('disabled', !tmuxRunning)
        if (state === 'needs_interaction') {
          const notice = within(card).getByRole('status')
          expect(notice).toHaveTextContent(message('claude.interactionNotice'))
          expect(notice).toBeVisible()
          expect(notice.closest('details')).toBeNull()
        } else {
          expect(
            within(card).queryByText(message('claude.interactionNotice')),
          ).toBeNull()
        }
        expect(current.revealOutput).not.toHaveBeenCalled()
        expect(document.querySelector('.sensitive-output pre')).toBeNull()
      },
    )

    it.each(['start', 'stop', 'output'] as const)(
      'keeps %s pending and errors owned by Project A while Project B remains usable',
      (operation) => {
        const current = presentationModel({
          pending: [{ projectId: sessionA.project_id, operation }],
          actionErrors: model().actionErrors,
          view: loadedClaude([
            { ...sessionA, tmux_running: operation !== 'start' },
            sessionB,
          ]),
        })
        vi.mocked(useClaude).mockReturnValue(current)
        render(<ClaudePage locale={locale} />)

        const cardA = projectCard(sessionA.display_name)
        const cardB = projectCard(sessionB.display_name)
        const pendingAction = within(cardA).getByRole('button', {
          name: message(
            operation === 'start'
              ? 'claude.starting'
              : operation === 'stop'
                ? 'claude.stopping'
                : 'claude.stopSession',
          ),
        })
        const pendingOutput = within(cardA).getByRole('button', {
          name: message(
            operation === 'output' ? 'claude.outputLoading' : 'claude.reveal',
          ),
        })
        expect(pendingAction).toBeDisabled()
        expect(pendingOutput).toBeDisabled()
        const refresh = screen.getByRole('button', {
          name: message('claude.refresh'),
        })
        expect(refresh).toBeDisabled()
        fireEvent.click(pendingAction)
        fireEvent.click(pendingOutput)
        fireEvent.click(refresh)
        expect(current.sessionAction).not.toHaveBeenCalled()
        expect(current.revealOutput).not.toHaveBeenCalled()
        expect(current.refresh).not.toHaveBeenCalled()

        const error = within(cardA).getByRole('alert')
        expect(error).toHaveTextContent(
          localizeApiError(locale, 'CLAUDE_RUNTIME_UNAVAILABLE'),
        )
        expect(error).toHaveTextContent('req_project_a_failure')
        expect(error).toBeVisible()
        expect(error.closest('details')).toBeNull()
        expect(within(cardB).queryByRole('alert')).toBeNull()
        expect(document.body.textContent).not.toContain(
          'PROJECT-A-SERVER-PROSE-CANARY',
        )

        const stopB = within(cardB).getByRole('button', {
          name: message('claude.stopSession'),
        })
        const revealB = within(cardB).getByRole('button', {
          name: message('claude.reveal'),
        })
        expect(stopB).toBeEnabled()
        expect(revealB).toBeEnabled()
        fireEvent.click(stopB)
        fireEvent.click(revealB)
        expect(current.sessionAction).toHaveBeenCalledExactlyOnceWith(
          sessionB.project_id,
          'stop',
        )
        expect(current.revealOutput).toHaveBeenCalledExactlyOnceWith(
          sessionB.project_id,
        )
      },
    )

    it('disables both Project mutation and output controls during refresh', () => {
      const current = presentationModel({
        refreshing: true,
        view: loadedClaude([{ ...sessionA, tmux_running: false }, sessionB]),
      })
      vi.mocked(useClaude).mockReturnValue(current)
      render(<ClaudePage locale={locale} />)

      for (const name of [
        message('claude.refresh'),
        message('claude.startSession'),
        message('claude.stopSession'),
        message('claude.reveal'),
      ]) {
        for (const control of screen.getAllByRole('button', {
          name,
        })) {
          expect(control).toBeDisabled()
          fireEvent.click(control)
        }
      }
      expect(current.refresh).not.toHaveBeenCalled()
      expect(current.sessionAction).not.toHaveBeenCalled()
      expect(current.revealOutput).not.toHaveBeenCalled()
    })

    it('renders long Project names as inert text and copies only the supplied generated attach command', async () => {
      const displayName = `项目 <img src=x onerror=alert(1)> ${'long-project-name-'.repeat(12)}`
      const attachCommand = `tmux attach-session -t =agentbox-claude-${'immutable-relative-key-'.repeat(10)}`
      const session = {
        ...sessionA,
        display_name: displayName,
        attach_command: attachCommand,
      }
      const current = presentationModel({
        view: loadedClaude([session, { ...sessionB, attach_command: null }]),
      })
      const writeText = vi.fn(async () => undefined)
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText },
      })
      vi.mocked(useClaude).mockReturnValue(current)
      render(<ClaudePage locale={locale} />)

      const cardA = projectCard(displayName)
      const cardB = projectCard(sessionB.display_name)
      const name = within(cardA).getByText(displayName)
      expect(name.tagName).toBe('BDI')
      expect(name).toHaveAttribute('dir', 'auto')
      expect(name).toHaveAttribute('translate', 'no')
      expect(cardA.querySelector('img, script, iframe, a')).toBeNull()
      const command = within(cardA).getByText(attachCommand)
      expect(command).toBeVisible()
      expect(command).toHaveAttribute('lang', 'en')
      expect(command).toHaveAttribute('dir', 'ltr')
      expect(command).toHaveAttribute('translate', 'no')
      expect(
        within(cardA).getByText(message('claude.attachLabel')),
      ).toBeVisible()
      expect(writeText).not.toHaveBeenCalled()
      expect(
        within(cardB).getByRole('button', {
          name: message('claude.copyAttach'),
        }),
      ).toBeDisabled()

      fireEvent.click(
        within(cardA).getByRole('button', {
          name: message('claude.copyAttach'),
        }),
      )
      await waitFor(() =>
        expect(writeText).toHaveBeenCalledExactlyOnceWith(attachCommand),
      )
      expect(
        await within(cardA).findByRole('button', {
          name: message('claude.copied'),
        }),
      ).toBeVisible()
      expect(
        within(cardB).queryByRole('button', { name: message('claude.copied') }),
      ).toBeNull()
      fireEvent.click(
        within(cardA).getByRole('button', {
          name: message('claude.stopSession'),
        }),
      )
      expect(current.sessionAction).toHaveBeenCalledExactlyOnceWith(
        sessionA.project_id,
        'stop',
      )
      expect(current.revealOutput).not.toHaveBeenCalled()
    })

    it('keeps pane text absent by default and removes the revealed DOM when Hide clears it', () => {
      const current = presentationModel()
      vi.mocked(useClaude).mockReturnValue(current)
      const { rerender } = render(<ClaudePage locale={locale} />)
      expect(document.querySelector('.sensitive-output pre')).toBeNull()
      expect(current.revealOutput).not.toHaveBeenCalled()
      const cardA = projectCard(sessionA.display_name)
      fireEvent.click(
        within(cardA).getByRole('button', { name: message('claude.reveal') }),
      )
      expect(current.revealOutput).toHaveBeenCalledExactlyOnceWith(
        sessionA.project_id,
      )

      const output =
        '<script>window.paneCanary = true</script> SYNTHETIC-PANE-CANARY'
      vi.mocked(useClaude).mockReturnValue({
        ...current,
        outputs: { [sessionA.project_id]: { output, truncated: true } },
      })
      rerender(<ClaudePage locale={locale} />)
      const revealed = within(projectCard(sessionA.display_name)).getByText(
        output,
      )
      expect(revealed.closest('pre')).toBeVisible()
      expect(revealed.closest('details')).toBeNull()
      expect(revealed).toHaveAttribute('dir', 'auto')
      expect(revealed).toHaveAttribute('translate', 'no')
      expect(screen.getByText(message('claude.outputTruncated'))).toBeVisible()
      expect(document.querySelector('.sensitive-output script')).toBeNull()
      expect(projectCard(sessionB.display_name).querySelector('pre')).toBeNull()

      fireEvent.click(
        within(projectCard(sessionA.display_name)).getByRole('button', {
          name: message('claude.hide'),
        }),
      )
      expect(current.hideOutput).toHaveBeenCalledExactlyOnceWith(
        sessionA.project_id,
      )
      vi.mocked(useClaude).mockReturnValue(current)
      rerender(<ClaudePage locale={locale} />)
      expect(document.body.textContent).not.toContain(output)
      expect(document.querySelector('.sensitive-output pre')).toBeNull()
      expect(screen.queryByText(message('claude.outputTruncated'))).toBeNull()
    })
  },
)
