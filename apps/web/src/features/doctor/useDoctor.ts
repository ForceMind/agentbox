import { useEffect, useState } from 'react'

import { technicalValue } from '../../i18n'
import { ApiError } from '../../lib/api'
import { DoctorResponse, parseDoctorResponse } from '../../lib/contracts'
import { useAuth } from '../auth/AuthContext'

const SAFE_ERROR_CODE = /^[A-Z][A-Z0-9_]{0,79}$/
const SAFE_REQUEST_ID = /^[A-Za-z0-9._:-]{1,96}$/
const SAFE_FINDING_CODE = /^[A-Z][A-Z0-9_]{0,79}$/

export type DoctorDisplayError = Readonly<{
  code: string
  requestId?: string
}>

type DoctorViewData = Readonly<{
  status: DoctorResponse['data']['status']
  checks: Readonly<DoctorResponse['data']['checks']>
  policy: Readonly<{
    environment: DoctorResponse['data']['policy']['environment']
    bind_host: string | null
    bind_port: number
    session_ttl_seconds: number
    session_idle_ttl_seconds: number
    login_rate_limit: number
    login_rate_window_seconds: number
    login_lock_duration_seconds: number
  }>
  codex: Readonly<{
    installed: DoctorResponse['data']['codex']['installed']
    version: string | null
    installation_type: DoctorResponse['data']['codex']['installation_type']
    remote_control: DoctorResponse['data']['codex']['remote_control']
    remote_state: DoctorResponse['data']['codex']['remote_state']
    findings: readonly string[]
  }>
  claude: Readonly<{
    installed: DoctorResponse['data']['claude']['installed']
    version: string | null
    authentication: DoctorResponse['data']['claude']['authentication']
    remote_control: DoctorResponse['data']['claude']['remote_control']
    tmux_installed: DoctorResponse['data']['claude']['tmux_installed']
    tmux_version: string | null
    managed_sessions: number
    unmanaged_sessions: number
    workspace_interaction_warnings: number
    findings: readonly string[]
  }>
  projects: Readonly<{
    project_root: string
    project_count: number
    git_installed: DoctorResponse['data']['projects']['git_installed']
    git_version: string | null
    github_cli_installed: DoctorResponse['data']['projects']['github_cli_installed']
    github_authentication: DoctorResponse['data']['projects']['github_authentication']
    findings: readonly string[]
  }>
}>

export type DoctorViewResponse = Readonly<{ data: DoctorViewData }>

export type DoctorState =
  | { status: 'loading' }
  | { status: 'loaded'; response: DoctorViewResponse }
  | { status: 'error'; error: DoctorDisplayError }

function safeTechnical(value: string | null): string | null {
  if (value === null) return null
  try {
    return technicalValue(value).value
  } catch {
    return null
  }
}

function safeErrorCode(value: unknown): string | null {
  return typeof value === 'string' && SAFE_ERROR_CODE.test(value) ? value : null
}

function safeRequestId(value: unknown): string | null {
  return typeof value === 'string' && SAFE_REQUEST_ID.test(value) ? value : null
}

/** Only fixed-format diagnostic identifiers can leave the transport boundary. */
export function isSafeDoctorFindingCode(value: unknown): value is string {
  return typeof value === 'string' && SAFE_FINDING_CODE.test(value)
}

function projectFindings(findings: readonly string[]): readonly string[] {
  return Object.freeze(findings.filter(isSafeDoctorFindingCode))
}

/** ApiError.message is server prose and is intentionally absent from this view. */
export function projectDoctorError(error: unknown): DoctorDisplayError {
  if (!(error instanceof ApiError))
    return Object.freeze({ code: 'DOCTOR_UNAVAILABLE' })
  const code = safeErrorCode(error.code) ?? 'DOCTOR_UNAVAILABLE'
  const requestId = safeRequestId(error.requestId)
  return Object.freeze({
    code,
    ...(requestId === null ? {} : { requestId }),
  })
}

/**
 * Copies only page-owned fields into React state. Parsed response envelopes,
 * diagnostics prose and unstructured findings remain outside the view model.
 */
export function projectDoctorResponse(
  response: DoctorResponse,
): DoctorViewResponse {
  const data = response.data
  return Object.freeze({
    data: Object.freeze({
      status: data.status,
      checks: Object.freeze({ ...data.checks }),
      policy: Object.freeze({
        environment: data.policy.environment,
        bind_host: safeTechnical(data.policy.bind_host),
        bind_port: data.policy.bind_port,
        session_ttl_seconds: data.policy.session_ttl_seconds,
        session_idle_ttl_seconds: data.policy.session_idle_ttl_seconds,
        login_rate_limit: data.policy.login_rate_limit,
        login_rate_window_seconds: data.policy.login_rate_window_seconds,
        login_lock_duration_seconds: data.policy.login_lock_duration_seconds,
      }),
      codex: Object.freeze({
        installed: data.codex.installed,
        version: safeTechnical(data.codex.version),
        installation_type: data.codex.installation_type,
        remote_control: data.codex.remote_control,
        remote_state: data.codex.remote_state,
        findings: projectFindings(data.codex.findings),
      }),
      claude: Object.freeze({
        installed: data.claude.installed,
        version: safeTechnical(data.claude.version),
        authentication: data.claude.authentication,
        remote_control: data.claude.remote_control,
        tmux_installed: data.claude.tmux_installed,
        tmux_version: safeTechnical(data.claude.tmux_version),
        managed_sessions: data.claude.managed_sessions,
        unmanaged_sessions: data.claude.unmanaged_sessions,
        workspace_interaction_warnings:
          data.claude.workspace_interaction_warnings,
        findings: projectFindings(data.claude.findings),
      }),
      projects: Object.freeze({
        // The configured Project root may be user Unicode and is rendered as an
        // opaque, untranslated value rather than technical/server prose.
        project_root: data.projects.project_root,
        project_count: data.projects.project_count,
        git_installed: data.projects.git_installed,
        git_version: safeTechnical(data.projects.git_version),
        github_cli_installed: data.projects.github_cli_installed,
        github_authentication: data.projects.github_authentication,
        findings: projectFindings(data.projects.findings),
      }),
    }),
  })
}

export function useDoctor(): DoctorState {
  const { api } = useAuth()
  const [state, setState] = useState<DoctorState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void api
      .get<DoctorResponse>('/api/v1/doctor', {
        signal: controller.signal,
        timeoutMs: 90_000,
        validate: parseDoctorResponse,
      })
      .then((response) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'loaded',
            response: projectDoctorResponse(response),
          })
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ status: 'error', error: projectDoctorError(error) })
        }
      })
    return () => controller.abort()
  }, [api])

  return state
}
