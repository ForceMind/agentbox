import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface CommonMessageParameters {
  readonly 'common.cancel': NoMessageParameters
  readonly 'common.close': NoMessageParameters
  readonly 'common.loading': NoMessageParameters
  readonly 'common.retry': NoMessageParameters
  readonly 'common.unknown': NoMessageParameters
}

export const commonCatalog = defineCatalogShard<CommonMessageParameters>(
  'common',
  {
    en: {
      'common.cancel': () => 'Cancel',
      'common.close': () => 'Close',
      'common.loading': () => 'Loading…',
      'common.retry': () => 'Retry',
      'common.unknown': () => 'Unknown',
    },
    'zh-CN': {
      'common.cancel': () => '取消',
      'common.close': () => '关闭',
      'common.loading': () => '正在加载…',
      'common.retry': () => '重试',
      'common.unknown': () => '未知',
    },
  },
)
