import { useEffect } from 'react'

import { currentLocale, formatMessage } from '../i18n'

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = formatMessage(currentLocale(), 'document.title', { title })
  }, [title])
}
