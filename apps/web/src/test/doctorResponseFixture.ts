import type { DoctorResponse } from '../lib/contracts'

export function doctorResponse(): DoctorResponse {
  return {
    api_version: 'v1',
    request_id: 'req_admin_doctor_fixture',
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
        login_rate_limit: 12345,
        login_rate_window_seconds: 60,
        login_lock_duration_seconds: 73,
      },
      codex: {
        installed: true,
        version: '0.admin-fixture',
        installation_type: 'standalone',
        remote_control: 'supported',
        remote_state: 'stopped',
        findings: [],
      },
      claude: {
        installed: true,
        version: '1.admin-fixture',
        authentication: 'authenticated',
        remote_control: 'supported',
        tmux_installed: true,
        tmux_version: '3.admin-fixture',
        managed_sessions: 1234,
        unmanaged_sessions: 2,
        workspace_interaction_warnings: 1,
        findings: [],
      },
      projects: {
        project_root: '/Projects/admin-fixture',
        project_count: 7,
        git_installed: true,
        git_version: '2.admin-fixture',
        github_cli_installed: true,
        github_authentication: 'authenticated',
        findings: [],
      },
    },
  }
}
