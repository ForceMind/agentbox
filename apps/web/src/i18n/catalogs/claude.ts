import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface ClaudeMessageParameters {
  readonly 'claude.title': NoMessageParameters
  readonly 'claude.eyebrow': NoMessageParameters
  readonly 'claude.description': NoMessageParameters
  readonly 'claude.refresh': NoMessageParameters
  readonly 'claude.loading': NoMessageParameters
  readonly 'claude.statusUnavailable': NoMessageParameters
  readonly 'claude.installationAria': NoMessageParameters
  readonly 'claude.claudeCode': NoMessageParameters
  readonly 'claude.installation': NoMessageParameters
  readonly 'claude.installed': NoMessageParameters
  readonly 'claude.yes': NoMessageParameters
  readonly 'claude.no': NoMessageParameters
  readonly 'claude.version': NoMessageParameters
  readonly 'claude.unknown': NoMessageParameters
  readonly 'claude.authentication': NoMessageParameters
  readonly 'claude.remoteCapability': NoMessageParameters
  readonly 'claude.persistence': NoMessageParameters
  readonly 'claude.tmux': NoMessageParameters
  readonly 'claude.unavailable': NoMessageParameters
  readonly 'claude.managedSessions': NoMessageParameters
  readonly 'claude.unmanagedSessions': NoMessageParameters
  readonly 'claude.workspaceWarnings': NoMessageParameters
  readonly 'claude.projects': NoMessageParameters
  readonly 'claude.remoteSessions': NoMessageParameters
  readonly 'claude.noConfiguredProjects': NoMessageParameters
  readonly 'claude.noConfiguredProjectsDescription': NoMessageParameters
  readonly 'claude.sessionsAria': NoMessageParameters
  readonly 'claude.project': NoMessageParameters
  readonly 'claude.stateRunning': NoMessageParameters
  readonly 'claude.stateStopped': NoMessageParameters
  readonly 'claude.stateStarting': NoMessageParameters
  readonly 'claude.stateNeedsInteraction': NoMessageParameters
  readonly 'claude.stateBroken': NoMessageParameters
  readonly 'claude.stateUnknown': NoMessageParameters
  readonly 'claude.remoteReadiness': NoMessageParameters
  readonly 'claude.ready': NoMessageParameters
  readonly 'claude.workspaceTrust': NoMessageParameters
  readonly 'claude.workspaceUnknown': NoMessageParameters
  readonly 'claude.workspaceRequiresConfirmation': NoMessageParameters
  readonly 'claude.workspaceInitialized': NoMessageParameters
  readonly 'claude.interactionNotice': NoMessageParameters
  readonly 'claude.attachLabel': NoMessageParameters
  readonly 'claude.copyAttach': NoMessageParameters
  readonly 'claude.copied': NoMessageParameters
  readonly 'claude.starting': NoMessageParameters
  readonly 'claude.startSession': NoMessageParameters
  readonly 'claude.stopping': NoMessageParameters
  readonly 'claude.stopSession': NoMessageParameters
  readonly 'claude.stopNote': NoMessageParameters
  readonly 'claude.recentOutput': NoMessageParameters
  readonly 'claude.sensitive': NoMessageParameters
  readonly 'claude.outputDescription': NoMessageParameters
  readonly 'claude.outputLoading': NoMessageParameters
  readonly 'claude.reveal': NoMessageParameters
  readonly 'claude.noRecentOutput': NoMessageParameters
  readonly 'claude.outputTruncated': NoMessageParameters
  readonly 'claude.hide': NoMessageParameters
  readonly 'claude.actionFailed': NoMessageParameters
}

