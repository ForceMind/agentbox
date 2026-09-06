import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const useDoctorMock = vi.hoisted(() => vi.fn())

vi.mock('../features/doctor/useDoctor', () => ({
  isSafeDoctorFindingCode: (value: unknown) =>
    typeof value === 'string' && /^[A-Z][A-Z0-9_]{0,79}$/.test(value),
  useDoctor: useDoctorMock,
}))

import { DoctorPage } from './DoctorPage'

function loadedDoctor(projectRoot = '/Projects/agentbox') {
  return {
    status: 'loaded' as const,
    response: {
      data: {
        status: 'ready' as const,
        checks: {
          configuration_valid: true,
          database_reachable: true,
          migrations_current: true,
          admin_initialized: true,
          control_plane_ready: true,
        },
        policy: {
          environment: 'test',
          bind_host: '127.0.0.1',
          bind_port: 8080,
          session_ttl_seconds: 7200,
          session_idle_ttl_seconds: 1800,
          login_rate_limit: 5,
          login_rate_window_seconds: 60,
          login_lock_duration_seconds: 30,
        },
        codex: {
          installed: true,
          version: '0.3.0-rc.9',
          installation_type: 'standalone' as const,
          remote_control: 'supported' as const,
          remote_state: 'stopped' as const,
          findings: [],
        },
        claude: {
          installed: true,
          version: '1.2.3',
          authentication: 'authenticated' as const,
          remote_control: 'supported' as const,
          tmux_installed: true,
          tmux_version: '3.5',
          managed_sessions: 0,
          unmanaged_sessions: 0,
          workspace_interaction_warnings: 0,
          findings: [],
        },
        projects: {
          project_root: projectRoot,
          project_count: 1,
          git_installed: true,
          git_version: '2.48.0',
          github_cli_installed: true,
          github_authentication: 'authenticated' as const,
          findings: [],
        },
      },
    },
  }
}

describe('DoctorPage technical value boundary', () => {
  beforeEach(() => useDoctorMock.mockReset())

  it('renders a valid Project root as fixed English LTR technical text', () => {
    useDoctorMock.mockReturnValue(loadedDoctor())
    render(<DoctorPage locale="en" />)

    const root = screen.getByText('/Projects/agentbox')
    expect(root).toHaveAttribute('lang', 'en')
    expect(root).toHaveAttribute('dir', 'ltr')
    expect(root).toHaveAttribute('translate', 'no')
  })

  it('does not render an invalid Project root', () => {
    const root = '/Projects/维护者'
    useDoctorMock.mockReturnValue(loadedDoctor(root))
    render(<DoctorPage locale="zh-CN" />)

    expect(screen.queryByText(root)).not.toBeInTheDocument()
    expect(screen.getAllByText('未知').length).toBeGreaterThanOrEqual(1)
  })
})
