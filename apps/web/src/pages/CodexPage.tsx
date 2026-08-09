import { AlertTriangle, Bot, Clipboard, EyeOff, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useCodex } from '../features/codex/useCodex'
import { usePageTitle } from '../hooks/usePageTitle'

function label(value: string) {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function CodexPage() {
  usePageTitle('Codex')
  const codex = useCodex()
  const [confirmPair, setConfirmPair] = useState(false)
  const [copied, setCopied] = useState(false)

  async function copyPairCode() {
    if (!codex.pair) return
    await navigator.clipboard.writeText(codex.pair.pair_code)
    setCopied(true)
  }

  async function confirmGenerate() {
    setConfirmPair(false)
    setCopied(false)
    await codex.generatePairCode()
  }

  const status =
    codex.view.status === 'loaded' ? codex.view.response.data : null
  const startAllowed =
    status?.capabilities.start === 'supported' &&
    status.remote_state !== 'running'
  const stopAllowed =
    status?.capabilities.stop === 'supported' &&
    status.remote_state !== 'stopped'
  const pairAllowed =
    status?.capabilities.pair === 'supported' &&
    status.authentication !== 'unauthenticated'

  return (
    <>
      <PageHeader
        action={
          status ? (
            <StatusBadge
              tone={status.remote_state === 'running' ? 'good' : 'muted'}
            >
              {label(status.remote_state)}
            </StatusBadge>
          ) : undefined
        }
        description="Capability-aware Codex standalone and Remote Control management."
        eyebrow="Runtime"
        title="Codex"
      />

      {codex.view.status === 'loading' && (
        <p className="loading-panel" role="status">
          Detecting Codex safely…
        </p>
      )}
      {codex.view.status === 'error' && (
        <section className="error-panel" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <h2>Codex status unavailable</h2>
            <p>{codex.view.error.message}</p>
          </div>
        </section>
      )}
      {status && (
        <div className="codex-layout">
          <section
            className="runtime-card"
            aria-labelledby="codex-installation"
          >
            <div className="runtime-card-heading">
              <div>
                <p className="eyebrow">Installation</p>
                <h2 id="codex-installation">Codex CLI</h2>
              </div>
              <Bot aria-hidden="true" />
            </div>
            <dl className="runtime-details">
              <div>
                <dt>Installed</dt>
                <dd>{status.installed ? 'Installed' : 'Not Installed'}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{status.version ?? 'Unknown'}</dd>
              </div>
              <div>
                <dt>Installation</dt>
                <dd>{label(status.installation_type)}</dd>
              </div>
              <div>
                <dt>Authentication</dt>
                <dd>{label(status.authentication)}</dd>
              </div>
              <div>
                <dt>Executable</dt>
                <dd className="path-value">
                  {status.selected_executable ?? 'Unavailable'}
                </dd>
              </div>
            </dl>
          </section>

          <section className="runtime-card" aria-labelledby="remote-control">
            <div className="runtime-card-heading">
              <div>
                <p className="eyebrow">Remote Control</p>
                <h2 id="remote-control">Lifecycle</h2>
              </div>
              <StatusBadge
                tone={
                  status.capabilities.remote_control === 'supported'
                    ? 'good'
                    : 'warning'
                }
              >
                {label(status.capabilities.remote_control)}
              </StatusBadge>
            </div>
            <p className="runtime-copy">
              Observed state: <strong>{label(status.remote_state)}</strong>{' '}
              <span>({label(status.remote_confidence)})</span>
            </p>
            <div className="action-row">
              <button
                className="primary-button action-button"
                disabled={!startAllowed || codex.pending !== null}
                onClick={() => void codex.remoteAction('start')}
                type="button"
              >
                {codex.pending === 'start' ? 'Starting…' : 'Start Remote'}
              </button>
              <button
                className="secondary-button action-button"
                disabled={!stopAllowed || codex.pending !== null}
                onClick={() => void codex.remoteAction('stop')}
                type="button"
              >
                {codex.pending === 'stop' ? 'Stopping…' : 'Stop Remote'}
              </button>
              <button
                aria-label="Refresh Codex status"
                className="icon-button"
                disabled={codex.pending !== null}
                onClick={() => void codex.refresh()}
                type="button"
              >
                <RefreshCw size={18} />
              </button>
            </div>
          </section>

          <section
            className="runtime-card pair-card"
            aria-labelledby="pair-device"
          >
            <div className="runtime-card-heading">
              <div>
                <p className="eyebrow">Pair Device</p>
                <h2 id="pair-device">Temporary access</h2>
              </div>
              <StatusBadge tone="warning">Sensitive</StatusBadge>
            </div>
            <p className="runtime-copy">
              Generate only when pairing a device. AgentBox never saves the
              code.
            </p>
            {!codex.pair && (
              <button
                className="primary-button action-button"
                disabled={!pairAllowed || codex.pending !== null}
                onClick={() => setConfirmPair(true)}
                type="button"
              >
                {codex.pending === 'pair' ? 'Generating…' : 'Pair New Device'}
              </button>
            )}
            {codex.pair && (
              <div className="pair-secret" role="status">
                <p>Sensitive temporary code</p>
                <code>{codex.pair.pair_code}</code>
                <p className="pair-note">
                  Hidden from this page automatically after 90 seconds. This is
                  not the Codex-reported expiry.
                </p>
                <div className="action-row">
                  <button
                    className="secondary-button action-button"
                    onClick={() => void copyPairCode()}
                    type="button"
                  >
                    <Clipboard size={17} aria-hidden="true" />
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                  <button
                    className="secondary-button action-button"
                    onClick={codex.clearPair}
                    type="button"
                  >
                    <EyeOff size={17} aria-hidden="true" /> Hide
                  </button>
                </div>
              </div>
            )}
          </section>

          <section
            className="runtime-card diagnostics-card"
            aria-labelledby="diagnostics"
          >
            <div className="runtime-card-heading">
              <div>
                <p className="eyebrow">Diagnostics</p>
                <h2 id="diagnostics">Compatibility findings</h2>
              </div>
            </div>
            {status.diagnostics.length === 0 ? (
              <p className="runtime-copy">No current adapter findings.</p>
            ) : (
              <ul className="diagnostic-list">
                {status.diagnostics.map((finding) => (
                  <li key={finding.code}>
                    <StatusBadge
                      tone={finding.severity === 'info' ? 'muted' : 'warning'}
                    >
                      {finding.severity}
                    </StatusBadge>
                    <div>
                      <strong>{finding.summary}</strong>
                      {finding.remediation && <p>{finding.remediation}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {codex.actionError && (
        <section className="error-panel codex-action-error" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <h2>Codex action failed</h2>
            <p>{codex.actionError.message}</p>
          </div>
        </section>
      )}

      {confirmPair && (
        <div className="modal-backdrop" role="presentation">
          <section
            aria-labelledby="pair-confirm-title"
            aria-modal="true"
            className="modal"
            role="dialog"
          >
            <p className="eyebrow">Sensitive action</p>
            <h2 id="pair-confirm-title">
              Generate a new temporary pairing code?
            </h2>
            <p>The code is shown once and kept only in this page's memory.</p>
            <div className="action-row">
              <button
                className="primary-button action-button"
                onClick={() => void confirmGenerate()}
                type="button"
              >
                Generate Code
              </button>
              <button
                className="secondary-button action-button"
                onClick={() => setConfirmPair(false)}
                type="button"
              >
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
