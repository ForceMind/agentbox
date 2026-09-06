import {
  AlertTriangle,
  Clipboard,
  Eye,
  EyeOff,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import {
  LocalizedApiError,
  OpaqueUserValue,
  TechnicalValue,
} from '../components/i18n'
import { useClaude, type ClaudeSessionView } from '../features/claude/useClaude'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, type Locale } from '../i18n'
import {
  claudeCatalog,
  type ClaudeMessageParameters,
} from '../i18n/catalogs/claude'

type ClaudeMessageKey = keyof ClaudeMessageParameters

const stateMessageKeys: Readonly<
  Record<ClaudeSessionView['state'], ClaudeMessageKey>
> = {
  running: 'claude.stateRunning',
  stopped: 'claude.stateStopped',
  starting: 'claude.stateStarting',
  needs_interaction: 'claude.stateNeedsInteraction',
  broken: 'claude.stateBroken',
  unknown: 'claude.stateUnknown',
}

const workspaceMessageKeys: Readonly<
  Record<ClaudeSessionView['workspace_state'], ClaudeMessageKey>
> = {
  unknown: 'claude.workspaceUnknown',
  requires_user_confirmation: 'claude.workspaceRequiresConfirmation',
  initialized_by_agentbox: 'claude.workspaceInitialized',
}

function stateTone(state: ClaudeSessionView['state']) {
  return state === 'running'
    ? ('good' as const)
    : state === 'stopped'
      ? ('muted' as const)
      : ('warning' as const)
}

