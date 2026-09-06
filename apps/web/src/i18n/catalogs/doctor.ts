import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface DoctorMessageParameters {
  readonly 'doctor.title': NoMessageParameters
  readonly 'doctor.eyebrow': NoMessageParameters
  readonly 'doctor.description': NoMessageParameters
  readonly 'doctor.ready': NoMessageParameters
  readonly 'doctor.notReady': NoMessageParameters
  readonly 'doctor.loading': NoMessageParameters
  readonly 'doctor.unavailable': NoMessageParameters
  readonly 'doctor.checksAria': NoMessageParameters
  readonly 'doctor.configurationValid': NoMessageParameters
  readonly 'doctor.databaseReachable': NoMessageParameters
  readonly 'doctor.migrationsCurrent': NoMessageParameters
  readonly 'doctor.adminInitialized': NoMessageParameters
  readonly 'doctor.controlPlaneReady': NoMessageParameters
  readonly 'doctor.runtimeDiagnostic': NoMessageParameters
  readonly 'doctor.workspaceDiagnostic': NoMessageParameters
  readonly 'doctor.codexTitle': NoMessageParameters
  readonly 'doctor.claudeTitle': NoMessageParameters
  readonly 'doctor.projectsTitle': NoMessageParameters
  readonly 'doctor.installed': NoMessageParameters
  readonly 'doctor.notInstalled': NoMessageParameters
  readonly 'doctor.available': NoMessageParameters
  readonly 'doctor.unknown': NoMessageParameters
  readonly 'doctor.capabilitySupported': NoMessageParameters
  readonly 'doctor.capabilityUnsupported': NoMessageParameters
  readonly 'doctor.remoteRunning': NoMessageParameters
  readonly 'doctor.remoteStopped': NoMessageParameters
  readonly 'doctor.remoteBroken': NoMessageParameters
  readonly 'doctor.authenticationAuthenticated': NoMessageParameters
  readonly 'doctor.authenticationUnauthenticated': NoMessageParameters
  readonly 'doctor.version': NoMessageParameters
  readonly 'doctor.installation': NoMessageParameters
  readonly 'doctor.remoteCapability': NoMessageParameters
  readonly 'doctor.remoteState': NoMessageParameters
  readonly 'doctor.claudeVersion': NoMessageParameters
  readonly 'doctor.authentication': NoMessageParameters
  readonly 'doctor.tmuxVersion': NoMessageParameters
  readonly 'doctor.managedSessions': NoMessageParameters
  readonly 'doctor.unmanagedSessions': NoMessageParameters
  readonly 'doctor.workspaceWarnings': NoMessageParameters
  readonly 'doctor.projectsCount': Readonly<{ count: string }>
  readonly 'doctor.projectRoot': NoMessageParameters
  readonly 'doctor.git': NoMessageParameters
  readonly 'doctor.githubCli': NoMessageParameters
  readonly 'doctor.githubAuthentication': NoMessageParameters
  readonly 'doctor.scopeNote': NoMessageParameters
  readonly 'doctor.findingsAria': NoMessageParameters
  readonly 'doctor.findingUnknown': NoMessageParameters
  readonly 'doctor.findingCodexNotInstalled': NoMessageParameters
  readonly 'doctor.findingCodexOwnerMismatch': NoMessageParameters
  readonly 'doctor.findingCodexVersionUnavailable': NoMessageParameters
  readonly 'doctor.findingCodexCapabilityProbeFailed': NoMessageParameters
  readonly 'doctor.findingCodexLegacyUnitPresent': NoMessageParameters
  readonly 'doctor.findingCodexRemoteStatusUnsupported': NoMessageParameters
  readonly 'doctor.findingCodexAlternativeInvalid': NoMessageParameters
  readonly 'doctor.findingCodexExecutableInvalid': NoMessageParameters
  readonly 'doctor.findingCodexMultipleExecutables': NoMessageParameters
  readonly 'doctor.findingCodexInstallationConflict': NoMessageParameters
  readonly 'doctor.findingClaudeNotInstalled': NoMessageParameters
  readonly 'doctor.findingClaudeVersionUnknown': NoMessageParameters
  readonly 'doctor.findingClaudeRemoteCapabilityUnknown': NoMessageParameters
  readonly 'doctor.findingProjectWorkspaceUnavailable': NoMessageParameters
}

