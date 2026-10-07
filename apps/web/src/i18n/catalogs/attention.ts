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
  readonly 'attention.forbidden': NoMessageParameters
  readonly 'attention.details': NoMessageParameters
  readonly 'attention.window': NoMessageParameters
  readonly 'attention.count': Readonly<{ count: string }>
}

export const attentionCatalog = defineCatalogShard<AttentionMessageParameters>(
  'attention',
  {
    en: {
      'attention.title': () => 'Needs attention',
      'attention.eyebrow': () => 'Recent operations',
      'attention.description': () =>
        'Operations marked as needing attention among your 100 most recently created Jobs.',
      'attention.refresh': () => 'Refresh',
      'attention.loading': () => 'Checking recent operations…',
      'attention.stale': () =>
        'Status is out of date. It will refresh when this page is active and online.',
      'attention.failed': () => 'Recent operations could not be loaded.',
      'attention.empty': () => 'No recent operations need attention.',
      'attention.job': () => 'Job',
      'attention.project': () => 'Open project',
      'attention.unlinked': () => 'No project link',
      'attention.reason': () => 'Reason code',
      'attention.observed': () => 'Last checked',
      'attention.unknown': () => 'Unknown',
      'attention.forbidden': () =>
        'You do not have permission to view these operations.',
      'attention.details': () => 'Technical details',
      'attention.window': () =>
        'This view covers your 100 most recently created Jobs.',
      'attention.count': ({ count }) =>
        `${count} need attention in the recent window`,
    },
    'zh-CN': {
      'attention.title': () => '待处理',
      'attention.eyebrow': () => '最近操作',
      'attention.description': () =>
        '你最近创建的 100 项作业中，状态为待处理的操作。',
      'attention.refresh': () => '刷新',
      'attention.loading': () => '正在检查最近操作…',
      'attention.stale': () => '状态已过期。页面恢复可见且联网后会重新检查。',
      'attention.failed': () => '无法加载最近操作。',
      'attention.empty': () => '最近没有需要处理的操作。',
      'attention.job': () => '作业',
      'attention.project': () => '打开项目',
      'attention.unlinked': () => '无项目链接',
      'attention.reason': () => '原因代码',
      'attention.observed': () => '上次检查',
      'attention.unknown': () => '未知',
      'attention.forbidden': () => '你没有查看这些操作的权限。',
      'attention.details': () => '技术详情',
      'attention.window': () => '此视图仅覆盖你最近创建的 100 项作业。',
      'attention.count': ({ count }) => `最近记录中有 ${count} 项待处理`,
    },
  },
)
