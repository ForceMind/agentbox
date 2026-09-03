import { AlertTriangle, MonitorUp, RefreshCw, ShieldAlert } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { usePageTitle } from '../hooks/usePageTitle'
import './WorkspacePage.css'
import type { WorkspacePageModel } from '../features/workspace/workspaceView'

const labels: Record<string, string> = {
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
}

export function WorkspacePage({ model }: { model: WorkspacePageModel }) {
  usePageTitle('交互式工作区')
  const stopDialog = useRef<HTMLDialogElement>(null)
  const busy = model.pending !== null
  const metadata =
    model.runtimeView.status === 'loaded'
      ? model.runtimeView.response.data
      : null
  const runtimeError =
    model.runtimeView.status === 'error' ? model.runtimeView.error.code : null
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
        title="交互式工作区"
        description="在正式 READY Project 中管理受控的 Claude 或 Codex 工作区生命周期。终端连接尚未开放。"
      />
      <section
        className="runtime-card workspace-selection-card"
        aria-labelledby="workspace-selection"
      >
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">Workspace selection</p>
            <h2 id="workspace-selection">选择 Project 与 AgentType</h2>
          </div>
          <MonitorUp aria-hidden="true" />
        </div>
        <div className="project-forms">
          <label>
            正式 READY Project
            <select
              aria-label="正式 READY Project"
              value={model.selectedProjectId}
              onChange={(e) => model.selectProject(e.target.value)}
              disabled={model.projectsLoading || model.projects.length === 0}
            >
              {!model.projectsLoading &&
                model.projects.length > 0 &&
                !model.selectedProjectId && (
                  <option value="">请选择 Project</option>
                )}
              {model.projectsLoading && (
                <option value="">正在加载 Project…</option>
              )}
              {!model.projectsLoading && model.projects.length === 0 && (
                <option value="">暂无 READY Project</option>
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
            {model.projectError}
          </p>
        )}
        {model.lookup === 'unregistered' && (
          <p className="interaction-notice" role="status">
            当前 AgentType 尚未注册，无法启动工作区。
          </p>
        )}
        {model.lookup === 'loading' && (
          <p className="loading-panel" role="status">
            正在读取工作区信息…
          </p>
        )}
        {model.lookup === 'error' && !model.error && (
          <p className="error-panel" role="alert">
            工作区信息暂不可用。{runtimeError && <code>{runtimeError}</code>}
          </p>
        )}
      </section>
      <section className="runtime-card" aria-labelledby="workspace-status">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">Lifecycle state</p>
            <h2 id="workspace-status">工作区记录状态</h2>
          </div>
          <StatusBadge
            tone={model.lifecycleState === 'RUNNING' ? 'good' : 'warning'}
          >
            {labels[model.lifecycleState ?? ''] ??
              model.lifecycleState ??
              '未加载'}
          </StatusBadge>
        </div>
        <p className="workspace-state-line">
          <code>{model.lifecycleState ?? '未加载'}</code>
          {model.workspaceId && <code>{model.workspaceId}</code>}
          {model.generation && <code>generation {model.generation}</code>}
        </p>
        {metadata && (
          <dl className="runtime-details" aria-label="Runtime metadata">
            <div>
              <dt>Runtime 状态</dt>
              <dd>{metadata.state}</dd>
            </div>
            <div>
              <dt>进程状态</dt>
              <dd>{metadata.process_state}</dd>
            </div>
            <div>
              <dt>Generation</dt>
              <dd>{metadata.generation}</dd>
            </div>
            <div>
              <dt>Reconciliation 状态</dt>
              <dd>{metadata.reconciliation_state}</dd>
            </div>
          </dl>
        )}
        <button
          aria-label="刷新工作区状态"
          className="icon-button"
          disabled={model.runtimeView.status === 'loading'}
          onClick={() => void model.refresh()}
          type="button"
        >
          <RefreshCw size={18} />
        </button>
        {model.notice && (
          <p className="workspace-notice" role="status">
            {model.notice}
          </p>
        )}
        {model.error && (
          <p className="error-panel" role="alert">
            {model.error.code === 'WAW_INVALID_AGENT'
              ? '链接中的 AgentType 无效，请重新选择项目与 AgentType。'
              : '操作未完成，请刷新状态后重试。'}{' '}
            <code>{model.error.code}</code>
          </p>
        )}
      </section>
      <section className="runtime-card" aria-labelledby="workspace-terminal">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">Terminal viewport</p>
            <h2 id="workspace-terminal">受控终端</h2>
          </div>
          <StatusBadge tone="muted">NOT ADMITTED</StatusBadge>
        </div>
        <pre
          aria-label="Terminal output"
          className="workspace-terminal-placeholder"
        >
          终端连接尚未开放。当前页面仅提供状态与生命周期管理。
        </pre>
        <p className="sensitive-output workspace-sensitive-warning">
          <ShieldAlert aria-hidden="true" />
          终端内容不写入浏览器存储，也不提供历史记录下载。
        </p>
        <div className="action-row">
          <button
            className="primary-button"
            disabled={!model.canStart || busy}
            onClick={() => void model.start()}
            type="button"
          >
            启动工作区
          </button>
          <button
            className="secondary-button"
            disabled={!model.canStop || busy}
            onClick={() => {
              model.requestStop()
            }}
            type="button"
          >
            停止工作区
          </button>
        </div>
        <div className="action-row">
          <button className="secondary-button" disabled type="button">
            连接终端
          </button>
          <button className="secondary-button" disabled type="button">
            重新连接
          </button>
          <button className="secondary-button" disabled type="button">
            断开连接
          </button>
          <button className="secondary-button" disabled type="button">
            键盘输入
          </button>
        </div>
        <p className="stop-note">
          连接终端、重新连接、断开连接与键盘输入将在真实连接能力完成后开放。
        </p>
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
          <h2 id="stop-title">确认停止工作区</h2>
          <p>仅停止受管进程，保留 Project 和 Git 修改。</p>
          {model.stopTarget && (
            <p>
              Workspace ID：<code>{model.stopTarget.workspaceId}</code>
              <br />
              Generation：<code>{model.stopTarget.generation}</code>
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
              取消
            </button>
            <button
              className="primary-button"
              disabled={busy || !model.stopTarget}
              onClick={() => {
                if (model.stopTarget && !busy) void model.confirmStop()
              }}
              type="button"
            >
              确认停止
            </button>
          </div>
        </div>
      </dialog>
    </>
  )
}
