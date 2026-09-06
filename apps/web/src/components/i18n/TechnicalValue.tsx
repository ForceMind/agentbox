import type { ComponentPropsWithoutRef } from 'react'

import { technicalValue } from '../../i18n'
import type { RawHtmlProperty } from './rawHtmlProperty'

export interface TechnicalValueProps extends Omit<
  ComponentPropsWithoutRef<'bdi'>,
  'children' | RawHtmlProperty | 'dir' | 'lang' | 'translate'
> {
  readonly value: string
}

/** Renders validated protocol data in a fixed English, LTR text boundary. */
export function TechnicalValue({ value, ...props }: TechnicalValueProps) {
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
}
