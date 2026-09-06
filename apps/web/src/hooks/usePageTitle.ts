import { useEffect } from 'react'

import { currentLocale, formatMessage, type MessageArguments } from '../i18n'

export function usePageTitle(title: string): void
export function usePageTitle(...message: MessageArguments): void
export function usePageTitle(
  ...arguments_: readonly [title: string] | MessageArguments
) {
  const locale = currentLocale()
  const title =
    arguments_.length === 1
      ? arguments_[0]
      : formatMessage(locale, ...(arguments_ as MessageArguments))
  const documentTitle = formatMessage(locale, 'document.title', { title })

  useEffect(() => {
    document.title = documentTitle
  }, [documentTitle])
}
