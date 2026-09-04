import type { ApiError } from '../../lib/api'
import type { WorkspaceAction } from './useWorkspaceActions'
import type { WorkspaceStatusView } from './useWorkspaceStatus'

export type WorkspaceAgent = 'claude' | 'codex'
export type WorkspaceProjectChoice = { id: string; displayName: string }
export type WorkspaceStopTarget = { workspaceId: string; generation: string }
export type WorkspaceNotice =
  'START_CONFIRMED' | 'STOP_CONFIRMED' | 'RUNTIME_RECOVERY_REQUIRED'

/** Presentation model for metadata only. It cannot claim stream admission. */
export type WorkspacePageModel = {
  projects: WorkspaceProjectChoice[]
  projectsLoading: boolean
  projectError: string | null
  selectedProjectId: string
  agentType: WorkspaceAgent
  lookup: 'idle' | 'loading' | 'unregistered' | 'ready' | 'error'
  workspaceId: string | null
  generation: string | null
  lifecycleState: string | null
  reconciliationState: string | null
  runtimeView: WorkspaceStatusView
  pending: WorkspaceAction | null
  error: ApiError | null
  notice: WorkspaceNotice | null
  canStart: boolean
  canStop: boolean
  stopTarget: WorkspaceStopTarget | null
  selectProject: (projectId: string) => void
  selectAgent: (agent: WorkspaceAgent) => void
  refresh: () => Promise<void>
  start: () => Promise<void>
  requestStop: () => void
  cancelStop: () => void
  confirmStop: () => Promise<void>
}
