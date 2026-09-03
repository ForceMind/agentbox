import type { WorkspaceAgent } from './workspaceView'

export type WorkspaceMetadata = {
  id: string
  project_id: string
  agent_type: WorkspaceAgent
  state: string
  reconciliation_state: string
  generation: number
  revision: number
  created_at: string
  updated_at: string
  last_seen_at: string
  exit_code: number | null
  failure_code: string | null
}
export const isWorkspaceId = (value: string) => /^aws_[a-f0-9]{32}$/.test(value)
export const isProjectId = (value: string) => /^prj_[a-f0-9]{32}$/.test(value)
const states = [
  'STARTING',
  'RUNNING',
  'NEEDS_INTERACTION',
  'TRUST_REQUIRED',
  'LOGIN_REQUIRED',
  'STOPPING',
  'EXITED',
  'STOPPED',
  'MISSING',
  'COLLISION',
  'BROKEN',
  'UNKNOWN',
]
const reconciliationStates = [
  'authoritative',
  'stopping',
  'missing',
  'collision',
  'exited',
  'reconciliation_required',
  'unknown',
]
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).length !== keys.length ||
    Object.keys(value).some((key) => !keys.includes(key))
  )
    throw new Error('Invalid workspace metadata')
  return value as Record<string, unknown>
}
function text(value: unknown, max = 128): string {
  if (typeof value !== 'string' || !value || value.length > max)
    throw new Error('Invalid workspace metadata string')
  return value
}
function metadata(value: unknown): WorkspaceMetadata {
  const row = object(value, [
    'id',
    'project_id',
    'agent_type',
    'state',
    'reconciliation_state',
    'generation',
    'revision',
    'created_at',
    'updated_at',
    'last_seen_at',
    'exit_code',
    'failure_code',
  ])
  if (
    !isWorkspaceId(text(row.id)) ||
    !isProjectId(text(row.project_id)) ||
    !['claude', 'codex'].includes(text(row.agent_type)) ||
    !states.includes(text(row.state)) ||
    !reconciliationStates.includes(text(row.reconciliation_state)) ||
    !Number.isSafeInteger(row.generation) ||
    Number(row.generation) <= 0 ||
    !Number.isSafeInteger(row.revision) ||
    Number(row.revision) <= 0 ||
    (row.exit_code !== null && !Number.isSafeInteger(row.exit_code))
  )
    throw new Error('Invalid workspace metadata identity')
  for (const key of ['created_at', 'updated_at', 'last_seen_at']) {
    if (!Number.isFinite(Date.parse(text(row[key], 64))))
      throw new Error('Invalid workspace metadata time')
  }
  if (row.failure_code !== null) text(row.failure_code)
  return row as WorkspaceMetadata
}
export function parseWorkspaceList(
  value: unknown,
  projectId: string,
  agentType: WorkspaceAgent,
): WorkspaceMetadata | null {
  const envelope = object(value, ['request_id', 'data'])
  text(envelope.request_id)
  const data = object(envelope.data, ['workspaces'])
  if (!Array.isArray(data.workspaces) || data.workspaces.length > 1)
    throw new Error('Workspace lookup is not exact')
  const row = data.workspaces.length ? metadata(data.workspaces[0]) : null
  if (row && (row.project_id !== projectId || row.agent_type !== agentType))
    throw new Error('Workspace lookup identity mismatch')
  return row
}
export function parseWorkspaceMetadata(
  value: unknown,
  workspaceId: string,
): WorkspaceMetadata {
  const envelope = object(value, ['request_id', 'data'])
  text(envelope.request_id)
  const row = metadata(envelope.data)
  if (row.id !== workspaceId) throw new Error('Workspace identity mismatch')
  return row
}
