import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useProjects } from '../projects/useProjects'
import { useWorkspaceActions } from './useWorkspaceActions'
import { useWorkspaceStatus } from './useWorkspaceStatus'
import {
  useWAWBrowserAttachment,
  type WAWAttachmentDependencies,
} from './useWAWBrowserAttachment'
import { WAWBrowserControllerError } from './wawBrowserController'
import {
  isProjectId,
  isWorkspaceId,
  parseWorkspaceList,
  parseWorkspaceMetadata,
  type WorkspaceMetadata,
} from './workspaceMetadata'
import type {
  WorkspaceAgent,
  WorkspaceNotice,
  WorkspacePageModel,
  WorkspaceStopTarget,
  WorkspaceApiErrorView,
} from './workspaceView'
import { workspaceApiError, workspaceError } from './workspaceView'

type Lookup = {
  key: string
  status: WorkspacePageModel['lookup']
  row: WorkspaceMetadata | null
  error: WorkspaceApiErrorView | null
}

type ScopedActionError = {
  readonly error: WorkspaceApiErrorView
  readonly scope: string
  readonly selectionKey: string
  readonly attachmentKey: string | null
}
function failure(error: unknown): WorkspaceApiErrorView {
  return workspaceApiError(error, 'WAW_METADATA_INVALID')
}

