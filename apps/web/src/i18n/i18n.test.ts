import { describe, expect, it } from 'vitest'

import {
  applyDocumentLocale,
  detectLocale,
  formatDate,
  formatMessage,
  formatNumber,
  formatPlural,
  I18nMessageError,
  KNOWN_API_ERROR_MESSAGES,
  localizeApiError,
  MESSAGE_DOMAINS,
  MESSAGE_KEYS,
  messageDomain,
  messageCatalogs,
  technicalApiIdentifier,
  technicalValue,
} from './index'
import type { MessageKey } from './index'

describe('browser locale selection', () => {
  it.each([
    [['zh'], 'zh-CN'],
    [['zh-CN'], 'zh-CN'],
    [['zh-Hant'], 'zh-CN'],
    [['en-US'], 'en'],
    [['fr-FR'], 'en'],
    [['fr-FR', 'zh-CN'], 'en'],
    [[], 'en'],
    [['not_a_locale'], 'en'],
  ] as const)('selects %s as %s', (languages, expected) => {
    expect(detectLocale({ languages })).toBe(expected)
  })

  it('sets the selected locale on the document element', () => {
    document.documentElement.lang = 'en'

    expect(applyDocumentLocale(document, { languages: ['zh-Hant-TW'] })).toBe(
      'zh-CN',
    )
    expect(document.documentElement.lang).toBe('zh-CN')
  })
})

describe('catalogs and formatters', () => {
  it('keeps each locale catalog complete and callable', () => {
    const expectedKeys = [...MESSAGE_KEYS].sort()

    for (const locale of ['en', 'zh-CN'] as const) {
      const catalog = messageCatalogs[locale]
      expect(Object.keys(catalog).sort()).toEqual(expectedKeys)
      expect(
        Object.values(catalog).every((value) => typeof value === 'function'),
      ).toBe(true)
    }
  })

  it('assigns every key to an approved product domain', () => {
    expect(MESSAGE_KEYS.map(messageDomain)).toEqual(
      expect.arrayContaining([...MESSAGE_DOMAINS]),
    )
  })

  it('formats named message parameters without a source-text fallback', () => {
    expect(formatMessage('en', 'document.title', { title: 'Dashboard' })).toBe(
      'Dashboard · AgentBox',
    )
    expect(formatMessage('zh-CN', 'items.count', { count: '3' })).toBe('3 项')
    expect(() =>
      formatMessage('en', 'missing.message' as MessageKey, {} as never),
    ).toThrow(I18nMessageError)
  })

  it('uses the selected locale for date, number and plural formatting', () => {
    expect(
      formatDate('en', new Date(Date.UTC(2026, 0, 2)), { timeZone: 'UTC' }),
    ).toBe('1/2/2026')
    expect(formatNumber('zh-CN', 1234567.5)).toBe('1,234,567.5')
    expect(
      formatPlural('en', 1, {
        one: ({ formattedCount }) => `${formattedCount} item`,
        other: ({ formattedCount }) => `${formattedCount} items`,
      }),
    ).toBe('1 item')
    expect(
      formatPlural('en', 2, {
        one: ({ formattedCount }) => `${formattedCount} item`,
        other: ({ formattedCount }) => `${formattedCount} items`,
      }),
    ).toBe('2 items')
  })
})

describe('technical values', () => {
  it('keeps technical values ASCII, LTR and excluded from translation', () => {
    expect(technicalValue('AUTH_SESSION_INVALID')).toEqual({
      value: 'AUTH_SESSION_INVALID',
      lang: 'en',
      dir: 'ltr',
      translate: 'no',
    })
    for (const value of [
      '',
      '错误',
      'line\nbreak',
      'tab\tvalue',
      'delete\u007f',
    ]) {
      expect(() => technicalValue(value)).toThrow(TypeError)
    }
  })
})

describe('API error localization', () => {
  it('uses only the code mapping and never server-provided prose', () => {
    expect(localizeApiError('en', 'WAW_INVALID_AGENT')).toBe(
      'The selected AgentType is not valid.',
    )
    expect(localizeApiError('zh-CN', 'WAW_INVALID_AGENT')).toBe(
      '所选 AgentType 无效。',
    )
    expect(localizeApiError('en', 'UNTRUSTED_SERVER_PROSE')).toBe(
      'The operation could not be completed. Try again.',
    )
  })

  it('maps every known API error to an existing localized message', () => {
    for (const [code, key] of Object.entries(KNOWN_API_ERROR_MESSAGES)) {
      expect(localizeApiError('en', code)).toBe(formatMessage('en', key, {}))
      expect(localizeApiError('zh-CN', code)).toBe(
        formatMessage('zh-CN', key, {}),
      )
    }
  })

  it('keeps valid codes and request IDs technical, and drops invalid values', () => {
    expect(technicalApiIdentifier('WAW_INVALID_AGENT')).toEqual(
      technicalValue('WAW_INVALID_AGENT'),
    )
    expect(technicalApiIdentifier('req_2026-09-05:1')).toEqual(
      technicalValue('req_2026-09-05:1'),
    )
    expect(technicalApiIdentifier('错误')).toBeNull()
  })
})
