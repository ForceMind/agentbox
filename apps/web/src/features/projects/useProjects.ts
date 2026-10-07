import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { technicalValue } from '../../i18n'
import { ApiError } from '../../lib/api'
import {
  GitBranchData,
  GitBranchListResponse,
  JobData,
  JobResponse,
  ProjectData,
  ProjectJobResponse,
  ProjectListResponse,
  ProjectResponse,
  parseGitBranchListResponse,
  parseJobResponse,
  parseProjectJobResponse,
  parseProjectListResponse,
  parseProjectResponse,
} from '../../lib/contracts'

export type ProjectApiErrorView = Readonly<{
  code: string
  requestId?: string
}>

export type ProjectJobPhase =
  | 'queued'
  | 'running'
  | 'executing'
  | 'recovery_required'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'needs_attention'

export type ProjectJobView = Readonly<
  Pick<JobData, 'id' | 'status'> & {
    error_code?: string
    phase?: ProjectJobPhase
    progress?: number
  }
>

type JobInput = Pick<JobData, 'id' | 'status'> &
  Partial<Pick<JobData, 'error_code' | 'phase' | 'progress'>>

const TERMINAL_JOBS = new Set([
  'succeeded',
  'failed',
  'cancelled',
  'needs_attention',
])

const JOB_PHASES = new Set<ProjectJobPhase>([
  'queued',
  'running',
  'executing',
  'recovery_required',
  'succeeded',
  'failed',
  'cancelled',
  'needs_attention',
])

const SAFE_ERROR_CODE = /^[A-Z][A-Z0-9_]{0,79}$/
const SAFE_TECHNICAL_IDENTIFIER = /^[A-Za-z0-9._:-]{1,96}$/

function safeTechnicalIdentifier(value: unknown): string | null {
  if (typeof value !== 'string' || !SAFE_TECHNICAL_IDENTIFIER.test(value)) {
    return null
  }
  try {
    return technicalValue(value).value
  } catch {
    return null
  }
}

function safeErrorCode(value: unknown): string | null {
  if (typeof value !== 'string' || !SAFE_ERROR_CODE.test(value)) return null
  try {
    return technicalValue(value).value
  } catch {
    return null
  }
}

function safeApiError(
  value: unknown,
  fallbackCode: string,
): ProjectApiErrorView {
  if (!(value instanceof ApiError)) return Object.freeze({ code: fallbackCode })
  const code = safeErrorCode(value.code) ?? fallbackCode
  const requestId = safeTechnicalIdentifier(value.requestId)
  return Object.freeze({
    code,
    ...(requestId === null ? {} : { requestId }),
  })
}

function safeJobView(value: JobInput): ProjectJobView | null {
  const id = safeTechnicalIdentifier(value.id)
  if (id === null) return null
  const phase =
    typeof value.phase === 'string' &&
    JOB_PHASES.has(value.phase as ProjectJobPhase)
      ? (value.phase as ProjectJobPhase)
      : undefined
  const errorCode = safeErrorCode(value.error_code)
  const progress =
    typeof value.progress === 'number' &&
    Number.isInteger(value.progress) &&
    value.progress >= 0 &&
    value.progress <= 100
      ? value.progress
      : undefined
  return Object.freeze({
    id,
    status: value.status,
    ...(phase === undefined ? {} : { phase }),
    ...(progress === undefined ? {} : { progress }),
    ...(errorCode === null ? {} : { error_code: errorCode }),
  })
}

function key() {
  return `web-${crypto.randomUUID()}`
}

function idempotencyKey(
  keys: Map<string, string>,
  operation: string,
  body: object,
) {
  const fingerprint = operation + ':' + JSON.stringify(body)
  const existing = keys.get(fingerprint)
  if (existing) return { fingerprint, value: existing }
  const value = key()
  keys.set(fingerprint, value)
  return { fingerprint, value }
}

function receivedDefinitiveFailure(value: unknown) {
  return value instanceof ApiError && value.status > 0
}

