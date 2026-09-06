import type { ComponentPropsWithoutRef, ReactNode } from 'react'

import { technicalValue } from '../../i18n'
import type { RawHtmlProperty } from './rawHtmlProperty'

export interface SafeTechnicalValueProps extends Omit<
  ComponentPropsWithoutRef<'bdi'>,
  'children' | RawHtmlProperty | 'dir' | 'lang' | 'translate'
> {
  readonly fallback: ReactNode
  readonly value: unknown
}

/**
 * Renders external protocol text only after the fixed printable-ASCII check.
 * Invalid or missing values use caller-owned localized fallback copy instead
 * of throwing or presenting the original external value.
 */
export function SafeTechnicalValue({
  fallback,
  value,
  ...props
}: SafeTechnicalValueProps) {
  if (typeof value !== 'string') return <>{fallback}</>

  try {
    const technical = technicalValue(value)
    return (
      <bdi
        {...props}
        dir={technical.dir}
        lang={technical.lang}
        translate={technical.translate}
      >
        {technical.value}
      </bdi>
    )
  } catch {
    return <>{fallback}</>
  }
}
