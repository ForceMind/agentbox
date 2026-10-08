import { defineCatalogShard } from './types'

export interface DocumentMessageParameters {
  readonly 'document.title': Readonly<{ title: string }>
}

export const documentCatalog = defineCatalogShard<DocumentMessageParameters>(
  'document',
  {
    en: {
      'document.title': ({ title }) => `${title} · Kebui`,
    },
    'zh-CN': {
      'document.title': ({ title }) => `${title} · Kebui`,
    },
  },
)