export function useProjects() {
  const { api, auth } = useAuth()
  const [projects, setProjects] = useState<ProjectData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ProjectApiErrorView | null>(null)
  const [pending, setPending] = useState(false)
  const [job, setJob] = useState<ProjectJobView | null>(null)
  const idempotencyKeys = useRef(new Map<string, string>())

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.get<ProjectListResponse>('/api/v1/projects', {
        timeoutMs: 45_000,
        validate: parseProjectListResponse,
      })
      setProjects(response.data.projects)
      setError(null)
    } catch (value) {
      setError(safeApiError(value, 'CONTROL_PLANE_UNAVAILABLE'))
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => void refresh(), [refresh])

  useEffect(() => {
    if (!job || TERMINAL_JOBS.has(job.status)) return
    let cancelled = false
    const timeout = window.setTimeout(() => {
      void api
        .get<JobResponse>(`/api/v1/jobs/${encodeURIComponent(job.id)}`, {
          timeoutMs: 15_000,
          validate: parseJobResponse,
        })
        .then((response) => {
          if (cancelled) return
          const nextJob = safeJobView(response.data)
          if (nextJob === null) {
            setJob(null)
            setError({ code: 'PROJECT_JOB_RESPONSE_INVALID' })
            return
          }
          setJob(nextJob)
          if (TERMINAL_JOBS.has(response.data.status)) void refresh()
        })
        .catch((value: unknown) => {
          if (!cancelled)
            setError(safeApiError(value, 'CONTROL_PLANE_UNAVAILABLE'))
        })
    }, 750)
    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [api, job, refresh])

  async function create(name: string) {
    if (!auth) return
    const body = { name }
    const requestKey = idempotencyKey(
      idempotencyKeys.current,
      'project.create',
      body,
    )
    setPending(true)
    try {
      const response = await api.post<ProjectJobResponse>('/api/v1/projects', {
        body,
        csrfToken: auth.csrf_token,
        idempotencyKey: requestKey.value,
        validate: parseProjectJobResponse,
      })
      idempotencyKeys.current.delete(requestKey.fingerprint)
      const nextJob = safeJobView(response.data.job)
      setJob(nextJob)
      setProjects((current) => [...current, response.data.project])
      setError(
        nextJob === null ? { code: 'PROJECT_JOB_RESPONSE_INVALID' } : null,
      )
    } catch (value) {
      if (receivedDefinitiveFailure(value)) {
        idempotencyKeys.current.delete(requestKey.fingerprint)
      }
      setError(safeApiError(value, 'PROJECT_OPERATION_FAILED'))
    } finally {
      setPending(false)
    }
  }

  async function clone(repositoryUrl: string, name: string) {
    if (!auth) return
    const body = { repository_url: repositoryUrl, name: name || null }
    const requestKey = idempotencyKey(
      idempotencyKeys.current,
      'project.clone',
      body,
    )
    setPending(true)
    try {
      const response = await api.post<ProjectJobResponse>(
        '/api/v1/projects/clone',
        {
          body,
          csrfToken: auth.csrf_token,
          idempotencyKey: requestKey.value,
          validate: parseProjectJobResponse,
        },
      )
      idempotencyKeys.current.delete(requestKey.fingerprint)
      const nextJob = safeJobView(response.data.job)
      setJob(nextJob)
      setProjects((current) => [...current, response.data.project])
      setError(
        nextJob === null ? { code: 'PROJECT_JOB_RESPONSE_INVALID' } : null,
      )
    } catch (value) {
      if (receivedDefinitiveFailure(value)) {
        idempotencyKeys.current.delete(requestKey.fingerprint)
      }
      setError(safeApiError(value, 'PROJECT_OPERATION_FAILED'))
    } finally {
      setPending(false)
    }
  }

  return { clone, create, error, job, loading, pending, projects, refresh }
}

type ProjectDetailPhase = 'loading' | 'ready' | 'stale' | 'error' | 'forbidden'

