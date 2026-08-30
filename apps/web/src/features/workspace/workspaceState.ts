/**
 * Browser-only state for the Web Agent Workspace shell.
 *
 * This reducer deliberately has no transport or API dependencies.  In
 * particular, a successful HTTP response is not an admission signal: only an
 * explicit `admitted` event may move the UI to `connected`.
 */

export type WorkspaceStatus =
  | 'checking'
  | 'starting'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error'
  | 'stopping'
  | 'detached'
  | 'stopped'
  | 'gap'
  | 'input_uncertain'
  | 'login_required'
  | 'trust_required'
  | 'exited'
  | 'missing'
  | 'collision'
  | 'unavailable'

export type WorkspaceState = {
  status: WorkspaceStatus
  projectId: string | null
  workspaceId: string | null
  agentType: 'claude'
  errorCode: string | null
  message: string | null
}

export const initialWorkspaceState: WorkspaceState = {
  status: 'checking',
  projectId: null,
  workspaceId: null,
  agentType: 'claude',
  errorCode: null,
  message: null,
}

export type WorkspaceAction =
  | { type: 'checking' }
  | { type: 'start_requested'; projectId: string }
  | { type: 'start_accepted'; workspaceId: string; projectId: string }
  | { type: 'connecting' }
  | { type: 'admitted' }
  | { type: 'reconnect_requested' }
  | { type: 'detached' }
  | { type: 'stop_requested' }
  | { type: 'stopped' }
  | { type: 'gap'; message?: string }
  | { type: 'input_uncertain'; message?: string }
  | {
      type:
        | 'error'
        | 'login_required'
        | 'trust_required'
        | 'exited'
        | 'missing'
        | 'collision'
        | 'unavailable'
      message: string
      code?: string
    }

function withStatus(
  state: WorkspaceState,
  status: WorkspaceStatus,
  message: string | null = null,
  errorCode: string | null = null,
): WorkspaceState {
  return { ...state, status, message, errorCode }
}

export function workspaceReducer(
  state: WorkspaceState,
  action: WorkspaceAction,
): WorkspaceState {
  switch (action.type) {
    case 'checking':
      return withStatus(state, 'checking')
    case 'start_requested':
      return withStatus(
        { ...state, projectId: action.projectId, workspaceId: null },
        'starting',
      )
    case 'start_accepted':
      return withStatus(
        {
          ...state,
          projectId: action.projectId,
          workspaceId: action.workspaceId,
        },
        'connecting',
      )
    case 'connecting':
      return withStatus(state, 'connecting')
    case 'admitted':
      // `connected` is intentionally reachable only after Runtime admission.
      if (state.status !== 'connecting' && state.status !== 'reconnecting') {
        return state
      }
      return withStatus(state, 'connected')
    case 'reconnect_requested':
      return withStatus(state, 'reconnecting')
    case 'detached':
      return withStatus(state, 'detached')
    case 'stop_requested':
      return withStatus(state, 'stopping')
    case 'stopped':
      return withStatus(state, 'stopped')
    case 'gap':
      return withStatus(
        state,
        'gap',
        action.message ?? 'Output history has a bounded gap.',
      )
    case 'input_uncertain':
      return withStatus(
        state,
        'input_uncertain',
        action.message ??
          'Input delivery is uncertain; do not retry automatically.',
      )
    case 'error':
    case 'login_required':
    case 'trust_required':
    case 'exited':
    case 'missing':
    case 'collision':
    case 'unavailable':
      return withStatus(state, action.type, action.message, action.code ?? null)
    default:
      return state
  }
}
