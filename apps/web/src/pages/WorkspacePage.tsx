import { AlertTriangle, MonitorUp, RefreshCw, ShieldAlert } from 'lucide-react'
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { MAX_INPUT_BYTES } from '../features/workspace/wawCryptoProfile'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, technicalValue, type Locale } from '../i18n'
import './WorkspacePage.css'
import type { WorkspacePageModel } from '../features/workspace/workspaceView'

const COPY = {
  en: {
    title: 'Interactive workspace',
    description:
      'Manage the controlled Claude or Codex workspace lifecycle for a formal READY Project. Terminal access requires local trust admission.',
    selectionEyebrow: 'Workspace selection',
    selectionTitle: 'Select a Project and AgentType',
    readyProject: 'Formal READY Project',
    selectProject: 'Select a Project',
    loadingProject: 'Loading Projects…',
    noProject: 'No READY Projects',
    projectListUnavailable:
      'The Project list is temporarily unavailable. Refresh and try again.',
    unregistered:
      'This AgentType is not registered and cannot start a workspace.',
    loadingWorkspace: 'Loading workspace information…',
    infoUnavailable: 'Workspace information is temporarily unavailable.',
    lifecycleEyebrow: 'Lifecycle state',
    statusTitle: 'Workspace record status',
    unloaded: 'Not loaded',
    runtimeStatus: 'Runtime status',
    processStatus: 'Process status',
    reconciliationStatus: 'Reconciliation status',
    refresh: 'Refresh workspace status',
    invalidAgent:
      'The AgentType in this link is invalid. Select a Project and AgentType again.',
    operationFailed:
      'The operation did not complete. Refresh the status and retry.',
    notices: {
      START_CONFIRMED:
        'The start request was confirmed. Process status and browser terminal connection status are shown separately.',
      STOP_CONFIRMED:
        'The managed process stopped. Project and Git changes were preserved.',
      RUNTIME_RECOVERY_REQUIRED:
        'Runtime recovery review is required. Workspace operations are paused.',
    },
    terminalEyebrow: 'Terminal viewport',
    terminalTitle: 'Controlled terminal',
    terminalPlaceholder:
      'Connect only after the current Project, Runtime and local trust provider are admitted.',
    providerUnavailable:
      'The managed browser trust provider is unavailable, so no terminal ticket was requested.',
    connectionStatus: 'Connection status',
    terminalStatuses: {
      IDLE: 'Ready to connect',
      ACQUIRING_TICKET: 'Requesting terminal ticket',
      AUTHORIZING_TRUST: 'Checking local trust',
      CONNECTING: 'Connecting transport',
      HANDSHAKING: 'Verifying terminal channel',
      CONNECTED: 'Connected',
      DETACHING: 'Disconnecting',
      DETACHED: 'Disconnected',
      STOPPING: 'Stopping workspace',
      STOPPED: 'Stopped',
      FENCED: 'Connection fenced',
      UNAVAILABLE: 'Trust provider unavailable',
    },
    redrawTruncated:
      'The initial terminal redraw was bounded. Refreshing the terminal starts a new bounded redraw.',
    storageWarning:
      'Terminal content is not stored in browser storage or offered as a history download.',
    start: 'Start workspace',
    stop: 'Stop workspace',
    connect: 'Connect terminal',
    reconnect: 'Reconnect',
    detach: 'Disconnect',
    keyboard: 'Send input',
    inputPlaceholder: 'Type terminal input and press Enter',
    inputPasteRejected: 'Multi-line paste is not sent through this input.',
    inputTooLong: 'Terminal input is limited to 16 KiB.',
    inputSending: 'Sending terminal input…',
    inputRateLimited: 'Input was rate limited and was not sent. Try again.',
    inputUncertain: 'Input delivery is uncertain and will not be resent.',
    viewportResize: 'Terminal size follows the visible viewport.',
    confirmTitle: 'Confirm workspace stop',
    confirmDescription:
      'Stop only the managed process and preserve Project and Git changes.',
    workspaceId: 'Workspace ID',
    generation: 'Generation',
    technicalSeparator: ': ',
    runtimeMetadata: 'Runtime metadata',
    cancel: 'Cancel',
    confirmStop: 'Confirm stop',
    states: {
      STARTING: 'Starting',
      RUNNING: 'Running',
      NEEDS_INTERACTION: 'Interaction required',
      TRUST_REQUIRED: 'Local trust confirmation required',
      LOGIN_REQUIRED: 'Local login required',
      STOPPING: 'Stopping',
      EXITED: 'Process exited',
      STOPPED: 'Stopped',
      MISSING: 'Process missing',
      COLLISION: 'Conflict detected',
      BROKEN: 'Recovery review required',
      UNKNOWN: 'Status unknown',
    },
  },
  'zh-CN': {
    title: '交互式工作区',
    description:
      '在正式 READY Project 中管理受控的 Claude 或 Codex 工作区生命周期。终端访问需要完成本地信任准入。',
    selectionEyebrow: '工作区选择',
    selectionTitle: '选择 Project 与 AgentType',
    readyProject: '正式 READY Project',
    selectProject: '请选择 Project',
    loadingProject: '正在加载 Project…',
    noProject: '暂无 READY Project',
    projectListUnavailable: 'Project 列表暂不可用，请刷新后重试。',
    unregistered: '当前 AgentType 尚未注册，无法启动工作区。',
    loadingWorkspace: '正在读取工作区信息…',
    infoUnavailable: '工作区信息暂不可用。',
    lifecycleEyebrow: '生命周期状态',
    statusTitle: '工作区记录状态',
    unloaded: '未加载',
    runtimeStatus: 'Runtime 状态',
    processStatus: '进程状态',
    reconciliationStatus: 'Reconciliation 状态',
    refresh: '刷新工作区状态',
    invalidAgent: '链接中的 AgentType 无效，请重新选择 Project 与 AgentType。',
    operationFailed: '操作未完成，请刷新状态后重试。',
    notices: {
      START_CONFIRMED: '启动请求已确认。进程状态与浏览器终端连接状态分别显示。',
      STOP_CONFIRMED: '受管进程已停止，Project 和 Git 修改已保留。',
      RUNTIME_RECOVERY_REQUIRED: 'Runtime 需要恢复核对，工作区操作已暂停。',
    },
    terminalEyebrow: '终端视口',
    terminalTitle: '受控终端',
    terminalPlaceholder:
      '仅在当前 Project、Runtime 与本地信任 provider 完成准入后连接终端。',
    providerUnavailable:
      '受管浏览器信任 provider 不可用，因此未请求终端 ticket。',
    connectionStatus: '连接状态',
    terminalStatuses: {
      IDLE: '可以连接',
      ACQUIRING_TICKET: '正在请求终端 ticket',
      AUTHORIZING_TRUST: '正在核对本地信任',
      CONNECTING: '正在连接传输',
      HANDSHAKING: '正在验证终端通道',
      CONNECTED: '已连接',
      DETACHING: '正在断开',
      DETACHED: '已断开',
      STOPPING: '正在停止工作区',
      STOPPED: '已停止',
      FENCED: '连接已围栏',
      UNAVAILABLE: '信任 provider 不可用',
    },
    redrawTruncated: '初始终端重绘已受限。刷新终端会开始新的受限重绘。',
    storageWarning: '终端内容不写入浏览器存储，也不提供历史记录下载。',
    start: '启动工作区',
    stop: '停止工作区',
    connect: '连接终端',
    reconnect: '重新连接',
    detach: '断开连接',
    keyboard: '发送输入',
    inputPlaceholder: '输入终端内容后按 Enter 发送',
    inputPasteRejected: '此输入框不会发送多行粘贴内容。',
    inputTooLong: '终端输入最多为 16 KiB。',
    inputSending: '正在发送终端输入…',
    inputRateLimited: '输入已被限流，未发送到终端。请稍后重试。',
    inputUncertain: '输入结果不确定，系统不会自动重发。',
    viewportResize: '终端尺寸会跟随可见视口。',
    confirmTitle: '确认停止工作区',
    confirmDescription: '仅停止受管进程，保留 Project 和 Git 修改。',
    workspaceId: '工作区 ID',
    generation: '代次',
    technicalSeparator: '：',
    runtimeMetadata: 'Runtime 元数据',
    cancel: '取消',
    confirmStop: '确认停止',
    states: {
      STARTING: '启动中',
      RUNNING: '运行中',
      NEEDS_INTERACTION: '需要交互',
      TRUST_REQUIRED: '需要本地确认信任',
      LOGIN_REQUIRED: '需要本地登录',
      STOPPING: '停止中',
      EXITED: '进程已退出',
      STOPPED: '已停止',
      MISSING: '进程不存在',
      COLLISION: '检测到冲突',
      BROKEN: '需要恢复核对',
      UNKNOWN: '状态未知',
    },
  },
} as const satisfies Record<Locale, Record<string, unknown>>

