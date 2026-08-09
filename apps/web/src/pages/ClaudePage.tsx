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
import { useClaude } from '../features/claude/useClaude'
import { usePageTitle } from '../hooks/usePageTitle'
import { ClaudeSessionData } from '../lib/contracts'

const stateLabels: Record<ClaudeSessionData['state'], string> = {
  running: 'Running',
  stopped: 'Stopped',
  starting: 'Starting',
  needs_interaction: 'Needs Interaction',
  broken: 'Broken',
  unknown: 'Unknown',
}

function stateTone(state: ClaudeSessionData['state']) {
  return state === 'running'
    ? ('good' as const)
    : state === 'stopped'
      ? ('muted' as const)
      : ('warning' as const)
}

export function ClaudePage() {
  const claude = useClaude()
  const [copied, setCopied] = useState<string | null>(null)
  usePageTitle('Claude')

  async function copyAttach(session: ClaudeSessionData) {
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
            onClick={() => void claude.refresh()}
            type="button"
          >
            <RefreshCw size={17} aria-hidden="true" /> Refresh
          </button>
        }
        description="Project-scoped Claude Code Remote sessions persisted by the Runtime user's tmux server."
        eyebrow="Runtime"
        title="Claude"
      />

      {claude.view.status === 'loading' && (
        <p className="loading-panel" role="status">
          Inspecting Claude and managed sessions…
        </p>
      )}
      {claude.view.status === 'error' && (
        <section className="error-panel" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <h2>Claude status unavailable</h2>
            <p>{claude.view.error.message}</p>
          </div>
        </section>
      )}
      {claude.view.status === 'loaded' && (
        <>
          <section
            className="claude-runtime-grid"
            aria-label="Claude installation status"
          >
            <article className="runtime-card">
              <div className="runtime-card-heading">
                <div>
                  <p className="eyebrow">Claude Code</p>
                  <h2>Installation</h2>
                </div>
                <Sparkles aria-hidden="true" />
              </div>
              <dl className="runtime-details">
                <div>
                  <dt>Installed</dt>
                  <dd>{claude.view.data.status.installed ? 'Yes' : 'No'}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{claude.view.data.status.version ?? 'Unknown'}</dd>
                </div>
                <div>
                  <dt>Authentication</dt>
                  <dd>{claude.view.data.status.authentication}</dd>
                </div>
                <div>
                  <dt>Remote capability</dt>
                  <dd>{claude.view.data.status.capabilities.remote_control}</dd>
                </div>
              </dl>
            </article>
            <article className="runtime-card">
              <div className="runtime-card-heading">
                <div>
                  <p className="eyebrow">Persistence</p>
                  <h2>tmux</h2>
                </div>
                <StatusBadge
                  tone={
                    claude.view.data.status.tmux_installed ? 'good' : 'warning'
                  }
                >
                  {claude.view.data.status.tmux_installed
                    ? 'Installed'
                    : 'Unavailable'}
                </StatusBadge>
              </div>
              <dl className="runtime-details">
                <div>
                  <dt>Version</dt>
                  <dd>{claude.view.data.status.tmux_version ?? 'Unknown'}</dd>
                </div>
                <div>
                  <dt>Managed sessions</dt>
                  <dd>{claude.view.data.status.managed_sessions}</dd>
                </div>
                <div>
                  <dt>Unmanaged sessions</dt>
                  <dd>{claude.view.data.status.unmanaged_sessions}</dd>
                </div>
                <div>
                  <dt>Workspace warnings</dt>
                  <dd>
                    {claude.view.data.status.workspace_interaction_warnings}
                  </dd>
                </div>
              </dl>
            </article>
          </section>

          <div className="section-heading">
            <div>
              <p className="eyebrow">Projects</p>
              <h2>Remote sessions</h2>
            </div>
          </div>
          {claude.view.data.sessions.length === 0 ? (
            <section className="empty-state">
              <h2>No configured projects</h2>
              <p>
                Phase 6 only lists existing immediate directories under the
                configured project root.
              </p>
            </section>
          ) : (
            <section
              className="claude-session-grid"
              aria-label="Claude project sessions"
            >
              {claude.view.data.sessions.map((session) => {
                const output = claude.outputs[session.project_id]
                const actionPending =
                  claude.pending?.endsWith(`:${session.project_id}`) ?? false
                return (
                  <article
                    className="claude-session-card"
                    key={session.project_id}
                  >
                    <div className="runtime-card-heading">
                      <div>
                        <p className="eyebrow">Project</p>
                        <h2>{session.display_name}</h2>
                      </div>
                      <StatusBadge tone={stateTone(session.state)}>
                        {stateLabels[session.state]}
                      </StatusBadge>
                    </div>
                    <dl className="runtime-details compact-details">
                      <div>
                        <dt>tmux</dt>
                        <dd>{session.tmux_running ? 'Running' : 'Stopped'}</dd>
                      </div>
                      <div>
                        <dt>Remote readiness</dt>
                        <dd>
                          {session.remote_readiness === 'ready'
                            ? 'Ready'
                            : 'Unknown'}
                        </dd>
                      </div>
                      <div>
                        <dt>Workspace Trust</dt>
                        <dd>{session.workspace_state.replaceAll('_', ' ')}</dd>
                      </div>
                    </dl>
                    {session.state === 'needs_interaction' && (
                      <div className="interaction-notice" role="status">
                        Claude requires terminal interaction before Remote
                        Control can continue. AgentBox never accepts Workspace
                        Trust automatically. Attach, confirm the project, then
                        exit the interactive Claude session and start Remote
                        Control again.
                      </div>
                    )}
                    <div className="attach-box">
                      <span>Attach from the Runtime user's terminal</span>
                      <code>{session.attach_command}</code>
                      <button
                        className="secondary-button"
                        onClick={() => void copyAttach(session)}
                        type="button"
                      >
                        <Clipboard size={16} aria-hidden="true" />{' '}
                        {copied === session.project_id
                          ? 'Copied'
                          : 'Copy attach command'}
                      </button>
                    </div>
                    <div className="action-row">
                      {!session.tmux_running ? (
                        <button
                          className="primary-button action-button"
                          disabled={actionPending}
                          onClick={() =>
                            void claude.sessionAction(
                              session.project_id,
                              'start',
                            )
                          }
                          type="button"
                        >
                          {claude.pending === `start:${session.project_id}`
                            ? 'Starting…'
                            : 'Start Session'}
                        </button>
                      ) : (
                        <button
                          className="secondary-button action-button"
                          disabled={actionPending}
                          onClick={() =>
                            void claude.sessionAction(
                              session.project_id,
                              'stop',
                            )
                          }
                          type="button"
                        >
                          {claude.pending === `stop:${session.project_id}`
                            ? 'Stopping…'
                            : 'Stop Session'}
                        </button>
                      )}
                    </div>
                    <p className="stop-note">
                      Stopping ends only this Claude/tmux session. It does not
                      delete the project.
                    </p>
                    <div className="sensitive-output">
                      <div>
                        <strong>Recent session output</strong>
                        <StatusBadge tone="warning">Sensitive</StatusBadge>
                      </div>
                      <p>
                        May contain project or model output. It is fetched only
                        when revealed.
                      </p>
                      {!output ? (
                        <button
                          className="secondary-button"
                          disabled={!session.tmux_running || actionPending}
                          onClick={() =>
                            void claude.revealOutput(session.project_id)
                          }
                          type="button"
                        >
                          <Eye size={16} aria-hidden="true" />{' '}
                          {claude.pending === `output:${session.project_id}`
                            ? 'Loading…'
                            : 'Reveal'}
                        </button>
                      ) : (
                        <>
                          <pre>{output.output || 'No recent output.'}</pre>
                          {output.truncated && (
                            <p>Output was truncated to the safety limit.</p>
                          )}
                          <button
                            className="secondary-button"
                            onClick={() =>
                              claude.hideOutput(session.project_id)
                            }
                            type="button"
                          >
                            <EyeOff size={16} aria-hidden="true" /> Hide
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
      {claude.actionError && (
        <section className="error-panel claude-action-error" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <h2>Claude action failed</h2>
            <p>{claude.actionError.message}</p>
          </div>
        </section>
      )}
    </>
  )
}
