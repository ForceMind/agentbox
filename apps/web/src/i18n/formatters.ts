import type { Locale } from './locale'

export function formatDate(
  locale: Locale,
  value: Date | number,
  options?: Intl.DateTimeFormatOptions,
): string {
  return new Intl.DateTimeFormat(locale, options).format(value)
}

export function formatNumber(
  locale: Locale,
  value: number | bigint,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(locale, options).format(value)
}

export type PluralForms = Readonly<
  Partial<
    Record<Intl.LDMLPluralRule, (parameters: PluralParameters) => string>
  > & {
    other: (parameters: PluralParameters) => string
  }
>

export interface PluralParameters {
  readonly count: number
  readonly formattedCount: string
}

export function formatPlural(
  locale: Locale,
  count: number,
  forms: PluralForms,
  numberOptions?: Intl.NumberFormatOptions,
  pluralOptions?: Intl.PluralRulesOptions,
): string {
  const category = new Intl.PluralRules(locale, pluralOptions).select(count)
  const formatter = forms[category] ?? forms.other
  return formatter({
    count,
    formattedCount: formatNumber(locale, count, numberOptions),
  })
}
