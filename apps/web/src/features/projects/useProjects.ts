import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../../lib/api'
import {
  ProjectData,
  ProjectJobResponse,
  ProjectListResponse,
  ProjectResponse,
  parseProjectJobResponse,
  parseProjectListResponse,
  parseProjectResponse,
} from '../../lib/contracts'

function key() {
  return `web-${crypto.randomUUID()}`
}

export function useProjects() {
  const { api, auth } = useAuth()
  const [projects, setProjects] = useState<ProjectData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.get<ProjectListResponse>('/api/v1/projects', {
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
      setProjects((current) => [...current, response.data.project])
      setError(null)
    } catch (value) {
      setError(value as ApiError)
    } finally {
      setPending(false)
    }
  }

  return { clone, create, error, loading, pending, projects, refresh }
}

export function useProject(projectId: string | undefined) {
  const { api, auth } = useAuth()
  const [project, setProject] = useState<ProjectData | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!projectId) return
    try {
      const response = await api.get<ProjectResponse>(
        `/api/v1/projects/${encodeURIComponent(projectId)}`,
        { validate: parseProjectResponse },
      )
      setProject(response.data)
      setError(null)
    } catch (value) {
      setError(value as ApiError)
    }
  }, [api, projectId])

  useEffect(() => void refresh(), [refresh])

  async function mutate(path: string, body?: object) {
    if (!auth || !projectId) return
    setPending(path)
    try {
      await api.post(
        `/api/v1/projects/${encodeURIComponent(projectId)}/${path}`,
        {
          body,
          csrfToken: auth.csrf_token,
          idempotencyKey: key(),
        },
      )
      setError(null)
    } catch (value) {
      setError(value as ApiError)
    } finally {
      setPending(null)
    }
  }

  return { error, mutate, pending, project, refresh }
}
