export type AdminView = {
  id: string
  username: string
}

export type AuthData = {
  user: AdminView
  session: { id: string; expires_at: string }
  csrf_token: string
}

export type AuthEnvelope = {
  api_version: 'v1'
  request_id: string
  data: AuthData
}

export type HealthResponse = { status: 'ok' }

export type ReadinessResponse = {
  status: 'ready' | 'not_ready'
  checks: { database: boolean; migrations: boolean }
}

export type MetaResponse = {
  name: 'AgentBox'
  version: string
  api_version: 'v1'
  environment: 'development' | 'test' | 'production'
}

export type DoctorResponse = {
  api_version: 'v1'
  request_id: string
  data: {
    status: 'ready' | 'not_ready'
    checks: {
      configuration_valid: boolean
      database_reachable: boolean
      migrations_current: boolean
      admin_initialized: boolean
      control_plane_ready: boolean
    }
    policy: {
      environment: 'development' | 'test' | 'production'
      bind_host: string
      bind_port: number
      session_ttl_seconds: number
      session_idle_ttl_seconds: number
      login_rate_limit: number
      login_rate_window_seconds: number
      login_lock_duration_seconds: number
    }
    codex: {
      installed: boolean | null
      version: string | null
      installation_type: 'standalone' | 'npm' | 'conflict' | 'unknown'
      remote_control: CapabilityState
      remote_state: RemoteState
      findings: string[]
    }
    claude: {
      installed: boolean | null
      version: string | null
      authentication: AuthenticationState
      remote_control: CapabilityState
      tmux_installed: boolean | null
      tmux_version: string | null
      managed_sessions: number
      unmanaged_sessions: number
      workspace_interaction_warnings: number
      findings: string[]
    }
    projects: {
      project_root: string
      project_count: number
      git_installed: boolean | null
      git_version: string | null
      github_cli_installed: boolean | null
      github_authentication: AuthenticationState
      findings: string[]
    }
  }
}

export type CapabilityState = 'supported' | 'unsupported' | 'unknown'
export type RemoteState = 'running' | 'stopped' | 'broken' | 'unknown'
export type AuthenticationState =
  'authenticated' | 'unauthenticated' | 'unknown'
export type ClaudeSessionState =
  | 'running'
  | 'stopped'
  | 'starting'
  | 'needs_interaction'
  | 'broken'
  | 'unknown'

export type CodexStatusData = {
  installed: boolean
  version: string | null
  selected_executable: string | null
  alternatives: string[]
  installation_type: 'standalone' | 'npm' | 'conflict' | 'unknown'
  conflict_detected: boolean
  authentication: 'authenticated' | 'unauthenticated' | 'unknown'
  capabilities: {
    remote_control: CapabilityState
    start: CapabilityState
    stop: CapabilityState
    pair: CapabilityState
    status: CapabilityState
  }
  remote_state: RemoteState
  remote_confidence: 'reported' | 'inferred' | 'unknown'
  diagnostics: Array<{
    code: string
    severity: 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info'
    summary: string
    remediation: string | null
  }>
}

export type CodexStatusResponse = {
  api_version: 'v1'
  request_id: string
  data: CodexStatusData
}

export type CodexRemoteActionResponse = {
  api_version: 'v1'
  request_id: string
  data: {
    outcome: 'started' | 'stopped' | 'already_running' | 'already_stopped'
    remote_state: RemoteState
  }
}

export type CodexPairResponse = {
  api_version: 'v1'
  request_id: string
  data: { pair_code: string; expires_at: string | null; display_once: true }
}

export type ClaudeStatusData = {
  installed: boolean
  version: string | null
  authentication: AuthenticationState
  capabilities: {
    remote_control: CapabilityState
    remote_start: CapabilityState
    version: CapabilityState
  }
  tmux_installed: boolean
  tmux_version: string | null
  managed_sessions: number
  unmanaged_sessions: number
  workspace_interaction_warnings: number
  diagnostics: Array<{
    code: string
    severity: 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info'
    summary: string
    remediation: string | null
  }>
}

export type ClaudeStatusResponse = {
  api_version: 'v1'
  request_id: string
  data: ClaudeStatusData
}

export type ClaudeSessionData = {
  project_id: string
  display_name: string
  state: ClaudeSessionState
  managed: boolean
  session_name: string
  attach_command: string
  workspace_state:
    'unknown' | 'requires_user_confirmation' | 'initialized_by_agentbox'
  tmux_running: boolean
  remote_readiness: 'ready' | 'unknown'
}

