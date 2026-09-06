import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthContextValue } from '../auth/AuthContext'
import { ApiClient, ApiError } from '../../lib/api'
import type { DoctorResponse } from '../../lib/contracts'
import {
  projectDoctorError,
  projectDoctorResponse,
  useDoctor,
} from './useDoctor'

const RAW_FINDING_CANARY = 'RC9 RAW FINDING PROSE CANARY'

function response(): DoctorResponse {
  return {
    api_version: 'v1',
    request_id: 'req_rc9_doctor_projection',
    data: {
      status: 'ready',
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
        installation_type: 'standalone',
        remote_control: 'supported',
        remote_state: 'stopped',
        findings: [
          'CODEX_NOT_INSTALLED',
          'RUNTIME_UNAVAILABLE',
          RAW_FINDING_CANARY,
        ],
      },
      claude: {
        installed: true,
        version: '1.2.3',
        authentication: 'authenticated',
        remote_control: 'supported',
        tmux_installed: true,
        tmux_version: '3.5',
        managed_sessions: 0,
        unmanaged_sessions: 0,
        workspace_interaction_warnings: 0,
        findings: [],
      },
      projects: {
        project_root: '/Projects/维护者',
        project_count: 0,
        git_installed: true,
        git_version: '2.48.0',
        github_cli_installed: true,
        github_authentication: 'authenticated',
        findings: [RAW_FINDING_CANARY],
      },
    },
  }
}

function context(doctor: DoctorResponse): AuthContextValue {
  return {
    api: { get: vi.fn(async () => doctor) } as unknown as ApiClient,
    auth: null,
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

describe('useDoctor safe view projection', () => {
  it('keeps only an allowlisted Doctor view and strict finding codes', () => {
    const projected = projectDoctorResponse(response())

    expect(projected).toEqual({
      data: expect.objectContaining({
        codex: expect.objectContaining({
          findings: ['CODEX_NOT_INSTALLED', 'RUNTIME_UNAVAILABLE'],
        }),
        projects: expect.objectContaining({ findings: [] }),
      }),
    })
    expect(JSON.stringify(projected)).not.toContain(RAW_FINDING_CANARY)
    expect(JSON.stringify(projected)).not.toContain('request_id')
    expect(JSON.stringify(projected)).not.toContain('api_version')
  })

  it('projects ApiError without reading or retaining its server message', () => {
    const canary = 'RC9 DOCTOR ERROR PROSE CANARY'
    let messageReads = 0
    const error = new ApiError({
      code: 'RC9_UNKNOWN_DOCTOR_FAILURE',
      message: canary,
      requestId: 'req_rc9_doctor_error',
      status: 503,
    })
    Object.defineProperty(error, 'message', {
      configurable: true,
      get: () => {
        messageReads += 1
        return canary
      },
    })

    const projected = projectDoctorError(error)

    expect(projected).toEqual({
      code: 'RC9_UNKNOWN_DOCTOR_FAILURE',
      requestId: 'req_rc9_doctor_error',
    })
    expect(JSON.stringify(projected)).not.toContain(canary)
    expect(messageReads).toBe(0)
  })

  it('stores only the projected Doctor view in hook state', async () => {
    const value = context(response())
    const wrapper = ({ children }: { children: ReactNode }) => (
      <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    )
    const { result } = renderHook(() => useDoctor(), { wrapper })

    await waitFor(() => expect(result.current.status).toBe('loaded'))
    expect(result.current).toMatchObject({
      status: 'loaded',
      response: {
        data: {
          codex: { findings: ['CODEX_NOT_INSTALLED', 'RUNTIME_UNAVAILABLE'] },
          projects: { findings: [] },
        },
      },
    })
    expect(JSON.stringify(result.current)).not.toContain(RAW_FINDING_CANARY)
  })
})
