import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface DashboardMessageParameters {
  readonly 'dashboard.title': NoMessageParameters
  readonly 'dashboard.eyebrow': NoMessageParameters
  readonly 'dashboard.description': NoMessageParameters
  readonly 'dashboard.statusAria': NoMessageParameters
  readonly 'dashboard.controlPlane': NoMessageParameters
  readonly 'dashboard.readiness': NoMessageParameters
  readonly 'dashboard.agentboxVersion': NoMessageParameters
  readonly 'dashboard.administrator': NoMessageParameters
  readonly 'dashboard.checking': NoMessageParameters
  readonly 'dashboard.healthy': NoMessageParameters
  readonly 'dashboard.degraded': NoMessageParameters
  readonly 'dashboard.unavailable': NoMessageParameters
  readonly 'dashboard.ready': NoMessageParameters
  readonly 'dashboard.notReady': NoMessageParameters
  readonly 'dashboard.apiVersion': NoMessageParameters
  readonly 'dashboard.sessionExpires': NoMessageParameters
  readonly 'dashboard.currentCapabilitiesEyebrow': NoMessageParameters
  readonly 'dashboard.currentCapabilitiesTitle': NoMessageParameters
  readonly 'dashboard.currentCapabilitiesStatus': NoMessageParameters
  readonly 'dashboard.codexTitle': NoMessageParameters
  readonly 'dashboard.codexDescription': NoMessageParameters
  readonly 'dashboard.claudeTitle': NoMessageParameters
  readonly 'dashboard.claudeDescription': NoMessageParameters
  readonly 'dashboard.projectsTitle': NoMessageParameters
  readonly 'dashboard.projectsDescription': NoMessageParameters
  readonly 'dashboard.environment': NoMessageParameters
  readonly 'dashboard.database': NoMessageParameters
  readonly 'dashboard.migrations': NoMessageParameters
}

export const dashboardCatalog = defineCatalogShard<DashboardMessageParameters>(
  'dashboard',
  {
    en: {
      'dashboard.title': () => 'Dashboard',
      'dashboard.eyebrow': () => 'Workstation overview',
      'dashboard.description': () =>
        'Current control-plane health and the available AgentBox workflows.',
      'dashboard.statusAria': () => 'Control plane status',
      'dashboard.controlPlane': () => 'Control Plane',
      'dashboard.readiness': () => 'Readiness',
      'dashboard.agentboxVersion': () => 'AgentBox version',
      'dashboard.administrator': () => 'Administrator',
      'dashboard.checking': () => 'Checking',
      'dashboard.healthy': () => 'Healthy',
      'dashboard.degraded': () => 'Degraded',
      'dashboard.unavailable': () => 'Unavailable',
      'dashboard.ready': () => 'Ready',
      'dashboard.notReady': () => 'Not Ready',
      'dashboard.apiVersion': () => 'API',
      'dashboard.sessionExpires': () => 'Session expires',
      'dashboard.currentCapabilitiesEyebrow': () => 'Available workflows',
      'dashboard.currentCapabilitiesTitle': () => 'Current capabilities',
      'dashboard.currentCapabilitiesStatus': () => 'Available',
      'dashboard.codexTitle': () => 'Codex',
      'dashboard.codexDescription': () =>
        'Inspect the installation, remote controls, and pairing when supported.',
      'dashboard.claudeTitle': () => 'Claude',
      'dashboard.claudeDescription': () =>
        'Review managed sessions and their safe lifecycle state.',
      'dashboard.projectsTitle': () => 'Projects',
      'dashboard.projectsDescription': () =>
        'Create or clone bounded Projects and review workspace state.',
      'dashboard.environment': () => 'Environment',
      'dashboard.database': () => 'Database',
      'dashboard.migrations': () => 'Migrations',
    },
    'zh-CN': {
      'dashboard.title': () => '概览',
      'dashboard.eyebrow': () => '工作站概览',
      'dashboard.description': () =>
        '查看当前控制平面健康状态和可用的 AgentBox 工作流。',
      'dashboard.statusAria': () => '控制平面状态',
      'dashboard.controlPlane': () => '控制平面',
      'dashboard.readiness': () => '就绪状态',
      'dashboard.agentboxVersion': () => 'AgentBox 版本',
      'dashboard.administrator': () => '管理员',
      'dashboard.checking': () => '正在检查',
      'dashboard.healthy': () => '正常',
      'dashboard.degraded': () => '降级',
      'dashboard.unavailable': () => '暂不可用',
      'dashboard.ready': () => '已就绪',
      'dashboard.notReady': () => '未就绪',
      'dashboard.apiVersion': () => 'API',
      'dashboard.sessionExpires': () => '会话过期时间',
      'dashboard.currentCapabilitiesEyebrow': () => '可用工作流',
      'dashboard.currentCapabilitiesTitle': () => '当前能力',
      'dashboard.currentCapabilitiesStatus': () => '可用',
      'dashboard.codexTitle': () => 'Codex',
      'dashboard.codexDescription': () =>
        '在已支持时查看安装状态、Remote 控制和配对。',
      'dashboard.claudeTitle': () => 'Claude',
      'dashboard.claudeDescription': () => '查看托管会话及其安全生命周期状态。',
      'dashboard.projectsTitle': () => 'Projects',
      'dashboard.projectsDescription': () =>
        '创建或克隆受限的 Project，并查看工作区状态。',
      'dashboard.environment': () => '环境',
      'dashboard.database': () => '数据库',
      'dashboard.migrations': () => '迁移',
    },
  },
)
