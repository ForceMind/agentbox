import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface WorkspaceMessageParameters {
  readonly 'workspace.title': NoMessageParameters
  readonly 'workspace.eyebrow': NoMessageParameters
  readonly 'workspace.description': NoMessageParameters
  readonly 'workspace.selectionEyebrow': NoMessageParameters
  readonly 'workspace.selectionTitle': NoMessageParameters
  readonly 'workspace.readyProject': NoMessageParameters
  readonly 'workspace.agentType': NoMessageParameters
  readonly 'workspace.selectProject': NoMessageParameters
  readonly 'workspace.loadingProjects': NoMessageParameters
  readonly 'workspace.noReadyProjects': NoMessageParameters
  readonly 'workspace.projectListUnavailable': NoMessageParameters
  readonly 'workspace.currentProject': NoMessageParameters
  readonly 'workspace.currentAgentType': NoMessageParameters
  readonly 'workspace.unregistered': NoMessageParameters
  readonly 'workspace.loadingWorkspace': NoMessageParameters
  readonly 'workspace.infoUnavailable': NoMessageParameters
  readonly 'workspace.lifecycleEyebrow': NoMessageParameters
  readonly 'workspace.statusTitle': NoMessageParameters
  readonly 'workspace.unloaded': NoMessageParameters
  readonly 'workspace.runtimeStatus': NoMessageParameters
  readonly 'workspace.processStatus': NoMessageParameters
  readonly 'workspace.reconciliationStatus': NoMessageParameters
  readonly 'workspace.refresh': NoMessageParameters
  readonly 'workspace.noticeStartConfirmed': NoMessageParameters
  readonly 'workspace.noticeStopConfirmed': NoMessageParameters
  readonly 'workspace.noticeRecoveryRequired': NoMessageParameters
  readonly 'workspace.terminalEyebrow': NoMessageParameters
  readonly 'workspace.terminalTitle': NoMessageParameters
  readonly 'workspace.terminalPlaceholder': NoMessageParameters
  readonly 'workspace.providerUnavailable': NoMessageParameters
  readonly 'workspace.connectionStatus': NoMessageParameters
  readonly 'workspace.terminalIdle': NoMessageParameters
  readonly 'workspace.terminalAcquiringTicket': NoMessageParameters
  readonly 'workspace.terminalAuthorizingTrust': NoMessageParameters
  readonly 'workspace.terminalConnecting': NoMessageParameters
  readonly 'workspace.terminalHandshaking': NoMessageParameters
  readonly 'workspace.terminalConnected': NoMessageParameters
  readonly 'workspace.terminalDetaching': NoMessageParameters
  readonly 'workspace.terminalDetached': NoMessageParameters
  readonly 'workspace.terminalStopping': NoMessageParameters
  readonly 'workspace.terminalStopped': NoMessageParameters
  readonly 'workspace.terminalFenced': NoMessageParameters
  readonly 'workspace.terminalUnavailable': NoMessageParameters
  readonly 'workspace.redrawTruncated': NoMessageParameters
  readonly 'workspace.storageWarning': NoMessageParameters
  readonly 'workspace.start': NoMessageParameters
  readonly 'workspace.stop': NoMessageParameters
  readonly 'workspace.connect': NoMessageParameters
  readonly 'workspace.reconnect': NoMessageParameters
  readonly 'workspace.detach': NoMessageParameters
  readonly 'workspace.sendInput': NoMessageParameters
  readonly 'workspace.inputPlaceholder': NoMessageParameters
  readonly 'workspace.inputPasteRejected': NoMessageParameters
  readonly 'workspace.inputTooLong': NoMessageParameters
  readonly 'workspace.inputSending': NoMessageParameters
  readonly 'workspace.inputRateLimited': NoMessageParameters
  readonly 'workspace.inputUncertain': NoMessageParameters
  readonly 'workspace.viewportResize': NoMessageParameters
  readonly 'workspace.confirmTitle': NoMessageParameters
  readonly 'workspace.confirmDescription': NoMessageParameters
  readonly 'workspace.workspaceId': NoMessageParameters
  readonly 'workspace.generation': NoMessageParameters
  readonly 'workspace.technicalSeparator': NoMessageParameters
  readonly 'workspace.runtimeMetadata': NoMessageParameters
  readonly 'workspace.cancel': NoMessageParameters
  readonly 'workspace.confirmStop': NoMessageParameters
  readonly 'workspace.stateStarting': NoMessageParameters
  readonly 'workspace.stateRunning': NoMessageParameters
  readonly 'workspace.stateNeedsInteraction': NoMessageParameters
  readonly 'workspace.stateTrustRequired': NoMessageParameters
  readonly 'workspace.stateLoginRequired': NoMessageParameters
  readonly 'workspace.stateStopping': NoMessageParameters
  readonly 'workspace.stateExited': NoMessageParameters
  readonly 'workspace.stateStopped': NoMessageParameters
  readonly 'workspace.stateMissing': NoMessageParameters
  readonly 'workspace.stateCollision': NoMessageParameters
  readonly 'workspace.stateBroken': NoMessageParameters
  readonly 'workspace.stateUnknown': NoMessageParameters
}

