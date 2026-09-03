import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from '../../lib/api'
import { useAuth } from '../auth/AuthContext'
import { useProjects } from '../projects/useProjects'
import { useWorkspaceActions } from './useWorkspaceActions'
import { useWorkspaceStatus } from './useWorkspaceStatus'
import {
  isProjectId,
  isWorkspaceId,
  parseWorkspaceList,
  parseWorkspaceMetadata,
  type WorkspaceMetadata,
} from './workspaceMetadata'
import type {
  WorkspaceAgent,
  WorkspacePageModel,
  WorkspaceStopTarget,
} from './workspaceView'

type Lookup = {
  key: string
  status: WorkspacePageModel['lookup']
  row: WorkspaceMetadata | null
  error: ApiError | null
}
function failure(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({
        code: 'WAW_METADATA_INVALID',
        message: '工作区信息不完整，请刷新后重试',
        status: 0,
      })
}

/** Metadata/lifecycle workflow only. No ticket acquisition or admission is inferred. */
export function useWorkspaceController(options: {
  workspaceId?: string
  projectId?: string
  agentType?: string
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
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [confirmation, setConfirmation] = useState<
    (WorkspaceStopTarget & { key: string; runtimeFingerprint: string }) | null
  >(null)
  const requestSequence = useRef(0)
  const selectionEpoch = useRef(0)
  const mounted = useRef(false)
  const routeResolved = useRef(false)
  const authScope = auth ? `${auth.session.id}:${auth.csrf_token}` : ''
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
          error: new ApiError({
            code: 'WAW_INVALID_AGENT',
            message: 'URL 中的 AgentType 无效，请重新选择项目与 AgentType',
            status: 400,
          }),
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
            error: new ApiError({
              code: 'WORKSPACE_NOT_FOUND',
              message: '工作区标识无效',
              status: 404,
            }),
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
            throw new ApiError({
              code: 'PROJECT_NOT_READY',
              message: '该工作区所属项目不可用',
              status: 409,
            })
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
          error: new ApiError({
            code: 'PROJECT_NOT_READY',
            message: '请选择可用的正式项目',
            status: 409,
          }),
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
    setNotice(null)
    setActionError(null)
    try {
      const response = await actions.start(row.project_id, row.agent_type)
      if (!mounted.current || selectionEpoch.current !== epoch) return
      if (!response || response.workspace_id !== row.id)
        throw new ApiError({
          code: 'PROJECT_IDENTITY_CHANGED',
          message: '工作区身份已变化，请刷新',
          status: 409,
        })
      setNotice('启动请求已确认。进程状态与浏览器终端连接状态分别显示。')
      setReload((value) => value + 1)
    } catch (error) {
      if (mounted.current && selectionEpoch.current === epoch)
        setActionError(failure(error))
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
    setActionError(null)
    try {
      const response = await actions.stop(
        target.workspaceId,
        target.generation,
        row.agent_type,
      )
      if (!mounted.current || selectionEpoch.current !== epoch) return
      if (!response || response.state !== 'STOPPED')
        throw new ApiError({
          code: 'RECONCILIATION_REQUIRED',
          message: '停止尚未确认，请刷新状态',
          status: 409,
        })
      setConfirmation(null)
      setNotice('受管进程已停止，项目与 Git 修改已保留。')
      setReload((value) => value + 1)
    } catch (error) {
      if (mounted.current && selectionEpoch.current === epoch) {
        setConfirmation(null)
        setActionError(failure(error))
      }
    }
  }
  async function refresh() {
    setConfirmation(null)
    setActionError(null)
    await projects.refresh()
    if (mounted.current) setReload((value) => value + 1)
  }
  return {
    projects: choices,
    projectsLoading: projects.loading,
    projectError: projects.error ? '项目列表读取失败，请刷新后重试。' : null,
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
          error: new ApiError({
            code: 'PROJECT_IDENTITY_CHANGED',
            message: 'Runtime 代次已变化，请刷新工作区',
            status: 409,
          }),
        }
      : status.view,
    pending: actions.pending,
    error: actionError ?? currentLookup.error,
    notice: runtimeNeedsRecovery
      ? 'Runtime 需要恢复核对，当前操作已暂停。'
      : notice,
    canStart,
    canStop,
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
  }
}
