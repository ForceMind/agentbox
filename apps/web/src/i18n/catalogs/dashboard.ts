import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface DashboardMessageParameters {
  readonly 'dashboard.systemDetails': NoMessageParameters
  readonly 'dashboard.systemDescription': NoMessageParameters
  readonly 'dashboard.jobId': NoMessageParameters
  readonly 'dashboard.unknown': NoMessageParameters
  readonly 'dashboard.noProjectLink': NoMessageParameters
  readonly 'dashboard.visibleLimit': NoMessageParameters
  readonly 'dashboard.windowCount': NoMessageParameters
  readonly 'dashboard.needsAttention': NoMessageParameters
  readonly 'dashboard.running': NoMessageParameters
  readonly 'dashboard.queued': NoMessageParameters
  readonly 'dashboard.allProjects': NoMessageParameters
  readonly 'dashboard.allAttention': NoMessageParameters
  readonly 'dashboard.openProject': NoMessageParameters
  readonly 'dashboard.metadataUpdated': NoMessageParameters
  readonly 'dashboard.received': NoMessageParameters
  readonly 'dashboard.emptyProjects': NoMessageParameters
  readonly 'dashboard.emptyActive': NoMessageParameters
  readonly 'dashboard.emptyAttention': NoMessageParameters
  readonly 'dashboard.permissionWork': NoMessageParameters
  readonly 'dashboard.failedWork': NoMessageParameters
  readonly 'dashboard.staleWork': NoMessageParameters
  readonly 'dashboard.loadingWork': NoMessageParameters
  readonly 'dashboard.projectsScope': NoMessageParameters
  readonly 'dashboard.jobsScope': NoMessageParameters
  readonly 'dashboard.recentProjects': NoMessageParameters
  readonly 'dashboard.active': NoMessageParameters
  readonly 'dashboard.attention': NoMessageParameters
  readonly 'dashboard.refreshWork': NoMessageParameters
  readonly 'dashboard.workDescription': NoMessageParameters
  readonly 'dashboard.workTitle': NoMessageParameters
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
      'dashboard.systemDetails': () => 'System & capabilities',
      'dashboard.systemDescription': () =>
        'Control-plane health and available management workflows. Workspace connection and Agent readiness are checked separately.',
      'dashboard.workTitle': () => 'Your work',
      'dashboard.workDescription': () =>
        'A read-only snapshot of your operations and the managed project catalog.',
      'dashboard.refreshWork': () => 'Refresh work overview',
      'dashboard.attention': () => 'Needs attention',
      'dashboard.active': () => 'Active work',
      'dashboard.recentProjects': () => 'Recently updated projects',
      'dashboard.jobsScope': () =>
        'Counts cover only your 100 most recently created Jobs, not all work. Queued and running are recorded operation states, not AI progress.',
      'dashboard.projectsScope': () =>
        'Up to 6 non-archived projects, ordered by metadata update time. This is not last-used time or live Runtime status.',
      'dashboard.loadingWork': () => 'Loading work metadata…',
      'dashboard.staleWork': () =>
        'This snapshot is out of date and has been cleared. Return online to this page or refresh to check again.',
      'dashboard.failedWork': () =>
        'Work metadata could not be loaded. Refresh to try again.',
      'dashboard.permissionWork': () =>
        'You do not have access to this snapshot. Sign in again or check your permissions.',
      'dashboard.emptyAttention': () =>
        'No needs-attention operations in this window.',
      'dashboard.emptyActive': () =>
        'No queued or running operations in this window.',
      'dashboard.emptyProjects': () =>
        'No registered projects yet. Open Projects to create or discover one.',
      'dashboard.received': () => 'Snapshot received on this device',
      'dashboard.metadataUpdated': () => 'Metadata updated',
      'dashboard.openProject': () => 'Open project',
      'dashboard.allAttention': () => 'Review needs attention',
      'dashboard.allProjects': () => 'Browse projects',
      'dashboard.queued': () => 'Queued',
      'dashboard.running': () => 'Running',
      'dashboard.needsAttention': () => 'Needs attention',
      'dashboard.windowCount': () => 'In this window',
      'dashboard.visibleLimit': () =>
        'Showing up to 6 operations per section, newest first.',
      'dashboard.noProjectLink': () => 'No available project link',
      'dashboard.unknown': () => 'Unknown',
      'dashboard.jobId': () => 'Job',
      'dashboard.title': () => 'Dashboard',
      'dashboard.eyebrow': () => 'Workstation overview',
      'dashboard.description': () =>
        'Check your recent work, projects, and control-plane health.',
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
      'dashboard.systemDetails': () => '系统状态与能力',
      'dashboard.systemDescription': () =>
        '查看控制平面健康状态和已有管理入口。工作台连接与 Agent 就绪条件分别检查。',
      'dashboard.workTitle': () => '工作概览',
      'dashboard.workDescription': () => '只读查看你的操作记录与受管项目。',
      'dashboard.refreshWork': () => '刷新工作概览',
      'dashboard.attention': () => '待处理',
      'dashboard.active': () => '进行中的工作',
      'dashboard.recentProjects': () => '最近更新的项目',
      'dashboard.jobsScope': () =>
        '数量仅来自你最近创建的 100 项作业，不代表全部工作。排队和运行中是操作记录状态，不代表 AI 进度。',
      'dashboard.projectsScope': () =>
        '按元数据更新时间显示最多 6 个未归档项目；这不是最近使用时间或实时 Runtime 状态。',
      'dashboard.loadingWork': () => '正在加载工作元数据…',
      'dashboard.staleWork': () =>
        '此快照已过期并清除。联网返回此页或刷新后重新检查。',
      'dashboard.failedWork': () => '无法加载工作元数据，请刷新重试。',
      'dashboard.permissionWork': () =>
        '你无权查看此快照，请重新登录或检查权限。',
      'dashboard.emptyAttention': () => '此窗口内没有待处理的操作。',
      'dashboard.emptyActive': () => '此窗口内没有排队或运行中的操作。',
      'dashboard.emptyProjects': () =>
        '尚无已登记的项目。打开 Projects 创建或发现项目。',
      'dashboard.received': () => '此设备收到快照的时间',
      'dashboard.metadataUpdated': () => '元数据更新',
      'dashboard.openProject': () => '打开项目',
      'dashboard.allAttention': () => '查看待处理',
      'dashboard.allProjects': () => '浏览项目',
      'dashboard.queued': () => '排队中',
      'dashboard.running': () => '运行中',
      'dashboard.needsAttention': () => '待处理',
      'dashboard.windowCount': () => '此窗口内',
      'dashboard.visibleLimit': () => '每栏最多显示 6 项操作，最新创建的优先。',
      'dashboard.noProjectLink': () => '无可用的项目链接',
      'dashboard.unknown': () => '未知',
      'dashboard.jobId': () => '作业',
      'dashboard.title': () => '概览',
      'dashboard.eyebrow': () => '工作站概览',
      'dashboard.description': () => '查看最近工作、项目与控制平面健康状态。',
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
