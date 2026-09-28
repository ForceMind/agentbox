import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface ShellMessageParameters {
  readonly 'shell.dashboard': NoMessageParameters
  readonly 'shell.attention': NoMessageParameters
  readonly 'shell.codex': NoMessageParameters
  readonly 'shell.claude': NoMessageParameters
  readonly 'shell.workspace': NoMessageParameters
  readonly 'shell.projects': NoMessageParameters
  readonly 'shell.doctor': NoMessageParameters
  readonly 'shell.logs': NoMessageParameters
  readonly 'shell.settings': NoMessageParameters
  readonly 'shell.controlPlane': NoMessageParameters
  readonly 'shell.primaryNavigation': NoMessageParameters
  readonly 'shell.openWorkTabs': NoMessageParameters
  readonly 'shell.tabProject': NoMessageParameters
  readonly 'shell.tabChanges': NoMessageParameters
  readonly 'shell.closeWorkTab': Readonly<{ tab: string }>
  readonly 'shell.signedInAs': NoMessageParameters
  readonly 'shell.signingOut': NoMessageParameters
  readonly 'shell.signOut': NoMessageParameters
  readonly 'shell.logoutFailed': NoMessageParameters
  readonly 'shell.openNavigation': NoMessageParameters
  readonly 'shell.closeNavigation': NoMessageParameters
  readonly 'shell.version': NoMessageParameters
  readonly 'shell.healthChecking': NoMessageParameters
  readonly 'shell.healthHealthy': NoMessageParameters
  readonly 'shell.healthUnavailable': NoMessageParameters
  readonly 'shell.controlPlaneStatus': Readonly<{ status: string }>
  readonly 'shell.commandCenter': NoMessageParameters
  readonly 'shell.closeCommandCenter': NoMessageParameters
  readonly 'shell.commandSearch': NoMessageParameters
  readonly 'shell.commandSearchPlaceholder': NoMessageParameters
  readonly 'shell.commandPage': NoMessageParameters
  readonly 'shell.commandProject': NoMessageParameters
  readonly 'shell.commandLoading': NoMessageParameters
  readonly 'shell.commandLoadFailed': NoMessageParameters
  readonly 'shell.commandEmpty': NoMessageParameters
}

export const shellCatalog = defineCatalogShard<ShellMessageParameters>(
  'shell',
  {
    en: {
      'shell.dashboard': () => 'Dashboard',
      'shell.attention': () => 'Needs attention',
      'shell.codex': () => 'Codex',
      'shell.claude': () => 'Claude',
      'shell.workspace': () => 'Workspace',
      'shell.projects': () => 'Projects',
      'shell.doctor': () => 'Doctor',
      'shell.logs': () => 'Logs',
      'shell.settings': () => 'Settings',
      'shell.controlPlane': () => 'Control Plane',
      'shell.primaryNavigation': () => 'Primary navigation',
      'shell.openWorkTabs': () => 'Open Project views',
      'shell.tabProject': () => 'Project',
      'shell.tabChanges': () => 'Changed paths',
      'shell.closeWorkTab': ({ tab }) => `Close ${tab}`,
      'shell.signedInAs': () => 'Signed in as',
      'shell.signingOut': () => 'Signing out…',
      'shell.signOut': () => 'Sign out',
      'shell.logoutFailed': () => 'Logout could not be completed',
      'shell.openNavigation': () => 'Open navigation',
      'shell.closeNavigation': () => 'Close navigation',
      'shell.version': () => 'Version',
      'shell.healthChecking': () => 'Checking',
      'shell.healthHealthy': () => 'Healthy',
      'shell.healthUnavailable': () => 'Unavailable',
      'shell.controlPlaneStatus': ({ status }) => `Control plane: ${status}`,
      'shell.commandCenter': () => 'Command center',
      'shell.closeCommandCenter': () => 'Close command center',
      'shell.commandSearch': () => 'Search pages and Projects',
      'shell.commandSearchPlaceholder': () => 'Go to a page or Project…',
      'shell.commandPage': () => 'Page',
      'shell.commandProject': () => 'Project',
      'shell.commandLoading': () => 'Loading Projects…',
      'shell.commandLoadFailed': () =>
        'Projects could not be loaded. Page navigation is still available.',
      'shell.commandEmpty': () => 'No matching page or Project.',
    },
    'zh-CN': {
      'shell.dashboard': () => '概览',
      'shell.attention': () => '待处理',
      'shell.codex': () => 'Codex',
      'shell.claude': () => 'Claude',
      'shell.workspace': () => '工作区',
      'shell.projects': () => '项目',
      'shell.doctor': () => '诊断',
      'shell.logs': () => '日志',
      'shell.settings': () => '设置',
      'shell.controlPlane': () => '控制平面',
      'shell.primaryNavigation': () => '主导航',
      'shell.openWorkTabs': () => '已打开的 Project 页面',
      'shell.tabProject': () => '项目',
      'shell.tabChanges': () => '变更路径',
      'shell.closeWorkTab': ({ tab }) => `关闭 ${tab}`,
      'shell.signedInAs': () => '当前登录用户',
      'shell.signingOut': () => '正在退出…',
      'shell.signOut': () => '退出登录',
      'shell.logoutFailed': () => '无法完成退出登录',
      'shell.openNavigation': () => '打开导航',
      'shell.closeNavigation': () => '关闭导航',
      'shell.version': () => '版本',
      'shell.healthChecking': () => '检查中',
      'shell.healthHealthy': () => '正常',
      'shell.healthUnavailable': () => '不可用',
      'shell.controlPlaneStatus': ({ status }) => `控制平面：${status}`,
      'shell.commandCenter': () => '命令中心',
      'shell.closeCommandCenter': () => '关闭命令中心',
      'shell.commandSearch': () => '搜索页面和项目',
      'shell.commandSearchPlaceholder': () => '前往页面或项目…',
      'shell.commandPage': () => '页面',
      'shell.commandProject': () => '项目',
      'shell.commandLoading': () => '正在加载项目…',
      'shell.commandLoadFailed': () => '项目加载失败，仍可打开页面。',
      'shell.commandEmpty': () => '没有匹配的页面或项目。',
    },
  },
)
