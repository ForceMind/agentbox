import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface AppMessageParameters {
  readonly 'app.name': NoMessageParameters
}

export const appCatalog = defineCatalogShard<AppMessageParameters>('app', {
  en: {
    'app.name': () => 'Kebui',
  },
  'zh-CN': {
    'app.name': () => 'Kebui',
  },
})