/** Metadata/lifecycle workflow only. No ticket acquisition or admission is inferred. */
export function useWorkspaceController(options: {
  workspaceId?: string
  projectId?: string
  agentType?: string
  /** @internal Test-only composition seam; production always uses managed Chromium trust. */
  attachmentDependencies?: WAWAttachmentDependencies
}): WorkspacePageModel {
  const { api, auth } = useAuth()
  const projects = useProjects()
  const actions = useWorkspaceActions()
  const initialAgent: WorkspaceAgent =
    options.agentType === 'codex' ? 'codex' : 'claude'
  const [selection, setSelection] = useState({
    projectId: options.projectId ?? '',
    agentType: initialAgent,
  })
  const [invalidAgent, setInvalidAgent] = useState(
    options.agentType !== undefined &&
      !['claude', 'codex'].includes(options.agentType),
  )
  const selectionRef = useRef(selection)
  const [reload, setReload] = useState(0)
  const [lookup, setLookup] = useState<Lookup>({
    key: '',
    status: 'idle',
    row: null,
    error: null,
  })
  const [notice, setNotice] = useState<WorkspaceNotice | null>(null)
  const [actionError, setActionError] = useState<ScopedActionError | null>(null)
  const [confirmation, setConfirmation] = useState<
    (WorkspaceStopTarget & { key: string; runtimeFingerprint: string }) | null
  >(null)
  const requestSequence = useRef(0)
  const selectionEpoch = useRef(0)
  const attachmentFence = useRef<() => void>(() => undefined)
  const attachmentIdentityRef = useRef<string | null>(null)
  const mounted = useRef(false)
  const routeResolved = useRef(false)
  const authScope = auth ? `${auth.session.id}:${auth.csrf_token}` : ''
  const authScopeRef = useRef(authScope)
  authScopeRef.current = authScope
  const key = `${authScope}:${selection.projectId}:${selection.agentType}`
  const choices = useMemo(
    () =>
      projects.projects
        .filter(
          (project) => project.state === 'ready' && isProjectId(project.id),
        )
        .map((project) => ({
          id: project.id,
          displayName: project.display_name,
        })),
    [projects.projects],
  )
  const readyIds = useMemo(
    () => choices.map((project) => project.id),
    [choices],
  )
  const selectedReady = readyIds.includes(selection.projectId)

  const invalidate = useCallback(() => {
    attachmentFence.current()
    selectionEpoch.current++
    requestSequence.current++
  }, [])
  useEffect(() => {
    mounted.current = true
    invalidate()
    return () => {
      mounted.current = false
      invalidate()
    }
  }, [authScope, invalidate])

  const select = useCallback(
    (projectId: string, agentType: WorkspaceAgent) => {
      invalidate()
      routeResolved.current = true
      selectionRef.current = { projectId, agentType }
      setSelection({ projectId, agentType })
      setInvalidAgent(false)
      setConfirmation(null)
      setNotice(null)
      setActionError(null)
    },
    [invalidate],
  )

  useEffect(() => {
    if (projects.loading || !authScope) return
    const controller = new AbortController()
    const sequence = ++requestSequence.current
    const current = () =>
      mounted.current &&
      !controller.signal.aborted &&
      requestSequence.current === sequence
    const load = async () => {
      if (projects.error) {
        setLookup({ key, status: 'idle', row: null, error: null })
        return
      }
      if (invalidAgent) {
        setLookup({
          key,
          status: 'error',
          row: null,
          error: workspaceError('WAW_INVALID_AGENT'),
        })
        return
      }
      if (
        !selection.projectId &&
        options.workspaceId &&
        !routeResolved.current
      ) {
        if (!isWorkspaceId(options.workspaceId)) {
          setLookup({
            key,
            status: 'error',
            row: null,
            error: workspaceError('WORKSPACE_NOT_FOUND'),
          })
          return
        }
        setLookup({ key, status: 'loading', row: null, error: null })
        try {
          const row = await api.get(
            `/api/v1/workspaces/${options.workspaceId}`,
            {
              signal: controller.signal,
              validate: (value) =>
                parseWorkspaceMetadata(value, options.workspaceId!),
            },
          )
          if (!current()) return
          if (!readyIds.includes(row.project_id))
            throw workspaceError('PROJECT_NOT_READY')
          select(row.project_id, row.agent_type)
        } catch (error) {
          if (current())
            setLookup({
              key,
              status: 'error',
              row: null,
              error: failure(error),
            })
        }
        return
      }
      if (!selection.projectId) {
        setLookup({ key, status: 'idle', row: null, error: null })
        return
      }
      if (!isProjectId(selection.projectId) || !selectedReady) {
        setLookup({
          key,
          status: 'error',
          row: null,
          error: workspaceError('PROJECT_NOT_READY'),
        })
        return
      }
      setLookup({ key, status: 'loading', row: null, error: null })
      try {
        const row = await api.get(
          `/api/v1/workspaces?project_id=${selection.projectId}&agent_type=${selection.agentType}`,
          {
            signal: controller.signal,
            validate: (value) =>
              parseWorkspaceList(
                value,
                selection.projectId,
                selection.agentType,
              ),
          },
        )
        if (current())
          setLookup({
            key,
            status: row ? 'ready' : 'unregistered',
            row,
            error: null,
          })
      } catch (error) {
        if (current())
          setLookup({ key, status: 'error', row: null, error: failure(error) })
      }
    }
    void load()
    return () => controller.abort()
  }, [
    api,
    authScope,
    key,
    options.workspaceId,
    invalidAgent,
    projects.loading,
    projects.error,
    readyIds,
    reload,
    select,
    selectedReady,
    selection,
  ])

  const currentLookup: Lookup =
    lookup.key === key
      ? lookup
      : {
          key,
          status:
            selection.projectId || options.workspaceId ? 'loading' : 'idle',
          row: null,
          error: null,
        }
  const row = currentLookup.row
  const status = useWorkspaceStatus(row?.id, `${reload}:${row?.revision ?? ''}`)
  const observed =
    status.view.status === 'loaded' ? status.view.response.data : null
  const runtimeMismatch =
    !!row &&
    !!observed &&
    (observed.workspace_id !== row.id ||
      observed.project_id !== row.project_id ||
      observed.agent_type !== row.agent_type ||
      observed.generation !== String(row.generation))
  const runtimeNeedsRecovery =
    !!observed &&
    (['unknown', 'reconciliation_required'].includes(
      observed.reconciliation_state,
    ) ||
      ['UNKNOWN', 'COLLISION', 'BROKEN', 'MISSING'].includes(observed.state))
  const runtimeFingerprint = observed
    ? [
        observed.workspace_id,
        observed.generation,
        observed.binding_revision,
        observed.binding_digest,
        observed.runtime_epoch,
      ].join(':')
    : ''
  const attachment = useWAWBrowserAttachment({
    actions,
    agentType: selection.agentType,
    authScope,
    contextEpoch: selectionEpoch,
    generation: row ? String(row.generation) : null,
    projectId: row?.project_id ?? null,
    runtime: observed,
    workspaceId: row?.id ?? null,
    dependencies: options.attachmentDependencies,
  })
  attachmentFence.current = attachment.fence
  attachmentIdentityRef.current = attachment.identity?.key ?? null
  const actionStillCurrent = (
    epoch: number,
    scope: string,
    attachmentKey: string | null,
  ) =>
    mounted.current &&
    selectionEpoch.current === epoch &&
    authScopeRef.current === scope &&
    attachmentIdentityRef.current === attachmentKey
  const setScopedActionError = (error: WorkspaceApiErrorView) => {
    setActionError({
      error,
      scope: authScope,
      selectionKey: key,
      attachmentKey: attachment.identity?.key ?? null,
    })
  }
  const currentActionError =
    actionError !== null &&
    actionError.scope === authScope &&
    actionError.selectionKey === key &&
    actionError.attachmentKey === (attachment.identity?.key ?? null)
      ? actionError.error
      : null
  const validCurrentRow = () =>
    !!row &&
    row.project_id === selectionRef.current.projectId &&
    row.agent_type === selectionRef.current.agentType &&
    selectedReady &&
    !runtimeMismatch &&
    !runtimeNeedsRecovery
  const canStart =
    !!row &&
    !projects.loading &&
    !projects.error &&
    currentLookup.status === 'ready' &&
    !actions.pending &&
    selectedReady &&
    !runtimeMismatch &&
    !runtimeNeedsRecovery &&
    ['STARTING', 'STOPPED', 'EXITED'].includes(row.state) &&
    !['unknown', 'reconciliation_required'].includes(row.reconciliation_state)
  const canStop =
    !!row &&
    !projects.loading &&
    !projects.error &&
    currentLookup.status === 'ready' &&
    !actions.pending &&
    selectedReady &&
    !runtimeMismatch &&
    !runtimeNeedsRecovery &&
    [
      'RUNNING',
      'NEEDS_INTERACTION',
      'TRUST_REQUIRED',
      'LOGIN_REQUIRED',
    ].includes(row.state) &&
    row.reconciliation_state === 'authoritative' &&
    !!observed &&
    observed.reconciliation_state === 'authoritative'

  async function start() {
    if (!canStart || !validCurrentRow() || !row) return
    const epoch = selectionEpoch.current
    const scope = authScope
    const attachmentKey = attachment.identity?.key ?? null
    setNotice(null)
    setActionError(null)
    try {
      const response = await actions.start(row.project_id, row.agent_type)
      if (!actionStillCurrent(epoch, scope, attachmentKey)) return
      if (!response || response.workspace_id !== row.id)
        throw workspaceError('PROJECT_IDENTITY_CHANGED')
      setNotice('START_CONFIRMED')
      setReload((value) => value + 1)
    } catch (error) {
      if (actionStillCurrent(epoch, scope, attachmentKey))
        setScopedActionError(failure(error))
    }
  }
  function requestStop() {
    if (!canStop || !validCurrentRow() || !row) return
    setConfirmation({
      key,
      workspaceId: row.id,
      generation: String(row.generation),
      runtimeFingerprint,
    })
  }
  async function confirmStop() {
    if (
      !confirmation ||
      confirmation.key !== key ||
      !row ||
      !canStop ||
      !validCurrentRow() ||
      confirmation.workspaceId !== row.id ||
      confirmation.generation !== String(row.generation) ||
      confirmation.runtimeFingerprint !== runtimeFingerprint
    ) {
      setConfirmation(null)
      return
    }
    const target = confirmation
    const epoch = selectionEpoch.current
    const scope = authScope
    const attachmentKey = attachment.identity?.key ?? null
    setActionError(null)
    try {
      const attached = attachment.view.attached
      let state: string
      if (attached !== null) {
        if (
          !attachment.canControlStop ||
          attached.workspaceId !== target.workspaceId ||
          attached.generation !== target.generation ||
          attached.projectId !== row.project_id ||
          attached.agentType !== row.agent_type
        ) {
          throw new WAWBrowserControllerError('CONTEXT_CHANGED')
        }
        const outcome = await attachment.stop()
        if (!outcome.detachConfirmed) {
          throw new WAWBrowserControllerError('DETACH_FAILED')
        }
        state = outcome.stop.state
      } else {
        attachment.fence()
        state = (
          await actions.stop(
            target.workspaceId,
            target.generation,
            row.agent_type,
            attachment.controlSignal(),
          )
        ).state
      }
      if (!actionStillCurrent(epoch, scope, attachmentKey)) return
      if (state !== 'STOPPED') throw workspaceError('RECONCILIATION_REQUIRED')
      setConfirmation(null)
      setNotice('STOP_CONFIRMED')
      setReload((value) => value + 1)
    } catch (error) {
      if (actionStillCurrent(epoch, scope, attachmentKey)) {
        setConfirmation(null)
        setScopedActionError(failure(error))
      }
    }
  }
  async function refresh() {
    setConfirmation(null)
    setActionError(null)
    await projects.refresh()
    if (mounted.current) setReload((value) => value + 1)
  }
  async function connectTerminal() {
    const epoch = selectionEpoch.current
    const scope = authScope
    const attachmentKey = attachment.identity?.key ?? null
    setActionError(null)
    try {
      await attachment.connect()
    } catch (error) {
      if (
        mounted.current &&
        selectionEpoch.current === epoch &&
        authScopeRef.current === scope &&
        attachmentIdentityRef.current === attachmentKey
      ) {
        setScopedActionError(failure(error))
      }
    }
  }
  async function reconnectTerminal() {
    const epoch = selectionEpoch.current
    const scope = authScope
    const attachmentKey = attachment.identity?.key ?? null
    setActionError(null)
    try {
      await attachment.reconnect()
    } catch (error) {
      if (
        mounted.current &&
        selectionEpoch.current === epoch &&
        authScopeRef.current === scope &&
        attachmentIdentityRef.current === attachmentKey
      ) {
        setScopedActionError(failure(error))
      }
    }
  }
  async function detachTerminal() {
    const epoch = selectionEpoch.current
    const scope = authScope
    const attachmentKey = attachment.identity?.key ?? null
    setActionError(null)
    try {
      await attachment.detach()
    } catch (error) {
      if (
        mounted.current &&
        selectionEpoch.current === epoch &&
        authScopeRef.current === scope &&
        attachmentIdentityRef.current === attachmentKey
      ) {
        setScopedActionError(failure(error))
      }
    }
  }
  async function sendTerminalInput(text: string) {
    const epoch = selectionEpoch.current
    const scope = authScope
    const attachmentKey = attachment.identity?.key ?? null
    setActionError(null)
    try {
      await attachment.sendInput(text)
    } catch (error) {
      if (
        mounted.current &&
        selectionEpoch.current === epoch &&
        authScopeRef.current === scope &&
        attachmentIdentityRef.current === attachmentKey
      ) {
        setScopedActionError(failure(error))
      }
    }
  }
  return {
    projects: choices,
    projectsLoading: projects.loading,
    projectError: projects.error,
    selectedProjectId: selection.projectId,
    agentType: selection.agentType,
    lookup: currentLookup.status,
    workspaceId: row?.id ?? null,
    generation: row ? String(row.generation) : null,
    lifecycleState: row?.state ?? null,
    reconciliationState: row?.reconciliation_state ?? null,
    runtimeView: runtimeMismatch
      ? {
          status: 'error',
          error: workspaceError('PROJECT_IDENTITY_CHANGED'),
        }
      : status.view,
    attachment: attachment.view,
    pending: actions.pending,
    error: currentActionError ?? currentLookup.error ?? attachment.error,
    notice: runtimeNeedsRecovery ? 'RUNTIME_RECOVERY_REQUIRED' : notice,
    canStart,
    canStop,
    canConnect: attachment.canConnect && !actions.pending,
    canReconnect: attachment.canReconnect && !actions.pending,
    canDetach: attachment.canDetach && !actions.pending,
    canInput: attachment.canInput && !actions.pending,
    canResize: attachment.canResize && !actions.pending,
    stopTarget:
      confirmation?.key === key &&
      confirmation.runtimeFingerprint === runtimeFingerprint &&
      !runtimeNeedsRecovery
        ? confirmation
        : null,
    selectProject: (projectId) =>
      select(projectId, selectionRef.current.agentType),
    selectAgent: (agent) => {
      if (agent === 'claude' || agent === 'codex')
        select(selectionRef.current.projectId, agent)
    },
    refresh,
    start,
    requestStop,
    cancelStop: () => setConfirmation(null),
    confirmStop,
    setTerminalSurface: attachment.setSurface,
    setTerminalViewport: attachment.setViewport,
    setTerminalInputClearer: attachment.setInputClearer,
    connect: connectTerminal,
    reconnect: reconnectTerminal,
    detach: detachTerminal,
    sendInput: sendTerminalInput,
  }
}
