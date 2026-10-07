import { useMemo, useState } from 'react'
import { formatMessage, type Locale } from '../../i18n'
import { parseUnifiedDiff, type DiffRow } from './unifiedDiff'
import './VerifiedPatchView.css'

const KIND_LABEL = {
  context: 'changes.patchContext',
  added: 'changes.patchAdded',
  deleted: 'changes.patchDeleted',
  marker: 'changes.patchMarker',
} as const satisfies Record<DiffRow['kind'], `changes.${string}`>

// Mounted only beneath the existing completed owner. No independent content owner.
export function VerifiedPatchView({
  text,
  locale,
}: {
  text: string
  locale: Locale
}) {
  const parsed = useMemo(() => parseUnifiedDiff(text), [text])
  const [raw, setRaw] = useState(false)
  const [wrap, setWrap] = useState(true)
  const unified = parsed.kind === 'unified' && !raw
  return (
    <div className="verified-patch-view">
      <div
        className="diff-view-controls"
        role="group"
        aria-label={formatMessage(locale, 'changes.patchControls', {})}
      >
        {parsed.kind === 'unified' && (
          <>
            <button
              type="button"
              className="secondary-button"
              aria-pressed={!raw}
              onClick={() => setRaw(false)}
            >
              {formatMessage(locale, 'changes.patchUnified', {})}
            </button>
            <button
              type="button"
              className="secondary-button"
              aria-pressed={raw}
              onClick={() => setRaw(true)}
            >
              {formatMessage(locale, 'changes.patchRaw', {})}
            </button>
          </>
        )}
        <label>
          <input
            type="checkbox"
            checked={wrap}
            onChange={(event) => setWrap(event.target.checked)}
          />
          {formatMessage(locale, 'changes.patchWrap', {})}
        </label>
      </div>
      <p className="diff-view-note">
        {formatMessage(
          locale,
          parsed.kind === 'raw'
            ? parsed.reason === 'limit'
              ? 'changes.patchLimitFallback'
              : 'changes.patchFormatFallback'
            : 'changes.patchCoordinates',
          {},
        )}
      </p>
      {unified ? (
        <div
          className={`changes-patch diff-region${wrap ? '' : ' diff-no-wrap'}`}
          tabIndex={0}
          role="region"
          aria-label={formatMessage(locale, 'changes.patchUnifiedRegion', {})}
          data-testid="a3-complete-patch"
        >
          <pre className="diff-headers">{parsed.headers}</pre>
          <table
            className="unified-diff-table"
            data-testid="unified-diff-table"
          >
            <caption>
              {formatMessage(locale, 'changes.patchCaption', {})}
            </caption>
            <colgroup>
              <col className="diff-number-column" />
              <col className="diff-number-column" />
              <col />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">
                  {formatMessage(locale, 'changes.patchOldLine', {})}
                </th>
                <th scope="col">
                  {formatMessage(locale, 'changes.patchNewLine', {})}
                </th>
                <th scope="col">
                  {formatMessage(locale, 'changes.patchText', {})}
                </th>
              </tr>
            </thead>
            {parsed.hunks.map((hunk, index) => (
              <tbody key={index}>
                <tr className="diff-hunk">
                  <th scope="rowgroup" colSpan={3}>
                    {hunk.header}
                  </th>
                </tr>
                {hunk.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} data-kind={row.kind}>
                    <td
                      className="diff-line-number"
                      data-testid="diff-old-line"
                    >
                      {row.oldLine}
                    </td>
                    <td
                      className="diff-line-number"
                      data-testid="diff-new-line"
                    >
                      {row.newLine}
                    </td>
                    <td className="diff-line-text">
                      <span className="diff-kind-label">
                        {formatMessage(locale, KIND_LABEL[row.kind], {})}
                      </span>
                      <span data-testid="diff-line-text">{row.text}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      ) : (
        <pre
          className={`changes-patch${wrap ? '' : ' diff-no-wrap'}`}
          tabIndex={0}
          aria-label={formatMessage(locale, 'changes.patchRawRegion', {})}
          data-testid="a3-complete-patch"
        >
          {text}
        </pre>
      )}
    </div>
  )
}