export function ClaudePage({ locale = currentLocale() }: { locale?: Locale }) {
  const claude = useClaude()
  const [copied, setCopied] = useState<string | null>(null)
  const catalog = claudeCatalog.catalogs[locale]
  const message = (key: ClaudeMessageKey) => catalog[key]({})
  usePageTitle(message('claude.title'))

  async function copyAttach(session: ClaudeSessionView) {
    if (session.attach_command === null) return
    await navigator.clipboard.writeText(session.attach_command)
    setCopied(session.project_id)
    window.setTimeout(() => setCopied(null), 1500)
  }

  return (
    <>
      <PageHeader
        action={
          <button
            className="secondary-button"
            disabled={claude.refreshing || claude.pending.length > 0}
            onClick={() => void claude.refresh()}
            type="button"
          >
            <RefreshCw size={17} aria-hidden="true" />{' '}
            {message('claude.refresh')}
          </button>
        }
        description={message('claude.description')}
        eyebrow={message('claude.eyebrow')}
        title={message('claude.title')}
      />

      {claude.view.status === 'loading' && (
        <p className="loading-panel" role="status">
          {message('claude.loading')}
        </p>
      )}
      {claude.view.status === 'error' && (
        <section className="error-panel">
          <AlertTriangle aria-hidden="true" />
          <div>
            <h2>{message('claude.statusUnavailable')}</h2>
            <LocalizedApiError error={claude.view.error} locale={locale} />
          </div>
        </section>
      )}
      {claude.view.status === 'loaded' && (
        <>
          <section
            className="claude-runtime-grid"
            aria-label={message('claude.installationAria')}
          >
            <article className="runtime-card">
              <div className="runtime-card-heading">
                <div>
                  <p className="eyebrow">{message('claude.claudeCode')}</p>
                  <h2>{message('claude.installation')}</h2>
                </div>
                <Sparkles aria-hidden="true" />
              </div>
              <dl className="runtime-details">
                <div>
                  <dt>{message('claude.installed')}</dt>
                  <dd>
                    {claude.view.data.status.installed
                      ? message('claude.yes')
                      : message('claude.no')}
                  </dd>
                </div>
                <div>
                  <dt>{message('claude.version')}</dt>
                  <dd>
                    {claude.view.data.status.version === null ? (
                      message('claude.unknown')
                    ) : (
                      <TechnicalValue value={claude.view.data.status.version} />
                    )}
                  </dd>
                </div>
                <div>
                  <dt>{message('claude.authentication')}</dt>
                  <dd>
                    <TechnicalValue
                      value={claude.view.data.status.authentication}
                    />
                  </dd>
                </div>
                <div>
                  <dt>{message('claude.remoteCapability')}</dt>
                  <dd>
                    <TechnicalValue
                      value={
                        claude.view.data.status.capabilities.remote_control
                      }
                    />
                  </dd>
                </div>
              </dl>
            </article>
            <article className="runtime-card">
              <div className="runtime-card-heading">
                <div>
                  <p className="eyebrow">{message('claude.persistence')}</p>
                  <h2>{message('claude.tmux')}</h2>
                </div>
                <StatusBadge
                  tone={
                    claude.view.data.status.tmux_installed ? 'good' : 'warning'
                  }
                >
                  {claude.view.data.status.tmux_installed
                    ? message('claude.installed')
                    : message('claude.unavailable')}
                </StatusBadge>
              </div>
              <dl className="runtime-details">
                <div>
                  <dt>{message('claude.version')}</dt>
                  <dd>
                    {claude.view.data.status.tmux_version === null ? (
                      message('claude.unknown')
                    ) : (
                      <TechnicalValue
                        value={claude.view.data.status.tmux_version}
                      />
                    )}
                  </dd>
                </div>
                <div>
                  <dt>{message('claude.managedSessions')}</dt>
                  <dd>
                    <TechnicalValue
                      value={String(claude.view.data.status.managed_sessions)}
                    />
                  </dd>
                </div>
                <div>
                  <dt>{message('claude.unmanagedSessions')}</dt>
                  <dd>
                    <TechnicalValue
                      value={String(claude.view.data.status.unmanaged_sessions)}
                    />
                  </dd>
                </div>
                <div>
                  <dt>{message('claude.workspaceWarnings')}</dt>
                  <dd>
                    <TechnicalValue
                      value={String(
                        claude.view.data.status.workspace_interaction_warnings,
                      )}
                    />
                  </dd>
                </div>
              </dl>
            </article>
          </section>

          <div className="section-heading">
            <div>
              <p className="eyebrow">{message('claude.projects')}</p>
              <h2>{message('claude.remoteSessions')}</h2>
            </div>
          </div>
          {claude.view.data.sessions.length === 0 ? (
            <section className="empty-state">
              <h2>{message('claude.noConfiguredProjects')}</h2>
              <p>{message('claude.noConfiguredProjectsDescription')}</p>
            </section>
          ) : (
            <section
              className="claude-session-grid"
              aria-label={message('claude.sessionsAria')}
            >
              {claude.view.data.sessions.map((session) => {
                const output = claude.outputs[session.project_id]
                const actionError = claude.actionErrors[session.project_id]
                const actionPending = claude.pending.some(
                  (operation) => operation.projectId === session.project_id,
                )
                return (
                  <article
                    className="claude-session-card"
                    key={session.project_id}
                  >
                    <div className="runtime-card-heading">
                      <div>
                        <p className="eyebrow">{message('claude.project')}</p>
                        <h2>
                          <OpaqueUserValue value={session.display_name} />
                        </h2>
                      </div>
                      <StatusBadge tone={stateTone(session.state)}>
                        {message(stateMessageKeys[session.state])}
                      </StatusBadge>
                    </div>
                    <dl className="runtime-details compact-details">
                      <div>
                        <dt>{message('claude.tmux')}</dt>
                        <dd>
                          {session.tmux_running
                            ? message('claude.stateRunning')
                            : message('claude.stateStopped')}
                        </dd>
                      </div>
                      <div>
                        <dt>{message('claude.remoteReadiness')}</dt>
                        <dd>
                          {session.remote_readiness === 'ready'
                            ? message('claude.ready')
                            : message('claude.unknown')}
                        </dd>
                      </div>
                      <div>
                        <dt>{message('claude.workspaceTrust')}</dt>
                        <dd>
                          {message(
                            workspaceMessageKeys[session.workspace_state],
                          )}
                        </dd>
                      </div>
                    </dl>
                    {session.state === 'needs_interaction' && (
                      <div className="interaction-notice" role="status">
                        {message('claude.interactionNotice')}
                      </div>
                    )}
                    <div className="attach-box">
                      <span>{message('claude.attachLabel')}</span>
                      <code>
                        {session.attach_command === null ? (
                          message('claude.unknown')
                        ) : (
                          <TechnicalValue value={session.attach_command} />
                        )}
                      </code>
                      <button
                        className="secondary-button"
                        disabled={session.attach_command === null}
                        onClick={() => void copyAttach(session)}
                        type="button"
                      >
                        <Clipboard size={16} aria-hidden="true" />{' '}
                        {copied === session.project_id
                          ? message('claude.copied')
                          : message('claude.copyAttach')}
                      </button>
                    </div>
                    <div className="action-row">
                      {!session.tmux_running ? (
                        <button
                          className="primary-button action-button"
                          disabled={actionPending || claude.refreshing}
                          onClick={() =>
                            void claude.sessionAction(
                              session.project_id,
                              'start',
                            )
                          }
                          type="button"
                        >
                          {claude.pending.some(
                            (operation) =>
                              operation.projectId === session.project_id &&
                              operation.operation === 'start',
                          )
                            ? message('claude.starting')
                            : message('claude.startSession')}
                        </button>
                      ) : (
                        <button
                          className="secondary-button action-button"
                          disabled={actionPending || claude.refreshing}
                          onClick={() =>
                            void claude.sessionAction(
                              session.project_id,
                              'stop',
                            )
                          }
                          type="button"
                        >
                          {claude.pending.some(
                            (operation) =>
                              operation.projectId === session.project_id &&
                              operation.operation === 'stop',
                          )
                            ? message('claude.stopping')
                            : message('claude.stopSession')}
                        </button>
                      )}
                    </div>
                    <p className="stop-note">{message('claude.stopNote')}</p>
                    {actionError && (
                      <section className="error-panel claude-action-error">
                        <AlertTriangle aria-hidden="true" />
                        <div>
                          <h3>{message('claude.actionFailed')}</h3>
                          <LocalizedApiError
                            error={actionError}
                            locale={locale}
                          />
                        </div>
                      </section>
                    )}
                    <div className="sensitive-output">
                      <div>
                        <strong>{message('claude.recentOutput')}</strong>
                        <StatusBadge tone="warning">
                          {message('claude.sensitive')}
                        </StatusBadge>
                      </div>
                      <p>{message('claude.outputDescription')}</p>
                      {!output ? (
                        <button
                          className="secondary-button"
                          disabled={
                            !session.tmux_running ||
                            actionPending ||
                            claude.refreshing
                          }
                          onClick={() =>
                            void claude.revealOutput(session.project_id)
                          }
                          type="button"
                        >
                          <Eye size={16} aria-hidden="true" />{' '}
                          {claude.pending.some(
                            (operation) =>
                              operation.projectId === session.project_id &&
                              operation.operation === 'output',
                          )
                            ? message('claude.outputLoading')
                            : message('claude.reveal')}
                        </button>
                      ) : (
                        <>
                          <pre>
                            {output.output ? (
                              <OpaqueUserValue value={output.output} />
                            ) : (
                              message('claude.noRecentOutput')
                            )}
                          </pre>
                          {output.truncated && (
                            <p>{message('claude.outputTruncated')}</p>
                          )}
                          <button
                            className="secondary-button"
                            onClick={() =>
                              claude.hideOutput(session.project_id)
                            }
                            type="button"
                          >
                            <EyeOff size={16} aria-hidden="true" />{' '}
                            {message('claude.hide')}
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                )
              })}
            </section>
          )}
        </>
      )}
    </>
  )
}
