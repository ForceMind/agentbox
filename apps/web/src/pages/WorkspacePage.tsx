import { AlertTriangle, MonitorUp, RefreshCw, ShieldAlert } from 'lucide-react'
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react'

import {
  LocalizedApiError,
  OpaqueUserValue,
  TechnicalValue,
} from '../components/i18n'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { MAX_INPUT_BYTES } from '../features/workspace/wawCryptoProfile'
import type {
  WorkspaceNotice,
  WorkspacePageModel,
} from '../features/workspace/workspaceView'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  currentLocale,
  formatMessage,
  type Locale,
  type MessageArguments,
  type ParameterFreeMessageKey,
} from '../i18n'
import './WorkspacePage.css'

type WorkspaceMessageKey = Extract<
  ParameterFreeMessageKey,
  `workspace.${string}`
>

function copy(locale: Locale, key: WorkspaceMessageKey): string {
  return formatMessage(locale, ...([key, {}] as MessageArguments))
}

const NOTICE_COPY = {
  START_CONFIRMED: 'workspace.noticeStartConfirmed',
  STOP_CONFIRMED: 'workspace.noticeStopConfirmed',
  RUNTIME_RECOVERY_REQUIRED: 'workspace.noticeRecoveryRequired',
} as const satisfies Record<WorkspaceNotice, WorkspaceMessageKey>

const TERMINAL_STATUS_COPY = {
  IDLE: 'workspace.terminalIdle',
  ACQUIRING_TICKET: 'workspace.terminalAcquiringTicket',
  AUTHORIZING_TRUST: 'workspace.terminalAuthorizingTrust',
  CONNECTING: 'workspace.terminalConnecting',
  HANDSHAKING: 'workspace.terminalHandshaking',
  CONNECTED: 'workspace.terminalConnected',
  DETACHING: 'workspace.terminalDetaching',
  DETACHED: 'workspace.terminalDetached',
  STOPPING: 'workspace.terminalStopping',
  STOPPED: 'workspace.terminalStopped',
  FENCED: 'workspace.terminalFenced',
  UNAVAILABLE: 'workspace.terminalUnavailable',
} as const satisfies Record<
  WorkspacePageModel['attachment']['status'],
  WorkspaceMessageKey
>

const LIFECYCLE_STATE_COPY = {
  STARTING: 'workspace.stateStarting',
  RUNNING: 'workspace.stateRunning',
  NEEDS_INTERACTION: 'workspace.stateNeedsInteraction',
  TRUST_REQUIRED: 'workspace.stateTrustRequired',
  LOGIN_REQUIRED: 'workspace.stateLoginRequired',
  STOPPING: 'workspace.stateStopping',
  EXITED: 'workspace.stateExited',
  STOPPED: 'workspace.stateStopped',
  MISSING: 'workspace.stateMissing',
  COLLISION: 'workspace.stateCollision',
  BROKEN: 'workspace.stateBroken',
  UNKNOWN: 'workspace.stateUnknown',
} as const satisfies Readonly<Record<string, WorkspaceMessageKey>>

function lifecycleCopy(locale: Locale, state: string | null): string {
  if (state && Object.hasOwn(LIFECYCLE_STATE_COPY, state)) {
    return copy(
      locale,
      LIFECYCLE_STATE_COPY[state as keyof typeof LIFECYCLE_STATE_COPY],
    )
  }
  return copy(locale, 'workspace.unloaded')
}

function inputResultNotice(
  locale: Locale,
  outcome: WorkspacePageModel['attachment']['lastInputOutcome'],
): string | null {
  if (outcome === null) return null
  if (
    outcome.state === 'rejected' &&
    outcome.reasonCode === 'INPUT_RATE_LIMITED'
  ) {
    return copy(locale, 'workspace.inputRateLimited')
  }
  if (
    outcome.state === 'write_uncertain' ||
    outcome.state === 'local_uncertain' ||
    outcome.state === 'rejected'
  ) {
    return copy(locale, 'workspace.inputUncertain')
  }
  return null
}

