import { describe, expect, it, vi } from 'vitest'

import {
  applyDocumentLocale,
  currentLocale,
  detectLocale,
  formatDate,
  formatMessage,
  formatNumber,
  formatPlural,
  I18nMessageError,
  initializeI18n,
  KNOWN_API_ERROR_CODES,
  KNOWN_API_ERROR_MESSAGES,
  localizeApiError,
  localizeApiErrorData,
  MESSAGE_DOMAINS,
  MESSAGE_KEYS,
  messageDomain,
  messageCatalogs,
  parameterFreeMessage,
  technicalApiIdentifier,
  technicalValue,
} from './index'

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
    const documentLike = { documentElement: { lang: 'en' } }

    expect(
      applyDocumentLocale(documentLike, { languages: ['zh-Hant-TW'] }),
    ).toBe('zh-CN')
    expect(documentLike.documentElement.lang).toBe('zh-CN')

    expect(applyDocumentLocale(documentLike, { languages: ['en-US'] })).toBe(
      'zh-CN',
    )
    expect(documentLike.documentElement.lang).toBe('zh-CN')
  })

  it('reads only the first language and never consults a fallback property', () => {
    const languages = new Proxy(['en-US', 'zh-CN'], {
      get(target, property, receiver) {
        if (property === '1') throw new Error('later language was read')
        return Reflect.get(target, property, receiver)
      },
    })
    const source = {
      languages,
      get language(): never {
        throw new Error('navigator.language fallback was read')
      },
    }

    expect(detectLocale(source)).toBe('en')
  })

  it('keeps the initialized locale immutable for the current document', () => {
    const languages = vi
      .spyOn(window.navigator, 'languages', 'get')
      .mockReturnValue(['en-US'])

    expect(initializeI18n()).toBe('en')
    languages.mockReturnValue(['zh-CN'])
    expect(currentLocale()).toBe('en')
    expect(applyDocumentLocale(document, { languages: ['zh-CN'] })).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    languages.mockRestore()
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
      expect(Object.isFrozen(catalog)).toBe(true)
    }
    expect(Object.keys(messageCatalogs.en).sort()).toEqual(
      Object.keys(messageCatalogs['zh-CN']).sort(),
    )
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
    const unsafeFormatMessage = formatMessage as unknown as (
      locale: 'en',
      key: string,
      parameters: unknown,
    ) => string
    expect(() => unsafeFormatMessage('en', 'missing.message', {})).toThrow(
      I18nMessageError,
    )
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

  it.each([
    [
      'AUTH_INVALID_CREDENTIALS',
      'The username or password is incorrect.',
      '用户名或密码错误。',
    ],
    [
      'AUTH_SESSION_INVALID',
      'Your session is no longer valid. Sign in again.',
      '会话已失效，请重新登录。',
    ],
    [
      'AUTH_RATE_LIMITED',
      'Too many sign-in attempts. Try again later.',
      '登录尝试过于频繁，请稍后重试。',
    ],
    [
      'AUTH_RECENT_REQUIRED',
      'Sign in again before requesting a Codex pair code.',
      '请重新登录后再请求 Codex 配对码。',
    ],
    [
      'CODEX_PAIR_RATE_LIMITED',
      'A Codex pair code was requested too recently. Try again later.',
      'Codex 配对码请求过于频繁，请稍后重试。',
    ],
    [
      'CODEX_PAIR_OUTPUT_UNRECOGNIZED',
      'Codex did not return a recognizable pair code.',
      'Codex 未返回可识别的配对码。',
    ],
    [
      'CODEX_PAIR_TIMEOUT',
      'Codex did not create a pair code in time. Try again.',
      'Codex 未能及时创建配对码，请重试。',
    ],
    [
      'PROJECT_NOT_FOUND',
      'The requested Project was not found.',
      '未找到请求的 Project。',
    ],
  ] as const)(
    'uses dedicated copy for stable code %s',
    (code, english, chinese) => {
      expect(localizeApiError('en', code)).toBe(english)
      expect(localizeApiError('zh-CN', code)).toBe(chinese)
      expect(english).not.toBe(localizeApiError('en', 'UNKNOWN_API_CODE'))
      expect(chinese).not.toBe(localizeApiError('zh-CN', 'UNKNOWN_API_CODE'))
    },
  )

  it('maps every known API error to an existing localized message', () => {
    expect(Object.keys(KNOWN_API_ERROR_MESSAGES).sort()).toEqual(
      [...KNOWN_API_ERROR_CODES].sort(),
    )
    for (const [code, key] of Object.entries(KNOWN_API_ERROR_MESSAGES)) {
      expect(localizeApiError('en', code)).toBe(
        formatMessage('en', ...parameterFreeMessage(key)),
      )
      expect(localizeApiError('zh-CN', code)).toBe(
        formatMessage('zh-CN', ...parameterFreeMessage(key)),
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

  it('projects only local copy and bounded retry metadata', () => {
    const error = {
      code: 'CODEX_PAIR_RATE_LIMITED',
      requestId: 'req_pair_7',
      retryAfter: 7,
      get message(): never {
        throw new Error('server prose was read')
      },
    }

    expect(localizeApiErrorData('zh-CN', error)).toEqual({
      text: 'Codex 配对码请求过于频繁，请稍后重试。',
      code: technicalValue('CODEX_PAIR_RATE_LIMITED'),
      requestId: technicalValue('req_pair_7'),
      retryAfter: 7,
    })
  })

  it.each([0, -1, 1.5, 86_401, Number.NaN, '7', null])(
    'drops unsafe Retry-After value %s',
    (retryAfter) => {
      const localized = localizeApiErrorData('en', {
        code: 'CODEX_PAIR_RATE_LIMITED',
        retryAfter,
      })

      expect(localized).not.toHaveProperty('retryAfter')
    },
  )

  it('keeps unknown codes generic while retaining safe transport metadata', () => {
    expect(
      localizeApiErrorData('en', {
        code: 'UNPUBLISHED_SERVER_CODE',
        retryAfter: 86_400,
      }),
    ).toMatchObject({
      text: 'The operation could not be completed. Try again.',
      retryAfter: 86_400,
    })
  })
})
