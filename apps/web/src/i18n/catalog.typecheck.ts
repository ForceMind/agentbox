import { formatMessage, type MessageKey } from './catalog'

/** Compile-only checks that guard interpolation and empty-parameter contracts. */
export function verifyMessageParameterTypes(): void {
  formatMessage('en', 'common.close', {})
  formatMessage('en', 'document.title', { title: 'Dashboard' })

  // @ts-expect-error parameterized messages require their declared value
  formatMessage('en', 'document.title', {})
  // @ts-expect-error parameterized messages reject a different value name
  formatMessage('en', 'document.title', { label: 'Dashboard' })
  // @ts-expect-error parameter-free messages reject arbitrary values
  formatMessage('en', 'common.close', { sourceText: 'Close' })

  const dynamicKey = 'common.close' as MessageKey
  // @ts-expect-error a runtime-wide key cannot discard its parameter correlation
  formatMessage('en', dynamicKey, {})

  const dynamicMessage =
    Date.now() > 0
      ? (['common.close', {}] as const)
      : (['document.title', { title: 'Dashboard' }] as const)
  formatMessage('en', ...dynamicMessage)
}
