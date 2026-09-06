import type { ComponentPropsWithoutRef } from 'react'

export interface OpaqueUserValueProps extends Omit<
  ComponentPropsWithoutRef<'bdi'>,
  'children' | 'dangerouslySetInnerHTML' | 'dir' | 'translate'
> {
  readonly value: string
}

/**
 * Renders an untranslated user or Project name as Unicode text. It deliberately
 * does not use the printable-ASCII technical-value validator.
 */
export function OpaqueUserValue({ value, ...props }: OpaqueUserValueProps) {
  return (
    <bdi {...props} dir="auto" translate="no">
      {value}
    </bdi>
  )
}
