import type { Locale } from './locale'

export const MESSAGE_KEYS = [
  'app.name',
  'common.cancel',
  'common.close',
  'common.loading',
  'common.retry',
  'common.unknown',
  'document.title',
  'items.count',
] as const

export type MessageKey = (typeof MESSAGE_KEYS)[number]

type EmptyMessageParameters = Readonly<Record<never, never>>

export interface MessageParameters {
  readonly 'app.name': EmptyMessageParameters
  readonly 'common.cancel': EmptyMessageParameters
  readonly 'common.close': EmptyMessageParameters
  readonly 'common.loading': EmptyMessageParameters
  readonly 'common.retry': EmptyMessageParameters
  readonly 'common.unknown': EmptyMessageParameters
  readonly 'document.title': Readonly<{ title: string }>
  readonly 'items.count': Readonly<{ count: string }>
}

export type MessageCatalog = Readonly<{
  [Key in MessageKey]: (parameters: MessageParameters[Key]) => string
}>

const en = {
  'app.name': () => 'AgentBox',
  'common.cancel': () => 'Cancel',
  'common.close': () => 'Close',
  'common.loading': () => 'Loading…',
  'common.retry': () => 'Retry',
  'common.unknown': () => 'Unknown',
  'document.title': ({ title }: MessageParameters['document.title']) =>
    `${title} · AgentBox`,
  'items.count': ({ count }: MessageParameters['items.count']) =>
    `${count} items`,
} satisfies MessageCatalog

const zhCN = {
  'app.name': () => 'AgentBox',
  'common.cancel': () => '取消',
  'common.close': () => '关闭',
  'common.loading': () => '正在加载…',
  'common.retry': () => '重试',
  'common.unknown': () => '未知',
  'document.title': ({ title }: MessageParameters['document.title']) =>
    `${title} · AgentBox`,
  'items.count': ({ count }: MessageParameters['items.count']) => `${count} 项`,
} satisfies MessageCatalog

export const messageCatalogs: Readonly<Record<Locale, MessageCatalog>> =
  Object.freeze({
    en: Object.freeze(en),
    'zh-CN': Object.freeze(zhCN),
  })

export class I18nMessageError extends Error {
  constructor(readonly key: string) {
    super(`Missing i18n message: ${key}`)
    this.name = 'I18nMessageError'
  }
}

/** Formats an explicitly typed message; message keys never fall back to source text. */
export function formatMessage<Key extends MessageKey>(
  locale: Locale,
  key: Key,
  parameters: MessageParameters[Key],
): string {
  const formatter = messageCatalogs[locale][key]
  if (typeof formatter !== 'function') throw new I18nMessageError(key)
  return formatter(parameters)
}
