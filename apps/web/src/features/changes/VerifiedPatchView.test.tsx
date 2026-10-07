import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { VerifiedPatchView } from './VerifiedPatchView'

afterEach(cleanup)
const source =
  'diff --git a/f b/f\nindex 1111111..2222222 100644\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-旧\r\n+<img src=x onerror=alert(1)>\t🌍\r\n\\ No newline at end of file\n'
const locales = [
  {
    locale: 'zh-CN' as const,
    columns: ['旧行', '新行', '补丁文本'],
    context: '上下文：',
    added: '增加：',
    deleted: '删除：',
    marker: '行尾说明：',
    coordinates:
      '行号仅为补丁声明的旧/新坐标；头部信息不证明仓库或源文件身份。',
    controls: '补丁显示方式',
    wrap: '换行显示',
    raw: '原文',
    unified: '统一视图',
    unifiedRegion: '完整暂存补丁：统一视图',
    rawRegion: '完整暂存补丁：原文',
    caption: '暂存补丁行：＋增加，−删除，空格为上下文',
    format: '此补丁格式不支持统一视图，已显示完整原文，未截断。',
    limit: '超出统一视图的显示范围，已显示完整原文，未截断。',
  },
  {
    locale: 'en' as const,
    columns: ['Old line', 'New line', 'Patch text'],
    context: 'Context:',
    added: 'Added:',
    deleted: 'Deleted:',
    marker: 'Line ending note:',
    coordinates:
      'Line numbers are old/new coordinates declared by the patch. Headers do not prove repository or source file identity.',
    controls: 'Patch display',
    wrap: 'Wrap lines',
    raw: 'Raw text',
    unified: 'Unified view',
    unifiedRegion: 'Complete staged patch: unified view',
    rawRegion: 'Complete staged patch: raw text',
    caption: 'Staged patch lines: + added, − deleted, space for context',
    format:
      'This patch format is not supported by the unified view. The complete original text is shown without truncation.',
    limit:
      'This patch exceeds the unified view display limits. The complete original text is shown without truncation.',
  },
]
describe.each(locales)('completed-owner inert diff view ($locale)', (copy) => {
  it('renders semantic columns, hunk rows and explicit kinds without source-generated elements', () => {
    render(<VerifiedPatchView text={source} locale={copy.locale} />)
    expect(screen.getByTestId('unified-diff-table').tagName).toBe('TABLE')
    expect(screen.getByRole('table', { name: copy.caption })).toBeVisible()
    expect(screen.getByRole('group', { name: copy.controls })).toBeVisible()
    for (const name of copy.columns)
      expect(screen.getByRole('columnheader', { name })).toBeVisible()
    expect(screen.getByText('@@ -1 +1 @@')).toBeVisible()
    expect(
      screen.getAllByTestId('diff-line-text').map((node) => node.textContent),
    ).toEqual([
      '-旧\r',
      '+<img src=x onerror=alert(1)>\t🌍\r',
      '\\ No newline at end of file',
    ])
    expect(
      screen.getAllByTestId('diff-old-line').map((node) => node.textContent),
    ).toEqual(['1', '', ''])
    expect(
      screen.getAllByTestId('diff-new-line').map((node) => node.textContent),
    ).toEqual(['', '1', ''])
    expect(
      screen
        .getByTestId('a3-complete-patch')
        .querySelector('img,script,svg,a,iframe'),
    ).toBeNull()
    expect(screen.getByText(copy.added)).toBeInTheDocument()
    expect(screen.getByText(copy.deleted)).toBeInTheDocument()
    expect(screen.getByText(copy.marker)).toBeInTheDocument()
    expect(screen.getByText(copy.coordinates)).toBeVisible()
    expect(screen.getByRole('region', { name: copy.unifiedRegion })).toBe(
      screen.getByTestId('a3-complete-patch'),
    )
    expect(screen.getByTestId('a3-complete-patch')).toHaveAttribute(
      'tabindex',
      '0',
    )
  })
  it('keeps context prefix, whitespace and both patch-declared coordinates', () => {
    render(
      <VerifiedPatchView
        locale={copy.locale}
        text={source.replace(
          '@@ -1 +1 @@\n',
          '@@ -1,2 +1,2 @@\n same\tvalue\r\n',
        )}
      />,
    )
    expect(screen.getByText(copy.context)).toBeInTheDocument()
    expect(screen.getAllByTestId('diff-line-text')[0].textContent).toBe(
      ' same\tvalue\r',
    )
    expect(screen.getAllByTestId('diff-old-line')[0].textContent).toBe('1')
    expect(screen.getAllByTestId('diff-new-line')[0].textContent).toBe('1')
  })
  it('repeated view/wrap switches preserve exactly the original string, without retaining hidden raw DOM', () => {
    const result = render(
      <VerifiedPatchView text={source} locale={copy.locale} />,
    )
    const wrap = screen.getByRole('checkbox', { name: copy.wrap })
    expect(wrap).toBeChecked()
    for (let attempt = 0; attempt < 3; attempt++) {
      fireEvent.click(screen.getByRole('button', { name: copy.raw }))
      expect(screen.getByRole('button', { name: copy.raw })).toHaveAttribute(
        'aria-pressed',
        'true',
      )
      expect(screen.getByTestId('a3-complete-patch').textContent).toBe(source)
      expect(screen.getByLabelText(copy.rawRegion)).toBe(
        screen.getByTestId('a3-complete-patch'),
      )
      expect(screen.queryByTestId('unified-diff-table')).toBeNull()
      fireEvent.click(wrap)
      expect(screen.getByTestId('a3-complete-patch')).toHaveClass(
        'diff-no-wrap',
      )
      fireEvent.click(wrap)
      fireEvent.click(screen.getByRole('button', { name: copy.unified }))
      expect(
        screen.getByRole('button', { name: copy.unified }),
      ).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByTestId('unified-diff-table')).toBeVisible()
    }
    result.unmount()
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(document.body.textContent).not.toContain('onerror')
  })
  it.each([
    {
      text: 'legacy plain <svg/onload=alert(1)>\r\n\t🌍',
      reason: 'format' as const,
    },
    { text: source.replace('+<img', '+\0<img'), reason: 'format' as const },
    {
      text: source.replace('@@ -1 +1 @@', '@@ -1,2 +1 @@'),
      reason: 'format' as const,
    },
    { text: 'x'.repeat(8193) + '\r\nEND', reason: 'limit' as const },
    { text: '🌍'.repeat(70000) + '\r\nEND', reason: 'limit' as const },
  ])(
    'shows complete exact fallback without unified controls ($reason) %#',
    ({ text, reason }) => {
      render(<VerifiedPatchView text={text} locale={copy.locale} />)
      expect(screen.getByTestId('a3-complete-patch').textContent).toBe(text)
      expect(screen.getByText(copy[reason])).toBeVisible()
      expect(screen.getByLabelText(copy.rawRegion)).toHaveAttribute(
        'tabindex',
        '0',
      )
      expect(screen.queryByRole('button', { name: copy.unified })).toBeNull()
      expect(screen.queryByTestId('unified-diff-table')).toBeNull()
      expect(
        screen
          .getByTestId('a3-complete-patch')
          .querySelector('img,script,svg,a'),
      ).toBeNull()
    },
  )
})
