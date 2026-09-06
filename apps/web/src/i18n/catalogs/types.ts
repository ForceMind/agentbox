import type { Locale } from '../locale'
import type { MessageDomain } from '../domains'

/** An empty parameter object that rejects every named property. */
export type NoMessageParameters = Readonly<Record<string, never>>

export type CatalogFor<ParametersByKey extends object> = Readonly<{
  [Key in keyof ParametersByKey]: (parameters: ParametersByKey[Key]) => string
}>

type MessageDomainFor<ParametersByKey extends object> = Extract<
  Extract<keyof ParametersByKey, string> extends `${infer Domain}.${string}`
    ? Domain
    : never,
  MessageDomain
>

export interface CatalogShard<ParametersByKey extends object> {
  readonly domain: MessageDomainFor<ParametersByKey>
  readonly catalogs: Readonly<Record<Locale, CatalogFor<ParametersByKey>>>
}

/**
 * Defines one independently owned product-domain catalog. The parameter map is
 * declared before the messages, so keys and interpolation values stay typed.
 */
export function defineCatalogShard<ParametersByKey extends object>(
  domain: MessageDomainFor<ParametersByKey>,
  catalogs: Record<Locale, CatalogFor<ParametersByKey>>,
): CatalogShard<ParametersByKey> {
  for (const locale of ['en', 'zh-CN'] as const) {
    for (const key of Object.keys(catalogs[locale])) {
      if (!key.startsWith(`${domain}.`)) {
        throw new TypeError(`Message ${key} is outside the ${domain} domain`)
      }
    }
  }

  return Object.freeze({
    domain,
    catalogs: Object.freeze({
      en: Object.freeze({ ...catalogs.en }),
      'zh-CN': Object.freeze({ ...catalogs['zh-CN'] }),
    }),
  })
}