type ProjectDetailView = {
  project: ProjectData | null
  branches: GitBranchData[]
  error: ProjectApiErrorView | null
  pending: string | null
  job: ProjectJobView | null
  phase: ProjectDetailPhase
}

function emptyProjectDetail(phase: ProjectDetailPhase): ProjectDetailView {
  return {
    project: null,
    branches: [],
    error: null,
    pending: null,
    job: null,
    phase,
  }
}

function projectJobMatches(job: JobData, projectId: string, jobId?: string) {
  return (
    job.project_id === projectId &&
    job.target_type === 'project' &&
    job.target_id === projectId &&
    (jobId === undefined || job.id === jobId)
  )
}

export function useProject(projectId: string | undefined) {
  const { api, auth, status } = useAuth()
  const identity =
    status === 'authenticated' && auth && projectId
      ? JSON.stringify([auth.user.id, auth.session.id, projectId])
      : null
  // A new object is necessary for A → B → A; a matching route string is not
  // proof that a callback belongs to this visit or this adminSession.
  const owner = useMemo(
    () => ({
      api,
      identity,
      active: false,
      epoch: 0,
      read: 0,
      dirty: true,
      controller: null as AbortController | null,
      operation: null as object | null,
      view: emptyProjectDetail(identity ? 'loading' : 'forbidden'),
    }),
    [api, identity],
  )
  const currentOwner = useRef(owner)
  currentOwner.current = owner
  const availability = useRef({
    pageHidden: false,
    frozen: false,
    offline: !navigator.onLine,
  })
  const [snapshot, setSnapshot] = useState<{
    owner: typeof owner
    epoch: number
    view: ProjectDetailView
  } | null>(null)
  const idempotencyKeys = useRef(new Map<string, string>())

  const current = useCallback(
    () =>
      currentOwner.current === owner &&
      owner.active &&
      owner.identity !== null &&
      !availability.current.pageHidden &&
      !availability.current.frozen &&
      !availability.current.offline &&
      navigator.onLine &&
      document.visibilityState !== 'hidden',
    [owner],
  )

  const publish = useCallback(
    (view: ProjectDetailView) => {
      owner.view = view
      setSnapshot({ owner, epoch: owner.epoch, view })
    },
    [owner],
  )

  const refresh = useCallback(async () => {
    if (!projectId || !current() || owner.operation !== null) return
    owner.dirty = false
    owner.controller?.abort()
    const controller = new AbortController()
    owner.controller = controller
    const epoch = owner.epoch
    const revision = ++owner.read
    const accepts = () =>
      current() &&
      owner.epoch === epoch &&
      owner.read === revision &&
      !controller.signal.aborted
    let refreshedJob = owner.view.job
    publish({
      ...owner.view,
      project: null,
      branches: [],
      error: null,
      phase: 'loading',
    })
    try {
      // Retry only this already known Job. A failed poll is not evidence that
      // the operation ended, and a readback must never replay its POST.
      if (refreshedJob && !TERMINAL_JOBS.has(refreshedJob.status)) {
        const jobResponse = await api.get<JobResponse>(
          `/api/v1/jobs/${encodeURIComponent(refreshedJob.id)}`,
          {
            timeoutMs: 15_000,
            signal: controller.signal,
            validate: parseJobResponse,
          },
        )
        if (!accepts()) return
        const nextJob = projectJobMatches(
          jobResponse.data,
          projectId,
          refreshedJob.id,
        )
          ? safeJobView(jobResponse.data)
          : null
        if (nextJob === null) {
          publish({
            ...emptyProjectDetail('error'),
            job: refreshedJob,
            error: { code: 'PROJECT_JOB_RESPONSE_INVALID' },
          })
          return
        }
        refreshedJob = nextJob
      }
      const response = await api.get<ProjectResponse>(
        `/api/v1/projects/${encodeURIComponent(projectId)}`,
        {
          timeoutMs: 45_000,
          signal: controller.signal,
          validate: parseProjectResponse,
        },
      )
      if (!accepts()) return
      if (response.data.id !== projectId) {
        publish({
          ...emptyProjectDetail('error'),
          job: refreshedJob,
          error: { code: 'PROJECT_RESPONSE_INVALID' },
        })
        return
      }
      let branches: GitBranchData[] = []
      if (response.data.state === 'ready' && response.data.git?.is_repository) {
        const branchResponse = await api.get<GitBranchListResponse>(
          `/api/v1/projects/${encodeURIComponent(projectId)}/git/branches`,
          {
            timeoutMs: 30_000,
            signal: controller.signal,
            validate: parseGitBranchListResponse,
          },
        )
        if (!accepts()) return
        branches = branchResponse.data.branches
      }
      publish({
        ...owner.view,
        project: response.data,
        branches,
        job: refreshedJob,
        error: null,
        phase: 'ready',
      })
    } catch (value) {
      if (!accepts()) return
      const phase =
        value instanceof ApiError && [401, 403].includes(value.status)
          ? 'forbidden'
          : 'error'
      publish({
        ...emptyProjectDetail(phase),
        job: refreshedJob,
        error: safeApiError(value, 'CONTROL_PLANE_UNAVAILABLE'),
      })
    } finally {
      if (owner.controller === controller) owner.controller = null
    }
  }, [api, current, owner, projectId, publish])

  useEffect(() => {
    owner.active = true
    function invalidate() {
      owner.epoch += 1
      owner.read += 1
      owner.dirty = true
      owner.controller?.abort()
      owner.controller = null
      // This abandons local observation only. The server operation may continue.
      owner.operation = null
      publish(emptyProjectDetail('stale'))
    }
    function resumeIfDirty() {
      if (owner.dirty) void refresh()
    }
    function visibility() {
      if (document.visibilityState === 'hidden') invalidate()
      else resumeIfDirty()
    }
    function pageHide() {
      availability.current.pageHidden = true
      invalidate()
    }
    function pageShow() {
      availability.current.pageHidden = false
      resumeIfDirty()
    }
    function freeze() {
      availability.current.frozen = true
      invalidate()
    }
    function resume() {
      availability.current.frozen = false
      resumeIfDirty()
    }
    function offline() {
      availability.current.offline = true
      invalidate()
    }
    function online() {
      availability.current.offline = false
      resumeIfDirty()
    }
    if (owner.identity === null) publish(emptyProjectDetail('forbidden'))
    else if (!current()) publish(emptyProjectDetail('stale'))
    else void refresh()
    document.addEventListener('visibilitychange', visibility)
    document.addEventListener('freeze', freeze)
    document.addEventListener('resume', resume)
    window.addEventListener('pagehide', pageHide)
    window.addEventListener('pageshow', pageShow)
    window.addEventListener('offline', offline)
    window.addEventListener('online', online)
    return () => {
      owner.active = false
      owner.epoch += 1
      owner.read += 1
      owner.controller?.abort()
      owner.operation = null
      document.removeEventListener('visibilitychange', visibility)
      document.removeEventListener('freeze', freeze)
      document.removeEventListener('resume', resume)
      window.removeEventListener('pagehide', pageHide)
      window.removeEventListener('pageshow', pageShow)
      window.removeEventListener('offline', offline)
      window.removeEventListener('online', online)
    }
  }, [current, owner, publish, refresh])

  const available =
    identity !== null &&
    !availability.current.pageHidden &&
    !availability.current.frozen &&
    !availability.current.offline &&
    navigator.onLine &&
    document.visibilityState !== 'hidden'
  // A prior owner must never be visible during the render before effect cleanup.
  const view =
    snapshot?.owner === owner && snapshot.epoch === owner.epoch && available
      ? snapshot.view
      : emptyProjectDetail(
          identity === null ? 'forbidden' : available ? 'loading' : 'stale',
        )
  const job = view.job
  const phase = view.phase

  useEffect(() => {
    if (
      !projectId ||
      !job ||
      phase !== 'ready' ||
      TERMINAL_JOBS.has(job.status) ||
      !current()
    )
      return
    const epoch = owner.epoch
    const readRevision = owner.read
    const controller = new AbortController()
    let cancelled = false
    const accepts = () =>
      !cancelled &&
      !controller.signal.aborted &&
      current() &&
      owner.epoch === epoch &&
      owner.read === readRevision &&
      owner.view.phase === 'ready' &&
      owner.view.job?.id === job.id
    const timeout = window.setTimeout(() => {
      if (!accepts()) return
      void api
        .get<JobResponse>(`/api/v1/jobs/${encodeURIComponent(job.id)}`, {
          timeoutMs: 15_000,
          signal: controller.signal,
          validate: parseJobResponse,
        })
        .then((response) => {
          if (!accepts()) return
          const nextJob = projectJobMatches(response.data, projectId, job.id)
            ? safeJobView(response.data)
            : null
          if (nextJob === null) {
            publish({
              ...owner.view,
              error: { code: 'PROJECT_JOB_RESPONSE_INVALID' },
            })
            return
          }
          publish({ ...owner.view, job: nextJob })
          if (TERMINAL_JOBS.has(nextJob.status)) void refresh()
        })
        .catch((value: unknown) => {
          if (accepts())
            publish({
              ...owner.view,
              error: safeApiError(value, 'CONTROL_PLANE_UNAVAILABLE'),
            })
        })
    }, 750)
    return () => {
      cancelled = true
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [api, current, job, owner, phase, projectId, publish, refresh])

  async function mutate(path: string, body?: object) {
    if (
      !auth ||
      !projectId ||
      !current() ||
      owner.view.phase !== 'ready' ||
      owner.view.project?.state !== 'ready' ||
      owner.operation !== null ||
      (owner.view.job !== null && !TERMINAL_JOBS.has(owner.view.job.status))
    )
      return
    const operation = {}
    let terminalAcknowledged = false
    owner.operation = operation
    const epoch = owner.epoch
    owner.read += 1
    owner.controller?.abort()
    const accepts = () =>
      current() && owner.epoch === epoch && owner.operation === operation
    const requestKey = idempotencyKey(
      idempotencyKeys.current,
      identity + ':' + path,
      body ?? {},
    )
    publish({ ...owner.view, pending: path, error: null })
    try {
      const response = await api.post<JobResponse>(
        `/api/v1/projects/${encodeURIComponent(projectId)}/${path}`,
        {
          body,
          csrfToken: auth.csrf_token,
          idempotencyKey: requestKey.value,
          validate: parseJobResponse,
        },
      )
      if (!accepts()) return
      const nextJob = projectJobMatches(response.data, projectId)
        ? safeJobView(response.data)
        : null
      if (nextJob !== null) {
        idempotencyKeys.current.delete(requestKey.fingerprint)
        terminalAcknowledged = TERMINAL_JOBS.has(nextJob.status)
      }
      publish({
        ...owner.view,
        job: nextJob,
        error:
          nextJob === null ? { code: 'PROJECT_JOB_RESPONSE_INVALID' } : null,
      })
    } catch (value) {
      if (!accepts()) return
      if (receivedDefinitiveFailure(value))
        idempotencyKeys.current.delete(requestKey.fingerprint)
      publish({
        ...(value instanceof ApiError && [401, 403].includes(value.status)
          ? emptyProjectDetail('forbidden')
          : owner.view),
        error: safeApiError(value, 'PROJECT_OPERATION_FAILED'),
      })
    } finally {
      if (accepts()) {
        owner.operation = null
        publish({ ...owner.view, pending: null })
        if (terminalAcknowledged) void refresh()
      }
    }
  }

  const busy =
    view.phase !== 'ready' ||
    view.pending !== null ||
    (view.job !== null && !TERMINAL_JOBS.has(view.job.status))
  return {
    ...view,
    busy,
    loading: view.phase === 'loading',
    stale: view.phase === 'stale',
    mutate,
    refresh,
  }
}
