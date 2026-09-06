import { defineCatalogShard } from './types'

export interface ItemsMessageParameters {
  readonly 'items.count': Readonly<{ count: string }>
}

export const itemsCatalog = defineCatalogShard<ItemsMessageParameters>(
  'items',
  {
    en: {
      'items.count': ({ count }) => `${count} items`,
    },
    'zh-CN': {
      'items.count': ({ count }) => `${count} 项`,
    },
  },
)
