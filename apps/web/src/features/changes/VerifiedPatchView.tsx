import { useMemo, useState } from 'react'
import { parseUnifiedDiff } from './unifiedDiff'
import './VerifiedPatchView.css'

const KIND_LABEL = {
  context: '上下文',
  added: '增加',
  deleted: '删除',
  marker: '行尾说明',
}

// Mounted only beneath the existing completed owner. No independent content owner.
export function VerifiedPatchView({ text }: { text: string }) {
  const parsed = useMemo(() => parseUnifiedDiff(text), [text])
  const [raw, setRaw] = useState(false)
  const [wrap, setWrap] = useState(true)
  const unified = parsed.kind === 'unified' && !raw
  return (
    <div className="verified-patch-view">
      <div className="diff-view-controls" aria-label="补丁显示方式">
        {parsed.kind === 'unified' && (
          <>
            <button
              type="button"
              className="secondary-button"
              aria-pressed={!raw}
              onClick={() => setRaw(false)}
            >
              统一视图
            </button>
            <button
              type="button"
              className="secondary-button"
              aria-pressed={raw}
              onClick={() => setRaw(true)}
            >
              原文
            </button>
          </>
        )}
        <label>
          <input
            type="checkbox"
            checked={wrap}
            onChange={(event) => setWrap(event.target.checked)}
          />
          换行显示
        </label>
      </div>
      <p className="diff-view-note">
        {parsed.kind === 'raw'
          ? parsed.reason === 'limit'
            ? '超出统一视图的显示范围，已显示完整原文，未截断。'
            : '此补丁格式不支持统一视图，已显示完整原文，未截断。'
          : '行号仅为补丁声明的旧/新坐标；头部信息不证明仓库或源文件身份。'}
      </p>
      {unified ? (
        <div
          className={`changes-patch diff-region${wrap ? '' : ' diff-no-wrap'}`}
          tabIndex={0}
          role="region"
          aria-label="完整暂存补丁：统一视图"
          data-testid="a3-complete-patch"
        >
          <pre className="diff-headers">{parsed.headers}</pre>
          <table
            className="unified-diff-table"
            data-testid="unified-diff-table"
          >
            <caption>暂存补丁行：＋增加，−删除，空格为上下文</caption>
            <colgroup>
              <col className="diff-number-column" />
              <col className="diff-number-column" />
              <col />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">旧行</th>
                <th scope="col">新行</th>
                <th scope="col">补丁文本</th>
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
                        {KIND_LABEL[row.kind]}：{' '}
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
          aria-label="完整暂存补丁：原文"
          data-testid="a3-complete-patch"
        >
          {text}
        </pre>
      )}
    </div>
  )
}
