import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface AppMessageParameters {
  readonly 'app.name': NoMessageParameters
}

export const appCatalog = defineCatalogShard<AppMessageParameters>('app', {
  en: {
    'app.name': () => 'AgentBox',
  },
  'zh-CN': {
    'app.name': () => 'AgentBox',
  },
})
