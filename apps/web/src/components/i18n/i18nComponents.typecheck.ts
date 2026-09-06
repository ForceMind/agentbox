import type {
  LocalizedApiErrorProps,
  OpaqueUserValueProps,
  TechnicalValueProps,
} from './index'

/** Compile-only checks that callers cannot replace safe text with raw HTML. */
export function verifySafeTextProps(): void {
  const technical: TechnicalValueProps = {
    value: 'SAFE',
    // @ts-expect-error technical values cannot accept raw HTML
    dangerouslySetInnerHTML: { __html: 'unsafe' },
  }
  const opaque: OpaqueUserValueProps = {
    value: 'User',
    // @ts-expect-error user values cannot accept raw HTML
    dangerouslySetInnerHTML: { __html: 'unsafe' },
  }
  const error: LocalizedApiErrorProps = {
    error: { code: 'REQUEST_TIMEOUT' },
    // @ts-expect-error localized errors cannot accept raw HTML
    dangerouslySetInnerHTML: { __html: 'unsafe' },
  }

  void technical
  void opaque
  void error
}
