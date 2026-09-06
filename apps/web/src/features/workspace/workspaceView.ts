import type { WorkspaceAction } from './useWorkspaceActions'
import type { WorkspaceStatusView } from './useWorkspaceStatus'
import type { WAWAttachmentView } from './useWAWBrowserAttachment'

export type WorkspaceAgent = 'claude' | 'codex'
export type WorkspaceProjectChoice = { id: string; displayName: string }
export type WorkspaceProjectError = Readonly<{
  code: string
  requestId?: string
}>
export type WorkspaceApiErrorView = Readonly<{
  code: string
  requestId?: string
  retryAfter?: number
}>
export type WorkspaceStopTarget = { workspaceId: string; generation: string }
export type WorkspaceNotice =
  'START_CONFIRMED' | 'STOP_CONFIRMED' | 'RUNTIME_RECOVERY_REQUIRED'

/** Presentation model for metadata only. It cannot claim stream admission. */
export type WorkspacePageModel = {
  projects: WorkspaceProjectChoice[]
  projectsLoading: boolean
  projectError: WorkspaceProjectError | null
  selectedProjectId: string
  agentType: WorkspaceAgent
  lookup: 'idle' | 'loading' | 'unregistered' | 'ready' | 'error'
  workspaceId: string | null
  generation: string | null
  lifecycleState: string | null
  reconciliationState: string | null
  runtimeView: WorkspaceStatusView
  attachment: WAWAttachmentView
  pending: WorkspaceAction | null
  error: WorkspaceApiErrorView | null
  notice: WorkspaceNotice | null
  canStart: boolean
  canStop: boolean
  canConnect: boolean
  canReconnect: boolean
  canDetach: boolean
  canInput: boolean
  canResize: boolean
  stopTarget: WorkspaceStopTarget | null
  selectProject: (projectId: string) => void
  selectAgent: (agent: WorkspaceAgent) => void
  refresh: () => Promise<void>
  start: () => Promise<void>
  requestStop: () => void
  cancelStop: () => void
  confirmStop: () => Promise<void>
  setTerminalSurface: (surface: HTMLElement | null) => void
  setTerminalViewport: (viewport: HTMLElement | null) => void
  setTerminalInputClearer: (clearer: (() => void) | null) => void
  connect: () => Promise<void>
  reconnect: () => Promise<void>
  detach: () => Promise<void>
  sendInput: (text: string) => Promise<void>
}

const SAFE_ERROR_CODE = /^[A-Z][A-Z0-9_]{0,79}$/
const SAFE_REQUEST_ID = /^[A-Za-z0-9._:-]{1,72}$/
const MAX_RETRY_AFTER_SECONDS = 86_400

function ownDataProperty(value: unknown, key: string): unknown {
  if (
    (typeof value !== 'object' && typeof value !== 'function') ||
    value === null
  ) {
    return undefined
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key)
  return descriptor && 'value' in descriptor ? descriptor.value : undefined
}

/**
 * Projects an error to bounded machine evidence without touching Error.message
 * or invoking accessors supplied by an upstream failure object.
 */
export function workspaceApiError(
  value: unknown,
  fallbackCode: string,
): WorkspaceApiErrorView {
  const rawCode = ownDataProperty(value, 'code')
  const code =
    typeof rawCode === 'string' && SAFE_ERROR_CODE.test(rawCode)
      ? rawCode
      : fallbackCode
  const rawRequestId = ownDataProperty(value, 'requestId')
  const requestId =
    typeof rawRequestId === 'string' && SAFE_REQUEST_ID.test(rawRequestId)
      ? rawRequestId
      : undefined
  const rawRetryAfter = ownDataProperty(value, 'retryAfter')
  const retryAfter =
    typeof rawRetryAfter === 'number' &&
    Number.isInteger(rawRetryAfter) &&
    rawRetryAfter > 0 &&
    rawRetryAfter <= MAX_RETRY_AFTER_SECONDS
      ? rawRetryAfter
      : undefined

  return Object.freeze({
    code,
    ...(requestId === undefined ? {} : { requestId }),
    ...(retryAfter === undefined ? {} : { retryAfter }),
  })
}

export function workspaceError(code: string): WorkspaceApiErrorView {
  return workspaceApiError({ code }, 'WAW_ACTION_FAILED')
}
