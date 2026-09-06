import { AlertTriangle, Bot, Clipboard, EyeOff, RefreshCw } from 'lucide-react'
import {
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useRef,
  useState,
} from 'react'

import { LocalizedApiError } from '../components/i18n/LocalizedApiError'
import { SafeTechnicalValue } from '../components/i18n/SafeTechnicalValue'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { useCodex } from '../features/codex/useCodex'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  currentLocale,
  formatMessage,
  type Locale,
  type MessageArguments,
  type ParameterFreeMessageKey,
} from '../i18n'
import type {
  CapabilityState,
  CodexStatusData,
  RemoteState,
} from '../lib/contracts'

type CodexMessageKey = Extract<ParameterFreeMessageKey, `codex.${string}`>

function copy(locale: Locale, key: CodexMessageKey): string {
  return formatMessage(locale, ...([key, {}] as MessageArguments))
}

const CAPABILITY_COPY = {
  supported: 'codex.capabilitySupported',
  unsupported: 'codex.capabilityUnsupported',
  unknown: 'codex.capabilityUnknown',
} as const satisfies Record<CapabilityState, CodexMessageKey>

const REMOTE_COPY = {
  running: 'codex.remoteRunning',
  stopped: 'codex.remoteStopped',
  broken: 'codex.remoteBroken',
  unknown: 'codex.remoteUnknown',
} as const satisfies Record<RemoteState, CodexMessageKey>

const CONFIDENCE_COPY = {
  reported: 'codex.confidenceReported',
  inferred: 'codex.confidenceInferred',
  unknown: 'codex.confidenceUnknown',
} as const satisfies Record<
  CodexStatusData['remote_confidence'],
  CodexMessageKey
>

const INSTALLATION_COPY = {
  standalone: 'codex.installationStandalone',
  npm: 'codex.installationNpm',
  conflict: 'codex.installationConflict',
  unknown: 'codex.installationUnknown',
} as const satisfies Record<
  CodexStatusData['installation_type'],
  CodexMessageKey
>

const AUTHENTICATION_COPY = {
  authenticated: 'codex.authenticationAuthenticated',
  unauthenticated: 'codex.authenticationUnauthenticated',
  unknown: 'codex.authenticationUnknown',
} as const satisfies Record<CodexStatusData['authentication'], CodexMessageKey>

const SEVERITY_COPY = {
  critical: 'codex.severityCritical',
  high: 'codex.severityHigh',
  medium: 'codex.severityMedium',
  low: 'codex.severityLow',
  warning: 'codex.severityWarning',
  info: 'codex.severityInfo',
} as const satisfies Record<
  CodexStatusData['diagnostics'][number]['severity'],
  CodexMessageKey
>