export type ClaudeSessionListResponse = {
  api_version: 'v1'
  request_id: string
  data: { sessions: ClaudeSessionData[] }
}

export type ClaudeSessionActionResponse = {
  api_version: 'v1'
  request_id: string
  data: {
    outcome: 'started' | 'stopped' | 'already_running' | 'already_stopped'
    session: ClaudeSessionData
  }
}

export type ClaudeSessionResponse = {
  api_version: 'v1'
  request_id: string
  data: ClaudeSessionData
}

export type ClaudeSessionOutputResponse = {
  api_version: 'v1'
  request_id: string
  data: {
    project_id: string
    session_name: string
    output: string
    truncated: boolean
    sensitive: true
  }
}

export type WorkspaceRuntimeStatus = {
  workspace_id: string
  project_id: string
  agent_type: 'claude' | 'codex'
  generation: string
  binding_revision: string
  binding_digest: string
  state: string
  reconciliation_state: string
  runtime_epoch: string
  process_state: string
  exit_code: number | null
  attachment_capacity: {
    admitted: string
    pending: string
    limit: string
  }
}

export type WorkspaceRuntimeStatusResponse = {
  request_id: string
  data: WorkspaceRuntimeStatus
}

export type WorkspaceStartResponse = {
  request_id: string
  workspace_id: string
  project_id: string
  agent_type: 'claude'
  state: string
  generation: string
}

export type WorkspaceStopResponse = WorkspaceStartResponse & {
  stop_operation_id: string
}

export type WorkspaceAttachmentTicketResponse = {
  protocol_version: 1
  request_id: string
  ticket: string
  workspace_id: string
  project_id: string
  agent_type: 'claude'
  attachment_id: string
  mode: 'writer'
  lease_number: string
  generation: string
  binding_revision: string
  binding_digest: string
  auth_epoch: string
  api_authority_epoch: string
  runtime_host_installation_id: string
  runtime_host_installation_revision: string
  runtime_epoch: string
  expires_at: string
}

export type WorkspaceDetachResponse = {
  request_id: string
  detach_operation_id: string
  workspace_id: string
  attachment_id: string
  generation: string
  lease_number: string
  result: 'detached' | 'already_detached'
  cleanup_state: 'ATTACH_PTY_CLOSED'
  state: string
}

export type GitStatusData = {
  is_repository: boolean
  branch: string | null
  detached_head: boolean
  unborn_branch: boolean
  upstream: string | null
  ahead: number
  behind: number
  staged_count: number
  unstaged_count: number
  untracked_count: number
  conflicted_count: number
  clean: boolean
  remote_url: string | null
  submodules_detected: boolean
}

export type ProjectData = {
  id: string
  slug: string
  display_name: string
  source_type: 'empty' | 'git_clone' | 'existing'
  state: 'creating' | 'ready' | 'error' | 'archived'
  repository_url: string | null
  default_branch: string | null
  created_at: string
  updated_at: string
  git: GitStatusData | null
  github: {
    available: boolean
    repository: string | null
    pull_request_number: number | null
    pull_request_title: string | null
    pull_request_state: string | null
    pull_request_draft: boolean | null
    pull_request_url: string | null
    pull_request_base: string | null
    pull_request_head: string | null
    mergeability: string | null
    checks: 'pass' | 'fail' | 'pending' | 'unknown'
  } | null
  claude_state:
    | 'running'
    | 'stopped'
    | 'starting'
    | 'needs_interaction'
    | 'broken'
    | 'unknown'
    | null
}

export type ProjectListResponse = {
  api_version: 'v1'
  request_id: string
  data: { projects: ProjectData[] }
}

export type ProjectResponse = {
  api_version: 'v1'
  request_id: string
  data: ProjectData
}

export type ProjectJobResponse = {
  api_version: 'v1'
  request_id: string
  data: { project: ProjectData; job: Pick<JobData, 'id' | 'status'> }
}

export type GitBranchData = { name: string; current: boolean }

export type GitBranchListResponse = {
  api_version: 'v1'
  request_id: string
  data: { branches: GitBranchData[] }
}

