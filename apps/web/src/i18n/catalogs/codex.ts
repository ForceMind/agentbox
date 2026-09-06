import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface CodexMessageParameters {
  readonly 'codex.title': NoMessageParameters
  readonly 'codex.eyebrow': NoMessageParameters
  readonly 'codex.description': NoMessageParameters
  readonly 'codex.loading': NoMessageParameters
  readonly 'codex.statusUnavailableTitle': NoMessageParameters
  readonly 'codex.installationEyebrow': NoMessageParameters
  readonly 'codex.installationTitle': NoMessageParameters
  readonly 'codex.installedLabel': NoMessageParameters
  readonly 'codex.installedYes': NoMessageParameters
  readonly 'codex.installedNo': NoMessageParameters
  readonly 'codex.versionLabel': NoMessageParameters
  readonly 'codex.installationTypeLabel': NoMessageParameters
  readonly 'codex.authenticationLabel': NoMessageParameters
  readonly 'codex.executableLabel': NoMessageParameters
  readonly 'codex.unavailable': NoMessageParameters
  readonly 'codex.remoteEyebrow': NoMessageParameters
  readonly 'codex.remoteTitle': NoMessageParameters
  readonly 'codex.observedStateLabel': NoMessageParameters
  readonly 'codex.confidenceLabel': NoMessageParameters
  readonly 'codex.startRemote': NoMessageParameters
  readonly 'codex.startingRemote': NoMessageParameters
  readonly 'codex.stopRemote': NoMessageParameters
  readonly 'codex.stoppingRemote': NoMessageParameters
  readonly 'codex.refreshStatusLabel': NoMessageParameters
  readonly 'codex.pairEyebrow': NoMessageParameters
  readonly 'codex.pairTitle': NoMessageParameters
  readonly 'codex.sensitive': NoMessageParameters
  readonly 'codex.pairDescription': NoMessageParameters
  readonly 'codex.generatingPair': NoMessageParameters
  readonly 'codex.pairNewDevice': NoMessageParameters
  readonly 'codex.pairSecretLabel': NoMessageParameters
  readonly 'codex.pairTimeoutNote': NoMessageParameters
  readonly 'codex.copy': NoMessageParameters
  readonly 'codex.copied': NoMessageParameters
  readonly 'codex.copyFailed': NoMessageParameters
  readonly 'codex.hide': NoMessageParameters
  readonly 'codex.diagnosticsEyebrow': NoMessageParameters
  readonly 'codex.diagnosticsTitle': NoMessageParameters
  readonly 'codex.diagnosticsEmpty': NoMessageParameters
  readonly 'codex.actionFailedTitle': NoMessageParameters
  readonly 'codex.confirmEyebrow': NoMessageParameters
  readonly 'codex.confirmTitle': NoMessageParameters
  readonly 'codex.confirmDescription': NoMessageParameters
  readonly 'codex.generateCode': NoMessageParameters
  readonly 'codex.capabilitySupported': NoMessageParameters
  readonly 'codex.capabilityUnsupported': NoMessageParameters
  readonly 'codex.capabilityUnknown': NoMessageParameters
  readonly 'codex.remoteRunning': NoMessageParameters
  readonly 'codex.remoteStopped': NoMessageParameters
  readonly 'codex.remoteBroken': NoMessageParameters
  readonly 'codex.remoteUnknown': NoMessageParameters
  readonly 'codex.confidenceReported': NoMessageParameters
  readonly 'codex.confidenceInferred': NoMessageParameters
  readonly 'codex.confidenceUnknown': NoMessageParameters
  readonly 'codex.installationStandalone': NoMessageParameters
  readonly 'codex.installationNpm': NoMessageParameters
  readonly 'codex.installationConflict': NoMessageParameters
  readonly 'codex.installationUnknown': NoMessageParameters
  readonly 'codex.authenticationAuthenticated': NoMessageParameters
  readonly 'codex.authenticationUnauthenticated': NoMessageParameters
  readonly 'codex.authenticationUnknown': NoMessageParameters
  readonly 'codex.severityCritical': NoMessageParameters
  readonly 'codex.severityHigh': NoMessageParameters
  readonly 'codex.severityMedium': NoMessageParameters
  readonly 'codex.severityLow': NoMessageParameters
  readonly 'codex.severityWarning': NoMessageParameters
  readonly 'codex.severityInfo': NoMessageParameters
}