export const workspaceCatalog = defineCatalogShard<WorkspaceMessageParameters>(
  'workspace',
  {
    en: {
      'workspace.title': () => 'Interactive workspace',
      'workspace.eyebrow': () => 'Web Agent Workspace',
      'workspace.description': () =>
        'Manage the controlled Claude or Codex workspace lifecycle for a formal READY Project. Terminal access requires local trust admission.',
      'workspace.selectionEyebrow': () => 'Workspace selection',
      'workspace.selectionTitle': () => 'Select a Project and AgentType',
      'workspace.readyProject': () => 'Formal READY Project',
      'workspace.agentType': () => 'AgentType',
      'workspace.selectProject': () => 'Select a Project',
      'workspace.loadingProjects': () => 'Loading Projects…',
      'workspace.noReadyProjects': () => 'No READY Projects',
      'workspace.projectListUnavailable': () =>
        'The Project list is temporarily unavailable. Refresh and try again.',
      'workspace.currentProject': () => 'Current Project',
      'workspace.currentAgentType': () => 'Current AgentType',
      'workspace.unregistered': () =>
        'This AgentType is not registered and cannot start a workspace.',
      'workspace.loadingWorkspace': () => 'Loading workspace information…',
      'workspace.infoUnavailable': () =>
        'Workspace information is temporarily unavailable.',
      'workspace.lifecycleEyebrow': () => 'Lifecycle state',
      'workspace.statusTitle': () => 'Workspace record status',
      'workspace.unloaded': () => 'Not loaded',
      'workspace.runtimeStatus': () => 'Runtime status',
      'workspace.processStatus': () => 'Process status',
      'workspace.reconciliationStatus': () => 'Reconciliation status',
      'workspace.refresh': () => 'Refresh workspace status',
      'workspace.noticeStartConfirmed': () =>
        'The start request was confirmed. Process status and browser terminal connection status are shown separately.',
      'workspace.noticeStopConfirmed': () =>
        'The managed process stopped. Project and Git changes were preserved.',
      'workspace.noticeRecoveryRequired': () =>
        'Runtime recovery review is required. Workspace operations are paused.',
      'workspace.terminalEyebrow': () => 'Terminal viewport',
      'workspace.terminalTitle': () => 'Controlled terminal',
      'workspace.terminalPlaceholder': () =>
        'Connect only after the current Project, Runtime and local trust provider are admitted.',
      'workspace.providerUnavailable': () =>
        'The managed browser trust provider is unavailable, so no terminal ticket was requested.',
      'workspace.connectionStatus': () => 'Connection status',
      'workspace.terminalIdle': () => 'Ready to connect',
      'workspace.terminalAcquiringTicket': () => 'Requesting terminal ticket',
      'workspace.terminalAuthorizingTrust': () => 'Checking local trust',
      'workspace.terminalConnecting': () => 'Connecting transport',
      'workspace.terminalHandshaking': () => 'Verifying terminal channel',
      'workspace.terminalConnected': () => 'Connected',
      'workspace.terminalDetaching': () => 'Disconnecting',
      'workspace.terminalDetached': () => 'Disconnected',
      'workspace.terminalStopping': () => 'Stopping workspace',
      'workspace.terminalStopped': () => 'Stopped',
      'workspace.terminalFenced': () => 'Connection fenced',
      'workspace.terminalUnavailable': () => 'Trust provider unavailable',
      'workspace.redrawTruncated': () =>
        'The initial terminal redraw was bounded. Refreshing the terminal starts a new bounded redraw.',
      'workspace.storageWarning': () =>
        'Terminal content is not stored in browser storage or offered as a history download.',
      'workspace.start': () => 'Start workspace',
      'workspace.stop': () => 'Stop workspace',
      'workspace.connect': () => 'Connect terminal',
      'workspace.reconnect': () => 'Reconnect',
      'workspace.detach': () => 'Disconnect',
      'workspace.sendInput': () => 'Send input',
      'workspace.inputPlaceholder': () => 'Type terminal input and press Enter',
      'workspace.inputPasteRejected': () =>
        'Multi-line paste is not sent through this input.',
      'workspace.inputTooLong': () => 'Terminal input is limited to 16 KiB.',
      'workspace.inputSending': () => 'Sending terminal input…',
      'workspace.inputRateLimited': () =>
        'Input was rate limited and was not sent. Try again.',
      'workspace.inputUncertain': () =>
        'Input delivery is uncertain and will not be resent.',
      'workspace.viewportResize': () =>
        'Terminal size follows the visible viewport.',
      'workspace.confirmTitle': () => 'Confirm workspace stop',
      'workspace.confirmDescription': () =>
        'Stop only the managed process and preserve Project and Git changes.',
      'workspace.workspaceId': () => 'Workspace ID',
      'workspace.generation': () => 'Generation',
      'workspace.technicalSeparator': () => ': ',
      'workspace.runtimeMetadata': () => 'Runtime metadata',
      'workspace.cancel': () => 'Cancel',
      'workspace.confirmStop': () => 'Confirm stop',
      'workspace.stateStarting': () => 'Starting',
      'workspace.stateRunning': () => 'Running',
      'workspace.stateNeedsInteraction': () => 'Interaction required',
      'workspace.stateTrustRequired': () => 'Local trust confirmation required',
      'workspace.stateLoginRequired': () => 'Local login required',
      'workspace.stateStopping': () => 'Stopping',
      'workspace.stateExited': () => 'Process exited',
      'workspace.stateStopped': () => 'Stopped',
      'workspace.stateMissing': () => 'Process missing',
      'workspace.stateCollision': () => 'Conflict detected',
      'workspace.stateBroken': () => 'Recovery review required',
      'workspace.stateUnknown': () => 'Status unknown',
    },
    'zh-CN': {
      'workspace.title': () => '交互式工作区',
      'workspace.eyebrow': () => 'Web Agent Workspace',
      'workspace.description': () =>
        '在正式 READY Project 中管理受控的 Claude 或 Codex 工作区生命周期。终端访问需要完成本地信任准入。',
      'workspace.selectionEyebrow': () => '工作区选择',
      'workspace.selectionTitle': () => '选择 Project 与 AgentType',
      'workspace.readyProject': () => '正式 READY Project',
      'workspace.agentType': () => 'AgentType',
      'workspace.selectProject': () => '请选择 Project',
      'workspace.loadingProjects': () => '正在加载 Project…',
      'workspace.noReadyProjects': () => '暂无 READY Project',
      'workspace.projectListUnavailable': () =>
        'Project 列表暂不可用，请刷新后重试。',
      'workspace.currentProject': () => '当前 Project',
      'workspace.currentAgentType': () => '当前 AgentType',
      'workspace.unregistered': () =>
        '当前 AgentType 尚未注册，无法启动工作区。',
      'workspace.loadingWorkspace': () => '正在读取工作区信息…',
      'workspace.infoUnavailable': () => '工作区信息暂不可用。',
      'workspace.lifecycleEyebrow': () => '生命周期状态',
      'workspace.statusTitle': () => '工作区记录状态',
      'workspace.unloaded': () => '未加载',
      'workspace.runtimeStatus': () => 'Runtime 状态',
      'workspace.processStatus': () => '进程状态',
      'workspace.reconciliationStatus': () => 'Reconciliation 状态',
      'workspace.refresh': () => '刷新工作区状态',
      'workspace.noticeStartConfirmed': () =>
        '启动请求已确认。进程状态与浏览器终端连接状态分别显示。',
      'workspace.noticeStopConfirmed': () =>
        '受管进程已停止，Project 和 Git 修改已保留。',
      'workspace.noticeRecoveryRequired': () =>
        'Runtime 需要恢复核对，工作区操作已暂停。',
      'workspace.terminalEyebrow': () => '终端视口',
      'workspace.terminalTitle': () => '受控终端',
      'workspace.terminalPlaceholder': () =>
        '仅在当前 Project、Runtime 与本地信任 provider 完成准入后连接终端。',
      'workspace.providerUnavailable': () =>
        '受管浏览器信任 provider 不可用，因此未请求终端 ticket。',
      'workspace.connectionStatus': () => '连接状态',
      'workspace.terminalIdle': () => '可以连接',
      'workspace.terminalAcquiringTicket': () => '正在请求终端 ticket',
      'workspace.terminalAuthorizingTrust': () => '正在核对本地信任',
      'workspace.terminalConnecting': () => '正在连接传输',
      'workspace.terminalHandshaking': () => '正在验证终端通道',
      'workspace.terminalConnected': () => '已连接',
      'workspace.terminalDetaching': () => '正在断开',
      'workspace.terminalDetached': () => '已断开',
      'workspace.terminalStopping': () => '正在停止工作区',
      'workspace.terminalStopped': () => '已停止',
      'workspace.terminalFenced': () => '连接已围栏',
      'workspace.terminalUnavailable': () => '信任 provider 不可用',
      'workspace.redrawTruncated': () =>
        '初始终端重绘已受限。刷新终端会开始新的受限重绘。',
      'workspace.storageWarning': () =>
        '终端内容不写入浏览器存储，也不提供历史记录下载。',
      'workspace.start': () => '启动工作区',
      'workspace.stop': () => '停止工作区',
      'workspace.connect': () => '连接终端',
      'workspace.reconnect': () => '重新连接',
      'workspace.detach': () => '断开连接',
      'workspace.sendInput': () => '发送输入',
      'workspace.inputPlaceholder': () => '输入终端内容后按 Enter 发送',
      'workspace.inputPasteRejected': () => '此输入框不会发送多行粘贴内容。',
      'workspace.inputTooLong': () => '终端输入最多为 16 KiB。',
      'workspace.inputSending': () => '正在发送终端输入…',
      'workspace.inputRateLimited': () =>
        '输入已被限流，未发送到终端。请稍后重试。',
      'workspace.inputUncertain': () => '输入结果不确定，系统不会自动重发。',
      'workspace.viewportResize': () => '终端尺寸会跟随可见视口。',
      'workspace.confirmTitle': () => '确认停止工作区',
      'workspace.confirmDescription': () =>
        '仅停止受管进程，保留 Project 和 Git 修改。',
      'workspace.workspaceId': () => '工作区 ID',
      'workspace.generation': () => '代次',
      'workspace.technicalSeparator': () => '：',
      'workspace.runtimeMetadata': () => 'Runtime 元数据',
      'workspace.cancel': () => '取消',
      'workspace.confirmStop': () => '确认停止',
      'workspace.stateStarting': () => '启动中',
      'workspace.stateRunning': () => '运行中',
      'workspace.stateNeedsInteraction': () => '需要交互',
      'workspace.stateTrustRequired': () => '需要本地确认信任',
      'workspace.stateLoginRequired': () => '需要本地登录',
      'workspace.stateStopping': () => '停止中',
      'workspace.stateExited': () => '进程已退出',
      'workspace.stateStopped': () => '已停止',
      'workspace.stateMissing': () => '进程不存在',
      'workspace.stateCollision': () => '检测到冲突',
      'workspace.stateBroken': () => '需要恢复核对',
      'workspace.stateUnknown': () => '状态未知',
    },
  },
)
