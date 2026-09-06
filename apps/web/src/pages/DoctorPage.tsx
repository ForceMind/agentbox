import { Activity, Check, X } from 'lucide-react'

import { LocalizedApiError, TechnicalValue } from '../components/i18n'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import {
  isSafeDoctorFindingCode,
  useDoctor,
  type DoctorViewResponse,
} from '../features/doctor/useDoctor'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, formatNumber, type Locale } from '../i18n'
import {
  doctorCatalog,
  type DoctorMessageParameters,
} from '../i18n/catalogs/doctor'
import type {
  AuthenticationState,
  CapabilityState,
  RemoteState,
} from '../lib/contracts'

type DoctorMessageKey = keyof DoctorMessageParameters
type DoctorStaticMessageKey = Exclude<DoctorMessageKey, 'doctor.projectsCount'>
type DoctorData = DoctorViewResponse['data']

const CHECK_MESSAGE_KEYS = {
  configuration_valid: 'doctor.configurationValid',
  database_reachable: 'doctor.databaseReachable',
  migrations_current: 'doctor.migrationsCurrent',
  admin_initialized: 'doctor.adminInitialized',
  control_plane_ready: 'doctor.controlPlaneReady',
} as const satisfies Record<keyof DoctorData['checks'], DoctorStaticMessageKey>

const CAPABILITY_MESSAGE_KEYS = {
  supported: 'doctor.capabilitySupported',
  unsupported: 'doctor.capabilityUnsupported',
  unknown: 'doctor.unknown',
} as const satisfies Record<CapabilityState, DoctorStaticMessageKey>

const REMOTE_MESSAGE_KEYS = {
  running: 'doctor.remoteRunning',
  stopped: 'doctor.remoteStopped',
  broken: 'doctor.remoteBroken',
  unknown: 'doctor.unknown',
} as const satisfies Record<RemoteState, DoctorStaticMessageKey>

const AUTHENTICATION_MESSAGE_KEYS = {
  authenticated: 'doctor.authenticationAuthenticated',
  unauthenticated: 'doctor.authenticationUnauthenticated',
  unknown: 'doctor.unknown',
} as const satisfies Record<AuthenticationState, DoctorStaticMessageKey>

const KNOWN_FINDING_MESSAGE_KEYS = {
  CODEX_NOT_INSTALLED: 'doctor.findingCodexNotInstalled',
  CODEX_EXECUTABLE_OWNER_MISMATCH: 'doctor.findingCodexOwnerMismatch',
  CODEX_VERSION_UNAVAILABLE: 'doctor.findingCodexVersionUnavailable',
  CODEX_CAPABILITY_PROBE_FAILED: 'doctor.findingCodexCapabilityProbeFailed',
  CODEX_LEGACY_UNIT_PRESENT: 'doctor.findingCodexLegacyUnitPresent',
  CODEX_REMOTE_STATUS_UNSUPPORTED: 'doctor.findingCodexRemoteStatusUnsupported',
  CODEX_ALTERNATIVE_INVALID: 'doctor.findingCodexAlternativeInvalid',
  CODEX_EXECUTABLE_INVALID: 'doctor.findingCodexExecutableInvalid',
  CODEX_MULTIPLE_EXECUTABLES: 'doctor.findingCodexMultipleExecutables',
  CODEX_INSTALLATION_CONFLICT: 'doctor.findingCodexInstallationConflict',
  CLAUDE_NOT_INSTALLED: 'doctor.findingClaudeNotInstalled',
  CLAUDE_VERSION_UNKNOWN: 'doctor.findingClaudeVersionUnknown',
  CLAUDE_REMOTE_CAPABILITY_UNKNOWN:
    'doctor.findingClaudeRemoteCapabilityUnknown',
  PROJECT_WORKSPACE_UNAVAILABLE: 'doctor.findingProjectWorkspaceUnavailable',
} as const satisfies Readonly<Record<string, DoctorStaticMessageKey>>

function TechnicalOrUnknown({
  value,
  unknown,
}: {
  value: string | null
  unknown: string
}) {
  return <SafeTechnicalValue fallback={unknown} value={value} />
}