export function CodexPage() {
  const locale = currentLocale()
  const title = copy(locale, 'codex.title')
  usePageTitle(title)
  const codex = useCodex()
  const [confirmPair, setConfirmPair] = useState(false)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>(
    'idle',
  )
  const pairTriggerRef = useRef<HTMLButtonElement>(null)
  const generateButtonRef = useRef<HTMLButtonElement>(null)
  const cancelButtonRef = useRef<HTMLButtonElement>(null)
  const pairRevealRef = useRef<HTMLDivElement>(null)
  const actionErrorRef = useRef<HTMLElement>(null)
  const restorePairTriggerRef = useRef(true)
  const pairGenerationRequestedRef = useRef(false)

  useEffect(() => {
    if (!confirmPair) return
    const trigger = pairTriggerRef.current
    generateButtonRef.current?.focus()
    return () => {
      if (restorePairTriggerRef.current) trigger?.focus()
    }
  }, [confirmPair])

  useEffect(() => {
    if (!pairGenerationRequestedRef.current) return
    if (codex.pair) {
      pairGenerationRequestedRef.current = false
      pairRevealRef.current?.focus()
    } else if (codex.actionError) {
      pairGenerationRequestedRef.current = false
      actionErrorRef.current?.focus()
    }
  }, [codex.actionError, codex.pair])

  async function copyPairCode() {
    if (!codex.pair) return
    setCopyState('idle')
    try {
      await navigator.clipboard.writeText(codex.pair.pair_code)
      setCopyState('copied')
    } catch {
      setCopyState('error')
    }
  }

  async function confirmGenerate() {
    restorePairTriggerRef.current = false
    pairGenerationRequestedRef.current = true
    setConfirmPair(false)
    setCopyState('idle')
    await codex.generatePairCode()
  }

  function openPairConfirmation() {
    restorePairTriggerRef.current = true
    setConfirmPair(true)
  }

  function closePairConfirmation() {
    setConfirmPair(false)
  }

  function handlePairDialogKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      closePairConfirmation()
      return
    }
    if (event.key !== 'Tab') return

    const first = generateButtonRef.current
    const last = cancelButtonRef.current
    if (!first || !last) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    } else if (!event.currentTarget.contains(document.activeElement)) {
      event.preventDefault()
      first.focus()
    }
  }

  function clearPair() {
    setCopyState('idle')
    codex.clearPair()
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
      <div
        aria-hidden={confirmPair ? true : undefined}
        inert={confirmPair ? true : undefined}
      >
        <PageHeader
          action={
            status ? (
              <StatusBadge
                tone={status.remote_state === 'running' ? 'good' : 'muted'}
              >
                {copy(locale, REMOTE_COPY[status.remote_state])}
              </StatusBadge>
            ) : undefined
          }
          description={copy(locale, 'codex.description')}
          eyebrow={copy(locale, 'codex.eyebrow')}
          title={title}
        />

        {codex.view.status === 'loading' && (
          <p className="loading-panel" role="status">
            {copy(locale, 'codex.loading')}
          </p>
        )}
        {codex.view.status === 'error' && (
          <section className="error-panel" role="alert">
            <AlertTriangle aria-hidden="true" />
            <div>
              <h2>{copy(locale, 'codex.statusUnavailableTitle')}</h2>
              <p>
                <LocalizedApiError
                  error={codex.view.error}
                  locale={locale}
                  role="presentation"
                />
              </p>
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
                  <p className="eyebrow">
                    {copy(locale, 'codex.installationEyebrow')}
                  </p>
                  <h2 id="codex-installation">
                    {copy(locale, 'codex.installationTitle')}
                  </h2>
                </div>
                <Bot aria-hidden="true" />
              </div>
              <dl className="runtime-details">
                <div>
                  <dt>{copy(locale, 'codex.installedLabel')}</dt>
                  <dd>
                    {copy(
                      locale,
                      status.installed
                        ? 'codex.installedYes'
                        : 'codex.installedNo',
                    )}
                  </dd>
                </div>
                <div>
                  <dt>{copy(locale, 'codex.versionLabel')}</dt>
                  <dd>
                    {status.version ? (
                      <SafeTechnicalValue
                        fallback={copy(locale, 'codex.capabilityUnknown')}
                        value={status.version}
                      />
                    ) : (
                      copy(locale, 'codex.capabilityUnknown')
                    )}
                  </dd>
                </div>
                <div>
                  <dt>{copy(locale, 'codex.installationTypeLabel')}</dt>
                  <dd>
                    {copy(locale, INSTALLATION_COPY[status.installation_type])}
                  </dd>
                </div>
                <div>
                  <dt>{copy(locale, 'codex.authenticationLabel')}</dt>
                  <dd>
                    {copy(locale, AUTHENTICATION_COPY[status.authentication])}
                  </dd>
                </div>
                <div>
                  <dt>{copy(locale, 'codex.executableLabel')}</dt>
                  <dd className="path-value">
                    {status.selected_executable ? (
                      <SafeTechnicalValue
                        fallback={copy(locale, 'codex.capabilityUnknown')}
                        value={status.selected_executable}
                      />
                    ) : (
                      copy(locale, 'codex.unavailable')
                    )}
                  </dd>
                </div>
              </dl>
            </section>

            <section className="runtime-card" aria-labelledby="remote-control">
              <div className="runtime-card-heading">
                <div>
                  <p className="eyebrow">
                    {copy(locale, 'codex.remoteEyebrow')}
                  </p>
                  <h2 id="remote-control">
                    {copy(locale, 'codex.remoteTitle')}
                  </h2>
                </div>
                <StatusBadge
                  tone={
                    status.capabilities.remote_control === 'supported'
                      ? 'good'
                      : 'warning'
                  }
                >
                  {copy(
                    locale,
                    CAPABILITY_COPY[status.capabilities.remote_control],
                  )}
                </StatusBadge>
              </div>
              <p className="runtime-copy">
                {copy(locale, 'codex.observedStateLabel')}:{' '}
                <strong>
                  {copy(locale, REMOTE_COPY[status.remote_state])}
                </strong>{' '}
                <span>
                  ({copy(locale, 'codex.confidenceLabel')}:{' '}
                  {copy(locale, CONFIDENCE_COPY[status.remote_confidence])})
                </span>
              </p>
              <div className="action-row">
                <button
                  className="primary-button action-button"
                  disabled={!startAllowed || codex.pending !== null}
                  onClick={() => void codex.remoteAction('start')}
                  type="button"
                >
                  {copy(
                    locale,
                    codex.pending === 'start'
                      ? 'codex.startingRemote'
                      : 'codex.startRemote',
                  )}
                </button>
                <button
                  className="secondary-button action-button"
                  disabled={!stopAllowed || codex.pending !== null}
                  onClick={() => void codex.remoteAction('stop')}
                  type="button"
                >
                  {copy(
                    locale,
                    codex.pending === 'stop'
                      ? 'codex.stoppingRemote'
                      : 'codex.stopRemote',
                  )}
                </button>
                <button
                  aria-label={copy(locale, 'codex.refreshStatusLabel')}
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
                  <p className="eyebrow">{copy(locale, 'codex.pairEyebrow')}</p>
                  <h2 id="pair-device">{copy(locale, 'codex.pairTitle')}</h2>
                </div>
                <StatusBadge tone="warning">
                  {copy(locale, 'codex.sensitive')}
                </StatusBadge>
              </div>
              <p className="runtime-copy">
                {copy(locale, 'codex.pairDescription')}
              </p>
              {!codex.pair && (
                <button
                  className="primary-button action-button"
                  disabled={!pairAllowed || codex.pending !== null}
                  onClick={openPairConfirmation}
                  ref={pairTriggerRef}
                  type="button"
                >
                  {copy(
                    locale,
                    codex.pending === 'pair'
                      ? 'codex.generatingPair'
                      : 'codex.pairNewDevice',
                  )}
                </button>
              )}
              {codex.pair && (
                <div
                  className="pair-secret"
                  ref={pairRevealRef}
                  role="status"
                  tabIndex={-1}
                >
                  <p>{copy(locale, 'codex.pairSecretLabel')}</p>
                  <code>
                    <SafeTechnicalValue
                      fallback={copy(locale, 'codex.capabilityUnknown')}
                      value={codex.pair.pair_code}
                    />
                  </code>
                  <p className="pair-note">
                    {copy(locale, 'codex.pairTimeoutNote')}
                  </p>
                  <div className="action-row">
                    <button
                      className="secondary-button action-button"
                      onClick={() => void copyPairCode()}
                      type="button"
                    >
                      <Clipboard size={17} aria-hidden="true" />
                      {copy(
                        locale,
                        copyState === 'copied' ? 'codex.copied' : 'codex.copy',
                      )}
                    </button>
                    <button
                      className="secondary-button action-button"
                      onClick={clearPair}
                      type="button"
                    >
                      <EyeOff size={17} aria-hidden="true" />
                      {copy(locale, 'codex.hide')}
                    </button>
                  </div>
                  {copyState === 'error' && (
                    <p className="pair-note" role="alert">
                      {copy(locale, 'codex.copyFailed')}
                    </p>
                  )}
                </div>
              )}
            </section>

            <section
              className="runtime-card diagnostics-card"
              aria-labelledby="diagnostics"
            >
              <div className="runtime-card-heading">
                <div>
                  <p className="eyebrow">
                    {copy(locale, 'codex.diagnosticsEyebrow')}
                  </p>
                  <h2 id="diagnostics">
                    {copy(locale, 'codex.diagnosticsTitle')}
                  </h2>
                </div>
              </div>
              {status.diagnostics.length === 0 ? (
                <p className="runtime-copy">
                  {copy(locale, 'codex.diagnosticsEmpty')}
                </p>
              ) : (
                <ul className="diagnostic-list">
                  {status.diagnostics.map((finding, index) => (
                    <li key={`${finding.code}:${index}`}>
                      <StatusBadge
                        tone={finding.severity === 'info' ? 'muted' : 'warning'}
                      >
                        {copy(locale, SEVERITY_COPY[finding.severity])}
                      </StatusBadge>
                      <div>
                        <LocalizedApiError
                          className="path-value"
                          error={{ code: finding.code }}
                          locale={locale}
                          role="status"
                          showRequestId={false}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}

        {codex.actionError && (
          <section
            className="error-panel codex-action-error"
            ref={actionErrorRef}
            role="alert"
            tabIndex={-1}
          >
            <AlertTriangle aria-hidden="true" />
            <div>
              <h2>{copy(locale, 'codex.actionFailedTitle')}</h2>
              <p>
                <LocalizedApiError
                  error={codex.actionError}
                  locale={locale}
                  role="presentation"
                />
              </p>
            </div>
          </section>
        )}
      </div>

      {confirmPair && (
        <div className="modal-backdrop" role="presentation">
          <section
            aria-labelledby="pair-confirm-title"
            aria-modal="true"
            className="modal"
            onKeyDown={handlePairDialogKeyDown}
            role="dialog"
          >
            <p className="eyebrow">{copy(locale, 'codex.confirmEyebrow')}</p>
            <h2 id="pair-confirm-title">
              {copy(locale, 'codex.confirmTitle')}
            </h2>
            <p>{copy(locale, 'codex.confirmDescription')}</p>
            <div className="action-row">
              <button
                className="primary-button action-button"
                onClick={() => void confirmGenerate()}
                ref={generateButtonRef}
                type="button"
              >
                {copy(locale, 'codex.generateCode')}
              </button>
              <button
                className="secondary-button action-button"
                onClick={closePairConfirmation}
                ref={cancelButtonRef}
                type="button"
              >
                {formatMessage(locale, 'common.cancel', {})}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
