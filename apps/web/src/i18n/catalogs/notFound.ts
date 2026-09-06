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
      'notFound.heading': () => 'That route is not part of AgentBox.',
      'notFound.description': () =>
        'The address may be outdated, or the capability may belong to a later phase.',
      'notFound.backToDashboard': () => 'Back to Dashboard',
      'notFound.backToSignIn': () => 'Back to sign in',
    },
    'zh-CN': {
      'notFound.title': () => '未找到页面',
      'notFound.heading': () => '该路由不属于 AgentBox。',
      'notFound.description': () =>
        '该地址可能已失效，或此能力将在后续阶段提供。',
      'notFound.backToDashboard': () => '返回 Dashboard',
      'notFound.backToSignIn': () => '返回登录',
    },
  },
)