function DiagnosticFindings({
  findings,
  locale,
}: {
  findings: readonly string[]
  locale: Locale
}) {
  const catalog = doctorCatalog.catalogs[locale]
  if (findings.length === 0) return null

  return (
    <ul
      aria-label={catalog['doctor.findingsAria']({})}
      className="diagnostic-list"
    >
      {findings.map((finding, index) => {
        const knownKey = (
          KNOWN_FINDING_MESSAGE_KEYS as Readonly<
            Record<string, DoctorStaticMessageKey>
          >
        )[finding]
        const safeCode = isSafeDoctorFindingCode(finding) ? finding : null
        return (
          <li key={`${finding}:${index}`}>
            {catalog[knownKey ?? 'doctor.findingUnknown']({})}
            {safeCode === null ? null : (
              <>
                {' '}
                <TechnicalValue value={safeCode} />
              </>
            )}
          </li>
        )
      })}
    </ul>
  )
}

export function DoctorPage({ locale = currentLocale() }: { locale?: Locale }) {
  const doctor = useDoctor()
  const catalog = doctorCatalog.catalogs[locale]
  const message = (key: DoctorStaticMessageKey) => catalog[key]({})
  usePageTitle(message('doctor.title'))

  return (
    <>
      <PageHeader
        action={
          doctor.status === 'loaded' ? (
            <StatusBadge
              tone={
                doctor.response.data.status === 'ready' ? 'good' : 'warning'
              }
            >
              {doctor.response.data.status === 'ready'
                ? message('doctor.ready')
                : message('doctor.notReady')}
            </StatusBadge>
          ) : undefined
        }
        description={message('doctor.description')}
        eyebrow={message('doctor.eyebrow')}
        title={message('doctor.title')}
      />

      {doctor.status === 'loading' && (
        <p className="loading-panel" role="status">
          {message('doctor.loading')}
        </p>
      )}
      {doctor.status === 'error' && (
        <section className="error-panel" role="alert">
          <Activity aria-hidden="true" />
          <div>
            <h2>{message('doctor.unavailable')}</h2>
            <LocalizedApiError
              error={doctor.error}
              locale={locale}
              role="none"
            />
          </div>
        </section>
      )}
      {doctor.status === 'loaded' && (
        <>
          <section
            className="check-list"
            aria-label={message('doctor.checksAria')}
          >
            {Object.entries(doctor.response.data.checks).map(([key, value]) => (
              <article key={key}>
                <span
                  className={value ? 'check-icon good' : 'check-icon bad'}
                  aria-hidden="true"
                >
                  {value ? <Check size={17} /> : <X size={17} />}
                </span>
                <span>
                  {message(
                    CHECK_MESSAGE_KEYS[key as keyof DoctorData['checks']],
                  )}
                </span>
                <StatusBadge tone={value ? 'good' : 'warning'}>
                  {value ? message('doctor.ready') : message('doctor.notReady')}
                </StatusBadge>
              </article>
            ))}
          </section>
          <section
            className="runtime-card doctor-runtime"
            aria-labelledby="doctor-codex"
          >
            <div className="runtime-card-heading">
              <div>
                <p className="eyebrow">{message('doctor.runtimeDiagnostic')}</p>
                <h2 id="doctor-codex">{message('doctor.codexTitle')}</h2>
              </div>
              <StatusBadge
                tone={doctor.response.data.codex.installed ? 'good' : 'warning'}
              >
                {doctor.response.data.codex.installed === true
                  ? message('doctor.installed')
                  : doctor.response.data.codex.installed === false
                    ? message('doctor.notInstalled')
                    : message('doctor.unknown')}
              </StatusBadge>
            </div>
            <dl className="runtime-details">
              <div>
                <dt>{message('doctor.version')}</dt>
                <dd>
                  <TechnicalOrUnknown
                    unknown={message('doctor.unknown')}
                    value={doctor.response.data.codex.version}
                  />
                </dd>
              </div>
              <div>
                <dt>{message('doctor.installation')}</dt>
                <dd>
                  <TechnicalValue
                    value={doctor.response.data.codex.installation_type}
                  />
                </dd>
              </div>
              <div>
                <dt>{message('doctor.remoteCapability')}</dt>
                <dd>
                  {message(
                    CAPABILITY_MESSAGE_KEYS[
                      doctor.response.data.codex.remote_control
                    ],
                  )}
                </dd>
              </div>
              <div>
                <dt>{message('doctor.remoteState')}</dt>
                <dd>
                  {message(
                    REMOTE_MESSAGE_KEYS[
                      doctor.response.data.codex.remote_state
                    ],
                  )}
                </dd>
              </div>
            </dl>
            <DiagnosticFindings
              findings={doctor.response.data.codex.findings}
              locale={locale}
            />
          </section>
          <section
            className="runtime-card doctor-runtime"
            aria-labelledby="doctor-claude"
          >
            <div className="runtime-card-heading">
              <div>
                <p className="eyebrow">{message('doctor.runtimeDiagnostic')}</p>
                <h2 id="doctor-claude">{message('doctor.claudeTitle')}</h2>
              </div>
              <StatusBadge
                tone={
                  doctor.response.data.claude.installed &&
                  doctor.response.data.claude.tmux_installed
                    ? 'good'
                    : 'warning'
                }
              >
                {doctor.response.data.claude.installed === true &&
                doctor.response.data.claude.tmux_installed === true
                  ? message('doctor.available')
                  : message('doctor.unknown')}
              </StatusBadge>
            </div>
            <dl className="runtime-details">
              <div>
                <dt>{message('doctor.claudeVersion')}</dt>
                <dd>
                  <TechnicalOrUnknown
                    unknown={message('doctor.unknown')}
                    value={doctor.response.data.claude.version}
                  />
                </dd>
              </div>
              <div>
                <dt>{message('doctor.authentication')}</dt>
                <dd>
                  {message(
                    AUTHENTICATION_MESSAGE_KEYS[
                      doctor.response.data.claude.authentication
                    ],
                  )}
                </dd>
              </div>
              <div>
                <dt>{message('doctor.remoteCapability')}</dt>
                <dd>
                  {message(
                    CAPABILITY_MESSAGE_KEYS[
                      doctor.response.data.claude.remote_control
                    ],
                  )}
                </dd>
              </div>
              <div>
                <dt>{message('doctor.tmuxVersion')}</dt>
                <dd>
                  <TechnicalOrUnknown
                    unknown={message('doctor.unknown')}
                    value={doctor.response.data.claude.tmux_version}
                  />
                </dd>
              </div>
              <div>
                <dt>{message('doctor.managedSessions')}</dt>
                <dd>
                  {formatNumber(
                    locale,
                    doctor.response.data.claude.managed_sessions,
                  )}
                </dd>
              </div>
              <div>
                <dt>{message('doctor.unmanagedSessions')}</dt>
                <dd>
                  {formatNumber(
                    locale,
                    doctor.response.data.claude.unmanaged_sessions,
                  )}
                </dd>
              </div>
              <div>
                <dt>{message('doctor.workspaceWarnings')}</dt>
                <dd>
                  {formatNumber(
                    locale,
                    doctor.response.data.claude.workspace_interaction_warnings,
                  )}
                </dd>
              </div>
            </dl>
            <DiagnosticFindings
              findings={doctor.response.data.claude.findings}
              locale={locale}
            />
          </section>
          <section
            className="runtime-card doctor-runtime"
            aria-labelledby="doctor-projects"
          >
            <div className="runtime-card-heading">
              <div>
                <p className="eyebrow">
                  {message('doctor.workspaceDiagnostic')}
                </p>
                <h2 id="doctor-projects">{message('doctor.projectsTitle')}</h2>
              </div>
              <StatusBadge
                tone={
                  doctor.response.data.projects.github_cli_installed
                    ? 'good'
                    : 'warning'
                }
              >
                {catalog['doctor.projectsCount']({
                  count: formatNumber(
                    locale,
                    doctor.response.data.projects.project_count,
                  ),
                })}
              </StatusBadge>
            </div>
            <dl className="runtime-details">
              <div>
                <dt>{message('doctor.projectRoot')}</dt>
                <dd>
                  <SafeTechnicalValue
                    fallback={message('doctor.unknown')}
                    value={doctor.response.data.projects.project_root}
                  />
                </dd>
              </div>
              <div>
                <dt>{message('doctor.git')}</dt>
                <dd>
                  <TechnicalOrUnknown
                    unknown={message('doctor.unknown')}
                    value={doctor.response.data.projects.git_version}
                  />
                </dd>
              </div>
              <div>
                <dt>{message('doctor.githubCli')}</dt>
                <dd>
                  {doctor.response.data.projects.github_cli_installed === true
                    ? message('doctor.installed')
                    : doctor.response.data.projects.github_cli_installed ===
                        false
                      ? message('doctor.notInstalled')
                      : message('doctor.unknown')}
                </dd>
              </div>
              <div>
                <dt>{message('doctor.githubAuthentication')}</dt>
                <dd>
                  {message(
                    AUTHENTICATION_MESSAGE_KEYS[
                      doctor.response.data.projects.github_authentication
                    ],
                  )}
                </dd>
              </div>
            </dl>
            <DiagnosticFindings
              findings={doctor.response.data.projects.findings}
              locale={locale}
            />
          </section>
          <p className="scope-note">{message('doctor.scopeNote')}</p>
        </>
      )}
    </>
  )
}