export const codexCatalog = defineCatalogShard<CodexMessageParameters>(
  'codex',
  {
    en: {
      'codex.title': () => 'Codex',
      'codex.eyebrow': () => 'Runtime',
      'codex.description': () =>
        'Capability-aware Codex standalone and Remote Control management.',
      'codex.loading': () => 'Detecting Codex safely…',
      'codex.statusUnavailableTitle': () => 'Codex status unavailable',
      'codex.installationEyebrow': () => 'Installation',
      'codex.installationTitle': () => 'Codex CLI',
      'codex.installedLabel': () => 'Installed',
      'codex.installedYes': () => 'Installed',
      'codex.installedNo': () => 'Not installed',
      'codex.versionLabel': () => 'Version',
      'codex.installationTypeLabel': () => 'Installation',
      'codex.authenticationLabel': () => 'Authentication',
      'codex.executableLabel': () => 'Executable',
      'codex.unavailable': () => 'Unavailable',
      'codex.remoteEyebrow': () => 'Remote Control',
      'codex.remoteTitle': () => 'Lifecycle',
      'codex.observedStateLabel': () => 'Observed state',
      'codex.confidenceLabel': () => 'confidence',
      'codex.startRemote': () => 'Start Remote',
      'codex.startingRemote': () => 'Starting…',
      'codex.stopRemote': () => 'Stop Remote',
      'codex.stoppingRemote': () => 'Stopping…',
      'codex.refreshStatusLabel': () => 'Refresh Codex status',
      'codex.pairEyebrow': () => 'Pair Device',
      'codex.pairTitle': () => 'Temporary access',
      'codex.sensitive': () => 'Sensitive',
      'codex.pairDescription': () =>
        'Generate only when pairing a device. AgentBox never saves the code.',
      'codex.generatingPair': () => 'Generating…',
      'codex.pairNewDevice': () => 'Pair New Device',
      'codex.pairSecretLabel': () => 'Sensitive temporary code',
      'codex.pairTimeoutNote': () =>
        'Hidden from this page automatically after 90 seconds. This is not the Codex-reported expiry.',
      'codex.copy': () => 'Copy',
      'codex.copied': () => 'Copied',
      'codex.copyFailed': () => 'The code could not be copied. Try again.',
      'codex.hide': () => 'Hide',
      'codex.diagnosticsEyebrow': () => 'Diagnostics',
      'codex.diagnosticsTitle': () => 'Compatibility findings',
      'codex.diagnosticsEmpty': () => 'No current adapter findings.',
      'codex.actionFailedTitle': () => 'Codex action failed',
      'codex.confirmEyebrow': () => 'Sensitive action',
      'codex.confirmTitle': () => 'Generate a new temporary pairing code?',
      'codex.confirmDescription': () =>
        "The code is shown once and kept only in this page's memory.",
      'codex.generateCode': () => 'Generate Code',
      'codex.capabilitySupported': () => 'Supported',
      'codex.capabilityUnsupported': () => 'Unsupported',
      'codex.capabilityUnknown': () => 'Unknown',
      'codex.remoteRunning': () => 'Running',
      'codex.remoteStopped': () => 'Stopped',
      'codex.remoteBroken': () => 'Broken',
      'codex.remoteUnknown': () => 'Unknown',
      'codex.confidenceReported': () => 'Reported',
      'codex.confidenceInferred': () => 'Inferred',
      'codex.confidenceUnknown': () => 'Unknown',
      'codex.installationStandalone': () => 'Standalone',
      'codex.installationNpm': () => 'npm',
      'codex.installationConflict': () => 'Conflict',
      'codex.installationUnknown': () => 'Unknown',
      'codex.authenticationAuthenticated': () => 'Authenticated',
      'codex.authenticationUnauthenticated': () => 'Unauthenticated',
      'codex.authenticationUnknown': () => 'Unknown',
      'codex.severityCritical': () => 'Critical',
      'codex.severityHigh': () => 'High',
      'codex.severityMedium': () => 'Medium',
      'codex.severityLow': () => 'Low',
      'codex.severityWarning': () => 'Warning',
      'codex.severityInfo': () => 'Info',
    },
    'zh-CN': {
      'codex.title': () => 'Codex',
      'codex.eyebrow': () => 'Runtime',
      'codex.description': () =>
        '根据实际能力管理 Codex 独立安装和 Remote Control。',
      'codex.loading': () => '正在安全检测 Codex…',
      'codex.statusUnavailableTitle': () => '无法获取 Codex 状态',
      'codex.installationEyebrow': () => '安装',
      'codex.installationTitle': () => 'Codex CLI',
      'codex.installedLabel': () => '安装状态',
      'codex.installedYes': () => '已安装',
      'codex.installedNo': () => '未安装',
      'codex.versionLabel': () => '版本',
      'codex.installationTypeLabel': () => '安装方式',
      'codex.authenticationLabel': () => '身份验证',
      'codex.executableLabel': () => '可执行文件',
      'codex.unavailable': () => '不可用',
      'codex.remoteEyebrow': () => 'Remote Control',
      'codex.remoteTitle': () => '生命周期',
      'codex.observedStateLabel': () => '实际状态',
      'codex.confidenceLabel': () => '可信度',
      'codex.startRemote': () => '启动 Remote',
      'codex.startingRemote': () => '正在启动…',
      'codex.stopRemote': () => '停止 Remote',
      'codex.stoppingRemote': () => '正在停止…',
      'codex.refreshStatusLabel': () => '刷新 Codex 状态',
      'codex.pairEyebrow': () => '配对设备',
      'codex.pairTitle': () => '临时访问',
      'codex.sensitive': () => '敏感信息',
      'codex.pairDescription': () =>
        '仅在配对设备时生成。AgentBox 绝不会保存该配对码。',
      'codex.generatingPair': () => '正在生成…',
      'codex.pairNewDevice': () => '配对新设备',
      'codex.pairSecretLabel': () => '敏感临时配对码',
      'codex.pairTimeoutNote': () =>
        '该配对码将在 90 秒后自动从此页面隐藏；这不是 Codex 报告的过期时间。',
      'codex.copy': () => '复制',
      'codex.copied': () => '已复制',
      'codex.copyFailed': () => '无法复制配对码，请重试。',
      'codex.hide': () => '隐藏',
      'codex.diagnosticsEyebrow': () => '诊断',
      'codex.diagnosticsTitle': () => '兼容性检查结果',
      'codex.diagnosticsEmpty': () => '当前没有适配器检查结果。',
      'codex.actionFailedTitle': () => 'Codex 操作失败',
      'codex.confirmEyebrow': () => '敏感操作',
      'codex.confirmTitle': () => '生成新的临时配对码？',
      'codex.confirmDescription': () =>
        '配对码只显示一次，并且只保留在当前页面的内存中。',
      'codex.generateCode': () => '生成配对码',
      'codex.capabilitySupported': () => '支持',
      'codex.capabilityUnsupported': () => '不支持',
      'codex.capabilityUnknown': () => '未知',
      'codex.remoteRunning': () => '运行中',
      'codex.remoteStopped': () => '已停止',
      'codex.remoteBroken': () => '异常',
      'codex.remoteUnknown': () => '未知',
      'codex.confidenceReported': () => '已报告',
      'codex.confidenceInferred': () => '已推断',
      'codex.confidenceUnknown': () => '未知',
      'codex.installationStandalone': () => '独立安装',
      'codex.installationNpm': () => 'npm',
      'codex.installationConflict': () => '安装冲突',
      'codex.installationUnknown': () => '未知',
      'codex.authenticationAuthenticated': () => '已验证',
      'codex.authenticationUnauthenticated': () => '未验证',
      'codex.authenticationUnknown': () => '未知',
      'codex.severityCritical': () => '严重',
      'codex.severityHigh': () => '高',
      'codex.severityMedium': () => '中',
      'codex.severityLow': () => '低',
      'codex.severityWarning': () => '警告',
      'codex.severityInfo': () => '信息',
    },
  },
)