export const doctorCatalog = defineCatalogShard<DoctorMessageParameters>(
  'doctor',
  {
    en: {
      'doctor.title': () => 'Doctor',
      'doctor.eyebrow': () => 'Diagnostics',
      'doctor.description': () =>
        "Read-only checks for AgentBox's own control-plane foundation.",
      'doctor.ready': () => 'Ready',
      'doctor.notReady': () => 'Not ready',
      'doctor.loading': () => 'Running safe checks…',
      'doctor.unavailable': () => 'Diagnostics unavailable',
      'doctor.checksAria': () => 'Control plane checks',
      'doctor.configurationValid': () => 'Configuration valid',
      'doctor.databaseReachable': () => 'Database reachable',
      'doctor.migrationsCurrent': () => 'Migration state current',
      'doctor.adminInitialized': () => 'Administrator initialized',
      'doctor.controlPlaneReady': () => 'Control plane ready',
      'doctor.runtimeDiagnostic': () => 'Runtime diagnostic',
      'doctor.workspaceDiagnostic': () => 'Workspace diagnostic',
      'doctor.codexTitle': () => 'Codex',
      'doctor.claudeTitle': () => 'Claude + tmux',
      'doctor.projectsTitle': () => 'Projects + GitHub',
      'doctor.installed': () => 'Installed',
      'doctor.notInstalled': () => 'Not installed',
      'doctor.available': () => 'Available',
      'doctor.unknown': () => 'Unknown',
      'doctor.capabilitySupported': () => 'Supported',
      'doctor.capabilityUnsupported': () => 'Unsupported',
      'doctor.remoteRunning': () => 'Running',
      'doctor.remoteStopped': () => 'Stopped',
      'doctor.remoteBroken': () => 'Broken',
      'doctor.authenticationAuthenticated': () => 'Authenticated',
      'doctor.authenticationUnauthenticated': () => 'Unauthenticated',
      'doctor.version': () => 'Version',
      'doctor.installation': () => 'Installation',
      'doctor.remoteCapability': () => 'Remote capability',
      'doctor.remoteState': () => 'Remote state',
      'doctor.claudeVersion': () => 'Claude version',
      'doctor.authentication': () => 'Authentication',
      'doctor.tmuxVersion': () => 'tmux version',
      'doctor.managedSessions': () => 'Managed sessions',
      'doctor.unmanagedSessions': () => 'Unmanaged sessions',
      'doctor.workspaceWarnings': () => 'Workspace interaction warnings',
      'doctor.projectsCount': ({ count }) => `${count} Projects`,
      'doctor.projectRoot': () => 'Project Root',
      'doctor.git': () => 'Git',
      'doctor.githubCli': () => 'GitHub CLI',
      'doctor.githubAuthentication': () => 'GitHub authentication',
      'doctor.scopeNote': () =>
        'Runtime checks use safe adapter summaries. Unmanaged tmux names, pane output, credentials, private Runtime configuration, general systemd state, and host networking are not exposed here.',
      'doctor.findingsAria': () => 'Diagnostic findings',
      'doctor.findingUnknown': () => 'A runtime diagnostic was reported.',
      'doctor.findingCodexNotInstalled': () => 'Codex is not installed.',
      'doctor.findingCodexOwnerMismatch': () =>
        'The selected Codex executable needs an ownership review.',
      'doctor.findingCodexVersionUnavailable': () =>
        'The Codex version could not be read safely.',
      'doctor.findingCodexCapabilityProbeFailed': () =>
        'Codex capability probing did not complete.',
      'doctor.findingCodexLegacyUnitPresent': () =>
        'A legacy Codex service unit is present.',
      'doctor.findingCodexRemoteStatusUnsupported': () =>
        'Codex does not report Remote status.',
      'doctor.findingCodexAlternativeInvalid': () =>
        'An alternative Codex executable is invalid.',
      'doctor.findingCodexExecutableInvalid': () =>
        'The selected Codex executable is invalid.',
      'doctor.findingCodexMultipleExecutables': () =>
        'Multiple Codex executables need review.',
      'doctor.findingCodexInstallationConflict': () =>
        'The Codex installation has a conflict.',
      'doctor.findingClaudeNotInstalled': () => 'Claude is not installed.',
      'doctor.findingClaudeVersionUnknown': () =>
        'The Claude version could not be read safely.',
      'doctor.findingClaudeRemoteCapabilityUnknown': () =>
        'Claude Remote capability could not be confirmed.',
      'doctor.findingProjectWorkspaceUnavailable': () =>
        'One or more ready Projects do not have an available workspace.',
    },
    'zh-CN': {
      'doctor.title': () => '诊断',
      'doctor.eyebrow': () => '诊断信息',
      'doctor.description': () => '对 AgentBox 控制平面基础能力进行只读检查。',
      'doctor.ready': () => '已就绪',
      'doctor.notReady': () => '未就绪',
      'doctor.loading': () => '正在运行安全检查…',
      'doctor.unavailable': () => '诊断信息暂不可用',
      'doctor.checksAria': () => '控制平面检查',
      'doctor.configurationValid': () => '配置有效',
      'doctor.databaseReachable': () => '数据库可访问',
      'doctor.migrationsCurrent': () => '迁移状态最新',
      'doctor.adminInitialized': () => '管理员已初始化',
      'doctor.controlPlaneReady': () => '控制平面已就绪',
      'doctor.runtimeDiagnostic': () => 'Runtime 诊断',
      'doctor.workspaceDiagnostic': () => 'Workspace 诊断',
      'doctor.codexTitle': () => 'Codex',
      'doctor.claudeTitle': () => 'Claude + tmux',
      'doctor.projectsTitle': () => 'Projects + GitHub',
      'doctor.installed': () => '已安装',
      'doctor.notInstalled': () => '未安装',
      'doctor.available': () => '可用',
      'doctor.unknown': () => '未知',
      'doctor.capabilitySupported': () => '支持',
      'doctor.capabilityUnsupported': () => '不支持',
      'doctor.remoteRunning': () => '运行中',
      'doctor.remoteStopped': () => '已停止',
      'doctor.remoteBroken': () => '异常',
      'doctor.authenticationAuthenticated': () => '已验证',
      'doctor.authenticationUnauthenticated': () => '未验证',
      'doctor.version': () => '版本',
      'doctor.installation': () => '安装',
      'doctor.remoteCapability': () => 'Remote 能力',
      'doctor.remoteState': () => 'Remote 状态',
      'doctor.claudeVersion': () => 'Claude 版本',
      'doctor.authentication': () => '身份验证',
      'doctor.tmuxVersion': () => 'tmux 版本',
      'doctor.managedSessions': () => '托管会话',
      'doctor.unmanagedSessions': () => '非托管会话',
      'doctor.workspaceWarnings': () => 'Workspace 交互警告',
      'doctor.projectsCount': ({ count }) => `${count} 个 Projects`,
      'doctor.projectRoot': () => 'Project 根目录',
      'doctor.git': () => 'Git',
      'doctor.githubCli': () => 'GitHub CLI',
      'doctor.githubAuthentication': () => 'GitHub 身份验证',
      'doctor.scopeNote': () =>
        'Runtime 检查仅使用安全的适配器摘要。不会在此显示非托管 tmux 名称、pane 输出、凭据、私有 Runtime 配置、常规 systemd 状态或主机网络信息。',
      'doctor.findingsAria': () => '诊断发现',
      'doctor.findingUnknown': () => '发现一项 Runtime 诊断信息。',
      'doctor.findingCodexNotInstalled': () => '未安装 Codex。',
      'doctor.findingCodexOwnerMismatch': () =>
        '所选 Codex 可执行文件需要检查所有权。',
      'doctor.findingCodexVersionUnavailable': () =>
        '无法安全读取 Codex 版本。',
      'doctor.findingCodexCapabilityProbeFailed': () =>
        'Codex 能力探测未完成。',
      'doctor.findingCodexLegacyUnitPresent': () =>
        '检测到旧版 Codex service unit。',
      'doctor.findingCodexRemoteStatusUnsupported': () =>
        'Codex 不报告 Remote 状态。',
      'doctor.findingCodexAlternativeInvalid': () =>
        '一个候选 Codex 可执行文件无效。',
      'doctor.findingCodexExecutableInvalid': () =>
        '所选 Codex 可执行文件无效。',
      'doctor.findingCodexMultipleExecutables': () =>
        '需要检查多个 Codex 可执行文件。',
      'doctor.findingCodexInstallationConflict': () => 'Codex 安装存在冲突。',
      'doctor.findingClaudeNotInstalled': () => '未安装 Claude。',
      'doctor.findingClaudeVersionUnknown': () => '无法安全读取 Claude 版本。',
      'doctor.findingClaudeRemoteCapabilityUnknown': () =>
        '无法确认 Claude Remote 能力。',
      'doctor.findingProjectWorkspaceUnavailable': () =>
        '一个或多个已就绪 Project 没有可用的 workspace。',
    },
  },
)
