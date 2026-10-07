import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface NotFoundMessageParameters {
  readonly 'notFound.title': NoMessageParameters
  readonly 'notFound.heading': NoMessageParameters
  readonly 'notFound.description': NoMessageParameters
  readonly 'notFound.backToDashboard': NoMessageParameters
  readonly 'notFound.backToSignIn': NoMessageParameters
}

export const notFoundCatalog = defineCatalogShard<NotFoundMessageParameters>(
  'notFound',
  {
    en: {
      'notFound.title': () => 'Page not found',
      'notFound.heading': () => 'We couldn’t find this page.',
      'notFound.description': () =>
        'The address may have changed or is no longer available. Use the link below to continue.',
      'notFound.backToDashboard': () => 'Back to Dashboard',
      'notFound.backToSignIn': () => 'Back to sign in',
    },
    'zh-CN': {
      'notFound.title': () => '未找到页面',
      'notFound.heading': () => '这里没有找到页面。',
      'notFound.description': () =>
        '地址可能已更改或不再可用。请通过下方入口继续。',
      'notFound.backToDashboard': () => '返回 Dashboard',
      'notFound.backToSignIn': () => '返回登录',
    },
  },
)
