import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface AttentionMessageParameters {
  readonly 'attention.title': NoMessageParameters
  readonly 'attention.eyebrow': NoMessageParameters
  readonly 'attention.description': NoMessageParameters
  readonly 'attention.refresh': NoMessageParameters
  readonly 'attention.loading': NoMessageParameters
  readonly 'attention.stale': NoMessageParameters
  readonly 'attention.failed': NoMessageParameters
  readonly 'attention.empty': NoMessageParameters
  readonly 'attention.job': NoMessageParameters
  readonly 'attention.project': NoMessageParameters
  readonly 'attention.unlinked': NoMessageParameters
  readonly 'attention.reason': NoMessageParameters
  readonly 'attention.observed': NoMessageParameters
  readonly 'attention.unknown': NoMessageParameters
}

export const attentionCatalog = defineCatalogShard<AttentionMessageParameters>(
  'attention',
  {
    en: {
      'attention.title': () => 'Needs attention',
      'attention.eyebrow': () => 'Recent operations',
      'attention.description': () =>
        'Operations needing a decision or recovery among your 100 most recently created Jobs.',
      'attention.refresh': () => 'Refresh',
      'attention.loading': () => 'Checking recent operations…',
      'attention.stale': () =>
        'Status is out of date. Return to this tab to refresh.',
      'attention.failed': () => 'Recent operations could not be loaded.',
      'attention.empty': () => 'No recent operations need attention.',
      'attention.job': () => 'Job',
      'attention.project': () => 'Open project',
      'attention.unlinked': () => 'No project link',
      'attention.reason': () => 'Reason code',
      'attention.observed': () => 'Last checked',
      'attention.unknown': () => 'Unknown',
    },
    'zh-CN': {
      'attention.title': () => '待处理',
      'attention.eyebrow': () => '最近操作',
      'attention.description': () =>
        '你最近创建的 100 项作业中需要决策或恢复的操作。',
      'attention.refresh': () => '刷新',
      'attention.loading': () => '正在检查最近操作…',
      'attention.stale': () => '状态已过期。返回此页面后会重新检查。',
      'attention.failed': () => '无法加载最近操作。',
      'attention.empty': () => '最近没有需要处理的操作。',
      'attention.job': () => '作业',
      'attention.project': () => '打开项目',
      'attention.unlinked': () => '无项目链接',
      'attention.reason': () => '原因代码',
      'attention.observed': () => '上次检查',
      'attention.unknown': () => '未知',
    },
  },
)
