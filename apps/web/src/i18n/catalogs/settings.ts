import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'
import { formatPlural } from '../formatters'

export interface SettingsMessageParameters {
  readonly 'settings.title': NoMessageParameters
  readonly 'settings.eyebrow': NoMessageParameters
  readonly 'settings.description': NoMessageParameters
  readonly 'settings.readOnly': NoMessageParameters
  readonly 'settings.loading': NoMessageParameters
  readonly 'settings.environment': NoMessageParameters
  readonly 'settings.bindAddress': NoMessageParameters
  readonly 'settings.absoluteSessionLifetime': NoMessageParameters
  readonly 'settings.idleSessionLifetime': NoMessageParameters
  readonly 'settings.loginRateLimitLabel': NoMessageParameters
  readonly 'settings.loginRateLimit': Readonly<{
    count: string
    duration: string
  }>
  readonly 'settings.loginLockDuration': NoMessageParameters
  readonly 'settings.hours': Readonly<{ count: number }>
  readonly 'settings.minutes': Readonly<{ count: number }>
  readonly 'settings.seconds': Readonly<{ count: number }>
  readonly 'settings.scopeNote': NoMessageParameters
  readonly 'settings.unavailable': NoMessageParameters
}

export const settingsCatalog = defineCatalogShard<SettingsMessageParameters>(
  'settings',
  {
    en: {
      'settings.title': () => 'Settings',
      'settings.eyebrow': () => 'Control plane',
      'settings.description': () =>
        'A safe summary of active control-plane policy.',
      'settings.readOnly': () => 'Read only',
      'settings.loading': () => 'Loading safe settings…',
      'settings.environment': () => 'Environment',
      'settings.bindAddress': () => 'Bind address',
      'settings.absoluteSessionLifetime': () => 'Absolute session lifetime',
      'settings.idleSessionLifetime': () => 'Idle session lifetime',
      'settings.loginRateLimitLabel': () => 'Login rate limit',
      'settings.loginRateLimit': ({ count, duration }) =>
        `${count} failures per ${duration}`,
      'settings.loginLockDuration': () => 'Login lock duration',
      'settings.hours': ({ count }) =>
        formatPlural('en', count, {
          one: ({ formattedCount }) => `${formattedCount} hour`,
          other: ({ formattedCount }) => `${formattedCount} hours`,
        }),
      'settings.minutes': ({ count }) =>
        formatPlural('en', count, {
          one: ({ formattedCount }) => `${formattedCount} minute`,
          other: ({ formattedCount }) => `${formattedCount} minutes`,
        }),
      'settings.seconds': ({ count }) =>
        formatPlural('en', count, {
          one: ({ formattedCount }) => `${formattedCount} second`,
          other: ({ formattedCount }) => `${formattedCount} seconds`,
        }),
      'settings.scopeNote': () =>
        'Secrets, database URLs, filesystem paths, and credential state are never exposed here. Editing settings arrives in a later phase.',
      'settings.unavailable': () => 'Unavailable',
    },
    'zh-CN': {
      'settings.title': () => '设置',
      'settings.eyebrow': () => '控制平面',
      'settings.description': () => '当前控制平面策略的安全摘要。',
      'settings.readOnly': () => '只读',
      'settings.loading': () => '正在加载安全设置…',
      'settings.environment': () => '环境',
      'settings.bindAddress': () => '绑定地址',
      'settings.absoluteSessionLifetime': () => '会话绝对有效期',
      'settings.idleSessionLifetime': () => '会话空闲有效期',
      'settings.loginRateLimitLabel': () => '登录速率限制',
      'settings.loginRateLimit': ({ count, duration }) =>
        `每 ${duration}最多 ${count} 次失败`,
      'settings.loginLockDuration': () => '登录锁定时长',
      'settings.hours': ({ count }) =>
        formatPlural('zh-CN', count, {
          other: ({ formattedCount }) => `${formattedCount} 小时`,
        }),
      'settings.minutes': ({ count }) =>
        formatPlural('zh-CN', count, {
          other: ({ formattedCount }) => `${formattedCount} 分钟`,
        }),
      'settings.seconds': ({ count }) =>
        formatPlural('zh-CN', count, {
          other: ({ formattedCount }) => `${formattedCount} 秒`,
        }),
      'settings.scopeNote': () =>
        '不会在此显示 Secret、数据库 URL、文件系统路径或凭据状态。编辑设置将在后续阶段提供。',
      'settings.unavailable': () => '不可用',
    },
  },
)
