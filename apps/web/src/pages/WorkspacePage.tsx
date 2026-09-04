import { AlertTriangle, MonitorUp, RefreshCw, ShieldAlert } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, technicalValue, type Locale } from '../i18n'
import './WorkspacePage.css'
import type { WorkspacePageModel } from '../features/workspace/workspaceView'

const COPY = {
  en: {
    title: 'Interactive workspace',
    description:
      'Manage the controlled Claude or Codex workspace lifecycle for a formal READY Project. Terminal connection is not yet available.',
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
    notAdmitted: 'Not admitted',
    terminalPlaceholder:
      'Terminal connection is not yet available. This page currently provides status and lifecycle management only.',
    storageWarning:
      'Terminal content is not stored in browser storage or offered as a history download.',
    start: 'Start workspace',
    stop: 'Stop workspace',
    connect: 'Connect terminal',
    reconnect: 'Reconnect',
    detach: 'Disconnect',
    keyboard: 'Keyboard input',
    futureNote:
      'Terminal connection, reconnect, disconnect and keyboard input will be enabled after the real connection capability is complete.',
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
      '在正式 READY Project 中管理受控的 Claude 或 Codex 工作区生命周期。终端连接尚未开放。',
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
    notAdmitted: '尚未准入',
    terminalPlaceholder: '终端连接尚未开放。当前页面仅提供状态与生命周期管理。',
    storageWarning: '终端内容不写入浏览器存储，也不提供历史记录下载。',
    start: '启动工作区',
    stop: '停止工作区',
    connect: '连接终端',
    reconnect: '重新连接',
    detach: '断开连接',
    keyboard: '键盘输入',
    futureNote:
      '连接终端、重新连接、断开连接与键盘输入将在真实连接能力完成后开放。',
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

export function WorkspacePage({
  model,
  locale = currentLocale(),
}: {
  model: WorkspacePageModel
  locale?: Locale
}) {
  const copy = COPY[locale]
  usePageTitle(copy.title)
  const stopDialog = useRef<HTMLDialogElement>(null)
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
  useEffect(() => {
    const dialog = stopDialog.current
    if (model.stopTarget && dialog && !dialog.open) {
      dialog.showModal()
    }
    if (!model.stopTarget && dialog?.open) dialog.close()
  }, [model.stopTarget])
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
      </section>
      <section className="runtime-card" aria-labelledby="workspace-terminal">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">{copy.terminalEyebrow}</p>
            <h2 id="workspace-terminal">{copy.terminalTitle}</h2>
          </div>
          <StatusBadge tone="muted">{copy.notAdmitted}</StatusBadge>
        </div>
        <pre
          aria-label={copy.terminalTitle}
          className="workspace-terminal-placeholder"
        >
          {copy.terminalPlaceholder}
        </pre>
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
          <button className="secondary-button" disabled type="button">
            {copy.connect}
          </button>
          <button className="secondary-button" disabled type="button">
            {copy.reconnect}
          </button>
          <button className="secondary-button" disabled type="button">
            {copy.detach}
          </button>
          <button className="secondary-button" disabled type="button">
            {copy.keyboard}
          </button>
        </div>
        <p className="stop-note">{copy.futureNote}</p>
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