export const claudeCatalog = defineCatalogShard<ClaudeMessageParameters>(
  'claude',
  {
    en: {
      'claude.title': () => 'Claude',
      'claude.eyebrow': () => 'Runtime',
      'claude.description': () =>
        "Project-scoped Claude Code Remote sessions persisted by the Runtime user's tmux server.",
      'claude.refresh': () => 'Refresh',
      'claude.loading': () => 'Inspecting Claude and managed sessions…',
      'claude.statusUnavailable': () => 'Claude status unavailable',
      'claude.installationAria': () => 'Claude installation status',
      'claude.claudeCode': () => 'Claude Code',
      'claude.installation': () => 'Installation',
      'claude.installed': () => 'Installed',
      'claude.yes': () => 'Yes',
      'claude.no': () => 'No',
      'claude.version': () => 'Version',
      'claude.unknown': () => 'Unknown',
      'claude.authentication': () => 'Authentication',
      'claude.remoteCapability': () => 'Remote capability',
      'claude.persistence': () => 'Persistence',
      'claude.tmux': () => 'tmux',
      'claude.unavailable': () => 'Unavailable',
      'claude.managedSessions': () => 'Managed sessions',
      'claude.unmanagedSessions': () => 'Unmanaged sessions',
      'claude.workspaceWarnings': () => 'Workspace warnings',
      'claude.projects': () => 'Projects',
      'claude.remoteSessions': () => 'Remote sessions',
      'claude.noConfiguredProjects': () => 'No configured projects',
      'claude.noConfiguredProjectsDescription': () =>
        'Existing immediate directories under the configured Project root appear here.',
      'claude.sessionsAria': () => 'Claude Project sessions',
      'claude.project': () => 'Project',
      'claude.stateRunning': () => 'Running',
      'claude.stateStopped': () => 'Stopped',
      'claude.stateStarting': () => 'Starting',
      'claude.stateNeedsInteraction': () => 'Needs Interaction',
      'claude.stateBroken': () => 'Broken',
      'claude.stateUnknown': () => 'Unknown',
      'claude.remoteReadiness': () => 'Remote readiness',
      'claude.ready': () => 'Ready',
      'claude.workspaceTrust': () => 'Workspace Trust',
      'claude.workspaceUnknown': () => 'Unknown',
      'claude.workspaceRequiresConfirmation': () =>
        'Requires user confirmation',
      'claude.workspaceInitialized': () => 'Initialized by AgentBox',
      'claude.interactionNotice': () =>
        'Claude requires terminal interaction before Remote Control can continue. AgentBox never accepts Workspace Trust automatically. Attach, confirm the Project, then exit the interactive Claude session and start Remote Control again.',
      'claude.attachLabel': () => "Attach from the Runtime user's terminal",
      'claude.copyAttach': () => 'Copy attach command',
      'claude.copied': () => 'Copied',
      'claude.starting': () => 'Starting…',
      'claude.startSession': () => 'Start Session',
      'claude.stopping': () => 'Stopping…',
      'claude.stopSession': () => 'Stop Session',
      'claude.stopNote': () =>
        'Stopping ends only this Claude/tmux session. It does not delete the Project.',
      'claude.recentOutput': () => 'Recent session output',
      'claude.sensitive': () => 'Sensitive',
      'claude.outputDescription': () =>
        'May contain Project or model output. It is fetched only when revealed.',
      'claude.outputLoading': () => 'Loading…',
      'claude.reveal': () => 'Reveal',
      'claude.noRecentOutput': () => 'No recent output.',
      'claude.outputTruncated': () =>
        'Output was truncated to the safety limit.',
      'claude.hide': () => 'Hide',
      'claude.actionFailed': () => 'Claude action failed',
    },
    'zh-CN': {
      'claude.title': () => 'Claude',
      'claude.eyebrow': () => 'Runtime',
      'claude.description': () =>
        '在 Project 范围内管理 Claude Code Remote 会话；会话由 Runtime 用户的 tmux server 持久化。',
      'claude.refresh': () => '刷新',
      'claude.loading': () => '正在检查 Claude 和托管会话…',
      'claude.statusUnavailable': () => 'Claude 状态暂不可用',
      'claude.installationAria': () => 'Claude 安装状态',
      'claude.claudeCode': () => 'Claude Code',
      'claude.installation': () => '安装',
      'claude.installed': () => '已安装',
      'claude.yes': () => '是',
      'claude.no': () => '否',
      'claude.version': () => '版本',
      'claude.unknown': () => '未知',
      'claude.authentication': () => '身份验证',
      'claude.remoteCapability': () => 'Remote 能力',
      'claude.persistence': () => '持久化',
      'claude.tmux': () => 'tmux',
      'claude.unavailable': () => '不可用',
      'claude.managedSessions': () => '托管会话',
      'claude.unmanagedSessions': () => '非托管会话',
      'claude.workspaceWarnings': () => 'Workspace 警告',
      'claude.projects': () => 'Projects',
      'claude.remoteSessions': () => 'Remote 会话',
      'claude.noConfiguredProjects': () => '没有已配置的 Project',
      'claude.noConfiguredProjectsDescription': () =>
        '已配置 Project 根目录下现有的直接子目录会显示在此处。',
      'claude.sessionsAria': () => 'Claude Project 会话',
      'claude.project': () => 'Project',
      'claude.stateRunning': () => '运行中',
      'claude.stateStopped': () => '已停止',
      'claude.stateStarting': () => '正在启动',
      'claude.stateNeedsInteraction': () => '需要交互',
      'claude.stateBroken': () => '异常',
      'claude.stateUnknown': () => '未知',
      'claude.remoteReadiness': () => 'Remote 就绪状态',
      'claude.ready': () => '已就绪',
      'claude.workspaceTrust': () => 'Workspace Trust',
      'claude.workspaceUnknown': () => '未知',
      'claude.workspaceRequiresConfirmation': () => '需要用户确认',
      'claude.workspaceInitialized': () => '已由 AgentBox 初始化',
      'claude.interactionNotice': () =>
        '继续使用 Remote Control 前，Claude 需要在 terminal 中完成交互。AgentBox 绝不会自动接受 Workspace Trust。请 attach 会话、确认 Project，然后退出交互式 Claude 会话并重新启动 Remote Control。',
      'claude.attachLabel': () => '从 Runtime 用户的 terminal attach',
      'claude.copyAttach': () => '复制 attach command',
      'claude.copied': () => '已复制',
      'claude.starting': () => '正在启动…',
      'claude.startSession': () => '启动会话',
      'claude.stopping': () => '正在停止…',
      'claude.stopSession': () => '停止会话',
      'claude.stopNote': () =>
        '停止操作只会结束当前 Claude/tmux 会话，不会删除 Project。',
      'claude.recentOutput': () => '最近的会话输出',
      'claude.sensitive': () => '敏感内容',
      'claude.outputDescription': () =>
        '其中可能包含 Project 或模型输出；仅在明确显示时获取。',
      'claude.outputLoading': () => '正在加载…',
      'claude.reveal': () => '显示',
      'claude.noRecentOutput': () => '没有最近的输出。',
      'claude.outputTruncated': () => '输出已截断到安全上限。',
      'claude.hide': () => '隐藏',
      'claude.actionFailed': () => 'Claude 操作失败',
    },
  },
)
