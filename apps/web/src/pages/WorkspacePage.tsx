import { AlertTriangle, Keyboard, MonitorUp, ShieldAlert } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  initialWorkspaceState,
  WorkspaceState,
} from '../features/workspace/workspaceState'

const statusLabels: Record<WorkspaceState['status'], string> = {
  checking: '检查中',
  starting: '启动中',
  connecting: '连接中',
  connected: '已连接',
  reconnecting: '重新连接中',
  error: '错误',
  stopping: '停止中',
  detached: '已分离',
  stopped: '已停止',
  gap: '输出有缺口',
  input_uncertain: '输入状态不确定',
  login_required: '需要本地登录',
  trust_required: '需要 Workspace Trust',
  exited: '进程已退出',
  missing: '进程不存在',
  collision: '检测到冲突',
  unavailable: '不可用',
}

function statusTone(status: WorkspaceState['status']) {
  if (status === 'connected') return 'good' as const
  if (status === 'stopped' || status === 'detached') return 'muted' as const
  return 'warning' as const
}

export function WorkspacePage({
  initialState = initialWorkspaceState,
}: {
  initialState?: WorkspaceState
}) {
  // The transport hook will own this state in the implementation slice.  The
  // current PR intentionally remains a static, injectable presentation shell.
  const state = initialState
  usePageTitle('Workspace')

  const terminalMessage =
    state.status === 'connected'
      ? 'Runtime ADMITTED 已确认。终端输出仅在当前页面内存中显示。'
      : '等待 Runtime ADMITTED；当前不会显示终端输出。'
  const isTerminal = state.status === 'connected'

  return (
    <>
      <PageHeader
        description="在一个正式 READY Project 中连接受控的 Claude AgentType。此页面只提供受限的交互式 Workspace，不是 shell 或 Provider 登录入口。"
        eyebrow="Web Agent Workspace"
        title="Interactive Workspace"
      />

      <section className="runtime-card" aria-labelledby="workspace-selection">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">Workspace selection</p>
            <h2 id="workspace-selection">选择 Project 与 AgentType</h2>
          </div>
          <MonitorUp aria-hidden="true" />
        </div>
        <div className="project-forms">
          <label>
            Formal READY Project
            <select aria-label="Formal READY Project" disabled>
              <option>请先加载 READY Project</option>
            </select>
          </label>
          <label>
            AgentType
            <select aria-label="AgentType" defaultValue="claude" disabled>
              <option value="claude">Claude · claude</option>
            </select>
          </label>
        </div>
        <p className="interaction-notice">
          Start 不会自动执行。此安全 UI 骨架尚未连接 WAW API 或
          WebSocket，因而不会伪造 workspace、ticket 或运行状态。
        </p>
      </section>

      <section className="runtime-card" aria-labelledby="workspace-status">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">Connection state</p>
            <h2 id="workspace-status">连接状态</h2>
          </div>
          <StatusBadge tone={statusTone(state.status)}>
            {statusLabels[state.status]}
          </StatusBadge>
        </div>
        <p className="workspace-state-line">
          <code>{state.status}</code>
          {state.workspaceId && <code>{state.workspaceId}</code>}
          {state.errorCode && <code>{state.errorCode}</code>}
        </p>
        {state.message && <p className="workspace-notice">{state.message}</p>}
        {state.status === 'error' && (
          <p className="error-panel" role="alert">
            <AlertTriangle aria-hidden="true" /> Workspace 操作未完成。请查看
            technical error code；页面不会重试或猜测 Runtime 状态。
          </p>
        )}
        {state.status === 'gap' && (
          <p className="interaction-notice" role="status">
            输出历史存在 bounded GAP。页面不会声称拥有完整
            transcript，也不提供下载。
          </p>
        )}
        {state.status === 'input_uncertain' && (
          <p className="interaction-notice" role="status">
            Runtime 未能确认输入是否写入 PTY。请由用户决定是否重新输入；AgentBox
            不会自动重放。
          </p>
        )}
      </section>

      <section className="runtime-card" aria-labelledby="workspace-terminal">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">Terminal viewport</p>
            <h2 id="workspace-terminal">Claude terminal</h2>
          </div>
          <StatusBadge tone={isTerminal ? 'good' : 'muted'}>
            {isTerminal ? 'ADMITTED' : 'NOT ADMITTED'}
          </StatusBadge>
        </div>
        <pre
          aria-label="Terminal output"
          className="workspace-terminal-placeholder"
        >
          {terminalMessage}
        </pre>
        <p className="sensitive-output workspace-sensitive-warning">
          <ShieldAlert aria-hidden="true" />{' '}
          终端内容可能包含源码、模型输出、提示词或误粘贴的敏感数据。不会保存
          transcript、ticket、input history 或 terminal content。
        </p>
        <div className="action-row">
          <button className="primary-button" disabled type="button">
            Start / Connect
          </button>
          <button className="secondary-button" disabled type="button">
            Detach（保留 agent）
          </button>
          <button className="secondary-button" disabled type="button">
            Stop workspace
          </button>
        </div>
        <p className="stop-note">
          Stop 需要二次确认，只终止 exact managed workspace，不删除 Project 或
          Git changes。Detach 只断开当前浏览器连接。
        </p>
      </section>

      <section className="runtime-card" aria-labelledby="workspace-input">
        <div className="runtime-card-heading">
          <div>
            <p className="eyebrow">Input controls</p>
            <h2 id="workspace-input">键盘与移动设备</h2>
          </div>
          <Keyboard aria-hidden="true" />
        </div>
        <p className="runtime-copy">
          支持文本、Enter、箭头、Tab、Esc 和 Ctrl
          组合键；移动设备提供等价的显式控制。输入确认只代表写入 PTY，不代表
          Agent 已消费。
        </p>
        <div className="action-row" aria-label="Mobile terminal controls">
          {['↑', '↓', '←', '→', 'Tab', 'Esc', 'Ctrl'].map((key) => (
            <button
              className="secondary-button"
              disabled
              key={key}
              type="button"
            >
              {key}
            </button>
          ))}
        </div>
      </section>
    </>
  )
}
