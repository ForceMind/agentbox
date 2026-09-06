import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface LogsMessageParameters {
  readonly 'logs.title': NoMessageParameters
  readonly 'logs.eyebrow': NoMessageParameters
  readonly 'logs.description': NoMessageParameters
  readonly 'logs.agentboxTitle': NoMessageParameters
  readonly 'logs.agentboxDescription': NoMessageParameters
  readonly 'logs.runtimeTitle': NoMessageParameters
  readonly 'logs.runtimeDescription': NoMessageParameters
  readonly 'logs.auditTitle': NoMessageParameters
  readonly 'logs.auditDescription': NoMessageParameters
  readonly 'logs.planned': NoMessageParameters
  readonly 'logs.notImplemented': NoMessageParameters
  readonly 'logs.previewOnly': NoMessageParameters
  readonly 'logs.capabilitiesAria': NoMessageParameters
}

export const logsCatalog = defineCatalogShard<LogsMessageParameters>('logs', {
  en: {
    'logs.title': () => 'Logs',
    'logs.eyebrow': () => 'Observability',
    'logs.description': () =>
      'Application and host log viewing is not available yet.',
    'logs.agentboxTitle': () => 'AgentBox logs',
    'logs.agentboxDescription': () => 'Bounded control-plane diagnostics.',
    'logs.runtimeTitle': () => 'Runtime logs',
    'logs.runtimeDescription': () => 'Redacted runtime-specific output.',
    'logs.auditTitle': () => 'Audit events',
    'logs.auditDescription': () => 'Security-relevant action history.',
    'logs.planned': () => 'Planned',
    'logs.notImplemented': () => 'Not implemented yet',
    'logs.previewOnly': () =>
      'This section is a product preview only. It does not invoke a runtime, system command, or host service.',
    'logs.capabilitiesAria': () => 'Planned Logs capabilities',
  },
  'zh-CN': {
    'logs.title': () => '日志',
    'logs.eyebrow': () => '可观测性',
    'logs.description': () => '应用和主机日志查看功能尚不可用。',
    'logs.agentboxTitle': () => 'AgentBox 日志',
    'logs.agentboxDescription': () => '有界的控制平面诊断信息。',
    'logs.runtimeTitle': () => 'Runtime 日志',
    'logs.runtimeDescription': () => '已脱敏的 Runtime 专用输出。',
    'logs.auditTitle': () => '审计事件',
    'logs.auditDescription': () => '与安全相关的操作历史。',
    'logs.planned': () => '计划中',
    'logs.notImplemented': () => '尚未实现',
    'logs.previewOnly': () =>
      '此区域仅展示产品预览，不会调用 Runtime、系统命令或主机服务。',
    'logs.capabilitiesAria': () => '计划中的日志能力',
  },
})