export function WorkspacePage({ model }: { model: WorkspacePageModel }) {
  const locale = currentLocale()
  usePageTitle(copy(locale, 'workspace.title'))
  const { setTerminalInputClearer } = model
  const stopDialog = useRef<HTMLDialogElement>(null)
  const terminalInput = useRef<HTMLInputElement>(null)
  const composingTerminalInput = useRef(false)
  const [inputNotice, setInputNotice] = useState<string | null>(null)
  const busy = model.pending !== null
  const metadata =
    model.runtimeView.status === 'loaded'
      ? model.runtimeView.response.data
      : null
  const statusReceivedAt =
    model.runtimeView.status === 'loaded'
      ? new Date(model.runtimeView.receivedAt)
      : null
  const selectedProject = model.projects.find(
    (project) => project.id === model.selectedProjectId,
  )
  const lifecycleCode = model.lifecycleState
  const attachmentStatus = model.attachment.status
  const attachmentStatusCopy = copy(
    locale,
    TERMINAL_STATUS_COPY[attachmentStatus],
  )
  const settledInputNotice = inputResultNotice(
    locale,
    model.attachment.lastInputOutcome,
  )
  const attachmentTone =
    attachmentStatus === 'CONNECTED'
      ? 'good'
      : attachmentStatus === 'FENCED' || attachmentStatus === 'UNAVAILABLE'
        ? 'warning'
        : 'muted'
  const terminalInputScope = [
    model.workspaceId ?? '',
    model.generation ?? '',
    model.attachment.attached?.attachmentId ?? '',
    attachmentStatus === 'CONNECTED' ? 'connected' : 'closed',
  ].join(':')

  useEffect(() => {
    const dialog = stopDialog.current
    if (model.stopTarget && dialog && !dialog.open) dialog.showModal()
    if (!model.stopTarget && dialog?.open) dialog.close()
  }, [model.stopTarget])

  useLayoutEffect(() => {
    const clear = () => {
      if (terminalInput.current) terminalInput.current.value = ''
      composingTerminalInput.current = false
    }
    setTerminalInputClearer(clear)
    return () => setTerminalInputClearer(null)
  }, [setTerminalInputClearer])

  useLayoutEffect(() => {
    if (terminalInput.current) terminalInput.current.value = ''
    composingTerminalInput.current = false
    setInputNotice(null)
  }, [terminalInputScope])

  function submitInput(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const input = terminalInput.current
    if (!input || !model.canInput || busy || composingTerminalInput.current)
      return
    const value = `${input.value}\r`
    const encoded = new TextEncoder().encode(value)
    const tooLong = encoded.byteLength > MAX_INPUT_BYTES
    encoded.fill(0)
    if (tooLong) {
      setInputNotice(copy(locale, 'workspace.inputTooLong'))
      return
    }
    input.value = ''
    setInputNotice(null)
    void model.sendInput(value)
  }

  return (
    <>
      <PageHeader
        eyebrow={copy(locale, 'workspace.eyebrow')}
        title={copy(locale, 'workspace.title')}
        description={copy(locale, 'workspace.description')}
      />
      <section
        className="runtime-card workspace-selection-card"
        aria-labelledby="workspace-selection"
      >
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">
              {copy(locale, 'workspace.selectionEyebrow')}
            </p>
            <h2 id="workspace-selection">
              {copy(locale, 'workspace.selectionTitle')}
            </h2>
          </div>
          <MonitorUp aria-hidden="true" />
        </div>
        <div className="project-forms">
          <label>
            {copy(locale, 'workspace.readyProject')}
            <select
              aria-label={copy(locale, 'workspace.readyProject')}
              value={model.selectedProjectId}
              onChange={(event) => model.selectProject(event.target.value)}
              disabled={model.projectsLoading || model.projects.length === 0}
            >
              {!model.projectsLoading &&
                model.projects.length > 0 &&
                !model.selectedProjectId && (
                  <option value="">
                    {copy(locale, 'workspace.selectProject')}
                  </option>
                )}
              {model.projectsLoading && (
                <option value="">
                  {copy(locale, 'workspace.loadingProjects')}
                </option>
              )}
              {!model.projectsLoading && model.projects.length === 0 && (
                <option value="">
                  {copy(locale, 'workspace.noReadyProjects')}
                </option>
              )}
              {model.projects.map((project) => (
                <option
                  dir="auto"
                  key={project.id}
                  translate="no"
                  value={project.id}
                >
                  {project.displayName}
                </option>
              ))}
            </select>
          </label>
          <label>
            {copy(locale, 'workspace.agentType')}
            <select
              aria-label={copy(locale, 'workspace.agentType')}
              value={model.agentType}
              onChange={(event) =>
                model.selectAgent(event.target.value as 'claude' | 'codex')
              }
            >
              <option lang="en" translate="no" value="claude">
                Claude
              </option>
              <option lang="en" translate="no" value="codex">
                Codex
              </option>
            </select>
          </label>
        </div>
        {selectedProject && (
          <dl
            aria-label={copy(locale, 'workspace.selectionTitle')}
            className="runtime-details compact-details workspace-current-selection"
          >
            <div>
              <dt>{copy(locale, 'workspace.currentProject')}</dt>
              <dd>
                <OpaqueUserValue value={selectedProject.displayName} />
              </dd>
            </div>
            <div>
              <dt>{copy(locale, 'workspace.currentAgentType')}</dt>
              <dd>
                <TechnicalValue value={model.agentType} />
              </dd>
            </div>
          </dl>
        )}
        {model.projectError && (
          <p className="error-panel" role="alert">
            <AlertTriangle aria-hidden="true" />
            <span>{copy(locale, 'workspace.projectListUnavailable')} </span>
            <LocalizedApiError
              error={model.projectError}
              locale={locale}
              role="presentation"
            />
          </p>
        )}
        {model.lookup === 'unregistered' && (
          <p className="interaction-notice" role="status">
            {copy(locale, 'workspace.unregistered')}
          </p>
        )}
        {model.lookup === 'loading' && (
          <p className="loading-panel" role="status">
            {copy(locale, 'workspace.loadingWorkspace')}
          </p>
        )}
        {model.lookup === 'error' && (
          <p className="error-panel" role="alert">
            {model.error ? (
              <LocalizedApiError
                error={model.error}
                locale={locale}
                role="presentation"
              />
            ) : (
              copy(locale, 'workspace.infoUnavailable')
            )}
          </p>
        )}
      </section>
      <section className="runtime-card" aria-labelledby="workspace-status">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">
              {copy(locale, 'workspace.lifecycleEyebrow')}
            </p>
            <h2 id="workspace-status">
              {copy(locale, 'workspace.statusTitle')}
            </h2>
          </div>
          <StatusBadge
            tone={model.lifecycleState === 'RUNNING' ? 'good' : 'warning'}
          >
            {lifecycleCopy(locale, model.lifecycleState)}
          </StatusBadge>
        </div>
        <p className="workspace-state-line">
          {lifecycleCode ? (
            <TechnicalValue value={lifecycleCode} />
          ) : (
            <span>{copy(locale, 'workspace.unloaded')}</span>
          )}
          {model.workspaceId && <TechnicalValue value={model.workspaceId} />}
          {model.generation && (
            <span>
              {copy(locale, 'workspace.generation')}{' '}
              <TechnicalValue value={model.generation} />
            </span>
          )}
        </p>
        {metadata && (
          <dl
            className="runtime-details"
            aria-label={copy(locale, 'workspace.runtimeMetadata')}
          >
            <div>
              <dt>{copy(locale, 'workspace.runtimeStatus')}</dt>
              <dd>
                <TechnicalValue value={metadata.state} />
              </dd>
            </div>
            <div>
              <dt>{copy(locale, 'workspace.processStatus')}</dt>
              <dd>
                <TechnicalValue value={metadata.process_state} />
              </dd>
            </div>
            <div>
              <dt>{copy(locale, 'workspace.generation')}</dt>
              <dd>
                <TechnicalValue value={metadata.generation} />
              </dd>
            </div>
            <div>
              <dt>{copy(locale, 'workspace.reconciliationStatus')}</dt>
              <dd>
                <TechnicalValue value={metadata.reconciliation_state} />
              </dd>
            </div>
          </dl>
        )}
        {model.runtimeView.status === 'stale' && (
          <p className="interaction-notice" role="status">
            {copy(locale, 'workspace.statusStale')}
          </p>
        )}
        {model.runtimeView.status === 'revalidating' && (
          <p className="loading-panel" role="status">
            {copy(locale, 'workspace.statusRevalidating')}
          </p>
        )}
        {statusReceivedAt && (
          <p className="workspace-state-line">
            <span>{copy(locale, 'workspace.lastReceived')}</span>
            <time dateTime={statusReceivedAt.toISOString()}>
              {new Intl.DateTimeFormat(locale, {
                dateStyle: 'medium',
                timeStyle: 'medium',
              }).format(statusReceivedAt)}
            </time>
          </p>
        )}
        <button
          aria-label={copy(locale, 'workspace.refresh')}
          className="icon-button"
          disabled={
            model.runtimeView.status === 'loading' ||
            model.runtimeView.status === 'revalidating'
          }
          onClick={() => void model.refresh()}
          type="button"
        >
          <RefreshCw aria-hidden="true" size={18} />
        </button>
        {model.notice && (
          <p className="workspace-notice" role="status">
            {copy(locale, NOTICE_COPY[model.notice])}
          </p>
        )}
        {model.error && model.lookup !== 'error' && (
          <p className="error-panel" role="alert">
            <LocalizedApiError
              error={model.error}
              locale={locale}
              role="presentation"
            />
          </p>
        )}
        {model.runtimeView.status === 'error' && (
          <p className="error-panel" role="alert">
            <LocalizedApiError
              error={model.runtimeView.error}
              locale={locale}
              role="presentation"
            />
          </p>
        )}
      </section>
      <section className="runtime-card" aria-labelledby="workspace-terminal">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">
              {copy(locale, 'workspace.terminalEyebrow')}
            </p>
            <h2 id="workspace-terminal">
              {copy(locale, 'workspace.terminalTitle')}
            </h2>
          </div>
          <StatusBadge tone={attachmentTone}>
            {attachmentStatusCopy}
          </StatusBadge>
        </div>
        <p className="workspace-connection-state" role="status">
          {copy(locale, 'workspace.connectionStatus')}
          {copy(locale, 'workspace.technicalSeparator')}
          {attachmentStatusCopy}
          {model.attachment.reason && (
            <>
              {' '}
              <TechnicalValue value={model.attachment.reason} />
            </>
          )}
        </p>
        <div
          className="workspace-terminal-frame"
          ref={model.setTerminalViewport}
        >
          <div
            aria-label={copy(locale, 'workspace.terminalTitle')}
            aria-live="off"
            className="workspace-terminal-surface"
            ref={model.setTerminalSurface}
            role="log"
          />
          {attachmentStatus !== 'CONNECTED' && (
            <p className="workspace-terminal-placeholder">
              {attachmentStatus === 'UNAVAILABLE'
                ? copy(locale, 'workspace.providerUnavailable')
                : copy(locale, 'workspace.terminalPlaceholder')}
            </p>
          )}
        </div>
        {model.attachment.freshRedrawTruncated && (
          <p className="interaction-notice" role="status">
            {copy(locale, 'workspace.redrawTruncated')}
          </p>
        )}
        <p className="sensitive-output workspace-sensitive-warning">
          <ShieldAlert aria-hidden="true" />
          {copy(locale, 'workspace.storageWarning')}
        </p>
        <div className="action-row">
          <button
            className="primary-button"
            disabled={!model.canStart || busy}
            onClick={() => void model.start()}
            type="button"
          >
            {copy(locale, 'workspace.start')}
          </button>
          <button
            className="secondary-button"
            disabled={!model.canStop || busy}
            onClick={model.requestStop}
            type="button"
          >
            {copy(locale, 'workspace.stop')}
          </button>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            disabled={!model.canConnect || busy}
            onClick={() => void model.connect()}
            type="button"
          >
            {copy(locale, 'workspace.connect')}
          </button>
          <button
            className="secondary-button"
            disabled={!model.canReconnect || busy}
            onClick={() => void model.reconnect()}
            type="button"
          >
            {copy(locale, 'workspace.reconnect')}
          </button>
          <button
            className="secondary-button"
            disabled={!model.canDetach || busy}
            onClick={() => void model.detach()}
            type="button"
          >
            {copy(locale, 'workspace.detach')}
          </button>
        </div>
        <form className="workspace-terminal-input" onSubmit={submitInput}>
          <input
            aria-label={copy(locale, 'workspace.sendInput')}
            autoComplete="off"
            disabled={!model.canInput || busy}
            onCompositionEnd={() => {
              composingTerminalInput.current = false
            }}
            onCompositionStart={() => {
              composingTerminalInput.current = true
            }}
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                (composingTerminalInput.current ||
                  event.nativeEvent.isComposing)
              ) {
                event.preventDefault()
              }
            }}
            onPaste={(event) => {
              const value = event.clipboardData.getData('text')
              if (/\r|\n/.test(value)) {
                event.preventDefault()
                setInputNotice(copy(locale, 'workspace.inputPasteRejected'))
              }
            }}
            placeholder={copy(locale, 'workspace.inputPlaceholder')}
            ref={terminalInput}
            spellCheck={false}
            type="text"
          />
          <button
            className="secondary-button"
            disabled={!model.canInput || busy}
            type="submit"
          >
            {copy(locale, 'workspace.sendInput')}
          </button>
        </form>
        {inputNotice && (
          <p className="interaction-notice" role="status">
            {inputNotice}
          </p>
        )}
        {model.attachment.input !== null && (
          <p className="workspace-connection-state" role="status">
            {copy(locale, 'workspace.inputSending')}
          </p>
        )}
        {settledInputNotice && (
          <p className="interaction-notice" role="status">
            {settledInputNotice}{' '}
            {model.attachment.lastInputOutcome?.reasonCode && (
              <TechnicalValue
                value={model.attachment.lastInputOutcome.reasonCode}
              />
            )}
          </p>
        )}
        <p className="workspace-connection-state">
          {copy(locale, 'workspace.viewportResize')}
        </p>
      </section>
      <dialog
        aria-describedby="stop-description"
        aria-labelledby="stop-title"
        aria-modal="true"
        className="workspace-stop-dialog"
        ref={stopDialog}
        role="dialog"
        onCancel={(event) => {
          event.preventDefault()
          if (!busy) model.cancelStop()
        }}
      >
        <div className="runtime-card">
          <h2 id="stop-title">{copy(locale, 'workspace.confirmTitle')}</h2>
          <p id="stop-description">
            {copy(locale, 'workspace.confirmDescription')}
          </p>
          {model.stopTarget && (
            <p>
              {copy(locale, 'workspace.workspaceId')}
              {copy(locale, 'workspace.technicalSeparator')}
              <TechnicalValue value={model.stopTarget.workspaceId} />
              <br />
              {copy(locale, 'workspace.generation')}
              {copy(locale, 'workspace.technicalSeparator')}
              <TechnicalValue value={model.stopTarget.generation} />
            </p>
          )}
          <div className="action-row">
            <button
              autoFocus
              className="secondary-button"
              disabled={busy}
              onClick={model.cancelStop}
              type="button"
            >
              {copy(locale, 'workspace.cancel')}
            </button>
            <button
              className="primary-button"
              disabled={busy || !model.stopTarget}
              onClick={() => {
                if (model.stopTarget && !busy) void model.confirmStop()
              }}
              type="button"
            >
              {copy(locale, 'workspace.confirmStop')}
            </button>
          </div>
        </div>
      </dialog>
    </>
  )
}
