import { useCallback, useEffect, useRef, useState } from 'react'

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

export function useProject(projectId: string | undefined) {
  const { api, auth } = useAuth()
  const [project, setProject] = useState<ProjectData | null>(null)
  const [error, setError] = useState<ProjectApiErrorView | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [branches, setBranches] = useState<GitBranchData[]>([])
  const [job, setJob] = useState<ProjectJobView | null>(null)
  const idempotencyKeys = useRef(new Map<string, string>())

  const refresh = useCallback(async () => {
    if (!projectId) return
    try {
      const response = await api.get<ProjectResponse>(
        `/api/v1/projects/${encodeURIComponent(projectId)}`,
        { timeoutMs: 45_000, validate: parseProjectResponse },
      )
      setProject(response.data)
      if (response.data.state === 'ready' && response.data.git?.is_repository) {
        const branchResponse = await api.get<GitBranchListResponse>(
          `/api/v1/projects/${encodeURIComponent(projectId)}/git/branches`,
          { timeoutMs: 30_000, validate: parseGitBranchListResponse },
        )
        setBranches(branchResponse.data.branches)
      } else {
        setBranches([])
      }
      setError(null)
    } catch (value) {
      setError(safeApiError(value, 'CONTROL_PLANE_UNAVAILABLE'))
    }
  }, [api, projectId])

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

  async function mutate(path: string, body?: object) {
    if (!auth || !projectId) return
    const requestBody = body ?? {}
    const requestKey = idempotencyKey(
      idempotencyKeys.current,
      projectId + ':' + path,
      requestBody,
    )
    setPending(path)
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
      idempotencyKeys.current.delete(requestKey.fingerprint)
      const nextJob = safeJobView(response.data)
      setJob(nextJob)
      setError(
        nextJob === null ? { code: 'PROJECT_JOB_RESPONSE_INVALID' } : null,
      )
    } catch (value) {
      if (receivedDefinitiveFailure(value)) {
        idempotencyKeys.current.delete(requestKey.fingerprint)
      }
      setError(safeApiError(value, 'PROJECT_OPERATION_FAILED'))
    } finally {
      setPending(null)
    }
  }

  const busy =
    pending !== null || (job !== null && !TERMINAL_JOBS.has(job.status))
  return { branches, busy, error, job, mutate, pending, project, refresh }
}
