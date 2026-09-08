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

function combineAbortSignals(...signals: AbortSignal[]) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  for (const signal of signals) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', abort, { once: true })
  }
  return {
    signal: controller.signal,
    dispose: () => {
      for (const signal of signals) signal.removeEventListener('abort', abort)
    },
  }
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
    | (WorkspaceStopTarget & {
        key: string
        observationToken: number
        runtimeFingerprint: string
      })
    | null
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
    setConfirmation(null)
    setNotice(null)
    setActionError(null)
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
  const revokeObservationState = useCallback(() => {
    setConfirmation(null)
    setNotice(null)
    setActionError(null)
  }, [])
  const status = useWorkspaceStatus(
    row?.id,
    `${reload}:${row?.revision ?? ''}`,
    revokeObservationState,
  )
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
    observationToken: number,
  ) =>
    mounted.current &&
    selectionEpoch.current === epoch &&
    authScopeRef.current === scope &&
    attachmentIdentityRef.current === attachmentKey &&
    status.isCurrent(observationToken)
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
  const validCurrentRow = (token = status.observationToken) =>
    !!row &&
    !!observed &&
    status.isCurrent(token) &&
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
    !!observed &&
    status.isCurrent(status.observationToken) &&
    !runtimeMismatch &&
    !runtimeNeedsRecovery &&
    ['STARTING', 'STOPPED', 'EXITED'].includes(row.state) &&
    ['STARTING', 'STOPPED', 'EXITED'].includes(observed.state) &&
    !['unknown', 'reconciliation_required'].includes(row.reconciliation_state)
  const canStop =
    !!row &&
    !projects.loading &&
    !projects.error &&
    currentLookup.status === 'ready' &&
    !actions.pending &&
    selectedReady &&
    !!observed &&
    !runtimeMismatch &&
    !runtimeNeedsRecovery &&
    [
      'RUNNING',
      'NEEDS_INTERACTION',
      'TRUST_REQUIRED',
      'LOGIN_REQUIRED',
    ].includes(row.state) &&
    [
      'RUNNING',
      'NEEDS_INTERACTION',
      'TRUST_REQUIRED',
      'LOGIN_REQUIRED',
    ].includes(observed.state) &&
    row.reconciliation_state === 'authoritative' &&
    status.isCurrent(status.observationToken) &&
    observed.reconciliation_state === 'authoritative'
  const canConnect =
    attachment.canConnect && !actions.pending && validCurrentRow()
  const canReconnect =
    attachment.canReconnect && !actions.pending && validCurrentRow()
  const canDetach =
    attachment.canDetach && !actions.pending && validCurrentRow()
  const canInput = attachment.canInput && !actions.pending && validCurrentRow()
  const canResize =
    attachment.canResize && !actions.pending && validCurrentRow()

  async function start() {
    const observationToken = status.observationToken
    const signal = status.observationSignal
    if (
      observationToken === null ||
      !canStart ||
      !validCurrentRow(observationToken) ||
      !row ||
      !signal
    )
      return
    const epoch = selectionEpoch.current
    const scope = authScope
    const attachmentKey = attachment.identity?.key ?? null
    setNotice(null)
    setActionError(null)
    try {
      const response = await actions.start(
        row.project_id,
        row.agent_type,
        signal,
      )
      if (!actionStillCurrent(epoch, scope, attachmentKey, observationToken))
        return
      if (!response || response.workspace_id !== row.id)
        throw workspaceError('PROJECT_IDENTITY_CHANGED')
      setNotice('START_CONFIRMED')
      setReload((value) => value + 1)
    } catch (error) {
      if (actionStillCurrent(epoch, scope, attachmentKey, observationToken))
        setScopedActionError(failure(error))
    }
  }
  function requestStop() {
    const observationToken = status.observationToken
    if (
      observationToken === null ||
      !canStop ||
      !validCurrentRow(observationToken) ||
      !row
    )
      return
    setConfirmation({
      key,
      workspaceId: row.id,
      generation: String(row.generation),
      observationToken,
      runtimeFingerprint,
    })
  }
  async function confirmStop() {
    if (
      !confirmation ||
      confirmation.key !== key ||
      !row ||
      !canStop ||
      !validCurrentRow(confirmation.observationToken) ||
      confirmation.workspaceId !== row.id ||
      confirmation.generation !== String(row.generation) ||
      confirmation.runtimeFingerprint !== runtimeFingerprint
    ) {
      setConfirmation(null)
      return
    }
    const target = confirmation
    const signal = status.observationSignal
    if (!signal) {
      setConfirmation(null)
      return
    }
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
        const control = combineAbortSignals(signal, attachment.controlSignal())
        try {
          state = (
            await actions.stop(
              target.workspaceId,
              target.generation,
              row.agent_type,
              control.signal,
            )
          ).state
        } finally {
          control.dispose()
        }
      }
      if (
        !actionStillCurrent(
          epoch,
          scope,
          attachmentKey,
          target.observationToken,
        )
      )
        return
      if (state !== 'STOPPED') throw workspaceError('RECONCILIATION_REQUIRED')
      setConfirmation(null)
      setNotice('STOP_CONFIRMED')
      setReload((value) => value + 1)
    } catch (error) {
      if (
        actionStillCurrent(epoch, scope, attachmentKey, target.observationToken)
      ) {
        setConfirmation(null)
        setScopedActionError(failure(error))
      }
    }
  }
  async function refresh() {
    setConfirmation(null)
    setNotice(null)
    setActionError(null)
    await projects.refresh()
    if (mounted.current) setReload((value) => value + 1)
  }
  async function connectTerminal() {
    const observationToken = status.observationToken
    if (!canConnect || !validCurrentRow(observationToken)) return
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
        attachmentIdentityRef.current === attachmentKey &&
        status.isCurrent(observationToken)
      ) {
        setScopedActionError(failure(error))
      }
    }
  }
  async function reconnectTerminal() {
    const observationToken = status.observationToken
    if (!canReconnect || !validCurrentRow(observationToken)) return
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
        attachmentIdentityRef.current === attachmentKey &&
        status.isCurrent(observationToken)
      ) {
        setScopedActionError(failure(error))
      }
    }
  }
  async function detachTerminal() {
    const observationToken = status.observationToken
    if (!canDetach || !validCurrentRow(observationToken)) return
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
        attachmentIdentityRef.current === attachmentKey &&
        status.isCurrent(observationToken)
      ) {
        setScopedActionError(failure(error))
      }
    }
  }
  async function sendTerminalInput(text: string) {
    const observationToken = status.observationToken
    if (!canInput || !validCurrentRow(observationToken)) return
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
        attachmentIdentityRef.current === attachmentKey &&
        status.isCurrent(observationToken)
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
    notice:
      status.isCurrent(status.observationToken) && runtimeNeedsRecovery
        ? 'RUNTIME_RECOVERY_REQUIRED'
        : status.isCurrent(status.observationToken)
          ? notice
          : null,
    canStart,
    canStop,
    canConnect,
    canReconnect,
    canDetach,
    canInput,
    canResize,
    stopTarget:
      confirmation?.key === key &&
      confirmation.runtimeFingerprint === runtimeFingerprint &&
      status.isCurrent(confirmation.observationToken) &&
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
