/** The UI locale is selected once for each newly loaded browser document. */
export type Locale = 'zh-CN' | 'en'

export interface BrowserLocaleSource {
  readonly languages?: readonly unknown[]
}

export interface LocaleDocument {
  readonly documentElement: {
    lang: string
  }
}

let initializedLocale: Locale | null = null

function canonicalPrimaryLanguage(value: unknown): string | null {
  if (typeof value !== 'string') return null

  try {
    const locales = Intl.getCanonicalLocales(value)
    if (locales.length !== 1) return null
    return locales[0].split('-', 1)[0]
  } catch {
    return null
  }
}

/**
 * Reads only the first browser preference. Later preferences must not change
 * the selected UI language for the current document.
 */
export function detectLocale(source: BrowserLocaleSource): Locale {
  return canonicalPrimaryLanguage(source.languages?.[0]) === 'zh'
    ? 'zh-CN'
    : 'en'
}

export function detectBrowserLocale(): Locale {
  if (typeof navigator === 'undefined') return 'en'
  return detectLocale({ languages: navigator.languages })
}

export function applyDocumentLocale(
  documentLike: LocaleDocument,
  source: BrowserLocaleSource,
): Locale {
  const locale = detectLocale(source)
  documentLike.documentElement.lang = locale
  return locale
}

/**
 * Initializes the one locale for this JavaScript document before React renders.
 * Browser preference changes need a fresh document and never hot-switch UI copy.
 */
export function initializeI18n(): Locale {
  if (initializedLocale !== null) return initializedLocale

  initializedLocale = detectBrowserLocale()
  if (typeof document !== 'undefined') {
    document.documentElement.lang = initializedLocale
  }
  return initializedLocale
}

export function currentLocale(): Locale {
  return initializeI18n()
}