export type JobData = {
  id: string
  type: string
  status:
    | 'queued'
    | 'running'
    | 'succeeded'
    | 'failed'
    | 'cancelled'
    | 'needs_attention'
  target_type: string
  target_id: string | null
  project_id: string | null
  progress: number | null
  phase: string | null
  result_summary: string | null
  error_code: string | null
  error_summary: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type JobResponse = {
  api_version: 'v1'
  request_id: string
  data: JobData
}

type JsonObject = Record<string, unknown>

function object(value: unknown, context: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`Invalid ${context} response`)
  }
  return value as JsonObject
}

function string(value: unknown, context: string): string {
  if (typeof value !== 'string') throw new Error(`Invalid ${context} response`)
  return value
}

function boolean(value: unknown, context: string): boolean {
  if (typeof value !== 'boolean') throw new Error(`Invalid ${context} response`)
  return value
}

function number(value: unknown, context: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Invalid ${context} response`)
  }
  return value
}

function nullableString(value: unknown, context: string): string | null {
  if (value === null) return null
  return string(value, context)
}

function nullableBoolean(value: unknown, context: string): boolean | null {
  if (value === null) return null
  return boolean(value, context)
}

function nullableNumber(value: unknown, context: string): number | null {
  if (value === null) return null
  return number(value, context)
}

function array(value: unknown, context: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`Invalid ${context} response`)
  return value
}

function literal<T extends string>(
  value: unknown,
  values: readonly T[],
  context: string,
): T {
  if (typeof value !== 'string' || !values.includes(value as T)) {
    throw new Error(`Invalid ${context} response`)
  }
  return value as T
}

export function parseAuthEnvelope(value: unknown): AuthEnvelope {
  const envelope = object(value, 'authentication')
  const data = object(envelope.data, 'authentication data')
  const user = object(data.user, 'administrator')
  const session = object(data.session, 'session')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      user: {
        id: string(user.id, 'administrator ID'),
        username: string(user.username, 'administrator username'),
      },
      session: {
        id: string(session.id, 'session ID'),
        expires_at: string(session.expires_at, 'session expiry'),
      },
      csrf_token: string(data.csrf_token, 'CSRF token'),
    },
  }
}

export function parseHealthResponse(value: unknown): HealthResponse {
  const response = object(value, 'health')
  return { status: literal(response.status, ['ok'], 'health status') }
}

export function parseReadinessResponse(value: unknown): ReadinessResponse {
  const response = object(value, 'readiness')
  const checks = object(response.checks, 'readiness checks')
  return {
    status: literal(
      response.status,
      ['ready', 'not_ready'],
      'readiness status',
    ),
    checks: {
      database: boolean(checks.database, 'database readiness'),
      migrations: boolean(checks.migrations, 'migration readiness'),
    },
  }
}

export function parseMetaResponse(value: unknown): MetaResponse {
  const response = object(value, 'metadata')
  return {
    name: literal(response.name, ['AgentBox'], 'application name'),
    version: string(response.version, 'application version'),
    api_version: literal(response.api_version, ['v1'], 'API version'),
    environment: literal(
      response.environment,
      ['development', 'test', 'production'],
      'environment',
    ),
  }
}

export function parseDoctorResponse(value: unknown): DoctorResponse {
  const response = object(value, 'Doctor')
  const data = object(response.data, 'Doctor data')
  const checks = object(data.checks, 'Doctor checks')
  const policy = object(data.policy, 'Doctor policy')
  const codex = object(data.codex, 'Doctor Codex summary')
  const claude = object(data.claude, 'Doctor Claude summary')
  const projects = object(data.projects, 'Doctor Project summary')
  return {
    api_version: literal(response.api_version, ['v1'], 'API version'),
    request_id: string(response.request_id, 'request ID'),
    data: {
      status: literal(data.status, ['ready', 'not_ready'], 'Doctor status'),
      checks: {
        configuration_valid: boolean(
          checks.configuration_valid,
          'configuration check',
        ),
        database_reachable: boolean(
          checks.database_reachable,
          'database check',
        ),
        migrations_current: boolean(
          checks.migrations_current,
          'migration check',
        ),
        admin_initialized: boolean(
          checks.admin_initialized,
          'administrator check',
        ),
        control_plane_ready: boolean(
          checks.control_plane_ready,
          'control-plane check',
        ),
      },
      policy: {
        environment: literal(
          policy.environment,
          ['development', 'test', 'production'],
          'environment',
        ),
        bind_host: string(policy.bind_host, 'bind host'),
        bind_port: number(policy.bind_port, 'bind port'),
        session_ttl_seconds: number(
          policy.session_ttl_seconds,
          'session lifetime',
        ),
        session_idle_ttl_seconds: number(
          policy.session_idle_ttl_seconds,
          'idle session lifetime',
        ),
        login_rate_limit: number(policy.login_rate_limit, 'login rate limit'),
        login_rate_window_seconds: number(
          policy.login_rate_window_seconds,
          'login rate window',
        ),
        login_lock_duration_seconds: number(
          policy.login_lock_duration_seconds,
          'login lock duration',
        ),
      },
      codex: {
        installed: nullableBoolean(codex.installed, 'Codex installation'),
        version: nullableString(codex.version, 'Codex version'),
        installation_type: literal(
          codex.installation_type,
          ['standalone', 'npm', 'conflict', 'unknown'],
          'Codex installation type',
        ),
        remote_control: literal(
          codex.remote_control,
          ['supported', 'unsupported', 'unknown'],
          'Codex Remote capability',
        ),
        remote_state: literal(
          codex.remote_state,
          ['running', 'stopped', 'broken', 'unknown'],
          'Codex Remote state',
        ),
        findings: array(codex.findings, 'Codex findings').map((finding) =>
          string(finding, 'Codex finding'),
        ),
      },
      claude: {
        installed: nullableBoolean(claude.installed, 'Claude installation'),
        version: nullableString(claude.version, 'Claude version'),
        authentication: literal(
          claude.authentication,
          ['authenticated', 'unauthenticated', 'unknown'],
          'Claude authentication',
        ),
        remote_control: literal(
          claude.remote_control,
          ['supported', 'unsupported', 'unknown'],
          'Claude Remote capability',
        ),
        tmux_installed: nullableBoolean(
          claude.tmux_installed,
          'tmux installation',
        ),
        tmux_version: nullableString(claude.tmux_version, 'tmux version'),
        managed_sessions: number(
          claude.managed_sessions,
          'managed Claude sessions',
        ),
        unmanaged_sessions: number(
          claude.unmanaged_sessions,
          'unmanaged tmux sessions',
        ),
        workspace_interaction_warnings: number(
          claude.workspace_interaction_warnings,
          'Workspace interaction warnings',
        ),
        findings: array(claude.findings, 'Claude findings').map((finding) =>
          string(finding, 'Claude finding'),
        ),
      },
      projects: {
        project_root: string(projects.project_root, 'Project Root'),
        project_count: number(projects.project_count, 'Project count'),
        git_installed: nullableBoolean(
          projects.git_installed,
          'Git installation',
        ),
        git_version: nullableString(projects.git_version, 'Git version'),
        github_cli_installed: nullableBoolean(
          projects.github_cli_installed,
          'GitHub CLI installation',
        ),
        github_authentication: literal(
          projects.github_authentication,
          ['authenticated', 'unauthenticated', 'unknown'],
          'GitHub authentication',
        ),
        findings: array(projects.findings, 'Project findings').map((finding) =>
          string(finding, 'Project finding'),
        ),
      },
    },
  }
}

export function parseCodexStatusResponse(value: unknown): CodexStatusResponse {
  const envelope = object(value, 'Codex status')
  const data = object(envelope.data, 'Codex status data')
  const capabilities = object(data.capabilities, 'Codex capabilities')
  const diagnostics = array(data.diagnostics, 'Codex diagnostics').map(
    (raw): CodexStatusData['diagnostics'][number] => {
      const item = object(raw, 'Codex diagnostic')
      return {
        code: string(item.code, 'Codex diagnostic code'),
        severity: literal(
          item.severity,
          ['critical', 'high', 'medium', 'low', 'warning', 'info'],
          'Codex diagnostic severity',
        ),
        summary: string(item.summary, 'Codex diagnostic summary'),
        remediation: nullableString(
          item.remediation,
          'Codex diagnostic remediation',
        ),
      }
    },
  )
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      installed: boolean(data.installed, 'Codex installation'),
      version: nullableString(data.version, 'Codex version'),
      selected_executable: nullableString(
        data.selected_executable,
        'Codex executable',
      ),
      alternatives: array(data.alternatives, 'Codex alternatives').map(
        (entry) => string(entry, 'Codex alternative'),
      ),
      installation_type: literal(
        data.installation_type,
        ['standalone', 'npm', 'conflict', 'unknown'],
        'Codex installation type',
      ),
      conflict_detected: boolean(data.conflict_detected, 'Codex conflict'),
      authentication: literal(
        data.authentication,
        ['authenticated', 'unauthenticated', 'unknown'],
        'Codex authentication',
      ),
      capabilities: {
        remote_control: literal(
          capabilities.remote_control,
          ['supported', 'unsupported', 'unknown'],
          'Remote Control capability',
        ),
        start: literal(
          capabilities.start,
          ['supported', 'unsupported', 'unknown'],
          'start capability',
        ),
        stop: literal(
          capabilities.stop,
          ['supported', 'unsupported', 'unknown'],
          'stop capability',
        ),
        pair: literal(
          capabilities.pair,
          ['supported', 'unsupported', 'unknown'],
          'pair capability',
        ),
        status: literal(
          capabilities.status,
          ['supported', 'unsupported', 'unknown'],
          'status capability',
        ),
      },
      remote_state: literal(
        data.remote_state,
        ['running', 'stopped', 'broken', 'unknown'],
        'Remote state',
      ),
      remote_confidence: literal(
        data.remote_confidence,
        ['reported', 'inferred', 'unknown'],
        'Remote confidence',
      ),
      diagnostics,
    },
  }
}

export function parseCodexRemoteActionResponse(
  value: unknown,
): CodexRemoteActionResponse {
  const envelope = object(value, 'Codex Remote action')
  const data = object(envelope.data, 'Codex Remote action data')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      outcome: literal(
        data.outcome,
        ['started', 'stopped', 'already_running', 'already_stopped'],
        'Codex Remote outcome',
      ),
      remote_state: literal(
        data.remote_state,
        ['running', 'stopped', 'broken', 'unknown'],
        'Codex Remote state',
      ),
    },
  }
}

export function parseCodexPairResponse(value: unknown): CodexPairResponse {
  const envelope = object(value, 'Codex pair')
  const data = object(envelope.data, 'Codex pair data')
  if (data.display_once !== true) {
    throw new Error('Invalid display-once response')
  }
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      pair_code: string(data.pair_code, 'Pair Code'),
      expires_at: nullableString(data.expires_at, 'Pair expiry'),
      display_once: true,
    },
  }
}

function parseClaudeSession(value: unknown): ClaudeSessionData {
  const session = object(value, 'Claude session')
  return {
    project_id: string(session.project_id, 'Claude project ID'),
    display_name: string(session.display_name, 'Claude project display name'),
    state: literal(
      session.state,
      [
        'running',
        'stopped',
        'starting',
        'needs_interaction',
        'broken',
        'unknown',
      ],
      'Claude session state',
    ),
    managed: boolean(session.managed, 'Claude managed state'),
    session_name: string(session.session_name, 'Claude session name'),
    attach_command: string(session.attach_command, 'Claude attach command'),
    workspace_state: literal(
      session.workspace_state,
      ['unknown', 'requires_user_confirmation', 'initialized_by_agentbox'],
      'Claude Workspace state',
    ),
    tmux_running: boolean(session.tmux_running, 'Claude tmux state'),
    remote_readiness: literal(
      session.remote_readiness,
      ['ready', 'unknown'],
      'Claude Remote readiness',
    ),
  }
}

export function parseClaudeStatusResponse(
  value: unknown,
): ClaudeStatusResponse {
  const envelope = object(value, 'Claude status')
  const data = object(envelope.data, 'Claude status data')
  const capabilities = object(data.capabilities, 'Claude capabilities')
  const diagnostics = array(data.diagnostics, 'Claude diagnostics').map(
    (raw): ClaudeStatusData['diagnostics'][number] => {
      const finding = object(raw, 'Claude diagnostic')
      return {
        code: string(finding.code, 'Claude diagnostic code'),
        severity: literal(
          finding.severity,
          ['critical', 'high', 'medium', 'low', 'warning', 'info'],
          'Claude diagnostic severity',
        ),
        summary: string(finding.summary, 'Claude diagnostic summary'),
        remediation: nullableString(
          finding.remediation,
          'Claude diagnostic remediation',
        ),
      }
    },
  )
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      installed: boolean(data.installed, 'Claude installation'),
      version: nullableString(data.version, 'Claude version'),
      authentication: literal(
        data.authentication,
        ['authenticated', 'unauthenticated', 'unknown'],
        'Claude authentication',
      ),
      capabilities: {
        remote_control: literal(
          capabilities.remote_control,
          ['supported', 'unsupported', 'unknown'],
          'Claude Remote capability',
        ),
        remote_start: literal(
          capabilities.remote_start,
          ['supported', 'unsupported', 'unknown'],
          'Claude Remote start capability',
        ),
        version: literal(
          capabilities.version,
          ['supported', 'unsupported', 'unknown'],
          'Claude version capability',
        ),
      },
      tmux_installed: boolean(data.tmux_installed, 'tmux installation'),
      tmux_version: nullableString(data.tmux_version, 'tmux version'),
      managed_sessions: number(data.managed_sessions, 'managed sessions'),
      unmanaged_sessions: number(data.unmanaged_sessions, 'unmanaged sessions'),
      workspace_interaction_warnings: number(
        data.workspace_interaction_warnings,
        'Workspace interaction warnings',
      ),
      diagnostics,
    },
  }
}

export function parseClaudeSessionListResponse(
  value: unknown,
): ClaudeSessionListResponse {
  const envelope = object(value, 'Claude session list')
  const data = object(envelope.data, 'Claude session list data')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      sessions: array(data.sessions, 'Claude sessions').map(parseClaudeSession),
    },
  }
}

export function parseClaudeSessionResponse(
  value: unknown,
): ClaudeSessionResponse {
  const envelope = object(value, 'Claude session')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: parseClaudeSession(envelope.data),
  }
}

export function parseClaudeSessionActionResponse(
  value: unknown,
): ClaudeSessionActionResponse {
  const envelope = object(value, 'Claude session action')
  const data = object(envelope.data, 'Claude session action data')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      outcome: literal(
        data.outcome,
        ['started', 'stopped', 'already_running', 'already_stopped'],
        'Claude session action outcome',
      ),
      session: parseClaudeSession(data.session),
    },
  }
}

export function parseClaudeSessionOutputResponse(
  value: unknown,
): ClaudeSessionOutputResponse {
  const envelope = object(value, 'Claude session output')
  const data = object(envelope.data, 'Claude session output data')
  if (data.sensitive !== true) {
    throw new Error('Invalid Claude output sensitivity marker')
  }
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      project_id: string(data.project_id, 'Claude output project ID'),
      session_name: string(data.session_name, 'Claude output session name'),
      output: string(data.output, 'Claude output'),
      truncated: boolean(data.truncated, 'Claude output truncation'),
      sensitive: true,
    },
  }
}

export function parseWorkspaceRuntimeStatusResponse(
  value: unknown,
): WorkspaceRuntimeStatusResponse {
  const envelope = object(value, 'Workspace runtime status')
  const data = object(envelope.data, 'Workspace runtime status data')
  const capacity = object(
    data.attachment_capacity,
    'Workspace attachment capacity',
  )
  for (const forbidden of ['terminal', 'terminal_output', 'ticket']) {
    if (forbidden in data || forbidden in capacity) {
      throw new Error(`Invalid Workspace runtime status response`)
    }
  }
  return {
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      workspace_id: string(data.workspace_id, 'workspace ID'),
      project_id: string(data.project_id, 'Project ID'),
      agent_type: literal(data.agent_type, ['claude', 'codex'], 'AgentType'),
      generation: string(data.generation, 'workspace generation'),
      binding_revision: string(data.binding_revision, 'binding revision'),
      binding_digest: string(data.binding_digest, 'binding digest'),
      state: string(data.state, 'workspace state'),
      reconciliation_state: string(
        data.reconciliation_state,
        'reconciliation state',
      ),
      runtime_epoch: string(data.runtime_epoch, 'Runtime epoch'),
      process_state: string(data.process_state, 'process state'),
      exit_code: nullableNumber(data.exit_code, 'exit code'),
      attachment_capacity: {
        admitted: string(capacity.admitted, 'admitted attachment count'),
        pending: string(capacity.pending, 'pending attachment count'),
        limit: string(capacity.limit, 'attachment limit'),
      },
    },
  }
}

export function parseWorkspaceStartResponse(value: unknown): WorkspaceStartResponse {
  const data = object(value, 'Workspace start')
  return {
    request_id: string(data.request_id, 'request ID'),
    workspace_id: string(data.workspace_id, 'workspace ID'),
    project_id: string(data.project_id, 'Project ID'),
    agent_type: literal(data.agent_type, ['claude'], 'AgentType'),
    state: string(data.state, 'workspace state'),
    generation: string(data.generation, 'workspace generation'),
  }
}

export function parseWorkspaceStopResponse(value: unknown): WorkspaceStopResponse {
  const data = parseWorkspaceStartResponse(value)
  const envelope = object(value, 'Workspace stop')
  return { ...data, stop_operation_id: string(envelope.stop_operation_id, 'stop operation ID') }
}

export function parseWorkspaceAttachmentTicketResponse(value: unknown): WorkspaceAttachmentTicketResponse {
  const data = object(value, 'Workspace attachment ticket')
  return {
    protocol_version: data.protocol_version === 1 ? 1 : (() => { throw new Error('Invalid protocol version response') })(),
    request_id: string(data.request_id, 'request ID'),
    ticket: string(data.ticket, 'attachment ticket'),
    workspace_id: string(data.workspace_id, 'workspace ID'),
    project_id: string(data.project_id, 'Project ID'),
    agent_type: literal(data.agent_type, ['claude'], 'AgentType'),
    attachment_id: string(data.attachment_id, 'attachment ID'),
    mode: literal(data.mode, ['writer'], 'attachment mode'),
    lease_number: string(data.lease_number, 'lease number'),
    generation: string(data.generation, 'workspace generation'),
    binding_revision: string(data.binding_revision, 'binding revision'),
    binding_digest: string(data.binding_digest, 'binding digest'),
    auth_epoch: string(data.auth_epoch, 'auth epoch'),
    api_authority_epoch: string(data.api_authority_epoch, 'API authority epoch'),
    runtime_host_installation_id: string(data.runtime_host_installation_id, 'Runtime host installation ID'),
    runtime_host_installation_revision: string(data.runtime_host_installation_revision, 'Runtime host installation revision'),
    runtime_epoch: string(data.runtime_epoch, 'Runtime epoch'),
    expires_at: string(data.expires_at, 'ticket expiry'),
  }
}

export function parseWorkspaceDetachResponse(value: unknown): WorkspaceDetachResponse {
  const data = object(value, 'Workspace detach')
  return {
    request_id: string(data.request_id, 'request ID'),
    detach_operation_id: string(data.detach_operation_id, 'detach operation ID'),
    workspace_id: string(data.workspace_id, 'workspace ID'),
    attachment_id: string(data.attachment_id, 'attachment ID'),
    generation: string(data.generation, 'workspace generation'),
    lease_number: string(data.lease_number, 'lease number'),
    result: literal(data.result, ['detached', 'already_detached'], 'detach result'),
    cleanup_state: literal(data.cleanup_state, ['ATTACH_PTY_CLOSED'], 'cleanup state'),
    state: string(data.state, 'workspace state'),
  }
}

function parseGitStatus(value: unknown): GitStatusData {
  const data = object(value, 'Git status')
  return {
    is_repository: boolean(data.is_repository, 'repository state'),
    branch: nullableString(data.branch, 'branch'),
    detached_head: boolean(data.detached_head, 'detached HEAD'),
    unborn_branch: boolean(data.unborn_branch, 'unborn branch'),
    upstream: nullableString(data.upstream, 'upstream'),
    ahead: number(data.ahead, 'ahead count'),
    behind: number(data.behind, 'behind count'),
    staged_count: number(data.staged_count, 'staged count'),
    unstaged_count: number(data.unstaged_count, 'unstaged count'),
    untracked_count: number(data.untracked_count, 'untracked count'),
    conflicted_count: number(data.conflicted_count, 'conflict count'),
    clean: boolean(data.clean, 'clean state'),
    remote_url: nullableString(data.remote_url, 'remote URL'),
    submodules_detected: boolean(data.submodules_detected, 'submodule state'),
  }
}

function parseProject(value: unknown): ProjectData {
  const data = object(value, 'Project')
  return {
    id: string(data.id, 'Project ID'),
    slug: string(data.slug, 'Project slug'),
    display_name: string(data.display_name, 'Project name'),
    source_type: literal(
      data.source_type,
      ['empty', 'git_clone', 'existing'],
      'source type',
    ),
    state: literal(
      data.state,
      ['creating', 'ready', 'error', 'archived'],
      'Project state',
    ),
    repository_url: nullableString(data.repository_url, 'repository URL'),
    default_branch: nullableString(data.default_branch, 'default branch'),
    created_at: string(data.created_at, 'created time'),
    updated_at: string(data.updated_at, 'updated time'),
    git: data.git === null ? null : parseGitStatus(data.git),
    github: parseGitHubProject(data.github),
    claude_state:
      data.claude_state === null
        ? null
        : literal(
            data.claude_state,
            [
              'running',
              'stopped',
              'starting',
              'needs_interaction',
              'broken',
              'unknown',
            ] as const,
            'Claude Project state',
          ),
  }
}

function parseGitHubProject(value: unknown): ProjectData['github'] {
  if (value === null) return null
  const data = object(value, 'GitHub status')
  return {
    available: boolean(data.available, 'GitHub availability'),
    repository: nullableString(data.repository, 'GitHub repository'),
    pull_request_number: nullableNumber(
      data.pull_request_number,
      'pull request number',
    ),
    pull_request_title: nullableString(
      data.pull_request_title,
      'pull request title',
    ),
    pull_request_state: nullableString(
      data.pull_request_state,
      'pull request state',
    ),
    pull_request_draft: nullableBoolean(
      data.pull_request_draft,
      'pull request draft',
    ),
    pull_request_url: nullableString(data.pull_request_url, 'pull request URL'),
    pull_request_base: nullableString(
      data.pull_request_base,
      'pull request base',
    ),
    pull_request_head: nullableString(
      data.pull_request_head,
      'pull request head',
    ),
    mergeability: nullableString(
      data.mergeability,
      'pull request mergeability',
    ),
    checks: literal(
      data.checks,
      ['pass', 'fail', 'pending', 'unknown'],
      'check status',
    ),
  }
}

export function parseProjectListResponse(value: unknown): ProjectListResponse {
  const envelope = object(value, 'Projects')
  const data = object(envelope.data, 'Project list')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: { projects: array(data.projects, 'Projects').map(parseProject) },
  }
}

export function parseProjectResponse(value: unknown): ProjectResponse {
  const envelope = object(value, 'Project')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: parseProject(envelope.data),
  }
}

export function parseProjectJobResponse(value: unknown): ProjectJobResponse {
  const envelope = object(value, 'Project Job')
  const data = object(envelope.data, 'Project Job data')
  const job = object(data.job, 'Job')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      project: parseProject(data.project),
      job: {
        id: string(job.id, 'Job ID'),
        status: literal(
          job.status,
          [
            'queued',
            'running',
            'succeeded',
            'failed',
            'cancelled',
            'needs_attention',
          ],
          'Job status',
        ),
      },
    },
  }
}

export function parseGitBranchListResponse(
  value: unknown,
): GitBranchListResponse {
  const envelope = object(value, 'Git branches')
  const data = object(envelope.data, 'Git branch list')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: {
      branches: array(data.branches, 'Git branches').map((value) => {
        const branch = object(value, 'Git branch')
        return {
          name: string(branch.name, 'Git branch name'),
          current: boolean(branch.current, 'current Git branch'),
        }
      }),
    },
  }
}

function parseJob(value: unknown): JobData {
  const data = object(value, 'Job')
  return {
    id: string(data.id, 'Job ID'),
    type: string(data.type, 'Job type'),
    status: literal(
      data.status,
      [
        'queued',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'needs_attention',
      ],
      'Job status',
    ),
    target_type: string(data.target_type, 'Job target type'),
    target_id: nullableString(data.target_id, 'Job target ID'),
    project_id: nullableString(data.project_id, 'Job Project ID'),
    progress: nullableNumber(data.progress, 'Job progress'),
    phase: nullableString(data.phase, 'Job phase'),
    result_summary: nullableString(data.result_summary, 'Job result'),
    error_code: nullableString(data.error_code, 'Job error code'),
    error_summary: nullableString(data.error_summary, 'Job error summary'),
    created_at: string(data.created_at, 'Job creation time'),
    started_at: nullableString(data.started_at, 'Job start time'),
    finished_at: nullableString(data.finished_at, 'Job finish time'),
  }
}

export function parseJobResponse(value: unknown): JobResponse {
  const envelope = object(value, 'Job')
  return {
    api_version: literal(envelope.api_version, ['v1'], 'API version'),
    request_id: string(envelope.request_id, 'request ID'),
    data: parseJob(envelope.data),
  }
}
