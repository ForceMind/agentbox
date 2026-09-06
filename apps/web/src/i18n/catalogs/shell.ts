import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface ShellMessageParameters {
  readonly 'shell.dashboard': NoMessageParameters
  readonly 'shell.codex': NoMessageParameters
  readonly 'shell.claude': NoMessageParameters
  readonly 'shell.workspace': NoMessageParameters
  readonly 'shell.projects': NoMessageParameters
  readonly 'shell.doctor': NoMessageParameters
  readonly 'shell.logs': NoMessageParameters
  readonly 'shell.settings': NoMessageParameters
  readonly 'shell.controlPlane': NoMessageParameters
  readonly 'shell.primaryNavigation': NoMessageParameters
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
}

export const shellCatalog = defineCatalogShard<ShellMessageParameters>(
  'shell',
  {
    en: {
      'shell.dashboard': () => 'Dashboard',
      'shell.codex': () => 'Codex',
      'shell.claude': () => 'Claude',
      'shell.workspace': () => 'Workspace',
      'shell.projects': () => 'Projects',
      'shell.doctor': () => 'Doctor',
      'shell.logs': () => 'Logs',
      'shell.settings': () => 'Settings',
      'shell.controlPlane': () => 'Control Plane',
      'shell.primaryNavigation': () => 'Primary navigation',
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
    },
    'zh-CN': {
      'shell.dashboard': () => '概览',
      'shell.codex': () => 'Codex',
      'shell.claude': () => 'Claude',
      'shell.workspace': () => '工作区',
      'shell.projects': () => '项目',
      'shell.doctor': () => '诊断',
      'shell.logs': () => '日志',
      'shell.settings': () => '设置',
      'shell.controlPlane': () => '控制平面',
      'shell.primaryNavigation': () => '主导航',
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
    },
  },
)
