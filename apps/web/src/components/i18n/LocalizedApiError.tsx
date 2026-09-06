import type { HTMLAttributes } from 'react'

import {
  currentLocale,
  formatMessage,
  localizeApiErrorData,
  type Locale,
} from '../../i18n'
import { TechnicalValue } from './TechnicalValue'
import type { RawHtmlProperty } from './rawHtmlProperty'

export interface LocalizableApiError {
  readonly code: string
  readonly requestId?: string
  readonly retryAfter?: number
}

export interface LocalizedApiErrorProps extends Omit<
  HTMLAttributes<HTMLSpanElement>,
  'children' | RawHtmlProperty
> {
  readonly error: LocalizableApiError
  readonly locale?: Locale
  readonly showCode?: boolean
  readonly showRequestId?: boolean
}

/**
 * Maps only stable machine fields to display content. The structural error type
 * intentionally excludes `message`, so server prose cannot become a fallback.
 */
export function LocalizedApiError({
  error,
  locale = currentLocale(),
  role,
  showCode = true,
  showRequestId = true,
  ...props
}: LocalizedApiErrorProps) {
  const localized = localizeApiErrorData(locale, error)
  const code = showCode ? localized.code : null
  const requestId = showRequestId ? localized.requestId : null

  return (
    <span {...props} role={role ?? 'alert'}>
      <span>{localized.text}</span>
      {code ? (
        <span>
          {' '}
          {formatMessage(locale, 'error.codeLabel', {})}:{' '}
          <TechnicalValue value={code.value} />
        </span>
      ) : null}
      {requestId ? (
        <span>
          {' '}
          {formatMessage(locale, 'error.requestIdLabel', {})}:{' '}
          <TechnicalValue value={requestId.value} />
        </span>
      ) : null}
    </span>
  )
}
