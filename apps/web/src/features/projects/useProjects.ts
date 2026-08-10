import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
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

type JobView = Pick<JobData, 'id' | 'status'> &
  Partial<Pick<JobData, 'error_code' | 'error_summary' | 'phase' | 'progress'>>

const TERMINAL_JOBS = new Set([
  'succeeded',
  'failed',
  'cancelled',
  'needs_attention',
])

function key() {
  return `web-${crypto.randomUUID()}`
}

export function useProjects() {
  const { api, auth } = useAuth()
  const [projects, setProjects] = useState<ProjectData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState(false)
  const [job, setJob] = useState<JobView | null>(null)

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
      setError(value as ApiError)
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
          setJob(response.data)
          if (TERMINAL_JOBS.has(response.data.status)) void refresh()
        })
        .catch((value: unknown) => {
          if (!cancelled) setError(value as ApiError)
        })
    }, 750)
    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [api, job, refresh])

  async function create(name: string) {
    if (!auth) return
    setPending(true)
    try {
      const response = await api.post<ProjectJobResponse>('/api/v1/projects', {
        body: { name },
        csrfToken: auth.csrf_token,
        idempotencyKey: key(),
        validate: parseProjectJobResponse,
      })
      setJob(response.data.job)
      setProjects((current) => [...current, response.data.project])
      setError(null)
    } catch (value) {
      setError(value as ApiError)
    } finally {
      setPending(false)
    }
  }

  async function clone(repositoryUrl: string, name: string) {
    if (!auth) return
    setPending(true)
    try {
      const response = await api.post<ProjectJobResponse>(
        '/api/v1/projects/clone',
        {
          body: { repository_url: repositoryUrl, name: name || null },
          csrfToken: auth.csrf_token,
          idempotencyKey: key(),
          validate: parseProjectJobResponse,
        },
      )
      setJob(response.data.job)
      setProjects((current) => [...current, response.data.project])
      setError(null)
    } catch (value) {
      setError(value as ApiError)
    } finally {
      setPending(false)
    }
  }

  return { clone, create, error, job, loading, pending, projects, refresh }
}

export function useProject(projectId: string | undefined) {
  const { api, auth } = useAuth()
  const [project, setProject] = useState<ProjectData | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [branches, setBranches] = useState<GitBranchData[]>([])
  const [job, setJob] = useState<JobView | null>(null)

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
      setError(value as ApiError)
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
          setJob(response.data)
          if (TERMINAL_JOBS.has(response.data.status)) void refresh()
        })
        .catch((value: unknown) => {
          if (!cancelled) setError(value as ApiError)
        })
    }, 750)
    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [api, job, refresh])

  async function mutate(path: string, body?: object) {
    if (!auth || !projectId) return
    setPending(path)
    try {
      const response = await api.post<JobResponse>(
        `/api/v1/projects/${encodeURIComponent(projectId)}/${path}`,
        {
          body,
          csrfToken: auth.csrf_token,
          idempotencyKey: key(),
          validate: parseJobResponse,
        },
      )
      setJob(response.data)
      setError(null)
    } catch (value) {
      setError(value as ApiError)
    } finally {
      setPending(null)
    }
  }

  const busy =
    pending !== null || (job !== null && !TERMINAL_JOBS.has(job.status))
  return { branches, busy, error, job, mutate, pending, project, refresh }
}