function TechnicalValue({ value }: { value: string }) {
  try {
    const technical = technicalValue(value)
    return (
      <code
        dir={technical.dir}
        lang={technical.lang}
        translate={technical.translate}
      >
        {technical.value}
      </code>
    )
  } catch {
    return null
  }
}

function inputResultNotice(
  copy: Readonly<{
    inputRateLimited: string
    inputUncertain: string
  }>,
  outcome: WorkspacePageModel['attachment']['lastInputOutcome'],
): string | null {
  if (outcome === null) return null
  if (
    outcome.state === 'rejected' &&
    outcome.reasonCode === 'INPUT_RATE_LIMITED'
  ) {
    return copy.inputRateLimited
  }
  if (
    outcome.state === 'write_uncertain' ||
    outcome.state === 'local_uncertain' ||
    outcome.state === 'rejected'
  ) {
    return copy.inputUncertain
  }
  return null
}

export function WorkspacePage({
  model,
  locale = currentLocale(),
}: {
  model: WorkspacePageModel
  locale?: Locale
}) {
  const copy = COPY[locale]
  usePageTitle(copy.title)
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
  const runtimeError =
    model.runtimeView.status === 'error' ? model.runtimeView.error.code : null
  const lifecycleCode = model.lifecycleState ? (
    <TechnicalValue value={model.lifecycleState} />
  ) : null
  const attachmentStatus = model.attachment.status
  const settledInputNotice = inputResultNotice(
    copy,
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
    if (model.stopTarget && dialog && !dialog.open) {
      dialog.showModal()
    }
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
      setInputNotice(copy.inputTooLong)
      return
    }
    input.value = ''
    setInputNotice(null)
    void model.sendInput(value)
  }
  return (
    <>
      <PageHeader
        eyebrow="Web Agent Workspace"
        title={copy.title}
        description={copy.description}
      />
      <section
        className="runtime-card workspace-selection-card"
        aria-labelledby="workspace-selection"
      >
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">{copy.selectionEyebrow}</p>
            <h2 id="workspace-selection">{copy.selectionTitle}</h2>
          </div>
          <MonitorUp aria-hidden="true" />
        </div>
        <div className="project-forms">
          <label>
            {copy.readyProject}
            <select
              aria-label={copy.readyProject}
              value={model.selectedProjectId}
              onChange={(e) => model.selectProject(e.target.value)}
              disabled={model.projectsLoading || model.projects.length === 0}
            >
              {!model.projectsLoading &&
                model.projects.length > 0 &&
                !model.selectedProjectId && (
                  <option value="">{copy.selectProject}</option>
                )}
              {model.projectsLoading && (
                <option value="">{copy.loadingProject}</option>
              )}
              {!model.projectsLoading && model.projects.length === 0 && (
                <option value="">{copy.noProject}</option>
              )}
              {model.projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.displayName}
                </option>
              ))}
            </select>
          </label>
          <label>
            AgentType
            <select
              aria-label="AgentType"
              value={model.agentType}
              onChange={(e) =>
                model.selectAgent(e.target.value as 'claude' | 'codex')
              }
            >
              <option value="claude">Claude</option>
              <option value="codex">Codex</option>
            </select>
          </label>
        </div>
        {model.projectError && (
          <p className="error-panel" role="alert">
            <AlertTriangle aria-hidden="true" />
            {copy.projectListUnavailable}
          </p>
        )}
        {model.lookup === 'unregistered' && (
          <p className="interaction-notice" role="status">
            {copy.unregistered}
          </p>
        )}
        {model.lookup === 'loading' && (
          <p className="loading-panel" role="status">
            {copy.loadingWorkspace}
          </p>
        )}
        {model.lookup === 'error' && !model.error && (
          <p className="error-panel" role="alert">
            {copy.infoUnavailable}{' '}
            {runtimeError && <TechnicalValue value={runtimeError} />}
          </p>
        )}
      </section>
      <section className="runtime-card" aria-labelledby="workspace-status">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">{copy.lifecycleEyebrow}</p>
            <h2 id="workspace-status">{copy.statusTitle}</h2>
          </div>
          <StatusBadge
            tone={model.lifecycleState === 'RUNNING' ? 'good' : 'warning'}
          >
            {copy.states[model.lifecycleState as keyof typeof copy.states] ??
              copy.unloaded}
          </StatusBadge>
        </div>
        <p className="workspace-state-line">
          {lifecycleCode ?? <span>{copy.unloaded}</span>}
          {model.workspaceId && <TechnicalValue value={model.workspaceId} />}
          {model.generation && (
            <TechnicalValue value={`generation ${model.generation}`} />
          )}
        </p>
        {metadata && (
          <dl className="runtime-details" aria-label={copy.runtimeMetadata}>
            <div>
              <dt>{copy.runtimeStatus}</dt>
              <dd>
                <TechnicalValue value={metadata.state} />
              </dd>
            </div>
            <div>
              <dt>{copy.processStatus}</dt>
              <dd>
                <TechnicalValue value={metadata.process_state} />
              </dd>
            </div>
            <div>
              <dt>{copy.generation}</dt>
              <dd>
                <TechnicalValue value={metadata.generation} />
              </dd>
            </div>
            <div>
              <dt>{copy.reconciliationStatus}</dt>
              <dd>
                <TechnicalValue value={metadata.reconciliation_state} />
              </dd>
            </div>
          </dl>
        )}
        <button
          aria-label={copy.refresh}
          className="icon-button"
          disabled={model.runtimeView.status === 'loading'}
          onClick={() => void model.refresh()}
          type="button"
        >
          <RefreshCw size={18} />
        </button>
        {model.notice && (
          <p className="workspace-notice" role="status">
            {copy.notices[model.notice]}
          </p>
        )}
        {model.error && (
          <p className="error-panel" role="alert">
            {model.error.code === 'WAW_INVALID_AGENT'
              ? copy.invalidAgent
              : copy.operationFailed}{' '}
            <TechnicalValue value={model.error.code} />
          </p>
        )}
        {model.runtimeView.status === 'error' && runtimeError && (
          <p className="error-panel" role="alert">
            {copy.infoUnavailable} <TechnicalValue value={runtimeError} />
          </p>
        )}
      </section>
      <section className="runtime-card" aria-labelledby="workspace-terminal">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">{copy.terminalEyebrow}</p>
            <h2 id="workspace-terminal">{copy.terminalTitle}</h2>
          </div>
          <StatusBadge tone={attachmentTone}>
            {copy.terminalStatuses[attachmentStatus]}
          </StatusBadge>
        </div>
        <p className="workspace-connection-state" role="status">
          {copy.connectionStatus}
          {copy.technicalSeparator}
          {copy.terminalStatuses[attachmentStatus]}
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
            aria-label={copy.terminalTitle}
            aria-live="off"
            className="workspace-terminal-surface"
            ref={model.setTerminalSurface}
            role="log"
          />
          {attachmentStatus !== 'CONNECTED' && (
            <p className="workspace-terminal-placeholder">
              {attachmentStatus === 'UNAVAILABLE'
                ? copy.providerUnavailable
                : copy.terminalPlaceholder}
            </p>
          )}
        </div>
        {model.attachment.freshRedrawTruncated && (
          <p className="interaction-notice" role="status">
            {copy.redrawTruncated}
          </p>
        )}
        <p className="sensitive-output workspace-sensitive-warning">
          <ShieldAlert aria-hidden="true" />
          {copy.storageWarning}
        </p>
        <div className="action-row">
          <button
            className="primary-button"
            disabled={!model.canStart || busy}
            onClick={() => void model.start()}
            type="button"
          >
            {copy.start}
          </button>
          <button
            className="secondary-button"
            disabled={!model.canStop || busy}
            onClick={() => {
              model.requestStop()
            }}
            type="button"
          >
            {copy.stop}
          </button>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            disabled={!model.canConnect || busy}
            onClick={() => void model.connect()}
            type="button"
          >
            {copy.connect}
          </button>
          <button
            className="secondary-button"
            disabled={!model.canReconnect || busy}
            onClick={() => void model.reconnect()}
            type="button"
          >
            {copy.reconnect}
          </button>
          <button
            className="secondary-button"
            disabled={!model.canDetach || busy}
            onClick={() => void model.detach()}
            type="button"
          >
            {copy.detach}
          </button>
        </div>
        <form className="workspace-terminal-input" onSubmit={submitInput}>
          <input
            aria-label={copy.keyboard}
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
                setInputNotice(copy.inputPasteRejected)
              }
            }}
            placeholder={copy.inputPlaceholder}
            ref={terminalInput}
            spellCheck={false}
            type="text"
          />
          <button
            className="secondary-button"
            disabled={!model.canInput || busy}
            type="submit"
          >
            {copy.keyboard}
          </button>
        </form>
        {inputNotice && (
          <p className="interaction-notice" role="status">
            {inputNotice}
          </p>
        )}
        {model.attachment.input !== null && (
          <p className="workspace-connection-state" role="status">
            {copy.inputSending}
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
        <p className="workspace-connection-state">{copy.viewportResize}</p>
      </section>
      <dialog
        className="workspace-stop-dialog"
        ref={stopDialog}
        aria-labelledby="stop-title"
        onCancel={(event) => {
          event.preventDefault()
          if (!busy) model.cancelStop()
        }}
      >
        <div className="runtime-card">
          <h2 id="stop-title">{copy.confirmTitle}</h2>
          <p>{copy.confirmDescription}</p>
          {model.stopTarget && (
            <p>
              {copy.workspaceId}
              {copy.technicalSeparator}
              <TechnicalValue value={model.stopTarget.workspaceId} />
              <br />
              {copy.generation}
              {copy.technicalSeparator}
              <TechnicalValue value={model.stopTarget.generation} />
            </p>
          )}
          <div className="action-row">
            <button
              className="secondary-button"
              disabled={busy}
              autoFocus
              onClick={() => {
                model.cancelStop()
              }}
              type="button"
            >
              {copy.cancel}
            </button>
            <button
              className="primary-button"
              disabled={busy || !model.stopTarget}
              onClick={() => {
                if (model.stopTarget && !busy) void model.confirmStop()
              }}
              type="button"
            >
              {copy.confirmStop}
            </button>
          </div>
        </div>
      </dialog>
    </>
  )
}
