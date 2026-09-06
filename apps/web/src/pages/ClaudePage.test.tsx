import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useClaude } from '../features/claude/useClaude'
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
