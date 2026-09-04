export interface TechnicalValue {
  readonly value: string
  readonly lang: 'en'
  readonly dir: 'ltr'
  readonly translate: 'no'
}

function isPrintableAscii(value: string): boolean {
  if (!value.length) return false
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    if (code < 0x20 || code > 0x7e) return false
  }
  return true
}

/**
 * Provides safe display metadata for protocol values, codes and identifiers.
 * Such values remain ASCII English and are never translated as ordinary UI copy.
 */
export function technicalValue(value: string): TechnicalValue {
  if (!isPrintableAscii(value)) {
    throw new TypeError(
      'Technical values must contain one or more printable ASCII characters',
    )
  }

  return Object.freeze({
    value,
    lang: 'en',
    dir: 'ltr',
    translate: 'no',
  })
}
