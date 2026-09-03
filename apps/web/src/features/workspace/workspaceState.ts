/**
 * Memory-only UI reducer. Events must come from the future authenticated
 * transport/control adapter; tuple matching is not cryptographic admission.
 * No ticket, input bytes, transcript or automatic retry is stored here.
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

export type WorkspaceFence = Readonly<{
  projectId: string
  workspaceId: string
  agentType: 'claude' | 'codex'
  sessionId: string
  generation: string
  bindingRevision: string
  bindingDigest: string
  hostId: string
  hostRevision: string
  runtimeEpoch: string
  apiAuthorityEpoch: string
  sessionAuthEpoch: string
}>
export type AttachmentFence = Readonly<{
  attachmentId: string
  leaseNumber: string
}>
export type RuntimeEvent = Readonly<{
  fence: WorkspaceFence
  attachment: AttachmentFence
}>

export type WorkspaceState = {
  status: WorkspaceStatus
  projectId: string | null
  workspaceId: string | null
  agentType: 'claude' | 'codex'
  errorCode: string | null
  message: string | null
  // Optional only for static, non-interactive page fixtures.
  workspaceFence?: WorkspaceFence | null
  attachmentFence?: AttachmentFence | null
  cursor?: string | null
  requestSequence?: string
  startAttempt?: string | null
  connectionAttempt?: string | null
  stopAttempt?: string | null
  lastAttachment?: AttachmentFence | null
  recoveryRequired?: boolean
}
export const initialWorkspaceState: WorkspaceState = {
  status: 'checking',
  projectId: null,
  workspaceId: null,
  agentType: 'claude',
  errorCode: null,
  message: null,
  workspaceFence: null,
  attachmentFence: null,
  cursor: null,
  requestSequence: '0',
  startAttempt: null,
  connectionAttempt: null,
  stopAttempt: null,
  lastAttachment: null,
  recoveryRequired: false,
}

export type WorkspaceAction =
  | { type: 'checking' }
  | {
      type: 'start_requested'
      projectId: string
      agentType?: 'claude' | 'codex'
      attempt: string
    }
  | {
      type: 'start_accepted'
      projectId: string
      workspaceId: string
      attempt: string
      fence: WorkspaceFence
    }
  | { type: 'connecting' | 'reconnect_requested'; attempt: string }
  | { type: 'attachment_prepared'; attempt: string; event: RuntimeEvent }
  | { type: 'admitted' | 'detached' | 'input_uncertain'; event: RuntimeEvent }
  | { type: 'output_observed'; event: RuntimeEvent; cursor: string }
  | { type: 'gap'; event: RuntimeEvent; fromCursor: string; toCursor: string }
  | { type: 'stop_requested'; attempt: string }
  | { type: 'stopped'; attempt: string; fence: WorkspaceFence }
  | {
      type: 'api_restarted' | 'runtime_restarted' | 'recovery_reconciled'
      previous: WorkspaceFence
      next: WorkspaceFence
    }
  | { type: 'visibility_changed'; visible: boolean }
  | {
      type: 'request_failed'
      operation: 'start' | 'connect' | 'stop'
      attempt: string
      message: string
      code: string
    }
  | {
      type:
        | 'error'
        | 'login_required'
        | 'trust_required'
        | 'exited'
        | 'missing'
        | 'collision'
        | 'unavailable'
      event: RuntimeEvent
      message: string
      code?: string
    }

const MAX_UINT64 = 18446744073709551615n
const MAX_CURSOR = MAX_UINT64 - 1n
export function isCanonicalUint64(
  value: unknown,
  positive = false,
): value is string {
  return (
    typeof value === 'string' &&
    value.length <= 20 &&
    /^(0|[1-9][0-9]{0,19})$/.test(value) &&
    (!positive || value !== '0') &&
    BigInt(value) <= MAX_UINT64
  )
}
function validCursor(value: unknown): value is string {
  return isCanonicalUint64(value, true) && BigInt(value) <= MAX_CURSOR
}
const fenceKeys: readonly (keyof WorkspaceFence)[] = [
  'projectId',
  'workspaceId',
  'agentType',
  'sessionId',
  'generation',
  'bindingRevision',
  'bindingDigest',
  'hostId',
  'hostRevision',
  'runtimeEpoch',
  'apiAuthorityEpoch',
  'sessionAuthEpoch',
]
function validFence(fence: WorkspaceFence): boolean {
  return (
    !!fence &&
    /^prj_[a-f0-9]{32}$/.test(fence.projectId) &&
    /^aws_[a-f0-9]{32}$/.test(fence.workspaceId) &&
    /^wri_[a-f0-9]{32}$/.test(fence.hostId) &&
    /^[a-f0-9]{64}$/.test(fence.bindingDigest) &&
    (fence.agentType === 'claude' || fence.agentType === 'codex') &&
    typeof fence.sessionId === 'string' &&
    fence.sessionId.length > 0 &&
    fence.sessionId.length <= 128 &&
    !/[\s\p{C}]/u.test(fence.sessionId) &&
    [
      fence.generation,
      fence.bindingRevision,
      fence.hostRevision,
      fence.runtimeEpoch,
      fence.apiAuthorityEpoch,
      fence.sessionAuthEpoch,
    ].every((value) => isCanonicalUint64(value, true))
  )
}
function sameFence(
  a: WorkspaceFence | null | undefined,
  b: WorkspaceFence,
  except: readonly (keyof WorkspaceFence)[] = [],
): boolean {
  return (
    !!a &&
    validFence(a) &&
    validFence(b) &&
    fenceKeys.every((key) => except.includes(key) || a[key] === b[key])
  )
}
function validAttachment(attachment: AttachmentFence): boolean {
  return (
    !!attachment &&
    /^att_[a-f0-9]{32}$/.test(attachment.attachmentId) &&
    isCanonicalUint64(attachment.leaseNumber, true)
  )
}
function currentEvent(state: WorkspaceState, event: RuntimeEvent): boolean {
  return (
    !!event &&
    sameFence(state.workspaceFence, event.fence) &&
    validAttachment(event.attachment) &&
    !!state.attachmentFence &&
    state.attachmentFence.attachmentId === event.attachment.attachmentId &&
    state.attachmentFence.leaseNumber === event.attachment.leaseNumber
  )
}
function newAttempt(state: WorkspaceState, attempt: string): boolean {
  return (
    isCanonicalUint64(attempt, true) &&
    BigInt(attempt) > BigInt(state.requestSequence ?? '0')
  )
}
function withStatus(
  state: WorkspaceState,
  status: WorkspaceStatus,
  message: string | null = null,
  errorCode: string | null = null,
): WorkspaceState {
  return { ...state, status, message, errorCode }
}
function disconnect(state: WorkspaceState): WorkspaceState {
  return { ...state, attachmentFence: null, connectionAttempt: null }
}
function streamState(state: WorkspaceState): boolean {
  return (
    !state.recoveryRequired &&
    ['connected', 'gap', 'input_uncertain'].includes(state.status)
  )
}

export function workspaceReducer(
  state: WorkspaceState,
  action: WorkspaceAction,
): WorkspaceState {
  // Only an explicit new Start can leave a completed process. Late callbacks,
  // background events and uncorrelated errors cannot resurrect it.
  if (
    (state.status === 'stopped' || state.status === 'exited') &&
    action.type !== 'start_requested'
  )
    return state
  switch (action.type) {
    case 'checking':
      return state.workspaceFence ? state : withStatus(state, 'checking')
    case 'start_requested': {
      const agentType = action.agentType ?? 'claude'
      if (
        state.recoveryRequired ||
        state.status === 'stopping' ||
        state.attachmentFence ||
        !newAttempt(state, action.attempt) ||
        !/^prj_[a-f0-9]{32}$/.test(action.projectId) ||
        !['claude', 'codex'].includes(agentType)
      )
        return state
      return {
        ...initialWorkspaceState,
        status: 'starting',
        projectId: action.projectId,
        agentType,
        requestSequence: action.attempt,
        startAttempt: action.attempt,
      }
    }
    case 'start_accepted':
      if (
        state.status !== 'starting' ||
        action.attempt !== state.startAttempt ||
        !validFence(action.fence) ||
        state.projectId !== action.projectId ||
        action.projectId !== action.fence.projectId ||
        action.workspaceId !== action.fence.workspaceId ||
        state.agentType !== action.fence.agentType
      )
        return state
      return withStatus(
        {
          ...state,
          workspaceId: action.workspaceId,
          workspaceFence: { ...action.fence },
          startAttempt: null,
        },
        'connecting',
      )
    case 'connecting':
    case 'reconnect_requested':
      if (
        state.recoveryRequired ||
        state.status === 'stopping' ||
        !state.workspaceFence ||
        !newAttempt(state, action.attempt)
      )
        return state
      return withStatus(
        {
          ...disconnect(state),
          requestSequence: action.attempt,
          connectionAttempt: action.attempt,
        },
        action.type === 'connecting' ? 'connecting' : 'reconnecting',
      )
    case 'attachment_prepared': {
      const { event } = action
      if (
        state.recoveryRequired ||
        !['connecting', 'reconnecting'].includes(state.status) ||
        action.attempt !== state.connectionAttempt ||
        state.attachmentFence ||
        !sameFence(state.workspaceFence, event.fence) ||
        !validAttachment(event.attachment)
      )
        return state
      const previous = state.lastAttachment
      if (
        previous &&
        (event.attachment.attachmentId === previous.attachmentId ||
          BigInt(event.attachment.leaseNumber) <= BigInt(previous.leaseNumber))
      )
        return state
      return {
        ...state,
        attachmentFence: { ...event.attachment },
        lastAttachment: { ...event.attachment },
      }
    }
    case 'admitted':
      return !state.recoveryRequired &&
        ['connecting', 'reconnecting'].includes(state.status) &&
        !!state.connectionAttempt &&
        currentEvent(state, action.event)
        ? withStatus(state, 'connected')
        : state
    case 'output_observed':
      if (
        !streamState(state) ||
        !currentEvent(state, action.event) ||
        !validCursor(action.cursor) ||
        (state.cursor && BigInt(action.cursor) <= BigInt(state.cursor))
      )
        return state
      // A frame may cover several bytes; a numeric jump alone never invents GAP.
      return { ...state, cursor: action.cursor }
    case 'gap': {
      if (
        !streamState(state) ||
        !currentEvent(state, action.event) ||
        !validCursor(action.fromCursor) ||
        !isCanonicalUint64(action.toCursor, true) ||
        BigInt(action.fromCursor) >= BigInt(action.toCursor)
      )
        return state
      // GAP is an explicit half-open range from the current Runtime stream.
      // It advances past known loss, and an exact replay is idempotent.
      const end = BigInt(action.toCursor) - 1n
      if (
        state.cursor &&
        (end <= BigInt(state.cursor) ||
          BigInt(action.fromCursor) !== BigInt(state.cursor) + 1n)
      )
        return state
      if (state.status === 'input_uncertain') {
        return { ...state, cursor: end.toString() }
      }
      return withStatus(
        { ...state, cursor: end.toString() },
        'gap',
        '部分输出已超出保留范围，历史内容不完整。',
      )
    }
    case 'input_uncertain':
      return streamState(state) && currentEvent(state, action.event)
        ? withStatus(
            state,
            'input_uncertain',
            '输入是否写入尚不确定，不会自动重新发送。',
          )
        : state
    case 'detached':
      return currentEvent(state, action.event) && state.status !== 'stopping'
        ? withStatus(disconnect(state), 'detached')
        : state
    case 'stop_requested':
      if (!state.workspaceFence || !newAttempt(state, action.attempt))
        return state
      return withStatus(
        {
          ...state,
          requestSequence: action.attempt,
          stopAttempt: action.attempt,
        },
        'stopping',
      )
    case 'stopped':
      return state.status === 'stopping' &&
        action.attempt === state.stopAttempt &&
        sameFence(state.workspaceFence, action.fence)
        ? withStatus(
            { ...disconnect(state), cursor: null, stopAttempt: null },
            'stopped',
          )
        : state
    case 'api_restarted':
      // API authority epochs are random namespaces, not monotonic counters.
      // Exact previous identity provides the stale-notification fence.
      if (
        !sameFence(state.workspaceFence, action.previous) ||
        !sameFence(action.previous, action.next, ['apiAuthorityEpoch']) ||
        action.previous.apiAuthorityEpoch === action.next.apiAuthorityEpoch
      )
        return state
      return withStatus(
        {
          ...disconnect(state),
          workspaceFence: { ...action.next },
          cursor: null,
          lastAttachment: null,
        },
        state.recoveryRequired
          ? 'unavailable'
          : state.status === 'stopping'
            ? 'stopping'
            : 'reconnecting',
        state.recoveryRequired
          ? 'Runtime 仍需恢复核对。'
          : '服务连接已更新，请重新连接。',
      )
    case 'runtime_restarted': {
      if (
        !sameFence(state.workspaceFence, action.previous) ||
        !sameFence(action.previous, action.next, [
          'runtimeEpoch',
          'apiAuthorityEpoch',
        ]) ||
        BigInt(action.next.runtimeEpoch) <= BigInt(action.previous.runtimeEpoch)
      )
        return state
      return withStatus(
        {
          ...disconnect(state),
          workspaceFence: { ...action.next },
          cursor: null,
          lastAttachment: null,
          recoveryRequired: true,
        },
        'unavailable',
        'Runtime 已重启，需要管理员核对恢复证据。',
        'RECONCILIATION_REQUIRED',
      )
    }
    case 'recovery_reconciled':
      if (
        !state.recoveryRequired ||
        !sameFence(state.workspaceFence, action.previous) ||
        !sameFence(action.previous, action.next, ['generation']) ||
        BigInt(action.next.generation) <= BigInt(action.previous.generation)
      )
        return state
      return withStatus(
        {
          ...disconnect(state),
          workspaceFence: { ...action.next },
          cursor: null,
          lastAttachment: null,
          recoveryRequired: false,
        },
        'detached',
        '恢复核对已完成，请显式重新连接。',
      )
    case 'visibility_changed':
      if (action.visible || !state.attachmentFence || state.recoveryRequired)
        return state
      return withStatus(
        disconnect(state),
        state.status === 'stopping' ? 'stopping' : 'reconnecting',
        '页面进入后台，输入已暂停；返回后请重新连接。',
      )
    case 'request_failed': {
      const expected =
        action.operation === 'start'
          ? state.startAttempt
          : action.operation === 'connect'
            ? state.connectionAttempt
            : state.stopAttempt
      if (!expected || action.attempt !== expected) return state
      return withStatus(
        disconnect(state),
        state.recoveryRequired ? 'unavailable' : 'error',
        action.message.slice(0, 512),
        action.code.slice(0, 128),
      )
    }
    case 'error':
    case 'login_required':
    case 'trust_required':
    case 'exited':
    case 'missing':
    case 'collision':
    case 'unavailable':
      if (!currentEvent(state, action.event)) return state
      if (state.status === 'stopping' && action.type !== 'exited') {
        return {
          ...disconnect(state),
          message: action.message.slice(0, 512),
          errorCode: action.code?.slice(0, 128) ?? null,
        }
      }
      return withStatus(
        {
          ...disconnect(state),
          cursor: action.type === 'exited' ? null : state.cursor,
        },
        action.type,
        action.message.slice(0, 512),
        action.code?.slice(0, 128) ?? null,
      )
    default:
      return state
  }
}
